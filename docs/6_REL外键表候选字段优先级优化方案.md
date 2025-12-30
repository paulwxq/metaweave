# REL 外键表候选字段优先级优化方案

**文档类型：** 📋 **设计规范与改造方案**（代码尚未实施）  
**创建日期：** 2025-12-31  
**影响范围：** `--step rel` 和 `--step rel_llm`  
**修改类型：** 🔧 逻辑优化（不涉及 Schema 变更）

---

## 1. 背景与目标

### 1.1 术语说明

在关系发现过程中，涉及两个表：

| 术语 | 说明 | 代码中的名称 | 示例 |
|------|------|--------------|------|
| **驱动表** | 拥有主键/唯一键的表，是关系的"一"方 | `source_table` | `dim_product`（产品维度表） |
| **外键表** | 引用驱动表的表，是关系的"多"方 | `target_table` | `order_item`（订单明细表） |
| **候选字段** | 参与关系发现的列 | `source_columns` / `target_columns` | `product_id` |

**关系方向：** 外键表 → 驱动表（例如：`order_item.product_id` → `dim_product.product_id`）

### 1.2 优化目标

**问题：** 当前实现中，外键表的索引列和同名列没有得到应有的优先级

**目标：** 优化外键表的候选字段筛选规则，提升关系发现的召回率和准确性

**原则：**
1. ✅ **驱动表规则保持不变**（严格筛选，只有 PK/UK/逻辑键才能成为候选）
2. ✅ **外键表规则优化**（智能筛选，利用索引和同名信号）
3. ✅ **配置驱动**（减少硬编码，提高灵活性）

---

## 2. 当前实现分析

### 2.1 驱动表的候选字段规则（保持不变）

**准入条件（二选一）：**
```
1. 物理约束：PK（主键）或 UK（唯一约束）
2. 逻辑主键：单列逻辑主键且置信度 >= 0.8
3. ❌ 索引：不作为准入条件
```

**语义角色过滤：**
- 🟢 **完全不过滤**
- 理由：物理约束是 DBA 的明确意图，必须尊重；逻辑主键在元数据生成阶段已过滤

**设计理念：** 严格筛选，只从"确定的关键列"出发寻找关系

### 2.2 外键表的候选字段规则（当前实现）

**当前优先级：**
```
优先级1：物理约束（PK/UK）
├─ 判断条件：is_primary_key OR is_unique OR is_unique_constraint
├─ 过滤规则：🟢 完全不过滤语义角色
└─ 结果：直接通过

优先级2：Complex 类型（硬编码）
├─ 判断条件：semantic_role == "complex"
├─ 过滤规则：🔴 永远过滤（即使同名也过滤）
└─ 结果：continue（跳过）

优先级3：同名列
├─ 判断条件：源列名 == 外键表列名（不区分大小写）
├─ 过滤规则：🟢 不过滤其他语义角色
└─ 结果：直接通过

优先级4：其他列
├─ 判断条件：不满足以上任何条件
├─ 过滤规则：🔴 按 exclude_semantic_roles 配置过滤
└─ 结果：如果 role in exclude_semantic_roles，则 continue（跳过）
```

**存在的问题：**

| 问题 | 当前行为 | 影响 |
|------|---------|------|
| **索引列无特权** | 索引列如果不同名会走优先级4被过滤 | 可能错过有索引优化的关联列 |
| **同名优先级低** | 同名列的优先级低于 Complex 检查 | 同名 + Complex 的列会被误杀 |
| **硬编码 Complex** | Complex 检查硬编码在代码中 | 违反"配置驱动"原则，缺乏灵活性 |

**示例场景：**

| 场景 | 当前处理 | 问题 |
|------|---------|------|
| 驱动表 `order_id` (PK) → 外键表 `order_id` (indexed) | ✅ 保留（优先级1或3） | 正常 |
| 驱动表 `order_id` (PK) → 外键表 `order_id` (complex) | ❌ **被过滤**（优先级2） | **误杀！同名应该优先** |
| 驱动表 `product_id` (PK) → 外键表 `prod_id` (indexed, role=audit) | ❌ **被过滤**（优先级4） | **误杀！索引应该有特权** |

