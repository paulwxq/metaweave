"""名称相似度服务

统一改造（doc 15）：
- 移除 `method: string`（SequenceMatcher）业务路径，`method` 唯一取值为
  `embedding`；仅保留“同名短路”（本地字符串比较，不发 API）；
- 新增中文注释 embedding 通道（`comment_channel`），独立配置模型/缓存/阈值，
  供候选生成闸门（3.4/3.5）与评分维度 `comment_similarity`（3.11）共用；
- 注释通道维护"低信息量注释黑名单"（`generic_comment_blacklist`），命中黑名单
  的注释视为无信息量，注释闸直接不通过。
"""

import asyncio
import logging
from collections import OrderedDict
from typing import Dict, List, Optional

import numpy as np

from metaweave.services.embedding_service import EmbeddingService
from metaweave.utils.logger import get_metaweave_logger

logger = get_metaweave_logger("relationships.name_similarity")


class InvalidNameSimilarityConfig(ValueError):
    """显式非法配置（如 method: string）导致的初始化失败。

    与"无 embedding 环境"（EmbeddingService 因缺少 active/providers/model/
    api_key 等而抛出的 ValueError）区分开：后者属于 doc 15 第5节的降级语义，
    调用方（pipeline.py）可以捕获并降级；前者是 doc 4.3 明确要求"检测到即
    报错、不静默兼容"的旧配置项，调用方必须让它继续向上传播，不能被吞掉。
    """


class LRUCache:
    """简单 LRU 缓存，容量受限。"""

    def __init__(self, capacity: int):
        self.cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.capacity = max(1, capacity)

    def get(self, key: str) -> Optional[np.ndarray]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value: np.ndarray) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)


class CommentSimilarityChannel:
    """中文注释 embedding 通道（独立配置与缓存，见 doc 15 §3.5）"""

    def __init__(self, comment_channel_config: dict, embedding_config: dict):
        self.config = comment_channel_config or {}
        self.enabled = bool(self.config.get("enabled", True))

        method = (self.config.get("method") or "embedding").lower()
        if method != "embedding":
            raise InvalidNameSimilarityConfig(
                f"relationships.name_similarity.comment_channel.method 只支持 'embedding'，"
                f"检测到不支持的取值: {method!r}。SequenceMatcher 路径已废弃（doc 15 2.4）。"
            )

        cache_size = int(self.config.get("cache_size", 5000) or 5000)
        self.cache = LRUCache(cache_size)

        self.generic_blacklist = {
            self._normalize(w) for w in (self.config.get("generic_comment_blacklist") or [])
        }

        self.embedding_service: Optional[EmbeddingService] = None
        if self.enabled:
            # 首版默认复用全局 embedding 配置；注释通道自身的 method/cache_size
            # 等字段通过 self.config 传给 EmbeddingService 作为 name_similarity_config
            self.embedding_service = EmbeddingService(embedding_config, self.config)
            logger.info("注释相似度通道已启用，缓存容量=%s", cache_size)
        else:
            logger.info("注释相似度通道已禁用")

    @staticmethod
    def _normalize(text: str) -> str:
        return (text or "").strip()

    def is_generic(self, comment: str) -> bool:
        """判断注释是否为低信息量通用注释（命中黑名单）"""
        norm = self._normalize(comment)
        return norm in self.generic_blacklist if norm else False

    def is_usable(self, comment: Optional[str]) -> bool:
        """注释是否可用于比较：非空、启用了通道、不在黑名单中"""
        if not self.enabled or not self.embedding_service:
            return False
        norm = self._normalize(comment)
        if not norm:
            return False
        return not self.is_generic(norm)

    def _get_embedding(self, norm_text: str) -> np.ndarray:
        cached = self.cache.get(norm_text)
        if cached is not None:
            return cached
        if not self.embedding_service:
            raise RuntimeError("注释通道 EmbeddingService 未启用但尝试获取向量")
        embedding = self.embedding_service.get_embedding(norm_text)
        self.cache.put(norm_text, embedding)
        return embedding

    async def _aget_embedding(self, norm_text: str) -> np.ndarray:
        cached = self.cache.get(norm_text)
        if cached is not None:
            return cached
        if not self.embedding_service:
            raise RuntimeError("注释通道 EmbeddingService 未启用但尝试获取向量")
        embedding = await self.embedding_service.aget_embedding(norm_text)
        self.cache.put(norm_text, embedding)
        return embedding

    def compare(self, comment_a: Optional[str], comment_b: Optional[str]) -> Optional[float]:
        """比较两条注释的相似度。

        Returns:
            0~1 的相似度；若任一注释不可用（空/黑名单/通道未启用）返回 None，
            调用方据此判断注释闸/维度是否可用（见 3.4/3.11 的按列对回退语义）。
        """
        if not self.is_usable(comment_a) or not self.is_usable(comment_b):
            return None

        norm_a, norm_b = self._normalize(comment_a), self._normalize(comment_b)
        if norm_a == norm_b:
            return 1.0

        vec_a = self._get_embedding(norm_a)
        vec_b = self._get_embedding(norm_b)
        denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
        if denom == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / denom)

    async def acompare(self, comment_a: Optional[str], comment_b: Optional[str]) -> Optional[float]:
        if not self.is_usable(comment_a) or not self.is_usable(comment_b):
            return None

        norm_a, norm_b = self._normalize(comment_a), self._normalize(comment_b)
        if norm_a == norm_b:
            return 1.0

        vec_a, vec_b = await asyncio.gather(
            self._aget_embedding(norm_a),
            self._aget_embedding(norm_b),
        )
        denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
        if denom == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / denom)


