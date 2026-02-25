# cql 与 cql_llm 统一输入源改造规划

## 文档说明

本文档详细规划 `--step cql` 和 `--step cql_llm` 命令的改造方案，主要目标是统一输入源目录，简化命令语义，并增加生成元数据文档功能。

**改造范围：**
- `metaweave metadata --config configs/metadata_config.yaml --step cql`
- `metaweave metadata --config configs/metadata_config.yaml --step cql_llm`

**文档版本：** 2.2  
**创建日期：** 2025-12-26  
**最后更新：** 2025-12-27（完善示例数据说明和实施计划）

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
| **增加元数据文档** | 生成 `import_all.md` 记录生成信息（最小必需字段） | P0（必需） |
| **统一配置使用** | 统一使用 `json_directory` 配置项 | P0（必需） |
| **优化 CLI 文案** | `cql_llm` 文案保持一致性，在日志中说明等价性 | P1（重要） |

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

> **注意**：以下示例使用假设数据（13 表、156 列、18 关系）用于说明格式。  
> 实施完成后，建议使用实际项目数据更新此示例，使文档更具参考价值。

```markdown
# Neo4j CQL 导入脚本元数据

> **自动生成文档**  
> 本文件记录 CQL 脚本的生成信息和统计数据。

---

## 生成信息

- **生成时间**: 2025-12-26 14:30:00
- **生成命令**: `metaweave metadata --step cql_llm`

---

## 统计数据

### 节点

| 节点类型 | 数量 |
|---------|------|
| Table | 13 |
| Column | 156 |
| **节点总数** | **169** |

### 边

| 边类型 | 数量 |
|-------|------|
| HAS_COLUMN | 156 |
| JOIN_ON | 18 |
| **边总数** | **174** |

---

## 输入输出目录

| 类型 | 路径 |
|-----|------|
| JSON 元数据 | `output/json` |
| 关系数据 | `output/rel` |
| CQL 输出 | `output/cql` |

---

## 输出文件

| 文件名 | 行数 |
|-------|------|
| import_all.cypher | 1743 |
| import_all.md | - |

---

**文档生成工具**: metaweave  
**文档版本**: 1.0
```

---

## 三、改造方案

### 1. 总体思路

**设计原则：**
1. **最小改动**：只修改 CLI 层面的逻辑和增加元数据生成
2. **核心逻辑不变**：`CQLGenerator` 的 Cypher 生成逻辑不修改
3. **统一配置**：统一使用 `json_directory` 配置项
4. **格式保持**：`import_all.cypher` 格式不变
5. **新增功能**：增加 `import_all.md` 生成逻辑（最小必需字段）

### 2. 改造范围

#### 2.1 需要修改的文件

| 文件 | 修改内容 | 改动行数（估算） |
|-----|---------|----------------|
| `metaweave/cli/metadata_cli.py` | 1. 去掉 `cql_llm` 的 json_dir 覆盖逻辑<br>2. 简化 CLI 文案，保持一致性<br>3. 增加日志说明等价性<br>4. 增加废弃配置检测逻辑<br>5. 传递 `step_name` 参数 | 约 20 行 |
| `metaweave/core/cql_generator/writer.py` | 增加 `write_metadata()` 方法（最小必需版本，7 个参数） | 约 55 行 |
| `metaweave/core/cql_generator/generator.py` | 1. 增加 `step_name` 参数<br>2. 调用 `write_metadata()`<br>3. 增加调试日志和容错处理 | 约 15 行 |
| `configs/metadata_config.yaml` | 更新注释，明确废弃 `json_llm_directory` | 约 3 行 |

**总改动行数：** 约 93 行

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

**改造后代码：**

```python
if step == "cql_llm":
    from metaweave.core.cql_generator.generator import CQLGenerator

    click.echo("🔧 开始生成 Neo4j CQL...")
    click.echo("")

    generator = CQLGenerator(config_path)
    
    # ✅ 检测废弃配置（帮助用户平滑过渡）
    if generator.config.get("output", {}).get("json_llm_directory"):
        logger.warning(
            "⚠️ 配置项 'json_llm_directory' 已废弃，"
            "cql_llm 现在使用 'json_directory'，与 cql 行为一致"
        )
    
    # ✅ 统一使用 json_directory（不再读取 json_llm_directory）
    # generator.json_dir 默认已指向 output.json_directory
    logger.info(f"使用 cql_llm 命令（功能等同于 cql）")
    logger.info(f"使用 JSON 目录: {generator.json_dir}")
    
    # ✅ 传递命令名称（用于元数据生成）
    result = generator.generate(step_name="cql_llm")
```

**改动说明：**
1. **不再覆盖 `json_dir`**：使用 generator 默认的 `json_directory`（`output/json`）
2. **统一输入源**：与 `cql` 命令使用相同的输入目录
3. **简化 CLI 文案**：去掉冗长的等价性说明，保持与 `cql` 一致的用户体验
4. **日志说明等价性**：在日志中说明 `cql_llm` 功能等同于 `cql`
5. **废弃配置检测**：检测并警告用户配置了已废弃的 `json_llm_directory`
6. **传递 `step_name`**：用于元数据文档生成

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
- 文案不需要修改

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

