"""测试RelationshipScorer模块"""

import pytest
from unittest.mock import Mock
from metaweave.core.relationships.scorer import RelationshipScorer


FIVE_DIM_WEIGHTS = {
    "inclusion_rate": 0.40,
    "name_similarity": 0.10,
    "comment_similarity": 0.10,
    "type_compatibility": 0.20,
    "jaccard_index": 0.20,
}


class FakeCommentChannel:
    enabled = True

    def is_usable(self, comment):
        return bool(comment)

    def compare(self, a, b):
        return 0.42


class FakeNameSimilarityService:
    comment_channel = FakeCommentChannel()

    def compare_columns(self, source_cols, target_cols):
        return 1.0 if [c.lower() for c in source_cols] == [c.lower() for c in target_cols] else 0.0


class TestRelationshipScorer:
    """RelationshipScorer单元测试"""

    @pytest.fixture
    def mock_connector(self):
        """创建Mock数据库连接器"""
        connector = Mock()
        connector.execute_query.return_value = [
            {"col1": "value1"},
            {"col1": "value2"},
            {"col1": "value3"}
        ]
        return connector

    @pytest.fixture
    def scorer(self, mock_connector):
        """创建Scorer实例（5维度评分体系）"""
        config = {"weights": dict(FIVE_DIM_WEIGHTS)}
        return RelationshipScorer(config, mock_connector)

    def test_calculate_name_similarity(self, scorer):
        """测试列名相似度计算"""
        score = scorer._calculate_name_similarity(["store_id"], ["store_id"])
        assert score == 1.0

        score = scorer._calculate_name_similarity(["user_id"], ["company_id"])
        assert score == 0.0

        score = scorer._calculate_name_similarity(["Store_ID"], ["store_id"])
        assert score == 1.0

        score = scorer._calculate_name_similarity(
            ["store_id", "date_day"],
            ["store_id", "date_day"]
        )
        assert score == 1.0

    def test_comment_similarity_degraded_mode_uses_fallback(self, scorer):
        """降级模式（无 embedding 服务）下 comment_similarity 用 fallback，不退回名称。"""
        assert scorer.name_similarity_service is None

        assert scorer._score_comment_pair("store_id", None, "store_id", None) == 0.3
        assert scorer._score_comment_pair("user_id", None, "company_id", None) == 0.3
        assert scorer._score_comment_pair("store_id", "门店编号", "store_id", "门店标识") == 0.3

    def test_calculate_comment_similarity_degraded_mode_uses_fallback(self, scorer):
        """整列 comment_similarity 在降级模式下同样用 fallback。"""
        score = scorer._calculate_comment_similarity(
            ["store_id"], {"store_id": {"comment": None}},
            ["store_id"], {"store_id": {"comment": None}},
        )
        assert score == 0.3

    def test_comment_similarity_non_degraded_mode(self, mock_connector):
        """双方注释可用走 embedding；否则用 fallback。名称由独立维度计分。"""
        config = {"weights": dict(FIVE_DIM_WEIGHTS)}
        scorer = RelationshipScorer(config, mock_connector, FakeNameSimilarityService())

        assert scorer._score_comment_pair("a", "注释A", "b", "注释B") == 0.42
        assert scorer._score_comment_pair("store_id", "注释A", "store_id", None) == 0.3
        assert scorer._score_comment_pair("user_id", "注释A", "company_id", None) == 0.3
        assert scorer._score_comment_pair("store_id", None, "store_id", None) == 0.3

        assert scorer._calculate_name_similarity(["store_id"], ["store_id"]) == 1.0
        assert scorer._calculate_name_similarity(["user_id"], ["company_id"]) == 0.0

    def test_comment_similarity_disabled_channel_uses_fallback(self, mock_connector):
        """comment_channel.enabled: false 时 comment 用 fallback，名称仍独立计分。"""
        class DisabledCommentChannel:
            enabled = False

            def is_usable(self, comment):
                return False

            def compare(self, a, b):
                raise AssertionError("禁用通道不应比较注释")

        class FakeService:
            comment_channel = DisabledCommentChannel()

            def compare_columns(self, source_cols, target_cols):
                return 1.0 if [c.lower() for c in source_cols] == [c.lower() for c in target_cols] else 0.0

        config = {"weights": dict(FIVE_DIM_WEIGHTS)}
        scorer = RelationshipScorer(config, mock_connector, FakeService())

        assert scorer._score_comment_pair("store_id", "门店编号", "store_id", "门店标识") == 0.3
        assert scorer._score_comment_pair("store_id", None, "store_id", None) == 0.3
        assert scorer._score_comment_pair("user_id", "用户", "company_id", "公司") == 0.3
        assert scorer._calculate_name_similarity(["store_id"], ["store_id"]) == 1.0
        assert scorer._calculate_name_similarity(["user_id"], ["company_id"]) == 0.0

    def test_calculate_scores_returns_five_dimensions(self, mock_connector):
        """_calculate_scores 返回五维 + reverse_inclusion_rate，且与 weights 键集一致。"""
        config = {"weights": dict(FIVE_DIM_WEIGHTS)}
        scorer = RelationshipScorer(config, mock_connector, FakeNameSimilarityService())
        # (inclusion, reverse_inclusion, jaccard, source_uniq, target_uniq, join_mult)
        scorer._sample_and_calculate_inclusion = Mock(
            return_value=(1.0, 0.8, 0.5, 1.0, 1.0, 1.0)
        )

        source_table = {
            "table_info": {"schema_name": "public", "table_name": "orders"},
            "column_profiles": {
                "product_id": {"comment": "购买商品唯一标识ID", "data_type": "integer"}
            },
        }
        target_table = {
            "table_info": {"schema_name": "public", "table_name": "products"},
            "column_profiles": {
                "product_id": {"comment": "商品唯一标识ID", "data_type": "integer"}
            },
        }

        score_details, cardinality, reverse_inclusion_rate = scorer._calculate_scores(
            source_table, ["product_id"], target_table, ["product_id"]
        )
        assert set(score_details.keys()) == set(FIVE_DIM_WEIGHTS.keys())
        assert score_details["name_similarity"] == 1.0
        assert score_details["comment_similarity"] == 0.42
        assert score_details["inclusion_rate"] == 1.0
        assert score_details["jaccard_index"] == 0.5
        assert score_details["type_compatibility"] == 1.0
        assert reverse_inclusion_rate == 0.8
        assert cardinality in {"1:1", "1:N", "N:1", "M:N"}

    def test_old_four_dim_weights_rejected(self, mock_connector):
        """旧四维 weights 与五维 score_details 不一致时该候选不计分。"""
        config = {"weights": {
            "inclusion_rate": 0.50,
            "comment_similarity": 0.20,
            "type_compatibility": 0.20,
            "jaccard_index": 0.10,
        }}
        scorer = RelationshipScorer(config, mock_connector)
        scorer._sample_and_calculate_inclusion = Mock(
            return_value=(1.0, 1.0, 0.5, 1.0, 1.0, 1.0)
        )
        table = {
            "table_info": {"schema_name": "public", "table_name": "t"},
            "column_profiles": {"id": {"data_type": "integer"}},
        }
        candidate = {
            "source": table,
            "target": table,
            "source_columns": ["id"],
            "target_columns": ["id"],
        }
        details, _, _ = scorer._calculate_scores(table, ["id"], table, ["id"])
        assert "name_similarity" in details
        assert set(details.keys()) != set(scorer.weights.keys())
        scored = scorer.score_candidates([candidate], {})
        assert scored == []

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



