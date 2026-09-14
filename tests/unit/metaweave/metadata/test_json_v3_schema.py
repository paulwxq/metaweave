import json

import pandas as pd
import pytest

from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.metadata_document import (
    MetadataDocument,
    MetadataDocumentError,
)
from metaweave.core.metadata.models import (
    ColumnInfo,
    IndexInfo,
    PrimaryKey,
    TableMetadata,
    UniqueConstraint,
)
from metaweave.core.metadata.profiler import MetadataProfiler


def _profiled_metadata() -> tuple[TableMetadata, pd.DataFrame]:
    metadata = TableMetadata(
        schema_name="public",
        table_name="orders",
        database="orders",
        comment="订单表",
        row_count=2,
        columns=[
            ColumnInfo(
                "order_id",
                1,
                "integer",
                numeric_precision=32,
                numeric_scale=0,
                is_nullable=False,
                comment="订单编号",
                statistics={
                    "sample_count": 2,
                    "null_count": 0,
                    "null_rate": 0.0,
                    "unique_count": 2,
                    "uniqueness": 1.0,
                    "min": "1",
                    "max": "2",
                    "mean": "1.5",
                    "avg_length": 1.0,
                    "value_distribution": {"1": 1, "2": 1},
                },
            ),
            ColumnInfo(
                "amount",
                2,
                "numeric",
                numeric_precision=12,
                numeric_scale=2,
                is_nullable=True,
                statistics={
                    "sample_count": 2,
                    "null_count": 1,
                    "null_rate": 0.5,
                    "unique_count": 1,
                    "uniqueness": 0.5,
                    "min": "18.00",
                    "max": "18.00",
                },
            ),
        ],
        primary_keys=[PrimaryKey("orders_pkey", ["order_id"])],
        unique_constraints=[
            UniqueConstraint("orders_id_key", ["order_id"], is_partial=False)
        ],
        indexes=[
            IndexInfo(
                "orders_amount_expr_idx",
                columns=[],
                included_columns=["order_id"],
                key_expressions=["lower((amount)::text)"],
                definition="CREATE INDEX orders_amount_expr_idx ...",
            )
        ],
    )
    sample = pd.DataFrame(
        [{"order_id": 1, "amount": "18.00"}, {"order_id": 2, "amount": None}],
        dtype=object,
    )
    profiler = MetadataProfiler()
    metadata.column_profiles = profiler._profile_columns(metadata, sample)
    metadata.table_profile = profiler._profile_table(
        metadata,
        metadata.column_profiles,
    )
    return metadata, sample


def test_v3_formatter_emits_compact_schema(tmp_path):
    metadata, sample = _profiled_metadata()
    formatter = OutputFormatter(
        {
            "output_dir": tmp_path,
            "json_options": {"include_generation_timestamps": False},
            "ddl_options": {"sample_records": {"count": 2}},
        },
        database_name="orders",
    )

    path = formatter._save_json(metadata, sample)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["metadata_version"] == "3.0"
    assert "generated_timestamp" not in data
    assert "total_columns" not in data["table_info"]
    assert data["profiling"] == {"sample_method": "limit", "sample_count": 2}
    assert data["sample_records"] == {
        "sample_method": "limit",
        "records": [
            {"order_id": "1", "amount": "18.00"},
            {"order_id": "2", "amount": None},
        ],
    }

    order_id = data["column_profiles"]["order_id"]
    assert order_id["data_type"] == "integer"
    assert "column_name" not in order_id
    assert "character_maximum_length" not in order_id
    assert "numeric_precision" not in order_id
    assert "numeric_scale" not in order_id
    assert "structure_flags" not in order_id
    assert "role_specific_info" not in order_id
    assert order_id["statistics"] == {
        "null_count": 0,
        "unique_count": 2,
        "min": "1",
        "max": "2",
        "value_distribution": {"1": 1, "2": 1},
    }
    assert data["column_profiles"]["amount"]["data_type"] == "numeric(12,2)"

    table_profile = data["table_profile"]
    assert table_profile["classification_source"] == "rule"
    assert "classification_reason" not in table_profile
    assert "rule_based_classification" not in table_profile
    assert "column_statistics" not in table_profile
    assert "is_partial" not in table_profile["physical_constraints"][
        "unique_constraints"
    ][0]
    assert table_profile["indexes"][0]["included_columns"] == ["order_id"]
    assert table_profile["indexes"][0]["key_expressions"] == [
        "lower((amount)::text)"
    ]


