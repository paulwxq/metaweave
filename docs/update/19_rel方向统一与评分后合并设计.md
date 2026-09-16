# Rel 方向统一与评分后合并设计

## 1. 文档目的

解决两个问题:

1. **方向混乱**:rel 产物的 from/to 方向随候选来源漂移(规则候选"主键→外键"、
   LLM 候选与 FK 直通"外键→主键"),下游(尤其 CQL)需要 1:N 翻转兜底;
2. **反向重复**:池内去重键包含方向,同一业务关系的"规则正向 + LLM 反向"两条
   不合并,双双落盘(现状实例:`categories.category_id ↔ products.category_id`
   各存一条)。

目标:rel 产物方向按基数分层统一——**N:1 恒为引用方(外键侧)→ 被引用方(键侧)**;
**1:1** 按方向决策层级定方向(规则键侧优先,字典序兜底);**M:N** 作为对称推断
关联,按字典序定方向(不称隐式外键)。同一业务关系只出现一条,CQL 删除翻转逻辑
变纯消费。

**验收入口仍是独立执行的 `metadata --step rel`;`--step json` 零改动。**

## 2. 现状确认

### 2.1 三种来源的方向约定不一致

| 来源 | from 是什么 | 方向语义 |
|---|---|---|
| 规则候选 | 源键集所在表(键侧)——搜索起点 | **机械方向,无"谁引用谁"语义** |
| LLM 候选 | 提示词约定 from = 外键表(多端) | 语义方向:外键→主键 |
| FK 直通 | 外键所在表 | 语义方向:外键→主键 |

数据库惯例:SQL 里外键定义在子表、`REFERENCES` 指向父表;元数据/图工具的关联
边普遍从引用方指向被引用方,即 **from = 引用方,to = 被引用方**。但该语义
**仅对 N:1 成立**:1:1 两端都唯一,单靠基数无法判断哪边是引用方;M:N 两端都不
唯一,不存在"外键字段→主键字段"语义。1:1 / M:N 的方向由 §3.3 的方向决策层级
与字典序决定。三个来源中只有规则候选违背 N:1 惯例。

### 2.2 池内去重键含方向,反向不合并

升级版 `compute_relationship_id` 的签名含"源表→目标表"顺序——同一条业务关系
的"规则正向(键→外键)"与"LLM 反向(外键→键)"身份不同,合并阶段视作两条。
只有 FK 排除做了双向检查(`_reverse_relationship_id`),池内合并没有。

后果:统计双计(本应是 `rule+llm` 重叠,实际算成 rule 1 条 + llm 1 条)、评分
双跑、CQL 端翻转后同向重复。

### 2.3 LLM 返回不含 cardinality

提示词输出只有 `type / from_table / from_column / to_table / to_column /
confidence`,**没有 cardinality 字段**;方向约定隐含"from 是外键表"。基数完全
由评分阶段计算,最终以计算为准——LLM 判反时(数据算出 1:N),以计算值写文件。

### 2.4 不修改的后果(现状问题的完整清单)

1. **同一业务关系双份落盘**:规则正向与 LLM 反向各存一条(已验证实例:
   `categories.category_id → products.category_id 1:N`(规则)与
   `products.category_id → categories.category_id N:1`(LLM)同时存在于当前
   rel 产物);
2. **来源统计失真**:四档统计把同一条关系算成"1 条 rule + 1 条 llm",而不是
   "1 条 rule+llm 重叠"——`rule_llm_overlap_relationships` 被低估,
   `rule_only` / `llm_only` 被高估;
3. **无控制的重复评分**:同源重复、FK 重复和明显 superkey 也可能进入评分,
   产生无意义的数据库采样;
4. **下游必须自带方向解读逻辑**:rel JSON 的 from/to 语义随来源漂移,任何
   消费方(不止 CQL)都要理解"必须看 cardinality 才知道谁是外键侧"——否则把
   1:N 的 from 误当外键表,方向判反;
5. **每个新消费方重复踩坑**:CQL 的 1:N 翻转是打补丁;未来的血缘、图谱加载、
   统计报表等消费方要么各自实现翻转,要么方向错误;
6. **1:1 / M:N 反向重复隐患**:无向语义的关系,两个方向可能同样并存且不合并
   (合并身份含方向);
7. **同表对同方向多列对在 CQL 端塌缩(已知下游限制,本次不解决)**:不同字段
   映射(如 `orders.shipping_address_id→addresses.id` 与
   `orders.billing_address_id→addresses.id`)是两条不同的业务关系,rel 层应
   保留两条;塌缩是 CQL MERGE 表达与 doc 18 去重策略的问题,与 rel 合并
   无关;
8. **产物不可复现风险**:1:1 / M:N 的方向取决于候选入池顺序,同一输入两次
   运行可能输出 A→B 与 B→A 两种写法。

以上后果均已由 §3 的设计消除:生成时方向规范化 + 评分后纠偏(1/4/5)、
统一身份合并(1/2/6)、评分前过滤消除同源重复/FK 重复/superkey 的无意义采样
(3;跨来源重叠候选允许分别评分,是评分后合并所需的保留成本)、确定性方向
决策(8);第 7 项为已知下游限制,由 doc 18 解决,本次不涉及。

## 3. 目标设计

### 3.1 分开评分、结果合并

