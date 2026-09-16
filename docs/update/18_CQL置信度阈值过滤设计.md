# CQL 置信度阈值过滤与 relationship_id 边身份设计

## 1. 需求

1. **阈值过滤**:在配置文件中为 CQL 增加一个阈值参数:生成 CQL 时,对 rel 文件
   中的推断关系按 `composite_score` 过滤,只有 **`composite_score >= 阈值`** 的
   关系才进入 cypher 文件(默认阈值 0.9);
2. **relationship_id 边身份 + 重复去重**:Cypher 原以
   `MERGE (src)-[r:JOIN_ON]->(dst)` 按"源节点 + 关系类型 + 目标节点"匹配边,
   同表对的多条**不同业务关系**(如 `orders.shipping_address_id→addresses.id`
   与 `orders.billing_address_id→addresses.id`)会命中同一条边、互相覆盖属性。
   改为 `MERGE (src)-[r:JOIN_ON {relationship_id: j.relationship_id}]->(dst)`,
   以 doc 19 提供的稳定 `relationship_id` 作为边身份:不同业务关系并存,同关系
   重复导入幂等;CQL 侧仅按 `relationship_id` 去除完全重复的条目。

这两项需求构成 CQL 消费 rel 产物的统一处理,但职责分别落在:
reader(分数校验、阈值过滤、重复 ID 校验与去重)、model(传递
relationship_id)、writer(以 relationship_id 建立边身份)。

## 2. 过滤规则

### 2.1 过滤对象:仅推断关系,FK 直通豁免

rel 文件中有两类关系:

| 类型 | 判定依据 | 是否参与过滤 |
|---|---|---|
| 物理外键直通 | `discovery_method == "foreign_key_constraint"` | **豁免,无条件保留**——数据库声明的事实,不受置信度影响 |
| 推断关系(rule / llm) | 其余(携带 `composite_score`) | 参与过滤 |

规则:**仅按 `discovery_method` 判定豁免**——`== "foreign_key_constraint"`
无条件保留;其余按 `composite_score >= 阈值` 过滤。

注意:
1. **`relationship_type` 是 Relation 内存字段,不进 rel JSON**(writer 输出键:
   `relationship_id / type / from_table / to_table / from_column(s) /
   to_column(s) / discovery_method / target_source_type / source_constraint /
   composite_score / confidence_level / metrics / cardinality`)。CQL 侧唯一
   判据是 `discovery_method`,不得按 `relationship_type` 判定(恒取 None);
   rel JSON 的 `type` 键含义是 single_column/composite,勿与关系类型混淆;
2. (doc 19 实施后)FK 直通现携带 `composite_score = 1.0`
   (`FOREIGN_KEY_COMPOSITE_SCORE`),**不得以"字段缺失"作为 FK 的判定依据**——
   豁免语义与分数值无关(未来 FK 分数调整也不得改变豁免行为)。

### 2.2 边界语义与输入校验

- `composite_score == 阈值` → 保留(`>=`);
- 阈值非法(非数值、< 0、> 1)→ 配置校验报错,沿用"非法配置不静默"纪律;
- 不做"0 = 不过滤"之类的隐式语义;想全量导入就显式把阈值设为 0;
- **推断关系的分数校验(数据损坏不静默)**:
  - FK 直通仅按 `discovery_method` 豁免,**不要求分数**;
  - 推断关系必须携带 `composite_score`,校验顺序与配置阈值完全一致:
    1. **拒绝 bool**(`isinstance(True, (int, float))` 为 True、
       `math.isfinite(True)` 为 True,JSON 中的 `"composite_score": true`
       会被当成 1.0 通过过滤,必须显式排除);
    2. 必须是 int / float;
    3. 必须有限(非 NaN / 无穷大);
    4. 必须在 `[0, 1]`;
  - 不符合任一 → **报错**,错误信息包含 `relationship_id` 与来源文件名——
    损坏数据不静默丢弃,由操作者修复源头;