---

## 3. 优化设计方案

### 3.1 新的优先级架构

```
优先级1：物理约束（PK/UK/索引）
├─ 判断条件：is_primary_key OR is_unique OR is_unique_constraint OR is_indexed
├─ 过滤规则：🟢 完全不过滤语义角色
└─ 结果：直接通过

优先级2：同名列
├─ 判断条件：源列名 == 外键表列名（不区分大小写）
├─ 过滤规则：🟢 不过滤任何语义角色（包括 complex）
└─ 结果：直接通过

优先级3：按配置过滤
├─ 判断条件：不满足优先级1和2
├─ 过滤规则：🔴 按 exclude_semantic_roles 配置过滤（包括 complex）
└─ 结果：如果 role in exclude_semantic_roles，则 continue（跳过）
```

### 3.2 关键变化

#### 变化 1：索引列提升到优先级1

**设计理由：**
- 索引通常是为了优化关联查询而创建的
- 外键表的索引列暗示"这个列经常被用于关联"
- 索引列应该被视为"关联的候选列"，享有与 PK/UK 同等的特权
- 索引的优先级与物理约束相同，因为它是针对关联优化的明确信号

**影响场景：**

| 场景 | 修改前 | 修改后 |
|------|--------|--------|
| 索引列 + 同名 | ✅ 保留（优先级3） | ✅ 保留（优先级1） |
| 索引列 + 不同名 + role=audit | ❌ **被过滤** | ✅ **保留** ⬆️ |
| 索引列 + 不同名 + role=identifier | ✅ 保留 | ✅ 保留（优先级提升） |

#### 变化 2：同名列提升到优先级2

**设计理由：**
- 驱动表的候选字段都是 PK/UK/逻辑主键（高质量的关键列）
- 如果外键表有**同名**字段 → **极强的关联信号**
- 同名 + 驱动表是主键 = **几乎确定的关联意图**
- 同名的优先级应该高于任何语义角色检查

**影响场景：**

| 场景 | 修改前 | 修改后 |
|------|--------|--------|
| 同名 + Complex 类型 | ❌ **被过滤** | ✅ **保留** ⬆️ |
| 同名 + audit 角色 | ✅ 保留 | ✅ 保留（优先级提升） |
| 不同名 + Complex 类型 | ❌ 被过滤 | ❌ 被过滤（由配置控制） |

#### 变化 3：删除硬编码的 Complex 检查

**设计理由：**
- `complex` 已经在配置文件的 `exclude_semantic_roles` 中定义
- 硬编码违反"配置驱动"的设计原则
- 统一由配置控制，提高灵活性
- 用户可以通过配置决定是否过滤 complex

**配置位置：** `configs/metadata_config.yaml`
```yaml
single_column:
  exclude_semantic_roles:
    - audit
    - metric
    - description
    - complex      # ← 统一由配置控制
```

### 3.3 优化效果对比

#### 场景 1：同名 + Complex 类型

**示例：** 驱动表 `orders.order_id` (PK) → 外键表 `order_items.order_id` (jsonb)

```
修改前：
├─ 检查优先级1：不是物理约束 → 继续
├─ 检查优先级2：是 complex 类型 → ❌ 被过滤（硬编码）
└─ 结果：错过关系

修改后：
├─ 检查优先级1：不是物理约束 → 继续
├─ 检查优先级2：是同名列 → ✅ 保留
└─ 结果：发现关系 ✅
```

#### 场景 2：索引列 + 不同名

**示例：** 驱动表 `products.product_id` (PK) → 外键表 `order_items.prod_id` (indexed, role=audit)

