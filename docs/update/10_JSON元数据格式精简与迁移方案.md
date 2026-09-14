# MetaWeave JSON 元数据格式精简与迁移方案

## 1. 文档目标

本文规划 `output/json/*.json` 的格式精简与下游兼容改造，目标包括：

1. 删除没有实际消费价值的重复字段和派生字段。
2. 保留物理结构、语义判断和逻辑主键所需的审计证据。
3. 避免把整份持久化 JSON 直接提交给 LLM，降低 Token 消耗和无关信息干扰。
4. 为 `table`、`view`、`materialized_view` 使用统一的对象元数据格式。
5. 用新格式直接替换旧格式，并让尚未适配的下游流程明确失败，避免静默读取默认值。
6. 尽量保留现有 JSON 的主要分组和叶子字段名，减少只为命名美观而产生的迁移工作。

本文只描述规划，不表示这些改动已经实现。

本次采用单一格式替换策略：`--step json` 只生成 `metadata_version: "3.0"`
的新格式，`--step json_llm` 只读取并增强该格式。项目不提供 v2/v3 输出开关，
也不允许同一输出目录混用两套格式。旧 JSON 只用于新旧字段对照；升级后应
重新执行 `--step json --clean`，不在运行时继续生成或兼容 v2。

## 2. 当前文件和代码核对范围

本次核对了 `output/json/` 中现有的 8 个 JSON 文件，以及以下消费流程：

- `--step rel`
- `--step rel_llm`
- `--step cql` / `--step cql_llm`
- `--step json_llm`
- `dim_config --generate`
- `table_schema_loader`
- Domain 生成和 SQL RAG

当前 8 个文件已经经过 `json_llm` 原地增强，合计约 195 KB，包含 107 个字段画像。实测结果如下：

| 精简范围 | 预计减少体积 | 说明 |
|---|---:|---|
| 删除 `role_specific_info`、重复 `column_name`、`column_statistics` | 约 12.5% | 风险较低，但仍需同步调整读取器和提示词输入视图 |
| 再移除整组 `structure_flags` 和默认不需要的详细统计 | 约 43% | 需要先建立统一元数据访问器 |
| 激进删除语义证据、结构精度和审计字段 | 约 60% | 不建议，会显著削弱排错和审计能力 |

## 3. 下游字段消费结论

| 消费方 | 当前使用的 JSON 内容 |
|---|---|
| `rel` | 对象标识、字段名、字段类型、`semantic_role`、部分 `structure_flags`、物理约束、索引列、逻辑主键、`uniqueness` |
| `rel_llm` | 关系发现基础字段；LLM 提示词目前使用黑名单裁剪后的整份 JSON；LLM 返回后再使用 `semantic_role` 和字段类型过滤 |
| `cql` / `cql_llm` | 对象标识和注释、表分类、字段类型和注释、语义角色、`uniqueness/null_rate`、约束、索引列、逻辑主键 |
| `json_llm` | 表名和注释、字段类型/可空性/注释、部分统计、整组 `structure_flags`、样例数据、物理约束 |
| `table_schema_loader` | JSON 中只使用 `table_category` 和字段 `data_type`；向量化正文主要来自 MD 文件 |
| `dim_config --generate` | `table_category` 和数据库/模式/对象名 |
| Domain 生成、SQL RAG | 不读取 `output/json` |

需要特别区分两种“使用”：

- **代码直接消费**：Python 代码明确读取某个属性并参与判断或输出。
- **LLM 间接消费**：属性没有单独的 `.get()`，但因为整段 JSON 被放入提示词，仍然会影响模型判断和 Token 消耗。

因此，不能仅根据全局搜索不到属性名就直接删除字段。

## 4. 设计原则

### 4.1 保持主要命名稳定

v3 JSON 继续保留以下主要路径：

- `table_info`
- `column_profiles`
- `table_profile`
- `sample_records`
- `schema_name`、`table_name`、`table_type`
- `constraint_name`
- `source_columns`、`target_schema`、`target_table`、`target_columns`
- `is_nullable`、`column_default`
- `semantic_analysis.semantic_role`

访问器 API 可以使用更简洁的领域名称，但不应为了格式外观全面改写持久化 JSON 的叶子字段名。

### 4.2 权威事实、推导值和审计证据分开处理

- 数据库对象、字段、约束和索引属于权威事实，应保留。
- 布尔标志、字段数和比例等可推导值，优先由访问器计算。
- 会影响关系判断的语义置信度、推断依据和逻辑主键证据，应保留。
- 作业时间、模型和配置等运行级审计信息，最终应迁移到作业记录或 manifest。

## 5. 字段处理建议

### 5.1 可以删除的字段

#### 5.1.1 `column_profiles.*.role_specific_info`

建议从标准 JSON 中整体删除。

原因：

- 没有下游算法读取。
- `json_llm` 的显式输入视图不包含它。
- `rel_llm` 会在构建提示词时明确删除它。
- `primary_key_info`、`foreign_key_info`、`index_info` 与表级约束和索引重复。
- `enum_info.values` 与 `statistics.value_distribution` 重复。

当前样本中该部分约占总大小的 9.5%。如未来需要详细语义诊断，可通过调试产物或独立审计文件输出。

#### 5.1.2 列对象内部的 `column_name`

当前结构重复保存字段名：

```json
{
  "column_profiles": {
    "order_id": {
      "column_name": "order_id"
    }
  }
}
```

建议直接使用字典键作为字段名，删除内部 `column_name`。`json_llm` 等读取器应使用迭代时获得的 `col_name`。

#### 5.1.3 `table_profile.column_statistics`

该属性只是各语义角色数量的汇总，例如 `identifier_count`、`metric_count`。它可以从字段语义画像重新计算，没有程序消费者。

删除前应先将 `rel_llm` 改为字段级白名单输入，避免删除该字段时无意改变 LLM 提示词。

#### 5.1.4 `table_info.total_columns`

`total_columns` 等于 `len(column_profiles)`，建议删除并由访问器计算。对象总行数无法从 JSON 其他字段推导，因此 `table_info.total_rows` 继续保留。

#### 5.1.5 样例数据中的重复属性

当前：

```json
{
  "sample_records": {
    "sample_method": "limit",
    "sample_size": 5,
    "total_rows": 500,
    "records": []
  }
}
```

建议改为：

```json
{
  "sample_records": {
    "sample_method": "limit",
    "records": []
  }
}
```

处理原则：

- 当前 `sample_size` 是实际写入的记录数，代码取值为 `len(records)`，不是配置请求量，因此可以精确派生。
- `sample_records.total_rows` 与 `table_info.total_rows` 重复，应删除。
- `sample_method` 有审计价值，应保留，而且必须表示实际执行的方法。
- 如果要审计配置请求量，应使用语义明确的 `requested_count`，不能继续用 `sample_size` 表达。

项目中有两套不同采样，不能混为一谈：

| 采样用途 | 当前配置 | 建议保存位置 |
|---|---|---|
| 字段画像和统计 | `sampling.sample_size` | `profiling.sample_count` 保存实际参与画像的行数 |
| DDL/JSON/MD 展示样例 | `output.ddl_options.sample_records.count` | 实际条数由 `sample_records.records.length` 得到 |

两处 `sample_method` 在概念上并不重复：

- `profiling.sample_method` 表示字段画像实际使用的采样方式。
- `sample_records.sample_method` 表示展示样例实际使用的采样方式。

它们未来可以不同，因此分别保留。两套采样的配置请求量更适合记录在作业 manifest 的配置快照中，避免在每个对象 JSON 中重复。

#### 5.1.6 当前 `sampling.sample_method` 配置未实际生效

当前配置声明 `sampling.sample_method` 支持 `limit`、`tablesample`、`range`，但生成器只读取 `sampling.sample_size`，数据库连接器实际固定执行 `SELECT ... LIMIT`。

因此不能直接把配置声明值写入 `profiling.sample_method`，否则可能出现“JSON 记录 tablesample、实际执行 limit”的错误审计。

