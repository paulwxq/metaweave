"""LLM 辅助关联关系发现。

数据来源：
- LLM 调用：从 json 文件读取表元数据，不查询数据库
- 评分阶段：复用 RelationshipScorer，需要数据库连接
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from itertools import combinations, product
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional

from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.relationships.models import Relation
from metaweave.core.relationships.repository import MetadataRepository
from metaweave.core.relationships.scorer import RelationshipScorer
from metaweave.core.relationships.name_similarity import NameSimilarityService
from metaweave.services.llm_service import LLMService
from metaweave.utils.file_utils import get_project_root
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.llm_discovery")


# LLM 提示词
RELATIONSHIP_DISCOVERY_PROMPT = """
你是一个数据库关系分析专家。请分析以下两个表以及表中的采样数据，判断它们之间是否存在关联关系。

## 表 1: {table1_name}
```json
{table1_json}
```

## 表 2: {table2_name}
```json
{table2_json}
```

## 任务
分析这两个表之间可能的关联关系（外键关系）。考虑以下因素：
1. 字段名相同或相似
2. 数据类型兼容
3. 字段注释的语义关联
4. 样例数据的值域匹配
5. 复合键的可能性（多个字段组合）

## 输出格式
返回 JSON 格式。如果存在关联，返回关联信息；如果没有关联，返回空数组。

**重要约定**：
- `from_table`: 外键表（多的一端，引用方）
- `from_column(s)`: 外键列
- `to_table`: 主键/唯一键表（一的一端，被引用方）
- `to_column(s)`: 主键/唯一键列

### 单列关联示例
```json
{{
  "relationships": [
    {{
      "type": "single_column",
      "from_table": {{"schema": "public", "table": "dim_store"}},
      "from_column": "region_id",
      "to_table": {{"schema": "public", "table": "dim_region"}},
      "to_column": "region_id"
    }}
  ]
}}
```
说明：dim_store.region_id（外键）引用 dim_region.region_id（主键）

### 多列关联示例（type 为 composite，字段用数组）
```json
{{
  "relationships": [
    {{
      "type": "composite",
      "from_table": {{"schema": "public", "table": "maintenance_work_order"}},
      "from_columns": ["equipment_id", "config_version"],
      "to_table": {{"schema": "public", "table": "equipment_config"}},
      "to_columns": ["equipment_id", "config_version"]
    }}
  ]
}}
```
说明：work_order 的复合字段（外键）引用 equipment_config 的复合主键

### 无关联
```json
{{
  "relationships": []
}}
```

