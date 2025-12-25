# json_llm 串行化改造规划（基于 json 全量输出后再 LLM 增强）

## 目标

把 `--step json_llm` 从“独立生成一份精简 JSON（output/json_llm）”改为“串行两段式”：
1) 先完全按 `--step json` 的既有逻辑生成 **全量 schema JSON**（包含 column_profiles、semantic_analysis、role_specific_info、logical_keys、table_profile 的规则推断等所有现有字段）。
2) 再调用 LLM **仅对两类内容做增量/覆盖式修改**，其余字段不删除、不裁剪，保持原样：
   - 表类型：用 LLM 结果覆盖 `table_profile.table_category`（`fact/dim/bridge/unknown`），并可选写入 `table_profile.table_domains`（如启用 domain）。
   - 注释增强：按配置对表/字段 comment 做“缺失补齐”或“覆盖更新”，并正确维护 `comment_source`。

输出路径调整：执行 `--step json_llm` 后，结果统一写入 `output/json`（不再写 `output/json_llm`）。

> 说明：这会影响 `rel_llm/cql_llm` 等下游读取目录的行为（本规划不包含下游改造）。

## 现状梳理（代码现状）

- `--step json`：`metaweave/core/metadata/generator.py` 生成全量元数据 JSON（带规则推断与 logical_keys），输出到 `output.json_directory`（默认 `output/json`）。
- `--step json_llm`：`metaweave/core/metadata/llm_json_generator.py` 直接生成“简化版 JSON”，并让 LLM 生成 `table_category` + 注释，输出到 `output.json_llm_directory`（默认 `output/json_llm`）。该版本会缺失 `semantic_analysis/role_specific_info/logical_keys/confidence/inference_basis/...` 等字段（属于“裁剪版”而不是“增量版”）。

## 改造后的目标执行流程（串行）

### 阶段 A：先跑全量 json 生成（不改变 json 的逻辑）

1. 走 `metaweave/core/metadata/generator.py` 的完整流程生成每张表 JSON：
   - DDL/DB 元数据提取
   - 采样统计写入 `column_profiles.*.statistics`
   - 规则语义推断写入 `semantic_analysis/role_specific_info`
   - 逻辑主键检测写入 `table_profile.logical_keys`
   - 规则表分类写入 `table_profile.table_category/confidence/inference_basis/...`
2. 输出到 `output/json`（保持原路径）。

### 阶段 B：LLM 增强（对全量 json 做“定点修改”）

对 `output/json/*.json` 逐表读取并就地更新（或写临时文件再原子替换）：

1. 表类型覆盖（强制执行）
   - 对每张表调用 LLM，得到 `table_profile.table_category`（以及可选的 `table_profile.table_domains`）。
   - 覆盖写入到 JSON 中。
   - 同步调整“与表类型判断相关字段”的口径：
     - 推荐：让 LLM 同时返回 `confidence` 与 `inference_basis`（或 `reason`），以替代规则推断的同名字段，避免出现 “table_category 是 LLM，但 confidence/inference_basis 是规则” 的语义撕裂。
     - 若不希望扩大输出字段：至少写入 `table_profile.inference_basis=["llm_inferred"]`，并将原值保留到新字段（见“字段保留策略”）。

2. 注释增强（按配置执行）
   - 表注释（`table_info.comment`）：
     - 缺失补齐：仅当 comment 为空/空白时生成并写入，`comment_source="llm_generated"`。
     - 覆盖更新：当 `overwrite_existing=true` 时允许覆盖已有注释并标记 `comment_source="llm_generated"`。
     - 否则保留原 comment 与原 `comment_source`（`ddl/db/...`）。
   - 字段注释（`column_profiles.*.comment`）同理，逐列按“缺失/覆盖”策略更新，并维护 `comment_source`。

3. 产物写回 `output/json`（不再写 `output/json_llm`）。

## 关键设计点

### 1) LLM 输入“视图”与 Token 控制

全量 json 文件可能很大（含 statistics/value_distribution/role_specific_info 等），直接把整份 json 塞给 LLM 风险高（成本、超 token、噪声）。

建议实现一个 “LLM 输入裁剪视图”（只用于 prompt，不影响最终输出保留全量字段）：
- 表级：table_info（name/comment）、table_profile.physical_constraints、（可选）table_profile.table_domains
- 列级：column_name、data_type、comment、structure_flags、statistics（可降维：仅保留 sample_count/unique_count/null_rate/uniqueness/value_distribution 的 topK）
- 样例：sample_records.records（限制行数/列数）
- 明确指示：`logical_keys`、`is_unique` 等属于采样推断，弱参考，不能当结论

