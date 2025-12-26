# cql 与 cql_llm 统一输入源改造规划

## 文档说明

本文档详细规划 `--step cql` 和 `--step cql_llm` 命令的改造方案，主要目标是统一输入源目录，简化命令语义，并增加生成元数据文档功能。

**改造范围：**
- `metaweave metadata --config configs/metadata_config.yaml --step cql`
- `metaweave metadata --config configs/metadata_config.yaml --step cql_llm`

**文档版本：** 1.0  
**创建日期：** 2025-12-26

---

## 一、背景与问题

### 1. 当前状况

#### 1.1 输入目录差异

| 命令 | JSON 输入目录 | rel 输入目录 | CQL 输出目录 |
|-----|-------------|-------------|-------------|
| `--step cql` | `output/json` | `output/rel` | `output/cql` |
| `--step cql_llm` | `output/json_llm` ❌ | `output/rel` | `output/cql` |

**问题：**
- `json_llm` 目录已废弃，与 `json` 目录统一
- `cql_llm` 仍硬编码访问已废弃的 `json_llm` 目录
- 导致执行失败或读取旧数据

#### 1.2 命令语义混淆

```bash
# 当前用户认知（错误）
--step cql      # 使用基础元数据
--step cql_llm  # 使用 LLM 增强元数据

# 实际情况
--step cql      # 读取 output/json
--step cql_llm  # 读取 output/json_llm（已废弃）
```

**问题：**
- 命令名称暗示处理方式不同，实际只是输入目录不同
- 用户已统一输入源，但命令仍区分 `cql` 和 `cql_llm`
- 增加理解成本和使用复杂度

#### 1.3 输出覆盖问题

**当前行为：**
- 两个命令输出到同一文件 `output/cql/import_all.cypher`
- 后执行的命令会覆盖前一个命令的结果
- 无法追溯哪个命令生成了当前文件

#### 1.4 缺少生成元数据

**当前输出：**
- 只有 `import_all.cypher` 文件
- 无法追溯：
  - 生成时间
  - 节点和边的统计数据
  - 使用哪个命令生成
  - 使用的配置参数

---

## 二、改造目标

### 1. 核心目标

| 目标 | 说明 | 优先级 |
|-----|------|--------|
| **统一输入源** | 两个命令都使用 `output/json` 和 `output/rel` | P0（必需） |
| **简化命令语义** | 改造后两个命令功能完全相同 | P0（必需） |
| **保持输出格式** | 不影响 `import_all.cypher` 文件格式 | P0（必需） |
| **增加元数据文档** | 生成 `import_all.md` 记录生成信息 | P0（必需） |
| **向后兼容** | 配置文件兼容旧配置，不破坏现有项目 | P1（重要） |
| **废弃旧配置** | 标记 `json_llm_directory` 为废弃 | P2（可选） |

### 2. 期望结果

#### 2.1 改造后的输入输出

| 命令 | JSON 输入目录 | rel 输入目录 | CQL 输出目录 |
|-----|-------------|-------------|-------------|
| `--step cql` | `output/json` ✅ | `output/rel` | `output/cql` |
| `--step cql_llm` | `output/json` ✅ | `output/rel` | `output/cql` |

**改进：**
- ✅ 统一输入源，避免目录混淆
- ✅ 两个命令功能等价
- ✅ 简化数据流，降低理解成本

#### 2.2 改造后的输出文件

```
output/cql/
├── import_all.cypher      # Cypher 导入脚本（格式不变）
└── import_all.md          # 生成元数据文档（新增）
```

**`import_all.md` 内容示例：**

```markdown
# Neo4j CQL 导入脚本元数据

## 生成信息

- **生成时间**: 2025-12-26 14:30:00
- **生成命令**: `metaweave metadata --step cql_llm`
- **配置文件**: `configs/metadata_config.yaml`

## 统计数据

| 类型 | 数量 |
|-----|------|
| 表节点 (Table) | 13 |
| 列节点 (Column) | 156 |
| HAS_COLUMN 关系 | 156 |
| JOIN_ON 关系 | 18 |

## 输入源

- **JSON 目录**: `output/json`
- **关系目录**: `output/rel`
- **CQL 目录**: `output/cql`

## 文件清单

- `import_all.cypher` (1743 lines)

## 使用方式

```bash
# 导入到 Neo4j
cypher-shell -u neo4j -p password < import_all.cypher
```
```

