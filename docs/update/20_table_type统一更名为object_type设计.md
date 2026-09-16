# table_type 统一更名为 object_type 设计

## 1. 背景与目标

`table_type` 的取值是 `table / view / materialized_view`,而 view 与物化视图
**不是表**——用 `table_type` 描述它们是自相矛盾的命名。项目内部早已用
`object_type` 称呼同一概念:

- `metadata/models.py`:`SUPPORTED_DATABASE_OBJECT_TYPES`、
  `DatabaseObjectRef.object_type`、`normalize_database_object_types()`;
- 配置:`database.include_object_types`;
- `formatter.py`:DDL 格式化局部变量已叫 `object_type`,DDL 头输出
  `-- Object Type: {object_type}`,DDL 的 SAMPLED_RECORDS 块输出键已叫
  `"object_type"`。

目标:代码与产物命名统一为 **object_type**,消除 table_type 的语义误导。

## 2. 现状盘点(table_type 全部使用位置)

### 2.1 代码(9 个文件,25 处)

| 文件 | 位置与用途 |
|---|---|
| `metadata/models.py` | `TableMetadata.table_type` 字段定义(:166);`to_dict` 序列化进 JSON `table_info.table_type`(:218) |
| `metadata/extractor.py:422` | 从 DB 抽取后构造 `TableMetadata(table_type=object_type)` |
| `metadata/ddl_loader.py:155/242` | 从 DDL 文件解析回填 `table_type` |
| `metadata/generator.py:345/690/786/862/962` | `processed_object_counts` 统计、DDL 与 DB 对象类型一致性校验 |
| `metadata/formatter.py:176/318/396` | DDL/MD 格式化——**局部变量已叫 object_type**,读 `metadata.table_type` |
| `metadata/formatter.py:692` | DDL SAMPLED_RECORDS 块输出键 **已叫 `"object_type"`** |
| `metadata/metadata_document.py:293` | 契约层 `build_json_llm_input()` 给 LLM 的输入键 `"table_type"` |
| `cql_generator/models.py` | `TableNode.table_type`(doc 18 新增,CQL 节点属性) |
| `cql_generator/reader.py` | `_extract_table` 读 JSON 的 `table_info.table_type` → TableNode |
| `cql_generator/writer.py` | 两处 Table 节点 `SET n.table_type = t.table_type` |

### 2.2 JSON 契约(落盘产物)

