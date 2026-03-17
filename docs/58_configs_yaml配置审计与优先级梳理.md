# 58_configs YAML 配置审计与优先级梳理

## 1. 文档目标

本文档对当前仓库 `configs/` 目录下的 YAML 配置进行一次完整审计，重点回答以下问题：

1. 各 YAML 文件分别负责什么
2. YAML 文件之间是否存在直接交叉、重复定义或相互覆盖
3. 代码实际如何读取这些配置，最终优先级是什么
4. 当前默认配置是否合理
5. 哪些地方存在维护风险，后续应如何收敛

本文档基于当前仓库代码与以下配置文件：

1. `configs/metadata_config.yaml`
2. `configs/loader_config.yaml`
3. `configs/sql_rag.yaml`
4. `configs/db_domains.yaml`
5. `configs/dim_tables.yaml`
6. `configs/logging.yaml`
7. `configs/config.yaml`

---

## 2. 结论摘要

### 2.1 总体结论

当前配置体系可以工作，但不是一个“单一事实源”式的干净配置结构。

它的主要特征是：

1. `metadata_config.yaml` 是元数据主链路的主配置
2. `loader_config.yaml` 与 `sql_rag.yaml` 主要作为“引用型配置”，会反向引用 `metadata_config.yaml`
3. `db_domains.yaml` 与 `dim_tables.yaml` 是“半自动生成、半人工维护”的业务配置
4. `config.yaml` 仍在部分路径中被当作全局配置读取，导致系统存在第二个隐式主配置
5. `logging.yaml` 是实际生效的日志配置，而不是 `metadata_config.yaml` 中的 `logging` 段

### 2.2 对两个核心问题的直接回答

#### 问题 1：这些 YAML 文件直接有交叉吗？

没有 YAML 语法层面的直接交叉。

当前 `configs/*.yaml` 中没有使用：

1. YAML anchor
2. alias
3. merge key（`<<:`）
4. include/import 语法

因此不存在“YAML 文件直接 merge 另一个 YAML 文件”的情况。

补充说明：

1. 虽然不存在跨文件的 YAML 级 merge
2. 但文件内部仍可能存在重复定义，例如 `metadata_config.yaml` 内部同时存在 `relationships.weights` 与顶层 `weights`
3. 这属于单文件内部冗余，不属于跨文件直接交叉

#### 问题 2：这些 YAML 会互相覆盖吗？

会，但主要是**代码运行时的读取与合并逻辑**，不是 YAML 自己互相覆盖。

当前真正存在的是：

1. 某些 YAML 通过字段引用另一个 YAML
2. 某些 CLI 参数会在运行时覆盖 YAML 中的路径配置
3. 某些模块会绕过当前链路配置，回退读取 `config.yaml`

---

## 3. 配置文件职责划分

### 3.1 `metadata_config.yaml`

职责：MetaWeave 主流程配置。

主要包含：

1. PostgreSQL 连接
2. 采样与画像
3. LLM 与 Embedding
4. 向量数据库
5. 输出目录
6. 关系发现参数
7. domain 生成参数

主要入口：

1. `metaweave/cli/metadata_cli.py`
2. `metaweave/core/metadata/generator.py`
3. `metaweave/core/relationships/pipeline.py`
4. `metaweave/core/loaders/table_schema_loader.py`

间接引用入口：

1. `metaweave/core/loaders/dim_value_loader.py`
2. `metaweave/core/sql_rag/loader.py`

结论：这是当前仓库中最接近“主配置”的文件。

### 3.2 `loader_config.yaml`

职责：数据加载阶段配置。

主要包含：

1. `metadata_config_file`
2. CQL Loader 配置
3. dim_value Loader 配置
4. table_schema Loader 配置
5. SQL Loader 配置

结论：它本身不是主配置，而是 loader 的入口配置；其中大量实际能力又依赖 `metadata_config.yaml`。

### 3.3 `sql_rag.yaml`

职责：SQL RAG 生成与校验配置。

主要包含：

1. `metadata_config_file`
2. 样例生成参数
3. SQL 校验参数

