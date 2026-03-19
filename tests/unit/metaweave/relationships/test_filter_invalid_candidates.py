"""_filter_invalid_candidates 单元测试

覆盖场景:
- 同表同列自环（single_column / composite）
- 同表不同列（合法自引用，应保留）
- 越界关系（表不在当前表对中）
- 正常关系通过
"""

import pytest

from metaweave.core.relationships.llm_relationship_discovery import (
    LLMRelationshipDiscovery,
)


class TestFilterInvalidCandidates:
    """_filter_invalid_candidates 静态方法测试"""

    _filter = staticmethod(LLMRelationshipDiscovery._filter_invalid_candidates)

    # ----- 正常关系 -----

    def test_valid_single_column_passes(self):
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "customer_id",
                "to_table": {"schema": "public", "table": "customers"},
                "to_column": "id",
            }
        ]
        result = self._filter(candidates, "public.orders", "public.customers")
        assert len(result) == 1

    def test_valid_composite_passes(self):
        candidates = [
            {
                "type": "composite",
                "from_table": {"schema": "public", "table": "order_items"},
                "from_columns": ["order_id", "product_id"],
                "to_table": {"schema": "public", "table": "orders"},
                "to_columns": ["id", "product_id"],
            }
        ]
        result = self._filter(candidates, "public.order_items", "public.orders")
        assert len(result) == 1

    # ----- 同表同列自环 -----

    def test_self_loop_single_column_rejected(self):
        """public.t.id -> public.t.id 应被丢弃"""
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "highway_metadata"},
                "from_column": "id",
                "to_table": {"schema": "public", "table": "highway_metadata"},
                "to_column": "id",
            }
        ]
        result = self._filter(
            candidates, "public.highway_metadata", "public.other_table"
        )
        assert len(result) == 0

    def test_self_loop_composite_rejected(self):
        """composite 同表同列自环应被丢弃"""
        candidates = [
            {
                "type": "composite",
                "from_table": {"schema": "public", "table": "t1"},
                "from_columns": ["a", "b"],
                "to_table": {"schema": "public", "table": "t1"},
                "to_columns": ["a", "b"],
            }
        ]
        result = self._filter(candidates, "public.t1", "public.t2")
        assert len(result) == 0

    # ----- 同表不同列（合法自引用） -----

    def test_same_table_different_columns_kept(self):
        """同表但不同列的自引用应保留（如 employee.manager_id -> employee.id）"""
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "employee"},
                "from_column": "manager_id",
                "to_table": {"schema": "public", "table": "employee"},
                "to_column": "id",
            }
        ]
        # 注意：当前实现中 table_pairs 不会产生 (t, t)，但过滤器本身不阻止不同列的同表关系
        result = self._filter(candidates, "public.employee", "public.employee")
        assert len(result) == 1

    # ----- 越界关系 -----

    def test_out_of_scope_table_rejected(self):
        """LLM 幻觉出的第三张表应被丢弃"""
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "product_id",
                "to_table": {"schema": "public", "table": "products"},
                "to_column": "id",
            }
        ]
        # 当前表对是 orders <-> customers，products 不在范围
        result = self._filter(candidates, "public.orders", "public.customers")
        assert len(result) == 0

    def test_both_tables_out_of_scope_rejected(self):
        candidates = [
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "x"},
                "from_column": "a",
                "to_table": {"schema": "public", "table": "y"},
                "to_column": "b",
            }
        ]
        result = self._filter(candidates, "public.orders", "public.customers")
        assert len(result) == 0

    # ----- 混合场景 -----

    def test_mixed_valid_and_invalid(self):
        """一个合法关系 + 一个自环 + 一个越界 → 只保留合法"""
        candidates = [
            # 合法
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "customer_id",
                "to_table": {"schema": "public", "table": "customers"},
                "to_column": "id",
            },
            # 自环
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "id",
                "to_table": {"schema": "public", "table": "orders"},
                "to_column": "id",
            },
            # 越界
            {
                "type": "single_column",
                "from_table": {"schema": "public", "table": "orders"},
                "from_column": "product_id",
                "to_table": {"schema": "public", "table": "products"},
                "to_column": "id",
            },
        ]
        result = self._filter(candidates, "public.orders", "public.customers")
        assert len(result) == 1
        assert result[0]["from_column"] == "customer_id"

    def test_empty_input(self):
        result = self._filter([], "public.a", "public.b")
        assert result == []
