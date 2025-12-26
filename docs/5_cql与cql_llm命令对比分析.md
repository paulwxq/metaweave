# cql 与 cql_llm 命令对比分析

## 文档说明

本文档详细对比 `--step cql` 和 `--step cql_llm` 两个命令的异同点。

**命令：**
```bash
metaweave metadata --config configs/metadata_config.yaml --step cql
metaweave metadata --config configs/metadata_config.yaml --step cql_llm
```

---

## 一、核心差异总结

| 对比维度 | `--step cql` | `--step cql_llm` | 是否相同 |
|---------|-------------|-----------------|---------|
| **输入：表/列 JSON** | `output/json` | `output/json_llm` | ❌ 不同 |
| **输入：关系 JSON** | `output/rel` | `output/rel` | ✅ 相同 |
| **输出：CQL 目录** | `output/cql` | `output/cql` | ✅ 相同 |
| **输出：文件名** | `import_all.cypher` | `import_all.cypher` | ✅ 相同 |
| **输出：文件格式** | Cypher 脚本 | Cypher 脚本 | ✅ 相同 |
| **生成逻辑** | `CQLGenerator.generate()` | `CQLGenerator.generate()` | ✅ 相同 |
| **代码复用** | 共享核心逻辑 | 共享核心逻辑 | ✅ 相同 |

**关键结论：**
- **唯一差异：输入的表/列 JSON 目录不同**
- **其他所有逻辑和输出完全相同**
- **两个命令会覆盖同一个输出文件**

---

## 二、详细对比分析

### 1. 输入数据源

#### 1.1 表/列画像 JSON

**代码位置：** `metaweave/cli/metadata_cli.py`

**`cql` 步骤（第 432-439 行）：**

```432:439:metaweave/cli/metadata_cli.py
        # Step 4: CQL 生成
        if step == "cql":
            from metaweave.core.cql_generator.generator import CQLGenerator

            click.echo("🔧 开始生成 Neo4j CQL...")
            click.echo("")

            generator = CQLGenerator(config_path)
            result = generator.generate()
```

- **输入目录：** `output/json`（从配置文件 `output.json_directory` 读取）
- **来源命令：** `--step json` 或 `--step json_llm`
- **特点：** 使用配置文件的默认值，不覆盖

**`cql_llm` 步骤（第 376-399 行）：**

```376:399:metaweave/cli/metadata_cli.py
        # Step: cql_llm - CQL 生成（LLM 流程）
        if step == "cql_llm":
            from metaweave.core.cql_generator.generator import CQLGenerator

            click.echo("🔧 开始生成 Neo4j CQL（LLM 流程）...")
            click.echo("")

            generator = CQLGenerator(config_path)
            
            # 覆盖 json_dir 为 json_llm 目录
            json_llm_dir = generator._resolve_path(
                generator.config.get("output", {}).get("json_llm_directory", "output/json_llm")
            )
            
            # 检查 json_llm 目录是否存在
            if not json_llm_dir.exists():
                raise FileNotFoundError(
                    f"json_llm 目录不存在: {json_llm_dir}\n"
                    f"请先执行 --step json_llm 生成 LLM 增强后的 JSON"
                )
            
            generator.json_dir = json_llm_dir
            logger.info(f"cql_llm: 使用 json_llm 目录: {json_llm_dir}")
            
            result = generator.generate()
```

- **输入目录：** `output/json_llm`（从配置文件 `output.json_llm_directory` 读取，默认 `output/json_llm`）
- **来源命令：** `--step json_llm`
- **特点：** CLI 层面覆盖 `generator.json_dir`，并进行目录存在性检查

**对比表：**

