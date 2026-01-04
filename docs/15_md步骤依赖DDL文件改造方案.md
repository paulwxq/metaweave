# 15. `--step md` 依赖 DDL 文件改造方案

## 问题背景

当前 `--step md` 直接从数据库查询元数据，导致以下问题：

| 步骤 | 元数据来源 | 问题 |
|------|-----------|------|
| `--step ddl` | 数据库查询（T1 时刻） | ✅ 基准输出 |
| `--step md` | **数据库查询（T2 时刻）** | ❌ 如果 T1 和 T2 之间数据库结构变化，输出不一致 |

**核心矛盾**：
- 如果在两次执行之间，数据库结构发生变化（添加列、修改约束、更新注释），`md` 输出会与 `ddl` 不一致
- 无法保证 DDL 文档和 Markdown 文档描述的是同一个数据库版本

## 改造目标

让 `--step md` 从 DDL 文件读取元数据，而非重新查询数据库：

1. **元数据来源**：从 `output/ddl/*.sql` 文件读取（而非重新查询数据库）
2. **注释补全**：当表/列注释缺失时，调用 LLM 生成（使用缓存）
3. **样例数据**：从 DDL 文件的 `/* SAMPLE_RECORDS */` 块解析并转换为 DataFrame
4. **依赖关系**：明确依赖 `--step ddl` 的输出，无 DDL 文件时报错

## 设计方案选择（B+ 硬隔离）

### 为什么不选方案 A（共用 `_process_table_from_ddl()`）

**方案 A 的风险**：
- ❌ json 和 md 共用同一方法，md 的 file-only 改动会影响 json
- ❌ json 需要 COUNT/画像，md 不需要，逻辑分支复杂
- ❌ 未来维护时容易误伤 json 的功能

### 为什么选方案 B+（独立方法 + 硬隔离）

**方案 B+ 的优势**：
- ✅ `_process_table_from_ddl()` 保持不变，json 完全不受影响
- ✅ 新增 `_process_table_from_ddl_for_md()` 专用于 md，逻辑清晰
- ✅ 清晰的路由边界：`json` → 原方法，`md` → 新方法
- ✅ 代码审查/测试/回归都更简单
- ✅ 未来 md 演进不会影响 json

**实施原则**：
1. **不复用**：md 不复用 `_process_table_from_ddl()`
2. **不修改**：json 的处理链路保持原样
3. **新增独立**：md 单独一条 file-only 链路

## 涉及文件清单

```
metaweave/
├── core/metadata/
│   ├── generator.py           # 修改①②③④⑤：延迟初始化连接器 + 从DDL推断schemas + 从DDL枚举表 + md独立处理方法 + 样例数据转换
│   └── ddl_loader.py          # 修改⑥（可选）：将 sample_records 转为 DataFrame
├── cli/
│   └── metadata_cli.py        # 修改⑦：添加 DDL 依赖检查
└── CLAUDE.md                  # 修改⑧：更新文档

注：不需要修改 connector.py（通过延迟初始化 connector 已解决）
```

## 详细修改方案

### 修改① - `generator.py`：延迟初始化 DatabaseConnector（避免 md 步骤触达数据库）

**位置**：`metaweave/core/metadata/generator.py:69-77`

**问题**：当前 `_init_components()` 会立即创建 `DatabaseConnector`，而 `DatabaseConnector.__init__()` 调用 `ConnectionPool(open=True)` 会立即连接数据库，即使 md 步骤不需要数据库。

**当前代码**：
```python
def _init_components(self):
    """初始化所有组件"""
    # 数据库连接器
    db_config = self.config.get("database", {})
    self.database_name = db_config.get("database")
    self.connector = DatabaseConnector(db_config)  # ← 立即连接数据库

    # 元数据提取器
    self.extractor = MetadataExtractor(self.connector)
```

**修改方案（方案A：条件初始化）**：
```python
def _init_components(self):
    """初始化所有组件"""
    # 数据库连接器（仅非 md 步骤初始化）
    db_config = self.config.get("database", {})
    self.database_name = db_config.get("database")

    # md 步骤不需要数据库连接
    self.connector = None
    self.extractor = None

    # 其他组件初始化...

def _ensure_connector(self):
    """延迟初始化数据库连接器（仅在需要时）"""
    if self.connector is None:
        db_config = self.config.get("database", {})
        self.connector = DatabaseConnector(db_config)
        self.extractor = MetadataExtractor(self.connector)
```

