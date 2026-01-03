from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.models import ColumnInfo, TableMetadata


def test_generate_ddl_includes_database_in_header(tmp_path):
    formatter = OutputFormatter(
        {
            "output_dir": tmp_path,
            "formats": ["ddl"],
        },
        database_name="store_db",
    )
    ddl = formatter.generate_ddl(
        TableMetadata(
            schema_name="public",
            table_name="department",
            comment="部门信息表",
            columns=[
                ColumnInfo(
                    column_name="dept_id",
                    ordinal_position=1,
                    data_type="integer",
                    is_nullable=False,
                )
            ],
        )
    )
    assert "-- Database: store_db" in ddl
    assert ddl.splitlines()[0] == "-- ===================================="
    assert ddl.splitlines()[1] == "-- Database: store_db"