```
修改前：
├─ 检查优先级1：不是物理约束（PK/UK） → 继续
├─ 检查优先级2：不是 complex → 继续
├─ 检查优先级3：不同名 → 继续
├─ 检查优先级4：role=audit 在 exclude_semantic_roles 中 → ❌ 被过滤
└─ 结果：错过关系

修改后：
├─ 检查优先级1：是索引列 → ✅ 保留
└─ 结果：发现关系 ✅
```

#### 场景 3：配置灵活性

**如果用户想保留 complex 类型的列：**

```yaml
# 修改前：无法配置（硬编码）
# 修改后：在配置中删除 complex
single_column:
  exclude_semantic_roles:
    - audit
    - metric
    - description
    # - complex  # ← 注释掉即可
```

---

## 4. 代码修改清单

### 4.1 修改总览

| 文件 | 行号 | 类型 | 修改内容 |
|------|------|------|---------|
| `candidate_generator.py` | 861-865 | ✅ 新增 | 物理约束判断添加 `is_indexed` |
| `candidate_generator.py` | 867-905 | 🔄 重构 | 优先级逻辑重排序 + 删除硬编码 Complex |
| `llm_relationship_discovery.py` | 619-623 | ✅ 新增 | 物理约束判断添加 `is_indexed` |
| `llm_relationship_discovery.py` | 625-646 | 🔄 重构 | 优先级逻辑重排序 + 删除硬编码 Complex |

### 4.2 详细修改

#### 修改 1：`candidate_generator.py` - 物理约束判断

**位置：** 第861-865行

**修改前：**
```python
# 检查外键表列是否有物理约束（广义：PK/UK/索引）
# ⚠️ 注意：外键表物理约束包括索引（与驱动表不同）
target_has_physical = (
    target_structure_flags.get("is_primary_key") or          # ✅ PK
    target_structure_flags.get("is_unique") or               # ✅ UK
    target_structure_flags.get("is_unique_constraint")       # ✅ UK
    # ❌ 不检查 is_indexed
)
```

**修改后：**
```python
# 检查外键表列是否有物理约束或索引
# 注意：
# 1. 外键表的索引列享有"物理约束豁免"特权（与驱动表不同）
# 2. 理由：索引通常用于优化关联查询，是关联列的强信号
target_has_physical = (
    target_structure_flags.get("is_primary_key") or          # ✅ PK
    target_structure_flags.get("is_unique") or               # ✅ UK（统计唯一）
    target_structure_flags.get("is_unique_constraint") or    # ✅ UK（物理约束）
    target_structure_flags.get("is_indexed")                 # ✅ 索引（新增）
)
```

#### 修改 2：`candidate_generator.py` - 优先级逻辑

**位置：** 第867-905行

**修改前：**
```python
# 过滤优先级规则（从高到低）：
# 1. 物理约束外键表列：不过滤语义角色
# 2. 非物理约束外键表列中，Complex 类型列：永远过滤（即使同名）
# 3. 非物理约束外键表列中，同名列：不过滤其他语义角色
# 4. 其他外键表列：按 exclude_semantic_roles 配置过滤
if target_has_physical:
    logger.debug(
        "[single_column_candidate] 外键表列为物理约束（PK/UK），不过滤: %s.%s (role=%s, flags=%s)",
        f"{target_schema}.{target_table_name}", target_col_name, target_role,
        {k: v for k, v in target_structure_flags.items() if v}
    )
    # ✅ 优先级1: 物理约束不过滤，直接通过
    pass
elif target_role == "complex":
    logger.debug(
        "[single_column_candidate] 跳过 complex 类型外键表列: %s.%s (即使同名也过滤)",
        f"{target_schema}.{target_table_name}", target_col_name
    )
    # ✅ 优先级2: complex 类型永远过滤（优先级高于同名）
    continue
elif col_name.lower() == target_col_name.lower():
    logger.debug(
        "[single_column_candidate] 同名列不过滤: %s.%s (role=%s)",
        f"{target_schema}.{target_table_name}", target_col_name, target_role
    )
    # ✅ 优先级3: 同名列不过滤
    pass
else:
    # ✅ 优先级4: 其他语义角色按配置过滤
    if target_role in self.exclude_semantic_roles:
        logger.debug(
            "[single_column_candidate] 跳过外键表列 %s.%s，语义角色=%s 被排除",
            f"{target_schema}.{target_table_name}", target_col_name, target_role
        )
        continue
    logger.debug(
        "[single_column_candidate] 外键表列通过过滤: %s.%s (role=%s)",
        f"{target_schema}.{target_table_name}", target_col_name, target_role
    )
```

