# Bug 修复：方向约定统一

## 问题发现

**发现时间**：2025-12-26
**严重等级**：🔴 高优先级
**影响范围**：LLM 辅助关系发现（`--step rel_llm`）

## 问题描述

### 原有的不一致约定

在修复 relationship_id 方向性问题时，发现 LLM 候选的方向约定在不同阶段存在不一致：

1. **Prompt 示例**（lines 52-79）：
   ```json
   {
     "from_table": {"schema": "public", "table": "dim_region"},  // 主键表
     "to_table": {"schema": "public", "table": "dim_store"}      // 外键表
   }
   ```
   - 示例暗示：`from=主键表, to=外键表`

2. **Scorer 期望**（scorer.py:28）：
   ```python
   # inclusion_rate: 源列值在目标列中的包含率
   # 即：检查 source 值是否在 target 值集中
   ```
   - 期望：`source=外键表, target=主键表`（才能正确计算包含率）

3. **_dict_to_relation() 处理**：
   - 假设 dict 是 `from=主键表, to=外键表`
   - 交换 from/to，翻转 cardinality
   - 重新计算 relationship_id

### 导致的问题

**如果 LLM 真的按 Prompt 示例输出**（from=PK, to=FK）：

1. **评分方向错误**：
   - Scorer 按 PK->FK 方向评分
   - `inclusion_rate` 检查"PK值是否在FK值集中"❌（应该反过来）
   - 正确关系的评分会偏低，更容易被拒绝

2. **relationship_id 不一致**：
   - dict 的 ID 按 PK->FK 计算
   - 物理外键的 ID 按 FK->PK 计算
   - 即使修复后重新计算，也需要额外的交换逻辑

3. **代码复杂度**：
   - 需要在多处进行方向交换
   - 需要翻转 cardinality (N:1 ↔ 1:N)
   - 容易出错，维护困难

## 修复方案

**选择方案1**：强约束 Prompt，统一为 `from=外键表(FK), to=主键表(PK)`

### 理由

1. **与 Scorer 一致**：不需要修改评分逻辑
2. **与 Relation 一致**：Relation 对象就是 `source=FK, target=PK`
3. **与物理外键一致**：物理外键的 relationship_id 是 FK->PK 方向
4. **简化代码**：不需要交换、翻转等复杂逻辑

## 修复内容

### 1. 更新 Prompt 示例

**文件**：`metaweave/core/relationships/llm_relationship_discovery.py`

**修改前**：
```
### 单列关联示例
{
  "from_table": {"schema": "public", "table": "dim_region"},
  "to_table": {"schema": "public", "table": "dim_store"},
  ...
}
```

**修改后**：
```
**重要约定**：
- `from_table`: 外键表（多的一端，引用方）
- `from_column(s)`: 外键列
- `to_table`: 主键/唯一键表（一的一端，被引用方）
- `to_column(s)`: 主键/唯一键列

### 单列关联示例
{
  "from_table": {"schema": "public", "table": "dim_store"},     // FK 表
  "from_column": "region_id",                                    // FK 列
  "to_table": {"schema": "public", "table": "dim_region"},       // PK 表
  "to_column": "region_id"                                       // PK 列
}
说明：dim_store.region_id（外键）引用 dim_region.region_id（主键）
```

### 2. 简化 _dict_to_relation()

**修改前**（需要交换和翻转）：
```python
def _dict_to_relation(self, rel_dict: Dict) -> Relation:
    # dict: from=主键表, to=外键表
    # Relation: source=外键表, target=主键表
    # 需要交换 from/to

    # 重新计算 relationship_id（交换方向）
    relationship_id = compute_relationship_id(
        source=rel_dict["to_table"],    # 交换
        target=rel_dict["from_table"]   # 交换
    )

    return Relation(
        relationship_id=relationship_id,
        source=rel_dict["to_table"],    # 交换
        target=rel_dict["from_table"],  # 交换
        cardinality=flip(rel_dict["cardinality"])  # 翻转
    )
```