```text
规则候选 → 生成时即规范化方向(关联字段表 → 键表;生成阶段已知,零成本)
        → 池内同向去重 → 最小键过滤 → FK 排除(双向)
        → 评分(物理键候选预期 N:1 / 1:1;逻辑键候选以评分计算为准)──┐
LLM 候选 → 生成(契约方向:外键→主键)→ 合法化                        │
        → 同向身份去重(同身份保留最高 confidence)                  │
        → 排序(confidence 降序、规范身份升序)→ top_k 截断          │
        → 最小键过滤(LLM 池单列 ∪ 规则池单列判定)                 │
        → FK 排除(双向) → 评分 ──────────────────────────────────┴→ 合并(写文件前):
    ① 评分后纠偏(按来源,见 3.2.2):LLM 判反 1:N → 翻转、改写 N:1 并重算
       inclusion_rate 与 composite_score;物理键规则候选 1:N/M:N → 按约束
       语义修正基数(1:1 / N:1,不翻转,记 warning);逻辑键规则候选 1:N/M:N
       → 丢弃并告警
    ② 无向身份分组:所有评分后候选按无向身份进组(见 3.3,不依赖方向)
    ③ 组内决定最终 cardinality(物理规则证据 > 有效逻辑规则证据 >
       纯 LLM 高分候选,见 3.3)
    ④ 按最终 cardinality 决定唯一方向:N:1 → 有规则证据时使用最高优先级
       规则候选方向,纯 LLM 使用决定最终 cardinality 的获胜候选方向;
       1:1 → 规则证据优先(物理>逻辑),否则字典序;M:N → 字典序
    ⑤ 组内所有候选规范到最终方向:翻转的取 reverse_inclusion_rate 并重算
       composite_score
    ⑥ 字段级合并(端点/cardinality/key_origin/candidate_origin/
       score_details 各按契约,见 3.3)
    ⑦ 生成最终有向 relationship_id
→ 决策(阈值 + 抑制,合并后的完整关系集上执行,位置不变)→ 写文件
```

- **只有"跨来源合并"与反向等价关系挪到评分后**;同源同向去重、最小键过滤、
  FK 排除留在各池评分前,避免浪费 DB 采样——**跨来源重叠及反向等价候选可能
  分别评分**,冗余最小;
- 评分维度、权重和现有推断候选 cardinality 计算公式不变;评分器的内部返回
  信息与总分重算接口按 §3.2.2 扩展。

#### 3.1.1 评分前过滤与同源去重落点

- **同源同向去重(评分前)**:规则池按统一身份去重(方向已生成时规范化);LLM
  池按统一身份去重(契约方向)——**且先于 top_k 执行**:同一身份只保留最高
  confidence 的一条,重复候选不得占用 top_k 名额(否则 top_k=2 下
  A(0.9)/A(0.8)/B(0.7) 会截得 A、A,去重后 B 被无意义丢弃);top_k 排序键为
  confidence 降序 + 规范身份升序,并列时不依赖 LLM 返回顺序。**规范身份 =
  未哈希、未加盐的规范签名**(source schema/table + source/target 列对应对
  + target schema/table)——`rel_id_salt` 只用于最终 relationship_id,不得
  参与候选排序与业务选择(否则仅修改盐值就会改变并列候选的 top_k 入选结果)。
  同一键集的多重发现(不同约束/逻辑键重复产生)、LLM 返回重复候选,都不得
  进入评分。**规则池同向去重的 key_origin 优先级**:同一有向身份重复时,
  key_origin 按 **physical > logical** 保留,不得由候选遍历顺序决定;相同
  来源的重复项再直接去重——key_origin 决定 3.2.2 的纠偏策略(物理键约束
  修正 vs 逻辑键失效丢弃),保留错误可能让本应存在的关系被删除;
- **最小键过滤(评分前,单向,含行为变化)**:
  - 覆盖范围**继续包含 LLM 池**(现状混合池即三来源全覆盖,本次保持):
    LLM 复合候选的超集泛滥是真实问题(LLM 可能同时返回 `order_id→order_id`
    单列与 `(order_id, product_id)→(order_id, product_id)` 复合);
  - **单向抑制**:规则单列抑制 LLM 复合(LLM 池评分前用
    "LLM 池单列 ∪ 规则池单列"并集判定 superkey)——规则单列键侧是
    PK/UK/逻辑键约束事实,LLM 复合是猜测,丢弃无损;LLM 池内单列同样抑制
    LLM 池内复合(池内自过滤);
  - **LLM 单列不抑制规则复合(行为变化)**:现状混合池为双向抑制;但规则复合
    通常有约束依据(复合主键/复合逻辑键),被 LLM 单列猜测抑制是误伤——如复合
    主键 `(order_id, product_id)` 的规则候选被 LLM 的 `order_id→order_id`
    单列猜测丢掉,不合理;
  - 与决策抑制的关系:此处是评分前的 superkey 过滤(丢复合),决策阶段"同表对
    复合压单列"是评分后抑制(丢单列),互不冲突;
- **FK 排除(评分前)**:双向检查(fwd/rev),FK 身份集合全局,两池各自执行无冲突;
- **反向等价关系(评分后)**:必须等评分得到 cardinality 才能判断等价性,留到
  合并阶段按**无向身份分组**(适用于所有评分后候选,见 3.3)——不同 cardinality
  的同一关系在各自方向规范化后可能变成相反方向,先分组才能执行组内
  cardinality 决策;

### 3.2 方向规则(规则候选评分前规范化;各来源评分后分别纠偏)

#### 3.2.1 规则候选:生成时规范化(评分前)

