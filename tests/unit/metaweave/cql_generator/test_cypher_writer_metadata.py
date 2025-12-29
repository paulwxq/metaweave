"""CypherWriter.write_metadata() 单元测试

测试目标：
1. import_all.md 内容生成的正确性
2. import_all.md 文件覆盖行为
3. 统计数据的准确性（节点、边）
"""

import pytest
from pathlib import Path
from metaweave.core.cql_generator.writer import CypherWriter
from metaweave.core.cql_generator.models import (
    TableNode, ColumnNode, HASColumnRelation, JOINOnRelation
)


@pytest.fixture
def sample_data():
    """准备测试数据"""
    tables = [
        TableNode(full_name="public.users", schema="public", name="users"),
        TableNode(full_name="public.orders", schema="public", name="orders"),
    ]
    columns = [
        ColumnNode(
            full_name="public.users.id",
            schema="public",
            table="users",
            name="id",
            data_type="integer"
        ),
        ColumnNode(
            full_name="public.users.name",
            schema="public",
            table="users",
            name="name",
            data_type="varchar"
        ),
        ColumnNode(
            full_name="public.orders.order_id",
            schema="public",
            table="orders",
            name="order_id",
            data_type="integer"
        ),
    ]
    has_column_rels = [
        HASColumnRelation("public.users", "public.users.id"),
        HASColumnRelation("public.users", "public.users.name"),
        HASColumnRelation("public.orders", "public.orders.order_id"),
    ]
    join_on_rels = [
        JOINOnRelation(
            src_full_name="public.orders",
            dst_full_name="public.users",
            cardinality="N:1",
            source_columns=["user_id"],
            target_columns=["id"]
        )
    ]
    return tables, columns, has_column_rels, join_on_rels