结论：它也是引用型配置，不独立定义数据库、LLM、Embedding 主参数，而是通过 `metadata_config_file` 回读主配置。

### 3.4 `db_domains.yaml`

职责：数据库业务主题配置。

主要包含：

1. 数据库名称与描述
2. 业务域列表
3. 每个业务域下的表清单

使用方：

1. `rel_llm`
2. `cql`
3. `sql-rag generate`
4. `DomainResolver`

结论：它是 domain 信息的单一事实源，但自身是“可自动生成、可人工改写”的配置型产物。

### 3.5 `dim_tables.yaml`

职责：维表向量加载配置。

主要包含：

1. 按 database 分组的维表清单
2. 每张表的 `embedding_col`

使用方：

1. `DimValueLoader`

生成方式：

1. `metaweave dim_config --generate`
2. `pipeline generate` 中的 `dim_config` 步骤

结论：它不是系统基础配置，而是“依赖 JSON 画像结果生成”的人工确认型配置。

### 3.6 `logging.yaml`

职责：MetaWeave CLI 实际生效的日志配置。

结论：这是独立的日志系统配置文件，按 step 分流日志。

### 3.7 `config.yaml`

职责：遗留的全局系统配置。

主要包含：

1. Neo4j 配置
2. PostgreSQL 配置
3. 向量数据库配置
4. embedding 配置
5. 其他 NL2SQL 历史配置

结论：在 MetaWeave 主链路中它已经不是唯一主配置，但仍被部分底层组件偷偷读取，因此构成隐式第二主配置。

---

## 4. YAML 之间的真实关系图

```text
metadata_config.yaml
├── 直接被 metadata / relationships / cql / table_schema / dim_value / sql loader 使用
├── 被 loader_config.yaml 通过 metadata_config_file 引用
└── 被 sql_rag.yaml 通过 metadata_config_file 引用

loader_config.yaml
├── 定义 loader 自身参数
└── 间接依赖 metadata_config.yaml

sql_rag.yaml
├── 定义 sql-rag 自身参数
└── 间接依赖 metadata_config.yaml

db_domains.yaml
├── 被 rel_llm 使用
├── 被 cql 使用
└── 被 sql-rag generate 使用

dim_tables.yaml
└── 被 dim_value loader 使用

logging.yaml
└── 被 CLI 主入口直接加载

config.yaml
├── 被 ConfigLoader 默认路径读取
├── 被 CQLLoader 在 use_global_config=true 时读取
└── 被 PGConnectionManager 初始化阶段读取 vector_database.active
```

---

## 5. 配置读取与优先级

### 5.1 `metadata_config.yaml` 的读取方式

主流程使用 `ConfigLoader(str(config_path)).load()` 加载 `metadata_config.yaml`，支持 `.env` 与 `${ENV_VAR:default}` 展开。

补充说明：

1. `ConfigLoader` 会先尝试加载项目根目录下的 `.env`
2. 再用 `os.getenv()` 替换 YAML 中的 `${ENV_VAR}` 或 `${ENV_VAR:default}`
3. 若进程环境中已存在同名变量，默认会优先使用进程环境变量，而不是 `.env` 中的值
4. 因此环境变量本身也是配置优先级链的一部分，不应只把 YAML 文件看作唯一配置来源

涉及代码：

1. `metaweave/core/metadata/generator.py`
2. `metaweave/core/relationships/pipeline.py`
3. `metaweave/core/loaders/table_schema_loader.py`
4. `metaweave/core/loaders/dim_value_loader.py`

结论：这条链路是清晰的，优先级也相对稳定。

### 5.2 `loader_config.yaml` 的优先级

默认优先级：

1. `loader_config.yaml` 先加载 loader 自身参数
2. Loader 内部再读取 `metadata_config_file`
3. 对于某些命令，CLI 参数会覆盖 `loader_config.yaml` 中的 `metadata_config_file`

典型例子：

`pipeline load` 中会显式执行：

```python
loader_cfg["metadata_config_file"] = str(_resolve(config, project_root))
```

也就是说：

1. `pipeline load --config xxx.yaml` 的优先级高于 `loader_config.yaml` 内部的 `metadata_config_file`
2. 这是**运行时显式覆盖**

