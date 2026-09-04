# -*- coding: utf-8 -*-
"""
Hello-Agents 感知记忆（PerceptualMemory）
对齐文档第八章 8.2.5（4）感知记忆

文档特点：
- 支持多模态数据（文本、图像、音频等）
- 跨模态相似性搜索
- 感知数据的语义理解

【简化实现说明】
文档采用模态分离的独立向量集合（perceptual_text/image/audio）+ CLIP/CLAP 专用编码器。
本项目按用户决策使用本地文本嵌入统一编码，所有模态共用一个集合，
通过 payload 的 modality 字段区分模态、按目标模态过滤检索。
文件路径等感知元数据存于 metadata。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import BaseMemory, MemoryConfig, MemoryItem
from ..embedding import get_text_embedder
from ..storage.qdrant_store import QdrantVectorStore

# 支持的模态
SUPPORTED_MODALITIES = ("text", "image", "audio", "video")


class PerceptualMemory(BaseMemory):
    """感知记忆实现（简化多模态）"""

    def __init__(self, config: Optional[MemoryConfig] = None, storage_backend=None):
        super().__init__(config, storage_backend)

        # 多模态编码器（简化：统一文本嵌入）
        self.text_embedder = get_text_embedder()
        self.vector_dim = self.text_embedder.dimension

        # 感知向量集合（独立于语义/情景集合）
        self.collection = "perceptual_vectors"
        self.vector_store = QdrantVectorStore(
            self.config.qdrant_url,
            self.config.qdrant_api_key,
            collection=self.collection,
            vector_size=self.vector_dim,
        )

    # ---------------- 添加 ----------------

    def add(self, memory_item: MemoryItem) -> str:
        """添加感知记忆

        metadata 约定：
        - modality: text / image / audio / video（默认 text）
        - file_path: 原始文件路径（图像/音频等）
        - description: 感知内容描述（图像/音频时作为嵌入文本）
        """
        memory_item.memory_type = "perceptual"
        modality = memory_item.metadata.get("modality", "text")
        file_path = memory_item.metadata.get("file_path", "")

        # 选择嵌入文本：图像/音频用描述，文本用内容本身
        embed_text = self._prepare_content(
            memory_item.content, modality, memory_item.metadata
        )
        vector = self.text_embedder.embed(embed_text)

        metadata = {
            "memory_id": memory_item.id,
            "content": memory_item.content,
            "memory_type": "perceptual",
            "modality": modality,
            "importance": memory_item.importance,
            "timestamp": memory_item.timestamp.isoformat(),
            "metadata": dict(memory_item.metadata),
            "user_id": memory_item.user_id,
            "session_id": memory_item.session_id,
        }
        if file_path:
            metadata["file_path"] = file_path

        self.vector_store.add_vectors(
            vectors=[vector],
            metadata=[metadata],
            ids=[memory_item.id],
            collection=self.collection,
        )
        return memory_item.id

    def _prepare_content(self, content: str, modality: str, metadata: dict) -> str:
        """选择用于嵌入的文本"""
        if modality in ("image", "audio", "video"):
            description = metadata.get("description") or metadata.get("caption")
            if description:
                return f"[{modality}] {description}"
        return content

    # ---------------- 检索 ----------------

    def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        """检索感知记忆

        支持同模态/跨模态检索：
        - target_modality: 限定返回的模态
        - query_modality:  查询内容的模态（默认 text）
        """
        user_id = kwargs.get("user_id")
        target_modality = kwargs.get("target_modality")
        query_modality = kwargs.get("query_modality", target_modality or "text")

        # 编码查询（简化：统一文本编码）
        query_vector = self._encode_data(query, query_modality)

        search_kwargs = {}
        if target_modality and target_modality != "all":
            search_kwargs["modality"] = target_modality

        hits = self.vector_store.search(
            query_vector,
            limit=limit * 2,
            user_id=user_id,
            memory_type="perceptual",
            collection=self.collection,
            **search_kwargs,
        )

        # 评分：向量相似度 × 重要性权重（文档同模态检索的融合逻辑）
        results = []
        for hit in hits:
            # importance 在 payload 顶层；嵌套 metadata 是感知元数据 dict
            importance = float(hit.get("importance", 0.5))
            importance_weight = 0.8 + (importance * 0.4)
            score = float(hit.get("score", 0.0)) * importance_weight
            results.append((score, self._create_memory_item(hit)))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def _encode_data(self, data: str, modality: str) -> List[float]:
        """编码查询数据（简化：所有模态统一文本编码）"""
        if modality in ("image", "audio", "video"):
            # 若传入路径或描述文本，直接嵌入
            return self.text_embedder.embed(data)
        return self.text_embedder.embed(data)

    def _create_memory_item(self, hit: Dict[str, Any]) -> MemoryItem:
        payload = hit.get("payload") or hit
        meta = hit.get("metadata") or {}  # 感知元数据（modality/file_path/description 等）
        return MemoryItem(
            id=str(hit.get("memory_id") or hit.get("id")),
            content=str(payload.get("content", "")),
            memory_type="perceptual",
            importance=float(payload.get("importance", 0.5)),
            timestamp=datetime.fromisoformat(payload.get("timestamp"))
            if payload.get("timestamp") else datetime.now(),
            metadata=dict(meta),
        )

    # ---------------- 其他接口 ----------------

    def remove(self, memory_id: str) -> bool:
        """删除感知记忆"""
        return self.vector_store.delete(memory_id, collection=self.collection)

    def clear(self) -> int:
        """清空感知记忆"""
        count = self.vector_store.count(collection=self.collection)
        self.vector_store.delete_by_filter(
            memory_type="perceptual", collection=self.collection
        )
        return count

    def count(self) -> int:
        """感知记忆总数"""
        return self.vector_store.count(collection=self.collection)

    def list_all(self) -> List[MemoryItem]:
        """列出全部感知记忆"""
        results = self.vector_store.list_all(
            memory_type="perceptual", collection=self.collection
        )
        return [self._create_memory_item(r) for r in results]
