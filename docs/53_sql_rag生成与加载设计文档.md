# SQL RAG 样例生成与加载设计文档

## 1. 模块定位

`sql_rag` 是 MetaWeave 新增的子模块，负责基于已有的表结构文档（`output/md/*.md`）和业务主题域配置（`configs/db_domains.yaml`），自动生成 Question-SQL 训练样例，经过 SQL EXPLAIN 校验后，将其向量化并加载到 Milvus，供下游 NL2SQL 系统做语义检索。

**与 data_pipeline 的区别**：data_pipeline 是一个端到端的完整流水线（表结构抽取 → DDL/MD → 主题 → Question-SQL → 校验 → 导入）。而 `sql_rag` 只负责后半段——MetaWeave 已有步骤（`--step md`、`--step ddl`）已生成表结构文档和 DDL，业务主题也已在 `db_domains.yaml` 中配置好，因此 `sql_rag` 的流程从 Question-SQL 生成开始。

**核心流程**：

```
output/md/*.md + configs/db_domains.yaml
        ↓
  Question-SQL 生成（LLM）
        ↓
  output/sql/qs_{db_name}_pair.json
        ↓
  SQL EXPLAIN 校验 + 可选 LLM 修复
        ↓
  向量化 question，连同 question_sql JSON 加载到 Milvus
```

---

## 2. 与 MetaWeave 现有架构的关系

### 2.1 复用现有服务

| 现有服务 | import 路径 | 用途 | 复用方式 |
|----------|------------|------|----------|
| `LLMService` | `from metaweave.services.llm_service import LLMService` | Question-SQL 生成、SQL 修复 | 直接调用 `call_llm(prompt, system_message)` |
| `EmbeddingService` | `from metaweave.services.embedding_service import EmbeddingService` | question 文本向量化 | 直接调用 `get_embeddings(texts)`，返回 `Dict[str, np.ndarray]` |
| `MilvusClient` | `from metaweave.services.vector_db.milvus_client import MilvusClient` | 向量存储与检索 | 调用 `ensure_collection()`、`upsert_batch()`（内容哈希主键天然幂等，无需按条件删除） |
| `ConfigLoader` | `from services.config_loader import ConfigLoader` | 配置加载（`.env` + YAML） | 直接调用 `load()` |
| `DatabaseConnector` | `from metaweave.core.metadata.connector import DatabaseConnector` | SQL EXPLAIN 校验的数据库连接 | 复用连接池（`get_connection()`），不使用 `execute_query()`，参考 `PGClient.explain_query()` 模式 |

### 2.2 复用现有输入产物

| 产物 | 路径 | 用途 |
|------|------|------|
| 表结构 Markdown | `output/md/*.md` | 作为 LLM 生成 Question-SQL 的上下文 |
| 表 DDL | `output/ddl/*.sql` | 可选，辅助 LLM 理解表约束 |
| 业务主题域 | `configs/db_domains.yaml` | 按主题域分组生成 Question-SQL |

### 2.3 模块放置

```
metaweave/core/sql_rag/
├── __init__.py
├── generator.py          # Question-SQL 生成器
├── validator.py          # SQL EXPLAIN 校验器
├── loader.py             # 向量化加载器（Milvus）
├── models.py             # 数据模型
└── prompts.py            # LLM 提示词模板
```

遵循 MetaWeave 现有的模块组织模式：`metaweave/core/` 下按功能域建子目录，每个子目录内按职责分文件。

---

## 3. 数据模型

### 3.1 `QuestionSQLPair`

单条 Question-SQL 训练样例：

```python
@dataclass
class QuestionSQLPair:
    question: str           # 自然语言问题（中文）
    sql: str                # 对应的 PostgreSQL 查询语句
    domain: str = ""        # 来源主题域名称（仅保留在 JSON 中间产物中，不写入 Milvus）
    tables: List[str] = field(default_factory=list)  # 涉及的表
```

> **关于 `domain` 字段的设计说明**：`output/sql/*.json` 中生成的 Question-SQL 样例保留 `domain` 字段，记录该样例来源的业务主题域。例如：
>
> ```json
> {"question": "各门店的月度租赁收入趋势如何？", "sql": "SELECT ...;", "domain": "财务与交易管理"}
> ```
>
> `domain` 仅作为生成阶段和中间产物的元数据保留，用于后续人工审查、结果统计、问题排查和样例来源追踪，**不参与向量化，也不作为检索提示词内容的一部分**。
>
> 在加载到 Milvus 时，仍然遵循"仅对 question 做向量化"的原则，向量库中只保存基于 question 生成的 embedding 以及 `{"question":"...","sql":"..."}` 形式的 `question_sql` JSON 字符串，不写入 `domain` 字段。也就是说，**`domain` 只存在于 `output/sql/*.json` 中，不进入最终的 Milvus Collection Schema**。
>
> 基于这一设计，Milvus 侧不再依赖 `domain` 做主键构造或旧数据删除。Loader 直接按主键幂等 upsert 数据；主键使用 `{db_name}:{content_hash8}` 形式，其中 `content_hash8` 为 `question + sql` 的 SHA256 前 8 位。这样既保留了生成阶段的主题域信息，又避免将与检索无关的字段写入向量库，保持检索载荷和提示词上下文尽可能简洁。

