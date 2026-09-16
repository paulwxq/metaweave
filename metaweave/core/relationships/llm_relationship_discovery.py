"""LLM 候选产出器（doc 15 统一改造：收缩版）。

职责收缩为"LLM 候选产出器"：构建 prompt → 调用 LLM（含重试）→ 解析响应
（含 confidence 归一化）→ 候选卫生处理（越界/自环过滤 + 大小写规范化）。

不再做：去重、过滤已有物理外键、语义角色过滤、类型过滤、阈值过滤、评分——
这些统一交给 `CandidateGenerator` + `RelationshipDiscoveryPipeline` 吸收
（见 docs/update/15_rel与rel_llm候选生成统一改造设计.md §3.7/§6.1）。

数据来源：LLM 调用从 json 文件读取表元数据，不查询数据库。
"""

import asyncio
import json
import logging
import time
from itertools import combinations
from typing import Any, Dict, List, Tuple, Optional

from metaweave.services.llm_service import LLMService
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.llm_discovery")


# LLM 提示词（doc 15 §3.14：新增 confidence 字段）
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
- `confidence`: 0~1 之间的小数，表示你认为该关系是真实主外键关联的置信度。
  置信度主要依据字段名相似、字段注释语义、类型兼容与复合键结构；样例数据值域
  仅供参考——两个表都是自增整型主键时数据天然重合，不要因为数据重合就给高分
  （后续会由数据库验证兜底）。

