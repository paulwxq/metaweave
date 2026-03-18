"""复杂类型兼容性测试 — 覆盖 docs/60 方案 §10.1 全部场景"""

import json
import math

import pandas as pd
import pytest

from metaweave.utils.data_utils import (
    get_column_statistics,
    dataframe_to_sample_dict,
    _is_complex_value,
    _normalize_for_hash,
    _is_null_value,
)


# =====================================================================
# 辅助函数单元测试
# =====================================================================


class TestIsComplexValue:
    def test_list(self):
        assert _is_complex_value([1, 2]) is True

    def test_dict(self):
        assert _is_complex_value({"a": 1}) is True

    def test_tuple(self):
        assert _is_complex_value((1, 2)) is True

    def test_set(self):
        assert _is_complex_value({1, 2}) is True

    def test_bytes(self):
        assert _is_complex_value(b"\x89PNG") is True

    def test_scalar_str(self):
        assert _is_complex_value("hello") is False

    def test_scalar_int(self):
        assert _is_complex_value(42) is False

    def test_none(self):
        assert _is_complex_value(None) is False


class TestNormalizeForHash:
    def test_dict_sort_keys(self):
        result = _normalize_for_hash({"b": 2, "a": 1})
        assert result == json.dumps({"a": 1, "b": 2}, ensure_ascii=False)

    def test_list_preserves_order(self):
        """list/tuple 保留原始顺序（PostgreSQL ARRAY 是有序的）"""
        assert _normalize_for_hash([3, 1, 2]) == json.dumps([3, 1, 2], ensure_ascii=False)
        assert _normalize_for_hash([1, 2]) != _normalize_for_hash([2, 1])

    def test_tuple_preserves_order(self):
        assert _normalize_for_hash((3, 1, 2)) == json.dumps([3, 1, 2], ensure_ascii=False)

    def test_set_sorted(self):
        """set 是无序的，排序后归一化"""
        result = _normalize_for_hash({3, 1, 2})
        assert result == json.dumps([1, 2, 3], ensure_ascii=False)

    def test_list_normalizes_nested_dict_keys(self):
        """JSONB 数组内嵌对象时，键顺序不同应视为相同值"""
        a = _normalize_for_hash([{"b": 2, "a": 1}])
        b = _normalize_for_hash([{"a": 1, "b": 2}])
        assert a == b

    def test_list_nested_dict_preserves_element_order(self):
        """数组元素顺序仍然保留"""
        a = _normalize_for_hash([{"a": 1}, {"b": 2}])
        b = _normalize_for_hash([{"b": 2}, {"a": 1}])
        assert a != b

    def test_list_with_non_serializable(self):
        """list 含非 JSON 原生类型时通过 default=str 兜底"""
        from datetime import date
        result = _normalize_for_hash([date(2025, 1, 1)])
        assert isinstance(result, str)

    def test_scalar_passthrough(self):
        assert _normalize_for_hash(42) == 42
        assert _normalize_for_hash("hello") == "hello"


class TestIsNullValue:
    def test_none(self):
        assert _is_null_value(None) is True

    def test_nan(self):
        assert _is_null_value(float("nan")) is True

    def test_pd_na(self):
        assert _is_null_value(pd.NA) is True

    def test_list_not_null(self):
        assert _is_null_value([1, 2]) is False

    def test_dict_not_null(self):
        assert _is_null_value({"a": 1}) is False

    def test_bytes_not_null(self):
        assert _is_null_value(b"\x00") is False

    def test_empty_list_not_null(self):
        assert _is_null_value([]) is False

    def test_scalar_zero(self):
        assert _is_null_value(0) is False

    def test_scalar_string(self):
        assert _is_null_value("hello") is False


# =====================================================================
# get_column_statistics — 标量回归
# =====================================================================


class TestStatsScalarRegression:
    """标量列统计结果应与修改前一致"""

    def test_int_column(self):
        df = pd.DataFrame({"x": [1, 2, 2, 3, None]})
        stats = get_column_statistics(df, "x")
        assert stats["sample_count"] == 5
        assert stats["unique_count"] == 3
        assert stats["null_count"] == 1
        assert stats["null_rate"] == 0.2
        assert "value_distribution" in stats

    def test_string_column_with_length_stats(self):
        df = pd.DataFrame({"s": ["abc", "defgh", "ij", None]})
        stats = get_column_statistics(df, "s")
        assert stats["unique_count"] == 3
        assert "avg_length" in stats
        assert "min_length" in stats

    def test_low_cardinality_value_distribution(self):
        df = pd.DataFrame({"c": ["a", "a", "b", "b", "b"]})
        stats = get_column_statistics(df, "c", value_distribution_threshold=10)
        assert "value_distribution" in stats
        assert stats["value_distribution"]["b"] == 3
        assert stats["value_distribution"]["a"] == 2


# =====================================================================
# get_column_statistics — ARRAY (list) 列
# =====================================================================