本次 JSON 格式迁移不同时引入新采样算法。建议采取以下约束：

1. 当前只接受 `limit`。
2. 用户配置 `tablesample` 或 `range` 时，在作业启动阶段明确报错，不得静默回退到 `limit`。
3. JSON 中的 `sample_method` 始终记录实际执行的方法。
4. `tablesample` 和 `range` 后续作为独立的采样算法改造，分别定义参数语义和测试基线。

切换采样方法会改变字段统计、语义角色和 `unique_column_sets`，它是算法输入变更，不是单纯的审计字段变更。`TABLESAMPLE SYSTEM` 还存在块级抽样偏差，其参数是抽样百分比，不能直接沿用 `sample_size` 的目标行数语义。因此新方法上线后，不应要求它们与 `limit` 生成的统计、逻辑主键和关系候选完全一致。

#### 5.1.7 `unique_constraints[].is_partial`

该字段不是新格式新增字段；旧模型已经定义它，抽取器目前固定写入 `false`。

建议在新格式的 `unique_constraints` 中删除它，原因是 PostgreSQL 的部分唯一性由带条件的唯一索引表达，不是 `UNIQUE` 约束的属性。应在 `indexes` 中使用以下两个事实表达：

- `is_unique: true`
- `condition` 保存部分索引谓词

旧文件中的该字段仅用于新旧格式对照，不由当前读取器接受。

### 5.2 建议通过统一访问器消除的字段

#### 5.2.1 整组 `structure_flags`

当前每个字段固定输出 11 个布尔值。现有 107 个字段共写入 1177 个布尔值，其中 1056 个为 `false`，整组约占当前 JSON 总体积的 20.8%。

这些标志可以从结构和统计事实推导，但当前 profiler 的实际语义包含历史细节，不能只写成理想化映射。

##### 5.2.1.1 旧版标志语义契约

| 旧标志 | 当前精确语义 |
|---|---|
| `is_primary_key` | 字段属于主键，且主键只有一个字段 |
| `is_composite_primary_key_member` | 字段属于多字段主键 |
| `is_foreign_key` | 字段属于外键，且代码取得的第一个外键是单列外键 |
| `is_composite_foreign_key_member` | 字段属于外键，且代码取得的第一个外键是复合外键 |
| `is_unique` | `round(unique_count / sample_count, 4) == 1.0`，并且字段不属于任何唯一约束 |
| `is_composite_unique_member` | 数据唯一，并且字段属于复合唯一约束 |
| `is_unique_constraint` | 字段属于单列唯一约束 |
| `is_composite_unique_constraint_member` | 字段属于复合唯一约束 |
| `is_indexed` | 字段的索引列表非空，且按收集顺序的第一项被判断为单列索引；当前数据库抽取查询按索引名升序返回 |
| `is_composite_indexed_member` | 字段的索引列表非空，且按收集顺序的第一项被判断为复合索引；当前数据库抽取查询按索引名升序返回 |
| `is_nullable` | 等于字段结构事实 `column_profiles.*.is_nullable` |

旧实现还存在三个需要明确记录的边界：

1. `is_unique` 不是单纯的“数据唯一”，它与是否存在唯一约束组合，并使用四位小数后的精确 `== 1.0`。
2. 两个索引标志互斥且顺序敏感，无法表达“同一字段同时属于单列索引和复合索引”这一真实状态。
3. 索引映射包含约束支撑索引，PK/UK 字段可以同时被标记为主键/唯一约束和已索引。

##### 5.2.1.2 目标访问器

不应把上述历史缺陷直接固化为新领域 API。当前格式只提供语义明确的目标领域接口：

```python
document.is_single_column_primary_key(column_name)
document.is_composite_primary_key_member(column_name)
document.has_single_column_unique_constraint(column_name)
document.is_composite_unique_constraint_member(column_name)
document.is_data_unique(column_name)
document.has_single_column_index(column_name)
document.is_composite_index_key_member(column_name)
document.has_index_key(column_name, include_constraint_backed=True)
document.column_null_rate(column_name)
document.column_uniqueness(column_name)
```

目标语义规定：

- `is_data_unique` 使用 `round(unique_count / sample_count, 4) == 1.0`，不再与唯一约束状态混合。
- 单列索引和复合索引成员不是互斥状态；同一字段可以同时返回 `True`。
- 索引键判断默认基于完整索引集合，包含约束支撑索引，以保持当前关系发现信号。
- `INCLUDE` 列不属于索引键，不能返回已索引键或复合索引键成员。
- 表达式索引保留用于审计，但表达式本身不能伪装成普通字段参与关系候选。

新格式直接删除持久化 `structure_flags`。目标接口必须只依赖 `physical_constraints`、`indexes`、字段可空性、字段统计和画像样本数等权威事实。

##### 5.2.1.3 金样本测试边界

需要增加三类测试：

1. **消费者谓词桥接测试**：目标接口只从权威事实推导，逐列对比消费者改造前实际使用的布尔谓词，而不是笼统对比整个 `structure_flags`。
2. **旧字段拒绝测试**：当前格式混入 `structure_flags` 时明确失败。
3. **目标语义样本**：验证修正后的多索引、表达式索引和 INCLUDE 语义，不要求与旧缺陷完全一致。

桥接测试至少覆盖以下当前消费口径：

- `candidate_generator` 的目标字段物理信号：单列主键、单列唯一约束、单列索引或复合索引成员。
- `candidate_generator` 的主键和唯一约束来源判定。
- `decision_engine` 的源字段独立约束判定。
- `writer` 的 `source_constraint` 和 `target_source_type` 判定。
- `repository` 的物理唯一性判定。

例如，`candidate_generator` 当前的目标字段物理信号是四个旧标志的 OR：

```python
old_target_has_physical = (
    flags.get("is_primary_key")
    or flags.get("is_unique_constraint")
    or flags.get("is_indexed")
    or flags.get("is_composite_indexed_member")
)
```

桥接测试应将它与仅基于结构事实的新谓词比较：

```python
new_target_has_physical = (
    document.is_single_column_primary_key(column_name)
    or document.has_single_column_unique_constraint(column_name)
    or document.has_index_key(column_name, include_constraint_backed=True)
)
```

两者在普通样本上必须一致；旧标志因“首索引决定”而丢失的多索引情况，按已批准的新语义记入预期差异清单。

对不包含已批准行为修正的样本，新旧消费谓词必须逐列一致。对多索引、`INCLUDE` 和表达式索引，必须用显式的“预期差异清单”说明为何不一致。

当前 orders 测试库可以覆盖普通 PK、约束支撑索引和普通索引，但不足以覆盖全部边界。还需要专用测试表，至少包含：

- 同一字段同时处于单列索引和复合索引。
- PK/UK 约束支撑索引。
- 一个索引键加一个 `INCLUDE` 列。
- 纯表达式索引。
- 普通字段与表达式混合索引。

除明确列出的行为修正外，其余访问器结果和下游关系结果必须保持一致。

### 5.3 建议精简的统计属性

当前字段统计同时保存原始计数、比例、数值统计和字符串长度统计。

建议标准格式默认保留：

- `null_count`
- `unique_count`
- `min` / `max`，适用时保留
- `value_distribution`，只对低基数字段保留

建议将以下字段移出默认 JSON，放入可选的详细画像产物：

- `mean`
- `avg_length`
- `min_length`
- `max_length`
- `median_length`
- `length_std`

同一对象的字段统计使用同一个 DataFrame，因此 `sample_count` 可以提升为表级 `profiling.sample_count`。这里保存的是实际参与画像的行数。

统计信息不是所有字段都具备。以下情况可能缺少部分或全部统计：

- BYTEA 会跳过 `unique_count` 和 `uniqueness`。
- 空样本不会产生字段统计。
- 不支持的复杂类型可能只有部分统计。
- 单个字段统计失败时，不能阻止整个对象被读取。

因此：

