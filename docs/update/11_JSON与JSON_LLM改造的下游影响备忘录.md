# MetaWeave JSON 与 JSON_LLM 改造的下游影响备忘录

## 1. 文档目的

本备忘录用于记录 `--step json` 和 `--step json_llm` 完成 JSON 元数据格式改造后，后续流程需要适配的范围。

字段级新旧格式对照、替换策略和完整 v3 模板以 [10_JSON元数据格式精简与迁移方案](./10_JSON元数据格式精简与迁移方案.md) 为准。本文只记录影响范围、后续步骤和相关代码文件，不展开具体实现。

## 2. 当前改造边界

本阶段只以下列两个步骤为功能修改目标：

- `metaweave metadata --step json`
- `metaweave metadata --step json_llm`

本阶段不修改 `rel`、`rel_llm`、`cql`、`cql_llm`、加载器和维表配置生成器的业务逻辑。如果 JSON 改造需要修改共享的元数据模型或抽取代码，必须确认 `ddl` 和 `md` 的现有产物没有非预期变化；无法隔离的共享行为变更应单独记录并延后实施。

本阶段可涉及的代码主要集中在：

- `metaweave/core/metadata/models.py`
- `metaweave/core/metadata/profiler.py`
- `metaweave/core/metadata/logical_key_detector.py`
- `metaweave/core/metadata/formatter.py`
- `metaweave/core/metadata/generator.py`
- `metaweave/core/metadata/json_llm_enhancer.py`
- `metaweave/core/metadata/metadata_document.py`（计划新增）
- `metaweave/cli/metadata_cli.py` 中与 `json` / `json_llm` 直接相关的分支
- `configs/metadata_config.yaml` 及相关配置校验
- `tests/unit/metaweave/metadata/` 和 `tests/unit/metaweave/test_json_llm_enhancer.py`

`extractor.py`、`sql_templates.py` 等共享抽取代码只能在 JSON 所需权威事实无法通过其他方式获得时修改，并必须对 `ddl` 产物做回归检查。

## 3. 主要产物变化

后续流程需要关注的 JSON 契约变化包括：

- 新格式 v3 直接替换 v2，不提供双版本输出或读取兼容。
- 删除持久化 `structure_flags`，改由统一访问器从权威事实推导。
- 将字段画像样本数提升到 `profiling.sample_count`。
- 删除字段级 `null_rate` 和 `uniqueness` 的持久化值，改由访问器计算。
- 将长度和精度合并进完整 `data_type` 字符串。
- 索引增加 `key_expressions` 和 `included_columns`，并改变 `columns` 的精确语义。
- 增加 `classification_source`、`classification_reason` 和 `rule_based_classification` 的联动契约。
- 删除重复字段、角色专属信息和表级派生汇总。
- 简化 `sample_records`，但保持 DDL、JSON 和 MD 样例的同源契约。
- `table`、`view` 和 `materialized_view` 使用同一 JSON 主结构，由 `table_info.table_type` 区分。

## 4. 后续流程影响总览

| 后续步骤或能力 | 影响类型 | 主要受影响内容 | 当前阶段是否修改 |
|---|---|---|---|
| `metadata --step rel` | 直接 | 字段结构标志、统计比例、索引和逻辑主键读取 | 否 |
| `metadata --step rel_llm` | 直接 | 与 `rel` 共享的候选与评分流程，以及 LLM 提示词的 JSON 白名单 | 否 |
| `metadata --step cql` | 直接 | 对象、字段类型、统计、约束、索引和逻辑主键读取 | 否 |
| `metadata --step cql_llm` | 直接 | 与 `cql` 使用相同的 JSON 读取逻辑 | 否 |
| `dim_config --generate` | 直接 | 数据库、schema、对象名和表分类 | 否 |
| Table Schema Loader | 直接 | 表分类、字段类型和时间字段提示 | 否 |
| `metadata --step standard` | 编排影响 | `json` 之后的 `rel` 和 `cql` 在适配前不能作为 v3 全流程验收 | 否 |
| `pipeline generate` | 编排影响 | `json_llm` 之后的 `dim_config`、`rel_llm` 和 `cql` | 否 |
| `pipeline load` | 直接与间接 | Table Schema Loader 直接读 JSON；CQL Loader 读取上游 CQL 产物 | 否 |
| Domain 生成 | 无直接影响 | 读取 MD 和配置，不读取 `output/json` | 否 |
| SQL RAG 生成与校验 | 无直接影响 | 读取 MD、SQL 和配置，不直接读取 `output/json`；可能因前置编排失败而未执行 | 否 |

