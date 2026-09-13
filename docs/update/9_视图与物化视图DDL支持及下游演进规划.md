# 视图与物化视图 DDL 支持及下游演进规划

日期：2026-09-13
状态：`--step ddl` 已实施；下游步骤仍按本文的分阶段方案等待适配。

## 实施记录

2026-09-13 已完成当前阶段的代码改造：

- `database.include_object_types` 支持 `table`、`view` 和 `materialized_view`，默认值仍为 `table`。
- DDL 对象发现改用 PostgreSQL 系统目录，并在整条提取和生成链路中保留对象类型。
- View 输出 `CREATE OR REPLACE VIEW`，Materialized View 输出 `CREATE MATERIALIZED VIEW`。
- Materialized View 会提取并输出普通索引和唯一索引；通过 PostgreSQL 返回的完整索引定义保留
  索引方法、表达式、`INCLUDE` 列和部分索引条件。由约束自动创建的索引不会被重复输出。
- 尚未适配的组合流程和下游步骤在配置了非表对象时会给出明确错误。
- DDL 类型渲染只对字符类型和 `numeric/decimal` 输出合法类型修饰符，整数的位宽元数据不会再
  被错误输出为 `INTEGER(32,0)`。
- DDL 样例使用保留 psycopg 原始标量类型的采样路径，读取数量由
  `output.ddl_options.sample_records.count` 决定；样例在内存中过滤全空行并按完整记录去重，查询
  不使用 `ORDER BY` 或数据库 `DISTINCT`。
- DDL 阶段不读取或输出对象行数；精确行数仍由后续 `json` 阶段负责。
- 机器可读元数据块只用于 View 和 Materialized View，内容包含对象类型、完整对象名、对象注释
  以及字段名、完整字段类型和字段注释；普通表继续以 `CREATE TABLE` 作为结构契约。
- 单元测试覆盖配置校验、对象发现、三类提取分支、View/MV DDL 和索引行为。
- PostgreSQL 17 实库验证成功处理 6 张表和 1 个物化视图，并正确生成物化视图唯一索引。

实库中没有普通 View，因此普通 View 当前由单元测试覆盖。

## 1. 背景

本次改造前，MetaWeave 的 `--step ddl` 只处理 PostgreSQL 普通表：

- 对象枚举查询使用 `pg_tables`。
- 对象存在性检查使用 `pg_tables`。
- 元数据提取器把 `table_type` 固定为 `table`。
- DDL 格式化器固定输出 `CREATE TABLE`。
- DDL 反向解析器只识别 `CREATE TABLE`。

虽然 `TableMetadata.table_type` 已预留 `table`、`view` 和
`materialized_view`，但改造前的执行链路没有真正实现 View 和 Materialized View。

本次规划希望让用户通过配置选择 `--step ddl` 要处理的数据库对象，并为后续
`md`、`json`、`json_llm`、`rel`、`rel_llm`、`cql`、`cql_llm` 和加载步骤保留稳定的
对象类型契约。

## 2. 已确认的阶段边界

### 2.1 当前阶段

当前改造只实现：

```text
--step ddl
```

本阶段支持从 PostgreSQL 发现、提取并输出以下对象：

```text
table
view
materialized_view
```

本阶段不实现 View 和 Materialized View 在以下步骤中的处理：

- `--step md`
- `--step json`
- `--step json_llm`
- `--step rel`
- `--step rel_llm`
- `--step cql`
- `--step cql_llm`
- Neo4j、Milvus、pgvector 等加载步骤

### 2.2 当前阶段的运行限制

在下游适配完成前，启用 `view` 或 `materialized_view` 时，只保证以下命令：

```bash
metaweave metadata \
  --config configs/metadata_config.yaml \
  --step ddl \
  --schemas public \
  --clean
```

不能把“DDL 已能生成 View 文件”解释为整个 `standard` 或 `pipeline generate` 已经支持
View。特别是当前 `DDLLoader` 只识别 `CREATE TABLE`，直接让 `md` 读取 View DDL 会产生
解析错误。

本阶段应增加清晰的兼容保护：当配置包含非 `table` 对象且用户执行尚未适配的组合流程时，
应在进入下游步骤前明确报错，不能等到 DDL 解析阶段以模糊异常失败。

