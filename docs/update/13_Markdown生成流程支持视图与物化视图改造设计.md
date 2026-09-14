# Markdown 生成流程支持视图与物化视图改造设计

## 1. 文档目的

本文设计直接执行 `--step md` 时对以下 PostgreSQL 数据库对象的支持：

- `table`
- `view`
- `materialized_view`

本次改造只处理 Markdown 单步骤生成流程，不放开 `standard`，不修改关系发现、CQL、
Neo4j、Milvus、pgvector、SQL RAG 或 REST API。

改造完成后，以下命令应能使用当前配置正常执行：

```bash
metaweave metadata \
  --config configs/metadata_config.yaml \
  --step md \
  --clean
```

## 2. 当前状态与问题

### 2.1 当前依赖关系

`md` 只依赖 `ddl` 产物：

```text
--step ddl
    ↓
output/ddl/*.sql
    ↓
DDLLoader
    ↓
--step md
    ↓
output/md/*.md
```

`md` 当前具有以下边界：

- 不访问 PostgreSQL。
- 不读取 `output/json`。
- 不执行列画像、逻辑主键识别或表分类。
- 使用 DDL 文件中的对象结构、中文注释和样例数据。
- 当前步骤级 LLM 初始化只对 `ddl` 生效，因此 `md` 不调用 LLM。

### 2.2 当前命令无法使用正式配置执行

当前 `configs/metadata_config.yaml` 启用了：

```yaml
database:
  include_object_types:
    - table
    - view
    - materialized_view
```

但 `metadata_cli.py` 将 `md` 放在不支持 View/MV 的步骤集合中，因此直接执行会在 CLI
前置检查阶段失败：

```text
当前组合步骤的下游处理尚未完成 view 和 materialized_view 适配
```

### 2.3 DDL 文件被强制标记为 table

当前 `_get_tables_from_ddl_dir()` 只从文件名提取对象名称，随后统一构造：

```python
DatabaseObjectRef(schema, object_name, "table")
```

这会导致：

- View/MV 的真实对象类型丢失。
- `database.include_object_types` 无法真正过滤 MD 输入。
- 即使配置只选择 `table`，MD 仍可能处理物化视图 SQL 文件。
- 处理统计把所有对象都显示为“表”。

### 2.4 Markdown 缺少对象类型

当前标题格式为：

```markdown
# public.mv_category_sales（商品分类销售汇总表）
```

标题无法明确说明该对象是基础表、视图还是物化视图。Markdown 会被 Domain 生成、
SQL RAG 和 LLM 上下文使用，对象类型缺失可能使派生数据被误认为基础数据。

### 2.5 DDLLoader 无法解析生成器当前的索引语法

当前索引正则主要支持：

```sql
CREATE INDEX idx_name ON public.object_name (column_name);
```

而生成器实际可能输出：

```sql
CREATE UNIQUE INDEX uq_mv_category_sales_category_id
ON public.mv_category_sales USING btree (category_id);
```

现有正则无法可靠处理 `USING btree`，因此物化视图的唯一索引可能无法进入 Markdown。

### 2.6 错误统计存在歧义

当前 MD 内部捕获部分错误并更新失败数量，外层调度仍可能将该对象计为成功，导致同一对象
同时出现在成功和失败统计中。Markdown 保存失败时也缺少统一的失败传播契约。

## 3. 改造目标

完成后应满足：

1. 直接 `--step md` 支持 Table、View 和 Materialized View。
2. 对象范围由 `database.include_object_types` 控制。
3. `--schemas`、`--tables` 和 `database.exclude_tables` 继续生效。
4. 对象类型来自 DDL 内容，不根据对象名称猜测。
5. Markdown 第一行明确包含对象类型。
6. View/MV 的对象注释、字段类型、字段注释和样例数据正确进入 Markdown。
7. 物化视图的独立唯一索引能够正确显示。
8. MD 不访问数据库、不调用 LLM。
9. 每个成功对象只计数一次，失败对象不计入成功数量。
10. `standard` 继续保持 View/MV 限制。

## 4. 范围边界

### 4.1 本次修改范围

- `metaweave/cli/metadata_cli.py`
- `metaweave/core/metadata/generator.py`
- `metaweave/core/metadata/formatter.py`
- `metaweave/core/metadata/ddl_loader.py`
- `configs/metadata_config.yaml` 中相关说明文字
- MD、DDLLoader、CLI 和汇总统计的相关测试

### 4.2 本次明确不修改

- `metadata_cli.py` 中 `standard` 的业务编排。
- `metaweave/cli/pipeline_cli.py`。
- JSON 3.0 格式及 JSON 生成流程。
- `rel`、`rel_llm` 关系发现。
- CQL 生成。
- Neo4j、Milvus、pgvector 加载。
- Domain 生成算法。
- SQL RAG 算法。
- REST API。

源码边界与行为边界需要区分：Markdown 第一行增加对象类型后，读取 Markdown 原文的
Domain 生成和 SQL RAG 会被动获得更明确的上下文，但本次不修改这些模块的代码。

### 4.3 对其他步骤的影响与隔离要求

本次只实现 `--step md` 的能力，不修改其他步骤的业务逻辑。不过，MD 入口和部分解析器是
共享代码，必须明确区分“主动修改其他步骤”和“其他流程复用 MD 后自然获得新产物”。