`table_info.table_type` 是 v3 契约的稳定字段(doc 17 §12.4 明确"两版都有、
完全不变")。**rel 步骤不读它**,当前唯一消费方是 CQL(以及 LLM 输入构造)。

### 2.3 测试(6 个文件)

`test_ddl_summary.py`、`test_ddl_view_support.py`、
`test_formatter_markdown_fk_label.py`、`test_json_v3_schema.py`、
`test_json_llm_enhancer.py`、CQL 侧 doc18 测试,以及
`tests/.tmp/*_smoke/json/` 冒烟产物。

### 2.4 文档(5 份)

doc 9/10/11/13/17 中的 `table_type` 表述(doc 17 §12.4 契约清单为首)。

## 3. 方案决策

> **已采纳方案 A,并已完成实施**(代码、测试、产物与 doc 17 契约清单已同步;
> 历史设计文档 doc 9/10/11/13 中的 `table_type` 表述属历史快照,不改写)。

### 方案 A:全量改名(含 JSON 契约)

`table_info.table_type` → `table_info.object_type`,全链路统一。

- 优点:一处命名,无映射;
- 代价:破坏 v3 JSON 契约字段(doc 17 明示的稳定字段),所有历史产物、外部
  下游工具、契约校验、5 份文档全部连带修改;收益仅是消掉一个映射。

### 方案 B(推荐):内部与产物命名统一为 object_type,JSON 契约保留 table_type

- 内存模型:`TableMetadata.table_type` → `object_type`(extractor /
  ddl_loader / generator / formatter 同步);
- 契约层:`build_json_llm_input` 输出键 `"table_type"` → `"object_type"`;
- CQL:`TableNode.table_type` → `object_type`,reader 从 JSON 读
  `table_info.table_type` 时**显式映射**(一行 + 注释);
- JSON 落盘键 **保留 `table_info.table_type`**(序列化时映射)——它是稳定
  契约字段,改名波及所有历史产物与下游工具,收益为负;
- 附带收益:DDL 产物的 SAMPLED_RECORDS 块与 LLM 输入从此与内部命名完全
  一致,不再有"内部 object_type、落盘 table_type"的混用。

选择依据:项目纪律是"代码不向下兼容",但 JSON 契约是**产品输出格式**而非
代码——历史上 doc 17 正是靠"契约字段稳定"保护下游消费方。方案 B 在语义
正确性与契约稳定性之间取得平衡,且映射点只有序列化(1 处)与 CQL reader
(1 处)两行代码。

## 4. 修改范围(按方案 B)

| 文件 | 修改内容 |
|---|---|
| `metadata/models.py` | `TableMetadata.table_type` → `object_type`;`to_dict` 的 `table_info` 序列化时写键 `"table_type": self.object_type`(边界映射 + 注释) |
| `metadata/extractor.py` | 构造参数 `table_type=` → `object_type=` |
| `metadata/ddl_loader.py` | 同上(2 处) |
| `metadata/generator.py` | `metadata.table_type` → `metadata.object_type`(5 处) |
| `metadata/formatter.py` | `metadata.table_type` → `metadata.object_type`(4 处读取) |
| `metadata/metadata_document.py` | `build_json_llm_input` 输出键 `"table_type"` → `"object_type"` |
| `cql_generator/models.py` | `TableNode.table_type` → `object_type`;`to_cypher_dict` 键同步 |
| `cql_generator/reader.py` | 读 `table_info.get("table_type", "table")` → 映射为 `object_type=...`(注释说明 JSON 契约字段名) |
| `cql_generator/writer.py` | 两处 `n.table_type` → `n.object_type` |
| 测试(6 个文件) | 字段/键名断言同步;`.tmp` 冒烟产物按新代码重新生成 |
| 文档(doc 17 §12.4 等 5 份) | doc 17 保持 `table_type`(契约未变),补充"内部/DDL/LLM 输入统一为 object_type"的说明;doc 9/10/11/13 顺带更新表述 |

方案 A 的增量:JSON 键、契约校验、doc 17 契约清单、全部测试断言与冒烟
产物、下游消费方(CQL reader 直接读 object_type)全部联动。

## 5. 测试计划

- `TableMetadata.object_type` 构造与 JSON 序列化(`table_info.table_type`
  键值正确);
- extractor / ddl_loader 构造路径;
- generator 的 `processed_object_counts` 与 DDL 一致性校验;
- formatter 的 DDL 头与 SAMPLED_RECORDS 块;
- 契约层 `build_json_llm_input` 输出键为 `"object_type"`;
- CQL:TableNode.object_type 透传、cypher 节点属性 `n.object_type`、
  物化视图用例(冒烟 `--step cql` 后解析节点参数验证
  `mv_category_sales → materialized_view`);
- 全量单测回归。

## 6. 验收标准

1. 代码内部不再存在 `table_type` 命名(仅保留 JSON 序列化与 CQL reader
   两处显式映射,附注释);
2. JSON 产物 `table_info.table_type` 键与值不变(冒烟 diff 无变化);
3. CQL 节点属性名为 `n.object_type`,物化视图值正确;
4. LLM 输入键为 `"object_type"`;
5. 全部单元测试通过、json/rel/cql 三层冒烟产物一致。

## 7. 非目标

- 不改 `database.include_object_types`(已是正确命名);
- 不改 Neo4j 中已有节点的属性名迁移(边/节点属性改名后,旧库需
  `load --type cql --clean` 全量重建,与 doc 18 的运维口径一致);
- 若采纳方案 B:不改 JSON 契约字段 `table_info.table_type`(稳定契约)。