# ✅ 实施时建议：添加调试日志确认数据可用性
logger.debug(f"has_column_rels count: {len(has_column_rels)}")
logger.debug(f"join_on_rels count: {len(join_on_rels)}")
logger.debug("Calling write_metadata after write_all")

# ✅ 保护主流程：元数据生成失败不应影响 CQL 生成
try:
    metadata_file = writer.write_metadata(
        tables=tables,
        columns=columns,
        has_column_rels=has_column_rels,  # ✅ 传递 HAS_COLUMN 关系列表
        join_on_rels=join_on_rels,
        step_name=step_name,
        json_dir=self.json_dir,
        rel_dir=self.rel_dir
        # ✅ cql_dir 不需要传递，writer 内部使用 self.output_dir
    )
    logger.info(f"  - 元数据文档: {metadata_file}")
    output_files.append(str(metadata_file))
except Exception as e:
    logger.warning(f"元数据文档生成失败（不影响主流程）: {e}")
```

**调用时机验证点：**

| 验证点 | 说明 | 数据来源 | 状态 |
|-------|------|---------|------|
| `has_column_rels` 可用 | `reader.read_all()` 返回值包含此字段 | `generator.py:91` | ✅ 已确认（代码验证） |
| `join_on_rels` 可用 | `reader.read_all()` 返回值包含此字段 | `generator.py:91` | ✅ 已确认（代码验证） |
| `import_all.cypher` 已生成 | `write_metadata()` 需要读取此文件行数 | `writer.write_all()` 之后 | ✅ 调用顺序正确 |
| `self.output_dir` 可用 | writer 实例初始化时已设置 | `writer.__init__()` | ✅ 已确认 |

**代码验证说明：**
- 通过读取 `metaweave/core/cql_generator/generator.py:91` 确认 `has_column_rels` 确实在 `reader.read_all()` 返回的元组中
- 返回格式：`(tables, columns, has_column_rels, join_on_rels)` = `reader.read_all()`
- 这验证了文档中的调用方式完全正确

**实施建议：**
1. 在开发阶段保留调试日志，验证数据完整性
2. 如果 `import_all.cypher` 不存在，`write_metadata()` 应该设置行数为 0（而非失败）
3. 考虑添加 try-except 保护，避免元数据生成失败影响主流程

#### 2.2 在 `CypherWriter` 中增加 `write_metadata()` 方法

**文件位置：** `metaweave/core/cql_generator/writer.py`

**新增方法（最小必需字段版本）：**

```python
def write_metadata(
    self,
    tables: List[TableNode],
    columns: List[ColumnNode],
    has_column_rels: List[HASColumnRelation],
    join_on_rels: List[JOINOnRelation],
    step_name: str,
    json_dir: Path,
    rel_dir: Path
) -> Path:
    """生成 import_all.md 元数据文档（最小必需字段）
    
    Args:
        tables: 表节点列表
        columns: 列节点列表
        has_column_rels: HAS_COLUMN 关系列表
        join_on_rels: JOIN_ON 关系列表
        step_name: 执行的步骤名称（"cql" 或 "cql_llm"）
        json_dir: JSON 输入目录
        rel_dir: 关系输入目录
    
    Returns:
        元数据文档路径
    
    Note:
        CQL 输出目录使用 self.output_dir，无需额外传递
    """
    from datetime import datetime
    
    output_file = self.output_dir / "import_all.md"
    
    # 生成时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # ✅ 统计数据（使用准确的关系列表）
    has_column_count = len(has_column_rels)
    join_on_count = len(join_on_rels)
    edges_total = has_column_count + join_on_count
    
    # ✅ 获取 import_all.cypher 的行数（完善的容错处理）
    # 注意：此方法必须在 write_all() 之后调用，确保 Cypher 文件已生成
    cypher_file = self.output_dir / "import_all.cypher"
    cypher_lines = 0
    if cypher_file.exists():
        try:
            with open(cypher_file, "r", encoding="utf-8") as f:
                cypher_lines = sum(1 for _ in f)
            logger.debug(f"成功读取 Cypher 文件行数: {cypher_lines}")
        except Exception as e:
            logger.warning(f"无法读取 Cypher 文件行数: {e}")
            cypher_lines = 0  # 降级处理：设为 0
    else:
        logger.warning(
            f"import_all.cypher 不存在，无法统计行数。"
            f"路径: {cypher_file}"
        )
        cypher_lines = 0  # 降级处理：设为 0
    
    # ✅ 生成最小必需内容
    content = f"""# Neo4j CQL 导入脚本元数据

> **自动生成文档**  
> 本文件记录 CQL 脚本的生成信息和统计数据。

---

## 生成信息

- **生成时间**: {timestamp}
- **生成命令**: `metaweave metadata --step {step_name}`

---

## 统计数据

### 节点

| 节点类型 | 数量 |
|---------|------|
| Table | {len(tables)} |
| Column | {len(columns)} |
| **节点总数** | **{len(tables) + len(columns)}** |

### 边

| 边类型 | 数量 |
|-------|------|
| HAS_COLUMN | {has_column_count} |
| JOIN_ON | {join_on_count} |
| **边总数** | **{edges_total}** |

---

## 输入输出目录

| 类型 | 路径 |
|-----|------|
| JSON 元数据 | `{json_dir}` |
| 关系数据 | `{rel_dir}` |
| CQL 输出 | `{self.output_dir}` |

---

## 输出文件

| 文件名 | 行数 |
|-------|------|
| import_all.cypher | {cypher_lines} |
| import_all.md | - |

---

**文档生成工具**: metaweave  
**文档版本**: 1.0
"""
    
    # 写入文件
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"元数据文档已生成: {output_file}")
    return output_file