### 3.2 `ValidationResult`

单条 SQL 的校验结果：

```python
@dataclass
class ValidationResult:
    sql: str                # 参与校验的规范化 SQL（经 _normalize_sql 处理）
    valid: bool             # EXPLAIN 是否通过
    index: int = -1         # 在 pair 列表中的序号（由 validate_batch 注入）
    error_message: str = "" # 错误信息
    execution_time: float = 0.0
    retry_count: int = 0
    # SQL 修复相关
    repair_attempted: bool = False
    repair_successful: bool = False
    repaired_sql: str = ""  # LLM 修复后的 SQL（如果修复成功）
    repair_error: str = ""  # 修复失败原因
```

### 3.3 `GenerationResult`

一次生成任务的完整结果：

```python
@dataclass
class GenerationResult:
    success: bool
    pairs: List[QuestionSQLPair]
    domain_stats: Dict[str, int]   # 每个主题域的生成数量
    total_generated: int
    output_file: str               # 固定路径：output/sql/qs_{db_name}_pair.json
```

---

## 4. 详细设计

### 4.1 Step 1: Question-SQL 生成（`generator.py`）

#### 4.1.1 输入

- **MD 文件目录**：`output/md/`，包含所有表的结构文档
- **主题域配置**：`configs/db_domains.yaml`，包含数据库描述和业务主题域列表
- **生成参数**：每个主题域生成多少条 Question-SQL（默认 10；`_未分类_` 域默认 3）

#### 4.1.2 处理流程

```
1. 读取 db_domains.yaml，获取 database 描述和 domains 列表
2. 读取 output/md/*.md，构建 {表名: MD内容} 映射字典
3. 对每个主题域：
   - 若 name == "_未分类_" 且 skip_uncategorized=true，跳过该域
   - 若 name == "_未分类_" 且 skip_uncategorized=false，使用 uncategorized_questions
     （默认 3）作为生成数量，以较少样例保证基本覆盖
   a. 根据 tables 字段，从映射字典中查找相关表的 MD 内容
   b. 构建 LLM 提示词（注入：数据库描述、主题域信息、相关表的 MD 内容）
   c. 调用 LLMService.call_llm() 生成 Question-SQL JSON
   d. 解析并清洗 LLM 返回结果
   e. 对每条清洗后的 pair，由生成器补写 domain = 当前主题域名称
      （domain 不由 LLM 产出，而是生成器根据当前处理的域自动注入）
   f. 合并到总结果集
4. 确保输出目录存在（output_dir.mkdir(parents=True, exist_ok=True)）
5. 将全部 Question-SQL 写入固定文件 output/sql/qs_{db_name}_pair.json（默认覆盖，不追加）
```

#### 4.1.3 MD 上下文构建策略

**表名到 MD 文件的映射规则**：`db_domains.yaml` 中的表名格式为 `dvdrental.public.customer`，`output/md/` 下的文件名格式为 `dvdrental.public.customer.md`。两者通过 `{table_name}.md` 直接对应，无需做名称转换。

对每个主题域，根据其 `tables` 字段列出的表名，从 `output/md/` 中读取对应的 MD 文件内容，只注入该主题域涉及的表的 MD 内容，避免全量注入导致 token 超限。

如果某个表名找不到对应的 MD 文件，记录 warning 并跳过该表（不阻断整体流程）。

如果 `db_domains.yaml` 的 domain 中 `tables` 为空列表，则使用全量 MD 内容（适用于表数量较少的场景，如当前 15 张表）。

#### 4.1.4 LLM 提示词设计

系统提示词：

```
你是一位精通 PostgreSQL 的业务数据分析师。根据给定的数据库表结构文档和业务主题，
生成符合实际业务场景的自然语言问题与对应的 SQL 查询。
```

用户提示词模板（见 `prompts.py`）：

```
## 数据库背景
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
  {"question": "问题文本", "sql": "SELECT ...;"},
  ...
]
```

#### 4.1.5 结果清洗

- 从 LLM 返回文本中提取 JSON（支持 markdown code block 包裹）
- 过滤 `question` 或 `sql` 为空的项
- 将多行文本折叠为单行（`' '.join(text.split())`）
- 确保 SQL 以分号结尾
- 去除首尾空白

#### 4.1.6 输出

文件路径：`output/sql/qs_{db_name}_pair.json`（固定文件名，一个数据库对应一个文件）

