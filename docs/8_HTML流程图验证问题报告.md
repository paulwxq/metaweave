# HTML 流程图验证问题报告

## 文档基本信息
- 被验证文档：`docs/8_semantic_role_计算流程详解.html`
- 验证时间：2025-12-30
- 验证对象：文档中描述的流程图与实际代码 `metaweave/core/metadata/profiler.py` 的一致性

## 验证结果概览

✅ **整体结构正确**：HTML文档的整体框架和主要流程都正确
❌ **发现多处细节错误**：在代码引用、流程图细节、配置参数等方面存在不符

---

## 发现的问题列表

### 问题 1：audit 检测流程图中的 `_determine_audit_type` 返回值不准确

**位置**：第 3.1 节 audit 判定流程图（第 441-471 行）

**问题描述**：
流程图中显示 `_determine_audit_type` 返回"audit 类型"，但实际代码中该方法返回的是 **`(audit_type, description)`** 元组，包含类型和描述两个值。

**实际代码**（profiler.py 第 641、1195 行）：
```python
audit_type, description = self._determine_audit_type(lower_name, column.data_type)
# ...
def _determine_audit_type(self, column_name: str, data_type: str) -> Tuple[str, str]:
    """判断审计字段的类型和用途"""
```

**建议修正**：
流程图中应明确显示返回 `(类型, 描述)` 元组。

---

### 问题 2：audit 代码示例行号不准确

**位置**：第 488-500 行的代码示例

**问题描述**：
文档中标注"代码位置：profiler.py: 第638-652行"，但实际代码在第 **637-652 行**（audit 检测从第 637 行开始）。

**实际代码位置**：
```python
# profiler.py: 第637-652行（不是638）
# audit detection - 最高优先级
audit_pattern = self._match_pattern(self._compiled_audit_patterns, lower_name)
if audit_pattern:
    # ...
```

**建议修正**：
将行号改为 637-652。

---

### 问题 3：audit 代码示例内容不完整

**位置**：第 488-500 行的代码示例

**问题描述**：
代码示例简化了实际逻辑，遗漏了关键细节：
1. 实际代码使用 `self._match_pattern(self._compiled_audit_patterns, lower_name)` 而不是直接遍历
2. 实际代码中 `audit_type, description` 是两个返回值，不只是 `audit_type`
3. 代码示例中的 `AuditInfo` 构造参数不完整

**实际代码**（profiler.py 第 637-652 行）：
```python
audit_pattern = self._match_pattern(self._compiled_audit_patterns, lower_name)
if audit_pattern:
    inference_basis.append(f"audit_pattern:{audit_pattern.pattern}")
    audit_type, description = self._determine_audit_type(lower_name, column.data_type)
    return (
        "audit",
        0.95,
        None,  # identifier_info
        None,  # metric_info
        None,  # datetime_info
        None,  # enum_info
        AuditInfo(audit_type=audit_type, description=description),
        None,  # description_info
        inference_basis,
    )
```

**建议修正**：
更新代码示例以反映真实实现。

---

### 问题 4：datetime 检测流程图逻辑过于简化

**位置**：第 3.2 节 datetime 判定流程图（第 536-556 行）

**问题描述**：
流程图显示"类型匹配"和"命名匹配"是两个独立分支，但实际代码是 **OR 逻辑合并判断**：

**实际代码**（profiler.py 第 654-669 行）：
```python
# datetime detection
if column.data_type.lower() in self.config.datetime_types or self._matches_datetime_name(lower_name):
    inference_basis.append("datetime_type_match" if column.data_type.lower() in self.config.datetime_types else "datetime_name_match")
    confidence = 1.0 if column.data_type.lower() in self.config.datetime_types else 0.85
    # ...
    return ("datetime", confidence, ...)
```

这是一个 **if 条件**，不是两个独立的分支路径。

**建议修正**：
流程图应改为：
1. 检查"类型匹配 OR 命名匹配"
2. 如果满足任一，推断时间粒度
3. 返回 datetime（置信度根据匹配方式决定）

---

### 问题 5：datetime 代码示例行号错误

**位置**：第 572-583 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第654-669行"是正确的，但代码示例内容不完整。

**实际代码**（profiler.py 第 654-669 行）：
```python
# datetime detection
if column.data_type.lower() in self.config.datetime_types or self._matches_datetime_name(lower_name):
    inference_basis.append("datetime_type_match" if column.data_type.lower() in self.config.datetime_types else "datetime_name_match")
    confidence = 1.0 if column.data_type.lower() in self.config.datetime_types else 0.85
    grain = self._infer_datetime_grain(lower_name)
    return (
        "datetime",
        confidence,
        None,
        None,
        DateTimeInfo(datetime_type=column.data_type.lower(), datetime_grain=grain),
        None,
        None,
        None,
        inference_basis,
    )
```

