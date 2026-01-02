from metaweave.core.relationships.candidate_generator import CandidateGenerator


def _make_config() -> dict:
    return {
        "single_column": {
            "important_constraints": [
                "single_field_primary_key",
                "single_field_unique_constraint",
            ],
            "exclude_semantic_roles": ["audit", "metric", "description", "complex"],
            "logical_key_min_confidence": 0.8,
            "min_type_compatibility": 0.8,
            "name_similarity_important_target": 0.6,
            "name_similarity_normal_target": 0.9,
        },
        "composite": {
            "max_columns": 3,
            "min_type_compatibility": 0.8,
            "logical_key_min_confidence": 0.8,
            "name_similarity_important_target": 0.6,
            "exclude_semantic_roles": ["metric"],
        },
    }


def test_stage1_success_returns_without_running_stage2(monkeypatch):
    """Stage 1 匹配成功后，应直接返回，不再执行 Stage 2（动态同名）。"""
    generator = CandidateGenerator(_make_config(), set())

    source_table = {
        "table_info": {"schema_name": "public", "table_name": "dim"},
        "column_profiles": {
            "a": {"data_type": "integer"},
            "b": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": {"columns": ["a", "b"]},
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    target_table = {
        "table_info": {"schema_name": "public", "table_name": "fact"},
        "column_profiles": {
            "a": {"data_type": "integer"},
            "b": {"data_type": "integer"},
            "c": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": None,
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [
                {"index_name": "idx_fact_c_b_a", "columns": ["c", "b", "a"], "is_unique": False}
            ],
        },
    }

    def _should_not_run_stage2(*args, **kwargs):
        raise AssertionError("Stage 2 should not run when Stage 1 already matched")

    monkeypatch.setattr(generator, "_find_dynamic_same_name", _should_not_run_stage2)

    matched = generator._find_target_columns(
        source_columns=["a", "b"],
        source_table=source_table,
        target_table=target_table,
        combo_type="physical",
    )

    assert matched == ["a", "b"]


def test_stage1_can_match_target_pk_with_subset_and_reorder():
    """Stage 1 支持 m>n 乱序子集匹配（例如源(a,b) 匹配目标PK(c,b,a)）。"""
    generator = CandidateGenerator(_make_config(), set())

    source_table = {
        "table_info": {"schema_name": "public", "table_name": "dim"},
        "column_profiles": {
            "a": {"data_type": "integer"},
            "b": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": {"columns": ["a", "b"]},
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    target_table = {
        "table_info": {"schema_name": "public", "table_name": "fact"},
        "column_profiles": {
            "a": {"data_type": "integer"},
            "b": {"data_type": "integer"},
            "c": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": {"columns": ["c", "b", "a"]},
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    matched = generator._find_target_columns(
        source_columns=["a", "b"],
        source_table=source_table,
        target_table=target_table,
        combo_type="physical",
    )

    assert matched == ["a", "b"]

