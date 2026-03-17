# 59_configs YAML 配置收敛实施方案

> **实施状态**：全部三阶段已完成，并额外完成了 NL2SQL 残留代码清理。
> 最后更新：2026-03-17

## 1. 文档定位

本文档是 MetaWeave 配置体系收敛的完整实施方案，包含现状问题、收敛目标、改动清单与验收标准。

---

## 2. 现状问题总结

### 2.1 核心问题

当前配置体系存在以下问题，按影响程度归纳为三类：

**结构性问题**（影响整体架构）：

1. `config.yaml` 与 `metadata_config.yaml` 双主配置并存
2. `loader_config.yaml` 与 `sql_rag.yaml` 作为"引用型配置"，自身价值有限却引入了间接引用
3. 配置加载方式不统一（ConfigLoader / yaml.safe_load / get_config 三种路径并存）

**冗余问题**（影响维护成本）：

4. `metadata_config.yaml` 内部 `relationships.weights` 与顶层 `weights` 重复
5. `metadata_config.yaml.logging` 段不生效却仍保留
6. 命名与注释存在历史残留

**冗余绑定**（影响可移植性）：

7. `loader_config.yaml` 中路径写死为 `dvdrental`

### 2.2 补充问题

#### 2.2.1 加载方式不一致导致环境变量行为不可预期

当前配置文件存在三种加载方式：

| 加载方式 | 涉及文件 | 环境变量替换 |
|---------|---------|-----------|
| `ConfigLoader(path).load()` | `metadata_config.yaml` | 支持 `${VAR:default}` |
| `yaml.safe_load()` 直读 | `loader_config.yaml`、`db_domains.yaml`、`logging.yaml` | 不支持 |
| `get_config()` 全局单例 | `config.yaml` | 支持 |

后果：用户在 `.env` 中修改了 `MILVUS_HOST`，期望全系统生效，但 `loader_config.yaml` 中如果硬编码了地址，不会被替换。

#### 2.2.2 CQLGenerator 使用 yaml.safe_load 读取 metadata_config.yaml

`CQLGenerator` 不经过 `ConfigLoader`，直接 `yaml.safe_load()` 读取 `metadata_config.yaml`。如果文件中包含 `${ENV_VAR}` 占位符，CQL 生成步骤读到的是未替换的原始字符串。

#### 2.2.3 引用型配置的实际独有内容极少

| 文件 | 独有配置项 | 其余内容 |
|------|-----------|---------|
| `loader_config.yaml` | `cql_loader.input_file`、各 loader 的 `batch_size`、`collection_name` | 指向 `metadata_config.yaml` |
| `sql_rag.yaml` | `questions_per_domain`、`validation.*` 参数 | 指向 `metadata_config.yaml` |

这些独有配置完全可以作为 `metadata_config.yaml` 的子节点存在，不需要独立文件 + 间接引用。

---

## 3. 收敛目标

### 3.1 目标结构（已达成）

从当前 7 个 YAML 收敛到 4 个：

```text
收敛后：
configs/
├── metadata_config.yaml      ← 唯一主配置（已合并 loader_config + sql_rag）
├── db_domains.yaml            ← 业务配置产物（人工维护）
├── dim_tables.yaml            ← 业务配置产物（人工维护）
└── logging.yaml               ← 独立日志配置

退役文件（已改名为 .yaml_bak）：
├── config.yaml_bak            ← 原 NL2SQL 主配置（NL2SQL 已从项目拆走）
├── loader_config.yaml_bak     ← 内容已合并进 metadata_config.yaml
└── sql_rag.yaml_bak           ← 内容已合并进 metadata_config.yaml
```

| 文件 | 处置 | 说明 |
|------|------|------|
| `config.yaml` | 改名为 `.yaml_bak` | NL2SQL 已从项目拆走，`get_config()` 已删除 |
| `loader_config.yaml` | 改名为 `.yaml_bak` | 内容合并进 `metadata_config.yaml` 的 `loaders:` 段 |
| `sql_rag.yaml` | 改名为 `.yaml_bak` | 内容合并进 `metadata_config.yaml` 的 `sql_rag:` 段 |

### 3.2 统一加载方式（已达成）