| 属性 | `cql` | `cql_llm` |
|-----|-------|----------|
| 配置项 | `output.json_directory` | `output.json_llm_directory` |
| 默认值 | `output/json` | `output/json_llm` |
| 覆盖逻辑 | ❌ 不覆盖，使用初始化值 | ✅ CLI 层面覆盖 `generator.json_dir` |
| 目录检查 | ❌ 无（由 JSONReader 抛出异常） | ✅ 明确检查并提示 |
| 错误提示 | 通用 "目录不存在" | 明确 "请先执行 --step json_llm" |

#### 1.2 关系 JSON

**代码位置：** `metaweave/core/cql_generator/generator.py` 第 45-46 行

```45:46:metaweave/core/cql_generator/generator.py
        self.rel_dir = self._resolve_path(
            self.config.get("output", {}).get("rel_directory", "output/rel")
        )
```

**对比：**

| 属性 | `cql` | `cql_llm` |
|-----|-------|----------|
| 配置项 | `output.rel_directory` | `output.rel_directory` |
| 默认值 | `output/rel` | `output/rel` |
| 文件名 | `relationships_*.json` | `relationships_*.json` |
| 是否相同 | ✅ **完全相同** | ✅ **完全相同** |

**说明：**
- 两个命令使用**同一个关系目录**
- 关系数据可以来自 `--step rel` 或 `--step rel_llm`
- CQL 生成器不区分关系来源（规则算法 vs LLM 辅助）

---

### 2. 输出目标

#### 2.1 输出目录

**代码位置：** `metaweave/core/cql_generator/generator.py` 第 48-50 行

```48:50:metaweave/core/cql_generator/generator.py
        self.cql_dir = self._resolve_path(
            self.config.get("output", {}).get("cql_directory", "output/cql")
        )
```

**对比：**

| 属性 | `cql` | `cql_llm` |
|-----|-------|----------|
| 配置项 | `output.cql_directory` | `output.cql_directory` |
| 默认值 | `output/cql` | `output/cql` |
| 是否相同 | ✅ **完全相同** | ✅ **完全相同** |

#### 2.2 输出文件

**代码位置：** `metaweave/core/cql_generator/writer.py` 第 61-64 行

```61:64:metaweave/core/cql_generator/writer.py
        # 生成单个完整的 import_all.cypher 文件
        import_all_file = self._write_import_all(
            tables, columns, has_column_rels, join_on_rels
        )
```

**对比：**

| 属性 | `cql` | `cql_llm` |
|-----|-------|----------|
| 文件名 | `import_all.cypher` | `import_all.cypher` |
| 文件路径 | `output/cql/import_all.cypher` | `output/cql/import_all.cypher` |
| 是否相同 | ✅ **完全相同** | ✅ **完全相同** |

**⚠️ 重要警告：文件覆盖问题**

由于两个命令输出到同一个文件，**后执行的命令会覆盖前一个命令的输出**：

```bash
# 执行顺序 1
metaweave metadata --step cql      # 生成 output/cql/import_all.cypher
metaweave metadata --step cql_llm  # ❌ 覆盖上一步的输出

# 执行顺序 2
metaweave metadata --step cql_llm  # 生成 output/cql/import_all.cypher
metaweave metadata --step cql      # ❌ 覆盖上一步的输出
```

**解决方案：**
1. **只执行其中一个命令**（推荐）
2. **手动备份输出文件**（重命名 `import_all.cypher`）
3. **修改配置文件**（使用不同的 `cql_directory`）

---

### 3. 生成逻辑

#### 3.1 核心生成流程

**代码位置：** `metaweave/core/cql_generator/generator.py` 第 77-124 行

