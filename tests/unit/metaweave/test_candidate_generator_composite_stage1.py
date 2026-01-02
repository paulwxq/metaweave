import pytest

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


def test_stage1_can_match_target_index_subset_any_order():
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

    matched = generator._find_target_columns(
        source_columns=["a", "b"],
        source_table=source_table,
        target_table=target_table,
        combo_type="physical",
    )

    assert matched == ["a", "b"]


def test_stage1_can_match_target_pk_subset_any_order():
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


def test_stage1_target_uccs_not_semantic_filtered():
    generator = CandidateGenerator(_make_config(), set())

    source_table = {
        "table_info": {"schema_name": "public", "table_name": "dim"},
        "column_profiles": {
            "x": {"data_type": "integer"},
            "y": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": {"columns": ["x", "y"]},
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    target_table = {
        "table_info": {"schema_name": "public", "table_name": "fact"},
        "column_profiles": {
            "x": {"data_type": "integer", "semantic_analysis": {"semantic_role": "metric"}},
            "y": {"data_type": "integer", "semantic_analysis": {"semantic_role": "metric"}},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": None,
                "unique_constraints": [],
            },
            "unique_column_sets": [
                {"columns": ["x", "y"], "confidence_score": 0.95},
            ],
            "indexes": [],
        },
    }

    matched = generator._find_target_columns(
        source_columns=["x", "y"],
        source_table=source_table,
        target_table=target_table,
        combo_type="physical",
    )

    assert matched == ["x", "y"]