**在 generate() 中调用**：
```python
def generate(self, ...):
    result = GenerationResult(success=True)
    self.active_step = self._normalize_step(step)
    self.active_formats = self._resolve_formats_for_step(self.active_step)
    logger.info(f"执行步骤: {self.active_step}")

    try:
        # 测试数据库连接（md 步骤跳过）
        if self.active_step != "md":
            self._ensure_connector()  # ← 延迟初始化
            if not self.connector.test_connection():
                result.success = False
                result.add_error("数据库连接失败")
                return result
        else:
            logger.info("md 步骤跳过数据库连接（从 DDL 文件读取）")

        # ... 其他处理逻辑 ...

    except Exception as e:
        logger.error(f"元数据生成过程出错: {e}")
        result.success = False
        result.add_error(str(e))

    finally:
        # 关闭数据库连接（防空检查）
        if self.connector is not None:  # ← 新增：防止 md 步骤报错
            self.connector.close()

    return result
```

**注意**：
- 所有使用 `self.connector` 的地方都需先判断 `self.active_step != "md"` 或调用 `_ensure_connector()`
- `finally` 块必须增加 `if self.connector is not None` 检查

---

### 修改② - `generator.py`：从 DDL 目录推断 schemas（避免查询数据库）

**位置**：`metaweave/core/metadata/generator.py:172-178`

**问题**：当配置文件 `database.schemas` 为空且 CLI 未指定 `--schemas` 时，会调用 `connector.get_schemas()` 查询数据库。

**当前代码**：
```python
# 获取要处理的 schema 列表
if schemas is None:
    schemas = self.config.get("database", {}).get("schemas", [])

if not schemas:
    schemas = self.connector.get_schemas()  # ← md 步骤也会查库
```

**修改后**：
```python
# 获取要处理的 schema 列表
if schemas is None:
    schemas = self.config.get("database", {}).get("schemas", [])

if not schemas:
    if self.active_step == "md":
        # md 步骤：从 DDL 目录推断 schemas
        schemas = self._infer_schemas_from_ddl_dir()
        if not schemas:
            result.success = False
            result.add_error(
                "md 步骤无法推断 schemas：DDL 目录为空且配置文件未指定 database.schemas\n"
                "请在配置文件中设置 database.schemas 或先执行 --step ddl"
            )
            return result
    else:
        self._ensure_connector()
        schemas = self.connector.get_schemas()
```

**新增辅助方法**：
```python
def _infer_schemas_from_ddl_dir(self) -> List[str]:
    """从 DDL 目录推断 schemas（用于 md 步骤）

    仅支持严格的 {database}.{schema}.{table}.sql 文件名格式。
    schema 或 table 名称包含特殊字符（如 '.'）的文件会被跳过并警告。

    Returns:
        schema 列表（去重）
    """
    ddl_dir = self.formatter.output_dir / "ddl"
    if not ddl_dir.exists():
        logger.warning(f"DDL 目录不存在: {ddl_dir}")
        return []

    # DDL 文件格式: {database}.{schema}.{table}.sql
    database_name = self.database_name
    pattern = f"{database_name}.*.*.sql"  # glob 用于粗过滤（匹配 db.*.*.sql）
    schemas = set()

    # 注意：glob 只是粗过滤，最终以 stem 校验为准
    for ddl_file in ddl_dir.glob(pattern):
        # 解析文件名 stem（去除 .sql）: store_db.public.employee
        parts = ddl_file.stem.split(".")
        if len(parts) == 3:  # 严格校验 stem 为 3 段：db.schema.table
            schema = parts[1]
            schemas.add(schema)
        else:
            logger.warning(f"DDL 文件 stem 格式异常，跳过: {ddl_file.name}（期望 stem 3 段，实际 {len(parts)} 段）")

    schema_list = sorted(schemas)
    logger.info(f"从 DDL 目录推断出 {len(schema_list)} 个 schema: {schema_list}")
    return schema_list
```

---

### 修改③ - `generator.py`：从 DDL 目录枚举表（而非查询数据库）

**位置**：`metaweave/core/metadata/generator.py:213-231`

