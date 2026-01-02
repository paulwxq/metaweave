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


def test_stage2_runs_when_stage1_has_no_target_combinations():
    """当 Stage 1 目标侧没有任何组合可用时，应进入 Stage 2 动态同名匹配。"""
    generator = CandidateGenerator(_make_config(), set())

    source_table = {
        "table_info": {"schema_name": "public", "table_name": "dim"},
        "column_profiles": {
            "CompanyID": {"data_type": "integer"},
            "RegionID": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": {"columns": ["CompanyID", "RegionID"]},
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    target_table = {
        "table_info": {"schema_name": "public", "table_name": "fact"},
        "column_profiles": {
            "companyid": {"data_type": "integer"},
            "regionid": {"data_type": "bigint"},
        },
        # 关键：不给任何 PK/UK/UCCs/索引组合，Stage 1 无法匹配，只能走 Stage 2
        "table_profile": {
            "physical_constraints": {
                "primary_key": None,
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    matched = generator._find_target_columns(
        source_columns=["CompanyID", "RegionID"],
        source_table=source_table,
        target_table=target_table,
        combo_type="physical",
    )

    assert matched == ["companyid", "regionid"]


def test_stage2_fails_when_type_incompatible_even_if_same_name():
    """Stage 2 需要同名 + 类型兼容；类型不兼容时应失败。"""
    generator = CandidateGenerator(_make_config(), set())

    source_table = {
        "table_info": {"schema_name": "public", "table_name": "dim"},
        "column_profiles": {
            "created_at": {"data_type": "timestamp"},
            "user_id": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": {"columns": ["user_id", "created_at"]},
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    target_table = {
        "table_info": {"schema_name": "public", "table_name": "fact"},
        "column_profiles": {
            "created_at": {"data_type": "varchar"},
            "user_id": {"data_type": "integer"},
        },
        "table_profile": {
            "physical_constraints": {
                "primary_key": None,
                "unique_constraints": [],
            },
            "unique_column_sets": [],
            "indexes": [],
        },
    }

    matched = generator._find_target_columns(
        source_columns=["user_id", "created_at"],
        source_table=source_table,
        target_table=target_table,
        combo_type="physical",
    )

    assert matched is None

