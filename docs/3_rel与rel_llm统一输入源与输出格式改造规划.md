# rel / rel_llm 统一输入源与输出格式改造规划

> 目标：让 `--step rel` 与 `--step rel_llm` 都从 `output/json` 读取表元数据（统一 JSON 源），并在不影响 `--step cql` / `--step cql_llm` 读取关系 JSON 的前提下，尽量把两者的关系输出 JSON 结构对齐；同时让 `rel_llm` 也输出 `relationships_global.md`。
>
> 参考：`docs/3_rel_vs_rel_llm_命令对比与JSON兼容性评估.md`

---

## 0. 现状结论（基于代码与当前 output/json）

### 0.1 输入侧

- `--step rel` 已经读取 `output.json_directory`（`metaweave/core/relationships/pipeline.py:50-59`），当前实现天然兼容统一后的 `output/json`。
- `--step rel_llm` 仍读取 `output.json_llm_directory`（`metaweave/core/relationships/llm_relationship_discovery.py:219-227`），与“json/json_llm 合并到 output/json”的现状不一致。
- 当前 `output/json/*.json` 已包含 `rel` 与 `rel_llm` 所需的关键字段：
  - `table_profile.physical_constraints.*`（外键直通、唯一约束等）
  - `table_profile.logical_keys.candidate_primary_keys`（候选生成/打分）
  - `column_profiles.*.statistics / structure_flags / semantic_analysis`（候选生成/评分/决策/写出）
  - `sample_records.records`（`rel_llm` LLM 判断所需）

### 0.2 输出侧

- `--step rel` 通过 `RelationshipWriter.write_results()` 输出 **JSON + Markdown**（`metaweave/core/relationships/writer.py`），文件名为：
  - `output/rel/relationships_global.json`
  - `output/rel/relationships_global.md`
- `--step rel_llm` 当前只在 CLI 层写 `relationships_global.json`，**没有生成 md 总结**（`metaweave/cli/metadata_cli.py:307-363`）。
- 两者输出 JSON 的 top-level 字段、statistics 口径、relationship item 字段集存在差异（详见参考文档），但 `cql` 的读取逻辑对 top-level 扩展字段容忍度高（只关心 `relationships` 数组及其核心字段）。

---

## a) 让 rel_llm 使用 output/json：需要改哪些内容？

### 必改（代码路径）

1) `metaweave/core/relationships/llm_relationship_discovery.py`
- 把 `json_llm_directory` 改为读取 `output.json_directory`（与 `RelationshipDiscoveryPipeline` 同一策略）：
  - 优先 `output.json_directory`
  - fallback：`output.output_dir` + `/json`
- 同步把内部命名从 `json_llm_dir` 统一为 `json_dir`（减少误读与后续维护成本）
- 更新 docstring/注释/日志文案（例如“加载 json_llm 文件”→“加载 json 文件”）

2) `metaweave/cli/metadata_cli.py`（仅 rel_llm 分支的错误提示/检查）
- 目前 CLI 在 `rel_llm` 分支检查的是 `discovery.json_llm_dir.exists()`（`metaweave/cli/metadata_cli.py:332-337`）；当上面改为 `json_dir` 后，这里也要跟着改为检查 json 目录。
- 注意：你要求“暂时忽略下游仍依赖 json_llm_directory 的问题”，因此这里只改 `rel_llm` 分支即可。
- 同步修正文案：不再提示“简化版 JSON / json_llm 目录”，统一提示“请先生成 `output/json`（`--step json` 或 `--step json_llm`）”。

---

## b) rel / rel_llm 是否兼容当前 output/json 的文件格式？

### `--step rel`：✅ 兼容

`rel` 全链路从 `MetadataRepository` → `CandidateGenerator` → `RelationshipScorer` → `DecisionEngine` → `RelationshipWriter` 访问字段均通过 `.get()` 且与当前 `output/json` 中字段结构匹配。

### `--step rel_llm`：✅ 兼容（有一个条件分支例外）

默认不使用 `--domain/--cross-domain` 时，`rel_llm` 使用：
- `sample_records.records` 构 prompt
- `table_profile.physical_constraints.foreign_keys` 提取物理外键并去重
- `RelationshipScorer` 评分（依赖 column_profiles 的统计/标志位）

这些字段在当前 `output/json` 均存在，故兼容。