## 3. 当前阶段配置设计

配置写入主配置文件：

```text
configs/metadata_config.yaml
```

位置为 `database` 节点：

```yaml
database:
  host: ${DB_HOST:localhost}
  port: ${DB_PORT:5432}
  database: ${DB_NAME:your_database}
  user: ${DB_USER:postgres}
  password: ${DB_PASSWORD:your_password}

  schemas:
    - public

  include_object_types:
    - table
    # - view
    # - materialized_view
```

### 3.1 支持值

| 配置值 | 含义 | PostgreSQL 对象 |
|---|---|---|
| `table` | 普通表，包括分区表 | `pg_class.relkind` 为 `r` 或 `p` |
| `view` | 普通视图 | `pg_class.relkind` 为 `v` |
| `materialized_view` | 物化视图 | `pg_class.relkind` 为 `m` |

配置值统一使用小写下划线形式。未知值、空列表和非列表类型应在启动阶段报出明确配置错误。

### 3.2 默认值与兼容性

未声明 `include_object_types` 时，等价于：

```yaml
database:
  include_object_types:
    - table
```

默认行为必须与当前版本一致，不能因为升级而自动把已有数据库中的 View 加入输出。

### 3.3 与 `--tables` 的关系

现有 `--tables` 参数继续保留。它表示在已经由 `include_object_types` 选中的对象中按名称过滤：

```text
include_object_types 决定允许的对象类型
--schemas            决定 schema 范围
--tables             决定对象名称范围
exclude_tables       执行最终排除
```

虽然参数名仍为 `--tables`，为了保持 CLI 兼容，本阶段不重命名。帮助文本可以说明该参数也可匹配
View 和 Materialized View 名称。

同一个 schema 中不能同时存在同名的表和视图，因此现有
`{database}.{schema}.{object}.sql` 文件名不需要增加对象类型后缀。

### 3.4 与 `exclude_tables` 的关系

本阶段保留已有 `database.exclude_tables`，并让它对三种对象统一生效。暂不引入功能重复的
`exclude_objects`。配置文档应说明这里的 `tables` 是历史命名。

## 4. 数据库对象模型

建议新增轻量对象引用模型，例如：

```python
@dataclass(frozen=True)
class DatabaseObjectRef:
    schema_name: str
    object_name: str
    object_type: str
```

对象枚举阶段返回 `DatabaseObjectRef`，而不是只有表名字符串。这样可以避免：

- 在生成器内部再次查询对象类型；
- 把 View 临时伪装成 Table；
- 在并发任务中丢失对象类型；
- 后续步骤继续扩展时反复改变函数签名。

`TableMetadata` 保留现有 `table_type` 字段，并新增：

```python
view_definition: Optional[str] = None
```

字段名称暂时仍使用 `TableMetadata`，避免本阶段引发全项目模型重命名。未来可以评估重命名为
`DatabaseObjectMetadata`，但不作为当前 DDL 支持的前置条件。

## 5. PostgreSQL 对象发现

### 5.1 修改范围

主要修改：

- `metaweave/utils/sql_templates.py`
- `metaweave/core/metadata/connector.py`

新增统一查询，使用 `pg_class` 和 `pg_namespace` 发现对象，并依据 `relkind` 转换为 MetaWeave
对象类型。建议新增：

```python
get_database_objects(schema, include_object_types)
```

现有 `get_tables(schema)` 可以保留为兼容方法，内部固定请求 `table`。

### 5.2 对象存在性检查

现有 `check_table_exists()` 只查询 `pg_tables`。应增加统一方法：

```python
get_database_object(schema, object_name) -> Optional[DatabaseObjectRef]
```

它同时完成存在性和对象类型确认。提取阶段应校验枚举结果与实际对象类型一致，防止对象在任务
排队后被替换或删除。

### 5.3 系统对象排除

继续排除：

- `pg_catalog`
- `information_schema`
- `pg_toast`

用户配置的 schema 和排除模式继续优先于自动发现结果。

## 6. 元数据提取

主要修改：

- `metaweave/core/metadata/extractor.py`
- `metaweave/utils/sql_templates.py`

`extract_all()` 应接收对象引用或显式 `object_type`，不能再将类型固定为 `table`。

