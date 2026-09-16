# JSON v2.0 与 v3.0 格式差异对比

## 1. 文档目的与证据来源

本文详尽列出 `output/json/*.json` 从 v2.0 到 v3.0 的全部格式变化,供下游消费方
(rel / CQL / 统计 / 图谱)适配参考。证据来源:

1. **v2.0 序列化代码**:git 提交 `fb80de4`(v3 改造 `f30c350` 之前)的
  `metaweave/core/metadata/models.py`(`TableMetadata.to_dict`,docstring 明确
   "用于 JSON 序列化 v2.0 格式")与 `metaweave/utils/data_utils.py`
   (`get_column_statistics`);
2. **v3.0 契约**:当前 `metaweave/core/metadata/metadata_document.py`
  (`MetadataDocument.from_dict` 强校验);
3. **v3.0 实际产物**:当前 `output/json/*.json` 全库字段枚举。

v2 → v3 的本质一句话:**列级"加工过的信息"(结构标志、角色详情、预计算统计)全部
从落盘产物中移除,只保留原始事实(表级约束/索引/原始计数);需要加工值时由契约层
(**`MetadataDocument`**)方法按需现算。契约化强校验,旧字段混入直接报错(零兼容)。**

## 2. 顶层结构


| 键                     | v2.0              | v3.0                                         |
| --------------------- | ----------------- | -------------------------------------------- |
| `metadata_version`    | `"2.0"`           | `"3.0"`(契约校验:必须等于当前版本,否则报错)                  |
| `generated_timestamp` | 有                 | 有                                            |
| `table_info`          | 有                 | 有                                            |
| `column_profiles`     | 有                 | 有                                            |
| `table_profile`       | 有                 | 有(允许为 `null`)                                |
| `sample_records`      | 有(由 formatter 追加) | 有                                            |
| `profiling`           | **无**             | **新增**:`{sample_method, sample_count}`(见 §9) |
| `llm_enhanced_at`     | 有(LLM 增强落盘时写入)    | 增强改为内存完成,仅在时间戳开关下出现                          |




## 3. table_info


| 键                                                        | v2.0 | v3.0                                                                                                   |
| -------------------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------ |
| `database` / `schema_name` / `table_name` / `table_type` | 有    | 有                                                                                                      |
| `comment` / `comment_source`                             | 有    | 有                                                                                                      |
| `total_rows`                                             | 有    | 有                                                                                                      |
| `total_columns`                                          | 有    | **删除**——契约报错 `"JSON v3 不允许 table_info.total_columns"`(可由 column_profiles 键数推导,契约提供 `total_columns` 属性) |




## 4. column_profiles(每列画像,变化最大)



### 4.1 被删除的键(v2 有、v3 无,混入即报错)


| 键                                     | v2.0 内容           | v3.0                                                         |
| ------------------------------------- | ----------------- | ------------------------------------------------------------ |
| `column_name`                         | 冗余(键名即列名)         | 删除(forbidden)                                                |
| `character_maximum_length`            | 从 ColumnInfo 合并   | 删除(forbidden)                                                |
| `numeric_precision` / `numeric_scale` | 从 ColumnInfo 合并   | 删除(forbidden)                                                |
| `structure_flags`                     | 11 个列级物理标志(见 4.2) | 删除(forbidden)——约束事实统一挪到表级 `physical_constraints` / `indexes` |
| `role_specific_info`                  | 9 类角色详情(见 4.3)    | 删除(forbidden)——角色详情不再落盘                                      |




### 4.2 v2 的 structure_flags 完整字段(11 个,全部删除)

```text
is_primary_key, is_composite_primary_key_member,
is_foreign_key, is_composite_foreign_key_member,
is_unique, is_composite_unique_member,
is_unique_constraint, is_composite_unique_constraint_member,
is_indexed, is_composite_indexed_member,
is_nullable
```

v3 替代方式:契约层提供按需判定方法
`is_single_column_primary_key()` / `has_single_column_unique_constraint()` /
`has_single_column_index()` / `is_composite_*_member()` 等,全部改读表级
`physical_constraints` 与 `indexes`(见 §10)。

### 4.3 v2 的 role_specific_info 完整子键(9 类,全部删除)

```text
identifier_info, metric_info, datetime_info, enum_info, audit_info,
description_info, primary_key_info, foreign_key_info, index_info
```



### 4.4 两版都保留的键

```text
ordinal_position, data_type, is_nullable, column_default,
comment, comment_source, statistics,
semantic_analysis(内部:semantic_role / semantic_confidence / inference_basis)
```



