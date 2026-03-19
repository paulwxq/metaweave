"""SQL RAG CLI 单元测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from metaweave.cli.sql_rag_cli import sql_rag_command


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def setup_configs(tmp_path):
    """创建 CLI 测试所需的配置文件和目录"""
    # metadata_config.yaml
    meta_cfg = {
        "llm": {"active": "test", "providers": {"test": {"model": "test-model"}}},
        "database": {"host": "localhost", "port": 5432, "database": "testdb"},
        "embedding": {
            "active": "qwen",
            "providers": {"qwen": {"dimensions": 4}},
        },
        "vector_database": {
            "active": "milvus",
            "providers": {"milvus": {"host": "localhost", "port": 19530}},
        },
        "sql_rag": {
            "generation": {
                "questions_per_domain": 2,
                "output_dir": str(tmp_path / "output" / "sql"),
            },
            "validation": {
                "sql_validation_max_concurrent": 2,
                "timeout": 10,
                "enable_sql_repair": False,
            },
        },
        "loaders": {
            "sql_loader": {
                "input_file": str(tmp_path / "output" / "sql" / "qs_testdb_pair.json"),
                "collection_name": "test_sql",
                "options": {"batch_size": 10},
            }
        },
    }
    meta_path = tmp_path / "metadata_config.yaml"
    meta_path.write_text(yaml.dump(meta_cfg), encoding="utf-8")

    # db_domains.yaml
    domains_cfg = {
        "database": {"name": "testdb", "description": "test"},
        "domains": [
            {"name": "测试域", "description": "测试", "tables": ["t1"]},
        ],
    }
    domains_path = tmp_path / "db_domains.yaml"
    domains_path.write_text(yaml.dump(domains_cfg, allow_unicode=True), encoding="utf-8")

    # md 目录
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    (md_dir / "t1.md").write_text("# t1\n字段: id", encoding="utf-8")

    return {
        "tmp_path": tmp_path,
        "domains_config": str(domains_path),
        "md_dir": str(md_dir),
        "meta_config": str(meta_path),
    }


class TestGenerateCommand:
    @patch("metaweave.cli.sql_rag_cli.get_project_root")
    def test_generate_basic(self, mock_root, runner, setup_configs, tmp_path):
        mock_root.return_value = tmp_path

        llm_response = json.dumps([
            {"question": "Q1", "sql": "SELECT 1;"},
        ])

        with patch("metaweave.services.llm_service.LLMService") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.call_llm.return_value = llm_response
            MockLLM.return_value = mock_llm

            result = runner.invoke(sql_rag_command, [
                "generate",
                "--config", setup_configs["meta_config"],
                "--domains-config", setup_configs["domains_config"],
                "--md-dir", setup_configs["md_dir"],
            ])

        assert result.exit_code == 0, result.output
        assert "生成完成" in result.output


class TestValidateCommand:
    @patch("metaweave.cli.sql_rag_cli.get_project_root")
    def test_validate_with_input(self, mock_root, runner, setup_configs, tmp_path):
        mock_root.return_value = tmp_path

        # 创建输入文件
        output_dir = tmp_path / "output" / "sql"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_file = output_dir / "qs_testdb_pair.json"
        input_file.write_text(json.dumps([
            {"question": "Q1", "sql": "SELECT 1;"},
        ]), encoding="utf-8")

        with patch("metaweave.core.metadata.connector.DatabaseConnector") as MockConn:
            mock_connector = MagicMock()
            MockConn.return_value = mock_connector

            with patch("metaweave.core.sql_rag.validator.SQLValidator") as MockVal:
                mock_validator = MagicMock()
                mock_validator.validate_file.return_value = {
                    "total": 1,
                    "valid": 1,
                    "invalid": 0,
                    "success_rate": 100.0,
                    "total_time": 0.1,
                    "repair_stats": {"attempted": 0, "successful": 0, "failed": 0},
                    "repair_apply_stats": {"modified": 0, "deleted": 0, "failed": 0},
                }
                MockVal.return_value = mock_validator

                result = runner.invoke(sql_rag_command, [
                    "validate",
                    "--config", setup_configs["meta_config"],
                    "--input", str(input_file),
                ])

        assert result.exit_code == 0, result.output
        assert "校验完成" in result.output
        mock_validator.validate_file.assert_called_once_with(
            input_file=str(input_file),
            enable_repair=False,
        )

    @patch("metaweave.cli.sql_rag_cli.get_project_root")
    def test_validate_cli_override_enable_sql_repair_true(
        self, mock_root, runner, setup_configs, tmp_path
    ):
        mock_root.return_value = tmp_path

        output_dir = tmp_path / "output" / "sql"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_file = output_dir / "qs_testdb_pair.json"
        input_file.write_text(json.dumps([{"question": "Q1", "sql": "SELECT 1;"}]), encoding="utf-8")

        with patch("metaweave.core.metadata.connector.DatabaseConnector"):
            with patch("metaweave.services.llm_service.LLMService") as MockLLM:
                with patch("metaweave.core.sql_rag.validator.SQLValidator") as MockVal:
                    mock_validator = MagicMock()
                    mock_validator.validate_file.return_value = {
                        "total": 1,
                        "valid": 1,
                        "invalid": 0,
                        "success_rate": 100.0,
                        "total_time": 0.1,
                        "repair_stats": {"attempted": 0, "successful": 0, "failed": 0},
                        "repair_apply_stats": {"modified": 0, "deleted": 0, "failed": 0},
                    }
                    MockVal.return_value = mock_validator

                    result = runner.invoke(sql_rag_command, [
                        "validate",
                        "--config", setup_configs["meta_config"],
                        "--input", str(input_file),
                        "--enable_sql_repair", "true",
                    ])

        assert result.exit_code == 0, result.output
        MockLLM.assert_called_once()
        mock_validator.validate_file.assert_called_once_with(
            input_file=str(input_file),
            enable_repair=True,
        )

    @patch("metaweave.cli.sql_rag_cli.get_project_root")
    def test_validate_cli_override_enable_sql_repair_false(
        self, mock_root, runner, setup_configs, tmp_path
    ):
        mock_root.return_value = tmp_path

        sql_rag_path = Path(setup_configs["meta_config"])
        cfg = yaml.safe_load(sql_rag_path.read_text(encoding="utf-8"))
        cfg["sql_rag"]["validation"]["enable_sql_repair"] = True
        sql_rag_path.write_text(yaml.dump(cfg), encoding="utf-8")

        output_dir = tmp_path / "output" / "sql"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_file = output_dir / "qs_testdb_pair.json"
        input_file.write_text(json.dumps([{"question": "Q1", "sql": "SELECT 1;"}]), encoding="utf-8")

        with patch("metaweave.core.metadata.connector.DatabaseConnector"):
            with patch("metaweave.services.llm_service.LLMService") as MockLLM:
                with patch("metaweave.core.sql_rag.validator.SQLValidator") as MockVal:
                    mock_validator = MagicMock()
                    mock_validator.validate_file.return_value = {
                        "total": 1,
                        "valid": 1,
                        "invalid": 0,
                        "success_rate": 100.0,
                        "total_time": 0.1,
                        "repair_stats": {"attempted": 0, "successful": 0, "failed": 0},
                        "repair_apply_stats": {"modified": 0, "deleted": 0, "failed": 0},
                    }
                    MockVal.return_value = mock_validator

                    result = runner.invoke(sql_rag_command, [
                        "validate",
                        "--config", setup_configs["meta_config"],
                        "--input", str(input_file),
                        "--enable_sql_repair", "false",
                    ])

        assert result.exit_code == 0, result.output
        MockLLM.assert_not_called()
        mock_validator.validate_file.assert_called_once_with(
            input_file=str(input_file),
            enable_repair=False,
        )


class TestLoadCommand:
    @patch("metaweave.cli.sql_rag_cli.get_project_root")
    def test_load_basic(self, mock_root, runner, setup_configs, tmp_path):
        mock_root.return_value = tmp_path

        # 创建输入文件
        output_dir = tmp_path / "output" / "sql"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_file = output_dir / "qs_testdb_pair.json"
        input_file.write_text(json.dumps([
            {"question": "Q1", "sql": "SELECT 1;"},
        ]), encoding="utf-8")

        with patch("metaweave.core.loaders.factory.LoaderFactory.create") as mock_create:
            mock_loader = MagicMock()
            mock_loader.validate.return_value = True
            mock_loader.load.return_value = {
                "success": True,
                "message": "加载 1 条",
                "loaded": 1,
                "skipped": 0,
                "execution_time": 0.5,
            }
            mock_create.return_value = mock_loader

            result = runner.invoke(sql_rag_command, [
                "load",
                "--config", setup_configs["meta_config"],
            ])

        assert result.exit_code == 0, result.output
        assert "加载完成" in result.output


class TestRunAllCommand:
    @patch("metaweave.cli.sql_rag_cli.get_project_root")
    def test_run_all_with_clean(self, mock_root, runner, setup_configs, tmp_path):
        mock_root.return_value = tmp_path

        output_file = tmp_path / "output" / "sql" / "qs_testdb_pair.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps([{"question": "Q1", "sql": "SELECT 1;"}]),
            encoding="utf-8",
        )

        with patch("metaweave.services.llm_service.LLMService") as MockLLM:
            mock_llm = MagicMock()
            MockLLM.return_value = mock_llm

            with patch(
                "metaweave.core.sql_rag.generator.QuestionSQLGenerator"
            ) as MockGen:
                mock_generator = MagicMock()
                mock_generator.generate.return_value = MagicMock(
                    success=True,
                    total_generated=1,
                    output_file=str(output_file),
                )
                MockGen.return_value = mock_generator

                with patch(
                    "metaweave.core.metadata.connector.DatabaseConnector"
                ) as MockConn:
                    MockConn.return_value = MagicMock()

                    with patch(
                        "metaweave.core.sql_rag.validator.SQLValidator"
                    ) as MockVal:
                        mock_validator = MagicMock()
                        mock_validator.validate_file.return_value = {
                            "total": 1,
                            "valid": 1,
                            "invalid": 0,
                            "success_rate": 100.0,
                            "total_time": 0.1,
                            "repair_stats": {
                                "attempted": 0,
                                "successful": 0,
                                "failed": 0,
                            },
                            "repair_apply_stats": {
                                "modified": 0,
                                "deleted": 0,
                                "failed": 0,
                            },
                        }
                        MockVal.return_value = mock_validator

                        with patch(
                            "metaweave.core.loaders.factory.LoaderFactory.create"
                        ) as mock_create:
                            mock_loader = MagicMock()
                            mock_loader.validate.return_value = True
                            mock_loader.load.return_value = {
                                "success": True,
                                "message": "加载 1 条",
                                "loaded": 1,
                                "skipped": 0,
                                "execution_time": 0.5,
                            }
                            mock_create.return_value = mock_loader

                            result = runner.invoke(sql_rag_command, [
                                "run-all",
                                "--config", setup_configs["meta_config"],
                                "--domains-config", setup_configs["domains_config"],
                                "--md-dir", setup_configs["md_dir"],
                                "--clean",
                            ])

        assert result.exit_code == 0, result.output
        mock_generator.clean_output.assert_called_once_with("testdb")
        mock_loader.load.assert_called_once_with(clean=True)

    @patch("metaweave.cli.sql_rag_cli.get_project_root")
    def test_run_all_shows_repair_summary(self, mock_root, runner, setup_configs, tmp_path):
        mock_root.return_value = tmp_path

        sql_rag_path = Path(setup_configs["meta_config"])
        cfg = yaml.safe_load(sql_rag_path.read_text(encoding="utf-8"))
        cfg["sql_rag"]["validation"]["enable_sql_repair"] = True
        sql_rag_path.write_text(yaml.dump(cfg), encoding="utf-8")

        output_file = tmp_path / "output" / "sql" / "qs_testdb_pair.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps([{"question": "Q1", "sql": "SELECT 1;"}]),
            encoding="utf-8",
        )

        with patch("metaweave.services.llm_service.LLMService") as MockLLM:
            MockLLM.return_value = MagicMock()

            with patch(
                "metaweave.core.sql_rag.generator.QuestionSQLGenerator"
            ) as MockGen:
                mock_generator = MagicMock()
                mock_generator.generate.return_value = MagicMock(
                    success=True,
                    total_generated=73,
                    output_file=str(output_file),
                )
                MockGen.return_value = mock_generator

                with patch(
                    "metaweave.core.metadata.connector.DatabaseConnector"
                ):
                    with patch(
                        "metaweave.core.sql_rag.validator.SQLValidator"
                    ) as MockVal:
                        mock_validator = MagicMock()
                        mock_validator.validate_file.return_value = {
                            "total": 73,
                            "valid": 69,
                            "invalid": 4,
                            "success_rate": 94.5,
                            "total_time": 0.1,
                            "repair_stats": {
                                "attempted": 4,
                                "successful": 4,
                                "failed": 0,
                            },
                            "repair_apply_stats": {
                                "modified": 4,
                                "deleted": 0,
                                "failed": 0,
                            },
                        }
                        MockVal.return_value = mock_validator

                        with patch(
                            "metaweave.core.loaders.factory.LoaderFactory.create"
                        ) as mock_create:
                            mock_loader = MagicMock()
                            mock_loader.validate.return_value = True
                            mock_loader.load.return_value = {
                                "success": True,
                                "message": "加载 73 条",
                                "loaded": 73,
                                "skipped": 0,
                                "execution_time": 0.5,
                            }
                            mock_create.return_value = mock_loader

                            result = runner.invoke(sql_rag_command, [
                                "run-all",
                                "--config", setup_configs["meta_config"],
                                "--domains-config", setup_configs["domains_config"],
                                "--md-dir", setup_configs["md_dir"],
                            ])

        assert result.exit_code == 0, result.output
        assert "原始有效: 69, 无效: 4" in result.output
        assert "修复尝试: 4, 成功: 4, 失败: 0" in result.output
        assert "修复后有效: 73, 有效率: 100.0%" in result.output
        assert "修复回写: 替换 4 条, 删除 0 条" in result.output
        assert "校验: 修复后有效 73/73 (100.0%)" in result.output


class TestSQLRagGroup:
    def test_help(self, runner):
        result = runner.invoke(sql_rag_command, ["--help"])
        assert result.exit_code == 0
        assert "SQL RAG" in result.output

    def test_generate_help(self, runner):
        result = runner.invoke(sql_rag_command, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--config" in result.output
        assert "--domains-config" in result.output

    def test_validate_help(self, runner):
        result = runner.invoke(sql_rag_command, ["validate", "--help"])
        assert result.exit_code == 0
        assert "--enable_sql_repair" in result.output

    def test_load_help(self, runner):
        result = runner.invoke(sql_rag_command, ["load", "--help"])
        assert result.exit_code == 0
        assert "--clean" in result.output

    def test_run_all_help(self, runner):
        result = runner.invoke(sql_rag_command, ["run-all", "--help"])
        assert result.exit_code == 0
        assert "--clean" in result.output
        assert "--domains-config" in result.output
