# rel_llm：关系发现 LLM 提示词模板（完整）

来源：`metaweave/core/relationships/llm_relationship_discovery.py#RELATIONSHIP_DISCOVERY_PROMPT`  
拼装方式：`RELATIONSHIP_DISCOVERY_PROMPT.format(table1_name=..., table1_json=json.dumps(table1, ensure_ascii=False, indent=2), table2_name=..., table2_json=json.dumps(table2, ensure_ascii=False, indent=2))`（见 `metaweave/core/relationships/llm_relationship_discovery.py#_build_prompt`）

> 说明：实际调用时 `{table1_json}` / `{table2_json}` 会被替换为 `output/json_llm/*.json` 的完整内容。本文档为了便于阅读，不展开 JSON 内容，但**提示词模板本身不省略**。

## Prompt 模板（原样）

```text
你是一个数据库关系分析专家。请分析以下两个表以及表中的采样数据，判断它们之间是否存在关联关系。

## 表 1: {table1_name}
```json
{table1_json}
```

## 表 2: {table2_name}
```json
{table2_json}
```

## 任务
分析这两个表之间可能的关联关系（外键关系）。考虑以下因素：
1. 字段名相同或相似
2. 数据类型兼容
3. 字段注释的语义关联
4. 样例数据的值域匹配
5. 复合键的可能性（多个字段组合）

## 输出格式
返回 JSON 格式。如果存在关联，返回关联信息；如果没有关联，返回空数组。

### 单列关联示例
```json
{
  "relationships": [
    {
      "type": "single_column",
      "from_table": {"schema": "public", "table": "dim_region"},
      "to_table": {"schema": "public", "table": "dim_store"},
      "from_column": "region_id",
      "to_column": "region_id"
    }
  ]
}
```

### 多列关联示例（type 为 composite，字段用数组）
```json
{
  "relationships": [
    {
      "type": "composite",
      "from_table": {"schema": "public", "table": "equipment_config"},
      "to_table": {"schema": "public", "table": "maintenance_work_order"},
      "from_columns": ["equipment_id", "config_version"],
      "to_columns": ["equipment_id", "config_version"]
    }
  ]
}
```

### 无关联
```json
{
  "relationships": []
}
```

请只返回 JSON，不要包含其他内容。
```

## 提示词里 JSON 的典型形态（省略内容，仅示意）

实际传入的 `{table1_json}` / `{table2_json}` 大致结构为：
- `table_info`：schema/table/comment/comment_source/total_rows/total_columns
- `column_profiles`：每列的 `data_type/comment/comment_source/structure_flags/statistics`
- `table_profile`：`physical_constraints`、`table_category`（以及可选 `table_domains`）
- `sample_records.records`：若干行样例数据（对象数组）

