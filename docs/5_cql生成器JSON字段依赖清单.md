# CQL 生成器 JSON 字段依赖清单

## 文档说明

本文档详细列出 `--step cql` 和 `--step cql_llm` 在生成 Neo4j CQL 脚本时，需要访问的 JSON 文件字段和属性。

**适用步骤：**
- `metaweave metadata --config configs/metadata_config.yaml --step cql`
- `metaweave metadata --config configs/metadata_config.yaml --step cql_llm`

**数据来源：**
- **表/列画像 JSON**：`output/json/*.json`（来自 `--step json` 或 `--step json_llm`）
- **关系 JSON**：`output/rel/relationships_*.json`（来自 `--step rel` 或 `--step rel_llm`）

---

## 一、表/列画像 JSON 字段依赖

### 1. 顶层结构

```json
{
  "metadata_version": "3.2",
  "generated_at": "...",
  "table_info": { ... },
  "column_profiles": { ... },
  "table_profile": { ... },
  "sample_records": { ... }
}
```

**访问情况：**

| 字段 | 是否访问 | 用途 | 备注 |
|-----|---------|------|------|
| `metadata_version` | ❌ 否 | - | 未使用 |
| `generated_at` | ❌ 否 | - | 未使用 |
| `llm_enhanced_at` | ❌ 否 | - | 未使用 |
| `table_info` | ✅ 是 | 提取表基本信息 | **必需** |
| `column_profiles` | ✅ 是 | 提取列信息 | **必需** |
| `table_profile` | ✅ 是 | 提取约束、分类等 | **必需** |
| `sample_records` | ❌ 否 | - | 未使用 |

---

### 2. `table_info` 节点

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 144-151 行

```python
table_info = data.get("table_info", {})
schema = table_info.get("schema_name", "")
name = table_info.get("table_name", "")
comment = table_info.get("comment")
```

**字段依赖清单：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 |
|---------|---------|---------|------|----------------|
| `table_info.schema_name` | `string` | ✅ 必需 | Schema 名称 | `Table.schema` |
| `table_info.table_name` | `string` | ✅ 必需 | 表名 | `Table.name` |
| `table_info.comment` | `string` | ⭕ 可选 | 表注释 | `Table.comment` |

**示例：**

```json
{
  "table_info": {
    "schema_name": "public",
    "table_name": "employee",
    "comment": "员工表"
  }
}
```

---

### 3. `column_profiles` 节点

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 256-308 行

```python
column_profiles = data.get("column_profiles", {})
for col_name, col_data in column_profiles.items():
    data_type = col_data.get("data_type", "")
    comment = col_data.get("comment")
    semantic_analysis = col_data.get("semantic_analysis", {})
    semantic_role = semantic_analysis.get("semantic_role")
    structure_flags = col_data.get("structure_flags", {})
    statistics = col_data.get("statistics", {})
    uniqueness = statistics.get("uniqueness", 0.0)
    null_rate = statistics.get("null_rate", 0.0)
```

**字段依赖清单：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 |
|---------|---------|---------|------|----------------|
| `column_profiles.<column_name>` | `object` | ✅ 必需 | 列名（作为 key） | `Column.name` |
| `column_profiles.<column_name>.data_type` | `string` | ✅ 必需 | 数据类型 | `Column.data_type` |
| `column_profiles.<column_name>.comment` | `string` | ⭕ 可选 | 列注释 | `Column.comment` |
| `column_profiles.<column_name>.semantic_analysis` | `object` | ⭕ 可选 | 语义分析结果 | - |
| `column_profiles.<column_name>.semantic_analysis.semantic_role` | `string` | ⭕ 可选 | 语义角色 | `Column.semantic_role` |
| `column_profiles.<column_name>.structure_flags` | `object` | ⭕ 可选 | 结构标志 | - |
| `column_profiles.<column_name>.statistics` | `object` | ⭕ 可选 | 统计信息 | - |
| `column_profiles.<column_name>.statistics.uniqueness` | `float` | ⭕ 可选 | 唯一度 | `Column.uniqueness` |
| `column_profiles.<column_name>.statistics.null_rate` | `float` | ⭕ 可选 | 空值率 | `Column.null_rate` |