**问题**：当前 `_get_tables_to_process()` 调用 `connector.get_tables(schema)` 查询数据库枚举表。

**当前代码**：
```python
def _get_tables_to_process(
    self,
    schemas: List[str],
    tables: Optional[List[str]]
) -> List[tuple]:
    """获取要处理的表列表"""
    all_tables = []
    exclude_patterns = self.config.get("database", {}).get("exclude_tables", [])

    for schema in schemas:
        schema_tables = self.connector.get_tables(schema)  # ← 查询数据库

        for table in schema_tables:
            # 如果指定了表名列表，只处理列表中的表
            if tables and table not in tables:
                continue

            # 检查是否在排除列表中
            excluded = False
            for pattern in exclude_patterns:
                # ... 排除逻辑 ...
```

**修改后**：
```python
def _get_tables_to_process(
    self,
    schemas: List[str],
    tables: Optional[List[str]]
) -> List[tuple]:
    """获取要处理的表列表"""
    all_tables = []
    exclude_patterns = self.config.get("database", {}).get("exclude_tables", [])

    for schema in schemas:
        # ========== md 步骤：从 DDL 目录枚举表 ==========
        if self.active_step == "md":
            schema_tables = self._get_tables_from_ddl_dir(schema)
        else:
            schema_tables = self.connector.get_tables(schema)
        # ==============================================

        for table in schema_tables:
            # 如果指定了表名列表，只处理列表中的表
            if tables and table not in tables:
                continue

            # 检查是否在排除列表中
            excluded = False
            for pattern in exclude_patterns:
                # ... 排除逻辑 ...
```

**新增辅助方法**（添加到 `generator.py` 类中）：
```python
def _get_tables_from_ddl_dir(self, schema: str) -> List[str]:
    """从 DDL 目录扫描表名（用于 md 步骤）

    仅支持严格的 {database}.{schema}.{table}.sql 文件名格式。
    table 名称包含特殊字符（如 '.'）的文件会被跳过并警告。

    Args:
        schema: schema 名称

    Returns:
        表名列表
    """
    ddl_dir = self.formatter.output_dir / "ddl"
    if not ddl_dir.exists():
        logger.warning(f"DDL 目录不存在: {ddl_dir}")
        return []

    # DDL 文件格式: {database}.{schema}.{table}.sql
    database_name = self.database_name
    pattern = f"{database_name}.{schema}.*.sql"  # glob 用于粗过滤

    tables = []
    # 注意：glob 只是粗过滤，最终以 stem 校验为准
    for ddl_file in ddl_dir.glob(pattern):
        # 解析文件名 stem（去除 .sql）: store_db.public.employee → employee
        parts = ddl_file.stem.split(".")
        if len(parts) == 3:  # 严格校验 stem 为 3 段：db.schema.table
            table_name = parts[2]
            tables.append(table_name)
            logger.debug(f"从 DDL 文件发现表: {schema}.{table_name}")
        else:
            logger.warning(f"DDL 文件 stem 格式异常，跳过: {ddl_file.name}（期望 stem 3 段，实际 {len(parts)} 段）")

    logger.info(f"从 DDL 目录扫描到 {len(tables)} 张表: {schema}.*")
    return tables
```

---

### 修改④ - `generator.py`：md 使用独立的 file-only 处理路径（避免误伤 json）

**位置**：`metaweave/core/metadata/generator.py:305-314`

**问题**：如果让 json 和 md 共用 `_process_table_from_ddl()`，为 md 添加的 file-only 逻辑（跳过 COUNT/采样/画像）会破坏 json 步骤的功能。

**设计原则（B+ 方案：硬隔离）**：
- `_process_table_from_ddl()`：保持不变，仅供 json 使用（继续 COUNT/采样/画像）
- `_process_table_from_ddl_for_md()`：新增 md 专用方法（file-only，不查库）
- 清晰的路由边界，避免相互影响

**当前代码**：
```python
def _process_table(
    self,
    schema: str,
    table: str,
    result: GenerationResult
):
    if self.active_step == "json":
        self._process_table_from_ddl(schema, table, result)
    else:
        self._process_table_from_db(schema, table, result)  # ← md 走这里（重新查库）
```

