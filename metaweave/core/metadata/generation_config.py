"""DDL/JSON 生成阶段的规范化配置。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_LANGUAGES = {"zh", "en", "bilingual"}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"配置错误：'{path}' 必须是对象")
    return value


def _boolean(config: Mapping[str, Any], key: str, default: bool, path: str) -> bool:
    if key not in config:
        return default
    value = config[key]
    if type(value) is not bool:
        raise ValueError(f"配置错误：'{path}.{key}' 必须是布尔值")
    return value


def _positive_integer(
    config: Mapping[str, Any], key: str, default: int, path: str
) -> int:
    if key not in config:
        return default
    value = config[key]
    if type(value) is not int or value <= 0:
        raise ValueError(f"配置错误：'{path}.{key}' 必须是大于 0 的整数")
    return value


@dataclass(frozen=True)
class DdlCommentsConfig:
    llm_enabled: bool = True


@dataclass(frozen=True)
class JsonCommentsConfig:
    llm_enabled: bool = True
    language: str = "zh"
    overwrite: bool = False
    max_columns_per_call: int = 120
    enable_batch_processing: bool = True


@dataclass(frozen=True)
class JsonTableClassificationConfig:
    llm_enabled: bool = True


@dataclass(frozen=True)
class MetadataGenerationConfig:
    ddl_comments: DdlCommentsConfig
    json_comments: JsonCommentsConfig
    json_table_classification: JsonTableClassificationConfig

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "MetadataGenerationConfig":
        ddl_generation = _mapping(config.get("ddl_generation"), "ddl_generation")
        ddl_comments = _mapping(
            ddl_generation.get("comments"), "ddl_generation.comments"
        )

        json_generation = _mapping(config.get("json_generation"), "json_generation")
        json_comments = _mapping(
            json_generation.get("comments"), "json_generation.comments"
        )
        table_classification = _mapping(
            json_generation.get("table_classification"),
            "json_generation.table_classification",
        )

        language_value = json_comments.get("language", "zh")
        if not isinstance(language_value, str):
            raise ValueError(
                "配置错误：'json_generation.comments.language' 必须是字符串"
            )
        language = language_value.strip().lower()
        if language in {"zh-cn", "zh_cn"}:
            language = "zh"
        if language not in _LANGUAGES:
            raise ValueError(
                "配置错误：'json_generation.comments.language' 必须是 "
                "zh、en 或 bilingual"
            )

        return cls(
            ddl_comments=DdlCommentsConfig(
                llm_enabled=_boolean(
                    ddl_comments,
                    "llm_enabled",
                    True,
                    "ddl_generation.comments",
                )
            ),
            json_comments=JsonCommentsConfig(
                llm_enabled=_boolean(
                    json_comments,
                    "llm_enabled",
                    True,
                    "json_generation.comments",
                ),
                language=language,
                overwrite=_boolean(
                    json_comments,
                    "overwrite",
                    False,
                    "json_generation.comments",
                ),
                max_columns_per_call=_positive_integer(
                    json_comments,
                    "max_columns_per_call",
                    120,
                    "json_generation.comments",
                ),
                enable_batch_processing=_boolean(
                    json_comments,
                    "enable_batch_processing",
                    True,
                    "json_generation.comments",
                ),
            ),
            json_table_classification=JsonTableClassificationConfig(
                llm_enabled=_boolean(
                    table_classification,
                    "llm_enabled",
                    True,
                    "json_generation.table_classification",
                )
            ),
        )
