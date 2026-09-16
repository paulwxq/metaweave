"""JsonLlmEnhancer 单元测试

测试 JsonLlmEnhancer 的核心功能：
- Token 优化（裁剪视图）
- 注释按需生成
- 分类覆盖逻辑
- 原子写入
"""

import copy
import json
from typing import Dict
from unittest.mock import MagicMock

import pytest

from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer


def _as_v3(table_json: Dict) -> Dict:
    data = copy.deepcopy(table_json)
    data["metadata_version"] = "3.0"
    data["profiling"] = {"sample_method": "limit", "sample_count": 100}
    for column in data["column_profiles"].values():
        column.pop("column_name", None)
        column.pop("structure_flags", None)
        column.pop("role_specific_info", None)
        statistics = column.get("statistics", {})
        if "sample_count" in statistics and "null_rate" in statistics:
            statistics["null_count"] = round(
                statistics["sample_count"] * statistics["null_rate"]
            )
        statistics.pop("sample_count", None)
    table_profile = data["table_profile"]
    table_profile.pop("column_statistics", None)
    table_profile.pop("logical_keys", None)
    table_profile["classification_source"] = "rule"
    table_profile["unique_column_sets"] = []
    data["sample_records"] = {
        "sample_method": data["sample_records"]["sample_method"],
        "records": data["sample_records"]["records"],
    }
    return data


@pytest.fixture
def sample_config():
    """基础配置"""
    return {
        "llm": {
            "active": "qwen",
            "providers": {
                "qwen": {
                    "model": "qwen-plus",
                    "api_key": "mock-api-key-for-testing",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "temperature": 0.3,
                    "max_tokens": 500,
                    "timeout": 30
                }
            },
            "langchain_config": {
                "use_async": False,
                "batch_size": 10,
            }
        },
        "json_generation": {
            "comments": {
                "llm_enabled": True,
                "language": "zh",
                "max_columns_per_call": 120,
                "enable_batch_processing": True,
                "overwrite": False,
            },
            "table_classification": {"llm_enabled": True},
        },
    }


@pytest.fixture
def sample_table_json():
    """示例表 JSON（规则引擎输出）"""
    data = {
        "metadata_version": "3.0",
        "generated_timestamp": "2025-12-26T00:00:00.000000",
        "object_info": {
            "schema_name": "public",
            "object_name": "test_table",
            "comment": "",  # 缺失注释
            "comment_source": "",
        },
        "column_profiles": {
            "id": {
                "column_name": "id",
                "data_type": "integer",
                "is_nullable": False,
                "comment": "主键",  # 已有注释
                "comment_source": "ddl",
                "statistics": {
                    "sample_count": 100,
                    "unique_count": 100,
                    "null_rate": 0.0,
                    "uniqueness": 1.0,
                    "value_distribution": {"1": 1, "2": 1},
                },
                "structure_flags": {
                    "is_primary_key": True,
                    "is_nullable": False,
                },
                "semantic_analysis": {
                    "semantic_role": "identifier",
                    "semantic_confidence": 0.95,
                    "inference_basis": ["type_whitelist_passed"],
                },
                "role_specific_info": {
                    "identifier_info": {
                        "naming_pattern": "logical_primary_key",
                        "is_surrogate": True,
                    }
                },
            },
            "name": {
                "column_name": "name",
                "data_type": "varchar",
                "is_nullable": True,
                "comment": "",  # 缺失注释
                "comment_source": "",
                "statistics": {
                    "sample_count": 100,
                    "unique_count": 50,
                    "null_rate": 0.1,
                    "uniqueness": 0.5,
                    "value_distribution": {"Alice": 2, "Bob": 2},
                },
                "structure_flags": {
                    "is_primary_key": False,
                    "is_nullable": True,
                },
                "semantic_analysis": {
                    "semantic_role": "attribute",
                    "semantic_confidence": 0.7,
                    "inference_basis": ["fallback_attribute"],
                },
                "role_specific_info": {},
            },
        },
        "table_profile": {
            "table_category": "dim",  # 规则引擎分类
            "confidence": 0.8,
            "inference_basis": ["dim_name_pattern", "dim_has_primary_key"],
            "physical_constraints": {
                "primary_key": {"constraint_name": "pk_test", "columns": ["id"]},
                "foreign_keys": [],
                "unique_constraints": [],
                "indexes": [],
            },
            "column_statistics": {
                "total_columns": 2,
                "identifier_count": 1,
                "metric_count": 0,
                "datetime_count": 0,
                "enum_count": 0,
                "audit_count": 0,
                "attribute_count": 1,
                "primary_key_count": 1,
                "foreign_key_count": 0,
            },
            "logical_keys": {
                "candidate_primary_keys": [
                    {"columns": ["id"], "confidence_score": 1.0, "uniqueness": 1.0, "null_rate": 0.0}
                ]
            },
        },
        "sample_records": {
            "sample_method": "random",
            "sample_size": 3,
            "total_rows": 100,
            "records": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
                {"id": 3, "name": "Charlie"},
            ],
        },
    }
    return _as_v3(data)