规则生成阶段已知:原 source = 键表(主键/唯一约束/逻辑键所在表)、原 target =
关联字段所在表。**生成时即交换方向**,规范化为:

```text
关联字段表 → 键表
```

- 零成本(生成时已知的机械信息),评分方向 = 最终输出方向,
  `inclusion_rate` 语义天然正确(|关联值 ∩ 键值| / |关联值|);
- **物理 PK/UK 产生的规则候选预期为 N:1 或 1:1**(键侧由数据库约束保证唯一);
  **逻辑键候选仍以评分阶段计算结果为准**——逻辑键的唯一性来自样本画像而非
  数据库约束,评分阶段重新采样可能得到不同唯一性结果,采样不足、数据变化、
  查询失败也可能使 cardinality 不符合预期。意外基数的处理**按来源分别执行**
  (见 3.2.2):物理键候选按约束语义修正、逻辑键候选失效丢弃、LLM 候选判反
  翻转;
- 每个池内的同向重复候选只评一次;跨来源重叠及评分前无法确定等价性的反向
  候选允许分别评分,并在评分后合并(若以后优化查询次数,可增加同向身份评分
  缓存,本次不扩大实现范围);
- N:1 的评分方向即最终输出方向;1:1 的规则方向携带键侧信息(键侧=被引用方),
  合并阶段按 3.3 的方向决策层级定最终方向;若被翻转,取 reverse_inclusion_rate
  并按权重重算 `composite_score`,方向与数值严格一致。

#### 3.2.2 评分后纠偏(按来源分别处理)

规则候选与 LLM 候选的来源语义不同,判反纠偏**按来源分别处理**:

**LLM 候选**(按提示词契约方向评分;LLM 只是猜测方向,判反后翻转合理):

| 评分结果 cardinality | 处理 |
|---|---|
| `N:1` / `1:1` | 保持(1:1 的最终方向由 3.3 方向决策层级决定) |
| `1:N`(LLM 判反) | 翻转 from/to、改写 N:1,取 reverse_inclusion_rate 并重算 composite_score |
| `M:N` | 按对称推断关联保留(方向由 3.3 字典序决定),记录日志 |

**物理键规则候选**(方向 = 关联字段表→键表,键侧唯一性由 PK/UK 保证):
**不执行方向翻转**——scorer 得到 1:N/M:N 说明"键侧不唯一"的判断与物理约束
冲突,按约束语义修正:

| 评分结果 cardinality | 处理 |
|---|---|
| `N:1` / `1:1` | 保持(1:1 的最终方向由 3.3 方向决策层级决定) |
| `1:N` | 按 source 唯一修正为 **1:1**(target 唯一性由 PK/UK 保证,采样结果与约束冲突) |
| `M:N` | 按 source 不唯一修正为 **N:1** |

修正时记录采样结果与物理约束冲突的 warning。

**逻辑键规则候选**(key_origin=logical,键侧唯一性来自样本推断):

- `N:1` / `1:1`:正常保留(1:1 的最终方向由 3.3 方向决策层级决定);
- `1:N` / `M:N`:说明本次评分**未复现 target 的逻辑键唯一性**,候选依据失效
  ——**丢弃候选并告警**,不翻转为一条没有目标键证据的新关系(否则方向、
  key_origin 与 inference_method=rule_logical_key 不再一致)。

以下重算仅适用于**方向翻转**的场景(LLM 判反翻转、1:1/M:N 方向决策翻转);
物理键候选的基数修正不改变方向,无需重算。

重算细节:`inclusion_rate = |source ∩ target| / |source|` 是唯一方向相关维度
(`scorer.py:312`);scorer 在采样时同步计算两个标量:

```text
forward_inclusion_rate = |交集| / |source_values|   (正常方向的 inclusion_rate)
reverse_inclusion_rate = |交集| / |target_values|   (翻转方向的 inclusion_rate)
```

翻转时直接取 `reverse_inclusion_rate` 作为新 inclusion_rate——**不新增 DB
查询、不向 pipeline 暴露样本集合**(避免每个候选重复保留完整采样值,控制内存
与耦合;标量以内部返回信息携带,不进 `score_details` 与产物)。其余四维
(jaccard / type_compatibility / name_similarity / comment_similarity)对称,
无需重算。

**composite_score 同步重算**:`inclusion_rate` 是总分组成部分(权重 0.40),
翻转后必须同步——更新 `score_details.inclusion_rate` → 按五维(新
inclusion_rate + 其余四维不变)与现有权重重新加权求和 → **后续"冲突取高分者"
与决策阈值一律使用新总分**。否则明细与总分不一致,且旧总分可能导致合并时
选错候选。实现上复用 scorer 的加权函数(或提取为共享纯函数,权重单一来源,
`scorer.py:129`),合并阶段禁止硬编码权重。写文件时 `confidence_level` 按新
总分分档(`writer.py:290`),无需额外处理。

#### 3.2.3 FK 直通 cardinality(不经过纠偏,生成时即正确)

现状缺陷:`_infer_cardinality`(repository.py:268-319)对 FK 直通用**两端**唯一性
判断——源唯一 + 目标不唯一 → 1:N、都不唯一 → M:N;目标唯一性依赖目标表 JSON
画像(`_is_columns_unique`,画像缺失即 False)。目标表画像缺失/约束未加载/统计
不完整时,FK 直通会产出 1:N/M:N,与 FK 方向语义(引用方→被引用方)矛盾;而 FK
直通走 writer 独立分支,**不经过 3.2.2 的判反纠正**,最终违反"rel 中不存在
1:N"。

