"""SQL RAG LLM 提示词模板"""

SYSTEM_PROMPT = (
    "你是一位精通 PostgreSQL 的业务数据分析师。根据给定的数据库表结构文档和业务主题，"
    "生成符合实际业务场景的自然语言问题与对应的 SQL 查询。"
)

USER_PROMPT_TEMPLATE = """## 数据库背景
{database_description}

## 当前业务主题
主题名称：{domain_name}
主题描述：{domain_description}

## 相关表结构
{md_content}

## 生成要求
请针对上述业务主题，生成 {questions_per_domain} 组 question/sql 对，要求：
1. 使用 PostgreSQL 语法
2. 问题使用中文，贴近实际业务分析场景
3. SQL 中表名和字段名使用原始英文名，查询结果列使用中文别名
4. 涵盖多种分析角度：趋势分析、排行榜、汇总统计、明细查询、对比分析等
5. 合理使用 JOIN、GROUP BY、ORDER BY、HAVING、LIMIT 等
6. 所有 SQL 必须以分号结尾
7. question 和 sql 都必须是单行文本，不能包含换行符

## 输出格式
返回严格的 JSON 数组，不要包含其他文字：
[
  {{"question": "问题文本", "sql": "SELECT ...;"}},
  ...
]"""

SQL_REPAIR_SYSTEM_PROMPT = (
    "你是一位 PostgreSQL SQL 修复专家。根据给定的表结构文档、表间关系和错误信息修复 SQL 查询，"
    "确保修复后的 SQL 语法正确、字段名准确且能正常执行。"
)

SQL_REPAIR_PROMPT_TEMPLATE = """以下 SQL 查询在 PostgreSQL 执行 EXPLAIN 时报错，请根据提供的表结构和表间关系信息修复。

## 相关表结构
{table_schemas}

## 表间关系
{table_relationships}

## 待修复的 SQL
{failed_sqls}

## 修复要求
1. 只修复 SQL 语法和结构问题，不要改变查询意图
2. 确保使用 PostgreSQL 语法
3. 确保引用的表名和字段名在上述表结构中存在
4. JOIN 条件需符合上述表间关系
5. 所有 SQL 必须以分号结尾
6. 返回严格的 JSON 数组

## 输出格式
返回严格的 JSON 数组，不要包含其他文字：
[
  {{"index": 0, "sql": "修复后的 SELECT ...;"}},
  ...
]"""
