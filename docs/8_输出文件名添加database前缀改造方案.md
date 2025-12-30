# 输出文件名添加 database 前缀改造方案

> **文档版本**: 1.0  
> **创建日期**: 2025-12-29  
> **改造目标**: 将所有输出文件名从 `schema.table.ext` 改为 `database.schema.table.ext`

---

## 📋 改造目标

### 当前文件名格式
```
output/
├── ddl/
│   └── public.department.sql
├── json/
│   └── public.department.json
└── md/
    └── public.department.md
```

### 目标文件名格式
```
output/
├── ddl/
│   └── mydb.public.department.sql
├── json/
│   └── mydb.public.department.json
└── md/
    └── mydb.public.department.md
```

**优势**：
- 支持多数据库场景（未来可能有多个数据库的元数据）
- 文件名更明确，避免不同数据库的同名表冲突
- 便于组织和管理

---

## 🎯 影响分析

### 受影响的步骤

| 步骤 | 影响 | 说明 |
|-----|------|------|
| `--step ddl` | ✅ 需修改 | 生成 DDL 文件名 |
| `--step json` | ✅ 需修改 | 读取 DDL 样例数据 + 生成 JSON 文件名 |
| `--step json_llm` | ✅ 间接影响 | 读取 JSON 文件（文件名变了，但不影响功能） |
| `--step md` | ✅ 需修改 | 生成 Markdown 文件名 |
| `--step rel` | ❌ 无影响 | 读取 JSON 内容，不依赖文件名 |
| `--step rel_llm` | ❌ 无影响 | 读取 JSON 内容，不依赖文件名 |
| `--step cql` | ❌ 无影响 | 读取 JSON 内容，不依赖文件名 |

### ⚠️ 额外风险：仍有旧逻辑按文件名拆分 schema/table

仓库中仍存在按旧文件名 `schema.table.*` 拆分的遗留代码（示例）：
- `metaweave/core/metadata/llm_json_generator.py`：`schema, table = filename_stem.split(".", 1)`

如果该路径仍被任何命令/脚本调用，引入 `{database}.schema.table.*` 后会导致解析错误：
- `schema = database`
- `table = schema.table`

**处理建议（写清楚，避免踩坑）**：
- 若 `LLMJsonGenerator` 已废弃/不再被 CLI 路径调用：在本方案实施前做一次全仓检索，确认无入口后，在文档中标注“legacy，不在本次改造范围”。
- 若仍会被调用：必须同步修改其文件名解析逻辑（支持 `database.schema.table`），或改为从 JSON/DDL 内容中的 `table_info.schema_name/table_name` 获取（更稳）。

### 关键依赖链

```
DDL文件 (mydb.public.table.sql)
    ↓
    读取样例数据
    ↓
JSON文件 (mydb.public.table.json)
    ↓
    rel/cql 等后续步骤读取
```

**关键点**：JSON 生成时会从 DDL 读取样例数据，所以两者的文件名格式必须一致。

---

## 🛠️ 代码修改

### 修改文件

**`metaweave/core/metadata/formatter.py`**

**`metaweave/core/metadata/ddl_loader.py`**

（可选但推荐）**`metaweave/core/metadata/generator.py`**

### 修改内容

#### 1. 在 `__init__()` 方法中添加数据库名配置

```python
# 在 __init__() 方法第 58 行 ensure_dir(self.output_dir / "json") 之后添加
class OutputFormatter:
    def __init__(self, config: dict):
        # ... 现有代码 ...
        ensure_dir(self.output_dir / "json")
        
        # ✅ 新增：获取数据库名（来自 output.database_name；未设置则默认 "postgres"）
        # 注意：OutputFormatter 只接收 output 配置子树，不包含顶层 database 配置
        # 当前实现：MetadataGenerator 传入的是 config["output"]，因此这里直接用 config.get("database_name", ...)；若未来改为传全量 config，则需改为 config.get("output", {}).get("database_name", ...)
        self.database_name = config.get("database_name", "postgres")
        
        logger.info(f"输出格式化器已初始化: {self.output_dir}")
```

#### 2. 在 `__init__()` 方法之后添加辅助方法

```python
# 在 __init__() 方法之后（约第 62 行），format_and_save() 方法之前添加
def _get_filename(self, metadata: TableMetadata, extension: str) -> str:
    """生成标准文件名：database.schema.table.{extension}
    
    Args:
        metadata: 表元数据
        extension: 文件扩展名（如 'sql', 'json', 'md'）
        
    Returns:
        格式化的文件名
    """
    return f"{self.database_name}.{metadata.schema_name}.{metadata.table_name}.{extension}"
```

#### 3. 修改 `_save_ddl()` 方法

```python
# 修改前（第 369 行）
file_path = self.output_dir / "ddl" / f"{metadata.schema_name}.{metadata.table_name}.sql"

# 修改后
filename = self._get_filename(metadata, "sql")
file_path = self.output_dir / "ddl" / filename
```

#### 4. 修改 `_save_markdown()` 方法

