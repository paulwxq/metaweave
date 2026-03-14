# Data Pipeline 迁移改造注意事项

## 1. 文档目标

本文档说明：如果要把当前项目中的 `data_pipeline` 模块迁移到其他项目，需要重点改动哪些部分、哪些代码可以直接复用、哪些代码必须重写，以及推荐的迁移顺序。

这份文档关注的是“迁移改造”，不是功能说明。功能和流程请参考：

- [20_data_pipeline模块功能与处理流程说明.md](/mnt/c/Projects/cursor_projects/Vanna-Chainlit-Chromadb/docs/20_data_pipeline模块功能与处理流程说明.md)

---

## 2. 先给结论

`data_pipeline` 可以迁移，但不适合“整目录复制后直接运行”。

它当前是一个“项目内相对独立的子系统”，不是完全无依赖的独立包。迁移时，建议采用：

`保留核心流程 + 重写宿主适配层`

也就是：

- 保留：DDL/MD 生成、主题提取、Question-SQL 生成、SQL `EXPLAIN` 校验、训练文件扫描
- 重写：配置、日志、LLM/Vanna 工厂、任务管理、向量库存储适配

---

## 3. 哪些部分最值得迁移

最值得保留的核心代码有：

### 3.1 核心流程

- `data_pipeline/schema_workflow.py`
- `data_pipeline/ddl_generation/training_data_agent.py`
- `data_pipeline/qa_generation/qs_agent.py`
- `data_pipeline/analyzers/theme_extractor.py`
- `data_pipeline/validators/sql_validator.py`
- `data_pipeline/validators/sql_validation_agent.py`

这些文件决定了主流程：

`表结构抽取 -> DDL/MD -> 主题 -> Question-SQL -> SQL 校验`

### 3.2 单表工具链

- `data_pipeline/tools/base.py`
- `data_pipeline/tools/database_inspector.py`
- `data_pipeline/tools/data_sampler.py`
- `data_pipeline/tools/comment_generator.py`
- `data_pipeline/tools/ddl_generator.py`
- `data_pipeline/tools/doc_generator.py`

这些文件负责单表级处理逻辑，复用价值很高。

### 3.3 通用工具

- `data_pipeline/utils/data_structures.py`
- `data_pipeline/utils/table_parser.py`
- `data_pipeline/utils/system_filter.py`
- `data_pipeline/utils/permission_checker.py`
- `data_pipeline/utils/file_manager.py`
- `data_pipeline/validators/file_count_validator.py`

这些基本都可以直接迁移。

---

## 4. 迁移时必须重点改动的部分

以下部分不是不能迁移，而是不能直接照搬。

## 4.1 配置系统：必须改

当前 `data_pipeline` 依赖项目级 `app_config.py`，里面混合了：

- LLM 配置
- embedding 配置
- 业务数据库配置
- pgvector 配置
- 训练批处理配置
- Redis 配置

### 当前依赖点

- `core/vanna_llm_factory.py`
- `data_pipeline/api/simple_db_manager.py`
- `data_pipeline/trainer/vanna_trainer.py`
- `data_pipeline/trainer/vector_table_manager.py`

### 迁移建议

迁移后不要继续依赖 `app_config.py`，建议改成以下任一方式：

1. 一个独立的 `data_pipeline/settings.py`
2. `.env + pydantic-settings`
3. YAML/JSON 配置文件

### 最少需要拆出的配置项

- 业务库连接串
- 向量库连接串
- LLM 提供商与模型配置
- embedding 配置
- 输出目录配置
- SQL 校验配置
- 问答生成配置

---

## 4.2 LLM / Vanna 工厂：必须改

当前 `data_pipeline` 依赖：

- `core.vanna_llm_factory.create_vanna_instance()`
- `common.vanna_instance.get_vanna_instance()`

而 `create_vanna_instance()` 不只是创建 LLM，还会：

- 选择 LLM 类型
- 选择向量数据库类型
- 配置 embedding
- 创建 Vanna 实例
- 自动连接业务数据库

