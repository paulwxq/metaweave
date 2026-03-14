# Data Pipeline 模块功能与处理流程说明

## 流程速览

`data_pipeline` 的主流程可以概括为 4 步：

1. 先生成表结构训练材料  
   从业务数据库读取表结构、字段、注释和样例数据，生成每张表的 `.ddl` 和 `_detail.md` 文档。

2. 再生成 Question-SQL 样例  
   读取所有 `_detail.md`，先提取业务主题，再按主题生成一批 `question + sql` 样例，输出为 `*_pair.json`。

3. 然后校验 SQL  
   把 `*_pair.json` 里的 SQL 逐条发到数据库执行 `EXPLAIN`，检查 SQL 是否有效。可选地修复错误 SQL，并回写原文件。

4. 最后加载训练数据  
   扫描输出目录中的 `.ddl`、`.md`、`*_pair.json` 等文件，调用 Vanna 的训练接口，把这些数据加载到向量库中。

一句话概括就是：

`数据库表结构 -> DDL/MD 文档 -> 主题与 Question-SQL -> SQL Explain 校验 -> 导入 Vanna 训练库`

## 1. 模块定位

`data_pipeline` 是当前项目中负责“从业务数据库抽取结构信息，并将其加工为 Vanna 训练数据”的独立子系统。它不是面向终端问答的在线查询模块，而是面向训练数据生产、校验、导入和任务管理的离线/半离线流水线。

从代码职责上看，这个模块承担了四类核心工作：

1. 从 PostgreSQL 业务库读取表结构、字段信息、样例数据和统计信息。
2. 生成带中文注释的 `.ddl` 与 `_detail.md` 文档。
3. 基于表结构文档提取业务主题，并为每个主题生成一组 `question/sql` 训练样例。
4. 使用数据库 `EXPLAIN` 校验 SQL 有效性，并把产物加载到 Vanna / pgvector 训练库中。

因此，`data_pipeline` 本质上是一个“训练数据生产流水线”，而不是单一的脚本集合。

---

## 2. 模块在项目中的职责边界

### 2.1 它负责什么

- 训练任务创建与目录管理
- 表清单解析与系统表过滤
- 数据库权限检查
- 表结构抽取与样例数据采样
- LLM 注释生成
- DDL / Markdown 文档落盘
- 业务主题提取
- 按主题生成 `question/sql` 对
- SQL `EXPLAIN` 校验
- 可选的 LLM SQL 修复与原文件回写
- 训练文件扫描与导入 Vanna
- Vector 表备份 / 清空
- API 任务执行与日志查询支撑

### 2.2 它不直接负责什么

- 在线自然语言问答
- 前端交互展示
- 聊天会话管理
- 普通业务 API

这些能力在项目的 `agent/`、`react_agent/`、`unified_api.py`、`citu_app.py` 等模块中实现。

---

## 3. 总体架构

`data_pipeline` 当前实现可以分成 5 层：

### 3.1 编排层

- `schema_workflow.py`
- `task_executor.py`
- `api/simple_workflow.py`

负责把多个步骤串成完整工作流，并管理执行状态、结果文件和步骤日志。

### 3.2 生成层

- `ddl_generation/training_data_agent.py`
- `qa_generation/qs_agent.py`
- `validators/sql_validation_agent.py`

分别负责：

- DDL/MD 生成
- Question-SQL 生成
- SQL 校验与修复

### 3.3 工具层

- `tools/database_inspector.py`
- `tools/data_sampler.py`
- `tools/comment_generator.py`
- `tools/ddl_generator.py`
- `tools/doc_generator.py`
- `tools/base.py`

负责单表级别的原子处理步骤，并由 `PipelineExecutor` 统一串联。

### 3.4 训练与向量库层

- `trainer/run_training.py`
- `trainer/vanna_trainer.py`
- `trainer/vector_table_manager.py`

负责把已生成的训练文件导入 Vanna，以及对 pgvector 相关表做备份和清空。

### 3.5 API / 任务支撑层

- `api/simple_db_manager.py`
- `api/simple_file_manager.py`
- `api/table_inspector_api.py`
- `api/vector_restore_manager.py`