### 6.1 通用信息

三种对象都需要提取：

- schema 名称；
- 对象名称；
- 对象类型；
- 对象注释；
- 字段名、顺序、类型、精度、可空性和字段注释；
- 可选样例数据。

对象注释建议统一使用 `obj_description(pg_class.oid, 'pg_class')`。字段注释查询应基于
`pg_class + pg_attribute + pg_description`，不再依赖只覆盖普通表的
`pg_statio_all_tables`。

### 6.2 View 定义

View 和 Materialized View 使用 `pg_get_viewdef(oid, true)` 提取定义，保存到
`TableMetadata.view_definition`。

数据库返回的定义可能不带结尾分号，格式化器负责统一补齐，提取器不应通过字符串拼接猜测
完整的 `CREATE VIEW` 语句。

### 6.3 物理约束和索引

| 元数据 | Table | View | Materialized View |
|---|---:|---:|---:|
| 主键约束 | 提取 | 空 | 空 |
| 外键约束 | 提取 | 空 | 空 |
| 唯一约束 | 提取 | 空 | 空 |
| 索引 | 提取 | 空 | 提取 |

普通 View 没有独立的表约束和索引。Materialized View 可以创建索引，但这些唯一索引不能被
错误地当成表的唯一约束。

现有索引格式化逻辑会过滤所有唯一索引，因为普通表中唯一索引常与唯一约束相关。该规则不能
直接用于 Materialized View，否则它的重要唯一索引会从 DDL 中消失。

## 7. 采样、行数与注释生成

### 7.1 DDL 阶段轻量采样

当前 `ddl` 为注释生成和样例记录执行轻量采样。三种对象均可使用：

```sql
SELECT * FROM schema.object LIMIT n;
```

其中 `n` 直接读取 `output.ddl_options.sample_records.count`。数据库不再二倍超采；取回的候选记录
在 Python 内存中过滤全空行并去重，过滤后不足 `n` 条时输出实际数量，不再补采。该策略使配置
数量直接对应数据库读取上限，也避免大表因 `ORDER BY` 或 `DISTINCT` 触发昂贵执行计划。

DDL 中的样例数据使用以下精简格式：

```sql
/* SAMPLED_RECORDS
{
  "object_type": "table",
  "object_name": "public.orders",
  "records": [
    {
      "order_id": "1",
      "user_id": "82"
    }
  ]
}
*/
```

新格式删除 `version`、`table`、`sample_method` 以及逐条记录的 `label/data` 包装。DDL 解析器继续
兼容历史 `SAMPLE_RECORDS` 块，并把两种格式统一为直接记录列表。`json` 输出中的
`sample_records` 协议保持不变，`md` 直接使用规范化后的记录生成示例值。

View 不应使用 `TABLESAMPLE`。即使全局采样配置选择 `tablesample`，View 也应回退到 `limit`，
并输出调试日志说明实际策略。

### 7.2 行数

DDL 阶段不查询或输出对象行数，也不读取 `pg_stat_get_live_tuples`。统计估值可能因
`ANALYZE`/autovacuum 尚未执行而失真，完整 `COUNT(*)` 对复杂 View 和大表又可能很昂贵，因此两种
口径都不适合作为 DDL 结构文件的一部分。

精确行数仍由后续 `json` 阶段负责。View 和 Materialized View 的行数策略等下游适配时单独设计。

### 7.3 LLM 注释

现有 `comment_generation.enabled` 对三种对象统一生效。提交给 LLM 的上下文应包含对象类型，
避免提示词把 View 描述为物理表。

示例上下文：

```text
对象类型：materialized_view
对象名称：public.monthly_order_summary
```

已有数据库注释仍受 `overwrite_existing: false` 保护。

## 8. DDL 输出设计

主要修改：

- `metaweave/core/metadata/formatter.py`

### 8.1 普通表

保持当前格式：

```sql
CREATE TABLE IF NOT EXISTS public.orders (
    ...
);
```

### 8.2 普通 View

输出真实、可读的 View DDL：

```sql
CREATE OR REPLACE VIEW public.order_summary AS
SELECT ...;
```

### 8.3 Materialized View