- **relationship_id 校验(边身份/去重键/MERGE 属性,适用所有关系)**:
  - 必须携带 `relationship_id`,且为**去除空白后非空**的字符串;
  - 缺失 / null / 空串 / 纯空白 / 非字符串 → **立即报错**,错误信息包含
    来源文件名与表/字段信息——否则会产生
    `MERGE (src)-[r:JOIN_ON {relationship_id: null}]->(dst)` 这类 Neo4j
    无法执行的语句;
  - **存在首尾空白 → 报错**(要求 `relationship_id == relationship_id.strip()`,
    不静默修改——它是持久化边身份;doc 19 生成的合法 ID 本不含空格,带空白
    即数据损坏)。

### 2.3 relationship_id 边身份与重复去重

**动机**:原 Cypher 的 `MERGE (src)-[r:JOIN_ON]->(dst)` 把"源节点 + 关系类型
+ 目标节点"当成边身份,同 `(src, dst)` 的多条关系命中同一条边,后处理条目通过
`SET` 覆盖先处理条目的属性(`on` / `cardinality` / `source_columns` /
`target_columns`),导致前一条的列对应关系静默丢失。典型实例(doc 19 §2.4 第
7 项):`orders.shipping_address_id→addresses.id` 与
`orders.billing_address_id→addresses.id`——同表对、同方向,但属两条不同的
业务关系。**按表对去重不可接受**:无论保留哪条,另一条真实关联都会永久丢失;
同表对存在两个物理 FK 时"FK 优先"也无法决定保留哪一个。根因是边身份缺失,
而不是"重复"。

**方案**:

- writer 的 MERGE 改为:
  `MERGE (src)-[r:JOIN_ON {relationship_id: j.relationship_id}]->(dst)`
  ——以 `relationship_id` 作为边身份属性:同表对不同 `relationship_id` 的
  业务关系各自成边、并存;相同关系重复导入命中同一条边,幂等;
- **产品语义变更(消费方须知)**:JOIN_ON 边语义从"一对表一条边"变为
  "一条业务关系一条边"——按 `(src, dst)` 查询可能返回多条平行边,下游
  (NL2SQL 图查询、图谱消费方)必须感知 `relationship_id` 才能区分;
- rel JSON 已落盘稳定的 `relationship_id`(doc 19 生成),reader 读取并透传
  到 `JOINOnRelation`;
- **CQL 侧去重仅按 `relationship_id` 完全相同的条目**执行(rel 正常产物不会
  重复,属防御性去重)。实现:去重前**按 `relationship_id` 字典序排序**,再
  处理相邻重复——完全确定,不依赖输入顺序;顺带使 cypher 输出顺序确定。
  **不得以"原始列表顺序"做任何 tie-break**:rel 文件顺序不具确定性(CQL 侧
  `glob` 未排序,rel 上游同样存在未排序文件遍历与集合迭代);
- **同 ID 的语义**(Python 稳定排序不能区分同 ID 条目的先后,必须显式规定;
  比较必须基于**规范化载荷**,不得直接比较原始列表):
  - `canonical_payload` 规范化比较结构:
    ```python
    canonical_payload = {
        "type": ...,                      # single_column / composite
        "from_table": ...,                # {schema, table}
        "to_table": ...,                  # {schema, table}
        "column_pairs": sorted(zip(from_columns, to_columns)),
                                          # 复合字段按"字段对应对"整体排序:
                                          # A(a,b)→B(x,y) 与 A(b,a)→B(y,x)
                                          # 是同一关系,不得误报冲突
        "discovery_method": ...,
        "composite_score": ...,           # 仅推断关系;FK 不参与
        "cardinality": ...,
        "constraint_name": ...,           # 缺失与 null 统一为 None
    }
    ```
  - 比较规则:
    - 相同 ID 且 `canonical_payload` 一致 → 完全重复,**载荷一致时保留一份**
      (不依赖输入顺序);
    - 相同 ID 但 `canonical_payload` 不同 → **数据冲突,报错**,错误信息列出
      两个来源文件(防御哈希碰撞与目录中混入不同批次文件;报错要求 reader
      汇总原始关系时保留来源文件,见 §5 `RawRelationshipEntry`);
    - **推断关系的 `composite_score` 不同视为冲突**;**FK 的分数不参与冲突
      比较**(FK 分数不参与过滤);
    - `metrics`、`confidence_level` 等 CQL 不消费的诊断字段**不参与比较**。