| 执行步骤或模块 | 是否修改其业务代码 | 是否可能被动受影响 | 影响与约束 |
|---|---:|---:|---|
| 直接 `--step ddl` | 否 | 否 | 数据库抽取和 DDL 文件格式必须保持不变 |
| 直接 `--step json` | 否 | 低 | 与 MD 共用 `DDLLoader`；最终 JSON 索引会由数据库目录重新抽取，JSON 产物必须保持不变 |
| 直接 `--step md` | 是 | 是 | 本次唯一目标，增加 View/MV、对象类型标题和独立唯一索引展示 |
| 直接 `--step rel/rel_llm` | 否 | 否 | 读取 JSON 和数据库，不读取 MD；候选与评分结果不得变化 |
| 直接 `--step cql/cql_llm` | 否 | 否 | 读取 JSON/关系产物，不读取 MD；CQL 结果不得变化 |
| `metadata --step standard` | 否 | 不纳入评估 | 完全排除在本次开发和验收范围之外，不开发其 View/MV 能力 |
| `pipeline generate` | 否 | 不纳入评估 | 完全排除在本次开发和验收范围之外，不开发其 View/MV 能力 |
| Domain 生成 | 否 | 是 | 会读取新版 MD 第一行，需验证现有 `name/name_comment/full` 模式兼容 |
| table schema loader | 否 | 是 | 会通过 `MDParser` 读取新版 MD，需验证对象名和字段注释不变 |
| SQL RAG | 否 | 是 | 会读取 Markdown 原文作为上下文，需验证读取过程不报错 |
| Neo4j/Milvus/pgvector 加载 | 否 | 原则上否 | 本次不改加载流程和数据模型；只有显式消费新版 MD 的 schema loader 需要兼容测试 |

#### 4.3.1 `standard` 和 `pipeline generate` 明确排除

本设计不修改、不测试，也不验收 `standard` 和 `pipeline generate` 对 View/MV 的支持。
两者不属于本次改造对象，因此不能将本次工作描述为：

- 为 `standard` 开发 View/MV 支持。
- 为 `pipeline generate` 开发 View/MV 支持。
- 验证 View/MV 可以经过上述组合流程继续流入 JSON、关系发现或 CQL。

本次只保证用户直接指定 `--step md` 时可以处理配置允许的 Table、View 和 Materialized
View。`standard` 和 `pipeline generate` 保持各自当前状态，相关适配应在后续串联流程改造
中单独设计和实施。

#### 4.3.2 `DDLLoader` 的共享影响

`DDLLoader` 同时被 `json` 和 `md` 使用。本次扩展索引解析后，JSON 加载 DDL 时也会得到更
完整的临时索引对象；但 `_process_table_from_ddl()` 随后会通过
`extractor.extract_json_indexes()` 使用 PostgreSQL 目录中的完整索引事实覆盖它们。因此：

- 不允许修改 JSON 格式。
- 不允许修改 JSON 中的约束、索引、字段画像、逻辑主键或表分类结果。
- 必须增加回归测试，证明相同数据库和 DDL 输入下，修改前后的 JSON 领域结果一致。
- DDLLoader 索引解析的错误策略不能让原本合法的 MetaWeave DDL 在 `--step json` 中新增
  失败。

如果实现中无法证明共享解析器不会改变 JSON 行为，应将新增索引解析封装为 DDLLoader 的
可复用辅助能力，并只在 MD 读取路径显式启用，不能把风险传给 JSON 步骤。

#### 4.3.3 Markdown 消费方的兼容条件

新版标题只能在对象名之后追加类型：

```markdown
# public.orders [table]（订单记录表）
```

对象名起始格式不得变化，字段列表格式不得变化，以保证：

- `MDParser.extract_table_name()` 仍返回 `public.orders`。
- `MDParser.get_column_descriptions()` 的结果完全一致。
- schema loader 生成的表名、字段名和字段描述不发生变化。
- Domain 与 SQL RAG 只新增对象类型上下文，不丢失既有内容。

#### 4.3.4 命令写入边界

执行：

```bash
metaweave metadata --config configs/metadata_config.yaml --step md --clean
```

只能写入或清理 `output.markdown_directory`，不得修改：

- `output/ddl`
- `output/json`
- `output/rel`
- `output/cql`
- Domain、维表或 SQL RAG 配置文件

配置文件只更新说明文字，不更改任何现有配置值，因此不会改变 DDL/JSON 的对象选择结果。

## 5. 目标执行流程

```text
加载配置
  ↓
校验 output.ddl_directory
  ↓
扫描当前 database + schema 对应的 DDL 文件
  ↓
DDLLoader 解析真实对象类型和元数据
  ↓
按照 include_object_types / --schemas / --tables / exclude_tables 过滤
  ↓
从 DDL 读取注释、字段、约束、索引和样例数据
  ↓
生成带对象类型的 Markdown
  ↓
写入 output/md
  ↓
按 Table / View / Materialized View 汇总
```

整个流程只访问本地文件系统。

## 6. CLI 修改设计

### 6.1 放开直接 md

当前：

```python
unsupported_view_steps = {"standard", "md"}
```

修改为：

```python
unsupported_view_steps = {"standard"}
```

这里只放开独立 `--step md`。`standard` 后续仍包含尚未适配 View/MV 的关系发现和 CQL，
因此不能同步放开。

