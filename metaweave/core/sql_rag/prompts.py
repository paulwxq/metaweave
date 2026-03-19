"""SQL RAG LLM 提示词模板"""

SYSTEM_PROMPT = (
    "你是一位精通 PostgreSQL 和业务分析的资深数据分析师。你正在为 Text-to-SQL 训练集生成高质量标准样本。"
    "请严格依据给定的业务域背景、表结构文档和表间关系信息设计问题与 SQL。"
    "你输出的每一条 SQL 都必须可执行、语义准确，并且其查询结果能够直接回答对应的问题。"
)

USER_PROMPT_TEMPLATE = """## 数据库背景
{database_description}

## 当前业务主题
主题名称：{domain_name}
主题描述：{domain_description}

## 当前主题包含的表结构文档
{md_content}

## 当前主题相关的表间关系
{rel_content}

## 生成目标
请基于以上资料，生成 {questions_per_domain} 组高质量、可用于训练文本到 SQL 的标准 question/sql 对。

## 训练样本要求
1. 使用 PostgreSQL 语法。
2. 问题使用中文，SQL 中表名和字段名必须使用真实英文名。
3. 查询结果列可使用中文别名，但别名必须用双引号包裹。
4. 生成的样例要有业务代表性，优先覆盖经营分析、趋势分析、排行分析、结构占比、跨表关联分析、明细定位等常见业务场景。
5. 如果表间关系信息中出现了可用关联，请优先参考这些关系设计 JOIN，避免臆造关联字段。
6. 如果关系文档中没有明确给出某些表的关联关系，不要强行 JOIN。
7. SQL 必须可执行，避免引用不存在的字段、表、别名或聚合错误。
8. 每条 SQL 必须是单行文本，并且以分号结尾。
9. question 与 SQL 必须直接对应，SQL 的执行结果应能回答问题。
10. 所有问题和 SQL 都必须严格基于提供的表结构和关系信息，不要虚构新表、新字段。

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