**修改后（B+ 方案）**：
```python
def _process_table(
    self,
    schema: str,
    table: str,
    result: GenerationResult
):
    if self.active_step == "json":
        # json 步骤：从 DDL 读取，但执行 COUNT/采样/画像（需要数据库）
        self._process_table_from_ddl(schema, table, result)
    elif self.active_step == "md":
        # md 步骤：完全 file-only，不访问数据库
        self._process_table_from_ddl_for_md(schema, table, result)
    else:
        # ddl/rel 等其他步骤：直接查库
        self._process_table_from_db(schema, table, result)
```

**关键改进**：
- ✅ json 和 md 完全隔离，互不影响
- ✅ json 的 COUNT/画像逻辑保持不变
- ✅ md 的 file-only 逻辑不会误伤 json

---

### 修改⑤ - `generator.py`：新增 md 专用的 file-only 处理方法

**位置**：`metaweave/core/metadata/generator.py`（新增方法）

**设计目标**：
- 创建独立的 `_process_table_from_ddl_for_md()` 方法
- 完全 file-only：只读 DDL 文件，不执行任何数据库查询
- 不影响 json 步骤的现有逻辑

**关键特性**：
1. **只读 DDL**：从 DDL 文件解析元数据和样例数据
2. **不查库**：跳过 COUNT、采样、数据库连接等所有查询
3. **简化画像**：跳过列画像、逻辑主键、表画像（md 不需要）
4. **补全注释**：仅在注释缺失时调用 LLM（使用缓存）

**新增方法（完整代码）**：
```python
def _process_table_from_ddl_for_md(
    self,
    schema: str,
    table: str,
    result: GenerationResult
):
    """md 专用：从 DDL 文件生成 Markdown（file-only，不访问数据库）

    与 _process_table_from_ddl() 的区别：
    - 不执行 COUNT 查询（md 不展示行数）
    - 不执行列画像/逻辑主键/表画像（md 不需要）
    - 不采样数据库（使用 DDL 的 sample_records）
    - 完全 file-only，零数据库访问
    """
    logger.info(f"开始处理表 (Markdown): {schema}.{table}")

    # 1. 从 DDL 文件加载元数据
    try:
        parsed = self._get_ddl_loader().load_table(schema, table)
        metadata = parsed.metadata
        metadata.database = self.database_name
    except DDLLoaderError as exc:
        logger.error(f"DDL 解析失败 ({schema}.{table}): {exc}")
        result.failed_tables += 1
        result.add_error(f"{schema}.{table}: {exc}")
        return

    # 2. 将 DDL sample_records 转换为 DataFrame（仅用于注释生成辅助）
    sample_data = None
    if parsed.sample_records:
        import pandas as pd
        records_data = [rec.get("data", {}) for rec in parsed.sample_records if rec.get("data")]
        if records_data:
            sample_data = pd.DataFrame(records_data)
            logger.info(f"使用 DDL 样例数据: {schema}.{table}, {len(sample_data)} 行")
        else:
            logger.warning(f"DDL 样例数据为空: {schema}.{table}")
    else:
        logger.warning(f"DDL 无样例数据: {schema}.{table}")

    # 3. 补全缺失的注释（可选，使用 LLM + 缓存）
    if self.comment_enabled:
        comment_count = self.comment_generator.enrich_metadata_with_comments(
            metadata,
            sample_data  # 辅助 LLM 理解字段含义
        )
        if comment_count > 0:
            result.generated_comments += comment_count
            logger.info(f"补全注释: {schema}.{table}, {comment_count} 个")

    # 4. 跳过列统计、画像、逻辑主键（md 不需要）
    # 注意：
    # - md 输出不展示列统计信息
    # - md 输出不展示画像/逻辑主键
    # - 保持字段为空值，避免序列化错误
    metadata.column_profiles = {}
    metadata.candidate_logical_primary_keys = []
    metadata.table_profile = None

    # 5. 格式化输出（仅生成 markdown）
    output_files = self.formatter.format_and_save(
        metadata,
        sample_data,  # 用于提取示例值
        formats_override=["markdown"]  # 仅输出 md 格式
    )
    for file_path in output_files.values():
        result.add_output_file(file_path)

    # 注意：不需要 result.processed_tables += 1
    # 外层框架（_process_tables_sequential/parallel）已统计
    logger.info(f"Markdown 生成完成: {schema}.{table}")
```

