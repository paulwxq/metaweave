# `--step rel` 与 `--step rel_llm` 关系发现执行流程对比

日期：2026-09-11

状态：基于当前仓库代码的现状说明，不代表改造后的目标流程。

## 1. 结论

当前 `rel_llm` 不是“在 `rel` 上增加一次 LLM 候选发现”。两者是两套独立编排：

- `rel` 使用 `RelationshipDiscoveryPipeline`，通过规则生成候选，再使用共享评分器评分，并由 `DecisionEngine` 统一执行阈值过滤和复合关系抑制。
- `rel_llm` 使用 `LLMRelationshipDiscovery`，由 LLM 直接提出候选关系，随后自行完成去重、语义过滤、类型过滤、评分和阈值过滤。
- 两者共享的主要能力是 JSON 元数据读取方式、物理外键提取、`RelationshipScorer`、名称相似度服务、`Relation` 模型和 `RelationshipWriter`。
- `rel_llm` 不会先执行 `rel`，也不会调用 `CandidateGenerator` 或 `DecisionEngine`。

两条命令都读取 `output.json_directory` 指定的 JSON 元数据，都在评分阶段访问源 PostgreSQL 数据库，并写入同一个 `output.rel_directory`。先后执行时，后一次结果会覆盖同名输出文件，不会自动合并两次运行结果。

## 2. 共同前置条件

### 2.1 JSON 元数据

两条路径依赖 JSON 中的以下信息：

- 表名、Schema、字段名和数据类型。
- `column_profiles` 中的统计信息与语义画像。
- `table_profile.physical_constraints` 中的主键、外键和唯一约束。
- `table_profile.unique_column_sets` 中的逻辑主键候选。
- 样例数据和注释等辅助信息。

`unique_column_sets` 在 `--step json` 中生成。逻辑主键检测发生在列画像生成之后：

1. 如果表已有物理主键，跳过逻辑主键检测。
2. 单列和复合逻辑主键分别按配置排除不适合的 `semantic_role`。
3. 候选必须满足唯一、非空、最低置信度和最小候选键要求。
4. 合格结果写入 `table_profile.unique_column_sets`。

因此，逻辑主键在进入关系发现之前已经接受过一次语义角色筛选。

### 2.2 物理外键

两条路径都调用 `MetadataRepository.collect_foreign_keys()`，从：

```text
table_profile.physical_constraints.foreign_keys
```

提取已经定义的物理外键。

物理外键属于确定性关系，直接进入最终结果，不调用 LLM，不参与语义角色过滤，也不进行四维评分和阈值判断。

### 2.3 四维评分

两条路径都复用 `RelationshipScorer`，评分维度及当前权重为：

| 维度 | 当前权重 | 含义 |
|---|---:|---|
| `inclusion_rate` | 0.55 | 来源字段值落入目标字段值域的比例 |
| `name_similarity` | 0.20 | 字段名称相似度 |
| `type_compatibility` | 0.15 | 字段类型兼容度 |
| `jaccard_index` | 0.10 | 两侧值集合交并比 |

`pipeline.py` 的部分注释和日志仍写着“6 维度”，实际 `scorer.py` 已经是上述 4 个维度。

## 3. `--step rel` 当前执行步骤

入口：`metaweave/cli/metadata_cli.py` 创建 `RelationshipDiscoveryPipeline` 并调用 `discover()`。

### 第 1 步：加载元数据并提取物理外键

1. 从配置的 JSON 目录加载所有表元数据。
2. 提取物理外键关系。
3. 记录物理外键签名，供后续规则候选去重。
4. 物理外键保留为最终结果的一部分。

### 第 2 步：使用规则生成候选关系

`CandidateGenerator` 先生成复合候选，再生成单列候选。

#### 复合候选

规则侧首先收集每张表的：

- 复合物理主键。
- 复合物理唯一约束。
- 达到 `composite.logical_key_min_confidence` 的复合逻辑主键。

随后在其他表查找可匹配的字段组合：

1. 特权匹配：与目标表的主键、唯一约束、逻辑主键或多列索引进行排列匹配，检查名称相似度和类型兼容性。
2. 动态同名匹配：按字段名精确匹配并检查类型兼容性。
3. 排除已经存在的物理外键候选。

当前复合路径对关键字段组合存在语义角色豁免：物理键和逻辑键作为驱动组合时不再过滤；部分目标侧特权候选也不进行语义过滤。

