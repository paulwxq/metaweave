# `rel` 与 `rel_llm` 统一关系发现流程改造备忘录

日期：2026-09-11

状态：目标设计备忘录，尚未实施。

## 1. 改造目标

将 `--step rel` 和 `--step rel_llm` 收敛到同一条关系发现管道：

```text
rel_llm = rel 标准流程 + LLM 补充候选字段
```

两种模式只在“是否调用 LLM 补充规则未发现的候选”这一点上不同。候选规范化、过滤、四维评分、决策、抑制、关系转换、统计和输出全部共用。

本次改造应解决以下问题：

- 两条命令分别维护候选处理和决策逻辑。
- `rel_llm` 没有先执行 `rel` 的确定性候选流程。
- 物理键、逻辑键和 LLM 候选没有统一的来源优先级。
- `rel_llm` 对已经生成的逻辑主键再次进行语义过滤。
- LLM 候选只按完整关系 ID 去重，没有与已有候选做字段重叠和包含检查。
- `rel_llm` 没有复用 `DecisionEngine` 的抑制逻辑。

## 2. 已确认的设计原则

### 2.1 物理外键直接进入最终结果

物理外键是数据库已经声明的确定性关系：

- 不调用 LLM。
- 不进行语义角色过滤。
- 不进行四维评分。
- 不受接受阈值影响。
- LLM 返回与其重复或被其覆盖的候选时，抛弃 LLM 返回项。

### 2.2 物理键和逻辑键优先

以下字段组合构成基础候选：

- 物理主键。
- 物理唯一约束。
- 达到置信度要求的逻辑主键 `unique_column_sets`。

这些候选由确定性规则先加入候选池。关系发现阶段不再按 `semantic_role` 排除它们：

- 物理键来自数据库约束，应尊重 DBA 定义。
- 逻辑主键在生成 `unique_column_sets` 时已经进行语义角色、唯一性、空值率、置信度和最小性检查，不需要在关系发现阶段重复执行相同语义过滤。

确定性来源优先级为：

```text
物理外键关系 > 物理主键/唯一键候选 > 逻辑主键候选 > LLM 补充候选
```

这里的优先含义是：低优先级来源与高优先级来源重叠时，抛弃低优先级返回项；不把两种来源“合并”为一个新的字段组合。

### 2.3 LLM 只补充全新的候选

`rel_llm` 必须先完成与 `rel` 相同的基础候选生成，再调用 LLM。

LLM 返回项加入候选池之前，必须与当前候选池进行重叠及包含关系检查。只有与现有候选完全无重叠的 LLM 返回项，才进入下一步检查。

当 LLM 返回项与物理外键、物理键候选、逻辑键候选或规则关系候选存在以下任一情况时，抛弃整个 LLM 返回项：

- 字段集合完全相同。
- LLM 字段集合包含已有候选字段集合。
- LLM 字段集合被已有候选字段集合包含。
- 按已确认的保守策略，字段集合存在任意交集。

被删除的是 LLM 返回项，候选池中已有的确定性或规则候选保持不变。

比较必须使用完全限定字段身份：

```text
database.schema.table.column
```

不能只按字段名比较。单列按一个元素的集合处理；复合字段按规范化后的字段集合处理，同时保留来源列与目标列的对应关系，避免字段顺序变化破坏映射。

示例：

```text
已有逻辑候选：public.customer.(customer_id)
LLM 返回：     public.customer.(customer_id, customer_type)
```

LLM 返回包含已有逻辑候选，因此直接抛弃 LLM 返回项，继续使用已有候选。

### 2.4 普通关联字段需要语义审查，LLM 新增候选必须检查两端

LLM 可能把金额、数量、比率等数值指标误判为关联字段。对于通过重叠检查的 LLM 新候选，必须检查关系两端字段的 `semantic_analysis.semantic_role`：

- 单列候选：来源端或目标端任意一端命中 `single_column.exclude_semantic_roles`，拒绝候选。
- 复合候选：来源端或目标端任意组成字段命中 `composite.exclude_semantic_roles`，拒绝整个组合。
- 物理主键、物理唯一键和已经进入 `unique_column_sets` 的逻辑主键不做二次语义过滤。

为了让规则模式和 LLM 模式遵循同一原则，过滤策略应依据“字段来源”决定，而不是依据命令名称决定：

| 字段来源 | 关系发现阶段的语义处理 |
|---|---|
| 物理外键 | 整条关系直通 |
| 物理主键/唯一键候选 | 不过滤 |
| `unique_column_sets` 逻辑键候选 | 不二次过滤 |
| 规则发现的普通关联字段 | 执行语义过滤 |
| LLM 新增的普通关联字段 | 执行语义过滤 |

