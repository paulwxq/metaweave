import pytest
from unittest.mock import MagicMock
from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery
from metaweave.core.relationships.repository import MetadataRepository
import time

@pytest.fixture
def empty_config():
    return {
        "relationships": {},
        "sampling": {},
        "embedding": {},
        "output": {"json_directory": "output/json"},
        "llm": {
            "active": "qwen",
            "providers": {"qwen": {"api_key": "dummy", "model": "qwen-plus"}}
        }
    }

def test_canonicalization_scenario_1_drifted_valid(empty_config):
    """场景 1：大小写漂移但真实 metadata 存在，经过处理后能输出规范名称"""
    connector = MagicMock()
    discovery = LLMRelationshipDiscovery(config=empty_config, connector=connector)
    
    tables = {
        "public.user": {
            "table_info": {"schema_name": "public", "table_name": "user"},
            "column_profiles": {"user_id": {}}
        },
        "public.order": {
            "table_info": {"schema_name": "public", "table_name": "order"},
            "column_profiles": {"customer_id": {}}
        }
    }
    
    candidates = [
        {
            "type": "single_column",
            "from_table": {"schema": "Public", "table": "User"},
            "from_column": "User_ID",
            "to_table": {"schema": "PUBLIC", "table": "ORDER"},
            "to_column": "Customer_Id"
        }
    ]
    
    # 模拟内部方法的依赖（评分和物理约束过滤）
    discovery._filter_existing_fks = lambda c, f: c
    discovery._filter_by_semantic_roles = lambda c, t: c
    discovery._filter_by_type_compatibility = lambda c, t: c
    discovery.repo = MagicMock()
    discovery.repo.fk_relationship_ids = set()
    
    discovery._finalize_relations(
        tables=tables,
        fk_relation_objects=[],
        fk_relationship_ids=set(),
        llm_candidates=candidates,
        start_time=time.time()
    )
    
    rel = candidates[0]
    # 检查已规范化
    assert rel["from_table"]["schema"] == "public"
    assert rel["from_table"]["table"] == "user"
    assert rel["from_column"] == "user_id"
    assert rel["to_table"]["schema"] == "public"
    assert rel["to_table"]["table"] == "order"
    assert rel["to_column"] == "customer_id"

def test_canonicalization_scenario_2_existing_fk_removal(empty_config):
    """场景 2：大小写漂移但其实是物理 FK，由于规范化而被正确识别并剔除"""
    connector = MagicMock()
    discovery = LLMRelationshipDiscovery(config=empty_config, connector=connector)
    
    tables = {
        "public.user": {
            "table_info": {"schema_name": "public", "table_name": "user"},
            "column_profiles": {"user_id": {}}
        },
        "public.order": {
            "table_info": {"schema_name": "public", "table_name": "order"},
            "column_profiles": {"customer_id": {}}
        }
    }
    
    # 构建物理外键的 ID
    rel_id = MetadataRepository.compute_relationship_id(
        source_schema="public",
        source_table="user",
        source_columns=["user_id"],
        target_schema="public",
        target_table="order",
        target_columns=["customer_id"],
        rel_id_salt=""
    )
    
    candidates = [
        {
            "type": "single_column",
            "from_table": {"schema": "Public", "table": "User"},
            "from_column": "User_ID",
            "to_table": {"schema": "PUBLIC", "table": "ORDER"},
            "to_column": "Customer_Id"
        }
    ]
    
    discovery._filter_by_semantic_roles = lambda c, t: c
    discovery._filter_by_type_compatibility = lambda c, t: c
    discovery.repo = MagicMock()
    discovery.repo.rel_id_salt = ""
    discovery.repo.fk_relationship_ids = {rel_id}
    
    rels, _, _ = discovery._finalize_relations(
        tables=tables,
        fk_relation_objects=[],
        fk_relationship_ids=set(),
        llm_candidates=candidates,
        start_time=time.time()
    )
    
    # 应该被 _filter_existing_fks 剔除
    assert len(rels) == 0

def test_canonicalization_scenario_3_id_consistency(empty_config):
    """场景 3：无论源数据的 schema/table/column 的大小写如何组合，它们都能生成完全一致的 relationship_id"""
    connector = MagicMock()
    discovery = LLMRelationshipDiscovery(config=empty_config, connector=connector)
    
    tables = {
        "schema_a.table_b": {
            "table_info": {"schema_name": "schema_a", "table_name": "table_b"},
            "column_profiles": {"col_1": {}}
        },
        "schema_c.table_d": {
            "table_info": {"schema_name": "schema_c", "table_name": "table_d"},
            "column_profiles": {"col_2": {}}
        }
    }
    
    candidate_lower = {
        "type": "single_column",
        "from_table": {"schema": "schema_a", "table": "table_b"},
        "from_column": "col_1",
        "to_table": {"schema": "schema_c", "table": "table_d"},
        "to_column": "col_2"
    }
    
    candidate_drifted = {
        "type": "single_column",
        "from_table": {"schema": "SCHEMA_A", "table": "Table_B"},
        "from_column": "COL_1",
        "to_table": {"schema": "Schema_c", "table": "TABLE_D"},
        "to_column": "Col_2"
    }
    
    norm_lower = discovery._canonicalize_candidate_identifiers([candidate_lower], tables)[0]
    norm_drifted = discovery._canonicalize_candidate_identifiers([candidate_drifted.copy()], tables)[0]
    
    assert norm_lower == norm_drifted