**例外：domain 过滤模式**
- `rel_llm` 在启用 `--domain` 或 `--cross-domain` 时会强制校验 `table_profile.table_domains`（`metaweave/core/relationships/llm_relationship_discovery.py:359-377`），而当前统一后的 JSON 文件一般不包含该字段（取决于你是否生成 domains）。
- 该问题不影响本次“统一 json_dir”目标，但会影响 domain 模式可用性。

本次改造不调整 domain 模式的前置条件：若使用 `--domain/--cross-domain`，要求输入 JSON 已包含 `table_profile.table_domains`；否则按现有逻辑直接报错退出（domain 生成/补齐属于后续任务）。

---

## c) 对齐 rel vs rel_llm 输出 JSON：不影响 cql/cql_llm 的前提下尽量兼容

### 关键事实：cql 只依赖 relationships 数组的核心字段

`metaweave/core/cql_generator/reader.py:_read_relationships()` 只读取：
- top-level：`relationships` 数组
- 每条 relationship：`from_table/to_table`、`type`、`cardinality`、`from_column|from_columns`、`to_column|to_columns`

因此：
- **允许增加 top-level metadata 字段**
- **允许让 statistics 更丰富**
- **允许在 relationship item 上补充字段**
只要保留上述核心字段即可。

### 统一输出基线（固定采用）：RelationshipWriter v3.2

原因：
- `rel` 已经使用 `RelationshipWriter` 产出 JSON+MD（稳定）
- `RelationshipWriter` 产出的 relationship item 字段更完整（含 `discovery_method`、`metrics`、`confidence_level`、`target_source_type`、`source_constraint` 等）

### 具体对齐策略

1) `rel` 保持现状：继续由 `RelationshipWriter.write_results()` 输出 `relationships_global.json/md`

2) `rel_llm` 改造为也走 `RelationshipWriter.write_results()`：
- 将 `LLMRelationshipDiscovery` 最终产出的“物理外键关系 + LLM 推断关系”转换成 `List[Relation]`
  - `relationship_id`: 复用现有计算逻辑
  - `relationship_type`: foreign_key / inferred
  - `source_schema/table/columns` 与 `target_schema/table/columns`：从候选里映射
  - `composite_score` / `score_details`：从 LLM 打分结果映射（当前 rel_llm 字段名为 `metrics`，需要转成 `score_details`）
  - `inference_method`: 固定写 `"llm_assisted"`（用于 writer 的 discovery_method 映射）
- `suppressed`：固定传空数组（`[]`）（rel_llm 当前无 suppressed 概念）
- `tables`：直接传 `tables`（用于 writer 获取 source_constraint / target_source_type 的结构化标记）

3) 扩展 writer 的 discovery_method 映射以保留 rel_llm 的语义

当前 `RelationshipWriter._parse_discovery_info()` 不认识 `"llm_assisted"`，会 fallback 为 `standard_matching`。

本次固定采用“最小改动”：补一个分支即可：
- inference_method == `"llm_assisted"` → `discovery_method="llm_assisted"`, `target_source_type="llm_inferred"`, `source_constraint=None`

4) statistics 字段尽量对齐

`RelationshipWriter` 当前固定输出 v3.2 的统计字段：
- `total_relationships_found`
- `foreign_key_relationships`
- `composite_key_relationships`
- `single_column_relationships`
- `total_suppressed_single_relations`
- `active_search_discoveries`
- `dynamic_composite_discoveries`

rel_llm 将：
- 继续输出上述 v3.2 字段；**rel_llm 无对应概念的统计项统一填 0**（例如：`total_suppressed_single_relations` / `active_search_discoveries` / `dynamic_composite_discoveries`）
- 额外追加（不影响 cql）：`llm_assisted_relationships`、`rejected_low_confidence`（无数据时填 0）

说明（基于当前代码的最小实现方式）：
- 若 `rel_llm` 复用 `RelationshipWriter` 输出 v3.2 JSON，则 v3.2 标准字段会由 writer 自动计算并稳定输出。
- `rel_llm` 只需确保：
  - 推断关系的 `Relation.inference_method="llm_assisted"`（用于计数与 discovery_method 映射）
  - `Relation.relationship_type` 正确区分 `foreign_key` / `inferred`
  - 单列/复合键通过 `Relation.source_columns` 长度自然区分（writer 会自动计算 `single_column_relationships/composite_key_relationships`）
- 本次不增加 `llm_api_calls`：它与“表对数量/批次数”相关，而不是与“最终关系条数”一一对应，容易误导。