## 5. 每列 statistics(关键差异,CQL 适配点)



### 5.1 v2.0 完整键清单(预计算指标 + 原始计数混合)


| 键                                                                           | 条件                 |
| --------------------------------------------------------------------------- | ------------------ |
| `sample_count`                                                              | 所有列                |
| `null_count`                                                                | 所有列                |
| `null_rate`                                                                 | 所有列(预计算)           |
| `unique_count`                                                              | 所有列(BYTEA 除外)      |
| `uniqueness`                                                                | 所有列(BYTEA 除外,预计算)  |
| `min` / `max` / `mean`                                                      | 数值列                |
| `avg_length` / `min_length` / `max_length` / `median_length` / `length_std` | 字符串列               |
| `value_distribution`                                                        | 唯一值数 ≤ 阈值(默认 10)的列 |




### 5.2 v3.0 允许的键(实际产物全库并集,只有原始计数)

```text
null_count, unique_count, min, max, value_distribution
```



### 5.3 v3.0 禁止的键(混入即报错,`forbidden_statistic_keys`)

```text
sample_count, null_rate, uniqueness,
mean, avg_length, min_length, max_length, median_length, length_std
```



### 5.4 v3 替代方式

契约层按需现算:`column_uniqueness()`(按 `unique_count`)、`column_null_rate()`
(按 `null_count`)、`column_statistics()`;统计不足时返回 `None`(与"缺数据"和"0"
区分,消费方据此判断)。

## 6. table_profile


| 键                                                   | v2.0                                                                                                                                                    | v3.0                                                                                          |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `table_category` / `confidence` / `inference_basis` | 有                                                                                                                                                       | 有                                                                                             |
| `classification_source`                             | 无                                                                                                                                                       | **新增**;契约限定 `"rule"` 或 `"llm"`                                                                |
| `classification_reason`                             | 无                                                                                                                                                       | **新增**(仅 `classification_source: llm` 时,必填非空)                                                 |
| `rule_based_classification`                         | 无                                                                                                                                                       | **新增**(仅 `classification_source: llm` 时,必填;含 `table_category`/`confidence`/`inference_basis`) |
| `physical_constraints.primary_key`                  | 有(`{constraint_name, columns}` 或 null)                                                                                                                  | 有(同)                                                                                          |
| `physical_constraints.foreign_keys[]`               | 有:`constraint_name, source_columns, target_schema, target_table, target_columns, on_delete, on_update`                                                  | 有(同,已在实际产物核实)                                                                                 |
| `physical_constraints.unique_constraints[]`         | 有(`{constraint_name, columns, is_partial}`)                                                                                                             | 有(同)                                                                                          |
| `indexes[]`                                         | 有                                                                                                                                                       | 有,但条目字段变化(见 §7)                                                                               |
| `column_statistics`                                 | 有(表级汇总:`total_columns, identifier_count, metric_count, datetime_count, enum_count, audit_count, attribute_count, primary_key_count, foreign_key_count`) | **删除**                                                                                        |
| `unique_column_sets[]`                              | 有(逻辑键:`{columns, confidence_score, uniqueness, null_rate}`)                                                                                             | 有(同)                                                                                          |




## 7. indexes[] 条目字段


| 字段                                                                                                                                             | v2.0           | v3.0                                                                 |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | -------------------------------------------------------------------- |
| `index_name` / `index_type` / `columns` / `is_unique` / `is_primary` / `condition` / `is_constraint_backed` / `constraint_name` / `definition` | 有              | 有                                                                    |
| `key_expressions`                                                                                                                              | 可选(None 时 pop) | **必填数组**(契约校验 `"indexes[].key_expressions 必须是数组"`;无值时以 `columns` 兜底) |
| `included_columns`                                                                                                                             | 可选(None 时 pop) | **必填数组**(同上;无值时写空数组)                                                 |




## 8. profiling 节点(新增)

```json
"profiling": {
  "sample_method": "limit",
  "sample_count": 500
}
```

契约校验:`sample_method` 当前仅允许 `"limit"`;`sample_count` 必须是整数。

## 9. sample_records


|      | v2.0                         | v3.0                                      |
| ---- | ---------------------------- | ----------------------------------------- |
| 结构   | `{sample_method, records[]}` | 同                                         |
| 契约校验 | 无                            | 新增:`sample_records` 必须是对象、`records` 必须是数组 |




## 10. 契约层(MetadataDocument)新增能力



### 10.1 强校验(from_dict,落盘前与消费方构造时)

