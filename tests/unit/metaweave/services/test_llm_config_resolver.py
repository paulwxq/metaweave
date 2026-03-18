"""LLM 配置解析器单元测试

覆盖以下函数：
- deep_merge_dict
- _validate_declared_module_llm_paths
- _validate_nonstandard_llm_paths
- _validate_override_llm_dict
- _validate_final_llm_config
- resolve_module_llm_config
"""

import pytest

from metaweave.services.llm_config_resolver import (
    SUPPORTED_MODULE_LLM_PATHS,
    _validate_declared_module_llm_paths,
    _validate_final_llm_config,
    _validate_nonstandard_llm_paths,
    _validate_override_llm_dict,
    deep_merge_dict,
    resolve_module_llm_config,
)


# ===========================================================================
# 公共 fixture
# ===========================================================================

def _base_config(active="qwen", model="qwen-plus", extra_providers=None):
    """构造一个合法的完整配置字典"""
    providers = {
        "qwen": {"model": model, "api_key": "key-qwen", "api_base": "http://qwen"},
        "deepseek": {"model": "deepseek-chat", "api_key": "key-ds", "api_base": "http://ds"},
    }
    if extra_providers:
        providers.update(extra_providers)
    return {
        "llm": {
            "active": active,
            "batch_size": 10,
            "retry_times": 2,
            "retry_delay": 2,
            "langchain_config": {
                "use_async": True,
                "async_concurrency": 10,
            },
            "providers": providers,
        }
    }


# ===========================================================================
# deep_merge_dict
# ===========================================================================