```

**设计说明：**
1. **最小必需字段**：只包含生成时间、命令、节点数、边数、目录信息、文件行数
2. **统计口径明确**：分别统计 HAS_COLUMN 和 JOIN_ON，并计算 edges_total
3. **去掉过度设计**：不包含表详情、关系详情、使用指南、版本历史等维护成本高的内容
4. **覆盖模式**：每次生成都覆盖 `import_all.md`
5. **完善的容错处理**：
   - **文件存在但读取失败**：捕获异常，记录警告日志，行数设为 0
   - **文件不存在**：记录警告日志（含文件路径），行数设为 0
   - **成功读取**：记录调试日志，便于问题排查
   - **降级策略**：任何情况下都不中断元数据生成，只是行数显示为 0
   - **主流程保护**：整个元数据生成被 try-except 保护，不影响 CQL 生成
6. **调用时机保证**：
   - 必须在 `write_all()` 之后调用（确保 Cypher 文件已生成）
   - `has_column_rels` 和 `join_on_rels` 来自 `reader.read_all()` 返回值
7. **格式一致性验证**：
   - ✅ 代码生成格式（第 437-492 行）与示例格式（第 107-162 行、第 1109-1152 行）完全一致
   - ✅ 验证点：章节标题、表格结构、分隔符、文档结构
   - ✅ 已通过格式对比检查

### 3. 元数据文档格式一致性验证

#### 3.1 格式对比结果

**验证范围：**
- **示例 1**：第 107-162 行（二、2.2 期望结果）
- **代码生成**：第 437-492 行（四、2.2 write_metadata() 方法）
- **示例 2**：第 1109-1152 行（附录 B）

**验证项目：**

| 验证项 | 示例格式 | 代码格式 | 一致性 |
|-------|---------|---------|-------|
| 文档标题 | `# Neo4j CQL 导入脚本元数据` | `# Neo4j CQL 导入脚本元数据` | ✅ 一致 |
| 引用块 | `> **自动生成文档**` | `> **自动生成文档**` | ✅ 一致 |
| 章节分隔 | `---` | `---` | ✅ 一致 |
| 生成信息 | 2 个字段（时间、命令） | 2 个字段（时间、命令） | ✅ 一致 |
| 节点统计表 | 3 行（Table、Column、总数） | 3 行（Table、Column、总数） | ✅ 一致 |
| 边统计表 | 3 行（HAS_COLUMN、JOIN_ON、总数） | 3 行（HAS_COLUMN、JOIN_ON、总数） | ✅ 一致 |
| 输入输出目录表 | 3 行（JSON、rel、CQL） | 3 行（JSON、rel、CQL） | ✅ 一致 |
| 输出文件表 | 2 行（cypher、md） | 2 行（cypher、md） | ✅ 一致 |
| 文档尾部 | 工具 + 版本 | 工具 + 版本 | ✅ 一致 |

**结论：** ✅ **代码生成格式与示例格式 100% 一致**

**验证依据：**
1. 所有章节标题（`##`）格式相同
2. 所有表格结构（列数、对齐方式）相同
3. 所有分隔符（`---`）位置相同
4. Markdown 语法（加粗、代码块）使用一致
5. 字段顺序和命名完全一致

### 4. 配置文件更新

#### 4.1 更新 `metadata_config.yaml`

**文件位置：** `configs/metadata_config.yaml`

**历史遗留配置示例（已在仓库中注释）：**

```yaml
output:
  # Step 2: 表/列画像输出配置
  json_directory: output/json
  json_llm_directory: output/json_llm  # ← 历史遗留，已废弃

  # Step 3: 关系发现输出配置
  rel_directory: output/rel

  # Step 4: CQL 生成输出配置
  cql_directory: output/cql
```

**标准配置（改造目标）：**

