from pathlib import Path

import pytest
import yaml

from metaweave.core.metadata.domain_generator import DomainGenerator


class _DummyLLMService:
    response = """
{
  "database": {
    "name": "电商分析库",
    "description": "该数据库覆盖订单、支付、履约与商品信息，支持交易分析和运营分析。"
  },
  "domains": [
    {"name": "_未分类_", "description": "忽略我"},
    {"name": "订单履约", "description": "管理订单与履约流程"}
  ]
}
"""
    last_prompt = ""

    def __init__(self, _config):
        pass

    def _call_llm(self, prompt: str) -> str:
        type(self).last_prompt = prompt
        return type(self).response


def _write_md_file(md_dir: Path) -> None:
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "shop.public.orders.md").write_text(
        "# 订单表\n\n用于存储订单主信息。",
        encoding="utf-8",
    )


def test_generate_domains_initializes_missing_yaml_and_writes_full_config(tmp_path, monkeypatch):
    monkeypatch.setattr("metaweave.core.metadata.domain_generator.LLMService", _DummyLLMService)

    md_dir = tmp_path / "md"
    _write_md_file(md_dir)
    yaml_path = tmp_path / "configs" / "db_domains.yaml"

    generator = DomainGenerator(
        config={"llm": {}},
        yaml_path=str(yaml_path),
        md_context=True,
        md_context_dir=str(md_dir),
        md_context_mode="name_comment",
        md_context_limit=100,
    )

    payload = generator.generate_from_context(user_description="这是一个电商交易库")
    final_domains = generator.write_to_yaml(payload)

    assert yaml_path.exists()
    written = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    assert written["database"]["name"] == "电商分析库"
    assert "订单" in written["database"]["description"]
    assert written["llm_inference"]["max_domains_per_table"] == 3
    assert written["domains"][0]["name"] == "_未分类_"
    assert sum(1 for d in written["domains"] if d["name"] == "_未分类_") == 1
    assert len(final_domains) == 2
    assert "用户补充说明" in _DummyLLMService.last_prompt
    assert "这是一个电商交易库" in _DummyLLMService.last_prompt


def test_generate_domains_requires_md_files(tmp_path, monkeypatch):
    monkeypatch.setattr("metaweave.core.metadata.domain_generator.LLMService", _DummyLLMService)

    generator = DomainGenerator(
        config={"llm": {}},
        yaml_path=str(tmp_path / "db_domains.yaml"),
        md_context=True,
        md_context_dir=str(tmp_path / "missing_md"),
    )

    with pytest.raises(FileNotFoundError) as exc:
        generator.generate_from_context()

    assert "--step md" in str(exc.value)


def test_prompt_without_description_uses_auto_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("metaweave.core.metadata.domain_generator.LLMService", _DummyLLMService)
    md_dir = tmp_path / "md"
    _write_md_file(md_dir)

    generator = DomainGenerator(
        config={"llm": {}},
        yaml_path=str(tmp_path / "db_domains.yaml"),
        md_context=True,
        md_context_dir=str(md_dir),
    )

    generator.generate_from_context(user_description=None)
    assert "用户补充说明" not in _DummyLLMService.last_prompt
    assert "表结构摘要" in _DummyLLMService.last_prompt
