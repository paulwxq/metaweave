# JSON 根字段 table_info 更名为 object_info 改造范围

## 1. 背景与目标

当前 JSON 元数据（`--step json` / `--step json_llm`）根节点使用 `"table_info"` 存放对象身份信息：`database`、`schema_name`、`table_name`、`object_type`、`comment` 等。该字段名与取值语义不一致——视图、物化视图同样走这条结构，但并不是 table。

目标：将 JSON 契约根字段 **`"table_info"` 改为 `"object_info"`**，并同步所有读写该键的上下游代码与测试。

约束：

- **不直接修改** `output/` 下已生成的静态产物；改代码后需重新跑流水线才会写出新键。
- 只改 JSON 字符串键 `"table_info"`，不要全局替换标识符 `table_info`。
- `MetadataExtractor.extract_table_info()`、已删除的 `fact_table_info` / `dim_table_info` / `bridge_table_info` 注释 **不是** 本字段，不在本次范围。

本文只记录影响范围与文件清单，不展开具体实现。

## 2. 数据流（谁写、谁读）

```
--step json
  TableMetadata._to_json_dict() 写出 "table_info"
        ↓
--step json_llm
  JsonLlmEnhancer + MetadataDocument 读写同一键
  （LLM 输入视图里也会再带一份 "table_info"）
        ↓
--step rel / rel_llm
  Repository 加载 JSON 时用该键取 schema/table
  候选里 source/target 是整份 JSON，后续模块继续 .get("table_info")
        ↓
--step cql / cql_llm
  CQL reader 用该键取 database/schema/name/comment/object_type
        ↓
dim_config --generate
  用该键识别维度表身份
```

`table_schema` 向量加载器只读 `table_profile` / `column_profiles`，**不依赖** `"table_info"`。

改生成端后必须同步改读取端，否则 `json_llm` / `rel` / `cql` / 维值配置会读不到库名、schema、对象名。

## 3. 必须改：生产端（写出 JSON）

| 模块 | 文件 | 作用 |
|------|------|------|
| `metaweave.core.metadata` | `models.py` | **唯一写出点**：`TableMetadata._to_json_dict()` 里 `data["table_info"] = {...}` |
| `metaweave.core.metadata` | `metadata_document.py` | JSON 契约校验：必需字段、`table_info` 属性、`build_json_llm_input()` 里再输出 `"table_info"` |
| `metaweave.core.metadata` | `json_llm_enhancer.py` | `--step json_llm`：读注释、写注释、构造 LLM 输入包装器 |

`formatter.py` / `generator.py` 本身没有 `"table_info"` 字符串，但会调用上面两个入口，改完即可。

建议：`MetadataDocument.table_info` 属性一并改成 `object_info`，避免契约键和访问器名字不一致。局部变量名可以暂不改。

## 4. 必须改：下游消费端（读 JSON）

### 4.1 关系发现 `metaweave.core.relationships`（`rel` / `rel_llm`）

| 文件 | 用途 |
|------|------|
| `repository.py` | 加载 JSON、抽 FK 时读 `schema_name` / `table_name` |
| `candidate_generator.py` | 候选 source/target 身份 |
| `scorer.py` | 采样评分日志/标识 |
| `decision_engine.py` | 决策与日志 |
| `pipeline.py` | 合并、日志、方向处理 |
| `writer.py` | 写关系结果时取表名 |
| `llm_relationship_discovery.py` | LLM prompt、列名规范化 |

注意：`llm_relationship_discovery.py` 中 `for table_key, table_info in tables.items()` 里的 `table_info` 是「整份表 JSON」循环变量，**不是** 根字段；真正要改的是后面的 `table_info.get("table_info", {})`。

### 4.2 CQL 生成 `metaweave.core.cql_generator`（`cql` / `cql_llm`）

