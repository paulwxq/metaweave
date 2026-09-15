# Rel 与 Rel_LLM 候选生成统一改造设计

## 1. 文档目的

本文仅设计 `--step rel` 的关系发现改造：把当前 `rel_llm` 的 LLM 候选能力纳入
`rel`，由配置决定是否启用。目标：

1. 把当前割裂的"单列 / 复合键"两条规则路径收敛为一条统一管线（递进式闸门匹配）；
2. 把 `rel_llm` 从一条**平行管线**降格为统一管线的**可选候选来源**——LLM 与规则候选
   并行生成、合并去重后进入同一套评分与决策；
3. 删除 `--step rel_llm` 命令行入口，改为 `relationships.llm_candidates.enabled`
   配置开关（默认启用），与 doc 12 的 json LLM 开关设计哲学一致。

**本阶段范围**：

- 修改候选生成阶段（规则候选 + LLM 候选 + 合并去重）；
- 评分阶段**维度调整**：`name_similarity` 维度替换为 `comment_similarity`
  （含按列对回退与低信息量检测），`inclusion_rate` / `jaccard_index` 的计算方式
  保持不变；
- 决策阶段（`decision_engine`）除 v3 适配修复外**代码不改**，决策阈值随候选池
  与评分维度变化**必须重新校准**（配置层）；
- 修改 `--step rel` 使用的关系发现内部编排
  （`metaweave/core/relationships/pipeline.py` 中的
  `RelationshipDiscoveryPipeline`），接入可选 LLM 候选与统一去重；
- 不修改 `metadata --step standard` 的编排实现与 `pipeline generate`
  （`pipeline_cli.py`）；两者复用本阶段修改的引擎与配置，过渡期不可用**不构成
  本阶段阻塞**。本阶段正式支持并验收的入口只有独立执行的 `metadata --step rel`；
- 物理外键直通逻辑保持不变。

## 2. 现状问题回顾

### 2.1 规则候选：单列与复合键是两条割裂的路径

`CandidateGenerator.generate_candidates()`（`candidate_generator.py:73`）分两次独立遍历：

- 复合路径只收 2~max_columns 列的键集（PK/UK/逻辑键），单列键被 `2 <= len(...)` 丢弃；
- 单列路径另走一套规则（重要性门控 + 三级过滤 + 动态阈值）；
- 两条路径规则互相矛盾：复合路径显式排除索引，单列路径把目标列索引当强信号；
- 阈值体系各自为政（`single_column.*` 与 `composite.*` 两套配置）。

### 2.2 规则候选：目标侧"特权模式"收益低、噪音大

复合路径 Stage 1 特权模式给目标表 PK/UK/索引组合 0.6 的宽松名称阈值，本意是"用数据
验证兜住语义模糊匹配"。实际问题是：整型主键数据大量重合（orders.id 与 users.id 都是
自增整型），"数据支持"无法区分"语义相同"与"巧合重合"，噪音大于收益。

**决定**：撤销目标侧全部特殊待遇，目标侧只剔除 metric / complex 两类字段，其余全量
平等。字段语义判断交给 LLM 注释通道（见 3.4），比数据盲猜可靠。

### 2.3 rel_llm 是一条平行管线

`LLMRelationshipDiscovery`（`llm_relationship_discovery.py`）维护自己的一整套流程：

```text
加载JSON → FK直通 → LLM全表对 → 规范化 → 去重 → 过滤已有FK → 语义角色过滤
        → 类型过滤 → 评分(共用scorer) → 阈值过滤 → 与FK合并 → 输出
```

其中评分器与 `rel` 共用，但候选规范化、过滤、去重、合并全部重复实现，且规则候选与
LLM 候选从未合并——两条管线产出互不相见。

### 2.4 名称相似度存在两套实现与错配配置

`relationships.name_similarity.method` 支持 `embedding` / `string`（SequenceMatcher）
切换，导致两套阈值口径（配置注释："非 embedding 建议 0.6，embedding 建议 0.9"），且
现状已是错配状态（method=embedding 配 0.6）。中文注释比对（新增能力）无法用
SequenceMatcher 支撑。

**决定**：移除 SequenceMatcher 业务路径，名称相似度 = embedding（主通道）+ 同名短路
（本地）。

### 2.5 评分阶段的 name_similarity 维度两头落空

评分四维中的 `name_similarity`（权重 0.20）在新候选体系下失去区分价值：

- 规则候选：已通过递进闸门（名称 ≥ 0.9 或注释 ≥ 0.85），评分时重算名称相似度
  必然高分——冗余的恒定加分项；
- LLM 候选：规则筛不出、LLM 筛出的列对多为"异名同义"，名称相似度恰好给这类
  候选低分——**惩罚了 LLM 的存在价值**。

相反，注释相似度能提供名称维度没有的区分能力："同名不同义"的列对（如
orders.id vs users.id）名称相似度为 1.0 无法区分，注释（"订单唯一标识" vs
"用户唯一标识"）却能拉开差距。

**决定**：评分维度 `name_similarity` 替换为 `comment_similarity`（按列对回退，见 3.11）。

### 2.6 现有去重不能作为统一管线的保证

规则路径分别收集物理 PK、UK 和逻辑键；同一复合字段组合可能从多个来源进入候选。
`CandidateGenerator.generate_candidates()` 只是拼接复合与单列候选，没有统一的规则候选
去重。`rel_llm` 当前会在评分前过滤与物理 FK 重复的 LLM 候选，统一管线收缩旧实现时
必须保留这项行为。

另有现存接口错配（且 FK 排重从未生效）：`MetadataRepository.collect_foreign_keys()`
返回的去重集合是 `rel_` + MD5 哈希（`compute_relationship_id`），规则候选生成器却
拿 `_make_signature()` 返回的**明文签名**与之比较——两种格式永远不相等，当前
`rel` 的 FK 排重实际从未生效。**修法钉死**：候选去重与 FK 排重全部复用统一身份
函数——升级 `compute_relationship_id` 为"按完整列对应对排序后哈希"
（`sorted(f"{s}={t}" for s, t in zip(source_columns, target_columns))` 再哈希），
废弃 `_make_signature`。升级原因：现有函数两侧列分别排序，会把不同字段指派合并
（`(A.id→B.id, A.code→B.code)` 与 `(A.id→B.code, A.code→B.id)` 得到同一 ID），
违反 3.8 的列对应语义；`relationship_id` 值集变化可接受（项目不向下兼容，v3
重新生成输出）。

### 2.7 v3 JSON 已移除列级 structure_flags，现有消费者失明

v3 JSON 契约把 `structure_flags` 列入 `forbidden_column_keys`
（`metadata_document.py:376`），column_profiles 不再携带列级物理约束标志。关系
发现模块仍有以下五处读取或依赖它：

| 消费者 | 位置 | v3 下的后果 |
|---|---|---|
| 决策器抑制例外 | `decision_engine.py:180-207` `_has_independent_constraint` | 恒返回 False → 同表对存在复合关系时，有单列物理 PK/UK 的单列关系也被**悄悄抑制** |
| 单列候选源门控 | `candidate_generator.py:646` `_has_defined_constraint` | 恒 False → 有物理主键的表（无逻辑键）其单列 PK/UK 源列**完全退出单列候选生成** |
| 目标列动态阈值/三级过滤 | `candidate_generator.py:683/738` `_is_qualified_target_column` | 物理约束目标列拿不到宽松阈值，被按角色过滤 |
| 单列唯一性判定 | `repository.py:342-345` `_is_columns_unique` | 退化为统计/逻辑键回退，cardinality 可能降级 |
| 输出键标注 | `writer.py:453-459` | 主键/唯一键标注退化 |

