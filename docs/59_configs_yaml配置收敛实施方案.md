# 59_configs YAML 配置收敛实施方案

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

### 3.1 目标结构

从当前 7 个 YAML 收敛到 4 个：

```text
收敛后：
configs/
├── metadata_config.yaml      ← 唯一主配置（合并 loader_config + sql_rag）
├── db_domains.yaml            ← 业务配置产物（人工维护）
├── dim_tables.yaml            ← 业务配置产物（人工维护）
└── logging.yaml               ← 独立日志配置
```

退役或降级的文件：

| 文件 | 处置 |
|------|------|
| `config.yaml` | 从 MetaWeave 主链路中完全剥离，仅保留给历史 NL2SQL 模块 |
| `loader_config.yaml` | 内容合并进 `metadata_config.yaml` 的 `loaders:` 段后废弃 |
| `sql_rag.yaml` | 内容合并进 `metadata_config.yaml` 的 `sql_rag:` 段后废弃 |

### 3.2 统一加载方式

收敛完成后（第三阶段结束），活跃配置文件只保留两种加载方式：

| 加载方式 | 适用文件 | 说明 |
|---------|---------|------|
| `ConfigLoader(path).load()` | `metadata_config.yaml` | 支持环境变量替换 |
| `yaml.safe_load()` | `logging.yaml` | 日志路径通常不需要环境变量，可保持直读 |

达成路径：

- 第二阶段消除 `get_config()` 全局单例路径，并将 `loader_config.yaml` 的直读改为 `ConfigLoader`
- 第三阶段将 `loader_config.yaml` 和 `sql_rag.yaml` 合并进 `metadata_config.yaml` 后，这两个文件的 `yaml.safe_load()` 路径随废弃而自然消除

`db_domains.yaml` 和 `dim_tables.yaml` 不在本次收敛范围内，其加载方式和相关代码保持不变。

### 3.3 优先级模型

配置生效过程分为两个独立阶段，不应混为一谈。

#### 阶段一：文件选择优先级

决定"最终加载哪个 YAML 文件"：

```text
CLI 参数（如 --config xxx.yaml）
> 引用型配置中的 metadata_config_file 字段（收敛后将消除）
> 代码默认路径（如 configs/metadata_config.yaml）
```

典型场景：`pipeline load --config xxx.yaml` 会在运行时用 CLI 参数覆盖 `loader_cfg["metadata_config_file"]`，再去加载目标主配置。环境变量不参与此阶段。

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

#### 禁止出现的模式

```text
× 任何模块通过 get_config() 隐式回退到 config.yaml
× 同一配置项在多个文件中定义
× 对同一文件使用不同加载方式（一处走 ConfigLoader，另一处走 yaml.safe_load）
```

---

## 4. metadata_config.yaml 合并后的结构

合并 `loader_config.yaml` 和 `sql_rag.yaml` 后，`metadata_config.yaml` 新增以下段：

```yaml
# ============================================================
# 新增段：数据加载配置（原 loader_config.yaml）
# ============================================================
loaders:
  cql_loader:
    input_file: "output/cql/import_all.*.cypher"
    neo4j:
      uri: "${NEO4J_URI:bolt://localhost:7687}"
      user: "${NEO4J_USER:neo4j}"
      password: "${NEO4J_PASSWORD:}"
      database: "${NEO4J_DATABASE:neo4j}"

  dim_loader:
    config_file: "configs/dim_tables.yaml"
    collection_name: "dim_value_embeddings"
    options:
      batch_size: 100

  table_schema_loader:
    md_directory: "output/md"
    json_llm_directory: "output/json"
    collection_name: "table_schema_embeddings"
    options:
      batch_size: 50

  sql_loader:
    collection_name: "sql_example_embeddings"
    options:
      batch_size: 50

# ============================================================
# 新增段：SQL RAG 配置（原 sql_rag.yaml）
# ============================================================
sql_rag:
  generation:
    questions_per_domain: 10
    llm_timeout: 120
    db_domains_file: "configs/db_domains.yaml"
    md_directory: "output/md"

  validation:
    sql_validation_max_concurrent: 5
    timeout: 30
    sql_validation_readonly: true
    enable_sql_repair: true
    sql_validation_max_retries: 2
```

