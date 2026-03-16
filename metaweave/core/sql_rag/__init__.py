"""SQL RAG 样例生成与加载模块

基于已有的表结构文档和业务主题域配置，自动生成 Question-SQL 训练样例，
经过 SQL EXPLAIN 校验后，将其向量化并加载到 Milvus。
"""

from metaweave.core.sql_rag.models import (
    GenerationResult,
    QuestionSQLPair,
    ValidationResult,
)

__all__ = [
    "QuestionSQLPair",
    "ValidationResult",
    "GenerationResult",
]