**决定**：全部改为读取 v3 表级 `table_profile.physical_constraints`
（`primary_key.columns` / `unique_constraints[].columns`）。决策器的
`_has_independent_constraint` 是唯一不在候选生成重写范围内的消费者，作为
**先行修复**独立实施，其例外口径为：单列物理主键 / 单列唯一约束 / **非
partial 单列唯一索引**（`table_profile.indexes[]` 中 `is_unique: true`、单列键、
`condition` 为空）；candidate_generator 的两处在统一候选重写中自然解决；
repository 的 `_is_columns_unique` **仅替换第 1 级物理约束的读取源**（单列
分支：列级 `structure_flags` → 表级 `physical_constraints`），第 2 级统计回退
（`uniqueness >= 0.95`，复合取最小唯一性）保持不变；writer 的键标注一并改为
表级判断。项目不考虑向下兼容。

### 2.8 配置迁移波及 JSON 逻辑键检测（跨模块耦合）

`single_column` / `composite` 节点不只是关系匹配配置——`MetadataGenerator` 的
构造路径（`generator.py:107-123`）仍从这两个节点读取逻辑键检测的语义排除配置：

```python
single_column_exclude_roles = single_column_config.get("exclude_semantic_roles", ["audit", "metric"])
logical_key_config["single_column_exclude_roles"] = single_column_exclude_roles
composite_exclude_roles = composite_config.get("exclude_semantic_roles", ["metric"])
logical_key_config["composite_exclude_roles"] = composite_exclude_roles
```

`MetadataGenerator` 是 `--step ddl` 与 `--step json` 共用的构造路径，因此 4.3 的
旧节点报错策略有两种失败形态：

| 场景 | 后果 |
|---|---|
| 迁移校验整体拒绝 `single_column` / `composite` 节点 | `--step ddl` / `--step json` 启动即失败 |
| 只从示例配置删除节点（不报错） | generator 的 `.get()` 静默回退默认值（复合排除角色从 `[metric, description, attribute, complex]` 退化为 `[metric]`），逻辑键检测行为漂移 |

**决定（一次性搬迁 + 删除，不做兼容层）**：把这两个键搬进 `logical_key_detection`
节点自身，切断与 `single_column` / `composite` 的耦合：

```text
single_column.exclude_semantic_roles
  -> logical_key_detection.single_column_exclude_roles
     （现状值 [audit, metric, description, complex] 原样搬运）

composite.exclude_semantic_roles
  -> logical_key_detection.composite_exclude_roles
     （现状值 [metric, description, attribute, complex] 原样搬运）
```

配套要求：

- `generator.py:107-123` 删除注入逻辑，`logical_key_detection` 节点中的两个新键
  直接透传（检测器 `logical_key_detector.py:45-52` 读取键名不变，无需改动）；
- 值按现状**原样搬运**，保证 ddl/json 的逻辑键检测在迁移前后行为等价——这是改造
  自身的等价性纪律，不是对旧配置的兼容；
- 与 4.3 的节点删除**同批实施**：先完成新路径读取，再删除旧节点，不允许出现
  中间态（中间态会静默漂移）；
- 该 generator 改动属于 doc 12 边界内的"配置读取最小改动"，实施时与 doc 15 的
  配置迁移同一批完成。

## 3. 目标设计

### 3.1 统一管线总览

```text
直通:物理外键 → 直接写入关系文件并登记关系身份(不评分,现状保留)

第1步 候选生成(本次改造,统一标准):
  ① 源侧:统一收集键集(PK / 唯一约束 / 逻辑键,1~N 列,一个列表)
  ② 目标侧:剔除 metric / complex 角色 → 目标列池,其余全量平等
  ③ 逐对递进闸门:英文名 embedding ≥ 0.9 → 过
                 否则 注释 embedding ≥ 0.85 → 过
                 否则 放弃
                 → 类型兼容 ≥ 0.8 → 进池,否则放弃
  ④ 集合指派(复合键):每源列独立过闸得候选集 → 穷举指派(非贪心)
  ⑤ LLM 候选(可选,llm_candidates.enabled=true 时):按统一域范围(见 3.13)
    对表对调用 LLM,不过递进闸门
  ⑥ LLM 候选截断:收到 LLM 返回后,在代码中按 confidence 降序取前 top_k
    (全局),再进入候选池(见 3.9)
  ⑦ 合并入池:规则候选 ∪ LLM 候选,记录 candidate_origin(rule / llm)
  ⑧ 池内统一去重(不再分来源单独去重):
     a. 按完整列对应对去重(升级版 compute_relationship_id,见 2.6)
     b. 最小键过滤:同池内单列 col→X 与复合 (col,other)→(X,Y)(col 配同一 X)
        → 丢弃复合(不区分来源:逻辑键超集已在检测器消除;物理约束的 superkey
        如单列 PK + 复合 UK 并存,同样由本条兜底;LLM 超集输出也由本条处理)
     c. 来源合并:同一关系命中两来源 → 标记 rule+llm
  ⑨ 物理 FK 排除:与直通 FK 相同的候选全部剔除,不进入评分
    (直通 FK 已直接写入关系文件,不重复计算)

第2步 评分(维度调整):
  inclusion_rate 0.50 + comment_similarity 0.20(按列对回退,见3.11)
  + type_compatibility 0.20 + jaccard_index 0.10,DB 采样

第3步 决策(规则不变,仅适配 v3 约束读取并重校准阈值):阈值过滤 + 抑制
```

`rel` 与 `rel_llm` 的行为差异只剩第 ⑤ 步开不开。

### 3.2 源侧键集统一收集

```text
源键集 = 物理主键 ∪ 物理唯一约束 ∪ 逻辑主键候选
         (1 ~ max_columns 列,统一列表,不再按宽度分流)
```

- 物理 PK/UK：完全尊重 DBA 定义，不按语义角色过滤；
- 逻辑键：生成阶段已按 `single_column_exclude_roles`(audit/metric) 与
  `composite_exclude_roles`(metric) 过滤过，天然干净；
- 索引不作为源侧键来源（与现状一致）。

### 3.3 目标列池构建（角色过滤前置）

对每个目标表，在**匹配开始前**构建目标列池：

```text
目标列池 = 目标表全部列 − {语义角色为 metric 的列} − {complex 类型列}
```

- complex 类型沿用 profiler 的 `_default_complex_types`（json/jsonb/array/bytea 等）；
- 角色过滤前置：零成本元数据检查，省掉大量无效 embedding 调用，与"每对匹配时再检查"
  语义完全等价；
- 目标列是否 PK/UK/索引、audit/description 角色：**一律不搞特殊待遇**。

### 3.4 递进式闸门匹配（规则候选专用）

对源键集中的每一列 × 目标列池中的每一列，按序执行：

```text
闸门1 英文名 embedding 相似度 ≥ name_threshold (0.9) → 过
      否则:
闸门2 中文注释 embedding 相似度 ≥ comment_threshold (0.85) → 过
      否则 → 放弃该列对

闸门3 类型兼容度 ≥ type_threshold (0.8) → 进入该源列的过闸候选集
      否则 → 放弃
```

设计要点：

- **同名短路**：英文名 normalize（strip + lower）后精确相等 → 相似度 1.0，不发 API；
  同名 + 类型兼容过关即进候选，**不看注释**；
