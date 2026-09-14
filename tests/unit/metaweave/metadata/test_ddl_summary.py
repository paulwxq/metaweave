from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from click.testing import CliRunner

from metaweave.cli import metadata_cli
from metaweave.core.metadata.generator import MetadataGenerator
from metaweave.core.metadata.models import (
    ForeignKey,
    GenerationResult,
    IndexInfo,
    PrimaryKey,
    TableMetadata,
    UniqueConstraint,
)


def _composite_metadata(table_name: str = "orders") -> TableMetadata:
    return TableMetadata(
        schema_name="public",
        table_name=table_name,
        primary_keys=[PrimaryKey("orders_pkey", ["tenant_id", "order_id"])],
        foreign_keys=[
            ForeignKey(
                "orders_customer_fkey",
                ["tenant_id", "customer_id"],
                "public",
                "customers",
                ["tenant_id", "customer_id"],
            )
        ],
        unique_constraints=[
            UniqueConstraint("orders_number_key", ["tenant_id", "order_number"])
        ],
        indexes=[
            IndexInfo("orders_pkey", is_unique=True, is_primary=True),
            IndexInfo("orders_created_at_idx"),
        ],
    )


def _generator_for_counting() -> MetadataGenerator:
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator._result_lock = Lock()
    return generator


def test_physical_structure_counts_composite_constraints_as_one() -> None:
    generator = _generator_for_counting()
    result = GenerationResult(success=True)

    generator._accumulate_ddl_statistics(_composite_metadata(), result)

    assert result.physical_primary_key_constraints_found == 1
    assert result.physical_foreign_key_constraints_found == 1
    assert result.unique_constraints_found == 1
    assert result.indexes_found == 2
    assert result.regular_indexes_found == 1
    assert result.unique_indexes_found == 1
    assert result.indexes_found == (
        result.regular_indexes_found + result.unique_indexes_found
    )
    assert result.processed_object_counts == {"table": 1}


def test_physical_structure_counts_accumulate_safely() -> None:
    generator = _generator_for_counting()
    result = GenerationResult(success=True)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(
                generator._accumulate_ddl_statistics,
                _composite_metadata(f"orders_{index}"),
                result,
            )
            for index in range(100)
        ]
        for future in futures:
            future.result()

    assert result.physical_primary_key_constraints_found == 100
    assert result.physical_foreign_key_constraints_found == 100
    assert result.unique_constraints_found == 100
    assert result.indexes_found == 200
    assert result.regular_indexes_found == 100
    assert result.unique_indexes_found == 100
    assert result.indexes_found == (
        result.regular_indexes_found + result.unique_indexes_found
    )
    assert result.processed_object_counts == {"table": 100}


def test_materialized_view_unique_index_is_classified_separately() -> None:
    generator = _generator_for_counting()
    result = GenerationResult(success=True)
    metadata = TableMetadata(
        schema_name="public",
        table_name="mv_category_sales",
        table_type="materialized_view",
        indexes=[IndexInfo("uq_mv_category_sales_category_id", is_unique=True)],
    )

    generator._accumulate_ddl_statistics(metadata, result)

    assert result.indexes_found == 1
    assert result.regular_indexes_found == 0
    assert result.unique_indexes_found == 1
    assert result.unique_constraints_found == 0
    assert result.processed_object_counts == {"materialized_view": 1}


class _SummaryMetadataGenerator:
    def __init__(self, _config_path: Path):
        pass

    def generate(self, *, step: str, **_kwargs) -> GenerationResult:
        if step == "ddl":
            return GenerationResult(
                success=True,
                processed_tables=2,
                physical_primary_key_constraints_found=1,
                physical_foreign_key_constraints_found=2,
                unique_constraints_found=3,
                indexes_found=4,
                regular_indexes_found=3,
                unique_indexes_found=1,
                processed_object_counts={"table": 2},
            )
        if step == "md":
            return GenerationResult(
                success=True,
                processed_tables=3,
                processed_object_counts={
                    "table": 1,
                    "view": 1,
                    "materialized_view": 1,
                },
            )
        return GenerationResult(
            success=True,
            processed_tables=2,
            logical_keys_found=5,
        )


def test_cli_summary_is_specific_to_ddl_and_json(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "metadata_config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(metadata_cli, "MetadataGenerator", _SummaryMetadataGenerator)
    runner = CliRunner()

    ddl_result = runner.invoke(
        metadata_cli.metadata_command,
        ["--config", str(config_path), "--step", "ddl"],
    )

    assert ddl_result.exit_code == 0, ddl_result.output
    assert "成功处理: 2 个对象" in ddl_result.output
    assert "Table: 2 个" in ddl_result.output
    assert "物理主键约束: 1 个" in ddl_result.output
    assert "物理外键约束: 2 个" in ddl_result.output
    assert "唯一约束: 3 个" in ddl_result.output
    assert "索引总数: 4 个" in ddl_result.output
    assert "普通索引: 3 个" in ddl_result.output
    assert "唯一索引: 1 个" in ddl_result.output
    assert "逻辑主键识别: 未执行" in ddl_result.output
    assert "识别逻辑主键: 0 个" not in ddl_result.output

    json_result = runner.invoke(
        metadata_cli.metadata_command,
        ["--config", str(config_path), "--step", "json"],
    )

    assert json_result.exit_code == 0, json_result.output
    assert "识别逻辑主键: 5 个" in json_result.output
    assert "物理主键约束" not in json_result.output


def test_standard_rejects_non_table_ddl_objects(tmp_path) -> None:
    config_path = tmp_path / "metadata_config.yaml"
    config_path.write_text(
        "database:\n  include_object_types:\n    - table\n    - view\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        metadata_cli.metadata_command,
        ["--config", str(config_path), "--step", "standard"],
    )

    assert result.exit_code != 0
    assert "--step ddl、--step json 或 --step md" in result.output


def test_cli_md_summary_uses_database_object_counts(tmp_path, monkeypatch) -> None:
    ddl_dir = tmp_path / "ddl"
    ddl_dir.mkdir()
    (ddl_dir / "store_db.public.orders.sql").write_text(
        "CREATE TABLE public.orders (order_id INTEGER);\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "metadata_config.yaml"
    config_path.write_text(
        "database:\n"
        "  database: store_db\n"
        "  include_object_types: [table, view, materialized_view]\n"
        "output:\n"
        f"  ddl_directory: {ddl_dir}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(metadata_cli, "MetadataGenerator", _SummaryMetadataGenerator)

    result = CliRunner().invoke(
        metadata_cli.metadata_command,
        ["--config", str(config_path), "--step", "md"],
    )

    assert result.exit_code == 0, result.output
    assert "成功处理: 3 个对象" in result.output
    assert "Table: 1 个" in result.output
    assert "View: 1 个" in result.output
    assert "Materialized View: 1 个" in result.output


def test_cli_md_precheck_ignores_other_database_ddl(tmp_path) -> None:
    ddl_dir = tmp_path / "ddl"
    ddl_dir.mkdir()
    (ddl_dir / "other_db.public.orders.sql").write_text(
        "CREATE TABLE public.orders (order_id INTEGER);\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "metadata_config.yaml"
    config_path.write_text(
        "database:\n"
        "  database: store_db\n"
        "  include_object_types: [table]\n"
        "output:\n"
        f"  ddl_directory: {ddl_dir}\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        metadata_cli.metadata_command,
        ["--config", str(config_path), "--step", "md"],
    )

    assert result.exit_code != 0
    assert "当前数据库 store_db" in result.output