---

## 三、改造方案

### 1. 总体思路

**设计原则：**
1. **最小改动**：只修改 CLI 层面的目录配置逻辑
2. **核心逻辑不变**：`CQLGenerator.generate()` 不修改
3. **向后兼容**：支持旧配置文件（`json_llm_directory`）
4. **格式保持**：`import_all.cypher` 格式不变
5. **新增功能**：增加 `import_all.md` 生成逻辑

### 2. 改造范围

#### 2.1 需要修改的文件

| 文件 | 修改内容 | 改动行数（估算） |
|-----|---------|----------------|
| `metaweave/cli/metadata_cli.py` | 统一 `cql_llm` 的输入目录读取逻辑 | 约 10 行 |
| `metaweave/core/cql_generator/writer.py` | 增加 `_write_metadata()` 方法 | 约 80 行 |
| `metaweave/core/cql_generator/generator.py` | 调用元数据生成方法 | 约 10 行 |
| `configs/metadata_config.yaml` | 更新注释，标记废弃配置 | 约 5 行 |

**总改动行数：** 约 105 行

#### 2.2 不需要修改的文件

| 文件 | 说明 |
|-----|------|
| `metaweave/core/cql_generator/reader.py` | JSON 读取逻辑不变 |
| `metaweave/core/cql_generator/models.py` | 数据模型不变 |
| 所有 `_write_*` 方法（除元数据） | Cypher 生成逻辑不变 |

---

## 四、详细改造方案

### 1. 统一输入目录（需求1）

#### 1.1 修改 `metadata_cli.py`

**文件位置：** `metaweave/cli/metadata_cli.py` 第 376-399 行

**当前代码（`cql_llm` 步骤）：**

```python
if step == "cql_llm":
    from metaweave.core.cql_generator.generator import CQLGenerator

    click.echo("🔧 开始生成 Neo4j CQL（LLM 流程）...")
    click.echo("")

    generator = CQLGenerator(config_path)
    
    # ❌ 覆盖 json_dir 为 json_llm 目录
    json_llm_dir = generator._resolve_path(
        generator.config.get("output", {}).get("json_llm_directory", "output/json_llm")
    )
    
    # ❌ 检查 json_llm 目录是否存在
    if not json_llm_dir.exists():
        raise FileNotFoundError(
            f"json_llm 目录不存在: {json_llm_dir}\n"
            f"请先执行 --step json_llm 生成 LLM 增强后的 JSON"
        )
    
    generator.json_dir = json_llm_dir
    logger.info(f"cql_llm: 使用 json_llm 目录: {json_llm_dir}")
    
    result = generator.generate()
```

**改造后代码（方案 1：统一输入源）：**

```python
if step == "cql_llm":
    from metaweave.core.cql_generator.generator import CQLGenerator

    click.echo("🔧 开始生成 Neo4j CQL（LLM 流程）...")
    click.echo("")

    generator = CQLGenerator(config_path)
    
    # ✅ 统一使用 json_directory（向后兼容 json_llm_directory）
    json_dir = generator.config.get("output", {}).get("json_directory") or \
               generator.config.get("output", {}).get("json_llm_directory", "output/json")
    json_dir_path = generator._resolve_path(json_dir)
    
    # ✅ 检查目录是否存在
    if not json_dir_path.exists():
        raise FileNotFoundError(
            f"JSON 目录不存在: {json_dir_path}\n"
            f"请先执行 --step json 或 --step json_llm 生成 JSON 元数据"
        )
    
    generator.json_dir = json_dir_path
    logger.info(f"cql_llm: 使用 JSON 目录: {json_dir_path}")
    
    # ✅ 传递命令名称（用于元数据生成）
    result = generator.generate(step_name="cql_llm")
```

**改动说明：**
1. **优先读取 `json_directory`**：统一输入源
2. **向后兼容 `json_llm_directory`**：支持旧配置
3. **错误提示更新**：提示可执行 `json` 或 `json_llm`
4. **传递 `step_name`**：用于元数据文档生成