| 文件 | 用途 |
|------|------|
| `reader.py` | 解析 JSON 建 `TableNode`（database / schema / name / comment / object_type） |
| `models.py` | 注释里写了契约键 `table_info.object_type`，建议改成 `object_info.object_type` |

### 4.3 维值配置 `metaweave.core.dim_value`

| 文件 | 用途 |
|------|------|
| `config_generator.py` | `_extract_table_identifiers()` 读 database / schema / table |

## 5. 必须改：测试

夹具和断言都写了 `"table_info"`，需同步改为 `"object_info"`。

### 5.1 metadata / json_llm

- `tests/unit/metaweave/metadata/test_json_v3_schema.py`
- `tests/unit/metaweave/metadata/test_json_generation_finalization.py`
- `tests/unit/metaweave/test_json_llm_enhancer.py`

### 5.2 relationships

- `tests/unit/metaweave/relationships/test_repository.py`
- `tests/unit/metaweave/relationships/test_candidate_generator.py`
- `tests/unit/metaweave/relationships/test_scorer.py`
- `tests/unit/metaweave/relationships/test_decision_engine.py`
- `tests/unit/metaweave/relationships/test_writer.py`
- `tests/unit/metaweave/relationships/test_doc19_merge_stage.py`
- `tests/unit/metaweave/relationships/test_llm_canonicalization.py`
- `tests/unit/metaweave/relationships/test_llm_relationship_discovery_prompt_prune.py`
- `tests/metaweave_relationships/test_candidate_only.py`
- `tests/metaweave_relationships/test_full_relationship_pipeline.py`
- `tests/metaweave_relationships/test_composite_logical_key_matching.py`
- `tests/metaweave_relationships/test_full_composite_generation.py`

### 5.3 其它

- `tests/unit/metaweave/dim_value/test_config_generator.py`
- `tests/test_llm_response_parsing.py`

## 6. 不要改

| 文件 | 原因 |
|------|------|
| `metaweave/core/metadata/extractor.py` | 方法 `extract_table_info()`，查库返回 `object_comment` 等，不写 JSON 键 |
| `tests/unit/metaweave/metadata/test_ddl_view_support.py` | 只 mock 了上面的方法 |
| `models.py` / `profiler.py` 里 `fact_table_info` 等注释 | 已删除的旧字段，与本次无关 |
| `metaweave/core/table_schema/json_extractor.py` | 不读 `table_info` |
| `metaweave/core/loaders/*` | 不读该键 |
| `output/` 下已生成 JSON | 按约定不动；改代码后重新跑 `--step json` 才会变成 `object_info` |

`docs/` 里大量示例仍写 `table_info`，**不是运行时依赖**。历史设计文档属快照，不强制改写；若要契约文档同步，可另开一轮。

## 7. 按模块汇总（实施清单）

**生产代码（13 个文件，4 个模块）：**

1. **`metaweave.core.metadata`**
   - `models.py`（写出）
   - `metadata_document.py`（契约 + LLM 输入）
   - `json_llm_enhancer.py`（json_llm 读写）
2. **`metaweave.core.relationships`**
   - `repository.py` / `candidate_generator.py` / `scorer.py` / `decision_engine.py` / `pipeline.py` / `writer.py` / `llm_relationship_discovery.py`
3. **`metaweave.core.cql_generator`**
   - `reader.py`（+ `models.py` 注释）
4. **`metaweave.core.dim_value`**
   - `config_generator.py`

**测试（16 个文件）：** 见第 5 节。

改法应是 **字符串键 `"table_info"` → `"object_info"`**，不要全局替换 `table_info` 这个标识符。

改完后需要重新跑流水线才会看到新键；现有 `output/json/*.json` 仍是旧键，未重跑前下游会读空。

后续嵌套字段 `object_info.table_name` → `object_info.object_name` 见 [22_JSON对象字段table_name更名为object_name改造范围](./22_JSON对象字段table_name更名为object_name改造范围.md)。两处改名已合并实施。