设计(物理 FK 基数固定):

- **target 端由数据库被引用约束保证唯一,不再依赖 JSON 画像验证**——
  PostgreSQL 允许建立外键,本身代表目标列满足被引用约束(PK、唯一约束或
  合格的唯一索引等);
- **source 端唯一性依次判断**:
  1. 单列或复合主键;
  2. 单列或复合唯一约束;
  3. 非部分、非表达式、键列完全匹配的唯一索引;
  4. 画像统计回退(**单列与复合口径不同**):
     - 单列:读取该列 `statistics.uniqueness`(阈值与现有逻辑一致,≥ 0.95);
     - 复合列:检查完全相同字段组合是否存在于
       `table_profile.unique_column_sets`,且满足逻辑键置信度要求(使用
       `relationships.candidate_matching.logical_key_min_confidence`,默认
       0.8,与规则候选生成同口径——**不得硬编码固定值**,否则用户调整该配置
       后 FK 基数口径与候选生成不一致);
     - **不得使用"各单列 uniqueness 的最小值"推断组合唯一**——(a,b) 组合
       唯一但 a、b 单独不唯一时会漏判 1:1;反之各列样本唯一也不能严格证明
       组合在全表唯一;
  5. 找不到组合级证据时保守视为不唯一;
- **复合唯一性证据采用无序字段集合比较**(长度相同且规范化字段集合相同);
  该规则**仅用于唯一性判断**——关系身份、FK 列映射及无向身份仍必须保留列
  的位置对应关系(UNIQUE(a,b) 同样证明 (b,a) 组合唯一;FK source_columns
  为 `[tenant_id, user_id]` 而 unique_column_sets 为 `[user_id, tenant_id]`
  时,仍判定唯一);
- source 唯一 → **1:1**;source 不唯一或无法判断 → **N:1**;

代码:`_infer_cardinality()` 是 FK 基数规则的唯一修改入口,但需同步完善其调用
的 `_is_columns_unique()`——当前该方法只认 PK/UK 与统计值,**不检查
`table_profile.indexes`**,源端非部分唯一索引(如
`CREATE UNIQUE INDEX ... ON user_profiles(user_id)` + FK)会被漏判为 N:1;
其复合列统计回退当前为"各单列 uniqueness 最小值"(repository.py:393-404),
按上表改为 unique_column_sets 组合级证据;若该回退被其他调用方使用,同步
替换,不得保留单列最小值推断。逻辑键置信度阈值经配置传入
MetadataRepository(或提取共享配置解析),不复用硬编码常量。

### 3.3 合并规则

- **无向身份分组(所有评分后候选,不依赖方向)**:评分后全部候选先按无向身份
  进组——**不再"仅用于 1:1 反向分组"**。不同 cardinality 的同一关系在各自
  方向规范化后可能变成相反方向,若不先按无向身份分组,会落进不同合并组,组内
  cardinality 决策(如物理规则 N:1 优先于 LLM M:N)将没有机会执行——实例:
  规则 `orders→categories N:1` 保持语义方向,而 LLM M:N 按字典序翻成
  `categories→orders`,有向 ID 不同,无法合并;
  - **无向身份算法**:
    1. 比较两个表端点(比较键同字典序定义:`(casefold, 原始值)`),确定字典序
       较小的表为规范左端;
    2. 若当前关系方向与规范方向相反,同时交换表端与两侧列;
    3. 在规范方向下对 `(left_column, right_column)` 配对**整体**排序;
    4. 用规范表端点与排序后的配对列表生成无向身份;
    5. **禁止分别排序左右字段列表**(会把不同的复合指派错误合并);
    示例:`A(a,b)→B(x,y)` 与 `B(y,x)→A(b,a)` 生成相同无向身份;
    `A(a,b)→B(y,x)` 是另一条关系;
- **组内 cardinality 决策(先于方向)**:
  1. **两个方向都有物理键规则证据 → 1:1**——两端都有物理键作为 target,说明
     两端都具备物理唯一性(即使各候选修正后各自为 N:1);
  2. 只有一个方向有物理键规则证据 → 使用该物理候选经 3.2.2 修正后的
     cardinality;
  3. 无物理证据、两个方向都有有效逻辑键证据 → **1:1**——两条逻辑键候选都
     未在 3.2.2 失效,说明本次采样两端都满足键唯一性;
  4. 只有一个方向有有效逻辑键证据 → 使用该逻辑候选的 cardinality;
  5. 纯 LLM → 使用**纠偏完成时**(最终方向尚未确定)按候选决胜键(见下)确定
     的获胜者的 cardinality——"最终规范方向"在 cardinality 决策阶段不存在,
     不能引用;该获胜候选仅用于定 cardinality(及 N:1 时的方向),最终分数在
     方向确定重算后另取最高者;
  6. cardinality 必须与最终方向一致,输出中不得出现 1:N;
  **评分内容可以来自高分候选,但 cardinality 优先服从键证据,不能随高分候选
  整对象复制;双向规则证据下的 cardinality 不依赖候选遍历顺序**;
- **候选决胜键(统一,适用于一切"取最高分候选"的位置)**:1) composite_score
  降序;2) 证据优先级:物理规则 > 逻辑规则 > LLM;3) **纠偏完成时的未加盐
  有向规范签名**升序——必须使用候选规范到最终方向**之前**的签名,否则反向
  候选在最终规范后签名相同,无法决胜;4) 仍相同 → 按 score_details 固定
  维度顺序(inclusion_rate / name_similarity / comment_similarity /
  type_compatibility / jaccard_index)组成元组后升序兜底。适用位置:组内
  cardinality 决策(纯 LLM 获胜者)、字段级合并(评分内容获胜者);