- **OR 语义**：英文名闸与注释闸任一通过即可，不需要权重合成；
- **缺注释自然处理**：注释为空 → 注释闸不通过，英文名闸不受影响。

闸门流程核对表：

| 流程表述（核对项） | 文档 3.4 设计 | 核对 |
|---|---|---|
| 从源表选择主键 | 源键集 = 主键 ∪ 唯一约束 ∪ 逻辑键（1~N 列） | ✓，不只是主键 |
| 目标表过滤后的字段（去掉复杂类型和指标） | 目标列池 = 全部列 − metric − complex | ✓ |
| 名称相似度超阈值 → 比类型 | 闸门 1：英文名 embedding ≥ 0.9 → 过闸 | ✓ |
| 名称低于阈值 → 比注释 | 否则闸门 2：注释 embedding ≥ 0.85 → 过闸；都不过 → 放弃 | ✓ |
| 注释超阈值 → 比类型 | 闸门 3：类型兼容 ≥ 0.8 → 进候选集，否则放弃 | ✓ |

配套说明：

- **同名短路**：英文名完全相同（大小写不敏感）→ 相似度 1.0，不发 API、不看注释，
  直接进入类型闸；
- **复合键**：闸门逐列对执行，每个源列独立过闸得候选集，再做集合指派（见 3.6）。

### 3.5 中文注释 embedding 通道（新增）

现状候选匹配完全未使用注释。新增注释通道的风险与对策：

| 风险 | 对策 |
|---|---|
| 注释大量为空（注释生成可选开关） | 注释通道定位为"补救通道"，OR 语义下不影响英文名闸 |
| 通用注释污染（`编号`/`名称`/`状态` 等） | 维护通用注释黑名单（配置 `name_similarity.comment_channel.generic_comment_blacklist`），命中则注释闸直接不通过；该列表与评分维度共用同一份（见 3.11） |
| 融合方式 | 递进式 OR 语义，不做加权合成 |
| 成本 | 向量缓存复用 LRU；注意 qwen embedding batch_size=10 限制 |

注释闸门独立配置：可单独指定 embedding 模型与阈值，与英文名闸解耦。

注释读取路径（v3 JSON 字段，实现时勿靠猜）：表注释 = `table_info.comment`；
字段注释 = `column_profiles.{col}.comment`。生成层闸门与评分维度
`comment_similarity` 都读同一路径。

### 3.6 集合指派（复合键，非贪心）

```text
组合成立 ⟺ 每个源列都有非空过闸候选集,且存在"每个源列配一个互不重复目标列"的完整指派
任一源列候选集为空 → 组合直接放弃(early-exit 只在这一层成立)
```

- **禁止贪心顺序**：col1 先占 X、col2 只匹配 X 时会误判失败（实际 col1→Y、col2→X
  合法）；
- 沿用 `_match_columns_as_set` 的穷举指派内核（N ≤ 3），阈值检查替换为递进闸门；
- 剪枝优化：源列按候选集大小升序排列，纯性能优化，不改变语义。

### 3.7 LLM 候选来源（可选）

- **触发条件**：`relationships.llm_candidates.enabled: true`（默认启用）；
- **输入范围**：与规则候选**共用统一域范围**（见 3.13），域未指定时全库两两组合；
  两路候选**并行独立**生成（方案 A）。LLM 的价值在"名字不同、注释也不同但业务
  相关"的场景，规则闸门覆盖不到；
- **不过递进闸门**：LLM 自身承担语义判断，不再用名称/注释/类型闸拦截（否则误杀
  "完全不同名但语义相关"的关系）；
- **候选层统一口径**：LLM 候选产出后执行与规则路径一致的目标列口径——剔除 metric /
  complex 角色的目标列（不是闸门，是候选合法性过滤）；
- **提示词与响应契约**：在现状基础上增加 `confidence` 字段（见 3.14），其余沿用
  （`_build_prompt` / `_parse_llm_response`）；
- **候选卫生处理（保留在产出器内，不并入统一管线）**：解析后立即执行
  `_filter_invalid_candidates`（丢弃同表自环与表对之外的越界候选，避免流进
  评分浪费 DB 查询）；入池前执行 `_canonicalize_candidate_identifiers`
  （表/列名大小写规范化为元数据标准名）——后者是池内按列对应对去重的前置
  条件，缺失会导致同一关系的大小写漂移表述被误判为两个关系。

### 3.8 合并去重与来源标记

- **去重顺序**：物理 FK 先直通并登记身份；规则候选与 LLM 候选（top_k 截断后）
  **合并入池，池内统一去重**（不再分来源单独去重）——按完整列对应对去重 +
  最小键过滤（见 3.9）+ 来源合并标记；最后排除与物理 FK 直通关系重复的所有
  候选。只有余下候选才进入评分。规则自身也不能假定没有重复，见 2.6；
- **去重键**：包含两张表身份及每一对源列与目标列的对应关系。把完整的列对应对
  排序后生成规范化身份；不分别排序 `source_columns`、`target_columns`，否则可能
  把不同的字段指派合并。`(A.id→B.id, A.code→B.code)` 与
  `(A.code→B.code, A.id→B.id)` 是同一关系；但
  `(A.id→B.code, A.code→B.id)` 是另一关系。存储候选时两侧列表始终按位置对齐；
  去重身份统一由升级版 `compute_relationship_id` 生成（见 2.6）；
- **物理 FK 优先**：直通 FK 不经评分、**直接写入关系文件**；规则或 LLM 发现与
  物理 FK 相同的完整列对应关系时，丢弃推断候选，仅保留直通关系——这项检查在
  合并去重之后、评分之前执行，不计算权重。对 LLM 返回的反向表述也要规范化或
  检查反向身份，避免漏掉已有物理 FK；
- **来源标记**：候选新增内存字段 `candidate_origin`（取值 `rule` / `llm` /
  `rule+llm`）。不得占用 `candidate["source"]` 键——那是源表对象，评分器
  （`scorer.py:84`）与决策器直接读取；
- **落地实现（P7 勘误，见代码审核）**：`candidate_origin` 不能只留在管线内存——
  若不透传到 `Relation`，`inference_method` 会把 `llm` 与 `rule+llm` 一并折叠成
  `llm_inferred`（见 §3.15），导致"仅 LLM / 重叠"这两档统计口径无法从输出关系
  反推。因此 `Relation` 数据模型新增 `candidate_origin: Optional[str]` 字段
  （`decision_engine._candidate_to_relation` 透传 `candidate.get("candidate_origin")`），
  仅推断关系有值；物理外键直通（`relationship_type == "foreign_key"`）不设置
  该字段（`Relation.to_dict()` 与 `composite_score`/`score_details`/
  `inference_method` 一并 pop 掉），其来源分档直接按 `relationship_type` 判断，
  不占用 `candidate_origin` 值域（因此不新增 `physical_foreign_key` 之类的值）；
- **统计口径（P7 勘误）**：最终关系统计按来源分档——物理 FK（`foreign_key_
  relationships`，按 `relationship_type` 判断）/ 仅规则（`rule_only_
  relationships`，`candidate_origin == "rule"`）/ 仅 LLM（`llm_only_
  relationships`，`candidate_origin == "llm"`）/ 重叠（`rule_llm_overlap_
  relationships`，`candidate_origin == "rule+llm"`）。替代旧版恒为 0 的
  `active_search_discoveries` / `dynamic_composite_discoveries`（依赖已删除的
  `single_active_search` / `composite_dynamic_same_name`，见 `writer.
  _calculate_statistics_v32`）。