class NameSimilarityService:
    """统一名称相似度服务（英文名 embedding 通道 + 同名短路）

    doc 15 改造：method 唯一取值为 embedding，不再支持 SequenceMatcher 路径。
    """

    def __init__(self, name_similarity_config: dict, embedding_config: dict):
        self.config = name_similarity_config or {}
        self.embedding_config = embedding_config or {}

        method = (self.config.get("method") or "embedding").lower()
        if method != "embedding":
            raise InvalidNameSimilarityConfig(
                f"relationships.name_similarity.method 只支持 'embedding'，"
                f"检测到不支持的取值: {method!r}。SequenceMatcher 路径已废弃（doc 15 2.4）。"
            )
        self.method = method

        cache_size = int(self.config.get("cache_size", 5000) or 5000)
        self.cache = LRUCache(cache_size)

        self.embedding_service: Optional[EmbeddingService] = EmbeddingService(
            self.embedding_config, self.config
        )
        logger.info("名称相似度将使用 Embedding，缓存容量=%s", cache_size)

        # 注释通道（生成闸门与评分维度共用，见 3.5/3.11）
        comment_channel_config = self.config.get("comment_channel", {})
        self.comment_channel = CommentSimilarityChannel(comment_channel_config, self.embedding_config)

    @staticmethod
    def _normalize(name: str) -> str:
        return (name or "").strip().lower()

    def _get_embedding(self, norm_name: str) -> np.ndarray:
        cached = self.cache.get(norm_name)
        if cached is not None:
            return cached

        if not self.embedding_service:
            raise RuntimeError("EmbeddingService 未启用但尝试获取向量")

        embedding = self.embedding_service.get_embedding(norm_name)
        self.cache.put(norm_name, embedding)
        return embedding

    def compare_pair(self, name_a: str, name_b: str) -> float:
        """比较单个字段名相似度（同名短路，不发 API）"""
        norm_a, norm_b = self._normalize(name_a), self._normalize(name_b)
        if norm_a == norm_b:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Embedding name similarity: '%s' vs '%s' -> 1.0000 (exact match)", norm_a, norm_b)
            return 1.0

        vec_a = self._get_embedding(norm_a)
        vec_b = self._get_embedding(norm_b)

        denom = (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        if denom == 0:
            return 0.0
        sim = float(np.dot(vec_a, vec_b) / denom)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Embedding name similarity: '%s' vs '%s' -> %.4f", norm_a, norm_b, sim)
        return sim

    def compare_columns(self, source_cols: list, target_cols: list) -> float:
        """多列配对平均相似度"""
        if len(source_cols) != len(target_cols):
            return 0.0

        total = 0.0
        for a, b in zip(source_cols, target_cols):
            total += self.compare_pair(a, b)
        return total / len(source_cols) if source_cols else 0.0

    # === 异步接口，复用同一缓存 ===
    async def acompare_pair(self, name_a: str, name_b: str) -> float:
        norm_a, norm_b = self._normalize(name_a), self._normalize(name_b)
        if norm_a == norm_b:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Embedding name similarity (async): '%s' vs '%s' -> 1.0000 (exact match)", norm_a, norm_b)
            return 1.0

        vec_a, vec_b = await asyncio.gather(
            self._aget_embedding(norm_a),
            self._aget_embedding(norm_b),
        )

        denom = (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        if denom == 0:
            return 0.0
        sim = float(np.dot(vec_a, vec_b) / denom)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Embedding name similarity (async): '%s' vs '%s' -> %.4f", norm_a, norm_b, sim)
        return sim

    async def acompare_columns(self, source_cols: list, target_cols: list) -> float:
        if len(source_cols) != len(target_cols):
            return 0.0
        sims = await asyncio.gather(
            *[self.acompare_pair(a, b) for a, b in zip(source_cols, target_cols)]
        )
        return float(sum(sims) / len(sims)) if sims else 0.0

    async def _aget_embedding(self, norm_name: str) -> np.ndarray:
        cached = self.cache.get(norm_name)
        if cached is not None:
            return cached
        if not self.embedding_service:
            raise RuntimeError("EmbeddingService 未启用但尝试获取向量")
        embedding = await self.embedding_service.aget_embedding(norm_name)
        self.cache.put(norm_name, embedding)
        return embedding

    # === 注释相似度（转发到 comment_channel，供闸门与评分维度共用） ===
    def compare_comment_pair(self, comment_a: Optional[str], comment_b: Optional[str]) -> Optional[float]:
        """比较单对注释相似度，任一不可用返回 None"""
        return self.comment_channel.compare(comment_a, comment_b)

    async def acompare_comment_pair(
        self, comment_a: Optional[str], comment_b: Optional[str]
    ) -> Optional[float]:
        return await self.comment_channel.acompare(comment_a, comment_b)

    def compare_comment_columns(
        self, source_comments: List[Optional[str]], target_comments: List[Optional[str]]
    ) -> Optional[float]:
        """多列配对注释相似度平均值；任一列对不可用则整体返回 None（按列对回退语义由调用方处理）"""
        if len(source_comments) != len(target_comments):
            return None
        sims = []
        for a, b in zip(source_comments, target_comments):
            sim = self.compare_comment_pair(a, b)
            if sim is None:
                return None
            sims.append(sim)
        return sum(sims) / len(sims) if sims else None