实现方式（必做）：
- 给 `RelationshipWriter.write_results()` 增加参数 `extra_statistics: Dict[str, Any] = None`，合并进 `data["statistics"]`
  - 不修改 `_calculate_statistics_v32()` 的核心逻辑
  - `rel_llm` 注入额外统计（如 `llm_assisted_relationships`、`rejected_low_confidence`）
  - v3.2 标准字段仍由 writer 统一计算

---

## d) 增加字段区分“由哪个命令生成”（必须实现）

### 现状

- `rel_llm` 输出目前有 `metadata_source: "json_llm_files"`（`LLMRelationshipDiscovery._build_output()`），但这个字段更像“输入来源/历史遗留”，并不能稳定表达“生成命令/生成算法”（尤其在你把输入目录统一到 `output/json` 后）。
- `rel` 输出固定写 `metadata_source: "json_files"`（`RelationshipWriter._write_json_v32()`），同样无法区分“规则推断 vs LLM 辅助”。

### 必须：增加明确的生成标识（不影响 cql）

在关系 JSON top-level 增加一个字段（必做）：

**必做**：
- `generated_by: "rel" | "rel_llm"`（明确“由哪个命令/模式生成”）

**实现示例（关系 JSON 顶层，省略部分字段）**：

```json
{
  "generated_by": "rel_llm",
  "metadata_source": "json_files",
  "analysis_timestamp": "2025-12-26T10:10:00Z",
  "statistics": {},
  "relationships": []
}
```

注：当前关系 JSON（v3.2 writer 输出）使用的是 `analysis_timestamp` 字段（见 `metaweave/core/relationships/writer.py:140-158`），不是 `generated_at`（`generated_at` 是 Step2 表元数据 JSON 的字段）。

实现提示（代码层面）：
- `RelationshipWriter.write_results()` 增加参数 `generated_by: str = "rel"`（写入 JSON 顶层；md 不做来源区分）
- CLI 调用：
  - `rel` 分支：传 `generated_by="rel"`
  - `rel_llm` 分支：传 `generated_by="rel_llm"`

#### 关于 `metadata_source` 是否删除？

本次改造**不删除** `metadata_source`：
- 当前 `RelationshipWriter` 与单测仍依赖该字段（例如 `tests/unit/metaweave/relationships/test_writer.py:95-101`）。
- 输入源统一到 `output/json` 后，`metadata_source="json_files"` 对 `rel` / `rel_llm` 都是成立的，不再产生“json_llm_files”那种误导。
- “生成命令/模式”的区分由新增的 `generated_by` 承担，语义更清晰。

如需移除 `metadata_source`，按“先标记 deprecated + 更新文档/测试 + 再删除”的两步法推进（后续任务）。

---

## e) rel_llm 是否缺少 md 总结？如何补齐？工作量大吗？

### 现状确认：✅ 确实缺少

- `rel`：`RelationshipWriter.write_results()` 会写 `relationships_global.md`（`metaweave/core/relationships/writer.py:86-90,560-646`）
- `rel_llm`：当前 CLI 仅写 `relationships_global.json`，未调用 `RelationshipWriter`，因此不会产出 md（`metaweave/cli/metadata_cli.py:307-363`）

### 实现方式（固定采用）：复用 RelationshipWriter

一旦按 c) 的方案让 `rel_llm` 也走 `RelationshipWriter.write_results()`：
- md 文件会自动生成，路径与 `rel` 完全一致（`output/rel/relationships_global.md`）

### 工作量评估

- **中等偏小**：核心工作是把 `rel_llm` 现有的 dict 关系结果转换为 `Relation` 对象，并让 `RelationshipWriter` 支持 `"llm_assisted"` 的 discovery_method 映射（小改动）。
- 不需要改 `cql`/`cql_llm`（它们只读 `relationships_*.json`）。

---

## f) 改造实施步骤（固定顺序）

1) **输入目录统一（必做）**
- 修改 `LLMRelationshipDiscovery` 从 `output.json_directory` 读取
- CLI `rel_llm` 的目录检查与日志同步更新

2) **输出对齐（必做）**
- 让 `rel_llm` 也使用 `RelationshipWriter.write_results()` 输出 JSON + MD
- 统一输出文件名仍为 `relationships_global.json/md`

3) **补充生成来源标识（必须，便于排查问题）**
- 在关系 JSON 顶层加 `generated_by`

4) **兼容性自检（本地可验证）**
- 用同一份 `output/json`：
  - 跑 `--step rel` 生成 `relationships_global.json/md`
  - 跑 `--step rel_llm` 生成 `relationships_global.json/md`