**语义角色特殊处理：**

| `semantic_role` 值 | Neo4j 标志位 | 说明 |
|-------------------|-------------|------|
| `"datetime"` | `Column.is_time = true` | 时间字段 |
| `"metric"` | `Column.is_measure = true` | 度量字段 |
| 其他 | 仅存储原值 | - |

**示例：**

```json
{
  "column_profiles": {
    "employee_id": {
      "data_type": "integer",
      "comment": "员工ID",
      "semantic_analysis": {
        "semantic_role": "identifier"
      },
      "structure_flags": {},
      "statistics": {
        "uniqueness": 1.0,
        "null_rate": 0.0
      }
    }
  }
}
```

---

### 4. `table_profile.physical_constraints` 节点

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 154-189 行

#### 4.1 主键 (Primary Key)

```python
pk_data = physical_constraints.get("primary_key")
if pk_data and isinstance(pk_data, dict):
    pk = pk_data.get("columns", [])
elif pk_data and isinstance(pk_data, list):
    pk = pk_data
else:
    pk = []
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 |
|---------|---------|---------|------|----------------|
| `table_profile.physical_constraints.primary_key` | `dict` 或 `list` | ⭕ 可选 | 物理主键 | `Table.pk` |
| `table_profile.physical_constraints.primary_key.columns` | `list<string>` | ⭕ 可选 | 主键列列表（dict 格式） | `Table.pk` |
| `table_profile.physical_constraints.primary_key.constraint_name` | `string` | ❌ 否 | 约束名称 | 未使用 |

**格式兼容性：**

```json
// 格式 1：dict（推荐）
"primary_key": {
  "constraint_name": "employee_pkey",
  "columns": ["employee_id"]
}

// 格式 2：list（兼容）
"primary_key": ["employee_id"]

// 格式 3：null 或不存在（表示无主键）
"primary_key": null
```

#### 4.2 唯一约束 (Unique Constraints)

```python
uk = []
for uk_data in physical_constraints.get("unique_constraints", []):
    if isinstance(uk_data, dict):
        columns = uk_data.get("columns", [])
        if columns:
            uk.append(columns)
    elif isinstance(uk_data, list):
        if uk_data:
            uk.append(uk_data)
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 |
|---------|---------|---------|------|----------------|
| `table_profile.physical_constraints.unique_constraints` | `list<dict>` 或 `list<list>` | ⭕ 可选 | 唯一约束列表 | `Table.uk` |
| `table_profile.physical_constraints.unique_constraints[].columns` | `list<string>` | ⭕ 可选 | 约束列列表（dict 格式） | `Table.uk[i]` |
| `table_profile.physical_constraints.unique_constraints[].constraint_name` | `string` | ❌ 否 | 约束名称 | 未使用 |

**格式兼容性：**

```json
// 格式 1：list<dict>（推荐）
"unique_constraints": [
  {
    "constraint_name": "uk_email",
    "columns": ["email"]
  },
  {
    "constraint_name": "uk_phone",
    "columns": ["phone"]
  }
]

// 格式 2：list<list>（兼容）
"unique_constraints": [
  ["email"],
  ["phone"]
]

// 格式 3：空数组（表示无唯一约束）
"unique_constraints": []
```

#### 4.3 外键 (Foreign Keys)