这意味着当前的 `data_pipeline` 已经默认绑定“Vanna + 项目里的模型工厂 + 项目里的数据库配置”。

### 当前影响范围

- `ToolRegistry` 自动给需要 LLM 的工具注入 `vn`
- `QuestionSQLGenerationAgent` 用 `vn.chat_with_llm()`
- `ThemeExtractor` 用 `vn.chat_with_llm()`
- `CommentGeneratorTool` 用 `vn.chat_with_llm()`
- 训练加载用 `vn.train(...)`

### 迁移建议

把这部分抽象成两个接口：

1. `LLMClient`
2. `TrainingStore`

建议拆分成：

- `chat_with_llm(prompt, system_prompt)`：仅负责生成文本
- `train(question/sql/ddl/documentation)`：仅负责训练落库

如果新项目不使用 Vanna，可以：

- 保留生成阶段
- 替换训练加载阶段

---

## 4.3 日志系统：建议重写

当前日志依赖：

- `core.logging`
- `core/logging/log_manager.py`
- `data_pipeline/dp_logging/__init__.py`

而这个日志系统还依赖项目级：

- `config/logging_config.yaml`
- `config/logging_config_windows.yaml`

### 迁移风险

如果直接搬过去，但没有这些配置文件，会出现：

- 日志目录不一致
- logger 名称混乱
- 文件 handler 配置丢失

### 迁移建议

迁移后直接改成标准 `logging` 即可：

- 一个控制台 handler
- 一个 RotatingFileHandler
- 可选任务目录日志

不要把整个 `core.logging` 一起搬过去，收益不高。

---

## 4.4 API 任务管理：通常要重写

当前 API 模式依赖：

- `data_pipeline/api/simple_db_manager.py`
- `data_pipeline/sql/init_tables.sql`

它在 pgvector 数据库中维护：

- `data_pipeline_tasks`
- `data_pipeline_task_steps`

### 如果新项目不需要这些能力

下面这些可以不迁移：

- 任务状态表
- 分步执行状态更新
- 任务列表查询
- 日志查询接口
- 文件上传接口

### 如果新项目仍需要任务管理

建议重写 `SimpleTaskManager`，不要强行复用原实现。原因：

- 现在它直接依赖 `app_config.PGVECTOR_CONFIG`
- 它假定任务表就建在 pgvector 库里
- 它的表设计是为当前项目 API 量身定做的

迁移时更合理的做法是：

- 保留 `SimpleWorkflowExecutor` 的思路
- 用新项目自己的任务表或消息队列重写任务状态持久化

---

## 4.5 训练加载层：取决于目标项目

当前训练加载的核心是：

- `run_training.py`
- `vanna_trainer.py`
- `custompgvector/pgvector.py`

它默认假设：

- 训练目标是 Vanna
- 存储目标是 `langchain_pg_collection` / `langchain_pg_embedding`
- 训练类型分为 `sql / ddl / documentation / error_sql`

### 如果目标项目仍使用 Vanna

这层可以保留，但要改：

- 配置来源
- Vanna 工厂
- 向量库连接

### 如果目标项目不使用 Vanna

这层建议全部替换：

- `vn.train(...)`
- `vn.get_training_data()`
- `PG_VectorStore`

都要换成你自己的训练数据落地方式。

---

## 5. 哪些代码大概率可以直接复用

以下代码通常改动较少：

- `data_pipeline/utils/data_structures.py`
- `data_pipeline/utils/table_parser.py`
- `data_pipeline/utils/system_filter.py`
- `data_pipeline/utils/permission_checker.py`
- `data_pipeline/utils/file_manager.py`
- `data_pipeline/validators/file_count_validator.py`
- `data_pipeline/tools/database_inspector.py`
- `data_pipeline/tools/data_sampler.py`
- `data_pipeline/tools/ddl_generator.py`
- `data_pipeline/tools/doc_generator.py`

原因是这些代码更多依赖：

- PostgreSQL
- 文件系统
- 标准 Python 库

而不是当前项目的宿主架构。

---

## 6. 哪些代码建议“保留思路，重写实现”

