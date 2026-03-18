"""Domain 映射机制重构 — 单元测试

覆盖设计文档 docs/20_db_domains_mapping_refactor_design.md 中的全部改造点：
- DomainGenerator: 专属 LLM 配置（深合并）、md_context_limit 配置优先级、
  prompt 升级（tables 分配）、tables 解析/写入、_未分类_ tables 合并
- TableProfile: table_domains 字段及序列化
- MetadataGenerator: db_domains.yaml 反向索引构建
- LLMRelationshipDiscovery: _validate_table_domains 放宽校验
"""

from pathlib import Path
from typing import Dict, List

import pytest
import yaml

from metaweave.core.metadata.domain_generator import DomainGenerator


# ---------------------------------------------------------------------------
# 公共 helpers
# ---------------------------------------------------------------------------

def _make_config(active="qwen", model="qwen-plus", domain_llm=None):
    """构造合法的标准格式配置字典"""
    cfg = {
        "llm": {
            "active": active,
            "providers": {
                "qwen": {"model": model, "api_key": "k", "api_base": "http://q"},
                "deepseek": {"model": "deepseek-chat", "api_key": "k", "api_base": "http://d"},
            },
            "langchain_config": {"use_async": False},
        }
    }
    if domain_llm is not None:
        cfg["domain_generation"] = {"llm": domain_llm}
    return cfg


# ---------------------------------------------------------------------------
# Mock LLM Services
# ---------------------------------------------------------------------------

class _CaptureLLMService:
    """捕获初始化参数的 mock LLMService"""
    captured_config: Dict = {}
    response = (
        '{"database": {"name": "TestDB", "description": "test"}, '
        '"domains": [{"name": "A", "description": "a", "tables": []}]}'
    )

    def __init__(self, config):
        type(self).captured_config = dict(config)

    def _call_llm(self, prompt: str) -> str:
        return type(self).response


class _TablesLLMService:
    """返回带 tables 的 LLM 响应"""
    response = ""
    last_prompt = ""

    def __init__(self, _config):
        pass

    def _call_llm(self, prompt: str) -> str:
        type(self).last_prompt = prompt
        return type(self).response


def _write_md(md_dir: Path) -> None:
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "testdb.public.users.md").write_text(
        "# 用户表\n用户信息", encoding="utf-8"
    )


# ===========================================================================
# Task 3: 专属 LLM 配置（深合并）+ md_context_limit 配置化
# ===========================================================================