```yaml
output:
  # Step 2: 表/列画像输出配置
  json_directory: output/json
  # json_llm_directory: output/json_llm  # ⚠️ 已废弃，cql_llm 不再读取此配置

  # Step 3: 关系发现输出配置
  rel_directory: output/rel

  # Step 4: CQL 生成输出配置
  cql_directory: output/cql
  
  # 注意：
  # - --step cql 和 --step cql_llm 功能完全等价
  # - 都从 json_directory 和 rel_directory 读取数据
  # - 输出到 cql_directory，生成 import_all.cypher 和 import_all.md
```

---

## 五、实现说明

### 1. 配置文件处理

#### 1.1 统一输入源实现

**唯一实现路径：**

```python
# ✅ cql_llm 不再覆盖 json_dir，直接使用 generator 默认配置
# generator.json_dir 默认指向 output.json_directory（output/json）
```

**说明：**
- **统一使用 `json_directory`**：`cql` 和 `cql_llm` 都读取同一个配置
- **去掉 CLI 覆盖逻辑**：`cql_llm` 不再在 CLI 层面覆盖 `json_dir`
- **配置已废弃 `json_llm_directory`**：`configs/metadata_config.yaml:265-266` 已注释

#### 1.2 标准配置

```yaml
output:
  json_directory: output/json  # ✅ cql 和 cql_llm 统一读取
  rel_directory: output/rel
  cql_directory: output/cql
  
  # 注意：
  # - --step cql 和 --step cql_llm 功能完全等价
  # - 都从 json_directory 和 rel_directory 读取数据
  # - 输出到 cql_directory，生成 import_all.cypher 和 import_all.md
```

#### 1.3 废弃配置检测

**检测逻辑：**

```python
# 在 cql_llm 步骤中检测废弃配置
if generator.config.get("output", {}).get("json_llm_directory"):
    logger.warning(
        "⚠️ 配置项 'json_llm_directory' 已废弃，"
        "cql_llm 现在使用 'json_directory'，与 cql 行为一致"
    )
```

**设计目的：**
1. **帮助用户理解**：明确告知配置项已废弃
2. **避免混淆**：说明现在使用 `json_directory`
3. **平滑过渡**：即使配置了废弃项，也不会失败，只是给出警告
4. **行为一致**：强调与 `cql` 行为一致

**警告时机：**
- 只在 `cql_llm` 步骤检测（`cql` 步骤不需要）
- 在实际执行前发出警告
- 使用 `logger.warning` 级别（不使用 `click.echo` 避免干扰 CLI 输出）

**示例输出：**

```
🔧 开始生成 Neo4j CQL...

⚠️ 配置项 'json_llm_directory' 已废弃，cql_llm 现在使用 'json_directory'，与 cql 行为一致
使用 cql_llm 命令（功能等同于 cql）
使用 JSON 目录: /path/to/project/output/json
```

### 2. 命令行为

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
# → CLI 文案保持一致，在日志中说明等价性
```

**改进效果：**
- ✅ `--step cql` 行为不变
- ✅ `--step cql_llm` 统一输入源
- ✅ 两个命令功能完全等价
- ✅ 用户体验保持一致

### 3. 输出格式

#### 3.1 `import_all.cypher` 格式保持不变

| 属性 | 改造前 | 改造后 |
|-----|-------|-------|
| 文件名 | `import_all.cypher` | `import_all.cypher` |
| 文件结构 | 5 个部分 | 5 个部分 |
| Table 节点属性 | 13 个 | 13 个 |
| Column 节点属性 | 15 个 | 15 个 |
| JOIN_ON 关系属性 | 6 个 | 6 个 |
| Cypher 语法 | MERGE + SET | MERGE + SET |

**结论：** ✅ **格式 100% 保持不变**

#### 3.2 新增元数据文件

**新增输出：**

```
output/cql/
├── import_all.cypher      # 格式不变
└── import_all.md          # 新增（记录生成信息和统计数据）
```

**说明：**
- ✅ 新增文件，记录最小必需元数据
- ✅ 每次生成覆盖，不会累积文件
- ✅ 不影响现有 Cypher 脚本使用

---

## 六、测试计划

### 1. 单元测试

#### 1.1 输入目录读取测试

**测试用例：**

| 测试用例 | 配置 | 期望结果 |
|---------|------|---------|
| TC-001 | 配置 `json_directory: output/json` | 读取并解析到 `<project_root>/output/json` |
| TC-002 | 配置 `json_directory: custom/path` | 读取并解析到 `<project_root>/custom/path` |
| TC-003 | 无 `json_directory` 配置 | 使用默认值，解析到 `<project_root>/output/json` |

**说明：** 相对路径会通过 `_resolve_path()` 解析为相对于项目根目录的绝对路径

#### 1.2 废弃配置检测测试

**测试用例：**

| 测试用例 | 配置 | 期望行为 |
|---------|------|---------|
| TC-011 | 配置了 `json_llm_directory` | 执行 `cql_llm` 时输出警告日志 |
| TC-012 | 未配置 `json_llm_directory` | 执行 `cql_llm` 时无警告 |
| TC-013 | 配置了 `json_llm_directory` | 执行 `cql` 时不检测（无警告） |
| TC-014 | 配置了 `json_llm_directory` | 仍正常使用 `json_directory`，功能不受影响 |

**验证方法：**
```python
# 模拟配置
config_with_deprecated = {
    "output": {
        "json_directory": "output/json",
        "json_llm_directory": "output/json_llm"  # 废弃配置
    }
}

