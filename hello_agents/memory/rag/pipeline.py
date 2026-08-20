# -*- coding: utf-8 -*-
"""
Hello-Agents RAG 检索管道
对齐文档第八章 8.3：索引 → 嵌入 → 高级检索（MQE 多查询扩展 / HyDE 假设文档嵌入）

检索框架（文档 PDF 页 270-275，"扩展-检索-合并"）：
        原始查询 ──────────────┐
  MQE:  改写查询1/2/3 ─────────┤ → 各自向量检索 → 合并去重 → 相关性排序 → top_k
  HyDE: 假设文档嵌入 ──────────┘

核心函数（对齐文档代码）：
- create_rag_pipeline()     构建 RAG 管道（存储 + LLM + 命名空间）
- index_chunks()            批量嵌入并写入向量库
- search_vectors_expanded() 扩展-检索-合并（支持 MQE / HyDE）
- _prompt_mqe() / _prompt_hyde()  LLM 生成改写查询 / 假设文档
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from ...core.llm import HelloAgentsLLM
from ..embedding import create_embedding_model_with_fallback
from .document import _preprocess_markdown_for_embedding

logger = logging.getLogger(__name__)

# RAG 向量 payload 标记（用于 Qdrant 过滤隔离 RAG 数据）
RAG_MEMORY_TYPE = "rag_chunk"
RAG_DATA_SOURCE = "rag_pipeline"

_llm_singleton: Optional[HelloAgentsLLM] = None


def _get_llm() -> HelloAgentsLLM:
    """惰性单例 LLM（供 MQE/HyDE 使用）"""
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = HelloAgentsLLM()
    return _llm_singleton


# ================================================================
# 管道构建
# ================================================================

def create_rag_pipeline(
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        collection_name: str = "rag_knowledge_base",
        rag_namespace: str = "default",
) -> Dict[str, Any]:
    """
    构建 RAG 管道（对齐文档 8.3.2）
    返回 dict 含 store / llm / collection_name / rag_namespace。
    """
    from ..storage import QdrantVectorStore

    store = QdrantVectorStore(
        url=qdrant_url,
        api_key=qdrant_api_key,
        collection=collection_name,
    )
    return {
        "store": store,
        "llm": _get_llm(),
        "collection_name": collection_name,
        "rag_namespace": rag_namespace,
    }


# ================================================================
# 索引
# ================================================================

def index_chunks(
        store,
        chunks: List[Dict[str, Any]],
        batch_size: int = 64,
        rag_namespace: str = "default",
) -> int:
    """
    批量嵌入并写入向量库（对齐文档 8.3.4 index_chunks）
    chunks: DocumentProcessor 输出的分块列表（含 content / heading_path / start / end）
    返回写入的分块数量。
    """
    embedder = create_embedding_model_with_fallback()
    total = len(chunks)
    added = 0

    for i in range(0, total, batch_size):
        batch = chunks[i: i + batch_size]
        # 1. 嵌入前预处理（去代码围栏、链接、压缩空白）
        texts = [_preprocess_markdown_for_embedding(c["content"]) for c in batch]
        vectors = embedder.encode(texts)

        # 2. 维度校验 + 零向量兜底（避免 Qdrant 拒绝）
        dim = getattr(embedder, "dimension", None) or len(vectors[0])
        cleaned = []
        for v in vectors:
            if not v or len(v) != dim or not any(v):
                # 零向量/维度不符：置为微小随机扰动，保证可检索且不报错
                v = [1e-8] * dim
            cleaned.append(v)

        # 3. 构造 metadata 与 id
        metadata = []
        ids = []
        for j, c in enumerate(batch):
            mid = str(uuid.uuid4())
            ids.append(mid)
            metadata.append({
                "content": c["content"],
                "heading_path": c.get("heading_path"),
                "source": c.get("source"),
                "start": c.get("start"),
                "end": c.get("end"),
                "chunk_index": i + j,
                "memory_type": RAG_MEMORY_TYPE,
                "is_rag_data": True,
                "data_source": RAG_DATA_SOURCE,
                "rag_namespace": rag_namespace,
            })

        store.add_vectors(cleaned, metadata, ids)
        added += len(batch)

    print(f"[RAG] 索引完成: {added} 个分块 -> {getattr(store, 'collection', '')} "
          f"(namespace={rag_namespace})")
    return added


# ================================================================
# 扩展-检索-合并（MQE / HyDE）
# ================================================================

def search_vectors_expanded(
        store,
        query: str,
        top_k: int = 8,
        rag_namespace: str = "default",
        only_rag_data: bool = True,
        score_threshold: Optional[float] = None,
        enable_mqe: bool = True,
        mqe_expansions: int = 2,
        enable_hyde: bool = True,
        candidate_pool_multiplier: int = 4,
) -> List[Dict[str, Any]]:
    """
    扩展-检索-合并检索（对齐文档 8.3.5）
    - 基础查询向量检索
    - MQE: 生成 N 个改写查询，各自检索
    - HyDE: 生成假设文档，嵌入检索
    - 合并去重，按最高分排序，取 top_k
    """
    embedder = create_embedding_model_with_fallback()
    candidate_pool = max(top_k * candidate_pool_multiplier, 20)

    # 1. 构造查询集合
    queries = [query]
    if enable_mqe:
        for n in range(1, mqe_expansions + 1):
            expanded = _prompt_mqe(query, n)
            if expanded and expanded != query and expanded not in queries:
                queries.append(expanded)
    if enable_hyde:
        hyde_doc = _prompt_hyde(query)
        if hyde_doc and hyde_doc != query:
            queries.append(hyde_doc)

    # 2. 逐查询检索
    filter_kwargs: Dict[str, Any] = {"rag_namespace": rag_namespace}
    if only_rag_data:
        filter_kwargs["is_rag_data"] = True

    merged: Dict[str, Dict[str, Any]] = {}
    for q in queries:
        qv = embedder.embed(q)
        try:
            hits = store.search(
                qv,
                limit=candidate_pool,
                score_threshold=score_threshold,
                **filter_kwargs,
            )
        except Exception as e:
            print(f"[WARNING] 检索失败 '{q[:30]}...': {e}")
            continue
        for hit in hits:
            mid = hit["id"]
            if mid not in merged or hit["score"] > merged[mid]["score"]:
                merged[mid] = hit

    # 3. 按最高分排序取 top_k
    ranked = sorted(merged.values(), key=lambda x: x.get("score", 0),
                    reverse=True)[:top_k]
    return ranked


# ================================================================
# MQE / HyDE 提示（对齐文档 _prompt_mqe / _prompt_hyde）
# ================================================================

def _prompt_mqe(query: str, n: int = 1) -> str:
    """
    多查询扩展（Multi-Query Expansion）
    让 LLM 从不同视角改写原始查询，扩大召回。
    """
    llm = _get_llm()
    messages = [
        {"role": "system", "content":
         "你是一个信息检索专家。用户会给出一个原始查询，请从不同角度改写它，"
         "帮助检索更全面的相关资料。只输出改写后的查询本身，不要任何解释。"},
        {"role": "user", "content":
         f"原始查询：{query}\n请输出第 {n} 个改写查询："},
    ]
    try:
        result = llm.invoke(messages, temperature=0.7).strip().strip('"\'')
        if result and len(result) > 2:
            print(f"[RAG] MQE改写#{n}: {result}")
            return result
    except Exception as e:
        logger.warning(f"MQE 扩展失败: {e}")
    return query


def _prompt_hyde(query: str) -> str:
    """
    假设文档嵌入（Hypothetical Document Embeddings）
    让 LLM 模拟"理想文档片段"，嵌入后检索。
    """
    llm = _get_llm()
    messages = [
        {"role": "system", "content":
         "你是一个知识库助手。请根据用户问题，模拟写出一段能回答该问题的"
         "文档片段（约80-150字，包含关键术语）。只输出文档片段本身。"},
        {"role": "user", "content": f"问题：{query}"},
    ]
    try:
        result = llm.invoke(messages, temperature=0.4).strip()
        if result and len(result) > 10:
            print(f"[RAG] HyDE假设文档: {result[:60]}...")
            return result
    except Exception as e:
        logger.warning(f"HyDE 失败: {e}")
    return query
