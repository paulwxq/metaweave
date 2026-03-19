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

    def test_supported_sql_rag_llm_passes(self):
        """sql_rag.llm 已接入白名单，不应报错"""
        config = _base_config()
        config["sql_rag"] = {"llm": {"active": "deepseek"}}
        _validate_declared_module_llm_paths(config)  # 不报错

    def test_supported_relationships_llm_passes(self):
        """relationships.llm 已接入白名单（Phase 3），不应报错"""
        config = _base_config()
        config["relationships"] = {"llm": {"active": "deepseek"}}
        _validate_declared_module_llm_paths(config)  # 不报错

    def test_supported_json_llm_llm_passes(self):
        """json_llm.llm 已接入白名单（Phase 3），不应报错"""
        config = _base_config()
        config["json_llm"] = {"llm": {"active": "qwen"}}
        _validate_declared_module_llm_paths(config)  # 不报错

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

    # --- 第二阶段：sql_rag.llm 支持 ---

    def test_sql_rag_llm_override_active(self):
        config = _base_config()
        config["sql_rag"] = {"llm": {"active": "deepseek"}}
        result = resolve_module_llm_config(config, "sql_rag.llm")
        assert result["active"] == "deepseek"
        assert "qwen" in result["providers"]
        assert "deepseek" in result["providers"]

    def test_sql_rag_llm_deep_merge_provider_model(self):
        config = _base_config()
        config["sql_rag"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        result = resolve_module_llm_config(config, "sql_rag.llm")
        assert result["providers"]["qwen"]["model"] == "qwen-max"
        assert result["providers"]["qwen"]["api_key"] == "key-qwen"

    def test_sql_rag_llm_deep_merge_timeout(self):
        """sql_rag.llm 覆盖 provider timeout"""
        config = _base_config()
        config["sql_rag"] = {
            "llm": {"providers": {"qwen": {"timeout": 120}}}
        }
        result = resolve_module_llm_config(config, "sql_rag.llm")
        assert result["providers"]["qwen"]["timeout"] == 120
        assert result["providers"]["qwen"]["model"] == "qwen-plus"

    def test_sql_rag_no_llm_inherits_global(self):
        """不配置 sql_rag.llm 时完全继承全局"""
        config = _base_config()
        config["sql_rag"] = {"generation": {"max_retries": 3}}
        result = resolve_module_llm_config(config, "sql_rag.llm")
        assert result["active"] == "qwen"
        assert result["providers"]["qwen"]["model"] == "qwen-plus"

    def test_sql_rag_llm_does_not_affect_domain_generation(self):
        """sql_rag.llm 不影响 domain_generation"""
        config = _base_config()
        config["sql_rag"] = {"llm": {"active": "deepseek"}}
        config["domain_generation"] = {"llm": {"providers": {"qwen": {"model": "qwen-max"}}}}
        sql_result = resolve_module_llm_config(config, "sql_rag.llm")
        domain_result = resolve_module_llm_config(config, "domain_generation.llm")
        assert sql_result["active"] == "deepseek"
        assert domain_result["active"] == "qwen"
        assert domain_result["providers"]["qwen"]["model"] == "qwen-max"

    def test_sql_rag_llm_illegal_model_name_raises(self):
        config = _base_config()
        config["sql_rag"] = {"llm": {"model_name": "qwen-max"}}
        with pytest.raises(ValueError, match="model_name"):
            resolve_module_llm_config(config, "sql_rag.llm")

    def test_sql_rag_llm_with_runtime_override(self):
        config = _base_config()
        config["sql_rag"] = {"llm": {"active": "deepseek"}}
        result = resolve_module_llm_config(
            config,
            "sql_rag.llm",
            runtime_override={"langchain_config": {"use_async": False}},
        )
        assert result["active"] == "deepseek"
        assert result["langchain_config"]["use_async"] is False

    def test_resolve_does_not_pollute_original_config(self):
        """深拷贝验证：resolve 产出不应污染原始 full_config"""
        config = _base_config()
        config["sql_rag"] = {"llm": {"providers": {"qwen": {"model": "qwen-max"}}}}
        result = resolve_module_llm_config(config, "sql_rag.llm")
        result["providers"]["qwen"]["model"] = "MUTATED"
        assert config["llm"]["providers"]["qwen"]["model"] == "qwen-plus"


# ===========================================================================
# 第二阶段：非标散落字段检测
# ===========================================================================

class TestValidateNonstandardLlmFields:

    def test_sql_rag_generation_llm_timeout_raises(self):
        config = _base_config()
        config["sql_rag"] = {"generation": {"llm_timeout": 120}}
        with pytest.raises(ValueError, match="sql_rag.generation.llm_timeout"):
            _validate_nonstandard_llm_paths(config)

    def test_sql_rag_generation_llm_timeout_error_suggests_standard_path(self):
        config = _base_config()
        config["sql_rag"] = {"generation": {"llm_timeout": 120}}
        with pytest.raises(ValueError, match="providers.*timeout"):
            _validate_nonstandard_llm_paths(config)

    def test_sql_rag_generation_without_llm_timeout_passes(self):
        config = _base_config()
        config["sql_rag"] = {"generation": {"questions_per_domain": 3}}
        _validate_nonstandard_llm_paths(config)  # 不报错


# ===========================================================================
# 第三阶段：relationships.llm 与 json_llm.llm 白名单与深合并
# ===========================================================================

class TestPhase3RelationshipsLlm:
    """relationships.llm 白名单与深合并测试"""

    def test_relationships_llm_in_whitelist(self):
        """relationships.llm 在白名单内，预检不报错"""
        config = _base_config()
        config["relationships"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        _validate_declared_module_llm_paths(config)  # 不报错

    def test_relationships_llm_deep_merge_override_active(self):
        """relationships.llm 可以覆盖 active 字段"""
        config = _base_config()
        config["relationships"] = {"llm": {"active": "deepseek"}}
        result = resolve_module_llm_config(config, "relationships.llm")
        assert result["active"] == "deepseek"
        # 全局 providers 应被继承
        assert "qwen" in result["providers"]

    def test_relationships_llm_deep_merge_provider_model(self):
        """relationships.llm 仅覆盖 provider 的 model，其余字段继承"""
        config = _base_config()
        config["relationships"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        result = resolve_module_llm_config(config, "relationships.llm")
        assert result["providers"]["qwen"]["model"] == "qwen-max"
        # api_key 等未声明字段应继承全局
        assert result["providers"]["qwen"]["api_key"] == "key-qwen"

    def test_relationships_llm_fallback_to_global(self):
        """无 relationships.llm 声明时回退到全局 llm"""
        config = _base_config()
        result = resolve_module_llm_config(config, "relationships.llm")
        assert result == config["llm"]


class TestPhase3JsonLlmLlm:
    """json_llm.llm 白名单、深合并与 runtime_override 测试"""

    def test_json_llm_llm_in_whitelist(self):
        """json_llm.llm 在白名单内，预检不报错"""
        config = _base_config()
        config["json_llm"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        _validate_declared_module_llm_paths(config)  # 不报错

    def test_json_llm_llm_deep_merge_override_active(self):
        """json_llm.llm 可以覆盖 active 字段"""
        config = _base_config()
        config["json_llm"] = {"llm": {"active": "deepseek"}}
        result = resolve_module_llm_config(config, "json_llm.llm")
        assert result["active"] == "deepseek"

    def test_json_llm_llm_deep_merge_provider_model(self):
        """json_llm.llm 深合并覆盖 provider model"""
        config = _base_config()
        config["json_llm"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        result = resolve_module_llm_config(config, "json_llm.llm")
        assert result["providers"]["qwen"]["model"] == "qwen-max"
        assert result["providers"]["qwen"]["api_key"] == "key-qwen"

    def test_json_llm_llm_runtime_override_use_async(self):
        """runtime_override 强制 use_async=False"""
        config = _base_config()
        config["llm"]["langchain_config"] = {"use_async": True, "batch_size": 50}
        result = resolve_module_llm_config(
            config, "json_llm.llm",
            runtime_override={"langchain_config": {"use_async": False}},
        )
        assert result["langchain_config"]["use_async"] is False
        # batch_size 应被继承
        assert result["langchain_config"]["batch_size"] == 50

    def test_json_llm_llm_runtime_override_stacks_with_module(self):
        """runtime_override 在模块级覆盖基础上再叠加"""
        config = _base_config()
        config["llm"]["langchain_config"] = {"use_async": True, "batch_size": 50}
        config["json_llm"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        result = resolve_module_llm_config(
            config, "json_llm.llm",
            runtime_override={"langchain_config": {"use_async": False}},
        )
        # 模块级覆盖生效
        assert result["providers"]["qwen"]["model"] == "qwen-max"
        # runtime_override 生效
        assert result["langchain_config"]["use_async"] is False
        # 全局继承
        assert result["langchain_config"]["batch_size"] == 50

    def test_json_llm_llm_fallback_to_global(self):
        """无 json_llm.llm 声明时回退到全局 llm"""
        config = _base_config()
        result = resolve_module_llm_config(config, "json_llm.llm")
        assert result == config["llm"]


class TestPhase3CrossModuleIsolation:
    """各模块覆盖互不干扰"""

    def test_relationships_and_json_llm_independent(self):
        """relationships.llm 和 json_llm.llm 的覆盖互不影响"""
        config = _base_config()
        config["relationships"] = {"llm": {"active": "deepseek"}}
        config["json_llm"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }

        rel_result = resolve_module_llm_config(config, "relationships.llm")
        json_result = resolve_module_llm_config(config, "json_llm.llm")

        # relationships 切换到 deepseek，但 model 不变
        assert rel_result["active"] == "deepseek"
        assert rel_result["providers"]["qwen"]["model"] == "qwen-plus"

        # json_llm 保持 qwen active，但 model 覆盖
        assert json_result["active"] == "qwen"
        assert json_result["providers"]["qwen"]["model"] == "qwen-max"

    def test_all_four_modules_independent(self):
        """四个已支持模块的覆盖完全隔离"""
        config = _base_config()
        config["domain_generation"] = {"llm": {"active": "deepseek"}}
        config["sql_rag"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-turbo"}}}
        }
        config["relationships"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-max"}}}
        }
        config["json_llm"] = {
            "llm": {"providers": {"qwen": {"model": "qwen-long"}}}
        }

        d = resolve_module_llm_config(config, "domain_generation.llm")
        s = resolve_module_llm_config(config, "sql_rag.llm")
        r = resolve_module_llm_config(config, "relationships.llm")
        j = resolve_module_llm_config(config, "json_llm.llm")

        assert d["active"] == "deepseek"
        assert s["providers"]["qwen"]["model"] == "qwen-turbo"
        assert r["providers"]["qwen"]["model"] == "qwen-max"
        assert j["providers"]["qwen"]["model"] == "qwen-long"

        # 全局配置未被污染
        assert config["llm"]["providers"]["qwen"]["model"] == "qwen-plus"


# ===========================================================================
# P1-Fix: 非 dict 模块级 llm 配置应 ValueError
# ===========================================================================

class TestNonDictModuleLlmRaises:
    """非 dict 的 xxx.llm 值必须报错，不得静默回退"""

    def test_string_llm_value_raises_on_precheck(self):
        """预检阶段：relationships.llm: 'deepseek' → ValueError"""
        config = _base_config()
        config["relationships"] = {"llm": "deepseek"}
        with pytest.raises(ValueError, match="relationships.llm.*dict"):
            _validate_declared_module_llm_paths(config)

    def test_list_llm_value_raises_on_precheck(self):
        """预检阶段：json_llm.llm: [] → ValueError"""
        config = _base_config()
        config["json_llm"] = {"llm": []}
        with pytest.raises(ValueError, match="json_llm.llm.*dict"):
            _validate_declared_module_llm_paths(config)

    def test_string_llm_value_raises_on_resolve(self):
        """resolve 阶段：路径值为字符串 → ValueError"""
        config = _base_config()
        config["relationships"] = {"llm": "deepseek"}
        with pytest.raises(ValueError, match="relationships.llm.*dict"):
            resolve_module_llm_config(config, "relationships.llm")

    def test_int_llm_value_raises_on_resolve(self):
        """resolve 阶段：路径值为整数 → ValueError"""
        config = _base_config()
        config["json_llm"] = {"llm": 42}
        with pytest.raises(ValueError, match="json_llm.llm.*dict"):
            resolve_module_llm_config(config, "json_llm.llm")


# ===========================================================================
# P2-Fix: deep_merge 返回值不与 override 共享引用
# ===========================================================================

class TestDeepMergeReferenceIsolation:
    """deep_merge_dict 返回值修改不应影响原始 override 或 full_config"""

    def test_override_new_key_is_isolated(self):
        """override 中新增的嵌套 key 不应与 merge 结果共享引用"""
        base = {"a": 1}
        override = {"extra": {"nested": "value"}}
        result = deep_merge_dict(base, override)

        # 修改 result 中的 extra.nested
        result["extra"]["nested"] = "changed"

        # 原始 override 不应被影响
        assert override["extra"]["nested"] == "value"

    def test_resolve_result_does_not_pollute_module_config(self):
        """resolve 结果的修改不应影响 full_config 中的模块 override"""
        config = _base_config()
        config["json_llm"] = {
            "llm": {
                "providers": {"qwen": {"model": "qwen-max", "timeout": 60}},
            }
        }
        result = resolve_module_llm_config(config, "json_llm.llm")

        # 修改 resolve 结果中的 provider timeout
        result["providers"]["qwen"]["timeout"] = 999

        # 原始配置不应被污染
        assert config["json_llm"]["llm"]["providers"]["qwen"]["timeout"] == 60


class TestPhase4CommentGenerationLlm:
    """Phase 4: comment_generation.llm 白名单与深合并测试"""

    def test_comment_generation_in_whitelist(self):
        """comment_generation.llm 已纳入白名单"""
        from metaweave.services.llm_config_resolver import SUPPORTED_MODULE_LLM_PATHS
        assert "comment_generation.llm" in SUPPORTED_MODULE_LLM_PATHS

    def test_comment_generation_llm_resolve(self):
        """comment_generation.llm 深合并正确执行"""
        config = {
            "llm": {
                "active": "qwen",
                "providers": {
                    "qwen": {
                        "model": "qwen-plus",
                        "api_key": "test-key",
                        "api_base": "https://test.api",
                        "timeout": 60,
                    },
                },
            },
            "comment_generation": {
                "enabled": True,
                "language": "zh",
                "llm": {
                    "providers": {
                        "qwen": {
                            "timeout": 180,
                        },
                    },
                },
            },
        }
        result = resolve_module_llm_config(config, "comment_generation.llm")
        # 覆盖生效
        assert result["providers"]["qwen"]["timeout"] == 180
        # 继承保留
        assert result["providers"]["qwen"]["model"] == "qwen-plus"
        assert result["active"] == "qwen"

    def test_comment_generation_precheck_passes(self):
        """comment_generation.llm 预检通过（不再报错）"""
        config = {
            "llm": {
                "active": "qwen",
                "providers": {
                    "qwen": {"model": "qwen-plus", "api_key": "k", "api_base": "u"},
                },
            },
            "comment_generation": {
                "llm": {"active": "qwen"},
            },
        }
        # 应正常通过，不抛异常
        _validate_declared_module_llm_paths(config)

    def test_comment_generation_no_override_inherits_global(self):
        """不声明 comment_generation.llm 时完全继承全局"""
        config = {
            "llm": {
                "active": "qwen",
                "providers": {
                    "qwen": {
                        "model": "qwen-plus",
                        "api_key": "test-key",
                        "api_base": "https://test.api",
                    },
                },
            },
            "comment_generation": {
                "enabled": True,
            },
        }
        result = resolve_module_llm_config(config, "comment_generation.llm")
        assert result["active"] == "qwen"
        assert result["providers"]["qwen"]["model"] == "qwen-plus"


class TestDeprecatedTopLevelKeyRejection:
    """P1-Fix: 旧顶层键 llm_comment_generation 必须被立即拒绝"""

    def test_old_key_without_llm_child_raises(self):
        """llm_comment_generation.enabled: false 被检测到并报错"""
        config = {
            "llm": {
                "active": "qwen",
                "providers": {
                    "qwen": {"model": "qwen-plus", "api_key": "k", "api_base": "u"},
                },
            },
            "llm_comment_generation": {
                "enabled": False,
            },
        }
        with pytest.raises(ValueError, match="llm_comment_generation"):
            _validate_nonstandard_llm_paths(config)

    def test_old_key_with_llm_child_raises(self):
        """llm_comment_generation.llm 也被检测到并报错"""
        config = {
            "llm": {
                "active": "qwen",
                "providers": {
                    "qwen": {"model": "qwen-plus", "api_key": "k", "api_base": "u"},
                },
            },
            "llm_comment_generation": {
                "llm": {"active": "qwen"},
            },
        }
        with pytest.raises(ValueError, match="comment_generation"):
            _validate_nonstandard_llm_paths(config)

    def test_new_key_passes(self):
        """新键名 comment_generation 不触发废弃检测"""
        config = {
            "llm": {
                "active": "qwen",
                "providers": {
                    "qwen": {"model": "qwen-plus", "api_key": "k", "api_base": "u"},
                },
            },
            "comment_generation": {
                "enabled": True,
            },
        }
        # 不应抛异常
        _validate_nonstandard_llm_paths(config)