**文件生成策略**：每次生成默认覆盖同名文件，不追加、不带时间戳。全流程优先"覆盖式重建"，不做复杂的增量维护。如需保留旧版本，用户可在生成前手动备份。

**`generate --clean` 语义**：仅删除当前数据库对应的目标样例文件 `qs_{db_name}_pair.json`，不影响同目录下其他数据库的样例文件，也不清理校验日志、备份文件和其他报告。

文件格式（核心字段 `question`/`sql` 兼容 data_pipeline，额外补充 `domain` 作为中间产物元数据，详见 3.1 节设计说明）：

```json
[
  {
    "question": "各门店的月度租赁收入趋势如何？",
    "sql": "SELECT s.store_id AS 门店ID, TO_CHAR(p.payment_date, 'YYYY-MM') AS 月份, SUM(p.amount) AS 月度收入 FROM payment p JOIN staff st ON p.staff_id = st.staff_id JOIN store s ON st.store_id = s.store_id GROUP BY s.store_id, TO_CHAR(p.payment_date, 'YYYY-MM') ORDER BY s.store_id, 月份;",
    "domain": "财务与交易管理"
  }
]
```

---

### 4.2 Step 2: SQL EXPLAIN 校验（`validator.py`）

#### 4.2.1 输入

- `output/sql/qs_{db_name}_pair.json` 文件（默认使用固定路径，也可通过 `--input` 覆盖）
- 数据库连接配置（通过 `sql_rag.yaml` 的 `metadata_config_file` 指向 `metadata_config.yaml`，读取其 `database` 段）

#### 4.2.2 校验机制

复用 `DatabaseConnector` 的**连接池**（而非 `execute_query()` 方法），在显式事务内依次执行 `SET LOCAL statement_timeout` 和 `EXPLAIN`，参考 `services/db/pg_client.py` 中 `PGClient.explain_query()` 的实现模式。

> **为什么不用 `DatabaseConnector.execute_query()`**：该方法每次调用从连接池取新连接，且无条件 `fetchall()`。这导致两个问题：(1) `SET` 和 `EXPLAIN` 在不同连接上执行，SET 不会对 EXPLAIN 生效；(2) `SET` 语句无结果集，`fetchall()` 会报 `ProgrammingError`。
>
> **为什么不直接用 `PGClient.explain_query()`**：`PGClient` 是 `services` 层的全局业务客户端（通过 `get_pg_manager()` 获取全局连接池），职责偏向量检索与 SQL 案例检索，且不支持注入局部连接配置。而 SQL 校验需要使用 `metaweave` 核心层的 `DatabaseConnector`（通过 `metadata_config.yaml` 的 `database` 段配置），以确保连接目标与元数据提取一致。因此 validator 只复用 `PGClient.explain_query()` 的**实现模式**（同连接双 cursor），不直接复用其实例。

```python
def _normalize_sql(self, sql: str) -> str:
    """规范化 SQL：去除首尾空白和尾部分号，拒绝多语句"""
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise ValueError("SQL 为空")
    if ";" in sql:
        raise ValueError(f"检测到多语句（中间含分号），拒绝校验: {sql[:80]}...")
    return sql

def validate_sql(self, sql: str) -> ValidationResult:
    """规范化 + 在显式事务内执行 SET LOCAL timeout + EXPLAIN"""
    start_time = time.time()
    timeout = self.config.get("timeout", 30)
    try:
        sql = self._normalize_sql(sql)
        readonly = self.config.get("sql_validation_readonly", True)
        with self.connector.get_connection() as conn:
            # 临时关闭 autocommit，开启显式事务
            conn.autocommit = False
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        # SET LOCAL 仅在当前事务内生效，事务结束后自动恢复
                        cur.execute(f"SET LOCAL statement_timeout = {timeout * 1000}")
                        if readonly:
                            cur.execute("SET LOCAL default_transaction_read_only = on")
                        cur.execute(f"EXPLAIN {sql}")
                        cur.fetchall()  # 消费结果集
            finally:
                # 恢复 autocommit，确保归还到连接池的连接状态干净
                conn.autocommit = True
        execution_time = time.time() - start_time
        return ValidationResult(sql=sql, valid=True, execution_time=execution_time)
    except Exception as e:
        execution_time = time.time() - start_time
        return ValidationResult(sql=sql, valid=False, error_message=str(e), execution_time=execution_time)
```

**关键设计决策**：