负责任务持久化、任务目录文件管理、表信息 API 复用、向量数据恢复等。

---

## 4. 目录与文件职责说明

| 目录 / 文件 | 作用 |
| --- | --- |
| `data_pipeline/__init__.py` | 模块导出入口，暴露训练 Agent、SQL 校验 Agent、工作流编排器 |
| `config.py` | 全局配置中心，定义处理链、Question-SQL 生成参数、SQL 校验参数、文件上传参数、Vector 管理参数 |
| `schema_workflow.py` | 端到端工作流编排器，串联四个核心阶段 |
| `task_executor.py` | subprocess 执行入口，供 API 调用 |
| `ddl_generation/` | DDL/MD 训练数据生成 |
| `qa_generation/` | 主题提取与 Question-SQL 生成 |
| `validators/` | 文件数量校验、SQL 校验、CLI 入口 |
| `tools/` | 单表处理工具链 |
| `trainer/` | 训练文件导入 Vanna，管理向量表 |
| `api/` | 任务、文件、表检查、恢复等接口支撑 |
| `utils/` | 表清单解析、权限检查、文件名管理、数据结构等通用能力 |
| `sql/init_tables.sql` | Data Pipeline API 相关任务表的初始化脚本 |

---

## 5. 核心数据结构

模块内部围绕 `TableMetadata` 和 `TableProcessingContext` 组织处理状态。

### 5.1 `FieldInfo`

定义单字段的标准结构，包含：

- 字段名、类型、可空性、默认值
- 原始注释与 LLM 生成注释
- 是否主键、是否外键
- 是否枚举及枚举值
- 长度、精度、小数位

### 5.2 `TableMetadata`

定义单表元数据，包含：

- `schema_name`
- `table_name`
- `full_name`
- 表注释
- 字段列表
- 样例数据
- 行数、表大小

它是 DDL 生成、MD 生成、注释生成、文档生成的核心输入对象。

### 5.3 `ProcessingResult`

每个工具步骤的统一输出结构，包含：

- 是否成功
- 结果数据
- 错误信息
- warnings
- 执行耗时
- metadata

### 5.4 `TableProcessingContext`

单表处理上下文，用于在各工具之间传递状态，核心字段包括：

- 当前表元数据
- 业务上下文
- 输出目录
- 当前 pipeline 名称
- Vanna / LLM 实例
- 文件管理器
- 数据库连接串
- 各步骤执行结果

---

## 6. 处理链配置与执行机制

`config.py` 中定义了 3 种处理链：

- `full`: `database_inspector -> data_sampler -> comment_generator -> ddl_generator -> doc_generator`
- `ddl_only`: `database_inspector -> data_sampler -> comment_generator -> ddl_generator`
- `analysis_only`: `database_inspector -> data_sampler -> comment_generator`

处理链执行由 `tools/base.py` 中的 `PipelineExecutor` 完成：

1. 从 `ToolRegistry` 获取工具实例。
2. 对需要 LLM 的工具自动注入 `create_vanna_instance()` 创建的 Vanna 实例。
3. 顺序执行每个工具。
4. 将每一步结果写回 `TableProcessingContext.step_results`。
5. 依据 `continue_on_error` 决定失败后是继续还是中止。

这意味着 DDL/MD 生成不是一个单脚本行为，而是单表级“多工具流水线”的聚合结果。

---

## 7. 主流程一：DDL / MD 文档生成

### 7.1 入口

- CLI: `ddl_generation/ddl_md_generator.py`
- 编程入口: `SchemaTrainingDataAgent`
- 工作流入口: `SchemaWorkflowOrchestrator._execute_step_1_ddl_md_generation`

### 7.2 输入

- 业务数据库连接字符串
- 表清单文件
- 业务上下文描述
- 输出目录
- pipeline 类型

### 7.3 处理步骤

#### 步骤 1：初始化

`SchemaTrainingDataAgent` 会：

- 创建输出目录
- 初始化 `FileNameManager`
- 初始化 `PipelineExecutor`
- 创建数据库连接池

#### 步骤 2：数据库权限检查

`DatabasePermissionChecker` 会检测：

- 能否连接数据库
- 能否查询元数据
- 能否查询数据
- 是否为只读库

