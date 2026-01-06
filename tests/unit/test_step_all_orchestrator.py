from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import yaml
from click.testing import CliRunner

from metaweave.cli import metadata_cli
from metaweave.core.metadata.models import GenerationResult
from metaweave.core.relationships.models import RelationshipDiscoveryResult, Relation
from metaweave.core.cql_generator.models import CQLGenerationResult


def _write_config(tmp_path: Path) -> Path:
    # 重要：--clean 会校验输出目录必须位于项目根目录内，因此这里使用项目内路径
    out_dir = (Path.cwd().resolve() / "tests" / ".tmp" / f"out_{tmp_path.name}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "database": {
            "database": "test_db",
            "schemas": ["public"],
        },
        "output": {
            "output_dir": str(out_dir.relative_to(Path.cwd().resolve())),
            "json_directory": str((out_dir / "json").relative_to(Path.cwd().resolve())),
            "rel_directory": str((out_dir / "rel").relative_to(Path.cwd().resolve())),
            "cql_directory": str((out_dir / "cql").relative_to(Path.cwd().resolve())),
        },
        "comment_generation": {"enabled": False},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return path


class _DummyMetadataGenerator:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.config = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        out_dir = Path(self.config.get("output", {}).get("output_dir", "output"))
        self.formatter = SimpleNamespace(output_dir=out_dir)

    def generate(self, *, step: str, **_kwargs):
        step = (step or "").lower()
        out_dir = Path(self.config.get("output", {}).get("output_dir", "output"))
        (out_dir / "ddl").mkdir(parents=True, exist_ok=True)
        (out_dir / "json").mkdir(parents=True, exist_ok=True)

        output_files: list[str] = []
        if step == "ddl":
            ddl_file = out_dir / "ddl" / "test_db.public.test_table.sql"
            ddl_file.write_text("-- dummy ddl", encoding="utf-8")
            output_files.append(str(ddl_file))
        if step == "json":
            json_file = out_dir / "json" / "test_db.public.test_table.json"
            json_file.write_text("{}", encoding="utf-8")
            output_files.append(str(json_file))

        return GenerationResult(
            success=True,
            processed_tables=1,
            failed_tables=0,
            output_files=output_files,
            errors=[],
        )


class _DummyRelPipeline:
    def __init__(self, _config_path: Path):
        pass

    def discover(self) -> RelationshipDiscoveryResult:
        return RelationshipDiscoveryResult(success=True, total_relations=1)


class _DummyCQLGenerator:
    def __init__(self, _config_path: Path):
        pass

    def generate(self, step_name: str = "cql") -> CQLGenerationResult:
        return CQLGenerationResult(success=True, output_files=[f"import_all.{step_name}.cypher"])


class _DummyJsonLlmEnhancer:
    def __init__(self, _config: dict):
        pass

    def enhance_json_files(self, json_files):
        return len(list(json_files))


class _DummyDbConnector:
    def __init__(self, _db_config: dict):
        pass

    def close(self):
        return None


class _DummyRelDiscovery:
    def __init__(self, config: dict, connector, domain_filter=None, cross_domain=False, db_domains_config=None):
        out_dir = Path(config.get("output", {}).get("output_dir", "output"))
        self.json_dir = out_dir / "json"
        self.tables = {}

    def discover(self):
        return [], 0, {}


class _DummyRelWriter:
    def __init__(self, _config: dict):
        pass

    def write_results(self, **_kwargs):
        return ["out.json", "out.md"]


def test_step_all_orchestrates_in_order(tmp_path: Path, monkeypatch):
    cfg = _write_config(tmp_path)

    steps = []

    def _record_step(s):
        steps.append((s or "").lower())

    monkeypatch.setattr(metadata_cli, "MetadataGenerator", _DummyMetadataGenerator)
    monkeypatch.setattr(metadata_cli, "set_current_step", _record_step)

    monkeypatch.setattr(
        "metaweave.core.relationships.pipeline.RelationshipDiscoveryPipeline",
        _DummyRelPipeline,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.cql_generator.generator.CQLGenerator",
        _DummyCQLGenerator,
        raising=False,
    )

    runner = CliRunner()
    result = runner.invoke(metadata_cli.metadata_command, ["--config", str(cfg), "--step", "all"])

    assert result.exit_code == 0, result.output
    # 过滤掉 parent_step，只看子步骤顺序
    sub_steps = [s for s in steps if s != "all"]
    assert sub_steps == ["ddl", "md", "json", "rel", "cql"]
    assert "开始步骤: ddl" in result.output
    assert "开始步骤: cql" in result.output


