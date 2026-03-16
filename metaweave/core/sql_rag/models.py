"""SQL RAG 数据模型定义"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class QuestionSQLPair:
    """单条 Question-SQL 训练样例"""

    question: str  # 自然语言问题（中文）
    sql: str  # 对应的 PostgreSQL 查询语句
    domain: str = ""  # 来源主题域名称（仅保留在 JSON 中间产物中，不写入 Milvus）
    tables: List[str] = field(default_factory=list)  # 涉及的表


@dataclass
class ValidationResult:
    """单条 SQL 的校验结果"""

    sql: str  # 参与校验的规范化 SQL（经 _normalize_sql 处理）
    valid: bool  # EXPLAIN 是否通过
    index: int = -1  # 在 pair 列表中的序号（由 validate_batch 注入）
    error_message: str = ""  # 错误信息
    execution_time: float = 0.0
    retry_count: int = 0
    # SQL 修复相关
    repair_attempted: bool = False
    repair_successful: bool = False
    repaired_sql: str = ""  # LLM 修复后的 SQL（如果修复成功）
    repair_error: str = ""  # 修复失败原因


@dataclass
class GenerationResult:
    """一次生成任务的完整结果"""

    success: bool
    pairs: List[QuestionSQLPair]
    domain_stats: Dict[str, int]  # 每个主题域的生成数量
    total_generated: int
    output_file: str  # 固定路径：output/sql/qs_{db_name}_pair.json
