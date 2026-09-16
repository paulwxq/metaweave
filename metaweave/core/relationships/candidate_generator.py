"""候选关系生成器（doc 15 统一改造 + doc 19 方向统一与分池出口）

统一管线（单列 + 复合键共用一条路径）：
① 源侧：统一收集键集（PK / 唯一约束 / 逻辑键，1~N 列）
② 目标侧：剔除 metric / complex 角色 → 目标列池，其余全量平等
③ 逐对递进闸门：英文名 embedding ≥ name_threshold → 过
               否则 注释 embedding ≥ comment_threshold → 过
               否则放弃
               → 类型兼容 ≥ type_threshold → 进候选集，否则放弃
④ 集合指派（复合键）：每源列独立过闸得候选集 → 穷举指派（非贪心，找出全部合法指派）
⑤ 规则候选生成时即规范化方向（关联字段表 → 键表，doc 19 §3.2.1）
⑥ 规则池与 LLM 池各自独立出口：同向去重（规则池 key_origin physical > logical；
   LLM 池去重先于 top_k）→ 最小键过滤（单向：规则单列抑制 LLM 复合）→
   FK 排除（双向），全部在评分前完成（doc 19 §3.1）

详见 docs/update/15_rel与rel_llm候选生成统一改造设计.md 与
docs/update/19_rel方向统一与评分后合并设计.md。
"""

import logging
from typing import Dict, List, Set, Any, Optional, Tuple

from metaweave.core.metadata.profiler import _default_complex_types
from metaweave.core.relationships.name_similarity import NameSimilarityService
from metaweave.core.relationships.repository import MetadataRepository
from metaweave.core.relationships.type_compatibility import get_type_compatibility_score
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.candidate_generator")

_COMPLEX_TYPES = _default_complex_types()

# candidate_matching 默认值（见 doc 15 §4.1），config 缺失该节点或个别字段时
# 按此降级，构造函数本身不因 null/空 relationships 配置崩溃（null 防御测试）。
DEFAULT_CANDIDATE_MATCHING = {
    "max_columns": 3,
    "name_threshold": 0.9,
    "comment_threshold": 0.85,
    "type_threshold": 0.8,
    "logical_key_min_confidence": 0.8,
    "exclude_target_semantic_roles": ["metric"],
    "exclude_target_complex_types": True,
}


