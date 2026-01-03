from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.models import ColumnInfo, ForeignKey, PrimaryKey, TableMetadata


def test_markdown_supplementary_includes_fk_label(tmp_path):
    formatter = OutputFormatter(
        {
            "output_dir": tmp_path,
            "formats": ["markdown"],
        },
        database_name="store_db",
    )

    metadata = TableMetadata(
        schema_name="public",
        table_name="order_item",
        columns=[
            ColumnInfo(column_name="item_id", ordinal_position=1, data_type="integer", is_nullable=False),
            ColumnInfo(column_name="order_id", ordinal_position=2, data_type="integer", is_nullable=False),
            ColumnInfo(column_name="order_date", ordinal_position=3, data_type="date", is_nullable=False),
        ],
        primary_keys=[PrimaryKey(constraint_name="order_item_pkey", columns=["item_id"])],
        foreign_keys=[
            ForeignKey(
                constraint_name="fk_order_item_header",
                source_columns=["order_date", "order_id"],
                target_schema="public",
                target_table="order_header",
                target_columns=["order_date", "order_id"],
            )
        ],
    )

    md = formatter.generate_markdown(metadata)
    assert "- 主键约束 order_item_pkey: item_id" in md
    assert "- 外键约束 order_date, order_id 关联 public.order_header.order_date, order_id" in md