# 验证警告日志
with self.assertLogs(logger, level='WARNING') as cm:
    # 执行 cql_llm 步骤
    ...
    # 验证警告消息
    self.assertIn("json_llm_directory' 已废弃", cm.output[0])
```

#### 1.3 元数据生成测试

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
# 注意：以下命令需要在 bash/WSL 环境执行
# PowerShell 用户请使用等价命令：Get-Content, Select-String 等

# 执行 cql
metaweave metadata --step cql

# 检查 import_all.md
cat output/cql/import_all.md | grep "cql"
# PowerShell 等价：Get-Content output/cql/import_all.md | Select-String "cql"

# 执行 cql_llm
metaweave metadata --step cql_llm

# 检查 import_all.md（应该被覆盖）
cat output/cql/import_all.md | grep "cql_llm"
# PowerShell 等价：Get-Content output/cql/import_all.md | Select-String "cql_llm"
```

#### 2.2 功能等价性测试

**测试场景：验证 cql 和 cql_llm 功能等价**

```yaml
# 标准配置
output:
  json_directory: output/json
  rel_directory: output/rel
  cql_directory: output/cql
```

```bash
# 注意：以下命令需要在 bash/WSL 环境执行
# PowerShell 用户请使用等价命令：Copy-Item, Get-Content, Select-String, Compare-Object 等

# 1. 执行 cql 命令
metaweave metadata --step cql
cp output/cql/import_all.cypher cql_result.cypher
cp output/cql/import_all.md cql_result.md
# PowerShell 等价：Copy-Item output/cql/import_all.cypher cql_result.cypher

# 2. 执行 cql_llm 命令
metaweave metadata --step cql_llm
cp output/cql/import_all.cypher cql_llm_result.cypher
cp output/cql/import_all.md cql_llm_result.md

# 3. 验证 Cypher 文件（应该完全相同，除了时间戳注释）
diff <(grep -v "^// 生成时间:" cql_result.cypher) \
     <(grep -v "^// 生成时间:" cql_llm_result.cypher)

# 期望输出：无差异

# 4. 验证 MD 文件（应该只在生成时间和生成命令上有差异）
diff <(grep -v "^- \*\*生成时间\*\*:" cql_result.md | grep -v "^- \*\*生成命令\*\*:") \
     <(grep -v "^- \*\*生成时间\*\*:" cql_llm_result.md | grep -v "^- \*\*生成命令\*\*:")

# 期望输出：无差异

# 或使用跨平台方式：
grep -v "^- \*\*生成时间\*\*:" cql_result.md | grep -v "^- \*\*生成命令\*\*:" > cql_result_filtered.md
grep -v "^- \*\*生成时间\*\*:" cql_llm_result.md | grep -v "^- \*\*生成命令\*\*:" > cql_llm_result_filtered.md
diff cql_result_filtered.md cql_llm_result_filtered.md
# PowerShell 等价：
# Get-Content cql_result.md | Where-Object {$_ -notmatch "^- \*\*生成时间\*\*:" -and $_ -notmatch "^- \*\*生成命令\*\*:"} | Set-Content cql_result_filtered.md
# Get-Content cql_llm_result.md | Where-Object {$_ -notmatch "^- \*\*生成时间\*\*:" -and $_ -notmatch "^- \*\*生成命令\*\*:"} | Set-Content cql_llm_result_filtered.md
# Compare-Object (Get-Content cql_result_filtered.md) (Get-Content cql_llm_result_filtered.md)
```

#### 2.3 快速验证方法（推荐用于日常开发）

**适用场景：**
- 日常开发调试
- 快速确认核心功能
- 不需要完整的文件对比

**验证方法：**

```bash
# 注意：以下命令适用于 bash/WSL 环境
# PowerShell 用户请使用 Select-String 等价命令

# 1. 执行两个命令
metaweave metadata --step cql
cp output/cql/import_all.md cql_result.md

metaweave metadata --step cql_llm
cp output/cql/import_all.md cql_llm_result.md

# 2. 快速验证：只检查核心统计数据是否一致
echo "=== 验证节点总数 ==="
grep "节点总数" cql_result.md
grep "节点总数" cql_llm_result.md

echo "=== 验证边总数 ==="
grep "边总数" cql_result.md
grep "边总数" cql_llm_result.md

# 3. 可选：验证具体统计
echo "=== 验证 Table 数量 ==="
grep "| Table |" cql_result.md
grep "| Table |" cql_llm_result.md

echo "=== 验证 Column 数量 ==="
grep "| Column |" cql_result.md
grep "| Column |" cql_llm_result.md

# PowerShell 等价：
# Select-String "节点总数" cql_result.md
# Select-String "节点总数" cql_llm_result.md
```