**统一处理顺序**(校验与冲突检查必须先于阈值过滤,否则"损坏数据不静默"
不成立——同 ID 两条分数不同(0.95 / 0.85,阈值 0.9)时,先过滤会删掉低分
条目,冲突检查永远发现不了目录混入了两批不同产物):

1. 读取全部文件,并保留来源文件(`RawRelationshipEntry`);
2. 校验所有 `relationship_id`(缺失 / null / 空串 / 纯空白 / 非字符串 → 报错);
3. **校验关系结构**(在构造 canonical_payload 之前——Python `zip()` 会静默
   截断长度不同的列表,`from_columns=["a","b"]` 与 `to_columns=["x"]` 会静默
   变成 `[("a","x")]`,损坏数据不得被静默转换成不完整关系):
   - **`type` 必须严格为 `single_column` 或 `composite`**——缺失 / 未知值 /
     拼写错误 → 报错(当前 reader 的 else 分支会一律按复合处理,拼写错误被
     静默吞掉,必须改);
   - `type == "single_column"`:`from_column` / `to_column` 必须是非空字符串;
   - `type == "composite"`:两侧必须是非空列表;
   - 两侧字段数量必须相等;
   - 列表元素必须是非空字符串;
   - `from_table` / `to_table` 的 schema / table 必须有效;
   - **"非空字符串"统一口径:`isinstance(value, str) and bool(value.strip())`**
     ——`"   "` 在 Python 中仍是非空字符串,必须按去除空白后非空判定;
   - **`cardinality` 必须显式存在且只能是 `N:1` / `1:1` / `M:N`**——`1:N`
     报错(doc 19 输出契约下不应出现);缺失**不得**静默默认为 N:1(当前
     reader 的 `rel.get("cardinality", "N:1")` 掩盖损坏数据,必须改);
   - **`discovery_method` 必须是非空字符串**:`== "foreign_key_constraint"`
     → FK 豁免;其他非空字符串 → 按推断关系过滤;缺失 / 空值 / 非字符串 →
     报错(不把推断类型写死为固定枚举,未来新增方法自动落入推断路径);
   - 不符合 → 报错,含 `relationship_id` 与来源文件;
4. 校验所有推断关系分数(FK 直通豁免;缺失 / null / 字符串 / NaN / 无穷大 /
   越界 → 报错);
5. 按 `relationship_id` 分组并检查载荷冲突(同 ID 关键内容不同 → 报错并列出
   两个来源文件);
6. 执行阈值过滤(FK 豁免);
7. 对已确认一致的重复 ID 去重(按 `relationship_id` 字典序排序,保留一份);
8. 转换成 `JOINOnRelation`。

### 2.4 过滤位置与范围

过滤在 **CQL reader 读取 rel 文件时执行**,用**原始 rel dict** 的
`composite_score` 判断——`JOINOnRelation` 模型不携带该字段,转换后无法过滤。

**范围:必须跨文件统一执行**。`_read_relationships` 是
`glob("*.relationships_*.json")` 的多文件循环(配置留有
`rel_granularity: global | schema` 扩展位,当前 Phase 1 只有 global 一份),
阈值过滤与 relationship_id 去重必须在**所有文件读完、`_extract_join_relation`
转换之前**对全部关系统一执行,然后统一返回——**不得在单文件循环内做去重**
(跨文件的同 ID 重复与同表对覆盖同理会漏网)。

## 3. 配置设计

新增顶层配置节点:

