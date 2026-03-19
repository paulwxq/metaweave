"""测试RelationshipScorer模块"""

import pytest
from unittest.mock import Mock
from metaweave.core.relationships.scorer import RelationshipScorer


class TestRelationshipScorer:
    """RelationshipScorer单元测试"""

    @pytest.fixture
    def mock_connector(self):
        """创建Mock数据库连接器"""
        connector = Mock()
        # Mock execute_query返回字典格式的示例数据
        connector.execute_query.return_value = [
            {"col1": "value1"},
            {"col1": "value2"},
            {"col1": "value3"}
        ]
        return connector

    @pytest.fixture
    def scorer(self, mock_connector):
        """创建Scorer实例（4维度评分体系）"""
        config = {
            "weights": {
                "inclusion_rate": 0.55,
                "name_similarity": 0.20,
                "type_compatibility": 0.15,
                "jaccard_index": 0.10
            }
        }
        return RelationshipScorer(config, mock_connector)

    def test_calculate_name_similarity(self, scorer):
        """测试列名相似度计算"""
        # 完全相同
        score = scorer._calculate_name_similarity(["store_id"], ["store_id"])
        assert score == 1.0

        # 不同的列名
        score = scorer._calculate_name_similarity(["user_id"], ["company_id"])
        assert 0.0 <= score < 1.0

        # 复合键
        score = scorer._calculate_name_similarity(
            ["store_id", "date_day"],
            ["store_id", "date_day"]
        )
        assert score == 1.0

    def test_calculate_type_compatibility(self, scorer):
        """测试类型兼容性计算"""
        source_columns = ["store_id"]
        target_columns = ["store_id"]

        source_profiles = {
            "store_id": {"data_type": "integer"}
        }

        target_profiles = {
            "store_id": {"data_type": "integer"}
        }

        score = scorer._calculate_type_compatibility(
            source_columns, source_profiles,
            target_columns, target_profiles
        )
        assert score == 1.0  # 完全相同类型

    def test_extract_value_set_single_column(self, scorer):
        """测试单列值集合提取"""
        rows = [
            {"col1": "value1"},
            {"col1": "value2"},
            {"col1": "value1"},  # 重复
            {"col1": None}        # NULL值
        ]
        columns = ["col1"]

        value_set, valid_count = scorer._extract_value_set(rows, columns)

        # 应该去重且排除None
        assert len(value_set) == 2
        assert ("value1",) in value_set
        assert ("value2",) in value_set
        # valid_count 应该是排除 None 后的行数（3行有效）
        assert valid_count == 3

    def test_extract_value_set_composite_columns(self, scorer):
        """测试复合列值集合提取"""
        rows = [
            {"col1": "val1", "col2": "val2"},
            {"col1": "val3", "col2": "val4"},
            {"col1": "val1", "col2": "val2"},  # 重复
            {"col1": None, "col2": "val5"},    # 包含None
        ]
        columns = ["col1", "col2"]

        value_set, valid_count = scorer._extract_value_set(rows, columns)

        # 应该去重且排除包含None的行
        assert len(value_set) == 2
        assert ("val1", "val2") in value_set
        assert ("val3", "val4") in value_set
        # valid_count 应该是排除含 None 行后的有效行数（3行有效，含1行重复）
        assert valid_count == 3