这是合理的，但必须在文档中明确。

### 5.3 `sql_rag.yaml` 的优先级

默认优先级：

1. 先读取 `sql_rag.yaml`
2. 再通过其中的 `metadata_config_file` 读取 `metadata_config.yaml`
3. 部分 CLI 参数可覆盖 `sql_rag.yaml` 内部参数

例如：

1. `sql-rag validate --input` 覆盖默认输入文件
2. `sql-rag validate --enable_sql_repair` 覆盖 `validation.enable_sql_repair`
3. `sql-rag load --input` 覆盖 `loader_config.yaml` 内 SQL 输入路径
4. `sql-rag run-all` 会在内存中把 `ldr_cfg["sql_loader"]["input_file"]` 注入为刚生成的文件

结论：`sql_rag.yaml` 本身不是“会被其他 YAML 覆盖”，而是 CLI 运行时会对其关键字段做显式覆盖。

### 5.4 `logging.yaml` 的优先级

CLI 启动时走的是：

1. `--log-config` 指定的日志配置
2. 否则默认 `configs/logging.yaml`

因此 `metadata_config.yaml` 中的 `logging` 段不参与主 CLI 日志系统初始化。

### 5.5 `config.yaml` 的优先级

这是当前最容易误判的地方。

`ConfigLoader()` 在**未传路径**时，默认读取：

```python
configs/config.yaml
```

因此凡是调用 `get_config()` 的代码，都会读 `config.yaml`，而不是 `metadata_config.yaml`。

这会产生两类结果：

1. 你以为系统完全由 `metadata_config.yaml` 驱动
2. 实际上有一部分底层行为还在被 `config.yaml` 控制

---

## 6. 是否存在重复定义或隐式覆盖

### 6.1 不存在 YAML 级别 merge

如前所述，没有 YAML anchor / alias / `<<:`，因此不存在 YAML 层面的直接叠加。

### 6.2 存在字段级重复定义

### 6.2.1 关系评分权重重复定义

`metadata_config.yaml` 中同时存在：

1. `relationships.weights`
2. 顶层 `weights`

而 `RelationshipDiscoveryPipeline` 的逻辑是：

1. 先读取 `relationships`
2. 再把顶层 `single_column`、`composite`、`decision`、`weights` 补进 `rel_config`
3. 仅当 `relationships` 内没有对应键时，才使用顶层键

因此当前实际生效优先级是：

```text
relationships.weights > top-level weights
```

当前两份值一致，所以运行上没有错误；但维护上属于重复定义，后续极易漂移。

### 6.2.2 日志配置重复表达

当前仓库内同时存在：

1. `configs/logging.yaml`
2. `configs/metadata_config.yaml` 中的 `logging`

但真正生效的是前者。

结论：这不是“双配置协同”，而是“一个生效、一个近似死配置”。

### 6.3 存在运行时显式覆盖

### 6.3.1 `pipeline load` 覆盖 `metadata_config_file`

`pipeline load` 会在运行时修改 `loader_cfg["metadata_config_file"]`，确保 CLI `--config` 优先。

这是合理覆盖。

### 6.3.2 `sql-rag run-all` 与 `sql-rag load` 覆盖 `sql_loader.input_file`

`sql-rag run-all` 会把刚生成的 `qs_{db}_pair.json` 直接注入 loader 配置。  
`sql-rag load --input` 也会覆盖输入文件。

这也是合理覆盖。

### 6.4 存在隐式全局回退

### 6.4.1 CQL Loader 读取 `config.yaml`

`loader_config.yaml` 中：

```yaml
cql_loader:
  neo4j:
    use_global_config: true
```

而 `CQLLoader` 的实现是：

1. 若 `use_global_config=true`
2. 则调用 `get_config()`
3. 默认读取 `configs/config.yaml`

也就是说 CQL 落库的 Neo4j 连接信息来自 `config.yaml`，不是 `metadata_config.yaml`。

### 6.4.2 `PGConnectionManager` 仍读取 `config.yaml`

即使外层把 `metadata_config["database"]` 传给了 `PGConnectionManager`，它在 `initialize()` 时仍会再次读取：

