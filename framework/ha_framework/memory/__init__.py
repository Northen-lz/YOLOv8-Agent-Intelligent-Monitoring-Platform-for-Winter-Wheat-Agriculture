# -*- coding: utf-8 -*-
"""
Hello-Agents 记忆系统（对齐文档第八章）
- base.py      MemoryItem / MemoryConfig / BaseMemory
- embedding.py 统一嵌入服务（本地 transformer + TFIDF 兜底）
- storage/     SQLite / Qdrant / Neo4j 存储后端
- types/       四种记忆类型
- rag/         RAG 系统
"""

from .base import BaseMemory, MemoryConfig, MemoryItem
from .manager import MemoryManager
from .embedding import (
    TEXT_EMBEDDING_DIMENSION,
    BaseEmbeddingModel,
    LocalTransformerEmbedding,
    TFIDFEmbedding,
    create_embedding_model_with_fallback,
    embed_query,
    get_text_embedder,
)

__all__ = [
    "MemoryItem",
    "MemoryConfig",
    "BaseMemory",
    "MemoryManager",
    "BaseEmbeddingModel",
    "LocalTransformerEmbedding",
    "TFIDFEmbedding",
    "create_embedding_model_with_fallback",
    "get_text_embedder",
    "embed_query",
    "TEXT_EMBEDDING_DIMENSION",
]