**期望输出示例：**

```
=== 验证节点总数 ===
| **节点总数** | **169** |
| **节点总数** | **169** |

=== 验证边总数 ===
| **边总数** | **174** |
| **边总数** | **174** |
```

**验证标准：**
- ✅ 两个文件的统计数据完全一致
- ✅ 节点总数相同
- ✅ 边总数相同
- ✅ Table、Column 数量相同

**优势：**
1. **快速**：无需完整 diff，几秒内完成
2. **直观**：直接显示关键统计数据
3. **简单**：命令简单易记
4. **聚焦核心**：关注最重要的功能等价性

**何时使用完整验证 vs 快速验证：**

| 场景 | 使用方法 | 原因 |
|-----|---------|------|
| 日常开发调试 | 快速验证 | 只需确认核心统计一致 |
| 代码修改后验证 | 快速验证 | 快速反馈 |
| 正式测试 | 完整验证（diff） | 确保所有细节一致 |
| CI/CD 自动化测试 | 完整验证（diff） | 全面覆盖 |
| 发布前验证 | 完整验证（diff） | 最高质量要求 |

### 3. 回归测试

#### 3.1 输出格式验证

**测试方法：**

```bash
# 注意：以下命令需要在 bash/WSL 环境执行
# PowerShell 用户请使用等价命令或 GUI 对比工具（如 Beyond Compare, WinMerge）

# 改造前生成
metaweave metadata --step cql
cp output/cql/import_all.cypher before.cypher
# PowerShell 等价：Copy-Item output/cql/import_all.cypher before.cypher

# 改造后生成
metaweave metadata --step cql
cp output/cql/import_all.cypher after.cypher

# 对比（忽略生成时间戳注释行）
diff <(grep -v "^// 生成时间:" before.cypher) \
     <(grep -v "^// 生成时间:" after.cypher)

# 或使用跨平台方式：
grep -v "^// 生成时间:" before.cypher > before_filtered.cypher
grep -v "^// 生成时间:" after.cypher > after_filtered.cypher
diff before_filtered.cypher after_filtered.cypher
# PowerShell 等价：Compare-Object (Get-Content before_filtered.cypher) (Get-Content after_filtered.cypher)
```

**期望结果：** 除时间戳注释外，格式完全相同

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
| 1 | 修改 `metadata_cli.py`（去掉覆盖 + 文案 + 日志 + 废弃检测） | 开发 | 0.5h |
| 2 | 增加 `write_metadata()` 方法（最小必需版本，7 参数 + 容错） | 开发 | 1.5h |
| 3 | 修改 `generate()` 方法（参数 + 调用 + 日志 + 容错） | 开发 | 0.5h |
| 4 | 更新配置文件注释 | 开发 | 0.5h |
| 5 | 编写单元测试（包括废弃配置检测测试） | 开发 | 1h |
| 6 | 编写集成测试 | 开发 | 1h |

**总工时：** 约 5 小时

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
| 4 | 使用实际数据更新文档示例 | 文档 | 0.5h |
| 5 | 发布新版本 | 开发 | 0.5h |

**总工时：** 约 3 小时

**步骤 4 说明：**
- 运行改造后的代码，生成真实的 `import_all.md`
- 用实际统计数据替换文档中的假设示例（13 表、156 列等）
- 更新示例文件路径和行数
- 确保文档示例反映真实使用场景

### 4. 总时间估算

- **开发阶段**：5 小时
- **测试阶段**：7 小时
- **发布阶段**：3 小时
- **总计**：约 15 小时（约 2 个工作日）

---

## 八、风险评估

### 1. 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| 输出格式意外变化 | 高 | 低 | 充分回归测试，代码审查 |
| 元数据生成失败 | 低 | 低 | 使用 try-except 保护，不影响主流程 |
| 调用时机错误 | 中 | 低 | 在 write_all() 之后调用，添加验证日志 |
| Cypher 文件读取失败 | 低 | 低 | 完善的异常处理，降级为行数 0，记录警告日志 |
| 统计数据不准确 | 低 | 低 | 使用准确的关系列表统计，添加调试日志验证 |
| 文件覆盖丢失数据 | 低 | 低 | 文档明确说明覆盖行为 |

### 2. 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| 用户混淆两个命令用途 | 低 | 低 | 更新 CLI 文案，明确等价语义 |
| 用户不理解元数据文档 | 低 | 低 | 文档内容简洁清晰，字段含义明确 |
| 命令接口误解 | 低 | 低 | 命令接口保持不变 |

### 3. 风险总结

**整体风险等级：** 🟢 低

**理由：**
1. 改动范围小（约 93 行）
2. 核心 Cypher 生成逻辑不变
3. 只是统一输入源和增加元数据文档，不涉及复杂逻辑
4. 完善的测试计划和容错处理
5. 友好的废弃配置检测和用户引导