class TestTokenOptimization:
    """测试 Token 优化功能"""

    def test_build_llm_input_view_removes_noise_fields(self, sample_config, sample_table_json):
        """测试输入视图裁剪：移除规则推断字段"""
        enhancer = JsonLlmEnhancer(sample_config)
        llm_input = enhancer._build_llm_input_view(sample_table_json)

        # 验证保留了必要字段
        assert "object_info" in llm_input
        assert llm_input["object_info"]["object_name"] == "test_table"
        assert "table_name" not in llm_input["object_info"]
        assert "column_profiles" in llm_input
        assert "sample_records" in llm_input
        assert "physical_constraints" in llm_input

        # 验证移除了规则推断字段
        assert "logical_keys" not in llm_input.get("table_profile", {})

        # 验证列画像简化
        for col_name, col_data in llm_input["column_profiles"].items():
            assert "column_name" in col_data
            assert "data_type" in col_data
            assert "statistics" in col_data
            # 不应包含规则推断字段
            assert "semantic_analysis" not in col_data
            assert "role_specific_info" not in col_data

    def test_simplify_column_statistics(self, sample_config, sample_table_json):
        """测试列统计简化"""
        enhancer = JsonLlmEnhancer(sample_config)
        llm_input = enhancer._build_llm_input_view(sample_table_json)

        id_stats = llm_input["column_profiles"]["id"]["statistics"]

        # 验证保留关键统计
        assert "sample_count" in id_stats
        assert "unique_count" in id_stats
        assert "null_rate" in id_stats
        assert "uniqueness" in id_stats
        assert "value_distribution" in id_stats

    def test_limit_value_distribution(self, sample_config):
        """测试值分布限制"""
        enhancer = JsonLlmEnhancer(sample_config)

        # 模拟大量值分布
        large_dist = {f"value_{i}": i for i in range(100)}
        limited = enhancer._limit_value_distribution(large_dist, top_k=10)

        assert len(limited) == 10
        # 验证保留的是频次最高的
        assert all(v >= 90 for v in limited.values())


class TestCommentNeedsAnalysis:
    """测试注释需求分析"""

    def test_analyze_comment_needs_detects_missing(self, sample_config, sample_table_json):
        """测试检测缺失注释"""
        enhancer = JsonLlmEnhancer(sample_config)
        needs = enhancer._analyze_comment_needs(sample_table_json)

        # 表注释缺失
        assert needs["need_table_comment"] is True

        # 列注释：id 有注释，name 缺失
        assert "name" in needs["columns_need_comment"]
        assert "id" not in needs["columns_need_comment"]

    def test_analyze_comment_needs_with_overwrite(self, sample_config, sample_table_json):
        """测试覆盖模式"""
        sample_config["json_generation"]["comments"]["overwrite"] = True
        enhancer = JsonLlmEnhancer(sample_config)
        needs = enhancer._analyze_comment_needs(sample_table_json)

        # 覆盖模式：所有注释都需要生成
        assert needs["need_table_comment"] is True
        assert len(needs["columns_need_comment"]) == 2  # id 和 name 都需要

    def test_analyze_comment_needs_disabled(self, sample_config, sample_table_json):
        """测试注释生成禁用"""
        sample_config["json_generation"]["comments"]["llm_enabled"] = False
        enhancer = JsonLlmEnhancer(sample_config)
        needs = enhancer._analyze_comment_needs(sample_table_json)

        # 禁用时不需要生成任何注释
        assert needs["need_table_comment"] is False
        assert len(needs["columns_need_comment"]) == 0


