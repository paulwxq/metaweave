import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from metaweave.core.metadata.generator import MetadataGenerator


def _write_config(tmp_path: Path, object_types: list[str]) -> Path:
    ddl_dir = tmp_path / "ddl"
    md_dir = tmp_path / "md"
    config = {
        "database": {
            "database": "store_db",
            "schemas": ["public"],
            "include_object_types": object_types,
            "exclude_tables": [],
        },
        "sampling": {"enabled": False},
        "logical_key_detection": {"enabled": False},
        "ddl_generation": {"comments": {"llm_enabled": False}},
        "json_generation": {
            "comments": {"llm_enabled": False},
            "table_classification": {"llm_enabled": False},
        },
        "output": {
            "output_dir": str(tmp_path / "output"),
            "ddl_directory": str(ddl_dir),
            "markdown_directory": str(md_dir),
            "json_directory": str(tmp_path / "json"),
            "formats": ["ddl", "markdown", "json"],
            "ddl_options": {"sample_records": {"enabled": False, "count": 0}},
        },
    }
    config_path = tmp_path / "metadata_config.yaml"
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    ddl_dir.mkdir(parents=True, exist_ok=True)
    return config_path


def _write_table_ddl(ddl_dir: Path) -> None:
    (ddl_dir / "store_db.public.orders.sql").write_text(
        """CREATE TABLE public.orders (
    order_id INTEGER NOT NULL,
    CONSTRAINT orders_pkey PRIMARY KEY (order_id)
);
COMMENT ON COLUMN public.orders.order_id IS '订单ID';
COMMENT ON TABLE public.orders IS '订单表';
/* SAMPLED_RECORDS
{"object_type":"table","object_name":"public.orders","records":[{"order_id":"1"}]}
*/
""",
        encoding="utf-8",
    )


def _write_derived_ddl(
    ddl_dir: Path,
    *,
    object_name: str,
    object_type: str,
    with_unique_index: bool = False,
    with_samples: bool = True,
) -> None:
    payload = {
        "object_type": object_type,
        "object_name": f"public.{object_name}",
        "object_comment": "派生订单对象",
        "columns": [
            {
                "column_name": "order_id",
                "data_type": "integer",
                "column_comment": "订单ID",
            }
        ],
    }
    create_keyword = "VIEW" if object_type == "view" else "MATERIALIZED VIEW"
    index_sql = ""
    if with_unique_index:
        index_sql = (
            f"CREATE UNIQUE INDEX {object_name}_order_uidx "
            f"ON public.{object_name} USING btree (order_id);\n"
        )
    sample_block = ""
    if with_samples:
        sample_block = (
            "/* SAMPLED_RECORDS\n"
            f"{json.dumps({'object_type': object_type, 'object_name': f'public.{object_name}', 'records': [{'order_id': '1'}]}, ensure_ascii=False)}\n"
            "*/\n"
        )
    content = (
        f"CREATE {create_keyword} public.{object_name} AS SELECT 1 AS order_id;\n"
        "/* OBJECT_METADATA\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "*/\n"
        f"{index_sql}"
        f"{sample_block}"
    )
    (ddl_dir / f"store_db.public.{object_name}.sql").write_text(
        content,
        encoding="utf-8",
    )


def _write_all_object_types(ddl_dir: Path) -> None:
    _write_table_ddl(ddl_dir)
    _write_derived_ddl(
        ddl_dir,
        object_name="v_orders",
        object_type="view",
        with_samples=False,
    )
    _write_derived_ddl(
        ddl_dir,
        object_name="mv_orders",
        object_type="materialized_view",
        with_unique_index=True,
    )


def test_md_step_generates_table_view_and_materialized_view(tmp_path) -> None:
    config_path = _write_config(
        tmp_path,
        ["table", "view", "materialized_view"],
    )
    ddl_dir = tmp_path / "ddl"
    _write_all_object_types(ddl_dir)
    generator = MetadataGenerator(config_path)
    loader = generator._get_ddl_loader()

    with patch.object(loader, "load_table", wraps=loader.load_table) as load_table:
        result = generator.generate(step="md", max_workers=2)

    assert result.success is True
    assert result.processed_tables == 3
    assert result.failed_tables == 0
    assert result.processed_object_counts == {
        "table": 1,
        "view": 1,
        "materialized_view": 1,
    }
    assert len(result.output_files) == 3
    assert load_table.call_count == 3
    assert generator.connector is None
    assert generator.llm_service is None

    md_dir = tmp_path / "md"
    assert (
        (md_dir / "store_db.public.orders.md")
        .read_text(encoding="utf-8")
        .startswith("# public.orders [table]（订单表）")
    )
    assert (
        (md_dir / "store_db.public.v_orders.md")
        .read_text(encoding="utf-8")
        .startswith("# public.v_orders [view]（派生订单对象）")
    )
    assert "[示例: null]" in (md_dir / "store_db.public.v_orders.md").read_text(
        encoding="utf-8"
    )
    mv_markdown = (md_dir / "store_db.public.mv_orders.md").read_text(encoding="utf-8")
    assert mv_markdown.startswith(
        "# public.mv_orders [materialized_view]（派生订单对象）"
    )
    assert "- 唯一索引 mv_orders_order_uidx (btree): order_id" in mv_markdown


@pytest.mark.parametrize(
    ("selected_type", "expected_file"),
    [
        ("table", "store_db.public.orders.md"),
        ("view", "store_db.public.v_orders.md"),
        ("materialized_view", "store_db.public.mv_orders.md"),
    ],
)
def test_md_step_honors_include_object_types(
    tmp_path,
    selected_type,
    expected_file,
) -> None:
    config_path = _write_config(tmp_path, [selected_type])
    ddl_dir = tmp_path / "ddl"
    _write_all_object_types(ddl_dir)

    result = MetadataGenerator(config_path).generate(step="md", max_workers=1)

    assert result.processed_tables == 1
    assert result.failed_tables == 0
    assert result.processed_object_counts == {selected_type: 1}
    assert sorted(path.name for path in (tmp_path / "md").glob("*.md")) == [
        expected_file
    ]


def test_md_step_honors_tables_and_exclusions(tmp_path) -> None:
    config_path = _write_config(
        tmp_path,
        ["table", "view", "materialized_view"],
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["database"]["exclude_tables"] = ["public.v_orders"]
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _write_all_object_types(tmp_path / "ddl")

    result = MetadataGenerator(config_path).generate(
        step="md",
        tables=["v_orders", "mv_orders"],
        max_workers=1,
    )

    assert result.processed_tables == 1
    assert result.processed_object_counts == {"materialized_view": 1}


def test_md_step_reports_markdown_save_failure_once(tmp_path) -> None:
    config_path = _write_config(tmp_path, ["table"])
    _write_table_ddl(tmp_path / "ddl")
    generator = MetadataGenerator(config_path)

    with patch.object(generator.formatter, "format_and_save", return_value={}):
        result = generator.generate(step="md", max_workers=1)

    assert result.success is False
    assert result.processed_tables == 0
    assert result.failed_tables == 1
    assert result.processed_object_counts == {}
    assert len(result.errors) == 1
    assert "Markdown 保存失败" in result.errors[0]
