"""core 层 __init__() 空值防御测试

验证 relationships/sampling/embedding 为 null 时构造函数不崩溃。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLLMRelationshipDiscoveryNullConfig:
    """LLMRelationshipDiscovery（收缩为"LLM 候选产出器"，doc 15）接收
    relationships/sampling/embedding 为 null 时构造函数不崩溃。

    产出器本身不再持有 rel_config / sample_size（不做评分/DB采样），
    只需校验重试与异步相关属性按默认值降级。
    """

    @patch("metaweave.core.relationships.llm_relationship_discovery.LLMService")
    def test_init_with_null_config_sections(self, mock_llm_service):
        from metaweave.core.relationships.llm_relationship_discovery import (
            LLMRelationshipDiscovery,
        )

        config = {
            "relationships": None,
            "sampling": None,
            "embedding": None,
            "llm": {
                "active": "qwen",
                "providers": {"qwen": {"api_key": "dummy", "model": "qwen-plus"}}
            },
            "output": {"json_directory": "output/json"},
        }
        discovery = LLMRelationshipDiscovery(config=config)
        assert discovery.llm_max_retries == 3
        assert discovery.use_async is False

    @patch("metaweave.core.relationships.llm_relationship_discovery.LLMService")
    def test_init_with_empty_config(self, mock_llm_service):
        from metaweave.core.relationships.llm_relationship_discovery import (
            LLMRelationshipDiscovery,
        )

        config = {
            "relationships": {},
            "sampling": {},
            "embedding": {},
            "llm": {
                "active": "qwen",
                "providers": {"qwen": {"api_key": "dummy", "model": "qwen-plus"}}
            },
            "output": {"json_directory": "output/json"},
        }
        discovery = LLMRelationshipDiscovery(config=config)
        assert discovery.llm_max_retries == 3
        assert discovery.use_async is False


_PIPELINE_MODULE = "metaweave.core.relationships.pipeline"


class TestNameSimilarityInvalidConfigNotSwallowed:
    """显式非法配置（method: string）必须报错，不能被"无 embedding 环境"降级
    语义吞掉（doc 4.3 vs doc 15 第5节的边界，见 pipeline.py 初始化注释）。
    """

    @patch(f"{_PIPELINE_MODULE}.LLMRelationshipDiscovery")
    @patch(f"{_PIPELINE_MODULE}.RelationshipWriter")
    @patch(f"{_PIPELINE_MODULE}.DecisionEngine")
    @patch(f"{_PIPELINE_MODULE}.RelationshipScorer")
    @patch(f"{_PIPELINE_MODULE}.MetadataRepository")
    @patch(f"{_PIPELINE_MODULE}.DatabaseConnector")
    @patch(f"{_PIPELINE_MODULE}.RelationshipDiscoveryPipeline._load_config")
    def test_invalid_method_string_raises_not_degrades(
        self, mock_load, mock_connector, mock_repo, mock_scorer, mock_engine, mock_writer, mock_llm_discovery
    ):
        from metaweave.core.relationships.name_similarity import InvalidNameSimilarityConfig
        from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline

        mock_load.return_value = {
            "relationships": {"name_similarity": {"method": "string"}},
            "sampling": {},
            "embedding": {},
            "output": {"json_directory": "output/json"},
            "database": {},
        }

        with pytest.raises(InvalidNameSimilarityConfig):
            RelationshipDiscoveryPipeline(config_path=Path("dummy.yaml"))

    def test_comment_channel_invalid_method_raises(self):
        """comment_channel.method 与名称通道同一防御：非法取值检测到即报错，不得静默忽略"""
        from metaweave.core.relationships.name_similarity import (
            CommentSimilarityChannel,
            InvalidNameSimilarityConfig,
        )

        with pytest.raises(InvalidNameSimilarityConfig, match="comment_channel.method"):
            CommentSimilarityChannel({"enabled": False, "method": "string"}, {})

    @patch(f"{_PIPELINE_MODULE}.LLMRelationshipDiscovery")
    @patch(f"{_PIPELINE_MODULE}.RelationshipWriter")
    @patch(f"{_PIPELINE_MODULE}.DecisionEngine")
    @patch(f"{_PIPELINE_MODULE}.RelationshipScorer")
    @patch(f"{_PIPELINE_MODULE}.MetadataRepository")
    @patch(f"{_PIPELINE_MODULE}.DatabaseConnector")
    @patch(f"{_PIPELINE_MODULE}.RelationshipDiscoveryPipeline._load_config")
    def test_missing_embedding_env_still_degrades(
        self, mock_load, mock_connector, mock_repo, mock_scorer, mock_engine, mock_writer, mock_llm_discovery
    ):
        """真正的"无 embedding 环境"（embedding 配置缺失/不完整）仍应按第5节降级，不受本次修复影响"""
        from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline

        mock_load.return_value = {
            "relationships": {"name_similarity": {"method": "embedding"}},
            "sampling": {},
            "embedding": {},  # 缺少 active/providers，EmbeddingService 会失败
            "output": {"json_directory": "output/json"},
            "database": {},
        }

        pipeline = RelationshipDiscoveryPipeline(config_path=Path("dummy.yaml"))
        assert pipeline.name_similarity_service is None

    @patch(f"{_PIPELINE_MODULE}.LLMRelationshipDiscovery")
    @patch(f"{_PIPELINE_MODULE}.RelationshipWriter")
    @patch(f"{_PIPELINE_MODULE}.DecisionEngine")
    @patch(f"{_PIPELINE_MODULE}.RelationshipScorer")
    @patch(f"{_PIPELINE_MODULE}.MetadataRepository")
    @patch(f"{_PIPELINE_MODULE}.DatabaseConnector")
    @patch(f"{_PIPELINE_MODULE}.RelationshipDiscoveryPipeline._load_config")
    def test_non_positive_llm_top_k_raises(
        self, mock_load, mock_connector, mock_repo, mock_scorer, mock_engine, mock_writer, mock_llm_discovery
    ):
        """llm_candidates.top_k 必须是正整数；0 / 负数不得静默变成不限量或回退默认值"""
        from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline

        mock_load.return_value = {
            "relationships": {"llm_candidates": {"enabled": True, "top_k": 0}},
            "sampling": {},
            "embedding": {},
            "output": {"json_directory": "output/json"},
            "database": {},
        }
        with pytest.raises(ValueError, match="正整数"):
            RelationshipDiscoveryPipeline(config_path=Path("dummy.yaml"))


class TestRelationshipDiscoveryPipelineNullConfig:
    """RelationshipDiscoveryPipeline 接收 null config 节点时不抛 AttributeError

    __init__() 内部会依次创建 DatabaseConnector、MetadataRepository、
    RelationshipScorer、DecisionEngine、RelationshipWriter，
    测试需要全部隔离，否则会因缺少真实 DB 配置先崩溃。
    """

    @patch(f"{_PIPELINE_MODULE}.LLMRelationshipDiscovery")
    @patch(f"{_PIPELINE_MODULE}.RelationshipWriter")
    @patch(f"{_PIPELINE_MODULE}.DecisionEngine")
    @patch(f"{_PIPELINE_MODULE}.RelationshipScorer")
    @patch(f"{_PIPELINE_MODULE}.MetadataRepository")
    @patch(f"{_PIPELINE_MODULE}.DatabaseConnector")
    @patch(f"{_PIPELINE_MODULE}.RelationshipDiscoveryPipeline._load_config")
    def test_init_with_null_relationships(
        self, mock_load, mock_connector, mock_repo, mock_scorer, mock_engine, mock_writer, mock_llm_discovery
    ):
        from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline

        mock_load.return_value = {
            "relationships": None,
            "sampling": None,
            "embedding": None,
            "output": {"json_directory": "output/json"},
            "database": {},
        }
        pipeline = RelationshipDiscoveryPipeline(config_path=Path("dummy.yaml"))
        assert pipeline.rel_config.get("sample_size") == 1000
        # candidate_matching / name_similarity_service 均按降级语义构造成功
        assert pipeline.candidate_generator is not None
        assert pipeline.name_similarity_service is None

    @patch(f"{_PIPELINE_MODULE}.LLMRelationshipDiscovery")
    @patch(f"{_PIPELINE_MODULE}.RelationshipWriter")
    @patch(f"{_PIPELINE_MODULE}.DecisionEngine")
    @patch(f"{_PIPELINE_MODULE}.RelationshipScorer")
    @patch(f"{_PIPELINE_MODULE}.MetadataRepository")
    @patch(f"{_PIPELINE_MODULE}.DatabaseConnector")
    @patch(f"{_PIPELINE_MODULE}.RelationshipDiscoveryPipeline._load_config")
    def test_init_with_empty_relationships(
        self, mock_load, mock_connector, mock_repo, mock_scorer, mock_engine, mock_writer, mock_llm_discovery
    ):
        from metaweave.core.relationships.pipeline import RelationshipDiscoveryPipeline

        mock_load.return_value = {
            "relationships": {},
            "sampling": {},
            "embedding": {},
            "output": {"json_directory": "output/json"},
            "database": {},
        }
        pipeline = RelationshipDiscoveryPipeline(config_path=Path("dummy.yaml"))
        assert pipeline.rel_config.get("sample_size") == 1000
        assert pipeline.candidate_generator is not None
        assert pipeline.name_similarity_service is None
