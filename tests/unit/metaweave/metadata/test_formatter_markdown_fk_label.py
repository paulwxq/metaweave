from metaweave.core.metadata.formatter import OutputFormatter
import pytest

from metaweave.core.metadata.models import (
    ColumnInfo,
    ForeignKey,
    IndexInfo,
    PrimaryKey,
    TableMetadata,
)


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
            ColumnInfo(
                column_name="item_id",
                ordinal_position=1,
                data_type="integer",
                is_nullable=False,
            ),
            ColumnInfo(
                column_name="order_id",
                ordinal_position=2,
                data_type="integer",
                is_nullable=False,
            ),
            ColumnInfo(
                column_name="order_date",
                ordinal_position=3,
                data_type="date",
                is_nullable=False,
            ),
        ],
        primary_keys=[
            PrimaryKey(constraint_name="order_item_pkey", columns=["item_id"])
        ],
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
    assert (
        "- 外键约束 order_date, order_id 关联 public.order_header.order_date, order_id"
        in md
    )


@pytest.mark.parametrize("object_type", ["table", "view", "materialized_view"])
def test_markdown_title_contains_database_object_type(tmp_path, object_type):
    formatter = OutputFormatter(
        {"output_dir": tmp_path, "formats": ["markdown"]},
        database_name="store_db",
    )
    metadata = TableMetadata(
        schema_name="public",
        table_name="orders",
        table_type=object_type,
        comment="订单对象",
    )

    markdown = formatter.generate_markdown(metadata)

    assert markdown.splitlines()[0] == f"# public.orders [{object_type}]（订单对象）"


def test_markdown_includes_standalone_unique_index_details(tmp_path):
    formatter = OutputFormatter(
        {"output_dir": tmp_path, "formats": ["markdown"]},
        database_name="store_db",
    )
    metadata = TableMetadata(
        schema_name="public",
        table_name="mv_sales",
        table_type="materialized_view",
        indexes=[
            IndexInfo(
                index_name="mv_sales_category_uidx",
                index_type="btree",
                columns=["category_id"],
                is_unique=True,
                included_columns=["total_amount"],
                key_expressions=["category_id"],
                condition="category_id IS NOT NULL",
            ),
            IndexInfo(
                index_name="mv_sales_constraint_uidx",
                columns=["category_id"],
                is_unique=True,
                is_constraint_backed=True,
            ),
        ],
    )

    markdown = formatter.generate_markdown(metadata)

    assert (
        "- 唯一索引 mv_sales_category_uidx (btree): category_id；"
        "INCLUDE: total_amount；WHERE: category_id IS NOT NULL"
    ) in markdown
    assert "mv_sales_constraint_uidx" not in markdown