```python
fk = []
for fk_data in physical_constraints.get("foreign_keys", []):
    source_columns = fk_data.get("source_columns", [])
    if source_columns:
        fk.append(source_columns)
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 |
|---------|---------|---------|------|----------------|
| `table_profile.physical_constraints.foreign_keys` | `list<dict>` | ⭕ 可选 | 外键约束列表 | `Table.fk` |
| `table_profile.physical_constraints.foreign_keys[].source_columns` | `list<string>` | ⭕ 可选 | 源列列表 | `Table.fk[i]` |
| `table_profile.physical_constraints.foreign_keys[].constraint_name` | `string` | ❌ 否 | 约束名称 | 未使用 |
| `table_profile.physical_constraints.foreign_keys[].target_schema` | `string` | ❌ 否 | 目标 schema | 未使用（从关系 JSON 读取） |
| `table_profile.physical_constraints.foreign_keys[].target_table` | `string` | ❌ 否 | 目标表名 | 未使用（从关系 JSON 读取） |
| `table_profile.physical_constraints.foreign_keys[].target_columns` | `list<string>` | ❌ 否 | 目标列列表 | 未使用（从关系 JSON 读取） |

**说明：**
- CQL 生成器只提取 `source_columns`（外键源列）
- 完整的外键关系信息（目标表、目标列等）从 `relationships_*.json` 读取

**示例：**

```json
{
  "foreign_keys": [
    {
      "constraint_name": "fk_company",
      "source_columns": ["company_id"],
      "target_schema": "public",
      "target_table": "dim_company",
      "target_columns": ["company_id"]
    }
  ]
}
```

#### 4.4 索引 (Indexes)

```python
indexes = []
for idx_data in physical_constraints.get("indexes", []):
    columns = idx_data.get("columns", [])
    if columns:
        indexes.append(columns)
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 |
|---------|---------|---------|------|----------------|
| `table_profile.physical_constraints.indexes` | `list<dict>` | ⭕ 可选 | 索引列表 | `Table.indexes` |
| `table_profile.physical_constraints.indexes[].columns` | `list<string>` | ⭕ 可选 | 索引列列表 | `Table.indexes[i]` |
| `table_profile.physical_constraints.indexes[].index_name` | `string` | ❌ 否 | 索引名称 | 未使用 |
| `table_profile.physical_constraints.indexes[].is_unique` | `boolean` | ❌ 否 | 是否唯一索引 | 未使用 |

**示例：**

```json
{
  "indexes": [
    {
      "index_name": "idx_hire_date",
      "columns": ["hire_date"],
      "is_unique": false
    },
    {
      "index_name": "idx_name_dept",
      "columns": ["name", "department_id"],
      "is_unique": false
    }
  ]
}
```

---

### 5. `table_profile.logical_keys` 节点

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 191-196 行

```python
logical_keys = table_profile.get("logical_keys", {})
logic_pk = []
for candidate in logical_keys.get("candidate_primary_keys", []):
    confidence = candidate.get("confidence_score", 0.0)
    if confidence >= 0.8:
        logic_pk.append(candidate.get("columns", []))
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 |
|---------|---------|---------|------|----------------|
| `table_profile.logical_keys` | `object` | ⭕ 可选 | 逻辑键信息 | - |
| `table_profile.logical_keys.candidate_primary_keys` | `list<dict>` | ⭕ 可选 | 候选逻辑主键列表 | `Table.logic_pk` |
| `table_profile.logical_keys.candidate_primary_keys[].columns` | `list<string>` | ⭕ 可选 | 逻辑主键列列表 | `Table.logic_pk[i]` |
| `table_profile.logical_keys.candidate_primary_keys[].confidence_score` | `float` | ⭕ 可选 | 置信度 | 用于过滤（≥ 0.8） |
| `table_profile.logical_keys.candidate_primary_keys[].uniqueness` | `float` | ❌ 否 | 唯一度 | 未使用 |
| `table_profile.logical_keys.candidate_primary_keys[].null_rate` | `float` | ❌ 否 | 空值率 | 未使用 |

**过滤规则：**
- 只保留 `confidence_score >= 0.8` 的候选逻辑主键
- 如果置信度字段缺失，默认为 `0.0`（会被过滤）

**示例：**

```json
{
  "logical_keys": {
    "candidate_primary_keys": [
      {
        "columns": ["employee_id"],
        "uniqueness": 1.0,
        "null_rate": 0.0,
        "confidence_score": 0.95
      },
      {
        "columns": ["name", "hire_date"],
        "uniqueness": 1.0,
        "null_rate": 0.0,
        "confidence_score": 0.75
      }
    ]
  }
}
```

**输出结果：**
- 只有第一个候选（`confidence_score = 0.95`）会被写入 `Table.logic_pk`
- 第二个候选（`confidence_score = 0.75`）会被过滤掉

---

### 6. `table_profile.table_domains` 节点

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 210 行

```python
table_domains=table_profile.get("table_domains", [])
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 | 参数依赖 |
|---------|---------|---------|------|----------------|---------|
| `table_profile.table_domains` | `list<string>` | ⭕ 可选 | 业务主题列表 | `Table.table_domains` | ❌ 无 |