```77:124:metaweave/core/cql_generator/generator.py
    def generate(self) -> CQLGenerationResult:
        """执行 CQL 生成

        Returns:
            生成结果
        """
        try:
            logger.info("=" * 60)
            logger.info("开始 Step 4: Neo4j CQL 生成")
            logger.info("=" * 60)

            # 1. 读取 JSON 数据
            logger.info("\n[1/2] 读取 Step 2 和 Step 3 的 JSON 文件...")
            reader = JSONReader(self.json_dir, self.rel_dir)
            tables, columns, has_column_rels, join_on_rels = reader.read_all()

            logger.info(f"  - 表节点: {len(tables)}")
            logger.info(f"  - 列节点: {len(columns)}")
            logger.info(f"  - HAS_COLUMN 关系: {len(has_column_rels)}")
            logger.info(f"  - JOIN_ON 关系: {len(join_on_rels)}")

            # 2. 生成 Cypher 文件
            logger.info("\n[2/2] 生成 Cypher 脚本文件...")
            writer = CypherWriter(self.cql_dir)
            output_files = writer.write_all(
                tables, columns, has_column_rels, join_on_rels
            )

            logger.info(f"  - 生成文件: {len(output_files)} 个")
            for file_path in output_files:
                logger.info(f"    * {file_path}")

            # 构造结果
            result = CQLGenerationResult(
                success=True,
                output_files=output_files,
                tables_count=len(tables),
                columns_count=len(columns),
                relationships_count=len(join_on_rels),
                errors=[]
            )

            logger.info("\n" + "=" * 60)
            logger.info("✅ Step 4 完成")
            logger.info("=" * 60)
            logger.info(str(result))

            return result

        except Exception as e:
            logger.error(f"CQL 生成失败: {e}", exc_info=True)
            return CQLGenerationResult(
                success=False,
                output_files=[],
                tables_count=0,
                columns_count=0,
                relationships_count=0,
                errors=[str(e)]
            )
```

**对比：**

| 步骤 | `cql` | `cql_llm` | 是否相同 |
|-----|-------|----------|---------|
| 1. 读取 JSON 数据 | `JSONReader(self.json_dir, self.rel_dir)` | `JSONReader(self.json_dir, self.rel_dir)` | ✅ 相同 |
| 2. 提取表/列节点 | `reader.read_all()` | `reader.read_all()` | ✅ 相同 |
| 3. 提取关系 | `reader.read_all()` | `reader.read_all()` | ✅ 相同 |
| 4. 生成 Cypher 文件 | `CypherWriter.write_all()` | `CypherWriter.write_all()` | ✅ 相同 |
| 5. 构造结果 | `CQLGenerationResult(...)` | `CQLGenerationResult(...)` | ✅ 相同 |

**结论：** 两个命令使用**完全相同的生成逻辑**，只是输入的 JSON 目录不同。

#### 3.2 代码复用架构

```
metaweave/cli/metadata_cli.py
    │
    ├─ step == "cql"
    │   └─ CQLGenerator(config_path)
    │       ├─ json_dir = output/json       (默认)
    │       ├─ rel_dir = output/rel
    │       └─ cql_dir = output/cql
    │
    └─ step == "cql_llm"
        └─ CQLGenerator(config_path)
            ├─ json_dir = output/json_llm  (覆盖)
            ├─ rel_dir = output/rel
            └─ cql_dir = output/cql

            ↓
metaweave/core/cql_generator/generator.py
    └─ generate()
        ├─ JSONReader(json_dir, rel_dir)
        │   └─ read_all()
        │       ├─ _read_table_profiles()
        │       └─ _read_relationships()
        │
        └─ CypherWriter(cql_dir)
            └─ write_all()
                └─ _write_import_all()
```

**设计优势：**
- ✅ 核心逻辑高度复用
- ✅ CLI 层面轻量切换（只需覆盖 1 个属性）
- ✅ 易于维护（修改一处，两个命令同时生效）

---

### 4. 生成的 Cypher 文件格式

#### 4.1 文件结构

**代码位置：** `metaweave/core/cql_generator/writer.py` 第 169-229 行

**生成文件：** `output/cql/import_all.cypher`

**文件内容结构：**