```yaml
cql_generation:
  composite_score_threshold: 0.9   # 仅导入 composite_score >= 0.9 的推断关系;FK 直通不受限
```

- 节点缺失或字段缺失 → 默认值 `0.9`(与 `decision.high_confidence_threshold`
  0.90 语义对齐);
- 校验顺序(显式声明非法值 → 报错):
  1. **拒绝 bool**(`isinstance(True, int)` 为 True,必须显式排除);
  2. 接受 int / float;
  3. `math.isfinite(value)`(排除 NaN / ±inf,NaN 会绕过普通范围判断);
  4. `0 <= value <= 1`;
- 由 `CQLGenerator` 读取配置并透传给 reader(与现有架构一致:generator 持有
  self.config)。

## 4. 代码修改范围

| 文件 | 修改内容 |
|---|---|
| `configs/metadata_config.yaml` | 新增 `cql_generation.composite_score_threshold: 0.9`(附注释) |
| `metaweave/core/cql_generator/generator.py` | 读取并校验阈值;透传给 reader;接收五元组结果;将 `filter_stats` 写入 `CQLGenerationResult` 并传给 writer |
| `metaweave/core/cql_generator/models.py` | `JOINOnRelation` 新增 `relationship_id` 字段(写入 cypher 参数);`CQLGenerationResult` 新增 `filter_stats` 字段(见 §5) |
| `metaweave/core/cql_generator/reader.py` | 文件循环读取并汇总原始关系(保留来源文件,即 §2.3 第 1 步);随后按 §2.3 的完整八步流程处理:校验 ID → 校验关系结构 → 校验分数 → 同 ID 冲突检查 → 阈值过滤 → 重复 ID 去重 → `_extract_join_relation` 转换(透传 `relationship_id`);统计经 `RelationshipFilterStats` 返回给 generator(见 §5) |
| `metaweave/core/cql_generator/writer.py` | ①**两处 JOIN_ON 模板都要改**为 `MERGE (src)-[r:JOIN_ON {relationship_id: j.relationship_id}]->(dst)`:独立关系文件 `_write_join_on_rels()`(writer.py:222)与 import_all 文件 `_write_import_all()`(writer.py:346)——只改一处会导致 05_rels_join_on.cypher 支持多关系、import_all.*.cypher 仍覆盖同表对;两个输出文件都必须包含 `{relationship_id: j.relationship_id}` 匹配键;②`write_metadata()` 增加 `filter_stats` 参数,md 数量表增加六项过滤统计,最终 JOIN_ON 数必须等于 `filter_stats.final_count`;generator 调用 `write_metadata()` 时透传统计 |
| `metaweave/cli/metadata_cli.py` | `cql`(约 711 行)与 `cql_llm`(约 663 行)两个结果统计区读取 `result.filter_stats`,输出候选数 / 阈值通过数 / 过滤数 / 重复组数 / 丢弃数 / 最终数 |
| `tests/unit/.../cql_generator/*`(按现有测试目录) | 新增阈值过滤与边身份去重用例(见 §6);**同步适配受接口变化影响的现有测试**:`test_cql_generator.py:192`(JOINOnRelation 直接构造,需带 relationship_id)、`test_import_all_cypher_ids.py:32`(同)、`test_cypher_writer_metadata.py:69`(write_metadata 新签名)、`test_step_all_orchestrator.py:91`(CQLGenerationResult 直接构造,filter_stats 用 default_factory 后无需传参但需回归验证) |

不改:rel 管线、scorer、decision、writer(rel 侧)。

## 5. 统计与报告

- 过滤与去重必须**可观测**,统计经显式数据结构跨模块传递:

```python
@dataclass
class RelationshipFilterStats:
    candidate_count: int = 0              # 候选关系数 = 全部条目
    threshold_passed_count: int = 0       # 通过阈值数 = FK 直通豁免 + 达标推断
    threshold_filtered_count: int = 0     # 被阈值过滤数 = 不达标推断
    duplicate_group_count: int = 0        # 重复 relationship_id 组数
    duplicate_discarded_count: int = 0    # 重复 ID 去重丢弃数
    final_count: int = 0                  # 最终 JOIN_ON 数(直接记录,避免使用方自行计算)
```

