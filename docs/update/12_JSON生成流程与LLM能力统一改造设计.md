# MetaWeave JSON 生成流程与 LLM 能力统一改造设计

## 1. 文档目的

本文设计 `--step json` 与 `--step json_llm` 的统一改造方案，目标是：

1. 废除对外暴露的 `--step json_llm` 参数，只保留 `--step json`。
2. 将 DDL 和 JSON 阶段的注释 LLM 开关彻底分开。
3. 将 JSON 注释生成与 JSON 表分类设置为两个独立开关。
4. 允许 DDL 和 JSON 分别配置模型名称及模型参数。
5. 在内存中完成规则画像和可选 LLM 增强，最终只写一次 JSON 文件。
6. 保持当前 JSON 3.0 格式，本阶段只修改 `--step ddl` 和 `--step json` 及其直接依赖的配置解析代码。
7. 为 DDL 和 JSON 注释分别提供增量与覆盖模式，并对每个对象、字段独立记录生成结果。

本设计中的“统一”只指将 `json` 和 `json_llm` 两个命令入口统一为一个
`--step json`。它不表示合并 DDL 与 JSON，也不表示让两个步骤共用模型。

### 1.1 本阶段修改边界

本阶段允许修改：

- `--step ddl` 的配置读取、LLM 延迟初始化和注释生成入口；
- `--step json` 的配置读取、规则画像、可选 LLM 注释、可选 LLM 表分类和最终保存；
- metadata CLI 中 `ddl`、`json`、删除 `json_llm` 参数所必需的分支；
- DDL/JSON 直接共用的配置校验、LLM 配置解析、JSON formatter、JSON enhancer 和元数据文档校验代码；
- 仅验证上述行为的单元测试与配置文档。

本阶段不修改：

- `metadata --step standard` 的编排实现；
- `pipeline generate`、`pipeline load` 和 `metaweave/cli/pipeline_cli.py`；
- `rel`、`rel_llm`、`cql`、`cql_llm`；
- Dim Config、Domain、SQL RAG；
- Neo4j、Milvus、pgvector 及其他加载器。

这些未修改流程受到的新配置路径或统一 JSON 行为影响，只在本文和下游影响备忘录中
记录，留到相应步骤改造时处理。

这里的“不修改”仅表示不改动这些流程的源代码，不表示其运行行为不受影响。
`standard`、`pipeline generate` 和 `pipeline load` 会复用本阶段修改的生成器、增强器或
配置校验器，因此过渡期内不承诺这些组合命令可用。本阶段正式支持并验收的入口只有
独立执行的 `metadata --step ddl` 和 `metadata --step json`。

## 2. 当前实现核对结果

### 2.1 当前 `json_llm` 是外层两阶段编排

当前 `--step json_llm` 实际执行：

```text
--step json
    ↓
生成规则版 JSON 并写入 output/json
    ↓
重新读取本次生成的 JSON
    ↓
调用 LLM 完成表分类和可选注释增强
    ↓
原地覆盖同一个 JSON 文件
```

这套编排分别存在于：

- `metaweave/cli/metadata_cli.py`
- `metaweave/cli/pipeline_cli.py`

它不是一种独立的画像算法，而是“规则 JSON + LLM 增强”的组合入口。

### 2.2 当前注释配置的真实作用范围

当前配置为：

```yaml
comment_generation:
  enabled: true
  language: zh
  overwrite_existing: false
  max_columns_per_call: 120
  enable_batch_processing: true
```

各字段实际作用范围如下：

| 当前参数 | `ddl` | `json` | `json_llm` |
|---|---|---|---|
| `enabled` | 控制是否调用 LLM 补充缺失注释 | 构造阶段会读取并可能初始化 LLM，但实际 JSON 路径不生成注释 | 控制是否生成或补充 JSON 注释 |
| `language` | 未使用 | 未使用 | 使用 |
| `overwrite_existing` | 未使用；DDL 始终只补缺失注释 | 未使用 | 使用；仅影响 JSON |
| `max_columns_per_call` | 未使用 | 未使用 | 使用 |
| `enable_batch_processing` | 未使用 | 未使用 | 使用 |

因此，现有顶层 `comment_generation` 同时承载不同阶段、不同语义的配置，容易误导使用者。

### 2.3 当前注释覆盖边界

`json_llm` 不会修改 `output/ddl/*.sql`：

- 它从 DDL 文件读取已有注释；
- `overwrite_existing: false` 时只补充 JSON 中的空注释；
- `overwrite_existing: true` 时只覆盖 JSON 中的注释；
- 覆盖时直接替换，不保留原注释审计；
- 无论开关如何，都不会把 JSON 注释反向写回 DDL 文件或数据库。

DDL 的注释生成器当前只补充缺失注释（增量模式），本设计为其增加覆盖模式（见 4.5）。
两种模式均不写回数据库。

### 2.4 当前表分类始终由规则开始

`json` 先通过规则生成表分类；`json_llm` 再用 LLM 结果覆盖最终分类。因此关闭
LLM 后，分类不会为空，而是保留规则结果：

- `fact`
- `dim`
- `bridge`
- 无法判断时为 `unknown`

## 3. 目标 CLI 设计

### 3.1 只保留 `--step json`

目标命令：

```bash
metaweave metadata \
  --config configs/metadata_config.yaml \
  --step json \
  --clean
```

删除 CLI 的 `json_llm` 可选值及独立执行 `step == "json_llm"` 的专用分支。
`standard` 循环内部另有一段当前不可达的 `child_step == "json_llm"` 分支，本阶段只记录，
不删除该分支，也不修改 `standard` 编排。

是否调用 LLM、调用 LLM 完成哪些任务、使用哪个模型，全部由配置决定。

### 3.2 本阶段只统一 metadata 的 JSON 入口

本阶段需要修改：