```cypher
// ============================================================
// Neo4j Cypher 导入脚本（完整版）
// 生成时间: 2025-12-26 10:00:00
// ============================================================

// 第一步：创建唯一约束
CREATE CONSTRAINT table_id IF NOT EXISTS FOR (t:Table) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT table_full_name IF NOT EXISTS FOR (t:Table) REQUIRE t.full_name IS UNIQUE;
CREATE CONSTRAINT column_full_name IF NOT EXISTS FOR (c:Column) REQUIRE c.full_name IS UNIQUE;

// 第二步：创建 Table 节点
UNWIND [...] AS t
MERGE (n:Table {full_name: t.full_name})
SET n.id = t.full_name, ...

// 第三步：创建 Column 节点
UNWIND [...] AS c
MERGE (n:Column {full_name: c.full_name})
SET n.schema = c.schema, ...

// 第四步：创建 HAS_COLUMN 关系
UNWIND [...] AS rel
MATCH (t:Table {full_name: rel.table_full_name})
MATCH (c:Column {full_name: rel.column_full_name})
MERGE (t)-[:HAS_COLUMN]->(c);

// 第五步：创建 JOIN_ON 关系
UNWIND [...] AS rel
MATCH (src:Table {full_name: rel.src_full_name})
MATCH (dst:Table {full_name: rel.dst_full_name})
MERGE (src)-[r:JOIN_ON]->(dst)
SET r.cardinality = rel.cardinality, ...
```

**对比：**

| 属性 | `cql` | `cql_llm` | 是否相同 |
|-----|-------|----------|---------|
| 文件名 | `import_all.cypher` | `import_all.cypher` | ✅ 相同 |
| 文件结构 | 5 个步骤 | 5 个步骤 | ✅ 相同 |
| 约束语句 | `CREATE CONSTRAINT ...` | `CREATE CONSTRAINT ...` | ✅ 相同 |
| 节点创建 | `MERGE + SET` | `MERGE + SET` | ✅ 相同 |
| 关系创建 | `MERGE` | `MERGE` | ✅ 相同 |
| 幂等性 | ✅ 支持 | ✅ 支持 | ✅ 相同 |

**结论：** 生成的 Cypher 文件**格式完全相同**，只是数据来源不同。

#### 4.2 Table 节点属性

**Cypher 语句：**

```cypher
SET n.id       = t.full_name,
    n.schema   = t.schema,
    n.name     = t.name,
    n.comment  = t.comment,
    n.pk       = t.pk,
    n.uk       = t.uk,
    n.fk       = t.fk,
    n.logic_pk = t.logic_pk,
    n.logic_fk = t.logic_fk,
    n.logic_uk = t.logic_uk,
    n.indexes  = t.indexes,
    n.table_domains = CASE
        WHEN t.table_domains IS NOT NULL AND size(t.table_domains) > 0
            THEN t.table_domains
        ELSE coalesce(n.table_domains, [])
    END,
    n.table_category = CASE
        WHEN t.table_category IS NOT NULL
            THEN t.table_category
        ELSE n.table_category
    END;
```

**对比：**

| 属性 | `cql` | `cql_llm` | 差异说明 |
|-----|-------|----------|---------|
| `table_domains` | 可能为空 `[]` | 通常有值 | 取决于输入 JSON |
| `table_category` | 可能为 `null` | 通常有值 | 取决于输入 JSON |
| 其他属性 | 格式相同 | 格式相同 | ✅ 完全相同 |

**数据质量差异：**

| 属性 | `cql`（来自 `--step json`） | `cql_llm`（来自 `--step json_llm`） |
|-----|---------------------------|----------------------------------|
| `table_domains` | ❌ 通常为空 `[]` | ✅ LLM 推断的业务主题（如果使用 `--domain`） |
| `table_category` | ❌ 通常为 `null` | ✅ LLM 分类结果（`fact`/`dim`/`bridge`） |
| `comment` | ✅ 数据库原生注释 | ✅ 数据库注释 + LLM 补全 |
| `semantic_role` | ⭕ 可能有（取决于配置） | ✅ LLM 增强的语义角色 |

---

