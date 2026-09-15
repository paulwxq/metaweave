from __future__ import annotations

import pytest

from metaweave.core.metadata.generation_config import MetadataGenerationConfig


def test_generation_config_defaults_enable_all_llm_tasks():
    config = MetadataGenerationConfig.from_config({})

    assert config.ddl_comments.llm_enabled is True
    assert config.ddl_comments.overwrite is False
    assert config.json_comments.llm_enabled is True
    assert config.json_table_classification.llm_enabled is True
    assert config.json_comments.overwrite is False
    assert config.json_comments.language == "zh"
    assert config.json_comments.max_columns_per_call == 120
    assert config.json_comments.enable_batch_processing is True


def test_generation_config_reads_independent_switches():
    config = MetadataGenerationConfig.from_config(
        {
            "ddl_generation": {
                "comments": {"llm_enabled": True, "overwrite": True}
            },
            "json_generation": {
                "comments": {
                    "llm_enabled": True,
                    "language": "en",
                    "overwrite": True,
                    "max_columns_per_call": 8,
                    "enable_batch_processing": False,
                },
                "table_classification": {"llm_enabled": True},
            },
        }
    )

    assert config.ddl_comments.llm_enabled is True
    assert config.ddl_comments.overwrite is True
    assert config.json_comments.llm_enabled is True
    assert config.json_comments.language == "en"
    assert config.json_comments.overwrite is True
    assert config.json_comments.max_columns_per_call == 8
    assert config.json_comments.enable_batch_processing is False
    assert config.json_table_classification.llm_enabled is True


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            {"ddl_generation": {"comments": {"llm_enabled": "true"}}},
            "ddl_generation.comments.llm_enabled",
        ),
        (
            {"json_generation": {"comments": {"overwrite": 1}}},
            "json_generation.comments.overwrite",
        ),
        (
            {
                "ddl_generation": {
                    "comments": {"llm_enabled": False, "overwrite": True}
                }
            },
            "ddl_generation.comments.overwrite=true",
        ),
        (
            {
                "json_generation": {
                    "comments": {"llm_enabled": False, "overwrite": True}
                }
            },
            "json_generation.comments.overwrite=true",
        ),
        (
            {
                "json_generation": {
                    "comments": {"enable_batch_processing": "false"}
                }
            },
            "json_generation.comments.enable_batch_processing",
        ),
        (
            {"json_generation": {"comments": {"language": "fr"}}},
            "json_generation.comments.language",
        ),
        (
            {"json_generation": {"comments": {"max_columns_per_call": 0}}},
            "json_generation.comments.max_columns_per_call",
        ),
    ],
)
def test_generation_config_rejects_invalid_values(config, message):
    with pytest.raises(ValueError, match=message):
        MetadataGenerationConfig.from_config(config)