**建议修正**：
完整展示代码逻辑，包括 `grain` 推断和完整的返回元组。

---

### 问题 6：complex 检测代码示例行号错误

**位置**：第 652-665 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第671-692行"，但实际代码在第 **671-692 行**，代码示例与实际不完全一致。

**实际代码**（profiler.py 第 671-692 行）：
```python
# ========== complex detection ==========
# 在 datetime 之后、identifier 之前插入
data_type_lower = column.data_type.lower()
# 检查1: 直接匹配 complex_types 配置
# 检查2: 特殊处理数组类型
is_complex = (
    data_type_lower in self.config.complex_types or
    ("array" in self.config.complex_types and data_type_lower.endswith("[]"))
)
if is_complex:
    inference_basis.append(f"complex_type:{data_type_lower}")
    return (
        "complex",                 # semantic_role
        0.95,                      # confidence
        None,                      # identifier_info
        None,                      # metric_info
        None,                      # datetime_info
        None,                      # enum_info
        None,                      # audit_info
        None,                      # description_info
        inference_basis,           # List[str]
    )
```

**建议修正**：
代码示例应与实际代码完全一致，包括完整的返回元组和注释。

---

### 问题 7：identifier 流程图中缺少"指标词拦截"逻辑

**位置**：第 3.4 节 identifier 判定流程图（第 706-745 行）

**问题描述**：
文档在第 747-749 行提到了"指标词拦截"机制，但在流程图中**没有画出这个逻辑分支**。

**实际情况**：
根据 `docs/7_identifier_high_uniqueness_指标词拦截_简版方案.md`，这是一个**已知未实现**的功能：
- 配置项 `sampling.identifier_detection.high_uniqueness_block_keywords` 未被读取
- 代码中没有实现拦截逻辑

**问题分析**：
1. 如果这个功能未实现，文档不应在警告框中说"应增加"，而应明确说"尚未实现"
2. 流程图不应包含未实现的逻辑

**建议修正**：
1. 在流程图中不画这个分支（因为未实现）
2. 在警告框中明确说明"这是一个已知问题，尚未实现"
3. 或者，实现这个功能后再更新文档

---

### 问题 8：identifier 代码示例行号严重错误

**位置**：第 792-820 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第1006-1058行"，但实际：
1. `_is_identifier` 方法从第 **1006 行**开始
2. 方法结束在第 **1064 行**（不是 1058）

**实际代码**（profiler.py 第 1006-1064 行）：
```python
def _is_identifier(
    self,
    column: ColumnInfo,
    stats: Optional[Dict],
    struct_flags: StructureFlags,
) -> Tuple[bool, float, Optional[str], List[str]]:
    """综合判断是否为 identifier
    
    按优先级依次检查：
    0. 命名排除规则（name/desc 等描述性字段）
    1. 数据类型白名单（前置过滤）
    2. 物理约束（PK/FK/UNIQUE）
    3. 统计特征（唯一性>high_uniqueness_threshold + 非空率>min_non_null_rate）
    4. 命名特征（关键词 + 唯一性>low_uniqueness_threshold）
    
    返回: (是否identifier, 置信度, 匹配的模式/关键词, 推断依据列表)
    """
    # ... (代码省略)
    return (False, 0.0, None, [])
```

**建议修正**：
将行号改为 1006-1064。

---

### 问题 9：identifier 示例中 "应被指标词拦截" 的说法不准确

**位置**：第 861-869 行的示例

**问题描述**：
示例中说：
```
❌ amount (integer, 唯一性 0.99)   → 应被指标词拦截，判为 metric
```

但根据代码和相关文档（`7_identifier_high_uniqueness_指标词拦截_简版方案.md`），这个功能**尚未实现**。

**实际情况**：
当前代码中，`amount (integer, 唯一性 0.99)` 如果没有物理约束，**会被判为 identifier**，不会被拦截。

**建议修正**：
将示例改为：
```
❌ amount (integer, 唯一性 0.99)   → 当前会被误判为 identifier（已知问题，待修复）
```

---

### 问题 10：description 检测流程图中遗漏"排除索引字段"检查

**位置**：第 3.5 节 description 判定流程图（第 877-919 行）