- **SQL 规范化前置**：进入 EXPLAIN 前先执行 `_normalize_sql()`——去除首尾空白和尾部分号，检测中间分号（多语句）并拒绝。这是防御 LLM 返回多语句或带尾部分号的最小必要措施
- 使用 `EXPLAIN` 而非 `EXPLAIN ANALYZE`：只做计划验证，不实际执行查询
- 使用 **`SET LOCAL statement_timeout`** + 显式事务做超时保护（默认 30 秒）。`SET LOCAL` 仅在当前事务内生效，事务结束（COMMIT 或 ROLLBACK）后自动恢复，**不会污染连接池中的 session 状态**
- 临时关闭 `autocommit` 以开启事务，EXPLAIN 完成后立即恢复 `autocommit=True`，确保归还到池中的连接行为与其他代码一致
- 复用 `DatabaseConnector` 的连接池（`get_connection()`），但不使用其 `execute_query()` 方法
- 不引入 asyncpg 等额外依赖，与 MetaWeave 现有技术栈一致

> **关于只读保护**：`EXPLAIN` 本身不执行查询，但作为纵深防御，当配置 `sql_validation_readonly=true`（默认）时，在事务内追加 `SET LOCAL default_transaction_read_only = on`，防止规范化漏网的异常 SQL 意外写入数据。`SET LOCAL` 同样只在事务内生效，不污染连接池。

#### 4.2.3 并发控制

使用 `concurrent.futures.ThreadPoolExecutor` 控制并发校验数（默认 5），与 MetaWeave 项目的同步 psycopg3 技术栈保持一致：

```python
def validate_batch(self, sqls: List[str]) -> List[ValidationResult]:
    """并发批量校验"""
    max_concurrent = self.config.get("sql_validation_max_concurrent", 5)
    # 实际并发数不超过连接池上限，避免线程空等连接
    pool_max = self.connector.pool.max_size if self.connector.pool else max_concurrent
    max_workers = min(max_concurrent, pool_max)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(self.validate_sql, sqls))
    # 由 validate_batch 统一注入 index，validate_sql 不关心序号
    for i, r in enumerate(results):
        r.index = i
    return results
```

> **并发数与连接池的约束**：每个并发校验线程需要独占一个数据库连接。若 `validation.sql_validation_max_concurrent` > `database.pool_max_size`，多出的线程会阻塞等待连接池分配，造成无意义的线程空等。实现时自动取 `min(max_concurrent, pool_max_size)` 作为实际 worker 数，无需用户手动对齐两个配置。
>
> **与 data_pipeline 的差异说明**：data_pipeline 使用 asyncpg + asyncio.Semaphore 做异步并发校验。MetaWeave 项目全局使用同步 psycopg3，为保持技术栈一致性，此处改用 ThreadPoolExecutor。EXPLAIN 是轻量 IO 操作（通常 < 100ms），同步线程池完全满足性能需求。

#### 4.2.4 重试机制

对以下类型的错误自动重试（最多 2 次）：

- 连接错误（`connection`、`network`）
- 超时错误（`timeout`）
- 连接池错误（`pool`）

语法错误不重试。判断逻辑与 data_pipeline 的 `SQLValidator._should_retry()` 一致：检查错误信息中是否包含上述关键词。

#### 4.2.5 LLM SQL 修复

默认关闭（`enable_sql_repair = false`）。启用方式：配置文件设为 `true`，或在 `validate` 命令中用 `--enable_sql_repair true/false` 临时覆盖配置文件。

启用后，对每条校验失败的 SQL：

1. 收集失败的 SQL、对应的 question 及 PostgreSQL 错误信息
2. 构建修复提示词，调用 `LLMService.call_llm()` 生成修复后的 SQL
3. 对修复后的 SQL 再次执行 EXPLAIN 校验
4. **修复成功**：替换原 JSON 中的 SQL
5. **修复失败**：从原 JSON 中删除该条 question-sql 对

修复按 `repair_batch_size`（默认 2）分批进行，每批构建一个包含多条待修复 SQL 的提示词，一次 LLM 调用返回多条修复结果。

#### 4.2.6 修复结果回写

当 `enable_sql_repair = true` 时，修复流程结束后会自动回写原文件；当 `enable_sql_repair = false` 时，只进行 SQL 校验和日志输出，不修改原 JSON 文件。回写处理流程：

1. 创建原文件的 `.backup` 备份（如 `qs_dvdrental_pair.json.backup`）
2. 遍历校验结果：
   - 校验通过的 SQL → 保留不动
   - 修复成功的 SQL → 替换为修复后的版本
   - 修复失败的 SQL → 从 JSON 数组中删除
3. 写回原文件
4. 生成修改日志 `file_modifications_{timestamp}.log`

#### 4.2.7 校验报告

输出路径：`output/sql/sql_validation_{timestamp}_summary.log`

报告格式参照 data_pipeline 的验证报告，包含以下段落：

