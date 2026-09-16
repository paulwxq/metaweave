"""关系评分器

为候选关系计算5维度评分（必须使用数据库采样）。
"""

from typing import Dict, List, Tuple, Any, Set, Optional
from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.relationships.name_similarity import NameSimilarityService
from metaweave.core.relationships.type_compatibility import get_type_compatibility_score
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.scorer")

# 默认评分权重（5维度，doc 16）
DEFAULT_WEIGHTS = {
    "inclusion_rate": 0.40,
    "name_similarity": 0.10,
    "comment_similarity": 0.10,
    "type_compatibility": 0.20,
    "jaccard_index": 0.20,
}

# 双方均无可用注释时 comment_similarity 维度的默认得分
DEFAULT_COMMENT_FALLBACK_SCORE = 0.3


class RelationshipScorer:
    """关系评分器

    5个评分维度：
    1. inclusion_rate (40%)：源列值在目标列中的包含率（数据库采样）
    2. name_similarity (10%)：列名相似度（embedding + 同名短路）
    3. comment_similarity (10%)：注释相似度；不可用或通道关闭时用
       comment_fallback_score，不再回退到名称相似度
    4. type_compatibility (20%)：类型兼容性
    5. jaccard_index (20%)：Jaccard相似度（数据库采样）
    """

    def __init__(
            self,
            config: dict,
            connector: DatabaseConnector,
            name_similarity_service: Optional[NameSimilarityService] = None,
    ):
        """初始化评分器

        Args:
            config: relationships配置
            connector: 数据库连接器（必需）
        """
        self.config = config
        self.connector = connector
        self.weights = config.get("weights", DEFAULT_WEIGHTS)
        self.name_similarity_service = name_similarity_service

        # 采样配置（评分阶段从数据库取样的行数上限）
        self.sample_size = config.get("sample_size", 1000)

        # comment_similarity 维度双方均无可用注释时的低默认值
        self.comment_fallback_score = (config.get("scoring") or {}).get(
            "comment_fallback_score", DEFAULT_COMMENT_FALLBACK_SCORE
        )

        self.query_count = 0

        logger.info("关系评分器已初始化（5维度评分体系）:")
        logger.info(f"  - sample_size={self.sample_size}")
        logger.info(f"  - weights={self.weights}")
        logger.info(f"  - comment_fallback_score={self.comment_fallback_score}")
        logger.debug(f"  - weights总和={sum(self.weights.values()):.4f}")

    @staticmethod
    def recompute_composite_score(
            score_details: Dict[str, float],
            weights: Dict[str, float],
    ) -> float:
        """按权重重算总分（共享纯函数，权重单一来源，见 doc 19 §3.2.2）

        合并阶段在方向翻转后调用：更新 score_details["inclusion_rate"] 后，
        用本函数重新加权求和。合并阶段禁止硬编码权重，必须复用本函数或
        传入与评分阶段相同的 weights。
        """
        return sum(score_details[dim] * weights[dim] for dim in score_details)

    def score_candidates(
            self,
            candidates: List[Dict[str, Any]],
            tables: Dict[str, dict]
    ) -> List[Dict[str, Any]]:
        """为候选关系计算评分

        Args:
            candidates: 候选列表
            tables: 表元数据字典

        Returns:
            评分后的候选列表（添加composite_score和score_details字段）
        """
        scored_candidates = []

        for i, candidate in enumerate(candidates):
            try:
                source_table = candidate["source"]
                target_table = candidate["target"]
                source_columns = candidate["source_columns"]
                target_columns = candidate["target_columns"]

                # 计算5个维度评分和基数（附带反向 inclusion 供合并阶段翻转重算）
                score_details, cardinality, reverse_inclusion_rate = self._calculate_scores(
                    source_table, source_columns,
                    target_table, target_columns
                )

                # 防御性检查：验证 score_details 的键与 weights 的键是否一致
                score_keys = set(score_details.keys())
                weight_keys = set(self.weights.keys())

                if score_keys != weight_keys:
                    missing_in_weights = score_keys - weight_keys
                    missing_in_scores = weight_keys - score_keys
                    error_msg = (
                        f"评分维度与权重配置不匹配！\n"
                        f"  score_details 的维度: {sorted(score_keys)}\n"
                        f"  weights 的维度: {sorted(weight_keys)}\n"
                    )
                    if missing_in_weights:
                        error_msg += f"  score_details 中有但 weights 中缺失: {sorted(missing_in_weights)}\n"
                    if missing_in_scores:
                        error_msg += f"  weights 中有但 score_details 中缺失: {sorted(missing_in_scores)}\n"
                    error_msg += (
                        "\n请确保配置文件中的 weights 只包含以下5个维度：\n"
                        "  - inclusion_rate: 0.40\n"
                        "  - name_similarity: 0.10\n"
                        "  - comment_similarity: 0.10\n"
                        "  - type_compatibility: 0.20\n"
                        "  - jaccard_index: 0.20\n"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                # 计算加权求和（共享纯函数，合并阶段重算总分复用同一来源）
                composite_score = self.recompute_composite_score(
                    score_details, self.weights
                )

                # 验证权重总和为1.0（允许浮点误差）
                weight_sum = sum(self.weights.values())
                if abs(weight_sum - 1.0) > 0.001:
                    logger.warning(
                        f"权重总和不为1.0: {weight_sum:.4f}，可能导致评分不准确。"
                        f"当前权重: {self.weights}"
                    )

                # 添加评分信息和基数到候选
                candidate["composite_score"] = composite_score
                candidate["score_details"] = score_details
                candidate["cardinality"] = cardinality
                # 内部返回信息（不进 score_details 与产物）：翻转方向后的
                # inclusion_rate = |交集| / |target_values|，供合并阶段
                # 翻转重算（见 doc 19 §3.2.2，不新增 DB 查询）
                candidate["_reverse_inclusion_rate"] = reverse_inclusion_rate

                source_info = source_table.get("object_info", {})
                target_info = target_table.get("object_info", {})
                relation_label = (
                    f"{source_info.get('schema_name')}.{source_info.get('object_name')}"
                    f"[{', '.join(source_columns)}] -> "
                    f"{target_info.get('schema_name')}.{target_info.get('object_name')}"
                    f"[{', '.join(target_columns)}]"
                )
                logger.debug(
                    "评分完成 %s: %s, composite=%.4f",
                    relation_label,
                    score_details,
                    composite_score,
                )

                scored_candidates.append(candidate)

                if (i + 1) % 10 == 0:
                    logger.info(f"已评分: {i + 1}/{len(candidates)} 个候选")

            except Exception as e:
                logger.error(f"候选评分失败: {e}")

        logger.info(f"候选评分完成: {len(scored_candidates)} 个")
        return scored_candidates

    def _calculate_scores(
            self,
            source_table: dict,
            source_columns: List[str],
            target_table: dict,
            target_columns: List[str]
    ) -> Tuple[Dict[str, float], str, float]:
        """计算5个维度评分和关系基数

        Args:
            source_table: 源表元数据
            source_columns: 源列列表
            target_table: 目标表元数据
            target_columns: 目标列列表

        Returns:
            (score_details, cardinality, reverse_inclusion_rate):
            reverse_inclusion_rate = |交集| / |target_values|，为翻转方向后的
            inclusion_rate（内部返回信息，见 doc 19 §3.2.2）
        """
        source_info = source_table.get("object_info", {})
        target_info = target_table.get("object_info", {})

        source_schema = source_info.get("schema_name")
        source_table_name = source_info.get("object_name")
        target_schema = target_info.get("schema_name")
        target_table_name = target_info.get("object_name")

        source_profiles = source_table.get("column_profiles", {})
        target_profiles = target_table.get("column_profiles", {})

        logger.debug(
            f"开始计算评分: {source_schema}.{source_table_name}{source_columns} -> "
            f"{target_schema}.{target_table_name}{target_columns}"
        )

        # 1 & 2: inclusion_rate, jaccard_index + 唯一性和JOIN倍率（用于基数计算）
        inclusion_rate, reverse_inclusion_rate, jaccard_index, source_uniqueness, target_uniqueness, join_multiplicity = \
            self._sample_and_calculate_inclusion(
                source_schema, source_table_name, source_columns,
                target_schema, target_table_name, target_columns
            )

        # 3: name_similarity（列名相似度，独立维度）
        name_similarity = self._calculate_name_similarity(
            source_columns, target_columns
        )

        # 4: comment_similarity（注释相似度，不回退到名称）
        comment_similarity = self._calculate_comment_similarity(
            source_columns, source_profiles,
            target_columns, target_profiles
        )

        # 5: type_compatibility（类型兼容性）
        type_compatibility = self._calculate_type_compatibility(
            source_columns, source_profiles,
            target_columns, target_profiles
        )

        # 计算基数
        cardinality = self._calculate_cardinality(
            source_uniqueness, target_uniqueness, join_multiplicity
        )

        logger.debug(
            f"评分明细: inclusion_rate={inclusion_rate:.4f}, jaccard_index={jaccard_index:.4f}, "
            f"name_similarity={name_similarity:.4f}, comment_similarity={comment_similarity:.4f}, "
            f"type_compatibility={type_compatibility:.4f}"
        )
        logger.info(
            f"关系基数: {source_schema}.{source_table_name}{source_columns} -> "
            f"{target_schema}.{target_table_name}{target_columns} = {cardinality}"
        )

        return {
            "inclusion_rate": inclusion_rate,
            "name_similarity": name_similarity,
            "comment_similarity": comment_similarity,
            "type_compatibility": type_compatibility,
            "jaccard_index": jaccard_index,
        }, cardinality, reverse_inclusion_rate

    def _sample_and_calculate_inclusion(
            self,
            source_schema: str,
            source_table: str,
            source_columns: List[str],
            target_schema: str,
            target_table: str,
            target_columns: List[str]
    ) -> Tuple[float, float, float, float, float, float]:
        """从数据库采样并计算评分指标和基数计算所需的统计值

        Args:
            source_schema: 源schema
            source_table: 源表
            source_columns: 源列列表
            target_schema: 目标schema
            target_table: 目标表
            target_columns: 目标列列表

        Returns:
            (inclusion_rate, reverse_inclusion_rate, jaccard_index,
             source_uniqueness, target_uniqueness, join_multiplicity)
            reverse_inclusion_rate = |交集| / |target_values|（见 doc 19 §3.2.2）
        """
        try:
            # 采样源表（只取需要的列）
            source_col_expr = ", ".join([f'"{col}"' for col in source_columns])
            source_sql = f'''
                SELECT {source_col_expr}
                FROM "{source_schema}"."{source_table}"
                LIMIT %s
            '''
            source_rows = self.connector.execute_query(source_sql, (self.sample_size,))
            self.query_count += 1

            # 采样目标表
            target_col_expr = ", ".join([f'"{col}"' for col in target_columns])
            target_sql = f'''
                SELECT {target_col_expr}
                FROM "{target_schema}"."{target_table}"
                LIMIT %s
            '''
            target_rows = self.connector.execute_query(target_sql, (self.sample_size,))
            self.query_count += 1

            if not source_rows or not target_rows:
                logger.warning(f"采样数据为空: {source_schema}.{source_table} 或 {target_schema}.{target_table}")
                return 0.0, 0.0, 0.0, 0.0, 0.0, 1.0

            # 提取值集合（组合多列为元组）- 返回值集合和有效行数
            source_values, source_valid_count = self._extract_value_set(source_rows, source_columns)
            target_values, target_valid_count = self._extract_value_set(target_rows, target_columns)

            if not source_values or not target_values:
                return 0.0, 0.0, 0.0, 0.0, 0.0, 1.0

            # 计算交集
            intersection = source_values & target_values
            union = source_values | target_values

            # inclusion_rate = |source ∩ target| / |source|
            inclusion_rate = len(intersection) / len(source_values) if source_values else 0.0
            # reverse_inclusion_rate = |source ∩ target| / |target|（翻转方向的
            # inclusion_rate，采样时同步计算，翻转重算时直接取用，不新增查询）
            reverse_inclusion_rate = len(intersection) / len(target_values) if target_values else 0.0

            # jaccard_index = |source ∩ target| / |source ∪ target|
            jaccard_index = len(intersection) / len(union) if union else 0.0

            logger.debug(f"采样统计: source={len(source_values)}, target={len(target_values)}, "
                         f"intersection={len(intersection)}, inclusion={inclusion_rate:.3f}, jaccard={jaccard_index:.3f}")

            # 计算组合唯一性（使用有效行数作为分母，修复 NULL 值问题）
            source_uniqueness = len(source_values) / source_valid_count if source_valid_count > 0 else 0.0
            target_uniqueness = len(target_values) / target_valid_count if target_valid_count > 0 else 0.0

            # NULL 率过高时记录警告
            if source_valid_count < len(source_rows) * 0.5:
                logger.warning(
                    f"源列 NULL 率过高: {source_schema}.{source_table}{source_columns}, "
                    f"有效行数={source_valid_count}/{len(source_rows)}, 基数判断可能不准确"
                )
            if target_valid_count < len(target_rows) * 0.5:
                logger.warning(
                    f"目标列 NULL 率过高: {target_schema}.{target_table}{target_columns}, "
                    f"有效行数={target_valid_count}/{len(target_rows)}, 基数判断可能不准确"
                )

            # 执行 JOIN COUNT 获取精确倍率（传入 source_valid_count 作为分母）
            join_multiplicity = self._execute_join_count(
                source_schema, source_table, source_columns,
                target_schema, target_table, target_columns,
                source_valid_count
            )

            logger.debug(
                f"采样统计扩展: source_uniq={source_uniqueness:.3f} ({len(source_values)}/{source_valid_count}), "
                f"target_uniq={target_uniqueness:.3f} ({len(target_values)}/{target_valid_count}), "
                f"join_mult={join_multiplicity:.3f}, source_sample={len(source_rows)}, source_valid={source_valid_count}"
            )

            return inclusion_rate, reverse_inclusion_rate, jaccard_index, source_uniqueness, target_uniqueness, join_multiplicity

        except Exception as e:
            logger.error(f"数据库采样失败: {e}")
            return 0.0, 0.0, 0.0, 0.0, 0.0, 1.0

    def _execute_join_count(
            self,
            source_schema: str,
            source_table: str,
            source_columns: List[str],
            target_schema: str,
            target_table: str,
            target_columns: List[str],
            source_valid_count: int
    ) -> float:
        """执行 JOIN COUNT 获取 JOIN 倍率

        在采样数据上执行真实 JOIN 查询，计算源表记录的扩散倍数。

        Args:
            source_schema: 源schema
            source_table: 源表
            source_columns: 源列列表
            target_schema: 目标schema
            target_table: 目标表
            target_columns: 目标列列表
            source_valid_count: 源表有效行数（排除 NULL 后实际参与比较的行数）

        Returns:
            join_multiplicity: JOIN 倍率（join_count / source_valid_count）
        """
        try:
            # 构造列表达式
            source_col_expr = ", ".join([f'"{col}"' for col in source_columns])

            # 构造 JOIN ON 条件
            join_conditions = " AND ".join([
                f's."{src_col}" = t."{tgt_col}"'
                for src_col, tgt_col in zip(source_columns, target_columns)
            ])

            # JOIN COUNT SQL（在采样数据上执行）
            join_sql = f'''
                WITH source_sample AS (
                    SELECT {source_col_expr}
                    FROM "{source_schema}"."{source_table}"
                    LIMIT %s
                )
                SELECT COUNT(*) AS join_count
                FROM source_sample s
                INNER JOIN "{target_schema}"."{target_table}" t
                ON {join_conditions}
            '''

            result = self.connector.execute_query(join_sql, (self.sample_size,))
            self.query_count += 1
            join_count = result[0].get('join_count', 0) if result else 0

            # 计算倍率：使用传入的 source_valid_count 作为分母
            multiplicity = join_count / source_valid_count if source_valid_count > 0 else 0.0

            logger.debug(
                f"JOIN COUNT: {source_schema}.{source_table} → {target_schema}.{target_table}, "
                f"source_valid_count={source_valid_count}, join_count={join_count}, multiplicity={multiplicity:.3f}"
            )

            return multiplicity

        except Exception as e:
            logger.error(f"执行 JOIN COUNT 失败: {e}")
            return 1.0  # 失败时返回 1.0（保守估计，避免误判为 M:N）

    def _calculate_cardinality(
            self,
            source_uniqueness: float,
            target_uniqueness: float,
            join_multiplicity: float
    ) -> str:
        """计算关系基数（静态+动态混合判断）

        三层判断策略：
        1. 静态预判（基于唯一性）：快速识别明确的 1:1、1:N、N:1
        2. 动态验证（基于 JOIN 倍率）：处理边界情况
        3. M:N 兜底：无法判断时统一返回 M:N

        Args:
            source_uniqueness: 源列组合唯一性（采样数据）
            target_uniqueness: 目标列组合唯一性（采样数据）
            join_multiplicity: JOIN 倍率（采样数据）

        Returns:
            基数类型: "1:1" | "1:N" | "N:1" | "M:N"
        """
        HIGH = 0.95  # 高唯一度阈值
        LOW = 0.80   # 低唯一度阈值

        logger.debug(
            f"基数判断输入: source_uniq={source_uniqueness:.3f}, "
            f"target_uniq={target_uniqueness:.3f}, join_mult={join_multiplicity:.3f}"
        )

        # === 第一层：静态预判（基于唯一性） ===

        # 1:1 - 双方都高度唯一
        if source_uniqueness >= HIGH and target_uniqueness >= HIGH:
            logger.debug("基数判断: 1:1（双方高唯一）")
            return "1:1"

        # 1:N - 源唯一，目标重复
        if source_uniqueness >= HIGH and target_uniqueness < LOW:
            logger.debug("基数判断: 1:N（源唯一，目标重复）")
            return "1:N"

        # N:1 - 源重复，目标唯一
        if source_uniqueness < LOW and target_uniqueness >= HIGH:
            logger.debug("基数判断: N:1（源重复，目标唯一）")
            return "N:1"

        # === 第二层：动态验证（边界情况） ===

        logger.debug(f"进入动态判断（唯一性在边界区间 [{LOW}, {HIGH})）")

        # 倍率接近 1 → 一对一或多对一
        if join_multiplicity <= 1.1:
            if source_uniqueness >= target_uniqueness:
                logger.debug("基数判断: 1:1（倍率≈1，源更唯一）")
                return "1:1"
            else:
                logger.debug("基数判断: N:1（倍率≈1，目标更唯一）")
                return "N:1"

        # 倍率显著 > 1 → 一对多或多对多
        if join_multiplicity > 1.5:
            if source_uniqueness >= 0.85:
                logger.debug("基数判断: 1:N（倍率>1.5，源较唯一）")
                return "1:N"
            else:
                logger.debug("基数判断: M:N（倍率>1.5，双方都不唯一）")
                return "M:N"

        # === 第三层：M:N 兜底 ===

        logger.debug("基数判断: M:N（兜底，无法明确判断）")
        return "M:N"

    @staticmethod
    def _make_hashable(value: Any) -> Any:
        """将不可哈希的值转换为可哈希表示。

        PostgreSQL 复杂类型（array → list, json/jsonb → dict/list, hstore → dict）
        在 Python 中不可哈希，无法直接放入 set。此方法递归转换：
        - list → tuple（递归处理元素）
        - dict → tuple(sorted items)（递归处理值）
        - 其他不可哈希类型 → str()

        已知可哈希的基础类型（int, str, float, bool, None, datetime 等）直接返回。
        """
        # 快速路径：绝大多数值是基础可哈希类型
        if isinstance(value, (int, float, str, bool, type(None), bytes)):
            return value
        if isinstance(value, list):
            return tuple(RelationshipScorer._make_hashable(v) for v in value)
        if isinstance(value, dict):
            return tuple(
                (k, RelationshipScorer._make_hashable(v))
                for k, v in sorted(value.items())
            )
        # 兜底：尝试哈希，不行就 str()
        try:
            hash(value)
            return value
        except TypeError:
            return str(value)

    def _extract_value_set(self, rows: List[Dict], columns: List[str]) -> Tuple[Set[Tuple], int]:
        """从查询结果中提取值集合

        Args:
            rows: 查询结果行列表
            columns: 列名列表

        Returns:
            (value_set, valid_count): 
            - value_set: 值元组集合（多列组合为元组，已排除含 NULL 的行）
            - valid_count: 有效行数（排除含 NULL 的行后实际参与比较的行数）
        """
        value_set: Set[Tuple] = set()
        valid_count = 0
        warned_columns: Set[str] = set()

        for row in rows:
            raw_values = [row.get(col) for col in columns]

            # 跳过包含 NULL 的行
            if None in raw_values:
                continue

            # 将不可哈希值转为可哈希表示
            safe_values: list = []
            for col, val in zip(columns, raw_values):
                try:
                    hash(val)
                    safe_values.append(val)
                except TypeError:
                    if col not in warned_columns:
                        warned_columns.add(col)
                        logger.warning(
                            "列 '%s' 包含不可哈希类型 %s（如 array/json），"
                            "将转换为可哈希表示用于集合比较",
                            col,
                            type(val).__name__,
                        )
                    safe_values.append(self._make_hashable(val))

            value_set.add(tuple(safe_values))
            valid_count += 1

        return value_set, valid_count

    def _calculate_name_similarity(
            self,
            source_columns: List[str],
            target_columns: List[str]
    ) -> float:
        """计算列名相似度（平均值），写入 score_details['name_similarity']。

        Args:
            source_columns: 源列列表
            target_columns: 目标列列表

        Returns:
            平均名称相似度（0-1）
        """
        if len(source_columns) != len(target_columns):
            return 0.0

        if self.name_similarity_service:
            return self.name_similarity_service.compare_columns(source_columns, target_columns)

        # 无 embedding 环境的降级语义（doc 15 §2.4/§5）：同名短路通过（1.0），
        # 不同名直接放弃（0.0）。SequenceMatcher 模糊匹配路径已废弃，不再兜底。
        total_sim = 0.0
        for src_col, tgt_col in zip(source_columns, target_columns):
            sim = 1.0 if src_col.lower() == tgt_col.lower() else 0.0
            total_sim += sim

        return total_sim / len(source_columns)

    def _calculate_comment_similarity(
            self,
            source_columns: List[str],
            source_profiles: Dict[str, dict],
            target_columns: List[str],
            target_profiles: Dict[str, dict],
    ) -> float:
        """计算注释相似度（平均值）。

        与 name_similarity 正交：注释不可用或通道关闭时用 comment_fallback_score，
        不回退到名称相似度。
        """
        if len(source_columns) != len(target_columns):
            return 0.0

        total = 0.0
        for src_col, tgt_col in zip(source_columns, target_columns):
            src_comment = (source_profiles.get(src_col, {}) or {}).get("comment")
            tgt_comment = (target_profiles.get(tgt_col, {}) or {}).get("comment")
            total += self._score_comment_pair(src_col, src_comment, tgt_col, tgt_comment)

        return total / len(source_columns)

    def _score_comment_pair(
            self,
            src_col: str,
            src_comment: Optional[str],
            tgt_col: str,
            tgt_comment: Optional[str],
    ) -> float:
        """单列对的 comment_similarity 打分。

        能力关闭（无 embedding / comment_channel.enabled: false）或任一侧注释
        不可用时，返回 comment_fallback_score；双方注释都可用时用注释 embedding。
        """
        if self.name_similarity_service is None:
            return self.comment_fallback_score

        comment_channel = getattr(self.name_similarity_service, "comment_channel", None)
        if comment_channel is None or getattr(comment_channel, "enabled", True) is False:
            return self.comment_fallback_score

        src_usable = comment_channel.is_usable(src_comment)
        tgt_usable = comment_channel.is_usable(tgt_comment)

        if src_usable and tgt_usable:
            sim = comment_channel.compare(src_comment, tgt_comment)
            if sim is not None:
                return sim

        return self.comment_fallback_score

    def _calculate_type_compatibility(
            self,
            source_columns: List[str],
            source_profiles: Dict[str, dict],
            target_columns: List[str],
            target_profiles: Dict[str, dict]
    ) -> float:
        """计算类型兼容性（平均值）

        Args:
            source_columns: 源列列表
            source_profiles: 源列画像
            target_columns: 目标列列表
            target_profiles: 目标列画像

        Returns:
            平均类型兼容性（0-1）
        """
        if len(source_columns) != len(target_columns):
            return 0.0

        total_compat = 0
        for src_col, tgt_col in zip(source_columns, target_columns):
            src_profile = source_profiles.get(src_col, {})
            tgt_profile = target_profiles.get(tgt_col, {})

            src_type = src_profile.get("data_type", "")
            tgt_type = tgt_profile.get("data_type", "")

            compat = get_type_compatibility_score(src_type, tgt_type)
            total_compat += compat

        return total_compat / len(source_columns)

