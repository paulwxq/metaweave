"""CQLGenerator 单元测试

测试目标：
1. 输入目录解析（json_directory, rel_directory, cql_directory）
2. 废弃配置检测（json_llm_directory）
3. step_name 参数传递
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from metaweave.core.cql_generator.generator import CQLGenerator
from metaweave.core.cql_generator.models import CQLGenerationResult


@pytest.fixture
def temp_config_file(tmp_path):
    """创建临时配置文件"""
    config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass",
            "schemas": ["public"]
        },
        "output": {
            "json_directory": "output/json",
            "rel_directory": "output/rel",
            "cql_directory": "output/cql"
        }
    }
    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
    return config_path


@pytest.fixture
def temp_config_file_with_deprecated(tmp_path):
    """创建包含废弃配置的临时配置文件"""
    config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass",
            "schemas": ["public"]
        },
        "output": {
            "json_directory": "output/json",
            "json_llm_directory": "output/json_llm",  # 废弃配置
            "rel_directory": "output/rel",
            "cql_directory": "output/cql"
        }
    }
    config_path = tmp_path / "test_config_deprecated.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
    return config_path


class TestCQLGenerator:
    """CQLGenerator 测试类"""

    def test_init_loads_config(self, temp_config_file):
        """测试：初始化时正确加载配置"""
        generator = CQLGenerator(temp_config_file)

        assert generator.config is not None
        assert generator.config["database"]["host"] == "localhost"
        assert generator.config["output"]["json_directory"] == "output/json"

    def test_input_directory_parsing(self, temp_config_file):
        """测试：正确解析输入输出目录"""
        generator = CQLGenerator(temp_config_file)

        # 验证目录解析（应该相对于项目根目录）
        assert generator.json_dir.name == "json"
        assert generator.rel_dir.name == "rel"
        assert generator.cql_dir.name == "cql"

        # 验证路径是绝对路径
        assert generator.json_dir.is_absolute()
        assert generator.rel_dir.is_absolute()
        assert generator.cql_dir.is_absolute()

    def test_deprecated_config_detection(self, temp_config_file_with_deprecated):
        """测试：检测废弃配置 json_llm_directory"""
        generator = CQLGenerator(temp_config_file_with_deprecated)

        # 验证废弃配置存在
        assert "json_llm_directory" in generator.config["output"]

        # 验证仍然使用 json_directory（不使用废弃配置）
        assert generator.json_dir.name == "json"

    @patch("metaweave.core.cql_generator.generator.JSONReader")
    @patch("metaweave.core.cql_generator.generator.CypherWriter")
    def test_generate_with_step_name(self, mock_writer_class, mock_reader_class, temp_config_file):
        """测试：generate() 方法正确传递 step_name 参数"""
        # 模拟 JSONReader
        mock_reader = MagicMock()
        mock_reader.read_all.return_value = ([], [], [], [])
        mock_reader_class.return_value = mock_reader

        # 模拟 CypherWriter
        mock_writer = MagicMock()
        mock_writer.write_all.return_value = ["/tmp/import_all.cypher"]
        mock_writer.write_metadata.return_value = Path("/tmp/import_all.md")
        mock_writer_class.return_value = mock_writer

        generator = CQLGenerator(temp_config_file)
        result = generator.generate(step_name="cql_llm")

        # 验证 write_metadata 被调用，且 step_name 参数正确
        mock_writer.write_metadata.assert_called_once()
        call_kwargs = mock_writer.write_metadata.call_args[1]
        assert call_kwargs["step_name"] == "cql_llm"

        # 验证返回结果
        assert isinstance(result, CQLGenerationResult)
        assert result.success is True

    @patch("metaweave.core.cql_generator.generator.JSONReader")
    @patch("metaweave.core.cql_generator.generator.CypherWriter")
    def test_generate_metadata_failure_captured_in_errors(
        self, mock_writer_class, mock_reader_class, temp_config_file
    ):
        """测试：元数据生成失败时异常被添加到 result.errors"""
        # 模拟 JSONReader
        mock_reader = MagicMock()
        mock_reader.read_all.return_value = ([], [], [], [])
        mock_reader_class.return_value = mock_reader

        # 模拟 CypherWriter：write_metadata 抛出异常
        mock_writer = MagicMock()
        mock_writer.write_all.return_value = ["/tmp/import_all.cypher"]
        mock_writer.write_metadata.side_effect = Exception("MD generation failed")
        mock_writer_class.return_value = mock_writer

        generator = CQLGenerator(temp_config_file)
        result = generator.generate(step_name="cql")

        # 验证 success 仍为 True（元数据生成失败不影响主流程）
        assert result.success is True

        # 验证异常被添加到 errors
        assert len(result.errors) == 1
        assert "元数据文档生成失败" in result.errors[0]
        assert "MD generation failed" in result.errors[0]

    @patch("metaweave.core.cql_generator.generator.JSONReader")
    @patch("metaweave.core.cql_generator.generator.CypherWriter")
    def test_generate_returns_correct_counts(
        self, mock_writer_class, mock_reader_class, temp_config_file
    ):
        """测试：generate() 返回正确的统计数据"""
        from metaweave.core.cql_generator.models import (
            TableNode, ColumnNode, HASColumnRelation, JOINOnRelation
        )

        # 模拟数据
        tables = [
            TableNode(full_name="public.table1", schema="public", name="table1"),
            TableNode(full_name="public.table2", schema="public", name="table2"),
        ]
        columns = [
            ColumnNode(
                full_name="public.table1.col1",
                schema="public",
                table="table1",
                name="col1",
                data_type="integer"
            ),
            ColumnNode(
                full_name="public.table1.col2",
                schema="public",
                table="table1",
                name="col2",
                data_type="varchar"
            ),
        ]
        has_column_rels = [
            HASColumnRelation("public.table1", "public.table1.col1"),
            HASColumnRelation("public.table1", "public.table1.col2"),
        ]
        join_on_rels = [
            JOINOnRelation(
                src_full_name="public.table1",
                dst_full_name="public.table2",
                cardinality="N:1"
            )
        ]

        # 模拟 JSONReader
        mock_reader = MagicMock()
        mock_reader.read_all.return_value = (tables, columns, has_column_rels, join_on_rels)
        mock_reader_class.return_value = mock_reader

        # 模拟 CypherWriter
        mock_writer = MagicMock()
        mock_writer.write_all.return_value = ["/tmp/import_all.cypher"]
        mock_writer.write_metadata.return_value = Path("/tmp/import_all.md")
        mock_writer_class.return_value = mock_writer

        generator = CQLGenerator(temp_config_file)
        result = generator.generate(step_name="cql")

        # 验证统计数据
        assert result.tables_count == 2
        assert result.columns_count == 2
        assert result.has_column_count == 2
        assert result.relationships_count == 1
        assert len(result.output_files) == 2  # .cypher + .md
