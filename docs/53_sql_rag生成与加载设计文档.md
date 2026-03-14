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
  output/sql/*_pair.json
        ↓
  SQL EXPLAIN 校验 + 可选 LLM 修复
        ↓
  向量化 question，连同 question_sql JSON 加载到 Milvus
```

---

## 2. 与 MetaWeave 现有架构的关系

### 2.1 复用现有服务

| 现有服务 | 用途 | 复用方式 |
|----------|------|----------|
| `services/llm_service.py` → `LLMService` | Question-SQL 生成、SQL 修复 | 直接调用 `call_llm(prompt, system_message)` |
| `services/embedding_service.py` → `EmbeddingService` | question 文本向量化 | 直接调用 `get_embeddings(texts)` |
| `services/vector_db/milvus_client.py` → `MilvusClient` | 向量存储与检索 | 直接调用 `ensure_collection()`、`upsert_batch()` |
| `services/config_loader.py` → `ConfigLoader` | 配置加载（`.env` + YAML） | 直接调用 `load()` |
| `metaweave/core/metadata/connector.py` → `DatabaseConnector` | SQL EXPLAIN 校验的数据库连接 | 复用连接配置 |

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
    domain: str = ""        # 来源主题域名称
    tables: List[str] = field(default_factory=list)  # 涉及的表
```

### 3.2 `ValidationResult`

单条 SQL 的校验结果：

```python
@dataclass
class ValidationResult:
    index: int              # 在 pair 列表中的序号
    sql: str                # 原始 SQL
    valid: bool             # EXPLAIN 是否通过
    error_message: str = "" # 错误信息
    execution_time: float = 0.0
    repaired_sql: str = ""  # LLM 修复后的 SQL（如果修复成功）
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
    output_file: str
```

---

## 4. 详细设计

### 4.1 Step 1: Question-SQL 生成（`generator.py`）

#### 4.1.1 输入

- **MD 文件目录**：`output/md/`，包含所有表的结构文档
- **主题域配置**：`configs/db_domains.yaml`，包含数据库描述和业务主题域列表
- **生成参数**：每个主题域生成多少条 Question-SQL（默认 10）

#### 4.1.2 处理流程

```
1. 读取 db_domains.yaml，获取 database 描述和 domains 列表
2. 读取 output/md/*.md，构建表结构文本上下文
3. 跳过 name == "_未分类_" 的主题域
4. 对每个主题域：
   a. 构建 LLM 提示词（注入：数据库描述、主题域信息、相关表的 MD 内容）
   b. 调用 LLMService.call_llm() 生成 Question-SQL JSON
   c. 解析并清洗 LLM 返回结果
   d. 合并到总结果集
5. 将全部 Question-SQL 写入 output/sql/{db_name}_{timestamp}_pair.json
```

#### 4.1.3 MD 上下文构建策略

对每个主题域，只注入该主题域 `related_tables`（在 `db_domains.yaml` 中虽未显式列出 `related_tables` 字段，但可通过主题域描述中提到的实体推断相关表）中涉及的表的 MD 内容，避免全量注入导致 token 超限。

如果 `db_domains.yaml` 未包含 `related_tables` 字段，则使用全量 MD 内容（适用于表数量较少的场景，如当前 15 张表）。

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
- 将多行文本折叠为单行
- 确保 SQL 以分号结尾
- 去除首尾空白

#### 4.1.6 输出

文件路径：`output/sql/{db_name}_{timestamp}_pair.json`

文件格式（与 data_pipeline 保持一致）：

```json
[
  {
    "question": "各门店的月度租赁收入趋势如何？",
    "sql": "SELECT s.store_id AS 门店ID, TO_CHAR(p.payment_date, 'YYYY-MM') AS 月份, SUM(p.amount) AS 月度收入 FROM payment p JOIN staff st ON p.staff_id = st.staff_id JOIN store s ON st.store_id = s.store_id GROUP BY s.store_id, TO_CHAR(p.payment_date, 'YYYY-MM') ORDER BY s.store_id, 月份;"
  }
]
```

---

### 4.2 Step 2: SQL EXPLAIN 校验（`validator.py`）

#### 4.2.1 输入

- `output/sql/*_pair.json` 文件
- 数据库连接配置（从 `metadata_config.yaml` 中读取）

#### 4.2.2 校验机制

使用 PostgreSQL `EXPLAIN`（不使用 `ANALYZE`）来验证 SQL 的语法和执行计划可行性：

```python
async with pool.acquire() as conn:
    # 设置只读模式，防止意外写入
    await conn.execute("SET default_transaction_read_only = on")
    await conn.execute(f"EXPLAIN {sql}")
```

**关键设计决策**：

- 使用 `EXPLAIN` 而非 `EXPLAIN ANALYZE`：只做计划验证，不实际执行查询
- 设置 `default_transaction_read_only = on`：防止 SQL 包含写操作时误执行
- 每条 SQL 设置超时保护（默认 30 秒）

#### 4.2.3 并发控制

- 使用 `asyncio.Semaphore` 控制并发校验数（默认 5）
- 使用 `psycopg` 异步连接池

#### 4.2.4 重试机制

对以下类型的错误自动重试（最多 2 次）：

- 连接错误（`connection`、`network`）
- 超时错误（`timeout`）
- 连接池错误（`pool`）

语法错误不重试。

#### 4.2.5 LLM SQL 修复

默认启用（`enable_sql_repair = true`）。对每条校验失败的 SQL：

1. 收集失败的 SQL、对应的 question 及 PostgreSQL 错误信息
2. 构建修复提示词，调用 `LLMService.call_llm()` 生成修复后的 SQL
3. 对修复后的 SQL 再次执行 EXPLAIN 校验
4. **修复成功**：替换原 JSON 中的 SQL
5. **修复失败**：从原 JSON 中删除该条 question-sql 对

#### 4.2.6 原文件修改

默认启用（`modify_original_file = true`）。处理流程：

1. 创建原文件的 `.backup` 备份（如 `qs_dvdrental_20260314_pair.json.backup`）
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

输入文件: output/sql/qs_dvdrental_20260314_120000_pair.json
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
    FieldSchema(name="domain",        dtype=DataType.VARCHAR, max_length=256),
    FieldSchema(name="embedding",     dtype=DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema(name="updated_at",    dtype=DataType.INT64),
]
```

字段说明：

| 字段 | 说明 |
|------|------|
| `example_id` | 主键，格式 `{db_name}.{domain}.{index}`，支持 upsert |
| `question_sql` | question 与 sql 的合并 JSON 串，如 `{"question":"...","sql":"..."}` |
| `domain` | 来源业务主题域 |
| `embedding` | **基于 question 文本**计算的向量表示（1024 维） |
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
1. 读取 output/sql/*_pair.json
2. 初始化 MilvusClient 和 EmbeddingService
3. 确保 Collection 存在（ensure_collection）
4. 分批处理：
   a. 提取当前批次的 question 列表
   b. 调用 EmbeddingService.get_embeddings(questions) 得到向量
   c. 将每条 {question, sql} 序列化为 JSON 字符串，写入 question_sql 字段
   d. 调用 MilvusClient.upsert_batch() 写入（支持 clean 模式用 insert_batch）
5. 返回加载统计结果
```

#### 4.3.4 继承 `BaseLoader`

遵循 MetaWeave 现有的 Loader 模式，继承 `metaweave.core.loaders.base.BaseLoader`，实现 `validate()` 和 `load()` 方法：

```python
class SQLExampleLoader(BaseLoader):
    def validate(self) -> bool: ...
    def load(self, clean: bool = False) -> Dict[str, Any]: ...
```

---

## 5. 配置设计

### 5.1 `metadata_config.yaml` 新增部分

不新增——复用现有 `llm`、`embedding`、`vector_database`、`database` 配置段。

### 5.2 `loader_config.yaml` 新增部分

在现有 `sql_loader` 段中补充完整配置：

```yaml
# SQL Example 加载器配置
sql_loader:
  # 输入目录路径（相对于项目根目录）
  input_dir: "output/sql"
  # Milvus Collection 名称（必填）
  collection_name: "sql_example_embeddings"

  # 加载选项
  options:
    batch_size: 50            # 每批向量化和写入的数量
```

### 5.3 `configs/sql_rag.yaml` 新增配置文件

Question-SQL 生成和校验的独立配置：

```yaml
# SQL RAG 生成与校验配置

# Question-SQL 生成配置
generation:
  # 每个主题域生成的 Question-SQL 数量
  questions_per_domain: 10
  # 跳过 _未分类_ 主题域
  skip_uncategorized: true
  # 输出目录
  output_dir: "output/sql"
  # 输出文件前缀
  output_file_prefix: "qs"
  # LLM 调用超时（秒）
  llm_timeout: 120

# SQL 校验配置
validation:
  # 并发校验数
  max_concurrent: 5
  # 单条 SQL 超时（秒）
  timeout: 30
  # 只读模式
  readonly_mode: true
  # 最大重试次数
  max_retries: 2
  # 是否启用 LLM SQL 修复（修复失败的 SQL 将从 JSON 中删除）
  enable_sql_repair: true
  # 是否修改原 JSON 文件（修复成功则替换，修复失败则删除）
  modify_original_file: true
  # 修复批大小（每次 LLM 调用修复几条 SQL）
  repair_batch_size: 2
```

---

## 6. CLI 集成

### 6.1 新增子命令 `sql-rag`

在 `metaweave/cli/` 下新增 `sql_rag_cli.py`，注册为 `cli` 的子命令：

```bash
# 生成 Question-SQL
uv run metaweave sql-rag generate \
  --config configs/sql_rag.yaml \
  --domains-config configs/db_domains.yaml \
  --md-dir output/md

# 校验 SQL
uv run metaweave sql-rag validate \
  --config configs/sql_rag.yaml \
  --input output/sql/qs_dvdrental_20260314_pair.json

# 加载到 Milvus
uv run metaweave sql-rag load \
  --config configs/loader_config.yaml \
  --clean

# 一键执行全部（生成 → 校验 → 加载）
uv run metaweave sql-rag run-all \
  --config configs/sql_rag.yaml \
  --domains-config configs/db_domains.yaml \
  --md-dir output/md \
  --clean
```

### 6.2 与现有 `load` 命令的整合

同时在 `loader_cli.py` 的 `--type` 选项中将 `sql` 类型实现为调用 `SQLExampleLoader`，使以下命令也可用：

```bash
uv run metaweave load --type sql --config configs/loader_config.yaml
```

---

## 7. 目录结构总览

新增/修改的文件清单：

```
metaweave/
├── core/
│   ├── sql_rag/
│   │   ├── __init__.py           # 模块导出
│   │   ├── generator.py          # Question-SQL 生成器
│   │   ├── validator.py          # SQL EXPLAIN 校验器
│   │   ├── loader.py             # Milvus 向量化加载器
│   │   ├── models.py             # 数据模型定义
│   │   └── prompts.py            # LLM 提示词模板
│   └── loaders/
│       └── factory.py            # [修改] 注册 sql 类型的 Loader
├── cli/
│   ├── sql_rag_cli.py            # [新增] sql-rag 子命令
│   └── main.py                   # [修改] 注册 sql-rag 子命令
configs/
├── sql_rag.yaml                  # [新增] 生成与校验配置
├── loader_config.yaml            # [修改] sql_loader 段补全
output/
└── sql/                          # [新增目录] Question-SQL 输出
    └── qs_{db}_{timestamp}_pair.json
```

---

## 8. 与 data_pipeline 的对比

| 维度 | data_pipeline | MetaWeave sql_rag |
|------|---------------|-------------------|
| 表结构来源 | 自行从 DB 抽取并生成 DDL/MD | 复用 `--step md` 已生成的 `output/md/*.md` |
| 主题域来源 | LLM 从 MD 自动提取 | 直接读取 `configs/db_domains.yaml` |
| LLM 调用 | 通过 `vn.chat_with_llm()` | 通过 `LLMService.call_llm()` |
| SQL 校验 | asyncpg + EXPLAIN | psycopg（异步） + EXPLAIN |
| 向量化目标 | question+sql 整体做向量化 → pgvector | 仅 question 做向量化，question+sql 合并为 JSON 串存储 → Milvus |
| 向量存储 | `langchain_pg_embedding` 表 | Milvus Collection |
| 配置方式 | `app_config` + 全局 dict | `ConfigLoader` + YAML + `.env` |
| 日志方式 | `core.logging` | `metaweave.utils.logger` |
| CLI | 独立 `python -m` 脚本 | Click 子命令 |

---

## 9. 依赖与约束

### 9.1 已有依赖（无需新增）

- `psycopg[binary]`：PostgreSQL 连接（SQL 校验）
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

### 10.2 校验阶段

- 数据库连接失败时立即终止并报错
- 单条 SQL 校验超时不阻断其他 SQL
- 连接类错误自动重试

### 10.3 加载阶段

- Embedding 服务调用失败时重试 2 次，仍失败则跳过该批次
- Milvus 写入失败记录错误，不阻断后续批次

---

## 11. 实施计划

建议分 3 步实施：

### 第一步：核心生成与输出

实现 `generator.py`、`models.py`、`prompts.py`，完成：

- 读取 MD 和 db_domains.yaml
- 调用 LLM 生成 Question-SQL
- 输出 `*_pair.json`

验收标准：能生成格式正确的 JSON 文件。

### 第二步：SQL 校验

实现 `validator.py`，完成：

- EXPLAIN 校验
- 可选 LLM 修复
- 校验报告生成

验收标准：能对 JSON 中的 SQL 执行 EXPLAIN 并输出通过率。

### 第三步：Milvus 加载与 CLI

实现 `loader.py`、`sql_rag_cli.py`，完成：

- question 向量化并写入 Milvus
- CLI 子命令注册
- LoaderFactory 注册

验收标准：能通过 CLI 一键完成 生成 → 校验 → 加载 全流程。
