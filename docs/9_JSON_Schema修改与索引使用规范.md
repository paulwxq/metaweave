# JSON Schema 修改与索引使用规范

**文档类型：** 📋 **设计规范与改造方案**（代码尚未实施）  
**修改日期：** 2025-12-30  
**影响步骤：** `--step json`, `--step json_llm`, `--step rel`, `--step rel_llm`, `--step cql`  
**支持数据库：** PostgreSQL, Greenplum（暂不支持其他数据库）  
**变更类型：** 🔴 **破坏性变更（断崖式升级）**

---

## 零、版本策略与兼容性声明

### 0.1 破坏性变更说明

本次修改为**断崖式升级**，包含以下不兼容变更：

| 变更项 | 影响 | 破坏性 |
|--------|------|--------|
| `logical_keys` → `unique_column_sets` | JSON 结构变化 | 🔴 是 |
| `physical_constraints.indexes` → `table_profile.indexes` | JSON 访问路径变化 | 🔴 是 |
| `table_info` 新增 `database` 字段 | 下游需适配新字段 | 🟡 否（新增字段） |
| REL/CQL 步骤代码逻辑变更 | 索引不再参与关系发现 | 🔴 是 |

### 0.2 版本策略

**`metadata_version` 处理：**
- 当前版本保持 `2.0` 不变
- 原因：`metadata_version` 目前主要用于标识元数据提取的基本能力（表/列/约束提取），而非 JSON 输出格式版本
- **未来建议：** 如需严格版本管理，应引入独立的 `schema_version` 字段（如 `"schema_version": "3.0"`）

**兼容性策略：**
- ❌ **不保留向后兼容**：代码不再支持读取旧格式 JSON（`logical_keys`, `physical_constraints.indexes`）
- ⚠️ **强制重新生成**：所有使用旧格式的 JSON 文件必须重新运行 `--step json` 或 `--step json_llm`（推荐后者，含 LLM 增强）
- ✅ **一次性升级**：升级后所有步骤（JSON → REL → CQL）统一使用新格式

### 0.3 升级路径

**升级步骤：**
1. 备份现有 `output/json/` 和 `output/rel/` 目录（可选）
2. 清空或删除旧的 JSON 输出文件
3. 重新运行：
   ```bash
   # 步骤 0：确保有 DDL 文件（--step json 依赖）
   # 如果 output/ddl 目录为空或不存在，需要先生成 DDL
   python metaweave.py --step ddl
   
   # 方案 A：仅生成基础 JSON（无 LLM 增强）
   python metaweave.py --step json
   
   # 方案 B：生成 LLM 增强的 JSON（推荐，会自动先执行 --step json）
   python metaweave.py --step json_llm
   
   # ⚠️ 注意：不要同时执行 json 和 json_llm，json_llm 会自动执行 json
   
   # 重新发现关系（使用新逻辑）
   python metaweave.py --step rel          # 基础关系发现
   python metaweave.py --step rel_llm      # LLM 辅助关系发现
   
   # 重新导入 Neo4j
   python metaweave.py --step cql
   ```

**依赖说明：**
- ⚠️ `--step json` 从 `output/ddl/*.sql` 文件读取表结构（DDL 路径）
- ⚠️ 如果环境中没有运行过 `--step ddl`，必须先执行步骤 0
- ✅ `--step all` 会自动生成 DDL + JSON，无需手动执行步骤 0

**数据丢失风险：**
- ✅ **无数据丢失**：所有信息仍在数据库中，重新生成即可
- ⚠️ **手动标注丢失**：如果旧 JSON 中有手动修改的内容（如人工调整的 `semantic_role`），需要重新标注

---

## 一、JSON Schema 修改说明

### 1.1 修改目标

1. 去掉 `logical_keys` 包装层，`candidate_primary_keys` 改名为 `unique_column_sets` 并提升到 `table_profile` 层级
2. 将 `indexes` 从 `physical_constraints` 中分离，提升到与 `physical_constraints` 平级
3. 在 `table_info` 下增加 `database` 字段

### 1.2 数据库支持说明

**当前支持：** PostgreSQL, Greenplum