输出：

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS public.monthly_order_summary AS
SELECT ...;
```

随后输出其索引。唯一索引需要保留 `UNIQUE`：

```sql
CREATE UNIQUE INDEX monthly_order_summary_key
ON public.monthly_order_summary (...);
```

索引还应尽量保留：

- 索引方法，例如 `btree`、`gin`；
- 字段或表达式；
- `UNIQUE`；
- 部分索引条件。

### 8.4 注释语句

分别使用：

```sql
COMMENT ON TABLE ...;
COMMENT ON VIEW ...;
COMMENT ON MATERIALIZED VIEW ...;
```

字段注释继续使用 `COMMENT ON COLUMN`。

### 8.5 文件头

文件头按实际对象类型输出：

```sql
-- View: public.order_summary
-- Object Type: view
```

普通表、View 和 Materialized View 分别使用 `-- Table:`、`-- View:` 和
`-- Materialized View:`。现有 `DDLLoader` 按 `CREATE TABLE` 解析，不依赖文件头，因此无需为
非表对象保留会造成语义冲突的 `-- Table:`。

## 9. 为下游保留的机器可读契约

View 的 `CREATE VIEW ... AS SELECT ...` 不直接声明结果字段类型。后续步骤不能只靠解析 SQL 文本
可靠还原字段名和完整字段类型。

因此当前 DDL 阶段只为 View 和 Materialized View 写入精简的机器可读元数据块：

```sql
/* OBJECT_METADATA
{
  "object_type": "view",
  "object_name": "public.order_summary",
  "object_comment": "订单汇总视图",
  "columns": [
    {
      "column_name": "order_id",
      "data_type": "bigint",
      "column_comment": "订单编号"
    }
  ]
}
*/
```

设计要求：

- 普通表不写入该元数据块，字段结构继续由 `CREATE TABLE` 完整表达；
- View 和 Materialized View 的元数据块包含 `object_type`、完整限定的 `object_name`、
  `object_comment` 和 `columns`；对象没有注释时输出空字符串；
- 每个字段包含 `column_name`、带长度或精度修饰符的完整 `data_type` 和
  `column_comment`；没有注释时输出空字符串；
- 字段类型来自 PostgreSQL 元数据：View 读取 `information_schema.columns`，Materialized View
  读取 `pg_attribute` 并使用 `format_type`，不根据样例记录推断；
- 元数据块不包含行数、注释、约束、索引或字段统计；
- 后续 `DDLLoader` 适配 View/MV 时读取该元数据块，普通表继续走现有解析器。

虽然当前阶段不修改 `json`，但应现在确定并测试该输出契约，避免下游推进时重新生成全部 DDL。

## 10. DDL 结果统计

在已经实现的物理约束统计基础上，增加对象类型统计：

```text
✅ 成功处理: 6 个对象
  - Table: 4 个
  - View: 1 个
  - Materialized View: 1 个
💬 生成注释: 17 个
🔐 物理主键约束: 3 个
🔗 物理外键约束: 2 个
🔒 唯一约束: 1 个
📇 索引总数: 6 个
  - 普通索引: 3 个
  - 唯一索引: 3 个