收敛完成后，活跃配置文件只保留两种加载方式：

| 加载方式 | 适用文件 | 说明 |
|---------|---------|------|
| `ConfigLoader(path).load()` | `metadata_config.yaml` | 支持环境变量替换 |
| `yaml.safe_load()` | `logging.yaml` | 日志路径通常不需要环境变量，可保持直读 |

已消除的路径：

- `get_config()` 全局单例：**已删除**（不是 deprecated，是物理删除）
- `ConfigLoader(None)` 默认路径：**已改为 raise ValueError**
- `PGConnectionManager(config=None)` 回退路径：**已改为 raise ValueError**
- `Neo4jConnectionManager(config=None)` 回退路径：**已改为 raise ValueError**

`db_domains.yaml` 和 `dim_tables.yaml` 不在本次收敛范围内，其加载方式和相关代码保持不变。

### 3.3 优先级模型

配置生效过程分为两个独立阶段，不应混为一谈。

#### 阶段一：文件选择优先级

决定"最终加载哪个 YAML 文件"：

```text
CLI 参数（如 --config xxx.yaml）
> 代码默认路径（configs/metadata_config.yaml）
```

收敛后不再存在"引用型配置中的 metadata_config_file 字段"这一中间层。

#### 阶段二：文件内占位符解析优先级

决定"被加载文件中 `${VAR:default}` 占位符的最终值"：

```text
进程环境变量（系统/容器注入）
> .env 文件（load_dotenv 默认 override=False，不覆盖已存在的环境变量）
> YAML 中 ${VAR:default} 的 default 部分
```

说明：

1. 环境变量只在 `ConfigLoader` 解析 `${VAR:default}` 时参与，不影响文件选择
2. `load_dotenv(override=False)` 意味着 `.env` 不会覆盖进程中已存在的同名变量
3. `logging.yaml` 不经过 `ConfigLoader`，不参与占位符解析

#### 已消除的模式

```text
✅ 已消除：任何模块通过 get_config() 隐式回退到 config.yaml（函数已删除）
✅ 已消除：同一配置项在多个文件中定义（引用型配置已合并）
✅ 已消除：对同一文件使用不同加载方式（CQLGenerator 已改用 ConfigLoader）
```

---

## 4. metadata_config.yaml 合并后的结构

合并 `loader_config.yaml` 和 `sql_rag.yaml` 后，`metadata_config.yaml` 新增以下段：

```yaml
# ============================================================
# 数据加载配置（原 loader_config.yaml）
# ============================================================
loaders:
  cql_loader:
    input_file: "output/cql/import_all.*.cypher"
    neo4j:
      uri: "${NEO4J_URI:bolt://localhost:7687}"
      user: "${NEO4J_USER:neo4j}"
      password: "${NEO4J_PASSWORD:}"
      database: "${NEO4J_DATABASE:neo4j}"
    options:
      transaction_mode: "by_section"
      validate_after_load: true

  dim_loader:
    config_file: "configs/dim_tables.yaml"
    collection_name: "dim_value_embeddings"
    options:
      batch_size: 100

  table_schema_loader:
    md_directory: "output/md"
    json_llm_directory: "output/json"   # 字段名保持原名，实际指向 json 目录
    collection_name: "table_schema_embeddings"
    options:
      batch_size: 50

  sql_loader:
    # input_file 留空：运行时自动从 database.database + sql_rag.generation.output_dir
    # 拼出 output/sql/qs_{db_name}_pair.json；也可通过 CLI --input 显式指定
    input_file: ""
    collection_name: "sql_example_embeddings"
    options:
      batch_size: 50

# ============================================================
# SQL RAG 配置（原 sql_rag.yaml）
# ============================================================
sql_rag:
  generation:
    questions_per_domain: 10
    uncategorized_questions: 3
    skip_uncategorized: false
    output_dir: "output/sql"
    llm_timeout: 120

  validation:
    sql_validation_max_concurrent: 5
    timeout: 30
    sql_validation_readonly: true
    sql_validation_max_retries: 2
    enable_sql_repair: true
    repair_batch_size: 1
```

关键变化：