class TestSampleFailurePaths:
    """采样失败路径的保守返回值（doc 19 回归：6 元组顺序修复）

    契约顺序:
    (inclusion_rate, reverse_inclusion_rate, jaccard_index,
     source_uniqueness, target_uniqueness, join_multiplicity)
    失败时不得把 target_uniqueness 误报为 1.0（否则空数据被误判 N:1）。
    """

    def _make_scorer(self, connector):
        config = {"weights": dict(FIVE_DIM_WEIGHTS)}
        return RelationshipScorer(config, connector)

    def test_empty_sample_returns_conservative_tuple(self):
        connector = Mock()
        connector.execute_query.return_value = []
        scorer = self._make_scorer(connector)
        result = scorer._sample_and_calculate_inclusion(
            "public", "a", ["id"], "public", "b", ["id"]
        )
        assert len(result) == 6
        assert result[3] == 0.0  # source_uniqueness
        assert result[4] == 0.0  # target_uniqueness（不得为 1.0）
        assert result[5] == 1.0  # join_multiplicity 保守 1.0

    def test_all_null_rows_returns_conservative_tuple(self):
        connector = Mock()
        connector.execute_query.return_value = [
            {"id": None}, {"id": None},
        ]
        scorer = self._make_scorer(connector)
        result = scorer._sample_and_calculate_inclusion(
            "public", "a", ["id"], "public", "b", ["id"]
        )
        assert result[3] == 0.0
        assert result[4] == 0.0
        assert result[5] == 1.0

    def test_query_exception_returns_conservative_tuple(self):
        connector = Mock()
        connector.execute_query.side_effect = RuntimeError("db down")
        scorer = self._make_scorer(connector)
        result = scorer._sample_and_calculate_inclusion(
            "public", "a", ["id"], "public", "b", ["id"]
        )
        assert result[3] == 0.0
        assert result[4] == 0.0
        assert result[5] == 1.0
