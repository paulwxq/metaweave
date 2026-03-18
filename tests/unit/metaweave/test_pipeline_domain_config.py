"""pipeline_cli._step_rel_llm 从 yaml 读取 domain/cross_domain 的测试"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@dataclass
class _FakeContext:
    project_root: Path = Path(".")
    config_path: Path = Path("dummy.yaml")
    loaded_config: dict = field(default_factory=dict)
    domains_path: Path = Path("configs/db_domains.yaml")
    description: str = None
    regenerate_configs: bool = False
    sql_rag_gen_result: Any = None
    sql_rag_cfg: dict = field(default_factory=dict)
    llm_service: Any = None
    _sql_connector: Any = None


@pytest.fixture
def _patch_imports():
    """Mock 重量级依赖，使 _step_rel_llm 可在无 DB 环境下测试"""
    mock_connector_cls = MagicMock()
    mock_connector = MagicMock()
    mock_connector_cls.return_value = mock_connector
    mock_discovery_cls = MagicMock()
    mock_discovery = MagicMock()
    mock_discovery.json_dir = Path("output/json")
    mock_discovery.json_dir.exists = MagicMock(return_value=True)
    mock_discovery.discover.return_value = ([], 0, {})
    mock_discovery.tables = {}
    mock_discovery_cls.return_value = mock_discovery
    mock_writer_cls = MagicMock()

    with patch(
        "metaweave.cli.pipeline_cli.DatabaseConnector" if False else
        "metaweave.core.metadata.connector.DatabaseConnector",
        mock_connector_cls,
    ), patch(
        "metaweave.core.relationships.llm_relationship_discovery.LLMRelationshipDiscovery",
        mock_discovery_cls,
    ), patch(
        "metaweave.core.relationships.writer.RelationshipWriter",
        mock_writer_cls,
    ):
        yield {
            "connector_cls": mock_connector_cls,
            "discovery_cls": mock_discovery_cls,
            "writer_cls": mock_writer_cls,
        }


class TestStepRelLlmDomainFromYaml:
    """验证 _step_rel_llm 从 yaml 读取 domain/cross_domain"""

    def test_yaml_domain_null_means_no_domain(self, tmp_path):
        from metaweave.cli.pipeline_cli import _step_rel_llm, _StepError

        ctx = _FakeContext(
            loaded_config={
                "relationships": {"domain": None},
                "database": {},
                "output": {"json_directory": "output/json"},
            },
        )

        mock_connector = MagicMock()
        mock_discovery = MagicMock()
        mock_discovery.json_dir = MagicMock()
        mock_discovery.json_dir.exists.return_value = True
        mock_discovery.discover.return_value = ([], 0, {})
        mock_discovery.tables = {}

        with patch(
            "metaweave.core.metadata.connector.DatabaseConnector",
            return_value=mock_connector,
        ), patch(
            "metaweave.core.relationships.llm_relationship_discovery.LLMRelationshipDiscovery",
        ) as mock_disc_cls, patch(
            "metaweave.core.relationships.writer.RelationshipWriter",
        ):
            mock_disc_cls.return_value = mock_discovery
            _step_rel_llm(ctx)
            call_kwargs = mock_disc_cls.call_args[1]
            assert call_kwargs["domain_filter"] is None
            assert call_kwargs["cross_domain"] is False
            assert call_kwargs["domain_resolver"] is None

    def test_yaml_domain_all_cross_true(self, tmp_path):
        from metaweave.cli.pipeline_cli import _step_rel_llm

        domains_path = tmp_path / "db_domains.yaml"
        domains_path.write_text(
            "database:\n  name: test\ndomains:\n  - name: d1\n    tables: [t1]\n",
            encoding="utf-8",
        )

        ctx = _FakeContext(
            loaded_config={
                "relationships": {"domain": "all", "cross_domain": True},
                "database": {},
                "output": {"json_directory": "output/json"},
            },
            domains_path=domains_path,
        )

        mock_connector = MagicMock()
        mock_discovery = MagicMock()
        mock_discovery.json_dir = MagicMock()
        mock_discovery.json_dir.exists.return_value = True
        mock_discovery.discover.return_value = ([], 0, {})
        mock_discovery.tables = {}

        with patch(
            "metaweave.core.metadata.connector.DatabaseConnector",
            return_value=mock_connector,
        ), patch(
            "metaweave.core.relationships.llm_relationship_discovery.LLMRelationshipDiscovery",
        ) as mock_disc_cls, patch(
            "metaweave.core.relationships.writer.RelationshipWriter",
        ):
            mock_disc_cls.return_value = mock_discovery
            _step_rel_llm(ctx)
            call_kwargs = mock_disc_cls.call_args[1]
            assert call_kwargs["domain_filter"] == "all"
            assert call_kwargs["cross_domain"] is True
            assert call_kwargs["domain_resolver"] is not None

    def test_yaml_relationships_null(self, tmp_path):
        from metaweave.cli.pipeline_cli import _step_rel_llm

        ctx = _FakeContext(
            loaded_config={
                "relationships": None,
                "database": {},
                "output": {"json_directory": "output/json"},
            },
        )

        mock_connector = MagicMock()
        mock_discovery = MagicMock()
        mock_discovery.json_dir = MagicMock()
        mock_discovery.json_dir.exists.return_value = True
        mock_discovery.discover.return_value = ([], 0, {})
        mock_discovery.tables = {}

        with patch(
            "metaweave.core.metadata.connector.DatabaseConnector",
            return_value=mock_connector,
        ), patch(
            "metaweave.core.relationships.llm_relationship_discovery.LLMRelationshipDiscovery",
        ) as mock_disc_cls, patch(
            "metaweave.core.relationships.writer.RelationshipWriter",
        ):
            mock_disc_cls.return_value = mock_discovery
            _step_rel_llm(ctx)
            call_kwargs = mock_disc_cls.call_args[1]
            assert call_kwargs["domain_filter"] is None
            assert call_kwargs["cross_domain"] is False

    def test_yaml_domain_all_missing_domains_file_raises(self, tmp_path):
        from metaweave.cli.pipeline_cli import _step_rel_llm, _StepError

        ctx = _FakeContext(
            loaded_config={
                "relationships": {"domain": "all"},
                "database": {"database": "test"},
            },
            domains_path=tmp_path / "nonexistent.yaml",
        )

        with patch(
            "metaweave.core.metadata.connector.DatabaseConnector",
            return_value=MagicMock(),
        ):
            with pytest.raises(_StepError) as exc_info:
                _step_rel_llm(ctx)
            assert any("domains 配置文件不存在" in e for e in exc_info.value.errors)

    def test_yaml_domain_all_empty_domains_raises(self, tmp_path):
        from metaweave.cli.pipeline_cli import _step_rel_llm, _StepError

        domains_path = tmp_path / "db_domains.yaml"
        domains_path.write_text(
            "database:\n  name: test\ndomains: []\n",
            encoding="utf-8",
        )
        ctx = _FakeContext(
            loaded_config={
                "relationships": {"domain": "all"},
                "database": {"database": "test"},
            },
            domains_path=domains_path,
        )

        with patch(
            "metaweave.core.metadata.connector.DatabaseConnector",
            return_value=MagicMock(),
        ):
            with pytest.raises(_StepError) as exc_info:
                _step_rel_llm(ctx)
            assert any("domains 列表为空" in e for e in exc_info.value.errors)
