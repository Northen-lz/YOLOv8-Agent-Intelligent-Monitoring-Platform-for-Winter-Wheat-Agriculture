# -*- coding: utf-8 -*-
"""
Hello-Agents RAG 系统（对齐文档第八章 8.3）
- document.py  DocumentProcessor（多格式文档 → Markdown → 智能分块）
- pipeline.py  索引 + 扩展-检索-合并（MQE / HyDE）
"""

from .document import (
    DEFAULT_CHUNK_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    Document,
    DocumentProcessor,
    _approx_token_len,
    _chunk_paragraphs,
    _is_cjk,
    _split_paragraphs_with_headings,
    convert_to_markdown,
)
from .pipeline import (
    create_rag_pipeline,
    index_chunks,
    search_vectors_expanded,
    _prompt_hyde,
    _prompt_mqe,
)

__all__ = [
    "Document",
    "DocumentProcessor",
    "convert_to_markdown",
    "DEFAULT_CHUNK_TOKENS",
    "DEFAULT_OVERLAP_TOKENS",
    "create_rag_pipeline",
    "index_chunks",
    "search_vectors_expanded",
    "_prompt_mqe",
    "_prompt_hyde",
    "_split_paragraphs_with_headings",
    "_chunk_paragraphs",
    "_approx_token_len",
    "_is_cjk",
]