**修改后：**
```python
# 外键表候选字段过滤优先级（从高到低）：
# 1. 物理约束或索引：不过滤语义角色（强约束/强信号）
# 2. 同名列：不过滤语义角色（强关联信号）
# 3. 其他列：按 exclude_semantic_roles 配置过滤（包括 complex）
if target_has_physical:
    logger.debug(
        "[single_column_candidate] 优先级1: 外键表列为物理约束/索引，不过滤: %s.%s (role=%s, flags=%s)",
        f"{target_schema}.{target_table_name}", target_col_name, target_role,
        {k: v for k, v in target_structure_flags.items() if v}
    )
    # ✅ 优先级1: 物理约束/索引不过滤，直接通过
    pass
elif col_name.lower() == target_col_name.lower():
    logger.debug(
        "[single_column_candidate] 优先级2: 同名列不过滤: %s.%s (role=%s)",
        f"{target_schema}.{target_table_name}", target_col_name, target_role
    )
    # ✅ 优先级2: 同名列不过滤（包括 complex 类型）
    pass
else:
    # ✅ 优先级3: 其他语义角色按配置过滤
    if target_role in self.exclude_semantic_roles:
        logger.debug(
            "[single_column_candidate] 优先级3: 跳过外键表列 %s.%s，语义角色=%s 被配置排除",
            f"{target_schema}.{target_table_name}", target_col_name, target_role
        )
        continue
    logger.debug(
        "[single_column_candidate] 优先级3: 外键表列通过过滤: %s.%s (role=%s)",
        f"{target_schema}.{target_table_name}", target_col_name, target_role
    )
```

#### 修改 3：`llm_relationship_discovery.py` - 物理约束判断

**位置：** 第619-623行

**修改前：**
```python
# 优先级 1: 检查是否为物理约束列
structure_flags = col_profile.get("structure_flags", {})
is_physical = (
    structure_flags.get("is_primary_key") or
    structure_flags.get("is_unique") or
    structure_flags.get("is_unique_constraint")
)
```

**修改后：**
```python
# 优先级 1: 检查是否为物理约束或索引列
structure_flags = col_profile.get("structure_flags", {})
is_physical = (
    structure_flags.get("is_primary_key") or
    structure_flags.get("is_unique") or
    structure_flags.get("is_unique_constraint") or
    structure_flags.get("is_indexed")  # ✅ 新增
)
```

#### 修改 4：`llm_relationship_discovery.py` - 优先级逻辑

**位置：** 第625-646行

**修改前：**
```python
if is_physical:
    continue  # 物理约束列不过滤

# 获取语义角色
semantic_role = col_profile.get("semantic_analysis", {}).get("semantic_role")

# 优先级 2: Complex 永远过滤（即使同名）
if semantic_role == "complex":
    logger.debug(
        f"[filter_semantic_roles] 跳过候选（外键表列 {to_col} 为 complex，即使同名也过滤）: "
        f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
    )
    should_skip = True
    skipped_count += 1
    break

# 优先级 3: 同名列不过滤其他语义角色
if is_same_name:
    continue  # 同名列跳过语义角色检查

# 优先级 4: 其他列按配置过滤
if semantic_role in self.exclude_semantic_roles:
    logger.debug(
        f"[filter_semantic_roles] 跳过候选（外键表列 {to_col} 语义角色 {semantic_role} 被配置排除）: "
        f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
    )
    should_skip = True
    skipped_count += 1
    break
```