关键变化：

1. `loader_config.yaml` 的 `metadata_config_file` 字段不再需要——因为已在同一文件中
2. `sql_rag.yaml` 的 `metadata_config_file` 字段同理消除
3. `cql_loader.neo4j` 的配置从 `config.yaml` 迁移到此处，使用环境变量占位符
4. `sql_loader.input_file` 不再硬编码，由 CLI 运行时注入

### 4.1 配置字段迁移表

合并过程中，以下字段的位置发生变化。**本次合并只做位置迁移，不做字段重命名**，字段名与当前代码保持一致。

| 旧位置（原文件.字段） | 新位置（metadata_config.yaml 内） | 字段名是否变化 | 说明 |
|----------------------|----------------------------------|--------------|------|
| `loader_config.metadata_config_file` | 消除 | - | 已在同一文件中，不再需要 |
| `sql_rag.metadata_config_file` | 消除 | - | 同上 |
| `loader_config.cql_loader.*` | `loaders.cql_loader.*` | 否 | 仅移动层级 |
| `loader_config.dim_loader.*` | `loaders.dim_loader.*` | 否 | 仅移动层级 |
| `loader_config.table_schema_loader.*` | `loaders.table_schema_loader.*` | 否 | 仅移动层级，`json_llm_directory` 保持原名 |
| `loader_config.sql_loader.*` | `loaders.sql_loader.*` | 否 | 仅移动层级 |
| `sql_rag.generation.*` | `sql_rag.generation.*` | 否 | 仅移动文件 |
| `sql_rag.validation.*` | `sql_rag.validation.*` | 否 | 仅移动文件，`sql_validation_max_concurrent` 等保持原名 |
| `config.yaml` → Neo4j 配置 | `loaders.cql_loader.neo4j` | 是（结构变化） | 从 `get_config()` 隐式读取改为显式配置段 |

注意：部分字段名存在历史遗留问题（如 `json_llm_directory` 实际指向 `output/json`、`sql_validation_max_retries` 语义上更接近 `max_repair_attempts`），但这些重命名不在本次改造范围内，应作为后续独立清理任务处理。

---

## 5. 实施阶段

> **实施提醒**：各阶段验收中的 `pytest tests/` 是全量回归门槛。实际推进时建议先跑一组不依赖数据库/LLM 的 smoke case（如 unit tests），避免环境波动拖慢阶段推进。

### 5.1 第一阶段：低风险清理

**目标**：消除 `metadata_config.yaml` 内部冗余，不改变文件数量和加载逻辑。

**改动清单**：

| 编号 | 改动 | 涉及文件 | 风险 |
|------|------|---------|------|
| 1.1 | 删除 `metadata_config.yaml` 顶层 `weights` | `metadata_config.yaml` | 低 |
| 1.2 | 删除 `metadata_config.yaml` 中的 `logging` 段 | `metadata_config.yaml` | 低 |
| 1.3 | 修正 `loader_config.yaml` 中 `json_llm_directory` 命名 | `loader_config.yaml` | 低 |
| 1.4 | 清理过时注释（"未来实现"等） | 多个 YAML | 低 |
| 1.5 | 将 `loader_config.yaml` 中 `sql_loader.input_file` 默认值改为空 | `loader_config.yaml` | 低 |

**验收**：

- 运行 `metaweave metadata --config configs/metadata_config.yaml --step ddl` 正常完成
- 运行 `metaweave metadata --config configs/metadata_config.yaml --step rel` 关系权重与改动前一致
- `pytest tests/` 全部通过

### 5.2 第二阶段：消除部分隐式主配置依赖

**目标**：

1. 消除 `PGConnectionManager` 和 `CQLGenerator` 对 `config.yaml` 的隐式依赖
2. 将 `loader_config.yaml` 的直读改为 `ConfigLoader`