## 三、执行流程对比

### 1. `cql` 命令执行流程

```
┌─────────────────────────────────────────────┐
│  metaweave metadata --step cql              │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  1. 创建 CQLGenerator(config_path)          │
│     - json_dir = output/json (默认)         │
│     - rel_dir = output/rel                  │
│     - cql_dir = output/cql                  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  2. generator.generate()                    │
│     ├─ JSONReader(json_dir, rel_dir)        │
│     │   ├─ 读取 output/json/*.json          │
│     │   └─ 读取 output/rel/relationships_*.json │
│     │                                        │
│     └─ CypherWriter(cql_dir)                │
│         └─ 写入 output/cql/import_all.cypher │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  3. 输出结果统计                            │
│     - 表节点数                              │
│     - 列节点数                              │
│     - 关系数                                │
│     - 输出文件列表                          │
└─────────────────────────────────────────────┘
```

### 2. `cql_llm` 命令执行流程

```
┌─────────────────────────────────────────────┐
│  metaweave metadata --step cql_llm          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  1. 创建 CQLGenerator(config_path)          │
│     - json_dir = output/json (默认)         │
│     - rel_dir = output/rel                  │
│     - cql_dir = output/cql                  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  2. CLI 层面覆盖 json_dir                   │
│     ✅ json_dir = output/json_llm           │
│     ✅ 检查目录是否存在                     │
│     ✅ 如果不存在，提示先执行 json_llm      │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  3. generator.generate()                    │
│     ├─ JSONReader(json_dir, rel_dir)        │
│     │   ├─ 读取 output/json_llm/*.json      │
│     │   └─ 读取 output/rel/relationships_*.json │
│     │                                        │
│     └─ CypherWriter(cql_dir)                │
│         └─ 写入 output/cql/import_all.cypher │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  4. 输出结果统计（LLM 流程）                │
│     - 表节点数                              │
│     - 列节点数                              │
│     - 关系数                                │
│     - 输出文件列表                          │
└─────────────────────────────────────────────┘
```

### 3. 流程对比表

| 步骤 | `cql` | `cql_llm` | 差异 |
|-----|-------|----------|------|
| 1. 创建生成器 | ✅ `CQLGenerator(config_path)` | ✅ `CQLGenerator(config_path)` | ✅ 相同 |
| 2. 覆盖 json_dir | ❌ 不覆盖 | ✅ 覆盖为 `json_llm` | ❌ 不同 |
| 3. 目录存在性检查 | ❌ 无（由 JSONReader 处理） | ✅ CLI 层面明确检查 | ❌ 不同 |
| 4. 读取 JSON | ✅ `JSONReader(json_dir, rel_dir)` | ✅ `JSONReader(json_dir, rel_dir)` | ✅ 相同 |
| 5. 生成 Cypher | ✅ `CypherWriter.write_all()` | ✅ `CypherWriter.write_all()` | ✅ 相同 |
| 6. 输出统计 | ✅ "CQL 生成结果统计" | ✅ "CQL 生成结果统计（LLM 流程）" | ⭕ 标题略有不同 |

---

## 四、配置文件参数

### 1. 相关配置项

**配置文件：** `configs/metadata_config.yaml`

```yaml
output:
  # Step 2: 表/列画像输出配置
  json_directory: output/json        # ← cql 使用
  json_llm_directory: output/json_llm  # ← cql_llm 使用（已废弃，建议统一）

  # Step 3: 关系发现输出配置
  rel_directory: output/rel          # ← 两者共用

  # Step 4: CQL 生成输出配置
  cql_directory: output/cql          # ← 两者共用（⚠️ 会覆盖）
```

### 2. 配置对比