### 3.9 候选池与最小键优先；LLM 候选 top-K

- **不熔断、完整比对**：同一源键集在目标表内可命中多个合法指派，全部生成候选；
- **规则候选不限量**：规则候选通过递进闸门（布尔判定）产生，数量受闸门自然约束，
  不做数量截断；将来如需控制数量，通过调节闸门阈值（name / comment / type
  threshold）实现；
- **LLM 候选 top-K**：LLM 一个表对可返回多条关系，总候选量 = 表对数 × 每对关系数，
  是评分成本的主要风险源。**时机：收到 LLM 返回的候选列后立即执行**——在代码中按
  `confidence`（见 3.14）降序排序，**全局**取前 `top_k` 个（配置
  `relationships.llm_candidates.top_k`，默认 50，**必须是 ≥1 的正整数**），其余丢弃；**先截断、后入池**，
  截断后的候选进入候选池，参与池内统一去重（见 3.1 第 ⑦⑧ 步）；
  confidence 并列时按返回顺序稳定截断。该截断仅用于限制评分阶段 DB 采样成本，
  发生在四维评分之前。`top_k: 0` / 负数不是"不限量"：配置校验拒绝非正整数；
  关闭 LLM 候选请用 `llm_candidates.enabled: false`；
- **最小键过滤（池内统一去重时执行，见 3.1 第 ⑧b 步）**：同池内，若单列键 col
  与目标列 X 的候选已存在，且复合键（col, other）的某指派同样把 col 配到 X，
  则该复合候选视为 superkey 冗余，丢弃。此规则**不区分候选来源**：逻辑键来源
  的超集已在检测器最小化过滤（JSON 生成阶段）中消除；但物理约束来源理论上
  也会出现 superkey（如单列 PK(id) 与复合 UK(id, tenant_id) 并存，两个键都会
  进入源键集），同样由本条兜底。

### 3.10 LLM 失败与重试

沿用现状 `_call_llm` 的重试机制（`llm_relationship_discovery.py:947-976`），配置化：

- `retry_times: 3`（重试 3 次，含首次共 4 次尝试；现状默认 2）；
- `retry_delay: 1`（重试间隔秒）；
- 每次失败记 warning 日志；最终失败记 error 日志并**跳过该表对**（返回空候选），
  不影响其他表对；
- **新增 CLI 汇总项**：LLM 请求数 / 成功数 / 失败表对数打印到控制台（现状失败只进
  日志文件）；
- LLM 整体不可用（如 API 故障）→ 降级为纯规则管线，命令返回非成功状态但产物可用；
- **异步批量调用保留**：`use_async`（读 `llm.langchain_config.use_async`）+
  `batch_size`（读 `llm.langchain_config.batch_size`，默认 50）分批并发
  （`discover_async` / `_discover_llm_candidates_async` /
  `batch_call_llm_async`）随"LLM 候选产出器"一并保留。统一后 `--step rel`
  默认启用 LLM 候选且表对数为 O(N²)，异步批量是必保的性能手段；删除范围仅限
  过滤/合并等管线逻辑，不碰调用层。

### 3.11 评分维度设计（name → comment 替换）

评分四维调整为：

| 维度 | 权重 | 说明 |
|---|---|---|
| `inclusion_rate` | 0.50 | 计算方式不变（源值在目标值中的包含率，DB 采样） |
| `comment_similarity` | 0.20 | **替代 `name_similarity`**，按列对回退 |
| `type_compatibility` | 0.20 | 保留：对 LLM 候选（不过闸）仍有防幻觉价值 |
| `jaccard_index` | 0.10 | 计算方式不变 |

这组 `0.50 / 0.20 / 0.20 / 0.10` 是待校准的初始权重。提高类型兼容权重
主要影响类型不兼容的候选；两个无关的整数字段仍可能同时取得高包含率和高类型分，
不能仅靠这次权重调整解决该类误判。实施前用已知正确关系和误判样例对比校准。

`comment_similarity` 维度得分规则（按列对回退）：

```text
双方都有注释 → 注释 embedding 相似度
任一缺失     → 退回名称相似度（生成层已认定语义资格,评分层不二次惩罚）
两者都缺     → 低默认值(`relationships.scoring.comment_fallback_score`,默认 0.3)
```

能力关闭 vs 数据缺失（P6 / 本次审核补充）：`name_similarity_service is None`
（无 embedding 环境）与 `comment_channel.enabled: false`（通道显式禁用）都是
评分能力不可用，统一退回名称相似度，**不**落到"两者都缺 → 0.3"。0.3 仅用于
通道已启用、但该列两侧注释确实不可用（空 / 黑名单）的数据级缺失。否则所有
候选一律拿 0.3 会整体压低 `composite_score`，边缘候选可能被 `accept_threshold`
误杀（排序不变，绝对分下移）。

配套要求：

- **低信息量注释检测（必修）**：通用注释（"唯一标识"/"编号"类）在评分维度中会
  高估语义分，叠加 inclusion_rate 的数据重合即假阳性放大器；评分维度与生成层
  闸门**共用同一份黑名单**——两者都读取
  `name_similarity.comment_channel.generic_comment_blacklist`（配置唯一，不存在
  第二份列表）；降权策略实施前用真实数据评估；
- **键校验同步**：`scorer.py:95-124` 的 `score_details` 键与 `weights` 一致性校验
  同步更新维度名；
- **阈值重校准**：候选池变化 + 维度替换后，`accept_threshold` 与高/中置信度阈值
  （0.9/0.8）必须用真实数据重新校准；
- **回退路径**：若实测注释质量波动导致评分不稳，可进一步收敛为"纯数据评分"
  （删语义维度，仅 inclusion_rate + jaccard），记为备选方案。

### 3.12 对象范围（View/MV 一视同仁参与）

- v3 JSON 产物已包含视图与物化视图（如 `orders.public.mv_category_sales.json`），
  `repository.load_all_tables()` 也会加载它们——**不做 object_type 过滤**，
  View/MV 与 table 一视同仁参与关系发现；
- View/MV 无物理主键/外键/唯一约束，主要依靠逻辑键候选与列画像参与匹配，
  其列同样进入目标列池（受 metric / complex 排除规则约束）；LLM 表对同样
  包含 View/MV；
- 派生数据的关系语义细化（如 MV 与基表之间的依赖血缘）留作后续专题，本阶段
  只保证"参与、不排除"。

### 3.13 域范围统一（--domain 参数）

现状：`--step rel` **完全忽略** `--domain` / `relationships.domain`（pipeline.py
与 candidate_generator.py 无任何 domain 引用，参数传了也无效）；只有 `rel_llm`
使用 `domain_filter` / `cross_domain` / `domain_resolver`。统一后若不同步，会
出现"同一次运行中规则候选覆盖全库、LLM 候选只覆盖指定域"的范围分裂。

**决定**：统一入口接收域参数，规则候选与 LLM 候选**共用同一表对范围**：

- `RelationshipDiscoveryPipeline` 新增 `domain_filter` / `cross_domain` /
  `domain_resolver` 参数；`metadata_cli.py` 的 rel 分支把阶段 3 已算好的
  `effective_domain` / `effective_cross_domain` / `domain_resolver` 传入，
  `--domain` 参数不再被忽略；