## 5. 关系发现流程

### 5.1 影响内容

- 物理主键、唯一约束和索引的候选准入。
- 逻辑主键 `unique_column_sets` 的读取。
- 字段 `data_type`、`semantic_role`、`null_rate` 和 `uniqueness` 的获取。
- 单列和复合索引候选，包括表达式索引和 `INCLUDE` 列的排除。
- `rel_llm` 的 LLM 输入裁剪、候选去重和返回后过滤。
- 视图和物化视图是否参与关系发现的对象选择。

### 5.2 后续代码文件

- `metaweave/core/relationships/pipeline.py`
- `metaweave/core/relationships/repository.py`
- `metaweave/core/relationships/candidate_generator.py`
- `metaweave/core/relationships/decision_engine.py`
- `metaweave/core/relationships/scorer.py`
- `metaweave/core/relationships/type_compatibility.py`
- `metaweave/core/relationships/llm_relationship_discovery.py`
- `metaweave/core/relationships/writer.py`
- `metaweave/cli/metadata_cli.py` 中的 `rel` / `rel_llm` 分支

### 5.3 后续回归测试

- `tests/metaweave_relationships/`
- `tests/unit/metaweave/relationships/`
- `tests/test_composite_matching.py`
- `tests/test_two_stage_matching.py`

## 6. CQL 与 Neo4j 产物流程

### 6.1 影响内容

- 当前 v3 JSON 的读取和版本检查。
- 对象类型、表分类、字段类型与字段语义的读取。
- 主键、外键、唯一约束、索引和逻辑主键的图属性生成。
- 完整 `data_type` 字符串导致的 CQL 文本预期变化。
- 视图和物化视图在图谱中的节点类型和属性。

### 6.2 后续代码文件

- `metaweave/core/cql_generator/generator.py`
- `metaweave/core/cql_generator/reader.py`
- `metaweave/core/cql_generator/models.py`
- `metaweave/core/cql_generator/writer.py`
- `metaweave/cli/metadata_cli.py` 中的 `cql` / `cql_llm` 分支

### 6.3 后续回归测试

- `tests/unit/metaweave/cql_generator/test_cql_generator.py`
- `tests/unit/metaweave/cql_generator/test_cypher_writer_metadata.py`
- `tests/unit/metaweave/cql_generator/test_import_all_cypher_ids.py`

Neo4j CQL Loader 不直接读取 JSON，但它加载的 CQL 由该流程生成，因此属于间接受影响的下游能力。

## 7. 向量加载与维表配置

### 7.1 Table Schema Loader

直接读取 `output/json` 的表分类和字段类型，后续需要通过统一访问器读取 v3，并确认视图和物化视图是否进入向量化范围。

相关代码：

- `metaweave/core/loaders/table_schema_loader.py`
- `metaweave/core/table_schema/json_extractor.py`
- `metaweave/core/table_schema/models.py`
- `tests/unit/metaweave/table_schema/test_json_extractor.py`
- `tests/unit/metaweave/table_schema/test_table_schema_loader.py`

Milvus 或后续 pgvector 适配器不直接解析此 JSON，但向量文本和元数据由 Table Schema Loader 构造，因此受间接影响。

