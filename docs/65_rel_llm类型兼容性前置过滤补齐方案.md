# `rel_llm` 类型兼容性前置过滤补齐方案

## 1. 背景

最近几次 `pipeline generate` 执行日志表明，`rel_llm` 主流程虽然能够跑通，且最终结果未被污染，但在评分阶段仍然会对一些**明显类型不兼容**的候选关系执行 `JOIN COUNT`，从而产生数据库错误日志。

典型日志现象包括：

- `public.bss_branch.service_area_id -> public.highway_metadata.id`
- `public.highway_metadata.id -> public.bss_company.id`

对应错误为：

- `character varying = integer`
- `integer = character varying`

这类错误不会进入最终关系文件，但会带来：

1. 运行期错误日志噪音
2. 无意义的数据库查询开销
3. `rel` 与 `rel_llm` 在“类型兼容性过滤”行为上的不一致

本方案用于补齐 `rel_llm` 在评分前的类型兼容性前置过滤，使其与 `rel` 的行为更一致。

---

## 2. 问题定义

### 2.1 当前 `rel` 与 `rel_llm` 的差异

当前两条关系发现链路在“类型兼容性”的使用位置不同：

#### `rel`

`rel` 走的是标准规则链路：

1. `CandidateGenerator.generate_candidates()`
2. `RelationshipScorer.score_candidates()`

其中，`CandidateGenerator` 在**候选生成阶段**就会计算类型兼容性分数，并用配置阈值过滤掉不兼容候选。

这意味着很多 `varchar -> integer` 之类的候选，根本进不到评分阶段。

#### `rel_llm`

`rel_llm` 当前流程是：

1. LLM 返回候选
2. `_filter_invalid_candidates()`
3. `_filter_existing_fks()`
4. `_filter_by_semantic_roles()`
5. `_score_candidates()`

问题在于：

- 它**没有复用 `CandidateGenerator` 的类型兼容性前置过滤**
- 候选会直接进入 scorer
- scorer 会先采样、先跑 `JOIN COUNT`
- 后面才把 `type_compatibility` 作为评分项计算

因此，不兼容类型会先触发数据库错误，再被低分淘汰。

### 2.2 为什么这不是“复杂类型过滤”的同一个问题

此前已经修复过一类问题：

- 源列是 `semantic_role == "complex"`（如 `array/jsonb`）
- 但 `rel_llm` 过滤阶段没有拦住

该问题属于**复杂类型漏过滤**，已经通过在 `_filter_by_semantic_roles()` 中补充源列 `complex` 过滤解决。

本文讨论的是另一类问题：

- 列不是 `complex`
- 但两侧标量类型之间根本不应进行原生等值 JOIN
- 例如 `character varying` 与 `integer`

这类问题的根因不是语义角色，而是**缺少评分前的类型兼容性拦截**。

---

## 3. 现状中的可复用规则

项目中已经存在一套较完整的类型兼容性规则，定义在：

- `metaweave/core/relationships/candidate_generator.py`

关键函数：

- `_normalize_type(data_type)`
- `_get_type_compatibility_score(type1, type2)`
- `_is_type_compatible(type1, type2)`

### 3.1 当前这套规则覆盖的类型族

`CandidateGenerator._get_type_compatibility_score()` 已定义了以下兼容性：

1. 完全相同类型
2. 整数类型族内部
3. 字符串类型族内部
4. 数值类型族内部
5. 整数族与数值族交叉
6. 日期/时间类型族内部
7. `boolean` 与 `integer`
8. `uuid` 与 `uuid`

同时它还明确给出了一些不兼容情况：

1. 数值类型 vs 字符串类型
2. 时间类型 vs 字符串类型
3. `uuid` vs 非 `uuid`
4. `time` vs `date/timestamp`

### 3.2 当前 `rel` 的过滤阈值

配置文件中已经定义了候选生成阶段的最低类型兼容性阈值：

- `single_column.min_type_compatibility: 0.8`
- `composite.min_type_compatibility: 0.8`

因此：

- `varchar <-> integer` 分数为 `0.0`，会在 `rel` 中被前置过滤
- `integer <-> numeric` 可以通过
- `integer <-> float` 一般会因分数不足而被过滤

### 3.3 为什么不建议重复造一套规则

当前项目已经存在可用规则，继续在 `rel_llm` 里重新定义一套“兼容类型白名单”会带来：

1. 规则分叉
2. 后续维护困难
3. `rel` / `rel_llm` 行为不一致

因此本次改造的原则是：