### 单列关联示例
```json
{{
  "relationships": [
    {{
      "type": "single_column",
      "from_table": {{"schema": "public", "table": "dim_store"}},
      "from_column": "region_id",
      "to_table": {{"schema": "public", "table": "dim_region"}},
      "to_column": "region_id",
      "confidence": 0.92
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
      "to_columns": ["equipment_id", "config_version"],
      "confidence": 0.85
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


def generate_all_pairs(tables: Dict[str, Dict]) -> List[Tuple[str, str]]:
    return list(combinations(tables.keys(), 2))


class LLMRelationshipDiscovery:
    """LLM 候选产出器

    数据来源：LLM 调用从 json 文件读取表元数据，不查询数据库；本类不做评分、
    不做去重、不做 FK 过滤——产出的是"规范化的干净候选列表"，交由统一管线合并。
    """

    def __init__(
        self,
        config: Dict,
        domain_filter: Optional[str] = None,
        cross_domain: bool = False,
        domain_resolver: "Optional[Any]" = None,
    ):
        self.config = config

        from metaweave.services.llm_config_resolver import resolve_module_llm_config

        llm_config = resolve_module_llm_config(config, "relationships.llm")
        self.llm_service = LLMService(llm_config)

        # LLM 重试配置（同步路径 _call_llm 使用；异步路径的重试由
        # LLMService.batch_call_llm_async 内部读取同一份 llm_config 完成，见 3.10）
        self.llm_max_retries = llm_config.get("retry_times", 3)
        self.llm_retry_delay = llm_config.get("retry_delay", 1)

        langchain_config = llm_config.get("langchain_config", {}) or {}
        self.use_async = bool(langchain_config.get("use_async", False))
        self.batch_size = max(1, int(langchain_config.get("batch_size", 50) or 50))

        # Domain 相关（表对解析，见 3.13；主流程由 pipeline 统一计算 table_pairs
        # 后直接传入 discover()/discover_async()，此处保留仅用于独立调用场景）
        self.domain_filter = domain_filter
        self.cross_domain = cross_domain
        self.domain_resolver = domain_resolver

        # 统计（供 CLI 汇总，见 3.10 "新增 CLI 汇总项"）
        self.total_pairs = 0
        self.success_pairs = 0
        self.failed_pairs = 0

        logger.info(
            "LLM 候选产出器已初始化: max_retries=%s, retry_delay=%ss, use_async=%s, batch_size=%s",
            self.llm_max_retries,
            self.llm_retry_delay,
            self.use_async,
            self.batch_size,
        )

    # ------------------------------------------------------------------
    # 表对解析（保留，见 3.13）
    # ------------------------------------------------------------------

    def resolve_table_pairs(self, tables: Dict[str, Dict]) -> List[Tuple[str, str]]:
        """根据 domain 配置生成表对列表（独立调用场景使用；主流程由 pipeline 统一计算）"""
        if not self.domain_filter:
            return list(combinations(tables.keys(), 2))

        if self.domain_resolver is None:
            raise ValueError(
                f"domain={self.domain_filter} 已生效，但未提供 DomainResolver。"
                f"请确认 domains 配置文件存在且已正确加载"
            )
        return self.domain_resolver.resolve_table_pairs(
            available_tables=list(tables.keys()),
            domain_filter=self.domain_filter,
            cross_domain=bool(self.cross_domain),
        )

    # ------------------------------------------------------------------
    # 产出入口
    # ------------------------------------------------------------------

    def discover(
        self,
        tables: Dict[str, Dict],
        table_pairs: Optional[List[Tuple[str, str]]] = None,
    ) -> List[Dict]:
        """同步产出候选（不去重、不评分）。

        Returns:
            规范化后的候选字典列表（含 confidence，已过滤越界/自环候选）
        """
        if table_pairs is None:
            table_pairs = self.resolve_table_pairs(tables)

        self.total_pairs = len(table_pairs)
        self.success_pairs = 0
        self.failed_pairs = 0

        logger.info("LLM 候选产出: 共 %s 个表对需要处理（同步）", self.total_pairs)

        candidates: List[Dict] = []
        for i, (t1, t2) in enumerate(table_pairs):
            pair_candidates = self._call_llm(tables[t1], tables[t2])
            if pair_candidates is None:
                self.failed_pairs += 1
                continue
            self.success_pairs += 1
            pair_candidates = self._filter_invalid_candidates(pair_candidates, t1, t2)
            candidates.extend(pair_candidates)

            if (i + 1) % 10 == 0:
                logger.info("LLM 调用进度: %s/%s", i + 1, self.total_pairs)

        candidates = self._canonicalize_candidate_identifiers(candidates, tables)
        logger.info(
            "LLM 候选产出完成: 成功 %s/%s 个表对，失败 %s 个，候选 %s 个",
            self.success_pairs,
            self.total_pairs,
            self.failed_pairs,
            len(candidates),
        )
        return candidates

    async def discover_async(
        self,
        tables: Dict[str, Dict],
        table_pairs: Optional[List[Tuple[str, str]]] = None,
    ) -> List[Dict]:
        """异步入口，适用于已有事件循环的环境。"""
        if table_pairs is None:
            table_pairs = self.resolve_table_pairs(tables)

        self.total_pairs = len(table_pairs)
        self.success_pairs = 0
        self.failed_pairs = 0

        logger.info(
            "LLM 候选产出: 共 %s 个表对需要处理（异步，分批大小=%s）",
            self.total_pairs,
            self.batch_size,
        )

        candidates = await self._discover_llm_candidates_async(tables, table_pairs)
        candidates = self._canonicalize_candidate_identifiers(candidates, tables)
        logger.info(
            "LLM 候选产出完成: 成功 %s/%s 个表对，失败 %s 个，候选 %s 个",
            self.success_pairs,
            self.total_pairs,
            self.failed_pairs,
            len(candidates),
        )
        return candidates

    def run_discover(
        self,
        tables: Dict[str, Dict],
        table_pairs: Optional[List[Tuple[str, str]]] = None,
    ) -> List[Dict]:
        """按 use_async 配置自动选择同步/异步路径的统一入口（供 pipeline 调用）"""
        if self.use_async:
            return self._run_async(self.discover_async(tables, table_pairs))
        return self.discover(tables, table_pairs)

    async def _discover_llm_candidates_async(
        self,
        tables: Dict[str, Dict],
        table_pairs: List[Tuple[str, str]],
    ) -> List[Dict]:
        total_pairs = len(table_pairs)
        if total_pairs == 0:
            return []

        candidates: List[Dict] = []
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
                    logger.info("LLM 调用进度: %s/%s", global_completed, total_pairs)
                else:
                    logger.debug("LLM 调用完成: %s/%s", global_completed, total_pairs)

            logger.debug(
                "LLM 候选产出器当前 LLM 模型: %s（异步批量，共 %s 个 prompts）",
                self.llm_service.model,
                len(batch_prompts),
            )
            results = await self.llm_service.batch_call_llm_async(
                batch_prompts,
                on_progress=on_progress,
            )

            pair_by_idx = dict(enumerate(batch_pairs))
            for idx, response in results:
                t1, t2 = pair_by_idx[idx]
                if response:
                    self.success_pairs += 1
                    pair_candidates = self._parse_llm_response(response)
                    pair_candidates = self._filter_invalid_candidates(pair_candidates, t1, t2)
                    candidates.extend(pair_candidates)
                else:
                    self.failed_pairs += 1
                    logger.warning(f"表对 {t1} <-> {t2} 无响应")

            del batch_prompts
            del pair_by_idx

        return candidates

    def _run_async(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError(
            "检测到已存在运行中的事件循环。"
            "请改用 await discovery.discover_async() 或在 CLI 层调用 asyncio.run()."
        )

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def _build_prompt(self, table1: Dict, table2: Dict) -> str:
        table1 = self._prune_table_json_for_llm(table1)
        table2 = self._prune_table_json_for_llm(table2)

        table1_info = table1.get("object_info", {})
        table2_info = table2.get("object_info", {})
        table1_name = f"{table1_info['schema_name']}.{table1_info['object_name']}"
        table2_name = f"{table2_info['schema_name']}.{table2_info['object_name']}"

        prompt = RELATIONSHIP_DISCOVERY_PROMPT.format(
            table1_name=table1_name,
            table1_json=json.dumps(table1, ensure_ascii=False, indent=2),
            table2_name=table2_name,
            table2_json=json.dumps(table2, ensure_ascii=False, indent=2),
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("LLM 提示词（已裁剪 JSON） - 表对: %s <-> %s\n%s", table1_name, table2_name, prompt)
        return prompt

    @staticmethod
    def _prune_table_json_for_llm(table_json: Dict) -> Dict:
        """构造提交给 LLM 的表 JSON 视图（不修改原始 dict）

        仅删除每列画像中以下字段，保留 statistics 等其它信息：
        - column_profiles.{col}.semantic_analysis
        - column_profiles.{col}.structure_flags
        - column_profiles.{col}.role_specific_info
        """
        pruned = dict(table_json or {})
        column_profiles = pruned.get("column_profiles")
        if not isinstance(column_profiles, dict):
            return pruned

        pruned_profiles: Dict[str, Dict] = {}
        for col_name, col_profile in column_profiles.items():
            if not isinstance(col_profile, dict):
                pruned_profiles[col_name] = col_profile
                continue
            col_copy = dict(col_profile)
            col_copy.pop("semantic_analysis", None)
            col_copy.pop("structure_flags", None)
            col_copy.pop("role_specific_info", None)
            pruned_profiles[col_name] = col_copy

        pruned["column_profiles"] = pruned_profiles
        return pruned

    # ------------------------------------------------------------------
    # 候选卫生处理：大小写规范化（保留，见 3.7）
    # ------------------------------------------------------------------

    def _canonicalize_candidate_identifiers(
        self, candidates: list[dict], tables: dict[str, dict]
    ) -> list[dict]:
        """将候选关系中的大小写漂移的表名和列名规范化为元数据中的标准名称。

        Args:
            candidates: LLM返回的原始候选列表
            tables: 元数据，用于构建大小写不敏感映射

        Returns:
            规范化后的候选列表（原地修改）
        """
        table_canonical_map = {}
        column_canonical_maps = {}

        for table_key, table_info in tables.items():
            tk_lower = table_key.lower()
            info = table_info.get("object_info", {})
            real_schema = info.get("schema_name", "")
            real_table = info.get("object_name", "")
            table_canonical_map[tk_lower] = (real_schema, real_table)

            col_map = {}
            for col_name in table_info.get("column_profiles", {}).keys():
                col_map[col_name.lower()] = col_name
            column_canonical_maps[tk_lower] = col_map

        for c in candidates:
            ft = c.get("from_table", {})
            from_schema = ft.get("schema", "")
            from_table = ft.get("table", "")
            ft_key_lower = f"{from_schema}.{from_table}".lower()

            if ft_key_lower in table_canonical_map:
                ft["schema"], ft["table"] = table_canonical_map[ft_key_lower]

            tt = c.get("to_table", {})
            to_schema = tt.get("schema", "")
            to_table = tt.get("table", "")
            tt_key_lower = f"{to_schema}.{to_table}".lower()

            if tt_key_lower in table_canonical_map:
                tt["schema"], tt["table"] = table_canonical_map[tt_key_lower]

            c_type = c.get("type", "single_column")
            if c_type == "single_column":
                from_col = c.get("from_column", "")
                if from_col and ft_key_lower in column_canonical_maps and from_col.lower() in column_canonical_maps[ft_key_lower]:
                    c["from_column"] = column_canonical_maps[ft_key_lower][from_col.lower()]

                to_col = c.get("to_column", "")
                if to_col and tt_key_lower in column_canonical_maps and to_col.lower() in column_canonical_maps[tt_key_lower]:
                    c["to_column"] = column_canonical_maps[tt_key_lower][to_col.lower()]
            else:
                from_cols = c.get("from_columns", [])
                if from_cols and ft_key_lower in column_canonical_maps:
                    c["from_columns"] = [
                        column_canonical_maps[ft_key_lower].get(col.lower(), col)
                        for col in from_cols
                    ]

                to_cols = c.get("to_columns", [])
                if to_cols and tt_key_lower in column_canonical_maps:
                    c["to_columns"] = [
                        column_canonical_maps[tt_key_lower].get(col.lower(), col)
                        for col in to_cols
                    ]

        return candidates

    # ------------------------------------------------------------------
    # 候选合法性过滤（保留，见 3.7）
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_invalid_candidates(
        candidates: List[Dict],
        table1_full: str,
        table2_full: str,
    ) -> List[Dict]:
        """过滤 LLM 返回的非法候选关系。

        规则：
        1. 同表同列自环（from_table == to_table 且列完全相同）→ 丢弃
        2. 候选涉及的表不属于当前表对 (table1, table2) → 丢弃

        Args:
            candidates: _parse_llm_response 的原始输出
            table1_full: 当前表对的表 1 全限定名（schema.table）
            table2_full: 当前表对的表 2 全限定名（schema.table）

        Returns:
            过滤后的候选列表
        """
        valid_tables = {table1_full.lower(), table2_full.lower()}
        filtered: List[Dict] = []

        for c in candidates:
            ft = c.get("from_table", {})
            tt = c.get("to_table", {})
            from_full = f"{ft.get('schema', '')}.{ft.get('table', '')}".lower()
            to_full = f"{tt.get('schema', '')}.{tt.get('table', '')}".lower()

            # 规则 1: 同表自环（同表 + 完全相同列）
            if from_full == to_full:
                if c.get("type") == "single_column":
                    same_cols = str(c.get("from_column", "")).lower() == str(c.get("to_column", "")).lower()
                else:
                    from_c = [str(n).lower() for n in c.get("from_columns", [])]
                    to_c = [str(n).lower() for n in c.get("to_columns", [])]
                    same_cols = sorted(from_c) == sorted(to_c)
                if same_cols:
                    logger.warning(
                        "丢弃自环关系: %s.%s -> %s.%s（同表同列）",
                        from_full,
                        c.get("from_column") or c.get("from_columns"),
                        to_full,
                        c.get("to_column") or c.get("to_columns"),
                    )
                    continue

            # 规则 2: 涉及的表不在当前表对范围内
            if from_full not in valid_tables or to_full not in valid_tables:
                logger.warning(
                    "丢弃越界关系: %s -> %s（不属于当前表对 %s <-> %s）",
                    from_full,
                    to_full,
                    table1_full,
                    table2_full,
                )
                continue

            filtered.append(c)

        if len(filtered) < len(candidates):
            logger.info(
                "候选过滤: %s -> %s（丢弃 %s 条非法关系）",
                len(candidates),
                len(filtered),
                len(candidates) - len(filtered),
            )
        return filtered

    # ------------------------------------------------------------------
    # LLM 调用（含重试）
    # ------------------------------------------------------------------

    def _call_llm(self, table1: Dict, table2: Dict) -> Optional[List[Dict]]:
        """调用 LLM 获取候选关联（带重试）

        注意：table1/table2 来自 json 文件，不查询数据库

        Returns:
            成功时返回候选列表（可能为空列表，代表 LLM 认为无关联）；
            达到最大重试次数后仍失败返回 None（该表对被跳过，见 3.10）
        """
        table1_info = table1.get("object_info", {})
        table2_info = table2.get("object_info", {})
        table1_name = f"{table1_info['schema_name']}.{table1_info['object_name']}"
        table2_name = f"{table2_info['schema_name']}.{table2_info['object_name']}"

        prompt = self._build_prompt(table1, table2)

        # 重试逻辑
        for attempt in range(self.llm_max_retries + 1):
            try:
                logger.debug("LLM 候选产出器当前 LLM 模型: %s", self.llm_service.model)
                response = self.llm_service._call_llm(prompt)
                candidates = self._parse_llm_response(response)

                if attempt > 0:
                    logger.info(
                        f"✓ LLM 调用成功（重试 {attempt} 次后）: {table1_name} <-> {table2_name}"
                    )

                logger.debug(f"LLM 返回 {len(candidates)} 个候选: {table1_name} <-> {table2_name}")
                return candidates

            except Exception as e:
                if attempt < self.llm_max_retries:
                    logger.warning(
                        f"LLM 调用失败 (尝试 {attempt + 1}/{self.llm_max_retries + 1}): "
                        f"{table1_name} <-> {table2_name}, 错误: {e}, "
                        f"{self.llm_retry_delay}秒后重试..."
                    )
                    time.sleep(self.llm_retry_delay)
                else:
                    logger.error(
                        f"✗ LLM 调用失败（已重试 {self.llm_max_retries} 次）: "
                        f"{table1_name} <-> {table2_name}, 最终错误: {e}"
                    )
                    logger.debug(f"调用失败时的提示词（前1000字符）: {prompt[:1000]}")
                    return None

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------

    def _parse_llm_response(self, response: str) -> List[Dict]:
        """解析 LLM 返回（增强版，多模式提取）

        提取优先级：
        1. ```json ... ``` 代码块（最可靠）
        2. ``` ... ``` 无语言标签代码块
        3. 首个完整 JSON 对象（使用状态机，正确处理字符串内的花括号）
        4. 降级：简单 brace_count（向后兼容，但有已知缺陷）

        每条关系解析后都会执行 confidence 字段归一化（见 3.14）。
        """
        import re

        try:
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
                        return self._normalize_relationships(data.get("relationships", []))
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
                        return self._normalize_relationships(data.get("relationships", []))
                except json.JSONDecodeError as e:
                    logger.warning(f"方法2失败: 通用代码块解析失败: {e}")

            # === 方法 3: 使用状态机提取首个完整 JSON 对象（正确处理字符串）===
            json_obj = self._extract_first_json_object(response)
            if json_obj:
                try:
                    data = json.loads(json_obj)
                    if self._validate_response_structure(data):
                        logger.debug(f"✅ 方法3成功: 状态机提取 JSON，得到 {len(data.get('relationships', []))} 个关系")
                        return self._normalize_relationships(data.get("relationships", []))
                except json.JSONDecodeError as e:
                    logger.warning(f"方法3失败: 状态机提取的 JSON 解析失败: {e}")

            # === 方法 4: Fallback 到简单 brace_count（向后兼容，但不处理字符串内花括号）===
            logger.warning("⚠️  前3种方法均失败，降级到方法4: 简单 brace_count（可能不准确）")

            cleaned_response = response
            cleaned_response = re.sub(r'^```(?:json)?\s*', '', cleaned_response, flags=re.MULTILINE)
            cleaned_response = re.sub(r'\s*```\s*$', '', cleaned_response, flags=re.MULTILINE)
            cleaned_response = cleaned_response.strip()

            start_idx = cleaned_response.find('{')
            if start_idx == -1:
                logger.warning("方法4失败: 未找到 JSON 对象起始 {")
                return []

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
                return self._normalize_relationships(data.get("relationships", []))
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

    @staticmethod
    def _normalize_relationships(relationships: List[Dict]) -> List[Dict]:
        """对每条关系执行 confidence 归一化（见 3.14）"""
        return [LLMRelationshipDiscovery._normalize_confidence(r) for r in relationships]

    @staticmethod
    def _normalize_confidence(rel: Dict) -> Dict:
        """校验并归一化单条关系的 confidence 字段。

        规则（见 3.14）：
        - 缺失/非法（非数值 / 越界 / 字符串等）→ 记默认值 0.5 + warning 日志，
          该关系仍保留（单个字段问题不导致整个表对失败，不连坐）；
        - 合法（0~1 数值）→ 原样透传（转为 float）。
        """
        conf = rel.get("confidence")
        is_valid = (
            isinstance(conf, (int, float))
            and not isinstance(conf, bool)
            and 0.0 <= float(conf) <= 1.0
        )
        if not is_valid:
            if conf is not None:
                logger.warning(
                    "关系的 confidence 字段非法（%r），已置为默认值 0.5: %s",
                    conf,
                    {k: v for k, v in rel.items() if k != "confidence"},
                )
            rel["confidence"] = 0.5
        else:
            rel["confidence"] = float(conf)
        return rel

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
            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if not in_string:
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx is not None:
                        return text[start_idx:i + 1]

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