### 6.1 `core/vanna_llm_factory.py`

不建议直接迁移。因为它绑定了：

- `app_config`
- 当前 LLM 配置选择逻辑
- 当前 vector db 配置
- 当前 embedding 配置
- 当前业务库连接方式

### 6.2 `common/vanna_instance.py`

这是项目级单例管理器，建议在新项目里按需要重写，不要原样搬。

### 6.3 `data_pipeline/api/simple_db_manager.py`

这是当前项目 API 任务表适配器。除非新项目任务模型和当前项目几乎完全一致，否则建议重写。

### 6.4 `data_pipeline/dp_logging/__init__.py`

建议直接替换为标准日志封装。

### 6.5 `trainer/vanna_trainer.py`

如果新项目不再使用 Vanna，这部分不应迁移。

---

## 7. 迁移时最容易忽略的改动点

## 7.1 `ToolRegistry` 会自动注入 Vanna

`tools/base.py` 中，注册工具后，凡是 `needs_llm=True` 的工具都会自动注入 `create_vanna_instance()` 创建的实例。

这意味着一旦迁移后没有改这里：

- `comment_generator`
- `theme_extractor`
- `qs_agent`

都会继续隐式依赖老项目的 Vanna 工厂。

迁移时这里必须改。

## 7.2 `create_vanna_instance()` 会自动连接业务数据库

这会导致两个耦合问题：

1. LLM 初始化和业务数据库连接耦合在一起
2. 新项目如果连接方式不同，整个初始化会失败

迁移后最好拆成：

- “文本生成客户端”
- “业务数据库连接”
- “训练存储客户端”

三层分离。

## 7.3 路径默认值绑定项目目录

很多地方默认写的是：

- `./data_pipeline/training_data/`
- `Path(__file__).parent.parent.parent / "data_pipeline" / "training_data"`

如果你把模块迁到新项目但不改这些默认路径：

- 文件会写到错误目录
- 日志目录可能错位
- 任务目录解析可能失效

迁移时统一改成配置驱动。

## 7.4 `sql_validate_cli.py` 会覆盖默认配置

SQL 校验 CLI 里会直接改全局 `SCHEMA_TOOLS_CONFIG['sql_validation']`。

如果迁移后改成服务化部署或多任务并发执行，这种“运行时改全局配置”的写法风险较大。

建议改成：

- 每次实例化 `SQLValidationAgent` 时传入局部配置
- 不要直接修改模块级全局变量

## 7.5 训练导入依赖 `langchain_pg_*` 物理表

如果新项目继续用 pgvector，但不是 LangChain PGVector 默认表结构，那么：

- `langchain_pg_collection`
- `langchain_pg_embedding`

相关逻辑都要改，包括：

- 导入
- 查询
- 删除
- 备份
- 恢复

---

## 8. 推荐的迁移拆分方案

建议按下面方式拆成 4 个层次。

## 8.1 `pipeline_core`

放纯流程和纯工具：

- `schema_workflow.py`
- `training_data_agent.py`
- `qs_agent.py`
- `sql_validation_agent.py`
- `tools/`
- `utils/`

要求：

- 不依赖 `app_config`
- 不依赖项目 logger
- 不依赖项目 API 表结构

## 8.2 `pipeline_adapters`

放适配层：

- LLM 适配器
- embedding 适配器
- vector store 适配器
- training store 适配器
- task store 适配器

## 8.3 `pipeline_cli`

放命令行入口：

- `ddl_md_generator.py`
- `qs_generator.py`
- `sql_validate_cli.py`
- `run_training.py`

要求：

- 只负责参数解析和调用
- 不直接修改全局配置

## 8.4 `pipeline_api`

如果需要服务化，再保留：

- `simple_workflow.py`
- `simple_file_manager.py`
- `table_inspector_api.py`

任务状态和数据库层建议重新适配。

---

## 9. 推荐迁移顺序

建议不要一次性迁走全部内容，推荐分 5 步。

### 第一步：先迁“只读核心”

先迁这些不依赖训练落库的部分：