### 6.2 改进 DDL 依赖预检

MD 启动前继续检查 DDL 目录，但检查范围需要收紧：

1. 读取 `output.ddl_directory`。
2. 检查目录是否存在。
3. 读取配置中的数据库名。
4. 只匹配当前数据库的 DDL 文件：

   ```text
   {database}.{schema}.{object}.sql
   ```

5. 目录中只有其他数据库的 SQL 文件时，应视为当前数据库没有 DDL 输入。
6. 精确的 schema、类型和对象过滤交给生成器完成。

### 6.3 保持 clean 语义

```bash
--step md --clean
```

只清理 `output.markdown_directory`，不得清理或修改 `output/ddl`。

## 7. DDL 对象枚举设计

### 7.1 替换旧接口

将：

```python
_get_tables_from_ddl_dir(schema) -> List[str]
```

替换为语义准确的接口：

```python
_get_objects_from_ddl_dir(schema) -> List[DatabaseObjectRef]
```

### 7.2 枚举规则

对每个 schema：

1. 使用当前数据库名构造 glob 模式。
2. 按文件名排序，保证输出顺序稳定。
3. 严格校验 `{database}.{schema}.{object}.sql` 文件名。
4. 使用 `DDLLoader` 解析文件。
5. 从 `parsed.metadata.table_type` 获取对象类型。
6. 只接受 `table`、`view`、`materialized_view`。
7. 构造带真实类型的 `DatabaseObjectRef`。

不得使用 `mv_`、`view_`、`v_` 等名称前缀推断类型。

### 7.3 统一过滤顺序

推荐过滤顺序：

1. database 文件名前缀。
2. schema。
3. `database.include_object_types`。
4. CLI `--tables`。
5. `database.exclude_tables`。

这样可以保持 DDL、JSON 和 MD 的对象选择语义一致。

## 8. DDL 解析缓存

对象枚举需要解析 DDL 才能知道真实类型，生成 Markdown 时又需要完整的 `ParsedDDL`。
为避免同一文件读取两次，建议在一次 MD 作业中维护只读缓存：

```python
self._md_parsed_ddl = {
    ("public", "orders"): ParsedDDL(...),
    ("public", "mv_category_sales"): ParsedDDL(...),
}
```

要求：

- 每次 `generate(step="md")` 开始前清空缓存。
- 枚举阶段写入缓存。
- 工作线程只读取缓存。
- 直接调用单对象内部接口时，缓存未命中可以回退到 `load_table()`。
- 不把缓存跨作业持久化，避免读取旧 DDL。

## 9. 单对象 MD 处理设计

### 9.1 修改函数签名

将：

```python
_process_table_from_ddl_for_md(schema, table, result)
```

修改为：

```python
_process_table_from_ddl_for_md(
    schema,
    object_name,
    object_type,
    result,
)
```

### 9.2 处理步骤

1. 从 MD DDL 缓存取得 `ParsedDDL`。
2. 缓存未命中时通过 `DDLLoader.load_table()` 回退读取。
3. 校验解析后的 `metadata.table_type` 与 `object_type` 一致。
4. 设置当前数据库名。
5. 将 DDL 中的样例记录转换为 DataFrame。
6. 不执行数据库采样。
7. 不执行字段画像、逻辑主键识别和表分类。
8. 不调用 LLM。
9. 调用 formatter 生成单个 Markdown。
10. 保存成功后更新对象类型计数。

### 9.3 删除不可达 LLM 分支

当前 MD 处理函数仍保留：

```python
if self.comment_enabled:
    self.comment_generator.enrich_metadata_with_comments(...)
```

新的步骤级 LLM 初始化只对 DDL 生效，这段在 MD 中不可达。建议删除，明确 MD 只使用 DDL
已经生成或保留的注释。

如果以后需要 MD 独立调用 LLM，应另行设计 `md_generation.comments`，不能复用 DDL 或
JSON 的开关。

## 10. Markdown 输出契约

### 10.1 标题包含对象类型

推荐格式：

```markdown
# public.orders [table]（订单记录表）
```

```markdown
# public.order_summary [view]（订单汇总视图）
```

```markdown
# public.mv_category_sales [materialized_view]（商品分类销售汇总表）
```

使用稳定的英文枚举值，避免翻译差异，也方便后续程序和 LLM 识别。

对象类型放在第一行的原因：

- `DomainGenerator` 的默认 `name_comment` 模式只读取第一条非空行。
- `MDParser` 当前从标题起始位置提取 `schema.object_name`，在对象名后增加 `[type]` 不会
  改变表名提取结果。

### 10.2 字段格式保持兼容

字段部分继续使用：

```markdown
## 字段列表：
- category_id (integer) - 商品类别唯一标识ID [示例: 9, 3]
```

现有 `MDParser` 可以继续解析字段名和字段注释。

### 10.3 无样例数据

普通 View 可能没有生成样例数据。此时允许正常生成 Markdown：

```markdown
- category_id (integer) - 商品类别唯一标识ID [示例: null]
```

缺少样例不是对象生成失败条件。

## 11. 索引解析与展示

### 11.1 DDLLoader 解析能力

更新 DDLLoader 的索引解析，使其至少支持生成器当前可能写出的：

