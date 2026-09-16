"""当前 JSON 元数据格式的统一读取与校验接口。

当前由统一的 ``json`` 生成流程使用。后续关系发现、CQL 和加载器迁移时可复用，
但本模块不会主动改变这些下游流程。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


CURRENT_METADATA_VERSION = "3.0"


class MetadataDocumentError(ValueError):
    """JSON 元数据结构或版本不符合契约。"""


@dataclass(frozen=True)
class MetadataDocument:
    """包装一份 JSON 元数据，并提供统一的事实读取。"""

    data: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetadataDocument":
        if not isinstance(data, dict):
            raise MetadataDocumentError("JSON 元数据根节点必须是对象")
        version = data.get("metadata_version")
        if version != CURRENT_METADATA_VERSION:
            raise MetadataDocumentError(
                f"不支持的 metadata_version: {version!r}；"
                f"当前格式版本必须为 {CURRENT_METADATA_VERSION}"
            )
        for key in ("table_info", "column_profiles", "table_profile"):
            if key not in data:
                raise MetadataDocumentError(f"JSON 元数据缺少必需字段: {key}")
        if not isinstance(data["table_info"], dict):
            raise MetadataDocumentError("table_info 必须是对象")
        if not isinstance(data["column_profiles"], dict):
            raise MetadataDocumentError("column_profiles 必须是对象")
        if data["table_profile"] is not None and not isinstance(
            data["table_profile"], dict
        ):
            raise MetadataDocumentError("table_profile 必须是对象或 null")

        document = cls(data)
        document._validate_shape()
        document.validate_classification_contract()
        document._validate_indexes()
        return document

    @property
    def version(self) -> str:
        return self.data["metadata_version"]

    @property
    def table_info(self) -> Dict[str, Any]:
        return self.data["table_info"]

    @property
    def column_profiles(self) -> Dict[str, Dict[str, Any]]:
        return self.data["column_profiles"]

    @property
    def total_columns(self) -> int:
        """字段数在 v3 中由 column_profiles 动态派生。"""
        return len(self.column_profiles)

    def semantic_role(self, column_name: str) -> Optional[str]:
        semantic = self.column_profiles[column_name].get("semantic_analysis")
        if not isinstance(semantic, dict):
            return None
        value = semantic.get("semantic_role")
        return str(value) if value is not None else None

    @property
    def table_profile(self) -> Dict[str, Any]:
        return self.data.get("table_profile") or {}

    @property
    def sample_records(self) -> Dict[str, Any]:
        value = self.data.get("sample_records") or {}
        if not isinstance(value, dict):
            raise MetadataDocumentError("sample_records 必须是对象")
        return value

    @property
    def profiling_sample_count(self) -> Optional[int]:
        profiling = self.data.get("profiling")
        if profiling is None:
            return None
        if not isinstance(profiling, dict):
            raise MetadataDocumentError("profiling 必须是对象")
        value = profiling.get("sample_count")
        return None if value is None else int(value)

    def effective_index_key_expressions(self, index: Dict[str, Any]) -> list[str]:
        """返回普通字段键与表达式键组成的完整索引键列表。"""
        value = index.get("key_expressions")
        if value is None or not isinstance(value, list):
            raise MetadataDocumentError("indexes[].key_expressions 必须是数组")
        return list(value)

    def included_columns(self, index: Dict[str, Any]) -> list[str]:
        value = index.get("included_columns")
        if value is None or not isinstance(value, list):
            raise MetadataDocumentError("indexes[].included_columns 必须是数组")
        return list(value)

    def column_statistics(self, column_name: str) -> Dict[str, Any]:
        """返回适合提示词的统计；缺失保持未知，不伪造为 0。"""
        column = self.column_profiles[column_name]
        raw = column.get("statistics")
        if not isinstance(raw, dict):
            return {}

        result = {}
        sample_count = self.profiling_sample_count
        if sample_count is None and "sample_count" in raw:
            sample_count = int(raw["sample_count"])
        if sample_count is not None:
            result["sample_count"] = sample_count

        for key in ("unique_count", "value_distribution", "min", "max"):
            if key in raw and raw[key] is not None:
                result[key] = deepcopy(raw[key])

        null_rate = raw.get("null_rate")
        if null_rate is None and sample_count not in (None, 0) and "null_count" in raw:
            null_rate = round(int(raw["null_count"]) / sample_count, 4)
        if null_rate is not None:
            result["null_rate"] = float(null_rate)

        uniqueness = raw.get("uniqueness")
        if (
            uniqueness is None
            and sample_count not in (None, 0)
            and "unique_count" in raw
        ):
            uniqueness = round(int(raw["unique_count"]) / sample_count, 4)
        if uniqueness is not None:
            result["uniqueness"] = float(uniqueness)
        return result

    def column_constraints(self, column_name: str) -> list[str]:
        """由表级结构事实生成供 LLM 使用的紧凑约束标签。"""
        constraints = self.table_profile.get("physical_constraints") or {}
        labels = []
        primary_key = constraints.get("primary_key") or {}
        if column_name in primary_key.get("columns", []):
            labels.append("primary_key")
        if any(
            column_name in item.get("source_columns", [])
            for item in constraints.get("foreign_keys", [])
        ):
            labels.append("foreign_key")
        if any(
            column_name in item.get("columns", [])
            for item in constraints.get("unique_constraints", [])
        ):
            labels.append("unique")
        if any(
            column_name in item.get("columns", [])
            for item in self.table_profile.get("unique_column_sets", [])
        ):
            labels.append("logical_unique_candidate")
        return labels

    def column_null_rate(self, column_name: str) -> Optional[float]:
        """返回四位小数空值率；统计不足时返回 None。"""
        return self.column_statistics(column_name).get("null_rate")

    def column_uniqueness(self, column_name: str) -> Optional[float]:
        """返回四位小数唯一度；统计不足时返回 None。"""
        return self.column_statistics(column_name).get("uniqueness")

    def is_single_column_primary_key(self, column_name: str) -> bool:
        primary_key = (
            self.table_profile.get("physical_constraints") or {}
        ).get("primary_key") or {}
        columns = primary_key.get("columns", [])
        return len(columns) == 1 and column_name in columns

    def is_composite_primary_key_member(self, column_name: str) -> bool:
        primary_key = (
            self.table_profile.get("physical_constraints") or {}
        ).get("primary_key") or {}
        columns = primary_key.get("columns", [])
        return len(columns) > 1 and column_name in columns

    def has_single_column_unique_constraint(self, column_name: str) -> bool:
        return any(
            item.get("columns") == [column_name]
            for item in self._unique_constraints()
        )

    def is_composite_unique_constraint_member(self, column_name: str) -> bool:
        return any(
            len(item.get("columns", [])) > 1
            and column_name in item.get("columns", [])
            for item in self._unique_constraints()
        )

    def is_data_unique(self, column_name: str) -> bool:
        uniqueness = self.column_uniqueness(column_name)
        return uniqueness is not None and uniqueness == 1.0

    def has_single_column_index(self, column_name: str) -> bool:
        return any(
            column_name in index.get("columns", [])
            and self.all_index_keys_are_columns(index)
            and len(self.effective_index_key_expressions(index)) == 1
            for index in self._indexes()
        )

    def is_composite_index_key_member(self, column_name: str) -> bool:
        return any(
            column_name in index.get("columns", [])
            and self.all_index_keys_are_columns(index)
            and len(self.effective_index_key_expressions(index)) > 1
            for index in self._indexes()
        )

    def all_index_keys_are_columns(self, index: Dict[str, Any]) -> bool:
        return len(index.get("columns", [])) == len(
            self.effective_index_key_expressions(index)
        )

    def has_index_key(
        self,
        column_name: str,
        *,
        include_constraint_backed: bool = True,
    ) -> bool:
        return any(
            column_name in index.get("columns", [])
            and (
                include_constraint_backed
                or not index.get("is_constraint_backed", False)
            )
            for index in self._indexes()
        )

    def _unique_constraints(self) -> list[Dict[str, Any]]:
        constraints = self.table_profile.get("physical_constraints") or {}
        value = constraints.get("unique_constraints", [])
        return value if isinstance(value, list) else []

    def _indexes(self) -> list[Dict[str, Any]]:
        value = self.table_profile.get("indexes", [])
        return value if isinstance(value, list) else []

    def build_json_llm_input(self, *, value_distribution_top_k: int = 10) -> Dict[str, Any]:
        """构造字段级白名单的 json_llm 提示词输入。"""
        table_info = self.table_info
        columns = {}
        for column_name, raw_column in self.column_profiles.items():
            if not isinstance(raw_column, dict):
                raise MetadataDocumentError(
                    f"column_profiles.{column_name} 必须是对象"
                )
            statistics = self.column_statistics(column_name)
            distribution = statistics.get("value_distribution")
            if isinstance(distribution, dict) and len(distribution) > value_distribution_top_k:
                statistics["value_distribution"] = dict(
                    sorted(
                        distribution.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )[:value_distribution_top_k]
                )
            column_view = {
                "column_name": column_name,
                "data_type": raw_column.get("data_type", "unknown"),
                "is_nullable": raw_column.get("is_nullable", True),
                "comment": raw_column.get("comment", ""),
                "constraints": self.column_constraints(column_name),
            }
            if statistics:
                column_view["statistics"] = statistics
            columns[column_name] = column_view

        records = self.sample_records.get("records", []) or []
        if not isinstance(records, list):
            raise MetadataDocumentError("sample_records.records 必须是数组")
        return {
            "table_info": {
                "schema_name": table_info.get("schema_name", ""),
                "table_name": table_info.get("table_name", ""),
                "table_type": table_info.get("table_type", "table"),
                "comment": table_info.get("comment", ""),
            },
            "column_profiles": columns,
            "sample_records": {
                "sample_method": self.sample_records.get("sample_method", "none"),
                "records": records,
            },
            "physical_constraints": self.table_profile.get(
                "physical_constraints",
                {
                    "primary_key": None,
                    "foreign_keys": [],
                    "unique_constraints": [],
                },
            ),
        }

    def validate_classification_contract(self) -> None:
        if not self.table_profile:
            return
        source = self.table_profile.get("classification_source")
        if source not in {"rule", "llm"}:
            raise MetadataDocumentError(
                "v3 table_profile.classification_source 必须是 rule 或 llm"
            )
        has_reason = "classification_reason" in self.table_profile
        has_rule_backup = "rule_based_classification" in self.table_profile
        if source == "llm":
            reason = self.table_profile.get("classification_reason")
            if not isinstance(reason, str) or not reason.strip():
                raise MetadataDocumentError(
                    "classification_source=llm 时 classification_reason 必须非空"
                )
            if not isinstance(
                self.table_profile.get("rule_based_classification"), dict
            ):
                raise MetadataDocumentError(
                    "classification_source=llm 时 rule_based_classification 必须存在"
                )
        elif has_reason or has_rule_backup:
            raise MetadataDocumentError(
                "classification_source=rule 时不得输出 classification_reason 或 "
                "rule_based_classification"
            )

    def _validate_indexes(self) -> None:
        indexes: Iterable[Any] = self.table_profile.get("indexes", [])
        if not isinstance(indexes, list):
            raise MetadataDocumentError("table_profile.indexes 必须是数组")
        for index in indexes:
            if not isinstance(index, dict):
                raise MetadataDocumentError("table_profile.indexes[] 必须是对象")
            for key in ("key_expressions", "included_columns"):
                if key not in index:
                    raise MetadataDocumentError(
                        f"JSON table_profile.indexes[] 缺少 {key}"
                    )
            self.effective_index_key_expressions(index)
            self.included_columns(index)

    def _validate_shape(self) -> None:
        """校验当前格式，并拒绝旧格式字段混入。"""
        if "total_columns" in self.table_info:
            raise MetadataDocumentError("JSON v3 不允许 table_info.total_columns")

        profiling = self.data.get("profiling")
        if profiling is not None:
            if not isinstance(profiling, dict):
                raise MetadataDocumentError("profiling 必须是对象")
            if profiling.get("sample_method") != "limit":
                raise MetadataDocumentError(
                    "JSON v3 当前仅允许 profiling.sample_method=limit"
                )
            sample_count = profiling.get("sample_count")
            if isinstance(sample_count, bool) or not isinstance(sample_count, int):
                raise MetadataDocumentError("profiling.sample_count 必须是整数")

        forbidden_column_keys = {
            "column_name",
            "character_maximum_length",
            "numeric_precision",
            "numeric_scale",
            "structure_flags",
            "role_specific_info",
        }
        forbidden_statistic_keys = {
            "sample_count",
            "mean",
            "avg_length",
            "min_length",
            "max_length",
            "median_length",
            "length_std",
        }
        for column_name, column in self.column_profiles.items():
            if not isinstance(column, dict):
                raise MetadataDocumentError(
                    f"column_profiles.{column_name} 必须是对象"
                )
            mixed_keys = forbidden_column_keys.intersection(column)
            if mixed_keys:
                raise MetadataDocumentError(
                    f"JSON v3 字段 {column_name} 混入 v2 属性: "
                    f"{', '.join(sorted(mixed_keys))}"
                )
            statistics = column.get("statistics")
            if statistics is not None:
                if not isinstance(statistics, dict):
                    raise MetadataDocumentError(
                        f"column_profiles.{column_name}.statistics 必须是对象"
                    )
                mixed_statistics = forbidden_statistic_keys.intersection(
                    statistics
                )
                if mixed_statistics:
                    raise MetadataDocumentError(
                        f"JSON v3 字段 {column_name}.statistics 混入可派生属性: "
                        f"{', '.join(sorted(mixed_statistics))}"
                    )

        profile = self.table_profile
        forbidden_profile_keys = {
            "column_statistics",
            "table_category_rule_based",
            "confidence_rule_based",
            "inference_basis_rule_based",
            "logical_keys",
        }
        mixed_profile_keys = forbidden_profile_keys.intersection(profile)
        if mixed_profile_keys:
            raise MetadataDocumentError(
                "JSON v3 table_profile 混入 v2 属性: "
                f"{', '.join(sorted(mixed_profile_keys))}"
            )
        sample_records = self.sample_records
        mixed_sample_keys = {"sample_size", "total_rows"}.intersection(
            sample_records
        )
        if mixed_sample_keys:
            raise MetadataDocumentError(
                "JSON v3 sample_records 混入可派生属性: "
                f"{', '.join(sorted(mixed_sample_keys))}"
            )