```python
get_config().get("vector_database", {})
```

这意味着：

1. PostgreSQL 连接参数取自传入配置
2. 但是否按 `pgvector` 方式初始化，却取决于 `config.yaml`

这是一种隐式跨配置耦合。

---

## 7. 各配置文件的合理性评估

### 7.1 `metadata_config.yaml`

#### 7.1.1 合理的部分

1. `pool_min_size=1`、`pool_max_size=5` 对默认 `max-workers=4` 的元数据流程较稳妥
2. `sampling.sample_size=1000` 对示例库与中小库是平衡值
3. LLM `batch_size=10`、Embedding `batch_size=10` 与当前 Qwen 限制一致
4. `vector_database.active=milvus` 与现有 loader 默认实现匹配
5. `llm_comment_generation.overwrite_existing=false` 比较保守，避免误覆盖已有注释
6. `output` 目录规划清晰，路径含义明确

#### 7.1.2 风险点

1. 默认数据库名是 `your_database`，与仓库里其他现成配置不一致
2. `logging` 段基本不生效，容易误导
3. `relationships.weights` 与顶层 `weights` 重复
4. 注释中仍存在少量“已废弃但保留”的字段，配置认知成本较高

#### 7.1.3 结论

这是当前最合理的一份配置，但内部仍有历史遗留冗余。

### 7.2 `loader_config.yaml`

#### 7.2.1 合理的部分

1. 用 `metadata_config_file` 统一回读 Embedding/Milvus/数据库主配置，这一思路是对的
2. `dim_loader.options.batch_size=100`、`table_schema_loader.options.batch_size=50` 属于稳健默认值
3. 各 loader 职责分区清晰

#### 7.2.2 风险点

1. `cql_loader.neo4j.use_global_config=true` 将配置源切回 `config.yaml`
2. `sql_loader.input_file` 固定为 `output/sql/qs_dvdrental_pair.json`，对其他库不通用
3. `table_schema_loader.json_llm_directory` 命名滞后于实际实现，实际默认读的是 `output/json`
4. 部分注释还写着“未来实现”，但代码已存在实现，文档状态滞后

#### 7.2.3 结论

结构合理，但仍带着样例环境绑定和历史兼容痕迹。

### 7.3 `sql_rag.yaml`

#### 7.3.1 合理的部分

1. `metadata_config_file` 设计合理
2. 生成参数与校验参数分离清楚
3. `sql_validation_readonly=true` 安全性好
4. `enable_sql_repair=true` 与当前 pipeline 目标一致

#### 7.3.2 风险点

1. 依赖 `db_domains.yaml` 与 `output/md` 的内容质量
2. `questions_per_domain=10` 对大库可能偏少，对小库可能偏多，需要按场景调整
3. 若用户不了解 CLI 覆盖行为，可能误以为 loader 的输入文件完全由 YAML 决定

#### 7.3.3 结论

作为引用型配置是合理的，问题不大。

### 7.4 `db_domains.yaml`

#### 7.4.1 合理的部分

1. `database.name`、`database.description`、`domains[]` 结构清晰
2. 表名使用 `db.schema.table` 三段式格式，利于后续统一匹配
3. `_未分类_` 作为保底域很合理

#### 7.4.2 风险点

1. 是自动生成文件，但同时承担人工维护职责
2. `write_to_yaml()` 为整体重写，不是局部 merge
3. 通过独立命令（`metadata --generate-domains`）重新生成时，人工整理过的 domain 结构会被直接覆盖；`pipeline generate` 默认会跳过已有文件，仅在指定 `--regenerate-configs` 时才会先备份再重生成，风险已有缓解

#### 7.4.3 结论

业务语义上合理，但文件治理策略必须保守。

### 7.5 `dim_tables.yaml`

#### 7.5.1 合理的部分

1. 以 `databases.{db}.tables.{schema.table}` 组织，结构清楚
2. `embedding_col` 同时支持单列、列表、逗号分隔三种格式，使用成本低

#### 7.5.2 风险点