```
SQL验证报告
==================================================

输入文件: output/sql/qs_dvdrental_pair.json
验证时间: 2026-03-14T12:05:00.000000
验证耗时: 5.23秒

验证结果摘要:
  总SQL数量: 60
  有效SQL: 57
  无效SQL: 3
  成功率: 95.00%
  平均耗时: 0.025秒
  重试次数: 0

SQL修复统计:
  尝试修复: 3
  修复成功: 2
  修复失败: 1
  修复成功率: 66.67%

原始文件修改统计:
  修改的SQL: 2
  删除的无效项: 1
  修改失败: 0

错误详情（共1个）:
==================================================

1. 问题: xxx
   错误: xxx
   LLM修复尝试: 失败
   修复失败原因: xxx
   完整SQL:
   SELECT ...;
   ----------------------------------------

成功修复的SQL（共2个）:
==================================================

1. 问题: xxx
   原始错误: xxx
   修复后SQL:
   SELECT ...;
   ----------------------------------------
```

报告包含五个部分：

| 段落 | 内容 |
|------|------|
| 验证结果摘要 | 总数、有效/无效数、成功率、平均耗时 |
| SQL修复统计 | 尝试修复数、修复成功/失败数、修复成功率 |
| 原始文件修改统计 | 修改的 SQL 数、删除的无效项数 |
| 错误详情 | 每条无法修复的 SQL：问题文本、错误信息、修复失败原因、完整 SQL |
| 成功修复的SQL | 每条成功修复的 SQL：问题文本、原始错误、修复后的 SQL |

---

### 4.3 Step 3: 向量化加载到 Milvus（`loader.py`）

#### 4.3.1 设计原则

**embedding 基于 question 做向量化，question 和 sql 合并为一个 JSON 字符串存储**。

检索场景：用户提问 → embedding 向量检索找到语义最相似的历史问题 → 直接返回 `question_sql` 字段中的完整 JSON 串 `{"question":"...","sql":"..."}`。

这样设计的好处：

- embedding 字段只用 question 文本计算，语义匹配更精准（SQL 语法噪音不会干扰相似度）
- question 和 sql 作为一个整体 JSON 存储在 `question_sql` 字段中，检索命中后无需拼接，直接可用
- 与 data_pipeline 中 pgvector 的 `langchain_pg_embedding.document` 存储 `{"question":"...","sql":"..."}` JSON 串的方式保持一致

#### 4.3.2 Milvus Collection Schema

Collection 名称：`sql_example_embeddings`（在 `loader_config.yaml` 中配置）

```python
fields = [
    FieldSchema(name="example_id",    dtype=DataType.VARCHAR, max_length=256, is_primary=True, auto_id=False),
    FieldSchema(name="question_sql",  dtype=DataType.VARCHAR, max_length=16384),
    FieldSchema(name="embedding",     dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),  # 从 metadata_config.yaml 读取
    FieldSchema(name="updated_at",    dtype=DataType.INT64),
]
```

> **注意**：`domain` 字段不进入 Milvus Schema（详见 3.1 节设计说明）。

字段说明：

| 字段 | 说明 |
|------|------|
| `example_id` | 主键，格式 `{db_name}:{content_hash8}`，其中 `content_hash8` 是 `question+sql` 的 SHA256 前 8 位。相同内容幂等，不会重复插入 |
| `question_sql` | question 与 sql 的合并 JSON 串，如 `{"question":"...","sql":"..."}`。超过 16000 字符时记录 warning 并跳过 |
| `embedding` | **基于 question 文本**计算的向量表示，维度从 `metadata_config.yaml` 的 `embedding.providers.{active}.dimensions` 读取（参考 `embedding_service.py` 和 `table_schema_loader.py` 的实现） |
| `updated_at` | 更新时间戳 |

`question_sql` 字段存储示例：

```json
{"question": "各门店的月度租赁收入趋势如何？", "sql": "SELECT s.store_id AS 门店ID, TO_CHAR(p.payment_date, 'YYYY-MM') AS 月份, SUM(p.amount) AS 月度收入 FROM payment p JOIN staff st ON p.staff_id = st.staff_id JOIN store s ON st.store_id = s.store_id GROUP BY s.store_id, TO_CHAR(p.payment_date, 'YYYY-MM') ORDER BY s.store_id, 月份;"}
```

向量索引：

```python
index_params = {
    "index_type": "HNSW",
    "metric_type": "COSINE",
    "params": {"M": 16, "efConstruction": 200},
}
```

#### 4.3.3 加载流程

```
1. 确定输入文件（按优先级：--input 参数 > sql_loader.input_file 配置，默认为 output/sql/qs_{db_name}_pair.json）
2. 初始化依赖服务：
   a. 从 loader_config.yaml 读取 sql_loader 配置
   b. 从 metadata_config.yaml（路径通过 loader_config.yaml 的 metadata_config_file 指定）
      读取 embedding 和 vector_database 配置
   c. 初始化 EmbeddingService 和 MilvusClient
3. 确保 Collection 存在（ensure_collection）
4. 分批处理（batch_size 默认 50）：
   a. 提取当前批次的 question 文本列表
   b. 调用 EmbeddingService.get_embeddings(questions)
      返回 Dict[str, np.ndarray]（text → vector 映射）
   c. 遍历批次中的每条 pair：
      - 通过 embeddings.get(question) 获取对应向量（参考 TableSchemaLoader 的实现模式）
      - 将 {question, sql} 序列化为 JSON 字符串，写入 question_sql 字段（不含 domain）
      - 计算 example_id = f"{db_name}:{sha256(question+sql)[:8]}"
   d. 调用 MilvusClient.upsert_batch() 写入（统一使用 upsert，内容哈希主键天然幂等，
      避免同文件内重复 question+sql 导致 insert 主键冲突）
5. 返回加载统计结果
```

