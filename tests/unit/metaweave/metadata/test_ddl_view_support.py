import json
import re
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from metaweave.core.metadata.connector import DatabaseConnector
from metaweave.core.metadata.extractor import MetadataExtractor
from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.generator import MetadataGenerator
from metaweave.core.metadata.models import (
    ColumnInfo,
    DatabaseObjectRef,
    IndexInfo,
    TableMetadata,
)
from metaweave.utils.sql_templates import (
    GET_DATABASE_OBJECT_INFO_SQL,
    GET_INDEXES_SQL,
    GET_MATERIALIZED_VIEW_COLUMNS_SQL,
    SAMPLE_DATA_SQL,
)
from metaweave.utils.data_utils import dataframe_to_sample_dict


def _generator_with_config(database_config: dict) -> MetadataGenerator:
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.config = {"database": database_config}
    return generator


def _extract_object_metadata(ddl: str) -> dict:
    match = re.search(
        r"/\* OBJECT_METADATA\s*(\{.*?\})\s*\*/",
        ddl,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_ddl_object_types_default_to_table() -> None:
    generator = _generator_with_config({})

    assert generator._resolve_ddl_object_types() == ["table"]


def test_ddl_object_types_validate_and_deduplicate() -> None:
    generator = _generator_with_config(
        {
            "include_object_types": [
                "TABLE",
                "view",
                "materialized_view",
                "view",
            ]
        }
    )

    assert generator._resolve_ddl_object_types() == [
        "table",
        "view",
        "materialized_view",
    ]

    generator.config["database"]["include_object_types"] = ["sequence"]
    with pytest.raises(ValueError, match="不支持的数据库对象类型"):
        generator._resolve_ddl_object_types()

    generator.config["database"]["include_object_types"] = "table"
    with pytest.raises(ValueError, match="必须是非空列表"):
        generator._resolve_ddl_object_types()


def test_connector_maps_selected_object_types_to_pg_relkinds() -> None:
    connector = DatabaseConnector.__new__(DatabaseConnector)
    connector.execute_query = MagicMock(
        return_value=[
            {
                "schema_name": "public",
                "object_name": "orders",
                "object_type": "table",
            },
            {
                "schema_name": "public",
                "object_name": "order_view",
                "object_type": "view",
            },
        ]
    )

    objects = connector.get_database_objects("public", ["table", "view"])

    assert objects == [
        DatabaseObjectRef("public", "orders", "table"),
        DatabaseObjectRef("public", "order_view", "view"),
    ]
    _, params = connector.execute_query.call_args.args
    assert params == ("public", ["r", "p", "v"])


def test_ddl_sampling_preserves_database_scalar_types() -> None:
    connector = DatabaseConnector.__new__(DatabaseConnector)
    connector.execute_query = MagicMock(
        return_value=[
            {
                "category_id": 9,
                "total_quantity": 169,
                "total_amount": Decimal("6191.00"),
            }
        ]
    )

    frame = connector.sample_data_preserving_types(
        "public",
        "mv_category_sales",
        5,
    )
    samples = dataframe_to_sample_dict(frame)

    assert samples == [
        {
            "category_id": "9",
            "total_quantity": "169",
            "total_amount": "6191.00",
        }
    ]
    assert all(str(dtype) == "object" for dtype in frame.dtypes)
    _, params = connector.execute_query.call_args.args
    assert params == (5,)


def test_ddl_sampling_uses_limit_without_ordering() -> None:
    normalized_sql = " ".join(SAMPLE_DATA_SQL.split()).upper()

    assert "LIMIT %S" in normalized_sql
    assert "ORDER BY" not in normalized_sql


def test_ddl_sampling_uses_configured_count_and_deduplicates_in_memory() -> None:
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.formatter = MagicMock(
        sample_record_options={"enabled": True, "count": 4}
    )
    generator.connector = MagicMock()
    generator.connector.sample_data_preserving_types.return_value = pd.DataFrame(
        [
            {"id": None, "payload": None},
            {"id": 1, "payload": {"name": "A", "tags": [1, 2]}},
            {"id": 1, "payload": {"tags": [1, 2], "name": "A"}},
            {"id": 2, "payload": {"name": "B"}},
        ],
        dtype=object,
    )

    result = generator._sample_data_for_ddl("public", "events")

    generator.connector.sample_data_preserving_types.assert_called_once_with(
        "public",
        "events",
        4,
    )
    assert result["id"].tolist() == [1, 2]
    assert isinstance(result.iloc[0]["payload"], dict)


def test_ddl_sampling_count_zero_skips_database_query() -> None:
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.formatter = MagicMock(
        sample_record_options={"enabled": True, "count": 0}
    )
    generator.connector = MagicMock()

    assert generator._sample_data_for_ddl("public", "events") is None
    generator.connector.sample_data_preserving_types.assert_not_called()


def test_ddl_sampling_count_ten_is_not_truncated_to_five() -> None:
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.formatter = MagicMock(
        sample_record_options={"enabled": True, "count": 10}
    )
    generator.connector = MagicMock()
    generator.connector.sample_data_preserving_types.return_value = pd.DataFrame(
        [{"id": value} for value in range(10)],
        dtype=object,
    )

    result = generator._sample_data_for_ddl("public", "events")

    generator.connector.sample_data_preserving_types.assert_called_once_with(
        "public",
        "events",
        10,
    )
    assert len(result) == 10


def test_index_query_does_not_join_inbound_foreign_key_constraints() -> None:
    normalized_sql = " ".join(GET_INDEXES_SQL.split())

    assert "con.conrelid = c.oid" in normalized_sql
    assert "con.contype IN ('p', 'u', 'x')" in normalized_sql


def test_materialized_view_column_query_extracts_type_modifiers() -> None:
    normalized_sql = " ".join(GET_MATERIALIZED_VIEW_COLUMNS_SQL.split())

    assert "format_type(attr.atttypid, NULL) AS data_type" in normalized_sql
    assert (
        "information_schema._pg_char_max_length( attr.atttypid, "
        "attr.atttypmod ) AS character_maximum_length"
    ) in normalized_sql
    assert (
        "information_schema._pg_numeric_precision( attr.atttypid, "
        "attr.atttypmod ) AS numeric_precision"
    ) in normalized_sql
    assert (
        "information_schema._pg_numeric_scale( attr.atttypid, "
        "attr.atttypmod ) AS numeric_scale"
    ) in normalized_sql


def test_database_object_info_query_does_not_read_row_counts() -> None:
    normalized_sql = " ".join(GET_DATABASE_OBJECT_INFO_SQL.split()).lower()

    assert "pg_stat_get_live_tuples" not in normalized_sql
    assert "row_count" not in normalized_sql


def test_extractor_skips_constraints_for_view_and_keeps_mv_indexes() -> None:
    connector = MagicMock()
    connector.check_database_object_exists.return_value = True
    extractor = MetadataExtractor(connector)
    extractor.extract_table_info = MagicMock(return_value={"object_comment": "汇总对象"})
    extractor.extract_columns = MagicMock(
        return_value=[ColumnInfo("order_id", 1, "bigint")]
    )
    extractor.extract_view_definition = MagicMock(return_value="SELECT order_id FROM orders")
    extractor.extract_primary_keys = MagicMock()
    extractor.extract_foreign_keys = MagicMock()
    extractor.extract_unique_constraints = MagicMock()
    extractor.extract_indexes = MagicMock(
        return_value=[IndexInfo("mv_order_id_uidx", is_unique=True)]
    )

    view = extractor.extract_all("public", "order_view", "view")

    assert view is not None
    assert view.table_type == "view"
    assert view.row_count == 0
    assert view.view_definition == "SELECT order_id FROM orders"
    extractor.extract_primary_keys.assert_not_called()
    extractor.extract_foreign_keys.assert_not_called()
    extractor.extract_unique_constraints.assert_not_called()
    extractor.extract_indexes.assert_not_called()

    materialized_view = extractor.extract_all(
        "public",
        "order_mv",
        "materialized_view",
    )

    assert materialized_view is not None
    assert materialized_view.table_type == "materialized_view"
    assert materialized_view.row_count == 0
    assert materialized_view.indexes[0].is_unique is True
    extractor.extract_indexes.assert_called_once_with("public", "order_mv")


def test_extractor_keeps_complete_index_definition() -> None:
    connector = MagicMock()
    connector.execute_query.return_value = [
        {
            "index_name": "order_mv_uidx",
            "index_type": "btree",
            "columns": ["order_id"],
            "is_unique": True,
            "is_primary": False,
            "is_constraint_backed": False,
            "constraint_name": None,
            "condition": "order_id > 0",
            "index_definition": (
                "CREATE UNIQUE INDEX order_mv_uidx ON public.order_mv "
                "USING btree (order_id) WHERE (order_id > 0)"
            ),
        }
    ]
    extractor = MetadataExtractor(connector)

    indexes = extractor.extract_indexes("public", "order_mv")

    assert len(indexes) == 1
    assert indexes[0].is_unique is True
    assert indexes[0].condition == "order_id > 0"
    assert indexes[0].definition == connector.execute_query.return_value[0][
        "index_definition"
    ]


def test_formatter_generates_view_ddl_and_object_metadata(tmp_path) -> None:
    formatter = OutputFormatter({"output_dir": tmp_path}, database_name="orders")
    metadata = TableMetadata(
        schema_name="public",
        table_name="order_view",
        table_type="view",
        comment="订单'视图",
        columns=[
            ColumnInfo("order_id", 1, "bigint", comment="订单编号"),
            ColumnInfo(
                "label",
                2,
                "character varying",
                character_maximum_length=100,
            ),
            ColumnInfo(
                "amount",
                3,
                "numeric",
                numeric_precision=10,
                numeric_scale=2,
            ),
        ],
        view_definition="SELECT order_id FROM public.orders;",
    )

    ddl = formatter.generate_ddl(metadata)

    assert "-- View: public.order_view" in ddl
    assert "-- Table: public.order_view" not in ddl
    assert "-- Object Type: view" in ddl
    assert "-- Comment: 订单'视图" in ddl
    object_metadata = _extract_object_metadata(ddl)
    assert object_metadata["object_comment"] == metadata.comment
    assert object_metadata == {
        "object_type": "view",
        "object_name": "public.order_view",
        "object_comment": "订单'视图",
        "columns": [
            {
                "column_name": "order_id",
                "data_type": "bigint",
                "column_comment": "订单编号",
            },
            {
                "column_name": "label",
                "data_type": "character varying(100)",
                "column_comment": "",
            },
            {
                "column_name": "amount",
                "data_type": "numeric(10,2)",
                "column_comment": "",
            },
        ],
    }
    assert "CREATE OR REPLACE VIEW public.order_view AS" in ddl
    assert "SELECT order_id FROM public.orders;" in ddl
    assert "COMMENT ON VIEW public.order_view IS '订单''视图';" in ddl
    assert "CREATE TABLE" not in ddl


def test_formatter_generates_mv_indexes_and_standalone_unique_indexes(tmp_path) -> None:
    formatter = OutputFormatter({"output_dir": tmp_path}, database_name="orders")
    metadata = TableMetadata(
        schema_name="public",
        table_name="order_mv",
        table_type="materialized_view",
        row_count=42,
        comment="订单物化视图",
        columns=[ColumnInfo("order_id", 1, "bigint", comment="订单编号")],
        indexes=[
            IndexInfo("order_mv_idx", columns=["order_id"]),
            IndexInfo(
                "order_mv_uidx",
                columns=["order_id"],
                is_unique=True,
                definition=(
                    "CREATE UNIQUE INDEX order_mv_uidx ON public.order_mv "
                    "USING btree (order_id) WHERE (order_id > 0)"
                ),
            ),
            IndexInfo(
                "constraint_backed_idx",
                columns=["order_id"],
                is_unique=True,
                is_constraint_backed=True,
                constraint_name="some_constraint",
            ),
        ],
        view_definition="SELECT order_id FROM public.orders",
    )

    ddl = formatter.generate_ddl(metadata)

    assert "-- Materialized View: public.order_mv" in ddl
    assert "-- Table: public.order_mv" not in ddl
    assert _extract_object_metadata(ddl) == {
        "object_type": "materialized_view",
        "object_name": "public.order_mv",
        "object_comment": "订单物化视图",
        "columns": [
            {
                "column_name": "order_id",
                "data_type": "bigint",
                "column_comment": "订单编号",
            }
        ],
    }
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS public.order_mv AS" in ddl
    assert "CREATE INDEX order_mv_idx ON public.order_mv(order_id);" in ddl
    assert (
        "CREATE UNIQUE INDEX order_mv_uidx ON public.order_mv "
        "USING btree (order_id) WHERE (order_id > 0);"
    ) in ddl
    assert "constraint_backed_idx ON" not in ddl


def test_formatter_keeps_standalone_unique_index_for_table(tmp_path) -> None:
    formatter = OutputFormatter({"output_dir": tmp_path}, database_name="orders")
    metadata = TableMetadata(
        schema_name="public",
        table_name="orders",
        columns=[ColumnInfo("external_id", 1, "text")],
        indexes=[
            IndexInfo(
                "orders_external_id_uidx",
                columns=["external_id"],
                is_unique=True,
            )
        ],
    )

    ddl = formatter.generate_ddl(metadata)

    assert (
        "CREATE UNIQUE INDEX orders_external_id_uidx "
        "ON public.orders(external_id);"
    ) in ddl