**重要说明：**

- **CQL 生成器无 `--domain` 参数**
- 如果 JSON 中存在 `table_domains` 字段，会被读取并写入 Neo4j
- 如果 JSON 中不存在 `table_domains` 字段，默认为空数组 `[]`
- 是否包含 `table_domains` 取决于 JSON 生成时是否使用 `--domain` 参数：
  - `--step json`：不生成 `table_domains`
  - `--step json_llm --domain`：生成 `table_domains`

**Cypher 生成逻辑：**

```cypher
n.table_domains = CASE
    WHEN t.table_domains IS NOT NULL AND size(t.table_domains) > 0
        THEN t.table_domains
    ELSE coalesce(n.table_domains, [])
END
```

**示例：**

```json
{
  "table_profile": {
    "table_domains": ["销售管理", "订单管理"]
  }
}
```

---

### 7. `table_profile.table_category` 节点

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 211 行

```python
table_category=table_profile.get("table_category")
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 属性 | 参数依赖 |
|---------|---------|---------|------|----------------|---------|
| `table_profile.table_category` | `string` | ⭕ 可选 | 表类型分类 | `Table.table_category` | ❌ 无 |

**可能的值：**
- `"fact"`：事实表
- `"dim"`：维度表
- `"bridge"`：桥接表
- `"unknown"`：未知类型

**重要说明：**
- **CQL 生成器无特殊参数依赖**
- 如果 JSON 中存在 `table_category` 字段，会被读取并写入 Neo4j
- 如果不存在，则为 `null`
- `table_category` 通常由 `--step json_llm` 生成（无论是否使用 `--domain`）

**Cypher 生成逻辑：**

```cypher
n.table_category = CASE
    WHEN t.table_category IS NOT NULL
        THEN t.table_category
    ELSE n.table_category
END
```

**示例：**

```json
{
  "table_profile": {
    "table_category": "fact"
  }
}
```

---

## 二、关系 JSON 字段依赖

### 1. 文件查找

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 314-320 行

```python
rel_files = list(self.rel_dir.glob("relationships_*.json"))
```

**文件名模式：**
- `relationships_global.json`（全局关系，最常见）
- `relationships_*.json`（支持其他命名）

**数据来源：**
- `--step rel` 生成：`output/rel/relationships_global.json`
- `--step rel_llm` 生成：`output/rel/relationships_global.json`

---

### 2. 顶层结构

```json
{
  "metadata_version": "3.2",
  "generated_at": "...",
  "statistics": { ... },
  "relationships": [ ... ]
}
```

**访问情况：**

| 字段 | 是否访问 | 用途 | 备注 |
|-----|---------|------|------|
| `metadata_version` | ❌ 否 | - | 未使用 |
| `generated_at` | ❌ 否 | - | 未使用 |
| `statistics` | ❌ 否 | - | 未使用 |
| `relationships` | ✅ 是 | 提取表间关系 | **必需** |

---

### 3. `relationships` 数组元素

**代码位置：** `metaweave/core/cql_generator/reader.py` 第 341-412 行

#### 3.1 单列关系 (Single Column)

```json
{
  "type": "single_column",
  "from_table": {
    "schema": "public",
    "table": "employee"
  },
  "from_column": "company_id",
  "to_table": {
    "schema": "public",
    "table": "dim_company"
  },
  "to_column": "company_id",
  "cardinality": "N:1",
  "constraint_name": "fk_company"
}
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 关系 |
|---------|---------|---------|------|----------------|
| `type` | `string` | ✅ 必需 | 关系类型 | 用于区分单列/复合 |
| `from_table` | `object` | ✅ 必需 | 源表信息 | - |
| `from_table.schema` | `string` | ✅ 必需 | 源表 schema | `JOIN_ON` 起点 |
| `from_table.table` | `string` | ✅ 必需 | 源表名 | `JOIN_ON` 起点 |
| `from_column` | `string` | ✅ 必需 | 源列名 | `JOIN_ON.source_columns` |
| `to_table` | `object` | ✅ 必需 | 目标表信息 | - |
| `to_table.schema` | `string` | ✅ 必需 | 目标表 schema | `JOIN_ON` 终点 |
| `to_table.table` | `string` | ✅ 必需 | 目标表名 | `JOIN_ON` 终点 |
| `to_column` | `string` | ✅ 必需 | 目标列名 | `JOIN_ON.target_columns` |
| `cardinality` | `string` | ✅ 必需 | 基数关系 | `JOIN_ON.cardinality` |
| `constraint_name` | `string` | ⭕ 可选 | 约束名称 | `JOIN_ON.constraint_name` |

