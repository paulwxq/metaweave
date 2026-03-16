"""SQLExampleLoader 单元测试"""

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from metaweave.core.sql_rag.loader import SQLExampleLoader


class FakeEmbeddingService:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def get_embeddings(self, texts: List[str]) -> Dict[str, List[float]]:
        return {t: [0.1, 0.2, 0.3, 0.4] for t in texts}


class FakeMilvusClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.upsert_calls: List[List[Dict]] = []
        self.collections_created = []

    def connect(self) -> None:
        pass

    def ensure_collection(self, collection_name, schema, index_params, clean=False):
        self.collections_created.append({
            "name": collection_name,
            "clean": clean,
        })

    def upsert_batch(self, collection_name: str, data: List[Dict[str, Any]]) -> int:
        self.upsert_calls.append(data)
        return len(data)


def _write_metadata_config(tmp_path: Path) -> Path:
    cfg = {
        "embedding": {
            "active": "qwen",
            "providers": {"qwen": {"dimensions": 4}},
        },
        "vector_database": {
            "active": "milvus",
            "providers": {
                "milvus": {"host": "localhost", "port": 19530, "database": "nl2sql"}
            },
        },
        "database": {"database": "testdb"},
    }
    meta_path = tmp_path / "metadata_config.yaml"
    meta_path.write_text(yaml.dump(cfg), encoding="utf-8")
    return meta_path


def _write_input_file(tmp_path: Path, pairs=None) -> Path:
    if pairs is None:
        pairs = [
            {"question": "总订单数？", "sql": "SELECT COUNT(*) FROM orders;", "domain": "订单分析"},
            {"question": "客户列表？", "sql": "SELECT * FROM customers;", "domain": "客户管理"},
        ]
    input_file = tmp_path / "qs_testdb_pair.json"
    input_file.write_text(json.dumps(pairs, ensure_ascii=False), encoding="utf-8")
    return input_file


def _make_loader(tmp_path: Path, input_file=None, collection_name="test_coll"):
    meta_path = _write_metadata_config(tmp_path)
    if input_file is None:
        input_file = _write_input_file(tmp_path)

    config = {
        "metadata_config_file": str(meta_path),
        "sql_loader": {
            "input_file": str(input_file),
            "collection_name": collection_name,
            "options": {"batch_size": 10},
        },
    }
    return SQLExampleLoader(
        config,
        milvus_client_cls=FakeMilvusClient,
        embedding_service_cls=FakeEmbeddingService,
    )


class TestSQLExampleLoaderValidate:
    def test_validate_success(self, tmp_path):
        loader = _make_loader(tmp_path)
        assert loader.validate()
        assert loader._embedding_dim == 4
        assert loader._db_name == "testdb"

    def test_validate_missing_input_file(self, tmp_path):
        meta_path = _write_metadata_config(tmp_path)
        config = {
            "metadata_config_file": str(meta_path),
            "sql_loader": {
                "input_file": str(tmp_path / "nonexistent.json"),
                "collection_name": "test",
            },
        }
        loader = SQLExampleLoader(
            config,
            milvus_client_cls=FakeMilvusClient,
            embedding_service_cls=FakeEmbeddingService,
        )
        assert not loader.validate()

    def test_validate_missing_collection_name(self, tmp_path):
        meta_path = _write_metadata_config(tmp_path)
        input_file = _write_input_file(tmp_path)
        config = {
            "metadata_config_file": str(meta_path),
            "sql_loader": {
                "input_file": str(input_file),
                "collection_name": "",
            },
        }
        loader = SQLExampleLoader(
            config,
            milvus_client_cls=FakeMilvusClient,
            embedding_service_cls=FakeEmbeddingService,
        )
        assert not loader.validate()

    def test_validate_no_input_file_config(self, tmp_path):
        meta_path = _write_metadata_config(tmp_path)
        config = {
            "metadata_config_file": str(meta_path),
            "sql_loader": {"collection_name": "test"},
        }
        loader = SQLExampleLoader(
            config,
            milvus_client_cls=FakeMilvusClient,
            embedding_service_cls=FakeEmbeddingService,
        )
        assert not loader.validate()


class TestSQLExampleLoaderLoad:
    def test_load_basic(self, tmp_path):
        loader = _make_loader(tmp_path)
        assert loader.validate()
        result = loader.load()
        assert result["success"]
        assert result["loaded"] == 2
        assert result["skipped"] == 0
        assert result["total"] == 2

        # 验证 Milvus upsert 被调用
        milvus = loader._milvus_client
        assert len(milvus.upsert_calls) == 1
        rows = milvus.upsert_calls[0]
        assert len(rows) == 2

        # 验证数据结构
        row = rows[0]
        assert "example_id" in row
        assert row["example_id"].startswith("testdb:")
        assert "question_sql" in row
        assert "domain" in row
        assert "embedding" in row
        assert "updated_at" in row

        # domain 单独存储
        assert row["domain"] == "订单分析"

        # question_sql 不含 domain
        qs = json.loads(row["question_sql"])
        assert "question" in qs
        assert "sql" in qs
        assert "domain" not in qs

    def test_load_with_clean(self, tmp_path):
        loader = _make_loader(tmp_path)
        assert loader.validate()
        result = loader.load(clean=True)
        assert result["success"]

        milvus = loader._milvus_client
        assert milvus.collections_created[0]["clean"] is True

    def test_load_empty_file(self, tmp_path):
        input_file = _write_input_file(tmp_path, pairs=[])
        loader = _make_loader(tmp_path, input_file=input_file)
        assert loader.validate()
        result = loader.load()
        assert result["success"]
        assert result["loaded"] == 0


class TestComputeExampleId:
    def test_deterministic(self):
        id1 = SQLExampleLoader.compute_example_id("db", "Q", "S")
        id2 = SQLExampleLoader.compute_example_id("db", "Q", "S")
        assert id1 == id2
        assert id1.startswith("db:")
        assert len(id1.split(":")[1]) == 8

    def test_different_content_different_id(self):
        id1 = SQLExampleLoader.compute_example_id("db", "Q1", "S1")
        id2 = SQLExampleLoader.compute_example_id("db", "Q2", "S2")
        assert id1 != id2

    def test_different_db_different_id(self):
        id1 = SQLExampleLoader.compute_example_id("db1", "Q", "S")
        id2 = SQLExampleLoader.compute_example_id("db2", "Q", "S")
        assert id1 != id2


class TestBuildSchema:
    def test_schema_fields(self, tmp_path):
        loader = _make_loader(tmp_path)
        loader.validate()

        # _build_schema 需要 pymilvus，但我们可以 mock 它
        from unittest.mock import MagicMock, patch

        mock_field = MagicMock()
        mock_schema = MagicMock()
        mock_dtype = MagicMock()
        mock_dtype.VARCHAR = "VARCHAR"
        mock_dtype.FLOAT_VECTOR = "FLOAT_VECTOR"
        mock_dtype.INT64 = "INT64"

        with patch(
            "metaweave.core.sql_rag.loader._lazy_import_milvus",
            return_value=(mock_field, mock_schema, mock_dtype),
        ):
            schema, index_params = loader._build_schema()

        # 应创建 5 个字段（example_id, question_sql, embedding, domain, updated_at）
        assert mock_field.call_count == 5
        # 索引参数
        assert index_params["index_type"] == "HNSW"
        assert index_params["metric_type"] == "COSINE"