1. `loader_config.yaml` 的 `metadata_config_file` 字段不再需要——因为已在同一文件中
2. `sql_rag.yaml` 的 `metadata_config_file` 字段同理消除
3. `cql_loader.neo4j` 的配置从 `config.yaml` 迁移到此处，使用环境变量占位符
4. `sql_loader.input_file` 留空，由 CLI 运行时从 `database.database` 动态拼出路径 `output/sql/qs_{db_name}_pair.json`
5. `sql_rag.generation` 中不再包含 `db_domains_file` 和 `md_directory`——这些由 CLI 参数或 pipeline 上下文传入

### 4.1 配置字段迁移表

合并过程中，以下字段的位置发生变化。**本次合并只做位置迁移，不做字段重命名**，字段名与当前代码保持一致。

| 旧位置（原文件.字段） | 新位置（metadata_config.yaml 内） | 字段名是否变化 | 说明 |
|----------------------|----------------------------------|--------------|------|
| `loader_config.metadata_config_file` | 消除 | - | 已在同一文件中，不再需要 |
| `sql_rag.metadata_config_file` | 消除 | - | 同上 |
| `loader_config.cql_loader.*` | `loaders.cql_loader.*` | 否 | 仅移动层级 |
| `loader_config.dim_loader.*` | `loaders.dim_loader.*` | 否 | 仅移动层级 |
| `loader_config.table_schema_loader.*` | `loaders.table_schema_loader.*` | 否 | 仅移动层级，`json_llm_directory` 保持原名 |
| `loader_config.sql_loader.*` | `loaders.sql_loader.*` | 否 | 仅移动层级，`input_file` 改为运行时动态推断 |
| `sql_rag.generation.*` | `sql_rag.generation.*` | 否 | 仅移动文件 |
| `sql_rag.validation.*` | `sql_rag.validation.*` | 否 | 仅移动文件，`sql_validation_max_concurrent` 等保持原名 |
| `config.yaml` → Neo4j 配置 | `loaders.cql_loader.neo4j` | 是（结构变化） | 从 `get_config()` 隐式读取改为显式配置段 |

注意：部分字段名存在历史遗留问题（如 `json_llm_directory` 实际指向 `output/json`、`sql_validation_max_retries` 语义上更接近 `max_repair_attempts`），但这些重命名不在本次改造范围内，应作为后续独立清理任务处理。

### 4.2 sql_loader.input_file 动态推断机制

`sql_loader.input_file` 在配置中留空，由以下三个 CLI 入口在运行时自动推断：

| 入口 | 推断逻辑 |
|------|---------|
| `pipeline load` | 从 `database.database` + `sql_rag.generation.output_dir` 拼出路径 |
| `metaweave load --type sql` | 同上 |
| `sql-rag load` | 同上；也支持 `--input` 显式指定 |

推断公式：`{output_dir}/qs_{database.database}_pair.json`

示例：当 `database.database=dvdrental`、`sql_rag.generation.output_dir=output/sql` 时，推断为 `output/sql/qs_dvdrental_pair.json`。

`sql-rag run-all` 不需要推断——它直接注入上一步生成的 `gen_result.output_file`。

---

## 5. 实施阶段

> **实施提醒**：各阶段验收中的 `pytest tests/` 是全量回归门槛。实际推进时建议先跑一组不依赖数据库/LLM 的 smoke case（如 unit tests），避免环境波动拖慢阶段推进。

### 5.1 第一阶段：低风险清理 ✅ 已完成

**目标**：消除 `metadata_config.yaml` 内部冗余，不改变文件数量和加载逻辑。

**改动清单**：

| 编号 | 改动 | 涉及文件 | 风险 | 状态 |
|------|------|---------|------|------|
| 1.1 | 删除 `metadata_config.yaml` 顶层 `weights` | `metadata_config.yaml` | 低 | ✅ |
| 1.2 | 删除 `metadata_config.yaml` 中的 `logging` 段 | `metadata_config.yaml` | 低 | ✅ |
| 1.3 | 修正 `loader_config.yaml` 中 `json_llm_directory` 命名 | `loader_config.yaml` | 低 | ✅ |
| 1.4 | 清理过时注释（"未来实现"等） | 多个 YAML | 低 | ✅ |
| 1.5 | 将 `loader_config.yaml` 中 `sql_loader.input_file` 默认值改为空 | `loader_config.yaml` | 低 | ✅ |