- metadata CLI 的 `--step` 可选值；
- metadata CLI 中独立 `json_llm` 分支；
- `ddl`、`json` 直接使用的清理目录映射、帮助文本、日志步骤名和测试断言。

`standard` 和 `pipeline generate` 的现有编排本阶段不修改，但其行为会被共享代码的
变化被动影响：`standard` 会调用新的 `json` 实现；`pipeline generate` 的
`_step_json_llm()` 会先调用新的 `MetadataGenerator.generate(step="json")`，随后仍会
显式调用文件级 `JsonLlmEnhancer`。当 JSON LLM 任务开启时，后者会使同一批 JSON 再次
进入增强流程，存在重复调用 LLM 和重复合并结果的风险。

因此，“不修改 pipeline 源码”不等于“pipeline 不受影响”。本阶段不保证
`standard`、`pipeline generate` 或 `pipeline load` 可用，也不得用它们验收新实现；
后续改造相应编排时，应删除旧的 `json_llm` 两阶段调用，统一只调用新的 `json` 实现。

## 4. 目标配置设计

### 4.1 完整建议配置

```yaml
# 全局默认模型；步骤没有专属覆盖时继承这里
llm:
  active: qwen
  providers:
    qwen:
      model: qwen-plus
      temperature: 0.1
      timeout: 120

# DDL 阶段配置
ddl_generation:
  comments:
    llm_enabled: true
    overwrite: false   # false=增量(仅补缺失注释);true=覆盖(LLM 全量刷新)

  # DDL 阶段专属模型覆盖
  llm:
    providers:
      qwen:
        model: qwen-plus

# JSON 阶段配置
json_generation:
  comments:
    llm_enabled: true
    language: zh
    overwrite: false
    max_columns_per_call: 120
    enable_batch_processing: true

  table_classification:
    llm_enabled: true

  # JSON 阶段专属模型覆盖
  llm:
    providers:
      qwen:
        model: qwen3-max
        temperature: 0.2
        timeout: 180
```

### 4.2 配置语义

| 配置路径 | 含义 |
|---|---|
| `ddl_generation.comments.llm_enabled` | DDL 阶段是否调用 LLM 生成或刷新表和字段注释 |
| `ddl_generation.comments.overwrite` | DDL 注释模式：`false` 增量（仅补缺失，现状行为）；`true` 覆盖（LLM 全量刷新） |
| `ddl_generation.llm` | DDL 阶段独立的模型和参数覆盖 |
| `json_generation.comments.llm_enabled` | JSON 阶段是否调用 LLM 生成或增强注释 |
| `json_generation.comments.overwrite` | 是否允许覆盖从 DDL 读取的已有 JSON 注释 |
| `json_generation.comments.language` | JSON 注释输出语言 |
| `json_generation.comments.max_columns_per_call` | 单次注释调用包含的最大字段数 |
| `json_generation.comments.enable_batch_processing` | 字段过多时是否分批调用 |
| `json_generation.table_classification.llm_enabled` | 是否调用 LLM 对表进行分类 |
| `json_generation.llm` | JSON 阶段独立的模型和参数覆盖 |

不设置 JSON LLM 总开关。注释和表分类必须可以分别启停。

#### 4.2.1 缺省值

配置项省略时使用以下缺省值：

| 配置路径 | 缺省值 |
|---|---:|
| `ddl_generation.comments.llm_enabled` | `true` |
| `json_generation.comments.llm_enabled` | `true` |
| `json_generation.table_classification.llm_enabled` | `true` |
| `ddl_generation.comments.overwrite` | `false` |
| `json_generation.comments.overwrite` | `false` |
| `json_generation.comments.language` | `zh` |
| `json_generation.comments.max_columns_per_call` | `120` |
| `json_generation.comments.enable_batch_processing` | `true` |

三个 LLM 开关缺省为 `true`，含义如下：

- DDL 保持当前 `comment_generation.enabled` 省略时启用注释 LLM 的行为。
- 统一后的 `--step json` 在没有显式开关时，默认执行注释增强和 LLM 表分类，行为对应
  以前的 `--step json_llm`，而不是以前的纯规则 `--step json`。
- 如需以前纯规则 `--step json` 的行为，必须显式设置
  `json_generation.comments.llm_enabled: false` 和
  `json_generation.table_classification.llm_enabled: false`。

缺省启用不改变延迟初始化要求。只有执行到需要调用 LLM 的任务时才初始化相应服务；
DDL 注释开关关闭时不得初始化 DDL LLM，JSON 两个开关都关闭时不得初始化 JSON LLM。

#### 4.2.2 缺失值与非法值

- 配置项未声明时，使用 4.2.1 的缺省值。
- `llm_enabled`、`overwrite` 和 `enable_batch_processing` 显式声明时必须是布尔值，
  不接受字符串形式的 `"true"` 或 `"false"`。
- `language` 未声明时使用 `zh`；显式声明非法值时直接报错，不再警告后回退。
- `max_columns_per_call` 必须是大于零的整数。
- 同一注释配置中，`overwrite: true` 要求 `llm_enabled: true`。如果
  `llm_enabled: false` 且 `overwrite: true`，属于非法配置，必须输出明确错误并以非零
  状态退出。
- 上述非法组合必须在 `--clean` 删除已有产物、连接数据库、初始化 LLM 和写入任何文件
  之前完成校验。
- 只有实际需要调用 LLM 时才校验该步骤最终合并后的模型配置；相关 LLM 任务全部关闭时，
  不应因缺少 API Key 或模型配置而失败。

### 4.3 模型解析规则

模型配置采用现有深合并语义：

1. DDL 使用 `ddl_generation.llm`；未配置时继承全局 `llm`。
2. JSON 使用 `json_generation.llm`；未配置时继承全局 `llm`。
3. DDL 和 JSON 可以使用不同 provider、model、temperature、timeout 和并发参数。
4. JSON 内部的注释增强与表分类默认共用 `json_generation.llm`。
5. 本次不增加命令行 `--model` 参数，模型继续由配置文件管理。

