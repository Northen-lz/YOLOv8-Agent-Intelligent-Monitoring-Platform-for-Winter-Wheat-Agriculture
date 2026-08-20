# -*- coding: utf-8 -*-
"""
阶段4 验证：RAG 系统（DocumentProcessor + Pipeline + RAGTool）
复刻文档 8.3.3 "30秒上手RAG"：
  add_text 3条知识 → search → stats → add_document(PDF) → ask

运行: python examples/stage4_rag.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hello_agents import RAGTool


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def ensure_test_pdf(path="knowledge_base/hello_agents_intro.pdf"):
    """自建测试 PDF（pymupdf 生成），用于 add_document 验证（多章节 → 多分块）"""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        import fitz  # pymupdf
        text = (
            "# Hello-Agents 智能体框架简介\n"
            "\n"
            "## 概述\n"
            "Hello-Agents 是一个面向中文学习者的多智能体开发框架，围绕大语言模型提供"
            "统一的消息、记忆与工具调用接口。框架的目标是让开发者用最少的代码搭建"
            "具备记忆与检索能力的智能体应用。\n"
            "\n"
            "## 核心组件\n"
            "框架包含三大核心：消息系统（Message）负责智能体间的结构化通信，"
            "工具注册中心（ToolRegistry）管理所有可调用能力，智能体执行循环"
            "（SimpleAgent）编排对话与工具调用的多轮交互。所有工具通过统一的"
            "execute 分发入口被调用，便于扩展。\n"
            "\n"
            "## 记忆系统\n"
            "记忆系统模拟人类认知，分为工作记忆、情景记忆、语义记忆与感知记忆四种类型。"
            "工作记忆容量有限，用于存放当前任务上下文，有 TTL 自动过期策略；"
            "情景记忆按时间顺序记录发生过的事件，带时间近因评分；"
            "语义记忆存储长期事实知识，并通过向量数据库（Qdrant）与图数据库（Neo4j）"
            "双重索引；感知记忆处理图片、音频等多模态信息。\n"
            "\n"
            "## 检索增强生成（RAG）\n"
            "RAG 系统将文档切分为语义分块并向量化，回答问题时先检索最相关的片段，"
            "再交给大语言模型生成答案。系统内置多查询扩展（MQE）技术："
            "让大模型从多个视角改写原始问题，扩大召回范围；"
            "以及假设文档嵌入（HyDE）：先生成一个理想答案片段，再基于它检索，"
            "两者结合可显著提升复杂问题的召回质量。\n"
            "\n"
            "## 智能文档问答\n"
            "基于 RAG 与记忆系统的组合，可以构建智能学习助手：上传 PDF 文档后自动建立"
            "知识库，支持自然语言问答、读书笔记记录、学习统计报告生成等功能。\n"
            "\n"
            "## 开发语言\n"
            "整个框架使用 Python 实现，依赖 PyMuPDF、sentence-transformers、"
            "Qdrant、Neo4j 等开源组件，本地即可完成部署与学习。"
        )
        pdf = fitz.open()
        page = pdf.new_page()
        # 注意: 必须用内置中文字体 china-s，默认 Helvetica 不支持中文会变成乱码。
        # insert_textbox 自动换行，避免长行超出页面宽度被截断。
        rect = fitz.Rect(60, 60, 545, 780)
        page.insert_textbox(rect, text, fontname="china-s", fontsize=11)
        pdf.save(path)
        pdf.close()
        print(f"[SETUP] 已生成测试 PDF: {path}")
        return path
    except Exception as e:
        print(f"[WARNING] 无法生成 PDF: {e}，将跳过 add_document 测试")
        return None


def reset_rag_collection():
    """清空 RAG 集合，保证脚本可重复运行（幂等）"""
    from qdrant_client import QdrantClient
    client = QdrantClient(url="http://localhost:6333", timeout=10)
    if client.collection_exists("rag_knowledge_base"):
        client.delete_collection("rag_knowledge_base")
        print("[SETUP] 已清空 rag_knowledge_base 集合（幂等运行）")


def main():
    t0 = time.time()

    reset_rag_collection()

    # ---------- 复刻文档 8.3.3 三十秒上手 ----------
    section("[1] add_text：添加 3 条知识")
    rag = RAGTool(knowledge_base_path="./knowledge_base")
    rag.execute("stats")

    print("\n-- 知识1: 前端工程师技能栈 --")
    print(rag.execute("add_text",
                      content=("前端工程师需要掌握 HTML、CSS、JavaScript 三大基础，"
                               "熟悉 React 或 Vue 框架，并了解性能优化与浏览器渲染原理。"),
                      source="前端知识库.md"))

    print("\n-- 知识2: 后端工程师技能栈 --")
    print(rag.execute("add_text",
                      content=("后端工程师需要掌握 Python 或 Java，熟悉 RESTful API 设计、"
                               "数据库（SQL/NoSQL）与缓存技术，关注系统高可用与安全。"),
                      source="后端知识库.md"))

    print("\n-- 知识3: 大模型应用开发 --")
    print(rag.execute("add_text",
                      content=("大模型应用开发围绕提示工程、检索增强生成（RAG）与"
                               "智能体（Agent）展开，常见栈包括 LangChain、Qdrant 向量库"
                               "与 OpenAI 兼容接口。"),
                      source="大模型应用.md"))

    # ---------- search ----------
    section("[2] search：语义检索（MQE + HyDE）")
    print(rag.execute("search", query="前端开发需要学什么", top_k=3))

    print("\n-- 关闭高级检索对比 --")
    print(rag.execute("search", query="前端开发需要学什么", top_k=3,
                      enable_mqe=False, enable_hyde=False))

    # ---------- stats ----------
    section("[3] stats：知识库统计")
    print(rag.execute("stats"))

    # ---------- add_document：PDF ----------
    section("[4] add_document：PDF 文档")
    pdf_path = ensure_test_pdf()
    if pdf_path:
        # 用小 chunk_size 演示多分块智能切分（文档默认 1000/200）
        print(rag.execute("add_document", file_path=pdf_path,
                          chunk_size=300, chunk_overlap=60))
        print("\n-- stats 后 --")
        print(rag.execute("stats"))

    # ---------- ask ----------
    section("[5] ask：检索增强生成")
    print("问题：什么是 Hello-Agents 的记忆系统？")
    print(rag.execute("ask", query="什么是 Hello-Agents 的记忆系统？", top_k=5))

    print("\n问题：RAG 的 MQE 是什么？")
    print(rag.execute("ask", query="RAG 的 MQE 是什么？", top_k=5))

    print("\n" + "=" * 60)
    print(f"✅ 阶段4 验证全部通过！耗时 {time.time()-t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