### 7.2 Dim Config

`dim_config --generate` 直接读取 `table_info` 和 `table_profile.table_category`。主要字段路径在 v3 中保持，但仍应通过统一访问器完成版本检查和对象类型策略。

相关代码：

- `metaweave/core/dim_value/config_generator.py`
- `metaweave/cli/dim_config_cli.py`
- `tests/unit/metaweave/dim_value/test_config_generator.py`

Dim Value Loader 不直接读取元数据 JSON，但使用 Dim Config 生成结果，属于间接影响。

## 8. CLI 与流水线编排

### 8.1 `metadata --step standard`

`standard` 在执行 `json` 后会继续执行 `rel` 和 `cql`。下游读取器尚未适配 v3 时，不应使用完整 `standard` 作为本阶段的 v3 验收命令。

当前 `standard` 的步骤列表不含 `json_llm`，但循环内部仍保留
`elif child_step == "json_llm"`，属于不可达死代码。JSON 单步改造阶段不删除它，也不
修改 `standard` 编排；待各单步改造完成并统一串联流程时，再与旧 `json_llm` 入口一起
清理。

### 8.2 `pipeline generate`

当前顺序为：

```text
ddl → md → generate-domains → json_llm → dim_config
    → rel_llm → cql → sql-rag-generate → sql-rag-validate
```

`json_llm` 之后有三个直接 JSON 消费步骤：`dim_config`、`rel_llm` 和 `cql`。它们完成 v3 适配前，整条 `pipeline generate` 不能作为 v3 全流程验收。

按照后续的 JSON 入口统一方案，pipeline 还存在一个更早发生的编排冲突：当前
`_step_json_llm()` 先调用 `MetadataGenerator.generate(step="json")`，随后再显式调用
文件级 `JsonLlmEnhancer`。当新的 `json` 已在内存中完成可选 LLM 增强后，现有 pipeline
会让同一批文件再次进入增强流程，开启相应 LLM 任务时可能产生重复调用和重复合并。

另外，`pipeline generate` 会在启动阶段执行共享的模块级 LLM 配置校验。新配置路径
生效后，仍包含 `comment_generation` 或 `json_llm.llm` 的旧配置可能在任何 pipeline
步骤执行前直接失败。这里的“不修改 `pipeline_cli.py`”仅表示源码不在当前范围内，
不表示 pipeline 不受影响或仍然可用。

### 8.3 `pipeline load`

`pipeline load` 中的 Table Schema Loader 直接受影响；CQL Loader 通过上游 CQL 产物间接受影响。SQL Loader 不直接读取元数据 JSON。

后续需要复核的编排代码：

- `metaweave/cli/metadata_cli.py`
- `metaweave/cli/pipeline_cli.py`
- `tests/unit/metaweave/test_pipeline_domain_config.py`

## 9. 本阶段的运行限制

在下游 v3 读取适配完成前：

1. 本阶段的主验收命令只使用 `--step json` 和 `--step json_llm`。
2. 使用 `--step json --clean` 完整重建输出目录，不允许混入旧格式文件。
3. 不提供 `output.json_schema_version`；`json` 与 `json_llm` 只使用 v3。
4. 不使用 `metadata --step standard`、`pipeline generate` 或 `pipeline load` 判定本阶段 v3 改造失败，因为这些命令包含尚未迁移的下游步骤。
5. 实施 JSON 入口统一方案后，在 pipeline 完成适配前，只承诺独立的
   `metadata --step ddl` 和 `metadata --step json` 可用；`pipeline generate` 和
   `pipeline load` 的过渡期可用性不作保证。

## 10. 后续适配建议顺序

1. 稳定 `MetadataDocument` 的 v3 读取契约。
2. 适配 `rel` 和 `rel_llm`，优先锁定候选和关系结果回归。
3. 适配 `cql` 和 `cql_llm`，重建已批准变化后的 CQL 基线。
4. 适配 `dim_config` 和 Table Schema Loader。
5. 修改 `pipeline_cli.py`：删除旧 `_step_json_llm` 的二次文件增强，统一调用新的
   `json` 实现，并迁移 pipeline 使用的配置路径。