### 5.2 第二阶段：消除隐式主配置依赖 ✅ 已完成

**目标**：

1. 消除 `PGConnectionManager` 和 `CQLGenerator` 对 `config.yaml` 的隐式依赖
2. 将 `loader_config.yaml` 的直读改为 `ConfigLoader`

**改动清单**：

| 编号 | 改动 | 涉及文件 | 风险 | 状态 |
|------|------|---------|------|------|
| 2.1 | `PGConnectionManager` 不再允许 `config=None`，改为 raise ValueError | `pg_connection.py` | 中 | ✅ |
| 2.2 | `CQLGenerator` 改用 `ConfigLoader` 加载配置 | `cql_generator/generator.py` | 低 | ✅ |
| 2.3 | loader 链路入口改用 `ConfigLoader` 加载 `loader_config.yaml` | `loader_cli.py` / `pipeline_cli.py` | 低 | ✅ |

### 5.3 第三阶段：合并引用型配置 ✅ 已完成

**目标**：

1. 将 `loader_config.yaml` 和 `sql_rag.yaml` 合并进 `metadata_config.yaml`
2. 完成 CLI 参数与帮助文案切换

**配置传递契约**：

沿用当前模式，配置切分的唯一责任点在 CLI 层：

1. CLI 从 `metadata_config.yaml` 加载完整配置
2. CLI 按 `loaders.<type>` 切出子段，组装为各 loader 所需的 config dict
3. CLI 调用 `LoaderFactory.create(type, config)` 传入子段 config
4. `LoaderFactory` 和各 Loader 构造函数不感知主配置结构，只接收自己的 config dict

`LoaderFactory.create()` 的签名不变。

**改动清单**：

| 编号 | 改动 | 涉及文件 | 风险 | 状态 |
|------|------|---------|------|------|
| 3.1 | 在 `metadata_config.yaml` 中新增 `loaders:` 段（含 Neo4j 显式配置） | `metadata_config.yaml` | 中 | ✅ |
| 3.2 | 在 `metadata_config.yaml` 中新增 `sql_rag:` 段 | `metadata_config.yaml` | 中 | ✅ |
| 3.3 | `CQLLoader` 改为从传入的 config dict 读取 Neo4j 配置，不再调用 `get_config()` | `cql_loader.py` | 中 | ✅ |
| 3.4 | 修改 loader CLI：默认配置改为 `metadata_config.yaml`，从主配置切出 `loaders` 段 | `loader_cli.py`、`pipeline_cli.py` | 中 | ✅ |
| 3.5 | 修改 sql-rag CLI：从主配置切出 `sql_rag` 段；删除 `--loader-config`、`--sql-rag-config` 参数 | `sql_rag_cli.py`、`pipeline_cli.py` | 中 | ✅ |
| 3.6 | 各 Loader 类构造函数保持只接收 config dict，不感知主配置结构 | `table_schema_loader.py`、`dim_value_loader.py`、`sql_rag/loader.py` | 低 | ✅ |
| 3.7 | `loader_config.yaml` 改名为 `.yaml_bak` | - | 低 | ✅ |
| 3.8 | `sql_rag.yaml` 改名为 `.yaml_bak` | - | 低 | ✅ |
| 3.9 | `config.yaml` 改名为 `.yaml_bak` | - | 低 | ✅ |

### 5.4 额外清理：NL2SQL 残留代码 ✅ 已完成

NL2SQL 模块已从 MetaWeave 项目拆走，以下残留代码一并清理：

