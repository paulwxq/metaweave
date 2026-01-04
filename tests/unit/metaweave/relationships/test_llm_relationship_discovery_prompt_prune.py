from unittest.mock import MagicMock

from metaweave.core.relationships.llm_relationship_discovery import LLMRelationshipDiscovery


def test_build_prompt_prunes_column_profile_fields():
    config = {
        "llm": {
            "active": "qwen",
            "providers": {
                "qwen": {
                    "model": "qwen-plus",
                    "api_key": "mock-api-key-for-testing",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "temperature": 0.3,
                    "max_tokens": 500,
                    "timeout": 30,
                }
            },
            "langchain_config": {"use_async": False, "batch_size": 10},
        },
        "output": {"json_directory": "output/json"},
        "sampling": {"sample_size": 10},
        "relationships": {},
    }

    discovery = LLMRelationshipDiscovery(config=config, connector=MagicMock())

    table1 = {
        "table_info": {"schema_name": "public", "table_name": "t1"},
        "column_profiles": {
            "id": {
                "column_name": "id",
                "data_type": "integer",
                "comment": "",
                "statistics": {"sample_count": 10, "unique_count": 10},
                "semantic_analysis": {"semantic_role": "identifier"},
                "structure_flags": {"is_primary_key": True},
                "role_specific_info": {"identifier_info": {"naming_pattern": "id"}},
            }
        },
    }
    table2 = {
        "table_info": {"schema_name": "public", "table_name": "t2"},
        "column_profiles": {
            "t1_id": {
                "column_name": "t1_id",
                "data_type": "integer",
                "comment": "",
                "statistics": {"sample_count": 10, "unique_count": 5},
                "semantic_analysis": {"semantic_role": "identifier"},
                "structure_flags": {"is_foreign_key": True},
                "role_specific_info": {"identifier_info": {"naming_pattern": "id"}},
            }
        },
    }

    prompt = discovery._build_prompt(table1, table2)

    assert '"statistics"' in prompt
    assert '"semantic_analysis"' not in prompt
    assert '"structure_flags"' not in prompt
    assert '"role_specific_info"' not in prompt
