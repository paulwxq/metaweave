from metaweave.core.metadata.models import ColumnInfo, TableMetadata


def test_table_metadata_to_dict_uses_generated_timestamp_local():
    data = TableMetadata(
        schema_name="public",
        table_name="fact_store_sales_month",
        database="store_db",
        columns=[
            ColumnInfo(
                column_name="id",
                ordinal_position=1,
                data_type="integer",
                is_nullable=False,
            )
        ],
    ).to_dict()

    assert "generated_timestamp" in data
    assert "generated_at" not in data
    assert isinstance(data["generated_timestamp"], str)
    assert not data["generated_timestamp"].endswith("Z")