**修改后：**
```python
if is_physical:
    continue  # 优先级1: 物理约束/索引列不过滤

# 获取语义角色
semantic_role = col_profile.get("semantic_analysis", {}).get("semantic_role")

# 优先级 2: 同名列不过滤（包括 complex）
if is_same_name:
    continue  # 同名列跳过语义角色检查

# 优先级 3: 按配置过滤（包括 complex）
if semantic_role in self.exclude_semantic_roles:
    logger.debug(
        f"[filter_semantic_roles] 优先级3: 跳过候选（外键表列 {to_col} 语义角色 {semantic_role} 被配置排除）: "
        f"{candidate['from_table']['schema']}.{candidate['from_table']['table']} → {to_table_key}"
    )
    should_skip = True
    skipped_count += 1
    break
```

---

## 5. 测试验证

### 5.1 测试策略

**测试范围：**
- ✅ `--step rel`：单列候选生成
- ✅ `--step rel_llm`：LLM 辅助关系发现

**测试重点：**
1. 索引列是否正确享有优先级1特权
2. 同名列是否正确享有优先级2特权
3. Complex 类型是否由配置正确控制

### 5.2 测试用例

#### 测试用例 1：索引列 + 不同名 + audit 角色

**场景：**
- 驱动表：`products.product_id` (PK)
- 外键表：`order_items.prod_id` (indexed, role=audit)

**预期结果：**
- 修改前：❌ 被过滤（优先级4）
- 修改后：✅ 保留（优先级1）

**验证命令：**
```bash
python -m metaweave.cli.main metadata \
  --config configs/metadata_config.yaml \
  --step rel \
  --schemas public
```

**验证点：**
- 检查 `output/rel/relationships_global.json` 是否包含该关系
- 检查日志中是否有"优先级1: 外键表列为物理约束/索引"

#### 测试用例 2：同名列 + Complex 类型

**场景：**
- 驱动表：`orders.order_id` (PK)
- 外键表：`order_items.order_id` (jsonb, role=complex)

**预期结果：**
- 修改前：❌ 被过滤（优先级2硬编码）
- 修改后：✅ 保留（优先级2同名）

**验证命令：**
```bash
python -m metaweave.cli.main metadata \
  --config configs/metadata_config.yaml \
  --step rel \
  --schemas public
```

**验证点：**
- 检查 `output/rel/relationships_global.json` 是否包含该关系
- 检查日志中是否有"优先级2: 同名列不过滤"

#### 测试用例 3：配置灵活性

**场景：** 从配置中删除 `complex`

**配置修改：**
```yaml
single_column:
  exclude_semantic_roles:
    - audit
    - metric
    - description
    # - complex  # ← 注释掉
```

**预期结果：**
- Complex 类型的列（不同名）应该被保留

**验证点：**
- 修改前（硬编码）：complex 列永远被过滤
- 修改后（配置驱动）：complex 列可以通过配置控制

### 5.3 回归测试

**确保不影响现有功能：**
1. ✅ 驱动表的候选字段筛选不变
2. ✅ 物理约束（PK/UK）的处理不变
3. ✅ 名称相似度计算不变
4. ✅ 评分和决策逻辑不变

---

## 6. 影响分析

### 6.1 正面影响

| 影响 | 说明 |
|------|------|
| ✅ **召回率提升** | 索引列和同名列不会被误杀，发现更多有效关系 |
| ✅ **准确性提升** | 利用索引和同名的强信号，减少假阳性 |
| ✅ **架构优化** | 删除硬编码，配置驱动，代码更清晰 |
| ✅ **灵活性提升** | 用户可以通过配置控制所有语义角色过滤 |

### 6.2 潜在风险

