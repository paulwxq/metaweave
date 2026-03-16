"""SQLValidator 单元测试"""

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from metaweave.core.sql_rag.validator import SQLValidator


class FakeCursor:
    def __init__(self, should_fail=False, error_msg=""):
        self.should_fail = should_fail
        self.error_msg = error_msg
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)
        if self.should_fail and sql.startswith("EXPLAIN"):
            raise Exception(self.error_msg or "syntax error")

    def fetchall(self):
        return [("Plan",)]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeConnection:
    def __init__(self, cursor=None):
        self.autocommit = True
        self._cursor = cursor or FakeCursor()

    @contextmanager
    def transaction(self):
        yield

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeConnector:
    def __init__(self, connection=None, pool_max=5):
        self._connection = connection or FakeConnection()
        self.pool = MagicMock()
        self.pool.max_size = pool_max

    @contextmanager
    def get_connection(self):
        yield self._connection


class TestNormalizeSQL:
    def setup_method(self):
        self.validator = SQLValidator(
            connector=FakeConnector(),
            config={},
        )

    def test_reject_legacy_validation_config_keys(self):
        with pytest.raises(ValueError, match="已废弃键名"):
            SQLValidator(
                connector=FakeConnector(),
                config={"max_retries": 2},
            )

    def test_reject_removed_modify_original_file_config(self):
        with pytest.raises(ValueError, match="已删除键名"):
            SQLValidator(
                connector=FakeConnector(),
                config={"modify_original_file": True},
            )

    def test_strip_and_remove_trailing_semicolon(self):
        result = self.validator._normalize_sql("  SELECT 1 ;  ")
        assert result == "SELECT 1"

    def test_empty_sql_raises(self):
        with pytest.raises(ValueError, match="SQL 为空"):
            self.validator._normalize_sql("   ")

    def test_multi_statement_raises(self):
        with pytest.raises(ValueError, match="多语句"):
            self.validator._normalize_sql("SELECT 1; SELECT 2")