class TestDeepMergeDict:

    def test_scalar_override(self):
        result = deep_merge_dict({"a": 1, "b": 2}, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_new_key_appended(self):
        result = deep_merge_dict({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_dict_recursive_merge(self):
        base = {"providers": {"qwen": {"model": "qwen-plus", "timeout": 60}}}
        override = {"providers": {"qwen": {"model": "qwen-max"}}}
        result = deep_merge_dict(base, override)
        assert result["providers"]["qwen"]["model"] == "qwen-max"
        assert result["providers"]["qwen"]["timeout"] == 60  # 保留未覆盖字段

    def test_list_replaced_not_merged(self):
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge_dict(base, override)
        assert result["items"] == [4, 5]

    def test_does_not_mutate_base(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        deep_merge_dict(base, override)
        assert "c" not in base["a"]

    def test_extra_params_deep_merge(self):
        base = {"providers": {"qwen": {"extra_params": {"enable_thinking": False, "streaming": False}}}}
        override = {"providers": {"qwen": {"extra_params": {"enable_thinking": True}}}}
        result = deep_merge_dict(base, override)
        ep = result["providers"]["qwen"]["extra_params"]
        assert ep["enable_thinking"] is True
        assert ep["streaming"] is False

    def test_langchain_config_partial_override(self):
        base = {"langchain_config": {"use_async": True, "async_concurrency": 10}}
        override = {"langchain_config": {"async_concurrency": 4}}
        result = deep_merge_dict(base, override)
        assert result["langchain_config"]["use_async"] is True
        assert result["langchain_config"]["async_concurrency"] == 4


# ===========================================================================
# _validate_declared_module_llm_paths
# ===========================================================================

class TestValidateDeclaredModuleLlmPaths:

    def test_no_module_llm_declared_passes(self):
        config = _base_config()
        _validate_declared_module_llm_paths(config)  # 不报错

    def test_supported_path_passes(self):
        config = _base_config()
        config["domain_generation"] = {"llm": {"active": "deepseek"}}
        _validate_declared_module_llm_paths(config)  # 不报错

    def test_unsupported_sql_rag_llm_raises(self):
        config = _base_config()
        config["sql_rag"] = {"llm": {"active": "deepseek"}}
        with pytest.raises(ValueError, match="sql_rag.llm"):
            _validate_declared_module_llm_paths(config)

    def test_unsupported_relationships_llm_raises(self):
        config = _base_config()
        config["relationships"] = {"llm": {"active": "deepseek"}}
        with pytest.raises(ValueError, match="relationships.llm"):
            _validate_declared_module_llm_paths(config)

    def test_error_message_contains_supported_paths(self):
        config = _base_config()
        config["json_llm"] = {"llm": {"active": "qwen"}}
        with pytest.raises(ValueError, match="domain_generation.llm"):
            _validate_declared_module_llm_paths(config)

    def test_module_without_llm_key_passes(self):
        config = _base_config()
        config["sql_rag"] = {"generation": {"max_retries": 3}}  # 无 llm 子键
        _validate_declared_module_llm_paths(config)  # 不报错


# ===========================================================================
# _validate_nonstandard_llm_paths
# ===========================================================================

class TestValidateNonstandardLlmPaths:

    def test_clean_config_passes(self):
        config = _base_config()
        _validate_nonstandard_llm_paths(config)  # 不报错

    def test_sql_rag_generation_llm_raises(self):
        config = _base_config()
        config["sql_rag"] = {"generation": {"llm": {"active": "qwen"}}}
        with pytest.raises(ValueError, match="sql_rag.generation.llm"):
            _validate_nonstandard_llm_paths(config)

    def test_relationships_rel_llm_llm_raises(self):
        config = _base_config()
        config["relationships"] = {"rel_llm": {"llm": {"active": "qwen"}}}
        with pytest.raises(ValueError, match="relationships.rel_llm.llm"):
            _validate_nonstandard_llm_paths(config)


# ===========================================================================
# _validate_override_llm_dict
# ===========================================================================

class TestValidateOverrideLlmDict:

    def test_valid_active_override_passes(self):
        _validate_override_llm_dict({"active": "deepseek"}, "test.llm")

    def test_valid_providers_override_passes(self):
        _validate_override_llm_dict(
            {"providers": {"qwen": {"model": "qwen-max"}}}, "test.llm"
        )

    def test_valid_langchain_config_override_passes(self):
        _validate_override_llm_dict(
            {"langchain_config": {"use_async": False}}, "test.llm"
        )

    def test_illegal_model_name_raises(self):
        with pytest.raises(ValueError, match="model_name"):
            _validate_override_llm_dict({"model_name": "qwen-max"}, "domain_generation.llm")

    def test_illegal_provider_raises(self):
        with pytest.raises(ValueError, match="provider"):
            _validate_override_llm_dict({"provider": "openai"}, "domain_generation.llm")

    def test_illegal_temperature_at_top_raises(self):
        with pytest.raises(ValueError, match="temperature"):
            _validate_override_llm_dict({"temperature": 0.5}, "domain_generation.llm")

    def test_illegal_timeout_at_top_raises(self):
        with pytest.raises(ValueError, match="timeout"):
            _validate_override_llm_dict({"timeout": 120}, "domain_generation.llm")

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="unknown_field"):
            _validate_override_llm_dict({"unknown_field": "xxx"}, "test.llm")

    def test_error_contains_full_path(self):
        with pytest.raises(ValueError, match="domain_generation.llm.model_name"):
            _validate_override_llm_dict({"model_name": "x"}, "domain_generation.llm")

    def test_providers_with_timeout_inside_passes(self):
        """providers.<provider>.timeout 是合法写法，不应报错"""
        _validate_override_llm_dict(
            {"providers": {"qwen": {"timeout": 120}}}, "test.llm"
        )


# ===========================================================================
# _validate_final_llm_config
# ===========================================================================

class TestValidateFinalLlmConfig:

    def _valid(self):
        return {
            "active": "qwen",
            "providers": {"qwen": {"model": "qwen-plus"}},
        }

    def test_valid_config_passes(self):
        _validate_final_llm_config(self._valid())

    def test_missing_active_raises(self):
        cfg = self._valid()
        del cfg["active"]
        with pytest.raises(ValueError, match="active"):
            _validate_final_llm_config(cfg)

    def test_missing_providers_raises(self):
        cfg = self._valid()
        del cfg["providers"]
        with pytest.raises(ValueError, match="providers"):
            _validate_final_llm_config(cfg)

    def test_active_not_in_providers_raises(self):
        cfg = self._valid()
        cfg["active"] = "deepseek"
        with pytest.raises(ValueError, match="deepseek"):
            _validate_final_llm_config(cfg)

    def test_missing_model_raises(self):
        cfg = self._valid()
        cfg["providers"]["qwen"] = {"api_key": "xxx"}  # 无 model
        with pytest.raises(ValueError, match="model"):
            _validate_final_llm_config(cfg)


# ===========================================================================
# resolve_module_llm_config
# ===========================================================================

class TestResolveModuleLlmConfig:

    def test_no_override_returns_global_llm(self):
        config = _base_config()
        result = resolve_module_llm_config(config)
        assert result["active"] == "qwen"
        assert result["providers"]["qwen"]["model"] == "qwen-plus"

    def test_override_path_not_present_falls_back_to_global(self):
        config = _base_config()
        # domain_generation 不存在，回退到全局
        result = resolve_module_llm_config(config, "domain_generation.llm")
        assert result["active"] == "qwen"

    def test_override_active_via_path(self):
        config = _base_config()
        config["domain_generation"] = {"llm": {"active": "deepseek"}}
        result = resolve_module_llm_config(config, "domain_generation.llm")
        assert result["active"] == "deepseek"
        # providers 不丢失
        assert "qwen" in result["providers"]
        assert "deepseek" in result["providers"]

    def test_deep_merge_providers_model(self):
        """providers.qwen.model 覆盖，其他字段保留"""
        config = _base_config()
        config["domain_generation"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        result = resolve_module_llm_config(config, "domain_generation.llm")
        assert result["providers"]["qwen"]["model"] == "qwen-max"
        assert result["providers"]["qwen"]["api_key"] == "key-qwen"  # 保留

    def test_deep_merge_langchain_config_partial(self):
        """langchain_config 部分覆盖"""
        config = _base_config()
        config["domain_generation"] = {
            "llm": {"langchain_config": {"async_concurrency": 4}}
        }
        result = resolve_module_llm_config(config, "domain_generation.llm")
        assert result["langchain_config"]["async_concurrency"] == 4
        assert result["langchain_config"]["use_async"] is True  # 保留

    def test_runtime_override_has_highest_priority(self):
        config = _base_config()
        config["domain_generation"] = {"llm": {"active": "deepseek"}}
        result = resolve_module_llm_config(
            config,
            "domain_generation.llm",
            runtime_override={"langchain_config": {"use_async": False}},
        )
        assert result["active"] == "deepseek"
        assert result["langchain_config"]["use_async"] is False

    def test_override_path_and_dict_both_raises(self):
        config = _base_config()
        with pytest.raises(ValueError, match="不可同时传入"):
            resolve_module_llm_config(
                config,
                override_path="domain_generation.llm",
                override_dict={"active": "deepseek"},
            )

    def test_illegal_field_in_override_raises(self):
        config = _base_config()
        config["domain_generation"] = {"llm": {"model_name": "qwen-max"}}
        with pytest.raises(ValueError, match="model_name"):
            resolve_module_llm_config(config, "domain_generation.llm")

    def test_illegal_field_in_runtime_override_raises(self):
        config = _base_config()
        with pytest.raises(ValueError, match="provider"):
            resolve_module_llm_config(
                config,
                runtime_override={"provider": "openai"},
            )

    def test_override_dict_mode(self):
        config = _base_config()
        result = resolve_module_llm_config(
            config,
            override_dict={"active": "deepseek"},
        )
        assert result["active"] == "deepseek"

    def test_final_validation_fails_if_active_provider_missing(self):
        """模块覆盖切换到不存在的 provider 时，最终校验应报错"""
        config = _base_config()
        config["domain_generation"] = {"llm": {"active": "nonexistent"}}
        with pytest.raises(ValueError, match="nonexistent"):
            resolve_module_llm_config(config, "domain_generation.llm")
