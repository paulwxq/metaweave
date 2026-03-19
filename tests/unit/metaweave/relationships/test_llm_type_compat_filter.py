import pytest
from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery

class MockConnector:
    pass

@pytest.fixture
def discovery():
    config = {
        "relationships": {
            "single_column": {"min_type_compatibility": 0.8},
            "composite": {"min_type_compatibility": 0.8}
        },
        "llm": {
            "active": "qwen",
            "providers": {
                "qwen": {
                    "api_key": "dummy",
                    "model": "qwen-plus"
                }
            }
        }
    }
    return LLMRelationshipDiscovery(config, MockConnector())

@pytest.fixture
def metadata_tables():
    return {
        "public.source_table": {
            "table_info": {"schema_name": "public", "table_name": "source_table"},
            "column_profiles": {
                "id": {"data_type": "integer"},
                "name": {"data_type": "varchar"},
                "service_area_id": {"data_type": "varchar"},
                "status": {"data_type": "integer"},
            }
        },
        "public.target_table": {
            "table_info": {"schema_name": "public", "table_name": "target_table"},
            "column_profiles": {
                "id": {"data_type": "integer"},
                "service_area_id": {"data_type": "varchar"},
                "status": {"data_type": "varchar"},
            }
        },
        "public.missing_metadata_table": {
            "table_info": {"schema_name": "public", "table_name": "missing_metadata_table"},
        }
    }

def test_single_column_compatible(discovery, metadata_tables):
    candidate = {
        "type": "single_column",
        "from_table": {"schema": "public", "table": "source_table"},
        "from_column": "service_area_id",
        "to_table": {"schema": "public", "table": "target_table"},
        "to_column": "service_area_id"
    }
    filtered = discovery._filter_by_type_compatibility([candidate], metadata_tables)
    assert len(filtered) == 1

def test_single_column_incompatible(discovery, metadata_tables):
    candidate = {
        "type": "single_column",
        "from_table": {"schema": "public", "table": "source_table"},
        "from_column": "service_area_id",  # varchar
        "to_table": {"schema": "public", "table": "target_table"},
        "to_column": "id"  # integer
    }
    filtered = discovery._filter_by_type_compatibility([candidate], metadata_tables)
    assert len(filtered) == 0

def test_composite_incompatible_member(discovery, metadata_tables):
    candidate = {
        "type": "composite",
        "from_table": {"schema": "public", "table": "source_table"},
        "from_columns": ["id", "service_area_id"],  # integer, varchar
        "to_table": {"schema": "public", "table": "target_table"},
        "to_columns": ["id", "id"]  # integer, integer
    }
    filtered = discovery._filter_by_type_compatibility([candidate], metadata_tables)
    assert len(filtered) == 0

def test_missing_metadata(discovery, metadata_tables):
    candidate = {
        "type": "single_column",
        "from_table": {"schema": "public", "table": "source_table"},
        "from_column": "name",
        "to_table": {"schema": "public", "table": "missing_metadata_table"},
        "to_column": "missing_col"
    }
    filtered = discovery._filter_by_type_compatibility([candidate], metadata_tables)
    assert len(filtered) == 1  # 保守放行


def test_case_insensitive_table_lookup_filters_incompatible(discovery):
    metadata_tables = {
        "Public.Source_Table": {
            "table_info": {"schema_name": "Public", "table_name": "Source_Table"},
            "column_profiles": {
                "service_area_id": {"data_type": "varchar"},
            }
        },
        "PUBLIC.Target_Table": {
            "table_info": {"schema_name": "PUBLIC", "table_name": "Target_Table"},
            "column_profiles": {
                "id": {"data_type": "integer"},
            }
        },
    }
    candidate = {
        "type": "single_column",
        "from_table": {"schema": "public", "table": "source_table"},
        "from_column": "service_area_id",
        "to_table": {"schema": "public", "table": "target_table"},
        "to_column": "id",
    }
    filtered = discovery._filter_by_type_compatibility([candidate], metadata_tables)
    assert len(filtered) == 0


def test_case_insensitive_column_lookup_filters_incompatible(discovery, metadata_tables):
    candidate = {
        "type": "single_column",
        "from_table": {"schema": "public", "table": "source_table"},
        "from_column": "SERVICE_AREA_ID",
        "to_table": {"schema": "public", "table": "target_table"},
        "to_column": "Id",
    }
    filtered = discovery._filter_by_type_compatibility([candidate], metadata_tables)
    assert len(filtered) == 0