**索引处理机制：**
- PostgreSQL/Greenplum 在创建唯一约束时，会自动创建支持索引
- DDL 解析结果：唯一约束记录在 `unique_constraints`，对应索引记录在 `indexes`（is_unique=true）
- 因此，`unique_constraints` 已完整包含所有唯一性约束信息
- 索引（包括唯一索引）仅作为查询优化工具，不参与关系发现逻辑

### 1.3 修改前后对比

#### 修改前：
```json
{
  "table_info": {
    "schema_name": "public",
    "table_name": "dim_product_type",
    ...
  },
  "table_profile": {
    "physical_constraints": {
      "primary_key": null,
      "foreign_keys": [],
      "unique_constraints": [],
      "indexes": [...]  // ❌ 位置不当
    },
    "logical_keys": {     // ❌ 多余包装层
      "candidate_primary_keys": [...]
    }
  }
}
```

#### 修改后：
```json
{
  "table_info": {
    "database": "store_db",        // ✅ 新增
    "schema_name": "public",
    "table_name": "dim_product_type",
    ...
  },
  "table_profile": {
    "physical_constraints": {
      "primary_key": null,
      "foreign_keys": [],
      "unique_constraints": []
      // ✅ 移除 indexes
    },
    "indexes": [                   // ✅ 提升到平级
      {
        "index_name": "idx_...",
        "columns": [...],
        "is_unique": false,
        "index_type": "btree"
      }
    ],
    "unique_column_sets": [        // ✅ 替代 logical_keys.candidate_primary_keys
      {
        "columns": ["product_type_id"],
        "confidence_score": 1.0,
        "uniqueness": 1.0,
        "null_rate": 0.0
      }
    ]
  }
}
```

---

## 二、代码修改清单（完整版）

### 2.0 修改总览

| 文件 | 行号 | 类型 | 修改内容 |
|------|------|------|---------|
| **JSON 生成（Schema变更）** |
| `models.py` | 490-518 | Schema变更 | `TableProfile.to_dict()` - 提升 indexes，改 unique_column_sets |
| `models.py` | 158-166 | Schema变更 | `TableMetadata.to_dict()` - 添加 database 字段 |
| `models.py` | 100-117 | 新增字段 | `TableMetadata` dataclass 添加 `database: Optional[str] = None` |
| `generator.py` | ~332 | 赋值(DB路径) | `_process_table_from_db()` 中设置 `metadata.database` |
| `generator.py` | ~416 | 赋值(DDL路径) | `_process_table_from_ddl()` 中设置 `metadata.database` |
| **JSON_LLM 步骤（无需修改）** |
| `json_llm_enhancer.py` | - | ✅ 无需修改 | 增强器只读写JSON，Schema由 models.py 控制 |
| **REL 步骤 - 访问路径修改** |
| `candidate_generator.py` | 1037-1047 | 路径修改 | `_is_logical_primary_key()` - 改用 unique_column_sets |
| `candidate_generator.py` | 207-211 | 路径修改 | `_collect_source_combinations()` - 改用 unique_column_sets |
| **REL 步骤 - 索引完全排除** |
| `candidate_generator.py` | 199-204 | ❌ 删除 | 复合键候选生成删除索引收集代码 |
| `candidate_generator.py` | 868-875 | ❌ 删除 | 单列候选：目标列物理约束判断删除 is_indexed |
| `candidate_generator.py` | 1076-1078 | ❌ 删除 | 单列目标列筛选不检查 is_indexed |
| `decision_engine.py` | 210-213 | ❌ 删除 | 独立约束判断不检查 is_indexed |
| `writer.py` | 445-446 | ❌ 删除 | source_constraint 不使用 is_indexed |
| `writer.py` | 494-495 | ❌ 删除 | target_source_type 不使用 is_indexed |
| `writer.py` | 499-509 | 路径修改 | 改用 unique_column_sets |
| **REL_LLM 步骤** |
| `llm_relationship_discovery.py` | 623 | ❌ 删除 | 物理约束判断不包含 is_indexed |
| **CQL 步骤** |
| `reader.py` | 186-189 | 路径修改 | 索引访问路径改为 `table_profile.indexes` |
| `reader.py` | 192-196 | 路径修改 | 改用 unique_column_sets |