#### 4.3.4 继承 `BaseLoader`

遵循 MetaWeave 现有的 Loader 模式，继承 `metaweave.core.loaders.base.BaseLoader`，实现 `validate()` 和 `load()` 方法：

```python
class SQLExampleLoader(BaseLoader):
    def validate(self) -> bool: ...
    def load(self, clean: bool = False) -> Dict[str, Any]: ...
```

> **关于 `load(clean)` 参数**：`BaseLoader.load()` 抽象方法的签名不含 `clean` 参数，但现有的 `TableSchemaLoader` 已覆盖签名添加了 `clean` 参数。`SQLExampleLoader` 遵循同样的模式。`loader_cli.py` 中已有对应的特殊处理逻辑（跳过 `execute()`，手动调用 `validate()` + `load(clean=clean)`），需将 `"sql"` 加入该处理集合。

#### 4.3.5 LoaderFactory 注册

在 `metaweave/core/loaders/factory.py` 的 `_register_builtin_loaders()` 中注册：

```python
from metaweave.core.sql_rag.loader import SQLExampleLoader
LoaderFactory.register("sql", SQLExampleLoader)
```

同时在 `loader_cli.py` 第 119 行的特殊处理集合中加入 `"sql"`：

```python
if load_type in {"cql", "dim", "dim_value", "table_schema", "sql"}:
```

---

## 5. 配置设计

### 5.1 `metadata_config.yaml` 新增部分

不新增——复用现有 `llm`、`embedding`、`vector_database`、`database` 配置段。`sql_rag.yaml` 和 `loader_config.yaml` 均通过 `metadata_config_file` 字段指向该文件，运行时按需读取对应配置段。

### 5.2 `loader_config.yaml` 新增部分

在现有配置中补充 `sql_loader` 段：

```yaml
# 全局配置（已有，与 table_schema_loader 共用）
metadata_config_file: "configs/metadata_config.yaml"

# SQL Example 加载器配置
sql_loader:
  # 输入文件路径（固定文件名，与 generate 输出对应）
  input_file: "output/sql/qs_dvdrental_pair.json"
  # Milvus Collection 名称（必填）
  collection_name: "sql_example_embeddings"

  # 加载选项
  options:
    batch_size: 50            # 每批向量化和写入的数量
```

**输入文件解析优先级**（适用于 `sql-rag load` 和 `load --type sql` 两种入口）：

1. CLI `--input` 参数（仅 `sql-rag load` 支持）→ 最高优先，可覆盖配置
2. 配置文件 `sql_loader.input_file` → 默认入口，指向固定文件 `output/sql/qs_{db_name}_pair.json`
3. 以上均无命中 → `validate()` 返回 False，终止加载

不再需要"目录下按时间戳查找最新文件"的逻辑。固定文件名使得 generate → validate → load 全链路天然衔接。

> `SQLExampleLoader` 在初始化时通过 `metadata_config_file` 路径加载 `metadata_config.yaml`，从中获取 `embedding` 和 `vector_database.providers.milvus` 配置，与 `TableSchemaLoader` 的初始化模式完全一致。

### 5.3 `configs/sql_rag.yaml` 新增配置文件

Question-SQL 生成和校验的独立配置：

```yaml
# SQL RAG 生成与校验配置

# 基础配置：指向 metadata_config.yaml，从中读取 llm、database 等共享配置
# 生成阶段依赖 llm 段（LLMService），校验阶段依赖 database 段（DatabaseConnector）
metadata_config_file: "configs/metadata_config.yaml"

# Question-SQL 生成配置
generation:
  # 每个主题域生成的 Question-SQL 数量
  questions_per_domain: 10
  # _未分类_ 域的生成数量（较少样例保证基本覆盖，设为 0 等同于跳过）
  uncategorized_questions: 3
  # 是否完全跳过 _未分类_ 主题域（默认 false，保证训练集全覆盖）
  skip_uncategorized: false
  # 输出目录
  output_dir: "output/sql"
  # LLM 调用超时（秒）
  llm_timeout: 120

# SQL 校验配置
validation:
  # 并发校验数（ThreadPoolExecutor 的 max_workers）
  sql_validation_max_concurrent: 5
  # 单条 SQL 超时（秒）
  timeout: 30
  # 只读模式：开启时在事务内追加 SET LOCAL default_transaction_read_only = on
  sql_validation_readonly: true
  # 最大重试次数
  sql_validation_max_retries: 2
  # 是否启用 LLM SQL 修复并回写原 JSON 文件（关闭时只校验并生成日志）
  enable_sql_repair: false
  # 修复批大小（每次 LLM 调用修复几条 SQL）
  repair_batch_size: 2
```

