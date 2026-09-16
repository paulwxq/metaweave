# CQL 置信度阈值过滤与同表对去重设计

## 1. 需求

1. **阈值过滤**:在配置文件中为 CQL 增加一个阈值参数:生成 CQL 时,对 rel 文件
   中的推断关系按 `composite_score` 过滤,只有 **`composite_score >= 阈值`** 的
   关系才进入 cypher 文件(默认阈值 0.9);
2. **同表对去重**:Cypher 以 `MERGE (src)-[r:JOIN_ON]->(dst)` 按"源表 + 目标表"
   建边,同 `(src, dst)` 的多条关系会互相覆盖属性(列对应信息丢失)。生成 CQL 时
   对同 `(src_full_name, dst_full_name)` 的条目**只保留一条**:**FK 直通优先,
   其余以 `composite_score` 最高者为准**。

两条需求都在 CQL reader 消费 rel 文件时执行,属于同一个过滤环节。

## 2. 过滤规则

### 2.1 过滤对象:仅推断关系,FK 直通豁免

rel 文件中有两类关系:

| 类型 | 判定依据 | 是否参与过滤 |
|---|---|---|
| 物理外键直通 | `discovery_method == "foreign_key_constraint"`(或按 `relationship_type == "foreign_key"`);**无 `composite_score` 字段** | **豁免,无条件保留**——数据库声明的事实,不受置信度影响 |
| 推断关系(rule / llm) | 有 `composite_score` | 参与过滤 |

规则:**`composite_score` 字段存在且 < 阈值 → 丢弃;字段不存在(FK)→ 保留;
字段存在且 >= 阈值 → 保留**。

### 2.2 边界语义

- `composite_score == 阈值` → 保留(`>=`);
- 阈值非法(非数值、< 0、> 1)→ 配置校验报错,沿用"非法配置不静默"纪律;
- 不做"0 = 不过滤"之类的隐式语义;想全量导入就显式把阈值设为 0。

### 2.3 同表对去重

**动机**:Cypher 的 `MERGE (src)-[r:JOIN_ON]->(dst)` 按"源节点 + 关系类型 +
目标节点"匹配;同 `(src_full_name, dst_full_name)` 的多个列表条目会命中同一
条边,后处理条目通过 `SET` 覆盖先处理条目的属性(`on` / `cardinality` /
`source_columns` / `target_columns`),导致前一条的列对应关系静默丢失。现状
已有实例:rel 中 `products→orders(1:N)` 与 `orders→products(N:1)` 两条关系在
翻转后都变成 `orders→products`,同表对同方向(当前恰好 `on` 相同,无损;若
`on` 不同即丢信息)。

**规则**:同 `(src_full_name, dst_full_name)` 的条目只保留一条:

1. FK 直通(无 `composite_score`)**优先级最高**,无条件保留;
2. 其余保留 `composite_score` 最高者;
3. `composite_score` 相同 → 按列表原始顺序稳定保留第一条(确定性)。

**与阈值过滤的执行顺序**:先执行 2.1 阈值过滤(FK 豁免),再执行同表对去重;
两者结果与"先组内取最高、再比阈值"等价,实现按此顺序即可。

### 2.4 过滤位置

过滤在 **CQL reader 读取 rel 文件时执行**(`reader._read_relationships` 的
关系循环内、`_extract_join_relation` 转换之前),用**原始 rel dict** 的
`composite_score` 判断——`JOINOnRelation` 模型不携带该字段,转换后无法过滤。

## 3. 配置设计

新增顶层配置节点:

```yaml
cql_generation:
  composite_score_threshold: 0.9   # 仅导入 composite_score >= 0.9 的推断关系;FK 直通不受限
```

- 节点缺失或字段缺失 → 默认值 `0.9`(与 `decision.high_confidence_threshold`
  0.90 语义对齐);
- 校验:必须是数值且在 `[0, 1]` 内;显式声明非法值 → 报错;
- 由 `CQLGenerator` 读取配置并透传给 reader(或 reader 自行读配置,实现时二选
  一,以 generator 为配置读取入口为准)。

## 4. 代码修改范围

| 文件 | 修改内容 |
|---|---|
| `configs/metadata_config.yaml` | 新增 `cql_generation.composite_score_threshold: 0.9`(附注释) |
| `metaweave/core/cql_generator/generator.py` | 读取阈值配置并校验(数值、[0,1]);透传给 reader;CLI 汇总输出过滤统计 |
| `metaweave/core/cql_generator/reader.py` | `_read_relationships` 循环内:①按 2.1 阈值过滤(FK 豁免);②按 2.3 同 `(src, dst)` 去重(FK 优先,其余取 composite_score 最高);统计"候选 / 通过阈值 / 被过滤 / 同表对冲突组 / 去重丢弃"数量并暴露给 generator |
| `tests/unit/.../cql_generator/*`(按现有测试目录) | 阈值过滤用例(见 §5) |

不改:rel 管线、scorer、writer、cypher 生成模板。

## 5. 统计与报告

- 过滤与去重必须**可观测**:CLI 汇总与 md 报告体现五数——候选关系数 /
  通过阈值数 / 被阈值过滤数(含 FK 直通豁免数)/ 同表对冲突组数 / 去重丢弃数;
- 被过滤、被去重的关系不进 cypher 文件、不进 md 的关系清单。

## 6. 测试计划

- FK 直通关系(无 `composite_score`)在任意阈值下都保留;
- 推断关系 `composite_score` >= 阈值 → 保留;== 阈值 → 保留;< 阈值 → 丢弃;
- 阈值配置缺失 → 默认 0.9;显式非法值(非数值、-0.1、1.5)→ 报错;
- 阈值 0 → 全量导入(显式语义);阈值 1 → 仅 composite_score == 1.0 的推断
  关系 + 全部 FK;
- **同表对去重**:同 `(src, dst)` 两条且 `on` 不同 → 保留 composite_score 高者;
  FK 与推断冲突 → FK 保留;同分 → 稳定保留第一条;cardinality 一致但 on 不同
  → 仍去重(去重键是 (src, dst),与 cardinality/on 无关);
- CLI 汇总与 md 报告中的五数统计正确。

## 7. 验收标准

1. 配置文件新增 `cql_generation.composite_score_threshold`(默认 0.9);
2. 生成 CQL 时,推断关系按 `composite_score >= 阈值` 过滤,FK 直通无条件保留;
3. 同 `(src, dst)` 条目只保留一条:FK 优先,其余 composite_score 最高者;
4. 阈值非法值报错;缺失用默认值;
5. 输出(cypher + md)与统计体现过滤与去重结果;
6. rel、评分、决策代码零改动。

## 8. 非目标

- 不改 rel 阶段写文件的阈值(accept_threshold 0.8 保持不变);
- 不按 `confidence_level`(high/medium/low)过滤——只按数值 `composite_score`;
- 不改 rel 产物的方向语义(1:N 关系的 from/to 保持现状;CQL 的 1:N 翻转逻辑
  不变);
- 不涉及 CQL 的 uniqueness/null_rate 等其它适配(已有独立问题与修复)。
