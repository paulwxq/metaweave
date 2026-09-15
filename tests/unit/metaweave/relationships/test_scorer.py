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

        # 不同的列名：无 embedding 服务时按降级语义"不同名放弃"，得 0.0
        # （doc 15 §2.4/§5：SequenceMatcher 模糊匹配路径已废弃，不再兜底）
        score = scorer._calculate_name_similarity(["user_id"], ["company_id"])
        assert score == 0.0

        # 同名但大小写不同 → 仍算同名短路（与 embedding 路径的 normalize 语义一致）
        score = scorer._calculate_name_similarity(["Store_ID"], ["store_id"])
        assert score == 1.0

        # 复合键
        score = scorer._calculate_name_similarity(
            ["store_id", "date_day"],
            ["store_id", "date_day"]
        )
        assert score == 1.0

    def test_comment_similarity_degraded_mode_same_name_not_flat_low_default(self, scorer):
        """降级模式（无 embedding 服务）下的 comment_similarity 不应对同名候选
        一律给低默认值 0.3——应统一退回名称相似度语义（同名 1.0/异名 0），
        与 §5 名称闸降级精神一致，避免 0.20 权重下拖累合法的同名候选评分。
        """
        assert scorer.name_similarity_service is None

        # 同名（即便双方都没有注释）→ 退回名称相似度 = 1.0，不是 comment_fallback_score
        score = scorer._score_comment_pair("store_id", None, "store_id", None)
        assert score == 1.0

        # 异名且双方都没有注释 → 退回名称相似度 = 0.0
        score = scorer._score_comment_pair("user_id", None, "company_id", None)
        assert score == 0.0

        # 同名但双方都写了注释：降级模式下没有 embedding 能力比较注释，
        # 仍应统一退回名称相似度（1.0），而不是尝试比较注释文本
        score = scorer._score_comment_pair("store_id", "门店编号", "store_id", "门店标识")
        assert score == 1.0

    def test_calculate_comment_similarity_degraded_mode_uses_name_fallback(self, scorer):
        """整列的 comment_similarity 计算（按列对回退）在降级模式下同样生效"""
        score = scorer._calculate_comment_similarity(
            ["store_id"], {"store_id": {"comment": None}},
            ["store_id"], {"store_id": {"comment": None}},
        )
        assert score == 1.0

    def test_comment_similarity_non_degraded_mode_unaffected_by_fix(self, mock_connector):
        """非降级模式（服务存在、注释通道启用）下的按列对回退三态语义不受本次
        降级修复影响：双方都有注释→embedding 比较；任一缺失→退回名称相似度；
        两者都缺（通道启用但该列确实无注释）→ 低默认值 0.3。
        """
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

        config = {"weights": {
            "inclusion_rate": 0.50, "comment_similarity": 0.20,
            "type_compatibility": 0.20, "jaccard_index": 0.10,
        }}
        scorer = RelationshipScorer(config, mock_connector, FakeNameSimilarityService())

        # 双方都有注释 → embedding 比较结果
        assert scorer._score_comment_pair("a", "注释A", "b", "注释B") == 0.42
        # 任一缺失 → 退回名称相似度
        assert scorer._score_comment_pair("store_id", "注释A", "store_id", None) == 1.0
        assert scorer._score_comment_pair("user_id", "注释A", "company_id", None) == 0.0
        # 两者都缺（通道启用但列本身无注释）→ 低默认值 0.3
        assert scorer._score_comment_pair("store_id", None, "store_id", None) == 0.3

    def test_comment_similarity_disabled_channel_falls_back_to_name(self, mock_connector):
        """comment_channel.enabled: false 是能力关闭，不是"两侧注释缺失"。
        应退回名称相似度（同名 1.0 / 异名 0），而不是一律 0.3；否则 0.20 权重
        会整体压低 composite_score，边缘候选可能被 accept_threshold 误杀。
        """
        class DisabledCommentChannel:
            enabled = False

            def is_usable(self, comment):
                return False

            def compare(self, a, b):
                raise AssertionError("禁用通道不应比较注释")

        class FakeNameSimilarityService:
            comment_channel = DisabledCommentChannel()

            def compare_columns(self, source_cols, target_cols):
                return 1.0 if [c.lower() for c in source_cols] == [c.lower() for c in target_cols] else 0.0

        config = {"weights": {
            "inclusion_rate": 0.50, "comment_similarity": 0.20,
            "type_compatibility": 0.20, "jaccard_index": 0.10,
        }}
        scorer = RelationshipScorer(config, mock_connector, FakeNameSimilarityService())

        # 同名，即便双方都写了注释：通道禁用 → 退回名称相似度 1.0，不是 0.3
        assert scorer._score_comment_pair("store_id", "门店编号", "store_id", "门店标识") == 1.0
        # 同名且无注释：同样退回 1.0，不能落到低默认值
        assert scorer._score_comment_pair("store_id", None, "store_id", None) == 1.0
        # 异名：退回名称相似度 0.0
        assert scorer._score_comment_pair("user_id", "用户", "company_id", "公司") == 0.0

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