class TestEnhanceDocumentSwitches:
    def _service(self, response: str):
        service = MagicMock(model="test-model")
        service.call_llm.return_value = response
        return service

    def test_both_switches_disabled_do_not_initialize_llm(
        self, sample_config, sample_table_json
    ):
        sample_config["json_generation"]["comments"]["llm_enabled"] = False
        sample_config["json_generation"]["table_classification"][
            "llm_enabled"
        ] = False
        enhancer = JsonLlmEnhancer(sample_config)
        original = _as_v3(sample_table_json)

        outcome = enhancer.enhance_document(original)

        assert outcome.success is True
        assert outcome.llm_called is False
        assert outcome.request_count == 0
        assert enhancer.llm_service is None
        assert outcome.document == original

    def test_both_switches_disabled_do_not_require_llm_config(
        self, sample_table_json
    ):
        config = {
            "json_generation": {
                "comments": {"llm_enabled": False},
                "table_classification": {"llm_enabled": False},
            }
        }
        enhancer = JsonLlmEnhancer(config)

        outcome = enhancer.enhance_document(_as_v3(sample_table_json))

        assert outcome.success is True
        assert outcome.llm_called is False
        assert enhancer.llm_service is None

    def test_legacy_llm_timestamp_is_removed_without_llm(
        self, sample_config, sample_table_json
    ):
        sample_config["json_generation"]["comments"]["llm_enabled"] = False
        sample_config["json_generation"]["table_classification"]["llm_enabled"] = False
        original = _as_v3(sample_table_json)
        original["llm_enhanced_at"] = "2025-12-26T01:00:00"

        outcome = JsonLlmEnhancer(sample_config).enhance_document(original)

        assert outcome.success is True
        assert outcome.llm_called is False
        assert "llm_enhanced_at" not in outcome.document
        assert outcome.document["generated_timestamp"] == original["generated_timestamp"]
        assert "llm_enhanced_at" in original

    def test_legacy_comment_audit_fields_are_removed_without_llm(
        self, sample_config, sample_table_json
    ):
        sample_config["json_generation"]["comments"]["llm_enabled"] = False
        sample_config["json_generation"]["table_classification"]["llm_enabled"] = False
        original = _as_v3(sample_table_json)
        original["object_info"].update(
            comment="原对象注释",
            comment_original="旧对象注释",
            comment_source_original="ddl",
        )
        original["column_profiles"]["id"].update(
            comment_original="旧字段注释",
            comment_source_original="ddl",
        )

        outcome = JsonLlmEnhancer(sample_config).enhance_document(original)

        assert outcome.success is True
        assert outcome.llm_called is False
        assert "comment_original" not in outcome.document["object_info"]
        assert "comment_source_original" not in outcome.document["object_info"]
        assert "comment_original" not in outcome.document["column_profiles"]["id"]
        assert "comment_source_original" not in outcome.document["column_profiles"]["id"]
        assert "comment_original" in original["object_info"]

    def test_incremental_mode_removes_legacy_audit_fields(
        self, sample_config, sample_table_json
    ):
        sample_config["json_generation"]["table_classification"]["llm_enabled"] = False
        original = _as_v3(sample_table_json)
        original["object_info"].update(
            comment="已有对象注释",
            comment_original="旧对象注释",
            comment_source_original="ddl",
        )
        original["column_profiles"]["id"].update(
            comment_original="旧字段注释",
            comment_source_original="ddl",
        )
        enhancer = JsonLlmEnhancer(sample_config)
        enhancer.llm_service = self._service(
            '{"column_comments":{"name":"新名称注释"}}'
        )

        outcome = enhancer.enhance_document(original)

        assert outcome.success is True
        assert outcome.document["object_info"]["comment"] == "已有对象注释"
        assert outcome.document["column_profiles"]["id"]["comment"] == "主键"
        assert outcome.document["column_profiles"]["name"]["comment"] == "新名称注释"
        for item in (
            outcome.document["object_info"],
            outcome.document["column_profiles"]["id"],
            outcome.document["column_profiles"]["name"],
        ):
            assert "comment_original" not in item
            assert "comment_source_original" not in item

    def test_comments_only_preserves_rule_classification(
        self, sample_config, sample_table_json
    ):
        sample_config["json_generation"]["table_classification"][
            "llm_enabled"
        ] = False
        enhancer = JsonLlmEnhancer(sample_config)
        enhancer.llm_service = self._service(
            json.dumps(
                {
                    "table_comment": "测试对象",
                    "column_comments": {"name": "名称"},
                },
                ensure_ascii=False,
            )
        )

        outcome = enhancer.enhance_document(_as_v3(sample_table_json))

        assert outcome.success is True
        assert outcome.comment_task_succeeded is True
        assert outcome.classification_task_attempted is False
        assert outcome.document["table_profile"]["classification_source"] == "rule"
        assert outcome.document["object_info"]["comment"] == "测试对象"

    def test_classification_only_does_not_generate_comments(
        self, sample_config, sample_table_json
    ):
        sample_config["json_generation"]["comments"]["llm_enabled"] = False
        enhancer = JsonLlmEnhancer(sample_config)
        enhancer.llm_service = self._service(
            json.dumps(
                {
                    "table_category": "fact",
                    "confidence": 0.9,
                    "reason": "包含事实指标",
                },
                ensure_ascii=False,
            )
        )

        outcome = enhancer.enhance_document(_as_v3(sample_table_json))

        assert outcome.success is True
        assert outcome.comment_task_attempted is False
        assert outcome.classification_task_succeeded is True
        assert outcome.document["table_profile"]["table_category"] == "fact"
        assert outcome.document["object_info"]["comment"] == ""

    def test_combined_partial_failure_keeps_successful_items_without_retry(
        self, sample_config, sample_table_json
    ):
        enhancer = JsonLlmEnhancer(sample_config)
        enhancer.llm_service = self._service(
            json.dumps(
                {
                    "table_category": "fact",
                    "confidence": 0.9,
                    "reason": "包含事实指标",
                    "table_comment": "测试对象",
                },
                ensure_ascii=False,
            )
        )
        original = _as_v3(sample_table_json)

        outcome = enhancer.enhance_document(original)

        assert outcome.success is False
        assert outcome.request_count == 1
        assert enhancer.llm_service.call_llm.call_count == 1
        assert outcome.classification_task_succeeded is True
        assert outcome.object_comment_success_count == 1
        assert outcome.column_comment_failure_count == 1
        assert outcome.document["table_profile"]["table_category"] == "fact"
        assert outcome.document["object_info"]["comment"] == "测试对象"
        assert "llm_enhanced_at" not in outcome.document
        assert "generated_timestamp" in outcome.document
        assert outcome.document["column_profiles"]["name"]["comment"] == ""

    def test_combined_success_uses_one_request_and_merges_both_tasks(
        self, sample_config, sample_table_json
    ):
        enhancer = JsonLlmEnhancer(sample_config)
        enhancer.llm_service = self._service(
            json.dumps(
                {
                    "table_category": "fact",
                    "confidence": 0.91,
                    "reason": "包含事实指标",
                    "table_comment": "测试对象",
                    "column_comments": {"name": "名称"},
                },
                ensure_ascii=False,
            )
        )

        outcome = enhancer.enhance_document(_as_v3(sample_table_json))

        assert outcome.success is True
        assert outcome.request_count == 1
        assert outcome.comment_task_succeeded is True
        assert outcome.classification_task_succeeded is True
        assert outcome.document["table_profile"]["table_category"] == "fact"
        assert outcome.document["object_info"]["comment"] == "测试对象"

    def test_overwrite_mode_clears_failed_items_and_keeps_partial_success(
        self, sample_config, sample_table_json
    ):
        sample_config["json_generation"]["comments"]["overwrite"] = True
        sample_table_json["object_info"]["comment"] = "DDL 对象注释"
        enhancer = JsonLlmEnhancer(sample_config)
        enhancer.llm_service = self._service(
            json.dumps(
                {
                    "table_category": "fact",
                    "confidence": 0.91,
                    "reason": "包含事实指标",
                    "table_comment": "  ",
                    "column_comments": {"name": " 刷新后的名称 "},
                },
                ensure_ascii=False,
            )
        )

        outcome = enhancer.enhance_document(_as_v3(sample_table_json))

        assert outcome.success is False
        assert outcome.object_comment_failure_count == 1
        assert outcome.column_comment_success_count == 1
        assert outcome.column_comment_failure_count == 1
        assert outcome.document["object_info"]["comment"] == ""
        assert outcome.document["column_profiles"]["id"]["comment"] == ""
        assert outcome.document["column_profiles"]["name"]["comment"] == "刷新后的名称"
        assert "comment_original" not in outcome.document["object_info"]


