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
            row_count=500,
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
    assert ddl.splitlines()[2] == "-- Table: public.department"
    assert "/* OBJECT_METADATA" not in ddl


def test_generate_ddl_renders_only_valid_type_modifiers(tmp_path):
    formatter = OutputFormatter(
        {"output_dir": tmp_path, "formats": ["ddl"]},
        database_name="store_db",
    )
    metadata = TableMetadata(
        schema_name="public",
        table_name="measurements",
        columns=[
            ColumnInfo(
                "id",
                1,
                "integer",
                numeric_precision=32,
                numeric_scale=0,
            ),
            ColumnInfo(
                "total",
                2,
                "numeric",
                numeric_precision=10,
                numeric_scale=2,
            ),
            ColumnInfo(
                "count",
                3,
                "numeric",
                numeric_precision=10,
                numeric_scale=0,
            ),
            ColumnInfo(
                "name",
                4,
                "character varying",
                character_maximum_length=50,
            ),
        ],
    )

    ddl = formatter.generate_ddl(metadata)

    assert "id INTEGER" in ddl
    assert "INTEGER(" not in ddl
    assert "total NUMERIC(10,2)" in ddl
    assert "count NUMERIC(10,0)" in ddl
    assert "name CHARACTER VARYING(50)" in ddl