class TestDomainGeneratorLLMConfig:

    def test_falls_back_to_global_llm_when_no_dedicated(self, tmp_path, monkeypatch):
        """无 domain_generation.llm 时使用全局 llm"""
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = _make_config(active="qwen", model="qwen-plus")
        DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))
        assert _CaptureLLMService.captured_config["active"] == "qwen"
        assert _CaptureLLMService.captured_config["providers"]["qwen"]["model"] == "qwen-plus"

    def test_override_active_via_domain_llm(self, tmp_path, monkeypatch):
        """domain_generation.llm.active 覆盖全局 active"""
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = _make_config(active="qwen", domain_llm={"active": "deepseek"})
        DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))
        assert _CaptureLLMService.captured_config["active"] == "deepseek"
        # 全局 providers 不丢失
        assert "qwen" in _CaptureLLMService.captured_config["providers"]
        assert "deepseek" in _CaptureLLMService.captured_config["providers"]

    def test_deep_merge_providers_model(self, tmp_path, monkeypatch):
        """providers.qwen.model 覆盖，api_key 等其他字段保留"""
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = _make_config(
            domain_llm={"providers": {"qwen": {"model": "qwen-max"}}}
        )
        DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))
        qwen_cfg = _CaptureLLMService.captured_config["providers"]["qwen"]
        assert qwen_cfg["model"] == "qwen-max"
        assert qwen_cfg["api_key"] == "k"  # 保留

    def test_illegal_model_name_raises(self, tmp_path, monkeypatch):
        """domain_generation.llm.model_name 是非法旧字段，应立即报错"""
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = _make_config(domain_llm={"model_name": "qwen-max"})
        with pytest.raises(ValueError, match="model_name"):
            DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))

    def test_illegal_provider_raises(self, tmp_path, monkeypatch):
        """domain_generation.llm.provider 是非法旧字段，应立即报错"""
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = _make_config(domain_llm={"provider": "openai"})
        with pytest.raises(ValueError, match="provider"):
            DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))

    def test_md_context_limit_from_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = _make_config()
        config["domain_generation"] = {"md_context_limit": 200}
        gen = DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))
        assert gen.md_context_limit == 200

    def test_cli_md_context_limit_overrides_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = _make_config()
        config["domain_generation"] = {"md_context_limit": 200}
        gen = DomainGenerator(
            config=config,
            yaml_path=str(tmp_path / "d.yaml"),
            md_context_limit=50,
        )
        assert gen.md_context_limit == 50

    def test_default_md_context_limit_when_nothing_set(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        gen = DomainGenerator(config=_make_config(), yaml_path=str(tmp_path / "d.yaml"))
        assert gen.md_context_limit == 100


# ===========================================================================
# Task 4: prompt 升级 + tables 解析/写入 + _未分类_ 合并
# ===========================================================================

class TestDomainGeneratorTables:

    def test_prompt_includes_tables_assignment_instruction(self, tmp_path, monkeypatch):
        _TablesLLMService.response = (
            '{"database": {"name": "DB", "description": "d"}, '
            '"domains": [{"name": "A", "description": "a", "tables": ["db.public.t1"]}]}'
        )
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _TablesLLMService
        )
        md_dir = tmp_path / "md"
        _write_md(md_dir)
        gen = DomainGenerator(
            config=_make_config(),
            yaml_path=str(tmp_path / "d.yaml"),
            md_context_dir=str(md_dir),
        )
        gen.generate_from_context()
        prompt = _TablesLLMService.last_prompt.lower()
        assert "tables" in prompt
        assert "_未分类_" in _TablesLLMService.last_prompt

    def test_parse_response_extracts_tables(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        gen = DomainGenerator(config=_make_config(), yaml_path=str(tmp_path / "d.yaml"))
        payload = gen._parse_response(
            '{"database": {"name": "X", "description": "x"}, '
            '"domains": [{"name": "A", "description": "a", '
            '"tables": ["x.public.t1", "x.public.t2"]}]}'
        )
        assert payload["domains"][0]["tables"] == ["x.public.t1", "x.public.t2"]

    def test_parse_response_defaults_tables_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        gen = DomainGenerator(config=_make_config(), yaml_path=str(tmp_path / "d.yaml"))
        payload = gen._parse_response(
            '{"database": {"name": "X", "description": "x"}, '
            '"domains": [{"name": "A", "description": "a"}]}'
        )
        assert payload["domains"][0]["tables"] == []

    def test_write_to_yaml_persists_tables(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        yaml_path = tmp_path / "d.yaml"
        gen = DomainGenerator(config=_make_config(), yaml_path=str(yaml_path))
        gen.write_to_yaml({
            "database": {"name": "DB", "description": "d"},
            "domains": [
                {"name": "订单", "description": "订单域", "tables": ["db.public.orders"]},
            ],
        })
        written = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        order_domain = next(d for d in written["domains"] if d["name"] == "订单")
        assert order_domain["tables"] == ["db.public.orders"]

    def test_write_to_yaml_merges_unclassified_tables(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        yaml_path = tmp_path / "d.yaml"
        gen = DomainGenerator(config=_make_config(), yaml_path=str(yaml_path))
        gen.write_to_yaml({
            "database": {"name": "DB", "description": "d"},
            "domains": [
                {"name": "_未分类_", "description": "忽略", "tables": ["db.public.legacy"]},
                {"name": "订单", "description": "订单域", "tables": ["db.public.orders"]},
            ],
        })
        written = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        unclassified = written["domains"][0]
        assert unclassified["name"] == "_未分类_"
        assert "db.public.legacy" in unclassified["tables"]
        # description 应是系统预置的，不被 LLM 覆盖
        assert unclassified["description"] == "无法归入其他业务主题的表"

    def test_unclassified_tables_empty_when_llm_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        yaml_path = tmp_path / "d.yaml"
        gen = DomainGenerator(config=_make_config(), yaml_path=str(yaml_path))
        gen.write_to_yaml({
            "database": {"name": "DB", "description": "d"},
            "domains": [
                {"name": "订单", "description": "订单域", "tables": []},
            ],
        })
        written = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert written["domains"][0]["name"] == "_未分类_"
        assert written["domains"][0]["tables"] == []


# ===========================================================================
# Task 5-6: （已移除）table_domains 和 domain 反向索引已迁移至 DomainResolver
# 参见 tests/unit/metaweave/domains/test_domain_resolver.py
# ===========================================================================

# ===========================================================================
# Task 7: （已移除）_validate_table_domains 已迁移至 DomainResolver
# ===========================================================================