| 配置项 | `cql` 使用 | `cql_llm` 使用 | 建议 |
|-------|-----------|--------------|------|
| `json_directory` | ✅ 是 | ❌ 否 | 统一输入源后，两者都用此配置 |
| `json_llm_directory` | ❌ 否 | ✅ 是 | 已废弃，建议删除 |
| `rel_directory` | ✅ 是 | ✅ 是 | 保持共用 |
| `cql_directory` | ✅ 是 | ✅ 是 | ⚠️ 注意覆盖问题 |

### 3. 配置建议

#### 方案 1：统一输入源（推荐）

```yaml
output:
  json_directory: output/json      # 统一输入源
  # json_llm_directory: output/json_llm  # 删除此配置
  rel_directory: output/rel
  cql_directory: output/cql
```

**修改代码：**
- 修改 `cql_llm` 步骤，不再覆盖 `json_dir`
- 两个命令使用相同的 JSON 输入源

#### 方案 2：分离输出目录（避免覆盖）

```yaml
output:
  json_directory: output/json
  json_llm_directory: output/json_llm
  rel_directory: output/rel
  cql_directory: output/cql          # cql 使用
  cql_llm_directory: output/cql_llm  # cql_llm 使用（新增）
```

**修改代码：**
- 修改 `cql_llm` 步骤，覆盖 `cql_dir` 为 `cql_llm_directory`

---

## 五、使用场景对比

### 1. `cql` 命令使用场景

**适用情况：**
- ✅ 只需要基础的元数据（表名、列名、数据类型、约束等）
- ✅ 不需要 LLM 增强的注释和语义信息
- ✅ 数据库注释已经很完善
- ✅ 不需要 `table_domains` 和 `table_category` 分类

**前置步骤：**

```bash
# 方案 1：使用基础 JSON
metaweave metadata --step json
metaweave metadata --step rel
metaweave metadata --step cql

# 方案 2：使用 LLM 增强 JSON（不使用 --domain）
metaweave metadata --step json_llm
metaweave metadata --step rel
metaweave metadata --step cql
```

**优点：**
- ⚡ 执行速度快（不需要 LLM 调用）
- 💰 成本低（无 API 调用费用）
- 🔒 数据准确（来自数据库原生信息）

**缺点：**
- ❌ 缺少语义增强
- ❌ 缺少业务主题分类
- ❌ 缺少表类型分类

### 2. `cql_llm` 命令使用场景

**适用情况：**
- ✅ 需要 LLM 增强的注释和语义信息
- ✅ 需要 `table_domains`（业务主题分类）
- ✅ 需要 `table_category`（表类型分类：fact/dim/bridge）
- ✅ 数据库注释不完善，需要补全
- ✅ 需要更丰富的语义角色（identifier, datetime, metric 等）

**前置步骤：**

```bash
# 必须先执行 json_llm（可选 --domain）
metaweave metadata --step json_llm [--domain]
metaweave metadata --step rel_llm [--domain] [--cross-domain]
metaweave metadata --step cql_llm
```

**优点：**
- ✅ 语义信息丰富
- ✅ 支持业务主题分类
- ✅ 支持表类型分类
- ✅ 注释更完善

**缺点：**
- ⏱️ 执行速度慢（需要 LLM 调用）
- 💰 成本高（API 调用费用）
- ⚠️ 需要先执行 `json_llm`

### 3. 场景对比表

| 场景 | 推荐命令 | 理由 |
|-----|---------|------|
| 快速原型开发 | `cql` | 速度快，成本低 |
| 生产环境（无 LLM） | `cql` | 数据准确，稳定可靠 |
| 生产环境（有 LLM） | `cql_llm` | 语义丰富，业务友好 |
| 需要业务主题分类 | `cql_llm` | 必须使用 `--domain` |
| 需要表类型分类 | `cql_llm` | LLM 自动分类 |
| 数据库注释完善 | `cql` | 无需 LLM 补全 |
| 数据库注释缺失 | `cql_llm` | LLM 自动补全 |

---

## 六、常见问题

### Q1：两个命令可以同时使用吗？

**答：不推荐，会相互覆盖。**