---

## 九、文档更新清单

### 1. 需要更新的文档

| 文档 | 更新内容 | 优先级 |
|-----|---------|--------|
| `README.md` | 增加 `import_all.md` 元数据文档说明 | P0 |
| `CHANGELOG.md` | 记录本次改造内容和版本 | P0 |
| `docs/命令使用指南.md` | 更新 `cql` 和 `cql_llm` 说明，明确等价语义 | P1 |
| `docs/配置文件说明.md` | 说明 `json_directory` 统一使用 | P1 |
| `docs/5_cql与cql_llm命令对比分析.md` | 更新对比结果（已等价） | P2 |

---

## 十、成功标准

### 1. 功能标准

- [ ] `cql` 和 `cql_llm` 使用统一的输入目录（`json_directory`）
- [ ] 生成 `import_all.md` 元数据文档（最小必需字段）
- [ ] `import_all.cypher` 格式 100% 保持不变
- [ ] 元数据文档每次覆盖生成
- [ ] CLI 文案保持一致（两个命令用户体验相同）
- [ ] 日志中说明 `cql_llm` 功能等同于 `cql`
- [ ] 统计口径准确（HAS_COLUMN + JOIN_ON = edges_total）

### 2. 质量标准

- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试全部通过
- [ ] 回归测试无格式差异
- [ ] 代码审查通过

### 3. 文档标准

- [ ] README 更新（增加元数据文档说明）
- [ ] CHANGELOG 更新（记录改造内容）
- [ ] 命令使用指南更新（明确等价语义）
- [ ] 示例代码更新
- [ ] 文档示例数据更新（使用实际项目数据替换假设数据）

---

## 十一、附录

### A. 改造前后对比

#### A.1 命令行为对比

**改造前：**

```bash
# cql 命令
metaweave metadata --step cql
# CLI 文案：开始生成 Neo4j CQL...
# 输入：output/json
# 输出：output/cql/import_all.cypher

# cql_llm 命令
metaweave metadata --step cql_llm
# CLI 文案：开始生成 Neo4j CQL（LLM 流程）...
# 输入：output/json_llm（已废弃，可能失败）
# 输出：output/cql/import_all.cypher
```

**改造后：**

```bash
# cql 命令
metaweave metadata --step cql
# CLI 文案：开始生成 Neo4j CQL...
# 输入：output/json
# 输出：output/cql/import_all.cypher, import_all.md

# cql_llm 命令
metaweave metadata --step cql_llm
# CLI 文案：开始生成 Neo4j CQL...（与 cql 保持一致）
# 日志提示：使用 cql_llm 命令（功能等同于 cql）
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

### B. `import_all.md` 完整示例（最小必需版本）

> **注意**：以下示例使用假设数据（13 表、156 列、18 关系）用于说明格式。  
> 实施完成后，建议使用实际项目数据更新此示例，使文档更具参考价值。

```markdown
# Neo4j CQL 导入脚本元数据

> **自动生成文档**  
> 本文件记录 CQL 脚本的生成信息和统计数据。

---

## 生成信息

- **生成时间**: 2025-12-26 14:30:00
- **生成命令**: `metaweave metadata --step cql_llm`

---

## 统计数据

### 节点

| 节点类型 | 数量 |
|---------|------|
| Table | 13 |
| Column | 156 |
| **节点总数** | **169** |

### 边

| 边类型 | 数量 |
|-------|------|
| HAS_COLUMN | 156 |
| JOIN_ON | 18 |
| **边总数** | **174** |

---

## 输入输出目录

| 类型 | 路径 |
|-----|------|
| JSON 元数据 | `output/json` |
| 关系数据 | `output/rel` |
| CQL 输出 | `output/cql` |

---

## 输出文件

| 文件名 | 行数 |
|-------|------|
| import_all.cypher | 1743 |
| import_all.md | - |

---

