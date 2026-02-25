from pathlib import Path

from click.testing import CliRunner

from metaweave.cli import metadata_cli


class _DummyDomainGenerator:
    init_kwargs = {}
    user_description = None

    def __init__(
        self,
        config,
        yaml_path,
        md_context=True,
        md_context_dir=None,
        md_context_mode="name_comment",
        md_context_limit=100,
    ):
        type(self).init_kwargs = {
            "config": config,
            "yaml_path": yaml_path,
            "md_context": md_context,
            "md_context_dir": md_context_dir,
            "md_context_mode": md_context_mode,
            "md_context_limit": md_context_limit,
        }

    def generate_from_context(self, user_description=None):
        type(self).user_description = user_description
        return {
            "database": {"name": "test_db", "description": "test desc"},
            "domains": [{"name": "订单", "description": "订单领域"}],
        }

    def write_to_yaml(self, _generated):
        yaml_path = Path(type(self).init_kwargs["yaml_path"])
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text("database:\n  name: test_db\n", encoding="utf-8")
        return [
            {"name": "_未分类_", "description": "无法归入其他业务主题的表"},
            {"name": "订单", "description": "订单领域"},
        ]


def test_generate_domains_uses_config_markdown_directory_by_default(tmp_path, monkeypatch):
    cfg = tmp_path / "metadata_config.yaml"
    cfg.write_text("database:\n  database: demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "metaweave.core.metadata.domain_generator.DomainGenerator",
        _DummyDomainGenerator,
    )
    monkeypatch.setattr(
        "services.config_loader.load_config",
        lambda _path: {"output": {"markdown_directory": "configured/md"}},
    )
    monkeypatch.setattr(metadata_cli, "get_project_root", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        metadata_cli.metadata_command,
        [
            "--config",
            str(cfg),
            "--generate-domains",
            "--description",
            "测试数据库说明",
        ],
    )

    assert result.exit_code == 0, result.output
    assert _DummyDomainGenerator.init_kwargs["md_context"] is True
    assert _DummyDomainGenerator.user_description == "测试数据库说明"
    expected_md_dir = str((tmp_path / "configured" / "md").resolve())
    assert _DummyDomainGenerator.init_kwargs["md_context_dir"] == expected_md_dir


def test_generate_domains_conflicts_with_cross_domain(tmp_path):
    cfg = tmp_path / "metadata_config.yaml"
    cfg.write_text("database:\n  database: demo\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        metadata_cli.metadata_command,
        [
            "--config",
            str(cfg),
            "--generate-domains",
            "--cross-domain",
        ],
    )

    assert result.exit_code != 0
    assert "互斥" in result.output
