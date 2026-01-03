import json
from pathlib import Path

from metaweave.core.cql_generator.writer import CypherWriter
from metaweave.core.cql_generator.models import (
    TableNode,
    ColumnNode,
    HASColumnRelation,
    JOINOnRelation,
)


def test_import_all_includes_db_prefixed_ids_and_database_property(tmp_path):
    writer = CypherWriter(tmp_path)
    tables = [
        TableNode(full_name="public.dim_region", schema="public", name="dim_region", database="store_db"),
    ]
    columns = [
        ColumnNode(
            full_name="public.dim_region.city_name",
            schema="public",
            table="dim_region",
            name="city_name",
            data_type="varchar",
            database="store_db",
        )
    ]
    has_column_rels = [
        HASColumnRelation("public.dim_region", "public.dim_region.city_name"),
    ]
    join_on_rels = [
        JOINOnRelation(src_full_name="public.dim_region", dst_full_name="public.dim_region", cardinality="1:1"),
    ]

    output_files = writer.write_all(tables, columns, has_column_rels, join_on_rels)
    assert str(tmp_path / "import_all.store_db.cypher") in output_files

    content = (tmp_path / "import_all.store_db.cypher").read_text(encoding="utf-8")

    assert "CONSTRAINT column_id IF NOT EXISTS" in content
    assert "REQUIRE c.id IS UNIQUE" in content
    assert "SET n.id       = t.id" in content
    assert "n.database = t.database" in content
    assert "SET n.id           = c.id" in content
    assert "n.database     = c.database" in content

    # Verify embedded JSON contains expected values
    assert "\"id\": \"store_db.public.dim_region\"" in content
    assert "\"database\": \"store_db\"" in content
