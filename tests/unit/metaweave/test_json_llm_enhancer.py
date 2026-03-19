"""JsonLlmEnhancer 单元测试

测试 JsonLlmEnhancer 的核心功能：
- Token 优化（裁剪视图）
- 注释按需生成
- 分类覆盖逻辑
- 原子写入
"""

import json
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from metaweave.core.metadata.json_llm_enhancer import JsonLlmEnhancer


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
        "comment_generation": {
            "enabled": True,
            "language": "zh",
            "max_columns_per_call": 120,
            "enable_batch_processing": True,
            "overwrite_existing": False,
        },
    }


@pytest.fixture
def sample_table_json():
    """示例表 JSON（规则引擎输出）"""
    return {
        "metadata_version": "2.0",
        "generated_timestamp": "2025-12-26T00:00:00.000000",
        "table_info": {
            "schema_name": "public",
            "table_name": "test_table",
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


class TestTokenOptimization:
    """测试 Token 优化功能"""

    def test_build_llm_input_view_removes_noise_fields(self, sample_config, sample_table_json):
        """测试输入视图裁剪：移除规则推断字段"""
        enhancer = JsonLlmEnhancer(sample_config)
        llm_input = enhancer._build_llm_input_view(sample_table_json)

        # 验证保留了必要字段
        assert "table_info" in llm_input
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
        sample_config["comment_generation"]["overwrite_existing"] = True
        enhancer = JsonLlmEnhancer(sample_config)
        needs = enhancer._analyze_comment_needs(sample_table_json)

        # 覆盖模式：所有注释都需要生成
        assert needs["need_table_comment"] is True
        assert len(needs["columns_need_comment"]) == 2  # id 和 name 都需要

    def test_analyze_comment_needs_disabled(self, sample_config, sample_table_json):
        """测试注释生成禁用"""
        sample_config["comment_generation"]["enabled"] = False
        enhancer = JsonLlmEnhancer(sample_config)
        needs = enhancer._analyze_comment_needs(sample_table_json)

        # 禁用时不需要生成任何注释
        assert needs["need_table_comment"] is False
        assert len(needs["columns_need_comment"]) == 0


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
        assert enhanced["table_profile"]["table_category_rule_based"] == "dim"
        assert enhanced["table_profile"]["confidence_rule_based"] == 0.8
        assert "dim_name_pattern" in enhanced["table_profile"]["inference_basis_rule_based"]

    def test_merge_llm_result_consistent_classification(self, sample_config, sample_table_json):
        """测试 LLM 分类与规则引擎一致"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {
            "table_category": "dim",  # 与规则引擎一致
            "confidence": 0.95,
            "table_comment": "测试表",
            "column_comments": {},
        }

        enhanced = enhancer._merge_llm_result(sample_table_json, llm_result, need_comments=True)

        # 验证分类仍然覆盖（更新 confidence）
        assert enhanced["table_profile"]["table_category"] == "dim"
        assert enhanced["table_profile"]["confidence"] == 0.95  # 使用 LLM 的 confidence

        # 验证规则引擎结果备份
        assert enhanced["table_profile"]["table_category_rule_based"] == "dim"
        assert enhanced["table_profile"]["confidence_rule_based"] == 0.8

    def test_merge_llm_result_missing_table_category_raises(self, sample_config, sample_table_json):
        """测试 LLM 未返回 table_category 视为异常，不应落盘覆盖"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {
            "confidence": 0.95,
            "reason": "响应缺少 table_category",
        }

        with pytest.raises(ValueError):
            enhancer._merge_llm_result(sample_table_json, llm_result, need_comments=False)


class TestCommentMerging:
    """测试注释合并逻辑"""

    def test_merge_table_comment_missing(self, sample_config, sample_table_json):
        """测试补充缺失的表注释"""
        enhancer = JsonLlmEnhancer(sample_config)

        llm_result = {"table_comment": "这是一个测试表"}

        enhancer._merge_table_comment(sample_table_json, llm_result)

        assert sample_table_json["table_info"]["comment"] == "这是一个测试表"
        assert sample_table_json["table_info"]["comment_source"] == "llm_generated"

    def test_merge_table_comment_overwrite(self, sample_config, sample_table_json):
        """测试覆盖已有表注释"""
        sample_config["comment_generation"]["overwrite_existing"] = True
        sample_table_json["table_info"]["comment"] = "旧注释"
        sample_table_json["table_info"]["comment_source"] = "ddl"

        enhancer = JsonLlmEnhancer(sample_config)
        llm_result = {"table_comment": "新注释"}

        enhancer._merge_table_comment(sample_table_json, llm_result)

        # 验证覆盖
        assert sample_table_json["table_info"]["comment"] == "新注释"
        assert sample_table_json["table_info"]["comment_source"] == "llm_generated"

        # 验证备份
        assert sample_table_json["table_info"]["comment_original"] == "旧注释"
        assert sample_table_json["table_info"]["comment_source_original"] == "ddl"

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
