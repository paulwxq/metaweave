"""SQL RAG 数据模型单元测试"""

from metaweave.core.sql_rag.models import (
    GenerationResult,
    QuestionSQLPair,
    ValidationResult,
)


class TestQuestionSQLPair:
    def test_defaults(self):
        p = QuestionSQLPair(question="Q", sql="SELECT 1;")
        assert p.question == "Q"
        assert p.sql == "SELECT 1;"
        assert p.domain == ""
        assert p.tables == []

    def test_with_domain_and_tables(self):
        p = QuestionSQLPair(
            question="Q", sql="S", domain="财务", tables=["t1", "t2"]
        )
        assert p.domain == "财务"
        assert p.tables == ["t1", "t2"]

    def test_tables_default_not_shared(self):
        p1 = QuestionSQLPair(question="Q1", sql="S1")
        p2 = QuestionSQLPair(question="Q2", sql="S2")
        p1.tables.append("t")
        assert p2.tables == []


class TestValidationResult:
    def test_defaults(self):
        r = ValidationResult(sql="SELECT 1", valid=True)
        assert r.index == -1
        assert r.error_message == ""
        assert r.execution_time == 0.0
        assert r.retry_count == 0
        assert not r.repair_attempted
        assert not r.repair_successful
        assert r.repaired_sql == ""
        assert r.repair_error == ""

    def test_failed_result(self):
        r = ValidationResult(
            sql="BAD SQL",
            valid=False,
            error_message="syntax error",
            retry_count=2,
        )
        assert not r.valid
        assert r.error_message == "syntax error"
        assert r.retry_count == 2


class TestGenerationResult:
    def test_creation(self):
        pairs = [QuestionSQLPair(question="Q", sql="S")]
        r = GenerationResult(
            success=True,
            pairs=pairs,
            domain_stats={"d1": 1},
            total_generated=1,
            output_file="/tmp/test.json",
        )
        assert r.success
        assert len(r.pairs) == 1
        assert r.domain_stats == {"d1": 1}
        assert r.total_generated == 1
