import json
from pathlib import Path

from metaweave.core.dim_value.config_generator import DimTableConfigGenerator
from metaweave.core.dim_value.models import DimTablesConfig


def test_generate_dim_tables(tmp_path: Path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    # dim 表
    (json_dir / "dvdrental.public.dim_company.json").write_text(
        json.dumps(
            {
                "table_info": {"database": "dvdrental", "schema_name": "public", "table_name": "dim_company"},
                "table_profile": {"table_category": "dim"},
            }
        ),
        encoding="utf-8",
    )
    # 通过文件名回退解析 database
    (json_dir / "analytics.public.dim_region.json").write_text(
        json.dumps(
            {
                "table_profile": {
                    "table_category": "dim",
                    "schema_name": "public",
                    "table_name": "dim_region",
                }
            }
        ),
        encoding="utf-8",
    )
    # 非 dim 表
    (json_dir / "fact_sales.json").write_text(
        json.dumps(
            {
                "table_profile": {"table_category": "fact", "schema_name": "public", "table_name": "fact_sales"}
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "dim_tables.yaml"
    generator = DimTableConfigGenerator(json_dir=json_dir, output_path=output_path)

    config = generator.generate()
    assert "dvdrental" in config["databases"]
    assert "analytics" in config["databases"]
    assert "public.dim_company" in config["databases"]["dvdrental"]["tables"]
    assert "public.dim_region" in config["databases"]["analytics"]["tables"]
    assert "public.fact_sales" not in config["databases"]["dvdrental"]["tables"]
    assert output_path.exists()

    parsed = DimTablesConfig.from_yaml(config, database="dvdrental")
    assert "public.dim_company" in parsed.tables
    assert parsed.tables["public.dim_company"].embedding_col is None