- 表对范围统一由 `DomainResolver.resolve_table_pairs` 计算（复用 rel_llm 现有
  入口），规则候选与 LLM 表对都从这份表对清单出发；
- `--domain` 语义沿用现状：**逗号分隔多个 domain 名**（如 `--domain A,B`），
  `--domain all` 使用所有 domain；不传时读 `relationships.domain`，yaml 也
  未配置则全表两两组合（现状行为不变）；
- 注意：`--domain all` 与"未配置"**不等价**——前者走 domain 分组逻辑
  （`cross_domain` 控制跨域配对），后者是 `combinations(available_tables, 2)`
  全库组合，不感知 domain 边界；
- 顺带收益：指定 domain 时规则候选的 O(N²) 遍历范围同步收缩——实现方式是
  候选生成器改为**按表对列表驱动迭代**（见 6.1），而非仅过滤 tables 字典。

### 3.14 LLM 候选置信度（用于 LLM 候选 top-K 排序）

**决定**：要求 LLM 为它发现的每个关系附带置信度，完成"提示词要求返回 + 解析透传 +
结构校验"，并用于 LLM 候选的 top-K 排序截断（见 3.9）。除此之外**不做其他消费**
（不做阈值预过滤、不进评分权重）；进一步消费策略留作后续（见 10. 开放问题 1）。

提示词改动（`RELATIONSHIP_DISCOVERY_PROMPT`）：

- 输出格式为每个关系增加 `confidence` 字段，0~1 之间的小数；
- 单列关联示例：

```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "dim_store"},
      "from_column": "region_id",
      "to_table": {"schema": "public", "table": "dim_region"},
      "to_column": "region_id",
      "confidence": 0.92
    }
  ]
}
```

- 复合关联同样附带 `confidence`（字段用数组，格式同现状多列示例）；
- 提示词必须写明判定依据与防陷阱约束：

```text
- confidence：0~1 之间的小数，表示你认为该关系是真实主外键关联的置信度。
- 置信度主要依据字段名相似、字段注释语义、类型兼容与复合键结构；
  样例数据值域仅供参考——两个表都是自增整型主键时数据天然重合，
  不要因为数据重合就给高分（后续会由数据库验证兜底）。
```

代码改动（`llm_relationship_discovery.py` 保留部分）：

- `_parse_llm_response`：透传 `confidence` 字段；
- `_validate_response_structure`：`confidence` 存在时必须是数值且落在 `[0, 1]`；
- **缺失/非法时不连坐**：该关系仍保留，`confidence` 记默认值 `0.5` 并写 warning
  日志（单个字段问题不导致整个表对失败）。

### 3.15 inference_method 新分类体系（v3 专属，零兼容）

新统一管线删除旧两阶段/特权模式实现后，旧 candidate_type 值
（`composite_dynamic_same_name`、`single_defined_constraint*`、
`single_active_search` 等）整体消失。现状
`decision_engine._candidate_to_relation` 直接把 candidate_type 当作
inference_method 使用（`decision_engine.py:246`），writer 的
`_parse_discovery_info` 按旧字符串精确匹配映射 discovery_method /
target_source_type / source_constraint（`writer.py:305-350+`）——两者都必须按
新值集重建。

**原则**：v3 专属新值集，**零向后兼容**——不识别旧值、不保留任何旧值兼容分支；
旧 JSON 属性与旧字符串不参与新管线。下游消费方（CQL 生成、统计）随新值集同步
适配，记入影响备忘录。

新值集（仅覆盖推断关系，`relationship_type == "inferred"`）：

| inference_method | 来源 | discovery_method（writer 输出） |
|---|---|---|
| `rule_physical_key` | 规则候选，源键集为物理 PK / UK | `physical_key_matching` |
| `rule_logical_key` | 规则候选，源键集为逻辑键 | `logical_key_matching` |
| `llm_inferred` | LLM 候选（与规则重叠时同样记此值，来源分档靠 `candidate_origin`） | `llm_inferred` |

**勘误（P5，见代码审核）**：初版本表曾列 `physical_foreign_key` → `foreign_key`，
但物理外键直通（`relationship_type == "foreign_key"`）走 `repository.
collect_foreign_keys` 构造、`writer.py` 独立分支序列化，从不设置
`inference_method`、也不经过 `_parse_discovery_info`；其 `discovery_method`
固定沿用历史既有值 `foreign_key_constraint`（早于本次改造，见
`REFACTOR_SUMMARY_V32.md`），维持不变，不纳入本次 v3 taxonomy 改造范围。
`physical_foreign_key` 已从值集与 `_INFERENCE_METHOD_DISCOVERY_MAP` 中删除，
避免死代码。

配套要求：

- `_parse_discovery_info` 映射表按上表重建；**未知值不再回退
  `standard_matching`，而是报错**（新体系内所有值必须显式覆盖），避免静默丢失
  `target_source_type` / `source_constraint`；
- 删除 `single_active_search` 等一切向后兼容分支；
- `target_source_type` / `source_constraint` 字段语义保持不变（仅映射来源变化）；
- 物理外键直通不纳入 `inference_method` 体系，维持独立的 `foreign_key_constraint`
  契约（见上方勘误）。

## 4. 配置设计

### 4.1 新配置节点

```yaml
relationships:
  # LLM 候选来源开关(放在 llm 节点之外,避免 resolver 白名单报错)
  llm_candidates:
    enabled: true
    top_k: 50             # 必须 ≥1；关闭 LLM 候选请用 enabled: false，0 不是"不限量"

  # LLM 模型覆盖与重试(全部为 resolver 白名单字段)
  llm:
    retry_times: 3          # 重试次数(含首次共4次尝试)
    retry_delay: 1          # 重试间隔(秒)
    langchain_config:
      use_async: true       # 异步并发开关(大表场景必保,见 3.10)
      batch_size: 10        # 表对分批大小:发现器读 langchain_config.batch_size(默认 50)
                            # ⚠️ 顶层 llm.batch_size 是 LLMService 遗留死字段,与表对分批无关,勿用

  # 候选匹配统一配置(替代 single_column / composite 的匹配部分)
  candidate_matching:
    max_columns: 3                    # 键集最大列数
    name_threshold: 0.9               # 英文名 embedding 闸门
    comment_threshold: 0.85           # 中文注释 embedding 闸门
    type_threshold: 0.8               # 类型兼容硬门槛
    logical_key_min_confidence: 0.8   # 逻辑键进入源键集的最低置信度
    exclude_target_semantic_roles:    # 目标列池剔除角色
      - metric
    exclude_target_complex_types: true

  # 名称相似度(移除 method: string)
  name_similarity:
    method: embedding                 # 唯一取值
    cache_size: 5000
    comment_channel:                  # 注释通道独立配置(生成闸门与评分维度共用)
      enabled: true
      method: embedding
      cache_size: 5000
      generic_comment_blacklist:      # 低信息量注释黑名单:两处消费者共用一份
        - 编号
        - 名称
        - 状态
        - 备注
        - 描述

  # 物理外键直通(现状保留,不动)
  # 评分权重(name_similarity 替换为 comment_similarity,按列对回退)
  weights:
    inclusion_rate: 0.50
    comment_similarity: 0.20
    type_compatibility: 0.20
    jaccard_index: 0.10

  # 评分新增参数(weights 保持现状路径,新增参数集中放这里)
  scoring:
    comment_fallback_score: 0.3   # 双方均无注释时 comment_similarity 维度的得分
```

### 4.2 Embedding 模型名