```sql
CREATE [UNIQUE] INDEX index_name
ON schema.object_name
[USING method]
(index_keys)
[INCLUDE (included_columns)]
[WHERE predicate];
```

需要保留：

- 索引名。
- 索引方法。
- 普通索引键。
- 是否唯一。
- INCLUDE 列。
- 部分索引条件。
- 能够获得时保留完整定义。

表达式索引的字段拆分不能简单按逗号或第一个右括号截断。实现时应使用能够处理括号层级
的拆分逻辑，或至少对无法可靠拆分的表达式保留完整定义，不能生成错误的字段列表。

### 11.2 Markdown 展示规则

推荐输出：

```markdown
- 主键约束 cinema_halls_pkey: hall_id
- 唯一约束 uq_name: name
- 唯一索引 uq_mv_category_sales_category_id (btree): category_id
- 索引 idx_screenings_start_time (btree): start_time
```

去重规则：

- 主键支撑索引不重复显示。
- 唯一约束支撑索引不重复显示。
- 独立唯一索引必须显示。
- 物化视图唯一索引通常不是表约束，必须作为“唯一索引”展示。
- 普通索引继续展示为“索引”。

## 12. 结果统计

MD 保存成功后更新现有 `GenerationResult.processed_object_counts`：

```python
{
    "table": 6,
    "view": 0,
    "materialized_view": 1,
}
```

CLI 输出改为：

```text
✅ 成功处理: 7 个对象
  - Table: 6 个
  - View: 0 个
  - Materialized View: 1 个
💬 生成注释: 0 个
📁 输出文件: 7 个
```

日志中的“处理表”和“开始处理表”同步改为“处理对象”。

## 13. 错误处理契约

### 13.1 必须失败

以下情况命令应明确失败：

- DDL 目录不存在。
- 当前数据库没有任何 DDL 文件。
- DDL 文件名不符合既定格式且属于当前数据库的候选输入。
- 某个 DDL 无法解析。
- DDL 中的对象类型不是支持的三种类型。
- 枚举得到的对象类型与实际解析类型不一致。
- Markdown 保存失败。

### 13.2 允许继续

以下情况不是失败：

- View 没有样例数据。
- 对象没有物理约束。
- View 没有索引。
- 某个可选对象类型在当前 schema 中数量为零。

### 13.3 旧 View/MV DDL

View/MV 依赖 `OBJECT_METADATA` 提供可重建的字段定义。旧 DDL 缺少该块时，不应猜测字段
结构，应提示用户重新执行：

```bash
metaweave metadata \
  --config configs/metadata_config.yaml \
  --step ddl \
  --clean
```

### 13.4 成功与失败统计

单对象处理函数不应在捕获异常后正常返回并让外层继续记为成功。推荐由单对象函数抛出带
对象上下文的异常，统一交给顺序或并行调度器更新失败数量。

每个对象最终只能处于以下一种状态：

- 成功并生成一个 Markdown。
- 失败且不计入成功数量。

## 14. 配置说明

不增加新的配置项，继续复用：

```yaml
database:
  include_object_types:
    - table
    - view
    - materialized_view
```

将配置注释从：

```yaml
# --step ddl 要提取的数据库对象类型
```

更新为：

```yaml
# ddl、json、md 步骤允许处理的数据库对象类型
```

同一份对象范围配置有利于保证 DDL、JSON 和 Markdown 产物一致。本次不增加
`md_generation.object_types` 之类的重复配置。

## 15. 代码修改清单

本节按源码文件列出预计修改点。函数名以当前代码为准；实施过程中允许提取小型私有辅助
函数，但不得改变本节定义的职责边界。

### 15.1 生产代码改动总览

| 文件 | 修改级别 | 主要职责 | 是否必须修改 |
|---|---|---|---|
| `metaweave/cli/metadata_cli.py` | 小 | 放开直接 `md`，收紧 DDL 预检，修正 MD 汇总用语 | 是 |
| `metaweave/core/metadata/generator.py` | 中 | 从 DDL 枚举真实对象类型、过滤、缓存、处理与统计 | 是 |
| `metaweave/core/metadata/ddl_loader.py` | 中 | 解析 View/MV 元数据以及生成器输出的完整索引语法 | 是 |
| `metaweave/core/metadata/formatter.py` | 小 | 在 Markdown 中展示对象类型和独立唯一索引 | 是 |
| `configs/metadata_config.yaml` | 极小 | 更新 `include_object_types` 的适用步骤说明 | 是 |
| `metaweave/core/metadata/models.py` | 无 | 复用现有对象类型、索引和统计模型 | 原则上否 |
| `metaweave/core/table_schema/md_parser.py` | 无 | 现有标题正则兼容新增的 `[object_type]` | 原则上否 |
| `metaweave/core/metadata/domain_generator.py` | 无 | 自动读取新版 Markdown 第一行 | 否 |
| `metaweave/cli/pipeline_cli.py` | 无 | 本次不放开组合流水线 | 否 |

### 15.2 `metaweave/cli/metadata_cli.py`

#### 15.2.1 `metadata_command()` 的对象类型前置限制

当前代码：

```python
unsupported_view_steps = {"standard", "md"}
```

修改为：

```python
unsupported_view_steps = {"standard"}
```