当前 `rel` 中“同名字段无条件绕过语义过滤”的规则应在改造时重新评估。同名数值指标仍可能属于错误关系，不应仅因同名就自动豁免语义冲突。

### 2.5 所有推断候选共用后续处理

通过候选准入检查后，无论来源是规则还是 LLM，都执行同一套流程：

1. 类型兼容性预检查。
2. 候选方向规范化。
3. 候选去重。
4. 四维评分。
5. 统一阈值判断。
6. 统一复合/单列抑制。
7. 转换成同一个 `Relation` 模型。
8. 统一统计和输出。

## 3. 目标执行流程

### 阶段 1：加载并校验 JSON 元数据

统一加载器负责：

- 加载所有表 JSON。
- 检查表和字段身份是否完整。
- 检查 `physical_constraints`、`unique_column_sets` 和 `column_profiles` 的结构。
- 建立大小写不敏感的表名、字段名规范化索引。

`rel` 和 `rel_llm` 必须使用完全相同的输入和校验结果。

### 阶段 2：提取物理外键

使用 `MetadataRepository` 提取物理外键并直接放入最终关系集合，同时建立：

- 规范化关系 ID 集合。
- 物理外键两端的完全限定字段集合。
- 单列与复合字段映射索引。

这些索引用于阻止规则或 LLM 重复发现已有物理关系。

### 阶段 3：建立基础键候选池

统一 `KeyCandidateCollector` 收集：

- 物理主键。
- 物理唯一约束。
- 达到单列或复合置信度阈值的 `unique_column_sets`。

每个候选应记录：

```text
表身份
字段列表
单列/复合类型
来源：physical_primary_key / physical_unique_key / logical_key
逻辑键置信度（如适用）
是否需要语义过滤：false
```

候选池内部先进行规范化和最小性去重，避免同一字段组合以多个来源重复出现。确定性来源优先，不创建字段组合的并集。

### 阶段 4：规则生成关系候选

`RuleCandidateProvider` 使用基础键候选池，在其他表中寻找可能引用这些键的字段：

- 单列名称匹配。
- 复合字段集合匹配。
- 类型兼容性检查。
- 物理约束、逻辑键和必要索引信号。
- 配置允许的其他规则依据。

生成结果统一转换为标准候选关系模型，不直接评分或输出。

### 阶段 5：可选的 LLM 补充候选

仅 `rel_llm` 执行本阶段；`rel` 跳过本阶段。

1. 按统一的表对策略选择需要分析的表对。
2. 构造提示词，让 LLM 只寻找规则候选池尚未覆盖的关联字段。
3. 解析结构化输出，校验表、字段、单列/复合格式和字段对应关系。
4. 规范化表名和字段名。
5. 为候选标记 `candidate_source=llm`。

建议把 Domain 表对过滤下沉为公共能力。两种模式均可使用同一表对范围；LLM 只是该范围上的一个可选候选提供器。

### 阶段 6：LLM 候选重叠与包含检查

只处理 `candidate_source=llm` 的返回项：

```text
LLM 候选
  → 是否与物理外键字段或关系重叠？是则丢弃
  → 是否与基础键候选重叠？是则丢弃
  → 是否与规则关系候选重叠？是则丢弃
  → 是否存在相等、子集、超集或任意交集？是则丢弃
  → 完全无重叠才进入语义检查
```

这一阶段不修改已有候选，也不合并来源信息。统计中应分别记录：

- `llm_rejected_existing_fk`
- `llm_rejected_exact_duplicate`
- `llm_rejected_overlap`
- `llm_rejected_containment`

### 阶段 7：按候选来源执行语义过滤

统一 `SemanticRolePolicy` 根据候选字段来源决定是否过滤：

1. 确定性键字段跳过二次过滤。
2. 规则发现的普通字段执行过滤。
3. 无重叠的 LLM 新字段必须检查来源端和目标端。
4. 复合候选只要有一个组成字段命中排除角色，就拒绝整个候选。

应记录具体拒绝原因和字段，例如：

```text
rejected_reason=excluded_semantic_role
rejected_field=public.orders.amount
semantic_role=metric
candidate_source=llm
```

### 阶段 8：统一结构校验与候选规范化

所有剩余推断候选统一执行：

- 两端字段数量一致。
- 字段真实存在。
- 不允许无意义的同表同字段自环。
- 逐字段类型兼容度达到配置门槛。
- 字段顺序和映射关系规范化。
- 关系方向统一为 `FK → PK/UK/逻辑键`。
- 使用同一算法生成 `relationship_id`。
- 规则候选与 LLM 候选最终去重。