---

## 6. CLI 集成

### 6.1 新增子命令 `sql-rag`

在 `metaweave/cli/` 下新增 `sql_rag_cli.py`，注册为 `cli` 的子命令：

```bash
# 生成 Question-SQL（默认覆盖同名文件）
uv run metaweave sql-rag generate \
  --config configs/sql_rag.yaml \
  --domains-config configs/db_domains.yaml \
  --md-dir output/md

# 生成前清理当前库的旧样例文件（仅删除 qs_{db_name}_pair.json，不影响其他库）
uv run metaweave sql-rag generate \
  --config configs/sql_rag.yaml \
  --domains-config configs/db_domains.yaml \
  --md-dir output/md \
  --clean

# 校验 SQL（仅校验，输出报告；默认使用固定文件路径）
uv run metaweave sql-rag validate \
  --config configs/sql_rag.yaml

# 校验 + 修复（命令行参数优先于 YAML 配置）
uv run metaweave sql-rag validate \
  --config configs/sql_rag.yaml \
  --enable_sql_repair true

# 校验指定文件（--input 可选，覆盖默认路径）
uv run metaweave sql-rag validate \
  --config configs/sql_rag.yaml \
  --input output/sql/qs_dvdrental_pair.json

# 加载到 Milvus（默认使用 loader_config.yaml 中的 input_file）
uv run metaweave sql-rag load \
  --config configs/loader_config.yaml

# 加载前清空目标 Milvus Collection
uv run metaweave sql-rag load \
  --config configs/loader_config.yaml \
  --clean

# 一键执行全部（生成 → 校验 → 加载，固定文件名天然衔接各阶段）
uv run metaweave sql-rag run-all \
  --config configs/sql_rag.yaml \
  --loader-config configs/loader_config.yaml \
  --domains-config configs/db_domains.yaml \
  --md-dir output/md

# 一键执行全部并清理旧数据
uv run metaweave sql-rag run-all \
  --config configs/sql_rag.yaml \
  --loader-config configs/loader_config.yaml \
  --domains-config configs/db_domains.yaml \
  --md-dir output/md \
  --clean
```

> **`--clean` 语义区分**：
> - `generate --clean`：删除当前数据库对应的 `qs_{db_name}_pair.json`，然后重新生成
> - `load --clean`：清空目标 Milvus Collection（drop + recreate），然后全量写入
> - `run-all --clean`：同时执行上述两步，先清理当前库旧样例文件，再清空目标 Milvus Collection
>
> **`run-all` 的双配置文件说明**：`--config`（`sql_rag.yaml`）驱动生成和校验阶段，`--loader-config`（`loader_config.yaml`）驱动加载阶段（Milvus collection、embedding 配置等）。固定文件名使得各阶段天然衔接，用户无需指定 `--input`。

### 6.2 与现有 `load` 命令的整合

同时在 `loader_cli.py` 的 `--type` 选项中将 `sql` 类型实现为调用 `SQLExampleLoader`，使以下命令也可用：

```bash
# 使用配置文件中的 input_file 定位输入文件
uv run metaweave load --type sql --config configs/loader_config.yaml

# 加载前清空 Collection
uv run metaweave load --type sql --config configs/loader_config.yaml --clean
```

> 通用 `load` 命令不支持 `--input` 参数（保持现有 CLI 签名不变）。输入文件通过 `loader_config.yaml` 的 `sql_loader.input_file` 配置，默认指向固定文件 `output/sql/qs_{db_name}_pair.json`。如需覆盖指定文件，使用 `sql-rag load --input` 子命令。

---

## 7. 目录结构总览

新增/修改的文件清单：

```
project-root/
├── metaweave/
│   ├── core/
│   │   ├── sql_rag/
│   │   │   ├── __init__.py           # 模块导出
│   │   │   ├── generator.py          # Question-SQL 生成器
│   │   │   ├── validator.py          # SQL EXPLAIN 校验器
│   │   │   ├── loader.py             # Milvus 向量化加载器
│   │   │   ├── models.py             # 数据模型定义
│   │   │   └── prompts.py            # LLM 提示词模板
│   │   └── loaders/
│   │       └── factory.py            # [修改] 注册 sql → SQLExampleLoader
│   └── cli/
│       ├── sql_rag_cli.py            # [新增] sql-rag 子命令
│       ├── loader_cli.py             # [修改] 将 "sql" 加入 clean 参数特殊处理集合
│       └── main.py                   # [修改] 注册 sql-rag 子命令
├── services/                         # 公共服务层（非 metaweave 包内）
│   ├── vector_db/
│   │   └── milvus_client.py          # [现有] 使用 ensure_collection()、upsert_batch()
│   └── config_loader.py              # [现有] ConfigLoader
├── configs/
│   ├── sql_rag.yaml                  # [新增] 生成与校验配置
│   └── loader_config.yaml            # [修改] sql_loader 段补全
└── output/
    └── sql/                          # [新增目录] Question-SQL 输出
        └── qs_{db_name}_pair.json
```