- `statistics` 整体可选。
- `null_count`、`unique_count`、`min`、`max`、`value_distribution` 均为可选属性。
- `MetadataDocument` 只对对象标识、字段名和字段类型等关键结构事实进行强校验。
- 缺少统计时，关系流程应明确记录“统计未知”，不能把未知静默当成 0。

`null_rate` 和 `uniqueness` 可以由计数计算。为了保持 v2 行为，访问器应继续使用四位小数：

```python
null_rate = round(null_count / profiling_sample_count, 4)
uniqueness = round(unique_count / profiling_sample_count, 4)
```

迁移回归标准：

- 派生比例与 v2 值的绝对差不超过 `1e-4`。
- 最终候选集合和关系决策结果必须完全一致。
- 阈值边界样例必须单独测试，避免四舍五入方式变化导致候选跨过阈值。

不能采用 `null_count = null_rate × sample_count` 的反向恢复方式，因为 v2 比例已经四舍五入，不能保证精确还原。

### 5.4 建议合并的类型属性

当前字段同时保存：

- `data_type`
- `character_maximum_length`
- `numeric_precision`
- `numeric_scale`

建议改为 PostgreSQL 可读的完整类型字符串：

```json
"data_type": "character varying(100)"
```

```json
"data_type": "numeric(12,2)"
```

这样可以删除三个分散的类型修饰属性，同时让 LLM 直接看到完整类型。当前关系类型兼容模块已经会去掉括号中的精度后再比较类型，但仍需为常见 PostgreSQL 类型补充回归测试。

以下字段建议保留现有名称：

- `ordinal_position`：保证字段顺序明确，不依赖 JSON 对象顺序。
- `is_nullable`。
- `column_default`。

这些字段属于数据库结构事实，具有审计和结构重建价值。

### 5.5 必须保留的语义审计字段

建议保留当前结构和命名：

```json
"semantic_analysis": {
  "semantic_role": "identifier",
  "semantic_confidence": 0.95,
  "inference_basis": [
    "type_whitelist_passed",
    "high_uniqueness"
  ]
}
```

虽然关系算法主要读取 `semantic_role`，但它会影响逻辑主键识别和关系候选过滤。发生误判时，需要根据置信度和推断依据判断错误来自字段名称、类型、唯一性还是审计规则。

### 5.6 必须保留的对象和结构事实

以下内容不建议删除：

- `metadata_version`
- 数据库名、schema、对象名
- `table_type`，取值支持 `table`、`view`、`materialized_view`
- 对象注释及 `comment_source`
- 字段注释及 `comment_source`
- `table_info.total_rows`
- 主键、唯一约束、外键
- 外键目标、约束名、`on_delete`、`on_update`
- 索引名、索引类型、唯一性、部分索引条件、索引定义
- 逻辑主键的字段、置信度、唯一度和空值率证据

`table_info.total_columns` 不在保留清单中，由 `len(column_profiles)` 派生。

#### 5.6.1 表达式索引、部分索引和 `INCLUDE` 列

当前索引查询通过内连接 `pg_attribute` 获取 `pg_index.indkey` 中的全部属性，但没有正确处理表达式位置，也没有使用 `indnkeyatts` 区分索引键和 `INCLUDE` 列。

现有风险：

- 纯表达式索引可能被整个查询过滤掉。
- 普通字段与表达式混合索引可能只留下普通字段。
- `INCLUDE` 列可能被合并进 `columns`。
- “1 个索引键 + 1 个 INCLUDE 列”可能被误认为复合索引并进入关系发现 Stage 1 特权候选池。
- 即使 JSON 设计保留 `definition`，查询没有返回该索引时也无法完成审计。

这属于现有索引抽取和候选池污染问题，应在 v3 格式切换前作为独立修复完成，不能继续推迟。

建议保持现有索引叶子字段名，并增加：

```json
{
  "index_name": "idx_users_tenant_lower_email",
  "index_type": "btree",
  "columns": [
    "tenant_id"
  ],
  "included_columns": [
    "created_at"
  ],
  "key_expressions": [
    "tenant_id",
    "lower(email)"
  ],
  "is_unique": true,
  "is_primary": false,
  "is_constraint_backed": false,
  "constraint_name": null,
  "condition": "deleted_at IS NULL",
  "definition": "CREATE UNIQUE INDEX ..."
}
```

约定：

- `columns` 只保存索引键中的普通字段，不含表达式和 `INCLUDE` 列。
- `included_columns` 只保存 `INCLUDE` 列，永不进入关系候选池。
- `key_expressions` 按顺序保存全部索引键，普通字段和表达式都包含。
- 纯表达式索引允许 `columns` 为空数组。
- `condition` 保存部分索引条件。
- `definition` 继续保留完整 PostgreSQL 定义。
- `pg_index.indnkeyatts` 用于区分键位置和包含列位置。
- 可以通过 `pg_get_indexdef(index_oid, position, true)` 等 PostgreSQL 能力保留每个键位置的表达式。

关系候选仅使用“全部索引键都是普通字段”的索引：

```python
columns = index["columns"]
key_expressions = index["key_expressions"]
all_keys_are_columns = len(columns) == len(key_expressions)
```

`key_expressions` 和 `included_columns` 是新格式的必填数组；缺失或为 `null`
均视为格式错误。旧产物无法可靠恢复表达式索引与 `INCLUDE` 列，因此升级时
必须从数据库重新抽取，不能根据旧 JSON 猜测补齐。

纯表达式索引和混合表达式索引保留用于审计，但不作为复合关联字段候选。约束支撑索引仍保存在完整索引列表中，由访问器决定是否纳入具体判断。

### 5.7 注释审计

`comment_source` 必须保留，用来区分：

- 数据库原始注释
- DDL 中已有注释
- LLM 生成注释

启用覆盖已有注释时，当前代码可能生成 `comment_original` 和 `comment_source_original`。这些字段不应在没有替代机制时直接删除。

为了降低迁移范围，v3 初期可以继续沿用当前可选字段。等作业审计结构稳定后，再将真正发生过的覆盖记录集中到作业审计或可选的 `audit.comment_overrides`。

### 5.8 分类结果、审计和幂等性

当前 `json_llm` 会把规则分类备份成三个平铺属性：

- `table_category_rule_based`
- `confidence_rule_based`
- `inference_basis_rule_based`

当前合并逻辑每次都把“当前 `table_category`”当作规则结果。直接对已经增强过的文件再次执行 enhancer 时，当前值已经是上一次 LLM 结果，原始规则分类会被覆盖。

常规 `--step json_llm` 会先重新执行 `json`，因此通常重新获得规则结果；但 enhancer 作为可单独调用的组件仍然不具备幂等性，未来 REST 作业、重试和恢复执行都会暴露这个问题。

v3 建议保留当前 `table_category`、`confidence`、`inference_basis` 作为最终选择结果，并增加：

- `classification_source`
- `classification_reason`
- `rule_based_classification`

`classification_source` 和 `classification_reason` 必须满足联动约束：

| `classification_source` | `classification_reason` |
|---|---|
| `"llm"` | 必须存在且为非空字符串 |
| `"rule"` | 不得输出 |

规则分类的依据继续由 `table_profile.inference_basis` 表达。LLM 超时、调用异常或解析失败属于作业执行信息，应写入作业日志或 manifest，不得写入对象级 `classification_reason`。

```json
"rule_based_classification": {
  "table_category": "fact",
  "confidence": 0.82,
  "inference_basis": [
    "metric_columns",
    "foreign_key_columns"
  ]
}
```

幂等规则：

1. `rule_based_classification` 已存在时，永远保留原值。
2. v2 三个规则备份字段已存在时，优先从它们迁移。
3. 只有前两种记录都不存在时，才把当前分类视为原始规则分类。
4. enhancer 必须在内存中完成 LLM 响应校验和字段联动校验，只有整个增强结果有效时才原子写入。
5. 从规则结果发起增强且 LLM 失败时，保持 `classification_source: "rule"` 并确保不存在 `classification_reason`。
6. 对已成功增强的文件重跑时，若本次 LLM 失败，保留上一次完整的 `source="llm"` 和 reason，本次失败只记录到作业日志。
7. 重跑 enhancer 成功时可以更新最终 LLM 分类、置信度和 reason，但不能覆盖规则原值。
8. 注释原值也只备份一次。
9. 多次 LLM 执行历史放到作业审计，不在对象 JSON 中无限追加。