- 根节点必须是对象;`metadata_version` 必须等于 `3.0`;
- `table_info` / `column_profiles` 必须是对象;`table_profile` 对象或 null;
- forbidden 键校验:§4.1 的列级键、§5.3 的统计键、`table_info.total_columns`;
- 分类契约校验:`classification_source` 取值、`rule` 时不得输出
`classification_reason`/`rule_based_classification`、`llm` 时两者必填;
- profiling / indexes / sample_records 结构校验。



### 10.2 按需计算接口(替代被删的预计算字段)

```text
column_uniqueness() / column_null_rate() / column_statistics() / is_data_unique()
is_single_column_primary_key() / is_composite_primary_key_member()
has_single_column_unique_constraint() / is_composite_unique_constraint_member()
has_single_column_index() / is_composite_index_key_member() / all_index_keys_are_columns()
column_constraints()(标签列表:primary_key/foreign_key/unique/logical_unique_candidate)
build_json_llm_input()(LLM 白名单输入构造)
```



## 11. 对下游消费方的影响


| 消费方                                              | 依赖的 v2 字段                                        | v3 状态                                                                                                                           |
| ------------------------------------------------ | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| rel / rel_llm(候选生成、决策器、writer、repository)        | 列级 `structure_flags`、`statistics.uniqueness`     | **已适配**(doc 15 改造:改读表级 constraints/indexes;最小键过滤与唯一性判定走表级)                                                                      |
| **CQL reader**                                   | `statistics.uniqueness` / `statistics.null_rate` | **未适配**——v3 下恒取默认 0.0,生成的 Cypher 节点属性 uniqueness/null_rate 全为 0(静默数据错误);修复方向:改调契约层 `column_uniqueness()` / `column_null_rate()` |
| CQL 其它读取(pk/uk/fk 列集、indexes、unique_column_sets) | —                                                | 已是 v3 兼容字段,无影响                                                                                                                  |




## 12. 完整双向对照表



### 12.1 v2 有、v3 删除(全量清单)


| v2 字段                                            | 处理方式                                    |
| ------------------------------------------------ | --------------------------------------- |
| `table_info.total_columns`                       | 删除,契约报错(可由 column_profiles 键数推导)        |
| `column_profiles[col].column_name`               | 删除(forbidden)                           |
| `column_profiles[col].character_maximum_length`  | 删除(forbidden)                           |
| `column_profiles[col].numeric_precision`         | 删除(forbidden)                           |
| `column_profiles[col].numeric_scale`             | 删除(forbidden)                           |
| `column_profiles[col].structure_flags`(11 标志)    | 删除(forbidden),表级 constraints/indexes 替代 |
| `column_profiles[col].role_specific_info`(9 类详情) | 删除(forbidden)                           |
| `statistics.sample_count`                        | 删除(forbidden)                           |
| `statistics.null_rate`                           | 删除(forbidden),按 null_count 现算           |
| `statistics.uniqueness`                          | 删除(forbidden),按 unique_count 现算         |
| `statistics.mean`                                | 删除(forbidden)                           |
| `statistics.avg_length`                          | 删除(forbidden)                           |
| `statistics.min_length`                          | 删除(forbidden)                           |
| `statistics.max_length`                          | 删除(forbidden)                           |
| `statistics.median_length`                       | 删除(forbidden)                           |
| `statistics.length_std`                          | 删除(forbidden)                           |
| `table_profile.column_statistics`(9 字段表级汇总)      | 删除                                      |
| 顶层 `llm_enhanced_at`                             | 删除(增强内存化;时间戳开关下可出现)                     |




### 12.2 v2 没有、v3 新增(全量清单)


| v3 字段                                     | 说明                                                                                             |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 顶层 `profiling`                            | `{sample_method: "limit", sample_count: N}`;契约校验取值与类型                                          |
| `table_profile.classification_source`     | LLM 分类审计;契约限定 `"rule"` / `"llm"`                                                               |
| `table_profile.classification_reason`     | 仅 `source=llm` 时必填非空                                                                           |
| `table_profile.rule_based_classification` | 仅 `source=llm` 时必填(规则分类备份)                                                                     |
| 契约层强校验(`MetadataDocument.from_dict`)      | 根/类型/版本/forbidden/分类契约/profiling/indexes/sample_records 全套校验                                   |
| 契约层按需计算接口                                 | `column_uniqueness()` / `column_null_rate()` / 约束与索引判定方法 / `build_json_llm_input()` 等(见 §10.2) |




### 12.3 两版都有、语义变化(全量清单)