```python
# 修改前（第 385 行）
file_path = self.markdown_dir / f"{metadata.schema_name}.{metadata.table_name}.md"

# 修改后
filename = self._get_filename(metadata, "md")
file_path = self.markdown_dir / filename
```

#### 5. 修改 `_extract_sample_records_from_ddl()` 方法

```python
# 修改前（第 403 行）
ddl_file = self.output_dir / "ddl" / f"{metadata.schema_name}.{metadata.table_name}.sql"

# 修改后
filename = self._get_filename(metadata, "sql")
ddl_file = self.output_dir / "ddl" / filename
```

#### 6. 修改 `_save_json()` 方法

```python
# 修改前（第 494 行）
file_path = self.output_dir / "json" / f"{metadata.schema_name}.{metadata.table_name}.json"

# 修改后
filename = self._get_filename(metadata, "json")
file_path = self.output_dir / "json" / filename
```

#### 7. 修改 `DDLLoader.load_table()`（必改，否则 --step json 读不到 DDL）

当前实现强依赖旧文件名：`{schema}.{table}.sql`（`metaweave/core/metadata/ddl_loader.py`）。

改造后 DDL 文件名变为 `{database}.{schema}.{table}.sql`，因此 `--step json` 在从 DDL 解析表结构时会报“DDL 文件不存在”。

建议改造（不做旧格式兼容，避免误读）：

```python
# metaweave/core/metadata/ddl_loader.py
# load_table(schema, table) 内：只认新格式
ddl_path = self.ddl_dir / f"{self.database_name}.{schema}.{table}.sql"
if not ddl_path.exists():
    raise DDLLoaderError(f"DDL 文件不存在: {ddl_path}")
```

说明：
- `DDLLoader` 需要新增 `database_name` 属性（构造参数传入）。
- 本方案要求清理旧文件（见“清理旧文件”章节），因此不提供旧格式回退逻辑。

#### 7.1 修改 `DDLLoader.__init__()`（新增参数与属性）

文件：`metaweave/core/metadata/ddl_loader.py`

需要给 `DDLLoader` 构造函数新增 `database_name` 参数，并保存为实例属性，供 `load_table()` 拼接文件名使用。

示例：

```python
# metaweave/core/metadata/ddl_loader.py
class DDLLoader:
    def __init__(self, ddl_dir: str | Path, database_name: str = "postgres"):
        self.ddl_dir = Path(ddl_dir)
        self.database_name = database_name  # 新增
        if not self.ddl_dir.exists():
            raise DDLLoaderError(f"DDL 目录不存在: {self.ddl_dir}")
```

#### 8. 传递 `database_name` 给 `DDLLoader`（推荐，避免多数据库歧义）

如果你按上一步给 `DDLLoader` 增加了 `database_name`，需要在 `MetadataGenerator` 创建 `DDLLoader` 时传入：

```python
# metaweave/core/metadata/generator.py
ddl_dir = self.formatter.output_dir / "ddl"
self.ddl_loader = DDLLoader(ddl_dir, database_name=self.formatter.database_name)
```

**修改前/修改后对比（便于开发定位）**：

```python
# 修改前：metaweave/core/metadata/generator.py（_get_ddl_loader 内）
self.ddl_loader = DDLLoader(ddl_dir)

# 修改后：metaweave/core/metadata/generator.py（_get_ddl_loader 内）
self.ddl_loader = DDLLoader(ddl_dir, database_name=self.formatter.database_name)
```

---

## 📝 实施步骤

### 第1步：备份

```powershell
# 代码备份
git add .
git commit -m "backup: before filename format change"

# 输出文件备份（可选）
Copy-Item output output_backup -Recurse
```

### 第2步：修改代码

修改 `metaweave/core/metadata/formatter.py`（6处）、`metaweave/core/metadata/ddl_loader.py`（2处），并推荐同步修改 `metaweave/core/metadata/generator.py`（1处，用于传递 `database_name`）。

### 第3步：清理旧文件

```powershell
# 删除受影响步骤的旧格式输出文件
Remove-Item output\ddl\*.sql -Force
Remove-Item output\json\*.json -Force
Remove-Item output\md\*.md -Force

# rel 和 cql 步骤虽不受文件名影响，但建议也重新生成以保持一致性
# 如果要全部重新生成，也可以删除：
# Remove-Item output\rel\*.json -Force
# Remove-Item output\cql\*.cypher -Force
```

### 第4步：最小测试

```powershell
# 先测试 1 张表
metaweave metadata --config configs/metadata_config.yaml --step ddl --tables department
metaweave metadata --config configs/metadata_config.yaml --step json --tables department

# 检查文件名（注意：实际的数据库名前缀取决于 output.database_name）
# 如果 output.database_name 为 "postgres"，文件名将是：
# postgres.public.department.sql
# postgres.public.department.json

# 验证文件是否存在
Get-ChildItem output\ddl\*.department.sql
Get-ChildItem output\json\*.department.json
```

### 第5步：完整测试