当前 LLM 返回的 `reason` 只写日志，最终 JSON 中通常只留下 `inference_basis: ["llm_inferred"]`。改造时应仅在 LLM 成功覆盖最终分类时保存真实 `classification_reason`。

### 5.9 生成时间和作业审计

`generated_timestamp` 和 `llm_enhanced_at` 当前没有下游消费者，而且会导致每次生成都产生文件差异。但在 REST 作业系统尚未实现前，它们仍有基本追溯价值。

过渡阶段建议增加：

```yaml
output:
  json_options:
    include_generation_timestamps: true
```

处理方式：

1. 初始默认值为 `true`，保持现有兼容行为。
2. 需要生成可复现文件时，用户可设置为 `false`。
3. REST 作业能力完成后，将时间、模型、配置摘要统一放入作业表或 `output/manifest.json`。
4. 作业审计落地后，把默认值调整为 `false`，对象 JSON 只保存 `job_id`。
5. 最后评估是否废弃该配置。

建议的作业审计信息包括：

- `job_id`
- `generated_at`
- `llm_enhanced_at`
- LLM provider 和 model
- 配置文件摘要或 hash
- 源数据库标识
- 元数据格式版本
- 画像采样和展示样例的配置请求量

### 5.10 单一输出格式策略

`json` 直接生成新格式，`json_llm` 只增强同一格式：

```text
数据库 + DDL -> json（3.0）-> json_llm（3.0）
```

规则：

- 不增加 `output.json_schema_version` 配置项。
- 不保留 v2 序列化分支，也不让 enhancer 按版本分派。
- `json_llm` 遇到旧格式或未知版本时明确失败，提示先重新执行 `--step json`。
- 执行 `--clean` 后重新生成整个 JSON 输出目录，避免残留旧文件。
- `metadata_version` 仍保留，用于校验产物是否符合当前契约以及支持未来真正的格式升级。

## 6. LLM 输入改造

### 6.1 `json_llm`

`json_llm` 当前已经使用顶层白名单输入视图，但仍会传入整组 `structure_flags`。因此应进一步升级为字段级白名单，由统一访问器构造紧凑事实：

```json
{
  "column_name": "order_id",
  "data_type": "integer",
  "is_nullable": false,
  "comment": "订单编号",
  "constraints": [
    "primary_key",
    "unique"
  ],
  "statistics": {
    "sample_count": 500,
    "unique_count": 500,
    "null_rate": 0.0,
    "uniqueness": 1.0
  }
}
```

该输入结构是内部提示词 DTO，不要求与持久化 JSON 使用相同结构或名称。

增强器还必须：

- 只接受当前 `metadata_version: "3.0"` 格式，不承担旧文件升级。
- 幂等保留原始规则分类。
- 幂等保留注释原值。
- 只在 LLM 成功覆盖最终分类时保存非空 `classification_reason`；规则分类结果不输出该字段。

### 6.2 `rel_llm`

当前 `rel_llm` 使用“复制整份 JSON，再删除三个字段”的黑名单方式。建议改成字段级白名单：

- 对象名、对象类型、对象注释
- 字段名、完整类型、字段注释
- 必要的精简统计和样例值
- 主键、唯一约束、外键、索引、逻辑主键

以下内容不进入关系发现提示词：

- 时间戳和作业审计信息
- 分类历史
- 注释覆盖历史
- 语义角色及其推断结果，避免让规则结论诱导 LLM 的独立发现
- 详细字符串长度统计
- 与关系判断无关的角色专属信息

LLM 返回候选后，关系代码仍从完整元数据文档读取 `semantic_analysis.semantic_role` 和字段类型，完成候选去重、语义排除及类型兼容检查。

## 7. v2 → v3 字段迁移对照表

本章是开发和验收时的字段级迁移契约。如果本章与前文的原则性描述出现歧义，应先更新本对照表和完整 JSON 模板，再实施代码改动。

### 7.1 操作类型

| 操作 | 含义 |
|---|---|
| 保留 | v3 继续输出原路径和原语义 |
| 删除 | v3 不再持久化，也不需要替代字段 |
| 派生 | v3 不再持久化，由 `MetadataDocument` 根据权威事实计算 |
| 合并 | 多个 v2 字段合并到一个 v3 字段 |
| 移动 | 信息保留，但更换持久化路径 |
| 移出标准 JSON | 不再放入默认产物，需要时写入可选的详细画像产物 |
| 新增 | v3 或过渡期扩展引入的新事实 |
| 过渡审计 | 暂时允许保留，作业审计落地后迁出对象 JSON |

### 7.2 完整删除、派生和移出清单

| v2 字段路径 | v3 处理 | 替代读取方式 | 主要影响 |
|---|---|---|---|
| `table_info.total_columns` | 派生 | `len(column_profiles)` | 所有读取器改用访问器 |
| `column_profiles.*.column_name` | 删除 | 使用 `column_profiles` 的字典键 | `json_llm` 及通用读取器 |
| `column_profiles.*.role_specific_info` 整组 | 删除 | 无；其中约束和索引事实以表级结构为准 | 缩小 JSON 和 LLM 输入 |
| `column_profiles.*.structure_flags` 整组 | 派生 | 由约束、索引、可空性和统计的领域接口替代 | `relationships` 模块（`candidate_generator`、`repository`、`decision_engine`、`writer`），以及 `rel_llm` 的共享关系处理流程 |
| `table_profile.column_statistics` | 派生 | 必要时从 `semantic_analysis.semantic_role` 和结构事实重算 | 删除前先将 LLM 输入白名单化 |
| `sample_records.sample_size` | 派生 | `len(sample_records.records)` | 样例读取器 |
| `sample_records.total_rows` | 删除 | 统一读取 `table_info.total_rows` | 样例读取器 |
| `column_profiles.*.statistics.sample_count` | 移动 | `profiling.sample_count` | 比例计算和关系评分 |
| `column_profiles.*.statistics.null_rate` | 派生 | `round(null_count / profiling.sample_count, 4)` | CQL 和关系判断改用访问器 |
| `column_profiles.*.statistics.uniqueness` | 派生 | `round(unique_count / profiling.sample_count, 4)` | `rel`、CQL 和逻辑主键相关读取 |
| `column_profiles.*.statistics.mean` | 移出标准 JSON | 可选的详细画像产物 | 当前无下游程序消费 |
| `column_profiles.*.statistics.avg_length` | 移出标准 JSON | 可选的详细画像产物 | 当前无下游程序消费 |
| `column_profiles.*.statistics.min_length` | 移出标准 JSON | 可选的详细画像产物 | 当前无下游程序消费 |
| `column_profiles.*.statistics.max_length` | 移出标准 JSON | 可选的详细画像产物 | 当前无下游程序消费 |
| `column_profiles.*.statistics.median_length` | 移出标准 JSON | 可选的详细画像产物 | 当前无下游程序消费 |
| `column_profiles.*.statistics.length_std` | 移出标准 JSON | 可选的详细画像产物 | 当前无下游程序消费 |
| `table_profile.physical_constraints.unique_constraints[].is_partial` | 删除 | 部分唯一性由 `indexes[].is_unique` 和 `indexes[].condition` 表达 | 当前格式不输出 |
| `generated_timestamp` | 过渡审计 | 过渡期受开关控制；最终迁至作业记录或 manifest | 重复生成的 diff |
| `llm_enhanced_at` | 过渡审计 | 最终迁至作业记录或 manifest | `json_llm` 审计 |

整组删除范围明确如下：