- 名称闸沿用全局 `embedding` 节点：`embedding.providers.qwen.model`
  （现状 `text-embedding-v3`）；
- 注释通道可在 `name_similarity.comment_channel` 下独立指定 provider / model，
  首版默认复用全局 embedding 配置。

### 4.3 废弃项

- CLI：`--step rel_llm` 可选值及其专用分支；
- 配置：`single_column.*`、`composite.*`（匹配部分）、`name_similarity.method: string`；
- 旧配置检测到即报错并提示新路径（沿用 doc 12 迁移策略：不静默兼容）；
- **删除前置条件**：`single_column` / `composite` 删除前，必须先将
  `exclude_semantic_roles` 搬入 `logical_key_detection` 新路径并完成 generator
  改造（见 2.8），两者同批实施。

### 4.4 行为语义变化提醒

- `--step rel` 默认启用 LLM 候选（`llm_candidates.enabled` 默认 true）；纯规则
  执行需显式 `llm_candidates.enabled: false`；
- 评分维度 `name_similarity` → `comment_similarity`：`score_details` 结构变化，
  下游消费关系 JSON 的代码（writer、统计）需同步适配；决策阈值必须重校准；
- 阈值均为 embedding 模式校准值，初始值需用真实数据回归校准（校准方法同 doc 13：
  新旧对比候选数量 / 最终关系数量，观察单闸门阈值边际影响）。

## 5. 降级语义

- **无 embedding 环境**：名称闸退化为"同名通过、不同名放弃"（仅同名短路），注释闸
  自动禁用，类型闸正常执行；
- **LLM 不可用**：`llm_candidates.enabled: true` 但全部表对调用失败 → 规则候选
  照常走完管线，命令返回非成功状态并汇总失败表对数，产物可用。

## 6. 代码修改范围

### 6.1 修改

- `metaweave/core/relationships/candidate_generator.py`
  - 重写 `generate_candidates()`：统一收集源键集 → 目标列池 → 递进闸门 → 集合指派 →
    规则候选不做数量截断（去重与最小键过滤统一在池内执行，见 3.8）；
  - 迭代方式由"全表嵌套遍历"改为"按 `DomainResolver.resolve_table_pairs`
    返回的表对列表驱动"（domain 未指定时该列表 = 全表两两组合，现状行为
    不变）；`tables` 完整字典保留，仅用于列/元数据查找，不用于范围限定
    （见 3.13）；
  - 新增 LLM 候选入池入口（接收外部 LLM 候选，合并入池后统一去重，
    不再单独去重）；入池时复用 3.3 已构建的目标列池对 LLM 候选做合法性过滤
    （剔除 metric / complex 角色的目标列，见 3.7 候选层统一口径）；
  - 统一物理 FK 关系身份与候选身份：候选去重与 FK 排重全部复用升级版
    `compute_relationship_id`（按列对应对排序后哈希），废弃 `_make_signature`
    （见 2.6）；合并后、评分前排除与直通 FK 重复的候选；
  - 删除：`_find_target_columns`（两阶段特权模式）、`_find_dynamic_same_name`、
    `_collect_target_combinations_for_privilege_mode`、单列三级过滤、
    `_is_qualified_target_column`；
  - 保留并改造：`_match_columns_as_set` 穷举指派内核（阈值检查换递进闸门）、
    `_collect_source_combinations`（去掉 `2 <= len` 限制）；
  - **`_make_signature` 整体删除**：新代码中不再存在该函数；关系身份统一由
    升级版 `compute_relationship_id` 生成（见 2.6），候选去重与 FK 排重都调用它。
- `metaweave/core/relationships/llm_relationship_discovery.py`（**收缩**）
  - 保留：`_build_prompt`、`_parse_llm_response`、`_call_llm`（含重试）、
    表对解析（domain 过滤）、LLM 候选产出、**异步批量调用**（`discover` /
    `discover_async`、`_discover_llm_candidates_async`、`batch_call_llm_async`、
    `use_async` / `batch_size` 配置读取，见 3.10）、**候选卫生处理**
    （`_filter_invalid_candidates`：解析后立即丢弃同表自环与表对之外的越界
    候选；`_canonicalize_candidate_identifiers`：入池前把表/列名大小写规范化
    为元数据标准名——池内按列对应对去重的前置条件，见 3.7）；
  - 提示词与解析支持 `confidence` 字段：输出格式要求 0~1 小数、解析透传、
    结构校验（缺失/非法记默认 0.5 + warning，不连坐，见 3.14）；
  - 删除：去重、过滤已有 FK、语义角色过滤、类型过滤、阈值过滤、与 FK 合并等
    管线逻辑（统一管线吸收）；
  - 删除后 LLM 候选为"规范化的干净候选列表"，交由统一管线合并。
- `metaweave/core/relationships/pipeline.py`（`--step rel` 的执行引擎
  `RelationshipDiscoveryPipeline`）
  - 在现有 FK 直通、候选生成、评分、决策与输出之间接入可选 LLM 候选、来源
    内部去重、跨来源合并及已直通 FK 排除；配置关闭时只执行规则候选路径；
  - LLM 候选按 `confidence` 排序后全局取前 `top_k`（见 3.9），规则候选不做
    数量截断；
  - 新增 `domain_filter` / `cross_domain` / `domain_resolver` 接收能力，规则
    与 LLM 候选共用统一表对范围（见 3.13）；
  - `--step standard` 的 rel 子步骤共用该引擎，standard 编排本身不修改、
    不承诺可用（见 6.2）。
- `metaweave/cli/metadata_cli.py`
  - 删除 `rel_llm` 的 `click.Choice` 值与独立分支；
  - `rel` 分支改为：FK 直通 → 规则候选 →（llm_candidates.enabled 时）LLM 候选 →
    合并入池与池内统一去重（含最小键过滤）→ 排除已直通 FK → 评分 → 决策，
    汇总增加来源维度统计与 LLM 失败表对数；
  - rel 分支把 `effective_domain` / `effective_cross_domain` / `domain_resolver`
    传入执行引擎（`--domain` 参数不再被忽略，见 3.13）。
- `metaweave/core/relationships/name_similarity.py`
  - 移除 `method: string` / SequenceMatcher 业务路径；保留同名短路；
  - 新增注释相似度接口（独立 embedding 配置与缓存）。
- `metaweave/core/relationships/scorer.py`
  - 评分维度 `name_similarity` → `comment_similarity`（按列对回退 + 低默认值）；
  - `score_details` 键与 `weights` 一致性校验同步；
  - 清理过时注释（`:30` "Levenshtein 算法"）；同步修正关系发现内部编排中的
    过时评分日志文案（`pipeline.py:148` "6维度" → "4维度"）。
- `metaweave/core/relationships/decision_engine.py`（仅 v3 适配修复）
  - `_has_independent_constraint`：删掉列级 `structure_flags` 读取，改为读取
    表级 `physical_constraints`（单列 `primary_key.columns` 或
    `unique_constraints[].columns`）+ 表级 `table_profile.indexes[]` 中的
    **非 partial 单列唯一索引**（`is_unique: true`、单列键、`condition` 为空）；
  - 抑制规则本身保持现状（复合被接受 → 抑制同表对无独立约束的单列），例外
    口径：单列为物理主键 / 唯一约束 / 唯一索引时保留；`_apply_suppression`
    docstring 中的"单列Index"保留并**真正实现**。
