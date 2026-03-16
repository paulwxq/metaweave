# 56_pipeline_generate_load最终规范

## 1. 目标

本文档定义统一编排命令 `pipeline generate` 与 `pipeline load` 的最终规则，用于替代“默认完整自动跑到底”的模糊方案。

本规范遵循以下原则：

1. 只支持 LLM 主链路，不再提供 `json/rel` 规则线的完整编排
2. 尽量复用现有 YAML 配置，不在 CLI 暴露过多灵活参数
3. 配置型 YAML 文件默认保守处理，避免覆盖人工维护内容
4. 生成与加载分离，避免 `dim_value` 因人工配置依赖而阻塞整条自动流程

## 2. 为什么不提供默认“完整执行”

不再提供默认的 `metaweave pipeline run` 全自动模式，原因如下：

1. `dim_value` 加载依赖 `configs/dim_tables.yaml`
2. `dim_tables.yaml` 虽然可以由系统初步生成，但其中哪些字段需要作为 `embedding_col` 进行向量化，通常需要人工确认
3. 因此“生成产物”与“将全部内容安全加载到目标库”之间天然存在人工检查断点

基于这一事实，统一编排命令只保留两类：

1. `metaweave pipeline generate`
2. `metaweave pipeline load`

## 3. 命令定义

### 3.1 generate

命令：

```bash
metaweave pipeline generate
```

职责：

1. 生成全部标准产物
2. 生成 `db_domains.yaml`
3. 生成 `dim_tables.yaml` 初稿
4. 生成 SQL RAG 样例并完成校验/修复
5. 不执行任何落库动作

### 3.2 load

命令：

```bash
metaweave pipeline load
```

职责：

1. 基于已有产物执行落库
2. 默认加载不依赖人工二次判断的内容
3. `dim_value` 作为显式可选加载阶段处理

## 4. pipeline generate 固定执行顺序

`pipeline generate` 固定按以下顺序执行：

```text
1. ddl
2. md
3. generate-domains
4. json_llm
5. dim_config --generate
6. rel_llm
7. cql
8. sql-rag generate
9. sql-rag validate/repair
```

对应说明如下。

### 4.1 ddl

生成数据库 DDL：

```text
output/ddl/*
```

### 4.2 md

基于元数据生成 Markdown 文档：

```text
output/md/*
```

### 4.3 generate-domains

强制执行 domain 配置生成，产出：

```text
configs/db_domains.yaml
```

说明：

1. `db_domains.yaml` 是后续 `rel_llm`、`cql`、`sql-rag` 的统一 domain 来源
2. 允许提供可选参数 `--description` 作为 LLM 的业务背景补充说明

### 4.4 json_llm

固定走 LLM 链路，只生成 `json_llm` 语义增强版本，不再提供 `json` 规则线作为统一流程选项。

当前项目实现中，`json_llm` 实际表现为：

1. 先跑 `json`
2. 再对 JSON 做 LLM 增强

输出目录保持与现有实现一致：

```text
output/json/*
```

### 4.5 dim_config --generate

在 `json_llm` 之后生成 `dim_tables.yaml` 初稿：

```text
configs/dim_tables.yaml
```

放在该位置的原因：

1. `dim_config` 依赖 JSON 画像结果识别维表
2. 统一流程只支持 LLM 线，因此应基于 `json_llm` 后的结果生成初稿
3. 该文件是用户后续人工维护 `embedding_col` 的基础
4. `dim_tables.yaml` 的目标路径建议统一来自 `loader_config.yaml -> dim_loader.config_file`

### 4.6 rel_llm

基于 `db_domains.yaml` 与 JSON 元数据执行 LLM 关系发现，输出：

```text
output/rel/*
```

### 4.7 cql

基于 JSON + REL 生成 Neo4j CQL：

```text
output/cql/*
```

说明：

1. 统一流程中固定使用 `cql`
2. `cql` 的输入目录是 `output.json_directory`，默认即 `output/json`
3. 在 LLM 链路下，`json_llm` 的增强结果同样写回 `output/json`
4. 因此统一流程中无需再单独暴露 `cql_llm`
5. 当前代码语义下，`cql_llm` 与 `cql` 仅保留命令名差异，不再区分独立输入目录

### 4.8 sql-rag generate

基于：

1. `db_domains.yaml`
2. `output/md/*`

生成 Question-SQL 样例：

```text
output/sql/*
```

### 4.9 sql-rag validate/repair

对生成的 SQL 样例做 EXPLAIN 校验，并按配置决定是否启用修复。

规则：

1. 默认遵循 `configs/sql_rag.yaml` 中的配置
2. 不在统一编排命令中新增单独的“是否修复”参数

第一版实现建议保持串行执行；未来如需优化，可考虑 `cql` 与 `sql-rag` 在 `rel_llm` 之后并行，但不作为本规范的首要目标。

## 5. pipeline load 固定执行顺序