**复用 `CandidateGenerator` 的类型兼容性规则，不新增第二套业务规则。**

---

## 4. 改造目标

本次改造的目标非常明确：

1. 在 `rel_llm` 的评分前，增加一层**类型兼容性前置过滤**
2. 复用 `rel` 已有的类型兼容性规则
3. 不改变 `rel` 当前行为
4. 不改 scorer 的评分顺序与评分公式，控制回归范围

换句话说：

**本次改造不是重写 scorer，而是把 `rel` 里已有的类型阈值过滤补到 `rel_llm` 上。**

---

## 5. 设计方案

## 5.1 总体思路

在 `LLMRelationshipDiscovery` 中新增一个“按类型兼容性过滤候选”的步骤，放在：

- `_filter_by_semantic_roles()` 之后
- `_score_candidates()` 之前

推荐顺序：

1. 非法候选过滤
2. 已有 FK 过滤
3. 语义角色过滤
4. **新增：类型兼容性过滤**
5. 评分

这样可以保证：

- 复杂类型先被语义角色过滤掉
- 普通标量列再按类型兼容性做硬过滤
- 不兼容候选不会再进入评分期数据库 JOIN

---

## 5.2 复用方式

### 推荐做法：抽共享函数

不建议在 `LLMRelationshipDiscovery` 中直接实例化 `CandidateGenerator` 并调用其私有方法。  
更稳妥的方案是：

将 `CandidateGenerator` 中的类型兼容性核心逻辑提取到共享模块，例如：

- `metaweave/core/relationships/type_compatibility.py`

建议抽出的函数：

```python
def normalize_pg_type(data_type: str) -> str:
    ...


def get_type_compatibility_score(type1: str, type2: str) -> float:
    ...
```

可选辅助函数：

```python
def meets_type_compatibility_threshold(
    type1: str,
    type2: str,
    threshold: float,
) -> bool:
    return get_type_compatibility_score(type1, type2) >= threshold
```

### 为什么要抽共享函数，而不是直接复制代码

原因：

1. `rel` 与 `rel_llm` 需要共享同一套规则
2. 避免未来修改一个地方、忘记另一个地方
3. `CandidateGenerator` 是候选生成器，不应该成为 `rel_llm` 的隐式依赖

---

## 5.3 `rel_llm` 中新增的过滤函数

建议在 `LLMRelationshipDiscovery` 中新增：

```python
def _filter_by_type_compatibility(
    self,
    candidates: List[Dict],
    tables: Dict[str, Dict],
) -> List[Dict]:
    ...
```

### 输入

- `candidates`: 已经过非法过滤、FK 过滤、语义角色过滤后的候选
- `tables`: 表元数据字典

### 输出

- 仅保留满足类型兼容性阈值的候选

### 单列候选规则

对 `single_column`：

1. 读取源列 `data_type`
2. 读取目标列 `data_type`
3. 调用共享函数计算 `type_score`
4. 若 `type_score < single_column.min_type_compatibility`，直接过滤掉

### 复合候选规则

对 `composite`：

1. 按列位置逐对取源列和目标列类型
2. 对每一对列调用共享函数
3. 任意一对列 `type_score < composite.min_type_compatibility`
4. 则整个复合候选过滤掉

### 元数据与大小写处理要求

新增过滤函数在读取表名、列名和 `data_type` 时，必须复用与 `_filter_by_semantic_roles()` 同级的**大小写不敏感映射逻辑**，避免 LLM 因大小写漂移导致“取不到元数据而误放行”。

实现要求：

1. 表名使用 `table_key_map` 进行大小写不敏感归一化
2. 列名使用 `col_profile_map` 进行大小写不敏感归一化
3. 不允许直接使用 LLM 原始返回的表名/列名字符串做字典索引

原因：

1. LLM 返回的表名、列名可能存在大小写漂移
2. 如果直接索引失败，会误走“元数据缺失”分支
3. 从而让本应被过滤的不兼容候选继续进入评分阶段

### 单列 / 复合候选的统一处理方式

为了避免在主逻辑中重复分支判断，建议在 `_filter_by_type_compatibility()` 中先将候选统一归一化为“列对数组”再处理：

- `single_column`：将 `from_column` / `to_column` 包装为长度为 1 的数组
- `composite`：直接使用 `from_columns` / `to_columns`

随后统一执行：

1. 逐对提取源列和目标列
2. 逐对获取 `data_type`
3. 逐对计算 `type_score`
4. 单列按单列阈值判断
5. 复合候选按“任一列对不达标则整体过滤”判断