- `metaweave/core/relationships/repository.py`
  - `_is_columns_unique` **仅替换第 1 级物理约束的读取源**：单列分支由列级
    `structure_flags` 改为表级 `physical_constraints`（单列 PK/UK）；第 2 级
    统计回退（`uniqueness >= 0.95`，复合取最小唯一性）保持不变；
  - `compute_relationship_id` 升级为"按完整列对应对排序后哈希"
    （`sorted(f"{s}={t}" ...)` 再哈希），供 FK 直通与候选排重共用（见 2.6/3.8）。
- `metaweave/core/relationships/writer.py`
  - 输出键标注（主键/唯一键）改为按表级 `physical_constraints` 判定；
  - `_parse_discovery_info` 映射表按 3.15 的新值集重建：删除全部旧值与向后兼容
    分支（含 `single_active_search`），未知值报错而非回退 `standard_matching`。
- `metaweave/core/metadata/generator.py`（跨模块，doc 12 边界的配置读取最小改动）
  - 删除 `:107-123` 从 `single_column` / `composite` 注入逻辑键排除角色的代码；
  - 逻辑键排除角色改由 `logical_key_detection` 节点的新键直接提供（见 2.8）。
- `configs/metadata_config.yaml`
  - 新增 `relationships.llm_candidates`（开关）、`relationships.llm`（重试参数）、
    `relationships.candidate_matching`、`name_similarity.comment_channel`；删除
    `single_column` / `composite` 匹配配置与 `method: string` 示例；
  - `metaweave/services/llm_config_resolver.py` **不修改**：`relationships.llm`
    只保留 resolver 白名单字段（模型覆盖 + `retry_times` / `retry_delay`），
    开关 `relationships.llm_candidates.enabled` 位于 llm 节点之外，由管线直接
    读取，不经过 resolver。

### 6.2 不修改

- `metadata --step standard` 的编排实现（`metadata_cli.py` 中 standard 分支）——
  不修改、过渡期不承诺可用；
- `metaweave/cli/pipeline_cli.py`（`pipeline generate` / `pipeline load`）——
  不修改、过渡期不承诺可用；
- 物理外键直通逻辑；
- 逻辑主键检测器（`logical_key_detector.py`）。

## 7. 实施顺序

0. 先行修复（独立提交，附单测）：`decision_engine._has_independent_constraint`
   改为读取表级 `physical_constraints`，修正 `_apply_suppression` docstring；
1. 配置层：新增 `relationships.llm_candidates` / `relationships.llm` /
   `candidate_matching` / `comment_channel` 节点与校验；旧配置报错提示；
   **同步完成逻辑键检测配置迁移**（2.8：新路径生效 →
   删除 `single_column` / `composite`，同一批内完成）；
2. `name_similarity.py`：移除 SequenceMatcher 路径，新增注释通道接口；
3. `candidate_generator.py`：源键集统一收集 + 目标列池 + 递进闸门 + 集合指派 +
   去重 / 最小键优先（规则候选不做数量截断）；
4. `llm_relationship_discovery.py`：收缩为"LLM 候选产出器"（删除管线逻辑）；
5. `--step rel` 的内部编排组装统一管线：FK 直通并登记身份 →
   规则与 LLM 候选合并入池 → 池内统一去重（含最小键过滤）→
   排除与 FK 重复的候选 → 评分 → 决策；
6. `metadata_cli.py`：删除 rel_llm 入口，rel 分支接入开关与汇总统计；
7. 回归：FK 直通不变；inclusion_rate / jaccard 计算方式不变验证；新旧候选对比
   报告（数量、重合度、差异分析）；
8. 阈值校准：决策阈值（accept_threshold、高/中置信度）按新评分分布重校准；
   递进闸门阈值按 4.4 方法回归固化；
9. 清理旧配置与旧测试（特权模式、动态同名、两阶段匹配、rel_llm 独立管线相关用例）。

## 8. 测试计划

### 8.1 统一收集测试

- 单列 PK / 单列 UK / 单列逻辑键进入源键集（现状复合路径会漏掉它们）；
- N 列复合键与单列键走同一匹配器；
- 目录含 View/MV JSON 时，View/MV 与 table 一同进入候选与 LLM 表对
  （不做 object_type 排除）。

### 8.2 闸门组合测试

- 英文名同名（大小写不同）→ 短路 1.0，不发 embedding 调用（mock 断言）；
- 英文名低于阈值 + 注释高于阈值 → 通过；
- 英文名低于阈值 + 注释为空 → 放弃；
- 英文名低于阈值 + 注释为通用黑名单词 → 放弃；
- 通过语义闸 + 类型兼容低于阈值 → 放弃；
- 目标列角色为 metric / complex → 在列池构建阶段即剔除。

### 8.3 集合指派测试（假阴性回归）

- col1 候选 {X, Y}（X 分高）、col2 候选 {X}：必须找到 col1→Y、col2→X 的指派
  （贪心实现会误判失败）；
- 任一源列候选集为空 → 组合放弃；
- 指派不允许同一目标列重复使用。

### 8.4 合并去重测试

- 同一复合关系分别由物理键与逻辑键进入候选池 → 池内统一去重后只留一个；
- LLM 重复返回同一完整列对应关系 → 池内统一去重后只留一个（LLM 不做独立
  去重，与规则候选合并后一起处理）；
- 规则与 LLM 提出同一列对 → 合并，来源标记 `rule+llm`；
- `(A.id→B.id, A.code→B.code)` 与 `(A.code→B.code, A.id→B.id)` →
  同一关系，合并且保留正确的逐列对应；
- `(A.id→B.id, A.code→B.code)` 与 `(A.id→B.code, A.code→B.id)` →
  不同字段指派，不能合并；
- 规则或 LLM 候选与已有物理 FK 完全相同（含 LLM 反向表述）→
  只保留直通关系，候选在评分前删除，评分器不收到该候选；
- FK 去重接口统一身份后，不再拿 `relationship_id` 与文本签名比较；
- 升级版 `compute_relationship_id`：同一关系（列对应顺序不同）同 ID；不同字段
  指派不同 ID；
- 池内最小键过滤：单列键已成立时，包含它的复合键（superkey）候选在池内统一
  去重时被丢弃——不区分来源，逻辑键/物理约束/LLM 三来源的超集都由本条处理；
  物理约束 superkey 用例：单列 PK(id) + 复合 UK(id, tenant_id) 并存时，复合
  候选被丢弃；
- LLM 返回大小写漂移的表/列名 → 入池前规范化，与规则候选正确合并为同一关系；
- LLM 返回同表自环或表对之外的候选 → 解析后丢弃，不进池、不评分。
- LLM 候选按 confidence 排序取前 top_k 生效，规则候选不受数量截断；
- 去重键生效。

### 8.5 LLM 开关与失败测试

- `llm_candidates.enabled: false` → 零 LLM 调用，纯规则管线；
- `llm_candidates.enabled: true` + 单表对失败 → 重试 3 次后跳过该表对，其余
  表对正常，汇总报告失败表对数；
- 配置含 `relationships.llm_candidates.enabled` 时，`relationships.llm` 的
  resolver 解析不报错（白名单兼容）；
- 异步批量调用保留：`use_async: true` 时按 `batch_size` 分批并发，行为与现状
  一致；统一管线可正常走通异步路径。
- LLM 全部失败 → 规则候选照常走完管线，命令返回非成功状态。

### 8.6 降级测试

- 无 embedding 配置：同名通过、不同名放弃、注释闸禁用、管线可运行。

### 8.7 行为不变测试（锚点）

