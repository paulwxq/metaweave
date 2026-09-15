"""关系输出器

负责输出关系发现结果（JSON + Markdown），符合 v3.2 文档规范。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from metaweave.core.metadata.metadata_document import CURRENT_METADATA_VERSION
from metaweave.core.relationships.models import FOREIGN_KEY_COMPOSITE_SCORE, Relation
from metaweave.utils.file_utils import ensure_dir
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.writer")


class RelationshipWriter:
    """关系输出器

    输出文件（当前版本仅支持 global 粒度）：
    - {db_name}.relationships_{granularity}.json（所有关系，v3.2格式）
    - {db_name}.relationships_{granularity}.md（可读报告）

    注意：Phase 1 仅支持 rel_granularity='global'，schema 粒度将在后续版本实现。
    """

    def __init__(self, config: dict):
        """初始化输出器

        Args:
            config: top-level 配置
        """
        output_config = config.get("output", {})
        database_config = config.get("database", {})

        self.rel_dir = Path(output_config.get("rel_directory", "output/rel"))
        self.rel_granularity = output_config.get("rel_granularity", "global")
        self.database_name = database_config.get("database")
        if not self.database_name:
            raise ValueError("database.database 未配置，无法生成关系输出文件名")

        # 验证粒度配置（Phase 1 仅支持 global）
        if self.rel_granularity != "global":
            logger.warning(
                f"当前版本仅支持 rel_granularity='global'，配置值 '{self.rel_granularity}' 将被忽略。"
                f"Schema 粒度输出功能计划在后续版本实现。"
            )
            self.rel_granularity = "global"  # 强制使用 global

        # 决策阈值（用于置信度分类）
        decision_config = config.get("decision", {})
        self.high_confidence_threshold = decision_config.get("high_confidence_threshold", 0.90)
        self.medium_confidence_threshold = decision_config.get("medium_confidence_threshold", 0.80)

        # 确保输出目录存在
        ensure_dir(self.rel_dir)
        self.tables: Dict[str, dict] = {}

        logger.info(f"关系输出器已初始化: {self.rel_dir}")

    @staticmethod
    def generated_by_label(llm_candidates_enabled: bool) -> str:
        """JSON / Markdown 共用的生成方式标记。"""
        return "rel_llm" if llm_candidates_enabled else "rel"

    def _json_metadata_version(self) -> str:
        """从读入的表画像带出 metadata_version；缺省为当前表 JSON 契约版本。"""
        versions = {
            table.get("metadata_version")
            for table in self.tables.values()
            if isinstance(table, dict) and table.get("metadata_version")
        }
        if not versions:
            return CURRENT_METADATA_VERSION
        if len(versions) > 1:
            logger.warning(
                "读入的表 JSON metadata_version 不一致: %s，按 %s 标记",
                sorted(str(v) for v in versions),
                CURRENT_METADATA_VERSION,
            )
            return CURRENT_METADATA_VERSION
        return next(iter(versions))

    @staticmethod
    def _relation_score(rel: Relation) -> Optional[float]:
        """JSON 与 Markdown 共用的有效综合分。外键直通固定为 1.0。"""
        if rel.relationship_type == "foreign_key":
            return FOREIGN_KEY_COMPOSITE_SCORE
        return rel.composite_score

    def _confidence_level(self, score: Optional[float]) -> Optional[str]:
        if score is None:
            return None
        if score >= self.high_confidence_threshold:
            return "high"
        if score >= self.medium_confidence_threshold:
            return "medium"
        return "low"

    def write_results(
            self,
            relations: List[Relation],
            suppressed: List[Dict[str, Any]],
            config: Dict[str, Any],
            tables: Optional[Dict[str, dict]] = None,
            generated_by: str = "rel",
            extra_statistics: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """输出关系发现结果（v3.2格式）

        Args:
            relations: 接受的关系列表（外键+推断）
            suppressed: 被抑制的候选列表
            config: 完整配置
            tables: 表元数据字典（用于获取列的约束信息）
            generated_by: 生成模式。未启用 LLM 候选为 "rel"，启用为 "rel_llm"
            extra_statistics: 额外的统计项（如 llm_assisted_relationships）

        Returns:
            输出文件路径列表
        """
        # 保存 tables 供后续使用
        self.tables = tables or {}
        
        output_files = []

        # 1. 输出JSON（v3.2格式）
        json_file = self._write_json_v32(relations, suppressed, config, generated_by, extra_statistics)
        if json_file:
            output_files.append(str(json_file))

        # 2. 输出Markdown
        md_file = self._write_markdown(relations, generated_by=generated_by)
        if md_file:
            output_files.append(str(md_file))

        logger.info(f"输出完成: {len(output_files)} 个文件")
        return output_files

    def _write_json_v32(
            self,
            relations: List[Relation],
            suppressed: List[Dict],
            config: Dict[str, Any],
            generated_by: str = "rel",
            extra_statistics: Optional[Dict[str, Any]] = None
    ) -> Path:
        """输出JSON文件（v3.2格式）

        Args:
            relations: 关系列表
            suppressed: 被抑制的候选
            config: 配置

        Returns:
            输出文件路径
        """
        # 将被抑制的单列关系按表对分组
        suppressed_by_table_pair = self._group_suppressed_by_table_pair(suppressed)

        logger.debug(
            "开始转换 JSON，关系=%d，被抑制=%d",
            len(relations),
            len(suppressed),
        )

        # 转换关系为v3.2格式，并嵌入被抑制的单列
        relationships_v32 = []
        for rel in relations:
            rel_dict = self._convert_to_v32_format(rel)

            # 如果是复合键关系，嵌入被抑制的单列
            if rel.is_composite:
                table_pair = rel.table_pair
                if table_pair in suppressed_by_table_pair:
                    rel_dict["suppressed_single_relations"] = suppressed_by_table_pair[table_pair]

            relationships_v32.append(rel_dict)

        if relationships_v32:
            sample_ids = [rel.get("relationship_id") for rel in relationships_v32[:3]]
            logger.debug("JSON 样例关系ID: %s", sample_ids)

        # 计算统计数据（v3.2口径）
        stats = self._calculate_statistics_v32(relations, suppressed)

        # 从 extra_statistics 提取顶层字段，其余归入 statistics（不修改原字典）
        db_queries = 0
        nested_extra = {}
        if extra_statistics:
            db_queries = extra_statistics.get("database_queries_executed", 0)
            nested_extra = {k: v for k, v in extra_statistics.items() if k != "database_queries_executed"}

        # 构建JSON数据（v3.2格式）
        data = {
            "generated_by": generated_by,
            "database": self.database_name,
            "metadata_source": "json_files",
            "json_metadata_version": self._json_metadata_version(),
            "json_files_loaded": stats["json_files_loaded"],
            "database_queries_executed": db_queries,
            "generated_timestamp": datetime.now().isoformat(),

            "statistics": {
                "total_relationships_found": stats["total_relationships_found"],
                "foreign_key_relationships": stats["foreign_key_relationships"],
                "composite_key_relationships": stats["composite_key_relationships"],
                "single_column_relationships": stats["single_column_relationships"],
                "total_suppressed_single_relations": stats["total_suppressed_single_relations"],
                "rule_only_relationships": stats["rule_only_relationships"],
                "llm_only_relationships": stats["llm_only_relationships"],
                "rule_llm_overlap_relationships": stats["rule_llm_overlap_relationships"],
            },

            "relationships": relationships_v32
        }

        # 合并额外的统计项（不含已提取的顶层字段）
        if nested_extra:
            data["statistics"].update(nested_extra)

        # 写入文件（使用配置的粒度，当前仅支持 global）
        json_file = self.rel_dir / f"{self.database_name}.relationships_{self.rel_granularity}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON已输出: {json_file}")
        return json_file

    def _group_suppressed_by_table_pair(
            self,
            suppressed: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """按表对分组被抑制的单列关系

        Args:
            suppressed: 被抑制的候选列表

        Returns:
            {table_pair: [suppressed_relation_dict, ...]}
        """
        grouped = defaultdict(list)

        for candidate in suppressed:
            # 只处理单列关系
            if len(candidate.get("source_columns", [])) > 1:
                continue

            source_info = candidate["source"].get("table_info", {})
            target_info = candidate["target"].get("table_info", {})

            table_pair = (
                f"{source_info.get('schema_name')}.{source_info.get('table_name')}->"
                f"{target_info.get('schema_name')}.{target_info.get('table_name')}"
            )

            # 转换为v3.2格式
            suppressed_rel = {
                "from_column": candidate["source_columns"][0],
                "to_column": candidate["target_columns"][0],
                "original_score": candidate.get("composite_score", 0.0),
                "suppression_reason": "在复合键中，无独立约束",
                "could_have_been_accepted": candidate.get("composite_score", 0.0) >= 0.80
            }

            grouped[table_pair].append(suppressed_rel)

        return dict(grouped)

    def _convert_to_v32_format(self, rel: Relation) -> Dict[str, Any]:
        """转换关系对象为v3.2 JSON格式

        Args:
            rel: 关系对象

        Returns:
            v3.2格式的字典
        """
        # 确定关系类型
        if rel.is_composite:
            rel_type = "composite"
        else:
            rel_type = "single_column"

        # 确定置信度级别（外键与推断共用同一套分数 → 档位规则）
        score = self._relation_score(rel)
        confidence_level = self._confidence_level(score)

        # 基础字段
        result = {
            "relationship_id": rel.relationship_id,
            "type": rel_type,
            "from_table": {
                "schema": rel.source_schema,
                "table": rel.source_table
            },
            "to_table": {
                "schema": rel.target_schema,
                "table": rel.target_table
            },
        }

        # 列名（单列用 from_column，复合用 from_columns）
        if rel.is_single_column:
            result["from_column"] = rel.source_columns[0]
            result["to_column"] = rel.target_columns[0]
        else:
            result["from_columns"] = rel.source_columns
            result["to_columns"] = rel.target_columns

        # 发现方法、来源类型、约束类型（规范化映射）
        if rel.relationship_type == "foreign_key":
            result["discovery_method"] = "foreign_key_constraint"
            result["target_source_type"] = "foreign_key"
            result["source_constraint"] = None
        else:
            # 从 inference_method (candidate_type) 拆分为规范字段
            discovery_info = self._parse_discovery_info(rel.inference_method, rel)
            result["discovery_method"] = discovery_info["discovery_method"]
            result["target_source_type"] = discovery_info.get("target_source_type")
            result["source_constraint"] = discovery_info.get("source_constraint")

        # 评分：JSON 与 MD 共用 _relation_score。推断关系带 metrics；外键无评分明细。
        if score is not None:
            result["composite_score"] = score
            result["confidence_level"] = confidence_level
            if rel.relationship_type != "foreign_key":
                result["metrics"] = rel.score_details or {}

        # 关系基数（所有关系都有）
        result["cardinality"] = rel.cardinality
        
        # 外键约束名（仅外键关系有值）
        if rel.constraint_name is not None:
            result["constraint_name"] = rel.constraint_name

        return result

    # inference_method 新分类体系（v3 专属，零向后兼容，见 doc 15 §3.15）
    #
    # 注意：此映射表只覆盖"推断关系"（relationship_type == "inferred"）。
    # 物理外键直通（relationship_type == "foreign_key"）走上面第 279 行的独立
    # 分支，从不设置 inference_method、也不经过 _parse_discovery_info——其
    # discovery_method 固定为历史既有值 "foreign_key_constraint"（早于 doc 15，
    # 见 REFACTOR_SUMMARY_V32.md 等），不属于本次改造范围。因此 v3 taxonomy
    # 中不再列 physical_foreign_key：该值在当前架构下永远不会被产出，列入映射
    # 表只会造成死代码（详见 doc 15 §3.15 勘误）。
    _INFERENCE_METHOD_DISCOVERY_MAP: Dict[str, str] = {
        "rule_physical_key": "physical_key_matching",
        "rule_logical_key": "logical_key_matching",
        "llm_inferred": "llm_inferred",
    }

    def _parse_discovery_info(
            self,
            inference_method: Optional[str],
            rel: Relation
    ) -> Dict[str, Optional[str]]:
        """解析 inference_method 为 discovery_method, target_source_type, source_constraint

        新值集（v3 专属，零向后兼容，见 doc 15 §3.15；仅覆盖推断关系，物理外键
        直通不经此函数，见类属性 `_INFERENCE_METHOD_DISCOVERY_MAP` 上方说明）：

        | inference_method       | 来源                         | discovery_method        |
        |-------------------------|------------------------------|--------------------------|
        | rule_physical_key      | 规则候选，源键集为物理 PK/UK  | physical_key_matching    |
        | rule_logical_key       | 规则候选，源键集为逻辑键       | logical_key_matching     |
        | llm_inferred           | LLM 候选（含与规则重叠）       | llm_inferred             |

        未识别旧值（如 single_active_search、composite_dynamic_same_name 等）
        与缺失值直接报错，不再静默回退 standard_matching。

        Args:
            inference_method: 推断方法字符串（v3 新值集之一）
            rel: 关系对象

        Returns:
            包含 discovery_method, target_source_type, source_constraint 的字典
        """
        if not inference_method:
            raise ValueError(
                f"关系 {rel.relationship_id} 缺少 inference_method，"
                f"v3 新体系下所有推断关系必须显式携带 inference_method（见 doc 15 §3.15）"
            )

        discovery_method = self._INFERENCE_METHOD_DISCOVERY_MAP.get(inference_method)
        if discovery_method is None:
            raise ValueError(
                f"关系 {rel.relationship_id} 携带未知的 inference_method: "
                f"{inference_method!r}。v3 新体系零向后兼容，仅支持: "
                f"{sorted(self._INFERENCE_METHOD_DISCOVERY_MAP)}（见 doc 15 §3.15）"
            )

        if inference_method in ("rule_physical_key", "rule_logical_key"):
            return {
                "discovery_method": discovery_method,
                "target_source_type": self._get_target_source_type(rel),
                "source_constraint": self._get_source_constraint(rel),
            }

        if inference_method == "llm_inferred":
            return {
                "discovery_method": discovery_method,
                "target_source_type": "llm_inferred",
                "source_constraint": None,
            }

        # physical_foreign_key：目前物理 FK 走独立分支（relationship_type ==
        # "foreign_key"）直接构造输出，不经过本方法；此处保留仅为完整性兜底。
        return {
            "discovery_method": discovery_method,
            "target_source_type": "foreign_key",
            "source_constraint": None,
        }

    def _get_source_constraint(self, rel: Relation) -> Optional[str]:
        """获取源列的实际约束类型（v3：按表级 physical_constraints / indexes 判定）

        Args:
            rel: 关系对象

        Returns:
            约束类型字符串，可能的值：
            - "single_field_primary_key": 单列主键
            - "single_field_unique_constraint": 单列唯一约束
            - "single_field_index": 单列索引（含唯一/非唯一）
            - None: 没有物理约束（只是数据唯一或逻辑主键）
        """
        if not hasattr(self, 'tables') or not self.tables or not rel.is_single_column:
            return None

        source_table_key = f"{rel.source_schema}.{rel.source_table}"
        source_table = self.tables.get(source_table_key)

        if not source_table:
            logger.debug(f"未找到源表元数据: {source_table_key}")
            return None

        table_profile = source_table.get("table_profile", {})
        physical = table_profile.get("physical_constraints", {})
        source_column = rel.source_columns[0]

        pk = physical.get("primary_key")
        if pk and list(pk.get("columns", [])) == [source_column]:
            return "single_field_primary_key"

        for uk in physical.get("unique_constraints", []):
            if list(uk.get("columns", [])) == [source_column]:
                return "single_field_unique_constraint"

        for index in table_profile.get("indexes", []) or []:
            if list(index.get("columns", [])) == [source_column]:
                return "single_field_index"

        # 没有物理约束（可能只是数据唯一或逻辑主键）
        return None

    def _get_target_source_type(self, rel: Relation) -> Optional[str]:
        """获取目标列的实际来源类型（v3：按表级 physical_constraints 判定）

        Args:
            rel: 关系对象

        Returns:
            目标列类型字符串，可能的值：
            - "primary_key": 物理主键
            - "unique_constraint": 物理唯一约束
            - "candidate_logical_key": 逻辑主键（置信度 >= 0.8）
            - None: 无物理约束或逻辑键（可能只是统计唯一）

        注意：
            - 只认物理约束，不认统计唯一
            - 与 _get_source_constraint() 保持相同的口径
        """
        if not hasattr(self, 'tables') or not self.tables or not rel.is_single_column:
            return None

        target_table_key = f"{rel.target_schema}.{rel.target_table}"
        target_table = self.tables.get(target_table_key)

        if not target_table:
            logger.debug(f"未找到目标表元数据: {target_table_key}")
            return None

        table_profile = target_table.get("table_profile", {})
        physical = table_profile.get("physical_constraints", {})
        target_column = rel.target_columns[0]

        pk = physical.get("primary_key")
        if pk and list(pk.get("columns", [])) == [target_column]:
            return "primary_key"

        for uk in physical.get("unique_constraints", []):
            if list(uk.get("columns", [])) == [target_column]:
                return "unique_constraint"

        # 检查是否为逻辑主键
        unique_column_sets = table_profile.get("unique_column_sets", [])

        for lk in unique_column_sets:
            lk_cols = lk.get("columns", [])
            lk_conf = lk.get("confidence_score", 0)

            # 单列逻辑主键且置信度 >= 0.8
            if (len(lk_cols) == 1 and
                lk_cols[0] == target_column and
                lk_conf >= 0.8):
                return "candidate_logical_key"

        return None

    def _calculate_statistics_v32(
            self,
            relations: List[Relation],
            suppressed: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """计算统计数据（v3 统一改造口径，见 doc 15 §3.8）

        统计字段包括：
        - total_relationships_found: 总关系数
        - foreign_key_relationships: 外键直通关系数（物理FK）
        - composite_key_relationships: 复合键关系数
        - single_column_relationships: 单列关系数
        - total_suppressed_single_relations: 被抑制的单列关系数
        - rule_only_relationships: 仅规则发现（candidate_origin == "rule"）
        - llm_only_relationships: 仅LLM发现（candidate_origin == "llm"）
        - rule_llm_overlap_relationships: 规则与LLM重叠确认
          （candidate_origin == "rule+llm"）

        旧口径 `active_search_discoveries` / `dynamic_composite_discoveries`
        依赖已删除的 candidate_type 值（single_active_search /
        composite_dynamic_same_name），v3 新分类体系下恒为 0，已按 doc 15 §3.8
        的"来源分档"要求替换为上述三个字段（P7 勘误，见 doc 15 §3.8）。

        Args:
            relations: 关系列表
            suppressed: 被抑制的候选

        Returns:
            统计字典
        """
        # 基础统计
        total = len(relations)

        # 外键直通关系数（relationship_type == "foreign_key"）
        foreign_key_count = len([r for r in relations if r.relationship_type == "foreign_key"])

        composite_count = len([r for r in relations if r.is_composite])
        single_count = len([r for r in relations if r.is_single_column])

        # 被抑制的单列关系数量
        suppressed_single_count = len([
            s for s in suppressed
            if len(s.get("source_columns", [])) == 1
        ])

        # 来源分档统计（doc 15 §3.8：物理FK / 仅规则 / 仅LLM / 重叠）
        # 物理FK 已由 foreign_key_count 覆盖（relationship_type 判断，不依赖
        # candidate_origin）；此处只统计推断关系的三种来源分档。
        rule_only_count = len([r for r in relations if r.candidate_origin == "rule"])
        llm_only_count = len([r for r in relations if r.candidate_origin == "llm"])
        overlap_count = len([r for r in relations if r.candidate_origin == "rule+llm"])

        return {
            "total_relationships_found": total,
            "foreign_key_relationships": foreign_key_count,
            "composite_key_relationships": composite_count,
            "single_column_relationships": single_count,
            "total_suppressed_single_relations": suppressed_single_count,
            "rule_only_relationships": rule_only_count,
            "llm_only_relationships": llm_only_count,
            "rule_llm_overlap_relationships": overlap_count,
            "json_files_loaded": len(self.tables),
        }

    def _write_markdown(self, relations: List[Relation], generated_by: str) -> Path:
        """输出Markdown报告

        Args:
            relations: 关系列表
            generated_by: 生成模式。未启用 LLM 候选为 "rel"，启用为 "rel_llm"

        Returns:
            输出文件路径
        """
        lines = []

        # 标题
        lines.append("# 表间关系发现报告")
        lines.append(f"database: {self.database_name}")
        lines.append(f"生成方式: {generated_by}")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"关系总数: {len(relations)}\n")

        # 统计摘要
        lines.append("## 统计摘要")
        composite_count = len([r for r in relations if r.is_composite])
        single_count = len([r for r in relations if r.is_single_column])
        foreign_key_count = len([r for r in relations if r.relationship_type == "foreign_key"])
        inferred_count = len([r for r in relations if r.relationship_type == "inferred"])

        scores = [self._relation_score(r) for r in relations]
        high_conf = len([
            s for s in scores if s is not None and s >= self.high_confidence_threshold
        ])
        medium_conf = len([
            s for s in scores
            if s is not None
            and self.medium_confidence_threshold <= s < self.high_confidence_threshold
        ])

        lines.append(f"- 外键直通: {foreign_key_count}")
        lines.append(f"- 推断关系: {inferred_count}")
        lines.append(f"- 复合键关系: {composite_count}")
        lines.append(f"- 单列关系: {single_count}")
        lines.append(f"- 高置信度 (≥{self.high_confidence_threshold}): {high_conf}")
        lines.append(f"- 中置信度 ({self.medium_confidence_threshold}-{self.high_confidence_threshold}): {medium_conf}\n")

        # 关系详情
        lines.append("## 关系详情")

        for i, rel in enumerate(relations, 1):
            lines.append(f"### {i}. {rel.source_full_name_with_columns} → {rel.target_full_name_with_columns}")

            # 类型
            rel_type = "复合键" if rel.is_composite else "单列"
            lines.append(f"- **类型**: {rel_type}")

            # 列名
            if rel.is_single_column:
                lines.append(f"- **源列**: `{rel.source_columns[0]}`")
                lines.append(f"- **目标列**: `{rel.target_columns[0]}`")
            else:
                lines.append(f"- **源列**: `{', '.join(rel.source_columns)}`")
                lines.append(f"- **目标列**: `{', '.join(rel.target_columns)}`")

            # 关系类型
            lines.append(f"- **关系类型**: {rel.relationship_type}")

            score = self._relation_score(rel)
            if score is not None:
                level = self._confidence_level(score)
                conf_label = {"high": "高", "medium": "中", "low": "低"}.get(level, "")
                lines.append(f"- **置信度**: {score:.3f} ({conf_label})")

                if rel.score_details:
                    lines.append("- **评分明细**:")
                    for dim, dim_score in rel.score_details.items():
                        lines.append(f"  - {dim}: {dim_score:.3f}")

                if rel.inference_method:
                    lines.append(f"- **推断方法**: {rel.inference_method}")

            lines.append("")  # 空行

        # 写入文件（使用配置的粒度，当前仅支持 global）
        md_file = self.rel_dir / f"{self.database_name}.relationships_{self.rel_granularity}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"Markdown已输出: {md_file}")
        return md_file