### 元数据缺失时的处理

如果某列画像缺失或 `data_type` 缺失：

- 建议**保守放行**
- 并打 `debug/warning` 日志

原因：

- 当前问题的核心是“已有类型信息却没过滤”
- 不是“元数据缺失时一律拒绝”
- 直接拒绝可能误杀一些本来可评分的候选

---

## 5.4 阈值来源

不新增新配置，直接复用现有配置。

在 `LLMRelationshipDiscovery` 中，实际读取路径应直接使用已经完成合并的 `self.rel_config`：

- `self.rel_config["single_column"]["min_type_compatibility"]`
- `self.rel_config["composite"]["min_type_compatibility"]`

即：

- `rel` 用什么阈值
- `rel_llm` 就用什么阈值

这样可以自然继承：

1. 全局 `relationships` 配置
2. 模块级覆盖配置
3. 未来新增的关系参数扩展

这样可以确保两条链路在“是否允许该候选进入评分”上保持一致。

---

## 5.5 `scorer.py` 的处理边界

本次不建议直接修改 `RelationshipScorer._calculate_scores()` 的执行顺序，原因是：

1. 评分器是 `rel` 与 `rel_llm` 共用的底层组件
2. 改 scorer 会扩大回归范围
3. 当前问题只出现在 `rel_llm` 缺少前置类型过滤

但这并不意味着 `scorer.py` 可以继续保留自己的独立类型兼容规则。

当前 `RelationshipScorer` 内部仍有一套简化版类型规则；如果本次只让 `rel_llm` 前置过滤复用共享规则，而 `scorer.py` 继续使用旧规则，就会出现：

1. 过滤阶段与评分阶段使用不同的兼容性定义
2. 候选能否进入评分与 `type_compatibility` 得分来源不一致
3. 后续调参与问题排查困难

因此，本次改造范围应修正为：

- **在 `rel_llm` 评分前补过滤**
- **不调整 scorer 的评分顺序**
- **让 `scorer.py` 的类型兼容性计算也复用共享模块**

也就是说：

- 不改 `scorer` 的执行顺序
- 不改 `scorer` 的权重和评分公式
- 只替换 `scorer` 内部类型兼容性函数的实现来源

这样既能维持低回归风险，也能保证全系统对类型兼容性的认知只有一套规则来源。

后续如果要继续做系统级优化，可以单独再讨论：

- scorer 是否也要在 `_execute_join_count()` 前做最终短路

但那不是本次必需项。

---

## 6. 需要修改的代码

## 6.1 新增共享模块

建议新增文件：

- `metaweave/core/relationships/type_compatibility.py`

内容：

1. `normalize_pg_type()`
2. `get_type_compatibility_score()`
3. 可选：`meets_type_compatibility_threshold()`

规则来源：

- 原样提取 `CandidateGenerator._normalize_type()`
- 原样提取 `CandidateGenerator._get_type_compatibility_score()`

目标：

- 保证 `rel` 与 `rel_llm` 使用同一套规则

## 6.2 修改 `CandidateGenerator`

文件：

- `metaweave/core/relationships/candidate_generator.py`

改动：

1. 将 `_normalize_type()` 改为调用共享函数
2. 将 `_get_type_compatibility_score()` 改为调用共享函数
3. `_is_type_compatible()` 可保留，内部改为基于共享函数或维持现有包装逻辑

目标：

- `rel` 行为保持不变
- 规则来源改为共享函数

## 6.3 修改 `LLMRelationshipDiscovery`

文件：

- `metaweave/core/relationships/llm_relationship_discovery.py`

改动：

1. 新增 `_filter_by_type_compatibility()`
2. 在 `_finalize_relations()` 主流程中，放在 `_filter_by_semantic_roles()` 后调用
3. 使用大小写不敏感的表/列映射获取 `data_type`
4. 先将 `single_column` / `composite` 统一归一化为列对数组，再复用统一循环处理
5. 阈值直接从 `self.rel_config` 中读取

即：

```python
filtered_candidates = self._filter_by_semantic_roles(filtered_candidates, tables)
filtered_candidates = self._filter_by_type_compatibility(filtered_candidates, tables)
scored_relations = self._score_candidates(filtered_candidates, tables)
```

日志建议：

- `debug`: 打印被过滤候选、源类型、目标类型、compat score、threshold
- `info`: 打印过滤前后数量

## 6.4 修改 `RelationshipScorer`

文件：

- `metaweave/core/relationships/scorer.py`

本次结论：

