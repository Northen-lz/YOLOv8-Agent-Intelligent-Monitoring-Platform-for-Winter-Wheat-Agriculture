# -*- coding: utf-8 -*-
"""
Hello-Agents 工作记忆（WorkingMemory）
对齐文档第八章 8.2.5（1）工作记忆

特点（文档）：
- 容量有限（默认50条）+ TTL自动清理
- 纯内存存储，访问速度极快（重启即失）
- 混合检索：TF-IDF向量化 + 关键词匹配

评分公式（文档）：
  (相似度 × 时间衰减) × (0.8 + 重要性 × 0.4)
其中 base_relevance = 向量分数×0.7 + 关键词分数×0.3（向量为0时退化为关键词）
"""

import re
from datetime import datetime
from typing import Dict, List, Optional

from ..base import BaseMemory, MemoryConfig, MemoryItem
from ..embedding import get_text_embedder

# 中英文 token 切分（中文按字符，英文按单词）
_TOKEN_RE = re.compile(r"[一-鿿]|[a-zA-Z0-9]+")


class WorkingMemory(BaseMemory):
    """工作记忆实现（纯内存 + TTL）"""

    def __init__(self, config: Optional[MemoryConfig] = None, storage_backend=None):
        super().__init__(config, storage_backend)
        self.max_capacity = self.config.working_memory_capacity or 50
        self.max_age_minutes = self.config.working_memory_ttl or 60
        self.memories: List[MemoryItem] = []

    # ---------------- 添加 ----------------

    def add(self, memory_item: MemoryItem) -> str:
        """添加工作记忆"""
        self._expire_old_memories()  # 过期清理

        if len(self.memories) >= self.max_capacity:
            self._remove_lowest_priority_memory()  # 容量管理

        self.memories.append(memory_item)
        return memory_item.id

    # ---------------- 检索 ----------------

    def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        """混合检索：TF-IDF向量化 + 关键词匹配"""
        self._expire_old_memories()

        # 尝试TF-IDF向量检索
        vector_scores = self._try_tfidf_search(query)

        # 计算综合分数
        scored_memories = []
        for memory in self.memories:
            vector_score = vector_scores.get(memory.id, 0.0)
            keyword_score = self._calculate_keyword_score(query, memory.content)

            # 混合评分（文档公式）
            if vector_score > 0:
                base_relevance = vector_score * 0.7 + keyword_score * 0.3
            else:
                base_relevance = keyword_score

            time_decay = self._calculate_time_decay(memory.timestamp)
            importance_weight = 0.8 + (memory.importance * 0.4)

            final_score = base_relevance * time_decay * importance_weight
            if final_score > 0:
                scored_memories.append((final_score, memory))

        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_memories[:limit]]

    # ---------------- 其他接口 ----------------

    def update(self, memory_id: str, **fields) -> bool:
        """更新工作记忆内容/重要性"""
        for memory in self.memories:
            if memory.id == memory_id:
                if "content" in fields:
                    memory.content = fields["content"]
                if "importance" in fields:
                    memory.importance = fields["importance"]
                return True
        return False

    def remove(self, memory_id: str) -> bool:
        """删除工作记忆"""
        for i, memory in enumerate(self.memories):
            if memory.id == memory_id:
                del self.memories[i]
                return True
        return False

    def clear(self) -> int:
        """清空工作记忆"""
        count = len(self.memories)
        self.memories = []
        return count

    def count(self) -> int:
        """当前条数"""
        return len(self.memories)

    def list_all(self) -> List[MemoryItem]:
        """列出全部工作记忆"""
        self._expire_old_memories()
        return list(self.memories)

    # ---------------- 内部实现 ----------------

    def _expire_old_memories(self):
        """TTL 过期清理"""
        now = datetime.now()
        self.memories = [
            m for m in self.memories
            if (now - m.timestamp).total_seconds() / 60 < self.max_age_minutes
        ]

    def _remove_lowest_priority_memory(self):
        """容量管理：移除最低优先级记忆（重要性最低且最旧）"""
        if not self.memories:
            return
        lowest = min(
            self.memories,
            key=lambda m: (m.importance, m.timestamp),
        )
        self.memories.remove(lowest)

    def _try_tfidf_search(self, query: str) -> Dict[str, float]:
        """TFIDF向量化：query 与全部记忆一起编码，返回 {id: 余弦相似度}"""
        if not self.memories:
            return {}
        try:
            import numpy as np
            embedder = get_text_embedder(model_type="tfidf")
            texts = [query] + [m.content for m in self.memories]
            vecs = embedder.encode(texts)
            qv = np.array(vecs[0])
            if np.linalg.norm(qv) == 0:
                return {}
            scores = {}
            for i, m in enumerate(self.memories):
                vec = np.array(vecs[i + 1])
                norm = np.linalg.norm(vec)
                if norm == 0:
                    continue
                scores[m.id] = float(np.dot(qv, vec))
            return scores
        except Exception:
            return {}

    @staticmethod
    def _calculate_keyword_score(query: str, content: str) -> float:
        """关键词重合度（Jaccard）"""
        q_words = set(_TOKEN_RE.findall(query.lower()))
        c_words = set(_TOKEN_RE.findall(content.lower()))
        if not q_words or not c_words:
            return 0.0
        return len(q_words & c_words) / len(q_words | c_words)

    def _calculate_time_decay(self, timestamp: datetime) -> float:
        """时间衰减：越新越接近1，超过TTL归零"""
        age_minutes = (datetime.now() - timestamp).total_seconds() / 60
        return max(0.0, 1.0 - age_minutes / self.max_age_minutes)