- `role_specific_info` 包括 `identifier_info`、`metric_info`、`datetime_info`、`enum_info`、`audit_info`、`description_info`、`primary_key_info`、`foreign_key_info` 和 `index_info`。
- `structure_flags` 包括 `is_primary_key`、`is_composite_primary_key_member`、`is_foreign_key`、`is_composite_foreign_key_member`、`is_unique`、`is_composite_unique_member`、`is_unique_constraint`、`is_composite_unique_constraint_member`、`is_indexed`、`is_composite_indexed_member` 和 `is_nullable`。
- `table_profile.column_statistics` 包括 `total_columns`、`identifier_count`、`metric_count`、`datetime_count`、`enum_count`、`audit_count`、`attribute_count`、`primary_key_count` 和 `foreign_key_count`。

`unique_column_sets[].uniqueness` 和 `unique_column_sets[].null_rate` 是逻辑主键的固化判定证据，不属于上表中要删除的字段级派生比例。

### 7.3 合并、移动和名称对照

| v2 路径 | v3 路径 | 操作 | 转换规则 |
|---|---|---|---|
| `column_profiles.*.data_type` + `character_maximum_length` | `column_profiles.*.data_type` | 合并 | 例如 `character varying` + `100` 变为 `character varying(100)` |
| `column_profiles.*.data_type` + `numeric_precision` + `numeric_scale` | `column_profiles.*.data_type` | 合并 | 例如 `numeric` + `12` + `2` 变为 `numeric(12,2)`；`integer` 不渲染位宽 |
| 每列 `statistics.sample_count` | `profiling.sample_count` | 移动 | 同一对象的字段画像共用一个实际样本数 |
| 字段画像的实际采样方法（v2 未准确持久化） | `profiling.sample_method` | 新增 | 本轮只允许并记录 `limit` |
| `table_profile.table_category_rule_based` | `table_profile.rule_based_classification.table_category` | 移动 | 已存在的原始规则值优先，不被重跑 LLM 覆盖 |
| `table_profile.confidence_rule_based` | `table_profile.rule_based_classification.confidence` | 移动 | 与规则分类一起幂等迁移 |
| `table_profile.inference_basis_rule_based` | `table_profile.rule_based_classification.inference_basis` | 移动 | 与规则分类一起幂等迁移 |
| 本次 LLM 分类来源 | `table_profile.classification_source` | 新增 | 记录最终分类来源，例如 `rule` 或 `llm` |
| 当前只写入日志的 LLM 分类理由 | `table_profile.classification_reason` | 新增 | 仅当 `classification_source="llm"` 时保存 LLM 实际返回的非空 reason |
| 过渡期的 `comment_original` / `comment_source_original` | 作业审计或可选 `audit.comment_overrides` | 后续移动 | v3 初期可选保留，且只备份一次 |

除上表外，v3 不对 `table_info`、`column_profiles`、`table_profile`、`sample_records` 四个主分组改名，也不批量改写约束、外键、可空性和语义分析的叶子字段名。

### 7.4 新增字段清单

| v3 字段路径 | 必填性 | 来源与用途 |
|---|---|---|
| `job_id` | 作业系统落地前可选 | 关联运行级审计记录 |
| `profiling` | v3 字段画像存在时必填 | 字段画像的表级采样上下文 |
| `profiling.sample_method` | `profiling` 存在时必填 | 实际执行的画像采样方法 |
| `profiling.sample_count` | `profiling` 存在时必填 | 实际参与所有字段画像的行数 |
| `table_profile.classification_source` | `table_profile` 存在时必填 | 标准 `json` 轨道写入 `rule`；LLM 成功覆盖最终分类后写入 `llm` |
| `table_profile.classification_reason` | `classification_source="llm"` 时必填；为 `"rule"` 时禁止输出 | 只保存成功采用的 LLM 分类理由；失败信息进入作业日志 |
| `table_profile.rule_based_classification` | `classification_source="llm"` 时必填；为 `"rule"` 时不输出 | 保存 LLM 覆盖前的原始规则结果 |
| `table_profile.indexes[].key_expressions` | 修正后新产物必填 | 按顺序保存所有普通键和表达式键 |
| `table_profile.indexes[].included_columns` | 修正后新产物必填 | 保存 `INCLUDE` 列，不进入关系候选 |

`indexes[].is_constraint_backed`、`indexes[].constraint_name` 和 `indexes[].definition` 已存在于当前 v2 模型，只是部分历史输出文件未必完整包含。v3 将它们作为权威索引事实明确保留，不将它们误列为全新字段。

### 7.5 保留原路径的字段

| 分组 | v3 继续保留的路径 | 说明 |
|---|---|---|
| 版本 | `metadata_version` | v3 值改为 `"3.0"` |
| 对象 | `table_info.database/schema_name/table_name/table_type/comment/comment_source/total_rows` | 对象身份、注释和规模事实 |
| 字段结构 | `ordinal_position/data_type/is_nullable/column_default/comment/comment_source` | `data_type` 值包含完整长度或精度 |
| 语义画像 | `semantic_analysis.semantic_role/semantic_confidence/inference_basis` | 保留误判排查证据 |
| 字段统计 | `statistics.null_count/unique_count/min/max/value_distribution` | 按字段类型和采样结果可选省略 |
| 最终表分类 | `table_profile.table_category/confidence/inference_basis` | 表示当前最终分类结果 |
| 物理主键 | `physical_constraints.primary_key.constraint_name/columns` | 权威结构事实 |
| 物理外键 | `foreign_keys[].constraint_name/source_columns/target_schema/target_table/target_columns/on_delete/on_update` | 权威结构事实 |
| 唯一约束 | `unique_constraints[].constraint_name/columns` | 不再包含 `is_partial` |
| 索引 | `index_name/index_type/columns/is_unique/is_primary/is_constraint_backed/constraint_name/condition/definition` | `columns` 在修正后只保存普通索引键 |
| 逻辑主键 | `unique_column_sets[].columns/confidence_score/uniqueness/null_rate` | 保留生成时的固化证据 |
| 展示样例 | `sample_records.sample_method/records` | 与字段画像采样分开记录 |

### 7.6 旧产物处理规则

| 输入情况 | 处理方式 | 原因 |
|---|---|---|
| `metadata_version` 不是 `"3.0"` | 明确失败 | 防止旧字段被静默解释成新语义 |
| 缺少 `indexes[].key_expressions` 或 `included_columns` | 明确失败 | 不能可靠恢复表达式键和 `INCLUDE` 列 |
| `key_expressions: null` | 明确失败 | 当前契约要求数组 |
| 存在 `structure_flags`、字段级 `sample_count` 等旧字段 | 明确失败 | 防止新旧格式混合 |
| 缺少可选字段统计 | 返回“未知” | 不得默认为 0 |
| `column_default` 为 `null` | 表示已确认没有默认值 | 与整个键缺失区分 |

历史文件不做运行时升级；使用当前代码重新执行 `--step json --clean`。

### 7.7 下游修改对照

| 模块 | 必须改造的读取点 | 验收标准 |
|---|---|---|
| `MetadataDocument` | 当前格式校验、字段名、比例、约束和索引访问 | 旧格式与混合格式明确失败 |
| `json_llm` | 通过访问器生成字段级白名单输入，幂等合并规则分类 | 只增强当前格式，原始规则值不被覆盖，来源与 reason 联动有效，失败不覆盖已有成功产物 |
| `rel` | 将原始 `structure_flags`、字段比例和索引读取迁到领域接口 | 除批准的索引修复外，候选和关系结果一致 |
| `rel_llm` | 与 `rel` 共用标准流程，LLM 输入改用白名单 | LLM 候选去重、语义排除、类型过滤和四维评分保持契约 |
| CQL 读取器 | 通过访问器读取字段类型、比例、约束、索引和逻辑主键 | 除完整类型字符串外，领域信息一致 |
| Table Schema Loader | 通过访问器读取表分类和字段类型 | 向量化输入信息不丢失 |
| Dim Config | 通过访问器读取数据库、schema、对象名和表分类 | 维表集合保持一致 |
| DDL / MD 样例消费 | 保持与 JSON `sample_records.records` 的同源契约 | 本次不改变采样、去重、全空行过滤和补采行为 |

