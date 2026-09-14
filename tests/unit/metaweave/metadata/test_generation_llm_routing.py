from __future__ import annotations

from unittest.mock import MagicMock, patch

from metaweave.core.metadata.generation_config import MetadataGenerationConfig
from metaweave.core.metadata.generator import MetadataGenerator
from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer


def _config() -> dict:
    return {
        "llm": {
            "active": "qwen",
            "providers": {
                "qwen": {
                    "model": "global-model",
                    "api_key": "key",
                    "api_base": "https://example.invalid",
                }
            },
        },
        "ddl_generation": {
            "comments": {"llm_enabled": True},
            "llm": {"providers": {"qwen": {"model": "ddl-model"}}},
        },
        "json_generation": {
            "comments": {"llm_enabled": False},
            "table_classification": {"llm_enabled": True},
            "llm": {"providers": {"qwen": {"model": "json-model"}}},
        },
    }


def _generator(config: dict, step: str) -> MetadataGenerator:
    generator = MetadataGenerator.__new__(MetadataGenerator)
    generator.config = config
    generator.generation_config = MetadataGenerationConfig.from_config(config)
    generator.active_step = step
    generator.comment_enabled = False
    generator.llm_service = None
    generator.comment_generator = None
    return generator


def test_ddl_uses_ddl_specific_model():
    generator = _generator(_config(), "ddl")
    fake_service = MagicMock()

    with patch(
        "metaweave.core.metadata.generator.LLMService", return_value=fake_service
    ) as service_cls, patch("metaweave.core.metadata.generator.CommentGenerator"):
        generator._configure_step_llm()

    assert generator.comment_enabled is True
    assert service_cls.call_args.args[0]["providers"]["qwen"]["model"] == "ddl-model"


def test_ddl_disabled_does_not_require_or_initialize_llm():
    config = {"ddl_generation": {"comments": {"llm_enabled": False}}}
    generator = _generator(config, "ddl")

    with patch("metaweave.core.metadata.generator.LLMService") as service_cls:
        generator._configure_step_llm()

    service_cls.assert_not_called()
    assert generator.comment_enabled is False
    assert generator.llm_service is None


def test_json_step_does_not_initialize_ddl_llm():
    generator = _generator(_config(), "json")

    with patch("metaweave.core.metadata.generator.LLMService") as service_cls:
        generator._configure_step_llm()

    service_cls.assert_not_called()
    assert generator.comment_enabled is False


def test_json_enhancer_uses_json_specific_model_lazily():
    enhancer = JsonLlmEnhancer(_config())
    assert enhancer.llm_service is None

    with patch("metaweave.core.metadata.json_llm_enhancer.LLMService") as service_cls:
        enhancer._ensure_llm_service()

    assert service_cls.call_args.args[0]["providers"]["qwen"]["model"] == "json-model"