**关键改动点**：
- **完全独立**：新方法与 `_process_table_from_ddl()` 无共享逻辑，互不影响
- **零数据库访问**：不执行 COUNT、采样、连接检查等任何查询
- **简化输出**：只生成 markdown，跳过 json/ddl 等格式
- **跳过画像**：`column_profiles = {}`、`candidate_logical_primary_keys = []`、`table_profile = None`
- **类型正确**：使用 `{}`（Dict）而非 `[]`（List）避免序列化错误
- **优雅降级**：DDL 无样例数据时仅警告，不影响 markdown 生成

**与 `_process_table_from_ddl()` 的对比**：

| 特性 | `_process_table_from_ddl()` (json) | `_process_table_from_ddl_for_md()` (md) |
|------|-----------------------------------|----------------------------------------|
| 数据库访问 | ✅ 需要（COUNT 查询） | ❌ 零访问 |
| 列统计 | ✅ 计算 | ❌ 跳过 |
| 列画像 | ✅ 生成 | ❌ 跳过 |
| 逻辑主键 | ✅ 检测 | ❌ 跳过 |
| 表画像 | ✅ 生成 | ❌ 跳过 |
| 输出格式 | json | markdown |
| 样例数据来源 | DDL | DDL |

**重要说明**：
- ✅ `_process_table_from_ddl()` **保持不变**，json 步骤继续使用
- ✅ `_process_table_from_ddl_for_md()` **全新方法**，仅 md 使用
- ✅ 两者**完全隔离**，修改 md 不会影响 json

---

### 修改⑥ - `ddl_loader.py`：添加辅助方法转换样例数据

**位置**：`metaweave/core/metadata/ddl_loader.py`

**背景**：当前 `ParsedDDL.sample_records` 是 `List[Dict]`，需要提供便捷方法转换为 DataFrame。

**新增辅助方法**（可选，也可以在 generator.py 中直接转换）：
```python
import pandas as pd

class DDLLoader:
    # ... 现有代码 ...

    @staticmethod
    def sample_records_to_dataframe(sample_records: List[Dict]) -> Optional[pd.DataFrame]:
        """将 sample_records 转换为 DataFrame

        Args:
            sample_records: DDL 中的样例数据 [{"label": "...", "data": {...}}, ...]

        Returns:
            DataFrame，如果无有效数据则返回 None
        """
        if not sample_records:
            return None

        # 提取所有记录的 data 字段
        records_data = [
            rec.get("data", {})
            for rec in sample_records
            if rec.get("data")
        ]

        if not records_data:
            return None

        return pd.DataFrame(records_data)
```

**注意**：这个方法是可选的，也可以直接在 `generator.py` 中进行转换（如修改⑤所示）。

---

### 修改⑦ - `metadata_cli.py`：添加 DDL 依赖检查

**位置**：`metaweave/cli/metadata_cli.py:523-552`

**当前代码**（md 可以直接执行）：
```python
# 初始化生成器
generator = MetadataGenerator(config_path)

# 解析 schemas 和 tables
schema_list = None
if schemas:
    schema_list = [s.strip() for s in schemas.split(",")]
    click.echo(f"🎯 指定 Schema: {schema_list}")
```

**修改后**（添加 DDL 依赖检查）：
```python
# ========== 新增：md 步骤依赖检查 ==========
if step == "md":
    from pathlib import Path
    from services.config_loader import load_config

    # 加载配置获取真实的 output_dir
    loaded_config = load_config(config_path)
    output_dir = Path(loaded_config.get("output", {}).get("output_dir", "output"))
    if not output_dir.is_absolute():
        from metaweave.utils.file_utils import get_project_root
        output_dir = get_project_root() / output_dir

    ddl_dir = output_dir / "ddl"

    if not ddl_dir.exists():
        raise click.UsageError(
            f"❌ --step md 依赖 DDL 文件，但 DDL 目录不存在: {ddl_dir}\n"
            f"请先执行: metaweave metadata --config {config} --step ddl"
        )

    # 检查是否有 DDL 文件（文件名格式：{database}.{schema}.{table}.sql）
    ddl_files = list(ddl_dir.glob("*.sql"))
    if not ddl_files:
        raise click.UsageError(
            f"❌ --step md 依赖 DDL 文件，但 DDL 目录为空: {ddl_dir}\n"
            f"请先执行: metaweave metadata --config {config} --step ddl"
        )

    click.echo(f"✅ 检测到 {len(ddl_files)} 个 DDL 文件，继续执行...")
# ==========================================

# 初始化生成器
generator = MetadataGenerator(config_path)

# 解析 schemas 和 tables
schema_list = None
if schemas:
    schema_list = [s.strip() for s in schemas.split(",")]
    click.echo(f"🎯 指定 Schema: {schema_list}")
```