**失败路径与兼容默认值**:全部字段默认 0——生成失败路径(generator 的
except 分支直接构造 `CQLGenerationResult`)、现有测试替身、其他直接构造结果
对象的调用方、CLI 在失败结果上读取统计,都获得稳定结构。`CQLGenerationResult`
的字段声明为:

```python
filter_stats: RelationshipFilterStats = field(default_factory=RelationshipFilterStats)
```

**统计恒等式**(以"先冲突检查、再过滤、再去重"的顺序为前提,实现时可用
assert 校验):

```text
candidate_count = threshold_passed_count + threshold_filtered_count
final_count     = threshold_passed_count - duplicate_discarded_count
```

- 代码位置:
  - `RelationshipFilterStats` 放在 **cql_generator/models.py**(被 reader、
    generator、writer、CLI 与 `CQLGenerationResult` 共享);
  - `RawRelationshipEntry` 放在 **reader.py**,作为 reader 内部实现,不向外
    暴露;
- 传递路径:reader 构造并返回 `RelationshipFilterStats` →
  `JSONReader.read_all()` 返回类型由四元组改为**五元组**:

  ```python
  tables, columns, has_column_rels, join_on_rels, filter_stats
  ```

  → generator 接收后写入 `CQLGenerationResult`(新增 `filter_stats` 字段)→
  CLI 汇总打印、透传给 writer 写入 md 数量表;
- 汇总原始关系时**保留来源文件**供冲突报错使用:

```python
@dataclass
class RawRelationshipEntry:
    relationship: dict
    source_file: Path
```

- 被过滤、被去重的关系不进 cypher 文件,**不计入 md 的最终 JOIN_ON 数量**
  (当前 md 只有数量表、无关系明细清单,统计落到数量表即可)。

## 6. 测试计划

- FK 直通关系(唯一判据 `discovery_method == "foreign_key_constraint"`,
  现携带 composite_score=1.0)在任意阈值下都保留——**含 FK 分数低于阈值的
  构造用例**(类型豁免与分数值无关;relationship_type 不落盘,不得作为判据);
- 推断关系 `composite_score` >= 阈值 → 保留;== 阈值 → 保留;< 阈值 → 丢弃;
- 阈值配置缺失 → 默认 0.9;显式非法值(非数值、-0.1、1.5、**true、
  NaN、±inf**)→ 报错;
- 阈值 0 → 全量导入(显式语义);阈值 1 → 仅 composite_score == 1.0 的推断
  关系 + 全部 FK;**构造阈值 1 的用例时数值必须用精确 1.0**——推断分数是五维
  加权浮点和,`>=` 语义下 0.9999… 会被正确过滤,若用"看起来是 1"的浮点近似
  值(如 0.5+0.1+0.1+0.1+0.2 的累积误差)会测出假阳性;
- **分数校验**:推断关系缺分数 / null / 字符串 / NaN / inf / -0.1 / 1.5 /
  **true / false** → 报错且错误信息含 relationship_id 与来源文件名;FK 直通
  分数缺失或为 0 → 不校验、正常豁免;
- **边身份去重**:同表对不同 `relationship_id`(shipping/billing 两字段映射)
  → **全部保留**,cypher 输出两条 MERGE 数据(各自带 relationship_id);
  相同 `relationship_id` 且载荷一致 → **保留一份**(不依赖输入顺序);cypher 的
  MERGE 模板含 `{relationship_id: j.relationship_id}` 匹配键;
- **规范化载荷比较**:`A(a,b)→B(x,y)` 与 `A(b,a)→B(y,x)`(字段对应对相同、
  顺序不同)→ 载荷一致,不误报冲突;constraint_name 缺失与 null 统一;FK 的
  分数差异不报冲突;
