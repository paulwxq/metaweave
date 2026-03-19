"""_filter_by_semantic_roles 源列 complex 类型过滤测试

验证源列 semantic_role == "complex" 时候选被正确过滤。
"""

import pytest
from unittest.mock import MagicMock, patch

from metaweave.core.relationships.llm_relationship_discovery import (
    LLMRelationshipDiscovery,
)


def _make_table_json(schema: str, table: str, columns: dict) -> dict:
    """构造最小化表 JSON，仅包含 column_profiles 中的 semantic_analysis"""
    return {
        "table_info": {"schema_name": schema, "table_name": table},
        "column_profiles": columns,
    }


def _col_profile(semantic_role: str = "identifier", data_type: str = "integer") -> dict:
    return {
        "data_type": data_type,
        "semantic_analysis": {"semantic_role": semantic_role},
        "structure_flags": {},
    }


@pytest.fixture
def discovery():
    """构造最简 LLMRelationshipDiscovery 实例"""
    config = {
        "relationships": {
            "method": "llm_only",
            "accept_threshold": 0.3,
        },
        "llm": {"active": "test", "providers": {"test": {"model": "m"}}},
    }
    with patch.object(LLMRelationshipDiscovery, "__init__", lambda self, *a, **kw: None):
        d = object.__new__(LLMRelationshipDiscovery)
    d.config = config
    d.rel_config = config.get("relationships", {})
    d.single_exclude_roles = {"complex", "boolean", "ordinal"}
    d.composite_exclude_roles = {"complex", "boolean", "ordinal"}
    return d


class TestSourceColumnComplexFilter:
    """源列 complex 类型过滤"""

    def test_source_complex_single_column_filtered(self, discovery):
        """源列为 complex → 候选被过滤"""
        tables = {
            "public.highway_metadata": _make_table_json("public", "highway_metadata", {
                "related_tables": _col_profile("complex", "array"),
                "id": _col_profile("identifier", "integer"),
            }),
            "public.bss_service_area": _make_table_json("public", "bss_service_area", {
                "id": _col_profile("identifier", "integer"),
            }),
        }
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "highway_metadata"},
                "from_column": "related_tables",
                "to_table": {"schema": "public", "table": "bss_service_area"},
                "to_column": "id",
            }
        ]
        result = discovery._filter_by_semantic_roles(candidates, tables)
        assert len(result) == 0

    def test_source_non_complex_passes(self, discovery):
        """源列不是 complex → 候选保留"""
        tables = {
            "public.orders": _make_table_json("public", "orders", {
                "customer_id": _col_profile("identifier", "integer"),
            }),
            "public.customers": _make_table_json("public", "customers", {
                "id": _col_profile("identifier", "integer"),
            }),
        }
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "customer_id",
                "to_table": {"schema": "public", "table": "customers"},
                "to_column": "id",
            }
        ]
        result = discovery._filter_by_semantic_roles(candidates, tables)
        assert len(result) == 1

    def test_composite_any_source_complex_filtered(self, discovery):
        """复合键中任一源列为 complex → 整个候选被过滤"""
        tables = {
            "public.t1": _make_table_json("public", "t1", {
                "normal_col": _col_profile("identifier", "integer"),
                "json_col": _col_profile("complex", "jsonb"),
            }),
            "public.t2": _make_table_json("public", "t2", {
                "a": _col_profile("identifier", "integer"),
                "b": _col_profile("identifier", "integer"),
            }),
        }
        candidates = [
            {
                "type": "composite",
                "from_table": {"schema": "public", "table": "t1"},
                "from_columns": ["normal_col", "json_col"],
                "to_table": {"schema": "public", "table": "t2"},
                "to_columns": ["a", "b"],
            }
        ]
        result = discovery._filter_by_semantic_roles(candidates, tables)
        assert len(result) == 0

    def test_source_table_missing_metadata_passes(self, discovery):
        """源表元数据缺失时不做源列过滤，交给后续阶段处理"""
        tables = {
            # 源表不在 tables 中
            "public.target": _make_table_json("public", "target", {
                "id": _col_profile("identifier", "integer"),
            }),
        }
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "source"},
                "from_column": "ref_id",
                "to_table": {"schema": "public", "table": "target"},
                "to_column": "id",
            }
        ]
        # 源表缺失 → 不做源列过滤 → 保留候选（后续 target 列检查也不会命中过滤）
        result = discovery._filter_by_semantic_roles(candidates, tables)
        assert len(result) == 1

    def test_case_insensitive_source_lookup(self, discovery):
        """大小写不敏感匹配源表和源列"""
        tables = {
            "Public.Highway_Metadata": _make_table_json("Public", "Highway_Metadata", {
                "Related_Tables": _col_profile("complex", "array"),
            }),
            "public.target": _make_table_json("public", "target", {
                "id": _col_profile("identifier", "integer"),
            }),
        }
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "highway_metadata"},
                "from_column": "related_tables",
                "to_table": {"schema": "public", "table": "target"},
                "to_column": "id",
            }
        ]
        result = discovery._filter_by_semantic_roles(candidates, tables)
        assert len(result) == 0