### 4.4 旧配置迁移

删除以下旧的顶层配置根节点：

```text
comment_generation
llm_comment_generation
json_llm
```

`llm_comment_generation` 是更早版本的废弃名称。当前 resolver 虽然已经能够检测它，
但错误提示仍要求迁移到即将废除的 `comment_generation`。本次应同时更新该规则，不再
把它当作可过渡到 `comment_generation` 的别名，而是直接提示最终的新配置路径。

替换为：

```text
comment_generation.enabled
  -> ddl_generation.comments.llm_enabled

comment_generation.language
  -> json_generation.comments.language

comment_generation.overwrite_existing
  -> json_generation.comments.overwrite

comment_generation.max_columns_per_call
  -> json_generation.comments.max_columns_per_call

comment_generation.enable_batch_processing
  -> json_generation.comments.enable_batch_processing

comment_generation.llm
  -> ddl_generation.llm

json_llm.llm
  -> json_generation.llm
```

如果旧配置使用 `llm_comment_generation`，其内部字段按照上表中
`comment_generation.*` 的同名字段直接迁移到最终位置。例如：

```text
llm_comment_generation.enabled
  -> ddl_generation.comments.llm_enabled

llm_comment_generation.llm
  -> ddl_generation.llm
```

旧配置不做静默兼容。启动预检必须按整个顶层根节点检测
`comment_generation`、`llm_comment_generation` 和 `json_llm`，不能只检测它们的
`.llm` 子项。即使旧根节点中只有 `enabled` 或 `language`，也必须明确报错并给出最终
新路径，避免配置被忽略后继续运行。其他流程对这些路径的适配不在本阶段完成。

配置迁移还必须明确提示默认行为：统一后的 `--step json` 在新开关缺失时默认启用 JSON
注释 LLM 和表分类 LLM。希望保持原来纯规则 `--step json` 行为的用户，需要在新配置中
显式关闭这两个开关。DDL 与 JSON 的注释模式缺省均为**增量模式**（`overwrite: false`），
覆盖模式需要显式开启。

### 4.5 DDL/JSON 注释双模式（增量 / 覆盖）

DDL 与 JSON 的注释生成各自支持两种模式，由 `overwrite` 开关控制（默认
`false` = 增量，即现状行为）：

| 步骤 | 增量模式（`overwrite: false`，默认） | 覆盖模式（`overwrite: true`） |
|---|---|---|
| `ddl` | 以 PostgreSQL 当前 COMMENT 为基准，仅对缺失注释的对象和字段生成注释；数据库已有注释不动 | 全部对象和字段统一用 LLM 刷新；生成成功则替换数据库原注释，生成失败则在 DDL 产物中留空 |
| `json` | 以 DDL `*.sql` 中的注释为基准，仅补充缺失的对象和字段注释；DDL 已有注释不动 | 全部对象和字段统一用 LLM 刷新；生成成功则替换 DDL 原注释，生成失败则在 JSON 产物中留空 |

补充规则：

- 增量模式下，基准产物中的全部对象和字段注释均已存在时，不产生注释调用；
- DDL 每次以 PostgreSQL 为权威输入，不读取上一次生成的 DDL 文件合并注释。数据库中仍
  缺少注释的字段在重复执行 DDL 时仍会再次调用 LLM，即使上一次 DDL 产物已生成过注释；
- JSON 每次以当前 DDL 文件为注释权威输入，不以 PostgreSQL 当前 COMMENT 覆盖 DDL 中的
  空注释。表、View 和 Materialized View 使用相同基准；
- 覆盖模式下，对象和字段全部进入注释生成任务；JSON 继续使用现有
  `max_columns_per_call` / `enable_batch_processing`，本阶段不为 DDL 新增批处理能力；
- 两种模式都**不写回数据库**（不修改 PG 的 COMMENT）；
- 覆盖模式直接替换原注释、不保留审计；成功项的 `comment_source` 标记为
  `llm_generated`，失败置空项的来源也置空，DDL 与 JSON 的内存语义一致；
- 注释结果按对象和字段分别采纳，允许部分成功；
- 增量模式下生成失败的待补注释保持为空；覆盖模式下生成失败的对象或字段注释置空，
  不保留原有 PostgreSQL/DDL 注释；
- 每个失败项均输出 WARNING 或 ERROR，步骤结束时分别汇总对象注释失败数和字段注释失败数；
- 影响范围：`pipeline generate` 的 ddl / json_llm 阶段共享同一生成器与配置，
  `overwrite` 配置对其同样生效（记入 12.7 Pipeline 影响审计）。

#### 4.5.1 缺失注释的统一定义

DDL 和 JSON 必须使用同一个注释归一化规则：

```python
normalized_comment = (comment or "").strip()
```

- `None`、空字符串、仅包含空格、换行或制表符的内容均视为缺失；
- 非空注释去除首尾空白后再参与判断和输出；
- 正文内部的正常空格必须保留，不得删除。

#### 4.5.2 `comment_source` 语义

`comment_source` 不是整张表共用的模式参数。表级注释和每个字段注释各自具有该属性，
用于记录当前注释的直接来源：

- `db`：当前步骤直接从 PostgreSQL COMMENT 读取；
- `ddl`：当前步骤直接从 DDL 文件读取；
- `llm_generated`：当前步骤成功调用 LLM 生成或刷新；
- 空字符串或省略：当前没有有效注释。

增量生成和覆盖生成都使用 `llm_generated`，不新增 `llm_overwriter`。更新模式只由配置
中的 `overwrite` 表达。DDL SQL 本身不持久化 `comment_source`；后续 JSON 从 DDL 读取
注释时，直接来源记为 `ddl`，不追溯该注释是否最初由 DDL 阶段的 LLM 生成。

#### 4.5.3 开关与单项结果决策表