---

### 2.1 JSON 生成阶段

**核心说明：**
- ✅ **JSON 输出结构变更集中在 `models.py` 的 `to_dict()` 方法**，另需补齐 `database` 字段定义与传递
- ✅ `--step json` 直接使用 `models.py` 生成新格式 JSON
- ✅ `--step json_llm` 先调用 `--step json` 生成JSON，再使用 `json_llm_enhancer.py` 原地增强
- ⚠️ `llm_json_generator.py` 已废弃（自 2025-12-26），不再使用

**修改清单：**
1. `models.py`: 修改 `to_dict()` 输出结构（提升 indexes、改 unique_column_sets）
2. `models.py`: 添加 `database` 字段到 `TableMetadata` dataclass
3. `generator.py`: 在两条路径中设置 `metadata.database`（DB路径 + DDL路径）

#### A. 数据模型 (`metaweave/core/metadata/models.py`)

**修改 1：** `TableProfile.to_dict()` (第490-518行)

**修改内容：**
```python
def to_dict(self, metadata: Optional['TableMetadata'] = None) -> Dict[str, Any]:
    result = {
        "table_category": self.table_category,
        "confidence": self.confidence,
        "inference_basis": self.inference_basis,
    }
    
    # 添加 physical_constraints（从 metadata 获取，不包含 indexes）
    if metadata:
        result["physical_constraints"] = {
            "primary_key": metadata.primary_keys[0].to_dict() if metadata.primary_keys else None,
            "foreign_keys": [fk.to_dict() for fk in metadata.foreign_keys],
            "unique_constraints": [uc.to_dict() for uc in metadata.unique_constraints],
            # ❌ 删除: "indexes": [idx.to_dict() for idx in metadata.indexes],
        }
        
        # ✅ 新增：indexes 提升到 table_profile 层级
        result["indexes"] = [idx.to_dict() for idx in metadata.indexes]
    
    # column_statistics
    result["column_statistics"] = self.column_statistics.to_dict()
    
    # ✅ 修改：unique_column_sets 替代 logical_keys
    if self.candidate_logical_primary_keys:
        result["unique_column_sets"] = [lk.to_dict() for lk in self.candidate_logical_primary_keys]
    
    return result
```

**修改 2：** `TableMetadata.to_dict()` (第158-166行)

**修改内容：**
```python
"table_info": {
    "database": self.database,  # ✅ 新增
    "schema_name": self.schema_name,
    "table_name": self.table_name,
    ...
}
```

**修改 3：** `TableMetadata` 类定义（第100-117行）

**修改内容：**
```python
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class TableMetadata:
    """表元数据"""
    schema_name: str
    table_name: str
    database: Optional[str] = None  # ✅ 新增字段（dataclass 风格）
    table_type: str = "table"
    comment: str = ""
    comment_source: str = "db"
    row_count: int = 0
    columns: List[ColumnInfo] = field(default_factory=list)
    # ... 其他字段
```

**注意：** 
- `TableMetadata` 使用 `@dataclass` 装饰器，不是手写 `__init__`
- 新增字段使用 `Optional[str]` 类型注解
- 默认值为 `None`（dataclass 语法）

#### B. 元数据生成器 (`metaweave/core/metadata/generator.py`)

**修改位置 1：** `_process_table_from_db()` (约第332行)

**修改内容：**
```python
# 1. 提取元数据
metadata = self.extractor.extract_all(schema, table)
if not metadata:
    raise ValueError(f"提取元数据失败: {schema}.{table}")

# ✅ 新增：设置 database 字段（从数据库提取时）
metadata.database = self.connector.database
```

**修改位置 2：** `_process_table_from_ddl()` (约第416行)

**修改内容：**
```python
try:
    parsed = self._get_ddl_loader().load_table(schema, table)
    metadata = parsed.metadata
    
    # ✅ 新增：设置 database 字段（从 DDL 提取时）
    # 注意：DDLLoader 的 database_name 来自 formatter.database_name
    # 必须与 connector.database 保持一致
    metadata.database = self._get_ddl_loader().database_name
except DDLLoaderError as exc:
    logger.error(f"DDL 解析失败 ({schema}.{table}): {exc}")
    ...
```