- **按最终 cardinality 决定唯一方向**:
  - `N:1`:有规则键证据时使用最高优先级规则候选方向(引用方→键端);纯 LLM
    时使用决定最终 N:1 cardinality 的获胜候选方向;
  - `1:1`:**1:1 方向决策层级**——1) 只有一个方向有规则证据 → **规则方向
    优先**(规则键侧 = PK/UK/逻辑键约束事实,LLM 契约方向仅为语义猜测);2)
    两个方向都有规则证据(双向键侧证据,如 categories ↔ mv_category_sales)→
    **物理键方向优先于逻辑键方向**;3) 两边键类型相同 → 按端点字典序;4) 纯
    LLM 候选 → 直接按端点字典序。方向不再受 composite_score 波动影响,也
    避免"先用方向相关分数选方向、再因方向变化重算分数"的循环;
    **附注**:方向决胜确定最终端点和键来源;评分内容取规范化后最高分,**不能
    从反向高分候选整体复制**——`key_origin` 仅作为方向决胜与内部一致性校验
    信息,不进入 Relation、不写产物;
  - `M:N`:对称推断关联,**不称隐式外键**;方向仅为确定性输出约定,按字典序;
  - **字典序定义**:端点 = `(schema, table, sorted(columns))` 三元组,比较键
    为 `(casefold 后的值, 原始值)` 元组逐级比较——先忽略大小写,相同时以
    原始字符串兜底(PostgreSQL 允许带引号的大小写敏感对象,如 `"Users"` 与
    `users`,纯 casefold 会相等而无法确定先后);schema、table、columns 均
    采用此规则,**较小的一端固定为 from**;
- **规范到最终方向 + 重算**:组内所有候选翻转到最终方向;翻转的取
  `reverse_inclusion_rate` 并按权重重算 `composite_score`(机制同 3.2.2,
  不新增 DB 查询);其余四维对称,无需重算。物理键候选的基数修正(3.2.2)不
  改变方向,无需重算。**重算后的最高分只决定最终 score_details /
  composite_score,不再反向修改已经确定的 cardinality**——cardinality 决策
  使用纠偏完成时的分数(两阶段规则),避免"分数→基数→方向→分数"的循环迭代;
- **字段级合并(冲突取高分者)**:组内多条候选(规则 + LLM 或同源多份),按
  **候选决胜键**(见上)确定获胜者,保留其 `composite_score`(连同
  `score_details`)——主键为**规范到最终方向后重算的新总分**,同分时按证据
  优先级、纠偏完成时签名、score_details 元组依次决胜。合并**不是整对象
  覆盖**,按字段拆分:
  - `source/target/source_columns/target_columns`:来自最终方向;
  - `cardinality`:来自组内 cardinality 决策(见上,先于方向);
  - `key_origin`:来自支持最终方向的规则候选(物理键优先)——仅合并阶段内部
    信息,不进入 Relation、不写产物;`rule+llm` 合并时 inference_method 恒为
    `llm_inferred`(与 doc 15 及决策代码一致),重叠来源由
    `candidate_origin=rule+llm` 承载;
  - `candidate_origin`:合并所有来源(`rule+llm` 或保持单一来源);
  - `score_details/composite_score`:候选全部规范到最终方向并重算 inclusion
    与总分后,取最高者;
  - 其他方向相关字段与最终方向重新对齐,不能从反向高分候选整体复制;
- **生成最终有向 relationship_id**:组内 cardinality 与方向确定、字段级合并
  完成后,以最终端点生成有向 `compute_relationship_id`(含 `rel_id_salt`);
- **relationship_id 变化**:ID 是方向的纯函数(签名含 `source->target`,
  repository.py);方向规范化后 ID 随之变化——**结构不变、字段值变,旧 rel 产物
  与新产物 ID 不兼容**。这是方向唯一化的必然结果,也是统一身份合并的前提,不是
  缺陷。下游影响:CQL 不读 `relationship_id`(doc 17 §13.2),不受影响;其他外部
  消费者(血缘、图谱加载、统计)需知晓 ID 语义从"方向相关身份"变为"方向规范化
  后的唯一身份";
- **确定性保证**:**对于最终判定为 1:1 或 M:N 的关系**,方向与 relationship_id
  由约束优先级与字典序确定,**不受候选遍历顺序、异步完成顺序及
  composite_score 波动影响**;**对于纯 LLM 的 N:1 关系,方向跟随基数决策阶段
  的获胜候选,因此可能随评分变化**;在候选及评分相同时,稳定决胜键保证结果
  不受候选输入顺序影响。cardinality、评分和阈值过滤仍依赖数据库采样;整体
  产物的完全复现要求采样结果相同——替代原"先入池者"方案(该方案依赖文件
  遍历与异步完成顺序,不是稳定契约)。

### 3.4 决策位置

决策(阈值过滤 + 抑制规则)在**合并后**执行,输入是合并后的完整关系集——抑制
规则(同表对复合压单列)需要完整关系集才有意义。位置与现状一致,只是输入从
"合并后的候选池"变为"合并后的已评分关系"。

方向规范化带来的决策适配(仅 `_has_independent_constraint` 检查端点,抑制
分组保持):