请只返回 JSON，不要包含其他内容。
"""


def _parse_domain_filter(domain: Optional[str]) -> Optional[List[str]]:
    if not domain:
        return None
    if domain.lower() == "all":
        return ["all"]
    return [d.strip() for d in domain.split(",") if d.strip()]


def _group_tables_by_domain(
    tables: Dict[str, Dict],
    domain_filter: Optional[List[str]],
    all_domains: List[str],
) -> Dict[str, List[str]]:
    if not domain_filter or "all" in domain_filter:
        target_domains = all_domains.copy()
    else:
        target_domains = domain_filter.copy()

    domain_tables: Dict[str, List[str]] = {}
    for full_name, data in tables.items():
        table_domains = data.get("table_profile", {}).get("table_domains", [])
        for d in table_domains:
            if d in target_domains:
                domain_tables.setdefault(d, []).append(full_name)
    return domain_tables


def generate_all_pairs(tables: Dict[str, Dict]) -> List[Tuple[str, str]]:
    return list(combinations(tables.keys(), 2))


def generate_intra_domain_pairs(
    tables: Dict[str, Dict],
    domain_filter: Optional[List[str]],
    all_domains: List[str],
) -> List[Tuple[str, str]]:
    domain_tables = _group_tables_by_domain(tables, domain_filter, all_domains)
    pairs: List[Tuple[str, str]] = []
    for table_list in domain_tables.values():
        pairs.extend(combinations(table_list, 2))
    return pairs


def generate_cross_domain_pairs(
    tables: Dict[str, Dict],
    domain_filter: Optional[List[str]],
    all_domains: List[str],
    intra_pairs: List[Tuple[str, str]] = None,
) -> List[Tuple[str, str]]:
    domain_tables = _group_tables_by_domain(tables, domain_filter, all_domains)
    processed = set(intra_pairs or [])
    pairs: List[Tuple[str, str]] = []
    domain_list = list(domain_tables.keys())

    for i, d1 in enumerate(domain_list):
        for d2 in domain_list[i + 1 :]:
            for t1, t2 in product(domain_tables[d1], domain_tables[d2]):
                if t1 == t2:
                    continue
                pair = tuple(sorted([t1, t2]))
                if pair not in processed:
                    pairs.append(pair)
                    processed.add(pair)
    return pairs


def get_table_pairs(
    tables: Dict[str, Dict],
    domain: Optional[str],
    cross_domain: bool,
    all_domains: List[str],
) -> List[Tuple[str, str]]:
    domain_filter = _parse_domain_filter(domain)
    if not domain and not cross_domain:
        return generate_all_pairs(tables)
    if domain and not cross_domain:
        return generate_intra_domain_pairs(tables, domain_filter, all_domains)
    if domain and cross_domain:
        intra_pairs = generate_intra_domain_pairs(tables, domain_filter, all_domains)
        cross_pairs = generate_cross_domain_pairs(
            tables, domain_filter, all_domains, intra_pairs=intra_pairs
        )
        return intra_pairs + cross_pairs
    if not domain and cross_domain:
        return generate_cross_domain_pairs(tables, None, all_domains, intra_pairs=[])
    return []


class LLMRelationshipDiscovery:
    """LLM 辅助关联关系发现

    数据来源：
    - LLM 调用：从 json 文件读取表元数据，不查询数据库
    - 评分阶段：复用 RelationshipScorer，需要数据库连接
    """
    
    def __init__(
        self,
        config: Dict,
        connector: DatabaseConnector,
        domain_filter: Optional[str] = None,
        cross_domain: bool = False,
        db_domains_config: Optional[Dict] = None,
    ):
        self.config = config
        self.connector = connector  # 仅用于评分阶段

        # 构造关系配置（兼容混合结构）
        self.rel_config = config.get("relationships", {}).copy()
        for key in ["single_column", "composite", "decision", "weights"]:
            if key in config and key not in self.rel_config:
                self.rel_config[key] = config[key]
        # 关系评分阶段的数据库采样行数上限：统一使用 sampling.sample_size
        self.rel_config["sample_size"] = config.get("sampling", {}).get("sample_size", 1000)

        # 初始化名称相似度服务
        embedding_config = config.get("embedding", {})
        name_sim_config = self.rel_config.get("name_similarity", {})
        if (name_sim_config.get("method") or "string").lower() != "string":
            self.name_similarity_service = NameSimilarityService(name_sim_config, embedding_config)
        else:
            self.name_similarity_service = None

        self.scorer = RelationshipScorer(self.rel_config, connector, self.name_similarity_service)

        llm_config = config.get("llm", {})
        self.llm_service = LLMService(llm_config)

        output_config = config.get("output", {})
        # 路径解析逻辑与 RelationshipDiscoveryPipeline 保持一致
        # 使用 get_project_root() 确保在非项目根目录执行时行为一致
        json_directory = output_config.get("json_directory")
        if json_directory:
            self.json_dir = get_project_root() / json_directory
        else:
            # Fallback: 从 output_dir 推导
            output_dir = output_config.get("output_dir", "output")
            self.json_dir = get_project_root() / output_dir / "json"
        
        # 读取 rel_id_salt 配置（与现有管道保持一致）
        rel_id_salt = output_config.get("rel_id_salt", "")
        
        # 复用 MetadataRepository 提取物理外键（包含 cardinality、relationship_id）
        self.repo = MetadataRepository(self.json_dir, rel_id_salt=rel_id_salt)
        
        # 读取决策阈值配置
        decision_config = self.rel_config.get("decision", {})
        self.accept_threshold = decision_config.get("accept_threshold", 0.65)
        self.high_confidence_threshold = decision_config.get("high_confidence_threshold", 0.90)
        self.medium_confidence_threshold = decision_config.get("medium_confidence_threshold", 0.80)

        # 读取语义角色排除配置（用于过滤目标列）
        self.single_exclude_roles = set(config.get("single_column", {}).get("exclude_semantic_roles", []))
        self.composite_exclude_roles = set(config.get("composite", {}).get("exclude_semantic_roles", []))

        # 读取 LLM 重试配置
        self.llm_max_retries = llm_config.get("retry_times", 2)
        self.llm_retry_delay = llm_config.get("retry_delay", 1)  # 重试延迟（秒）

        langchain_config = llm_config.get("langchain_config", {})
        self.use_async = langchain_config.get("use_async", False)
        self.batch_size = max(1, int(langchain_config.get("batch_size", 50) or 50))

        logger.info(
            f"阈值配置: accept={self.accept_threshold}, "
            f"high={self.high_confidence_threshold}, "
            f"medium={self.medium_confidence_threshold}"
        )
        logger.info(
            "LLM 异步配置: use_async=%s, batch_size=%s",
            self.use_async,
            self.batch_size,
        )
        logger.info(
            f"LLM 重试配置: max_retries={self.llm_max_retries}, "
            f"retry_delay={self.llm_retry_delay}s"
        )
        # Domain 相关
        self.domain_filter = domain_filter
        self.cross_domain = cross_domain
        self.db_domains_config = db_domains_config or {}
        
    def discover(self) -> tuple[List[Relation], int, Dict[str, Any]]:
        """同步入口：发现关联关系。

        Returns:
            (关系列表, 被拒绝数量, 额外统计信息)
        """

        start_time = time.time()
        logger.info("=" * 60)
        logger.info("开始 LLM 辅助关联关系发现")
        logger.info("=" * 60)

        tables, fk_relation_objects, fk_relationship_ids = self._load_tables_and_foreign_keys()

        logger.info("阶段3: 两两组合调用 LLM")
        if self.domain_filter or self.cross_domain:
            self._validate_table_domains(tables)
            all_domains = [d["name"] for d in self.db_domains_config.get("domains", [])]
            table_pairs = get_table_pairs(
                tables=tables,
                domain=self.domain_filter,
                cross_domain=self.cross_domain,
                all_domains=all_domains,
            )
        else:
            table_pairs = list(combinations(tables.keys(), 2))

        total_pairs = len(table_pairs)
        logger.info(f"共 {total_pairs} 个表对需要处理")

        if self.use_async:
            logger.info(f"阶段3: 异步并发调用 LLM (分批大小={self.batch_size})")
            llm_candidates = self._run_async(
                self._discover_llm_candidates_async(tables, table_pairs)
            )
        else:
            logger.info("阶段3: 同步串行调用 LLM")
            llm_candidates = self._discover_llm_candidates_sync(tables, table_pairs)

        logger.info(f"LLM 返回候选: {len(llm_candidates)} 个")

        return self._finalize_relations(
            tables,
            fk_relation_objects,
            fk_relationship_ids,
            llm_candidates,
            start_time,
        )

    async def discover_async(self) -> tuple[List[Relation], int, Dict[str, Any]]:
        """异步入口，适用于已有事件循环的环境。

        Returns:
            (关系列表, 被拒绝数量, 额外统计信息)
        """

        start_time = time.time()
        logger.info("=" * 60)
        logger.info("开始 LLM 辅助关联关系发现 (async)")
        logger.info("=" * 60)

        tables, fk_relation_objects, fk_relationship_ids = self._load_tables_and_foreign_keys()

        logger.info("阶段3: 两两组合调用 LLM")
        if self.domain_filter or self.cross_domain:
            self._validate_table_domains(tables)
            all_domains = [d["name"] for d in self.db_domains_config.get("domains", [])]
            table_pairs = get_table_pairs(
                tables=tables,
                domain=self.domain_filter,
                cross_domain=self.cross_domain,
                all_domains=all_domains,
            )
        else:
            table_pairs = list(combinations(tables.keys(), 2))
        total_pairs = len(table_pairs)
        logger.info(f"共 {total_pairs} 个表对需要处理")

        if self.use_async:
            logger.info(f"阶段3: 异步并发调用 LLM (分批大小={self.batch_size})")
            llm_candidates = await self._discover_llm_candidates_async(tables, table_pairs)
        else:
            logger.info("阶段3: 同步串行调用 LLM")
            llm_candidates = self._discover_llm_candidates_sync(tables, table_pairs)

        logger.info(f"LLM 返回候选: {len(llm_candidates)} 个")

        return self._finalize_relations(
            tables,
            fk_relation_objects,
            fk_relationship_ids,
            llm_candidates,
            start_time,
        )
    
    def _load_tables_and_foreign_keys(self):
        logger.info(f"阶段1: 加载 json 文件，目录: {self.json_dir}")
        tables = self._load_all_tables()
        logger.info(f"已加载 {len(tables)} 张表的元数据")

        logger.info("阶段2: 提取物理外键")
        fk_relation_objects, fk_relationship_ids = self.repo.collect_foreign_keys(tables)
        logger.info(f"物理外键直通: {len(fk_relation_objects)} 个")

        # 缓存 tables，供 CLI 传给 RelationshipWriter
        self.tables = tables

        return tables, fk_relation_objects, fk_relationship_ids

    def _validate_table_domains(self, tables: Dict) -> None:
        """校验所有表是否包含 table_domains 属性，缺失则报错退出。"""
        missing_tables = []
        for full_name, data in tables.items():
            table_profile = data.get("table_profile", {})
            if "table_domains" not in table_profile:
                missing_tables.append(full_name)

        if missing_tables:
            logger.error(
                "以下表的 JSON 文件缺少 table_domains 属性，"
                "请先执行 --step json --domain 生成："
            )
            for table in missing_tables:
                logger.error(f"  - {table}")
            raise ValueError(
                f"发现 {len(missing_tables)} 个表缺少 table_domains 属性，"
                "无法按 domain 进行关系发现"
            )

    def _discover_llm_candidates_sync(
        self,
        tables: Dict[str, Dict],
        table_pairs: List[Tuple[str, str]],
    ) -> List[Dict]:
        llm_candidates: List[Dict] = []
        for i, (table1_name, table2_name) in enumerate(table_pairs):
            logger.debug(
                "处理表对 [%s/%s]: %s <-> %s",
                i + 1,
                len(table_pairs),
                table1_name,
                table2_name,
            )

            candidates = self._call_llm(tables[table1_name], tables[table2_name])
            llm_candidates.extend(candidates)

            if (i + 1) % 10 == 0:
                logger.info(f"LLM 调用进度: {i + 1}/{len(table_pairs)}")

        return llm_candidates

    async def _discover_llm_candidates_async(
        self,
        tables: Dict[str, Dict],
        table_pairs: List[Tuple[str, str]],
    ) -> List[Dict]:
        total_pairs = len(table_pairs)
        if total_pairs == 0:
            return []

        llm_candidates: List[Dict] = []
        progress_step = max(1, total_pairs // 5)

        for batch_start in range(0, total_pairs, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_pairs)
            batch_pairs = table_pairs[batch_start:batch_end]
            batch_num = batch_start // self.batch_size + 1
            logger.info(
                "处理批次 %s: 表对 %s-%s/%s",
                batch_num,
                batch_start + 1,
                batch_end,
                total_pairs,
            )

            batch_prompts = [
                self._build_prompt(tables[t1], tables[t2])
                for t1, t2 in batch_pairs
            ]

            def on_progress(completed: int, total: int):
                global_completed = batch_start + completed
                if completed == total or global_completed % progress_step == 0:
                    logger.info(
                        "LLM 调用进度: %s/%s",
                        global_completed,
                        total_pairs,
                    )
                else:
                    logger.debug(
                        "LLM 调用完成: %s/%s",
                        global_completed,
                        total_pairs,
                    )

            results = await self.llm_service.batch_call_llm_async(
                batch_prompts,
                on_progress=on_progress,
            )

            pair_by_idx = dict(enumerate(batch_pairs))
            for idx, response in results:
                t1, t2 = pair_by_idx[idx]
                if response:
                    candidates = self._parse_llm_response(response)
                    llm_candidates.extend(candidates)
                else:
                    logger.warning(f"表对 {t1} <-> {t2} 无响应")

            del batch_prompts
            del pair_by_idx

        return llm_candidates

    def _build_prompt(self, table1: Dict, table2: Dict) -> str:
        table1_info = table1.get("table_info", {})
        table2_info = table2.get("table_info", {})
        table1_name = f"{table1_info['schema_name']}.{table1_info['table_name']}"
        table2_name = f"{table2_info['schema_name']}.{table2_info['table_name']}"

        return RELATIONSHIP_DISCOVERY_PROMPT.format(
            table1_name=table1_name,
            table1_json=json.dumps(table1, ensure_ascii=False, indent=2),
            table2_name=table2_name,
            table2_json=json.dumps(table2, ensure_ascii=False, indent=2),
        )

    def _run_async(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError(
            "检测到已存在运行中的事件循环。"
            "请改用 await discovery.discover_async() 或在 CLI 层调用 asyncio.run()."
        )

    def _filter_by_semantic_roles(
        self,
        candidates: List[Dict],
        tables: Dict[str, Dict]
    ) -> List[Dict]:
        """按语义角色过滤候选关系

        过滤范围说明：
        - 仅过滤目标列（to_cols），与 rel 保持一致
        - 源列（from_cols）不做语义过滤（理由：与 rel 的过滤侧保持一致，rel 只过滤目标列）

        过滤规则（优先级从高到低）：
        1. 物理约束目标列（PK/UK/索引）：不过滤语义角色
        2. 非物理约束目标列中，Complex 类型列：永远过滤（即使同名）
        3. 非物理约束目标列中，同名列：不过滤其他语义角色
        4. 其他目标列：按 exclude_semantic_roles 配置过滤

        Args:
            candidates: LLM 返回的候选关系
            tables: 表元数据字典（schema.table -> table_json）

        Returns:
            过滤后的候选关系
        """
        # 建立大小写不敏感的表key映射（避免LLM返回大小写不一致导致误判元数据缺失）
        # 假设前提：同一数据库内 schema.table 组合大小写不敏感且无冲突（PostgreSQL 标识符不区分大小写）
        # 已知限制：如果存在 "Public"."Foo" 和 "public"."foo" 两个不同表（极少见但理论可能），lower() 键会发生覆盖
        # 本次实现：不处理该极端情况（直接使用 lower() 映射）
        table_key_map = {
            table_key.lower(): table_json
            for table_key, table_json in tables.items()
        }

        filtered = []
        skipped_count = 0

        for candidate in candidates:
            candidate_type = candidate["type"]

            # 根据候选类型选择过滤规则
            if candidate_type == "single_column":
                from_cols = [candidate["from_column"]]
                to_cols = [candidate["to_column"]]
                exclude_roles = self.single_exclude_roles
            else:  # composite
                from_cols = candidate["from_columns"]
                to_cols = candidate["to_columns"]
                exclude_roles = self.composite_exclude_roles

            # 检查目标列（仅过滤目标列，与 rel 一致）
            should_skip = False
            to_table_key = f"{candidate['to_table']['schema']}.{candidate['to_table']['table']}"
            # 使用大小写不敏感查找（避免LLM返回大小写不一致导致误判）
            to_table_json = table_key_map.get(to_table_key.lower())

            if not to_table_json:
                logger.warning(f"[filter_semantic_roles] 目标表 {to_table_key} 元数据缺失，跳过候选")
                # 预期丢弃：元数据缺失的候选无法进行后续评分，此处提前过滤
                continue

            # 判断是否同名（大小写不敏感）
            if candidate_type == "single_column":
                is_same_name = (from_cols[0].lower() == to_cols[0].lower())
            else:  # composite
                # 复合键同名定义：对应位置逐列同名（大小写不敏感）
                # 例如：["a","b"] vs ["A","B"] 是同名，但 ["a","b"] vs ["b","a"] 不是同名（位置不对应）
                is_same_name = (
                    len(from_cols) == len(to_cols) and
                    all(f.lower() == t.lower() for f, t in zip(from_cols, to_cols))
                )

            # 建立大小写不敏感的列名映射（用于查找列画像）
            # 注意：LLM 返回的列名大小写可能与 column_profiles 不一致
            # 假设前提：同一表内列名大小写不敏感且无冲突（PostgreSQL 列名不区分大小写，极少出现 Foo/foo 同时存在）
            # 已知限制：如果同表存在 "Foo" 和 "foo" 两列（极少见但理论可能），lower() 键会发生覆盖
            # 本次实现：不处理该极端情况（直接使用 lower() 映射）
            col_profile_map = {
                col_name.lower(): col_profile
                for col_name, col_profile in to_table_json.get("column_profiles", {}).items()
            }

            for to_col in to_cols:
                # 获取目标列画像（大小写不敏感查找）
                col_profile = col_profile_map.get(to_col.lower())
                if not col_profile:
                    # 目标列画像缺失：预期丢弃该候选
                    # 原因：缺失画像会导致后续评分阶段 type_compatibility 误判（可能被算成 1.0）
                    logger.debug(
                        f"[filter_semantic_roles] 跳过候选（目标列 {to_col} 画像缺失）: "
                        f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
                    )
                    should_skip = True
                    skipped_count += 1
                    break

                # 优先级 1: 检查是否为物理约束列
                structure_flags = col_profile.get("structure_flags", {})
                is_physical = (
                    structure_flags.get("is_primary_key") or
                    structure_flags.get("is_unique") or
                    structure_flags.get("is_unique_constraint") or
                    structure_flags.get("is_indexed")
                )

                if is_physical:
                    continue  # 物理约束列不过滤

                # 获取语义角色
                semantic_role = col_profile.get("semantic_analysis", {}).get("semantic_role")

                # 优先级 2: Complex 永远过滤（即使同名）
                if semantic_role == "complex":
                    logger.debug(
                        f"[filter_semantic_roles] 跳过候选（目标列 {to_col} 为 complex，即使同名也过滤）: "
                        f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
                    )
                    should_skip = True
                    skipped_count += 1
                    break

                # 优先级 3: 同名列不过滤其他语义角色
                if is_same_name:
                    continue  # 同名列跳过语义角色检查

                # 优先级 4: 其他列按配置过滤
                if semantic_role in exclude_roles:
                    logger.debug(
                        f"[filter_semantic_roles] 跳过候选（目标列 {to_col} 为 {semantic_role}）: "
                        f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
                    )
                    should_skip = True
                    skipped_count += 1
                    break

            if not should_skip:
                filtered.append(candidate)

        logger.info(
            f"[filter_semantic_roles] 过滤前: {len(candidates)}, 过滤后: {len(filtered)}, "
            f"跳过: {skipped_count}"
        )
        return filtered

    def _finalize_relations(
        self,
        tables: Dict[str, Dict],
        fk_relation_objects: List[Relation],
        fk_relationship_ids: Set[str],
        llm_candidates: List[Dict],
        start_time: float,
    ) -> tuple[List[Relation], int, Dict[str, Any]]:
        """完成关系发现，返回 Relation 对象列表和统计信息

        Returns:
            (关系列表, 被拒绝数量, 额外统计信息)
        """
        logger.info("阶段4: 过滤已有物理外键（基于 relationship_id）")
        filtered_candidates = self._filter_existing_fks(llm_candidates, fk_relationship_ids)
        skipped_fk_count = len(llm_candidates) - len(filtered_candidates)
        logger.info(
            "过滤后候选: %s 个 (已跳过 %s 个物理外键)",
            len(filtered_candidates),
            skipped_fk_count,
        )

        # 新增：阶段 4.5: 按语义角色过滤
        logger.info("阶段4.5: 按语义角色过滤（exclude_semantic_roles）")
        filtered_candidates = self._filter_by_semantic_roles(filtered_candidates, tables)

        score_start = time.time()
        logger.info("阶段5: 对候选关联进行评分")
        scored_relations = self._score_candidates(filtered_candidates, tables)
        score_duration = time.time() - score_start
        logger.info(
            "评分后关系: %s 个 (耗时: %.2f秒, 节省了 %s 个物理外键的评分计算)",
            len(scored_relations),
            score_duration,
            skipped_fk_count,
        )

        logger.info(f"阶段6: 阈值过滤 (threshold={self.accept_threshold})")
        accepted_relations_dict, rejected_relations = self._filter_by_threshold(scored_relations)
        logger.info(f"过滤后接受: {len(accepted_relations_dict)} 个")

        logger.info("阶段7: 合并物理外键和推断关系")
        # 将接受的 dict 格式关系转换为 Relation 对象
        accepted_relation_objects = [self._dict_to_relation(rel) for rel in accepted_relations_dict]

        before_dedup_count = len(fk_relation_objects) + len(accepted_relation_objects)
        all_relations = self._deduplicate_by_relationship_id(fk_relation_objects, accepted_relation_objects)

        if before_dedup_count > len(all_relations):
            dup_count = before_dedup_count - len(all_relations)
            logger.warning(
                "⚠️ 阶段7发现 %s 个重复关系（阶段4可能遗漏），已去重。",
                dup_count,
            )
        else:
            logger.debug("✓ 阶段7未发现重复，阶段4去重有效")

        logger.info(f"最终关系总数: {len(all_relations)}")
        total_duration = time.time() - start_time
        logger.info(f"✓ 关系发现总耗时: {total_duration:.2f}秒")

        # 计算统计信息
        llm_assisted_count = sum(
            1 for rel in all_relations
            if rel.inference_method == "llm_assisted"
        )

        extra_statistics = {
            "llm_assisted_relationships": llm_assisted_count,
            "rejected_low_confidence": len(rejected_relations)
        }

        return all_relations, len(rejected_relations), extra_statistics

    def _load_all_tables(self) -> Dict[str, Dict]:
        """加载所有 json 文件"""
        tables = {}
        for json_file in self.json_dir.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            table_info = data.get("table_info", {})
            full_name = f"{table_info['schema_name']}.{table_info['table_name']}"
            tables[full_name] = data
            logger.debug(f"已加载: {full_name}")
        return tables
    
    def _relation_to_dict(self, rel: Relation) -> Dict:
        """将 Relation 对象转换为 dict 格式

        新约定（2025-12-26统一后）：
        - Relation: source=外键表(FK), target=主键表(PK)
        - dict: from=外键表(FK), to=主键表(PK)
        - 方向一致，直接映射，无需交换
        """
        rel_type = "composite" if len(rel.source_columns) > 1 else "single_column"

        # 直接映射，无需交换
        result = {
            "relationship_id": rel.relationship_id,
            "type": rel_type,
            "from_table": {"schema": rel.source_schema, "table": rel.source_table},  # FK 表
            "to_table": {"schema": rel.target_schema, "table": rel.target_table},    # PK 表
            "discovery_method": "foreign_key_constraint",
            "cardinality": rel.cardinality  # 直接使用，无需翻转
        }

        if rel_type == "single_column":
            result["from_column"] = rel.source_columns[0]   # FK 列
            result["to_column"] = rel.target_columns[0]     # PK 列
        else:
            result["from_columns"] = rel.source_columns     # FK 列
            result["to_columns"] = rel.target_columns       # PK 列

        return result
    
    def _flip_cardinality(self, cardinality: str) -> str:
        """翻转基数方向

        @deprecated 2025-12-26: 统一方向约定后不再需要翻转
        保留此方法仅为向后兼容，实际已不再使用
        """
        flip_map = {"1:N": "N:1", "N:1": "1:N", "1:1": "1:1", "M:N": "M:N"}
        return flip_map.get(cardinality, cardinality)

    def _dict_to_relation(self, rel_dict: Dict) -> Relation:
        """将 dict 格式的关系转换为 Relation 对象

        新约定（2025-12-26统一后）：
        - dict: from=外键表(FK), to=主键表(PK)
        - Relation: source=外键表(FK), target=主键表(PK)
        - 方向一致，直接映射，无需交换
        """
        # 提取列名
        if rel_dict["type"] == "single_column":
            from_columns = [rel_dict["from_column"]]
            to_columns = [rel_dict["to_column"]]
        else:
            from_columns = rel_dict["from_columns"]
            to_columns = rel_dict["to_columns"]

        # 重新计算 relationship_id，使用统一方向（FK->PK）
        relationship_id = MetadataRepository.compute_relationship_id(
            source_schema=rel_dict["from_table"]["schema"],    # FK 表
            source_table=rel_dict["from_table"]["table"],
            source_columns=from_columns,
            target_schema=rel_dict["to_table"]["schema"],      # PK 表
            target_table=rel_dict["to_table"]["table"],
            target_columns=to_columns,
            rel_id_salt=self.repo.rel_id_salt
        )

        # 创建 Relation 对象（直接映射，无需交换）
        return Relation(
            relationship_id=relationship_id,
            source_schema=rel_dict["from_table"]["schema"],    # FK 表
            source_table=rel_dict["from_table"]["table"],
            source_columns=from_columns,
            target_schema=rel_dict["to_table"]["schema"],      # PK 表
            target_table=rel_dict["to_table"]["table"],
            target_columns=to_columns,
            relationship_type="inferred" if rel_dict.get("discovery_method") == "llm_assisted" else "foreign_key",
            cardinality=rel_dict.get("cardinality", "N:1"),    # 直接使用，无需翻转
            composite_score=rel_dict.get("composite_score"),
            score_details=rel_dict.get("metrics"),
            inference_method=rel_dict.get("discovery_method")
        )

    def _call_llm(self, table1: Dict, table2: Dict) -> List[Dict]:
        """调用 LLM 获取候选关联（带重试）

        注意：table1/table2 来自 json 文件，不查询数据库
        """
        table1_info = table1.get("table_info", {})
        table2_info = table2.get("table_info", {})
        
        table1_name = f"{table1_info['schema_name']}.{table1_info['table_name']}"
        table2_name = f"{table2_info['schema_name']}.{table2_info['table_name']}"
        
        prompt = RELATIONSHIP_DISCOVERY_PROMPT.format(
            table1_name=table1_name,
            table1_json=json.dumps(table1, ensure_ascii=False, indent=2),
            table2_name=table2_name,
            table2_json=json.dumps(table2, ensure_ascii=False, indent=2),
        )
        
        # 添加调试日志：输出提示词长度
        logger.debug(f"LLM 提示词长度: {len(prompt)} 字符, 表对: {table1_name} <-> {table2_name}")
        
        # 重试逻辑
        for attempt in range(self.llm_max_retries + 1):
            try:
                response = self.llm_service._call_llm(prompt)
                candidates = self._parse_llm_response(response)
                
                # 如果之前有重试，记录成功信息
                if attempt > 0:
                    logger.info(
                        f"✓ LLM 调用成功（重试 {attempt} 次后）: {table1_name} <-> {table2_name}"
                    )
                
                logger.debug(f"LLM 返回 {len(candidates)} 个候选: {table1_name} <-> {table2_name}")
                return candidates
                
            except Exception as e:
                if attempt < self.llm_max_retries:
                    # 还有重试机会
                    logger.warning(
                        f"LLM 调用失败 (尝试 {attempt + 1}/{self.llm_max_retries + 1}): "
                        f"{table1_name} <-> {table2_name}, 错误: {e}, "
                        f"{self.llm_retry_delay}秒后重试..."
                    )
                    time.sleep(self.llm_retry_delay)
                else:
                    # 已达最大重试次数
                    logger.error(
                        f"✗ LLM 调用失败（已重试 {self.llm_max_retries} 次）: "
                        f"{table1_name} <-> {table2_name}, 最终错误: {e}"
                    )
                    logger.debug(f"调用失败时的提示词（前1000字符）: {prompt[:1000]}")
                    return []
    
    def _parse_llm_response(self, response: str) -> List[Dict]:
        """解析 LLM 返回（增强版，多模式提取）

        提取优先级：
        1. ```json ... ``` 代码块（最可靠）
        2. ``` ... ``` 无语言标签代码块
        3. 首个完整 JSON 对象（使用状态机，正确处理字符串内的花括号）
        4. 降级：简单 brace_count（向后兼容，但有已知缺陷）
        """
        import re

        try:
            # 添加调试日志：输出原始返回内容
            logger.debug(f"LLM 原始返回（前500字符）: {response[:500] if response else '(空响应)'}")

            response = response.strip()
            if not response:
                logger.warning("LLM 返回为空")
                return []

            # === 方法 1: 提取 ```json ... ``` 代码块 ===
            json_block_pattern = r'```json\s*\n(.*?)\n```'
            match = re.search(json_block_pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                try:
                    json_text = match.group(1).strip()
                    data = json.loads(json_text)
                    if self._validate_response_structure(data):
                        logger.debug(f"✅ 方法1成功: 解析 ```json 代码块，得到 {len(data.get('relationships', []))} 个关系")
                        return data.get("relationships", [])
                except json.JSONDecodeError as e:
                    logger.warning(f"方法1失败: ```json 代码块解析失败: {e}")

            # === 方法 2: 提取 ``` ... ``` 无语言标签代码块 ===
            generic_block_pattern = r'```\s*\n(.*?)\n```'
            match = re.search(generic_block_pattern, response, re.DOTALL)
            if match:
                try:
                    json_text = match.group(1).strip()
                    data = json.loads(json_text)
                    if self._validate_response_structure(data):
                        logger.debug(f"✅ 方法2成功: 解析 ``` 通用代码块，得到 {len(data.get('relationships', []))} 个关系")
                        return data.get("relationships", [])
                except json.JSONDecodeError as e:
                    logger.warning(f"方法2失败: 通用代码块解析失败: {e}")

            # === 方法 3: 使用状态机提取首个完整 JSON 对象（正确处理字符串）===
            json_obj = self._extract_first_json_object(response)
            if json_obj:
                try:
                    data = json.loads(json_obj)
                    if self._validate_response_structure(data):
                        logger.debug(f"✅ 方法3成功: 状态机提取 JSON，得到 {len(data.get('relationships', []))} 个关系")
                        return data.get("relationships", [])
                except json.JSONDecodeError as e:
                    logger.warning(f"方法3失败: 状态机提取的 JSON 解析失败: {e}")

            # === 方法 4: Fallback 到简单 brace_count（向后兼容，但不处理字符串内花括号）===
            logger.warning("⚠️  前3种方法均失败，降级到方法4: 简单 brace_count（可能不准确）")

            # 移除 Markdown 代码块标记
            cleaned_response = response
            cleaned_response = re.sub(r'^```(?:json)?\s*', '', cleaned_response, flags=re.MULTILINE)
            cleaned_response = re.sub(r'\s*```\s*$', '', cleaned_response, flags=re.MULTILINE)
            cleaned_response = cleaned_response.strip()

            # 找到第一个 {
            start_idx = cleaned_response.find('{')
            if start_idx == -1:
                logger.warning("方法4失败: 未找到 JSON 对象起始 {")
                return []

            # 简单计数花括号（不处理字符串）
            brace_count = 0
            end_idx = start_idx
            for i in range(start_idx, len(cleaned_response)):
                if cleaned_response[i] == '{':
                    brace_count += 1
                elif cleaned_response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break

            if brace_count != 0:
                logger.warning("方法4失败: JSON 括号不匹配")
                return []

            json_text = cleaned_response[start_idx:end_idx]
            logger.debug(f"方法4提取的 JSON（前200字符）: {json_text[:200]}")

            data = json.loads(json_text)
            if self._validate_response_structure(data):
                logger.debug(f"✅ 方法4成功: 简单 brace_count，得到 {len(data.get('relationships', []))} 个关系")
                return data.get("relationships", [])
            else:
                logger.warning("方法4失败: 结构验证失败")
                return []

        except json.JSONDecodeError as e:
            logger.warning(f"所有方法失败: JSON 解析错误: {e}")
            logger.debug(f"无法解析的响应: {response[:1000] if response else '(空)'}")
            return []
        except Exception as e:
            logger.error(f"解析 LLM 响应时发生异常: {e}")
            return []

    def _extract_first_json_object(self, text: str) -> Optional[str]:
        """使用状态机提取首个完整 JSON 对象（正确处理字符串内的花括号）

        状态机逻辑：
        - 跟踪是否在字符串内（in_string）
        - 处理转义字符（escape_next）
        - 只在非字符串内计数花括号

        Returns:
            提取的 JSON 字符串，如果未找到则返回 None
        """
        in_string = False
        escape_next = False
        brace_count = 0
        start_idx = None

        for i, char in enumerate(text):
            # 处理转义字符
            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            # 处理字符串边界
            if char == '"':
                in_string = not in_string
                continue

            # 只在非字符串内计数花括号
            if not in_string:
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx is not None:
                        return text[start_idx:i+1]

        return None

    def _validate_response_structure(self, data: Any) -> bool:
        """验证解析出的 JSON 结构是否符合预期

        预期结构: {"relationships": [...]}

        Args:
            data: 解析后的 JSON 数据

        Returns:
            True 如果结构正确，否则 False
        """
        if not isinstance(data, dict):
            logger.debug(f"结构验证失败: 不是 dict，而是 {type(data)}")
            return False

        if "relationships" not in data:
            logger.debug(f"结构验证失败: 缺少 'relationships' 键，实际键: {list(data.keys())}")
            return False

        if not isinstance(data["relationships"], list):
            logger.debug(f"结构验证失败: 'relationships' 不是 list，而是 {type(data['relationships'])}")
            return False

        return True
    
    def _score_candidates(self, candidates: List[Dict], tables: Dict[str, Dict]) -> List[Dict]:
        """对候选关联进行评分
        
        复用 RelationshipScorer._calculate_scores 方法
        """
        scored_relations = []
        rel_id_salt = self.config.get("output", {}).get("rel_id_salt", "")
        
        for candidate in candidates:
            from_table_info = candidate["from_table"]
            to_table_info = candidate["to_table"]
            
            from_full_name = f"{from_table_info['schema']}.{from_table_info['table']}"
            to_full_name = f"{to_table_info['schema']}.{to_table_info['table']}"
            
            # 获取表元数据
            from_table = tables.get(from_full_name)
            to_table = tables.get(to_full_name)
            
            if not from_table or not to_table:
                logger.warning(f"找不到表元数据: {from_full_name} 或 {to_full_name}")
                continue
            
            # 提取列名
            if candidate["type"] == "single_column":
                from_columns = [candidate["from_column"]]
                to_columns = [candidate["to_column"]]
            else:
                from_columns = candidate["from_columns"]
                to_columns = candidate["to_columns"]
            
            # 调用评分方法
            logger.debug(f"评分: {from_full_name}{from_columns} -> {to_full_name}{to_columns}")
            
            score_details, cardinality = self.scorer._calculate_scores(
                from_table, from_columns,
                to_table, to_columns
            )
            
            # 计算综合评分
            composite_score = sum(
                score_details[dim] * self.scorer.weights[dim]
                for dim in score_details
            )
            
            logger.debug(f"评分结果: composite={composite_score:.4f}, cardinality={cardinality}")
            
            # 生成 relationship_id（复用 MetadataRepository.compute_relationship_id）
            relationship_id = MetadataRepository.compute_relationship_id(
                source_schema=from_table_info["schema"],
                source_table=from_table_info["table"],
                source_columns=from_columns,
                target_schema=to_table_info["schema"],
                target_table=to_table_info["table"],
                target_columns=to_columns,
                rel_id_salt=rel_id_salt
            )
            
            # 构建关系对象（包含完整字段，与现有格式一致）
            relation = {
                "relationship_id": relationship_id,
                **candidate,
                "discovery_method": "llm_assisted",
                "target_source_type": "llm_inferred",  # 关系发现来源标记
                "source_constraint": None,             # LLM 推断，无源约束
                "composite_score": round(composite_score, 4),
                "confidence_level": self._get_confidence_level(composite_score),
                "metrics": {k: round(v, 4) for k, v in score_details.items()},
                "cardinality": cardinality
            }
            
            scored_relations.append(relation)
        
        return scored_relations
    
    def _filter_by_threshold(
        self, 
        scored_relations: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        """根据阈值过滤关系
        
        Args:
            scored_relations: 评分后的关系列表
            
        Returns:
            (accepted_relations, rejected_relations)
        """
        accepted = []
        rejected = []
        
        for relation in scored_relations:
            composite_score = relation.get("composite_score", 0)
            
            from_table = relation.get("from_table", {})
            to_table = relation.get("to_table", {})
            from_schema = from_table.get("schema", "")
            from_name = from_table.get("table", "")
            to_schema = to_table.get("schema", "")
            to_name = to_table.get("table", "")
            
            rel_desc = f"{from_schema}.{from_name} -> {to_schema}.{to_name}"
            
            if composite_score >= self.accept_threshold:
                accepted.append(relation)
                logger.debug(
                    f"✓ 通过阈值: {rel_desc} (score={composite_score:.4f})"
                )
            else:
                rejected.append(relation)
                logger.info(
                    f"✗ 低于阈值: {rel_desc} "
                    f"(score={composite_score:.4f} < {self.accept_threshold})"
                )
        
        logger.info(
            f"阈值过滤结果: {len(accepted)} 个通过, {len(rejected)} 个被拒绝"
        )
        return accepted, rejected
    
    def _get_confidence_level(self, score: float) -> str:
        """根据评分确定置信度等级"""
        if score >= 0.8:
            return "high"
        elif score >= 0.6:
            return "medium"
        else:
            return "low"
    
    def _make_signature(self, src_schema, src_table, src_cols, tgt_schema, tgt_table, tgt_cols) -> str:
        """生成关系签名用于去重"""
        src_cols_str = ",".join(sorted(src_cols))
        tgt_cols_str = ",".join(sorted(tgt_cols))
        return f"{src_schema}.{src_table}[{src_cols_str}]->{tgt_schema}.{tgt_table}[{tgt_cols_str}]"
    
    def _filter_existing_fks(self, candidates: List[Dict], fk_relationship_ids: Set[str]) -> List[Dict]:
        """过滤已有的物理外键（使用 relationship_id 去重）

        优化说明：
        - 使用 relationship_id 而非签名，避免字段顺序问题
        - 在评分前就排除物理外键，节省数据库查询和计算资源
        - ⚠️ relationship_id 是有方向的，检查正反两个方向以防 LLM 不遵守约定

        新约定（2025-12-26统一后）：
        - Prompt 已明确要求: from=外键表(FK), to=主键表(PK)
        - 正常情况下 forward_rel_id 应匹配物理外键
        - 但为防御 LLM 不遵守约定，仍检查 reverse_rel_id

        Args:
            candidates: LLM 返回的候选关系
            fk_relationship_ids: 物理外键的 relationship_id 集合

        Returns:
            过滤后的候选关系（排除了物理外键）
        """
        filtered = []
        skipped_count = 0

        for candidate in candidates:
            from_info = candidate["from_table"]
            to_info = candidate["to_table"]

            if candidate["type"] == "single_column":
                from_cols = [candidate["from_column"]]
                to_cols = [candidate["to_column"]]
            else:
                from_cols = candidate["from_columns"]
                to_cols = candidate["to_columns"]

            # 计算正向 relationship_id (from -> to)
            # 新约定下应该是 FK -> PK，与物理外键一致
            forward_rel_id = MetadataRepository.compute_relationship_id(
                source_schema=from_info["schema"],
                source_table=from_info["table"],
                source_columns=from_cols,
                target_schema=to_info["schema"],
                target_table=to_info["table"],
                target_columns=to_cols,
                rel_id_salt=self.repo.rel_id_salt
            )

            # 计算反向 relationship_id (to -> from)
            # 防御性检查：以防 LLM 不遵守约定返回了反向
            reverse_rel_id = MetadataRepository.compute_relationship_id(
                source_schema=to_info["schema"],
                source_table=to_info["table"],
                source_columns=to_cols,
                target_schema=from_info["schema"],
                target_table=from_info["table"],
                target_columns=from_cols,
                rel_id_salt=self.repo.rel_id_salt
            )

            # 检查正反两个方向的 ID 是否与物理外键匹配
            if forward_rel_id in fk_relationship_ids or reverse_rel_id in fk_relationship_ids:
                skipped_count += 1
                matched_id = forward_rel_id if forward_rel_id in fk_relationship_ids else reverse_rel_id
                logger.debug(
                    f"跳过物理外键: {from_info['schema']}.{from_info['table']} <-> "
                    f"{to_info['schema']}.{to_info['table']} "
                    f"(relationship_id={matched_id})"
                )
            else:
                filtered.append(candidate)
        
        if skipped_count > 0:
            logger.info(f"✓ 阶段4去重: 跳过 {skipped_count} 个物理外键，避免重复评分")
        
        return filtered
    
    def _deduplicate_by_relationship_id(
        self,
        fk_relations: List[Relation],
        llm_relations: List[Relation]
    ) -> List[Relation]:
        """根据 relationship_id 去重，优先保留物理外键

        Args:
            fk_relations: 物理外键关系列表（Relation 对象）
            llm_relations: LLM 推断关系列表（Relation 对象）

        Returns:
            去重后的关系列表（Relation 对象）
        """
        # 建立 relationship_id -> 物理外键 的映射
        fk_id_map = {rel.relationship_id: rel for rel in fk_relations}

        # 过滤 LLM 关系：如果 relationship_id 与物理外键重复，跳过
        filtered_llm_relations = []
        for llm_rel in llm_relations:
            rel_id = llm_rel.relationship_id
            if rel_id in fk_id_map:
                # 记录被去重的关系（Relation 对象：source=外键表, target=主键表）
                logger.debug(
                    f"去重：跳过 LLM 推断关系 {llm_rel.target_schema}.{llm_rel.target_table} -> "
                    f"{llm_rel.source_schema}.{llm_rel.source_table} "
                    f"(relationship_id={rel_id}，物理外键已存在)"
                )
            else:
                filtered_llm_relations.append(llm_rel)

        # 合并：物理外键 + 去重后的 LLM 关系
        all_relations = fk_relations + filtered_llm_relations

        if len(llm_relations) > len(filtered_llm_relations):
            dedup_count = len(llm_relations) - len(filtered_llm_relations)
            logger.info(f"去重：移除 {dedup_count} 个与物理外键重复的 LLM 推断关系")

        return all_relations
    
    def _build_output(self, relations: List[Dict], rejected: List[Dict] = None) -> Dict:
        """构建输出 JSON（与现有 rel JSON 格式一致）
        
        Args:
            relations: 接受的关系列表
            rejected: 被拒绝的关系列表（可选）
            
        Returns:
            输出 JSON 字典
        """
        stats = {
            "total_relationships_found": len(relations),
            "foreign_key_relationships": sum(
                1 for r in relations if r.get("discovery_method") == "foreign_key_constraint"
            ),
            "llm_assisted_relationships": sum(
                1 for r in relations if r.get("discovery_method") == "llm_assisted"
            )
        }
        
        # 记录被拒绝的关系统计
        if rejected:
            stats["rejected_low_confidence"] = len(rejected)
            logger.info(f"被拒绝的低置信度关系: {len(rejected)} 个")
        
        return {
            "metadata_source": "json_files",
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "statistics": stats,
            "relationships": relations
        }
