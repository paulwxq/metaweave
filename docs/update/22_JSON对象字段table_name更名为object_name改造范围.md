# JSON 对象字段 table_name 更名为 object_name 改造范围

## 1. 背景与目标

[21_JSON根字段table_info更名为object_info改造范围](./21_JSON根字段table_info更名为object_info改造范围.md) 已将 JSON 根节点 `"table_info"` 重命名为 `"object_info"`。该对象内部仍使用 `"table_name"` 存放对象名：

```json
{
  "metadata_version": "3.0",
  "object_info": {
    "database": "orders",
    "schema_name": "public",
    "table_name": "cinema_halls",
    "object_type": "table",
    "comment": "...",
    "comment_source": "ddl",
    "total_rows": 3
  }
}
```

视图、物化视图同样走这条结构，继续叫 `table_name` 与 `object_type` 矛盾。本次将 **`object_info.table_name` 改为 `object_info.object_name`**，目标产物为：

```json
{
  "metadata_version": "3.0",
  "object_info": {
    "database": "orders",
    "schema_name": "public",
    "object_name": "cinema_halls",
    "object_type": "table"
  }
}
```

约束：

- **不直接修改** `output/` 下已生成的静态产物；改代码后需重新跑流水线。
- 只改 JSON 契约键 `"table_name"`（位于 `object_info` / LLM 输入视图的同一对象内），**不要** 全局替换标识符 `table_name`。
- 与 doc 21 一起实施：生产代码同时完成 `table_info` → `object_info` 与 `table_name` → `object_name`。
- 内存模型 `TableMetadata.table_name`、关系模型 `source_table` / `target_table`、外键 JSON 的 `target_table`、Milvus 字段 `table_name` **不在本次范围**。

本文只记录影响范围与文件清单。实施时与 doc 21 合并落地。

## 2. 数据流（谁写、谁读）

```
--step json
  TableMetadata._to_json_dict()
    写出 object_info.object_name ← self.table_name
        ↓
--step json_llm
  JsonLlmEnhancer 用 object_info.object_name 打日志
  MetadataDocument.build_json_llm_input() 再输出 object_info.object_name
        ↓
--step rel / rel_llm
  Repository / candidate / scorer / pipeline / writer / LLM
  从 source/target 的 object_info 取 object_name 拼 schema.object
        ↓
--step cql / cql_llm
  reader 用 object_info.object_name 填 TableNode.name
        ↓
dim_config --generate
  优先读 object_info.object_name；table_profile.table_name / 根字段 table_name 仍作回退
```

## 3. 必须改：生产端（写出 JSON）

| 模块 | 文件 | 改动 |
|------|------|------|
| `metaweave.core.metadata` | `models.py` | `_to_json_dict()`：`"table_name": self.table_name` → `"object_name": self.table_name`。Python 字段 `TableMetadata.table_name` **保留**。 |
| `metaweave.core.metadata` | `metadata_document.py` | `build_json_llm_input()` 输出键改为 `"object_name"`；属性访问走 `object_info`。 |
| `metaweave.core.metadata` | `json_llm_enhancer.py` | `original["object_info"].get("object_name")`、`enhanced["object_info"]["object_name"]` |

`SampleData.to_dict()` 的 `"table_name"` 是样例数据结构，不是 JSON 元数据契约，**不改**。

## 4. 必须改：下游消费端（读 JSON）

读取路径一律从 `info.get("table_name")` 改为 `info.get("object_name")`，其中 `info` 来自 `data["object_info"]` 或候选的 `source`/`target`。

### 4.1 关系发现 `metaweave.core.relationships`

| 文件 | 用途 |
|------|------|
| `repository.py` | 加载 JSON、抽 FK 时取对象名 |
| `candidate_generator.py` | 候选身份、关系 ID、方向键 |
| `scorer.py` | 评分日志中的 `schema.object` |
| `decision_engine.py` | 决策日志与全名 |
| `pipeline.py` | 合并、字典序方向比较、调试输出 |
| `writer.py` | 写关系结果时取对象名 |
| `llm_relationship_discovery.py` | prompt 表名、列名规范化 |

### 4.2 CQL 生成 `metaweave.core.cql_generator`

| 文件 | 用途 |
|------|------|
| `reader.py` | `_extract_table` / `_extract_columns` / 占位符跳过：`object_info.object_name` |
| `models.py` | 注释中的契约键路径 |

占位符过滤当前排除字面量 `"table_name"`。改名后应同时排除 `"object_name"`，以免新旧模板文件漏过滤。

### 4.3 维值配置 `metaweave.core.dim_value`

| 文件 | 用途 |
|------|------|
| `config_generator.py` | `_extract_table_identifiers()` 主路径改为 `object_info.get("object_name")` |

回退链保留：`table_profile.get("table_name")`、`data.get("table_name")`。这两处不是 `object_info` 契约键，测试里有「无 object_info、靠 table_profile 回退」的用例。

## 5. 必须改：测试

JSON 夹具里嵌在 `table_info` / `object_info` 下的 `"table_name"` 改为 `"object_name"`。断言里 `...["table_info"]["table_name"]` 改为 `...["object_info"]["object_name"]`。

与 doc 21 相同的 16 个测试文件都要动；其中 `table_name` 额外出现在：

- `tests/unit/metaweave/relationships/test_candidate_generator.py`（`_table()` 工厂）
- `tests/unit/metaweave/relationships/test_doc19_merge_stage.py`
- `tests/unit/metaweave/relationships/test_decision_engine.py` 等夹具
- `tests/metaweave_relationships/test_candidate_only.py` 等集成测试的 `.get("table_name")`

`tests/unit/metaweave/dim_value/test_config_generator.py`：仅改带 `object_info` 的那条夹具；`table_profile.table_name` 回退夹具 **不改**。

`tests/unit/metaweave/metadata/test_json_v3_schema.py`：`TableMetadata(table_name="orders")` 是 Python 构造参数，**不改**；断言 `data["table_info"]` 改为 `data["object_info"]`。

## 6. 不要改

| 位置 | 原因 |
|------|------|
| `TableMetadata.table_name` / `CommentCacheKey.table_name` / `SampleData.table_name` | 内存模型字段，不是 JSON 契约键 |
| `TableMetadata(table_name=...)` 测试构造 | 同上 |
| 外键 JSON `target_table` / `source_table` | 物理外键约束字段 |
| `Relation.source_table` / `target_table` | 关系模型属性 |
| Milvus `FieldSchema(name="table_name")` 及 dim_value 向量检索 | 向量库 schema，与 JSON 元数据无关 |
| `table_profile.table_name`、根节点 `data["table_name"]` | 维值配置的历史回退路径 |
| `extractor.extract_table_info()` | 查库方法，不写 JSON 键 |
| `output/` 已生成 JSON | 按约定不动 |

## 7. 按模块汇总（与 doc 21 合并实施）

生产代码与 doc 21 同一批 13 个文件。本次在这些文件上 **额外** 把 `object_info` 内的 `"table_name"` 改为 `"object_name"`。

实施时只替换字符串键，不重命名 Python 变量。改完后重新跑 `--step json`，产物应为 `object_info.object_name`。

## 8. 实施状态

已与 doc 21 合并落地：生产代码与测试已将 `table_info` → `object_info`、`object_info.table_name` → `object_info.object_name`。`output/` 产物需重新跑 `--step json` 后才会更新。
