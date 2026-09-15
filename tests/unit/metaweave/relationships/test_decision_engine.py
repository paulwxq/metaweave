"""测试DecisionEngine模块"""

import pytest
from metaweave.core.relationships.decision_engine import DecisionEngine


class TestDecisionEngine:
    """DecisionEngine单元测试"""

    def test_threshold_filtering(self):
        """测试阈值过滤"""
        # 使用 top-level 配置结构
        config = {
            "decision": {
                "accept_threshold": 0.80,
                "suppress_single_if_composite": False
            }
        }
        engine = DecisionEngine(config)

        candidates = [
            {
                "source": {"table_info": {"schema_name": "public", "table_name": "fact_sales"}},
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
                "source_columns": ["store_id"],
                "target_columns": ["store_id"],
                "composite_score": 0.85,
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            },
            {
                "source": {"table_info": {"schema_name": "public", "table_name": "fact_sales"}},
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_company"}},
                "source_columns": ["company_id"],
                "target_columns": ["company_id"],
                "composite_score": 0.75,  # 低于阈值
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            }
        ]

        accepted, suppressed, below_threshold = engine.filter_and_suppress(candidates)

        # 只有一个候选通过阈值
        assert len(accepted) == 1
        assert accepted[0].composite_score == 0.85
        assert len(suppressed) == 0
        assert len(below_threshold) == 1
        assert below_threshold[0]["composite_score"] == 0.75

    def test_suppression_disabled(self):
        """测试禁用抑制规则"""
        config = {
            "decision": {
                "accept_threshold": 0.70,
                "suppress_single_if_composite": False
            }
        }
        engine = DecisionEngine(config)

        candidates = [
            {
                "source": {"table_info": {"schema_name": "public", "table_name": "fact_sales"}, "column_profiles": {}},
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
                "source_columns": ["store_id", "date_day"],
                "target_columns": ["store_id", "date_day"],
                "composite_score": 0.90,
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            },
            {
                "source": {"table_info": {"schema_name": "public", "table_name": "fact_sales"}, "column_profiles": {}},
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
                "source_columns": ["store_id"],
                "target_columns": ["store_id"],
                "composite_score": 0.85,
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            }
        ]

        accepted, suppressed, below_threshold = engine.filter_and_suppress(candidates)

        # 禁用抑制，应该都接受
        assert len(accepted) == 2
        assert len(suppressed) == 0
        assert len(below_threshold) == 0

    def test_suppression_enabled_with_composite(self):
        """测试启用抑制规则（有复合关系）"""
        config = {
            "decision": {
                "accept_threshold": 0.70,
                "suppress_single_if_composite": True
            }
        }
        engine = DecisionEngine(config)

        # 创建测试候选（同一表对）
        candidates = [
            {
                "source": {
                    "table_info": {"schema_name": "public", "table_name": "fact_sales"},
                    "column_profiles": {}
                },
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
                "source_columns": ["store_id", "date_day"],
                "target_columns": ["store_id", "date_day"],
                "composite_score": 0.90,
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            },
            {
                "source": {
                    "table_info": {"schema_name": "public", "table_name": "fact_sales"},
                    "column_profiles": {},
                    "table_profile": {
                        "physical_constraints": {"primary_key": None, "unique_constraints": []},
                        "indexes": []
                    }
                },
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
                "source_columns": ["store_id"],
                "target_columns": ["store_id"],
                "composite_score": 0.85,
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            }
        ]

        accepted, suppressed, below_threshold = engine.filter_and_suppress(candidates)

        # 复合关系应该被接受，单列关系应该被抑制（因为没有独立约束）
        assert len(accepted) == 1
        assert len(accepted[0].source_columns) == 2  # 复合关系
        assert len(suppressed) == 1
        assert len(below_threshold) == 0

    def test_below_threshold_not_mixed_into_suppressed(self):
        """未达阈值的单列不得记入复合键抑制列表（否则 writer 会误标 suppression_reason）"""
        config = {
            "decision": {
                "accept_threshold": 0.80,
                "suppress_single_if_composite": True
            }
        }
        engine = DecisionEngine(config)
        candidates = [
            {
                "source": {
                    "table_info": {"schema_name": "public", "table_name": "fact_sales"},
                    "column_profiles": {}
                },
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
                "source_columns": ["store_id", "date_day"],
                "target_columns": ["store_id", "date_day"],
                "composite_score": 0.90,
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            },
            {
                "source": {
                    "table_info": {"schema_name": "public", "table_name": "fact_sales"},
                    "column_profiles": {},
                    "table_profile": {
                        "physical_constraints": {"primary_key": None, "unique_constraints": []},
                        "indexes": []
                    }
                },
                "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
                "source_columns": ["store_id"],
                "target_columns": ["store_id"],
                "composite_score": 0.50,
                "score_details": {},
                "candidate_origin": "rule",
                "key_origin": "physical"
            }
        ]
        accepted, suppressed, below_threshold = engine.filter_and_suppress(candidates)
        assert len(accepted) == 1
        assert len(suppressed) == 0
        assert len(below_threshold) == 1
        assert below_threshold[0]["source_columns"] == ["store_id"]

    def test_has_independent_constraint(self):
        """测试独立约束检测（v3：读取表级 physical_constraints / indexes）"""
        config = {"decision": {}}
        engine = DecisionEngine(config)

        # 有单列主键约束的候选
        candidate_with_pk = {
            "source": {
                "table_profile": {
                    "physical_constraints": {
                        "primary_key": {"columns": ["store_id"]},
                        "unique_constraints": []
                    },
                    "indexes": []
                }
            },
            "source_columns": ["store_id"]
        }

        assert engine._has_independent_constraint(candidate_with_pk) is True

        # 有单列唯一约束的候选
        candidate_with_uk = {
            "source": {
                "table_profile": {
                    "physical_constraints": {
                        "primary_key": None,
                        "unique_constraints": [{"columns": ["store_code"]}]
                    },
                    "indexes": []
                }
            },
            "source_columns": ["store_code"]
        }

        assert engine._has_independent_constraint(candidate_with_uk) is True

        # 有非 partial 单列唯一索引的候选
        candidate_with_unique_index = {
            "source": {
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [
                        {"columns": ["email"], "is_unique": True, "condition": None}
                    ]
                }
            },
            "source_columns": ["email"]
        }

        assert engine._has_independent_constraint(candidate_with_unique_index) is True

        # partial 唯一索引不算独立约束
        candidate_with_partial_index = {
            "source": {
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": [
                        {"columns": ["email"], "is_unique": True, "condition": "deleted_at IS NULL"}
                    ]
                }
            },
            "source_columns": ["email"]
        }

        assert engine._has_independent_constraint(candidate_with_partial_index) is False

        # 没有约束的候选
        candidate_no_constraint = {
            "source": {
                "table_profile": {
                    "physical_constraints": {"primary_key": None, "unique_constraints": []},
                    "indexes": []
                }
            },
            "source_columns": ["some_col"]
        }

        assert engine._has_independent_constraint(candidate_no_constraint) is False

    def test_relation_id_with_salt(self):
        """测试推断关系ID生成支持盐值"""
        from metaweave.core.relationships.repository import MetadataRepository

        # 使用有盐值的配置
        config_with_salt = {
            "decision": {
                "accept_threshold": 0.80,
                "suppress_single_if_composite": False
            },
            "output": {
                "rel_id_salt": "myproject"
            }
        }
        engine_with_salt = DecisionEngine(config_with_salt)

        # 使用无盐值的配置
        config_no_salt = {
            "decision": {
                "accept_threshold": 0.80,
                "suppress_single_if_composite": False
            },
            "output": {
                "rel_id_salt": ""
            }
        }
        engine_no_salt = DecisionEngine(config_no_salt)

        # 相同的候选
        candidate = {
            "source": {"table_info": {"schema_name": "public", "table_name": "fact_sales"}},
            "target": {"table_info": {"schema_name": "public", "table_name": "dim_store"}},
            "source_columns": ["store_id"],
            "target_columns": ["store_id"],
            "composite_score": 0.85,
            "score_details": {},
            "candidate_origin": "rule",
            "key_origin": "physical"
        }

        # 转换为 Relation
        rel_with_salt = engine_with_salt._candidate_to_relation(candidate)
        rel_no_salt = engine_no_salt._candidate_to_relation(candidate)

        # 有盐值和无盐值应生成不同ID
        assert rel_with_salt.relationship_id != rel_no_salt.relationship_id

        # 验证有盐值的ID与Repository生成的ID一致
        expected_id = MetadataRepository.compute_relationship_id(
            "public", "fact_sales", ["store_id"],
            "public", "dim_store", ["store_id"],
            rel_id_salt="myproject"
        )
        assert rel_with_salt.relationship_id == expected_id