🔑 逻辑主键识别: 未执行
```

`processed_tables` 可以暂时保留在内部结果模型中以兼容现有调用，但 CLI 文案应改为“对象”。未来
对外 REST API 设计结果模型时，应使用 `processed_objects`，并提供按对象类型分组的统计。

索引总数表示提取到的 PostgreSQL 索引对象数，并按 `is_unique` 分为普通索引和唯一索引；
两类数量之和等于索引总数。索引统计可能包含普通表中由物理约束创建的索引，因此约束数量和
索引数量是两个不同口径。

## 11. 当前阶段代码修改清单

| 文件 | 修改内容 |
|---|---|
| `configs/metadata_config.yaml` | 增加 `database.include_object_types`，默认只含 `table` |
| `metaweave/core/metadata/models.py` | 增加对象引用模型、`view_definition` 和对象类型统计 |
| `metaweave/utils/sql_templates.py` | 增加统一对象发现、对象信息、View 定义和兼容字段注释查询 |
| `metaweave/core/metadata/connector.py` | 增加 `get_database_objects()` 和统一对象检查接口 |
| `metaweave/core/metadata/extractor.py` | 按对象类型提取定义、约束和索引 |
| `metaweave/core/metadata/generator.py` | 传递对象类型、控制采样并累计对象统计 |
| `metaweave/core/metadata/formatter.py` | 分别生成三类 DDL，仅为 View/MV 生成精简元数据块 |
| `metaweave/cli/metadata_cli.py` | 调整参数帮助、兼容保护和 DDL 统计输出 |

本阶段不修改关系发现、CQL、向量加载等业务逻辑。

## 12. 当前阶段测试计划

### 12.1 配置测试

- 未配置时默认只处理 `table`。
- 可以选择任意一种或多种受支持类型。
- 重复配置值执行去重。
- 未知值、空列表、字符串代替列表时明确失败。
- `--schemas`、`--tables` 和 `exclude_tables` 与对象类型过滤顺序正确。

### 12.2 对象发现测试

- `r`、`p` 映射为 `table`。
- `v` 映射为 `view`。
- `m` 映射为 `materialized_view`。
- 不返回配置未包含的对象类型。
- 不返回系统 schema 对象。

### 12.3 提取测试

- 三种对象都能提取字段和注释。
- View 和 Materialized View 能获取 `view_definition`。
- View 不产生物理约束和索引。
- Materialized View 保留普通索引和唯一索引。
- 普通表现有主键、外键、唯一约束和索引结果不变。

### 12.4 格式化测试

- 普通表继续生成 `CREATE TABLE`。
- View 生成 `CREATE OR REPLACE VIEW`。
- Materialized View 生成 `CREATE MATERIALIZED VIEW`。
- 三种对象生成正确的 `COMMENT ON` 语句。
- Materialized View 唯一索引不会被过滤。
- View/MV 文件包含精简机器元数据块，普通表文件不包含该元数据块。

### 12.5 CLI 与回归测试

- DDL 汇总按对象类型统计。
- 复合物理约束仍按一个约束计数。
- `--clean` 后输出只包含本次选中对象。
- 不使用 `--clean` 时明确记录覆盖与历史文件保留行为。
- 默认配置下现有普通表 DDL 内容和文件名保持兼容。
- 非 `table` 配置进入尚未支持的组合流程时得到明确错误。

### 12.6 PostgreSQL 集成验证

在测试数据库中准备：

```text
1 张普通表
1 张依赖该表的 View
1 张依赖该表的 Materialized View
1 个 Materialized View 唯一索引
```

分别运行：

```text
table only
view only
materialized_view only
all object types
```

核对发现数量、对象类型、定义、字段、注释、索引、样例记录和输出文件。

## 13. 下游步骤的对象类型配置原则

DDL 负责定义上游可用对象集合。后续每一个步骤都需要自己的对象类型选择能力，不能默认消费
目录中的所有文件。

基本规则：

```text
下游可处理对象 = 上游实际产出对象 ∩ 当前步骤配置允许对象
```

下游配置要求：

1. 每个步骤必须有明确默认值，默认只处理 `table`，保持兼容。
2. 每个产物必须携带 `object_type`，过滤不得依赖文件名。
3. 下游请求上游不存在的类型时，应明确提示缺少产物，不能静默当成空结果。
4. `rel` 和 `rel_llm` 在统一改造后应共享同一套对象过滤器。
5. `cql` 和 `cql_llm` 已共享主要代码，也应共享对象过滤规则。
6. loader 只加载当前配置允许的类型，并保留 `object_type` 属性。
7. `--clean` 的清理范围必须与作业输出范围一致，避免旧 View 文件混入新一轮 Table-only 作业。

建议的未来配置形态如下。具体键名在推进到对应步骤时结合该模块现有配置最终确认：

```yaml
# DDL：本阶段实施
database:
  include_object_types:
    - table
    - view
    - materialized_view

# 以下均为后续阶段候选设计，本阶段不写入正式配置
md:
  include_object_types:
    - table

json:
  include_object_types:
    - table

json_llm:
  include_object_types:
    - table

relationships:
  include_object_types:
    - table

cql:
  include_object_types:
    - table

loaders:
  table_schema_loader:
    include_object_types:
      - table