**问题描述**：
流程图中显示"排除规则1：有物理约束→False"和"排除规则2：被索引→False"是分开的，但实际代码是**合并检查**。

**实际代码**（profiler.py 第 1082-1089 行）：
```python
# 1. 排除：有物理约束或被索引的字段
if (struct_flags.is_primary_key or
    struct_flags.is_composite_primary_key_member or
    struct_flags.is_foreign_key or
    struct_flags.is_composite_foreign_key_member or
    struct_flags.is_indexed or
    struct_flags.is_composite_indexed_member):
    return (False, "")
```

这是一个 **if 条件**，不是两个独立的排除规则。

**建议修正**：
流程图应改为一个检查节点："检查约束和索引（有PK/FK/UK/索引）→ 返回False"。

---

### 问题 11：description 代码示例行号错误

**位置**：第 940-980 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第1060-1142行"是正确的，但代码示例过于简化，遗漏了关键检查：

**实际代码**（profiler.py 第 1082-1089 行）：
```python
# 1. 排除：有物理约束或被索引的字段
if (struct_flags.is_primary_key or
    struct_flags.is_composite_primary_key_member or
    struct_flags.is_foreign_key or
    struct_flags.is_composite_foreign_key_member or
    struct_flags.is_indexed or
    struct_flags.is_composite_indexed_member):
    return (False, "")
```

文档示例简化成：
```python
if self._has_physical_constraint(struct_flags)[0]:
    return (False, "")
if struct_flags.is_indexed:
    return (False, "")
```

但实际代码中**没有调用 `_has_physical_constraint` 方法**，而是直接检查 `struct_flags` 的多个字段。

**建议修正**：
代码示例应反映真实实现，不要简化关键逻辑。

---

### 问题 12：enum 检测流程图中条件检查顺序不清晰

**位置**：第 3.6 节 enum 判定流程图（第 1064-1106 行）

**问题描述**：
流程图中显示条件按 Cond0 → Cond1 → Cond2 → ... 的顺序检查，但实际代码的检查顺序略有不同。

**实际代码**（profiler.py 第 792-870 行）：
```python
def _is_simple_two_value_enum(
    self,
    column: ColumnInfo,
    stats: Optional[Dict],
    struct_flags: StructureFlags,
) -> bool:
    if not stats:
        return False
    
    # 条件0: 命名排除规则
    lower_name = column.column_name.lower()
    exclude_keywords = ["name", "nm", "desc", "description", "remark", "comment", "details", "memo", "summary"]
    for keyword in exclude_keywords:
        if keyword in lower_name:
            return False
    
    # 条件1: 唯一值数量恰好为 2
    num_unique = int(stats.get("num_unique", 0))
    if num_unique != 2:
        return False
    
    # 条件2: 数据类型检查
    # ...
```

流程图中**遗漏了最开始的 `if not stats: return False` 检查**。

**建议修正**：
在流程图开始处增加"有统计数据？"检查节点。

---

### 问题 13：enum 代码示例行号错误

**位置**：第 1120-1165 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第792-864行"，但实际：
1. `_is_simple_two_value_enum` 方法从第 **792 行**开始
2. 方法结束在第 **870 行**（不是 864）

**实际代码行数**：
```python
# profiler.py 第792-870行
def _is_simple_two_value_enum(self, column, stats, struct_flags):
    # ... (78 行代码)
    return True
```

**建议修正**：
将行号改为 792-870。

---

### 问题 14：metric 检测流程图中遗漏"serial 类型"

**位置**：第 3.7 节 metric 判定流程图和代码示例（第 1203-1283 行）

**问题描述**：
文档中提到的数值类型列表不完整。

**实际代码**（profiler.py 第 755-766 行）：
```python
numeric_type = column.data_type.lower() in {
    "numeric",
    "decimal",
    "number",
    "int",
    "integer",
    "bigint",
    "smallint",
    "double precision",
    "real",
    "float",
}
```

但文档第 1264-1267 行的代码示例中写的是：
```python
numeric_types = {
    "integer", "int", "bigint", "smallint", "numeric", "decimal", "float", "real",
    "double precision", "money", "serial", "bigserial", "smallserial"
}
```

两者不一致！实际代码中**没有包含** `money`, `serial`, `bigserial`, `smallserial`。

**建议修正**：
代码示例应与实际代码一致，或者说明这是文档错误。

---

### 问题 15：metric 代码示例行号错误

**位置**：第 1260-1282 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第754-786行"，实际代码在第 **754-786 行**是正确的，但代码内容不匹配。

