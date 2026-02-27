from types import SimpleNamespace

import services.vector_db.milvus_client as milvus_module
from services.vector_db.milvus_client import MilvusClient


class _FakeField:
    def __init__(self, name, is_primary=False, auto_id=False):
        self.name = name
        self.is_primary = is_primary
        self.auto_id = auto_id


class _FakeCollection:
    registry = {}

    def __init__(self, name, using=None):
        cfg = self.registry[name]
        self._cfg = cfg
        self.schema = SimpleNamespace(fields=cfg["fields"])
        self.indexes = []

    def insert(self, entities):
        self._cfg["insert_entities"] = entities
        count = len(entities[0]) if entities else 0
        return SimpleNamespace(primary_keys=list(range(count)))

    def flush(self):
        return None


def _patch_lazy_import(monkeypatch):
    monkeypatch.setattr(
        milvus_module,
        "_lazy_import_milvus",
        lambda: (None, None, None, None, _FakeCollection, None, None),
    )


def test_insert_batch_skips_auto_id_primary_field(monkeypatch):
    _patch_lazy_import(monkeypatch)
    _FakeCollection.registry = {
        "dim_value_embeddings": {
            "fields": [
                _FakeField("id", is_primary=True, auto_id=True),
                _FakeField("table_name"),
                _FakeField("col_name"),
                _FakeField("col_value"),
                _FakeField("embedding"),
                _FakeField("update_ts"),
            ]
        }
    }

    client = MilvusClient(config={})
    inserted = client.insert_batch(
        "dim_value_embeddings",
        [
            {
                "id": 123,
                "table_name": "public.actor",
                "col_name": "first_name",
                "col_value": "PENELOPE",
                "embedding": [0.1, 0.2],
                "update_ts": 1700000000,
            }
        ],
    )

    assert inserted == 1
    entities = _FakeCollection.registry["dim_value_embeddings"]["insert_entities"]
    assert len(entities) == 5
    assert entities[0] == ["public.actor"]  # table_name


def test_insert_batch_keeps_non_auto_primary_field(monkeypatch):
    _patch_lazy_import(monkeypatch)
    _FakeCollection.registry = {
        "table_schema_embeddings": {
            "fields": [
                _FakeField("object_id", is_primary=True, auto_id=False),
                _FakeField("object_type"),
            ]
        }
    }

    client = MilvusClient(config={})
    inserted = client.insert_batch(
        "table_schema_embeddings",
        [{"object_id": "public.actor", "object_type": "table"}],
    )

    assert inserted == 1
    entities = _FakeCollection.registry["table_schema_embeddings"]["insert_entities"]
    assert len(entities) == 2
    assert entities[0] == ["public.actor"]  # object_id