`pipeline load` 固定按以下顺序执行：

```text
1. load cql
2. load table_schema
3. load sql
4. optional: load dim_value
```

### 5.1 默认加载内容

默认加载以下内容：

1. `cql`
2. `table_schema`
3. `sql`

原因：

1. 这三类内容均可基于已有产物直接加载
2. 不依赖额外人工配置确认

### 5.2 为什么不是“加载 ddl/md/json/cql/sql”

当前项目并不存在对 `ddl`、`md`、`json` 的独立 loader。

当前真实加载路径为：

1. `cql` -> 加载到 Neo4j
2. `table_schema` -> 主要读取 `output/md`，同时依赖 `output/json` 中同名 JSON 文件补充 `time_col_hint` 与 `table_category`，再加载到向量库
3. `sql` -> 加载 `output/sql` 中的样例 SQL

因此，`pipeline load` 的语义应定义为“加载已有产物到目标数据库”，而不是“逐个加载每一种文件类型”。

### 5.3 dim_value 的处理

`dim_value` 不应作为默认加载步骤。

原因：

1. 它依赖 `configs/dim_tables.yaml`
2. `dim_tables.yaml` 虽然由 `pipeline generate` 生成初稿，但其 `embedding_col` 等关键配置需要人工确认

因此，建议 `pipeline load` 增加显式参数：

```bash
metaweave pipeline load --with-dim-values
```

规则：

1. 不传该参数时，跳过 `dim_value`
2. 传入该参数时，才执行 `dim_value` 加载
3. 若 `dim_tables.yaml` 不存在或校验失败，则直接报错
4. `dim_tables.yaml` 的路径来自 `loader_config.yaml -> dim_loader.config_file`

### 5.4 load 阶段的配置来源

`pipeline load` 的配置来源建议统一为：

1. `metadata_config.yaml`
   用于数据库、向量库、embedding 等公共配置
2. `loader_config.yaml`
   用于各类 loader 的输入文件、集合名与附属路径配置

具体约束：

1. `load cql` 读取 `loader_config.yaml -> cql_loader.input_file`
2. `load table_schema` 读取 `loader_config.yaml -> table_schema_loader.*`
3. `load sql` 读取 `loader_config.yaml -> sql_loader.input_file`
4. `load dim_value` 读取 `loader_config.yaml -> dim_loader.config_file`
5. `pipeline load` 不直接依赖 `sql_rag.yaml`

## 6. 参数收敛原则

统一编排命令尽量少暴露参数，优先复用 YAML 配置。

建议保留的核心参数如下：

### 6.1 generate

建议保留：

1. `--config`
   metadata 配置文件，默认 `configs/metadata_config.yaml`
2. `--sql-rag-config`
   SQL RAG 配置文件，默认 `configs/sql_rag.yaml`
3. `--loader-config`
   loader 配置文件，默认 `configs/loader_config.yaml`；用于确定 `dim_tables.yaml` 的目标路径，并保持 `generate/load` 对该文件路径来源的一致性
4. `--domains-config`
   domain 配置文件路径，默认 `configs/db_domains.yaml`
5. `--description`
   可选，仅用于生成 `db_domains.yaml`
6. `--regenerate-configs`
   允许备份并重建配置型 YAML 文件
7. `--clean`
   清理输出目录后重新生成
8. `--debug`

### 6.2 load

建议保留：

1. `--config`
   metadata 配置文件，默认 `configs/metadata_config.yaml`
2. `--loader-config`
   loader 配置文件，默认 `configs/loader_config.yaml`
3. `--with-dim-values`
   是否加载 `dim_value`
4. `--clean`
   加载前清理目标库
5. `--debug`

说明：

1. `pipeline load` 不需要单独提供 `--sql-rag-config`
2. `load sql` 的配置来源应统一为 `loader_config.yaml`
3. `dim_tables.yaml` 的路径也应统一从 `loader_config.yaml -> dim_loader.config_file` 获取

### 6.3 load 阶段的 --clean 语义

`pipeline load --clean` 与 `pipeline generate --clean` 的作用对象不同。

规则：

1. `pipeline load --clean` 不清理本地产物目录
2. 它只作用于目标数据库或目标集合

建议约定为：

1. `load cql --clean`
   清理 Neo4j 中本次导入目标覆盖的图数据
2. `load table_schema --clean`
   清理对应的 Milvus collection
3. `load sql --clean`
   清理对应的 SQL 示例 collection
4. `load dim_value --clean`
   清理对应的 dim value collection

因此：

1. `generate --clean` 清理的是 `output/*`
2. `load --clean` 清理的是目标库或目标集合
3. 两者语义不同，文档和命令帮助中应明确区分

## 7. 配置型文件的覆盖与备份规则

以下文件定义为“配置型产物”：

1. `configs/db_domains.yaml`
2. `configs/dim_tables.yaml`

这两类文件可能被用户手工维护，因此必须保守处理。