#### 单列候选

规则侧只以以下字段作为驱动候选：

- 单列物理主键。
- 单列物理唯一约束。
- 达到 `single_column.logical_key_min_confidence` 的单列逻辑主键。

这些驱动字段不再接受关系发现阶段的语义角色过滤。逻辑主键不二次过滤的依据是它在生成 `unique_column_sets` 时已经完成过语义筛选。

对其他表中的匹配字段，当前代码依次执行：

1. 判断目标字段是否具有物理约束、索引或逻辑键身份。
2. 应用语义角色规则；物理约束/索引字段和同名字段当前可以绕过这一步。
3. 检查类型兼容度。
4. 根据目标字段是否为关键字段选择名称相似度门槛。
5. 排除与已定义物理外键重复的候选。

### 第 3 步：四维评分

所有规则候选进入 `RelationshipScorer.score_candidates()`，查询源数据库样例值，计算四个维度、综合分数和关系基数。

### 第 4 步：统一决策

`DecisionEngine.filter_and_suppress()` 执行：

1. 按 `decision.accept_threshold` 拒绝低分候选。
2. 如果同一有向表对存在已接受的复合关系，根据 `suppress_single_if_composite` 抑制单列关系。
3. 如果单列关系的驱动字段拥有独立物理主键或唯一约束，则保留该单列关系。
4. 将接受候选转换为 `Relation`。

### 第 5 步：输出

将物理外键和推断关系交给 `RelationshipWriter`，输出全局 JSON 和 Markdown，并在输出中记录被拒绝或抑制候选的统计信息。

## 4. `--step rel_llm` 当前执行步骤

入口：`metaweave/cli/metadata_cli.py` 创建数据库连接和 `LLMRelationshipDiscovery`，调用 `discover()`，然后由 CLI 单独创建 `RelationshipWriter` 写出结果。

### 第 1 步：加载元数据

从与 `rel` 相同的 JSON 目录加载所有表元数据。

### 第 2 步：提取物理外键并直通

调用与 `rel` 相同的 `MetadataRepository.collect_foreign_keys()`。这些关系不进入 LLM 推断和后续评分。

### 第 3 步：确定 LLM 分析的表对

- 未指定 Domain 时，对所有表生成无序两两组合。
- 指定 Domain 时，通过 `DomainResolver` 和 `cross_domain` 配置确定表对。

当前 Domain 表对过滤只集成在 `rel_llm` 路径中。

### 第 4 步：调用 LLM 生成候选关系

每个表对调用一次 LLM，LLM 被要求直接返回单列或复合关系，并遵循：

```text
from/source = 外键表、引用方
to/target   = 主键或唯一键表、被引用方
```

提交给 LLM 前，代码删除每个字段画像中的：

- `semantic_analysis`
- `structure_flags`
- `role_specific_info`

表级 `physical_constraints`、`unique_column_sets` 和字段统计等信息仍会保留，因此 LLM 可以看到物理键和逻辑键信息，但当前代码没有强制 LLM 只能围绕这些键生成候选。

### 第 5 步：候选合法性检查与规范化

1. 拒绝当前表对之外的越界关系。
2. 拒绝同表同字段自环。
3. 将 LLM 返回的大小写漂移表名和字段名规范化成元数据中的名称。
4. 按 `relationship_id` 去除 LLM 自身返回的完全重复候选。

### 第 6 步：排除与物理外键完全重复的候选

代码同时计算正向和反向 `relationship_id`。如果 LLM 候选与物理外键完全相同，则抛弃 LLM 候选，保留物理外键。

当前实现只处理完整关系 ID 相同的情况，没有处理字段集合重叠、子集或超集关系。

### 第 7 步：语义角色过滤

当前代码对所有剩余 LLM 候选的两端统一执行语义角色过滤：

- 单列使用 `single_column.exclude_semantic_roles`。
- 复合关系使用 `composite.exclude_semantic_roles`。
- 复合关系任意一对字段命中排除角色，就拒绝整个候选。

这里没有识别某一端是否为物理主键、物理唯一键或 `unique_column_sets`。因此，LLM 返回的物理键和逻辑键也会接受二次语义过滤。

### 第 8 步：类型兼容性过滤

对单列或复合关系的逐字段映射计算类型兼容度。任何一对字段低于对应配置阈值时，拒绝候选。