class TestValidateSQL:
    def test_valid_sql(self):
        connector = FakeConnector()
        validator = SQLValidator(connector=connector, config={"timeout": 10})
        result = validator.validate_sql("SELECT 1;")
        assert result.valid
        assert result.sql == "SELECT 1"
        assert result.retry_count == 0

    def test_invalid_sql(self):
        cursor = FakeCursor(should_fail=True, error_msg="relation not found")
        conn = FakeConnection(cursor=cursor)
        connector = FakeConnector(connection=conn)
        validator = SQLValidator(connector=connector, config={"timeout": 10})
        result = validator.validate_sql("SELECT * FROM nonexistent;")
        assert not result.valid
        assert "relation not found" in result.error_message

    def test_retryable_error(self):
        call_count = 0
        original_cursor = FakeCursor()

        class RetryConnector:
            pool = MagicMock()
            pool.max_size = 5

            @contextmanager
            def get_connection(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("connection refused")
                yield FakeConnection(original_cursor)

        validator = SQLValidator(
            connector=RetryConnector(),
            config={"timeout": 10, "sql_validation_max_retries": 2},
        )
        result = validator.validate_sql("SELECT 1;")
        assert result.valid
        assert result.retry_count == 1

    def test_sql_validation_readonly(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor=cursor)
        connector = FakeConnector(connection=conn)
        validator = SQLValidator(
            connector=connector,
            config={"timeout": 10, "sql_validation_readonly": True},
        )
        result = validator.validate_sql("SELECT 1;")
        assert result.valid
        assert any(
            "default_transaction_read_only" in sql for sql in cursor.executed
        )

    def test_set_local_statement_timeout(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor=cursor)
        connector = FakeConnector(connection=conn)
        validator = SQLValidator(
            connector=connector,
            config={"timeout": 30},
        )
        validator.validate_sql("SELECT 1;")
        assert any("statement_timeout" in sql for sql in cursor.executed)
        assert any("30000" in sql for sql in cursor.executed)


class TestValidateBatch:
    def test_batch_validation(self):
        connector = FakeConnector()
        validator = SQLValidator(
            connector=connector,
            config={"sql_validation_max_concurrent": 2, "timeout": 10},
        )
        results = validator.validate_batch(["SELECT 1", "SELECT 2", "SELECT 3"])
        assert len(results) == 3
        assert all(r.valid for r in results)
        # index 已注入
        assert [r.index for r in results] == [0, 1, 2]


class TestValidateFile:
    def test_validate_file(self, tmp_path):
        pairs = [
            {"question": "Q1", "sql": "SELECT 1;"},
            {"question": "Q2", "sql": "SELECT 2;"},
        ]
        input_file = tmp_path / "test_pair.json"
        input_file.write_text(json.dumps(pairs), encoding="utf-8")

        connector = FakeConnector()
        validator = SQLValidator(
            connector=connector,
            config={"sql_validation_max_concurrent": 2, "timeout": 10},
        )
        stats = validator.validate_file(str(input_file))
        assert stats["total"] == 2
        assert stats["valid"] == 2
        assert stats["invalid"] == 0
        assert stats["success_rate"] == 100.0

        # 报告文件已写入
        report_files = list(tmp_path.glob("sql_validation_*_summary.log"))
        assert len(report_files) == 1

    def test_validate_file_without_repair_keeps_invalid_sqls(self, tmp_path):
        pairs = [{"question": "Q1", "sql": "SELECT * FROM missing;"}]
        input_file = tmp_path / "test_pair.json"
        original_content = json.dumps(pairs, ensure_ascii=False)
        input_file.write_text(original_content, encoding="utf-8")

        connector = FakeConnector()
        validator = SQLValidator(connector=connector, config={"timeout": 10})
        invalid_result = validator.validate_sql("SELECT * FROM missing;")
        invalid_result.valid = False
        invalid_result.error_message = "relation does not exist"

        with patch.object(validator, "validate_batch", return_value=[invalid_result]):
            stats = validator.validate_file(str(input_file), enable_repair=False)

        assert stats["invalid"] == 1
        assert stats["repair_apply_stats"] == {
            "modified": 0,
            "deleted": 0,
            "failed": 0,
        }
        assert input_file.read_text(encoding="utf-8") == original_content

    def test_validate_file_with_repair_deletes_unfixed_sqls(self, tmp_path):
        pairs = [{"question": "Q1", "sql": "SELECT * FROM missing;"}]
        input_file = tmp_path / "test_pair.json"
        input_file.write_text(json.dumps(pairs, ensure_ascii=False), encoding="utf-8")

        connector = FakeConnector()
        validator = SQLValidator(
            connector=connector,
            config={"timeout": 10},
            llm_service=MagicMock(),
        )
        invalid_result = validator.validate_sql("SELECT * FROM missing;")
        invalid_result.valid = False
        invalid_result.error_message = "relation does not exist"

        with patch.object(validator, "validate_batch", return_value=[invalid_result]):
            with patch.object(
                validator,
                "_repair_failed_sqls",
                return_value={"attempted": 1, "successful": 0, "failed": 1},
            ):
                stats = validator.validate_file(str(input_file), enable_repair=True)

        assert stats["repair_apply_stats"] == {
            "modified": 0,
            "deleted": 1,
            "failed": 0,
        }
        assert json.loads(input_file.read_text(encoding="utf-8")) == []


class TestShouldRetry:
    def test_retryable_keywords(self):
        validator = SQLValidator(connector=FakeConnector(), config={})
        assert validator._should_retry("connection refused")
        assert validator._should_retry("network error")
        assert validator._should_retry("timeout reached")
        assert validator._should_retry("pool exhausted")

    def test_non_retryable(self):
        validator = SQLValidator(connector=FakeConnector(), config={})
        assert not validator._should_retry("syntax error at position 5")
        assert not validator._should_retry("relation does not exist")


class TestParseRepairResponse:
    def setup_method(self):
        self.validator = SQLValidator(connector=FakeConnector(), config={})

    def test_parse_json_in_code_block(self):
        response = '```json\n[{"index": 0, "sql": "SELECT 1;"}]\n```'
        result = self.validator._parse_repair_response(response)
        assert len(result) == 1
        assert result[0]["index"] == 0

    def test_parse_raw_json(self):
        response = '[{"index": 0, "sql": "SELECT 1;"}]'
        result = self.validator._parse_repair_response(response)
        assert len(result) == 1

    def test_parse_invalid_json(self):
        result = self.validator._parse_repair_response("not json")
        assert result == []


class TestExtractTableNames:
    def test_simple_from(self):
        tables = SQLValidator._extract_table_names("SELECT * FROM orders;")
        assert tables == ["orders"]

    def test_from_with_join(self):
        sql = "SELECT * FROM orders o JOIN customers c ON o.cid = c.id"
        tables = SQLValidator._extract_table_names(sql)
        assert "orders" in tables
        assert "customers" in tables

    def test_multiple_joins(self):
        sql = (
            "SELECT * FROM orders "
            "LEFT JOIN customers ON orders.cid = customers.id "
            "INNER JOIN products ON orders.pid = products.id"
        )
        tables = SQLValidator._extract_table_names(sql)
        assert len(tables) == 3

    def test_schema_qualified(self):
        sql = "SELECT * FROM public.orders JOIN public.customers ON 1=1"
        tables = SQLValidator._extract_table_names(sql)
        assert "public.orders" in tables
        assert "public.customers" in tables

    def test_dedup(self):
        sql = "SELECT * FROM orders JOIN orders ON 1=1"
        tables = SQLValidator._extract_table_names(sql)
        assert len(tables) == 1

    def test_case_insensitive(self):
        sql = "select * from Orders JOIN CUSTOMERS on 1=1"
        tables = SQLValidator._extract_table_names(sql)
        assert len(tables) == 2


class TestExtractDbName:
    def test_standard_filename(self):
        assert SQLValidator._extract_db_name("output/sql/qs_dvdrental_pair.json") == "dvdrental"

    def test_underscore_in_name(self):
        assert SQLValidator._extract_db_name("qs_sakila_dvd_rental_pair.json") == "sakila_dvd_rental"

    def test_non_standard(self):
        assert SQLValidator._extract_db_name("some_other_file.json") == ""


class TestLoadTableMd:
    def test_load_existing_md(self, tmp_path):
        md_dir = tmp_path / "md"
        md_dir.mkdir()
        (md_dir / "testdb.public.orders.md").write_text("# orders\ncolumns...", encoding="utf-8")

        validator = SQLValidator(
            connector=FakeConnector(), config={}, md_dir=str(md_dir)
        )
        content = validator._load_table_md("orders", "testdb")
        assert "# orders" in content

    def test_load_schema_qualified(self, tmp_path):
        md_dir = tmp_path / "md"
        md_dir.mkdir()
        (md_dir / "testdb.myschema.orders.md").write_text("# orders", encoding="utf-8")

        validator = SQLValidator(
            connector=FakeConnector(), config={}, md_dir=str(md_dir)
        )
        content = validator._load_table_md("myschema.orders", "testdb")
        assert "# orders" in content

    def test_missing_md(self, tmp_path):
        md_dir = tmp_path / "md"
        md_dir.mkdir()

        validator = SQLValidator(
            connector=FakeConnector(), config={}, md_dir=str(md_dir)
        )
        assert validator._load_table_md("nonexistent", "testdb") == ""

    def test_no_md_dir(self):
        validator = SQLValidator(connector=FakeConnector(), config={})
        assert validator._load_table_md("orders", "testdb") == ""


class TestExtractRelevantRelationships:
    def test_extract_matching_sections(self, tmp_path):
        rel_dir = tmp_path / "rel"
        rel_dir.mkdir()
        rel_content = """# 表间关系
## 统计
### 1. public.orders.customer_id → public.customers.customer_id
- **类型**: 单列
- **关系类型**: foreign_key

### 2. public.film.language_id → public.language.language_id
- **类型**: 单列
- **关系类型**: foreign_key

### 3. public.orders.product_id → public.products.product_id
- **类型**: 单列
"""
        (rel_dir / "testdb.relationships_global.md").write_text(rel_content, encoding="utf-8")

        validator = SQLValidator(
            connector=FakeConnector(), config={}, rel_dir=str(rel_dir)
        )
        result = validator._extract_relevant_relationships(["orders", "customers"], "testdb")
        assert "orders.customer_id" in result
        assert "orders.product_id" in result
        assert "film.language_id" not in result

    def test_no_rel_dir(self):
        validator = SQLValidator(connector=FakeConnector(), config={})
        assert validator._extract_relevant_relationships(["orders"], "testdb") == ""

    def test_missing_rel_file(self, tmp_path):
        rel_dir = tmp_path / "rel"
        rel_dir.mkdir()
        validator = SQLValidator(
            connector=FakeConnector(), config={}, rel_dir=str(rel_dir)
        )
        assert validator._extract_relevant_relationships(["orders"], "testdb") == ""