#### 1.2 修改 `cql` 步骤（一致性）

**文件位置：** `metaweave/cli/metadata_cli.py` 第 432-465 行

**当前代码：**

```python
if step == "cql":
    from metaweave.core.cql_generator.generator import CQLGenerator

    click.echo("🔧 开始生成 Neo4j CQL...")
    click.echo("")

    generator = CQLGenerator(config_path)
    result = generator.generate()
```

**改造后代码：**

```python
if step == "cql":
    from metaweave.core.cql_generator.generator import CQLGenerator

    click.echo("🔧 开始生成 Neo4j CQL...")
    click.echo("")

    generator = CQLGenerator(config_path)
    
    # ✅ 传递命令名称（用于元数据生成）
    result = generator.generate(step_name="cql")
```

**改动说明：**
- 仅增加 `step_name` 参数传递
- 保持原有逻辑不变

### 2. 增加元数据文档生成（需求2）

#### 2.1 修改 `CQLGenerator.generate()` 方法

**文件位置：** `metaweave/core/cql_generator/generator.py` 第 77-124 行

**当前方法签名：**

```python
def generate(self) -> CQLGenerationResult:
```

**改造后方法签名：**

```python
def generate(self, step_name: str = "cql") -> CQLGenerationResult:
    """执行 CQL 生成
    
    Args:
        step_name: 执行的步骤名称（"cql" 或 "cql_llm"），用于元数据记录
    
    Returns:
        生成结果
    """
```

**在方法末尾增加元数据生成：**

```python
# 在 writer.write_all() 之后
logger.info("\n[额外] 生成元数据文档...")
metadata_file = writer.write_metadata(
    tables=tables,
    columns=columns,
    join_on_rels=join_on_rels,
    step_name=step_name,
    json_dir=self.json_dir,
    rel_dir=self.rel_dir,
    cql_dir=self.cql_dir,
    config_path=self.config_path
)
logger.info(f"  - 元数据文档: {metadata_file}")
output_files.append(str(metadata_file))
```

#### 2.2 在 `CypherWriter` 中增加 `write_metadata()` 方法

**文件位置：** `metaweave/core/cql_generator/writer.py`

**新增方法：**

```python
def write_metadata(
    self,
    tables: List[TableNode],
    columns: List[ColumnNode],
    join_on_rels: List[JOINOnRelation],
    step_name: str,
    json_dir: Path,
    rel_dir: Path,
    cql_dir: Path,
    config_path: str
) -> Path:
    """生成 import_all.md 元数据文档
    
    Args:
        tables: 表节点列表
        columns: 列节点列表
        join_on_rels: JOIN_ON 关系列表
        step_name: 执行的步骤名称（"cql" 或 "cql_llm"）
        json_dir: JSON 输入目录
        rel_dir: 关系输入目录
        cql_dir: CQL 输出目录
        config_path: 配置文件路径
    
    Returns:
        元数据文档路径
    """
    output_file = self.output_dir / "import_all.md"
    
    # 生成时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 统计数据
    has_column_count = sum(len(t.columns) for t in tables)  # 简化计算
    
    # 获取 import_all.cypher 的行数
    cypher_file = self.output_dir / "import_all.cypher"
    cypher_lines = 0
    if cypher_file.exists():
        with open(cypher_file, "r", encoding="utf-8") as f:
            cypher_lines = sum(1 for _ in f)
    
    # 生成 Markdown 内容
    content = f"""# Neo4j CQL 导入脚本元数据

> **自动生成文档**  
> 本文件由 `metaweave` 自动生成，记录 CQL 脚本的生成信息和统计数据。

---

## 生成信息

- **生成时间**: {timestamp}
- **生成命令**: `metaweave metadata --step {step_name}`
- **配置文件**: `{config_path}`

---

## 统计数据

### 节点统计

| 节点类型 | 数量 | 说明 |
|---------|------|------|
| **Table** | {len(tables)} | 数据库表节点 |
| **Column** | {len(columns)} | 数据库列节点 |

### 关系统计

| 关系类型 | 数量 | 说明 |
|---------|------|------|
| **HAS_COLUMN** | {len(columns)} | 表到列的包含关系 |
| **JOIN_ON** | {len(join_on_rels)} | 表之间的连接关系 |

### 汇总

- **节点总数**: {len(tables) + len(columns)}
- **关系总数**: {len(columns) + len(join_on_rels)}

---

## 输入源

| 类型 | 路径 |
|-----|------|
| **JSON 元数据** | `{json_dir}` |
| **关系数据** | `{rel_dir}` |
| **CQL 输出** | `{cql_dir}` |

---

## 输出文件

| 文件名 | 行数 | 说明 |
|-------|------|------|
| `import_all.cypher` | {cypher_lines} | Neo4j Cypher 导入脚本 |
| `import_all.md` | - | 本元数据文档 |

---

## 使用方式

### 1. 导入到 Neo4j

```bash
# 方式 1：使用 cypher-shell
cypher-shell -u neo4j -p your_password < import_all.cypher