这项改动只允许直接执行 `--step md` 时处理 View/MV。不得删除 `standard` 的限制，也不得
修改 `standard` 的步骤列表和调度逻辑。

#### 15.2.2 直接 MD 的 DDL 依赖预检

修改 `if step.lower() == "md":` 分支，替换当前“目录内任意 `*.sql` 即通过”的判断：

1. 保留 DDL 目录存在性检查。
2. 读取当前配置的 `database.database`。
3. 只统计 `{database}.*.*.sql` 候选文件。
4. 没有当前数据库候选文件时抛出 `click.UsageError`。
5. 提示信息使用“数据库对象”而不是“表”。
6. 不在 CLI 层解析每个 DDL；对象类型、schema、对象名和排除规则由生成器统一处理。

CLI 预检只负责尽早给出易懂错误，不能形成第二套对象过滤实现。

#### 15.2.3 直接命令的结果展示

当前结果展示只把 `ddl/json` 视为“对象”流程：

```python
if step_lower in {"ddl", "json"}:
```

需要把 `md` 纳入同一统计口径：

```python
if step_lower in {"ddl", "json", "md"}:
```

涉及两处：

- 成功数量及 Table/View/Materialized View 分类数量。
- 失败数量的单位，由“张表”改为“个对象”。

MD 的 `generated_comments` 应保持为 `0`，表示本步骤没有调用 LLM 生成注释。

#### 15.2.4 明确不修改的 CLI 代码

- `_clean_step_output_dir()`：现有 `md` 清理目录逻辑可以复用。
- `standard` 分支的 `steps = ["ddl", "md", "json", "rel", "cql"]`：本次不改。
- `standard` 内部的 MD 依赖检查和执行分支：本次不以 View/MV 为目标放开。
- 已存在但不可达的历史 `json_llm` 分支：与本改造无关。

### 15.3 `metaweave/core/metadata/generator.py`

这是本次改造的核心文件。

#### 15.3.1 导入与作业级缓存

从 `ddl_loader` 导入 `ParsedDDL`，并在 `MetadataGenerator` 中增加仅供 MD 作业使用的缓存：

```python
self._md_parsed_ddl: Dict[tuple[str, str], ParsedDDL] = {}
```

缓存键使用 `(schema_name, object_name)`。缓存只保存当前 `generate(step="md")` 扫描到的
DDL 解析结果，不跨作业复用。

#### 15.3.2 `generate()`

在确认 `active_step == "md"` 后、开始枚举前清空 `_md_parsed_ddl`。保持以下现有行为：

- MD 跳过 `_ensure_connector()` 和数据库连通测试。
- MD 不执行 `_configure_step_llm()` 中的任何 LLM 初始化；当前函数已经只允许 DDL 初始化
  LLM，无需扩展。
- schema 未显式传入时仍可从 DDL 文件推断。

如果对象枚举阶段发现某个候选 DDL 无法解析，异常必须进入 `GenerationResult`，命令最终
失败，不能把损坏文件静默当作“不存在的对象”。

#### 15.3.3 `_infer_schemas_from_ddl_dir()`

保留该函数，但细化为只扫描当前数据库的严格三段式文件名：

```text
{database}.{schema}.{object}.sql
```

要求：

- 文件排序后再处理。
- 忽略其他数据库的 DDL。
- 当前数据库前缀下格式异常的文件记录明确警告。
- 这里只推断 schema，不推断对象类型。

#### 15.3.4 替换 `_get_tables_from_ddl_dir()`

删除或重命名现有：

```python
_get_tables_from_ddl_dir(schema) -> List[str]
```

实现：

```python
_get_objects_from_ddl_dir(schema) -> List[DatabaseObjectRef]
```

具体职责：

1. 只扫描当前数据库和当前 schema 的 DDL。
2. 严格解析文件名取得对象名。
3. 调用 `_get_ddl_loader().load_table(schema, object_name)`。
4. 从 `ParsedDDL.metadata.table_type` 读取真实类型。
5. 校验类型属于 `table/view/materialized_view`。
6. 将 `ParsedDDL` 写入 `_md_parsed_ddl`。
7. 返回 `DatabaseObjectRef(schema, object_name, object_type)`。

函数名中的 `table` 应全部改成 `object`，避免继续把 View/MV 当表处理。

#### 15.3.5 `_get_tables_to_process()`

当前 MD 分支把全部 DDL 强制构造成 `object_type="table"`。修改为直接使用
`_get_objects_from_ddl_dir(schema)` 的返回值。

在进入通用 `--tables` 和 `exclude_tables` 过滤前，先应用：

```python
allowed_types = set(self._resolve_database_object_types())
```

只保留 `database_object.object_type in allowed_types` 的对象。随后复用现有：

- CLI `--tables` 精确对象名过滤。
- `_is_table_excluded()` 排除规则。

`_is_table_excluded()` 的历史函数名本次可以保留，避免无收益的全局重命名；其参数和实际
语义已经可用于三类数据库对象。

#### 15.3.6 `_process_tables_sequential()` 与 `_process_tables_parallel()`

功能逻辑不重写，只调整 MD 的显示与异常语义：

- `progress_desc` 在 `ddl/json/md` 中统一显示“处理对象”。
- 日志中的“处理表失败”改为“处理对象失败”。
- 单对象处理抛错时只由这一层累计 `failed_tables`。
- 只有 `_process_table()` 正常完成后才累计 `processed_tables`。