### 第 9 步：四维评分

`rel_llm` 直接调用共享评分器的内部 `_calculate_scores()`，得到与 `rel` 相同的四维分数、综合分数和关系基数。

### 第 10 步：阈值过滤

`rel_llm` 自行按 `decision.accept_threshold` 将候选分成接受和拒绝两类。

它没有调用 `DecisionEngine`，因此当前不会应用 `rel` 的“复合关系抑制同表对单列关系”规则。

### 第 11 步：输出

1. 将接受的 LLM 字典转换为 `Relation`。
2. 与物理外键合并。
3. 再按 `relationship_id` 去重，物理外键优先。
4. CLI 调用 `RelationshipWriter` 输出 JSON 和 Markdown。

`rel_llm` 写出时传入的 `suppressed=[]`，所以不会输出与 `rel` 相同的抑制信息。

## 5. 关键差异

| 对比项 | `rel` | `rel_llm` |
|---|---|---|
| 编排类 | `RelationshipDiscoveryPipeline` | `LLMRelationshipDiscovery` |
| 物理外键 | 直通 | 直通 |
| 规则候选生成 | 执行 | 不执行 |
| LLM 候选生成 | 不执行 | 对表对调用 LLM |
| 物理主键/唯一键 | 显式进入规则驱动候选 | 作为提示词上下文，未被强制采用 |
| 逻辑主键 | 显式读取并按置信度进入规则候选 | 作为提示词上下文，未被强制采用 |
| 关键字段语义豁免 | 规则候选阶段存在 | LLM 候选没有键身份豁免 |
| LLM 候选与已有候选的包含检查 | 不适用 | 未实现 |
| LLM 候选语义过滤 | 不适用 | 两端统一过滤 |
| 类型预过滤 | 候选生成阶段执行 | LLM 返回后执行 |
| 四维评分器 | `score_candidates()` | 直接调用 `_calculate_scores()` |
| 阈值过滤 | `DecisionEngine` | 自行实现 |
| 复合/单列抑制 | 有 | 无 |
| Domain 表对过滤 | 无 | 有 |
| 输出器 | 管道内部调用 | CLI 外部调用 |
| 输出位置 | `output.rel_directory` | 同一目录、同名文件 |

## 6. 当前实现带来的主要问题

1. `rel_llm` 不是 `rel + LLM`，两条路径可能对同一候选得出不同结果。
2. 阈值、语义过滤、去重、结果转换和统计分散在两套实现中，修改时容易发生行为漂移。
3. `rel_llm` 没有系统执行物理键、逻辑键驱动的规则候选生成，结果依赖 LLM 是否主动返回这些关系。
4. `rel_llm` 对逻辑主键再次执行语义角色过滤，与逻辑主键生成阶段重复。
5. `rel_llm` 只去除与物理外键完全相同的候选，没有处理 LLM 字段组合与已有候选的重叠及包含关系。
6. `rel_llm` 绕过 `DecisionEngine`，缺少与 `rel` 一致的单列/复合关系抑制规则。
7. 两条路径对候选方向的表达不够统一：`rel_llm` 明确使用 `FK → PK`；`rel` 的规则生成从关键字段组合出发搜索其他表字段。改造时应统一内部方向，再执行包含率计算、关系 ID 生成和输出。
8. 两条命令写入相同输出文件，无法从文件系统同时保留两套结果用于比较。

## 7. 代码依据

- `metaweave/cli/metadata_cli.py`：`rel` 与 `rel_llm` 的 CLI 分派。
- `metaweave/core/relationships/pipeline.py`：`rel` 的五阶段编排。
- `metaweave/core/relationships/candidate_generator.py`：规则候选生成、物理键/逻辑键处理和候选预过滤。
- `metaweave/core/relationships/llm_relationship_discovery.py`：LLM 表对分析、候选过滤、评分和阈值判断。
- `metaweave/core/relationships/repository.py`：JSON 加载、物理外键提取、关系 ID 和基数辅助判断。
- `metaweave/core/relationships/scorer.py`：四维评分。
- `metaweave/core/relationships/decision_engine.py`：阈值过滤和单列/复合关系抑制。
- `metaweave/core/relationships/writer.py`：统一关系结果输出。
- `metaweave/core/metadata/logical_key_detector.py`：逻辑主键的语义过滤、唯一性和置信度检测。
