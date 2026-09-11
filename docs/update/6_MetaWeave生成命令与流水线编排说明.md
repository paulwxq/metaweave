# MetaWeave 生成命令与流水线编排说明

## 1. 文档目的

本文根据当前代码梳理以下三类概念，避免把它们混为一谈：

1. `metaweave metadata --step` 支持的步骤值；
2. `metadata --step standard` 和 `pipeline generate` 的编排顺序；
3. 不属于 `--step`、但可以通过其他 CLI 入口单独执行的步骤。

代码依据主要包括：

- `metaweave/cli/main.py`
- `metaweave/cli/metadata_cli.py`
- `metaweave/cli/pipeline_cli.py`
- `metaweave/cli/dim_config_cli.py`
- `metaweave/cli/sql_rag_cli.py`
- `metaweave/core/metadata/generator.py`
- `metaweave/core/metadata/json_llm_enhancer.py`
- `metaweave/core/cql_generator/generator.py`

## 2. `metadata --step` 的全部可选值

当前 `--step` 由 `metaweave/cli/metadata_cli.py` 中的 `click.Choice` 定义，共有 9 个可选值：

```text
ddl
json
json_llm
cql
cql_llm
md
rel
rel_llm
standard
```

按照实际生成流程排列如下：


| 顺序  | `--step` 值 | 定位          | 是否调用生成式 LLM | 控制方式                                            | `metadata --step standard` | `pipeline generate`              |
| --- | ---------- | ----------- | ----------- | ----------------------------------------------- | -------------------------- | -------------------------------- |
| 1   | `ddl`      | 共用基础步骤      | 条件调用        | `comment_generation.enabled` 控制注释补全             | 第 1 步                      | 第 1 步                            |
| 2   | `md`       | 共用基础步骤      | 条件调用        | `comment_generation.enabled` 控制注释补全             | 第 2 步                      | 第 2 步                            |
| 3   | `json`     | 规则画像步骤      | 不调用         | 读取 DDL、查询数据库并执行规则画像                             | 第 3 步                      | 不是独立编排步骤；由第 4 步 `json_llm` 内部先执行 |
| 4   | `json_llm` | LLM 增强画像步骤  | 必须调用        | 表分类没有独立开关；注释补全受 `comment_generation.enabled` 控制 | 不使用                        | 第 4 步                            |
| 5   | `rel`      | 规则关系发现      | 不调用生成式 LLM  | 规则候选、数据库采样评分；字段名相似度可使用 Embedding                | 第 4 步                      | 不使用                              |
| 6   | `rel_llm`  | LLM 关系发现    | 必须调用        | 没有独立启停开关                                        | 不使用                        | 第 6 步                            |
| 7   | `cql`      | 共用 CQL 生成步骤 | 不调用         | 读取 JSON 和关系文件并生成 Cypher                         | 第 5 步                      | 第 7 步                            |
| 8   | `cql_llm`  | 历史兼容入口      | 不调用         | 与 `cql` 使用相同生成器，仅执行标签不同                         | 不使用                        | 不使用                              |
| 9   | `standard` | 规则轨道组合步骤    | 取决于各子步骤     | 子步骤各自控制                                         | 它本身就是该流程                   | 不属于 pipeline 步骤                  |




### 2.1 `json` 不直接调用 LLM

`json` 会：

1. 从 DDL 文件加载元数据；
2. 查询数据库获得真实行数；
3. 从数据库采样；
4. 生成列画像、逻辑主键和表画像；
5. 输出完整 JSON。

这段流程位于 `MetadataGenerator._process_table_from_ddl()`，没有调用注释生成器或其他生成式 LLM。JSON 中的注释可能来自此前执行 `ddl` 时生成并写入 DDL 的内容，但这不等于 `json` 自己调用了 LLM。

### 2.2 `json_llm` 内部包含一次 `json`

`json_llm` 是两阶段操作：

```text
阶段 1：执行 json，生成全量规则版 JSON
阶段 2：调用 JsonLlmEnhancer，使用 LLM 增强并原地写回 JSON
```

LLM 表分类在每张待处理表上固定执行，没有单独开关。`comment_generation.enabled` 只决定是否生成或覆盖表、字段注释，不会关闭表分类调用。

因此，`pipeline generate` 虽然将 `json_llm` 记为一个编排步骤，内部仍包含一次完整的 `json` 操作。

### 2.3 `rel` 不调用生成式 LLM，但可能调用 Embedding 服务

`rel` 使用规则生成候选关系，再访问数据库执行采样评分。它不会调用生成式 LLM。

当前配置中的名称相似度方式是：

```yaml
relationships:
  name_similarity:
    method: embedding
```

因此，当前 `rel` 运行期间可能调用 Embedding 服务计算字段名相似度。将它描述为“不调用生成式 LLM”比“完全不调用任何模型服务”更准确。

### 2.4 `cql` 是规则轨道和 LLM 轨道共用的步骤

`cql` 从统一的 `output.json_directory` 和 `output.rel_directory` 读取数据。它并不关心前置关系文件来自 `rel` 还是 `rel_llm`。

因此：

- `metadata --step standard` 在 `rel` 后执行 `cql`；
- `pipeline generate` 在 `rel_llm` 后同样执行 `cql`。