方向统一非常关键。包含率必须计算“外键候选值有多少存在于主键候选值集合中”，关系 ID 和输出也必须使用同一方向。

### 阶段 9：统一四维评分

所有推断候选调用公开的统一评分接口，不允许 `rel_llm` 继续直接调用 `_calculate_scores()` 私有方法。

```text
composite_score =
    0.55 × inclusion_rate
  + 0.20 × name_similarity
  + 0.15 × type_compatibility
  + 0.10 × jaccard_index
```

数据库值域指标用于验证已有候选假设，不能单独证明业务关联。应与此前确定的“禁止纯数据自动接受”策略结合：缺少规则或语义依据的候选，即使数据分数很高，也不能自动进入正式关系结果。

### 阶段 10：统一决策与抑制

所有评分结果进入同一个 `DecisionEngine`：

- 应用统一接受阈值。
- 应用统一的复合关系与单列关系抑制规则。
- 记录低分、重叠、语义冲突、类型冲突和被抑制候选。
- 保证 `rel` 和 `rel_llm` 对相同候选做出相同决定。

### 阶段 11：统一输出

`RelationshipWriter` 接收：

- 物理外键直通关系。
- 已接受的规则推断关系。
- `rel_llm` 模式下已接受的 LLM 补充关系。
- 各阶段拒绝和抑制统计。

两种模式使用相同输出格式，只通过 `generated_by`、候选来源和统计项标识模式差异。

## 4. 目标模式差异

| 阶段 | `rel` | `rel_llm` |
|---|---:|---:|
| 加载 JSON | 执行 | 执行 |
| 物理外键直通 | 执行 | 执行 |
| 收集物理键和逻辑键 | 执行 | 执行 |
| 规则候选生成 | 执行 | 执行 |
| LLM 补充候选 | 跳过 | 执行 |
| LLM 重叠/包含检查 | 无 LLM 候选 | 执行 |
| 按来源进行语义过滤 | 执行 | 执行 |
| 类型和结构校验 | 执行 | 执行 |
| 四维评分 | 执行 | 执行 |
| 统一决策与抑制 | 执行 | 执行 |
| 统一输出 | 执行 | 执行 |

最终代码层面应体现为同一个入口：

```python
pipeline.discover(use_llm=False)  # --step rel
pipeline.discover(use_llm=True)   # --step rel_llm
```

具体参数名可以在实施时调整，但不应继续保留两套完整编排。

## 5. 推荐模块边界

```text
UnifiedRelationshipDiscoveryPipeline
├── MetadataRepository
├── PhysicalForeignKeyCollector
├── KeyCandidateCollector
├── RuleCandidateProvider
├── LLMCandidateProvider             # 可选
├── CandidateOverlapPolicy
├── SemanticRolePolicy
├── CandidateNormalizer
├── RelationshipScorer
├── DecisionEngine
└── RelationshipWriter
```

建议职责：

| 模块 | 职责 |
|---|---|
| `KeyCandidateCollector` | 统一收集物理 PK/UK 和逻辑键 |
| `RuleCandidateProvider` | 根据确定性键和规则生成关系候选 |
| `LLMCandidateProvider` | 只负责调用 LLM、解析并返回标准候选，不负责评分和最终决策 |
| `CandidateOverlapPolicy` | 检查 LLM 返回与现有候选的相等、重叠和包含关系 |
| `SemanticRolePolicy` | 按字段来源决定是否过滤，输出明确拒绝原因 |
| `CandidateNormalizer` | 字段规范化、方向统一、映射校验和关系 ID 生成 |
| `RelationshipScorer` | 为所有推断候选计算同一套四维指标 |
| `DecisionEngine` | 统一阈值、证据准入和抑制规则 |
| `RelationshipWriter` | 统一输出和统计 |

候选提供器不得各自实现阈值过滤、结果转换或写文件。

## 6. 建议的统一候选模型

规则和 LLM 应输出同一种内部结构，例如：

```yaml
source_table: public.orders
source_columns: [customer_id]
target_table: public.customer
target_columns: [id]
candidate_source: rule | llm
key_source: physical_primary_key | physical_unique_key | logical_key | llm_only
candidate_type: single | composite
semantic_check_fields:
  - public.orders.customer_id
evidence:
  rule: name_match
  llm: null
```

其中：

- `source` 始终表示外键候选端。
- `target` 始终表示物理或逻辑键端。
- `candidate_source` 决定候选发现来源。
- `key_source` 决定键端是否免除二次语义过滤。
- `semantic_check_fields` 明确哪些普通字段必须接受语义检查。
- `evidence` 用于审计候选为何进入评分阶段，不用于把重复来源合并成新的字段组合。

## 7. 配置建议