DDL 和 JSON 的注释开关分别应用下表，不受另一步骤的注释开关影响：

| `llm_enabled` | `overwrite` | 配置是否有效 | 行为 |
|---:|---:|---:|---|
| `false` | `false` | 是 | 不初始化、不调用注释 LLM，原基准注释保持不变 |
| `true` | `false` | 是 | 增量模式，只提交基准中缺失的对象和字段注释 |
| `true` | `true` | 是 | 覆盖模式，提交全部对象和字段注释 |
| `false` | `true` | 否 | 在清理输出和访问外部资源前报错并退出 |

每个进入 LLM 任务的对象注释和字段注释按下表独立处理：

| 模式 | 返回有效非空注释 | 未返回、纯空白、非法或调用失败 |
|---|---|---|
| 增量 | 写入新注释，来源为 `llm_generated` | 保持空注释，来源为空，失败数加一 |
| 覆盖 | 替换原注释，来源为 `llm_generated` | 清空原注释及来源，失败数加一 |

步骤结束时的控制台和日志至少输出：

```text
LLM 对象注释：成功 N 个，失败 M 个
LLM 字段注释：成功 X 个，失败 Y 个
```

“成功”表示该项得到并采纳了有效非空 LLM 注释；“失败”表示该项已进入 LLM 任务但最终
没有得到可采纳注释。没有进入任务的已有注释不计入成功或失败。

## 5. 两个 JSON LLM 开关的组合行为

| JSON 注释 LLM | 表分类 LLM | 实际行为 |
|---|---|---|
| 关 | 关 | 完全不初始化或调用 JSON LLM；生成规则分类 JSON |
| 开 | 关 | 只在需要生成或覆盖注释时调用 LLM；分类保持规则结果 |
| 关 | 开 | 只调用 LLM 完成表分类，不生成注释 |
| 开 | 开 | 同时完成表分类和按需注释；可使用一次组合调用减少请求数 |

补充规则：

- 注释开关开启、`overwrite: false` 且全部注释已存在时，不产生注释调用。
- 如果此时分类开关也关闭，则整个 JSON 步骤不产生任何 LLM 调用。
- 注释开关开启且 `overwrite: true` 时，表和字段均进入注释生成任务。
- 分类开关关闭时，JSON 中仍输出规则分类，不输出空分类。

## 6. 规则表分类逻辑

### 6.1 规则输入

规则分类依赖：

- 字段语义角色，例如 `identifier`、`metric`、`datetime`；
- 物理外键数量；
- 物理主键和逻辑主键；
- 字段总数；
- 表名；
- 表注释。

字段语义角色本身又会受到字段名、字段类型、约束和采样统计影响，因此字段名称会
间接影响表分类。

### 6.2 判断顺序

#### 6.2.1 桥接表

当前默认条件：

- 外键字段数量不少于2；
- 总字段数不超过5；
- 指标字段数不超过1。

满足时输出 `bridge`，基础置信度为 `0.85`。

#### 6.2.2 事实表

在以下三个条件中默认至少满足两个：

1. 至少有1个指标字段；
2. 至少有2个标识字段；
3. 至少有1个时间字段。

满足后输出 `fact`。置信度从 `0.6` 开始，根据指标、标识符、时间字段、表名模式
和表注释关键词增加，最高为 `0.98`。

事实表名默认模式包括：

```text
^fact_
_fact$
^agg_
^sum_
```

表名匹配只增加 `0.05` 置信度，不能单独让一个表成为事实表。

#### 6.2.3 维度表

当前默认要求：

- 存在物理主键或逻辑主键；
- 至少存在一个标识字段；
- 指标字段数不超过0。

满足后输出 `dim`。置信度从 `0.7` 开始，根据主键、无指标字段、表名模式和表注释
关键词增加，最高为 `0.95`。

维度表名默认模式包括：

```text
^dim_
_dim$
^d_
```

表名匹配同样只增加 `0.05`，不能单独决定类型。

#### 6.2.4 未知类型

上述条件都不满足时输出：

```json
{
  "table_category": "unknown",
  "confidence": 0.5,
  "inference_basis": [],
  "classification_source": "rule"
}
```

### 6.3 当前桥接表名称规则的边界

代码虽然配置并编译了 `^bridge_` 和 `_bridge$` 模式，但当前桥接表分类分支没有使用
这些名称模式。桥接表目前只按外键、字段总数和指标字段数判断。

本次改造不顺带修改表分类算法。该问题作为后续规则分类优化项单独评估，避免将 CLI
和配置重构与分类结果变化混在同一批修改中。

## 7. 目标执行流程

```text
读取 DDL 与数据库结构
    ↓
数据库采样与字段统计
    ↓
字段语义画像
    ↓
物理约束、索引和逻辑主键处理
    ↓
规则表分类
    ↓
在内存中构造 JSON 3.0 文档
    ↓
按两个独立开关执行可选 LLM 注释与表分类
    ↓
校验最终 JSON 契约
    ↓
原子写入 output/json，一张表只落盘一次
```

规则画像与 LLM 增强仍存在必要的逻辑先后顺序，因为 LLM 输入依赖规则阶段生成的
字段画像、约束、统计和样例。需要删除的是对外的第二个命令和中间文件读写，不是
这项数据依赖。

## 8. 内部接口设计

### 8.1 JSON 构造与保存分离

当前 formatter 直接构造并保存 JSON。建议拆分为：

```python
document = formatter.build_json_document(metadata, sample_data)
formatter.save_json_document(document, output_path)
```

这样可以在两者之间插入可选 LLM 增强，而不需要先写文件再读回。

最终保存必须使用原子写入。当前 formatter 调用的通用 `save_json()` 会直接覆盖目标文件，
不满足这一要求；现有 `JsonLlmEnhancer._atomic_write_json()` 已有临时文件加
`os.replace()` 的基础实现，可以提取为共享工具后由 formatter 和 enhancer 共用。固定
实现约束如下：