当前逻辑允许只读数据库参与处理，只要查询权限足够。

#### 步骤 3：解析表清单

`TableListParser` 支持：

- 按换行解析
- 按逗号解析
- 跳过空行、注释行
- 去重
- 基础表名合法性校验

#### 步骤 4：过滤系统表

`SystemTableFilter` 会过滤：

- `pg_*`
- `information_schema`
- 系统 schema
- 临时表 schema

#### 步骤 5：逐表执行工具链

对每个表构造 `TableMetadata` 与 `TableProcessingContext` 后，执行如下工具：

1. `DatabaseInspectorTool`
2. `DataSamplerTool`
3. `CommentGeneratorTool`
4. `DDLGeneratorTool`
5. `DocGeneratorTool`

### 7.4 各工具在本阶段的作用

#### `DatabaseInspectorTool`

负责从 PostgreSQL 获取：

- 表是否存在
- 字段定义
- 主键 / 外键
- 表注释 / 字段注释
- 行数
- 表大小

#### `DataSamplerTool`

负责抽取样例数据：

- 小表用 `LIMIT`
- 大表使用“前段 + 中段 + 尾段”的智能采样
- 尝试使用 `TABLESAMPLE`

样例数据随后会进入注释生成提示词。

#### `CommentGeneratorTool`

负责调用 LLM 生成：

- 表中文注释
- 字段中文注释
- 枚举字段建议

同时它还会尝试校验枚举候选值，并将结果写回字段元数据。

#### `DDLGeneratorTool`

根据 `TableMetadata` 生成带中文说明的 DDL 文本，并写入 `.ddl` 文件。

#### `DocGeneratorTool`

根据 `TableMetadata` 和可选 DDL 内容生成 `_detail.md` 文档，包含：

- 表标题与简介
- 字段列表
- 字段约束
- 示例值
- 枚举说明
- 补充说明

### 7.5 输出产物

- `*.ddl`
- `*_detail.md`
- `filename_mapping.txt`
- 详细处理报告

---

## 8. 主流程二：Question-SQL 训练数据生成

### 8.1 入口

- CLI: `qa_generation/qs_generator.py`
- 编程入口: `QuestionSQLGenerationAgent`
- 工作流入口: `SchemaWorkflowOrchestrator._execute_step_2_question_sql_generation`

### 8.2 输入

- 上一步产出的 `_detail.md` 文件集合
- 表清单文件
- 业务上下文
- 输出目录

### 8.3 前置校验

先由 `FileCountValidator` 校验：

- 表清单数量是否超过 `qs_generation.max_tables`
- 每个表是否有对应的 `.ddl`
- 每个表是否有对应的 `_detail.md`

只有结构文档完整，才进入问答 SQL 生成阶段。

### 8.4 主题提取

`MDFileAnalyzer` 会将所有 `_detail.md` 汇总成一段大文本，然后 `ThemeExtractor` 调用 LLM 输出主题 JSON。

主题对象结构包括：

- `topic_name`
- `description`
- `related_tables`
- `biz_entities`
- `biz_metrics`

当前默认配置：

- `theme_count = 5`
- 每个主题生成 `questions_per_theme = 10`

因此一次标准任务默认会生成约 50 对问答 SQL。

### 8.5 按主题生成 Question-SQL

`QuestionSQLGenerationAgent` 对每个主题执行：

1. 构建 prompt，注入主题信息和全部 MD 内容
2. 调用 `vn.chat_with_llm`
3. 解析返回 JSON
4. 清洗 `question` 与 `sql`
5. 强制转为单行
6. 确保 SQL 以分号结尾

### 8.6 数据格式说明

最终产物不是单个 `{"问题": "SQL"}` 的 JSON map，而是数组格式：

```json
[
  {
    "question": "问题文本",
    "sql": "SELECT ...;"
  }
]
```

语义上仍然是“问题 -> SQL”的键值对集合，只是采用对象数组表示，便于后续附加更多字段。

### 8.7 附加输出

除主问答文件外，本阶段还会生成：

- `metadata.txt`
- `metadata_detail.md`
- `db_query_decision_prompt.txt`

其中：