可以在现有 `relationships` 配置下增加统一的候选策略。以下仅为拟议结构：

```yaml
relationships:
  llm_candidate_supplement:
    enabled: true
    reject_any_overlap: true
    reject_containment: true
    check_both_sides_semantic_role: true

  inference:
    allow_data_only: false
```

要求：

- `--step rel` 强制 `llm_candidate_supplement.enabled=false`。
- `--step rel_llm` 启用 LLM 候选提供器。
- 单列和复合语义排除角色继续复用现有配置，不再复制出不一致的名单。
- 空列表应能明确表示“不排除任何角色”，不能隐式回退到默认值。
- 拒绝原因必须写入日志和统计，便于核对误报与漏报。

## 8. 实施顺序

### 第一阶段：建立统一模型和公共后半段

1. 定义统一候选模型、字段身份和 `FK → PK` 方向。
2. 让规则候选适配统一模型。
3. 抽取公共规范化、评分、`DecisionEngine` 和输出流程。
4. 保持 `rel` 行为可回归比较。

### 第二阶段：把 LLM 改成候选提供器

1. 从 `LLMRelationshipDiscovery` 提取 LLM 调用和响应解析。
2. 删除其中重复的评分、阈值过滤、关系转换和输出准备逻辑。
3. 将 LLM 结果转换为统一候选模型。
4. 接入重叠/包含检查和双端语义检查。

### 第三阶段：统一入口

1. `rel` 与 `rel_llm` 调用同一个管道。
2. 用模式参数控制是否增加 `LLMCandidateProvider`。
3. 统一 Domain 表对解析、数据库连接生命周期、统计和错误处理。
4. 保留两个 CLI 名称，避免破坏现有调用方式。

### 第四阶段：清理旧实现

1. 删除 `rel_llm` 私有的评分和阈值实现。
2. 删除重复的关系转换、去重和统计代码。
3. 修正“6 维度”等过时注释与日志。
4. 更新流程文档和配置示例。

## 9. 验收用例

| 用例 | 预期结果 |
|---|---|
| 已定义物理外键 | 两种模式均直接输出，不评分 |
| LLM 返回与物理外键完全相同的字段对 | 抛弃 LLM 返回项 |
| LLM 复合字段包含完整物理外键 | 抛弃 LLM 返回项 |
| LLM 返回与物理 PK/UK 候选相同或包含的字段 | 抛弃 LLM 返回项，保留确定性候选 |
| LLM 返回与逻辑主键相同或包含的字段 | 抛弃 LLM 返回项，保留逻辑主键候选 |
| LLM 返回字段与已有候选存在部分交集 | 按保守策略抛弃 LLM 返回项 |
| LLM 返回完全无重叠的新字段，且两端语义允许 | 加入候选池并进行四维评分 |
| LLM 将 `amount`、`quantity` 等 `metric` 识别为关联字段 | 在评分前由语义角色策略拒绝 |
| LLM 复合候选任意组成字段属于排除角色 | 拒绝整个复合候选 |
| 逻辑主键已通过 JSON 阶段语义过滤 | 关系发现阶段不再二次过滤键端 |
| 普通规则候选字段命中排除角色 | 与 LLM 普通候选使用相同策略拒绝 |
| 相同候选分别由规则和 LLM 返回 | 保留规则候选，抛弃 LLM 返回项 |
| 候选字段均为整数且样例值高度重叠，但缺少业务依据 | 不允许仅靠数据分数自动接受 |
| 同一表对同时存在单列和复合高分候选 | 两种模式执行相同抑制策略 |
| 相同输入下关闭 LLM | `rel_llm` 的公共阶段结果与 `rel` 一致 |

## 10. 需要在编码前固定的细节

以下实现细节应通过测试固定，避免开发过程中再次产生歧义：

1. “任意重叠即拒绝”按来源端、目标端分别比较，还是把两端字段放入一个集合比较。建议按完全限定字段身份比较，两端任意交集都拒绝 LLM 返回项。
2. 复合字段顺序是否参与候选身份。建议集合用于重叠判断，有序映射用于评分和关系输出。
3. LLM 候选缺失字段画像或 `semantic_role` 时，是拒绝还是进入待确认结果。正式关系模式建议拒绝并记录原因。
4. 规则候选当前存在的同名字段语义豁免是否删除。为减少错误关联，建议普通字段即使同名也不能绕过明确的排除角色。
5. Domain 过滤是否同时适用于规则候选生成。建议统一适用，确保两种模式只相差 LLM 补充步骤。

这些细节不会改变总体原则：先运行完整标准关系发现流程，`rel_llm` 只增加 LLM 候选补充，所有候选共用后续规则。
