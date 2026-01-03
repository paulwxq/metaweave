import json
import re

import pandas as pd

from metaweave.core.metadata.formatter import OutputFormatter
from metaweave.core.metadata.models import ColumnInfo, TableMetadata


def test_generate_ddl_sample_records_block_omits_generated_at(tmp_path):
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
    match = re.search(r"/\*\s*SAMPLE_RECORDS\s*(?P<body>\{.*?\})\s*\*/", ddl, re.DOTALL)
    assert match, "SAMPLE_RECORDS block should exist"

    payload = json.loads(match.group("body"))
    assert payload.get("version") == 1
    assert "generated_at" not in payload
    assert isinstance(payload.get("records"), list)