## 8. 建议的完整 JSON 模板

下面是低迁移成本的 v3 完整示例：

- 保留现有四个主要分组名称。
- 保留约束、索引、字段和语义分析的现有叶子名称。
- 删除重复字段和可推导字段。
- 不适用的统计属性直接省略。
- `column_default: null` 明确表示已经抽取并确认“没有默认值”，因此保留。

```json
{
  "metadata_version": "3.0",
  "job_id": "metadata-20260913-001",
  "table_info": {
    "database": "orders",
    "schema_name": "public",
    "table_name": "orders",
    "table_type": "table",
    "comment": "订单明细表",
    "comment_source": "db",
    "total_rows": 500
  },
  "profiling": {
    "sample_method": "limit",
    "sample_count": 500
  },
  "column_profiles": {
    "order_id": {
      "ordinal_position": 1,
      "data_type": "integer",
      "is_nullable": false,
      "column_default": "nextval('orders_order_id_seq'::regclass)",
      "comment": "订单唯一编号",
      "comment_source": "db",
      "statistics": {
        "null_count": 0,
        "unique_count": 500,
        "min": "1",
        "max": "500"
      },
      "semantic_analysis": {
        "semantic_role": "identifier",
        "semantic_confidence": 0.98,
        "inference_basis": [
          "primary_key",
          "high_uniqueness"
        ]
      }
    },
    "user_id": {
      "ordinal_position": 2,
      "data_type": "integer",
      "is_nullable": false,
      "column_default": null,
      "comment": "下单用户编号",
      "comment_source": "llm_generated",
      "statistics": {
        "null_count": 0,
        "unique_count": 96,
        "min": "1",
        "max": "100"
      },
      "semantic_analysis": {
        "semantic_role": "identifier",
        "semantic_confidence": 0.9,
        "inference_basis": [
          "identifier_name_pattern"
        ]
      }
    },
    "status": {
      "ordinal_position": 3,
      "data_type": "character varying(20)",
      "is_nullable": false,
      "column_default": "'pending'::character varying",
      "comment": "订单状态",
      "comment_source": "db",
      "statistics": {
        "null_count": 0,
        "unique_count": 4,
        "value_distribution": {
          "pending": 120,
          "paid": 260,
          "cancelled": 80,
          "completed": 40
        }
      },
      "semantic_analysis": {
        "semantic_role": "enum",
        "semantic_confidence": 0.92,
        "inference_basis": [
          "low_cardinality"
        ]
      }
    },
    "amount": {
      "ordinal_position": 4,
      "data_type": "numeric(12,2)",
      "is_nullable": false,
      "column_default": null,
      "comment": "订单金额",
      "comment_source": "db",
      "statistics": {
        "null_count": 0,
        "unique_count": 438,
        "min": "1.00",
        "max": "9999.00"
      },
      "semantic_analysis": {
        "semantic_role": "metric",
        "semantic_confidence": 0.95,
        "inference_basis": [
          "numeric_type",
          "metric_name_pattern"
        ]
      }
    },
    "created_at": {
      "ordinal_position": 5,
      "data_type": "timestamp without time zone",
      "is_nullable": false,
      "column_default": "CURRENT_TIMESTAMP",
      "comment": "订单创建时间",
      "comment_source": "db",
      "statistics": {
        "null_count": 0,
        "unique_count": 500,
        "min": "2026-01-01 08:00:00",
        "max": "2026-09-13 18:30:00"
      },
      "semantic_analysis": {
        "semantic_role": "audit",
        "semantic_confidence": 0.95,
        "inference_basis": [
          "audit_pattern:created_at"
        ]
      }
    },
    "external_order_no": {
      "ordinal_position": 6,
      "data_type": "character varying(64)",
      "is_nullable": false,
      "column_default": null,
      "comment": "外部系统订单编号",
      "comment_source": "db",
      "statistics": {
        "null_count": 0,
        "unique_count": 500
      },
      "semantic_analysis": {
        "semantic_role": "identifier",
        "semantic_confidence": 0.91,
        "inference_basis": [
          "high_uniqueness",
          "identifier_name_pattern"
        ]
      }
    }
  },
  "table_profile": {
    "table_category": "fact",
    "confidence": 0.94,
    "inference_basis": [
      "llm_inferred"
    ],
    "classification_source": "llm",
    "classification_reason": "记录订单业务事件，包含订单金额、用户引用和业务发生时间",
    "rule_based_classification": {
      "table_category": "fact",
      "confidence": 0.86,
      "inference_basis": [
        "metric_columns",
        "foreign_key_columns",
        "event_time_column"
      ]
    },
    "physical_constraints": {
      "primary_key": {
        "constraint_name": "orders_pkey",
        "columns": [
          "order_id"
        ]
      },
      "foreign_keys": [
        {
          "constraint_name": "orders_user_id_fkey",
          "source_columns": [
            "user_id"
          ],
          "target_schema": "public",
          "target_table": "users",
          "target_columns": [
            "user_id"
          ],
          "on_delete": "NO ACTION",
          "on_update": "NO ACTION"
        }
      ],
      "unique_constraints": [
        {
          "constraint_name": "orders_external_order_no_key",
          "columns": [
            "external_order_no"
          ]
        }
      ]
    },
    "indexes": [
      {
        "index_name": "idx_orders_created_at",
        "index_type": "btree",
        "columns": [
          "created_at"
        ],
        "included_columns": [
          "status"
        ],
        "key_expressions": [
          "created_at"
        ],
        "is_unique": false,
        "is_primary": false,
        "is_constraint_backed": false,
        "constraint_name": null,
        "condition": null,
        "definition": "CREATE INDEX idx_orders_created_at ON public.orders USING btree (created_at) INCLUDE (status)"
      },
      {
        "index_name": "idx_orders_lower_external_no",
        "index_type": "btree",
        "columns": [],
        "included_columns": [],
        "key_expressions": [
          "lower((external_order_no)::text)"
        ],
        "is_unique": false,
        "is_primary": false,
        "is_constraint_backed": false,
        "constraint_name": null,
        "condition": "status <> 'cancelled'::character varying",
        "definition": "CREATE INDEX idx_orders_lower_external_no ON public.orders USING btree (lower((external_order_no)::text)) WHERE status <> 'cancelled'::character varying"
      }
    ],
    "unique_column_sets": [
      {
        "columns": [
          "external_order_no"
        ],
        "confidence_score": 0.92,
        "uniqueness": 1.0,
        "null_rate": 0.0
      }
    ]
  },
  "sample_records": {
    "sample_method": "limit",
    "records": [
      {
        "order_id": "1",
        "user_id": "82",
        "status": "paid",
        "amount": "18.00",
        "created_at": "2026-09-01 10:30:00",
        "external_order_no": "EXT-20260901-0001"
      },
      {
        "order_id": "2",
        "user_id": "29",
        "status": "completed",
        "amount": "19.00",
        "created_at": "2026-09-01 11:15:00",
        "external_order_no": "EXT-20260901-0002"
      }
    ]
  }
}
```

模板说明：

- `table_info.total_columns` 已删除，由 `len(column_profiles)` 派生。
- `profiling.sample_count` 是字段画像实际使用的行数。
- `sample_records` 的实际条数由 `records.length` 得到。
- `statistics` 及其子属性均允许按类型和采样结果省略。
- `column_default: null` 表示已确认没有默认值，不应与“未抽取”混淆。
- `rule_based_classification` 只在 `classification_source="llm"` 时输出，用于保存被 LLM 覆盖前的规则结果。
- 模板中 `classification_source` 为 `"llm"`，因此必须同时输出非空 `classification_reason`；标准规则分类不输出该字段。
- `job_id` 在作业系统建立前可以省略。
- 过渡期根据 `output.json_options.include_generation_timestamps` 决定是否继续输出旧时间戳。
- `view` 和 `materialized_view` 继续使用相同四个主要分组，通过 `table_info.table_type` 区分。
- 物化视图可以包含索引；普通视图通常没有物理约束和索引。
- 表达式索引允许 `columns` 为空，但必须通过 `key_expressions` 和 `definition` 保留完整事实。
- 模板刻意不再把 `table_info` 改名为 `object`，也不改写约束、外键、可空性和语义分析等现有叶子字段名。

