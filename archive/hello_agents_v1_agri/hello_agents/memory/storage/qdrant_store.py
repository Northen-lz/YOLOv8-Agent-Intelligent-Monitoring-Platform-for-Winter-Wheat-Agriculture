# -*- coding: utf-8 -*-
"""
Hello-Agents Qdrant 向量存储
对齐文档第八章 8.2 存储后端层：QdrantVectorStore（高性能语义检索）

职责：
- 连接 Qdrant / 创建或复用集合（cosine 距离）
- 向量 + 结构化 payload 存储
- 语义检索（支持 user_id / memory_type 过滤，用户隔离）
- 按记忆 ID 删除

对齐文档接口：
- add_vectors(vectors, metadata, ids)  批量添加
- search(query_vector, limit, user_id) 检索，返回含 score/metadata 的命中列表

日志对齐文档（PDF 页 235）：
✅ 成功连接到Qdrant服务: {url}
✅ 使用现有Qdrant集合: {collection}
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient, models

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Qdrant 向量存储"""

    def __init__(
            self,
            url: Optional[str] = None,
            api_key: Optional[str] = None,
            collection: Optional[str] = None,
            vector_size: Optional[int] = None,
            distance: str = "cosine",
            timeout: Optional[int] = None,
    ):
        from ..base import MemoryConfig
        cfg = MemoryConfig()
        self.url = url or cfg.qdrant_url
        self.api_key = api_key if api_key is not None else cfg.qdrant_api_key
        self.collection = collection or cfg.qdrant_collection
        self.vector_size = vector_size or cfg.qdrant_vector_size
        self.distance = distance
        self.timeout = timeout or 30

        self.client = QdrantClient(
            url=self.url,
            api_key=self.api_key or None,
            timeout=self.timeout,
        )
        self.connected = True
        self._connect()
        self._ensure_collection(self.collection, self.vector_size)

    # ---------------- 初始化 ----------------

    def _connect(self):
        try:
            # 简单连通性探测（集合列表）
            self.client.get_collections()
            print(f"✅ 成功连接到Qdrant服务: {self.url}")
            self.connected = True
        except Exception as e:
            # 容错：Qdrant 未启动时不再 raise（否则整站起不来），
            # 标记为未连接，具体操作返回友好错误提示。
            self.connected = False
            print(f"⚠️ Qdrant连接失败({self.url})，向量操作将降级为不可用: {e}")
            logger.warning("Qdrant连接失败（容错处理，后续操作将返回错误提示）")

    def _ensure_collection(self, name: str, vector_size: int):
        """创建或复用集合（未连接时跳过，避免二次报错）"""
        if not self.connected:
            return
        if self.client.collection_exists(name):
            print(f"✅ 使用现有Qdrant集合: {name}")
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"✅ 创建Qdrant集合: {name} (size={vector_size}, {self.distance})")

    def _require_connected(self):
        """未连接时抛出明确错误（供调用方 catch 后给出友好提示）"""
        if not self.connected:
            raise RuntimeError(
                f"Qdrant 服务未连接({self.url})，该操作不可用。"
                "请先启动 Qdrant（如 docker run -p 6333:6333 qdrant/qdrant）。")

    # ---------------- 写入 ----------------

    def add_vectors(
            self,
            vectors: List[List[float]],
            metadata: Optional[List[Dict[str, Any]]] = None,
            ids: Optional[List[str]] = None,
            collection: Optional[str] = None,
            **extra_payload,
    ) -> List[str]:
        """
        批量添加向量（对齐文档接口 add_vectors(vectors, metadata, ids)）
        metadata 中可含 user_id / session_id 等，用于用户隔离过滤。
        """
        name = collection or self.collection
        self._require_connected()
        if metadata is not None and len(vectors) != len(metadata):
            raise ValueError("vectors 与 metadata 长度必须一致")
        if ids is not None and len(vectors) != len(ids):
            raise ValueError("vectors 与 ids 长度必须一致")

        points = []
        for i, vector in enumerate(vectors):
            mid = ids[i] if ids else str(uuid.uuid4())
            meta = metadata[i] if metadata else {}
            payload = dict(extra_payload)
            payload.update(meta)
            # 平铺顶层字段便于过滤
            payload.setdefault("memory_id", mid)
            payload.setdefault("user_id", meta.get("user_id", "default_user"))
            payload.setdefault("session_id", meta.get("session_id", "default"))
            points.append(
                models.PointStruct(
                    id=uuid.UUID(mid),
                    vector=vector,
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=name, points=points)
        return [p.id for p in points]

    def add_vector(
            self,
            vector: List[float],
            metadata: Optional[Dict[str, Any]] = None,
            memory_id: Optional[str] = None,
            collection: Optional[str] = None,
    ) -> str:
        """添加单条向量"""
        self._require_connected()
        mid = memory_id or str(uuid.uuid4())
        self.add_vectors(
            [vector], [metadata or {}], [mid], collection=collection
        )
        return mid

    # ---------------- 检索 ----------------

    def search(
            self,
            query_vector: List[float],
            limit: int = 5,
            user_id: Optional[str] = None,
            memory_type: Optional[str] = None,
            collection: Optional[str] = None,
            score_threshold: Optional[float] = None,
            **filters,
    ) -> List[Dict[str, Any]]:
        """
        向量检索。
        返回命中列表，每项含 id / score / metadata / payload 平铺字段
        （对齐文档：hit["metadata"]["timestamp"]、result["memory_id"]）
        """
        name = collection or self.collection
        self._require_connected()
        query_filter = self._build_filter(user_id, memory_type, **filters)
        # qdrant-client >= 1.10 使用 query_points（search 已弃用/移除）
        kwargs = {"collection_name": name, "query": query_vector,
                  "query_filter": query_filter, "limit": limit}
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold
        response = self.client.query_points(**kwargs)
        results = []
        for p in response.points:
            payload = p.payload or {}
            results.append({
                "id": str(p.id),
                "score": p.score,
                "payload": payload,
                "metadata": payload.get("metadata", payload),
                **payload,
            })
        return results

    def get_by_id(self, memory_id: str, collection: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """按记忆ID取单条"""
        name = collection or self.collection
        self._require_connected()
        try:
            records = self.client.retrieve(
                collection_name=name,
                ids=[uuid.UUID(memory_id)],
            )
        except Exception:
            return None
        if not records:
            return None
        payload = records[0].payload or {}
        return {
            "id": str(records[0].id),
            "score": 1.0,
            "payload": payload,
            "metadata": payload.get("metadata", payload),
            **payload,
        }

    # ---------------- 删除 ----------------

    def delete(self, memory_id: str, collection: Optional[str] = None) -> bool:
        """按记忆ID删除"""
        name = collection or self.collection
        self._require_connected()
        try:
            self.client.delete(
                collection_name=name,
                points_selector=[uuid.UUID(memory_id)],
            )
            return True
        except Exception:
            return False

    def delete_by_filter(
            self,
            user_id: Optional[str] = None,
            memory_type: Optional[str] = None,
            collection: Optional[str] = None,
    ) -> int:
        """按过滤条件批量删除，返回删除数量（-1 表示未知）"""
        name = collection or self.collection
        self._require_connected()
        query_filter = self._build_filter(user_id, memory_type)
        if query_filter is None:
            return 0
        result = self.client.delete(
            collection_name=name,
            points_selector=models.FilterSelector(filter=query_filter),
        )
        return getattr(result, "count", -1)

    def list_all(
            self,
            limit: int = 100,
            user_id: Optional[str] = None,
            memory_type: Optional[str] = None,
            collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """滚动列出集合内向量（scroll，无向量评分）"""
        name = collection or self.collection
        self._require_connected()
        query_filter = self._build_filter(user_id, memory_type)
        points, _ = self.client.scroll(
            collection_name=name,
            limit=limit,
            scroll_filter=query_filter,
            with_payload=True,
            with_vectors=False,
        )
        results = []
        for p in points:
            payload = p.payload or {}
            results.append({
                "id": str(p.id),
                "score": 1.0,
                "payload": payload,
                "metadata": payload.get("metadata", payload),
                **payload,
            })
        return results

    def count(self, collection: Optional[str] = None) -> int:
        """集合内向量数量"""
        name = collection or self.collection
        self._require_connected()
        result = self.client.count(collection_name=name, exact=True)
        return result.count

    # ---------------- 内部 ----------------

    @staticmethod
    def _build_filter(
            user_id: Optional[str] = None,
            memory_type: Optional[str] = None,
            **filters,
    ) -> Optional[models.Filter]:
        must = []
        if user_id:
            must.append(models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            ))
        if memory_type:
            must.append(models.FieldCondition(
                key="memory_type",
                match=models.MatchValue(value=memory_type),
            ))
        for k, v in filters.items():
            must.append(models.FieldCondition(
                key=k,
                match=models.MatchValue(value=v),
            ))
        if not must:
            return None
        return models.Filter(must=must)
