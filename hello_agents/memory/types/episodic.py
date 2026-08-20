# -*- coding: utf-8 -*-
"""
Hello-Agents 情景记忆（EpisodicMemory）
对齐文档第八章 8.2.5（2）情景记忆

特点（文档）：
- 存储具体事件和经历，保持事件完整性与时间序列关系
- SQLite + Qdrant 混合存储：SQLite 结构化持久化，Qdrant 向量检索
- 支持时间序列和会话级检索

评分公式（文档）：
  (向量相似度 × 0.8 + 时间近因性 × 0.2) × (0.8 + 重要性 × 0.4)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import BaseMemory, MemoryConfig, MemoryItem
from ..embedding import create_embedding_model_with_fallback
from ..storage.document_store import SQLiteDocumentStore
from ..storage.qdrant_store import QdrantVectorStore


class Episode:
    """情景对象（对齐文档 Episode 结构：episode_id/session_id/timestamp/content/context）"""

    def __init__(self, episode_id, session_id, timestamp, content, context=None,
                 importance=0.5, user_id="default_user"):
        self.episode_id = episode_id
        self.session_id = session_id
        self.timestamp = timestamp
        self.content = content
        self.context = context or {}
        self.importance = importance
        self.user_id = user_id


class EpisodicMemory(BaseMemory):
    """情景记忆实现（SQLite 持久化 + Qdrant 向量）"""

    def __init__(self, config: Optional[MemoryConfig] = None, storage_backend=None):
        super().__init__(config, storage_backend)
        self.doc_store = SQLiteDocumentStore(self.config.database_path)
        self.vector_store = QdrantVectorStore(
            self.config.qdrant_url,
            self.config.qdrant_api_key,
        )
        self.embedder = create_embedding_model_with_fallback()
        self.sessions: Dict[str, list] = {}  # 会话索引
        # 从 SQLite 恢复会话索引
        for item in self.doc_store.get_by_type("episodic"):
            sid = item.session_id
            self.sessions.setdefault(sid, [])
            self.sessions[sid].append(item.id)

    # ---------------- 添加 ----------------

    def add(self, memory_item: MemoryItem) -> str:
        """添加情景记忆"""
        memory_item.memory_type = "episodic"
        episode = Episode(
            episode_id=memory_item.id,
            session_id=memory_item.metadata.get("session_id", "default"),
            timestamp=memory_item.timestamp,
            content=memory_item.content,
            context=memory_item.metadata,
            importance=memory_item.importance,
            user_id=memory_item.user_id,
        )

        # 更新会话索引
        if episode.session_id not in self.sessions:
            self.sessions[episode.session_id] = []
        self.sessions[episode.session_id].append(episode.episode_id)

        # 持久化存储（SQLite + Qdrant）
        self._persist_episode(episode)
        return memory_item.id

    def _persist_episode(self, episode: Episode):
        """持久化：SQLite 结构化 + Qdrant 向量"""
        # SQLite
        item = MemoryItem(
            id=episode.episode_id,
            content=episode.content,
            memory_type="episodic",
            importance=episode.importance,
            timestamp=episode.timestamp,
            metadata=episode.context,
        )
        self.doc_store.add(item)

        # Qdrant 向量（Qdrant 未启动时 SQLite 已持久化，向量部分跳过）
        try:
            vector = self.embedder.embed(episode.content)
            self.vector_store.add_vectors(
                vectors=[vector],
                metadata=[{
                    "memory_id": episode.episode_id,
                    "content": episode.content,
                    "memory_type": "episodic",
                    "importance": episode.importance,
                    "timestamp": episode.timestamp.isoformat(),
                    "metadata": episode.context,
                    "user_id": episode.user_id,
                    "session_id": episode.session_id,
                }],
                ids=[episode.episode_id],
            )
        except Exception as e:
            print(f"⚠️ 情景记忆向量存储失败（SQLite 已保存，向量检索暂不可用）: {e}")

    # ---------------- 检索 ----------------

    def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        """混合检索：结构化过滤 + 语义向量检索；Qdrant 不可用时降级 SQLite 关键词"""
        # 1. 结构化预过滤（时间范围、重要性等）
        candidate_ids = self._structured_filter(**kwargs)

        # 2. 向量语义检索
        hits = self._vector_search(query, limit * 5, kwargs.get("user_id"))

        # 3. 综合评分与排序
        results = []
        for hit in hits:
            if self._should_include(hit, candidate_ids, kwargs):
                score = self._calculate_episode_score(hit)
                memory_item = self._create_memory_item(hit)
                results.append((score, memory_item))

        results.sort(key=lambda x: x[0], reverse=True)
        ranked = [item for _, item in results[:limit]]
        # Qdrant 不可用（向量无命中）时降级：SQLite 关键词检索，保证离线可用
        if not ranked:
            ranked = self._sqlite_keyword_search(query, limit, candidate_ids, kwargs)
        return ranked

    def _sqlite_keyword_search(
            self, query: str, limit: int, candidate_ids: Optional[set],
            kwargs: dict,
    ) -> List[MemoryItem]:
        """Qdrant 未连接时的离线兜底：按关键词重合度检索 SQLite 中已持久化的情景记忆"""
        try:
            from .working import WorkingMemory
            items = self.doc_store.get_by_type("episodic")
        except Exception:
            return []
        min_importance = kwargs.get("min_importance")
        scored = []
        for item in items:
            if candidate_ids is not None and item.id not in candidate_ids:
                continue
            if min_importance and item.importance < min_importance:
                continue
            score = WorkingMemory._calculate_keyword_score(query, item.content)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def _vector_search(self, query: str, limit: int, user_id: Optional[str]) -> List[Dict[str, Any]]:
        """向量语义检索（含用户隔离）；Qdrant 未连接时返回空，避免整条检索崩溃"""
        try:
            query_vector = self.embedder.embed(query)
            return self.vector_store.search(
                query_vector,
                limit=limit,
                user_id=user_id,
                memory_type="episodic",
            )
        except Exception as e:
            print(f"⚠️ 情景记忆向量检索暂不可用（Qdrant 未连接？）: {e}")
            return []

    def _structured_filter(self, **kwargs) -> Optional[set]:
        """结构化预过滤：返回候选记忆ID集合（未指定条件返回 None 表示不过滤）"""
        session_id = kwargs.get("session_id")
        user_id = kwargs.get("user_id")
        min_importance = kwargs.get("min_importance")

        if not (session_id or user_id or min_importance):
            return None

        candidates = []
        if session_id:
            candidates.extend(self.doc_store.get_by_session(session_id))
        if user_id:
            for item in self.doc_store.list_all():
                if item.user_id == user_id:
                    candidates.append(item)
        if min_importance:
            candidates = [c for c in candidates
                          if c.importance >= min_importance]

        # 仅指定 min_importance（无 session/user）时，doc_store 无法做结构化过滤，
        # 返回 None 交由 _should_include 逐条判断，避免空候选集把全部命中过滤掉。
        if not (session_id or user_id):
            return None
        return {c.id for c in candidates}

    def _should_include(self, hit: Dict[str, Any], candidate_ids: Optional[set],
                        kwargs: dict) -> bool:
        """判断命中是否应包含在结果中"""
        if candidate_ids is not None:
            if hit.get("memory_id") not in candidate_ids:
                return False
        min_importance = kwargs.get("min_importance")
        if min_importance:
            # importance 存于 payload 顶层；嵌套 metadata 是用户上下文 dict，无该字段
            if float(hit.get("importance", 0)) < min_importance:
                return False
        return True

    def _calculate_episode_score(self, hit: Dict[str, Any]) -> float:
        """情景记忆评分算法（文档公式）"""
        vec_score = float(hit.get("score", 0.0))
        # importance/timestamp 在 payload 顶层（_vector_search 已平铺）
        recency_score = self._calculate_recency(hit.get("timestamp"))
        importance = float(hit.get("importance", 0.5))

        base_relevance = vec_score * 0.8 + recency_score * 0.2
        importance_weight = 0.8 + (importance * 0.4)
        return base_relevance * importance_weight

    def _create_memory_item(self, hit: Dict[str, Any]) -> MemoryItem:
        """从向量命中重建 MemoryItem"""
        meta = hit.get("metadata") or {}  # 写入时的用户上下文
        payload = hit.get("payload") or hit
        return MemoryItem(
            id=str(hit.get("memory_id") or hit.get("id")),
            content=str(payload.get("content", "")),
            memory_type="episodic",
            importance=float(payload.get("importance", 0.5)),
            timestamp=datetime.fromisoformat(payload.get("timestamp"))
            if payload.get("timestamp") else datetime.now(),
            metadata=dict(meta),
        )

    @staticmethod
    def _calculate_recency(timestamp_str: Optional[str]) -> float:
        """时间近因性：最近24小时内线性衰减到0"""
        if not timestamp_str:
            return 0.5
        try:
            ts = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            return 0.5
        age_minutes = (datetime.now() - ts).total_seconds() / 60
        return max(0.0, 1.0 - age_minutes / (24 * 60))

    # ---------------- 会话管理 ----------------

    def get_history(self, session_id: str) -> List[MemoryItem]:
        """按会话取历史"""
        return self.doc_store.get_by_session(session_id)

    def update(self, memory_id: str, **fields) -> bool:
        """更新（同步 SQLite + Qdrant）"""
        item = self.doc_store.get(memory_id)
        if item is None:
            return False
        if "content" in fields:
            item.content = fields["content"]
        if "importance" in fields:
            item.importance = float(fields["importance"])
        if "metadata" in fields:
            item.metadata = fields["metadata"]
        self.doc_store.add(item)
        # 同步向量
        try:
            vector = self.embedder.embed(item.content)
            self.vector_store.add_vectors(
                vectors=[vector],
                metadata=[{
                    "memory_id": item.id,
                    "content": item.content,
                    "memory_type": "episodic",
                    "importance": item.importance,
                    "timestamp": item.timestamp.isoformat(),
                    "metadata": item.metadata,
                    "user_id": item.user_id,
                    "session_id": item.session_id,
                }],
                ids=[item.id],
            )
        except Exception:
            pass
        return True

    def remove(self, memory_id: str) -> bool:
        """删除（同步 SQLite + Qdrant）"""
        ok_sqlite = self.doc_store.delete(memory_id)
        ok_vector = self.vector_store.delete(memory_id)
        return ok_sqlite or ok_vector

    def clear(self) -> int:
        """清空全部情景记忆"""
        items = self.doc_store.get_by_type("episodic")
        for item in items:
            self.doc_store.delete(item.id)
        # 清空向量
        self.vector_store.delete_by_filter(memory_type="episodic")
        self.sessions.clear()
        return len(items)

    def count(self) -> int:
        """情景记忆总数"""
        return len(self.doc_store.get_by_type("episodic"))

    def list_all(self) -> List[MemoryItem]:
        """列出全部情景记忆"""
        return self.doc_store.get_by_type("episodic")