**改进点**：
- 从配置文件读取 `output_dir`，而不是硬编码
- 正确处理相对路径和绝对路径
- 变量命名清晰：`loaded_config`（字典）vs `config`（CLI 参数字符串）

**重要说明**：
- 错误提示中的 `{config}` 是 CLI 参数（字符串路径，如 `"configs/metadata_config.yaml"`）
- 代码中的 `loaded_config` 是加载后的配置字典
- 两者不可混用：f-string 中使用 `{config}` 会正确显示配置文件路径

---

### 修改⑧ - `CLAUDE.md`：更新文档

**位置**：`CLAUDE.md` 的 "Processing Pipeline" 和 "Database Access Requirements" 部分

**当前描述**：
```markdown
**Independent**:
- `md` - Generate Markdown documentation directly from DB
```

**修改后**：
```markdown
**Standard Track (Rule-based)**:
1. `ddl` - Extract table structures from DB → `output/ddl/*.sql`
2. `json` - Generate data profiles from DDL + DB sampling → `output/json/*.json`
3. `md` - Generate Markdown documentation from DDL + LLM comment enrichment → `output/md/*.md`
4. `rel` - Discover relationships using algorithms + DB sampling → `output/rel/*.json`
5. `cql` - Generate Neo4j CQL scripts (file-only, no DB access) → `output/cql/*.cypher`
```

**Database Access Requirements** 部分更新：
```markdown
### Database Access Requirements

**Database access by step**:

- `ddl` - Queries table structures, constraints, indexes; samples data for comments
- `json` - Reads DDL files; executes COUNT queries and samples data for statistics
- `md` - Reads DDL files; **does NOT access database** (all data from DDL)
- `rel` - Samples data for relationship scoring (inclusion rate, Jaccard index)
- `rel_llm` - Same sampling as `rel` for validation
- `cql`/`cql_llm` - File-only processing, no database access

**Step Dependencies**:
- `json` depends on `ddl` (reads `output/ddl/{database}.{schema}.{table}.sql`)
- `md` depends on `ddl` (reads `output/ddl/{database}.{schema}.{table}.sql`)
- `cql`/`cql_llm` depend on `json` + `rel`/`rel_llm` (reads JSON + relationship files)
```

**运行示例** 部分添加：
```markdown
### Running MetaWeave

```bash
# Recommended execution order
uv run metaweave metadata --config configs/metadata_config.yaml --step ddl
uv run metaweave metadata --config configs/metadata_config.yaml --step md
```
```

---

## 配置参数说明

### `comment_generation` 配置对 `--step md` 的影响

```yaml
comment_generation:
  enabled: true                 # 是否启用注释生成（md 步骤会调用 LLM 补全缺失注释）
  language: zh                  # 注释语言
  cache_enabled: true           # 是否启用缓存（避免重复调用 LLM）
  cache_file: cache/comment_cache.json
  overwrite_existing: false     # 注意：此参数对 md 步骤无效，仅用于 json_llm 步骤
```

**行为说明**：
- `enabled: true`（默认）：只补全 DDL 中缺失的注释（不会覆盖已有注释）
- `enabled: false`：不调用 LLM，仅使用 DDL 中的原始注释

**重要**：`--step md` 固定为"只补缺失、不覆盖"模式，`overwrite_existing` 参数对 md 步骤不生效。

---

## 改造后的执行流程

### 推荐执行顺序

```bash
# 步骤1: 生成 DDL（基准数据）
uv run metaweave metadata --config configs/metadata_config.yaml --step ddl
# - 从数据库提取元数据
# - 调用 LLM 生成缺失注释（保存到缓存）
# - 采样数据并写入 DDL 的 /* SAMPLE_RECORDS */ 块
# - 输出：output/ddl/{database}.{schema}.{table}.sql