说明：`CQLLoader` 对 `config.yaml` 的依赖需要 Neo4j 配置迁移到新位置后才能消除，延后到第三阶段与 `loaders:` 段合并一起完成。

**改动清单**：

| 编号 | 改动 | 涉及文件 | 风险 |
|------|------|---------|------|
| 2.1 | `PGConnectionManager.initialize()` 不再调用 `get_config()`，vector_database 配置从传入参数获取 | `pg_connection.py` | 中 |
| 2.2 | `CQLGenerator` 改用 `ConfigLoader` 加载配置 | `cql_generator/generator.py` | 低 |
| 2.3 | loader 链路入口改用 `ConfigLoader` 加载 `loader_config.yaml` | `loader_cli.py` / `pipeline_cli.py` | 低 |

**验收**：

- 在 `config.yaml` 中故意修改 `vector_database.active` 为错误值，`PGConnectionManager` 初始化行为不受影响
- 在 `loader_config.yaml` 中添加一个 `${TEST_VAR:fallback}` 占位符，设置环境变量 `TEST_VAR=overridden`，分别通过 `metaweave load` 和 `metaweave pipeline load` 两个入口验证读取到的是 `overridden` 而非 `fallback`（证明 `loader_cli.py` 和 `pipeline_cli.py` 均已走 ConfigLoader）
- `pytest tests/` 全部通过

### 5.3 第三阶段：合并引用型配置

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

| 编号 | 改动 | 涉及文件 | 风险 |
|------|------|---------|------|
| 3.1 | 在 `metadata_config.yaml` 中新增 `loaders:` 段（含 Neo4j 显式配置） | `metadata_config.yaml` | 中 |
| 3.2 | 在 `metadata_config.yaml` 中新增 `sql_rag:` 段 | `metadata_config.yaml` | 中 |
| 3.3 | `CQLLoader` 改为从传入的 config dict 读取 Neo4j 配置，不再调用 `get_config()` | `cql_loader.py` | 中 |
| 3.4 | 修改 loader CLI：从主配置切出 `loaders.<type>` 子段后传给 `LoaderFactory.create()` | `loader_cli.py`、`pipeline_cli.py` | 中 |
| 3.5 | 修改 sql-rag CLI：从主配置切出 `sql_rag` 子段传给相关模块 | `sql_rag_cli.py`、`pipeline_cli.py` | 中 |
| 3.6 | 各 Loader 类构造函数保持只接收 config dict，不感知主配置结构 | `table_schema_loader.py`、`dim_value_loader.py`、`sql_rag/loader.py` | 低 |
| 3.7 | 废弃 `loader_config.yaml`（标记 deprecated，保留文件但不再使用） | - | 低 |
| 3.8 | 废弃 `sql_rag.yaml`（标记 deprecated，保留文件但不再使用） | - | 低 |

**验收**：

- `metaweave metadata` 全流程（ddl → json → rel → cql → md）正常
- `metaweave pipeline generate` + `pipeline load` 正常
- `metaweave sql-rag run-all` 正常
- 在 `config.yaml` 中故意修改 Neo4j URI 为错误值，`pipeline load` 仍能正常连接 Neo4j（证明 CQLLoader 不再读取 `config.yaml`）
- `pytest tests/` 全部通过

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

### 6.2 一致性检查

检查规则的严格程度随阶段推进逐步升级：

| 检查项 | 触发条件 | 第一、二阶段 | 第三阶段完成后 |
|-------|---------|------------|-------------|
| `config.yaml` 被主链路读取 | 任何主链路模块调用 `get_config()` | WARN | ERROR 并终止 |
| 必需环境变量缺失 | `${VAR}` 无默认值且环境中不存在 | ERROR 并终止 | ERROR 并终止 |
| 已废弃的配置文件仍被引用 | CLI 参数指向 `loader_config.yaml` 或 `sql_rag.yaml` | 不适用（文件尚未废弃） | WARN：提示使用 `metadata_config.yaml` |

---

## 7. 收敛前后对比

### 7.1 文件数量