---

## 8. 与 data_pipeline 的对比

| 维度 | data_pipeline | MetaWeave sql_rag |
|------|---------------|-------------------|
| 表结构来源 | 自行从 DB 抽取并生成 DDL/MD | 复用 `--step md` 已生成的 `output/md/*.md` |
| 主题域来源 | LLM 从 MD 自动提取 | 直接读取 `configs/db_domains.yaml` |
| LLM 调用 | 通过 `vn.chat_with_llm()` | 通过 `LLMService.call_llm()` |
| SQL 校验 | asyncpg + asyncio.Semaphore + EXPLAIN | 同步 psycopg3 `DatabaseConnector` + ThreadPoolExecutor + EXPLAIN |
| 向量化目标 | question+sql 整体做向量化 → pgvector | 仅 question 做向量化，question+sql 合并为 JSON 串存储 → Milvus |
| 向量存储 | `langchain_pg_embedding` 表 | Milvus Collection |
| 主键策略 | 无显式主键管理 | `{db}:{content_hash8}` 内容哈希，幂等 upsert（`domain` 仅保留在 JSON 中间产物中） |
| 配置方式 | `app_config` + 全局 dict | `ConfigLoader` + YAML + `.env` |
| 日志方式 | `core.logging` | `metaweave.utils.logger` |
| CLI | 独立 `python -m` 脚本 | Click 子命令 |

---

## 9. 依赖与约束

### 9.1 已有依赖（无需新增）

- `psycopg[binary]`：PostgreSQL 连接（SQL 校验，复用 `DatabaseConnector`）
- `pymilvus`：Milvus 向量库
- `dashscope`：Embedding 服务
- `langchain-*`：LLM 调用
- `PyYAML`：配置解析
- `click`：CLI

### 9.2 前置条件

1. 已运行 `uv run metaweave metadata --step md` 生成 `output/md/*.md`
2. 已配置 `configs/db_domains.yaml`（可通过 `--step json_llm` 的 LLM 推断辅助生成，也可手工编写）
3. `.env` 中已配置 LLM API Key、数据库连接、Milvus 连接

---

## 10. 处理异常与容错

### 10.1 生成阶段

- 单个主题域生成失败不阻断整体流程，记录错误并继续
- LLM 返回非法 JSON 时，尝试提取 markdown code block 内容
- 生成结果为空时跳过该主题域
- 某个表的 MD 文件缺失时记录 warning 并跳过该表

### 10.2 校验阶段

- 数据库连接失败时立即终止并报错
- 单条 SQL 校验超时不阻断其他 SQL
- 连接类错误自动重试（最多 2 次）
- LLM 修复批次失败时返回空结果，对应 SQL 视为修复失败

### 10.3 加载阶段

- Embedding 服务调用失败时重试 2 次，仍失败则跳过该批次（参考 `TableSchemaLoader` 的重试逻辑）
- Milvus 写入失败记录错误，不阻断后续批次
- `question_sql` JSON 串超过 16000 字符时记录 warning 并跳过该条

---

## 11. 实施计划

建议分 3 步实施：

### 第一步：核心生成与输出

实现 `generator.py`、`models.py`、`prompts.py`，完成：

- 读取 MD 和 db_domains.yaml
- 按主题域构建 LLM 提示词（注入相关表的 MD 内容）
- 调用 LLM 生成 Question-SQL
- 输出固定文件 `qs_{db_name}_pair.json`（覆盖式写入）

验收标准：能生成格式正确的 JSON 文件，包含 question、sql、domain 字段。

### 第二步：SQL 校验

实现 `validator.py`，完成：

- 复用 `DatabaseConnector` 执行 EXPLAIN 校验
- ThreadPoolExecutor 并发批量校验
- 可选 LLM 修复与原文件回写
- 校验报告生成

验收标准：能对 JSON 中的 SQL 执行 EXPLAIN 并输出通过率。

### 第三步：Milvus 加载与 CLI

实现 `loader.py`、`sql_rag_cli.py`，完成：

- question 向量化并写入 Milvus（内容哈希主键幂等 upsert）
- CLI 子命令注册（generate / validate / load / run-all）
- LoaderFactory 注册

验收标准：能通过 CLI 一键完成 生成 → 校验 → 加载 全流程。