- 临时文件创建在目标文件同一目录，确保替换发生在同一文件系统。
- 使用系统生成的唯一临时文件名，避免并发 worker 相互覆盖。
- 写入后执行 `flush()` 和 `os.fsync()`，再通过 `os.replace()` 替换目标文件。
- JSON 序列化、临时文件写入或替换失败时，原目标文件保持不变，并清理临时文件。
- 写入失败必须向上抛出，不使用容易被调用方忽略的布尔返回值。

### 8.2 增强器支持内存文档

将当前文件级入口调整为文档级入口：

```python
result = enhancer.enhance_document(
    document,
    comments_enabled=...,
    classification_enabled=...,
)
```

结果至少应包含：

- 增强后的文档；
- 是否实际调用 LLM；
- 注释任务是否成功；
- 分类任务是否成功；
- 对象注释成功数和失败数；
- 字段注释成功数和失败数；
- 每个失败对象或字段的名称与失败原因；
- 错误信息。

metadata CLI 的新 `json` 路径不再使用目录扫描、读取旧 JSON 和原地覆盖接口。由于
`pipeline_cli.py` 仍是旧文件级接口的调用方，本阶段暂时保留这些接口，不跨范围删除；
待 pipeline 改造后再清理。保留接口只是为了控制本阶段的源码改动范围，不代表现有
pipeline 编排与新的内存增强流程兼容。

### 8.3 四种提示词路径

增强器需要支持：

1. 注释与分类都关闭：不构造提示词。
2. 仅注释：响应不要求 `table_category`、`confidence` 和 `reason`。
3. 仅分类：响应不要求表和字段注释。
4. 注释与分类都开启：首批可以使用组合提示词，后续字段批次使用注释提示词。

第 4 种不是新增的请求形态。当前 enhancer 在存在注释任务时，已经通过组合提示词同时
请求表分类和首批注释；本次改造应尽量保持该提示词的任务结构，只补齐另外三种开关
组合所需的独立路径。

当前 `_merge_llm_result()` 无条件要求分类结果，不能直接满足“只生成注释”的组合，
必须拆分分类合并与注释合并。

### 8.4 LLM 初始化

LLM 服务必须延迟初始化：

- DDL 注释关闭时，不初始化 DDL LLM；
- JSON 两个开关都关闭时，不初始化 JSON LLM；
- JSON 注释开启但没有需要处理的注释，且分类关闭时，不初始化 JSON LLM；
- 不应仅因为构造 `MetadataGenerator` 就初始化所有步骤的 LLM。

### 8.5 并发边界

数据库对象并发继续由 `--max-workers` 控制。LLM 调用并发应使用
`json_generation.llm.langchain_config` 中的限制，不能直接把数据库 worker 数量当作
LLM 并发数量。

可以按有限批次完成“规则文档构造 → LLM 增强 → 原子保存”，避免对象数量很大时将
全部文档长期保存在内存中。

## 9. 输出与审计语义

### 9.1 分类 LLM 关闭

输出规则结果：

```json
{
  "table_category": "fact",
  "confidence": 0.85,
  "inference_basis": [
    "fact_has_metric",
    "fact_dimension_columns"
  ],
  "classification_source": "rule"
}
```

此时不得输出：

- `classification_reason`
- `rule_based_classification`

### 9.2 分类 LLM 成功

输出：

```json
{
  "table_category": "fact",
  "confidence": 0.95,
  "inference_basis": [
    "llm_inferred"
  ],
  "classification_source": "llm",
  "classification_reason": "……",
  "rule_based_classification": {
    "table_category": "unknown",
    "confidence": 0.5,
    "inference_basis": []
  }
}
```

即使 LLM 与规则分类相同，只要最终结果实际采用 LLM 判断，来源仍为 `llm`。

### 9.3 注释 LLM

- 没有实际生成或覆盖的注释保持原 `comment_source`。
- LLM 生成的注释标记为 `comment_source: "llm_generated"`。
- `overwrite: false` 时保留所有非空原注释。
- `overwrite: true` 时覆盖原注释（直接替换，不保留原注释审计）。
- 注释按对象和字段逐项合并，合法的非空结果立即作为该项的最终注释；未返回、返回空白、
  格式错误或调用失败的待处理项计为失败。
- 增量模式的失败项保持空注释；覆盖模式的失败项清空原注释，同时清空
  `comment_source`。
- DDL 和 JSON 分别汇总对象注释、字段注释的成功数与失败数，不能只按“整张表的注释
  请求是否成功”统计。
- JSON 注释变化不得修改 DDL SQL 或数据库 COMMENT。

### 9.4 LLM 失败

LLM 是可选增强，但启用后的失败必须可见，并允许其他对象或字段继续处理。本设计采用
以下固定策略，不额外增加失败策略配置：

1. 分类失败时保留规则分类及 `classification_source: "rule"`，不输出残缺的 LLM 分类字段。
2. 注释按对象和字段逐项判定。有效结果可以采纳，其他待处理项分别记录失败，不能因为
   一个字段失败而丢弃同一批次中的全部有效字段注释。
3. 增量模式的注释失败项原本就是缺失注释，失败后继续留空。
4. 覆盖模式的注释失败项必须置空，不回退到原 PostgreSQL 或 DDL 注释，以准确体现本次
   “全量刷新”没有成功完成该项。
5. 整次调用异常或响应无法解析时，该调用覆盖的全部待处理注释项均记为失败，并按对应
   模式处理为空；其他批次或对象可以继续执行。
6. 组合提示词中的分类结果和每个注释结果分别校验：分类失败不阻止有效注释被采纳，某个
   注释失败也不阻止有效分类和其他有效注释被采纳。
7. 组合提示词失败后不自动拆成分类请求和注释请求再次调用，避免隐式增加调用次数、费用
   和结果不确定性。