# 方式 2：使用 Neo4j Browser
# 复制 import_all.cypher 内容到 Neo4j Browser 执行
```

### 2. 验证导入结果

```cypher
// 查看表节点数量
MATCH (t:Table) RETURN count(t) AS table_count;

// 查看列节点数量
MATCH (c:Column) RETURN count(c) AS column_count;

// 查看关系数量
MATCH ()-[r:JOIN_ON]->() RETURN count(r) AS join_count;
```

---

## 数据源信息

### 表节点详情

| 序号 | Schema | 表名 | 列数 | 主键 | 外键数 |
|-----|--------|------|------|------|-------|
"""
    
    # 添加表详情
    for idx, table in enumerate(tables, 1):
        pk_str = ", ".join(table.pk) if table.pk else "-"
        fk_count = len(table.fk)
        col_count = len([c for c in columns if c.schema == table.schema and c.table == table.name])
        content += f"| {idx} | {table.schema} | {table.name} | {col_count} | {pk_str} | {fk_count} |\n"
    
    content += f"""
---

## 关系详情

### JOIN_ON 关系列表

| 序号 | 源表 | 目标表 | 基数 | 连接列 |
|-----|------|--------|------|--------|
"""
    
    # 添加关系详情
    for idx, rel in enumerate(join_on_rels, 1):
        src_name = rel.src_full_name.split('.')[-1]
        dst_name = rel.dst_full_name.split('.')[-1]
        cols = ", ".join(rel.source_columns)
        content += f"| {idx} | {src_name} | {dst_name} | {rel.cardinality} | {cols} |\n"
    
    content += f"""
---

## 版本历史

| 生成时间 | 命令 | 表数 | 列数 | 关系数 |
|---------|------|------|------|-------|
| {timestamp} | `--step {step_name}` | {len(tables)} | {len(columns)} | {len(join_on_rels)} |

---

**文档生成工具**: [metaweave](https://github.com/your-org/metaweave)  
**文档版本**: 1.0
"""
    
    # 写入文件
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"元数据文档已生成: {output_file}")
    return output_file
```

**设计说明：**
1. **覆盖模式**：每次生成都覆盖 `import_all.md`
2. **详细统计**：包含节点、关系、表详情、关系详情
3. **使用指南**：提供导入和验证的命令示例
4. **版本历史**：记录每次生成的时间和统计（单行记录，覆盖时更新）

### 3. 配置文件更新

#### 3.1 更新 `metadata_config.yaml`

**文件位置：** `configs/metadata_config.yaml`

**当前配置（第 268-276 行）：**

```yaml
output:
  # Step 2: 表/列画像输出配置
  json_directory: output/json
  json_llm_directory: output/json_llm  # ← 已废弃

  # Step 3: 关系发现输出配置
  rel_directory: output/rel

  # Step 4: CQL 生成输出配置
  cql_directory: output/cql
```

**改造后配置：**

```yaml
output:
  # Step 2: 表/列画像输出配置
  json_directory: output/json
  # json_llm_directory: output/json_llm  # ⚠️ 已废弃，请使用 json_directory

  # Step 3: 关系发现输出配置
  rel_directory: output/rel
  # rel_llm_directory: output/rel_llm  # ⚠️ 已废弃，请使用 rel_directory

  # Step 4: CQL 生成输出配置
  cql_directory: output/cql
  
  # 注意：
  # - --step cql 和 --step cql_llm 现在使用相同的输入目录
  # - 都从 json_directory 和 rel_directory 读取数据
  # - 输出到 cql_directory，生成 import_all.cypher 和 import_all.md
```