```bash
# ❌ 错误用法：后者会覆盖前者
metaweave metadata --step cql
metaweave metadata --step cql_llm  # 覆盖上一步的输出

# ✅ 正确用法：只使用其中一个
metaweave metadata --step cql

# 或者
metaweave metadata --step cql_llm
```

**解决方案：**
1. **手动备份**：在执行第二个命令前，重命名 `import_all.cypher`
2. **修改配置**：使用不同的 `cql_directory`
3. **只执行一个**：根据需求选择 `cql` 或 `cql_llm`

### Q2：`cql_llm` 必须使用 `json_llm` 目录吗？

**答：是的，这是硬编码的行为。**

**代码位置：** `metaweave/cli/metadata_cli.py` 第 385-387 行

```python
json_llm_dir = generator._resolve_path(
    generator.config.get("output", {}).get("json_llm_directory", "output/json_llm")
)
```

**如果希望使用统一的 `json` 目录：**

需要修改代码，将 `cql_llm` 改为读取 `json_directory`：

```python
# 修改后的代码
json_dir = generator._resolve_path(
    generator.config.get("output", {}).get("json_directory", "output/json")
)
generator.json_dir = json_dir
```

### Q3：生成的 Cypher 文件有格式差异吗？

**答：没有，格式完全相同。**

两个命令使用相同的 `CypherWriter.write_all()` 方法，生成的 Cypher 文件格式、结构、语法完全一致。

**唯一差异：数据内容**
- `cql`：来自 `output/json`（基础元数据）
- `cql_llm`：来自 `output/json_llm`（LLM 增强元数据）

### Q4：关系 JSON 可以混用吗？

**答：可以，两个命令使用相同的关系目录。**

```bash
# 场景 1：基础 JSON + 规则关系
metaweave metadata --step json
metaweave metadata --step rel
metaweave metadata --step cql

# 场景 2：LLM JSON + 规则关系
metaweave metadata --step json_llm
metaweave metadata --step rel
metaweave metadata --step cql_llm

# 场景 3：LLM JSON + LLM 关系
metaweave metadata --step json_llm --domain
metaweave metadata --step rel_llm --domain
metaweave metadata --step cql_llm

# 场景 4：基础 JSON + LLM 关系（不推荐，但可以工作）
metaweave metadata --step json
metaweave metadata --step rel_llm
metaweave metadata --step cql
```

**结论：** 关系来源（`rel` vs `rel_llm`）不影响 CQL 生成。

### Q5：如何选择使用哪个命令？

**决策树：**

```
需要 table_domains 或 table_category？
├─ 是 → 使用 cql_llm
│        └─ 前置：metaweave metadata --step json_llm [--domain]
│
└─ 否 → 需要 LLM 增强的注释？
         ├─ 是 → 使用 cql_llm
         │        └─ 前置：metaweave metadata --step json_llm
         │
         └─ 否 → 使用 cql
                  └─ 前置：metaweave metadata --step json
```

---

## 七、代码层面的差异

### 1. CLI 层面

**文件：** `metaweave/cli/metadata_cli.py`

| 差异点 | `cql`（432-465 行） | `cql_llm`（376-429 行） |
|-------|-------------------|----------------------|
| 创建生成器 | `CQLGenerator(config_path)` | `CQLGenerator(config_path)` |
| 覆盖 json_dir | ❌ 不覆盖 | ✅ 覆盖为 `json_llm_directory` |
| 目录检查 | ❌ 无 | ✅ 检查 `json_llm_dir.exists()` |
| 错误提示 | 通用 | "请先执行 --step json_llm" |
| 日志信息 | "开始生成 Neo4j CQL..." | "开始生成 Neo4j CQL（LLM 流程）..." |
| 结果标题 | "CQL 生成结果统计" | "CQL 生成结果统计（LLM 流程）" |
| 完成消息 | "✨ CQL 生成完成！" | "✨ CQL 生成完成（LLM 流程）！" |