- 物理外键直通产物与改造前一致；
- `inclusion_rate` / `jaccard_index` 对同一批候选的计算结果与改造前一致；
- `--step rel` 的内部编排在 LLM 开关开启时接入 LLM 候选；关闭时只走规则候选。

### 8.8 评分维度测试

- 双方都有注释 → 使用注释相似度；
- 任一缺失 → 退回名称相似度（不与生成层闸门冲突）；
- 两者都缺 → 低默认值（0.3）；
- 同名不同义（如 orders.id vs users.id）→ 注释维度给出区分（低于同名短路值）；
- 低信息量注释（"唯一标识"类）→ 检测并降权/拦截；
- 生成层闸门与评分维度读取**同一份**黑名单（修改
  `comment_channel.generic_comment_blacklist` 后两处行为同步变化）；
- `score_details` 键与 `weights` 一致性校验通过。

### 8.9 v3 适配测试

- v3 JSON（无 column_profiles.structure_flags）下，`_has_independent_constraint`
  对单列物理 PK / 单列 UK / **非 partial 单列唯一索引** 返回 True；partial
  唯一索引（`condition` 非空）不算独立约束；
- 同表对存在复合关系时，源列为单列物理键的单列关系**不被抑制**；
- `repository._is_columns_unique` 单列路径按表级约束判定唯一性；
- writer 输出键标注按表级约束生成。

### 8.10 配置迁移等价性测试

- 迁移后（`single_column` / `composite` 已删除、新路径生效），`--step ddl` /
  `--step json` 的逻辑键检测排除角色与迁移前完全一致；
- generator 不再读取 `single_column` / `composite`（移除节点后无任何读取引用）；
- 旧节点存在时报错路径正确（不静默兼容）。

### 8.11 域范围测试

- `--step rel --domain X` 时，规则候选与 LLM 候选的表对范围一致（均不含域外
  表对）；
- `--domain A,B` 逗号分隔多 domain 生效（复用 `DomainResolver._parse_domain_filter`）；
- `--domain all` 走 domain 分组逻辑（`cross_domain` 生效），与"未配置"的全库
  `combinations` 路径区分；
- 未指定 domain 且 yaml 未配置 → 全表两两组合（现状行为不变）；
- 指定 domain 时，规则候选生成器仅遍历域内表对（按表对列表驱动迭代，不靠
  过滤 tables 字典）；
- `--step rel` 传入 `--domain` 不再被忽略（执行引擎实际收到域参数）。

### 8.12 LLM 候选置信度测试

- LLM 返回含合法 `confidence`（0~1 数值）→ 解析透传,候选携带该值；
- `confidence` 缺失 → 候选保留,记默认值 0.5 + warning 日志；
- `confidence` 非法（非数值 / 越界 / 字符串）→ 候选保留,记默认值 0.5 +
  warning 日志,不导致表对失败；
- 单列与复合关联的 `confidence` 均正常解析；
- LLM 候选超过 `top_k` 时按 `confidence` 降序全局截断，并列者按返回顺序稳定
  截断，规则候选不受限；
- top_k 截断发生在与规则候选**合并去重之前**（先截断、后去重）；与直通 FK
  相同的候选在评分前被剔除（直通 FK 直接写入关系文件）。

### 8.13 inference_method 映射测试

- 新值集四种 inference_method 分别映射到正确的 discovery_method，且
  target_source_type / source_constraint 正确生成；
- 旧值（composite_dynamic_same_name、single_defined_constraint* 等）不再出现
  于任何输出；
- 未知 inference_method → 报错（不静默回退 standard_matching）；
- 规则与 LLM 重叠候选 → inference_method 记 `llm_inferred`，来源分档靠
  candidate_origin。

## 9. 验收标准

1. 候选生成只有一条规则路径：单列与复合键共用同一匹配器；
2. 目标侧仅剔除 metric / complex，PK/UK/索引/audit/description 一律平等；
3. 匹配按递进闸门执行：英文名 → 注释 → 类型；同名短路成立且不发 API；
4. 复合键指派非贪心（假阴性用例通过）；
5. 规则与 LLM 分别内部去重，再跨来源合并；列对应对顺序归一化且逐列对应
   不丢失，来源标记正确；与物理 FK 重复的候选在评分前排除；
6. `--step rel_llm` 不再存在；`relationships.llm_candidates.enabled`（默认 true）
   控制 LLM 候选；
7. LLM 失败按重试策略处理（3 次重试、1 秒间隔、跳过表对、汇总上报）；
8. 规则候选不做数量截断（数量由闸门阈值调控）；LLM 候选按 confidence 排序取
   前 top_k；去重、最小键优先生效；
9. 无 embedding 环境按第 5 节降级语义运行；
10. 物理外键直通行为不变；inclusion_rate / jaccard 计算方式不变；评分维度按
    name → comment 替换生效（含按列对回退与低默认值）；决策阈值完成重校准；
11. 旧配置报错并给出新路径提示；`--step rel` 的内部编排完成接入；
12. v3 JSON（无列级 structure_flags）下，决策器抑制例外（单列 PK / UK /
    非 partial 唯一索引）、单列唯一性判定与输出键标注均按表级约束正确工作；
13. `single_column` / `composite` 节点删除后，`--step ddl` / `--step json` 的
    逻辑键检测行为与迁移前一致（新路径 `logical_key_detection.*` 生效）；
14. 目录中存在 View/MV JSON 时，View/MV 与 table 一同参与关系发现，不因对象
    类型被排除；
15. `--step rel` 独立执行正常；`--step standard` 与 `pipeline generate` 不纳入
    本阶段验收；
16. `--step rel --domain X` 的规则与 LLM 候选共用同一表对范围，`--domain` 参数
    不再被忽略（支持逗号分隔多 domain 与 `all`）；
17. LLM 为每个发现的关系返回 `confidence`（0~1），解析透传并完成结构校验；
    缺失/非法时默认 0.5 且不影响候选保留；
18. 关系输出按 3.15 新值集标注 inference_method / discovery_method，无任何旧值
    与向后兼容分支；未知值报错；
19. LLM 候选生成的异步批量调用能力保留（use_async / batch_size 配置生效）。

## 10. 开放问题（本阶段不定,记录待议）

1. **LLM 自报置信度的进一步消费**：本阶段已要求 LLM 返回 `confidence`（见 3.14）
   并用于 LLM 候选 top-K 排序截断（见 3.9）。后续可选项：候选层预过滤（可配置
   阈值）等。注意 LLM 自报置信度校准差、跨模型不可比，只适合同一次运行内的
   相对排序与粗过滤，不建议进入评分权重；任何阈值都需按模型实测校准；
2. **非 partial 唯一索引并入源侧键集**：唯一索引与唯一约束的唯一性保证等价，是否将
   "非 partial、非 constraint-backed 的唯一索引"纳入源键集合，留待后续专题讨论；
3. **注释黑名单的维护方式**：静态配置表 vs 按词频动态识别，待真实数据评估；
4. **注释通道的独立模型选择**：首版默认复用全局 embedding 模型，配置预留独立节点；
5. **评分回退路径**：若注释质量波动导致评分不稳，可收敛为"纯数据评分"
   （仅 inclusion_rate + jaccard），备选方案已记录于 3.11；
6. **View/MV 派生语义**：本阶段 View/MV 一视同仁参与（见 3.12）；派生数据的
   关系语义（如 MV 依赖基表、视图列血缘）待专题讨论。