- **例外检查端点改为 target(键端)**:doc 15 例外口径"单列为物理主键/唯一
  约束/唯一索引时保留"中的"单列"= 键列——旧方向键列在 source 位,规范化后
  键端在 target,不改会错误检查引用侧(如 `orders.category_id →
  categories.category_id` 会被误判"无独立约束"而遭同表对复合压制)。实现改为
  检查 target 端表级约束,按基数分层:
  - **N:1**:检查 target(键端恒在 target);
  - **规则主导的 1:1**:检查 target(规则方向键端在 target);
  - **M:N**:无键端概念,**不应用该例外**;
  - **纯 LLM 1:1**:检查最终方向的 target——但这是物理约束验证,并不证明其
    业务方向正确;
  - `key_origin` 可作一致性防御校验(规则物理键候选的 target 端必有 PK/UK),
    不作主判定;
- **抑制分组保持有向表对**:规范化后大多数同一业务关系会保持相同方向;混合
  来源的 1:1 单列与复合候选仍可能方向不同,可能造成少量漏抑制——本阶段接受
  该残余风险,以避免无向分组误伤语义不同的反向关系。这是明确的精度取舍。

## 4. 代码修改范围

| 文件 | 修改内容 |
|---|---|
| `metaweave/core/relationships/candidate_generator.py` | 拆分出口:规则候选生成、LLM 候选入池各自独立返回;**规则候选生成时交换方向**(3.2.1);**LLM 入池顺序:合法化 → 同向身份去重(同身份保留最高 confidence)→ 排序(confidence 降序、规范身份升序)→ top_k 截断**(见 3.1.1,先于去重的旧顺序会浪费名额);**各池评分前同向去重**(统一身份);**最小键过滤:规则池自过滤 + LLM 池用"LLM 池单列 ∪ 规则池单列"并集判定(单向,见 3.1.1)**;FK 排除(双向)保留在两池评分前;**移除混合池统一 `_merge_and_dedup`**(跨来源合并挪到合并阶段) |
| `metaweave/core/relationships/pipeline.py` | 分开调用评分(规则结果、LLM 结果);新增**合并阶段**(严格按 3.3 顺序):评分后纠偏(按来源,3.2.2)→ 无向身份分组 → 组内 cardinality 决策 → 按最终 cardinality 定方向 → 规范到最终方向 + 重算(翻转取 reverse_inclusion_rate 并重算 composite_score)→ 字段级合并 → 生成最终有向 relationship_id → FK 兜底复查;决策输入改为合并后关系集 |
| `metaweave/core/relationships/repository.py` | 新增**无向身份函数**(精确列配对规范化算法见 3.3;用作**所有评分后候选的合并分组键**,不再仅用于 1:1 反向对);`_infer_cardinality`:物理 FK 固定按 1:1/N:1(见 3.2.3);`_is_columns_unique`:补查非部分/非表达式/键列完全匹配的唯一索引,复合列统计回退由"各单列 uniqueness 最小值"改为 unique_column_sets 组合级证据(逻辑键置信度阈值经配置传入,见 3.2.3) |
| `metaweave/core/cql_generator/reader.py` | **删除 1:N 翻转逻辑**(rel 归一后不再出现 1:N),纯消费;doc 18(阈值过滤与同表对去重)**尚未实施**,与本次改造相互独立、无实施顺序依赖,本设计不将其视为已存在的兜底能力 |
| `metaweave/core/relationships/scorer.py` | 评分维度与计算公式不变,扩展评分结果的**内部返回信息**:采样时同步计算 `forward/reverse_inclusion_rate` 两个标量(内部字段,不进 `score_details` 与产物),并提供**按权重重算总分的接口**(或提取共享纯函数)——供合并阶段翻转后取 reverse_inclusion_rate 并重算 composite_score(见 3.2.2,不新增 DB 查询、不暴露样本集合;权重单一来源,合并阶段禁止硬编码) |
| `metaweave/core/relationships/decision_engine.py` | 修改 `_has_independent_constraint`:检查端点从 source 改为 target(键端;N:1 / 规则主导 1:1 检查 target,M:N 不应用例外,纯 LLM 1:1 检查最终方向 target,见 3.4);抑制分组保持有向表对(精度取舍,见 3.4) |
| `metaweave/core/relationships/writer.py` | 不改(逻辑按 rel 定向查表,自动适配);方向规范化后 `target_source_type` 更符合语义(键侧在 target)、`source_constraint` 值变化(键侧约束 → 引用侧约束,仅规则单列关系)——顺带修正现状的语义错位,行为以回归测试锁定(见 §5) |

## 5. 测试计划

- **规则方向规范化**:规则候选生成后方向恒为"关联字段表 → 键表";物理 PK/UK
  候选预期 N:1 / 1:1;逻辑键候选以评分阶段计算结果为准;
- **评分后纠偏(按来源)**:物理键规则候选算出 1:N → 不翻转、按 source 唯一
  修正为 1:1;算出 M:N → 修正为 N:1;均记录采样与约束冲突 warning、不重算
  分数(方向未变);逻辑键规则候选算出 1:N/M:N → **丢弃候选并告警**(不翻转,
  断言产物无"无目标键证据"的关系);LLM 1:N → 翻转改写 N:1、取
  reverse_inclusion_rate 重算 composite_score;LLM M:N → 对称保留 + 日志;