#### 3.2 复合列关系 (Composite)

```json
{
  "type": "composite",
  "from_table": {
    "schema": "public",
    "table": "sales"
  },
  "from_columns": ["product_id", "region_id"],
  "to_table": {
    "schema": "public",
    "table": "product_region"
  },
  "to_columns": ["product_id", "region_id"],
  "cardinality": "N:1",
  "constraint_name": null
}
```

**字段依赖：**

| 字段路径 | 数据类型 | 是否必需 | 用途 | 对应 Neo4j 关系 |
|---------|---------|---------|------|----------------|
| `type` | `string` | ✅ 必需 | 关系类型 | 用于区分单列/复合 |
| `from_table` | `object` | ✅ 必需 | 源表信息 | - |
| `from_table.schema` | `string` | ✅ 必需 | 源表 schema | `JOIN_ON` 起点 |
| `from_table.table` | `string` | ✅ 必需 | 源表名 | `JOIN_ON` 起点 |
| `from_columns` | `list<string>` | ✅ 必需 | 源列列表 | `JOIN_ON.source_columns` |
| `to_table` | `object` | ✅ 必需 | 目标表信息 | - |
| `to_table.schema` | `string` | ✅ 必需 | 目标表 schema | `JOIN_ON` 终点 |
| `to_table.table` | `string` | ✅ 必需 | 目标表名 | `JOIN_ON` 终点 |
| `to_columns` | `list<string>` | ✅ 必需 | 目标列列表 | `JOIN_ON.target_columns` |
| `cardinality` | `string` | ✅ 必需 | 基数关系 | `JOIN_ON.cardinality` |
| `constraint_name` | `string` | ⭕ 可选 | 约束名称 | `JOIN_ON.constraint_name` |

#### 3.3 基数关系 (Cardinality)

**可能的值：**

| `cardinality` | 含义 | CQL 生成器处理 |
|--------------|------|---------------|
| `"N:1"` | 多对一 | 不翻转，保持原向 |
| `"1:N"` | 一对多 | **翻转方向**，变为 `N:1` |
| `"1:1"` | 一对一 | 不翻转，保持原向 |
| `"M:N"` | 多对多 | 不翻转，保持原向 |

**翻转逻辑：**

```python
if raw_cardinality == "1:N":
    # 翻转：箭头从 N 侧指向 1 侧
    src_table = to_table
    dst_table = from_table
    source_columns = to_columns
    target_columns = from_columns
    cardinality = "N:1"
else:
    # 不翻转
    src_table = from_table
    dst_table = to_table
    source_columns = from_columns
    target_columns = to_columns
    cardinality = raw_cardinality
```

**设计原因：**
- Neo4j 中的 `JOIN_ON` 关系统一为"箭头指向 1 侧"（ER 语义）
- 例如：`(employee)-[:JOIN_ON]->(company)` 表示"多个员工属于一个公司"

---

## 三、字段依赖总结表

### 1. 必需字段（缺失会报错）

| 字段路径 | 用途 | 来源 |
|---------|------|------|
| `table_info.schema_name` | 表 schema | JSON |
| `table_info.table_name` | 表名 | JSON |
| `column_profiles.<column_name>` | 列名 | JSON |
| `column_profiles.<column_name>.data_type` | 列数据类型 | JSON |
| `relationships[].from_table.schema` | 源表 schema | 关系 JSON |
| `relationships[].from_table.table` | 源表名 | 关系 JSON |
| `relationships[].to_table.schema` | 目标表 schema | 关系 JSON |
| `relationships[].to_table.table` | 目标表名 | 关系 JSON |
| `relationships[].cardinality` | 基数关系 | 关系 JSON |

