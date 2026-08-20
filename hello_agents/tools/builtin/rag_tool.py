# -*- coding: utf-8 -*-
"""
Hello-Agents RAG 检索增强生成工具（RAGTool）
对齐文档第八章 8.3.3 RAGTool

设计（"统一入口，分发处理"）：
- execute(action, **kwargs) 通过 action 参数指定具体操作
- 支持操作：add_text / add_document / search / ask / stats
- 多知识库命名空间：self._pipelines[rag_namespace] 各自独立

操作参数（对齐文档）：
- add_text:      content, source, **metadata
- add_document:  file_path, chunk_size=1000, chunk_overlap=200
- search:        query, top_k, enable_mqe, enable_hyde, score_threshold
- ask:           query, top_k, 检索增强生成（返回答案 + 来源）
- stats:         知识库分块统计
"""

import os
from typing import Any, Dict, List, Optional

from ...core.config import Config
from ...core.llm import HelloAgentsLLM
from ...memory.rag.document import (
    DocumentProcessor,
    _chunk_paragraphs,
    _split_paragraphs_with_headings,
)
from ...memory.rag.pipeline import (
    create_rag_pipeline,
    index_chunks,
    search_vectors_expanded,
)
from ..base import BaseTool


class RAGTool(BaseTool):
    """RAG工具 - 为Agent提供检索增强生成能力"""

    def __init__(
            self,
            knowledge_base_path: str = "./knowledge_base",
            qdrant_url: Optional[str] = None,
            qdrant_api_key: Optional[str] = None,
            collection_name: str = "rag_knowledge_base",
            rag_namespace: str = "default",
    ):
        super().__init__(
            name="rag",
            description="RAG工具 - 支持文档知识库的检索增强生成",
        )

        self.knowledge_base_path = knowledge_base_path
        os.makedirs(knowledge_base_path, exist_ok=True)

        # 多命名空间管道（每个 rag_namespace 独立集合/过滤）
        self._pipelines: Dict[str, Dict[str, Any]] = {}
        self._default_namespace = rag_namespace

        self._pipelines[rag_namespace] = create_rag_pipeline(
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            collection_name=collection_name,
            rag_namespace=rag_namespace,
        )

        self.doc_processor = DocumentProcessor()

    # ---------------- 统一入口 ----------------

    def execute(self, action: str = "search", **kwargs) -> str:
        """执行 RAG 操作"""
        handlers = {
            "add_text": self._add_text,
            "add_document": self._add_document,
            "search": self._search,
            "ask": self._ask,
            "stats": self._stats,
        }
        handler = handlers.get(action)
        if handler is None:
            return f"[RAGTool] 未知操作: {action}（支持 add_text/add_document/search/ask/stats）"
        try:
            return handler(**kwargs)
        except TypeError as e:
            # 参数映射错误时给出友好提示，避免崩溃
            return f"[RAGTool] {action} 参数错误: {e}"
        except Exception as e:
            return f"[RAGTool] {action} 执行失败: {e}"

    def run(self, *args, **kwargs) -> str:
        """兼容 BaseTool.run，支持多种调用形态：
        - run({"action": "search", "query": ...})（文档写法）
        - run(action="search", query=...) / run(input="...")（SimpleAgent 解析路径）
        - run("查询文本")（字符串直接检索）
        """
        params = {}
        if args and isinstance(args[0], dict):
            # 兼容文档写法：run({"action": "search", ...}) 传单个参数字典
            params = dict(args[0])
        elif args:
            # 字符串直接传入 → 默认视为 search 的 query
            params = {"query": args[0]}
        if kwargs:
            # input 键（SimpleAgent 对非 search/memory 工具的默认封装）
            inp = kwargs.pop("input", None)
            if inp is not None:
                if isinstance(inp, dict):
                    params = {**inp, **params}
                elif "query" not in params:
                    params["query"] = inp
            params = {**params, **kwargs}
        action = params.pop("action", "search")
        return self.execute(action=action, **params)

    # ---------------- 管道辅助 ----------------

    def _check_ready(self, rag_namespace: Optional[str] = None) -> Optional[str]:
        """Qdrant 服务未连接时返回提示文本（否则返回 None）"""
        store = self._get_pipeline(rag_namespace)["store"]
        if getattr(store, "connected", True) is False:
            return ("⚠️ Qdrant 向量服务未连接（localhost:6333），RAG 检索暂不可用。"
                    "请先启动 Qdrant 服务，再用 seed_rag_knowledge 灌入知识库。")
        return None

    def _get_pipeline(self, rag_namespace: Optional[str] = None):
        ns = rag_namespace or self._default_namespace
        if ns not in self._pipelines:
            self._pipelines[ns] = create_rag_pipeline(
                collection_name="rag_knowledge_base",
                rag_namespace=ns,
            )
        return self._pipelines[ns]

    # ---------------- 操作实现 ----------------

    def _add_text(self, content: str, source: Optional[str] = None,
                  rag_namespace: Optional[str] = None,
                  chunk_size: int = 1000, chunk_overlap: int = 200,
                  **metadata) -> str:
        """添加纯文本知识（自动分块 → 索引；chunk_size 控制粒度）"""
        if not content or not content.strip():
            return "[RAGTool] 空文本无法添加"

        # 文本 → 分段 → 分块（chunk_size 越小块越细，检索召回越精准）
        paragraphs = _split_paragraphs_with_headings(content)
        chunks = _chunk_paragraphs(paragraphs, chunk_size, chunk_overlap)
        for c in chunks:
            c["source"] = source or "add_text"

        ready = self._check_ready(rag_namespace)
        if ready:
            return ready
        pipeline = self._get_pipeline(rag_namespace)
        added = index_chunks(pipeline["store"], chunks,
                             rag_namespace=pipeline["rag_namespace"])
        print(f"[RAGTool] add_text: {added} 个分块（source={source or 'add_text'}）")
        return f"✅ 已添加知识，生成 {added} 个分块"

    def _add_document(self, file_path: str, chunk_size: int = 1000,
                      chunk_overlap: int = 200,
                      rag_namespace: Optional[str] = None) -> str:
        """添加文档（多格式：PDF/Word/MD/TXT 等）"""
        if not os.path.exists(file_path):
            return f"[RAGTool] 文件不存在: {file_path}"
        ready = self._check_ready(rag_namespace)
        if ready:
            return ready

        doc = self.doc_processor.process(
            file_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        )
        for c in doc.chunks:
            c["source"] = file_path

        pipeline = self._get_pipeline(rag_namespace)
        added = index_chunks(pipeline["store"], doc.chunks,
                             rag_namespace=pipeline["rag_namespace"])
        return (f"✅ 文档处理完成: {os.path.basename(file_path)} "
                f"→ {len(doc.chunks)} 个分块，已全部索引")

    def _search(self, query: str, top_k: int = 8,
                rag_namespace: Optional[str] = None,
                enable_mqe: Optional[bool] = None,
                enable_hyde: Optional[bool] = None,
                score_threshold: Optional[float] = None) -> str:
        """语义检索（MQE + HyDE 扩展；开关默认读 Config，env 可覆盖）"""
        if not query:
            return "[RAGTool] 查询不能为空"
        ready = self._check_ready(rag_namespace)
        if ready:
            return ready

        # 开关优先级：单次显式传参 > UI 运行时覆盖（RAG_BOOST_OVERRIDE）> env 默认
        boost = getattr(Config, "RAG_BOOST_OVERRIDE", None)
        if boost is not None:
            enable_mqe = boost if enable_mqe is None else enable_mqe
            enable_hyde = boost if enable_hyde is None else enable_hyde
        else:
            enable_mqe = Config.RAG_ENABLE_MQE if enable_mqe is None else enable_mqe
            enable_hyde = Config.RAG_ENABLE_HYDE if enable_hyde is None else enable_hyde

        pipeline = self._get_pipeline(rag_namespace)
        hits = search_vectors_expanded(
            pipeline["store"],
            query,
            top_k=top_k,
            rag_namespace=pipeline["rag_namespace"],
            only_rag_data=True,
            score_threshold=score_threshold,
            enable_mqe=enable_mqe,
            enable_hyde=enable_hyde,
        )

        if not hits:
            return "😕 未检索到相关知识，试试换个说法或先 add_document / add_text"

        lines = [f"🔍 检索到 {len(hits)} 条相关知识:"]
        for i, h in enumerate(hits, 1):
            payload = h.get("payload") or {}
            content = payload.get("content", "")[:120]
            score = h.get("score", 0)
            source = payload.get("source", "unknown")
            lines.append(f"\n[{i}] (score={score:.3f}, 来源={os.path.basename(source)})")
            lines.append(f"    {content}")
        return "\n".join(lines)

    def _ask(self, query: str, top_k: int = 8,
             rag_namespace: Optional[str] = None,
             enable_mqe: Optional[bool] = None,
             enable_hyde: Optional[bool] = None,
             score_threshold: Optional[float] = None) -> str:
        """检索增强生成：检索 → 拼上下文 → LLM 生成答案"""
        if not query:
            return "[RAGTool] 查询不能为空"
        ready = self._check_ready(rag_namespace)
        if ready:
            return ready

        # 开关优先级：单次显式传参 > UI 运行时覆盖（RAG_BOOST_OVERRIDE）> env 默认
        boost = getattr(Config, "RAG_BOOST_OVERRIDE", None)
        if boost is not None:
            enable_mqe = boost if enable_mqe is None else enable_mqe
            enable_hyde = boost if enable_hyde is None else enable_hyde
        else:
            enable_mqe = Config.RAG_ENABLE_MQE if enable_mqe is None else enable_mqe
            enable_hyde = Config.RAG_ENABLE_HYDE if enable_hyde is None else enable_hyde

        pipeline = self._get_pipeline(rag_namespace)
        hits = search_vectors_expanded(
            pipeline["store"],
            query,
            top_k=top_k,
            rag_namespace=pipeline["rag_namespace"],
            only_rag_data=True,
            score_threshold=score_threshold,
            enable_mqe=enable_mqe,
            enable_hyde=enable_hyde,
        )

        if not hits:
            return "😕 知识库中未找到相关内容。请先 add_text / add_document 添加知识。"

        # 拼接上下文
        context_parts = []
        for i, h in enumerate(hits, 1):
            payload = h.get("payload") or {}
            source = payload.get("source", "unknown")
            context_parts.append(
                f"【片段{i}｜来源:{os.path.basename(source)}】\n"
                f"{payload.get('content', '')}"
            )
        context = "\n\n".join(context_parts)

        messages = [
            {"role": "system", "content":
             "你是一个知识库问答助手。请根据提供的资料片段回答用户问题："
             "只要资料与问题相关，就尽量提炼、概括出答案；"
             "资料完全无关时才说明无法回答。回答要简洁准确，用中文。"
             "不要自行添加参考来源标注。"},
            {"role": "user", "content":
             f"资料片段:\n{context}\n\n用户问题: {query}"},
        ]

        llm: HelloAgentsLLM = pipeline["llm"]
        try:
            answer = llm.invoke(messages, temperature=0.3)
        except Exception as e:
            print(f"[WARNING] LLM 生成失败: {e}")
            return ("[RAGTool] LLM 调用失败，仅返回检索结果：\n" + self._search(query))

        # 来源列表
        sources = sorted({os.path.basename((h.get("payload") or {}).get("source", "unknown"))
                          for h in hits})
        sources_str = "、".join(sources)
        return f"{answer}\n\n📚 参考来源: {sources_str}"

    def _stats(self, rag_namespace: Optional[str] = None) -> str:
        """知识库统计"""
        ready = self._check_ready(rag_namespace)
        if ready:
            return ready
        pipeline = self._get_pipeline(rag_namespace)
        store = pipeline["store"]
        try:
            count = store.count(collection=store.collection)
        except Exception:
            count = -1
        return (f"📊 RAG 知识库统计 (namespace={pipeline['rag_namespace']}):\n"
                f"  - 集合: {store.collection}\n"
                f"  - 分块总数: {count}")