```

不建议让所有步骤永久共用一个全局列表。原因是用户可能希望：

- DDL 和文档包含 View；
- JSON 画像包含 Table 与 Materialized View；
- 关系发现只分析 Table；
- Neo4j 保存全部对象；
- 维度值加载只处理普通表。

因此 `database.include_object_types` 负责源对象发现和 DDL，后续模块配置负责各自的消费范围。

## 14. 下游实施顺序

### 阶段 A：当前 DDL 支持

```text
配置 → 对象发现 → 元数据提取 → DDL 输出 → DDL 统计
```

验收后，三种对象均可生成正确、可读且带机器元数据的 DDL 文件。

### 阶段 B：MD 和 DDLLoader

- `DDLLoader` 支持机器可读元数据块和三种对象类型。
- `md` 增加对象类型过滤。
- 文档标题和对象说明不再统一称为 Table。

### 阶段 C：JSON 和 JSON LLM

- `json` 增加对象类型过滤。
- View 行数、采样和逻辑主键策略单独确定。
- `json_llm` 提示词携带对象类型。
- JSON 中稳定保存 `table_info.table_type`。

### 阶段 D：rel 与 rel_llm

- 两条路径共享对象类型过滤。
- 默认仅处理普通表。
- 明确 View 是否允许成为关系来源端、目标端或两者。
- 防止基表与派生 View 产生大量重复关系。
- 物理外键直通只来自真实表约束。

该阶段应与既定的 `rel`/`rel_llm` 统一流程改造一起实施。

### 阶段 E：CQL 和加载器

- Neo4j 节点保留 `object_type`。
- 初期可以继续使用统一 `Table` 标签，通过属性区分对象类型。
- 向量加载对象携带 `object_type`，查询时可过滤。
- 各 loader 使用自己的对象类型配置。

### 阶段 F：REST API 和作业参数

REST API 作业请求允许覆盖配置中的对象类型，例如：

```json
{
  "step": "ddl",
  "schemas": ["public"],
  "include_object_types": ["table", "view"]
}
```

优先级建议保持：

```text
API/CLI 显式参数 > 步骤配置 > 兼容默认值 table
```

作业记录必须保存最终解析后的对象类型列表，确保结果可复现。

## 15. 风险与控制措施

### 15.1 复杂 View 查询成本

View 采样可能执行复杂联结和聚合。当前 DDL 阶段只做有限 `LIMIT` 采样，并沿用数据库语句超时。
后续 JSON 阶段需要独立评估 `COUNT(*)` 和画像查询成本。

### 15.2 DDL 依赖顺序

View 可能依赖其他 View。当前输出是一对象一文件，不执行数据库回放。以后如增加 PostgreSQL DDL
加载功能，需要依据依赖关系排序，这不属于当前范围。

### 15.3 派生关系重复

View 字段经常直接来自基表。若关系发现同时分析基表和 View，可能得到重复或传递关系。因此关系
发现默认保持 `table`，直到 View 关系语义和去重规则明确。

### 15.4 历史产物污染

配置从 `all` 改回 `table` 后，未使用 `--clean` 时旧 View 文件可能仍留在输出目录。当前阶段应在
日志中明确提示；下游阶段应结合对象类型字段、运行清单或作业隔离目录防止误读。

### 15.5 命名兼容

项目大量代码和输出仍使用 `table` 命名。当前阶段以增加 `object_type` 为主，不进行全局重命名，
避免把功能扩展演变为大范围无关重构。

## 16. 当前阶段验收标准

本阶段完成应同时满足：

- `database.include_object_types` 生效，默认只包含 `table`。
- `--step ddl` 可以分别或组合处理三种对象。
- 普通表 DDL 与现有行为兼容。
- View 和 Materialized View 输出真实 DDL，不伪装成 `CREATE TABLE`。
- Materialized View 的唯一索引得到保留。
- DDL 文件包含稳定的 `object_type` 和机器可读元数据。
- CLI 正确显示三种对象数量及物理结构统计。
- View 采样不会使用不兼容的采样方式。
- 启用非 Table 对象后，尚未支持的组合流程有清晰限制或错误提示。
- 当前阶段不改变 `json`、`rel`、`cql` 和 loader 的业务行为。

完成这些条件后，再按照第 14 节顺序逐步推进下游支持。