- **FK 直通 cardinality**:target 画像缺失或统计不完整,不影响结果;source 有
  单列/复合 PK → 1:1;source 有单列/复合 UK → 1:1;source 有非部分唯一索引 →
  1:1;source 单列 statistics.uniqueness ≥ 0.95 → 1:1;source 复合列在
  unique_column_sets 中且置信度达标 → 1:1(各单列不唯一、组合唯一时不得按
  "单列最小值"误判);**FK 源列顺序与复合 PK/UK、唯一索引键列、
  unique_column_sets 顺序相反 → 仍判定 1:1**(无序集合比较);字段集合不同
  (即使部分重叠)→ 不得判定唯一;source 只有普通索引、部分唯一索引、无组合
  级证据或无法获取画像 → N:1;**所有 FK 直通关系均不得输出 1:N/M:N**;
- **LLM 判反纠正**:LLM 候选被数据判为 1:N → 翻转 from/to、改写 N:1,
  inclusion_rate 取 reverse_inclusion_rate,**composite_score 按权重同步重算**
  (score_details 与总分一致);其余四维不变;**不新增 DB 查询、样本集合不外传**
  (mock 断言);
- **同源同向去重(评分前)**:规则池内重复候选(同一键集多重发现)与 LLM 池内
  重复候选均在评分前去重(mock 断言评分器收到的候选无重复);同一字段组合
  同时存在于 physical_constraints 与 unique_column_sets 时,只产生一个规则
  候选且 key_origin=physical(与收集/遍历顺序无关);
- **LLM 去重先于 top_k**:top_k=2 下 A(0.9)/A(0.8)/B(0.7)→ 截断结果为
  A、B(重复 A 不占名额);confidence 并列时按规范身份(未加盐签名)升序截断,
  与 LLM 返回顺序无关;**仅修改 rel_id_salt 不改变并列候选的 top_k 入选
  结果**;
- **最小键过滤(单向)**:规则单列抑制 LLM 复合(评分前丢弃);LLM 单列不抑制
  规则复合(规则复合保留);LLM 池内单列抑制 LLM 池内复合;
- **统一身份合并**:规则 N:1 与 LLM N:1(同列对应对)→ 合并为一条、来源
  `rule+llm`、取 composite_score 高者;
- **冲突取高分者**:两来源分数不同 → 按方向决策后重算的新总分保留高分者及
  其 score_details(字段级分离:端点/键来源随方向决胜,评分内容取规范化后最
  高分,key_origin 不与方向脱节);mock 断言旧总分不参与比较、反向高分候选
  不被整体复制;
- **合并 cardinality 决策**:物理规则 N:1(0.82)与 LLM M:N(0.88)重叠 →
  最终 N:1(分数取 0.88,基数服从键证据);**按各自方向规范化后恰好相反的
  案例**——规则 orders→categories N:1 与 LLM M:N 经字典序翻成
  categories→orders → 无向身份分组后仍合并,最终 N:1、方向
  orders→categories;**双向物理规则(两次采样各自 N:1)→ 组内最终 1:1**;
  双向有效逻辑规则 → 1:1;物理规则与反向逻辑规则冲突 → 物理规则优先;有效
  逻辑规则 N:1 与 LLM 1:1 重叠 → 最终 N:1;纯 LLM 冲突 → **纠偏完成时**
  高分候选的 cardinality(最终方向确定前,不引用"最终规范方向");重算后分数
  变化不反向修改 cardinality;端点、cardinality、key_origin、score_details
  分别按各自契约取值,输出无 1:N;
- **候选决胜键(同分确定性)**:纯 LLM 反向候选同分(0.82)、cardinality 不同
  (N:1 vs M:N)→ 打乱输入顺序后获胜候选、最终 cardinality、方向与 ID 不变;
  规则与 LLM 总分相同 → 按证据优先级(物理规则 > 逻辑规则 > LLM)选择评分
  内容;最终总分相同但 score_details 不同 → 打乱候选顺序后输出仍一致;
- **1:1 方向决策层级**:只有一个方向有规则证据 → 规则方向优先(规则 A→B 与
  LLM B→A → 方向 A→B);纯 LLM 反向对 → **直接按端点字典序**(方向与分数
  无关);
- **无向身份算法**:`A(a,b)→B(x,y)` 与 `B(y,x)→A(b,a)` 生成相同无向身份;
  `A(a,b)→B(y,x)` 生成另一条身份;断言配对整体排序语义——分别排序左右字段
  列表的错误实现会被用例拦截;
- **1:1 双向规则决胜**:双向规则候选(物理 vs 逻辑)→ 物理键方向;两边键类型
  相同 → 按端点字典序(**与 composite_score 无关,高分方向不参与决胜**);
  **保留规范到最终方向后的最高 score_details 与 composite_score;端点、
  key_origin 与最终方向的规则证据一致,inference_method 按既有来源契约生成
  (rule+llm 固定为 llm_inferred),不从反向高分候选整体复制**;
- **M:N 字典序**:对称推断关联,方向恒为字典序小者;翻转时取
  reverse_inclusion_rate 并重算 composite_score(mock 断言不新增 DB 查询、
  明细与总分一致、样本集合不外传);
- **确定性(三层)**:1) 固定 cardinality、改变评分与候选顺序 → 1:1/M:N 的
  方向与 ID 不变(方向只由语义/约束/字典序决定,与 composite_score 波动
  无关);2) 固定采样结果 → 完整评分、cardinality、方向与 ID 可复现;3) 采样
  结果改变导致 cardinality 改变时,允许方向与 ID 随之变化;