# 步骤2: 生成 Markdown（文档）
uv run metaweave metadata --config configs/metadata_config.yaml --step md
# - 从 DDL 文件读取元数据（包括结构、约束、注释、样例数据）
# - 解析 /* SAMPLE_RECORDS */ 并转换为 DataFrame
# - 从缓存读取注释（如缺失则调用 LLM）
# - 输出：output/md/{database}.{schema}.{table}.md（不包含行数信息）
# - 注意：完全不访问数据库
```

### 数据一致性保证

| 维度 | DDL | Markdown |
|------|-----|----------|
| 表结构 | 数据库查询（T1） | **DDL 文件**（T1） |
| 约束/索引 | 数据库查询（T1） | **DDL 文件**（T1） |
| 注释 | 数据库 + LLM + 缓存 | **DDL 文件** + LLM（缺失时）+ 缓存 |
| 样例数据 | 数据库采样 | **DDL 文件**（`/* SAMPLE_RECORDS */`） |

**关键改进**：
- ✅ Markdown 的所有数据来源统一（完全从 DDL 读取）
- ✅ 注释通过缓存机制保持一致
- ✅ Markdown 使用 DDL 中的样例数据，完全避免数据库访问
- ✅ 保证 T1 时刻的数据一致性（DDL 和 Markdown 描述同一版本）

---

## 向后兼容性

### 对现有功能的影响

**`--step md`**：
- ⚠️ **破坏性变更**：不再独立执行，必须先执行 `--step ddl`
- ✅ 好处：结构/约束/注释一致性保证，避免与 DDL 不一致

### 迁移建议

**升级前**（旧行为）：
```bash
# md 可以独立执行
uv run metaweave metadata --config config.yaml --step md
```

**升级后**（新行为）：
```bash
# 必须先执行 ddl
uv run metaweave metadata --config config.yaml --step ddl
uv run metaweave metadata --config config.yaml --step md
```

---

## 测试验证

### 验证一致性

```bash
# 1. 生成所有输出
uv run metaweave metadata --config configs/metadata_config.yaml --step ddl
uv run metaweave metadata --config configs/metadata_config.yaml --step md

# 2. 检查样例数据格式
grep -A 20 "SAMPLE_RECORDS" output/ddl/store_db.public.employee.sql

# 3. 手工对比验证
# 检查 DDL 中的表结构
head -n 30 output/ddl/store_db.public.employee.sql

# 检查 Markdown 中的字段列表
head -n 20 output/md/store_db.public.employee.md
```

### 预期结果

**DDL 输出** (`output/ddl/store_db.public.employee.sql`)：
```sql
-- ====================================
-- Database: store_db
-- Table: public.employee
-- Comment: 员工信息表，存储企业员工的基本信息、薪资及所属部门
-- Generated: 2026-01-04 00:00:34
-- ====================================

CREATE TABLE IF NOT EXISTS public.employee (
    emp_id INTEGER NOT NULL,
    emp_name VARCHAR(100) NOT NULL,
    salary DECIMAL(10,2),
    CONSTRAINT employee_pkey PRIMARY KEY (emp_id)
);