1. 通过独立命令（`dim_config --generate`）重新生成时会整体覆盖，不保留人工编辑上下文；`pipeline generate` 默认跳过已有文件，仅在指定 `--regenerate-configs` 时才会先备份再重生成
2. `embedding_col` 是否合理高度依赖人工判断
3. 当前 `dvdrental` 示例中把 `customer`、`staff`、`actor` 等实体表也作为维表处理，适用于示例库，但不一定适合真实业务库

#### 7.5.3 结论

结构合理，但不适合作为“可随时重新生成”的文件。

### 7.6 `logging.yaml`

#### 7.6.1 合理的部分

1. step 分流设计清晰
2. console 与 file handler 组合合理
3. loader 独立写 `loader.log`，便于排查

#### 7.6.2 风险点

1. `all_filter` 目前只允许 `all` / `all_llm`，实际仅部分编排场景会命中
2. 它与 `metadata_config.yaml.logging` 存在认知冲突

#### 7.6.3 结论

是当前实际生效且相对完善的日志配置。

### 7.7 `config.yaml`

#### 7.7.1 合理的部分

1. 对历史 NL2SQL 系统仍可作为全局兼容配置
2. Neo4j 与 Milvus 配置较全

#### 7.7.2 风险点

1. 对当前 MetaWeave 主流程来说，它不是显式主配置，却仍在部分模块中起作用
2. 它与 `metadata_config.yaml` 的 `database` / `embedding` / `vector_database` 存在平行定义
3. 一旦两边不一致，运行结果将依赖调用链，而不是依赖人的预期

#### 7.7.3 结论

这是当前配置体系最大的长期维护风险。

---

## 8. 当前最值得关注的 6 个问题

### 8.1 高优先级

#### 问题 1：`config.yaml` 与 `metadata_config.yaml` 双主配置并存

影响：

1. Neo4j 加载与部分数据库初始化逻辑不受 `metadata_config.yaml` 完全控制
2. 配置修改后容易“改错文件”

建议：

1. 明确规定 MetaWeave 主流程只允许一个主配置
2. 让 `CQLLoader`、`PGConnectionManager` 支持显式接收配置，不再隐式 `get_config()`

#### 问题 2：`metadata_config.yaml` 内部存在重复权重定义

影响：

1. 容易引发维护漂移
2. 用户不清楚究竟哪一份生效

建议：

1. 保留 `relationships.weights`
2. 删除顶层 `weights`

#### 问题 3：`metadata_config.yaml.logging` 是伪配置

影响：

1. 使用者会误以为改这里能控制日志
2. 实际行为与预期不一致

建议：

1. 删除该段
2. 或明确标注“仅保留兼容，不生效”

### 8.2 中优先级

#### 问题 4：`loader_config.yaml` 中 SQL 文件路径写死为 `dvdrental`

影响：

1. 换库即失效
2. 样例配置过度绑定当前演示环境

建议：

1. 改为占位说明
2. 或默认留空，由 `sql-rag run-all` / `sql-rag load --input` 注入

#### 问题 5：`db_domains.yaml` 与 `dim_tables.yaml` 缺少“人工维护保护”说明

影响：

1. 误操作时容易覆盖人工编辑内容

建议：

1. 在文档中明确写明“配置型产物，默认只生成一次”
2. 重新生成必须备份

#### 问题 6：命名与注释存在历史残留

典型例子：

1. `json_llm_directory` 实际默认指向 `output/json`
2. 注释中“未来实现”与实际代码状态不一致

建议：

1. 统一命名
2. 及时删除过时注释

---

## 9. 推荐的配置收敛方案

### 9.1 目标结构

建议将配置体系收敛为四类：

1. 主运行配置：`metadata_config.yaml`
2. 编排/加载入口配置：`loader_config.yaml`、`sql_rag.yaml`
3. 业务配置型产物：`db_domains.yaml`、`dim_tables.yaml`
4. 独立技术配置：`logging.yaml`

`config.yaml` 应逐步退出 MetaWeave 主链路，只保留给历史 NL2SQL 模块使用。

### 9.2 推荐优先级模型

配置生效过程分为两个独立阶段：

#### 文件选择优先级

决定”最终加载哪个 YAML 文件”：

