"""SQL Example 向量化加载器（Milvus）

将 Question-SQL JSON 文件向量化后加载到 Milvus，
仅对 question 做向量化，question_sql 合并为 JSON 串存储。
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from metaweave.core.loaders.base import BaseLoader
from services.config_loader import ConfigLoader
from metaweave.services.embedding_service import EmbeddingService
from metaweave.services.vector_db.milvus_client import MilvusClient

logger = logging.getLogger(__name__)


def _lazy_import_milvus():
    """延迟导入 pymilvus"""
    from pymilvus import CollectionSchema, DataType, FieldSchema

    return FieldSchema, CollectionSchema, DataType


class SQLExampleLoader(BaseLoader):
    """SQL Example 向量化加载器"""

    def __init__(
        self,
        config: Dict[str, Any],
        milvus_client_cls: Type[MilvusClient] = MilvusClient,
        embedding_service_cls: Type[EmbeddingService] = EmbeddingService,
    ):
        super().__init__(config)
        self.loader_cfg = self.config.get("sql_loader", {})
        self.input_file = self.loader_cfg.get("input_file", "")
        self.collection_name = str(self.loader_cfg.get("collection_name", "")).strip()
        self.options = self.loader_cfg.get("options", {})
        self.batch_size = self.options.get("batch_size", 50)

        # 读取 metadata_config 以获取 embedding 和 vector_database 配置
        self.metadata_config_path = self.config.get(
            "metadata_config_file", "configs/metadata_config.yaml"
        )

        self._milvus_client_cls = milvus_client_cls
        self._embedding_service_cls = embedding_service_cls
        self._milvus_client: Optional[MilvusClient] = None
        self._embedding_service: Optional[EmbeddingService] = None
        self._embedding_dim: int = 1024
        self._db_name: str = ""
        self._metadata_config: Dict[str, Any] = {}

    def validate(self) -> bool:
        """验证配置和依赖服务"""
        # 检查输入文件
        if self.input_file:
            input_path = Path(self.input_file)
            if not input_path.exists():
                logger.error("输入文件不存在: %s", self.input_file)
                return False
        else:
            logger.error("未配置 sql_loader.input_file")
            return False

        # 检查 collection 名称
        if not self.collection_name:
            logger.error("未配置 sql_loader.collection_name")
            return False

        # 加载 metadata_config
        try:
            meta_path = Path(self.metadata_config_path)
            if not meta_path.exists():
                logger.error("metadata_config 不存在: %s", self.metadata_config_path)
                return False
            self._metadata_config = ConfigLoader(str(meta_path)).load()
        except Exception:
            logger.exception("加载 metadata_config 失败")
            return False

        # 获取 embedding 维度
        embedding_config = self._metadata_config.get("embedding", {})
        active_provider = embedding_config.get("active", "qwen")
        provider_config = (
            embedding_config.get("providers", {}).get(active_provider, {})
        )
        self._embedding_dim = provider_config.get("dimensions", 1024)

        # 获取数据库名称（用于主键生成）
        db_config = self._metadata_config.get("database", {})
        self._db_name = db_config.get("database", "unknown")

        # 初始化 embedding service
        try:
            self._embedding_service = self._embedding_service_cls(embedding_config)
        except Exception:
            logger.exception("初始化 EmbeddingService 失败")
            return False

        # 初始化 Milvus client
        try:
            vector_config = self._metadata_config.get("vector_database", {})
            milvus_config = vector_config.get("providers", {}).get("milvus", {})
            self._milvus_client = self._milvus_client_cls(milvus_config)
            self._milvus_client.connect()
        except Exception:
            logger.exception("初始化 MilvusClient 失败")
            return False

        logger.info("SQLExampleLoader 验证通过")
        return True

    def load(self, clean: bool = False) -> Dict[str, Any]:
        """执行加载"""
        start_time = time.time()

        # 读取输入文件
        with open(self.input_file, "r", encoding="utf-8") as f:
            pairs = json.load(f)

        logger.info("读取 %d 条 Question-SQL from %s", len(pairs), self.input_file)

        # 确保 Collection 存在
        schema, index_params = self._build_schema()
        self._milvus_client.ensure_collection(
            self.collection_name, schema, index_params, clean=clean
        )

        # 分批处理
        loaded = 0
        skipped = 0

        for batch_start in range(0, len(pairs), self.batch_size):
            batch = pairs[batch_start : batch_start + self.batch_size]
            batch_loaded, batch_skipped = self._process_batch(batch)
            loaded += batch_loaded
            skipped += batch_skipped

        execution_time = time.time() - start_time
        result = {
            "success": True,
            "message": f"加载 {loaded} 条, 跳过 {skipped} 条",
            "loaded": loaded,
            "skipped": skipped,
            "total": len(pairs),
            "execution_time": execution_time,
        }
        logger.info(
            "SQLExampleLoader 完成: %s (%.2fs)", result["message"], execution_time
        )
        return result

    def _build_schema(self):
        """构建 Milvus Collection Schema"""
        FieldSchema, CollectionSchema, DataType = _lazy_import_milvus()

        fields = [
            FieldSchema(
                name="example_id",
                dtype=DataType.VARCHAR,
                max_length=256,
                is_primary=True,
                auto_id=False,
            ),
            FieldSchema(
                name="question_sql",
                dtype=DataType.VARCHAR,
                max_length=16384,
            ),
            FieldSchema(
                name="embedding",
                dtype=DataType.FLOAT_VECTOR,
                dim=self._embedding_dim,
            ),
            FieldSchema(
                name="domain",
                dtype=DataType.VARCHAR,
                max_length=256,
            ),
            FieldSchema(
                name="updated_at",
                dtype=DataType.INT64,
            ),
        ]
        schema = CollectionSchema(fields=fields, description="SQL Example Embeddings")

        index_params = {
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 200},
        }
        return schema, index_params

    def _process_batch(self, batch: List[Dict]) -> tuple:
        """处理一个批次的 Question-SQL"""
        questions = [p.get("question", "") for p in batch]

        # 获取 embeddings（带重试）
        embeddings = None
        for attempt in range(3):
            try:
                embeddings = self._embedding_service.get_embeddings(questions)
                break
            except Exception:
                if attempt < 2:
                    logger.warning("Embedding 服务调用失败，重试 %d/2", attempt + 1)
                else:
                    logger.exception("Embedding 服务调用失败，跳过批次")
                    return 0, len(batch)

        if not embeddings:
            return 0, len(batch)

        # 构建 Milvus 数据
        rows = []
        skipped = 0
        now_ts = int(time.time())

        for pair in batch:
            question = pair.get("question", "")
            sql = pair.get("sql", "")
            domain = pair.get("domain", "")

            embedding = embeddings.get(question)
            if embedding is None:
                logger.warning("question 未找到对应 embedding，跳过: %s", question[:50])
                skipped += 1
                continue

            # question_sql JSON 串（不含 domain）
            question_sql = json.dumps(
                {"question": question, "sql": sql}, ensure_ascii=False
            )
            if len(question_sql) > 16000:
                logger.warning("question_sql 超过 16000 字符，跳过: %s", question[:50])
                skipped += 1
                continue

            # 内容哈希主键
            content = question + sql
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
            example_id = f"{self._db_name}:{content_hash}"

            rows.append({
                "example_id": example_id,
                "question_sql": question_sql,
                "domain": domain,
                "embedding": embedding.tolist()
                if hasattr(embedding, "tolist")
                else list(embedding),
                "updated_at": now_ts,
            })

        # upsert
        if rows:
            try:
                self._milvus_client.upsert_batch(self.collection_name, rows)
            except Exception:
                logger.exception("Milvus upsert 失败，批次 %d 条", len(rows))
                return 0, len(batch)

        return len(rows), skipped

    @staticmethod
    def compute_example_id(db_name: str, question: str, sql: str) -> str:
        """计算 example_id（供外部使用）"""
        content = question + sql
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
        return f"{db_name}:{content_hash}"