8. 最终产物仍必须通过 DDL/JSON 契约校验。单项注释失败表现为空注释，不允许写入空白
   字符串、非法类型或半完成审计字段。
9. 每个失败项输出 WARNING 或 ERROR，内容至少包含对象名、字段名（对象注释除外）和失败
   原因；CLI 汇总分别报告 LLM 请求、对象注释、字段注释和分类的成功数、失败数。
10. 只要用户启用了某项 LLM 能力且发生任何调用、对象注释、字段注释或分类失败，命令应
    返回非成功状态，但仍保留已经生成的可用产物，便于排查和重试。

## 10. 代码修改范围

### 10.1 配置和模型解析

- `configs/metadata_config.yaml`
  - 增加 `ddl_generation` 和 `json_generation`。
  - 删除旧的 `comment_generation` 和 `json_llm` 示例。
- `metaweave/services/llm_config_resolver.py`
  - 删除 `comment_generation.llm`、`json_llm.llm`。
  - 增加 `ddl_generation.llm`、`json_generation.llm`。
  - 扩展现有顶层废弃键预检，按整个根节点拒绝 `comment_generation`、
    `llm_comment_generation` 和 `json_llm`，而不是只检查 `*.llm`。
  - 为三个旧根节点给出直接指向 `ddl_generation`、`json_generation` 的定制迁移提示；
    不再提示把 `llm_comment_generation` 迁移到同样会被废除的 `comment_generation`。
  - 保持 Domain、SQL RAG、relationships 等其他模块的解析行为不变。
- `metaweave/core/metadata/generation_config.py`（新增）
  - 集中解析和校验 `ddl_generation`、`json_generation`。
  - 统一应用 4.2.1 的缺省值和 4.2.2 的类型、取值约束。
  - 为 DDL 和 JSON 注释配置都解析 `overwrite`，并拒绝
    `llm_enabled: false`、`overwrite: true` 的非法组合。
  - 返回规范化且不可由调用方随意改变缺省语义的配置对象，供 generator 和 enhancer
    共用，避免两处分别使用 `.get()` 形成不同默认行为。

### 10.2 DDL 生成流程

- `metaweave/core/metadata/generator.py`
  - `ddl` 改读 `ddl_generation.comments.llm_enabled`。
  - 读取并透传 `ddl_generation.comments.overwrite`。
  - 只在 DDL 注释 LLM 开启且确实进入 DDL 步骤时初始化服务。
  - 改用 `ddl_generation.llm` 解析 DDL 专属模型。
  - 以 PostgreSQL 提取出的当前注释作为 DDL 增量/覆盖输入，不读取旧 DDL 文件回填。
  - 汇总对象注释和字段注释的成功数、失败数；部分字段失败不阻止其他字段及对象继续处理。
- `metaweave/core/metadata/comment_generator.py`
  - `enrich_metadata_with_comments` 增加 `overwrite` 参数（默认 `false`，保持
    现状“只补缺失注释”行为）；
  - `overwrite: true` 时：表注释与全部字段注释进入生成任务，替换已有注释，
    `comment_source` 标记为 `llm_generated`；
  - 对 LLM 返回结果逐项校验和应用：非空结果成功，缺失、空白或非法结果失败；
  - 覆盖模式的失败项清空旧注释，增量模式的失败项保持为空；
  - 返回结构化结果，至少包含对象/字段成功数、失败数及失败明细，不能继续只返回生成数量；
  - 保持现有调用形态和提示词，本阶段不新增 DDL 字段批处理能力。
- `metaweave/core/metadata/models.py`
  - 增加可表达逐项注释结果的数据结构；
  - `GenerationResult` 增加对象注释和字段注释的成功/失败计数，供 DDL/JSON 汇总共用。

### 10.3 Metadata CLI

- `metaweave/cli/metadata_cli.py`
  - 在任何 `--clean`、数据库连接、LLM 初始化和产物写入之前构造并校验规范化生成配置；
    非法的 `overwrite`/`llm_enabled` 组合立即输出配置错误并以非零状态退出。
  - 删除 `json_llm` 的 `click.Choice` 值和专用编排分支。
  - 调整独立 `ddl`、`json` 的日志和汇总，分别显示对象注释与字段注释的成功/失败数。
  - 上一项“专用编排分支”只指独立执行的 `if step == "json_llm"` 分支。
  - `standard` 的步骤列表当前不含 `json_llm`，其循环内部的
    `elif child_step == "json_llm"` 是不可达死代码。本阶段保留并记录该分支，不删除、
    不修改 `standard` 编排；待全部单步改造完成、统一串联流程时再处理。

### 10.4 JSON 生成流程

- `metaweave/core/metadata/generator.py`
  - 读取统一的规范化生成配置，不自行重复定义 JSON 开关和缺省值。
  - 按当前步骤延迟初始化对应 LLM。
  - 在 JSON 文档保存前执行可选增强。
  - 合并规则生成与 LLM 增强结果统计。
  - 对 View/MV 使用 PostgreSQL 目录补齐字段结构时，字段注释仍严格以 DDL 解析结果为准；
    DDL 注释为空时不能用数据库 COMMENT 回填，确保三类对象使用同一 JSON 注释基准。
- `metaweave/core/metadata/formatter.py`
  - 拆分 JSON 文档构造和原子保存。
- `metaweave/utils/file_utils.py`
  - 提供 formatter 和 enhancer 共用的 JSON 原子写入函数。
  - 使用同目录唯一临时文件、`flush()`、`os.fsync()` 和 `os.replace()`；任何失败都清理
    临时文件并向上抛出。