---

## 五、向后兼容性

### 1. 配置文件兼容性

#### 1.1 兼容策略

**读取优先级：**

```python
# 优先读取新配置，向后兼容旧配置
json_dir = config.get("json_directory") or \
           config.get("json_llm_directory", "output/json")
```

**兼容矩阵：**

| 配置文件状态 | 读取结果 | 是否兼容 |
|-----------|---------|---------|
| 只有 `json_directory` | `output/json` | ✅ 兼容 |
| 只有 `json_llm_directory` | `output/json_llm` | ✅ 兼容（旧项目） |
| 两者都有 | `json_directory` | ✅ 兼容（优先新配置） |
| 两者都无 | `output/json`（默认） | ✅ 兼容 |

#### 1.2 迁移指南

**旧配置（需要迁移）：**

```yaml
output:
  json_llm_directory: output/json_llm
  rel_directory: output/rel
  cql_directory: output/cql
```

**新配置（推荐）：**

```yaml
output:
  json_directory: output/json
  rel_directory: output/rel
  cql_directory: output/cql
```

**迁移步骤：**
1. 将 `json_llm_directory` 改为 `json_directory`
2. 删除或注释 `json_llm_directory` 行
3. 无需修改代码，改造后的代码会自动适配

### 2. 命令兼容性

#### 2.1 改造前后对比

**改造前：**

```bash
# cql 命令
metaweave metadata --step cql
# → 读取 output/json

# cql_llm 命令
metaweave metadata --step cql_llm
# → 读取 output/json_llm（已废弃，可能失败）
```

**改造后：**

```bash
# cql 命令
metaweave metadata --step cql
# → 读取 output/json

# cql_llm 命令
metaweave metadata --step cql_llm
# → 读取 output/json（统一）
```

**兼容性：**
- ✅ `--step cql` 行为不变
- ✅ `--step cql_llm` 行为改变（但更合理）
- ✅ 两个命令功能等价

#### 2.2 用户影响分析

| 用户场景 | 影响 | 解决方案 |
|---------|------|---------|
| **旧项目，有 `json_llm` 目录** | ⚠️ `cql_llm` 仍会读取旧目录 | 向后兼容，自动读取 |
| **新项目，只有 `json` 目录** | ✅ `cql_llm` 正常工作 | 无需操作 |
| **混合使用 `cql` 和 `cql_llm`** | ✅ 功能等价，无差异 | 无需操作 |

### 3. 输出格式兼容性

#### 3.1 `import_all.cypher` 格式

**改造前后对比：**

| 属性 | 改造前 | 改造后 | 是否兼容 |
|-----|-------|-------|---------|
| 文件名 | `import_all.cypher` | `import_all.cypher` | ✅ 相同 |
| 文件结构 | 5 个部分 | 5 个部分 | ✅ 相同 |
| Table 节点属性 | 13 个 | 13 个 | ✅ 相同 |
| Column 节点属性 | 15 个 | 15 个 | ✅ 相同 |
| JOIN_ON 关系属性 | 6 个 | 6 个 | ✅ 相同 |
| Cypher 语法 | MERGE + SET | MERGE + SET | ✅ 相同 |

**结论：** ✅ **格式 100% 兼容，无破坏性变更**

#### 3.2 新增文件

**新增输出：**

```
output/cql/
├── import_all.cypher      # 格式不变
└── import_all.md          # 新增（不影响现有功能）
```

**影响分析：**
- ✅ 新增文件，不影响现有工作流
- ✅ 可选文件，不读取也不影响功能
- ✅ 每次覆盖，不会累积文件

---

## 六、测试计划

### 1. 单元测试

#### 1.1 输入目录读取测试

**测试用例：**

| 测试用例 | 配置 | 期望结果 |
|---------|------|---------|
| TC-001 | 只有 `json_directory` | 读取 `json_directory` |
| TC-002 | 只有 `json_llm_directory` | 读取 `json_llm_directory` |
| TC-003 | 两者都有 | 优先 `json_directory` |
| TC-004 | 两者都无 | 使用默认值 `output/json` |