## 9. 代码修改范围

### 9.1 索引抽取修复

优先修改：

- `metaweave/utils/sql_templates.py`
- `metaweave/core/metadata/extractor.py`
- `metaweave/core/metadata/models.py`

目标：

- 使用 `indnkeyatts` 区分索引键和 `INCLUDE` 列。
- 不再因表达式位置无法连接 `pg_attribute` 而丢失整条索引。
- 增加有序 `key_expressions` 和 `included_columns`。
- `columns` 只包含普通索引键字段。
- 部分唯一性在索引中使用 `is_unique` 和 `condition` 表达。
- 将本项作为新格式生成的一部分，并建立新的 JSON 基线。

替换说明：

- 新格式必须输出 `indexes[].key_expressions` 和 `indexes[].included_columns`。
- 旧 JSON 无法恢复已丢失的表达式索引，也无法从旧 `columns` 中区分可能混入的 `INCLUDE` 列，必须从数据库重新抽取。
- 新基线直接使用重新抽取得到的 3.0 产物。

### 9.2 JSON 生成端

主要修改：

- `metaweave/core/metadata/models.py`
  - 用新格式序列化替换旧格式序列化，不保留版本选择分支。
  - 标准 `json` 轨道在 `table_profile` 存在时输出 `classification_source: "rule"`。
  - 删除 `role_specific_info`、重复 `column_name`、`column_statistics` 和 `total_columns`。
  - 从 `unique_constraints` 中删除语义不成立且当前恒为 `false` 的 `is_partial`。
  - 合并数据类型修饰属性。
  - 删除持久化的 `structure_flags`。
  - 保持主要分组和大多数叶子字段名稳定。
- `metaweave/core/metadata/formatter.py`
  - 删除 `sample_size` 和 `sample_records.total_rows`。
  - 保留现有采样、去重、全空行过滤和回退行为，只调整 JSON 序列化结构。
- `metaweave/core/metadata/generator.py` 和 `metaweave/core/metadata/connector.py`
  - 本轮只允许 `sampling.sample_method=limit`。
  - 作业启动时拒绝尚未实现的 `tablesample` 和 `range`，不得静默改用 `limit`。
  - 后续实现新采样算法时，为每种方法单独建立统计和候选结果基线。

### 9.3 统一读取与校验层

建议新增：

```text
metaweave/core/metadata/metadata_document.py
```

职责：

- 只读取当前 3.0 格式，旧版本明确失败。
- 校验必须字段和字段类型。
- 提供对象、字段、约束、统计、语义角色的统一访问接口。
- 为新流程提供语义明确的主键、唯一性和索引查询接口。
- 目标查询接口只从约束、索引、字段定义和统计事实推导，不回读 `structure_flags`。
- 为各个下游消费者提供精确的领域谓词，避免再组合原始布尔标志。
- 动态计算 `total_columns`、`null_rate` 和 `uniqueness`。
- 对缺失的关键结构事实明确报错。
- 对可选统计使用“未知”语义，不把缺失值静默转换为 0。
- 使用既有四位小数规则计算比例。
- 区分普通索引键、表达式索引键和 `INCLUDE` 列。
- 将索引关键数组的缺失与非法 `null` 都视为格式错误。

### 9.4 `json_llm`

修改 `metaweave/core/metadata/json_llm_enhancer.py`：

- 只接受并输出当前 3.0 格式。
- 删除对重复 `column_name`、`sample_size`、`sample_records.total_rows` 的依赖。
- 从统一访问器生成字段级白名单输入。
- 不再把整组 `structure_flags` 直接放入提示词。
- 幂等保留原始规则分类和注释原值。
- 只有 LLM 成功覆盖最终分类时，才将 `classification_source` 改为 `"llm"` 并写入非空 `classification_reason`。
- 从规则输入开始的任务在 LLM 未执行、失败或最终采用规则结果时，保持 `classification_source: "rule"` 并删除任何候选结果中的 `classification_reason`。
- 对已成功增强的产物重跑失败时，不覆盖上一次完整产物；失败信息只写作业日志。
- 在内存中完成 LLM 响应、字段联动和版本结构校验后，再原子替换输出文件，避免留下半完成状态。
- 防止旧格式字段被 `deepcopy` 后原样污染输出。

### 9.5 `rel` 与 `rel_llm`

修改：

- `metaweave/core/relationships/repository.py`
- `metaweave/core/relationships/candidate_generator.py`
- `metaweave/core/relationships/decision_engine.py`
- `metaweave/core/relationships/writer.py`
- `metaweave/core/relationships/llm_relationship_discovery.py`

目标：

- 全部通过统一访问器读取元数据。
- 取消对持久化 `structure_flags` 的依赖。
- `rel_llm` 使用字段级白名单构建提示词。
- LLM 候选返回后再读取完整元数据进行重叠检查、语义排除、类型过滤和四维评分。
- 物理外键继续直通；物理主键、唯一约束和逻辑主键继续进入标准候选池。
- `INCLUDE` 列永不进入索引候选。
- 纯表达式和混合表达式索引不作为普通复合关联字段候选。

### 9.6 CQL、向量加载和维表配置

修改：

- `metaweave/core/cql_generator/reader.py`
- `metaweave/core/table_schema/json_extractor.py`
- `metaweave/core/dim_value/config_generator.py`

目标：

- 改用统一访问器。
- 清理 CQL 读取器中读取后未使用的 `structure_flags` 局部变量。
- CQL 正确读取对象类型。
- CQL 字段 `data_type` 输出完整长度和精度；这是预期文本变化。
- Table Schema Loader 继续获得表分类和时间字段提示。
- Dim Config 继续获得数据库、schema、对象名和分类。

### 9.7 跨产物样例契约

DDL、JSON 和 MD 的样例数据存在同源关系：

- DDL 写入 `SAMPLED_RECORDS`。
- JSON 优先从 DDL 读取样例。
- MD 从 DDL 样例构建字段示例。

本次 JSON 格式改造不改变现有采样、去重、全空行过滤或补采规则。后续如要调整采样行为，应作为独立功能变更评审。

## 10. 推荐实施顺序

1. 保存旧产物的索引和关系基线，用于识别新格式及索引修复带来的预期变化。
2. 修复表达式索引和 `INCLUDE` 列抽取，明确普通键、表达式键和包含列的数据模型。
3. 实现单一的 3.0 序列化，删除旧格式生成分支和版本选择配置。
4. 为 3.0 格式补充 JSON Schema 或等价结构校验测试。
5. 建立只读取 3.0 的 `MetadataDocument` 访问器，旧格式和混合格式明确失败。
6. 将 `json_llm` 的输入改为字段级白名单，并修复分类审计幂等性。
7. 将 `sampling.sample_method` 约束为本轮仅支持 `limit`，对其他值早失败，并确保 JSON 记录实际采样方法。
8. 删除低风险冗余字段、持久化 `structure_flags`，精简统计信息并增加时间戳输出开关。
9. 使用 `--step json --clean` 重新生成完整的新格式产物并建立新基线。
10. 后续将 `rel`、`rel_llm`、CQL、Table Schema Loader、Dim Config 迁移到访问器及目标领域接口。
11. 后续将 `rel_llm` 从黑名单裁剪改为字段级白名单。
12. 后续重新生成 CQL 等下游产物，按“必须一致”和“预期变化”两类规则回归。
13. REST 作业审计落地后迁移运行级时间和配置信息。

## 11. 测试计划

### 11.1 序列化和版本校验

