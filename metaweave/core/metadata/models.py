"""数据模型定义

定义元数据生成过程中使用的所有数据结构。
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
import json

from metaweave.utils.data_utils import format_data_type


SUPPORTED_DATABASE_OBJECT_TYPES = frozenset(
    {"table", "view", "materialized_view"}
)


def normalize_database_object_types(configured: Any) -> List[str]:
    """校验并规范化数据库对象类型列表，保持配置顺序并去重。"""
    if not isinstance(configured, list) or not configured:
        raise ValueError(
            "database.include_object_types 必须是非空列表，可选值: "
            "table, view, materialized_view"
        )

    normalized = []
    for value in configured:
        object_type = str(value).strip().lower()
        if object_type not in SUPPORTED_DATABASE_OBJECT_TYPES:
            raise ValueError(
                f"不支持的数据库对象类型: {value!r}；可选值: "
                "table, view, materialized_view"
            )
        if object_type not in normalized:
            normalized.append(object_type)
    return normalized


@dataclass(frozen=True)
class DatabaseObjectRef:
    """PostgreSQL 中可由元数据流程处理的数据库对象。"""

    schema_name: str
    object_name: str
    object_type: str


@dataclass
class ColumnInfo:
    """字段信息"""
    column_name: str
    ordinal_position: int
    data_type: str
    character_maximum_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    is_nullable: bool = True
    column_default: Optional[str] = None
    comment: str = ""
    comment_source: str = "db"  # db / ddl / llm_generated / 空字符串
    statistics: Optional[Dict[str, Any]] = None  # 列统计信息

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class PrimaryKey:
    """主键约束"""
    constraint_name: str
    columns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class ForeignKey:
    """外键约束"""
    constraint_name: str
    source_columns: List[str] = field(default_factory=list)
    target_schema: str = ""
    target_table: str = ""
    target_columns: List[str] = field(default_factory=list)
    on_delete: str = "NO ACTION"
    on_update: str = "NO ACTION"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class UniqueConstraint:
    """唯一约束"""
    constraint_name: str
    columns: List[str] = field(default_factory=list)
    is_partial: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class IndexInfo:
    """索引信息"""
    index_name: str
    index_type: str = "btree"  # btree, hash, gist, gin, etc.
    columns: List[str] = field(default_factory=list)
    is_unique: bool = False
    is_primary: bool = False
    condition: Optional[str] = None
    is_constraint_backed: bool = False
    constraint_name: Optional[str] = None
    definition: Optional[str] = None

    # JSON v3 用于区分普通索引键、表达式键和 INCLUDE 列。None 表示旧抽取
    # 路径没有提供该事实；空列表表示已抽取且确认为空。
    included_columns: Optional[List[str]] = None
    key_expressions: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        if self.included_columns is None:
            result.pop("included_columns")
        if self.key_expressions is None:
            result.pop("key_expressions")
        return result

    def to_json_dict(self) -> Dict[str, Any]:
        """转换为当前 JSON 元数据格式的索引结构。"""
        result = asdict(self)
        result["included_columns"] = list(self.included_columns or [])
        result["key_expressions"] = (
            list(self.key_expressions)
            if self.key_expressions is not None
            else list(self.columns)
        )
        return result


@dataclass
class LogicalKey:
    """逻辑主键"""
    columns: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    uniqueness: float = 0.0
    null_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class TableMetadata:
    """表元数据"""
    schema_name: str
    table_name: str
    database: Optional[str] = None  # 数据库名称
    table_type: str = "table"  # table, view, materialized_view
    comment: str = ""
    comment_source: str = "db"  # db / ddl / llm_generated / 空字符串
    row_count: int = 0
    columns: List[ColumnInfo] = field(default_factory=list)
    primary_keys: List[PrimaryKey] = field(default_factory=list)
    foreign_keys: List[ForeignKey] = field(default_factory=list)
    unique_constraints: List[UniqueConstraint] = field(default_factory=list)
    indexes: List[IndexInfo] = field(default_factory=list)
    candidate_logical_primary_keys: List[LogicalKey] = field(default_factory=list)
    sample_records: List[Dict[str, Any]] = field(default_factory=list)
    column_profiles: Dict[str, "ColumnProfile"] = field(default_factory=dict)
    table_profile: Optional["TableProfile"] = None
    view_definition: Optional[str] = None

    def to_dict(
        self,
        *,
        include_generation_timestamp: bool = True,
        profiling_sample_method: str = "limit",
        profiling_sample_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """转换为当前 JSON 元数据格式。"""
        return self._to_json_dict(
            include_generation_timestamp=include_generation_timestamp,
            profiling_sample_method=profiling_sample_method,
            profiling_sample_count=profiling_sample_count,
        )

    def _to_json_dict(
        self,
        *,
        include_generation_timestamp: bool,
        profiling_sample_method: str,
        profiling_sample_count: Optional[int],
    ) -> Dict[str, Any]:
        """转换为精简后的 JSON 元数据格式。"""
        effective_sample_count = profiling_sample_count
        if effective_sample_count is None:
            for column in self.columns:
                statistics = column.statistics or {}
                if "sample_count" in statistics:
                    effective_sample_count = int(statistics["sample_count"])
                    break

        data: Dict[str, Any] = {"metadata_version": "3.0"}
        if include_generation_timestamp:
            data["generated_timestamp"] = datetime.now().isoformat()
        data["table_info"] = {
            "database": self.database,
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "table_type": self.table_type,
            "comment": self.comment,
            "comment_source": self.comment_source,
            "total_rows": self.row_count,
        }
        if effective_sample_count is not None:
            data["profiling"] = {
                "sample_method": profiling_sample_method,
                "sample_count": effective_sample_count,
            }

        data["column_profiles"] = {}
        columns_by_name = {column.column_name: column for column in self.columns}
        for name, profile in self.column_profiles.items():
            column = columns_by_name.get(name)
            if column is None:
                continue
            column_data: Dict[str, Any] = {
                "ordinal_position": column.ordinal_position,
                "data_type": format_data_type(
                    column.data_type,
                    char_length=column.character_maximum_length,
                    numeric_precision=column.numeric_precision,
                    numeric_scale=column.numeric_scale,
                ).lower(),
                "is_nullable": column.is_nullable,
                "column_default": column.column_default,
                "comment": column.comment,
                "comment_source": column.comment_source,
                "semantic_analysis": {
                    "semantic_role": profile.semantic_role,
                    "semantic_confidence": profile.semantic_confidence,
                    "inference_basis": list(profile.inference_basis),
                },
            }
            compact_statistics = self._compact_v3_statistics(column.statistics)
            if compact_statistics:
                column_data["statistics"] = compact_statistics
            data["column_profiles"][name] = column_data

        data["table_profile"] = (
            self.table_profile.to_json_dict(self) if self.table_profile else None
        )

        return data

    @staticmethod
    def _compact_v3_statistics(
        statistics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """只保留 v3 标准产物需要的不可派生统计事实。"""
        if not statistics:
            return {}
        retained = {}
        for key in ("null_count", "unique_count", "min", "max", "value_distribution"):
            if key in statistics and statistics[key] is not None:
                retained[key] = statistics[key]
        return retained

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
        )

    @property
    def full_name(self) -> str:
        """获取完整表名"""
        return f"{self.schema_name}.{self.table_name}"


@dataclass
class CommentTask:
    """LLM 注释生成任务"""
    task_type: str  # 'table' or 'column'
    schema_name: str
    table_name: str
    column_name: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def get_cache_key(self) -> str:
        """获取缓存键"""
        if self.task_type == "table":
            return f"table:{self.schema_name}.{self.table_name}"
        else:
            return f"column:{self.schema_name}.{self.table_name}.{self.column_name}"


@dataclass
class GenerationResult:
    """元数据生成结果"""
    success: bool
    processed_tables: int = 0
    failed_tables: int = 0
    generated_comments: int = 0
    logical_keys_found: int = 0
    output_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    physical_primary_key_constraints_found: int = 0
    physical_foreign_key_constraints_found: int = 0
    unique_constraints_found: int = 0
    indexes_found: int = 0
    regular_indexes_found: int = 0
    unique_indexes_found: int = 0
    processed_object_counts: Dict[str, int] = field(default_factory=dict)
    llm_request_count: int = 0
    llm_success_count: int = 0
    llm_failure_count: int = 0
    llm_comment_success_count: int = 0
    llm_comment_failure_count: int = 0
    llm_object_comment_success_count: int = 0
    llm_object_comment_failure_count: int = 0
    llm_column_comment_success_count: int = 0
    llm_column_comment_failure_count: int = 0
    llm_classification_success_count: int = 0
    llm_classification_failure_count: int = 0
    table_category_counts: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def add_error(self, error: str):
        """添加错误信息"""
        self.errors.append(error)
    
    def add_output_file(self, file_path: str):
        """添加输出文件"""
        self.output_files.append(file_path)


@dataclass
class SampleData:
    """样本数据"""
    schema_name: str
    table_name: str
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
        }


# ---------------------------------------------------------------------------
# Profiling-related data structures
# ---------------------------------------------------------------------------


@dataclass
class StructureFlags:
    is_primary_key: bool = False
    is_composite_primary_key_member: bool = False
    is_foreign_key: bool = False
    is_composite_foreign_key_member: bool = False
    is_unique: bool = False
    is_composite_unique_member: bool = False
    is_unique_constraint: bool = False
    is_composite_unique_constraint_member: bool = False
    is_indexed: bool = False
    is_composite_indexed_member: bool = False
    is_nullable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdentifierInfo:
    naming_pattern: str
    is_surrogate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MetricInfo:
    metric_category: str
    suggested_aggregations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DateTimeInfo:
    datetime_type: str
    datetime_grain: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EnumInfo:
    cardinality: int
    cardinality_level: str
    values: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditInfo:
    """审计字段信息"""
    audit_type: str  # timestamp, actor, flag, version, etl
    description: str  # 字段用途描述

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DescriptionInfo:
    """描述字段信息"""
    avg_length: float  # 平均长度
    max_length: int  # 最大长度
    length_variance: float  # 长度标准差
    is_rich_text: bool = False  # 是否包含富文本（HTML/Markdown）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PrimaryKeyProfileInfo:
    source: str  # constraint | logical
    confidence: Optional[float] = None
    is_single_column: bool = True
    composite_columns: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ForeignKeyProfileInfo:
    target_schema: str
    target_table: str
    target_columns: List[str]
    on_delete: str
    on_update: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IndexProfileInfo:
    index_name: str
    index_type: str
    is_unique: bool
    position: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ColumnProfile:
    column_name: str
    semantic_role: str
    semantic_confidence: float
    structure_flags: StructureFlags
    identifier_info: Optional[IdentifierInfo] = None
    metric_info: Optional[MetricInfo] = None
    datetime_info: Optional[DateTimeInfo] = None
    enum_info: Optional[EnumInfo] = None
    audit_info: Optional["AuditInfo"] = None
    description_info: Optional["DescriptionInfo"] = None
    primary_key_info: Optional[PrimaryKeyProfileInfo] = None
    foreign_key_info: Optional[ForeignKeyProfileInfo] = None
    index_info: Optional[IndexProfileInfo] = None
    inference_basis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        # 基础字段
        result = {
            "column_name": self.column_name,
        }
        
        # 添加 semantic_analysis 分组
        result["semantic_analysis"] = {
            "semantic_role": self.semantic_role,
            "semantic_confidence": self.semantic_confidence,
            "inference_basis": self.inference_basis,
        }
        
        result["structure_flags"] = self.structure_flags.to_dict()
        
        # 将所有 *_info 字段归类到 role_specific_info 下
        role_specific_info = {}
        if self.identifier_info:
            role_specific_info["identifier_info"] = self.identifier_info.to_dict()
        if self.metric_info:
            role_specific_info["metric_info"] = self.metric_info.to_dict()
        if self.datetime_info:
            role_specific_info["datetime_info"] = self.datetime_info.to_dict()
        if self.enum_info:
            role_specific_info["enum_info"] = self.enum_info.to_dict()
        if self.audit_info:
            role_specific_info["audit_info"] = self.audit_info.to_dict()
        if self.description_info:
            role_specific_info["description_info"] = self.description_info.to_dict()
        if self.primary_key_info:
            role_specific_info["primary_key_info"] = self.primary_key_info.to_dict()
        if self.foreign_key_info:
            role_specific_info["foreign_key_info"] = self.foreign_key_info.to_dict()
        if self.index_info:
            role_specific_info["index_info"] = self.index_info.to_dict()
        
        result["role_specific_info"] = role_specific_info
        
        return result


@dataclass
class ColumnStatisticsSummary:
    total_columns: int
    identifier_count: int
    metric_count: int
    datetime_count: int
    enum_count: int
    audit_count: int
    attribute_count: int
    primary_key_count: int
    foreign_key_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KeyColumnsSummary:
    primary_keys: List[str] = field(default_factory=list)
    logical_primary_keys: List[str] = field(default_factory=list)
    foreign_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FactTableInfo:
    grain: List[str]
    metrics: List[str]
    dimensions: List[str]
    time_dimension: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DimTableInfo:
    natural_key: Optional[str]
    surrogate_key: Optional[str]
    attributes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BridgeTableInfo:
    foreign_key_pairs: List[List[str]]
    weight_columns: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableProfile:
    table_category: str
    confidence: float
    column_statistics: ColumnStatisticsSummary
    key_columns: KeyColumnsSummary
    # 已移除未使用的字段（2025-12-26）:
    # - fact_table_info: Optional[FactTableInfo]
    # - dim_table_info: Optional[DimTableInfo]
    # - bridge_table_info: Optional[BridgeTableInfo]
    inference_basis: List[str] = field(default_factory=list)
    candidate_logical_primary_keys: List["LogicalKey"] = field(default_factory=list)

    def to_dict(self, metadata: Optional['TableMetadata'] = None) -> Dict[str, Any]:
        result = {
            "table_category": self.table_category,
            "confidence": self.confidence,
            "inference_basis": self.inference_basis,
        }
        
        # 添加 physical_constraints（从 metadata 获取，不包含 indexes）
        if metadata:
            result["physical_constraints"] = {
                "primary_key": metadata.primary_keys[0].to_dict() if metadata.primary_keys else None,
                "foreign_keys": [fk.to_dict() for fk in metadata.foreign_keys],
                "unique_constraints": [uc.to_dict() for uc in metadata.unique_constraints],
            }
            
            # indexes 提升到 table_profile 层级
            result["indexes"] = [idx.to_dict() for idx in metadata.indexes]
        
        # column_statistics
        result["column_statistics"] = self.column_statistics.to_dict()
        
        # unique_column_sets 替代 logical_keys
        if self.candidate_logical_primary_keys:
            result["unique_column_sets"] = [lk.to_dict() for lk in self.candidate_logical_primary_keys]

        # 已移除：表类型特定信息（fact_table_info/dim_table_info/bridge_table_info）
        # 这些字段在项目中未被使用，已于 2025-12-26 移除以减少维护成本

        return result

    def to_json_dict(self, metadata: 'TableMetadata') -> Dict[str, Any]:
        """转换为当前 JSON 元数据格式的表画像结构。"""
        result = {
            "table_category": self.table_category,
            "confidence": self.confidence,
            "inference_basis": list(self.inference_basis),
            "classification_source": "rule",
            "physical_constraints": {
                "primary_key": (
                    metadata.primary_keys[0].to_dict()
                    if metadata.primary_keys
                    else None
                ),
                "foreign_keys": [fk.to_dict() for fk in metadata.foreign_keys],
                "unique_constraints": [
                    {
                        "constraint_name": constraint.constraint_name,
                        "columns": list(constraint.columns),
                    }
                    for constraint in metadata.unique_constraints
                ],
            },
            "indexes": [index.to_json_dict() for index in metadata.indexes],
            "unique_column_sets": [
                logical_key.to_dict()
                for logical_key in self.candidate_logical_primary_keys
            ],
        }
        return result