**说明：**
- `_process_table_from_db()`: `--step ddl/md/all` 使用，从数据库提取
  - `database` 来源：`self.connector.database`（来自配置 `database.database`）
- `_process_table_from_ddl()`: `--step json` 使用，从 DDL 文件提取
  - `database` 来源：`self._get_ddl_loader().database_name`（来自 `formatter.database_name`）
  - `formatter.database_name` 实际来自配置 `output.database_name`

**⚠️ 关键要求：**
- **必须保证配置一致性**：`database.database` == `output.database_name`
- 如果两者不一致，同一张表在不同步骤生成的 JSON 中 `database` 字段将不同
- **推荐配置方式**：在配置文件中使用同一个环境变量
  ```yaml
  database:
    database: ${DB_NAME}  # 例如：store_db
  
  output:
    database_name: ${DB_NAME}  # 必须与 database.database 一致
  ```

#### C. JSON_LLM 增强器（无需修改）

**文件：** `metaweave/core/metadata/json_llm_enhancer.py`

**说明：**
- ✅ **无需修改**：增强器只负责读取 JSON、调用 LLM、写回 JSON
- ✅ JSON Schema 结构由 `models.py` 的 `to_dict()` 控制
- ✅ `--step json_llm` 工作流程：
  1. 先执行 `--step json`（使用新 Schema 生成 JSON）
  2. 读取 `output/json/*.json`
  3. LLM 增强（添加分类、评论等）
  4. 写回 `output/json/*.json`（覆盖）

---

### 2.2 REL 步骤（关系发现）

**核心原则：** REL 步骤**完全不再使用 `indexes` 作为约束来源**。索引相关代码将被完全删除，而非修改访问路径。

#### A. 访问路径修改（candidate_generator.py）

**位置 1：** `_is_logical_primary_key()` (第1037-1047行)

```python
# ❌ 原代码
logical_keys = table_profile.get("logical_keys", {})
for lk in logical_keys.get("candidate_primary_keys", []):
    ...

# ✅ 修改后
unique_column_sets = table_profile.get("unique_column_sets", [])
for lk in unique_column_sets:
    ...
```

**位置 2：** `_collect_source_combinations()` (第207-211行)

```python
# ❌ 原代码
logical_keys = table_profile.get("logical_keys", {})
for lk in logical_keys.get("candidate_primary_keys", []):
    ...

# ✅ 修改后
unique_column_sets = table_profile.get("unique_column_sets", [])
for lk in unique_column_sets:
    ...
```

**说明：** 原"位置3：索引访问路径"已在场景1中完全删除（见3.2节场景1），无需修改访问路径。

#### B. 访问路径修改（writer.py）

**文件：** `metaweave/core/relationships/writer.py`

**位置：** `_get_target_source_type()` (第499-509行)

```python
# ❌ 原代码
logical_keys = table_profile.get("logical_keys", {})
for lk in logical_keys.get("candidate_primary_keys", []):
    ...

# ✅ 修改后
unique_column_sets = table_profile.get("unique_column_sets", [])
for lk in unique_column_sets:
    ...
```

---

### 2.3 CQL 步骤（Neo4j 导入）

#### A. JSON 读取器

**文件：** `metaweave/core/cql_generator/reader.py`

**位置 1：** `_extract_table()` (第186-196行)

```python
# ❌ 原代码
indexes = []
for idx_data in physical_constraints.get("indexes", []):
    ...

logic_pk = []
logical_keys = table_profile.get("logical_keys", {})
for candidate in logical_keys.get("candidate_primary_keys", []):
    ...

# ✅ 修改后
indexes = []
for idx_data in table_profile.get("indexes", []):
    ...

logic_pk = []
unique_column_sets = table_profile.get("unique_column_sets", [])
for candidate in unique_column_sets:
    ...
```

---

## 三、索引使用规范修改

### 3.1 核心原则

**索引不是约束** - 索引只是查询优化工具，不应参与关系发现的业务逻辑。

#### 数据库支持说明（PostgreSQL/Greenplum）

