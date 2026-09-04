# -*- coding: utf-8 -*-
"""
Hello-Agents 语义记忆（SemanticMemory）
对齐文档第八章 8.2.5（3）语义记忆

特点（文档）：
- 存储抽象概念、规则和知识
- Qdrant 向量 + Neo4j 知识图谱混合架构
- 自动提取实体和关系，构建结构化知识表示
- 混合检索：向量 + 图 + 语义推理

评分公式（文档）：
  (向量相似度 × 0.7 + 图相似度 × 0.3) × (0.8 + 重要性 × 0.4)
向量权重 0.7（主要语义），图权重 0.3（关系补充）
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import BaseMemory, MemoryConfig, MemoryItem
from ..embedding import get_text_embedder
from ..storage.neo4j_store import Neo4jGraphStore
from ..storage.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)

# 中英文 token 切分
_TOKEN_RE = re.compile(r"[一-鿿]|[a-zA-Z][a-zA-Z0-9_]{1,}")

# 简单停用词（中文 + 英文常用词）
_STOPWORDS = {
    "是", "的", "了", "和", "与", "在", "有", "我", "你", "他", "她", "它",
    "我们", "你们", "他们", "它们", "一个", "一种", "以及", "或者", "这", "那",
    "对", "从", "到", "为", "要", "也", "就", "都", "等", "说", "把", "被",
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "and", "or",
    "in", "on", "for", "with", "that", "this", "it", "its", "be", "at",
}


class SemanticMemory(BaseMemory):
    """语义记忆实现（Qdrant + Neo4j）

    懒加载优化（YOLO 平台）：嵌入模型 / Qdrant / Neo4j / NLP 在首次
    add/retrieve 时才构造。原实现急切构造两个外部存储连接 + spaCy，
    是 MemoryTool 刻意避开 semantic 类型的原因（拖慢启动、依赖服务在线）。
    """

    def __init__(self, config: Optional[MemoryConfig] = None, storage_backend=None):
        super().__init__(config, storage_backend)

        # 懒加载占位（首次使用才真实构造，见 _ensure_backends / 属性访问器）
        self._backend_ready = False
        self._embedding_model: Any = None
        self._vector_store: Any = None
        self._graph_store: Any = None

        # 实体和关系缓存
        self.entities: Dict[str, Any] = {}
        self.relations: List[Any] = []

        # NLP处理器（懒加载后由 _ensure_backends 设置）
        self.nlp = None

    # ---------------- 懒加载 ----------------

    def _ensure_backends(self):
        """首次 add/retrieve 时构造嵌入模型 + Qdrant + Neo4j + NLP"""
        if self._backend_ready:
            return
        self._embedding_model = get_text_embedder()
        self._vector_store = QdrantVectorStore(
            self.config.qdrant_url,
            self.config.qdrant_api_key,
        )
        self._graph_store = Neo4jGraphStore(
            self.config.neo4j_uri,
            self.config.neo4j_username,
            self.config.neo4j_password,
        )
        self.nlp = self._init_nlp()
        self._backend_ready = True
        if self.nlp is not None:
            logger.info("✅ 语义记忆NLP处理器就绪")
        else:
            logger.info("⚠️ spaCy 不可用，降级使用简单实体提取")

    @property
    def embedding_model(self):
        self._ensure_backends()
        return self._embedding_model

    @property
    def vector_store(self):
        self._ensure_backends()
        return self._vector_store

    @property
    def graph_store(self):
        self._ensure_backends()
        return self._graph_store

    # ---------------- NLP 初始化 ----------------

    def _init_nlp(self):
        """加载中英文 spaCy 模型；全部失败返回 None（降级 jieba/简单提取）"""
        nlp_models = {}
        try:
            import spacy
        except ImportError:
            logger.warning("⚠️ 未安装 spacy，降级使用 jieba 分词")
            return None
        for lang, model_name in [("zh", "zh_core_web_sm"), ("en", "en_core_web_sm")]:
            try:
                nlp_models[lang] = spacy.load(model_name)
                logger.info(f"✅ 加载{lang}文spaCy模型: {model_name}")
            except OSError:
                logger.warning(f"⚠️ 加载 spaCy 模型 {model_name} 失败")
        return nlp_models if nlp_models else None

    # ---------------- 添加 ----------------

    def add(self, memory_item: MemoryItem) -> str:
        """添加语义记忆"""
        memory_item.memory_type = "semantic"
        user_id = memory_item.user_id

        # 1. 生成文本嵌入
        embedding = self.embedding_model.encode(memory_item.content)

        # 2. 提取实体和关系
        entities = self._extract_entities(memory_item.content)
        relations = self._extract_relations(memory_item.content, entities)

        # 3. 存储到 Neo4j 图数据库（Neo4j 不可用时降级，只存向量）
        try:
            for entity in entities:
                self._add_entity_to_graph(entity, memory_item, user_id)
            for relation in relations:
                self._add_relation_to_graph(relation, memory_item, user_id)
        except Exception as e:
            logger.warning(f"语义记忆图存储降级跳过（Neo4j 不可用）: {e}")

        # 4. 存储到 Qdrant 向量数据库
        metadata = {
            "memory_id": memory_item.id,
            "content": memory_item.content,
            "memory_type": "semantic",
            "importance": memory_item.importance,
            "timestamp": memory_item.timestamp.isoformat(),
            "metadata": dict(memory_item.metadata),
            "user_id": user_id,
            "session_id": memory_item.session_id,
            "entities": list(entities),
            "entity_count": len(entities),
            "relation_count": len(relations),
        }
        # encode 返回 List[List[float]]，直接作为批量向量
        self.vector_store.add_vectors(
            vectors=embedding,
            metadata=[metadata],
            ids=[memory_item.id],
        )
        return memory_item.id

    # ---------------- 检索 ----------------

    def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        """混合检索：向量 + 图"""
        user_id = kwargs.get("user_id")

        # 1. 向量检索
        vector_results = self._vector_search(query, limit * 2, user_id)

        # 2. 图检索
        graph_results = self._graph_search(query, limit * 2, user_id)

        # 3. 混合排序
        combined_results = self._combine_and_rank_results(
            vector_results, graph_results, query, limit
        )

        # 转为 MemoryItem
        return [self._result_to_item(r) for r in combined_results[:limit]]

    def _vector_search(self, query: str, limit: int, user_id: Optional[str]) -> List[Dict[str, Any]]:
        """向量语义检索（Qdrant 不可用时降级为空，不中断整次检索）"""
        try:
            query_vector = self.embedding_model.embed(query)
            return self.vector_store.search(
                query_vector,
                limit=limit,
                user_id=user_id,
                memory_type="semantic",
            )
        except Exception as e:
            logger.warning(f"语义记忆向量检索降级为空: {e}")
            return []

    def _graph_search(self, query: str, limit: int, user_id: Optional[str]) -> List[Dict[str, Any]]:
        """图检索：用查询中的实体匹配图谱（Neo4j 不可用时降级为空）"""
        try:
            entities = self._extract_entities(query)
            if not entities:
                return []
            scores = self.graph_store.find_memories_for_entities(
                entities, user_id=user_id
            )
        except Exception as e:
            logger.warning(f"语义记忆图检索降级为空: {e}")
            return []
        results = []
        for mid, sim in scores.items():
            meta = self.vector_store.get_by_id(mid)
            if meta is None:
                continue
            results.append({
                **meta,
                "memory_id": mid,
                "similarity": sim,
            })
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def _combine_and_rank_results(
            self,
            vector_results: List[Dict[str, Any]],
            graph_results: List[Dict[str, Any]],
            query: str,
            limit: int,
    ) -> List[Dict[str, Any]]:
        """混合排序结果（文档公式）"""
        combined: Dict[str, Dict[str, Any]] = {}

        # 合并向量和图检索结果
        for result in vector_results:
            combined[result["memory_id"]] = {
                **result,
                "vector_score": result.get("score", 0.0),
                "graph_score": 0.0,
            }

        for result in graph_results:
            memory_id = result["memory_id"]
            if memory_id in combined:
                combined[memory_id]["graph_score"] = result.get("similarity", 0.0)
            else:
                combined[memory_id] = {
                    **result,
                    "vector_score": 0.0,
                    "graph_score": result.get("similarity", 0.0),
                }

        # 计算混合分数
        for memory_id, result in combined.items():
            vector_score = result["vector_score"]
            graph_score = result["graph_score"]
            importance = result.get("importance", 0.5)

            # 基础相似度得分（文档公式）
            base_relevance = vector_score * 0.7 + graph_score * 0.3
            importance_weight = 0.8 + (importance * 0.4)
            result["combined_score"] = base_relevance * importance_weight

        sorted_results = sorted(
            combined.values(),
            key=lambda x: x["combined_score"],
            reverse=True,
        )
        return sorted_results[:limit]

    # ---------------- 实体与关系提取 ----------------

    def _extract_entities(self, content: str) -> List[str]:
        """提取实体：spaCy 命名实体 + jieba 概念词合并（文档"实体+关系构建"）"""
        entities: List[str] = []

        # 1. spaCy NER（命名实体：人名/组织/地名等）
        if self.nlp:
            for nlp in self.nlp.values():
                try:
                    doc = nlp(content)
                    ner = [ent.text for ent in doc.ents
                           if ent.label_ in ("PERSON", "ORG", "GPE", "PRODUCT",
                                             "WORK_OF_ART", "PER", "LOC")]
                    entities.extend(ner)
                except Exception:
                    continue

        # 2. jieba 概念词（补充非命名实体，如"Python/开发者"）
        entities.extend(self._simple_extract_entities(content))

        # 合并去重，保留顺序
        seen = set()
        result = []
        for e in entities:
            if e not in seen:
                seen.add(e)
                result.append(e)
        return result[:10]

    def _simple_extract_entities(self, content: str) -> List[str]:
        """降级实体提取：jieba 中文分词 → 正则兜底"""
        try:
            import jieba
            tokens = [t.strip() for t in jieba.cut(content) if t.strip()]
        except ImportError:
            tokens = _TOKEN_RE.findall(content)

        candidates = []
        for t in tokens:
            tl = t.lower()
            if len(tl) < 2 or tl in _STOPWORDS or tl.isdigit():
                continue
            # 纯中文词：若全部为停用字（是/的/了）则丢弃
            if re.fullmatch(r"[一-鿿]+", t) and all(ch in _STOPWORDS for ch in t):
                continue
            candidates.append(t)

        # 去重保序
        seen = set()
        result = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result[:10]

    def _extract_relations(self, content: str, entities: List[str]) -> List[tuple]:
        """提取关系三元组 (source, relation, target)

        文档使用更复杂的 NLP 依赖解析；此处降级为：
        - 相邻实体对建立 co_occur（共现）关系
        """
        relations = []
        if len(entities) < 2:
            return relations
        for i in range(len(entities)):
            for j in range(i + 1, min(i + 3, len(entities))):
                relations.append((entities[i], "co_occur", entities[j]))
        return relations[:20]

    def _add_entity_to_graph(self, entity: str, memory_item: MemoryItem, user_id: str):
        """实体写入图谱"""
        self.entities[entity] = entity
        self.graph_store.upsert_entity(
            name=entity,
            memory_id=memory_item.id,
            user_id=user_id,
        )

    def _add_relation_to_graph(self, relation: tuple, memory_item: MemoryItem, user_id: str):
        """关系写入图谱"""
        source, rel_type, target = relation
        self.relations.append(relation)
        self.graph_store.create_relation(
            source=source,
            relation=rel_type,
            target=target,
            memory_id=memory_item.id,
            user_id=user_id,
        )

    def _result_to_item(self, result: Dict[str, Any]) -> MemoryItem:
        """检索结果字典转 MemoryItem"""
        meta = result.get("metadata") or {}
        return MemoryItem(
            id=str(result.get("memory_id") or result.get("id")),
            content=str(result.get("content", "")),
            memory_type="semantic",
            importance=float(result.get("importance", 0.5)),
            timestamp=datetime.fromisoformat(result.get("timestamp"))
            if result.get("timestamp") else datetime.now(),
            metadata=dict(meta),
        )

    # ---------------- 其他接口 ----------------

    def update(self, memory_id: str, **fields) -> bool:
        """更新语义记忆"""
        meta = self.vector_store.get_by_id(memory_id)
        if meta is None:
            return False
        if "content" in fields:
            # 简化：先删除再重新添加
            item = MemoryItem(
                id=memory_id,
                content=fields["content"],
                memory_type="semantic",
                importance=fields.get("importance", meta.get("importance", 0.5)),
                timestamp=datetime.now(),
                metadata=meta.get("metadata") or {},
            )
            self.remove(memory_id)
            self.add(item)
            return True
        if "importance" in fields:
            import json
            meta["importance"] = float(fields["importance"])
            self.vector_store.add_vectors(
                vectors=[self.embedding_model.embed(meta.get("content", ""))],
                metadata=[{**meta, "metadata": {}}],
                ids=[memory_id],
            )
            return True
        return False

    def remove(self, memory_id: str) -> bool:
        """删除语义记忆"""
        ok_vector = self.vector_store.delete(memory_id)
        return ok_vector

    def clear(self) -> int:
        """清空语义记忆（向量 + 图谱）"""
        count = self.vector_store.count()
        self.vector_store.delete_by_filter(memory_type="semantic")
        self.graph_store.clear()
        self.entities.clear()
        self.relations.clear()
        return count

    def count(self) -> int:
        """语义记忆总数"""
        return self.vector_store.count()

    def list_all(self) -> List[MemoryItem]:
        """列出全部语义记忆"""
        results = self.vector_store.list_all(memory_type="semantic")
        return [self._result_to_item(r) for r in results]