- 不改执行顺序
- 不改 `_execute_join_count()` 逻辑
- 不改评分公式
- 但要改内部类型兼容性函数的实现来源

建议改动：

1. 删除或废弃内部重复的 `_normalize_type()` 实现
2. 删除或废弃内部重复的 `_get_type_compatibility()` 实现
3. 改为直接调用共享模块中的 `normalize_pg_type()` / `get_type_compatibility_score()`
4. 维持当前 `type_compatibility` 分值在总分中的权重不变

目标：

1. 保证过滤阶段和评分阶段使用同一套兼容性定义
2. 避免规则分叉
3. 不改变现有 scorer 框架行为

---

## 7. 日志与可观测性要求

为便于确认修复是否生效，建议新增以下日志：

### 7.1 过滤明细日志（debug）

示例：

```text
[filter_type_compat] 跳过候选: public.bss_branch.service_area_id -> public.highway_metadata.id
src_type=character varying, tgt_type=integer, score=0.00, threshold=0.80
```

### 7.2 统计日志（info）

示例：

```text
[filter_type_compat] 过滤前: 28, 过滤后: 24, 跳过: 4
```

### 7.3 修复后预期日志变化

修复后，以下日志应明显减少或消失：

- `操作符不存在: character varying = integer`
- `操作符不存在: integer = character varying`

前提是这些错误来源于 `rel_llm` 不兼容候选评分。

---

## 8. 测试方案

## 8.1 单元测试：共享类型规则

新增测试文件建议：

- `tests/unit/metaweave/relationships/test_type_compatibility.py`

至少覆盖：

1. `varchar <-> text`：兼容
2. `integer <-> bigint`：兼容
3. `integer <-> numeric`：兼容
4. `integer <-> float`：低分
5. `varchar <-> integer`：不兼容
6. `date <-> timestamp`：部分兼容
7. `uuid <-> uuid`：兼容
8. `uuid <-> varchar`：不兼容
9. `boolean <-> integer`：弱兼容

## 8.2 单元测试：`rel_llm` 类型前置过滤

新增测试文件建议：

- `tests/unit/metaweave/relationships/test_llm_type_compat_filter.py`

至少覆盖：

1. 单列兼容候选保留  
   `service_area_id (varchar) -> id (varchar)`

2. 单列不兼容候选过滤  
   `service_area_id (varchar) -> id (integer)`

3. 复合键中任一列不兼容时过滤整个候选

4. 源/目标列画像缺失时保守放行

5. 表名大小写漂移时仍能正确命中元数据并完成过滤

6. 列名大小写漂移时仍能正确命中元数据并完成过滤

7. `single_column` 与 `composite` 两种 JSON 结构都能被统一处理

## 8.3 回归测试

回归目标：

1. `rel` 行为不变
2. `rel_llm` 最终输出关系数量在合理范围内
3. 不再出现此前那类类型不兼容 JOIN 错误日志

建议至少复跑：

```bash
python -m metaweave.cli.main pipeline generate --description "数据库中包含多个高速公路服务区的各种数据" --clean --regenerate-configs
```

重点检查：

1. `logs/rel.log`
2. `output/rel/highway_db.relationships_global.md`

---

## 9. 验收标准

本次改造完成后，应满足以下验收标准：

1. `rel_llm` 在评分前会按类型兼容性过滤候选
2. 类型兼容规则与 `rel` 使用同一套共享函数
3. `scorer` 的 `type_compatibility` 评分也复用同一套共享函数
4. `varchar -> integer`、`integer -> varchar` 等明显不兼容候选不再进入评分
5. `logs/rel.log` 中对应的数据库 JOIN 类型错误明显消失
6. 最终关系文件中不出现新的误过滤或明显回归
7. `rel` 既有行为保持不变

---

## 10. 最终结论

当前问题不是“项目没有定义类型兼容规则”，而是：

**`rel` 有前置类型过滤，`rel_llm` 没有复用这层过滤。**

因此，本次最小且正确的修复方案是：

1. 抽出 `CandidateGenerator` 中已存在的类型兼容性规则为共享函数
2. 在 `LLMRelationshipDiscovery` 中补一层评分前类型兼容过滤
3. `LLMRelationshipDiscovery` 通过大小写不敏感映射读取表/列类型，并统一处理单列与复合候选
4. 复用现有 `min_type_compatibility` 配置阈值
5. `RelationshipScorer` 也改为复用同一套共享类型兼容规则，但不改执行顺序、权重和评分公式

这是当前风险最小、收益最直接、也最符合项目现有架构的一种实现路径。