def test_current_json_format_replaces_legacy_shape():
    metadata, _sample = _profiled_metadata()

    data = metadata.to_dict()

    assert data["metadata_version"] == "3.0"
    assert "generated_timestamp" in data
    assert "total_columns" not in data["table_info"]
    assert "column_name" not in data["column_profiles"]["order_id"]
    assert "structure_flags" not in data["column_profiles"]["order_id"]
    assert "role_specific_info" not in data["column_profiles"]["order_id"]


def test_metadata_document_derives_v3_rates_without_fabricating_missing_stats():
    metadata, _sample = _profiled_metadata()
    data = metadata.to_dict(
        include_generation_timestamp=False,
        profiling_sample_count=2,
    )
    data["column_profiles"]["unknown_value"] = {
        "ordinal_position": 3,
        "data_type": "bytea",
        "is_nullable": True,
        "column_default": None,
        "comment": "",
        "comment_source": "",
        "semantic_analysis": {
            "semantic_role": "complex",
            "semantic_confidence": 0.9,
            "inference_basis": [],
        },
    }
    document = MetadataDocument.from_dict(data)

    assert document.column_statistics("amount")["null_rate"] == 0.5
    assert document.column_statistics("amount")["uniqueness"] == 0.5
    assert document.column_statistics("unknown_value") == {}


def test_metadata_document_domain_accessors_use_structure_facts_only():
    data = {
        "metadata_version": "3.0",
        "table_info": {},
        "profiling": {"sample_method": "limit", "sample_count": 10},
        "column_profiles": {
            "id": {
                "data_type": "integer",
                "is_nullable": False,
                "statistics": {"null_count": 0, "unique_count": 10},
            },
            "tenant_id": {"data_type": "integer", "is_nullable": False},
            "included_value": {"data_type": "text", "is_nullable": True},
        },
        "table_profile": {
            "table_category": "dim",
            "confidence": 0.8,
            "inference_basis": [],
            "classification_source": "rule",
            "physical_constraints": {
                "primary_key": {"constraint_name": "pk", "columns": ["id"]},
                "foreign_keys": [],
                "unique_constraints": [
                    {"constraint_name": "uq", "columns": ["tenant_id", "id"]}
                ],
            },
            "indexes": [
                {
                    "columns": ["id"],
                    "key_expressions": ["id"],
                    "included_columns": ["included_value"],
                    "is_constraint_backed": True,
                },
                {
                    "columns": ["tenant_id"],
                    "key_expressions": ["tenant_id", "lower(email)"],
                    "included_columns": [],
                    "is_constraint_backed": False,
                },
            ],
            "unique_column_sets": [],
        },
    }
    document = MetadataDocument.from_dict(data)

    assert document.is_single_column_primary_key("id")
    assert document.is_data_unique("id")
    assert document.is_composite_unique_constraint_member("tenant_id")
    assert document.has_single_column_index("id")
    assert not document.is_composite_index_key_member("tenant_id")
    assert document.has_index_key("id", include_constraint_backed=True)
    assert not document.has_index_key("id", include_constraint_backed=False)
    assert not document.has_index_key("included_value")


def test_metadata_document_rejects_unknown_version_and_invalid_v3_classification():
    for unsupported_version in ("2.0", "9.0"):
        with pytest.raises(MetadataDocumentError, match="metadata_version"):
            MetadataDocument.from_dict(
                {
                    "metadata_version": unsupported_version,
                    "table_info": {},
                    "column_profiles": {},
                    "table_profile": {},
                }
            )

    with pytest.raises(MetadataDocumentError, match="classification_reason"):
        MetadataDocument.from_dict(
            {
                "metadata_version": "3.0",
                "table_info": {},
                "column_profiles": {},
                "table_profile": {
                    "classification_source": "llm",
                    "rule_based_classification": {},
                },
            }
        )