- `metaweave/core/metadata/json_llm_enhancer.py`
  - 与 generator 共用 `generation_config.py` 返回的规范化配置。
  - 改用共享原子写入函数，替换失败时不再遗留临时文件。
  - 改为内存文档增强。
  - 支持注释和分类独立开关。
  - 拆分分类合并与注释合并。
  - 表注释和每个字段注释分别校验、采纳和统计，允许同一响应或批次部分成功；
  - 增量模式失败项保持为空，覆盖模式失败项清空原 DDL 注释及 `comment_source`；
  - 覆盖模式不再写入 `comment_original` / `comment_source_original`
    审计字段（直接替换）。
  - 本阶段保留仍被 pipeline 使用的文件扫描和原地覆盖入口。
- `metaweave/core/metadata/metadata_document.py`
  - 继续负责最终 JSON 3.0 契约校验和 LLM 白名单输入构造。

### 10.5 明确不修改的代码

- `metaweave/cli/pipeline_cli.py`；
- `metadata_cli.py` 中 `standard` 的业务编排；
- `rel` 与 `rel_llm` 算法；
- CQL 生成逻辑；
- Neo4j、Milvus 和 pgvector 加载；
- JSON 3.0 字段结构；
- 规则表分类算法和阈值；
- 桥接表名称模式未参与判断的问题；
- REST API 作业接口。

上述“不修改”是源码边界。尤其是 `pipeline_cli.py`，它仍会调用本阶段修改的
`MetadataGenerator`、`JsonLlmEnhancer` 和 LLM 配置校验器，因此运行结果可能改变。
本阶段对 pipeline 的承诺是“记录影响并延后适配”，不是“保持可用”。

## 11. 实施顺序

1. 增加新配置结构和校验，建立模型独立解析测试。
2. 增加 DDL/JSON `overwrite` 解析、非法组合预检和统一空白注释归一化。
3. 修改 DDL 注释生成器，使其支持增量/覆盖、逐项采纳、失败置空和结构化统计。
4. 为 formatter 增加“构造文档”和“保存文档”两个接口。
5. 将增强器改为支持内存文档接口、四种 JSON 开关组合和逐项注释结果。
6. 在 `MetadataGenerator` 的 JSON 流程中接入可选增强和统一统计，并修正 View/MV 注释基准。
7. 删除 metadata CLI 的 `json_llm` 参数和独立分支。
8. 更新 DDL/JSON 配置示例、帮助文本和测试。
9. 执行独立 `--step ddl`、规则 `--step json` 和 LLM `--step json` 回归。
10. 记录 standard、pipeline 和下游的待适配点、过渡期运行限制及恢复条件，不修改其代码。

## 12. 测试计划

### 12.1 配置测试

- DDL 和 JSON 使用不同模型，解析结果互不影响。
- 步骤未配置专属模型时正确继承全局配置。
- 三个 `llm_enabled` 均未声明时，缺省值都是 `true`。
- DDL 和 JSON 的 `overwrite` 未声明时均使用 `false`；`language`、
  `max_columns_per_call` 和 `enable_batch_processing` 未声明时分别使用 `zh`、`120` 和
  `true`。
- DDL 或 JSON 任一注释配置出现 `llm_enabled: false`、`overwrite: true` 时，必须在
  `--clean`、数据库连接和文件写入之前报错退出；已有输出文件保持不变。
- `comment_generation`、`llm_comment_generation` 和 `json_llm` 三个旧顶层根节点只要
  存在就明确报错，包括仅包含 `enabled`、`language` 等非 LLM 字段的情况。
- 三种旧根节点的错误信息直接给出最终的新配置路径，不把
  `llm_comment_generation` 指向已废除的 `comment_generation`。
- 非布尔 `llm_enabled`、非布尔 `overwrite`、非布尔 `enable_batch_processing`、非法语言
  和非正整数 `max_columns_per_call` 明确报错。
- 相关 LLM 开关全部关闭时，不因缺少该步骤的模型配置或 API Key 而失败。
- 其他模块的 LLM 配置解析结果保持不变。

### 12.2 DDL 测试

- `ddl_generation.comments.llm_enabled: false` 时不初始化、不调用 DDL LLM。
- `overwrite: false`（默认）时以 PostgreSQL COMMENT 为基准，只补充缺失注释，数据库
  已有注释不被覆盖。
- 增量模式重复执行时，数据库中仍缺少注释的字段会再次进入 LLM 任务；不从旧 DDL 文件
  回填上一次生成的注释。
- `overwrite: true` 时全部对象/字段注释进入刷新任务；成功项替换原注释并将内存中的
  `comment_source` 标记为 `llm_generated`，失败项注释及来源置空。
- 表注释成功、部分字段成功、部分字段缺失或返回空白时，只采纳有效结果并准确逐项统计；
  不因单个字段失败回滚其他成功字段。
- 整次字段调用失败时，该调用包含的所有待处理字段均记为失败：增量模式保持为空，覆盖
  模式清空原注释。
- 只有空格、换行或制表符的数据库注释视为缺失；非空注释去除首尾空白，保留正文内部空格。
- DDL SQL 不持久化 `comment_source`；从该 DDL 生成 JSON 时，注释的直接来源为 `ddl`。
- 覆盖模式不写回数据库：执行前后 PG 的 COMMENT 不变。
- 汇总分别显示对象注释成功/失败数和字段注释成功/失败数，每个失败项有 WARNING 或
  ERROR 日志。
- DDL 与 JSON 使用不同模型时，实际调用的模型分别正确。
- 配置改名之外，表、视图、物化视图、约束、索引和样例产物保持一致。

### 12.3 JSON 开关组合测试

- 两个 JSON 开关都关闭时，LLMService 不被初始化和调用。
- 仅注释开启时，不要求 LLM 返回分类字段，规则分类保持不变。
- 仅分类开启时，不要求 LLM 返回注释字段。
- 两项都开启时，组合调用和分批注释正确工作。
- 注释开启但没有缺失注释、覆盖关闭、分类关闭时，零 LLM 调用。
- 组合响应中的分类和每个注释分别校验：有效项被采纳，失败项按模式置空并计数。
- 组合调用整体失败时不拆分为独立请求重试；分类保留规则结果，该调用中的全部待处理
  注释按模式置空，并准确报告失败。