在 PostgreSQL 和 Greenplum 中：
1. **唯一约束（UNIQUE CONSTRAINT）** 会自动创建支持索引
2. **DDL 解析结果：**
   - 唯一约束 → 记录在 `unique_constraints`
   - 对应的唯一索引 → 记录在 `indexes`（is_unique=true）
3. **结论：** `unique_constraints` 已完整包含所有唯一性约束信息，无需从 `indexes` 中再次提取

#### 修改策略

**一刀切禁用所有索引（包括唯一索引）**
- ❌ 复合键候选：不使用任何索引
- ❌ 单列目标列：不检查 `is_indexed`
- ❌ 独立约束：不检查 `is_indexed`
- ❌ 物理约束判断：不包含索引

**无召回率损失**
- 唯一约束信息已在 `unique_constraints` 中完整记录
- 不存在"只有唯一索引没有约束"的情况（PostgreSQL/Greenplum 机制保证）
- 普通索引本来就不应该参与关系发现

---

### 3.2 修改清单

#### 场景 1：复合键候选生成

**文件：** `candidate_generator.py`  
**位置：** 第199-204行

**修改内容：**
```python
# ❌ 删除此段代码
# 3. 索引（仅当 include_indexes=True 时收集）
if include_indexes:
    for idx in physical.get("indexes", []):
        idx_cols = idx.get("columns", [])
        if 2 <= len(idx_cols) <= self.max_columns:
            combinations.append({"columns": idx_cols, "type": "physical"})
```

**配置废弃：**
- `target_sources: ["composite_indexes"]` - 不再使用

**目标表只保留：** PK + UK + 逻辑键（unique_column_sets）

---

#### 场景 2：单列候选生成中的目标列物理约束判断

**文件：** `candidate_generator.py`  
**位置：** `_generate_single_column_candidates()` (第868-875行)

**修改内容：**
```python
# ❌ 原代码
target_has_physical = (
    target_structure_flags.get("is_primary_key") or
    target_structure_flags.get("is_unique") or
    target_structure_flags.get("is_unique_constraint") or
    target_structure_flags.get("is_indexed")  # ❌ 删除这行
)

# ✅ 修改后
target_has_physical = (
    target_structure_flags.get("is_primary_key") or
    target_structure_flags.get("is_unique") or
    target_structure_flags.get("is_unique_constraint")
    # ❌ 索引不再作为物理约束判断条件
)
```

**说明：** 
- 该方法用于生成单列候选关系
- 当目标列有"物理约束"时，跳过语义角色过滤（赋予特权）
- 索引不应该赋予此特权

---

#### 场景 3：单列目标列筛选

**文件：** `candidate_generator.py`  
**位置：** `_is_qualified_target_column()` (第1076-1078行)

**修改内容：**
```python
# ❌ 删除此段代码
# 3. 检查索引
if structure_flags.get("is_indexed"):
    return True
```

**修改后的逻辑：**
```python
def _is_qualified_target_column(self, col_name: str, col_profile: dict, table: dict) -> bool:
    """检查目标列（被引用列）是否满足合格条件
    
    合格条件：
    1. 物理主键
    2. 唯一约束
    3. 单列逻辑主键（confidence >= 0.8）
    """
    structure_flags = col_profile.get("structure_flags", {})
    
    # 1. 检查物理主键
    if structure_flags.get("is_primary_key"):
        return True
    
    # 2. 检查唯一约束
    if structure_flags.get("is_unique") or structure_flags.get("is_unique_constraint"):
        return True
    
    # 3. 检查是否为单列逻辑主键
    if self._is_logical_primary_key(col_name, table):
        return True
    
    return False
```

---

#### 场景 4：独立约束判断（抑制规则）

**文件：** `decision_engine.py`  
**位置：** 第210-213行

**修改内容：**
```python
# ❌ 删除此段代码
# 检查单列索引
if structure_flags.get("is_indexed"):
    # 需要确认是否为单列索引（而非复合索引的一部分）
    # Phase 1简化实现：有索引就算
    return True
```