### 2. 可选字段（缺失使用默认值）

| 字段路径 | 默认值 | 用途 |
|---------|-------|------|
| `table_info.comment` | `null` | 表注释 |
| `column_profiles.<column_name>.comment` | `null` | 列注释 |
| `column_profiles.<column_name>.semantic_analysis.semantic_role` | `null` | 语义角色 |
| `column_profiles.<column_name>.statistics.uniqueness` | `0.0` | 唯一度 |
| `column_profiles.<column_name>.statistics.null_rate` | `0.0` | 空值率 |
| `table_profile.physical_constraints.primary_key` | `[]` | 物理主键 |
| `table_profile.physical_constraints.unique_constraints` | `[]` | 唯一约束 |
| `table_profile.physical_constraints.foreign_keys` | `[]` | 外键 |
| `table_profile.physical_constraints.indexes` | `[]` | 索引 |
| `table_profile.logical_keys.candidate_primary_keys` | `[]` | 逻辑主键 |
| `table_profile.table_domains` | `[]` | 业务主题 |
| `table_profile.table_category` | `null` | 表类型 |
| `relationships[].constraint_name` | `null` | 约束名称 |

### 3. 未使用字段（存在但不读取）

| 字段路径 | 说明 |
|---------|------|
| `metadata_version` | 版本信息 |
| `generated_at` | 生成时间 |
| `llm_enhanced_at` | LLM 增强时间 |
| `sample_records` | 样本数据 |
| `column_profiles.<column_name>.structure_flags` | 结构标志（读取但未使用） |
| `table_profile.physical_constraints.primary_key.constraint_name` | 主键约束名（提取列即可） |
| `table_profile.physical_constraints.unique_constraints[].constraint_name` | 唯一约束名 |
| `table_profile.physical_constraints.foreign_keys[].target_*` | 外键目标信息（从关系 JSON 读取） |
| `table_profile.physical_constraints.indexes[].index_name` | 索引名 |
| `table_profile.logical_keys.candidate_primary_keys[].uniqueness` | 逻辑主键唯一度 |
| `table_profile.logical_keys.candidate_primary_keys[].null_rate` | 逻辑主键空值率 |

---

## 四、参数依赖分析

### 1. `--domain` 参数

**结论：CQL 生成器无 `--domain` 参数**

**说明：**
- CQL 生成器只读取 JSON 中的 `table_domains` 字段（如果存在）
- 是否包含 `table_domains` 取决于 JSON 生成时的参数：
  ```bash
  # 生成包含 table_domains 的 JSON
  metaweave metadata --step json_llm --domain
  
  # 使用上述 JSON 生成 CQL（会包含 table_domains）
  metaweave metadata --step cql
  ```

**参数传递流程：**

```
--step json_llm --domain
    ↓
生成 JSON（包含 table_domains）
    ↓
--step cql（读取 JSON）
    ↓
Neo4j 图谱（包含 table_domains 属性）
```

### 2. 其他参数

**CQL 生成器支持的参数：**

| 参数 | 是否支持 | 说明 |
|-----|---------|------|
| `--config` | ✅ 是 | 配置文件路径 |
| `--domain` | ❌ 否 | 无此参数 |
| `--cross-domain` | ❌ 否 | 无此参数 |
| `--generate-domains` | ❌ 否 | 无此参数 |

**配置文件参数：**

```yaml
# configs/metadata_config.yaml
output:
  json_directory: output/json      # 输入：表/列画像
  rel_directory: output/rel        # 输入：关系
  cql_directory: output/cql        # 输出：CQL 脚本
```

---

## 五、Neo4j 图谱映射

### 1. Table 节点属性

