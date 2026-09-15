"""LLM 候选产出器：候选卫生处理测试（doc 15 §3.7）

`LLMRelationshipDiscovery` 收缩为"LLM 候选产出器"后，去重/FK过滤/评分等管线
逻辑已移交 `CandidateGenerator` + `RelationshipDiscoveryPipeline`（见
docs/update/15_rel与rel_llm候选生成统一改造设计.md §3.7/§6.1）。
本文件只覆盖产出器自身仍保留的职责：大小写规范化、越界/自环候选过滤。
"""

import pytest

from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery


@pytest.fixture
def empty_config():
    return {
        "relationships": {},
        "sampling": {},
        "embedding": {},
        "output": {"json_directory": "output/json"},
        "llm": {
            "active": "qwen",
            "providers": {"qwen": {"api_key": "dummy", "model": "qwen-plus"}},
        },
    }


def test_canonicalization_normalizes_drifted_identifiers(empty_config):
    """大小写漂移但真实 metadata 存在 → 规范化为元数据标准名称"""
    discovery = LLMRelationshipDiscovery(config=empty_config)

    tables = {
        "public.user": {
            "table_info": {"schema_name": "public", "table_name": "user"},
            "column_profiles": {"user_id": {}},
        },
        "public.order": {
            "table_info": {"schema_name": "public", "table_name": "order"},
            "column_profiles": {"customer_id": {}},
        },
    }

    candidates = [
        {
            "type": "single_column",
            "from_table": {"schema": "Public", "table": "User"},
            "from_column": "User_ID",
            "to_table": {"schema": "PUBLIC", "table": "ORDER"},
            "to_column": "Customer_Id",
        }
    ]

    normalized = discovery._canonicalize_candidate_identifiers(candidates, tables)
    rel = normalized[0]

    assert rel["from_table"]["schema"] == "public"
    assert rel["from_table"]["table"] == "user"
    assert rel["from_column"] == "user_id"
    assert rel["to_table"]["schema"] == "public"
    assert rel["to_table"]["table"] == "order"
    assert rel["to_column"] == "customer_id"


def test_canonicalization_scenario_id_consistency(empty_config):
    """无论源数据的 schema/table/column 大小写如何组合，规范化后完全一致"""
    discovery = LLMRelationshipDiscovery(config=empty_config)

    tables = {
        "schema_a.table_b": {
            "table_info": {"schema_name": "schema_a", "table_name": "table_b"},
            "column_profiles": {"col_1": {}},
        },
        "schema_c.table_d": {
            "table_info": {"schema_name": "schema_c", "table_name": "table_d"},
            "column_profiles": {"col_2": {}},
        },
    }

    candidate_lower = {
        "type": "single_column",
        "from_table": {"schema": "schema_a", "table": "table_b"},
        "from_column": "col_1",
        "to_table": {"schema": "schema_c", "table": "table_d"},
        "to_column": "col_2",
    }

    candidate_drifted = {
        "type": "single_column",
        "from_table": {"schema": "SCHEMA_A", "table": "Table_B"},
        "from_column": "COL_1",
        "to_table": {"schema": "Schema_c", "table": "TABLE_D"},
        "to_column": "Col_2",
    }

    norm_lower = discovery._canonicalize_candidate_identifiers([candidate_lower], tables)[0]
    norm_drifted = discovery._canonicalize_candidate_identifiers([candidate_drifted.copy()], tables)[0]

    assert norm_lower == norm_drifted


def test_filter_invalid_candidates_drops_self_loop_and_out_of_scope(empty_config):
    """候选卫生处理：同表自环与表对之外的越界候选被丢弃（doc 15 §3.7）"""
    discovery = LLMRelationshipDiscovery(config=empty_config)

    candidates = [
        # 自环：同表同列
        {
            "type": "single_column",
            "from_table": {"schema": "public", "table": "user"},
            "from_column": "id",
            "to_table": {"schema": "public", "table": "user"},
            "to_column": "id",
        },
        # 越界：涉及表不在当前表对范围内
        {
            "type": "single_column",
            "from_table": {"schema": "public", "table": "user"},
            "from_column": "id",
            "to_table": {"schema": "public", "table": "other"},
            "to_column": "id",
        },
        # 合法候选
        {
            "type": "single_column",
            "from_table": {"schema": "public", "table": "user"},
            "from_column": "dept_id",
            "to_table": {"schema": "public", "table": "order"},
            "to_column": "dept_id",
        },
    ]

    filtered = discovery._filter_invalid_candidates(
        candidates, "public.user", "public.order"
    )

    assert len(filtered) == 1
    assert filtered[0]["from_column"] == "dept_id"
