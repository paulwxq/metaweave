"""_make_hashable / _extract_value_set 单元测试

覆盖场景:
- _make_hashable: 基础类型、list、dict、嵌套结构
- _extract_value_set: 正常值、含 NULL、含 array/json 列
"""

import pytest

from metaweave.core.relationships.scorer import RelationshipScorer


# ===========================================================================
# _make_hashable
# ===========================================================================

class TestMakeHashable:

    def test_int_passthrough(self):
        assert RelationshipScorer._make_hashable(42) == 42

    def test_str_passthrough(self):
        assert RelationshipScorer._make_hashable("hello") == "hello"

    def test_none_passthrough(self):
        assert RelationshipScorer._make_hashable(None) is None

    def test_bool_passthrough(self):
        assert RelationshipScorer._make_hashable(True) is True

    def test_float_passthrough(self):
        assert RelationshipScorer._make_hashable(3.14) == 3.14

    def test_list_to_tuple(self):
        result = RelationshipScorer._make_hashable([1, 2, 3])
        assert result == (1, 2, 3)
        assert isinstance(result, tuple)

    def test_nested_list(self):
        result = RelationshipScorer._make_hashable([1, [2, 3]])
        assert result == (1, (2, 3))

    def test_dict_to_sorted_tuple(self):
        result = RelationshipScorer._make_hashable({"b": 2, "a": 1})
        assert result == (("a", 1), ("b", 2))

    def test_nested_dict_with_list(self):
        result = RelationshipScorer._make_hashable({"key": [1, 2]})
        assert result == (("key", (1, 2)),)

    def test_result_is_hashable(self):
        """任意结构转换后都应可哈希"""
        complex_val = {"a": [1, {"b": [3, 4]}], "c": "text"}
        result = RelationshipScorer._make_hashable(complex_val)
        # 不抛异常即通过
        hash(result)

    def test_datetime_passthrough(self):
        """datetime 是可哈希的，应直接返回"""
        from datetime import datetime
        dt = datetime(2025, 1, 1)
        assert RelationshipScorer._make_hashable(dt) == dt


# ===========================================================================
# _extract_value_set（需要 mock scorer 实例，但只用到 staticmethod 调用）
# ===========================================================================

class TestExtractValueSetWithUnhashable:
    """验证 _extract_value_set 对不可哈希类型的安全处理"""

    @pytest.fixture
    def scorer(self):
        """构造最简 scorer 实例（只需要 _extract_value_set 可调用）"""
        # scorer.__init__ 需要 config 和 connector，用 mock 绕过
        from unittest.mock import MagicMock
        s = object.__new__(RelationshipScorer)
        s.config = {}
        s.connector = MagicMock()
        s.weights = {}
        s.sample_size = 100
        s.query_count = 0
        s.name_similarity_service = None
        return s

    def test_normal_values(self, scorer):
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        value_set, count = scorer._extract_value_set(rows, ["id", "name"])
        assert count == 2
        assert (1, "Alice") in value_set
        assert (2, "Bob") in value_set

    def test_null_rows_skipped(self, scorer):
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": None, "name": "Bob"},
            {"id": 3, "name": None},
        ]
        value_set, count = scorer._extract_value_set(rows, ["id", "name"])
        assert count == 1
        assert (1, "Alice") in value_set

    def test_array_column_does_not_crash(self, scorer):
        """PostgreSQL array 列返回 list，不应抛异常"""
        rows = [
            {"id": 1, "tags": ["a", "b"]},
            {"id": 2, "tags": ["c"]},
        ]
        value_set, count = scorer._extract_value_set(rows, ["id", "tags"])
        assert count == 2
        # list 被转为 tuple
        assert (1, ("a", "b")) in value_set
        assert (2, ("c",)) in value_set

    def test_json_column_does_not_crash(self, scorer):
        """PostgreSQL json/jsonb 列返回 dict"""
        rows = [
            {"id": 1, "meta": {"key": "val"}},
        ]
        value_set, count = scorer._extract_value_set(rows, ["id", "meta"])
        assert count == 1

    def test_mixed_hashable_and_unhashable(self, scorer):
        """同一列中混合可哈希和不可哈希值"""
        rows = [
            {"col": "simple_string"},
            {"col": [1, 2, 3]},
        ]
        value_set, count = scorer._extract_value_set(rows, ["col"])
        assert count == 2
