# -*- coding: utf-8 -*-
"""
阶段5 验证：PDFLearningAssistant（无头验证核心逻辑）
复刻文档 8.4：加载文档 → 问答 → 记笔记 → 回忆 → 统计 → 学习报告

运行: python examples/stage5_assistant.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 复用阶段4的测试 PDF 生成器
from examples.stage4_rag import ensure_test_pdf

from app import PDFLearningAssistant


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    t0 = time.time()

    section("[0] 初始化助手")
    assistant = PDFLearningAssistant(user_id="student_zhang")
    print(assistant.get_stats())

    # 准备测试 PDF
    pdf_path = ensure_test_pdf()
    assert pdf_path, "缺少测试 PDF"

    section("[1] load_document：加载 PDF 并索引")
    print(assistant.load_document(pdf_path))
    assert len(assistant.loaded_docs) == 1, "文档应被记录"

    section("[2] ask：检索增强生成")
    print("Q: 什么是记忆系统？")
    print(assistant.ask("什么是记忆系统？"))
    assert len(assistant.qa_history) == 1, "问答应被记录"

    print("\nQ: MQE 是什么？")
    print(assistant.ask("MQE 是什么？"))

    section("[3] add_note：记笔记 → 语义记忆")
    print(assistant.add_note("记忆系统分四种：工作/情景/语义/感知"))
    print(assistant.add_note("RAG 用 MQE 与 HyDE 提升检索质量"))
    assert len(assistant.notes) == 2, "应记录 2 条笔记"

    section("[4] recall：复习回忆")
    print("回忆 'RAG'：")
    print(assistant.recall("RAG"))

    section("[5] get_stats：组合统计")
    print(assistant.get_stats())

    section("[6] generate_report：学习报告")
    print(assistant.generate_report())

    print("\n" + "=" * 60)
    print(f"✅ 阶段5 核心逻辑验证通过！耗时 {time.time()-t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
