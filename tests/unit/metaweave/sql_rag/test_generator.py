"""QuestionSQLGenerator 单元测试"""

import json
from pathlib import Path

import pytest

from metaweave.core.sql_rag.generator import QuestionSQLGenerator


class FakeLLMService:
    """模拟 LLMService"""

    def __init__(self, response: str = ""):
        self.response = response
        self.calls = []
        self.model = "fake-model"

    def call_llm(self, prompt: str, system_message: str = None) -> str:
        self.calls.append({"prompt": prompt, "system_message": system_message})
        return self.response


def _write_domains_config(tmp_path: Path, db_name: str = "testdb") -> Path:
    cfg = {
        "database": {"name": db_name, "description": "测试数据库"},
        "domains": [
            {
                "name": "销售分析",
                "description": "销售相关查询",
                "tables": ["orders", "customers"],
            },
        ],
    }
    path = tmp_path / "db_domains.yaml"
    import yaml

    path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    return path


def _write_md_files(tmp_path: Path) -> Path:
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    (md_dir / "orders.md").write_text("# orders\n字段: id, amount", encoding="utf-8")
    (md_dir / "customers.md").write_text(
        "# customers\n字段: id, name", encoding="utf-8"
    )
    return md_dir


class TestGeneratorParseAndClean:
    def _make_generator(self, llm_response=""):
        llm = FakeLLMService(llm_response)
        return QuestionSQLGenerator(llm, {"questions_per_domain": 5})

    def test_extract_json_from_code_block(self):
        g = self._make_generator()
        text = '```json\n[{"question": "Q", "sql": "SELECT 1;"}]\n```'
        result = g._extract_json(text)
        assert '"question"' in result

    def test_extract_json_raw_array(self):
        g = self._make_generator()
        text = '[{"question": "Q", "sql": "SELECT 1;"}]'
        result = g._extract_json(text)
        assert result is not None

    def test_extract_json_no_match(self):
        g = self._make_generator()
        assert g._extract_json("no json here") is None

    def test_parse_and_clean_valid(self):
        g = self._make_generator()
        response = json.dumps([
            {"question": "各客户的订单总额是多少？", "sql": "SELECT c.name, SUM(o.amount) FROM orders o JOIN customers c ON o.cid = c.id GROUP BY c.name"},
        ])
        pairs = g._parse_and_clean(response)
        assert len(pairs) == 1
        assert pairs[0].sql.endswith(";")  # 自动添加分号

    def test_parse_and_clean_multiline_folded(self):
        g = self._make_generator()
        response = json.dumps([
            {"question": "多行\n问题", "sql": "SELECT\n  *\nFROM\n  t"},
        ])
        pairs = g._parse_and_clean(response)
        assert "\n" not in pairs[0].question
        assert "\n" not in pairs[0].sql

    def test_parse_and_clean_skips_empty(self):
        g = self._make_generator()
        response = json.dumps([
            {"question": "", "sql": "SELECT 1;"},
            {"question": "Q", "sql": ""},
            {"question": "Valid", "sql": "SELECT 1;"},
        ])
        pairs = g._parse_and_clean(response)
        assert len(pairs) == 1

    def test_parse_and_clean_invalid_json(self):
        g = self._make_generator()
        pairs = g._parse_and_clean("not json at all {{{")
        assert pairs == []

    def test_parse_and_clean_not_array(self):
        g = self._make_generator()
        pairs = g._parse_and_clean('{"question": "Q", "sql": "S"}')
        assert pairs == []


class TestGeneratorGenerate:
    def test_generate_success(self, tmp_path):
        llm_response = json.dumps([
            {"question": "总订单数？", "sql": "SELECT COUNT(*) FROM orders;"},
            {"question": "客户列表？", "sql": "SELECT * FROM customers;"},
        ])
        llm = FakeLLMService(llm_response)
        gen_config = {
            "questions_per_domain": 5,
            "output_dir": str(tmp_path / "output"),
        }
        generator = QuestionSQLGenerator(llm, gen_config)

        domains_path = _write_domains_config(tmp_path)
        md_dir = _write_md_files(tmp_path)

        result = generator.generate(
            domains_config_path=str(domains_path),
            md_dir=str(md_dir),
        )

        assert result.success
        assert result.total_generated == 2
        assert "销售分析" in result.domain_stats
        # domain 已注入
        assert all(p.domain == "销售分析" for p in result.pairs)
        # 输出文件存在
        assert Path(result.output_file).exists()
        with open(result.output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2
        assert all("domain" in item for item in data)

    def test_generate_with_uncategorized_skip(self, tmp_path):
        import yaml

        domains_cfg = {
            "database": {"name": "testdb", "description": "test"},
            "domains": [
                {"name": "_未分类_", "description": "未分类", "tables": ["t1"]},
            ],
        }
        domains_path = tmp_path / "domains.yaml"
        domains_path.write_text(yaml.dump(domains_cfg, allow_unicode=True), encoding="utf-8")

        md_dir = tmp_path / "md"
        md_dir.mkdir()
        (md_dir / "t1.md").write_text("# t1", encoding="utf-8")

        llm = FakeLLMService('[]')
        gen_config = {
            "questions_per_domain": 5,
            "skip_uncategorized": True,
            "output_dir": str(tmp_path / "output"),
        }
        generator = QuestionSQLGenerator(llm, gen_config)
        result = generator.generate(str(domains_path), str(md_dir))

        # 跳过未分类域，LLM 不应被调用
        assert llm.calls == []
        assert result.total_generated == 0

    def test_clean_output(self, tmp_path):
        gen_config = {"output_dir": str(tmp_path)}
        llm = FakeLLMService()
        generator = QuestionSQLGenerator(llm, gen_config)

        # 创建目标文件
        target = tmp_path / "qs_testdb_pair.json"
        target.write_text("[]", encoding="utf-8")
        assert target.exists()

        generator.clean_output("testdb")
        assert not target.exists()

    def test_build_md_context_all_tables(self):
        llm = FakeLLMService()
        gen = QuestionSQLGenerator(llm, {})
        md_map = {"t1": "content1", "t2": "content2"}
        # tables 为空时用全量
        result = gen._build_md_context([], md_map)
        assert "content1" in result
        assert "content2" in result

    def test_build_md_context_specific_tables(self):
        llm = FakeLLMService()
        gen = QuestionSQLGenerator(llm, {})
        md_map = {"t1": "content1", "t2": "content2"}
        result = gen._build_md_context(["t1"], md_map)
        assert "content1" in result
        assert "content2" not in result