COMMENT ON TABLE public.employee IS '员工信息表，存储企业员工的基本信息、薪资及所属部门';
COMMENT ON COLUMN public.employee.emp_id IS '员工唯一标识ID';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.employee",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "emp_id": "1",
        "emp_name": "张三",
        "salary": "8000.0"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "emp_id": "2",
        "emp_name": "李四",
        "salary": "9500.0"
      }
    }
  ]
}
*/
```

**Markdown 输出** (`output/md/store_db.public.employee.md`)：
```markdown
# public.employee（员工信息表，存储企业员工的基本信息、薪资及所属部门）
## 字段列表：
- emp_id (integer(32)) - 员工唯一标识ID [示例: 1, 2]
- emp_name (character varying(100)) - 员工姓名 [示例: 张三, 李四]
- salary (numeric(10,2)) - 月薪，单位为元 [示例: 8000.0, 9500.0]
- dept_id (integer(32)) - 所属部门ID [示例: 1, 2]
## 字段补充说明：
- 主键约束 employee_pkey: emp_id
- 外键约束 dept_id 关联 public.department.dept_id
- 唯一约束 employee_emp_no_key: emp_no
```

**关键点**：示例值内联在字段列表中（来自 DDL 的 `/* SAMPLE_RECORDS */`），格式保持不变。

---

## 实施步骤

1. ✅ 编写修改方案文档（本文档）
2. ⬜ 修改 `generator.py`：
   - 修改①：延迟初始化 DatabaseConnector（新增 `_ensure_connector` 方法）
   - 修改②：从 DDL 目录推断 schemas（新增 `_infer_schemas_from_ddl_dir` 方法）
   - 修改③：从 DDL 目录枚举表（新增 `_get_tables_from_ddl_dir` 方法）
   - 修改④：md 独立路由（路由到 `_process_table_from_ddl_for_md`，**不是** `_process_table_from_ddl`）
   - 修改⑤：新增 `_process_table_from_ddl_for_md` 方法（file-only，不影响 json）
3. ⬜ 修改 `ddl_loader.py`（可选）：添加 `sample_records_to_dataframe` 辅助方法
4. ⬜ 修改 `metadata_cli.py`：添加 DDL 依赖检查
5. ⬜ 更新 `CLAUDE.md`：修改架构说明
6. ⬜ 编写测试用例：验证一致性（重点测试 json 未受影响）
7. ⬜ 更新 README 和示例脚本

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **误伤 json 步骤** | **共用方法导致 json 的 COUNT/画像被破坏** | **采用 B+ 方案：md 独立方法，json 保持不变** |
| **finally 块无防空检查** | **md 步骤 connector 为 None，调用 .close() 报错** | **finally 块增加 `if self.connector is not None` 检查** |
| **双计数 processed_tables** | **并发/串行框架已统计，md 方法内再加导致翻倍** | **删除 md 方法内的 `result.processed_tables += 1`** |
| DDL 解析失败 | md 步骤无法执行 | 完善错误提示，引导用户重新执行 ddl |
| sample_records 为空 | Markdown 示例值显示 "null" | 仅警告，不影响 markdown 生成 |
| DataFrame 转换异常 | 统计计算失败 | 添加异常处理，跳过统计并记录警告 |
| 用户习惯变化 | md 不再独立执行 | 文档说明 + CLI 友好错误提示 |
| column_profiles 类型错误 | 赋值 [] 导致后续 .items() 调用失败 | 使用 {} 而非 [] |
| DatabaseConnector 提前初始化 | md 步骤也会连接数据库 | 延迟初始化，仅在需要时调用 _ensure_connector() |
| schemas 配置为空 | md 步骤调用 get_schemas() 查库 | 从 DDL 目录推断 schemas 或要求配置文件提供 |
| formatter.ddl_dir 不存在 | AttributeError | 使用 formatter.output_dir / "ddl" |

---

## 总结

本次改造让 `--step md` 完全依赖 DDL 文件，采用 **B+ 硬隔离方案**，核心改进：

1. ✅ **硬隔离设计**：md 使用独立的 `_process_table_from_ddl_for_md()` 方法，与 json 完全分离
2. ✅ **保护 json**：`_process_table_from_ddl()` 保持不变，json 的 COUNT/画像逻辑不受影响
3. ✅ **结构一致性**：md 从 DDL 文件读取表结构、约束、索引，避免数据库变更导致的不一致
4. ✅ **注释补全**：md 步骤通过 LLM + 缓存机制补全缺失注释
5. ✅ **样例数据复用**：md 解析 DDL 的 `/* SAMPLE_RECORDS */` 块，完全避免数据库采样
6. ✅ **明确依赖**：通过 CLI 检查强制执行顺序，避免用户误操作
7. ✅ **完全不查库**：md 步骤不访问数据库（包括连接检查、表枚举、COUNT、采样等所有查询）

**关键原则**：
- DDL 是唯一的数据源（Single Source of Truth）
- md 步骤完全不访问数据库（零数据库操作）：
  - 延迟初始化 `DatabaseConnector`（避免 `ConnectionPool(open=True)` 触达数据库）
  - 从 DDL 目录推断 schemas（而非 `get_schemas()` 查库）
  - 从 DDL 目录扫描表名（而非 `get_tables()` 查库）
  - 从 DDL 文件读取元数据（而非查询 information_schema）
  - 不执行 COUNT、采样等任何数据库查询
- LLM 注释通过缓存保证一致性
- 数据类型正确性：`column_profiles = {}`（Dict），而非 `[]`
- 步骤依赖关系明确且可验证