| Neo4j 属性 | JSON 来源 | 数据类型 |
|-----------|----------|----------|
| `full_name` | `schema_name.table_name` | `string` |
| `id` | `schema_name.table_name` | `string` |
| `schema` | `table_info.schema_name` | `string` |
| `name` | `table_info.table_name` | `string` |
| `comment` | `table_info.comment` | `string` |
| `pk` | `physical_constraints.primary_key.columns` | `list<string>` |
| `uk` | `physical_constraints.unique_constraints[].columns` | `list<list<string>>` |
| `fk` | `physical_constraints.foreign_keys[].source_columns` | `list<list<string>>` |
| `logic_pk` | `logical_keys.candidate_primary_keys[].columns` | `list<list<string>>` |
| `logic_fk` | `[]`（预留） | `list<list<string>>` |
| `logic_uk` | `[]`（预留） | `list<list<string>>` |
| `indexes` | `physical_constraints.indexes[].columns` | `list<list<string>>` |
| `table_domains` | `table_profile.table_domains` | `list<string>` |
| `table_category` | `table_profile.table_category` | `string` |

### 2. Column 节点属性

| Neo4j 属性 | JSON 来源 | 数据类型 |
|-----------|----------|----------|
| `full_name` | `schema.table.column` | `string` |
| `schema` | `table_info.schema_name` | `string` |
| `table` | `table_info.table_name` | `string` |
| `name` | `column_profiles.<column_name>` | `string` |
| `data_type` | `column_profiles.<column_name>.data_type` | `string` |
| `comment` | `column_profiles.<column_name>.comment` | `string` |
| `semantic_role` | `column_profiles.<column_name>.semantic_analysis.semantic_role` | `string` |
| `is_pk` | 计算得出（是否在 `primary_key.columns` 中） | `boolean` |
| `is_uk` | 计算得出（是否在 `unique_constraints[].columns` 中） | `boolean` |
| `is_fk` | 计算得出（是否在 `foreign_keys[].source_columns` 中） | `boolean` |
| `is_time` | 计算得出（`semantic_role == "datetime"`） | `boolean` |
| `is_measure` | 计算得出（`semantic_role == "metric"`） | `boolean` |
| `pk_position` | 计算得出（在主键列表中的位置 + 1） | `integer` |
| `uniqueness` | `column_profiles.<column_name>.statistics.uniqueness` | `float` |
| `null_rate` | `column_profiles.<column_name>.statistics.null_rate` | `float` |

### 3. JOIN_ON 关系属性

| Neo4j 属性 | JSON 来源 | 数据类型 |
|-----------|----------|----------|
| `cardinality` | `relationships[].cardinality`（翻转后） | `string` |
| `join_type` | 固定值 `"INNER JOIN"` | `string` |
| `on` | 计算得出（`SRC.col = DST.col` 格式） | `string` |
| `source_columns` | `relationships[].from_columns` | `list<string>` |
| `target_columns` | `relationships[].to_columns` | `list<string>` |
| `constraint_name` | `relationships[].constraint_name` | `string` |

---

## 六、常见问题

### 1. JSON 格式兼容性

**问题：** 我的 JSON 是 `--step json` 生成的，能用于 CQL 生成吗？

**答案：** 可以，但会缺失部分可选字段：
- ✅ 必需字段都存在（表名、列名、数据类型等）
- ❌ 缺失 `table_domains`（默认为 `[]`）
- ❌ 缺失 `table_category`（默认为 `null`）
- ❌ 可能缺失 `semantic_role`（取决于配置）

**建议：** 使用 `--step json_llm` 生成更完整的 JSON。

### 2. 逻辑主键置信度阈值

**问题：** 为什么我的逻辑主键没有被写入 Neo4j？

**答案：** CQL 生成器只保留 `confidence_score >= 0.8` 的候选逻辑主键。

**解决方案：**
- 检查 JSON 中的 `confidence_score` 值
- 如果需要更低的阈值，需要修改代码：
  ```python
  # metaweave/core/cql_generator/reader.py:194
  if confidence >= 0.7:  # 原来是 0.8
  ```

### 3. 关系方向翻转

**问题：** 为什么我的关系方向和 JSON 中的不一致？

**答案：** CQL 生成器会自动翻转 `1:N` 关系，确保箭头始终指向 1 侧。

**示例：**

```json
// 输入：relationships_global.json
{
  "from_table": {"table": "company"},
  "to_table": {"table": "employee"},
  "cardinality": "1:N"
}

// 输出：Neo4j
(employee)-[:JOIN_ON {cardinality: "N:1"}]->(company)
```

