# Bug 修复：relationship_id 方向性问题

## 问题发现

**发现时间**：2025-12-26
**严重等级**：🔴 高优先级
**影响范围**：LLM 辅助关系发现（`--step rel_llm`）

## 问题描述

### 错误假设

代码在 `_filter_existing_fks()` 方法中错误地假设 `relationship_id` 是**双向一致**的：

```python
# ❌ 错误的注释（line 904）
# relationship_id 是双向的，不受 LLM 返回方向影响
```

### 实际情况

`MetadataRepository.compute_relationship_id()` 的实现是**有方向性的**：

```python
# metaweave/core/relationships/repository.py:184
signature = (
    f"{source_schema}.{source_table}.[{','.join(src_cols)}]->"
    f"{target_schema}.{target_table}.[{','.join(tgt_cols)}]"
    f"{rel_id_salt}"
)
```

**示例**：
- 正向：`public.employee.[company_id]->public.company.[id]` → `rel_abc123def456`
- 反向：`public.company.[id]->public.employee.[company_id]` → `rel_xyz789ghi012`

两个方向生成**完全不同**的 relationship_id！

## 问题影响

### 场景复现

1. **物理外键方向**：`employee.company_id -> company.id`
   - relationship_id = `rel_abc123def456`

2. **LLM 返回反向**：`company.id <- employee.company_id`
   - 候选的 relationship_id = `rel_xyz789ghi012`

3. **过滤失效**：
   ```python
   # 原代码只检查一个方向
   if candidate_rel_id not in fk_relationship_ids:  # rel_xyz != rel_abc，通过！
       filtered.append(candidate)  # ❌ 错误地保留了物理外键
   ```

### 后果

1. **阶段4失效**：物理外键未被过滤，进入 LLM 评分阶段
   - 浪费数据库查询资源
   - 浪费评分计算资源

2. **阶段7可能失效**：如果阶段7的去重逻辑也依赖单向 ID，会导致：
   - 物理外键重复出现在最终输出
   - 统计数据错误（外键被计为 LLM 推断）

3. **用户困惑**：
   - 看到明显的物理外键被标记为 "llm_assisted"
   - 关系数量异常增多

## 修复方案

### 核心思路

计算**正反两个方向**的 relationship_id，与物理外键集合比较：

```python
# 计算正向 ID (from -> to)
forward_rel_id = MetadataRepository.compute_relationship_id(...)

# 计算反向 ID (to -> from)
reverse_rel_id = MetadataRepository.compute_relationship_id(
    source_schema=to_info["schema"],  # 交换
    source_table=to_info["table"],
    source_columns=to_cols,
    target_schema=from_info["schema"],  # 交换
    target_table=from_info["table"],
    target_columns=from_cols,
    ...
)

# 检查任一方向匹配
if forward_rel_id in fk_relationship_ids or reverse_rel_id in fk_relationship_ids:
    # 跳过这个候选（它是物理外键）
    skipped_count += 1
else:
    filtered.append(candidate)
```

### 代码变更

**文件**：`metaweave/core/relationships/llm_relationship_discovery.py`

**修改位置**：`_filter_existing_fks()` 方法（line 898-960）

**关键改动**：

1. ✅ 添加反向 ID 计算
2. ✅ 修改过滤条件为 `forward OR reverse`
3. ✅ 更新注释，明确说明方向性
4. ✅ 改进日志，显示匹配的 ID

### 性能影响

- **额外计算**：每个候选多计算一次 MD5（微不足道）
- **收益**：避免重复评分和数据库查询（显著节省）

## 测试验证

### 测试场景

```python
# 物理外键
fk = {
    "source": "employee", "source_columns": ["company_id"],
    "target": "company", "target_columns": ["id"]
}
fk_id = "rel_abc123"  # employee->company

# LLM 返回反向
llm_candidate = {
    "from_table": "company", "from_column": "id",
    "to_table": "employee", "to_column": "company_id"
}
# 原代码：candidate_id = "rel_xyz789" ≠ "rel_abc123" → 未过滤 ❌
# 修复后：reverse_id = "rel_abc123" = fk_id → 正确过滤 ✅
```

### 预期行为

修复后，无论 LLM 返回哪个方向，都能正确识别为物理外键并跳过。

## 相关代码位置

1. **Bug 位置**：`metaweave/core/relationships/llm_relationship_discovery.py:898-960`
2. **ID 计算**：`metaweave/core/relationships/repository.py:152-191`
3. **阶段7去重**：`metaweave/core/relationships/llm_relationship_discovery.py:_deduplicate_by_relationship_id()`

## Bug 2：`_dict_to_relation()` 使用错误的 relationship_id 方向

### 问题发现

在修复 Bug 1 后，进一步检查发现 `_deduplicate_by_relationship_id()` 也存在方向性问题，但根本原因不同。

### 问题描述

`_dict_to_relation()` 方法在将 dict 格式转换为 Relation 对象时，直接复制了 dict 的 relationship_id：

