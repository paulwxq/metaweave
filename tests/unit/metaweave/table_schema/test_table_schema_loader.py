import json
from pathlib import Path
from typing import Any, Dict, List

from metaweave.core.loaders.table_schema_loader import TableSchemaLoader


class FakeEmbeddingService:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def get_embeddings(self, texts: List[str]) -> Dict[str, List[float]]:
        # 简单返回定长向量
        return {t: [0.1, 0.2, 0.3, 0.4] for t in texts}


class FakeMilvusClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.insert_calls: int = 0
        self.upsert_calls: int = 0

    def test_connection(self) -> bool:
        return True

    def connect(self) -> None:
        return None

    def ensure_collection(self, **kwargs) -> None:
        return None

    def insert_batch(self, collection_name: str, data: List[Dict[str, Any]]) -> int:
        self.insert_calls += 1
        return len(data)

    def upsert_batch(self, collection_name: str, data: List[Dict[str, Any]]) -> int:
        self.upsert_calls += 1
        return len(data)


def _write_metadata_config(tmp_path: Path) -> Path:
    cfg = {
        "embedding": {
            "active": "qwen",
            "providers": {"qwen": {"dimensions": 4}},
        },
        "vector_database": {
            "active": "milvus",
            "providers": {"milvus": {"host": "localhost", "port": 19530, "database": "nl2sql"}},
        },
    }
    meta_path = tmp_path / "metadata_config.yaml"
    meta_path.write_text(json.dumps(cfg), encoding="utf-8")
    return meta_path


def _write_md_and_json(tmp_path: Path) -> None:
    md_dir = tmp_path / "md"
    json_dir = tmp_path / "json"
    md_dir.mkdir()
    json_dir.mkdir()

    md_content = """# public.dim_company（公司维表）
## 字段列表：
- company_id (integer(32)) - 公司ID（主键） [示例: 1, 2]
- company_name (character varying(200)) - 公司名称，唯一 [示例: 京东便利, 喜士多]
"""
    (md_dir / "public.dim_company.md").write_text(md_content, encoding="utf-8")

    json_content = {
        "table_profile": {"table_category": "dim"},
        "column_profiles": {
            "company_id": {"data_type": "integer"},
            "company_name": {"data_type": "varchar"},
            "created_at": {"data_type": "timestamp"},
        },
    }
    (json_dir / "public.dim_company.json").write_text(
        json.dumps(json_content), encoding="utf-8"
    )


def test_loader_clean_uses_insert(tmp_path):
    meta_cfg = _write_metadata_config(tmp_path)
    _write_md_and_json(tmp_path)

    config = {
        "metadata_config_file": str(meta_cfg),
        "table_schema_loader": {
            "md_directory": str(tmp_path / "md"),
            "json_llm_directory": str(tmp_path / "json"),
            "collection_name": "table_schema_embeddings",
            "options": {"batch_size": 2},
        },
    }

    loader = TableSchemaLoader(
        config,
        milvus_client_cls=FakeMilvusClient,
        embedding_service_cls=FakeEmbeddingService,
    )

    assert loader.validate()
    result = loader.load(clean=True)

    assert result["success"] is True
    assert result["objects_loaded"] > 0
    # 确认 clean 模式调用 insert
    assert loader._milvus_client.insert_calls >= 1  # type: ignore[attr-defined]
    assert loader._milvus_client.upsert_calls == 0  # type: ignore[attr-defined]


def test_loader_incremental_uses_upsert(tmp_path):
    meta_cfg = _write_metadata_config(tmp_path)
    _write_md_and_json(tmp_path)

    config = {
        "metadata_config_file": str(meta_cfg),
        "table_schema_loader": {
            "md_directory": str(tmp_path / "md"),
            "json_llm_directory": str(tmp_path / "json"),
            "collection_name": "table_schema_embeddings",
            "options": {"batch_size": 2},
        },
    }

    loader = TableSchemaLoader(
        config,
        milvus_client_cls=FakeMilvusClient,
        embedding_service_cls=FakeEmbeddingService,
    )

    assert loader.validate()
    result = loader.load(clean=False)

    assert result["success"] is True
    assert result["objects_loaded"] > 0
    # 确认增量模式调用 upsert
    assert loader._milvus_client.upsert_calls >= 1  # type: ignore[attr-defined]
    assert loader._milvus_client.insert_calls == 0  # type: ignore[attr-defined]


def test_loader_validate_fails_when_collection_name_missing(tmp_path):
    meta_cfg = _write_metadata_config(tmp_path)
    _write_md_and_json(tmp_path)

    config = {
        "metadata_config_file": str(meta_cfg),
        "table_schema_loader": {
            "md_directory": str(tmp_path / "md"),
            "json_llm_directory": str(tmp_path / "json"),
            "options": {"batch_size": 2},
        },
    }

    loader = TableSchemaLoader(
        config,
        milvus_client_cls=FakeMilvusClient,
        embedding_service_cls=FakeEmbeddingService,
    )

    assert loader.validate() is False


def test_loader_matches_json_by_md_filename(tmp_path):
    meta_cfg = _write_metadata_config(tmp_path)
    md_dir = tmp_path / "md"
    json_dir = tmp_path / "json"
    md_dir.mkdir()
    json_dir.mkdir()

    md_file = md_dir / "dvdrental.public.actor.md"
    md_file.write_text(
        """# public.actor（演员表）
## 字段列表：
- actor_id (integer(32)) - 演员ID（主键）
""",
        encoding="utf-8",
    )
    (json_dir / "dvdrental.public.actor.json").write_text(
        json.dumps(
            {
                "table_profile": {"table_category": "dim"},
                "column_profiles": {"created_at": {"data_type": "timestamp"}},
            }
        ),
        encoding="utf-8",
    )

    config = {
        "metadata_config_file": str(meta_cfg),
        "table_schema_loader": {
            "md_directory": str(md_dir),
            "json_llm_directory": str(json_dir),
            "collection_name": "table_schema_embeddings",
        },
    }
    loader = TableSchemaLoader(
        config,
        milvus_client_cls=FakeMilvusClient,
        embedding_service_cls=FakeEmbeddingService,
    )

    objects = loader._load_table_objects(md_file)
    table_obj = next(obj for obj in objects if obj.object_type == "table")

    assert table_obj.object_id == "dvdrental.public.actor"
    assert table_obj.table_category == "dim"
    assert table_obj.time_col_hint == "created_at"