- `metadata.txt` 保存主题元数据的建表与插入语句
- `metadata_detail.md` 是主题元数据表的说明文档
- `db_query_decision_prompt.txt` 用于帮助后续问答系统理解数据库的业务范围

### 8.8 输出产物

- `qs_<db_name>_<timestamp>_pair.json`
- `metadata.txt`
- `metadata_detail.md`
- `db_query_decision_prompt.txt`
- 可选的中间结果文件 / 恢复文件

---

## 9. 主流程三：SQL 校验与修复

### 9.1 入口

- CLI: `validators/sql_validate_cli.py`
- 编程入口: `SQLValidationAgent`
- 工作流入口: `SchemaWorkflowOrchestrator._execute_step_3_sql_validation`

### 9.2 输入

- `*_pair.json`
- 业务数据库连接串
- 输出目录
- 修复开关
- 原文件修改开关

### 9.3 核心校验逻辑

`SQLValidationAgent` 会：

1. 读取 JSON 文件
2. 提取全部 `sql`
3. 测试数据库连接
4. 分批并发执行校验

底层真正做校验的是 `SQLValidator`，其关键行为是：

- 创建 asyncpg 连接池
- 可选打开只读事务模式
- 对每条 SQL 执行 `EXPLAIN {sql}`
- 捕获超时、连接错误、语法错误
- 根据配置进行有限重试

因此这里不是“真正执行查询拿业务结果”，而是“通过数据库解析和执行计划生成能力验证 SQL 可行性”。

### 9.4 修复与回写机制

如果启用 SQL 修复：

1. 找到校验失败的 SQL
2. 调用 LLM 生成修复后的 SQL
3. 再次执行 `EXPLAIN`
4. 成功则替换原 SQL
5. 失败则保留错误信息

如果启用原文件修改：

- 修复成功的项会更新原 JSON 中的 SQL
- 无法修复的项会从原 JSON 中删除
- 同时会生成 `.backup` 备份文件

### 9.5 需要注意的配置实际行为

`config.py` 中默认值是：

- `enable_sql_repair = False`
- `modify_original_file = False`

但在完整工作流或 API 任务执行时，这两个值经常会被任务参数覆盖为 `True`。因此：

- “配置默认关闭”不代表“工作流执行时一定关闭”
- 实际是否修复、是否改原文件，取决于创建任务时传入的参数

### 9.6 输出产物

- SQL 校验摘要日志
- 可选 JSON 详细报告
- 可选 `.backup` 原文件备份
- 可选修改日志 `file_modifications_*.log`

---

## 10. 主流程四：训练数据加载

### 10.1 入口

- CLI: `trainer/run_training.py`
- 工作流入口: `SchemaWorkflowOrchestrator._execute_step_4_training_data_load`

### 10.2 功能目标

扫描任务输出目录中的训练文件，并根据文件类型导入 Vanna。

### 10.3 支持的训练文件类型

- `.ddl`
- `.md` / `.markdown`
- `_pair.json` / `_pairs.json`
- `_pair.sql` / `_pairs.sql`
- 普通 `.sql`

### 10.4 处理规则

`run_training.py` 会按扩展名分发：

- DDL 文件 -> `train_ddl_statements`
- Markdown 文档 -> `train_documentation_blocks`
- JSON 问答对 -> `train_json_question_sql_pairs`
- 格式化问答对 -> `train_formatted_question_sql_pairs`
- 普通 SQL -> `train_sql_examples`

### 10.5 Vanna 导入方式

真正写入 Vanna 的动作在 `vanna_trainer.py` 中完成，核心接口是：

- `vn.train(ddl=...)`
- `vn.train(documentation=...)`
- `vn.train(question=..., sql=...)`

模块内部还封装了一个 `BatchProcessor`，用于把多条训练项聚合后批处理，提高导入效率。

### 10.6 导入后的验证

工作流在训练加载完成后，会尝试通过 `vn.get_training_data()` 回读训练数据，以确认：

- 总记录数
- 各类型训练数据数量

---

## 10.1 `*_pair.json` 加载到 pgvector 时的目标表结构

`data_pipeline` 在加载 `*_pair.json` 时，并不会把 `question` 和 `sql` 分别插入一张业务明细表，而是写入 pgvector 的通用向量存储表。