并行映射建议保存 `(schema, object_name, object_type)`，使错误日志可以包含对象类型。

#### 15.3.7 `_process_table()`

MD 分支必须把类型继续传下去：

```python
self._process_table_from_ddl_for_md(
    schema,
    table,
    object_type,
    result,
)
```

JSON 和 DDL 分支不因本次改造改变。

#### 15.3.8 `_process_table_from_ddl_for_md()`

函数签名增加 `object_type`，内部按以下顺序实现：

1. 优先从 `_md_parsed_ddl[(schema, object_name)]` 读取 `ParsedDDL`。
2. 缓存未命中时回退到 `DDLLoader.load_table()`，便于单元测试和内部单对象调用。
3. 校验 `parsed.metadata.table_type == object_type`。
4. 设置 `metadata.database`。
5. 将 `parsed.sample_records` 转换成 DataFrame。
6. 清空 MD 不使用的画像和逻辑主键字段。
7. 调用 `formatter.format_and_save(..., formats_override=["markdown"])`。
8. 检查返回值中确实存在 `markdown` 路径；缺失时抛出异常。
9. 保存成功后，在 `_result_lock` 下累计 `processed_object_counts[object_type]`。

删除当前不可达的 `if self.comment_enabled` 分支。MD 只能消费 DDL 已有注释，不得在此处
调用 `CommentGenerator`。

当前函数捕获 `DDLLoaderError` 后自行增加 `failed_tables` 并正常返回，这会让外层再次把同一
对象计为成功。修改后不在该函数内累计成功或失败总数；给错误补充对象上下文后继续抛出，
由顺序/并行调度器统一计数。

#### 15.3.9 `_generate_summary()`

将 MD 纳入对象统计：

- 成功和失败单位使用“个对象”。
- 输出 Table/View/Materialized View 三类数量。
- 不增加约束、画像、分类或 LLM 请求统计。

#### 15.3.10 `_get_ddl_loader()`

复用现有延迟初始化逻辑，不改变构造参数。该实例同时服务于对象枚举和 Markdown 生成，
而 `_md_parsed_ddl` 负责避免相同文件重复读取、重复解析。

### 15.4 `metaweave/core/metadata/ddl_loader.py`

#### 15.4.1 继续复用现有对象类型解析

以下现有能力无需重写：

- `_parse_content()`：有 View/MV `OBJECT_METADATA` 时走对象元数据分支，否则解析
  `CREATE TABLE`。
- `_metadata_from_object_block()`：读取 `object_type`、`object_name`、`object_comment`、
  字段类型和字段注释。
- `_parse_sample_records()`：兼容 `SAMPLED_RECORDS` 和旧 `SAMPLE_RECORDS` 块。
- `load_table()`：校验 DDL 中的 schema/object 与调用参数一致。

本次应为这些既有行为补测试，避免为了 MD 再实现一套 View/MV 解析器。

#### 15.4.2 替换 `INDEX_PATTERN` 的简单正则方案

当前 `INDEX_PATTERN` 无法处理 `USING btree`，并使用 `[^)]` 截取键列表，不能正确处理
表达式索引。建议改为“语句定位 + 括号层级解析”：

1. 定位 `CREATE [UNIQUE] INDEX ... ON schema.object` 语句。
2. 读取可选 `USING method`，缺省为 `btree`。
3. 复用或抽取现有 `_extract_parenthesized_block()`，取得完整索引键块。
4. 按顶层逗号拆分索引键，保留括号内逗号。
5. 解析可选 `INCLUDE (...)`。
6. 解析可选 `WHERE predicate`。
7. 将原始 `CREATE INDEX` 语句写入 `IndexInfo.definition`。

建议增加私有辅助函数，名称可采用：

```python
_iter_create_index_statements(content)
_parse_index_statement(statement, schema, object_name)
_split_top_level_expressions(value)
```

普通字段键写入 `columns`；全部键文本写入 `key_expressions`；INCLUDE 列写入
`included_columns`。无法可靠识别为普通字段的表达式不能伪装成列名。

DDL 生成器已经排除了约束支撑索引，因此从独立 `CREATE INDEX` 语句解析的索引应设置：

```python
is_constraint_backed = False
constraint_name = None
```

主键和唯一约束继续由约束解析器负责，不能在索引解析器中重复合成。

#### 15.4.3 解析兼容边界

本轮至少保证 MetaWeave 自己生成的未加引号 DDL 能完整回读。对任意 PostgreSQL 手写 DDL
的全语法支持不作为本次验收条件，但遇到无法可靠解析的 MetaWeave 产物必须失败，不能
静默丢失索引。

### 15.5 `metaweave/core/metadata/formatter.py`

#### 15.5.1 `generate_markdown()` 标题

根据 `metadata.table_type` 输出：

```markdown
# public.orders [table]（订单记录表）
```

在输出前校验类型只属于三种受支持值。不得从名称前缀猜测类型。

#### 15.5.2 `generate_markdown()` 索引区

当前实现只展示 `not idx.is_primary and not idx.is_unique` 的普通索引，会丢失 MV 的独立
唯一索引。修改为：