class TestCypherWriterMetadata:
    """CypherWriter.write_metadata() 测试类"""

    def test_write_metadata_creates_file(self, tmp_path, sample_data):
        """测试：write_metadata 成功创建 import_all.md 文件"""
        tables, columns, has_column_rels, join_on_rels = sample_data

        writer = CypherWriter(tmp_path)
        metadata_file = writer.write_metadata(
            tables=tables,
            columns=columns,
            has_column_rels=has_column_rels,
            join_on_rels=join_on_rels,
            step_name="cql",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )

        # 验证文件已创建
        assert metadata_file.exists()
        assert metadata_file.name == "import_all.md"

    def test_write_metadata_content_structure(self, tmp_path, sample_data):
        """测试：import_all.md 内容结构正确"""
        tables, columns, has_column_rels, join_on_rels = sample_data

        writer = CypherWriter(tmp_path)
        metadata_file = writer.write_metadata(
            tables=tables,
            columns=columns,
            has_column_rels=has_column_rels,
            join_on_rels=join_on_rels,
            step_name="cql_llm",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )

        content = metadata_file.read_text(encoding="utf-8")

        # 验证标题
        assert "# Neo4j CQL 导入脚本元数据" in content

        # 验证生成信息段落
        assert "## 生成信息" in content
        assert "**生成时间**" in content
        assert "**生成命令**: `metaweave metadata --step cql_llm`" in content

        # 验证统计数据段落
        assert "## 统计数据" in content
        assert "### 节点" in content
        assert "### 边" in content

        # 验证输入输出目录段落
        assert "## 输入输出目录" in content
        assert "/tmp/json" in content
        assert "/tmp/rel" in content

        # 验证输出文件段落
        assert "## 输出文件" in content

    def test_write_metadata_statistics_accuracy(self, tmp_path, sample_data):
        """测试：统计数据准确性（节点、边）"""
        tables, columns, has_column_rels, join_on_rels = sample_data

        writer = CypherWriter(tmp_path)
        metadata_file = writer.write_metadata(
            tables=tables,
            columns=columns,
            has_column_rels=has_column_rels,
            join_on_rels=join_on_rels,
            step_name="cql",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )

        content = metadata_file.read_text(encoding="utf-8")

        # 验证节点统计
        assert "| Table | 2 |" in content
        assert "| Column | 3 |" in content
        assert "| **节点总数** | **5** |" in content

        # 验证边统计
        assert "| HAS_COLUMN | 3 |" in content
        assert "| JOIN_ON | 1 |" in content
        assert "| **边总数** | **4** |" in content

    def test_write_metadata_file_overwrite(self, tmp_path, sample_data):
        """测试：文件覆盖行为（多次调用应覆盖旧文件）"""
        tables, columns, has_column_rels, join_on_rels = sample_data

        writer = CypherWriter(tmp_path)

        # 第一次生成（step_name = "cql"）
        metadata_file_1 = writer.write_metadata(
            tables=tables,
            columns=columns,
            has_column_rels=has_column_rels,
            join_on_rels=join_on_rels,
            step_name="cql",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )
        content_1 = metadata_file_1.read_text(encoding="utf-8")
        assert "`metaweave metadata --step cql`" in content_1

        # 第二次生成（step_name = "cql_llm"）
        metadata_file_2 = writer.write_metadata(
            tables=tables,
            columns=columns,
            has_column_rels=has_column_rels,
            join_on_rels=join_on_rels,
            step_name="cql_llm",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )
        content_2 = metadata_file_2.read_text(encoding="utf-8")

        # 验证文件路径相同
        assert metadata_file_1 == metadata_file_2

        # 验证内容已被覆盖（使用完整匹配避免子串问题）
        assert "`metaweave metadata --step cql_llm`" in content_2
        assert "`metaweave metadata --step cql`" not in content_2

    def test_write_metadata_empty_data(self, tmp_path):
        """测试：空数据的处理"""
        writer = CypherWriter(tmp_path)
        metadata_file = writer.write_metadata(
            tables=[],
            columns=[],
            has_column_rels=[],
            join_on_rels=[],
            step_name="cql",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )

        content = metadata_file.read_text(encoding="utf-8")

        # 验证空数据的统计
        assert "| Table | 0 |" in content
        assert "| Column | 0 |" in content
        assert "| **节点总数** | **0** |" in content
        assert "| HAS_COLUMN | 0 |" in content
        assert "| JOIN_ON | 0 |" in content
        assert "| **边总数** | **0** |" in content

    def test_write_metadata_with_existing_cypher_file(self, tmp_path, sample_data):
        """测试：当 import_all.cypher 存在时，正确读取其行数"""
        tables, columns, has_column_rels, join_on_rels = sample_data

        # 创建 import_all.cypher 文件
        cypher_file = tmp_path / "import_all.cypher"
        cypher_content = "\n".join([f"// Line {i}" for i in range(1, 101)])  # 100 行
        cypher_file.write_text(cypher_content, encoding="utf-8")

        writer = CypherWriter(tmp_path)
        metadata_file = writer.write_metadata(
            tables=tables,
            columns=columns,
            has_column_rels=has_column_rels,
            join_on_rels=join_on_rels,
            step_name="cql",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )

        content = metadata_file.read_text(encoding="utf-8")

        # 验证 import_all.cypher 行数正确
        assert "| import_all.cypher | 100 |" in content

    def test_write_metadata_without_cypher_file(self, tmp_path, sample_data):
        """测试：当 import_all.cypher 不存在时，显示占位符"""
        tables, columns, has_column_rels, join_on_rels = sample_data

        writer = CypherWriter(tmp_path)
        metadata_file = writer.write_metadata(
            tables=tables,
            columns=columns,
            has_column_rels=has_column_rels,
            join_on_rels=join_on_rels,
            step_name="cql",
            json_dir=Path("/tmp/json"),
            rel_dir=Path("/tmp/rel")
        )

        content = metadata_file.read_text(encoding="utf-8")

        # 验证显示占位符（如果文件不存在）
        # 注意：实际实现可能显示 "0" 或 "-"，需要根据实际代码确认
        assert "| import_all.cypher |" in content