```powershell
# 生成所有步骤
metaweave metadata --config configs/metadata_config.yaml --step ddl
metaweave metadata --config configs/metadata_config.yaml --step json
metaweave metadata --config configs/metadata_config.yaml --step json_llm
metaweave metadata --config configs/metadata_config.yaml --step md
metaweave metadata --config configs/metadata_config.yaml --step rel
metaweave metadata --config configs/metadata_config.yaml --step cql
```

### 第6步：验证

```powershell
# 检查文件名格式
Get-ChildItem output\ddl\*.sql | Select-Object Name
Get-ChildItem output\json\*.json | Select-Object Name
Get-ChildItem output\md\*.md | Select-Object Name

# 应该看到类似格式（数据库名取决于你的配置）：
# {database}.public.department.sql
# {database}.public.department.json
# {database}.public.department.md
# 
# 例如，如果 output.database_name 配置为 "postgres"：
# postgres.public.department.sql
# postgres.public.department.json
# postgres.public.department.md
```

---

## ⚠️ 注意事项

### 1. database 名称配置

确保 `configs/metadata_config.yaml` 的 `output.database_name` 配置了正确的数据库名：

```yaml
# configs/metadata_config.yaml
output:
  output_dir: output

  # ✅ 新增：文件名前缀使用该值（建议与实际数据库名保持一致）
  # 可直接引用 .env 中的 DB_NAME
  database_name: ${DB_NAME:postgres}

  json_directory: output/json
  rel_directory: output/rel
  cql_directory: output/cql

  # ... 其他配置 ...
```

**默认值说明**：
- 如果配置文件中未设置 `output.database_name`，代码将使用默认值 `"postgres"`
- 建议明确配置数据库名，避免使用默认值导致混淆

（已简化）本方案不额外对 `output.database_name` 做 sanitize：数据库名本身应符合数据库的命名规范。

### 2. 一次性修改所有格式

**不建议**分步修改（如先只改 DDL），因为：
- JSON 依赖 DDL 的样例数据，文件名必须一致
- 新旧格式混合会造成混乱

**建议**一次性修改 DDL、JSON、MD，保持文件名完全统一。

### 3. 旧文件处理

修改后必须删除旧格式的文件，否则会导致：
- 新旧文件并存
- 不确定读取哪个文件
- 可能出现意外错误

---

## 📊 修改总结

| 修改项 | 位置 | 行号 | 改动内容 |
|-------|------|------|---------|
| 1. 添加配置 | `OutputFormatter.__init__()` | 约58行后 | 添加 `self.database_name`（读取 `output.database_name`） |
| 2. 添加辅助方法 | `OutputFormatter` 新增方法 | 约62行 | `_get_filename()` |
| 3. DDL 生成 | `OutputFormatter._save_ddl()` | 约369行 | 使用 `_get_filename()` |
| 4. Markdown 生成 | `OutputFormatter._save_markdown()` | 约385行 | 使用 `_get_filename()` |
| 5. DDL 读取 | `OutputFormatter._extract_sample_records_from_ddl()` | 约403行 | 使用 `_get_filename()` |
| 6. JSON 生成 | `OutputFormatter._save_json()` | 约494行 | 使用 `_get_filename()` |
| 7. DDLLoader 构造函数 | `DDLLoader.__init__()` | 约83行 | 添加 `database_name` 参数与属性 |
| 8. DDLLoader 读 DDL | `DDLLoader.load_table()` | 约89行 | 支持 `{database}.{schema}.{table}.sql`（不做旧格式兼容） |
| 9. 传递 database_name | `MetadataGenerator._get_ddl_loader()` | 约508行 | 传入 `database_name` |

**总计**：3 个文件，9 处关键改动

---

## ✅ 验收标准

改造完成后，确认以下内容：

- [ ] 所有 DDL 文件名格式为 `database.schema.table.sql`
- [ ] 所有 JSON 文件名格式为 `database.schema.table.json`
- [ ] 所有 MD 文件名格式为 `database.schema.table.md`
- [ ] `--step json` 能正确读取 DDL 的样例数据
- [ ] `--step json_llm` 能正确读取 JSON 文件
- [ ] `--step rel` 能正确读取 JSON 文件
- [ ] `--step cql` 能正确读取 JSON 和关系文件
- [ ] （如仍使用旧 LLMJsonGenerator 路径）相关脚本/命令不再依赖 `filename_stem.split(".", 1)` 的旧假设

---

## 📌 FAQ

### Q1: 为什么不保留向后兼容？

A: 用户明确表示可以删除旧文件，不需要兼容性。一次性改造更简单清晰。

### Q2: 如果有多个数据库怎么办？

A: 当前方案每次只处理一个数据库（由配置文件指定）。如果需要处理多个数据库，可以：
- 方案1: 使用不同的配置文件
- 方案2: 使用不同的输出目录

### Q3: 为什么 rel/cql 步骤不受影响？

A: 这些步骤读取的是 JSON 文件的**内容**，不依赖文件名。只要能找到 `*.json` 文件即可。虽然功能不受影响，但建议重新生成以保持输出一致性。

### Q4: 如果忘记删除旧文件会怎样？

A: 可能会读到旧文件或产生混乱。建议修改前先清空输出目录。

---

**文档结束**