当前使用的是两张底层表：

### `langchain_pg_collection`

```sql
CREATE TABLE langchain_pg_collection (
    uuid uuid PRIMARY KEY,
    name varchar NOT NULL UNIQUE,
    cmetadata json
);
```

字段含义：

- `uuid`: 集合主键
- `name`: 集合名称，例如 `sql`、`ddl`、`documentation`、`error_sql`
- `cmetadata`: 集合级元数据

### `langchain_pg_embedding`

```sql
CREATE TABLE langchain_pg_embedding (
    id varchar PRIMARY KEY,
    collection_id uuid REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding vector,
    document varchar,
    cmetadata jsonb
);
```

字段含义：

- `id`: 单条训练数据主键，当前项目中常见格式为 `uuid-sql`、`uuid-ddl`、`uuid-doc`
- `collection_id`: 指向 `langchain_pg_collection.uuid`
- `embedding`: 文本向量
- `document`: 实际文本内容
- `cmetadata`: 文档级元数据

### `*_pair.json` 的落库方式

当加载 `*_pair.json` 时，每一项通常长这样：

```json
{
  "question": "查询某个业务问题",
  "sql": "SELECT ..."
}
```

导入时，系统会把这一对数据组装成一个 JSON 字符串：

```json
{"question":"查询某个业务问题","sql":"SELECT ..."}
```

然后写入 `sql` collection，对应关系如下：

- `langchain_pg_collection.name = 'sql'`
- `langchain_pg_embedding.document = {"question":"...","sql":"..."}`
- `langchain_pg_embedding.cmetadata` 中至少包含训练项的 `id`

也就是说：

- `question` 和 `sql` **不会拆成两列单独存储**
- 它们会一起放进 `langchain_pg_embedding.document`
- 向量存放在同一行的 `embedding` 字段中

因此，从数据模型上看，`*_pair.json` 最终进入的是：

`Question-SQL 对 -> sql collection -> langchain_pg_embedding.document + embedding`

---

## 11. API 模式与脚本模式

`data_pipeline` 同时支持两种运行方式。

### 11.1 脚本模式

主要入口：

- `python -m data_pipeline.ddl_generation.ddl_md_generator`
- `python -m data_pipeline.qa_generation.qs_generator`
- `python -m data_pipeline.validators.sql_validate_cli`
- `python -m data_pipeline.trainer.run_training`
- `python -m data_pipeline.schema_workflow`

适合：

- 手动运行
- 开发调试
- 本地验证

### 11.2 API 模式

主要组件：

- `api/simple_db_manager.py`
- `api/simple_file_manager.py`
- `api/simple_workflow.py`
- `task_executor.py`

适合：

- Web API 调用
- 任务创建、轮询、日志查询
- 分步执行和结果文件下载

在 API 模式下，任务执行通常由宿主应用调用 `task_executor.py` 子进程完成，避免阻塞主服务线程。

---

## 12. 辅助能力说明

### 12.1 任务管理

`SimpleTaskManager` 会在 pgvector 库中维护任务状态，包括：

- 任务记录
- 步骤状态
- 执行时间
- 错误信息

它依赖 Data Pipeline API 相关数据库表。

### 12.2 文件管理

`SimpleFileManager` 管理任务目录中的：

- 文件列表
- 文件路径安全校验
- 表清单上传
- 文件大小与类型信息

### 12.3 表结构查询 API

`TableInspectorAPI` 复用了 `DatabaseInspectorTool`、`DataSamplerTool`、`CommentGeneratorTool`、`DDLGeneratorTool`、`DocGeneratorTool`，可直接对单表输出：

- DDL
- MD 文档
- 或两者同时输出

这是对 DDL/MD 生成能力的一种 API 化复用。

### 12.4 Vector 表管理

`VectorTableManager` 支持：

- 备份 `langchain_pg_collection`
- 备份 `langchain_pg_embedding`
- 清空 `langchain_pg_embedding`

通常在重新加载训练数据前使用，用于控制向量库状态。

---

## 13. 输入、输出与产物关系

### 13.1 主要输入

- 业务数据库连接串
- 表清单文件
- 业务上下文文本
- 可选任务参数

### 13.2 主要中间产物