| 编号 | 改动 | 涉及文件 | 说明 |
|------|------|---------|------|
| 4.1 | 删除 `get_config()` 函数 | `services/config_loader.py` | NL2SQL 全局配置单例，无引用 |
| 4.2 | 删除 `load_subgraph_config()` 函数 | `services/config_loader.py` | NL2SQL 子图配置加载，无引用 |
| 4.3 | 删除 `pg_client.py` | `services/db/pg_client.py` | NL2SQL 向量检索客户端，零引用 |
| 4.4 | 删除 `neo4j_client.py` | `services/db/neo4j_client.py` | NL2SQL 图查询客户端，零引用 |
| 4.5 | `ConfigLoader(None)` 改为 raise ValueError | `services/config_loader.py` | 旧默认路径 `config.yaml` 已不存在 |
| 4.6 | `Neo4jConnectionManager(None)` 改为 raise ValueError | `services/db/neo4j_connection.py` | 不再允许无参回退 |
| 4.7 | `ConfigLoader._get_project_root()` 去掉 `config.yaml` 查找 | `services/config_loader.py` | 仅通过 `pyproject.toml` 定位项目根 |
| 4.8 | `sql_loader.input_file` 动态推断 | `pipeline_cli.py`、`loader_cli.py`、`sql_rag_cli.py` | 三个 CLI 入口补全推断逻辑 |
| 4.9 | 修正旧提示词 `sql_rag.yaml` → `metadata_config.yaml` | `pipeline_cli.py:458` | 错误信息指路修正 |

---

## 6. 配置来源可观测性

### 6.1 启动时配置源打印

在 `--debug` 模式下，CLI 启动时应打印关键配置的实际来源：

```text
[config] 主配置文件: configs/metadata_config.yaml (via ConfigLoader)
[config] database.host: localhost (来源: .env DB_HOST)
[config] database.password: *** (来源: .env DB_PASSWORD)
[config] neo4j.uri: bolt://localhost:7687 (来源: metadata_config.yaml 默认值)
[config] vector_database.active: milvus (来源: metadata_config.yaml)
[config] 日志配置: configs/logging.yaml (直接加载)
[config] 业务域配置: configs/db_domains.yaml
[config] 维表配置: configs/dim_tables.yaml
```

> 注意：此为规划中的可观测性增强，尚未实现。当前 `--debug` 仅控制日志级别。

### 6.2 硬失败保护

收敛完成后，旧路径的触发方式为立即报错（不是 warning）：

| 触发点 | 错误类型 | 报错信息要点 |
|-------|---------|------------|
| `ConfigLoader(None)` | `ValueError` | config_path 必须显式指定 |
| `PGConnectionManager(config=None)` | `ValueError` | 必须显式传入 database 配置字典 |
| `Neo4jConnectionManager(config=None)` | `ValueError` | 必须显式传入 neo4j 配置字典 |

---

## 7. 收敛前后对比

### 7.1 文件数量

| | 收敛前 | 收敛后（当前状态） |
|--|-------|-----------------|
| 主配置 | 2 个（`metadata_config.yaml` + `config.yaml`） | 1 个（`metadata_config.yaml`） |
| 引用型配置 | 2 个（`loader_config.yaml` + `sql_rag.yaml`） | 0 个（已合并并改名 `.yaml_bak`） |
| 业务产物 | 2 个 | 2 个（不变） |
| 技术配置 | 1 个（`logging.yaml`） | 1 个 |
| **活跃文件总数** | **7** | **4** |

### 7.2 加载方式

| | 收敛前 | 收敛后（当前状态） |
|--|-------|-----------------|
| ConfigLoader + 环境变量 | 1 个文件 | 1 个文件（主配置） |
| yaml.safe_load 直读 | 3 个文件 | 3 个文件（logging、db_domains、dim_tables） |
| get_config() 全局单例 | 1 个文件 | **已删除** |

### 7.3 NL2SQL 残留

| | 收敛前 | 收敛后（当前状态） |
|--|-------|-----------------|
| `services/db/pg_client.py` | 存在（NL2SQL 向量检索） | **已删除** |
| `services/db/neo4j_client.py` | 存在（NL2SQL 图查询） | **已删除** |
| `get_config()` / `load_subgraph_config()` | 存在（NL2SQL 配置入口） | **已删除** |
| `config=None` 回退路径 | DeprecationWarning → 尝试读取 | **raise ValueError**（硬失败） |

### 7.4 配置优先级

收敛前：文件选择和值解析混在一起，且存在 `config.yaml` 隐式回退，实际生效配置取决于调用链而非用户预期。

收敛后：文件选择和占位符解析为两个独立阶段，详见第 3.3 节。

---

## 8. 风险与回退

### 8.1 各阶段风险评估