| | 收敛前 | 过渡期（废弃文件保留兼容读取） | 目标态（废弃文件物理删除后） |
|--|-------|------|------|
| 主配置 | 2 个（`metadata_config.yaml` + `config.yaml`） | 1 个（`metadata_config.yaml`） | 1 个 |
| 引用型配置 | 2 个（`loader_config.yaml` + `sql_rag.yaml`） | 0 个活跃，2 个标记 deprecated 仍在仓库中 | 0 个 |
| 业务产物 | 2 个 | 2 个（不变） | 2 个 |
| 技术配置 | 1 个（`logging.yaml`） | 1 个 | 1 个 |
| **活跃文件总数** | **7** | **4**（+ 2 个 deprecated） | **4** |

### 7.2 加载方式

| | 收敛前 | 过渡期（废弃文件保留兼容读取） | 目标态（废弃文件物理删除后） |
|--|-------|------|------|
| ConfigLoader + 环境变量 | 1 个文件 | 1 个文件（主配置） | 1 个文件 |
| yaml.safe_load 直读 | 3 个文件 | 3 个文件（logging、db_domains、dim_tables）+ 用户显式传入旧文件时仍可能触发 | 3 个文件（logging、db_domains、dim_tables，后两者不在本次改造范围） |
| get_config() 全局单例 | 1 个文件 | 0 个文件 | 0 个文件 |

### 7.3 配置优先级

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

### 8.2 回退策略

每个阶段完成后应创建 git tag：

```bash
git tag config-consolidation-phase-1
git tag config-consolidation-phase-2
git tag config-consolidation-phase-3
```

第二、三阶段的回退方式：

1. 通过 git tag 回退到对应阶段起点
2. `loader_config.yaml` 和 `sql_rag.yaml` 废弃后仍保留在仓库中（标记 `# DEPRECATED`），短期内可作为兼容读取的 fallback

### 8.3 兼容性考虑

对于可能使用旧配置文件的外部脚本或文档：

1. 废弃的文件保留 6 个月后再物理删除
2. 在废弃文件头部添加明确说明：

```yaml
# ============================================================
# DEPRECATED - 此文件已废弃，配置已合并至 metadata_config.yaml
# 请使用 metadata_config.yaml 中的 loaders: 段
# 此文件将在未来版本中删除
# ============================================================
```

---

## 9. 实施顺序与依赖关系

```text
第一阶段（低风险清理）
│   不依赖其他改动，可立即开始
│
├── 1.1 删除顶层 weights
├── 1.2 删除 logging 段
├── 1.3 修正命名
├── 1.4 清理注释
└── 1.5 清空 sql_loader.input_file 默认值
    │
    ▼
第二阶段（消除部分隐式主配置依赖）
│   依赖第一阶段完成
│
├── 2.1 PGConnectionManager 显式配置
├── 2.2 CQLGenerator 走 ConfigLoader
└── 2.3 loader 链路入口走 ConfigLoader  ← 阻塞 3.4
    │
    ▼
第三阶段（合并引用型配置）
│   依赖第二阶段完成
│
├── 3.1 新增 loaders: 段（含 Neo4j 配置）
├── 3.2 新增 sql_rag: 段
├── 3.3 CQLLoader 显式 Neo4j 配置     依赖 3.1
├── 3.4 修改 loader CLI               依赖 2.3
├── 3.5 修改 sql-rag CLI
├── 3.6 其他 Loader 类调整
├── 3.7 废弃 loader_config.yaml
└── 3.8 废弃 sql_rag.yaml
```

---

## 10. 附：本方案涉及的文件

### 第一阶段

- `configs/metadata_config.yaml`
- `configs/loader_config.yaml`

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

### 第三阶段附带：文档与脚本更新

以下文件可能引用旧的 `loader_config.yaml` 或 `sql_rag.yaml`，需同步检查更新：

- `README.md`（项目根目录）
- `metaweave/README.md`（包内说明，引用旧路径和旧命令示例）
- `CLAUDE.md`
- `docs/100_执行命令完整参考.md`
- `docs/` 下其他涉及 CLI 用法的文档
- `scripts/` 下引用旧配置文件的脚本