| 风险 | 缓解措施 |
|------|---------|
| ⚠️ **关系数量增加** | 通过评分和决策引擎过滤低质量关系 |
| ⚠️ **索引误导** | 只在外键表使用索引特权，驱动表不受影响 |
| ⚠️ **同名误导** | 通过类型兼容性和名称相似度进一步验证 |

### 6.3 不影响的部分

| 部分 | 说明 |
|------|------|
| ✅ **驱动表规则** | 完全不变，索引仍不作为驱动表准入条件 |
| ✅ **复合键候选** | 不涉及，本次只修改单列候选 |
| ✅ **评分逻辑** | 不涉及，候选生成后的评分和决策不变 |
| ✅ **JSON Schema** | 不涉及，不修改元数据结构 |

---

## 7. 配置说明

### 7.1 相关配置

**配置文件：** `configs/metadata_config.yaml`

```yaml
# 单列候选配置
single_column:
  # 驱动表的重要约束（准入条件）
  important_constraints:
    - single_field_primary_key
    - single_field_unique_constraint
    # 注意：不包含 single_field_index（驱动表不使用索引作为准入条件）
  
  # 外键表的语义角色过滤（优先级3）
  exclude_semantic_roles:
    - audit         # 审计字段
    - metric        # 度量字段
    - description   # 描述字段
    - complex       # 复杂类型字段（json/jsonb/array/bytea等）
  
  # 逻辑主键最低置信度
  logical_key_min_confidence: 0.8
  
  # 类型兼容性阈值
  min_type_compatibility: 0.8
  
  # 名称相似度阈值
  name_similarity_important_target: 0.6  # 重要外键表列
  name_similarity_normal_target: 0.9     # 普通外键表列
```

### 7.2 配置灵活性

**如果想保留 complex 类型的列：**
```yaml
exclude_semantic_roles:
  - audit
  - metric
  - description
  # - complex  # ← 注释掉即可
```

**如果想排除更多语义角色：**
```yaml
exclude_semantic_roles:
  - audit
  - metric
  - description
  - complex
  - attribute  # ← 新增
  - flag       # ← 新增
```

---

## 8. 升级路径

### 8.1 升级步骤

**本次优化无需重新生成 JSON 文件，只需重新执行关系发现：**

```bash
# 步骤 1: 代码更新
git pull origin main

# 步骤 2: 重新执行关系发现
python -m metaweave.cli.main metadata \
  --config configs/metadata_config.yaml \
  --step rel \
  --schemas <your_schemas>

# 步骤 3: 对比结果
# 比较 output/rel/relationships_global.json 的变化
```

### 8.2 兼容性

**向后兼容：**
- ✅ 不涉及 Schema 变更
- ✅ 不影响已生成的 JSON 文件
- ✅ 只需重新运行 `--step rel`

**断崖式变更：**
- ❌ 无

---

## 9. 总结

### 9.1 核心改进

| 改进点 | 说明 |
|--------|------|
| 🎯 **索引特权提升** | 外键表的索引列提升到优先级1，与 PK/UK 同级 |
| 🎯 **同名优先提升** | 同名列提升到优先级2，高于所有语义角色检查 |
| 🎯 **架构简化** | 删除硬编码的 Complex 检查，统一配置驱动 |
| 🎯 **优先级简化** | 从4级简化到3级，逻辑更清晰 |

### 9.2 设计理念

```
驱动表（严格）：只从"确定的关键列"出发
                ├─ PK/UK
                ├─ 逻辑主键
                └─ ❌ 索引不参与

外键表（智能）：利用强信号，配置控制弱信号
                ├─ 优先级1: 物理约束/索引（强约束/强信号）
                ├─ 优先级2: 同名列（强关联信号）
                └─ 优先级3: 配置过滤（灵活控制）
```

### 9.3 预期效果

- ✅ 召回率提升：不会错过有索引的关联列和同名的关联列
- ✅ 准确性提升：利用索引和同名的强信号
- ✅ 架构优化：配置驱动，代码简洁
- ✅ 灵活性提升：用户可以自定义过滤规则
