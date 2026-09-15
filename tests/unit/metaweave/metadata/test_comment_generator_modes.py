from __future__ import annotations

from unittest.mock import MagicMock

from metaweave.core.metadata.comment_generator import CommentGenerator
from metaweave.core.metadata.models import ColumnInfo, TableMetadata


def _metadata() -> TableMetadata:
    return TableMetadata(
        schema_name="public",
        table_name="orders",
        comment=" 数据库对象注释 ",
        comment_source="db",
        columns=[
            ColumnInfo("id", 1, "integer", comment=" 数据库字段注释 "),
            ColumnInfo("name", 2, "text", comment="   "),
        ],
    )


def test_incremental_mode_only_requests_missing_comments():
    service = MagicMock(model="test-model")
    service.generate_column_comments.return_value = {"name": "  新字段注释  "}
    generator = CommentGenerator(service)
    metadata = _metadata()

    result = generator.enrich_metadata_with_comments(metadata, overwrite=False)

    service.generate_table_comment.assert_not_called()
    assert service.generate_column_comments.call_count == 1
    assert [item["name"] for item in service.generate_column_comments.call_args.kwargs["columns"]] == ["name"]
    assert metadata.comment == "数据库对象注释"
    assert metadata.columns[0].comment == "数据库字段注释"
    assert metadata.columns[1].comment == "新字段注释"
    assert result.object_success_count == 0
    assert result.column_success_count == 1
    assert result.column_failure_count == 0


def test_overwrite_mode_clears_only_failed_items_and_keeps_partial_success():
    service = MagicMock(model="test-model")
    service.generate_table_comment.return_value = "   "
    service.generate_column_comments.return_value = {
        "id": " 刷新后的字段注释 ",
        "name": "\t",
    }
    generator = CommentGenerator(service)
    metadata = _metadata()

    result = generator.enrich_metadata_with_comments(metadata, overwrite=True)

    assert metadata.comment == ""
    assert metadata.comment_source == ""
    assert metadata.columns[0].comment == "刷新后的字段注释"
    assert metadata.columns[0].comment_source == "llm_generated"
    assert metadata.columns[1].comment == ""
    assert result.object_failure_count == 1
    assert result.column_success_count == 1
    assert result.column_failure_count == 1
    assert result.generated_count == 1
    assert len(result.failures) == 2