1. 排除 `is_primary=True` 的主键支撑索引。
2. 排除 `is_constraint_backed=True` 的约束支撑索引。
3. `is_unique=True` 的剩余索引以“唯一索引”展示。
4. 其他索引以“索引”展示。
5. 优先展示 `columns`；表达式键无法化为普通字段时，使用 `key_expressions` 或明确引用
   `definition`，不得输出空的冒号内容。
6. 有 INCLUDE 列或 WHERE 条件时保留这些信息，避免把部分唯一索引描述成无条件唯一。

主键、外键和唯一约束的现有 Markdown 文本保持不变。

#### 15.5.3 `_save_markdown()` 与 `format_and_save()`

不建议为了本次需求修改通用保存接口的异常约定。MD 单对象处理函数通过检查
`format_and_save()` 是否返回 `markdown` 路径来识别保存失败，并向外抛错。

这样可以修正 MD 成败统计，同时避免影响 DDL/JSON 现有调用方。

### 15.6 `configs/metadata_config.yaml`

只修改 `database.include_object_types` 上方的注释，明确配置同时作用于：

- `--step ddl`
- `--step json`
- `--step md`

不增加 `md_generation` 或其他对象类型配置，不改变当前三个已开启值。

### 15.7 本次原则上不修改的模型与下游模块

#### 15.7.1 `metaweave/core/metadata/models.py`

现有模型已经足够：

- `DatabaseObjectRef.object_type` 保存枚举阶段的真实类型。
- `TableMetadata.table_type` 保存 DDL 解析结果。
- `IndexInfo` 已有 `is_unique`、`is_primary`、`condition`、`is_constraint_backed`、
  `definition`、`included_columns` 和 `key_expressions`。
- `GenerationResult.processed_object_counts` 支持分类统计。

因此不新增数据类、不重命名 `processed_tables/failed_tables`。这两个历史字段继续表示处理
对象总数，界面文案负责使用“对象”。只有发现上述字段确实无法表达索引事实时，才允许对
模型做最小补充，并在实施记录中说明原因。

#### 15.7.2 `metaweave/core/table_schema/md_parser.py`

现有 `TABLE_NAME_PATTERN = r"^#\\s+([\\w.]+)"` 会在空格前结束匹配，因此可以从
`# public.orders [table]（...）` 中继续得到 `public.orders`。生产代码无需修改，但必须补
兼容测试。

#### 15.7.3 下游模块

以下生产代码不修改：

- `metaweave/core/metadata/domain_generator.py`
- `metaweave/core/loaders/table_schema_loader.py`
- `metaweave/core/sql_rag/`
- `metaweave/cli/pipeline_cli.py`
- `metaweave/core/relationships/`
- `metaweave/core/cql_generator/`

其中 Domain、schema loader 和 SQL RAG 会读取新版 Markdown，需要通过兼容测试确认其
现有读取逻辑不报错，但不在本次改造中新增业务能力。

### 15.8 测试代码修改清单

| 测试文件 | 计划 |
|---|---|
| `tests/unit/metaweave/test_ddl_loader.py` | 增加 `USING`、独立唯一索引、INCLUDE、WHERE、表达式键解析测试 |
| `tests/unit/metaweave/metadata/test_ddl_view_support.py` | 扩展 View/MV `OBJECT_METADATA`、字段注释、样例和索引回读测试 |
| `tests/unit/metaweave/metadata/test_formatter_sample_records_block.py` | 更新 MD 内部函数签名，验证缓存样例转换和类型校验 |
| `tests/unit/metaweave/metadata/test_formatter_markdown_fk_label.py` | 保留现有约束文本回归，并增加三类标题与独立唯一索引展示测试 |
| `tests/unit/metaweave/metadata/test_ddl_summary.py` | 增加 MD 分类数量和“个对象”CLI 输出测试 |
| `tests/unit/metaweave/metadata/test_md_view_support.py`（新增） | 覆盖 DDL 枚举、类型过滤、缓存、错误计数和 file-only 边界 |
| `tests/unit/metaweave/metadata/test_domain_generator.py` | 验证 `name_comment` 能消费带对象类型的第一行 |
| `tests/unit/metaweave/table_schema/test_md_parser.py`（按现有目录调整） | 验证新版标题仍能提取对象名和字段注释 |

如果测试目录中不存在最后一个路径，可在现有 MDParser 测试所在位置增加用例，不为追求
目录结构而移动已有测试。

### 15.9 明确禁止的扩大化修改

实施本设计时不得顺带进行以下修改：

- 重命名整个项目中的 `table`、`tables`、`processed_tables` 等历史接口。
- 修改 DDL 或 JSON 产物格式。
- 给 MD 增加数据库查询或独立 LLM 开关。
- 放开 `standard` 或 `pipeline generate` 对 View/MV 的限制。
- 修改关系发现、CQL、Neo4j、Milvus、pgvector、Domain 或 SQL RAG 的业务逻辑。
- 为兼容任意手写 PostgreSQL DDL 而把 DDLLoader 扩展成通用 SQL 解析器。

## 16. 实施顺序