| 阶段 | 整体风险 | 原因 |
|------|---------|------|
| 第一阶段 | **低** | 仅删除冗余，不改变运行逻辑 |
| 第二阶段 | **中** | 改变 PGConnectionManager 的配置来源，loader 链路切换 ConfigLoader |
| 第三阶段 | **中** | 合并配置文件、CQLLoader 切换 Neo4j 配置源、CLI 参数解析入口变更 |
| NL2SQL 清理 | **低** | NL2SQL 已拆走，删除的代码在 MetaWeave 中零引用 |

### 8.2 回退策略

废弃的配置文件已改名为 `.yaml_bak`（未物理删除），如需回退可直接改回原名。

---

## 9. 实施顺序与依赖关系

```text
第一阶段（低风险清理）                              ✅ 已完成
│   不依赖其他改动，可立即开始
│
├── 1.1 删除顶层 weights
├── 1.2 删除 logging 段
├── 1.3 修正命名
├── 1.4 清理注释
└── 1.5 清空 sql_loader.input_file 默认值
    │
    ▼
第二阶段（消除隐式主配置依赖）                      ✅ 已完成
│   依赖第一阶段完成
│
├── 2.1 PGConnectionManager 显式配置（改为 raise）
├── 2.2 CQLGenerator 走 ConfigLoader
└── 2.3 loader 链路入口走 ConfigLoader
    │
    ▼
第三阶段（合并引用型配置）                          ✅ 已完成
│   依赖第二阶段完成
│
├── 3.1 新增 loaders: 段（含 Neo4j 配置）
├── 3.2 新增 sql_rag: 段
├── 3.3 CQLLoader 显式 Neo4j 配置
├── 3.4 修改 loader CLI
├── 3.5 修改 sql-rag CLI
├── 3.6 其他 Loader 类调整
├── 3.7 ~ 3.9 废弃文件改名 .yaml_bak
    │
    ▼
额外清理（NL2SQL 残留代码）                         ✅ 已完成
│   NL2SQL 已从项目拆走
│
├── 4.1 ~ 4.2 删除 get_config() / load_subgraph_config()
├── 4.3 ~ 4.4 删除 pg_client.py / neo4j_client.py
├── 4.5 ~ 4.6 ConfigLoader/连接管理器 None 参数改为 raise
├── 4.7 _get_project_root() 去掉 config.yaml 查找
├── 4.8 sql_loader.input_file 动态推断
└── 4.9 旧提示词修正
```

---

## 10. 附：本方案涉及的文件

### 第一阶段

- `configs/metadata_config.yaml`
- `configs/loader_config.yaml`（已改名 `.yaml_bak`）

### 第二阶段

- `services/db/pg_connection.py`
- `metaweave/core/cql_generator/generator.py`
- `metaweave/cli/loader_cli.py`
- `metaweave/cli/pipeline_cli.py`

### 第三阶段

- `configs/metadata_config.yaml`
- `metaweave/cli/loader_cli.py`
- `metaweave/cli/pipeline_cli.py`
- `metaweave/cli/sql_rag_cli.py`
- `metaweave/core/loaders/cql_loader.py`
- `metaweave/core/loaders/table_schema_loader.py`
- `metaweave/core/loaders/dim_value_loader.py`
- `metaweave/core/sql_rag/loader.py`

### NL2SQL 清理

- `services/config_loader.py`（删除 `get_config`、`load_subgraph_config`；`ConfigLoader(None)` 改为 raise）
- `services/db/pg_connection.py`（`config=None` 改为 raise）
- `services/db/neo4j_connection.py`（`config=None` 改为 raise）
- `services/db/pg_client.py`（已删除）
- `services/db/neo4j_client.py`（已删除）
- `metaweave/cli/pipeline_cli.py`（sql_loader.input_file 动态推断 + 提示词修正）
- `metaweave/cli/loader_cli.py`（sql_loader.input_file 动态推断）
- `metaweave/cli/sql_rag_cli.py`（sql_loader.input_file 动态推断）

### 待更新的文档

- `docs/100_执行命令完整参考.md`（仍引用 `loader_config.yaml`、已删除的 CLI 参数等，需同步更新）
