"""测试 OutputFormatter 的输出路径配置功能。"""

from pathlib import Path
import pytest
import yaml
from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.models import TableMetadata, ColumnInfo

@pytest.fixture
def sample_metadata():
    return TableMetadata(
        schema_name="public",
        table_name="test_table",
        columns=[
            ColumnInfo(column_name="id", ordinal_position=1, data_type="integer")
        ]
    )

def test_formatter_uses_default_paths(tmp_path, sample_metadata):
    """测试未指定显式目录时使用默认子目录。"""
    config = {
        "output_dir": str(tmp_path / "output")
    }
    formatter = OutputFormatter(config, database_name="test_db")
    
    # 验证属性
    assert formatter.ddl_dir == tmp_path / "output" / "ddl"
    assert formatter.json_dir == tmp_path / "output" / "json"
    assert formatter.markdown_dir == tmp_path / "output" / "md"
    
    # 验证目录是否创建
    assert formatter.ddl_dir.exists()
    assert formatter.json_dir.exists()
    assert formatter.markdown_dir.exists()
    
    # 验证保存路径
    paths = formatter.format_and_save(sample_metadata)
    assert Path(paths["ddl"]).parent == formatter.ddl_dir
    assert Path(paths["json"]).parent == formatter.json_dir
    assert Path(paths["markdown"]).parent == formatter.markdown_dir

def test_formatter_uses_custom_paths(tmp_path, sample_metadata):
    """测试使用显式的 ddl_directory, json_directory, markdown_directory。"""
    custom_ddl = tmp_path / "custom_ddl"
    custom_json = tmp_path / "custom_json"
    custom_md = tmp_path / "custom_md"
    
    config = {
        "output_dir": str(tmp_path / "output"),
        "ddl_directory": str(custom_ddl),
        "json_directory": str(custom_json),
        "markdown_directory": str(custom_md)
    }
    formatter = OutputFormatter(config, database_name="test_db")
    
    # 验证属性
    assert formatter.ddl_dir == custom_ddl
    assert formatter.json_dir == custom_json
    assert formatter.markdown_dir == custom_md
    
    # 验证目录是否创建
    assert custom_ddl.exists()
    assert custom_json.exists()
    assert custom_md.exists()
    
    # 验证保存路径
    paths = formatter.format_and_save(sample_metadata)
    assert Path(paths["ddl"]).parent == custom_ddl
    assert Path(paths["json"]).parent == custom_json
    assert Path(paths["markdown"]).parent == custom_md

def test_formatter_handles_relative_custom_paths(tmp_path, sample_metadata, monkeypatch):
    """测试使用相对路径的自定义目录。"""
    # 切换当前工作目录以便测试相对路径
    monkeypatch.chdir(tmp_path)
    
    config = {
        "output_dir": "output",
        "ddl_directory": "my_ddls",
        "json_directory": "my_jsons",
        "markdown_directory": "my_mds"
    }
    formatter = OutputFormatter(config, database_name="test_db")
    
    assert formatter.ddl_dir == tmp_path / "my_ddls"
    assert formatter.json_dir == tmp_path / "my_jsons"
    assert formatter.markdown_dir == tmp_path / "my_mds"
    
    assert (tmp_path / "my_ddls").exists()
    assert (tmp_path / "my_jsons").exists()
    assert (tmp_path / "my_mds").exists()