### 7.1 默认规则

默认执行 `pipeline generate` 时：

1. 若文件不存在，则直接生成
2. 若文件已存在，则跳过生成
3. 必须在日志中明确告警“文件已存在，已跳过”

建议日志示例：

```text
[WARN] configs/db_domains.yaml 已存在，跳过生成。
[WARN] 如需备份旧文件并重新生成，请使用 --regenerate-configs。
```

```text
[WARN] configs/dim_tables.yaml 已存在，跳过生成。
[WARN] 如需备份旧文件并重新生成，请使用 --regenerate-configs。
```

### 7.2 --regenerate-configs 规则

传入：

```bash
--regenerate-configs
```

时，行为改为：

1. 如果旧文件存在，先备份
2. 再写入新的生成结果

备份文件命名规则：

```text
<原文件名>.bak_yyyyMMdd_HHmmss
```

例如：

```text
db_domains.yaml.bak_20260316_153045
dim_tables.yaml.bak_20260316_153045
```

说明：

1. 该参数同时作用于 `db_domains.yaml` 与 `dim_tables.yaml`
2. 不单独为某一个 YAML 文件提供专用刷新参数

## 8. output 目录文件的清理规则

以下目录属于普通输出产物：

1. `output/ddl/*`
2. `output/md/*`
3. `output/json/*`
4. `output/rel/*`
5. `output/cql/*`
6. `output/sql/*`

### 8.1 默认规则

默认执行 `pipeline generate` 时：

1. 不清空输出目录
2. 同名文件允许覆盖
3. 不同名历史文件保留

这与当前项目中 `metadata`、`sql-rag` 的现有 `--clean` 语义保持一致。

### 8.2 --clean 规则

传入：

```bash
--clean
```

时：

1. 先清空对应输出目录
2. 再重新生成本次产物

### 8.3 默认模式的风险提示

由于默认不清目录，可能存在历史残留文件。

因此建议日志中增加提醒：

```text
[INFO] 未启用 --clean，将覆盖同名文件，但不会删除历史产物。
[WARN] 如果本次生成范围与上次不同，目录中可能残留旧文件；如需全量重建，请使用 --clean。
```

## 9. 失败处理策略

统一编排命令采用 `fail-fast` 策略。

### 9.1 pipeline generate

规则：

1. 任一步失败，立即终止后续步骤
2. 不继续执行剩余生成步骤
3. 不自动回滚已生成产物

### 9.2 pipeline load

规则：

1. 任一 loader 失败，立即终止后续 loader
2. 不继续尝试剩余加载步骤
3. 不自动回滚已落库内容

### 9.3 断点续跑

第一版不提供专门的断点续跑机制。

用户在修复问题后可重新执行命令；由于：

1. 配置型 YAML 默认存在即跳过
2. `output/*` 默认不清目录

因此重新执行具备一定“人工续跑”效果，但这不是严格意义上的 checkpoint resume。

## 10. domain 相关规则

统一编排流程中，domain 规则如下：

1. `db_domains.yaml` 为统一事实来源
2. `pipeline generate` 必须包含 `generate-domains`
3. `rel_llm` 必须基于 `db_domains.yaml`
4. `cql` 应消费 `db_domains.yaml` 提供的 domain 信息
5. `sql-rag` 必须基于 `db_domains.yaml`

统一流程不再支持“只跑规则线的 json/rel”。

## 11. 推荐命令示例

### 11.1 生成全部产物

```bash
metaweave pipeline generate
```

### 11.2 生成全部产物并补充数据库业务说明

```bash
metaweave pipeline generate --description "这是一个零售业务数据库"
```

### 11.3 备份旧 YAML 后重建配置型文件

```bash
metaweave pipeline generate --regenerate-configs
```

### 11.4 清理输出目录后全量重建

```bash
metaweave pipeline generate --clean
```

### 11.5 加载默认内容

```bash
metaweave pipeline load
```

默认加载：

1. `cql`
2. `table_schema`
3. `sql`

### 11.6 加载默认内容并包含 dim_value

```bash
metaweave pipeline load --with-dim-values
```

## 12. 最终结论

统一编排的最终规则应为：

1. 不提供默认“自动生成并加载所有内容”的 `pipeline run`
2. 只提供 `pipeline generate` 与 `pipeline load`
3. `pipeline generate` 固定走 LLM 链路，并强制生成 `db_domains.yaml`
4. `pipeline generate` 在 `json_llm` 后生成 `dim_tables.yaml` 初稿
5. `db_domains.yaml` 与 `dim_tables.yaml` 默认存在则跳过，使用 `--regenerate-configs` 时先备份再重建
6. `output/*` 默认不清空，只有传入 `--clean` 时才清目录
7. `pipeline load` 默认不加载 `dim_value`，只有显式传参时才执行

这套规则既能覆盖主流使用场景，也能避免自动流程误覆盖人工维护配置或误触发高风险加载步骤。