class TestStatsArrayColumn:
    def test_list_column_no_error(self):
        df = pd.DataFrame({"tags": [[1, 2], [3], [1, 2], None]})
        stats = get_column_statistics(df, "tags")
        assert stats["sample_count"] == 4
        assert stats["null_count"] == 1
        assert "unique_count" in stats
        assert stats["unique_count"] == 2  # [1,2] appears twice
        assert "avg_length" not in stats  # no string length stats

    def test_list_order_matters(self):
        """PostgreSQL ARRAY 是有序的，[1,2] 和 [2,1] 应视为不同值"""
        df = pd.DataFrame({"tags": [[1, 2], [2, 1], [1, 2]]})
        stats = get_column_statistics(df, "tags")
        assert stats["unique_count"] == 2  # [1,2] x2, [2,1] x1

    def test_list_column_value_distribution(self):
        df = pd.DataFrame({"tags": [[1, 2], [1, 2], [3, 4]]})
        stats = get_column_statistics(df, "tags", value_distribution_threshold=10)
        assert "value_distribution" in stats


# =====================================================================
# get_column_statistics — JSON/JSONB (dict/list) 列
# =====================================================================


class TestStatsJsonColumn:
    def test_dict_root_no_error(self):
        df = pd.DataFrame({"meta": [{"a": 1}, {"b": 2}, {"a": 1}]})
        stats = get_column_statistics(df, "meta")
        assert stats["unique_count"] == 2
        assert "avg_length" not in stats

    def test_list_root_no_error(self):
        """JSON 根节点为数组时 psycopg3 返回 list，同样需要兼容"""
        df = pd.DataFrame({"arr": [[1, 2], [3, 4], [1, 2]]})
        stats = get_column_statistics(df, "arr")
        assert stats["unique_count"] == 2

    def test_dict_low_cardinality_distribution(self):
        df = pd.DataFrame({"cfg": [{"k": 1}, {"k": 1}, {"k": 2}]})
        stats = get_column_statistics(df, "cfg", value_distribution_threshold=10)
        assert "value_distribution" in stats


# =====================================================================
# get_column_statistics — 混合列（前几行标量、后续行为 list）
# =====================================================================


class TestStatsMixedColumn:
    def test_null_then_list(self):
        """前几行 NULL，后面才出现 list —— 全列扫描应检测到复杂类型"""
        df = pd.DataFrame({"m": [None, None, [1, 2], [3, 4]]})
        stats = get_column_statistics(df, "m")
        assert stats["sample_count"] == 4
        assert "unique_count" in stats
        assert stats["unique_count"] == 2


# =====================================================================
# get_column_statistics — BYTEA (bytes) 列
# =====================================================================


class TestStatsBytesColumn:
    def test_bytes_column_no_error(self):
        df = pd.DataFrame({"pic": [b"\x89PNG", b"\x00\x01", None]})
        stats = get_column_statistics(df, "pic")
        assert stats["sample_count"] == 3
        assert stats["null_count"] == 1
        assert "null_rate" in stats
        assert "unique_count" not in stats
        assert "uniqueness" not in stats
        assert "value_distribution" not in stats
        assert "avg_length" not in stats


# =====================================================================
# dataframe_to_sample_dict — 复杂类型序列化
# =====================================================================


class TestSampleDictComplexTypes:
    def test_list_serialized_as_json(self):
        df = pd.DataFrame({"tags": [[1, 2, 3]], "name": ["foo"]})
        result = dataframe_to_sample_dict(df)
        assert len(result) == 1
        assert result[0]["tags"] == json.dumps([1, 2, 3], ensure_ascii=False)
        assert result[0]["name"] == "foo"

    def test_dict_serialized_as_json(self):
        df = pd.DataFrame({"meta": [{"key": "val"}]})
        result = dataframe_to_sample_dict(df)
        assert result[0]["meta"] == json.dumps({"key": "val"}, ensure_ascii=False)

    def test_bytes_serialized_with_length(self):
        data = b"\x89PNG\r\n"
        df = pd.DataFrame({"pic": [data]})
        result = dataframe_to_sample_dict(df)
        assert result[0]["pic"] == f"<binary:{len(data)} bytes>"

    def test_null_value_preserved(self):
        df = pd.DataFrame({"x": [None, 1]})
        result = dataframe_to_sample_dict(df)
        assert result[0]["x"] is None
        assert result[1]["x"] == "1.0"  # Pandas coerces int to float in nullable column

    def test_nan_value_preserved(self):
        df = pd.DataFrame({"x": [float("nan"), "ok"]})
        result = dataframe_to_sample_dict(df)
        assert result[0]["x"] is None
        assert result[1]["x"] == "ok"


# =====================================================================
# dataframe_to_sample_dict — 单字段失败隔离
# =====================================================================


class TestSampleDictFieldIsolation:
    def test_bad_field_does_not_kill_row(self):
        """即使某列值序列化抛异常，其它列和行仍正常返回"""

        class _Unserializable:
            def __str__(self):
                raise RuntimeError("boom")

        df = pd.DataFrame({"ok": ["hello"], "bad": [_Unserializable()]})
        result = dataframe_to_sample_dict(df)
        assert len(result) == 1
        assert result[0]["ok"] == "hello"
        # safe_str catches the exception internally and returns "<unconvertible>";
        # the field-level try/except is a second safety net for cases safe_str can't handle.
        assert result[0]["bad"] == "<unconvertible>"
