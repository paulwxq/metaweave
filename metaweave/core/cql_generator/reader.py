"""Step 4 JSON 读取器

读取 Step 2 的表/列画像 JSON 和 Step 3 的表间关系 JSON。
"""

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Tuple

from metaweave.core.cql_generator.models import (
    TableNode,
    ColumnNode,
    HASColumnRelation,
    JOINOnRelation,
    RelationshipFilterStats,
)

logger = logging.getLogger("metaweave.cql_generator.reader")


@dataclass
class RawRelationshipEntry:
    """reader 内部实现(doc 18 §5):原始关系 + 来源文件,供冲突报错使用,不外露"""
    relationship: Dict[str, Any]
    source_file: Path


class JSONReader:
    """JSON 文件读取器

    负责读取 Step 2 和 Step 3 的 JSON 文件，并转换为内部数据模型。
    """

    def __init__(
            self,
            json_dir: Path,
            rel_dir: Path,
            domain_resolver=None,
            composite_score_threshold: float = 0.9,
    ):
        """初始化读取器

        Args:
            json_dir: Step 2 JSON 目录（表/列画像）
            rel_dir: Step 3 JSON 目录（表间关系）
            domain_resolver: DomainResolver 实例，用于从 YAML 获取 table_domains
            composite_score_threshold: CQL 置信度阈值（doc 18，由 generator
                校验后透传；推断关系 composite_score >= 阈值才进入 CQL）
        """
        self.json_dir = Path(json_dir)
        self.rel_dir = Path(rel_dir)
        self.domain_resolver = domain_resolver
        self.composite_score_threshold = composite_score_threshold
        self.database_name: str | None = None

        if not self.json_dir.exists():
            raise ValueError(f"JSON 目录不存在: {self.json_dir}")
        if not self.rel_dir.exists():
            raise ValueError(f"关系目录不存在: {self.rel_dir}")

    def read_all(self) -> Tuple[
        List[TableNode],
        List[ColumnNode],
        List[HASColumnRelation],
        List[JOINOnRelation],
        RelationshipFilterStats,
    ]:
        """读取所有数据

        Returns:
            (tables, columns, has_column_rels, join_on_rels, filter_stats)
        """
        logger.info("开始读取 Step 2 和 Step 3 的 JSON 文件...")

        # 读取 Step 2 表/列画像
        tables, columns, has_column_rels = self._read_table_profiles()

        # 读取 Step 3 表间关系
        join_on_rels, filter_stats = self._read_relationships()

        # 注意：不再动态回填 logic_fk
        # logic_fk 保持 Step 2 画像中的初始值（通常为空列表）
        # 关系方向已在 Step 3 输出时翻转为标准 ER 语义

        logger.info(
            f"读取完成: "
            f"{len(tables)} 张表, "
            f"{len(columns)} 个列, "
            f"{len(join_on_rels)} 个关系"
        )

        return tables, columns, has_column_rels, join_on_rels, filter_stats

    def _read_table_profiles(self) -> Tuple[
        List[TableNode],
        List[ColumnNode],
        List[HASColumnRelation]
    ]:
        """读取 Step 2 表/列画像

        Returns:
            (tables, columns, has_column_rels)
        """
        tables = []
        columns = []
        has_column_rels = []

        # 获取所有 JSON 文件，但过滤掉模板文件
        all_json_files = list(self.json_dir.glob("*.json"))
        json_files = []

        for f in all_json_files:
            # 跳过以 _ 或 . 开头的文件（模板文件和隐藏文件）
            if f.name.startswith("_") or f.name.startswith("."):
                logger.debug(f"跳过模板文件: {f.name}")
                continue
            json_files.append(f)

        logger.info(
            f"找到 {len(json_files)} 个有效 JSON 文件"
            f"（已过滤 {len(all_json_files) - len(json_files)} 个模板文件）"
        )

        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 验证表名不是占位符
                table_info = data.get("object_info", {})
                table_name = table_info.get("object_name", "")

                if not table_name or table_name in ["table_name", "object_name", "placeholder", "example"]:
                    logger.warning(
                        f"跳过占位符表: {json_file.name} (object_name={table_name})"
                    )
                    continue

                # 提取表信息
                table = self._extract_table(data)
                tables.append(table)

                # 提取列信息
                table_columns = self._extract_columns(data, table.full_name)
                columns.extend(table_columns)

                # 创建 HAS_COLUMN 关系
                for col in table_columns:
                    has_column_rels.append(
                        HASColumnRelation(
                            table_full_name=table.full_name,
                            column_full_name=col.full_name
                        )
                    )

            except Exception as e:
                logger.error(f"读取文件失败: {json_file}, 错误: {e}")
                raise

        return tables, columns, has_column_rels

    def _extract_table(self, data: Dict[str, Any]) -> TableNode:
        """从 JSON 中提取表信息"""
        table_info = data.get("object_info", {})
        table_profile = data.get("table_profile", {})
        physical_constraints = table_profile.get("physical_constraints", {})

        database = table_info.get("database")
        if database:
            if self.database_name is None:
                self.database_name = database
            elif self.database_name != database:
                raise ValueError(
                    f"JSON 目录包含多个 database: {self.database_name} vs {database}"
                )

        schema = table_info.get("schema_name", "")
        name = table_info.get("object_name", "")
        full_name = f"{schema}.{name}"

        # 提取物理主键（符合 list<string> 规范）
        pk_data = physical_constraints.get("primary_key")
        if pk_data and isinstance(pk_data, dict):
            # Step 2 格式: {"constraint_name": "...", "columns": [...]}
            pk = pk_data.get("columns", [])
        elif pk_data and isinstance(pk_data, list):
            # 已经是列表格式
            pk = pk_data
        else:
            pk = []

        # 提取唯一约束（符合 list<list<string>> 规范）
        uk = []
        for uk_data in physical_constraints.get("unique_constraints", []):
            if isinstance(uk_data, dict):
                # Step 2 格式: {"constraint_name": "...", "columns": [...]}
                columns = uk_data.get("columns", [])
                if columns:
                    uk.append(columns)
            elif isinstance(uk_data, list):
                # 已经是列表格式
                if uk_data:
                    uk.append(uk_data)

        # 提取外键（只保留源列名，转换为二维数组，与 indexes/logic_pk 格式一致）
        fk = []
        for fk_data in physical_constraints.get("foreign_keys", []):
            source_columns = fk_data.get("source_columns", [])
            if source_columns:  # 只添加非空的列列表
                fk.append(source_columns)

        # 提取索引（只保留列名列表，符合 list<list<string>> 规范）
        # 注意：indexes 现在位于 table_profile 层级，不在 physical_constraints 中
        indexes = []
        for idx_data in table_profile.get("indexes", []):
            columns = idx_data.get("columns", [])
            if columns:  # 只添加非空的列列表
                indexes.append(columns)

        # 提取候选逻辑主键（confidence >= 0.8）
        # 注意：使用 unique_column_sets 替代 logical_keys.candidate_primary_keys
        logic_pk = []
        unique_column_sets = table_profile.get("unique_column_sets", [])
        for candidate in unique_column_sets:
            confidence = candidate.get("confidence_score", 0.0)
            if confidence >= 0.8:
                logic_pk.append(candidate.get("columns", []))

        return TableNode(
            full_name=full_name,
            schema=schema,
            name=name,
            database=self.database_name,
            comment=table_info.get("comment"),
            object_type=table_info.get("object_type", "table"),
            pk=pk,
            uk=uk,
            fk=fk,
            logic_pk=logic_pk,
            logic_fk=[],  # 稍后从关系中填充
            logic_uk=[],  # 预留
            indexes=indexes,
            table_domains=self._resolve_table_domains(full_name, table_profile),
            table_category=table_profile.get("table_category"),
        )

    def _resolve_table_domains(self, full_name: str, table_profile: dict) -> list:
        """从 DomainResolver 获取 table_domains"""
        if self.domain_resolver and self.database_name:
            return self.domain_resolver.get_domains_for_schema_table(
                full_name, self.database_name
            )
        return []

    def _extract_columns(
        self,
        data: Dict[str, Any],
        table_full_name: str
    ) -> List[ColumnNode]:
        """从 JSON 中提取列信息"""
        table_info = data.get("object_info", {})
        database = table_info.get("database")
        if database:
            if self.database_name is None:
                self.database_name = database
            elif self.database_name != database:
                raise ValueError(
                    f"JSON 目录包含多个 database: {self.database_name} vs {database}"
                )
        schema = table_info.get("schema_name", "")
        table_name = table_info.get("object_name", "")

        column_profiles = data.get("column_profiles", {})
        table_profile = data.get("table_profile", {})
        physical_constraints = table_profile.get("physical_constraints", {})

        # 获取物理主键列表（提取 columns 字段）
        pk_data = physical_constraints.get("primary_key")
        if pk_data and isinstance(pk_data, dict):
            # Step 2 格式: {"constraint_name": "...", "columns": [...]}
            pk_columns = pk_data.get("columns", [])
        elif pk_data and isinstance(pk_data, list):
            # 已经是列表格式
            pk_columns = pk_data
        else:
            pk_columns = []

        # 获取唯一约束列表（扁平化，提取 columns 字段）
        uk_columns = set()
        for uk_data in physical_constraints.get("unique_constraints", []):
            if isinstance(uk_data, dict):
                # Step 2 格式: {"constraint_name": "...", "columns": [...]}
                columns = uk_data.get("columns", [])
                uk_columns.update(columns)
            elif isinstance(uk_data, list):
                # 已经是列表格式
                uk_columns.update(uk_data)

        # 获取外键列表（扁平化）
        fk_columns = set()
        for fk_data in physical_constraints.get("foreign_keys", []):
            fk_columns.update(fk_data.get("source_columns", []))

        columns = []
        for col_name, col_data in column_profiles.items():
            # 基本信息
            full_name = f"{schema}.{table_name}.{col_name}"
            data_type = col_data.get("data_type", "")
            comment = col_data.get("comment")

            # 语义角色
            semantic_analysis = col_data.get("semantic_analysis", {})
            semantic_role = semantic_analysis.get("semantic_role")

            # 结构标志
            structure_flags = col_data.get("structure_flags", {})

            # 判断是否是主键/唯一键/外键
            is_pk = col_name in pk_columns
            is_uk = col_name in uk_columns
            is_fk = col_name in fk_columns

            # 判断是否是时间/度量字段
            is_time = semantic_role == "datetime"
            is_measure = semantic_role == "metric"

            # 主键位置
            pk_position = 0
            if is_pk and col_name in pk_columns:
                pk_position = pk_columns.index(col_name) + 1

            # 统计信息
            statistics = col_data.get("statistics", {})
            uniqueness = statistics.get("uniqueness", 0.0)
            null_rate = statistics.get("null_rate", 0.0)

            columns.append(
                ColumnNode(
                    full_name=full_name,
                    schema=schema,
                    table=table_name,
                    name=col_name,
                    data_type=data_type,
                    database=self.database_name,
                    comment=comment,
                    semantic_role=semantic_role,
                    is_pk=is_pk,
                    is_uk=is_uk,
                    is_fk=is_fk,
                    is_time=is_time,
                    is_measure=is_measure,
                    pk_position=pk_position,
                    uniqueness=uniqueness,
                    null_rate=null_rate
                )
            )

        return columns

    def _read_relationships(
            self,
    ) -> Tuple[List[JOINOnRelation], RelationshipFilterStats]:
        """读取 Step 3 表间关系(doc 18 八步流程)

        文件循环只读取并汇总原始关系(保留来源文件);随后统一:
        ①校验 ID → ②校验结构 → ③校验分数 → ④同 ID 冲突检查 →
        ⑤阈值过滤 → ⑥重复 ID 去重 → ⑦转换为 JOINOnRelation。
        """
        rel_files = list(self.rel_dir.glob("*.relationships_*.json"))
        if not rel_files:
            logger.warning(f"未找到关系文件: {self.rel_dir}/*.relationships_*.json")
            return [], RelationshipFilterStats()

        logger.info(f"找到 {len(rel_files)} 个关系文件")

        # ---- 第 1 步:读取全部文件,汇总原始关系(保留来源文件) ----
        raw_entries: List[RawRelationshipEntry] = []
        for rel_file in rel_files:
            try:
                with open(rel_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"读取关系文件失败: {rel_file}, 错误: {e}")
                raise
            relationships = data.get("relationships", [])
            logger.info(f"从 {rel_file.name} 读取 {len(relationships)} 个关系")
            for rel in relationships:
                raw_entries.append(
                    RawRelationshipEntry(relationship=rel, source_file=rel_file)
                )

        stats = RelationshipFilterStats(candidate_count=len(raw_entries))

        def _fail(entry: RawRelationshipEntry, message: str) -> None:
            rel_id = entry.relationship.get("relationship_id", "<缺失>")
            raise ValueError(
                f"关系数据校验失败 [{entry.source_file.name}] "
                f"relationship_id={rel_id!r}: {message}"
            )

        # ---- 第 2 步:校验 relationship_id(所有关系,含 FK 直通) ----
        for entry in raw_entries:
            rel_id = entry.relationship.get("relationship_id")
            if not isinstance(rel_id, str) or not rel_id.strip():
                _fail(entry, "relationship_id 缺失 / null / 空串 / 纯空白 / 非字符串")
            if rel_id != rel_id.strip():
                _fail(entry, f"relationship_id 存在首尾空白: {rel_id!r}")

        # ---- 第 3 步:校验关系结构(canonical_payload 构造之前) ----
        for entry in raw_entries:
            rel = entry.relationship
            rel_type = rel.get("type")
            if rel_type not in ("single_column", "composite"):
                _fail(entry, f"type 必须严格为 single_column / composite,得到 {rel_type!r}")

            for key in ("from_table", "to_table"):
                info = rel.get(key)
                if not isinstance(info, dict):
                    _fail(entry, f"{key} 必须是对象,得到 {type(info).__name__}")
                schema = info.get("schema")
                table = info.get("table")
                if not (isinstance(schema, str) and schema.strip()) or not (
                        isinstance(table, str) and table.strip()
                ):
                    _fail(entry, f"{key}.schema / table 无效")

            if rel_type == "single_column":
                from_col = rel.get("from_column")
                to_col = rel.get("to_column")
                if not (isinstance(from_col, str) and from_col.strip()):
                    _fail(entry, "from_column 必须是非空字符串(去空白后非空)")
                if not (isinstance(to_col, str) and to_col.strip()):
                    _fail(entry, "to_column 必须是非空字符串(去空白后非空)")
                from_columns = [from_col]
                to_columns = [to_col]
            else:
                from_columns = rel.get("from_columns")
                to_columns = rel.get("to_columns")
                if not isinstance(from_columns, list) or not from_columns:
                    _fail(entry, "from_columns 必须是非空列表")
                if not isinstance(to_columns, list) or not to_columns:
                    _fail(entry, "to_columns 必须是非空列表")
                for col in list(from_columns) + list(to_columns):
                    if not (isinstance(col, str) and col.strip()):
                        _fail(entry, f"字段列表元素必须是非空字符串(去空白后非空): {col!r}")

            if len(from_columns) != len(to_columns):
                _fail(entry, f"两侧字段数量不一致: {len(from_columns)} vs {len(to_columns)}")

            cardinality = rel.get("cardinality")
            if cardinality not in ("N:1", "1:1", "M:N"):
                _fail(
                    entry,
                    f"cardinality 必须显式存在且 ∈ {{N:1, 1:1, M:N}},得到 "
                    f"{cardinality!r}(1:N 违反 doc 19 输出契约)",
                )

            discovery_method = rel.get("discovery_method")
            if not (isinstance(discovery_method, str) and discovery_method.strip()):
                _fail(entry, "discovery_method 必须是非空字符串")

        # ---- 第 4 步:校验推断关系分数(FK 直通豁免) ----
        for entry in raw_entries:
            rel = entry.relationship
            if rel.get("discovery_method") == "foreign_key_constraint":
                continue
            score = rel.get("composite_score")
            if isinstance(score, bool):
                _fail(entry, f"composite_score 不允许布尔值: {score!r}")
            if not isinstance(score, (int, float)):
                _fail(entry, f"composite_score 缺失或类型非法: {score!r}")
            if not math.isfinite(score):
                _fail(entry, f"composite_score 必须有限: {score!r}")
            if not (0.0 <= score <= 1.0):
                _fail(entry, f"composite_score 越界: {score!r}")

        # ---- 第 5 步:按 relationship_id 分组检查载荷冲突 ----
        def _canonical_payload(entry: RawRelationshipEntry) -> tuple:
            rel = entry.relationship
            if rel.get("type") == "single_column":
                from_columns = [rel["from_column"]]
                to_columns = [rel["to_column"]]
            else:
                from_columns = rel["from_columns"]
                to_columns = rel["to_columns"]
            payload = (
                rel.get("type"),
                (rel["from_table"]["schema"], rel["from_table"]["table"]),
                (rel["to_table"]["schema"], rel["to_table"]["table"]),
                tuple(sorted(zip(from_columns, to_columns))),
                rel.get("discovery_method"),
                rel.get("cardinality"),
                rel.get("constraint_name"),
            )
            # 推断关系的 composite_score 参与冲突比较;FK 分数不参与
            if rel.get("discovery_method") != "foreign_key_constraint":
                payload += (rel.get("composite_score"),)
            return payload

        groups: Dict[str, List[RawRelationshipEntry]] = {}
        for entry in raw_entries:
            rel_id = entry.relationship["relationship_id"]
            groups.setdefault(rel_id, []).append(entry)

        for rel_id, group in groups.items():
            if len(group) < 2:
                continue
            base = _canonical_payload(group[0])
            for other in group[1:]:
                if _canonical_payload(other) != base:
                    raise ValueError(
                        f"关系数据冲突: relationship_id={rel_id!r} 在 "
                        f"[{group[0].source_file.name}] 与 "
                        f"[{other.source_file.name}] 载荷不一致"
                        f"(防御哈希碰撞 / 目录混入不同批次产物)"
                    )

        # ---- 第 6 步:阈值过滤(FK 豁免) ----
        threshold = self.composite_score_threshold
        passed: List[RawRelationshipEntry] = []
        for entry in raw_entries:
            rel = entry.relationship
            if rel.get("discovery_method") == "foreign_key_constraint":
                passed.append(entry)
                continue
            if rel.get("composite_score") >= threshold:
                passed.append(entry)
        stats.threshold_passed_count = len(passed)
        stats.threshold_filtered_count = len(raw_entries) - len(passed)

        # ---- 第 7 步:重复 ID 去重(字典序排序,载荷已确认一致) ----
        passed.sort(key=lambda e: e.relationship["relationship_id"])
        id_counts: Dict[str, int] = {}
        for entry in passed:
            rel_id = entry.relationship["relationship_id"]
            id_counts[rel_id] = id_counts.get(rel_id, 0) + 1
        stats.duplicate_group_count = sum(1 for n in id_counts.values() if n > 1)

        seen: set = set()
        deduped: List[RawRelationshipEntry] = []
        for entry in passed:
            rel_id = entry.relationship["relationship_id"]
            if rel_id in seen:
                continue
            seen.add(rel_id)
            deduped.append(entry)
        stats.duplicate_discarded_count = len(passed) - len(deduped)
        stats.final_count = len(deduped)

        # ---- 第 8 步:转换为 JOINOnRelation ----
        join_on_rels = []
        for entry in deduped:
            join_rel = self._extract_join_relation(entry.relationship)
            if join_rel:
                join_on_rels.append(join_rel)

        # 统计恒等式(doc 18 §5,以"先冲突检查、再过滤、再去重"为前提)
        assert stats.candidate_count == (
                stats.threshold_passed_count + stats.threshold_filtered_count
        ), f"统计恒等式不成立: {stats}"
        assert stats.final_count == (
                stats.threshold_passed_count - stats.duplicate_discarded_count
        ), f"统计恒等式不成立: {stats}"

        return join_on_rels, stats

    def _extract_join_relation(self, rel: Dict[str, Any]) -> JOINOnRelation:
        """从关系 JSON 中提取 JOIN_ON 关系

        方向处理（doc 19）：**纯消费，不翻转**。rel 产物方向已统一——
        N:1 恒为引用方→键端，1:1 / M:N 为 rel 已确定的规范方向，
        CQL 不再自行改变任何关系方向。
        """
        from_table = rel.get("from_table", {})
        to_table = rel.get("to_table", {})
        # cardinality 已由 _read_relationships 结构校验保证显式存在且合法
        cardinality = rel["cardinality"]

        logger.debug(f"处理关系: {from_table.get('table')} -> {to_table.get('table')}, cardinality={cardinality}")

        src_schema = from_table.get("schema", "")
        src_table = from_table.get("table", "")
        dst_schema = to_table.get("schema", "")
        dst_table = to_table.get("table", "")

        rel_type = rel.get("type", "")
        if rel_type == "single_column":
            source_columns = [rel.get("from_column", "")]
            target_columns = [rel.get("to_column", "")]
        else:
            source_columns = rel.get("from_columns", [])
            target_columns = rel.get("to_columns", [])

        src_full_name = f"{src_schema}.{src_table}"
        dst_full_name = f"{dst_schema}.{dst_table}"
        
        # 构造 ON 表达式
        on_parts = []
        for src_col, tgt_col in zip(source_columns, target_columns):
            on_parts.append(f"SRC.{src_col} = DST.{tgt_col}")
        on_expr = " AND ".join(on_parts)
        
        logger.info(f"CQL 关系: ({src_full_name})-[:JOIN_ON]->({dst_full_name}), cardinality={cardinality}")
        
        return JOINOnRelation(
            relationship_id=rel["relationship_id"],
            src_full_name=src_full_name,
            dst_full_name=dst_full_name,
            cardinality=cardinality,
            join_type="INNER JOIN",
            on=on_expr,
            source_columns=source_columns,
            target_columns=target_columns,
            constraint_name=rel.get("constraint_name")
        )