- `*.ddl`
- `*_detail.md`
- `qs_intermediate_*.json`
- `metadata.txt`
- `db_query_decision_prompt.txt`
- SQL 校验日志

### 13.3 主要最终产物

- `*_pair.json`
- 已校验并修正后的 `*_pair.json`
- 导入到 Vanna / pgvector 的训练数据

可以把整个模块理解成如下产物流转：

`表清单 + 数据库连接`
-> `结构抽取`
-> `DDL/MD`
-> `主题`
-> `Question-SQL`
-> `EXPLAIN 校验/修复`
-> `训练数据导入`

---

## 14. 一次完整任务的典型处理流程

以完整工作流为例，实际顺序如下：

1. 创建任务目录与任务记录。
2. 执行 `ddl_generation`。
3. 从数据库读取表结构、字段、注释、样例数据。
4. 使用 LLM 生成更适合业务语义的中文注释。
5. 生成每个表的 `.ddl` 和 `_detail.md`。
6. 汇总全部 MD，提取 5 个业务主题。
7. 每个主题生成 10 个问答 SQL 对。
8. 输出 `*_pair.json`。
9. 对 JSON 内 SQL 执行 `EXPLAIN` 校验。
10. 可选调用 LLM 修复错误 SQL。
11. 可选回写原 JSON，并删除无法修复的项。
12. 扫描目录中的 `.ddl`、`.md`、`*_pair.json`。
13. 调用 `vn.train(...)` 导入训练数据。
14. 记录统计结果与任务状态。

---

## 15. 当前实现的依赖与耦合点

虽然 `data_pipeline` 在目录上已相对独立，但当前实现并不是完全无依赖的独立包，主要耦合点有：

- 依赖 `core.vanna_llm_factory.create_vanna_instance`
- 依赖 `core.logging`
- 依赖 `app_config` 中的数据库和训练配置
- 依赖 `common.vanna_instance`
- API 任务模式依赖项目内的任务表结构

因此，它更准确的定位是“项目内可复用的独立子系统”，而不是“完全脱离项目即可运行的纯净模块”。

---

## 16. 模块的优点

- 流程完整，从结构抽取到训练导入闭环清晰
- 各阶段都有独立 CLI，便于分步调试
- 内部处理对象统一，便于扩展
- SQL 校验使用 `EXPLAIN`，安全性比直接执行更高
- 任务模式与脚本模式并存，适配面较广
- 生成产物齐全，便于人工审查和问题追踪

---

## 17. 当前实现需要注意的点

### 17.1 完整性依赖较强

Question-SQL 生成依赖 DDL/MD 先生成完成，文件缺失会直接中断后续流程。

### 17.2 LLM 生成结果高度影响质量

表注释、主题、问答 SQL 都依赖 LLM 输出，因此：

- 业务上下文越清晰，结果通常越稳定
- 样例数据质量会直接影响注释与主题质量

### 17.3 SQL 校验是“可解析性校验”，不是“业务正确性证明”

`EXPLAIN` 可以证明 SQL 基本有效，但不能证明：

- 指标语义正确
- JOIN 逻辑正确
- 业务筛选条件合理

### 17.4 训练导入与当前项目技术栈绑定

最后一步默认导入的是当前项目的 Vanna / pgvector 方案，不适合直接迁移到任意训练框架而不做适配。

---

## 18. 结论

`data_pipeline` 是当前项目中最接近“离线训练数据工厂”的模块。它以 PostgreSQL 业务数据库为输入，通过表结构抽取、样例采样、LLM 注释增强、主题提取、问答 SQL 生成、SQL `EXPLAIN` 校验和 Vanna 导入，形成了一套较完整的训练数据生产链路。

从维护视角看，可以把它理解为：

- 一个可单独运行的训练数据流水线
- 一套可被 API 复用的结构分析与文档生成能力
- 一个与 Vanna 训练体系强绑定的训练数据装配模块

后续如果要继续演进，最值得优先抽象的边界是：

- LLM 适配层
- 日志适配层
- 任务状态存储层
- 训练结果落地层

这样可以把 `data_pipeline` 从“项目内部子系统”进一步提升为“可迁移的独立训练流水线模块”。