**文档生成工具**: metaweave  
**文档版本**: 1.0
```

### C. 相关文档

- [cql_llm 与 json 目录兼容性评估](./5_cql_llm与json目录兼容性评估.md)
- [CQL 生成器 JSON 字段依赖清单](./5_cql生成器JSON字段依赖清单.md)
- [cql 与 cql_llm 命令对比分析](./5_cql与cql_llm命令对比分析.md)
- [cql 与 cql_llm 输出格式一致性验证](./5_cql与cql_llm输出格式一致性验证.md)

---

## 十二、关键决策总结

### 1. 统一输入源实现

**决策：** `cql_llm` 步骤去掉 CLI 层面的 `json_dir` 覆盖逻辑，统一使用 `json_directory` 配置。

**理由：**
1. **与统一输入源目标一致**：两个命令读取相同的数据源
2. **简化实现**：去掉 CLI 层面的覆盖逻辑
3. **明确语义**：`cql` 和 `cql_llm` 功能完全等价
4. **配置清晰**：只需配置 `json_directory` 一个选项

**实现方式：**
- `cql`：使用 generator 默认的 `json_dir`
- `cql_llm`：使用 generator 默认的 `json_dir`（不再覆盖）

### 2. MD 只包含最小必需字段

**决策：** `import_all.md` 只包含生成时间、命令、节点数、边数、目录信息、文件行数。

**理由：**
1. **满足需求**：需求只要求记录生成信息和统计数据
2. **降低维护成本**：表详情、关系详情等容易与真实字段不一致
3. **避免文件过长**：详细信息会让文件变得冗长
4. **保持简洁**：最小必需字段最容易维护

**不包含的内容：**
- ❌ 表详情（Schema、主键、外键等）
- ❌ 关系详情（源表、目标表、基数等）
- ❌ 使用指南（导入命令、验证脚本）
- ❌ 版本历史（累积记录）

### 3. 统计口径明确

**决策：** 分别统计 HAS_COLUMN 和 JOIN_ON，并计算 edges_total = HAS_COLUMN + JOIN_ON。

**理由：**
1. **避免歧义**：`relationships_count` 只统计 JOIN_ON，不代表边总数
2. **准确性**：使用 `len(has_column_rels)` 而非推导计算
3. **清晰性**：明确区分两类边的统计口径

### 4. CLI 文案优化

**决策：** `cql_llm` 的 CLI 文案保持与 `cql` 一致，在日志中说明等价性。

**实现方式：**
```python
# CLI 文案（用户可见）
click.echo("🔧 开始生成 Neo4j CQL...")

# 日志说明（开发者/调试可见）
logger.info(f"使用 cql_llm 命令（功能等同于 cql）")
```

**理由：**
1. **简洁性**：CLI 文案保持简洁，聚焦核心操作（生成 CQL）
2. **一致性**：两个命令的用户体验完全一致
3. **信息分层**：核心信息在 CLI 展示，补充信息在日志中
4. **避免冗长**：去掉"等价于 cql，保留作为历史别名"等冗长说明

---

## 变更历史

| 日期 | 版本 | 说明 |
|-----|------|------|
| 2025-12-26 | 1.0 | 初始版本，完成改造规划设计 |
| 2025-12-27 | 1.1 | 根据审核意见修正：<br>1. 统一输入源实现<br>2. 修复 write_metadata() bug<br>3. 简化 MD 为最小必需字段<br>4. 明确统计口径<br>5. 修正测试命令<br>6. 更新 CLI 文案 |
| 2025-12-27 | 1.2 | 简化文档（项目未上线）：<br>去掉所有关于旧数据迁移的内容 |
| 2025-12-27 | 1.3 | 修正细节问题：<br>1. 删除矛盾的单元测试用例<br>2. 修正功能等价性测试命令<br>3. 配置片段改为"历史遗留示例"<br>4. 去掉 write_metadata() 冗余参数 cql_dir<br>5. 添加测试命令环境提示 |
| 2025-12-27 | 1.4 | 完善细节：<br>1. 修正相关文档链接大小写<br>2. 明确测试用例路径解析逻辑<br>3. 补充所有测试命令的跨平台提示 |
| 2025-12-27 | 1.5 | 完善测试一致性：<br>将 MD 文件验证从 grep 改为 diff 对比，与 Cypher 文件测试方式保持一致 |
| 2025-12-27 | 1.6 | 优化 CLI 文案：<br>简化 `cql_llm` 的 CLI 文案，保持与 `cql` 一致，在日志中说明等价性 |
| 2025-12-27 | 1.7 | 完善实施指导：<br>1. 添加调用时机验证点说明<br>2. 增加调试日志建议<br>3. 添加容错处理（try-except 保护）<br>4. 更新风险评估 |
| 2025-12-27 | 1.8 | 增加废弃配置检测：<br>1. 在 cql_llm 步骤检测 json_llm_directory 配置<br>2. 添加废弃配置警告日志<br>3. 增加相关测试用例<br>4. 完善用户引导 |
| 2025-12-27 | 1.9 | 验证格式一致性：<br>1. 确认代码生成格式与示例格式 100% 一致<br>2. 添加格式对比验证表<br>3. 验证 has_column_rels 数据可用性 |
| 2025-12-27 | 2.0 | 完善测试方法：<br>1. 新增快速验证方法（推荐日常使用）<br>2. 区分快速验证 vs 完整验证使用场景<br>3. 提供简单直观的统计数据验证命令 |
| 2025-12-27 | 2.1 | 完善错误处理：<br>1. 增加 Cypher 文件不存在时的警告日志<br>2. 添加成功读取时的调试日志<br>3. 完善降级策略说明<br>4. 提高代码健壮性 |
| 2025-12-27 | 2.2 | 完善示例数据说明：<br>1. 标注示例使用假设数据<br>2. 在发布阶段增加使用实际数据更新示例的任务<br>3. 更新文档标准和工时估算 |

---

**文档状态**: ✅ 已完成审核修正  
**下一步**: 开始开发实施