- v3.0 JSON 满足目标结构。
- 默认调用和 CLI 均只输出 v3.0，不存在版本选择配置。
- v2 输入、未知 `metadata_version` 和混合旧字段的产物明确失败。
- 缺失 `key_expressions`、缺失 `included_columns` 或值为 `null` 时明确失败。
- `json_llm` 输入和输出均为 v3.0。
- 未知 `metadata_version` 明确失败。
- 缺失字段类型、数据库、schema 或对象名等关键结构事实时明确失败。
- 缺少 `statistics`、`unique_count`、逻辑主键、索引、样例或审计记录时仍能正常处理。
- BYTEA、ARRAY、JSON、JSONB 和空样本分别覆盖。
- `total_columns` 与样例实际条数能够正确派生。
- `column_default: null` 与字段缺少 `column_default` 能被区分。
- 表、视图、物化视图分别覆盖。
- 标准 `json` 轨道生成 v3 且 `table_profile` 存在时，`classification_source` 为 `"rule"`。
- JSON Schema 使用条件校验：`classification_source="llm"` 时要求非空 `classification_reason` 和 `rule_based_classification`；`classification_source="rule"` 时禁止这两个字段。

### 11.2 `structure_flags` 删除与目标语义

- 目标访问器仅从权威事实推导，不读取持久化 `structure_flags`。
- 删除文档中的 `structure_flags` 前后，目标访问器结果完全一致。
- `candidate_generator`、`decision_engine`、`writer` 和 `repository` 的实际消费谓词逐列对比，除显式批准的行为修正外 diff 为 0。
- orders 测试库覆盖 PK、约束支撑索引和普通索引。
- 专用表覆盖同一字段同时属于单列和复合索引。
- 新接口允许单列索引和复合索引成员同时为真。
- `is_data_unique` 严格使用四位小数后的 `== 1.0`。
- 新 `is_data_unique` 不再与唯一约束状态混合。
- `INCLUDE` 列不属于索引键。
- 对多索引、表达式索引和 `INCLUDE` 建立显式的预期差异清单；其余结果必须与旧行为一致。

### 11.3 比例和关系发现回归

- 派生 `null_rate`、`uniqueness` 使用四位小数，与改造前基线值的绝对差不超过 `1e-4`。
- 在 `0.8`、`0.9`、`0.95`、`1.0` 等阈值附近增加边界样例。
- 同一数据库上，改造前后的物理外键直通结果一致。
- 物理主键、唯一约束、逻辑主键候选集合完全一致。
- 单列和复合字段的类型兼容结果一致。
- 语义角色排除结果一致。
- 最终关系接受、拒绝和抑制集合完全一致；索引修复导致的预期变化单独列出。

### 11.4 `json_llm` 幂等和 LLM 输入

- 对同一个已经增强的文件连续执行两次，`rule_based_classification` 保持原始规则值。
- 注释原值只备份一次。
- 重跑成功时允许更新最终 LLM 分类和 reason。
- LLM 成功覆盖最终分类时，`classification_source` 为 `"llm"` 且 `classification_reason` 是非空字符串。
- 从规则输入发起任务时，LLM 未执行、失败或回退到规则结果，`classification_source` 为 `"rule"` 且 `classification_reason` 键不存在。
- 已成功增强的文件重跑失败时，文件字节不变，上一次的 `source="llm"` 和 reason 保持配对。
- 模拟在响应解析和写入替换前失败，不产生临时半完成 JSON，失败原因可从作业日志追溯。
- `json_llm` 提示词只包含字段级白名单属性。
- `json_llm` 提示词不包含完整 `structure_flags`。
- `rel_llm` 提示词不包含时间戳、审计历史、规则分类备份和详细长度统计。
- `rel_llm` 提示词不包含规则生成的语义角色。
- 两个提示词的 Token 数相对现有版本明显下降。
- 提示词快照按新白名单重新建立，不与旧文本要求逐字一致。

### 11.5 索引抽取和候选池

- 普通单列索引。
- 普通复合索引，字段顺序正确。
- 纯表达式索引不会被遗漏，`columns` 为空且 `key_expressions` 完整。
- 普通字段与表达式混合索引的键顺序正确。
- 部分索引的 `condition` 完整。
- 唯一表达式索引的 `is_unique` 正确。
- 主键/唯一约束支撑索引的 `is_constraint_backed` 和 `constraint_name` 正确。
- 带 `INCLUDE` 列的索引能区分 `columns` 与 `included_columns`。
- 混合表达式索引明确包含 `key_expressions`，`all_keys_are_columns` 为 `false`，不进入普通复合关系候选。
- `unique_constraints` 不输出 `is_partial`。
- 部分唯一索引通过 `is_unique=true` 和非空 `condition` 准确表达。
- “1 个键 + 1 个 INCLUDE”不会作为复合索引进入 Stage 1。
- 纯表达式和混合表达式索引不作为普通复合关系候选。
- 物化视图上的普通、唯一、表达式、部分和 INCLUDE 索引分别覆盖。

### 11.6 CQL 和下游产物

CQL 回归分为两类：

**必须保持一致：**

- 对象和字段集合。
- 主键、外键、唯一约束和逻辑主键。
- 表分类、字段语义角色和关系集合。
- Table Schema Loader 的表分类和时间字段提示。
- Dim Config 识别出的维表集合。

**预期变化并重新建立基线：**

- `data_type` 从基础类型变为包含长度或精度的完整类型。
- 索引修复后新增的表达式索引和正确分离的 INCLUDE 列。
- `json_llm` 和 `rel_llm` 白名单化后的提示词文本。
- JSON 删除冗余字段后的文本和体积。

不能用修复前的 CQL 或提示词逐字快照判断 v3 回归。

### 11.7 跨产物样例和审计

- DDL `SAMPLED_RECORDS` 与 JSON `sample_records.records` 一致。
- MD 字段示例来自同一组 DDL 样例。
- 小表、重复行、全空行情况下 DDL、JSON、MD 行为一致。
- 没有 DDL 文件时，JSON 的数据库采样回退行为正确。
- 两处 `sample_method` 分别记录画像与展示样例的实际方法。
- 默认 `limit` 的现有行为和基线保持不变。
- 本轮配置 `tablesample` 或 `range` 时在作业启动阶段明确失败，不静默回退。
- 未来每新增一种采样方法，都单独重建统计、语义角色、`unique_column_sets` 和关系候选基线，不与 `limit` 结果做直接等值对比。
- `include_generation_timestamps=false` 时重复生成的 JSON 不因时间字段产生无意义 diff。
- 能区分数据库注释和 LLM 注释。
- 能解释字段语义角色和逻辑主键的判断依据。
- 能区分“字段没有默认值”和“默认值信息未抽取”。
- 能从 `job_id` 关联到生成时间、模型、配置摘要、采样请求量和执行状态。

## 12. 最终建议

这次改造不宜只在 `models.py.to_dict()` 中删除字段。JSON 是多个流程之间的接口，正确顺序是先修复索引事实，再建立统一访问器和两个 LLM 流程的字段级白名单，最后发布 v3.0 格式。

推荐的核心取舍是：

- 保留现有主要 JSON 分组和大部分叶子名称，减少迁移成本。
- 删除真正无用和重复的字段。
- 删除旧 `structure_flags`，不把首索引优先等缺陷固化为新领域语义。
- 使用语义明确、允许同时成立的索引和唯一性访问器。
- 保留会影响关系判断的语义和逻辑主键证据。
- 明确区分画像采样和展示样例，并记录实际执行方法。
- 本轮保持 `limit` 为唯一采样方法，将其他采样算法作为独立功能并分别建立基线。
- 先修复表达式索引和 INCLUDE 候选池污染，再建立新的 3.0 基线。
- 新格式删除 `unique_constraints[].is_partial`，部分唯一性统一由唯一索引的 `is_unique` 和 `condition` 表达。
- `json_llm` 只接受当前格式，并幂等保留原始规则分类。
- 将 CQL 类型字符串和提示词白名单变化归为预期产物变化。
- 将运行级审计信息逐步移到作业记录，对过渡期时间戳提供开关。

这样可以明显缩小 JSON 和 LLM 输入，同时保留关系误判、语义分类、逻辑主键、注释来源及索引抽取所需的排查证据，也不会继续保留已确认的历史缺陷。