**实际代码**（profiler.py 第 754-786 行）：
```python
# metric detection
numeric_type = column.data_type.lower() in {
    "numeric",
    "decimal",
    "number",
    "int",
    "integer",
    "bigint",
    "smallint",
    "double precision",
    "real",
    "float",
}
metric_pattern = self._match_pattern(self._compiled_metric_patterns, lower_name)
if numeric_type:
    inference_basis.append("numeric_type")
if metric_pattern:
    inference_basis.append(f"metric_pattern:{metric_pattern.pattern}")
if numeric_type or metric_pattern:
    confidence = 0.95 if numeric_type and metric_pattern else (0.7 if numeric_type else 0.6)
    category = self._determine_metric_category(lower_name)
    aggregations = self._suggest_metric_aggregations(category)
    return (
        "metric",
        confidence,
        None,
        MetricInfo(metric_category=category, suggested_aggregations=aggregations),
        None,
        None,
        None,
        None,
        inference_basis,
    )
```

文档中的代码示例简化过度，遗漏了关键细节。

**建议修正**：
使用完整的实际代码。

---

### 问题 16：metric 类别判定代码行号错误

**位置**：第 1303-1321 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第1179-1186行"，但实际：
1. `_determine_metric_category` 在第 **1179-1186 行**（正确）
2. `_suggest_metric_aggregations` 在第 **1188-1193 行**（不是示例中标注的位置）

**实际代码**：
```python
# profiler.py: 第1179-1186行
def _determine_metric_category(self, column_name: str) -> str:
    if re.search(r"(amount|price|cost|revenue|sales|profit)", column_name):
        return "amount"
    if re.search(r"(count|qty|quantity|num|number)", column_name):
        return "count"
    if re.search(r"(rate|ratio|percent|percentage)", column_name):
        return "ratio"
    return "metric"

# profiler.py: 第1188-1193行
def _suggest_metric_aggregations(self, category: str) -> List[str]:
    if category == "count":
        return ["SUM"]
    if category == "ratio":
        return ["AVG"]
    return ["SUM", "AVG", "MIN", "MAX"]
```

**建议修正**：
分别标注两个方法的准确行号。

---

### 问题 17：attribute 代码示例行号错误

**位置**：第 1364-1369 行的代码示例

**问题描述**：
文档标注"代码位置：profiler.py: 第788-790行"，但实际代码在第 **788-790 行**：

**实际代码**（profiler.py 第 788-790 行）：
```python
# default attribute
inference_basis.append("fallback_attribute")
return ("attribute", 0.7, None, None, None, None, None, None, inference_basis)
```

代码示例中的注释不准确（应该是 `fallback_attribute` 而不是 `default_attribute`）。

**建议修正**：
代码示例应与实际代码一致。

---

### 问题 18：配置文件示例中包含未实现的配置项

**位置**：第 1739-1822 行的配置文件完整示例

**问题描述**：
示例中包含了：
```yaml
high_uniqueness_block_keywords:
  - amount
  - count
  - total
  - cost
  - price
```

但根据实际代码和 `7_identifier_high_uniqueness_指标词拦截_简版方案.md`，这个配置项**尚未被读取和使用**。

**建议修正**：
1. 删除这个配置项
2. 或者明确标注"（待实现）"

---

## 总体建议

### 1. 代码行号准确性
建议使用脚本自动提取代码行号，避免手工标注错误。

### 2. 代码示例完整性
不要过度简化代码示例，关键逻辑应完整展示。

### 3. 流程图与代码对应
流程图应严格反映实际代码逻辑，不要添加未实现的功能。

### 4. 未实现功能的标注
对于文档中提到的未实现功能（如"指标词拦截"），应明确标注"已知问题，尚未实现"。

### 5. 配置示例的准确性
配置文件示例应只包含已实现的配置项，或明确标注未实现的部分。

---

## 验证方法

本次验证通过以下步骤：
1. 阅读 HTML 文档中的所有流程图和代码示例
2. 对照实际代码 `metaweave/core/metadata/profiler.py` 逐一核对
3. 参考相关设计文档（`7_identifier_high_uniqueness_指标词拦截_简版方案.md`）
4. 记录所有不一致之处

---

## 结论

HTML 文档的整体框架和思路是正确的，但在细节上存在较多不准确之处，主要集中在：
1. **代码行号标注错误**（多处）
2. **代码示例简化过度**，遗漏关键逻辑
3. **流程图与实际代码逻辑不完全一致**
4. **包含未实现功能的描述**，但未明确标注

建议对文档进行全面修订，确保与实际代码完全一致。

