"""决策引擎

应用决策规则和抑制逻辑，过滤候选关系。
"""

from typing import List, Dict, Tuple, Any

from metaweave.core.relationships.models import Relation
from metaweave.core.relationships.repository import MetadataRepository
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.decision_engine")


class DecisionEngine:
    """决策引擎

    职责：
    1. 阈值过滤：composite_score < accept_threshold -> 丢弃
    2. 抑制规则：复合关系存在时抑制同表对的单列关系（除非有独立约束）
    """

    def __init__(self, config: dict):
        """初始化决策引擎

        Args:
            config: relationships配置
        """
        decision_config = config.get("decision", {})
        output_config = config.get("output", {})

        self.accept_threshold = decision_config.get("accept_threshold", 0.80)
        self.high_confidence_threshold = decision_config.get("high_confidence_threshold", 0.90)
        self.medium_confidence_threshold = decision_config.get("medium_confidence_threshold", 0.80)
        self.suppress_single_if_composite = decision_config.get("suppress_single_if_composite", True)

        # 读取 rel_id_salt 配置（与 Repository 保持一致）
        self.rel_id_salt = output_config.get("rel_id_salt", "")

        logger.info(f"决策引擎已初始化: accept_threshold={self.accept_threshold}, "
                    f"suppress_single={self.suppress_single_if_composite}")

    def filter_and_suppress(
            self,
            scored_candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Relation], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """过滤和抑制候选关系

        Args:
            scored_candidates: 评分后的候选列表

        Returns:
            (accepted_relations, suppressed_candidates, below_threshold_candidates)
            - accepted_relations: 接受的推断关系列表
            - suppressed_candidates: 被复合键抑制的候选（不含未达阈值）
            - below_threshold_candidates: 未达 accept_threshold 的候选
        """
        # 1. 阈值过滤
        above_threshold = []
        below_threshold = []

        for candidate in scored_candidates:
            composite_score = candidate.get("composite_score", 0)
            if composite_score >= self.accept_threshold:
                above_threshold.append(candidate)
                logger.debug(
                    "通过阈值 %.2f: %s (score=%.4f)",
                    self.accept_threshold,
                    self._format_candidate(candidate),
                    composite_score,
                )
            else:
                below_threshold.append(candidate)
                logger.debug(
                    "低于阈值 %.2f: %s (score=%.4f)",
                    self.accept_threshold,
                    self._format_candidate(candidate),
                    composite_score,
                )

        logger.info(f"阈值过滤: {len(above_threshold)} 个通过，{len(below_threshold)} 个未达标")

        # 2. 应用抑制规则
        if self.suppress_single_if_composite:
            accepted, suppressed = self._apply_suppression(above_threshold)
        else:
            accepted = above_threshold
            suppressed = []

        # 3. 转换为Relation对象
        accepted_relations = []
        for candidate in accepted:
            relation = self._candidate_to_relation(candidate)
            accepted_relations.append(relation)

        logger.info(f"抑制规则: {len(accepted_relations)} 个接受，{len(suppressed)} 个抑制")

        return accepted_relations, suppressed, below_threshold

    def _apply_suppression(
            self,
            candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """应用抑制规则

        规则：
        - 如果存在accepted的复合关系(A->B)，抑制同表对的单列关系
        - 除非单列关系的源列有独立约束（单列PK/单列UK/非partial单列唯一Index，
          见 `_has_independent_constraint`；v3 改为读取表级 physical_constraints
          与 indexes，此前该例外因列级 structure_flags 缺失而恒不成立）

        Args:
            candidates: 候选列表

        Returns:
            (accepted, suppressed)
        """
        # 按表对分组
        table_pair_groups: Dict[str, List[Dict]] = {}

        for candidate in candidates:
            source_info = candidate["source"].get("object_info", {})
            target_info = candidate["target"].get("object_info", {})

            source_full = f"{source_info.get('schema_name')}.{source_info.get('object_name')}"
            target_full = f"{target_info.get('schema_name')}.{target_info.get('object_name')}"

            table_pair = f"{source_full}->{target_full}"

            if table_pair not in table_pair_groups:
                table_pair_groups[table_pair] = []

            table_pair_groups[table_pair].append(candidate)

        # 对每个表对应用抑制规则
        accepted = []
        suppressed = []

        for table_pair, group in table_pair_groups.items():
            # 检查是否有复合关系
            composite_relations = [c for c in group if len(c["source_columns"]) > 1]
            single_relations = [c for c in group if len(c["source_columns"]) == 1]

            if composite_relations:
                # 有复合关系，保留复合关系
                accepted.extend(composite_relations)
                for rel in composite_relations:
                    logger.debug(
                        "保留复合关系: %s",
                        self._format_candidate(rel),
                    )

                # 检查单列关系是否有独立约束
                for single_rel in single_relations:
                    if self._has_independent_constraint(single_rel):
                        # 有独立约束，保留
                        accepted.append(single_rel)
                        logger.debug(
                            "保留单列关系（独立约束）: %s",
                            self._format_candidate(single_rel),
                        )
                    else:
                        # 无独立约束，抑制
                        suppressed.append(single_rel)
                        logger.debug(
                            "抑制单列关系（存在复合关系）: %s",
                            self._format_candidate(single_rel),
                        )
            else:
                # 没有复合关系，保留所有单列关系
                accepted.extend(single_relations)
                for rel in single_relations:
                    logger.debug(
                        "保留单列关系: %s",
                        self._format_candidate(rel),
                    )

        return accepted, suppressed

    def _has_independent_constraint(self, candidate: Dict[str, Any]) -> bool:
        """检查键端（target）是否有独立约束（单列 PK / 单列 UK / 非 partial
        单列唯一索引），见 doc 19 §3.4。

        方向规范化后键端恒在 target：N:1 / 规则主导 1:1 检查 target；
        **M:N 无键端概念，不应用该例外**（恒 False）；
        纯 LLM 1:1 检查最终方向的 target——但这是物理约束验证，并不证明其
        业务方向正确。`key_origin` 可作一致性防御校验（规则物理键候选的
        target 端必有 PK/UK），不作主判定。

        v3 JSON 已移除列级 `structure_flags`，统一改为读取表级
        `table_profile.physical_constraints`（主键/唯一约束）以及
        `table_profile.indexes[]`（非 partial 的单列唯一索引，即
        `is_unique=True` 且 `condition` 为空的单列索引）。

        Args:
            candidate: 候选关系

        Returns:
            是否有独立约束
        """
        if candidate.get("cardinality") == "M:N":
            # M:N 无键端概念，不应用例外
            return False

        target_table = candidate["target"]
        target_columns = candidate["target_columns"]

        if len(target_columns) != 1:
            return False

        target_col_name = target_columns[0]
        table_profile = target_table.get("table_profile") or {}
        physical = table_profile.get("physical_constraints", {})

        found = False

        # 检查单列主键
        pk = physical.get("primary_key")
        if pk and list(pk.get("columns", [])) == [target_col_name]:
            found = True

        # 检查单列唯一约束
        if not found:
            for uk in physical.get("unique_constraints", []):
                if list(uk.get("columns", [])) == [target_col_name]:
                    found = True
                    break

        # 检查非 partial 的单列唯一索引（口径与 repository._is_columns_unique
        # 一致：is_unique 且 condition 为空、key_expressions == columns
        # （排除表达式索引的键改写）、columns == [target_col]）
        if not found:
            for index in table_profile.get("indexes", []) or []:
                if not index.get("is_unique"):
                    continue
                if index.get("condition"):
                    continue
                key_expressions = index.get("key_expressions") or []
                index_columns = index.get("columns") or []
                if key_expressions and key_expressions != index_columns:
                    continue  # 表达式索引（如 email + lower(name)），键列不直接匹配
                if list(index_columns) == [target_col_name]:
                    found = True
                    break

        # 防御性校验（不作主判定，见 doc 19 §3.4）
        if (
                not found
                and candidate.get("candidate_origin") == "rule"
                and candidate.get("key_origin") == "physical"
        ):
            logger.warning(
                "规则物理键候选的 target 端未检出物理约束（防御性校验失败）: %s",
                self._format_candidate(candidate),
            )

        return found

    def _candidate_to_relation(self, candidate: Dict[str, Any]) -> Relation:
        """将候选转换为Relation对象

        Args:
            candidate: 候选关系

        Returns:
            Relation对象
        """
        source_info = candidate["source"].get("object_info", {})
        target_info = candidate["target"].get("object_info", {})

        # 提取表和列信息
        source_schema = source_info.get("schema_name")
        source_table = source_info.get("object_name")
        target_schema = target_info.get("schema_name")
        target_table = target_info.get("object_name")
        source_columns = candidate["source_columns"]
        target_columns = candidate["target_columns"]

        # 使用 Repository 的静态方法生成 relationship_id（统一逻辑）
        relationship_id = MetadataRepository.compute_relationship_id(
            source_schema=source_schema,
            source_table=source_table,
            source_columns=source_columns,
            target_schema=target_schema,
            target_table=target_table,
            target_columns=target_columns,
            rel_id_salt=self.rel_id_salt
        )

        # 从评分结果获取基数（由 scorer 计算）
        cardinality = candidate.get("cardinality", "N:1")

        # 推断方法（v3 新分类体系，见 doc 15 §3.15，零向后兼容）
        inference_method = self._resolve_inference_method(candidate)

        return Relation(
            relationship_id=relationship_id,
            source_schema=source_schema,
            source_table=source_table,
            source_columns=source_columns,
            target_schema=target_schema,
            target_table=target_table,
            target_columns=target_columns,
            relationship_type="inferred",
            cardinality=cardinality,
            composite_score=candidate.get("composite_score"),
            score_details=candidate.get("score_details"),
            inference_method=inference_method,
            # 统计口径用（见 doc 15 §3.8：物理FK / 仅规则 / 仅LLM / 重叠），
            # 与 inference_method 分开保留，避免 llm/rule+llm 折叠丢失重叠信息
            candidate_origin=candidate.get("candidate_origin"),
        )

    @staticmethod
    def _resolve_inference_method(candidate: Dict[str, Any]) -> str:
        """按 candidate_origin / key_origin 解析新分类体系的 inference_method

        （见 doc 15 §3.15，零向后兼容，未知组合直接报错）

        - candidate_origin 为 llm 或 rule+llm → llm_inferred（来源分档靠
          candidate_origin，不体现在 inference_method 里）；
        - candidate_origin 为 rule → 按 key_origin 区分
          rule_physical_key / rule_logical_key。
        """
        origin = candidate.get("candidate_origin")
        if origin in ("llm", "rule+llm"):
            return "llm_inferred"
        if origin == "rule":
            key_origin = candidate.get("key_origin")
            if key_origin == "physical":
                return "rule_physical_key"
            if key_origin == "logical":
                return "rule_logical_key"
        raise ValueError(
            f"无法解析候选的 inference_method：candidate_origin={origin!r}, "
            f"key_origin={candidate.get('key_origin')!r}。"
            f"v3 新体系零向后兼容，候选必须携带合法的 candidate_origin/key_origin。"
        )

    def _format_candidate(self, candidate: Dict[str, Any]) -> str:
        """格式化候选信息用于日志"""

        def _fmt(table_meta: Dict[str, Any]) -> str:
            info = table_meta.get("object_info", {})
            return f"{info.get('schema_name')}.{info.get('object_name')}"

        source = _fmt(candidate["source"])
        target = _fmt(candidate["target"])
        src_cols = ",".join(candidate.get("source_columns", []))
        tgt_cols = ",".join(candidate.get("target_columns", []))
        origin = candidate.get("candidate_origin")
        key_origin = candidate.get("key_origin")
        return f"{source}[{src_cols}] -> {target}[{tgt_cols}] (origin={origin}, key_origin={key_origin})"