**修改后**（直接映射）：
```python
def _dict_to_relation(self, rel_dict: Dict) -> Relation:
    # 新约定：dict 和 Relation 方向一致
    # dict: from=外键表(FK), to=主键表(PK)
    # Relation: source=外键表(FK), target=主键表(PK)

    # 重新计算 relationship_id（直接使用）
    relationship_id = compute_relationship_id(
        source=rel_dict["from_table"],  # 直接映射
        target=rel_dict["to_table"]     # 直接映射
    )

    return Relation(
        relationship_id=relationship_id,
        source=rel_dict["from_table"],  # 直接映射
        target=rel_dict["to_table"],    # 直接映射
        cardinality=rel_dict["cardinality"]  # 直接使用
    )
```

### 3. 简化 _relation_to_dict()

同样移除了交换和翻转逻辑，改为直接映射。

### 4. 更新 _filter_existing_fks() 注释

说明在新约定下，正常情况 forward_rel_id 应该匹配物理外键，但仍保留 reverse 检查作为防御。

### 5. _score_candidates() 无需修改

因为它原本就是按 from->to 方向调用 scorer 和计算 relationship_id，在新约定下这已经是正确的。

## 验证测试

创建测试脚本 `/tmp/test_direction_convention_fix.py`：

```
1. 验证 dict 格式约定
  LLM 返回: employee.company_id (FK) -> company.id (PK)
  relationship_id: rel_e306fa5b42e1 (FK->PK 方向)

2. 验证物理外键 Relation
  source: employee.company_id (FK)
  target: company.id (PK)
  relationship_id: rel_e306fa5b42e1 (FK->PK 方向)

3. 验证方向一致性
  dict relationship_id:      rel_e306fa5b42e1
  物理外键 relationship_id:   rel_e306fa5b42e1
  ✅ 匹配！阶段7去重正常

4. 验证 cardinality 一致
  dict: N:1
  Relation: N:1
  ✅ 一致，无需翻转

5. 验证评分方向
  source=employee (FK表), target=company (PK表)
  ✅ inclusion_rate 将正确计算
```

## 影响分析

### 正面影响

1. **评分准确性提升**：
   - `inclusion_rate` 正确计算为"FK值在PK值集中的包含率"
   - 正确的关系不会因为评分低而被误拒

2. **去重正常工作**：
   - LLM 推断的 relationship_id 与物理外键一致
   - 阶段7去重能正确识别重复关系

3. **代码简洁**：
   - 移除了所有交换和翻转逻辑
   - 降低了维护成本和出错概率

### 潜在风险

1. **LLM 不遵守约定**：
   - 虽然 Prompt 中明确要求，但 LLM 可能仍返回反向
   - **缓解措施**：`_filter_existing_fks()` 保留双向检查作为防御

2. **历史数据兼容性**：
   - 如果之前有 LLM 生成的关系数据，方向可能相反
   - **影响**：仅影响 `--step rel_llm` 重新运行时的结果
   - **建议**：文档中提醒用户重新执行 `--step rel_llm`

## 相关代码位置

1. **Prompt 定义**：`llm_relationship_discovery.py:49-88`
2. **_dict_to_relation()**：`llm_relationship_discovery.py:624-665`
3. **_relation_to_dict()**：`llm_relationship_discovery.py:590-617`
4. **_filter_existing_fks()**：`llm_relationship_discovery.py:921-998`
5. **_score_candidates()**：`llm_relationship_discovery.py:764-858`（无需修改）

## 总结

本次修复彻底统一了方向约定：

✅ **Prompt**：明确要求 `from=FK, to=PK`
✅ **Dict 格式**：`from=FK, to=PK`
✅ **Relation 对象**：`source=FK, target=PK`
✅ **Scorer**：按 `FK->PK` 方向评分
✅ **relationship_id**：统一为 `FK->PK` 方向

**结果**：
- 评分更准确
- 去重正常工作
- 代码更简洁
- 维护更容易

---

## 变更记录

| 日期 | 版本 | 说明 |
|-----|------|------|
| 2025-12-26 | 1.0 | 统一方向约定，简化交换和翻转逻辑 |