**修改后的逻辑：**
```python
def _has_independent_constraint(self, candidate: Dict[str, Any]) -> bool:
    """检查源列是否有独立约束（PK/UK）
    
    独立约束 = 单列物理约束（不包括索引）
    """
    # ... 前面代码不变 ...
    
    # 检查单列主键
    if structure_flags.get("is_primary_key"):
        return True
    
    # 检查单列唯一约束
    if structure_flags.get("is_unique") or structure_flags.get("is_unique_constraint"):
        return True
    
    # ❌ 删除索引检查
    # ✅ 索引不算独立约束
    return False
```

---

#### 场景 5：复合键匹配中的"物理约束"判断

**文件：** `candidate_generator.py`  
**位置：** 第301行和第400-407行

**修改内容：**
```python
# ✅ 修改注释
target_is_physical=(target_combo["type"] == "physical")  # 目标表物理约束（PK/UK，不含索引）

# 在 _match_columns_as_set 中：
if target_is_physical:
    logger.debug(
        "[match_columns_as_set] 目标列 %s (物理约束: PK/UK) 不过滤，语义角色=%s",  # ✅ 修改注释
        tgt_col, tgt_semantic_role
    )
    # ✅ 物理约束不进行语义角色过滤，直接通过
    pass
```

**说明：** 由于场景 1 需要删除索引收集代码，此处 `target_is_physical` 自然不包含索引。

---

#### 场景 6：关系输出时的约束类型识别

**文件：** `writer.py`  
**位置 1：** `_get_source_constraint()` (第445-446行)

**修改内容：**
```python
# ❌ 删除此段代码
elif structure_flags.get("is_indexed"):
    return "single_field_index"
```

**位置 2：** `_get_target_source_type()` (第494-495行)

**修改内容：**
```python
# ❌ 删除此段代码
if structure_flags.get("is_indexed"):
    return "index"
```

**说明：** 生成关系 JSON 时，不再将索引标记为约束类型。

---

#### 场景 7：LLM 辅助关系发现中的物理约束判断

**文件：** `llm_relationship_discovery.py`  
**位置：** `_filter_by_semantic_roles()` (第623行)

**修改内容：**
```python
# ❌ 原代码
is_physical = (
    structure_flags.get("is_primary_key") or
    structure_flags.get("is_unique") or
    structure_flags.get("is_unique_constraint") or
    structure_flags.get("is_indexed")  # ❌ 删除这行
)

# ✅ 修改后
is_physical = (
    structure_flags.get("is_primary_key") or
    structure_flags.get("is_unique") or
    structure_flags.get("is_unique_constraint")
)
```

**说明：** 判断目标列是否为"物理约束"时，不包含索引。

---

#### 场景 8：保留 is_indexed flag

**文件：** `profiler.py`, `models.py`

**结论：** ✅ 保留不变

**原因：**
- `structure_flags.is_indexed` 在 JSON 中仍然有记录价值（文档、分析）
- `profiler.py` 负责计算 `is_indexed` 标志
- `models.py` 的 `to_dict()` 会输出该标志到 JSON
- 只是不在关系发现逻辑中使用

---

## 四、测试要点

**兼容性说明：** ⚠️ **断崖式升级，不考虑向后兼容**。
- 所有输出端（JSON生成）必须使用新格式
- 所有读取端（REL/CQL）只支持新格式
- 旧格式 JSON 文件将导致读取失败或逻辑错误

### 4.0 断崖式升级验证
- [ ] **旧JSON处理策略：** 访问 `logical_keys` 或 `physical_constraints.indexes` 时得到 `None`/`[]`（代码无显式校验）
- [ ] **结果验证：** 使用旧格式 JSON 运行 `--step rel`，虽不报错但生成的关系可能不完整（缺少逻辑键候选）
- [ ] **完整性测试：** 清空 `output/json/`，重新生成所有表的 JSON，验证新格式完整性
- [ ] **metadata_version：** 确认仍为 `2.0`（不变），未来建议增加 `schema_version`

**说明：** 
- ⚠️ 代码**不会主动校验**旧 JSON 格式并报错
- ⚠️ 旧 JSON 不会导致崩溃，但结果不可信（缺少关键字段）
- ✅ **推荐做法**：升级后强制重新生成所有 JSON，不依赖旧文件