class CandidateGenerator:
    """统一候选关系生成器（规则候选生成 + LLM 候选入池 + 池内去重）"""

    def __init__(
            self,
            config: dict,
            name_similarity_service: Optional[NameSimilarityService] = None,
            rel_id_salt: str = "",
    ):
        """初始化候选生成器

        Args:
            config: relationships 配置（candidate_matching 节点缺失时按
                DEFAULT_CANDIDATE_MATCHING 降级）
            name_similarity_service: 名称/注释相似度服务；为 None 时按降级语义运行
                （名称闸退化为同名短路，注释闸禁用，见 doc 15 第5节）
            rel_id_salt: relationship_id 哈希盐，需与 Repository 保持一致
        """
        self.config = config
        self.name_similarity_service = name_similarity_service
        self.rel_id_salt = rel_id_salt

        cm = (config or {}).get("candidate_matching") or {}
        self.max_columns = cm.get("max_columns", DEFAULT_CANDIDATE_MATCHING["max_columns"])
        self.name_threshold = cm.get("name_threshold", DEFAULT_CANDIDATE_MATCHING["name_threshold"])
        self.comment_threshold = cm.get("comment_threshold", DEFAULT_CANDIDATE_MATCHING["comment_threshold"])
        self.type_threshold = cm.get("type_threshold", DEFAULT_CANDIDATE_MATCHING["type_threshold"])
        self.logical_key_min_confidence = cm.get(
            "logical_key_min_confidence", DEFAULT_CANDIDATE_MATCHING["logical_key_min_confidence"]
        )
        self.exclude_target_semantic_roles = set(
            cm.get("exclude_target_semantic_roles", DEFAULT_CANDIDATE_MATCHING["exclude_target_semantic_roles"])
        )
        self.exclude_target_complex_types = bool(
            cm.get("exclude_target_complex_types", DEFAULT_CANDIDATE_MATCHING["exclude_target_complex_types"])
        )

        logger.info(
            "候选生成器已初始化: max_columns=%s, name_threshold=%s, comment_threshold=%s, "
            "type_threshold=%s, logical_key_min_confidence=%s, exclude_target_roles=%s, "
            "exclude_target_complex=%s, degraded=%s",
            self.max_columns, self.name_threshold, self.comment_threshold,
            self.type_threshold, self.logical_key_min_confidence,
            self.exclude_target_semantic_roles, self.exclude_target_complex_types,
            self.name_similarity_service is None,
        )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def generate_candidates(
            self,
            tables: Dict[str, dict],
            table_pairs: List[Tuple[str, str]],
            fk_relationship_ids: Set[str],
            llm_raw_candidates: Optional[List[Dict[str, Any]]] = None,
            llm_top_k: int = 50,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """生成规则池与 LLM 池（独立出口，doc 19 §3.1）

        两池各自完成：同向去重（规则池 key_origin physical > logical；
        LLM 池去重先于 top_k）→ 最小键过滤（单向：规则单列抑制 LLM 复合）
        → FK 排除（双向），全部在评分前完成。跨来源合并挪到评分后
        （pipeline 合并阶段）。

        Args:
            tables: 表元数据字典 {full_name: json_data}
            table_pairs: 表对列表（domain 未指定时 = 全表两两组合，见 3.13）
            fk_relationship_ids: 物理外键的 relationship_id 集合（排重用）
            llm_raw_candidates: LLM 产出器返回的原始候选（from_table/to_table 格式）
            llm_top_k: LLM 候选按 confidence 排序后全局保留的前 K 个

        Returns:
            (rule_pool, llm_pool)：分别可直接送入评分器的候选列表
        """
        rule_pool = self._build_rule_pool(tables, table_pairs, fk_relationship_ids)
        llm_pool = self._build_llm_pool(
            llm_raw_candidates or [], tables, llm_top_k, rule_pool, fk_relationship_ids
        )
        return rule_pool, llm_pool

    def _build_rule_pool(
            self,
            tables: Dict[str, dict],
            table_pairs: List[Tuple[str, str]],
            fk_relationship_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """规则池：生成（方向已规范化）→ 池内同向去重 → 最小键过滤 → FK 排除"""
        rule_candidates = self._generate_rule_candidates(tables, table_pairs)
        physical_n = sum(1 for c in rule_candidates if c.get("key_origin") == "physical")
        logical_n = sum(1 for c in rule_candidates if c.get("key_origin") == "logical")
        logger.info(
            "规则候选生成: %s 个（physical=%s, logical=%s）",
            len(rule_candidates), physical_n, logical_n,
        )

        deduped = self._dedup_rule_pool(rule_candidates)
        filtered = self._filter_superkeys(deduped)
        final = self._exclude_fk_duplicates(filtered, fk_relationship_ids)
        logger.info(
            "规则池最终: 生成 %s → 去重 %s → 最小键过滤 %s → FK 排除 %s 个",
            len(rule_candidates), len(deduped), len(filtered), len(final),
        )
        return final

    def _build_llm_pool(
            self,
            llm_raw_candidates: List[Dict[str, Any]],
            tables: Dict[str, dict],
            llm_top_k: int,
            rule_pool: List[Dict[str, Any]],
            fk_relationship_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """LLM 池：合法化 → 同向去重（同身份保留最高 confidence）→
        排序（confidence 降序、未加盐签名升序）→ top_k 截断 →
        最小键过滤（LLM 池单列 ∪ 规则池单列判定，单向）→ FK 排除（双向）"""
        if not llm_raw_candidates:
            return []

        converted = self._ingest_llm_candidates(llm_raw_candidates, tables)
        deduped = self._dedup_llm_pool(converted)
        truncated = self._truncate_llm_top_k(deduped, llm_top_k)
        filtered = self._filter_superkeys_llm_pool(truncated, rule_pool)
        final = self._exclude_fk_duplicates(filtered, fk_relationship_ids)
        logger.info(
            "LLM 池最终: 原始 %s → 合法化 %s → 去重 %s → top_k(%s) %s → "
            "最小键过滤 %s → FK 排除 %s 个",
            len(llm_raw_candidates), len(converted), len(deduped),
            llm_top_k, len(truncated), len(filtered), len(final),
        )
        return final

    # ------------------------------------------------------------------
    # ① 源侧：统一收集键集
    # ------------------------------------------------------------------

    def _collect_source_key_sets(self, table: dict) -> List[Dict[str, Any]]:
        """统一收集源键集：物理主键 ∪ 物理唯一约束 ∪ 逻辑主键候选（1~max_columns 列）

        - 物理 PK/UK：完全尊重 DBA 定义，不按语义角色过滤；
        - 逻辑键：生成阶段已按 single_column_exclude_roles / composite_exclude_roles
          过滤过，天然干净；
        - 索引不作为源侧键来源（与现状一致）。
        """
        key_sets: List[Dict[str, Any]] = []
        # 保序去重：列对应顺序是身份的一部分（见 doc 15 §3.8），(a,b) 与 (b,a)
        # 是两个不同的声明键，不能用 frozenset（顺序无关）合并，否则会静默丢弃
        # 一个物理约束声明（如 PK(a,b) 与 UK(b,a) 同时存在的边缘情况）。
        seen: Set[tuple] = set()

        def _add(cols: List[str], origin: str) -> None:
            if not cols or not (1 <= len(cols) <= self.max_columns):
                return
            dedup_key = tuple(c.lower() for c in cols)
            if dedup_key in seen:
                return
            seen.add(dedup_key)
            key_sets.append({"columns": list(cols), "origin": origin})

        table_profile = table.get("table_profile", {})
        physical = table_profile.get("physical_constraints", {})

        pk = physical.get("primary_key")
        if pk and pk.get("columns"):
            _add(pk["columns"], "physical")

        for uk in physical.get("unique_constraints", []) or []:
            _add(uk.get("columns", []), "physical")

        for lk in table_profile.get("unique_column_sets", []) or []:
            cols = lk.get("columns", [])
            conf = lk.get("confidence_score", 0)
            if cols and conf >= self.logical_key_min_confidence:
                _add(cols, "logical")

        return key_sets

    # ------------------------------------------------------------------
    # ② 目标侧：目标列池（角色过滤前置）
    # ------------------------------------------------------------------

    def _build_target_column_pool(self, table: dict) -> List[str]:
        """目标列池 = 全部列 − metric 角色列 − complex 类型列（见 3.3）"""
        profiles = table.get("column_profiles", {}) or {}
        pool = []
        for col_name, profile in profiles.items():
            semantic_role = (profile.get("semantic_analysis") or {}).get("semantic_role")
            if semantic_role in self.exclude_target_semantic_roles:
                continue
            if self.exclude_target_complex_types and self._is_complex_type(profile.get("data_type", "")):
                continue
            pool.append(col_name)
        return pool

    @staticmethod
    def _is_complex_type(data_type: str) -> bool:
        if not data_type:
            return False
        t = data_type.lower()
        return t in _COMPLEX_TYPES or ("array" in _COMPLEX_TYPES and t.endswith("[]"))

    # ------------------------------------------------------------------
    # ③ 递进式闸门匹配
    # ------------------------------------------------------------------

    def _passes_gate(
            self,
            src_col: str,
            src_comment: Optional[str],
            tgt_col: str,
            tgt_comment: Optional[str],
    ) -> bool:
        """闸门1（英文名）OR 闸门2（中文注释）；OR 语义，不做加权合成（见 3.4）"""
        if self.name_similarity_service is None:
            # 降级语义（见第5节）：名称闸退化为同名短路，注释闸禁用
            return src_col.strip().lower() == tgt_col.strip().lower()

        name_sim = self.name_similarity_service.compare_pair(src_col, tgt_col)
        if name_sim >= self.name_threshold:
            return True

        comment_sim = self.name_similarity_service.compare_comment_pair(src_comment, tgt_comment)
        if comment_sim is not None and comment_sim >= self.comment_threshold:
            return True

        return False

    def _qualifying_targets(
            self,
            src_col: str,
            src_profile: dict,
            target_pool: List[str],
            target_profiles: Dict[str, dict],
    ) -> Set[str]:
        """单个源列在目标列池中过闸（名称/注释 OR 类型兼容）后的合法目标列集合"""
        qualifying: Set[str] = set()
        src_type = src_profile.get("data_type", "")
        src_comment = src_profile.get("comment")

        for tgt_col in target_pool:
            tgt_profile = target_profiles.get(tgt_col, {}) or {}
            if not self._passes_gate(src_col, src_comment, tgt_col, tgt_profile.get("comment")):
                continue

            tgt_type = tgt_profile.get("data_type", "")
            type_compat = get_type_compatibility_score(src_type, tgt_type)
            if type_compat < self.type_threshold:
                continue

            qualifying.add(tgt_col)

        return qualifying

    # ------------------------------------------------------------------
    # ④ 集合指派（穷举，非贪心）
    # ------------------------------------------------------------------

    @staticmethod
    def _find_all_assignments(qualifying_sets: List[Set[str]]) -> List[List[str]]:
        """穷举所有"每个源列配一个互不重复目标列"的完整指派（见 3.6）

        任一源列候选集为空 → 直接返回空列表（组合放弃）。

        性能优化（doc 15 §3.6 末段，纯性能优化，不改变语义/最终结果集）：
        回溯前按候选集大小升序重排源列，小候选集优先分支，能更快触发
        `used` 冲突而剪掉无效分支，减少大目标列池下的无效搜索开销；
        结果在返回前还原为原始源列顺序，不影响调用方语义。
        """
        if not qualifying_sets or any(not s for s in qualifying_sets):
            return []

        n = len(qualifying_sets)
        # 升序排列：候选集越小越先分支（fail-fast），仅影响搜索顺序，不影响结果集
        order = sorted(range(n), key=lambda i: len(qualifying_sets[i]))
        ordered_sets = [qualifying_sets[i] for i in order]

        ordered_assignments: List[List[str]] = []

        def backtrack(i: int, used: Set[str], current: List[str]) -> None:
            if i == n:
                ordered_assignments.append(list(current))
                return
            for tgt in ordered_sets[i]:
                if tgt in used:
                    continue
                used.add(tgt)
                current.append(tgt)
                backtrack(i + 1, used, current)
                current.pop()
                used.discard(tgt)

        backtrack(0, set(), [])

        # 还原为原始源列顺序（order[pos] 是排序后第 pos 位对应的原始索引）
        assignments: List[List[str]] = []
        for ordered_assignment in ordered_assignments:
            restored: List[Optional[str]] = [None] * n
            for pos, orig_idx in enumerate(order):
                restored[orig_idx] = ordered_assignment[pos]
            assignments.append(restored)  # type: ignore[arg-type]

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "复合键集合指派：候选集大小=%s，指派数=%s",
                [len(s) for s in qualifying_sets],
                len(assignments),
            )

        return assignments

    # ------------------------------------------------------------------
    # 规则候选生成主流程
    # ------------------------------------------------------------------

    def _generate_rule_candidates(
            self,
            tables: Dict[str, dict],
            table_pairs: List[Tuple[str, str]],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for t1, t2 in table_pairs:
            table1 = tables.get(t1)
            table2 = tables.get(t2)
            if table1 is None or table2 is None:
                continue
            # 表对是无序的，但关系是有方向的：分别以 t1、t2 作为源表尝试
            candidates.extend(self._generate_directional_candidates(table1, table2))
            candidates.extend(self._generate_directional_candidates(table2, table1))
        return candidates

    def _generate_directional_candidates(
            self,
            source_table: dict,
            target_table: dict,
    ) -> List[Dict[str, Any]]:
        source_key_sets = self._collect_source_key_sets(source_table)
        if not source_key_sets:
            return []

        target_pool = self._build_target_column_pool(target_table)
        if not target_pool:
            return []

        source_profiles = source_table.get("column_profiles", {}) or {}
        target_profiles = target_table.get("column_profiles", {}) or {}

        candidates: List[Dict[str, Any]] = []
        for key_set in source_key_sets:
            source_columns = key_set["columns"]
            origin = key_set["origin"]

            qualifying_sets = []
            for src_col in source_columns:
                qset = self._qualifying_targets(
                    src_col, source_profiles.get(src_col, {}) or {}, target_pool, target_profiles
                )
                qualifying_sets.append(qset)

            assignments = self._find_all_assignments(qualifying_sets)
            for assignment in assignments:
                candidates.append({
                    # doc 19 §3.2.1：生成时即规范化方向（关联字段表 → 键表）。
                    # 原搜索起点是键表（source_table），规范化后键侧在 target。
                    "source": target_table,
                    "target": source_table,
                    "source_columns": assignment,
                    "target_columns": list(source_columns),
                    "candidate_origin": "rule",
                    "key_origin": origin,  # "physical" | "logical"，供 inference_method 映射使用
                })

        return candidates

    # ------------------------------------------------------------------
    # LLM 候选入池（合法性过滤 + top-K 截断）
    # ------------------------------------------------------------------

    def _ingest_llm_candidates(
            self,
            llm_raw_candidates: List[Dict[str, Any]],
            tables: Dict[str, dict],
    ) -> List[Dict[str, Any]]:
        """把 LLM 产出器返回的原始候选转换为统一内部候选格式，并执行候选层
        统一口径过滤（目标列必须在目标列池中，见 3.7）。
        """
        converted: List[Dict[str, Any]] = []
        pool_cache: Dict[str, Set[str]] = {}

        for c in llm_raw_candidates:
            from_info = c.get("from_table", {})
            to_info = c.get("to_table", {})
            from_full = f"{from_info.get('schema', '')}.{from_info.get('table', '')}"
            to_full = f"{to_info.get('schema', '')}.{to_info.get('table', '')}"

            source_table = tables.get(from_full)
            target_table = tables.get(to_full)
            if source_table is None or target_table is None:
                logger.warning("LLM 候选涉及未知表，丢弃: %s -> %s", from_full, to_full)
                continue

            if c.get("type") == "single_column":
                source_columns = [c.get("from_column")]
                target_columns = [c.get("to_column")]
            else:
                source_columns = c.get("from_columns", [])
                target_columns = c.get("to_columns", [])

            if not source_columns or not target_columns or len(source_columns) != len(target_columns):
                logger.warning("LLM 候选列信息不完整或不对齐，丢弃: %s", c)
                continue

            source_profiles = source_table.get("column_profiles", {}) or {}
            if not all(sc in source_profiles for sc in source_columns):
                logger.warning(
                    "LLM 候选源列不存在于源表，丢弃: %s.%s -> %s.%s",
                    from_full, source_columns, to_full, target_columns,
                )
                continue

            if to_full not in pool_cache:
                pool_cache[to_full] = set(self._build_target_column_pool(target_table))
            target_pool = pool_cache[to_full]

            if not all(tc in target_pool for tc in target_columns):
                logger.debug(
                    "LLM 候选目标列命中 metric/complex 排除规则，丢弃: %s.%s -> %s.%s",
                    from_full, source_columns, to_full, target_columns,
                )
                continue

            converted.append({
                "source": source_table,
                "target": target_table,
                "source_columns": list(source_columns),
                "target_columns": list(target_columns),
                "candidate_origin": "llm",
                "confidence": c.get("confidence", 0.5),
            })

        return converted

    @staticmethod
    def _truncate_llm_top_k(
            llm_candidates: List[Dict[str, Any]],
            top_k: Optional[int],
    ) -> List[Dict[str, Any]]:
        """按 confidence 降序截断前 top_k 个；并列按未加盐有向规范签名升序
        （见 doc 19 §3.1.1，不依赖 LLM 返回顺序；rel_id_salt 不得参与候选
        排序与业务选择）

        top_k 必须是 ≥1 的正整数。0 / 负数不是"不限量"：关闭 LLM 候选请用
        `llm_candidates.enabled: false`。
        """
        if top_k is None or top_k < 1:
            raise ValueError(
                f"llm_top_k 必须是正整数（≥1），检测到: {top_k!r}。"
                f"关闭 LLM 候选请设置 llm_candidates.enabled: false。"
            )

        def sort_key(candidate: Dict[str, Any]) -> Tuple[float, str]:
            return (
                -float(candidate.get("confidence", 0.5)),
                CandidateGenerator._directed_unsigned_signature(candidate),
            )

        # 始终排序再截断:候选数不超过 top_k 时也排序,保证评分顺序与产物
        # 顺序不依赖 LLM 返回顺序(doc 19 §3.1.1)
        return sorted(llm_candidates, key=sort_key)[:top_k]

    # ------------------------------------------------------------------
    # 分池出口：同向去重 + 最小键过滤 + FK 排除（评分前，doc 19 §3.1/3.1.1）
    # ------------------------------------------------------------------

    @staticmethod
    def _directed_unsigned_signature(candidate: Dict[str, Any]) -> str:
        """未哈希、未加盐的有向规范签名（业务选择用，不含 rel_id_salt）。

        用于池内同向去重、LLM top_k 并列排序（doc 19 §3.1.1）。禁止分别排序
        左右字段列表——按 (source_col=target_col) 配对整体排序。
        """
        src_info = candidate["source"].get("object_info", {})
        tgt_info = candidate["target"].get("object_info", {})
        pairs = sorted(
            f"{s}={t}" for s, t in zip(candidate["source_columns"], candidate["target_columns"])
        )
        return (
            f"{src_info.get('schema_name')}.{src_info.get('object_name')}->"
            f"{tgt_info.get('schema_name')}.{tgt_info.get('object_name')}:[{','.join(pairs)}]"
        )

    def _candidate_relationship_id(self, candidate: Dict[str, Any]) -> str:
        """含盐有向身份：与 repository 的 FK 身份集合口径一致，仅用于 FK 排除"""
        src_info = candidate["source"].get("object_info", {})
        tgt_info = candidate["target"].get("object_info", {})
        return MetadataRepository.compute_relationship_id(
            source_schema=src_info.get("schema_name"),
            source_table=src_info.get("object_name"),
            source_columns=candidate["source_columns"],
            target_schema=tgt_info.get("schema_name"),
            target_table=tgt_info.get("object_name"),
            target_columns=candidate["target_columns"],
            rel_id_salt=self.rel_id_salt,
        )

    def _reverse_relationship_id(self, candidate: Dict[str, Any]) -> str:
        """反向身份：用于兜住 LLM/规则候选与物理 FK 方向不一致的重复情形（见 3.8）"""
        src_info = candidate["source"].get("object_info", {})
        tgt_info = candidate["target"].get("object_info", {})
        return MetadataRepository.compute_relationship_id(
            source_schema=tgt_info.get("schema_name"),
            source_table=tgt_info.get("object_name"),
            source_columns=candidate["target_columns"],
            target_schema=src_info.get("schema_name"),
            target_table=src_info.get("object_name"),
            target_columns=candidate["source_columns"],
            rel_id_salt=self.rel_id_salt,
        )

    @staticmethod
    def _full_name(table: dict) -> str:
        info = table.get("object_info", {})
        return f"{info.get('schema_name')}.{info.get('object_name')}"

    def _dedup_rule_pool(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """规则池同向去重（doc 19 §3.1.1）：同一有向身份重复时 key_origin 按
        physical > logical 保留，不得由候选遍历顺序决定；相同来源的重复项直接
        去重。key_origin 决定 3.2.2 的纠偏策略（物理键约束修正 vs 逻辑键失效
        丢弃），保留错误可能让本应存在的关系被删除。
        """
        best: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            sig = self._directed_unsigned_signature(candidate)
            existing = best.get(sig)
            if existing is None:
                best[sig] = candidate
                continue
            if (
                    existing.get("key_origin") == "logical"
                    and candidate.get("key_origin") == "physical"
            ):
                best[sig] = candidate
        return list(best.values())

    def _dedup_llm_pool(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """LLM 池同向去重（doc 19 §3.1.1）：同一身份保留最高 confidence 的一条，
        且先于 top_k 执行——重复候选不得占用 top_k 名额。
        """
        best: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            sig = self._directed_unsigned_signature(candidate)
            existing = best.get(sig)
            if existing is None or float(candidate.get("confidence", 0.5)) > float(
                    existing.get("confidence", 0.5)
            ):
                best[sig] = candidate
        return list(best.values())

    def _exclude_fk_duplicates(
            self,
            candidates: List[Dict[str, Any]],
            fk_relationship_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """FK 排除（双向，评分前，doc 19 §3.1）：正向或反向身份命中物理 FK
        集合即排除。两池各自调用，FK 身份集合全局。
        """
        final = []
        for candidate in candidates:
            if self._candidate_relationship_id(candidate) in fk_relationship_ids:
                continue
            if self._reverse_relationship_id(candidate) in fk_relationship_ids:
                continue
            final.append(candidate)
        return final

    def _filter_superkeys_llm_pool(
            self,
            llm_candidates: List[Dict[str, Any]],
            rule_pool: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """LLM 池最小键过滤（单向，doc 19 §3.1.1）：superkey 判定用
        "LLM 池单列 ∪ 规则池单列"并集——规则单列抑制 LLM 复合（规则单列键侧
        是 PK/UK/逻辑键约束事实，LLM 复合是猜测，丢弃无损）、LLM 池内单列
        抑制 LLM 池内复合；**LLM 单列不抑制规则复合**（规则池已先行自过滤）。
        """
        single_map: Set[Tuple[str, str, str, str]] = set()
        for candidate in list(rule_pool) + list(llm_candidates):
            if len(candidate["source_columns"]) == 1:
                single_map.add((
                    self._full_name(candidate["source"]),
                    self._full_name(candidate["target"]),
                    candidate["source_columns"][0],
                    candidate["target_columns"][0],
                ))

        result = []
        for candidate in llm_candidates:
            if len(candidate["source_columns"]) > 1:
                src_full = self._full_name(candidate["source"])
                tgt_full = self._full_name(candidate["target"])
                is_superkey = any(
                    (src_full, tgt_full, sc, tc) in single_map
                    for sc, tc in zip(candidate["source_columns"], candidate["target_columns"])
                )
                if is_superkey:
                    continue
            result.append(candidate)
        return result

    def _filter_superkeys(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """最小键过滤：同池内若单列键 col→X 的候选已存在，复合键 (col, other)→(X, Y)
        的某指派同样把 col 配到 X，则该复合候选视为 superkey 冗余，丢弃（见 3.9）。
        不区分候选来源（逻辑键/物理约束/LLM 三来源的超集都由本条兜底）。
        """
        single_map: Set[Tuple[str, str, str, str]] = set()
        for c in candidates:
            if len(c["source_columns"]) == 1:
                single_map.add((
                    self._full_name(c["source"]), self._full_name(c["target"]),
                    c["source_columns"][0], c["target_columns"][0],
                ))

        result = []
        for c in candidates:
            if len(c["source_columns"]) > 1:
                src_full = self._full_name(c["source"])
                tgt_full = self._full_name(c["target"])
                is_superkey = any(
                    (src_full, tgt_full, sc, tc) in single_map
                    for sc, tc in zip(c["source_columns"], c["target_columns"])
                )
                if is_superkey:
                    continue
            result.append(c)
        return result