- **评分前过滤不浪费**:评分器不收到与 FK 重复的候选(FK 排除在评分前);
  最小键过滤在各池评分前生效;
- **CQL**:删除翻转后,rel 中无 1:N,N:1 关系保持引用方→键端;1:1 与 M:N
  保持 rel 已确定的规范方向;CQL 不再自行改变任何关系方向、忠实消费 rel
  方向(同表对多字段关系的塌缩属 doc 18 范围,本次不涉及);
- **writer 字段语义回归**:规则物理键关系规范方向后,`target_source_type`
  正确显示 `primary_key` / `unique_constraint`(键侧在 target);
  `source_constraint` 描述规范化后的引用侧(而非原搜索起点键表);逻辑键关系
  同理(`candidate_logical_key`);复合关系、LLM、FK 直通三类的这两个字段不变;
- **来源标记保持**:单条关系的 `inference_method`(rule_physical_key /
  rule_logical_key / llm_inferred)在方向规范化 + 合并后保持正确;**rule+llm
  合并 → inference_method 恒为 llm_inferred**;内部 `candidate_origin` 正确
  传递,顶层统计 rule_only / llm_only / rule_llm_overlap 数量正确;**单条
  关系不新增 candidate_origin 字段**(writer 输出结构不变);
- **决策例外端点(target)**:source 无约束、target 是单列 PK → 同表对存在
  同向复合时**保留**;source 无约束、target 也无单列物理唯一约束 →
  **压制**;LLM 判反纠正后的候选,例外检查作用于纠正后的 target 端;M:N 不
  应用例外;
- **抑制分组有向守卫**:构造方向相反、列组合不同的两组推断候选,验证它们
  不会因为属于同一个无向表对而互相抑制;
- **回归**:orders 库前后对比——无反向重复、方向统一、inclusion_rate 与
  最终方向一致、正配不丢、统计四档正确。

## 6. 验收标准

1. rel 产物方向分层:有向基数(N:1)统一为引用方→被引用方,**不存在 1:N**
   (LLM 经判反纠正、物理键规则候选经约束语义修正、逻辑键失效候选丢弃、FK
   直通经 3.2.3 基数固定——各来源均无 1:N);
   1:1 按方向决策层级(规则优先、双向规则按物理键 > 逻辑键 > 字典序决胜、
   纯 LLM 字典序,见 3.3);M:N 字典序(对称推断关联);且
   `inclusion_rate` 与最终方向一致、翻转后 `composite_score` 按权重同步重算
   (规则评分前规范化、LLM 判反/方向翻转重算),score_details 与总分一致;
2. 同一业务关系只出现一条(无向身份分组 + 组内 cardinality/方向决策 +
   字段级合并生效);内部来源归类正确(rule / llm / rule+llm),并正确反映在
   顶层来源统计中;单条关系不新增 candidate_origin 字段;
3. 合并冲突采用**字段级决策**:`score_details` 与 `composite_score` 取规范
   到最终方向后的最高分候选(同分按候选决胜键);cardinality、方向、
   key_origin 与 candidate_origin 分别遵循 §3.3 的独立契约,**不得直接复制
   最高分候选整个对象**;
4. 1:1 / M:N 方向与 relationship_id 稳定可复现:在候选来源、端点和
   cardinality 相同的前提下,方向与 ID 不受遍历/异步/入池顺序及
   composite_score 波动影响;最终 relationship_id 在组内 cardinality 与方向
   确定后生成;ID 随方向规范化更新,新旧产物 ID 不兼容为预期变化;整体产物的
   完全复现要求采样结果相同;
5. CQL 无翻转逻辑,纯消费;
6. FK 排除与最小键过滤在评分前执行;最小键过滤覆盖规则与 LLM 两池且单向
   (规则抑制 LLM,LLM 不抑制规则);
7. `--step json` 零改动;
8. 评分维度与权重(doc 16)、决策阈值数值与抑制规则口径保持不变(例外检查
   端点随方向规范化调整,见 3.4);
9. writer 输出的 `target_source_type` / `source_constraint` /
   `inference_method` 与规范方向一致;内部 `candidate_origin` 正确传递,并使
   来源分类统计(rule_only / llm_only / rule_llm_overlap)正确;
10. 抑制规则例外按键端(target)判定(N:1 / 规则主导 1:1 检查 target,M:N 不
    应用例外),分组保持有向表对,方向相反的不同业务关系不互相抑制。

## 7. 非目标

- 不改 `--step json`(JSON 产物 FK 方向已符合惯例、逻辑键无方向);
- 不改**推断候选在 scorer 中的** cardinality 计算公式(继续使用采样唯一性与
  JOIN 倍率);物理 FK 直通的 `_infer_cardinality()` 按 3.2.3 修正为仅输出
  1:1/N:1(数据库约束语义);
- 不改决策阈值数值(校准另议);
- doc 18(CQL 阈值过滤与同表对去重)范围不变、**尚未实施**;与本次方向统一
  相互独立,无实施顺序依赖,本设计不将其视为已存在的兜底能力;
- 不改 writer 输出结构(`source_constraint` 字段值随方向变化——语义归位,见
  §4/§5;`relationship_id` 字段值随方向变化,结构不变);
- 不改 writer `_get_target_source_type` 中 candidate_logical_key 判定硬编码
  0.8 的**已有问题**(与 `logical_key_min_confidence` 配置未对齐),记为后续
  一致性修正项,本次不扩大范围。