### 4.1 JSON 生成测试（--step json, --step json_llm, --step all）
- [ ] **配置一致性验证：** 确认 `database.database` == `output.database_name`（必须一致）
- [ ] **`table_info.database` 字段正确填充（DDL路径）**：`--step json` 生成的 JSON 中 database 名称正确
- [ ] **`table_info.database` 字段正确填充（all模式）**：`--step all` 生成的 JSON 中 database 名称正确
- [ ] **交叉验证：** 同一张表在 `--step json` 和 `--step all` 生成的 JSON 中，`database` 字段值相同
- [ ] `table_profile.indexes` 与 `physical_constraints` 平级
- [ ] `table_profile.unique_column_sets` 正确生成
- [ ] **`logical_keys` 字段不再出现**（输出端不再产生旧格式）
- [ ] **`physical_constraints.indexes` 字段不再出现**（输出端不再产生旧格式）
- [ ] 唯一约束同时记录在 `unique_constraints` 和 `indexes`（is_unique=true）
- [ ] `structure_flags.is_indexed` 仍然存在（保留用于文档/分析）

**说明：** 
- `--step ddl` 和 `--step md` 默认不输出 JSON，无需测试 JSON 格式
- `--step json_llm` 会自动先执行 `--step json`，只需测试最终 JSON 即可
- **database 字段来源**：
  - `--step json` → `output.database_name`
  - `--step all` → `database.database`
  - 如果配置不一致，会导致同一张表的 database 值不同

### 4.2 REL 步骤测试（--step rel）
- [ ] **复合键候选生成：** 不使用任何索引（需删除代码 199-204行）
- [ ] **单列候选生成：** 目标列物理约束判断不包含 `is_indexed`（需修改代码 868-875行）
- [ ] **单列目标列筛选：** 不检查 `is_indexed`（需删除代码 1076-1078行）
- [ ] **独立约束判断：** 不检查 `is_indexed`（需删除代码 210-213行）
- [ ] **复合键匹配：** 物理约束特权不包含索引（只含 PK/UK）
- [ ] **关系输出 JSON：** 不再出现 `source_constraint: "single_field_index"`
- [ ] **关系输出 JSON：** 不再出现 `target_source_type: "index"`
- [ ] **访问路径正确：** 读取 `unique_column_sets` 而非 `logical_keys.candidate_primary_keys`

### 4.3 REL_LLM 步骤测试（--step rel_llm）
- [ ] **语义角色过滤：** `is_indexed` 不作为"物理约束"判断条件（需修改代码 623行）
- [ ] **候选关系过滤：** 索引列不再享有"跳过语义角色过滤"的特权
- [ ] **物理约束判断：** 不再将 `is_indexed` 当作物理约束特权/过滤豁免条件
- [ ] **同名匹配：** 目标表物理约束不包含索引（与 --step rel 一致）

**说明：** 
- LLM 仍会接收完整的 JSON 输入（包含 `structure_flags.is_indexed` 和 `table_profile.indexes`）
- 修改点在**代码逻辑层面**：不再将索引作为"物理约束"的判断条件

### 4.4 CQL 步骤测试（--step cql）
- [ ] Neo4j 中 `Table.indexes` 正确导入（从 `table_profile.indexes` 读取）
- [ ] Neo4j 中 `Table.logic_pk` 正确导入（从 `unique_column_sets` 读取）
- [ ] 访问路径正确：不再从 `physical_constraints.indexes` 读取

### 4.5 召回率测试（跨步骤验证）
- [ ] 唯一约束关系未丢失（通过 `unique_constraints` 识别）
- [ ] 逻辑主键关系未丢失（通过 `unique_column_sets` 识别）
- [ ] 普通索引不再参与关系发现（符合预期，无召回损失）
- [ ] 唯一索引不再参与关系发现（符合预期，已由 `unique_constraints` 覆盖）

---

## 五、文档更新清单

需要更新的文档：
- [ ] `docs/5_cql生成器JSON字段依赖清单.md`
- [ ] `docs/6_rel命令执行流程详解.html`
- [ ] `docs/design/step 3.关联字段查找算法详解_v3.2.md`
- [ ] `docs/design/LLM辅助关联关系发现设计方案.md`

---

**End of Document**