- `utils/`
- `tools/database_inspector.py`
- `tools/data_sampler.py`
- `tools/ddl_generator.py`
- `tools/doc_generator.py`
- `ddl_generation/training_data_agent.py`

目标：

- 在新项目里先把 `.ddl` 和 `_detail.md` 跑通

### 第二步：迁 LLM 生成能力

再接入：

- `comment_generator.py`
- `theme_extractor.py`
- `qs_agent.py`

同时替换：

- `create_vanna_instance()`

目标：

- 在新项目里先把 `*_pair.json` 跑通

### 第三步：迁 SQL 校验能力

迁入：

- `sql_validator.py`
- `sql_validation_agent.py`

目标：

- 在新项目里把 `EXPLAIN` 校验跑通

### 第四步：决定是否迁训练导入

如果新项目还用 Vanna，就迁：

- `run_training.py`
- `vanna_trainer.py`
- `custompgvector/pgvector.py`

如果不用，就在这里改写成你自己的训练存储逻辑。

### 第五步：最后再迁 API 与任务层

只有在新项目确实需要这些时，再迁：

- 任务表
- 文件上传
- 任务查询
- 分步执行 API

不要把这一层放在最前面做。

---

## 10. 一份最小可用迁移清单

如果你的目标只是迁移“生成训练 SQL + explain 校验”能力，那么最小清单如下：

### 建议直接复制

- `data_pipeline/analyzers/theme_extractor.py`
- `data_pipeline/qa_generation/qs_agent.py`
- `data_pipeline/validators/sql_validator.py`
- `data_pipeline/validators/sql_validation_agent.py`
- `data_pipeline/analyzers/md_analyzer.py`
- `data_pipeline/validators/file_count_validator.py`
- `data_pipeline/utils/`

### 需要一起复制并改造

- `data_pipeline/config.py`
- `data_pipeline/tools/base.py`

### 需要重写

- `core/vanna_llm_factory.py`
- `app_config.py` 相关依赖
- `core.logging` / `dp_logging`
- 训练加载逻辑

这样可以用最小成本把核心链路迁走：

`MD 文档 -> 主题 -> Question-SQL -> EXPLAIN 校验`

---

## 11. 迁移后建议新增的抽象接口

为了避免再次耦合，建议在新项目里显式引入以下接口。

### 11.1 `LLMClient`

建议能力：

- `generate_text(prompt, system_prompt=None) -> str`

用于替代：

- `vn.chat_with_llm()`

### 11.2 `TrainingStore`

建议能力：

- `store_ddl(ddl: str)`
- `store_documentation(doc: str)`
- `store_question_sql(question: str, sql: str)`
- `list_training_data()`

用于替代：

- `vn.train(...)`
- `vn.get_training_data()`

### 11.3 `TaskStore`

建议能力：

- `create_task`
- `update_task_status`
- `update_step_status`
- `list_tasks`

用于替代当前 API 层的数据库任务表逻辑。

### 11.4 `Settings`

建议统一提供：

- 业务库配置
- 向量库配置
- 模型配置
- 输出目录
- SQL 校验参数

---

## 12. 迁移验收建议

迁移完成后，建议至少验证以下 4 件事：

1. 能否根据表清单成功生成 `.ddl` 和 `_detail.md`
2. 能否根据 `_detail.md` 成功生成 `*_pair.json`
3. 能否对 `*_pair.json` 中 SQL 执行 `EXPLAIN` 校验
4. 如果保留训练导入，能否成功写入目标训练库

验收顺序不要反过来。先验证前 3 步，再验证训练导入。

---

## 13. 最终建议

迁移 `data_pipeline` 的正确方式，不是“复制目录”，而是“拆核心、换适配层”。

最实用的策略是：

- 把 `data_pipeline` 当成一个“流程模板”
- 保留它对 PostgreSQL 结构抽取、主题生成、Question-SQL 生成、SQL 校验的实现
- 把所有和当前项目绑定的部分改成接口

如果这样做，迁移后的模块会更干净，也更适合以后再次复用。