**代码行数：**
- `cql`: 34 行（432-465 行）
- `cql_llm`: 54 行（376-429 行）
- **差异：** `cql_llm` 多了 20 行（主要是目录覆盖和检查逻辑）

### 2. 核心逻辑层面

**文件：** `metaweave/core/cql_generator/generator.py`

| 差异点 | `cql` | `cql_llm` | 是否相同 |
|-------|-------|----------|---------|
| `CQLGenerator.__init__()` | ✅ 使用 | ✅ 使用 | ✅ 相同 |
| `CQLGenerator.generate()` | ✅ 使用 | ✅ 使用 | ✅ 相同 |
| `JSONReader.read_all()` | ✅ 使用 | ✅ 使用 | ✅ 相同 |
| `CypherWriter.write_all()` | ✅ 使用 | ✅ 使用 | ✅ 相同 |

**结论：** 核心逻辑层面**完全共享**，无任何差异。

### 3. 代码复用率

**统计：**
- **CLI 层面差异代码：** 约 20 行（占比 < 5%）
- **核心逻辑共享代码：** 约 400+ 行（占比 > 95%）

**设计评价：** ⭐⭐⭐⭐⭐（高度复用，易于维护）

---

## 八、总结

### 1. 核心差异

| 对比维度 | `cql` | `cql_llm` |
|---------|-------|----------|
| **输入 JSON 目录** | `output/json` | `output/json_llm` |
| **其他所有方面** | 完全相同 | 完全相同 |

### 2. 关键结论

1. **唯一本质差异：输入的表/列 JSON 目录不同**
2. **所有生成逻辑、输出格式、Cypher 语法完全相同**
3. **两个命令会覆盖同一个输出文件**
4. **关系 JSON 输入相同，可以混用**
5. **代码高度复用（> 95%），CLI 层面轻量区分**

### 3. 使用建议

**选择 `cql`：**
- ✅ 快速原型开发
- ✅ 数据库注释完善
- ✅ 不需要业务分类
- ✅ 追求速度和成本

**选择 `cql_llm`：**
- ✅ 需要业务主题分类（`table_domains`）
- ✅ 需要表类型分类（`table_category`）
- ✅ 数据库注释不完善
- ✅ 追求语义丰富度

**避免同时使用：**
- ❌ 两者输出到同一文件，会相互覆盖
- ❌ 如需同时使用，需手动备份或修改配置

### 4. 改进建议

#### 建议 1：统一输入源

**问题：** `json_llm` 目录已废弃，但 `cql_llm` 仍然硬编码使用它。

**方案：** 修改 `cql_llm` 使用 `json_directory`，删除 `json_llm_directory` 配置。

**优点：**
- ✅ 简化配置
- ✅ 统一数据流
- ✅ 避免混淆

#### 建议 2：避免输出覆盖

**问题：** 两个命令输出到同一文件，后执行的会覆盖前者。

**方案：**
1. **文档明确警告**（当前已有）
2. **CLI 检测冲突**：执行前检查文件是否存在，提示用户
3. **分离输出目录**：`cql_directory` vs `cql_llm_directory`
4. **添加后缀**：`import_all.cypher` vs `import_all_llm.cypher`

#### 建议 3：合并命令

**问题：** 两个命令逻辑高度重复，只是输入目录不同。

**方案：** 合并为一个命令，通过参数区分：

```bash
# 方案 1：添加 --source 参数
metaweave metadata --step cql --source json      # 使用 json 目录
metaweave metadata --step cql --source json_llm  # 使用 json_llm 目录

# 方案 2：自动检测
metaweave metadata --step cql  # 自动检测 json 或 json_llm 目录
```

**优点：**
- ✅ 简化命令
- ✅ 减少维护成本
- ✅ 用户更易理解

---

## 变更历史

| 日期 | 版本 | 说明 |
|-----|------|------|
| 2025-12-26 | 1.0 | 初始版本 |