```python
# ❌ 错误的实现（line 633）
return Relation(
    relationship_id=rel_dict["relationship_id"],  # 使用 dict 的 ID
    source_schema=rel_dict["to_table"]["schema"],  # FK 表
    source_table=rel_dict["to_table"]["table"],
    source_columns=to_columns,
    target_schema=rel_dict["from_table"]["schema"],  # PK 表
    target_table=rel_dict["from_table"]["table"],
    target_columns=from_columns,
    # ...
)
```

### 实际情况

**Dict 的 relationship_id**（line 812-820）：
```python
relationship_id = MetadataRepository.compute_relationship_id(
    source_schema=from_table_info["schema"],  # PK 表（dict 约定）
    source_table=from_table_info["table"],
    source_columns=from_columns,
    target_schema=to_table_info["schema"],    # FK 表（dict 约定）
    target_table=to_table_info["table"],
    target_columns=to_columns,
    # ...
)
# 结果：relationship_id = hash("PK表 -> FK表")
```

**Relation 对象的约定**（repository.py:127-137）：
```python
relation = Relation(
    source_schema=source_schema,  # FK 表（Relation 约定）
    source_table=source_table,
    source_columns=source_columns,
    target_schema=target_schema,  # PK 表（Relation 约定）
    target_table=target_table,
    target_columns=target_columns,
    # ...
)
# relationship_id 应该 = hash("FK表 -> PK表")
```

### 问题影响

1. **阶段7去重完全失效**：
   ```python
   # _deduplicate_by_relationship_id() 中
   fk_id_map = {rel.relationship_id: rel for rel in fk_relations}
   # fk_relations: relationship_id = hash("FK -> PK")

   for llm_rel in llm_relations:
       rel_id = llm_rel.relationship_id  # hash("PK -> FK") ❌ 方向相反
       if rel_id in fk_id_map:  # 永远不匹配！
           # 这行代码永远不会执行
   ```

2. **后果**：
   - 所有物理外键都会被重复输出（一次作为 foreign_key，一次作为 llm_assisted）
   - 统计数据严重错误
   - 用户看到大量重复关系

### 修复方案

在 `_dict_to_relation()` 中重新计算 relationship_id，使用 Relation 约定（FK->PK）：

```python
def _dict_to_relation(self, rel_dict: Dict) -> Relation:
    # 提取列名
    if rel_dict["type"] == "single_column":
        from_columns = [rel_dict["from_column"]]
        to_columns = [rel_dict["to_column"]]
    else:
        from_columns = rel_dict["from_columns"]
        to_columns = rel_dict["to_columns"]

    # ✅ 重新计算 relationship_id，使用 Relation 方向（FK->PK）
    relationship_id = MetadataRepository.compute_relationship_id(
        source_schema=rel_dict["to_table"]["schema"],      # FK 表
        source_table=rel_dict["to_table"]["table"],
        source_columns=to_columns,
        target_schema=rel_dict["from_table"]["schema"],    # PK 表
        target_table=rel_dict["from_table"]["table"],
        target_columns=from_columns,
        rel_id_salt=self.repo.rel_id_salt
    )

    return Relation(
        relationship_id=relationship_id,  # ✅ 使用重新计算的 ID
        # ...
    )
```

### 预期行为

修复后：
- 物理外键 Relation: relationship_id = hash("FK -> PK")
- LLM 推断 Relation: relationship_id = hash("FK -> PK")
- 阶段7去重正常工作，物理外键不会重复输出

## 长期改进建议

### 方案A：规范化方向

在生成 relationship_id 之前，先规范化关系方向：

```python
def normalize_relationship_direction(source_table, target_table, ...):
    """规范化关系方向（例如：总是让字典序较小的表作为 source）"""
    if (source_schema, source_table) > (target_schema, target_table):
        # 交换 source 和 target
        return target_*, source_*, flipped_cardinality
    return source_*, target_*, cardinality
```

**优点**：
- relationship_id 真正变成双向一致
- 后续所有比较都简化

**缺点**：
- 需要同时翻转 cardinality（N:1 ↔ 1:N）
- 对现有数据库中的 relationship_id 可能有影响

### 方案B：保持方向性（当前方案）

明确 relationship_id 是有方向的，所有比较都检查双向：

**优点**：
- 不破坏现有数据
- 语义清晰（保留原始方向信息）

**缺点**：
- 每次比较都需要计算两个 ID
- 容易遗漏（如本次 bug）

## 总结

1. ✅ **Bug 1 已修复**：`_filter_existing_fks()` 现在正确处理双向 ID
   - 计算正反两个方向的 relationship_id
   - 检查任一方向是否与物理外键匹配
   - 避免物理外键进入 LLM 评分阶段

2. ✅ **Bug 2 已修复**：`_dict_to_relation()` 现在重新计算正确方向的 ID
   - 不再直接复制 dict 的 relationship_id
   - 使用 Relation 约定（FK->PK）重新计算
   - 确保阶段7去重能正常工作

3. 💡 **长期建议**：考虑方向规范化方案，彻底解决方向性问题

---

## 变更记录

| 日期 | 版本 | 说明 |
|-----|------|------|
| 2025-12-26 | 1.0 | 修复 _filter_existing_fks() 的双向 ID 比较 bug |
| 2025-12-26 | 2.0 | 修复 _dict_to_relation() 的 relationship_id 方向 bug |
