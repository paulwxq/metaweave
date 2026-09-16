from __future__ import annotations

from unittest.mock import MagicMock, patch

from metaweave.core.metadata.generator import MetadataGenerator
from metaweave.core.metadata.json_llm_enhancer import JsonEnhancementResult
from metaweave.core.metadata.models import GenerationResult


def test_llm_failure_saves_rule_document_once_and_marks_result_failed(tmp_path):
    rule_document = {
        "metadata_version": "3.0",
        "object_info": {"schema_name": "public", "object_name": "orders"},
        "column_profiles": {},
        "table_profile": {
            "table_category": "fact",
            "classification_source": "rule",
        },
        "sample_records": {"sample_method": "none", "records": []},
    }
    output_path = tmp_path / "orders.public.orders.json"
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.config = {}
    generator._pending_json_documents = [
        (rule_document, output_path, "public.orders")
    ]
    generator.formatter = MagicMock()
    generator.formatter.save_json_document.return_value = output_path
    result = GenerationResult(success=True, processed_tables=1)

    outcome = JsonEnhancementResult(
        document=rule_document,
        success=False,
        llm_called=True,
        request_count=1,
        comment_task_attempted=True,
        classification_task_attempted=True,
        error="invalid response",
    )
    enhancer = MagicMock()
    enhancer.enhance_document.return_value = outcome

    with patch(
        "metaweave.core.metadata.json_llm_enhancer.JsonLlmEnhancer",
        return_value=enhancer,
    ):
        generator._finalize_json_documents(result)

    generator.formatter.save_json_document.assert_called_once_with(
        rule_document, output_path
    )
    assert result.success is False
    assert result.llm_request_count == 1
    assert result.llm_failure_count == 1
    assert result.llm_comment_failure_count == 1
    assert result.llm_classification_failure_count == 1
    assert result.output_files == [str(output_path)]
    assert result.table_category_counts == {"fact": 1}
    assert "已保存可用 JSON" in result.errors[0]


def test_successful_enhancement_is_saved_once_as_final_document(tmp_path):
    enhanced_document = {
        "metadata_version": "3.0",
        "object_info": {"schema_name": "public", "object_name": "orders"},
        "column_profiles": {},
        "table_profile": {
            "table_category": "dim",
            "classification_source": "llm",
            "classification_reason": "测试替身返回",
        },
        "sample_records": {"sample_method": "none", "records": []},
    }
    output_path = tmp_path / "orders.public.orders.json"
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.config = {}
    generator._pending_json_documents = [
        ({"rule": True}, output_path, "public.orders")
    ]
    generator.formatter = MagicMock()
    generator.formatter.save_json_document.return_value = output_path
    result = GenerationResult(success=True, processed_tables=1)

    outcome = JsonEnhancementResult(
        document=enhanced_document,
        success=True,
        llm_called=True,
        request_count=1,
        generated_comments=2,
        comment_task_attempted=True,
        comment_task_succeeded=True,
        classification_task_attempted=True,
        classification_task_succeeded=True,
    )
    enhancer = MagicMock()
    enhancer.enhance_document.return_value = outcome

    with patch(
        "metaweave.core.metadata.json_llm_enhancer.JsonLlmEnhancer",
        return_value=enhancer,
    ):
        generator._finalize_json_documents(result)

    generator.formatter.save_json_document.assert_called_once_with(
        enhanced_document, output_path
    )
    assert result.success is True
    assert result.llm_success_count == 1
    assert result.generated_comments == 2
    assert result.table_category_counts == {"dim": 1}