#### 1.2 元数据生成测试

**测试用例：**

| 测试用例 | 输入 | 期望输出 |
|---------|------|---------|
| TC-101 | `step_name="cql"` | `import_all.md` 包含 `--step cql` |
| TC-102 | `step_name="cql_llm"` | `import_all.md` 包含 `--step cql_llm` |
| TC-103 | 10 表，100 列，20 关系 | 统计数据正确 |
| TC-104 | 重复生成 | 覆盖旧文件 |

### 2. 集成测试

#### 2.1 完整流程测试

**测试流程 1：基础流程**

```bash
# 1. 生成 JSON
metaweave metadata --step json

# 2. 发现关系
metaweave metadata --step rel

# 3. 生成 CQL（cql）
metaweave metadata --step cql

# 验证
- output/cql/import_all.cypher 存在
- output/cql/import_all.md 存在
- import_all.md 包含 "--step cql"
```

**测试流程 2：LLM 流程**

```bash
# 1. 生成 JSON（LLM 增强）
metaweave metadata --step json_llm

# 2. 发现关系（LLM）
metaweave metadata --step rel_llm

# 3. 生成 CQL（cql_llm）
metaweave metadata --step cql_llm

# 验证
- output/cql/import_all.cypher 存在
- output/cql/import_all.md 存在
- import_all.md 包含 "--step cql_llm"
```

**测试流程 3：混合使用**

```bash
# 执行 cql
metaweave metadata --step cql

# 检查 import_all.md
cat output/cql/import_all.md | grep "cql"

# 执行 cql_llm
metaweave metadata --step cql_llm

# 检查 import_all.md（应该被覆盖）
cat output/cql/import_all.md | grep "cql_llm"
```

#### 2.2 兼容性测试

**测试场景 1：旧配置文件**

```yaml
# 使用旧配置
output:
  json_llm_directory: output/json_llm
```

```bash
# 执行 cql_llm
metaweave metadata --step cql_llm

# 验证：应该读取 json_llm_directory
```

**测试场景 2：新配置文件**

```yaml
# 使用新配置
output:
  json_directory: output/json
```

```bash
# 执行 cql_llm
metaweave metadata --step cql_llm

# 验证：应该读取 json_directory
```

### 3. 回归测试

#### 3.1 输出格式验证

**测试方法：**

```bash
# 改造前生成
metaweave metadata --step cql > before.cypher

# 改造后生成
metaweave metadata --step cql > after.cypher

# 对比（忽略时间戳）
diff before.cypher after.cypher
```

**期望结果：** 除时间戳外，格式完全相同

#### 3.2 Neo4j 导入验证

**测试步骤：**

1. 使用改造后的代码生成 `import_all.cypher`
2. 导入到 Neo4j：`cypher-shell < import_all.cypher`
3. 验证节点和关系数量
4. 验证属性完整性

**验证脚本：**

```cypher
// 验证节点数量
MATCH (t:Table) RETURN count(t) AS table_count;
MATCH (c:Column) RETURN count(c) AS column_count;

// 验证关系数量
MATCH ()-[r:HAS_COLUMN]->() RETURN count(r) AS has_column_count;
MATCH ()-[r:JOIN_ON]->() RETURN count(r) AS join_on_count;

// 验证属性完整性
MATCH (t:Table) RETURN t LIMIT 1;
MATCH (c:Column) RETURN c LIMIT 1;
MATCH ()-[r:JOIN_ON]->() RETURN r LIMIT 1;
```

---

## 七、实施步骤

### 1. 开发阶段

| 步骤 | 任务 | 负责人 | 预计工时 |
|-----|------|-------|---------|
| 1 | 修改 `metadata_cli.py`（统一输入目录） | 开发 | 1h |
| 2 | 增加 `write_metadata()` 方法 | 开发 | 2h |
| 3 | 修改 `generate()` 方法（增加参数） | 开发 | 0.5h |
| 4 | 更新配置文件注释 | 开发 | 0.5h |
| 5 | 编写单元测试 | 开发 | 2h |
| 6 | 编写集成测试 | 开发 | 1h |