`cql_llm` 也调用相同的 `CQLGenerator`。当前主要差异是生成元数据文档中记录的步骤名称分别为 `cql` 和 `cql_llm`。`cql_llm` 没有被两个组合流程采用，可以通过 `metadata --step cql_llm` 单独执行。

## 3. 两条组合生成流程



### 3.1 规则轨道：`metadata --step standard`

```text
ddl → md → json → rel → cql
```

执行命令：

```bash
uv run metaweave metadata \
  --config configs/metadata_config.yaml \
  --step standard
```

该顺序由 `metaweave/cli/metadata_cli.py` 中的 `steps` 列表定义，共 5 步。

### 3.2 LLM 增强轨道：`pipeline generate`

```text
ddl
  → md
  → generate-domains
  → json_llm
  → dim_config
  → rel_llm
  → cql
  → sql-rag-generate
  → sql-rag-validate
```

执行命令：

```bash
uv run metaweave pipeline generate \
  --config configs/metadata_config.yaml
```

该顺序由 `metaweave/cli/pipeline_cli.py` 中的 `GENERATE_STEPS` 定义，共 9 个编排步骤。

## 4. 四个扩展步骤都可以单独执行

`generate-domains`、`dim_config`、`sql-rag-generate` 和 `sql-rag-validate` 不是 `metadata --step` 的可选值，但都有独立 CLI 入口。

需要区分以下两句话：

- “不能通过 `metadata --step` 执行”：正确；
- “只能在 `pipeline generate` 中执行”：错误。

对应关系如下：


| pipeline 内部步骤名     | 独立 CLI 入口                     | 能否单独运行 | 主要前置产物                                 |
| ------------------ | ----------------------------- | ------ | -------------------------------------- |
| `generate-domains` | `metadata --generate-domains` | 可以     | `output/md/*.md`                       |
| `dim_config`       | `dim_config --generate`       | 可以     | `output/json/*.json`                   |
| `sql-rag-generate` | `sql-rag generate`            | 可以     | `db_domains.yaml`、Markdown 元数据和关系数据    |
| `sql-rag-validate` | `sql-rag validate`            | 可以     | Question-SQL JSON 文件和目标 PostgreSQL 数据库 |




### 4.1 单独生成 Domain 配置

```bash
uv run metaweave metadata \
  --config configs/metadata_config.yaml \
  --generate-domains \
  --domains-config configs/db_domains.yaml
```

`--generate-domains` 是 `metadata` 命令的独立旗标。代码会优先处理它，生成 Domain 配置后立即返回，不会继续执行默认的 `--step standard`。

可使用以下参数补充生成上下文：

```bash
uv run metaweave metadata \
  --generate-domains \
  --description "数据库的业务背景说明" \
  --md-context-mode full
```



### 4.2 单独生成维度表配置

```bash
uv run metaweave dim_config \
  --generate \
  --config configs/metadata_config.yaml \
  --output configs/dim_tables.yaml
```

`dim_config` 是注册在 MetaWeave 主 CLI 下的顶级命令。它读取 `output.json_directory`，筛选 `table_category="dim"` 的表，生成 `dim_tables.yaml`。

生成后仍需根据实际使用需求填写各维表的 `embedding_col`。

### 4.3 单独生成 Question-SQL

```bash
uv run metaweave sql-rag generate \
  --config configs/metadata_config.yaml \
  --domains-config configs/db_domains.yaml \
  --md-dir output/md
```

`sql-rag generate` 是 `sql-rag` 命令组的独立子命令。它读取业务域配置、Markdown 表结构和关系数据，调用 LLM 生成 Question-SQL 文件。

### 4.4 单独校验 Question-SQL

```bash
uv run metaweave sql-rag validate \
  --config configs/metadata_config.yaml \
  --input output/sql/qs_<数据库名>_pair.json \
  --enable_sql_repair false
```

该命令连接 PostgreSQL，通过 `EXPLAIN` 校验 SQL。未指定 `--input` 时，会扫描 SQL RAG 输出目录：

- 只找到一个 `qs_*_pair.json` 时自动使用；
- 找不到文件时终止；
- 找到多个文件时要求使用 `--input` 明确指定。

当 `--enable_sql_repair true` 时，校验器会额外调用 LLM 尝试修复无效 SQL；关闭修复时不调用 LLM。

## 5. pipeline 步骤名与独立命令名的区别

`pipeline generate` 内部使用 `_STEP_MAP` 调用 Python 函数。这些内部名称不是直接暴露给用户的命令：

```text
pipeline 内部名            独立执行命令
------------------------------------------------------------
generate-domains      →    metadata --generate-domains
dim_config            →    dim_config --generate
sql-rag-generate      →    sql-rag generate
sql-rag-validate      →    sql-rag validate
```

当前没有类似下面这样的入口：

```bash
metaweave pipeline generate --step sql-rag-generate
```

如果只需要执行其中一个步骤，应使用右侧对应的独立命令。

## 6. 准确的整体表述

建议在其他设计文档中统一使用以下说法：

> `generate-domains`、`dim_config`、`sql-rag-generate` 和 `sql-rag-validate` 不是 `metadata --step` 的可选值，而是 `pipeline generate` 使用的扩展编排步骤。四个步骤均有对应的独立 CLI 入口：`metadata --generate-domains`、`dim_config --generate`、`sql-rag generate` 和 `sql-rag validate`，因此都可以单独执行。