| 字段                                                                              | v2.0           | v3.0                      |
| ------------------------------------------------------------------------------- | -------------- | ------------------------- |
| `metadata_version`                                                              | `"2.0"`        | `"3.0"`(契约校验必须)           |
| `indexes[].key_expressions`                                                     | 可选(None 时 pop) | **必填数组**(无值时以 columns 兜底) |
| `indexes[].included_columns`                                                    | 可选(None 时 pop) | **必填数组**(无值时写空数组)         |
| `statistics.null_count` / `unique_count` / `min` / `max` / `value_distribution` | 有(与预计算指标混合)    | 有(**唯一允许的统计键**)           |




### 12.4 两版都有、完全不变(全量清单)

```text
顶层:generated_timestamp, table_info, column_profiles, table_profile, sample_records
table_info:database, schema_name, table_name, table_type, comment, comment_source, total_rows
column_profiles[col]:ordinal_position, data_type, is_nullable, column_default,
    comment, comment_source, statistics,
    semantic_analysis(semantic_role / semantic_confidence / inference_basis)
table_profile:table_category, confidence, inference_basis,
    physical_constraints.primary_key({constraint_name, columns}),
    physical_constraints.foreign_keys[](constraint_name, source_columns, target_schema,
        target_table, target_columns, on_delete, on_update),
    physical_constraints.unique_constraints[]({constraint_name, columns, is_partial}),
    unique_column_sets[]({columns, confidence_score, uniqueness, null_rate})
indexes[]:index_name, index_type, columns, is_unique, is_primary, condition,
    is_constraint_backed, constraint_name, definition
sample_records:{sample_method, records[]}
```



## 13. CQL 消费字段清单(与 v3 核对结果)

`--step cql` 从 `output/json/` 与 `output/rel/` 读取以下字段;标注每个字段在
v3 中的状态。

### 13.1 从 output/json/(表元数据)读取


| CQL 读取的字段                                                          | v3 状态   | 影响                                  |
| ------------------------------------------------------------------ | ------- | ----------------------------------- |
| `table_info.database` / `schema_name` / `table_name` / `comment`   | ✓ 存在    | 正常                                  |
| `table_profile.physical_constraints.primary_key.columns`           | ✓ 存在    | 正常                                  |
| `table_profile.physical_constraints.unique_constraints[].columns`  | ✓ 存在    | 正常                                  |
| `table_profile.physical_constraints.foreign_keys[].source_columns` | ✓ 存在    | 正常                                  |
| `table_profile.indexes[].columns`                                  | ✓ 存在    | 正常                                  |
| `table_profile.unique_column_sets[].confidence_score / columns`    | ✓ 存在    | 正常                                  |
| `table_profile.table_category`                                     | ✓ 存在    | 正常                                  |
| `column_profiles[col].data_type`                                   | ✓ 存在    | 正常                                  |
| `column_profiles[col].comment`                                     | ✓ 存在    | 正常                                  |
| `column_profiles[col].semantic_analysis.semantic_role`             | ✓ 存在    | 正常                                  |
| `column_profiles[col].structure_flags`                             | ✗ v3 删除 | **无影响**(`reader.py:298` 读出后未使用,死代码) |
| `column_profiles[col].statistics.uniqueness`                       | ✗ v3 删除 | **功能缺口**:Cypher 列节点属性恒 0.0          |
| `column_profiles[col].statistics.null_rate`                        | ✗ v3 删除 | **功能缺口**:Cypher 列节点属性恒 0.0          |




### 13.2 从 output/rel/(关系结果)读取


| CQL 读取的字段                                                | v3 状态 | 影响               |
| -------------------------------------------------------- | ----- | ---------------- |
| `relationships[].from_table / to_table({schema, table})` | ✓ 存在  | 正常               |
| `relationships[].from_column / to_column`(单列)            | ✓ 存在  | 正常               |
| `relationships[].from_columns / to_columns`(复合)          | ✓ 存在  | 正常               |
| `relationships[].type`(single_column / composite)        | ✓ 存在  | 正常               |
| `relationships[].cardinality`                            | ✓ 存在  | 正常(1:N 方向翻转逻辑不变) |
| `relationships[].constraint_name`                        | ✓ 存在  | 正常               |




### 13.3 CQL 修复清单

1. `statistics.uniqueness` / `null_rate` → 改为按 `unique_count` / `null_count`
  现算(推荐调用契约层 `MetadataDocument.column_uniqueness()` /
   `column_null_rate()`,统计不足时区分 `None` 与 0);
2. 顺带删除 `reader.py:298` 的 `structure_flags` 死读;
3. 其余字段无需改动(全部 v3 兼容)。

