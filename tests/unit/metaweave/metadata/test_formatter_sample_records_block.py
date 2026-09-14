import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.generator import MetadataGenerator
from metaweave.core.metadata.models import ColumnInfo, TableMetadata


@pytest.mark.parametrize("invalid_count", [-1, True, "5", 1.5])
def test_sample_record_count_must_be_a_non_negative_integer(
    tmp_path,
    invalid_count,
):
    with pytest.raises(ValueError, match="sample_records.count 必须是非负整数"):
        OutputFormatter(
            {
                "output_dir": tmp_path,
                "ddl_options": {
                    "sample_records": {"count": invalid_count},
                },
            },
            database_name="store_db",
        )


def test_generate_ddl_uses_compact_sampled_records_block(tmp_path):
    formatter = OutputFormatter(
        {
            "output_dir": tmp_path,
            "formats": ["ddl"],
            "ddl_options": {
                "sample_records": {
                    "enabled": True,
                    "count": 1,
                }
            },
        },
        database_name="store_db",
    )

    metadata = TableMetadata(
        schema_name="public",
        table_name="department",
        columns=[
            ColumnInfo(
                column_name="dept_id",
                ordinal_position=1,
                data_type="integer",
                is_nullable=False,
            ),
            ColumnInfo(
                column_name="dept_name",
                ordinal_position=2,
                data_type="character varying",
                is_nullable=False,
            ),
        ],
    )
    sample_df = pd.DataFrame([{"dept_id": 1, "dept_name": "HR"}])

    ddl = formatter.generate_ddl(metadata, sample_data=sample_df)
    match = re.search(
        r"/\*\s*SAMPLED_RECORDS\s*(?P<body>\{.*?\})\s*\*/",
        ddl,
        re.DOTALL,
    )
    assert match, "SAMPLED_RECORDS block should exist"

    payload = json.loads(match.group("body"))
    assert payload == {
        "object_type": "table",
        "object_name": "public.department",
        "records": [{"dept_id": "1", "dept_name": "HR"}],
    }
    assert "/* SAMPLE_RECORDS" not in ddl


def test_configured_sample_count_flows_from_ddl_to_json(tmp_path):
    formatter = OutputFormatter(
        {
            "output_dir": tmp_path,
            "ddl_options": {
                "sample_records": {
                    "enabled": True,
                    "count": 10,
                }
            },
        },
        database_name="store_db",
    )
    metadata = TableMetadata(
        schema_name="public",
        table_name="events",
        columns=[ColumnInfo("event_id", 1, "integer")],
        row_count=10,
    )
    sample_df = pd.DataFrame(
        [{"event_id": value} for value in range(10)],
        dtype=object,
    )

    formatter._save_ddl(metadata, sample_df)
    extracted = formatter._extract_sample_records_from_ddl(metadata)

    assert extracted is not None
    assert extracted["sample_method"] == "limit"
    assert extracted["sample_size"] == 10
    assert len(extracted["records"]) == 10

    json_path = formatter._save_json(metadata)
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_data["sample_records"] == {
        "sample_method": "limit",
        "records": [{"event_id": value} for value in range(10)],
    }


def test_formatter_reads_legacy_sample_records_block(tmp_path):
    formatter = OutputFormatter(
        {
            "output_dir": tmp_path,
            "ddl_directory": str(tmp_path),
            "ddl_options": {"sample_records": {"count": 5}},
        },
        database_name="store_db",
    )
    metadata = TableMetadata(
        schema_name="public",
        table_name="legacy_events",
        columns=[ColumnInfo("event_id", 1, "integer")],
        row_count=20,
    )
    ddl_path = tmp_path / "store_db.public.legacy_events.sql"
    ddl_path.write_text(
        """/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.legacy_events",
  "sample_method": "limit",
  "records": [
    {"label": "Record 1", "data": {"event_id": "7"}}
  ]
}
*/""",
        encoding="utf-8",
    )

    extracted = formatter._extract_sample_records_from_ddl(metadata)

    assert extracted == {
        "sample_method": "limit",
        "sample_size": 1,
        "total_rows": 20,
        "records": [{"event_id": 7}],
    }


def test_md_step_uses_normalized_ddl_sample_records() -> None:
    metadata = TableMetadata(
        schema_name="public",
        table_name="events",
        columns=[ColumnInfo("event_id", 1, "integer")],
    )
    parsed = SimpleNamespace(
        metadata=metadata,
        sample_records=[{"event_id": "1"}, {"event_id": "2"}],
    )
    loader = MagicMock()
    loader.load_table.return_value = parsed

    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.database_name = "store_db"
    generator.comment_enabled = False
    generator._get_ddl_loader = MagicMock(return_value=loader)
    generator.formatter = MagicMock()
    generator.formatter.format_and_save.return_value = {}

    generator._process_table_from_ddl_for_md(
        "public",
        "events",
        MagicMock(),
    )

    sample_data = generator.formatter.format_and_save.call_args.args[1]
    assert sample_data.to_dict(orient="records") == [
        {"event_id": "1"},
        {"event_id": "2"},
    ]
