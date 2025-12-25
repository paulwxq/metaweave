"""元数据生成模块

负责从 PostgreSQL 数据库中抽取和增强元数据信息。
"""

from metaweave.core.metadata.generator import MetadataGenerator
from metaweave.core.metadata.models import TableMetadata, ColumnInfo
from metaweave.core.metadata.ddl_loader import DDLLoader

__all__ = ["MetadataGenerator", "TableMetadata", "ColumnInfo", "DDLLoader"]

