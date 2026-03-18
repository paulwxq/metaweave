"""core 层 __init__() 空值防御测试

验证 relationships/sampling/embedding 为 null 时构造函数不崩溃。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLLMRelationshipDiscoveryNullConfig:
    """LLMRelationshipDiscovery 接收 null config 节点时不抛 AttributeError"""

    @patch("metaweave.core.relationships.llm_relationship_discovery.LLMService")
    @patch("metaweave.core.relationships.llm_relationship_discovery.RelationshipScorer")
    def test_init_with_null_config_sections(self, mock_scorer, mock_llm_service):
        from metaweave.core.relationships.llm_relationship_discovery import (
            LLMRelationshipDiscovery,
        )

        config = {
            "relationships": None,
            "sampling": None,
            "embedding": None,
            "llm": {},
            "output": {"json_directory": "output/json"},
        }
        connector = MagicMock()
        discovery = LLMRelationshipDiscovery(config=config, connector=connector)
        assert discovery.rel_config.get("sample_size") == 1000

    @patch("metaweave.core.relationships.llm_relationship_discovery.LLMService")
    @patch("metaweave.core.relationships.llm_relationship_discovery.RelationshipScorer")
    def test_init_with_empty_config(self, mock_scorer, mock_llm_service):
        from metaweave.core.relationships.llm_relationship_discovery import (
            LLMRelationshipDiscovery,
        )

        config = {
            "relationships": {},
            "sampling": {},
            "embedding": {},
            "llm": {},
            "output": {"json_directory": "output/json"},
        }
        connector = MagicMock()
        discovery = LLMRelationshipDiscovery(config=config, connector=connector)
        assert discovery.rel_config.get("sample_size") == 1000


_PIPELINE_MODULE = "metaweave.core.relationships.pipeline"


class TestRelationshipDiscoveryPipelineNullConfig:
    """RelationshipDiscoveryPipeline 接收 null config 节点时不抛 AttributeError

    __init__() 内部会依次创建 DatabaseConnector、MetadataRepository、
    RelationshipScorer、DecisionEngine、RelationshipWriter，
    测试需要全部隔离，否则会因缺少真实 DB 配置先崩溃。
    """

    @patch(f"{_PIPELINE_MODULE}.RelationshipWriter")
    @patch(f"{_PIPELINE_MODULE}.DecisionEngine")
    @patch(f"{_PIPELINE_MODULE}.RelationshipScorer")
    @patch(f"{_PIPELINE_MODULE}.MetadataRepository")
    @patch(f"{_PIPELINE_MODULE}.DatabaseConnector")
    @patch(f"{_PIPELINE_MODULE}.RelationshipDiscoveryPipeline._load_config")
    def test_init_with_null_relationships(
        self, mock_load, mock_connector, mock_repo, mock_scorer, mock_engine, mock_writer
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

    @patch(f"{_PIPELINE_MODULE}.RelationshipWriter")
    @patch(f"{_PIPELINE_MODULE}.DecisionEngine")
    @patch(f"{_PIPELINE_MODULE}.RelationshipScorer")
    @patch(f"{_PIPELINE_MODULE}.MetadataRepository")
    @patch(f"{_PIPELINE_MODULE}.DatabaseConnector")
    @patch(f"{_PIPELINE_MODULE}.RelationshipDiscoveryPipeline._load_config")
    def test_init_with_empty_relationships(
        self, mock_load, mock_connector, mock_repo, mock_scorer, mock_engine, mock_writer
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