该裁剪逻辑可以复用/迁移 `metaweave/core/metadata/llm_json_generator.py#_build_simplified_json_for_llm` 的思路，但输入源改为“全量 json”。

### 2) 字段保留策略（不删除原 json 字段）

需求要求“不执行删除策略，保留原有所有属性”，因此：
- 对表类型：覆盖 `table_profile.table_category` 是硬要求；但为了可追溯/不丢信息，可新增保留字段：
  - `table_profile.table_category_rule_based`（原规则结果）
  - `table_profile.confidence_rule_based` / `table_profile.inference_basis_rule_based`
  - `table_profile.table_category_source`（如 `llm`）
- 对注释：覆盖时会改变 `comment/comment_source`；可选保留旧值到：
  - `table_info.comment_original` / `column_profiles.*.comment_original`（仅当发生覆盖时写入）

> 是否新增这些“保留字段”需要确认下游 schema 兼容性；但它不会删除原字段，符合“保留”要求。

### 3) “判断方法也改为 json_llm 的方式”的落地

表类型判断相关字段至少要做到一致性：
- 推荐：调整 LLM 输出 schema，使其返回：
  - `table_category`（必填）
  - `confidence`（0~1，可选但强烈建议）
  - `inference_basis`（短标签数组，例如 `["comment_semantics","name_pattern","column_role_mix","constraints"]`）
  - （可选）`table_domains`
- 然后用这些值覆盖 `table_profile.table_category/confidence/inference_basis/(table_domains)`，并把规则结果写入 `*_rule_based` 备份字段。

### 4) 执行入口与代码组织

建议在 CLI 的 `--step json_llm` 入口实现“管道编排”，并新增一个专门的 post-processor：
- `metaweave/cli/metadata_cli.py`：json_llm step 改为：
  1) 调用现有 `MetadataGenerator(...).generate(step="json")`
  2) 调用新的 `JsonLlmEnhancer(...).enhance_json_directory(output/json)`
- 新增模块：`metaweave/core/metadata/json_llm_enhancer.py`（命名可调整）
  - 负责加载 json 文件、构建 LLM 输入视图、调用 LLM、合并回写
  - 支持异步并发与分批（可复用 `LLMService.batch_call_llm_async`）

## 配置与参数规划

沿用现有配置并补齐差异：
- 表类型/注释增强开关：沿用 `comment_generation.*` + 新增/复用 `overwrite_existing`（目前只在 `llm_json_generator.py` 内部有该含义，需落到新 enhancer）
- LLM 并发与 batch：沿用 `llm.langchain_config.use_async/batch_size/async_concurrency`
- 样例截断：沿用 `comment_generation.max_sample_rows/max_sample_cols` 或为关系/分类新增独立配置段
- 输出目录：
  - `json_llm` step 最终写 `output.json_directory`
  - `output.json_llm_directory` 未来可保留但不使用（或作为兼容开关）

## 实施步骤（建议分 PR / 分阶段）

1. 增加 `JsonLlmEnhancer`（或同等组件）
   - 读取 `output/json/*.json`
   - 生成 LLM 输入裁剪视图
   - 生成表类型（含可选 domains）与注释增强结果
   - 合并并写回原 JSON（建议先写到临时文件再 replace）
2. 改写 CLI：`--step json_llm` 串行执行 A+B，并把最终输出落到 `output/json`
3. 新增/调整配置项：支持 overwrite、LLM 输出 confidence/inference_basis、样例截断等
4. 增加最小化的验证脚本/测试：
   - 断言 json_llm 运行后 `output/json` 中仍包含 `semantic_analysis/role_specific_info/logical_keys` 等字段
   - 断言 `table_profile.table_category` 已被覆盖且 `comment_source` 按策略更新
5. 文档更新：说明 `json_llm` 行为变化、对下游（rel_llm/cql_llm）的影响与迁移建议

## 风险与注意事项

- Token/成本：全量 json 直接喂给 LLM 可能成本爆炸；必须实现裁剪视图。
- 语义一致性：覆盖 `table_category` 后若不处理 `confidence/inference_basis`，会造成字段语义冲突；建议同步覆盖并保留规则值到备份字段。
- 覆盖策略：需要明确“缺失”判定（空字符串/仅空白/None）与覆盖时是否保留旧值备份。
- 并发：LLM 调用要支持 retry、并发限制、失败降级（失败时保留原值并记录）。