1. 为 Table、View、MV 的 MD 输出建立测试夹具和当前失败基线。
2. 扩展 DDLLoader 索引解析，覆盖 `USING`、唯一索引、INCLUDE 和部分索引。
3. 增加 MD DDL 解析缓存。
4. 将 DDL 枚举改为返回真实类型的 `DatabaseObjectRef`。
5. 接入 `database.include_object_types` 过滤。
6. 修改 MD 单对象处理函数签名并校验类型。
7. 删除 MD 中不可达的 LLM 注释分支。
8. 修改 Markdown 标题和索引展示。
9. 修改对象分类统计和 CLI 输出。
10. 从直接 `md` 的 CLI 限制中移除 View/MV。
11. 更新配置注释。
12. 执行单元测试、兼容测试和真实 DDL 冒烟测试。
13. 通过代码差异检查确认没有修改 `standard` 和 `pipeline generate` 的业务编排；不执行
    两者的 View/MV 功能验收。

## 17. 测试计划

### 17.1 DDL 枚举与过滤

- 正确识别 Table、View 和 Materialized View。
- 配置只启用 `table` 时不处理 View/MV。
- 配置只启用 `view` 时不处理 Table/MV。
- 配置只启用 `materialized_view` 时只处理 MV。
- 三类全部启用时全部处理。
- `--schemas` 正确过滤。
- `--tables` 正确过滤。
- `database.exclude_tables` 正确过滤。
- 目录中其他数据库的 DDL 不进入当前作业。
- 输出对象顺序稳定。

### 17.2 Markdown 内容

- 三类对象标题包含正确类型。
- 对象注释正确。
- 字段名、类型、注释正确。
- 样例值正确。
- 无样例 View 使用 `null`，但仍成功生成。
- 主键、外键和唯一约束保持现有格式。
- 普通索引正确显示。
- MV 独立唯一索引正确显示。
- 约束支撑索引不重复显示。

### 17.3 读取兼容性

- `MDParser.extract_table_name()` 能从带 `[object_type]` 的标题提取原对象名。
- `MDParser.get_column_descriptions()` 保持不变。
- `DomainGenerator` 的 `name_comment` 模式能够读到对象类型。
- `DomainGenerator` 的 `name` 模式仍只使用文件名。
- SQL RAG 读取 Markdown 原文时不发生解析错误。
- table schema loader 从新版 Markdown 提取的对象名、字段名和字段描述与旧格式一致。

### 17.4 运行边界

- MD 不创建数据库连接。
- MD 不初始化或调用 LLM。
- MD 不读取 JSON。
- `--clean` 只清理 Markdown 目录。
- 执行 MD 前后，DDL、JSON、REL 和 CQL 目录的文件内容与修改时间不变化。
- 不把 `standard` 或 `pipeline generate` 纳入本次 View/MV 测试矩阵。

### 17.5 其他步骤回归

由于 `DDLLoader` 是共享模块，需要增加最小回归保护：

- 使用同一组 DDL 和数据库输入执行 `--step json`，确认 JSON 格式及领域结果保持一致。
- JSON 中的字段、约束、索引、画像、逻辑主键、分类和样例数据不能因 MD 改造变化。
- `--step ddl` 的输出格式与内容不因 Markdown 标题调整变化。
- rel/rel_llm 的候选生成和评分模块没有代码改动。
- cql/cql_llm 的读取器、生成器和产物格式没有代码改动。
- 通过 Git diff 核对本次生产代码修改仅限第 15 节列出的 MD 入口及共享解析/格式化位置。

### 17.6 错误路径

- DDL 目录不存在时失败。
- 当前数据库没有 DDL 时失败。
- View/MV 缺少有效 `OBJECT_METADATA` 时失败。
- 对象类型不一致时失败。
- Markdown 保存失败时只计为失败。
- 单个对象不能同时计入成功和失败。

### 17.7 真实冒烟测试

使用当前 `orders` 测试库的 DDL 产物执行：

```bash
metaweave metadata \
  --config configs/metadata_config.yaml \
  --step md \
  --clean
```

当前预期：

```text
Table: 6
View: 0
Materialized View: 1
总输出: 7
```

重点核对：

- `orders.public.orders.md`
- `orders.public.screenings.md`
- `orders.public.mv_category_sales.md`

## 18. 验收标准

完成改造后应满足：

1. 当前正式配置可以直接执行 `--step md`。
2. 6 张表和 1 个物化视图各生成一个 Markdown。
3. 所有 Markdown 第一行包含正确对象类型。
4. 配置对象类型过滤真实生效。
5. MV 唯一索引进入 Markdown，且不与约束重复。
6. 字段、注释和样例数据与 DDL 一致。
7. MD 不访问数据库、不调用 LLM。
8. 成功、失败和对象类型统计准确。
9. 现有 MDParser、Domain 输入和 SQL RAG 读取保持兼容。
10. `standard`、pipeline、关系发现、CQL 和加载器代码没有被修改。
11. DDL 和 JSON 产物及其领域语义不因本次 MD 改造变化。

## 19. 使用注意事项

`md --clean` 只清理 Markdown 输出，不清理 DDL 输入。如果数据库对象已经删除，但旧 DDL
文件仍留在 `output/ddl`，MD 无法通过数据库确认其是否过期，仍可能处理该文件。

建议在需要完整刷新时按顺序执行：

```bash
metaweave metadata \
  --config configs/metadata_config.yaml \
  --step ddl \
  --clean

metaweave metadata \
  --config configs/metadata_config.yaml \
  --step md \
  --clean
```

这样可以确保 Markdown 使用的是当前数据库对象对应的最新 DDL 快照。