---

## 七、字段完整性检查清单

### 1. 最小可运行 JSON

**表/列画像 JSON（`output/json/*.json`）：**

```json
{
  "table_info": {
    "schema_name": "public",
    "table_name": "employee"
  },
  "column_profiles": {
    "employee_id": {
      "data_type": "integer"
    }
  },
  "table_profile": {}
}
```

**关系 JSON（`output/rel/relationships_global.json`）：**

```json
{
  "relationships": []
}
```

### 2. 推荐完整 JSON

**表/列画像 JSON：**

```json
{
  "metadata_version": "3.2",
  "generated_at": "2025-12-26T10:00:00",
  "llm_enhanced_at": "2025-12-26T10:05:00",
  "table_info": {
    "schema_name": "public",
    "table_name": "employee",
    "comment": "员工表"
  },
  "column_profiles": {
    "employee_id": {
      "data_type": "integer",
      "comment": "员工ID",
      "semantic_analysis": {
        "semantic_role": "identifier"
      },
      "statistics": {
        "uniqueness": 1.0,
        "null_rate": 0.0
      }
    }
  },
  "table_profile": {
    "physical_constraints": {
      "primary_key": {
        "constraint_name": "employee_pkey",
        "columns": ["employee_id"]
      },
      "unique_constraints": [],
      "foreign_keys": [],
      "indexes": []
    },
    "logical_keys": {
      "candidate_primary_keys": []
    },
    "table_domains": ["人力资源"],
    "table_category": "dim"
  }
}
```

**关系 JSON：**

```json
{
  "metadata_version": "3.2",
  "generated_at": "2025-12-26T10:10:00",
  "statistics": {
    "total_relationships_found": 1
  },
  "relationships": [
    {
      "type": "single_column",
      "from_table": {
        "schema": "public",
        "table": "employee"
      },
      "from_column": "company_id",
      "to_table": {
        "schema": "public",
        "table": "dim_company"
      },
      "to_column": "company_id",
      "cardinality": "N:1",
      "constraint_name": "fk_company"
    }
  ]
}
```

---

## 八、总结

### 1. 核心依赖字段

**必需字段（5 个）：**
1. `table_info.schema_name`
2. `table_info.table_name`
3. `column_profiles.<column_name>`
4. `column_profiles.<column_name>.data_type`
5. `relationships[].from_table/to_table/cardinality`

**推荐字段（10 个）：**
1. `table_info.comment`
2. `column_profiles.<column_name>.comment`
3. `column_profiles.<column_name>.semantic_analysis.semantic_role`
4. `column_profiles.<column_name>.statistics.uniqueness`
5. `column_profiles.<column_name>.statistics.null_rate`
6. `table_profile.physical_constraints.primary_key`
7. `table_profile.physical_constraints.unique_constraints`
8. `table_profile.physical_constraints.foreign_keys`
9. `table_profile.physical_constraints.indexes`
10. `table_profile.logical_keys.candidate_primary_keys`

**可选字段（2 个）：**
1. `table_profile.table_domains`（需要 `--step json_llm --domain`）
2. `table_profile.table_category`（需要 `--step json_llm`）

### 2. 参数依赖

| 参数 | CQL 生成器支持 | JSON 生成器支持 | 影响字段 |
|-----|--------------|--------------|---------|
| `--domain` | ❌ 否 | ✅ 是（`json_llm`） | `table_profile.table_domains` |
| `--cross-domain` | ❌ 否 | ✅ 是（`rel_llm`） | 关系数量 |

### 3. 数据流

```
Step 1: 元数据采集
--step json / --step json_llm [--domain]
    ↓
output/json/*.json
    ↓
Step 2: 关系发现
--step rel / --step rel_llm [--domain] [--cross-domain]
    ↓
output/rel/relationships_global.json
    ↓
Step 3: CQL 生成
--step cql / --step cql_llm
    ↓
output/cql/import_all.cypher
    ↓
Neo4j 图数据库
```

---

## 变更历史

| 日期 | 版本 | 说明 |
|-----|------|------|
| 2025-12-26 | 1.0 | 初始版本 |