6. 统一串联流程时删除 `standard` 循环中不可达的
   `elif child_step == "json_llm"`，并重新确认最终步骤列表和顺序。
7. 恢复 `metadata --step standard`、`pipeline generate` 和 `pipeline load` 的全流程回归。
8. 后续 REST API 作业系统记录输入格式版本、输出格式版本和下游兼容状态。

## 11. 本阶段与后续阶段的验收边界

### 11.1 本阶段必须验收

- `--step json` 生成结构合法的 v3 JSON。
- `--step json_llm` 只读取并输出 v3，满足分类来源、reason 和规则备份的联动契约。
- v3 文件通过结构校验与访问器单元测试；旧格式明确失败。
- LLM 失败不覆盖上一次成功产物，不留下半完成 JSON。
- 原有 `ddl` 和 `md` 产物没有因共享代码改动产生非预期变化。

### 11.2 留待后续阶段验收

- `rel` 与 `rel_llm` 的候选、评分和最终关系结果。
- `cql` 与 `cql_llm` 的节点、属性和关系产物。
- `dim_config` 的维表集合。
- Table Schema Loader 的向量化文本和元数据。
- `metadata --step standard`、`pipeline generate` 和 `pipeline load` 的完整编排。
- 新配置下 pipeline 不重复调用 JSON LLM，旧配置失败时给出明确迁移提示。

## 12. 后续代码文件汇总

| 范围 | 后续需复核或修改的文件 |
|---|---|
| 关系发现 | `metaweave/core/relationships/pipeline.py`<br>`metaweave/core/relationships/repository.py`<br>`metaweave/core/relationships/candidate_generator.py`<br>`metaweave/core/relationships/decision_engine.py`<br>`metaweave/core/relationships/scorer.py`<br>`metaweave/core/relationships/type_compatibility.py`<br>`metaweave/core/relationships/llm_relationship_discovery.py`<br>`metaweave/core/relationships/writer.py` |
| CQL | `metaweave/core/cql_generator/generator.py`<br>`metaweave/core/cql_generator/reader.py`<br>`metaweave/core/cql_generator/models.py`<br>`metaweave/core/cql_generator/writer.py` |
| Table Schema Loader | `metaweave/core/loaders/table_schema_loader.py`<br>`metaweave/core/table_schema/json_extractor.py`<br>`metaweave/core/table_schema/models.py` |
| Dim Config | `metaweave/core/dim_value/config_generator.py`<br>`metaweave/cli/dim_config_cli.py` |
| CLI 编排 | `metaweave/cli/metadata_cli.py`<br>`metaweave/cli/pipeline_cli.py` |
| 关系回归 | `tests/metaweave_relationships/`<br>`tests/unit/metaweave/relationships/`<br>`tests/test_composite_matching.py`<br>`tests/test_two_stage_matching.py` |
| CQL 回归 | `tests/unit/metaweave/cql_generator/` |
| 加载和维表回归 | `tests/unit/metaweave/table_schema/`<br>`tests/unit/metaweave/dim_value/` |
| 流水线回归 | `tests/unit/metaweave/test_pipeline_domain_config.py`<br>补充 JSON 统一入口、配置迁移和禁止重复增强的测试 |

## 13. 结论

本阶段可以独立完成 JSON 产物契约和统一入口改造，但源码范围外的 pipeline 会因共享
生成器、增强器和配置校验器发生被动变化。在 `pipeline_cli.py` 删除二次增强并迁移配置
路径之前，不承诺 `pipeline generate` 或 `pipeline load` 可用。后续改造应以统一访问器
为边界，逐步迁移关系发现、CQL、维表配置和向量加载流程。