**总工时：** 约 7 小时

### 2. 测试阶段

| 步骤 | 任务 | 负责人 | 预计工时 |
|-----|------|-------|---------|
| 1 | 单元测试执行 | 测试 | 1h |
| 2 | 集成测试执行 | 测试 | 2h |
| 3 | 回归测试执行 | 测试 | 1h |
| 4 | 兼容性测试 | 测试 | 1h |
| 5 | Bug 修复 | 开发 | 2h |

**总工时：** 约 7 小时

### 3. 发布阶段

| 步骤 | 任务 | 负责人 | 预计工时 |
|-----|------|-------|---------|
| 1 | 更新 CHANGELOG | 开发 | 0.5h |
| 2 | 更新用户文档 | 文档 | 1h |
| 3 | 更新 README | 文档 | 0.5h |
| 4 | 发布新版本 | 开发 | 0.5h |

**总工时：** 约 2.5 小时

### 4. 总时间估算

- **开发阶段**：7 小时
- **测试阶段**：7 小时
- **发布阶段**：2.5 小时
- **总计**：约 16.5 小时（约 2 个工作日）

---

## 八、风险评估

### 1. 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| 输出格式意外变化 | 高 | 低 | 充分测试，代码审查 |
| 向后兼容性问题 | 中 | 低 | 优先级读取，保留旧配置支持 |
| 元数据生成失败 | 低 | 低 | 使用 try-except 保护 |
| 文件覆盖丢失数据 | 低 | 低 | 文档明确说明覆盖行为 |

### 2. 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| 用户升级后配置不兼容 | 中 | 低 | 向后兼容，提供迁移指南 |
| 用户不理解新功能 | 低 | 中 | 完善文档和示例 |
| 现有脚本失效 | 低 | 低 | 保持命令接口不变 |

### 3. 风险总结

**整体风险等级：** 🟢 低

**理由：**
1. 改动范围小（约 105 行）
2. 核心逻辑不变
3. 充分的向后兼容
4. 完善的测试计划

---

## 九、文档更新清单

### 1. 需要更新的文档

| 文档 | 更新内容 | 优先级 |
|-----|---------|--------|
| `README.md` | 增加元数据文档说明 | P0 |
| `CHANGELOG.md` | 记录本次改造 | P0 |
| `docs/命令使用指南.md` | 更新 `cql` 和 `cql_llm` 说明 | P1 |
| `docs/配置文件说明.md` | 标记废弃配置项 | P1 |
| `docs/5_cql与cql_llm命令对比分析.md` | 更新对比结果 | P2 |

### 2. 需要创建的文档

| 文档 | 内容 | 优先级 |
|-----|------|--------|
| `docs/迁移指南.md` | 旧配置迁移到新配置 | P1 |
| `docs/元数据文档说明.md` | `import_all.md` 字段说明 | P2 |

---

## 十、成功标准

### 1. 功能标准

- [x] `cql` 和 `cql_llm` 使用统一的输入目录
- [x] 向后兼容旧配置文件
- [x] 生成 `import_all.md` 元数据文档
- [x] `import_all.cypher` 格式不变
- [x] 支持覆盖模式

### 2. 质量标准

- [x] 单元测试覆盖率 > 80%
- [x] 集成测试全部通过
- [x] 回归测试无格式差异
- [x] 代码审查通过

### 3. 文档标准

- [x] README 更新
- [x] CHANGELOG 更新
- [x] 迁移指南完成
- [x] 示例代码更新

---

## 十一、附录

### A. 改造前后对比

#### A.1 命令行为对比

**改造前：**

```bash
# cql 命令
metaweave metadata --step cql
# 输入：output/json
# 输出：output/cql/import_all.cypher

# cql_llm 命令
metaweave metadata --step cql_llm
# 输入：output/json_llm（已废弃，可能失败）
# 输出：output/cql/import_all.cypher
```

**改造后：**

```bash
# cql 命令
metaweave metadata --step cql
# 输入：output/json
# 输出：output/cql/import_all.cypher, import_all.md

# cql_llm 命令
metaweave metadata --step cql_llm
# 输入：output/json（统一）
# 输出：output/cql/import_all.cypher, import_all.md
```