### 12.4 JSON 注释测试

- `overwrite: false` 严格以 DDL 注释为基准，保留有效 DDL 注释，只补空注释。
- Table、View、Materialized View 的 JSON 注释基准一致；数据库 COMMENT 不能回填 DDL 中
  缺失的 View/MV 字段注释。
- `overwrite: true` 对全部对象和字段执行刷新；成功项覆盖 DDL 注释，失败项置空，不保留
  原值及 `comment_original` / `comment_source_original`。
- 部分字段缺失、返回空白或格式非法时，其他有效字段和分类结果仍然保留。
- DDL 及 LLM 返回的注释统一执行 `strip()`；纯空白注释视为失败或缺失，正文内部空格保留。
- LLM 成功生成或覆盖的注释来源为 `llm_generated`；未实际处理的 DDL 注释来源保持 `ddl`；
  失败置空项的来源也置空。
- 汇总分别显示对象注释成功/失败数和字段注释成功/失败数，每个失败项有 WARNING 或
  ERROR 日志。
- JSON 注释增强前后，DDL SQL 文件字节完全不变。
- DDL 注释开关关闭不影响 JSON 注释开关，反之亦然。

### 12.5 JSON 分类测试

- 分类 LLM 关闭时输出规则的 `fact/dim/bridge/unknown`。
- 规则分类不输出 LLM 审计字段。
- 分类 LLM 成功时输出来源、理由和原始规则分类。
- 分类失败时保留完整规则分类，不留下不完整审计字段。
- 表名匹配只改变已成立分类的置信度，不单独决定表类型。
- 规则分类结果与本次改造前保持一致。

### 12.6 Metadata CLI 测试

- `--step json_llm` 不再是合法选项。
- `--step json` 在四种开关组合下行为正确。
- `--clean` 只清理并重建 JSON 输出。
- LLM 部分失败时汇总和退出状态准确，规则 JSON 仍可读取。
- 本阶段不把 `standard`、`pipeline generate` 和 `pipeline load` 纳入成功通过标准。

### 12.7 Pipeline 影响审计

本阶段不做“pipeline 必须成功”的冒烟验收，但必须通过代码审查或单元测试记录以下
已知影响，防止把未执行 pipeline 误写成“不受影响”：

- 配置迁移后，仍包含 `comment_generation`、`llm_comment_generation` 或 `json_llm`
  旧根节点的配置会被共享配置校验器拒绝；`pipeline generate` 和 `pipeline load` 都可能
  在启动阶段失败。
- 使用新配置时，现有 `_step_json_llm()` 会在新的 `json` 流程之后再次调用文件级
  enhancer；开启相应 LLM 任务时存在重复增强风险。
- 在后续 pipeline 适配完成前，独立的 `metadata --step ddl` 和
  `metadata --step json` 是本阶段唯一承诺可用的执行入口。

### 12.8 产物测试

- 每个对象只原子写入一次最终 JSON。
- 并发写入时临时文件名唯一；序列化、写入或 `os.replace()` 失败时原文件不变，且不残留
  临时文件。
- 全部产物通过 `MetadataDocument` 3.0 校验。
- 两个开关关闭时，除时间戳外与当前规则 `--step json` 产物一致。
- 两个开关开启时，使用固定 LLM 测试替身和固定响应，验证最终分类、逐项注释、覆盖失败
  置空、来源字段和失败统计符合本文新契约；不再要求与旧 `--step json_llm` 的审计字段
  完全一致。
- 真实 LLM 冒烟测试只验证 JSON 契约、分类枚举、来源字段、注释覆盖规则和成功/失败
  汇总，不要求 `reason`、置信度、注释文本或分类结果逐次完全相同。
- 表、视图和物化视图都覆盖。

## 13. 验收标准

完成改造后应满足：

1. CLI 只暴露 `--step json`，不存在 `--step json_llm`。
2. DDL 和 JSON 的注释开关互不影响；两者注释均支持增量 / 覆盖双模式
   （`overwrite` 开关，默认 `false` = 增量）。
3. DDL 增量模式以 PostgreSQL COMMENT 为基准；JSON 增量模式以 DDL 文件注释为基准。
4. 覆盖模式成功项替换原注释，失败项置空；允许对象和字段部分成功，不保留原注释审计。
5. `llm_enabled: false` 与 `overwrite: true` 的非法组合在清理产物及访问外部资源前报错退出。
6. JSON 注释与表分类可以独立启停。
7. 两个 JSON 开关都关闭时，不初始化、不调用任何 JSON LLM。
8. 关闭分类 LLM 时仍能得到规则分类，最差为 `unknown`，不会为空。
9. DDL 和 JSON 能分别配置模型与参数。
10. 注释统一清理首尾空白，纯空白视为缺失或失败，正文内部空格保留。
11. DDL 和 JSON 分别准确汇总对象注释、字段注释的成功数和失败数，失败项有可定位日志。
12. JSON LLM 注释不会修改 DDL SQL，DDL/JSON 注释均不会写回 PostgreSQL。
13. 规则文档和可选 LLM 增强在内存中完成，最终只写一次 JSON。
14. LLM 部分失败只产生符合契约的有效注释或空注释，不生成非法类型、纯空白值或半完成
    审计字段。
15. JSON 3.0 格式不变；范围外流程的已知被动影响已经完整记录，不以“源码未修改”推断其行为不变。
16. 本阶段没有修改 pipeline、关系发现、CQL、Dim Config、加载器及其他下游源代码。
17. 文档明确说明 pipeline 的旧配置启动失败风险、重复增强风险、过渡期可用性和后续恢复条件。
18. 三个 LLM 开关缺省为 `true`；需要纯规则 JSON 时必须显式关闭 JSON 的两个开关。