```text
CLI 参数（如 --config xxx.yaml）
> 引用型 YAML 中的 metadata_config_file 字段
> 代码默认路径（如 configs/metadata_config.yaml）
```

典型场景：`pipeline load --config xxx.yaml` 会用 CLI 参数覆盖 `loader_cfg[“metadata_config_file”]`，再去加载目标主配置。环境变量不参与此阶段。

#### 文件内占位符解析优先级

决定”被加载文件中 `${VAR:default}` 占位符的最终值”：

```text
进程环境变量（系统/容器注入）
> .env 文件（load_dotenv 默认 override=False，不覆盖已存在的环境变量）
> YAML 中 ${VAR:default} 的 default 部分
```

注意：环境变量只在 `ConfigLoader` 解析占位符时参与，不影响文件选择。这两个阶段是串行的、独立的。

#### 禁止再出现

```text
当前命令链路 -> 隐式回退到 config.yaml
```

### 9.3 推荐整改动作

#### 第一阶段：低风险整理

1. 删除或标注 `metadata_config.yaml.logging`
2. 删除顶层 `weights`
3. 修正文档与注释中已过时的描述
4. 将 `loader_config.yaml.sql_loader.input_file` 改成通用说明

#### 第二阶段：消除隐式主配置

1. 改造 `CQLLoader`，优先从显式配置取 Neo4j
2. 改造 `PGConnectionManager`，不要在初始化时再调用 `get_config()`
3. 将 `config.yaml` 从 MetaWeave 主链路中剥离

#### 第三阶段：完善配置治理

1. 为 `db_domains.yaml` 和 `dim_tables.yaml` 增加“生成/备份/重生成”说明
2. 明确哪些文件允许人工改，哪些只读
3. 为关键配置增加启动时的一致性检查

### 9.4 推荐验收标准

每个整改阶段完成后，至少应满足以下验收条件：

1. 启动时能打印关键配置的实际来源，例如 Neo4j、Milvus、metadata 主配置、日志配置分别来自哪个文件
2. 对同一组输入，CLI 与 pipeline 两条链路读取到的主配置路径一致
3. 当 `config.yaml` 与 `metadata_config.yaml` 存在冲突值时，系统能够明确告警，而不是静默采用其中一份
4. 重新生成 `db_domains.yaml` 与 `dim_tables.yaml` 时，CLI 明确提示是否会覆盖人工维护内容
5. 通过最小回归验证覆盖以下场景：`metadata`、`pipeline load`、`sql-rag run-all`、`dim_config --generate`

---

## 10. 最终判断

当前 `configs/` 目录下的 YAML 配置：

1. 从“能否运行”的角度看，是基本合理的
2. 从“是否清晰无歧义”的角度看，还不够理想
3. 从“是否已经形成单一事实源”的角度看，答案是否定的

最核心的问题不是参数数值本身，而是：

1. 主配置并未完全唯一
2. 少量配置项存在重复定义
3. 个别配置段看似可用，实际不生效
4. 配置型产物与人工维护文件的边界还不够清楚

如果只给一句话结论：

> 当前配置体系“可以用”，但仍带有明显历史迁移痕迹；建议在下一轮配置治理或 pipeline 稳定化里程碑中完成主配置收敛，避免 `config.yaml` 与 `metadata_config.yaml` 长期并存。

---

## 11. 附：本次审计重点涉及的代码入口

1. `services/config_loader.py`
2. `metaweave/cli/main.py`
3. `metaweave/cli/metadata_cli.py`
4. `metaweave/cli/sql_rag_cli.py`
5. `metaweave/cli/pipeline_cli.py`
6. `metaweave/core/metadata/generator.py`
7. `metaweave/core/relationships/pipeline.py`
8. `metaweave/core/loaders/cql_loader.py`
9. `metaweave/core/loaders/table_schema_loader.py`
10. `metaweave/core/loaders/dim_value_loader.py`
11. `metaweave/core/sql_rag/loader.py`
12. `metaweave/core/metadata/domain_generator.py`
13. `services/db/pg_connection.py`
14. `metaweave/utils/logger.py`