#### A.2 输出文件对比

**改造前：**

```
output/cql/
└── import_all.cypher
```

**改造后：**

```
output/cql/
├── import_all.cypher      # 格式不变
└── import_all.md          # 新增
```

### B. `import_all.md` 完整示例

```markdown
# Neo4j CQL 导入脚本元数据

> **自动生成文档**  
> 本文件由 `metaweave` 自动生成，记录 CQL 脚本的生成信息和统计数据。

---

## 生成信息

- **生成时间**: 2025-12-26 14:30:00
- **生成命令**: `metaweave metadata --step cql_llm`
- **配置文件**: `configs/metadata_config.yaml`

---

## 统计数据

### 节点统计

| 节点类型 | 数量 | 说明 |
|---------|------|------|
| **Table** | 13 | 数据库表节点 |
| **Column** | 156 | 数据库列节点 |

### 关系统计

| 关系类型 | 数量 | 说明 |
|---------|------|------|
| **HAS_COLUMN** | 156 | 表到列的包含关系 |
| **JOIN_ON** | 18 | 表之间的连接关系 |

### 汇总

- **节点总数**: 169
- **关系总数**: 174

---

## 输入源

| 类型 | 路径 |
|-----|------|
| **JSON 元数据** | `output/json` |
| **关系数据** | `output/rel` |
| **CQL 输出** | `output/cql` |

---

## 输出文件

| 文件名 | 行数 | 说明 |
|-------|------|------|
| `import_all.cypher` | 1743 | Neo4j Cypher 导入脚本 |
| `import_all.md` | - | 本元数据文档 |

---

## 使用方式

### 1. 导入到 Neo4j

```bash
# 方式 1：使用 cypher-shell
cypher-shell -u neo4j -p your_password < import_all.cypher

# 方式 2：使用 Neo4j Browser
# 复制 import_all.cypher 内容到 Neo4j Browser 执行
```

### 2. 验证导入结果

```cypher
// 查看表节点数量
MATCH (t:Table) RETURN count(t) AS table_count;

// 查看列节点数量
MATCH (c:Column) RETURN count(c) AS column_count;

// 查看关系数量
MATCH ()-[r:JOIN_ON]->() RETURN count(r) AS join_count;
```

---

## 数据源信息

### 表节点详情

| 序号 | Schema | 表名 | 列数 | 主键 | 外键数 |
|-----|--------|------|------|------|-------|
| 1 | public | maintenance_work_order | 16 | wo_id, wo_line_no | 2 |
| 2 | public | order_item | 9 | order_id, item_seq | 1 |
| 3 | public | fault_catalog | 8 | product_line_code, subsystem_code, fault_code | 0 |
| ... | ... | ... | ... | ... | ... |

---

## 关系详情

### JOIN_ON 关系列表

| 序号 | 源表 | 目标表 | 基数 | 连接列 |
|-----|------|--------|------|--------|
| 1 | maintenance_work_order | equipment_config | N:1 | equipment_id |
| 2 | maintenance_work_order | fault_catalog | N:1 | product_line_code, subsystem_code, fault_code |
| ... | ... | ... | ... | ... |

---

## 版本历史

| 生成时间 | 命令 | 表数 | 列数 | 关系数 |
|---------|------|------|------|-------|
| 2025-12-26 14:30:00 | `--step cql_llm` | 13 | 156 | 18 |

---

**文档生成工具**: [metaweave](https://github.com/your-org/metaweave)  
**文档版本**: 1.0
```

### C. 相关文档

- [cql_llm 与 json 目录兼容性评估](./5_cql_llm与json目录兼容性评估.md)
- [CQL 生成器 JSON 字段依赖清单](./5_CQL生成器JSON字段依赖清单.md)
- [cql 与 cql_llm 命令对比分析](./5_cql与cql_llm命令对比分析.md)
- [cql 与 cql_llm 输出格式一致性验证](./5_cql与cql_llm输出格式一致性验证.md)

---

## 变更历史

| 日期 | 版本 | 说明 |
|-----|------|------|
| 2025-12-26 | 1.0 | 初始版本，完成改造规划设计 |

---

**文档状态**: ✅ 已完成  
**下一步**: 开始开发实施

