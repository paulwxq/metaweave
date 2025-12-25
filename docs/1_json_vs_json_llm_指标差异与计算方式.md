# output/json vs output/json_llm：指标差异与计算方式（干货版）

对比范围：`output/json/*.json` vs `output/json_llm/*.json`（按文件名一一对应，本次共 13 对文件）。

## 1) 谁比谁“多了哪些指标/字段”（JSON 独有）

| 指标路径（字段） | `output/json` | `output/json_llm` | 该指标如何计算/产生（核心口径） |
|---|---:|---:|---|
| `column_profiles.*.semantic_analysis`（`semantic_role`/`semantic_confidence`/`inference_basis`） | ✅ | ❌ | 规则引擎列语义分类：在 `metaweave/core/metadata/profiler.py` 中按优先级依次识别 `audit → datetime → identifier → description → enum(仅简单双值) → metric → attribute`；输入包含列名模式匹配、数据类型、结构约束（PK/FK/唯一/索引、复合成员）与采样统计（如 `uniqueness`、`unique_count` 等）；`inference_basis` 记录命中规则（如 `audit_pattern:*`、`metric_pattern:*`、`numeric_type`、`fallback_attribute`）。 |
| `column_profiles.*.role_specific_info`（`identifier_info`/`metric_info`/`datetime_info`/`enum_info`/`audit_info`/`description_info`/`primary_key_info`/`foreign_key_info`/`index_info`） | ✅ | ❌ | 基于 `semantic_analysis.semantic_role` + 物理约束进一步展开的“角色细节”：例如 `identifier_info.is_surrogate = not is_foreign_key`；`metric_info` 的 `metric_category` 由列名关键词判定并给出建议聚合；`primary_key_info`/`foreign_key_info`/`index_info` 来自约束/索引元数据。实现见 `metaweave/core/metadata/models.py#ColumnProfile.to_dict` 与 `metaweave/core/metadata/profiler.py`。 |
| `table_profile.confidence` | ✅ | ❌ | 表类型置信度（0~1）：规则分类输出的一部分，基于列语义统计（metric/identifier/datetime 数量）、FK 数量、表名模式、表注释关键词等加权计算；实现见 `metaweave/core/metadata/profiler.py#_classify_table`。 |
| `table_profile.inference_basis` | ✅ | ❌ | 表类型判定依据列表（如 `fact_has_metric`、`dim_has_primary_key`、`bridge_fk_threshold` 等），由 `_classify_table` 在命中条件时写入。 |
| `table_profile.column_statistics`（`identifier_count`/`metric_count`/`datetime_count`/`audit_count`/`attribute_count`/`primary_key_count`/`foreign_key_count`…） | ✅ | ❌ | 由列级 `semantic_role` + 结构约束汇总计数；实现见 `metaweave/core/metadata/profiler.py#_calculate_column_summary`。 |
| `table_profile.fact_table_info` / `dim_table_info` / `bridge_table_info` | ✅ | ❌ | 表类型特定信息：`fact` 输出 `grain/metrics/dimensions/time_dimension`；`dim` 输出 `natural_key/surrogate_key/attributes`；`bridge` 输出 `foreign_key_pairs/weight_columns`；构造逻辑见 `metaweave/core/metadata/profiler.py#_profile_table`。 |
| `table_profile.logical_keys.candidate_primary_keys[]`（`columns`/`confidence_score`/`uniqueness`/`null_rate`） | ✅ | ❌ | 逻辑主键候选（仅在“无物理主键”时尝试）：先筛选满足 `uniqueness==1.0 && null_rate==0.0` 的单列/复合列组合，再计算置信度并保留最小候选键；置信度：`0.3*name_score + 0.4*uniqueness + 0.2*(1-null_rate) + 0.1*type_score`。实现见 `metaweave/core/metadata/logical_key_detector.py` 与 `metaweave/utils/data_utils.py#calculate_uniqueness/calculate_null_rate`。 |

## 2) 同名指标但“计算方式不同 / 口径不同”（重点）

| 指标路径（字段） | `output/json` 口径 | `output/json_llm` 口径 | 本次目录的可观测差异 |
|---|---|---|---|
| `table_info.comment` / `table_info.comment_source` | 来自 DDL 解析（本次 `comment_source` 全为 `ddl`）。`json` 步骤走 `MetadataGenerator._process_table_from_ddl`。 | 以数据库系统注释为主（`comment_source=db`）；若缺失且启用注释生成，则用 LLM 补齐并标记 `llm_generated`（见 `LLMJsonGenerator._merge_and_save`）。 | 表注释来源：`json`=13×`ddl`；`json_llm`=9×`db` + 4×`llm_generated`。列注释来源：`json`=60×`ddl`；`json_llm`=41×`db` + 19×`llm_generated`。 |
| `table_info.total_rows` / `sample_records.total_rows` | 会额外执行 `SELECT COUNT(*)` 回填 `metadata.row_count`，再写入 `total_rows`（见 `metaweave/core/metadata/generator.py#_process_table_from_ddl`）。 | 直接使用 `MetadataExtractor` 得到的 `metadata.row_count`；该路径不做 `COUNT(*)`，默认常为 0（见 `metaweave/core/metadata/llm_json_generator.py#_build_simplified_json/_build_sample_records`）。 | 本次 `json` 目录 13/13 表 `total_rows>0`；`json_llm` 目录 0/13 表 `total_rows>0`（全部为 0）。 |
| `table_profile.table_category` | 规则引擎分类（输出同时包含 `confidence`/`inference_basis`）。 | **每张表都会被 LLM 结果覆盖**（无 `confidence`/`inference_basis`）。 | 表类型不一致 3 张：`public.employee.json`（`fact→dim`）、`public.order_header.json`（`dim→fact`）、`public.order_item.json`（`bridge→fact`）。 |
| `column_profiles.*.structure_flags.is_unique` | 基于采样统计判断“数据唯一”（`uniqueness==1.0`）且**不存在唯一约束**时置为 `true`；见 `metaweave/core/metadata/profiler.py#_is_unique` 与 `StructureFlags(is_unique=...)`。 | 固定为 `false`（仅保留“唯一约束/复合唯一约束成员”的标记）；见 `metaweave/core/metadata/llm_json_generator.py#_build_structure_flags`。 | 本次 `json` 有 23/60 列 `is_unique=true`；`json_llm` 为 0/60。 |

## 3) 两边一致但常被拿来当“指标”的统计口径（用于理解上面差异）

| 指标路径（字段） | 计算方式（两边一致） | 实现位置 |
|---|---|---|
| `column_profiles.*.statistics.uniqueness` | `unique_count / sample_count`（四舍五入到 4 位小数）。 | `metaweave/utils/data_utils.py#calculate_uniqueness` |
| `column_profiles.*.statistics.null_rate` | `包含空值的行数 / sample_count`（对单列等价于 `null_count/sample_count`，四舍五入到 4 位）。 | `metaweave/utils/data_utils.py#calculate_null_rate` |
| `column_profiles.*.statistics.*`（`sample_count/unique_count/null_count/min/max/mean/...`） | 基于采样 DataFrame：`sample_count=len(col)`、`unique_count=nunique()`、`null_count=isnull().sum()`；数值列补充 `min/max/mean`；字符串列补充长度统计；低基数补充 `value_distribution`。 | `metaweave/utils/data_utils.py#get_column_statistics` |
