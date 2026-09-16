"""元数据仓库

负责加载Step 2的JSON元数据文件，并提取外键直通关系。
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Set, Any

from metaweave.core.relationships.models import FOREIGN_KEY_COMPOSITE_SCORE, Relation
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.repository")


class MetadataRepository:
    """元数据仓库

    负责：
    1. 加载所有JSON元数据文件
    2. 提取外键直通关系
    3. 生成确定性relationship_id
    """

    HIGH_UNIQUENESS = 0.95  # 单列统计唯一性阈值（与 scorer 使用相同阈值）

    def __init__(
            self,
            json_dir: Path,
            rel_id_salt: str = "",
            logical_key_min_confidence: float = 0.8,
    ):
        """初始化元数据仓库

        Args:
            json_dir: JSON文件目录（Step 2输出）
            rel_id_salt: relationship_id哈希盐（用于命名空间隔离）
            logical_key_min_confidence: 逻辑键最低置信度（与规则候选生成同口径，
                见 doc 19 §3.2.3，不得硬编码固定值）
        """
        self.json_dir = Path(json_dir)
        self.rel_id_salt = rel_id_salt
        self.logical_key_min_confidence = logical_key_min_confidence

        if not self.json_dir.exists():
            raise FileNotFoundError(f"JSON目录不存在: {self.json_dir}")

        logger.info(f"元数据仓库已初始化: {self.json_dir}")

    def load_all_tables(self) -> Dict[str, dict]:
        """加载所有JSON元数据文件

        Returns:
            {full_name: json_data} 字典，其中full_name为"schema.table"
        """
        tables = {}
        json_files = list(self.json_dir.glob("*.json"))

        # 排除模板文件
        json_files = [f for f in json_files if not f.name.startswith("_template")]

        logger.info(f"发现 {len(json_files)} 个JSON文件")

        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                table_info = data.get("table_info", {})
                schema_name = table_info.get("schema_name")
                table_name = table_info.get("table_name")

                if not schema_name or not table_name:
                    logger.warning(f"JSON文件缺少schema_name或table_name: {json_file}")
                    continue

                full_name = f"{schema_name}.{table_name}"
                tables[full_name] = data

                logger.debug(f"加载表: {full_name}")

            except Exception as e:
                logger.error(f"加载JSON文件失败 ({json_file}): {e}")

        logger.info(f"成功加载 {len(tables)} 张表的元数据")
        return tables

    def collect_foreign_keys(self, tables: Dict[str, dict]) -> Tuple[List[Relation], Set[str]]:
        """从JSON元数据中提取外键直通关系

        Args:
            tables: 表元数据字典 {full_name: json_data}

        Returns:
            (pre_existing_relations, fk_relationship_id_set)
            - pre_existing_relations: 外键直通关系列表
            - fk_relationship_id_set: 外键的 relationship_id 集合（用于后续候选去重，双向一致）
        """
        pre_existing_relations: List[Relation] = []
        fk_relationship_id_set: Set[str] = set()

        for full_name, table_data in tables.items():
            table_info = table_data.get("table_info", {})
            source_schema = table_info.get("schema_name")
            source_table = table_info.get("table_name")

            # 从table_profile.physical_constraints.foreign_keys提取
            table_profile = table_data.get("table_profile")
            if not table_profile:
                continue

            physical_constraints = table_profile.get("physical_constraints", {})
            foreign_keys = physical_constraints.get("foreign_keys", [])

            if not foreign_keys:
                continue

            for fk in foreign_keys:
                try:
                    source_columns = fk.get("source_columns", [])
                    target_schema = fk.get("target_schema")
                    target_table = fk.get("target_table")
                    target_columns = fk.get("target_columns", [])

                    if not all([source_columns, target_schema, target_table, target_columns]):
                        logger.warning(f"外键信息不完整: {fk}")
                        continue

                    # 生成relationship_id
                    rel_id = self._generate_relation_id(
                        source_schema, source_table, source_columns,
                        target_schema, target_table, target_columns
                    )

                    # 创建Relation对象
                    relation = Relation(
                        relationship_id=rel_id,
                        source_schema=source_schema,
                        source_table=source_table,
                        source_columns=source_columns,
                        target_schema=target_schema,
                        target_table=target_table,
                        target_columns=target_columns,
                        relationship_type="foreign_key",
                        cardinality=self._infer_cardinality(fk, tables, full_name, target_schema, target_table),
                        constraint_name=fk.get("constraint_name"),
                        composite_score=FOREIGN_KEY_COMPOSITE_SCORE,
                    )

                    pre_existing_relations.append(relation)
                    # 收集 relationship_id 用于去重（双向一致，不受方向影响）
                    fk_relationship_id_set.add(rel_id)

                    logger.debug(f"外键直通: {source_schema}.{source_table}.{source_columns} -> "
                                 f"{target_schema}.{target_table}.{target_columns}")

                except Exception as e:
                    logger.error(f"处理外键失败 ({full_name}): {e}")

        logger.info(f"提取到 {len(pre_existing_relations)} 个外键直通关系")
        return pre_existing_relations, fk_relationship_id_set

    @staticmethod
    def compute_relationship_id(
            source_schema: str,
            source_table: str,
            source_columns: List[str],
            target_schema: str,
            target_table: str,
            target_columns: List[str],
            rel_id_salt: str = ""
    ) -> str:
        """生成确定性relationship_id（静态方法，可复用）

        格式: rel_ + MD5[:12]

        身份口径（2025 统一改造）：身份 = 两张表身份 + 完整列对应对集合。
        对应对集合按 "source_col=target_col" 字符串排序后再拼接，
        不再对 source_columns / target_columns 分别单独排序——分别排序会把
        不同的字段指派错误合并（如 (A.id→B.id, A.code→B.code) 与
        (A.id→B.code, A.code→B.id) 应视为不同关系）。列对应对顺序不同但
        对应关系相同（如整体反转顺序）会生成相同 ID。

        Args:
            source_schema: 源schema
            source_table: 源表
            source_columns: 源列列表
            target_schema: 目标schema
            target_table: 目标表
            target_columns: 目标列列表
            rel_id_salt: 哈希盐（用于命名空间隔离）

        Returns:
            relationship_id（格式: rel_abc123def456）
        """
        if len(source_columns) != len(target_columns):
            raise ValueError(
                "compute_relationship_id: source_columns 与 target_columns "
                "长度必须一致才能生成列对应对身份"
            )

        # 按列对应对（而非分别排序两侧列表）生成规范化签名
        pairs = sorted(f"{s}={t}" for s, t in zip(source_columns, target_columns))

        signature = (
            f"{source_schema}.{source_table}->{target_schema}.{target_table}:"
            f"[{','.join(pairs)}]"
            f"{rel_id_salt}"
        )

        # MD5哈希
        hash_digest = hashlib.md5(signature.encode("utf-8")).hexdigest()
        return f"rel_{hash_digest[:12]}"

    @staticmethod
    def compute_undirected_identity(
            source_schema: str,
            source_table: str,
            source_columns: List[str],
            target_schema: str,
            target_table: str,
            target_columns: List[str],
    ) -> str:
        """无向身份（评分后合并分组键，忽略方向，见 doc 19 §3.3）

        精确算法：
        1. 比较两个表端点（比较键为 (casefold, 原始值) 元组，先忽略大小写、
           相同时以原始字符串兜底），字典序较小的表为规范左端；
        2. 若当前关系方向与规范方向相反，同时交换表端与两侧列；
        3. 在规范方向下对 (left_column, right_column) 配对整体排序；
        4. 用规范表端点与排序后的配对列表生成无向身份。

        禁止分别排序左右字段列表（会把不同的复合指派错误合并）。
        `A(a,b)→B(x,y)` 与 `B(y,x)→A(b,a)` 生成相同无向身份；
        `A(a,b)→B(y,x)` 是另一条身份。

        注意：不含 rel_id_salt——盐只用于最终 relationship_id，不得参与
        候选分组与业务选择。
        """
        if len(source_columns) != len(target_columns):
            raise ValueError(
                "compute_undirected_identity: source_columns 与 target_columns "
                "长度必须一致"
            )

        left_key = (
            (source_schema.casefold(), source_schema),
            (source_table.casefold(), source_table),
        )
        right_key = (
            (target_schema.casefold(), target_schema),
            (target_table.casefold(), target_table),
        )

        if left_key <= right_key:
            left_schema, left_table = source_schema, source_table
            right_schema, right_table = target_schema, target_table
            left_columns, right_columns = list(source_columns), list(target_columns)
        else:
            left_schema, left_table = target_schema, target_table
            right_schema, right_table = source_schema, source_table
            left_columns, right_columns = list(target_columns), list(source_columns)

        pairs = sorted(f"{s}={t}" for s, t in zip(left_columns, right_columns))
        return (
            f"{left_schema}.{left_table}<->{right_schema}.{right_table}:"
            f"[{','.join(pairs)}]"
        )

    def _generate_relation_id(
            self,
            source_schema: str,
            source_table: str,
            source_columns: List[str],
            target_schema: str,
            target_table: str,
            target_columns: List[str]
    ) -> str:
        """生成确定性relationship_id（实例方法，调用静态方法）

        Args:
            source_schema: 源schema
            source_table: 源表
            source_columns: 源列列表
            target_schema: 目标schema
            target_table: 目标表
            target_columns: 目标列列表

        Returns:
            relationship_id（格式: rel_abc123def456）
        """
        return self.compute_relationship_id(
            source_schema=source_schema,
            source_table=source_table,
            source_columns=source_columns,
            target_schema=target_schema,
            target_table=target_table,
            target_columns=target_columns,
            rel_id_salt=self.rel_id_salt
        )

    def _generate_fk_signature(
            self,
            source_schema: str,
            source_table: str,
            source_columns: List[str],
            target_schema: str,
            target_table: str,
            target_columns: List[str]
    ) -> str:
        """生成FK签名（用于候选去重）

        Args:
            source_schema: 源schema
            source_table: 源表
            source_columns: 源列列表
            target_schema: 目标schema
            target_table: 目标表
            target_columns: 目标列列表

        Returns:
            FK签名字符串
        """
        src_cols = sorted(source_columns)
        tgt_cols = sorted(target_columns)

        return (
            f"{source_schema}.{source_table}.[{','.join(src_cols)}]->"
            f"{target_schema}.{target_table}.[{','.join(tgt_cols)}]"
        )

    def _infer_cardinality(
            self,
            fk: Dict[str, Any],
            tables: Dict[str, dict],
            source_full_name: str,
            target_schema: str,
            target_table: str
    ) -> str:
        """推断外键关系的基数（物理 FK 固定为 1:1 / N:1，见 doc 19 §3.2.3）

        - target 端由数据库被引用约束保证唯一（PostgreSQL 允许建立外键，
          本身代表目标列满足被引用约束），不再依赖 JSON 画像验证；
        - source 端唯一 → 1:1；source 不唯一或无法判断 → N:1（保守）。

        Args:
            fk: 外键信息
            tables: 所有表元数据
            source_full_name: 源表全名
            target_schema: 目标schema
            target_table: 目标表名

        Returns:
            基数（1:1 | N:1）
        """
        source_columns = fk["source_columns"]
        target_columns = fk.get("target_columns", fk.get("referenced_columns", []))

        source_is_unique = self._is_columns_unique(tables, source_full_name, source_columns)
        cardinality = "1:1" if source_is_unique else "N:1"

        logger.debug(
            f"外键基数推断: {source_full_name}{source_columns} -> {target_schema}.{target_table}{target_columns}, "
            f"source_unique={source_is_unique}, cardinality={cardinality}"
        )

        return cardinality

    def _is_columns_unique(
            self,
            tables: Dict[str, dict],
            full_name: str,
            columns: List[str]
    ) -> bool:
        """判断列组合（单列或复合列）是否唯一（见 doc 19 §3.2.3）

        优先级：物理约束（PK/UK）> 非部分/非表达式唯一索引 >
        组合级统计证据（单列 statistics 现算 / 复合列 unique_column_sets）。

        复合唯一性证据采用无序字段集合比较（长度相同且规范化字段集合相同），
        该规则仅用于唯一性判断——关系身份、FK 列映射及无向身份仍必须保留
        列的位置对应关系。

        Args:
            tables: 所有表元数据
            full_name: 表全名（schema.table）
            columns: 列名列表

        Returns:
            True: 列是唯一的
            False: 列不唯一或无法判断
        """
        table = tables.get(full_name)
        if not table:
            logger.warning(f"表元数据不存在: {full_name}")
            return False

        profiles = table.get("column_profiles") or {}
        table_profile = table.get("table_profile") or {}
        physical = table_profile.get("physical_constraints", {})

        col_set = set(columns)

        # 1. 主键（单列/复合，无序集合比较）
        pk = physical.get("primary_key")
        if pk and len(pk.get("columns", [])) == len(columns) and set(pk.get("columns", [])) == col_set:
            logger.debug(f"{full_name}.{columns}: 主键，判定为唯一")
            return True

        # 2. 唯一约束（单列/复合，无序集合比较）
        for uk in physical.get("unique_constraints", []):
            if len(uk.get("columns", [])) == len(columns) and set(uk.get("columns", [])) == col_set:
                logger.debug(f"{full_name}.{columns}: 唯一约束，判定为唯一")
                return True

        # 3. 非部分、非表达式、键列完全匹配的唯一索引（无序集合比较）
        for index in table_profile.get("indexes", []) or []:
            if not index.get("is_unique"):
                continue
            if index.get("condition"):
                continue  # 部分唯一索引不算独立证据
            key_expressions = index.get("key_expressions") or []
            index_columns = index.get("columns") or []
            if key_expressions and key_expressions != index_columns:
                continue  # 表达式索引（键改写），键列不直接匹配
            if len(index_columns) == len(columns) and set(index_columns) == col_set:
                logger.debug(f"{full_name}.{columns}: 非部分唯一索引，判定为唯一")
                return True

        # 4. 统计证据（单列与复合口径不同，见 doc 19 §3.2.3）
        if len(columns) == 1:
            col_name = columns[0]
            col_profile = profiles.get(col_name) or {}
            # v3 契约允许 statistics 缺失或为 null——缺失即无法证明唯一，
            # 保守返回不唯一，绝不抛异常让整条 FK 被丢弃
            stats = col_profile.get("statistics") or {}
            uniqueness = stats.get("uniqueness")
            # v3 JSON 的 statistics 只保留原始计数，uniqueness 按
            # unique_count / profiling.sample_count 现算（与契约层同口径）
            if uniqueness is None:
                profiling = table.get("profiling") or {}
                sample_count = profiling.get("sample_count")
                if sample_count and "unique_count" in stats:
                    uniqueness = int(stats["unique_count"]) / int(sample_count)

            if uniqueness is not None and uniqueness >= self.HIGH_UNIQUENESS:
                logger.debug(
                    f"{full_name}.{col_name}: 统计值 uniqueness={uniqueness:.3f} "
                    f">= {self.HIGH_UNIQUENESS}，判定为唯一"
                )
                return True
        else:
            # 复合列：unique_column_sets 组合级证据（禁止"各单列 uniqueness
            # 最小值"推断——(a,b) 组合唯一但各列不唯一时会漏判；反之各列样本
            # 唯一也不能严格证明组合在全表唯一）
            for lk in table_profile.get("unique_column_sets", []) or []:
                lk_columns = lk.get("columns", [])
                if len(lk_columns) != len(columns):
                    continue
                if set(lk_columns) != col_set:
                    continue
                if lk.get("confidence_score", 0.0) >= self.logical_key_min_confidence:
                    logger.debug(
                        f"{full_name}.{columns}: unique_column_sets 逻辑键证据，判定为唯一"
                    )
                    return True

        logger.debug(f"{full_name}.{columns}: 未满足唯一条件")
        return False