def test_step_all_with_clean_flag(tmp_path: Path, monkeypatch):
    cfg = _write_config(tmp_path)
    loaded = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    out_dir = Path.cwd().resolve() / loaded["output"]["output_dir"]

    # 预置旧文件（应被清理掉）
    (out_dir / "ddl").mkdir(parents=True, exist_ok=True)
    (out_dir / "md").mkdir(parents=True, exist_ok=True)
    (out_dir / "json").mkdir(parents=True, exist_ok=True)
    (out_dir / "rel").mkdir(parents=True, exist_ok=True)
    (out_dir / "cql").mkdir(parents=True, exist_ok=True)
    (out_dir / "ddl" / "old.sql").write_text("old", encoding="utf-8")
    (out_dir / "md" / "old.md").write_text("old", encoding="utf-8")
    (out_dir / "json" / "old.json").write_text("old", encoding="utf-8")
    (out_dir / "rel" / "old.json").write_text("old", encoding="utf-8")
    (out_dir / "cql" / "old.cypher").write_text("old", encoding="utf-8")

    monkeypatch.setattr(metadata_cli, "MetadataGenerator", _DummyMetadataGenerator)
    monkeypatch.setattr(
        "metaweave.core.relationships.pipeline.RelationshipDiscoveryPipeline",
        _DummyRelPipeline,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.cql_generator.generator.CQLGenerator",
        _DummyCQLGenerator,
        raising=False,
    )

    runner = CliRunner()
    try:
        result = runner.invoke(
            metadata_cli.metadata_command,
            ["--config", str(cfg), "--step", "all", "--clean"],
        )
        assert result.exit_code == 0, result.output

        # old files removed
        assert not (out_dir / "ddl" / "old.sql").exists()
        assert not (out_dir / "md" / "old.md").exists()
        assert not (out_dir / "json" / "old.json").exists()
        assert not (out_dir / "rel" / "old.json").exists()
        assert not (out_dir / "cql" / "old.cypher").exists()

        # new artifacts exist where expected (dummy only writes ddl/json)
        assert (out_dir / "ddl" / "test_db.public.test_table.sql").exists()
        assert (out_dir / "json" / "test_db.public.test_table.json").exists()
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_step_all_fails_on_ddl_error(tmp_path: Path, monkeypatch):
    cfg = _write_config(tmp_path)

    steps = []

    def _record_step(s):
        steps.append((s or "").lower())

    class _FailingDdlGenerator(_DummyMetadataGenerator):
        def generate(self, *, step: str, **kwargs):
            if (step or "").lower() == "ddl":
                return GenerationResult(
                    success=False,
                    processed_tables=0,
                    failed_tables=1,
                    output_files=[],
                    errors=["ddl boom"],
                )
            return super().generate(step=step, **kwargs)

    monkeypatch.setattr(metadata_cli, "MetadataGenerator", _FailingDdlGenerator)
    monkeypatch.setattr(metadata_cli, "set_current_step", _record_step)

    # 如果继续执行到 rel/cql，说明 fail-fast 失效：让它们直接报错
    class _ShouldNotRun:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("should not run")

    monkeypatch.setattr(
        "metaweave.core.relationships.pipeline.RelationshipDiscoveryPipeline",
        _ShouldNotRun,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.cql_generator.generator.CQLGenerator",
        _ShouldNotRun,
        raising=False,
    )

    runner = CliRunner()
    result = runner.invoke(metadata_cli.metadata_command, ["--config", str(cfg), "--step", "all"])

    assert result.exit_code != 0
    # 过滤掉 parent_step，只看子步骤顺序
    sub_steps = [s for s in steps if s != "all"]
    assert sub_steps == ["ddl"]
    assert "❌ ddl 失败" in result.output


def test_step_all_stops_after_first_failure(tmp_path: Path, monkeypatch):
    cfg = _write_config(tmp_path)

    steps = []

    def _record_step(s):
        steps.append((s or "").lower())

    class _FailingJsonGenerator(_DummyMetadataGenerator):
        def generate(self, *, step: str, **kwargs):
            if (step or "").lower() == "json":
                return GenerationResult(
                    success=False,
                    processed_tables=1,
                    failed_tables=1,
                    output_files=[],
                    errors=["json boom"],
                )
            return super().generate(step=step, **kwargs)

    monkeypatch.setattr(metadata_cli, "MetadataGenerator", _FailingJsonGenerator)
    monkeypatch.setattr(metadata_cli, "set_current_step", _record_step)

    # rel/cql 不应该被执行
    class _ShouldNotRun:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("should not run")

    monkeypatch.setattr(
        "metaweave.core.relationships.pipeline.RelationshipDiscoveryPipeline",
        _ShouldNotRun,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.cql_generator.generator.CQLGenerator",
        _ShouldNotRun,
        raising=False,
    )

    runner = CliRunner()
    result = runner.invoke(metadata_cli.metadata_command, ["--config", str(cfg), "--step", "all"])

    assert result.exit_code != 0
    # ddl/md/json 执行后在 json 失败，后续 rel/cql 不应出现
    sub_steps = [s for s in steps if s != "all"]
    assert sub_steps == ["ddl", "md", "json"]
    assert "❌ json 失败" in result.output


def test_step_all_llm_orchestrates_in_order(tmp_path: Path, monkeypatch):
    cfg = _write_config(tmp_path)

    steps = []

    def _record_step(s):
        steps.append((s or "").lower())

    monkeypatch.setattr(metadata_cli, "MetadataGenerator", _DummyMetadataGenerator)
    monkeypatch.setattr(metadata_cli, "set_current_step", _record_step)

    monkeypatch.setattr(
        "metaweave.core.metadata.json_llm_enhancer.JsonLlmEnhancer",
        _DummyJsonLlmEnhancer,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.metadata.connector.DatabaseConnector",
        _DummyDbConnector,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.relationships.llm_relationship_discovery.LLMRelationshipDiscovery",
        _DummyRelDiscovery,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.relationships.writer.RelationshipWriter",
        _DummyRelWriter,
        raising=False,
    )
    monkeypatch.setattr(
        "metaweave.core.cql_generator.generator.CQLGenerator",
        _DummyCQLGenerator,
        raising=False,
    )

    runner = CliRunner()
    result = runner.invoke(metadata_cli.metadata_command, ["--config", str(cfg), "--step", "all_llm"])

    assert result.exit_code == 0, result.output
    # 过滤掉 parent_step，只看子步骤顺序
    sub_steps = [s for s in steps if s != "all_llm"]
    assert sub_steps == ["ddl", "md", "json_llm", "rel_llm", "cql"]