class TestClassificationOverride:
    """测试分类覆盖逻辑"""

    def test_merge_llm_result_overrides_classification(self, sample_config, sample_table_json):
        """测试 LLM 分类覆盖规则引擎"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {
            "table_category": "fact",  # LLM 分类为 fact（与规则引擎 dim 不同）
            "confidence": 0.95,
            "reason": "包含度量字段",
            "table_comment": "测试表",
            "column_comments": {"name": "名称字段"},
        }

        enhanced = enhancer._merge_llm_result(sample_table_json, llm_result, need_comments=True)

        # 验证分类覆盖
        assert enhanced["table_profile"]["table_category"] == "fact"
        assert enhanced["table_profile"]["confidence"] == 0.95
        assert enhanced["table_profile"]["inference_basis"] == ["llm_inferred"]

        # 验证规则引擎结果备份
        rule = enhanced["table_profile"]["rule_based_classification"]
        assert rule["table_category"] == "dim"
        assert rule["confidence"] == 0.8
        assert "dim_name_pattern" in rule["inference_basis"]

    def test_merge_llm_result_consistent_classification(self, sample_config, sample_table_json):
        """测试 LLM 分类与规则引擎一致"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {
            "table_category": "dim",  # 与规则引擎一致
            "confidence": 0.95,
            "reason": "维度属性为主",
            "table_comment": "测试表",
            "column_comments": {},
        }

        enhanced = enhancer._merge_llm_result(sample_table_json, llm_result, need_comments=True)

        # 验证分类仍然覆盖（更新 confidence）
        assert enhanced["table_profile"]["table_category"] == "dim"
        assert enhanced["table_profile"]["confidence"] == 0.95  # 使用 LLM 的 confidence

        # 验证规则引擎结果备份
        rule = enhanced["table_profile"]["rule_based_classification"]
        assert rule["table_category"] == "dim"
        assert rule["confidence"] == 0.8

    def test_merge_llm_result_missing_table_category_raises(self, sample_config, sample_table_json):
        """测试 LLM 未返回 table_category 视为异常，不应落盘覆盖"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {
            "confidence": 0.95,
            "reason": "响应缺少 table_category",
        }

        with pytest.raises(ValueError):
            enhancer._merge_llm_result(sample_table_json, llm_result, need_comments=False)

    def test_v3_merge_records_source_reason_and_original_rule_once(
        self,
        sample_config,
        sample_table_json,
    ):
        enhancer = JsonLlmEnhancer(sample_config)
        original = _as_v3(sample_table_json)

        first = enhancer._merge_llm_result(
            original,
            {
                "table_category": "fact",
                "confidence": 0.95,
                "reason": "包含业务度量和事件记录",
            },
            need_comments=False,
        )
        second = enhancer._merge_llm_result(
            first,
            {
                "table_category": "bridge",
                "confidence": 0.85,
                "reason": "第二次分类判断",
            },
            need_comments=False,
        )

        profile = second["table_profile"]
        assert second["metadata_version"] == "3.0"
        assert profile["classification_source"] == "llm"
        assert profile["classification_reason"] == "第二次分类判断"
        assert profile["rule_based_classification"] == {
            "table_category": "dim",
            "confidence": 0.8,
            "inference_basis": ["dim_name_pattern", "dim_has_primary_key"],
        }

    def test_v3_merge_requires_nonempty_reason(
        self,
        sample_config,
        sample_table_json,
    ):
        enhancer = JsonLlmEnhancer(sample_config)
        with pytest.raises(ValueError, match="reason"):
            enhancer._merge_llm_result(
                _as_v3(sample_table_json),
                {"table_category": "fact", "confidence": 0.9},
                need_comments=False,
            )

    def test_v3_llm_input_uses_facts_and_omits_unknown_statistics(
        self,
        sample_config,
        sample_table_json,
    ):
        data = _as_v3(sample_table_json)
        data["column_profiles"]["name"].pop("statistics")
        enhancer = JsonLlmEnhancer(sample_config)

        llm_input = enhancer._build_llm_input_view(data)

        id_column = llm_input["column_profiles"]["id"]
        assert id_column["constraints"] == ["primary_key"]
        assert id_column["statistics"]["sample_count"] == 100
        assert id_column["statistics"]["null_rate"] == 0.0
        assert id_column["statistics"]["uniqueness"] == 1.0
        assert "structure_flags" not in id_column
        assert "statistics" not in llm_input["column_profiles"]["name"]
        assert set(llm_input["sample_records"]) == {"sample_method", "records"}

    def test_failed_v3_enhancement_keeps_file_byte_for_byte(
        self,
        sample_config,
        sample_table_json,
        tmp_path,
    ):
        enhancer = JsonLlmEnhancer(sample_config)
        enhancer.llm_service = MagicMock(model="test-model")
        enhancer.llm_service.call_llm = MagicMock(
            return_value='{"table_category":"fact","confidence":0.9}'
        )
        path = tmp_path / "table.json"
        original_text = json.dumps(
            _as_v3(sample_table_json),
            ensure_ascii=False,
            indent=4,
        )
        path.write_text(original_text, encoding="utf-8")

        assert enhancer.enhance_json_files([path]) == 0
        assert path.read_text(encoding="utf-8") == original_text

    def test_file_entry_removes_legacy_llm_timestamp_without_llm(
        self, sample_config, sample_table_json, tmp_path
    ):
        sample_config["json_generation"]["comments"]["llm_enabled"] = False
        sample_config["json_generation"]["table_classification"]["llm_enabled"] = False
        data = _as_v3(sample_table_json)
        data["llm_enhanced_at"] = "2025-12-26T01:00:00"
        path = tmp_path / "table.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        enhancer = JsonLlmEnhancer(sample_config)
        assert enhancer.enhance_json_files([path]) == 0

        saved = json.loads(path.read_text(encoding="utf-8"))
        assert "llm_enhanced_at" not in saved
        assert saved["generated_timestamp"] == data["generated_timestamp"]

    def test_timestamp_option_removes_transition_timestamps(
        self,
        sample_config,
        sample_table_json,
    ):
        sample_config["output"] = {
            "json_options": {"include_generation_timestamps": False}
        }
        enhancer = JsonLlmEnhancer(sample_config)
        data = _as_v3(sample_table_json)

        enhanced = enhancer._merge_llm_result(
            data,
            {
                "table_category": "fact",
                "confidence": 0.9,
                "reason": "事实表",
            },
            need_comments=False,
        )

        assert "generated_timestamp" not in enhanced
        assert "llm_enhanced_at" not in enhanced


class TestCommentMerging:
    """测试注释合并逻辑"""

    def test_merge_table_comment_missing(self, sample_config, sample_table_json):
        """测试补充缺失的表注释"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {"table_comment": "这是一个测试表"}

        enhancer._merge_table_comment(sample_table_json, llm_result)

        assert sample_table_json["object_info"]["comment"] == "这是一个测试表"
        assert sample_table_json["object_info"]["comment_source"] == "llm_generated"

    def test_merge_table_comment_overwrite(self, sample_config, sample_table_json):
        """测试覆盖已有表注释"""
        sample_config["json_generation"]["comments"]["overwrite"] = True
        sample_table_json["object_info"]["comment"] = "旧注释"
        sample_table_json["object_info"]["comment_source"] = "ddl"

        enhancer = JsonLlmEnhancer(sample_config)
        llm_result = {"table_comment": "新注释"}

        enhancer._merge_table_comment(sample_table_json, llm_result)

        # 验证覆盖
        assert sample_table_json["object_info"]["comment"] == "新注释"
        assert sample_table_json["object_info"]["comment_source"] == "llm_generated"

        # 覆盖模式直接替换，不保留旧注释审计副本。
        assert "comment_original" not in sample_table_json["object_info"]
        assert "comment_source_original" not in sample_table_json["object_info"]

    def test_merge_column_comments(self, sample_config, sample_table_json):
        """测试字段注释合并"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {"column_comments": {"name": "用户姓名"}}

        enhancer._merge_column_comments(sample_table_json, llm_result)

        # id 已有注释，不变
        assert sample_table_json["column_profiles"]["id"]["comment"] == "主键"

        # name 缺失注释，补充
        assert sample_table_json["column_profiles"]["name"]["comment"] == "用户姓名"
        assert sample_table_json["column_profiles"]["name"]["comment_source"] == "llm_generated"


class TestAtomicWrite:
    """测试原子写入"""

    def test_atomic_write_json_success(self, sample_config, tmp_path):
        """测试原子写入成功"""
        enhancer = JsonLlmEnhancer(sample_config)

        test_file = tmp_path / "test.json"
        test_data = {"test": "data"}

        enhancer._atomic_write_json(test_file, test_data)

        # 验证文件存在
        assert test_file.exists()

        # 验证内容正确
        with open(test_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data == test_data

        # 验证临时文件已清理
        temp_file = test_file.with_suffix(".tmp")
        assert not temp_file.exists()

    def test_atomic_write_preserves_original_on_error(self, sample_config, tmp_path):
        """测试写入失败时保留原文件"""
        enhancer = JsonLlmEnhancer(sample_config)

        test_file = tmp_path / "test.json"
        original_data = {"original": "data"}

        # 先写入原始数据
        with open(test_file, "w", encoding="utf-8") as f:
            json.dump(original_data, f)

        # 模拟写入错误（使用不可序列化的对象）
        bad_data = {"bad": object()}

        with pytest.raises(TypeError):
            enhancer._atomic_write_json(test_file, bad_data)

        # 验证原文件未损坏
        with open(test_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data == original_data


class TestLLMResponseParsing:
    """测试 LLM 响应解析"""

    def test_parse_llm_response_valid_json(self, sample_config):
        """测试解析有效的 JSON 响应"""
        enhancer = JsonLlmEnhancer(sample_config)

        response = '{"table_category": "dim", "confidence": 0.95}'
        result = enhancer._parse_llm_response(response, "test_table")

        assert result["table_category"] == "dim"
        assert result["confidence"] == 0.95

    def test_parse_llm_response_with_markdown(self, sample_config):
        """测试解析带 markdown 的响应"""
        enhancer = JsonLlmEnhancer(sample_config)

        response = '```json\n{"table_category": "fact", "confidence": 0.9}\n```'
        result = enhancer._parse_llm_response(response, "test_table")

        assert result["table_category"] == "fact"
        assert result["confidence"] == 0.9

    def test_parse_llm_response_invalid_json(self, sample_config):
        """测试解析无效的 JSON"""
        enhancer = JsonLlmEnhancer(sample_config)

        response = "这不是 JSON"
        result = enhancer._parse_llm_response(response, "test_table")

        # 解析失败返回空字典
        assert result == {}

    def test_parse_llm_response_with_extra_text(self, sample_config):
        """测试解析包含额外文本的响应"""
        enhancer = JsonLlmEnhancer(sample_config)

        response = '根据分析，这是一个维度表。\n{"table_category": "dim", "confidence": 0.95}\n以上是我的判断。'
        result = enhancer._parse_llm_response(response, "test_table")

        assert result["table_category"] == "dim"
        assert result["confidence"] == 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