- 验证 `--step cql` 能读取 `output/rel/relationships_*.json` 正常生成 CQL（重点验证 `_extract_join_relation` 的 cardinality/列翻转逻辑）。
- `--step cql_llm` 的输入目录统一属于下一阶段，但本次改造保证关系 JSON 的核心字段不变，格式对其解析保持兼容。

---

## 变更点清单（便于落地）

### 必改文件（本次必做）

- `metaweave/core/relationships/llm_relationship_discovery.py`
  - 输入目录改为 `output.json_directory`
  - 输出阶段改为产出 `List[Relation]`（并返回 rejected 统计给 CLI 用于写入 extra_statistics）
- `metaweave/core/relationships/writer.py`
  - 增加 `llm_assisted` 的 inference_method 映射
  - 支持 `generated_by` 参数注入（必须）
  - 支持 `extra_statistics` 参数注入（必须，用于 rel_llm 额外统计）
- `metaweave/cli/metadata_cli.py`
  - `rel_llm` 分支：目录检查/错误提示（`metaweave/cli/metadata_cli.py:332-337`）
  - `rel_llm` 分支：改为复用 `RelationshipWriter` 写 JSON+MD（当前为手写 json.dump，见 `metaweave/cli/metadata_cli.py:342-363`）

### 非目标（本次不做）

- 处理 `json_llm_directory` 被其他下游命令依赖的问题（你已明确下一阶段再做）
- CLI `cql_llm` 分支仍残留 `json_llm_directory` 的读取与目录检查（`metaweave/cli/metadata_cli.py:366-388`），属于下一阶段范围
- 缓存与费用优化相关改造

---

## 测试验证计划

### 单元测试

- [ ] `LLMRelationshipDiscovery` 读取 `output.json_directory`（替代 `json_llm_directory`）
- [ ] `RelationshipWriter._parse_discovery_info()` 支持 `inference_method=="llm_assisted"` 的映射输出
- [ ] `statistics` 字段：`rel_llm` 复用 writer 后 v3.2 标准字段齐全，且“无对应概念的字段为 0”
- [ ] `generated_by`：`rel`/`rel_llm` 写入正确（且不影响 `relationships` 解析）

### 集成测试（手工/命令级）

1) **输入兼容性**
- 用 `--step json` 生成的 `output/json` 运行 `--step rel_llm`（不带 domain）✅
- 用 `--step json_llm`（增强后仍写回 `output/json`）运行 `--step rel` ✅

2) **输出一致性**
- `--step rel` 与 `--step rel_llm` 都产出 `output/rel/relationships_global.json` ✅
- `--step rel` 与 `--step rel_llm` 都产出 `output/rel/relationships_global.md` ✅

3) **下游兼容性**
- 两种关系 JSON 都能被 `--step cql` 正常读取并生成 CQL ✅
- （下一阶段处理）`--step cql_llm` 的输入目录统一到 `json_directory`

---

## 向后兼容性影响（本次改造范围）

### 对现有命令的影响

- ✅ `--step rel`：不受影响（输入仍为 `output.json_directory`，输出仍为 v3.2 JSON+MD）
- ⚠️ `--step rel_llm`：输入目录由 `json_llm_directory` 切换为 `json_directory`（同一份 `output/json`）
- ✅ `--step cql`：不受影响（只读 `relationships_*.json` 的 `relationships` 核心字段）
- ⚠️ `--step cql_llm`：仍存在 `json_llm_directory` 残留（明确为下一阶段处理）

### 迁移指南（给已有 rel_llm 用户）

1) 先确保 `output/json` 已存在（可由 `--step json` 或 `--step json_llm` 生成）
2) 若曾在配置里显式设置过 `output.json_llm_directory`，无需依赖它；改造后 `rel_llm` 会读取 `output.json_directory`
3) 重新运行 `--step rel_llm`
4) 检查 `output/rel/relationships_global.md` 已生成且内容符合预期

---

## 配置文件变更说明

### `configs/metadata_config.yaml`

本次改造的目标是让 `rel_llm` 与 `rel` 统一读取 `output.json_directory`，因此配置侧理论上**无需新增参数**。

保持并确认以下配置存在：

```yaml
output:
  json_directory: output/json
  # json_llm_directory: output/json_llm  # 已废弃（仅遗留兼容/下一阶段清理）
  rel_directory: output/rel
```

确认点：
- ✅ `json_directory` 已存在：`rel` 已在使用；`rel_llm` 改造后也会使用
- ⚠️ `json_llm_directory`：你已注释掉并计划废弃；其他步骤的残留依赖属于下一阶段统一改造范围