- **结构校验失败路径**:复合两侧字段数量不一致 / 空列表 / 空字段名 /
  single_column 字段缺失 / **非法或缺失 type / cardinality 缺失或为 1:N /
  discovery_method 缺失、空值或非字符串 / `"   "` 类纯空白字段值**(代表用例
  `"from_column": "   "`,其余字段共用同一口径,不逐一重复测试)→ 报错(含
  relationship_id 与来源文件),不静默截断、不静默默认;
- **跨文件处理**:两条关系放在**不同 rel 文件**中(同表对或同 ID 重复)→
  过滤与去重结果与单文件场景一致;
- **双物理 FK 同表对**:同一表对存在两个不同物理 FK(不同字段映射)→ 两条
  边都保留,真实关系不因去重丢失;
- **顺序无关性**:反转文件顺序与关系列表顺序 → 过滤结果、去重结果一致,
  JOIN_ON 章节中关系**按 relationship_id 字典序排列**。**不得比较整个 CQL
  文件字节**——import_all 文件含 `datetime.now().isoformat()` 时间戳
  (writer.py:250),两次生成不可能字节级相同;断言方式:解析 JOIN_ON 章节的
  join_on_json(或仅比较该章节),不比较生成时间;
- **分数校验失败路径**:推断关系缺失 / 非法 / 非有限 composite_score → 明确
  报错(含 relationship_id 与文件名);
- **relationship_id 校验失败路径**:任一关系(含 FK 直通)缺失 / null / 空串 /
  纯空白 / 非字符串 relationship_id → 报错(含文件名与表/字段信息);
  **首尾空白**(如 `" rel_abc123 "`)→ 报错,不自动裁剪;
- **同 ID 冲突路径**:同 ID 载荷一致 → 去重留一份;同 ID 但 cardinality /
  方向 / 字段映射 / constraint_name 不同 → 报错并列出两个来源文件;**同 ID
  两条分数不同、低分在阈值之下 → 仍报冲突**(冲突检查先于阈值过滤);
- CLI 汇总与 md 报告中的六项统计正确。

## 7. 验收标准

1. 配置文件新增 `cql_generation.composite_score_threshold`(默认 0.9);
2. 生成 CQL 时,推断关系按 `composite_score >= 阈值` 过滤,FK 直通无条件保留;
3. JOIN_ON 边以 `relationship_id` 为身份:同表对不同业务关系各自成边并存;
   相同 `relationship_id` 的条目去重(幂等);
4. 阈值非法值报错;缺失用默认值;
5. 输出(cypher + md)与统计体现过滤与去重结果;
6. rel、评分、决策代码零改动。

## 8. 非目标

- 不改 rel 阶段写文件的阈值(accept_threshold 0.8 保持不变);
- 不按 `confidence_level`(high/medium/low)过滤——只按数值 `composite_score`;
- 不改 rel 产物的方向语义(doc 19 已统一方向并删除 CQL 的 1:N 翻转,本设计
  保持 CQL 纯消费,不恢复任何翻转);
- 不涉及 CQL 的 uniqueness/null_rate 等其它适配(已有独立问题与修复);
- 不涉及 Neo4j 历史数据迁移——旧边无 `relationship_id` 匹配键,新 MERGE 不会
  命中旧边,重新导入会新增带身份的边(旧边需人工清理,属运维行为,不在本设计
  范围)。**阈值或 `rel_id_salt` 变化后,建议全量重建;本次不支持增量同步**;
- **全量重建命令与语义**(避免混淆):
  - `metaweave load --type cql --clean`:执行
    `MATCH (n) DETACH DELETE n`(cql_loader.py:187)——**清空目标 Neo4j
    数据库的全部节点与关系,不只是 JOIN_ON**。若该 Neo4j 实例由 MetaWeave
    独占,这符合"清空后全量重写";若与其它数据共用,不得使用 --clean;
  - `metaweave metadata --step cql --clean`:**只清理本地 CQL 输出文件,
    不能清理 Neo4j**,两者不可混用。
