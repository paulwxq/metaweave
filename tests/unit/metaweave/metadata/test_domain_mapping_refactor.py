"""Domain 映射机制重构 — 单元测试

覆盖设计文档 docs/20_db_domains_mapping_refactor_design.md 中的全部改造点：
- DomainGenerator: 专属 LLM 配置、md_context_limit 配置优先级、
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
from metaweave.core.metadata.models import (
    ColumnStatisticsSummary,
    KeyColumnsSummary,
    TableProfile,
)
from metaweave.core.metadata.generator import MetadataGenerator


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
# Task 3: 专属 LLM 配置 + md_context_limit 配置化
# ===========================================================================

class TestDomainGeneratorLLMConfig:

    def test_uses_dedicated_llm_config_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = {
            "llm": {"provider": "qwen", "model_name": "qwen-plus"},
            "domain_generation": {
                "llm": {"provider": "openai", "model_name": "gpt-4o", "temperature": 0.1},
            },
        }
        DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))
        assert _CaptureLLMService.captured_config["provider"] == "openai"
        assert _CaptureLLMService.captured_config["model_name"] == "gpt-4o"

    def test_falls_back_to_global_llm_when_no_dedicated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = {"llm": {"provider": "qwen", "model_name": "qwen-plus"}}
        DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))
        assert _CaptureLLMService.captured_config["provider"] == "qwen"

    def test_md_context_limit_from_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = {
            "llm": {},
            "domain_generation": {"md_context_limit": 200},
        }
        gen = DomainGenerator(config=config, yaml_path=str(tmp_path / "d.yaml"))
        assert gen.md_context_limit == 200

    def test_cli_md_context_limit_overrides_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "metaweave.core.metadata.domain_generator.LLMService", _CaptureLLMService
        )
        config = {
            "llm": {},
            "domain_generation": {"md_context_limit": 200},
        }
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
        gen = DomainGenerator(config={"llm": {}}, yaml_path=str(tmp_path / "d.yaml"))
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
            config={"llm": {}},
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
        gen = DomainGenerator(config={"llm": {}}, yaml_path=str(tmp_path / "d.yaml"))
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
        gen = DomainGenerator(config={"llm": {}}, yaml_path=str(tmp_path / "d.yaml"))
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
        gen = DomainGenerator(config={"llm": {}}, yaml_path=str(yaml_path))
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
        gen = DomainGenerator(config={"llm": {}}, yaml_path=str(yaml_path))
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
        gen = DomainGenerator(config={"llm": {}}, yaml_path=str(yaml_path))
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
# Task 5: TableProfile 增加 table_domains
# ===========================================================================

class TestTableProfileDomains:

    def _make_profile(self, **kwargs):
        defaults = dict(
            table_category="fact",
            confidence=0.9,
            column_statistics=ColumnStatisticsSummary(
                total_columns=1,
                identifier_count=0,
                metric_count=0,
                datetime_count=0,
                enum_count=0,
                audit_count=0,
                attribute_count=0,
                primary_key_count=0,
                foreign_key_count=0,
            ),
            key_columns=KeyColumnsSummary(
                primary_keys=[], foreign_keys=[]
            ),
        )
        defaults.update(kwargs)
        return TableProfile(**defaults)

    def test_table_domains_defaults_to_empty_list(self):
        profile = self._make_profile()
        assert profile.table_domains == []

    def test_table_domains_in_to_dict(self):
        profile = self._make_profile(table_domains=["订单域", "支付域"])
        result = profile.to_dict()
        assert result["table_domains"] == ["订单域", "支付域"]

    def test_table_domains_empty_in_to_dict(self):
        profile = self._make_profile()
        result = profile.to_dict()
        assert result["table_domains"] == []


# ===========================================================================
# Task 6: 从 db_domains.yaml 构建反向索引
# ===========================================================================

class TestDomainReverseIndex:

    def test_build_domain_reverse_index(self, tmp_path):
        yaml_content = {
            "domains": [
                {"name": "_未分类_", "description": "未分类", "tables": ["db.public.legacy"]},
                {
                    "name": "订单域",
                    "description": "订单",
                    "tables": ["db.public.orders", "db.public.order_items"],
                },
                {
                    "name": "支付域",
                    "description": "支付",
                    "tables": ["db.public.orders", "db.public.payments"],
                },
            ]
        }
        yaml_path = tmp_path / "db_domains.yaml"
        yaml_path.write_text(
            yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8"
        )

        index = MetadataGenerator._build_domain_reverse_index(yaml_path)
        assert sorted(index["db.public.orders"]) == ["支付域", "订单域"]
        assert index["db.public.legacy"] == ["_未分类_"]
        assert "db.public.unknown" not in index

    def test_build_domain_reverse_index_casefold(self, tmp_path):
        yaml_content = {
            "domains": [
                {"name": "A", "description": "a", "tables": ["DB.Public.Users"]},
            ]
        }
        yaml_path = tmp_path / "db_domains.yaml"
        yaml_path.write_text(
            yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8"
        )

        index = MetadataGenerator._build_domain_reverse_index(yaml_path)
        assert index["db.public.users"] == ["A"]

    def test_build_domain_reverse_index_missing_file(self, tmp_path):
        index = MetadataGenerator._build_domain_reverse_index(
            tmp_path / "nonexistent.yaml"
        )
        assert index == {}

    def test_build_domain_reverse_index_empty_yaml(self, tmp_path):
        yaml_path = tmp_path / "db_domains.yaml"
        yaml_path.write_text("", encoding="utf-8")
        index = MetadataGenerator._build_domain_reverse_index(yaml_path)
        assert index == {}

    def test_lookup_domains_casefold(self, tmp_path):
        yaml_content = {
            "domains": [
                {"name": "用户域", "description": "用户", "tables": ["db.public.users"]},
            ]
        }
        yaml_path = tmp_path / "db_domains.yaml"
        yaml_path.write_text(
            yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8"
        )
        index = MetadataGenerator._build_domain_reverse_index(yaml_path)
        assert index.get("DB.Public.Users".casefold(), []) == ["用户域"]
        assert index.get("db.public.orders".casefold(), []) == []


# ===========================================================================
# Task 7: 放宽 _validate_table_domains 校验
# ===========================================================================

class TestValidateTableDomains:

    def test_empty_table_domains_does_not_raise(self):
        from metaweave.core.relationships.llm_relationship_discovery import (
            LLMRelationshipDiscovery,
        )

        tables = {
            "db.public.orders": {"table_profile": {"table_domains": []}},
            "db.public.users": {"table_profile": {"table_domains": ["用户域"]}},
        }
        discovery = object.__new__(LLMRelationshipDiscovery)
        discovery._validate_table_domains(tables)  # 不应抛出异常

    def test_missing_table_domains_key_does_not_raise(self):
        from metaweave.core.relationships.llm_relationship_discovery import (
            LLMRelationshipDiscovery,
        )

        tables = {
            "db.public.orders": {"table_profile": {}},
        }
        discovery = object.__new__(LLMRelationshipDiscovery)
        discovery._validate_table_domains(tables)  # 不应抛出异常
        # 应自动补充空列表
        assert tables["db.public.orders"]["table_profile"]["table_domains"] == []
