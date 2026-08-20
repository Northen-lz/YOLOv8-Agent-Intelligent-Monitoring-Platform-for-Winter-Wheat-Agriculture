# -*- coding: utf-8 -*-
"""
阶段5：智能文档问答助手（Gradio Web 应用）
对齐文档第八章 8.4：RAG + Memory 有机组合的 PDFLearningAssistant

功能：
- 上传 PDF → load_document：RAG 索引 + 情景记忆记录
- 智能问答 → ask：MQE/HyDE 检索增强生成（答案 + 来源）
- 读书笔记 → add_note：语义记忆存储
- 复习回忆 → recall：跨记忆检索
- 学习报告 → generate_report：汇总笔记 + 问答历史 + 统计

运行: python app.py  然后浏览器访问 http://localhost:7860
"""

import os
import time
import uuid
from datetime import datetime
from typing import List, Optional

import gradio as gr

from hello_agents import HelloAgentsLLM, RAGTool, MemoryTool

# 全局助手实例（单用户演示）
ASSISTANT = None


class PDFLearningAssistant:
    """智能文档问答助手 - 结合 RAG 检索与记忆系统"""

    def __init__(
            self,
            user_id: str = "default_user",
            knowledge_base_path: str = "./knowledge_base",
    ):
        # 用户隔离 + 会话追踪（对齐文档 8.4.2）
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())
        self.created_at = datetime.now().isoformat()

        # 两大子系统：RAG（知识检索）+ Memory（学习记忆）
        self.rag = RAGTool(knowledge_base_path=knowledge_base_path)
        self.memory = MemoryTool(
            user_id=user_id,
            memory_types=["working", "episodic", "semantic"],
        )

        # 会话状态
        self.loaded_docs: List[str] = []
        self.qa_history: List[str] = []
        self.notes: List[str] = []

    # ---------------- 文档加载 ----------------

    def load_document(self, file_path: str) -> str:
        """加载文档：RAG 索引 + 情景记忆"""
        if not file_path or not os.path.exists(file_path):
            return "❌ 请先上传 PDF 文档"

        result = self.rag.execute("add_document", file_path=file_path)
        self.loaded_docs.append(os.path.basename(file_path))

        # 情景记忆：记录"加载了文档"这一事件
        self.memory.execute(
            "add",
            content=f"{datetime.now().strftime('%Y-%m-%d %H:%M')} "
                    f"用户 {self.user_id} 加载了文档 {os.path.basename(file_path)}",
            memory_type="episodic",
            importance=0.6,
        )
        return result

    # ---------------- 智能问答 ----------------

    def ask(self, query: str) -> str:
        """检索增强生成 + 工作记忆记录"""
        if not query or not query.strip():
            return "请输入问题"
        answer = self.rag.execute("ask", query=query.strip())
        # 工作记忆：记录最近的问答，供后续回忆
        self.memory.execute(
            "add",
            content=f"用户提问: {query.strip()}",
            memory_type="working",
            importance=0.5,
        )
        self.qa_history.append(query.strip())
        return answer

    # ---------------- 读书笔记 ----------------

    def add_note(self, content: str) -> str:
        """记笔记 → 语义记忆（长期知识）"""
        if not content or not content.strip():
            return "请输入笔记内容"
        content = content.strip()
        result = self.memory.execute(
            "add",
            content=content,
            memory_type="semantic",
            importance=0.8,
        )
        # 会话内同步记录（供学习报告使用）
        self.notes.append(content)
        return result

    def recall(self, query: str) -> str:
        """复习回忆：检索语义/情景/工作记忆"""
        if not query or not query.strip():
            return "请输入回忆关键词"
        return self.memory.execute(
            "search", query=query.strip(), limit=5,
        )

    # ---------------- 统计与报告 ----------------

    def get_stats(self) -> str:
        """组合统计：RAG 知识库 + 记忆系统"""
        rag_stats = self.rag.execute("stats")
        mem_stats = self.memory.execute("stats")
        return (
            f"👤 用户: {self.user_id} | 会话: {self.session_id[:8]}\n"
            f"📄 已加载文档: {len(self.loaded_docs)} 个\n"
            f"💬 问答次数: {len(self.qa_history)}\n"
            f"{'-' * 40}\n{rag_stats}\n{'-' * 40}\n{mem_stats}"
        )

    def generate_report(self) -> str:
        """生成学习报告：LLM 汇总笔记 + 问答历史 + 统计"""
        # 收集素材：会话笔记 + 语义记忆中的历史笔记（跨会话）
        notes = list(self.notes)
        try:
            notes_hits = self.memory.memory_manager.retrieve_memories(
                "学习笔记 重点", limit=10, memory_types=["semantic"]
            )
            for n in notes_hits:
                if n.content not in notes:
                    notes.append(n.content)
        except Exception as e:
            print(f"[WARNING] 检索历史笔记失败: {e}")
        qa = self.qa_history[-10:]

        materials = [
            f"学习用户: {self.user_id}",
            f"本次会话提问数: {len(self.qa_history)}",
            f"已加载文档: {', '.join(self.loaded_docs) or '无'}",
        ]
        if notes:
            materials.append(f"读书笔记 {len(notes)} 条:\n" + "\n".join(f"- {n[:80]}" for n in notes))
        else:
            materials.append("读书笔记: 暂无")
        if qa:
            materials.append("最近提问:\n" + "\n".join(f"- {q}" for q in qa))
        else:
            materials.append("提问记录: 暂无")

        prompt = ("\n".join(materials)
                  + "\n\n请生成一份简洁的中文学习报告：总结学习内容、"
                    "已掌握的知识点、建议巩固的方向。")

        try:
            llm = HelloAgentsLLM()
            report = llm.invoke(
                [{"role": "system",
                  "content": "你是学习教练，用友好、鼓励的语气生成学习报告。"},
                 {"role": "user", "content": prompt}],
                temperature=0.4,
            )
            return f"📋 学习报告\n{'-' * 40}\n{report}"
        except Exception as e:
            print(f"[WARNING] 报告生成失败: {e}")
            return f"📋 学习报告（LLM 失败，返回统计）\n{self.get_stats()}"


# ================================================================
# Gradio 界面（对齐文档 8.4.5）
# ================================================================

def get_assistant() -> PDFLearningAssistant:
    global ASSISTANT
    if ASSISTANT is None:
        ASSISTANT = PDFLearningAssistant()
    return ASSISTANT


def build_ui():
    with gr.Blocks(title="智能文档问答助手", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# 📚 智能文档问答助手\n"
            "上传 PDF → 智能问答 → 记笔记 → 生成学习报告\n"
            "（基于 Hello-Agents：RAG 检索增强生成 + 记忆系统）"
        )

        with gr.Row():
            # ---- 左列：文档管理 ----
            with gr.Column(scale=1):
                file_input = gr.File(
                    label="上传 PDF 文档", file_types=[".pdf", ".md", ".txt"],
                    file_count="single",
                )
                load_btn = gr.Button("📄 加载文档", variant="primary")
                load_status = gr.Textbox(label="加载状态", lines=3, interactive=False)

                stats_btn = gr.Button("📊 查看统计")
                stats_out = gr.Textbox(label="系统统计", lines=8, interactive=False)

                report_btn = gr.Button("📋 生成学习报告")
                report_out = gr.Textbox(label="学习报告", lines=8, interactive=False)

            # ---- 右列：问答 + 笔记 ----
            with gr.Column(scale=2):
                gr.Markdown("### 💬 智能问答")
                with gr.Row():
                    ask_input = gr.Textbox(label="你的问题", placeholder="例如：什么是记忆系统？", scale=3)
                    ask_btn = gr.Button("提问", variant="primary", scale=1)
                ask_out = gr.Markdown(label="回答")

                gr.Markdown("### ✍️ 读书笔记")
                with gr.Row():
                    note_input = gr.Textbox(label="记笔记", placeholder="记录你学到的重点…", scale=3)
                    note_btn = gr.Button("保存笔记", scale=1)
                note_status = gr.Textbox(label="笔记状态", lines=2, interactive=False)

                gr.Markdown("### 🔁 复习回忆")
                with gr.Row():
                    recall_input = gr.Textbox(label="回忆关键词", placeholder="例如：RAG", scale=3)
                    recall_btn = gr.Button("回忆", scale=1)
                recall_out = gr.Markdown(label="回忆结果")

        # ---- 事件绑定 ----
        load_btn.click(
            lambda f: get_assistant().load_document(f),
            inputs=file_input, outputs=load_status,
        )
        ask_btn.click(
            lambda q: get_assistant().ask(q),
            inputs=ask_input, outputs=ask_out,
        )
        ask_input.submit(
            lambda q: get_assistant().ask(q),
            inputs=ask_input, outputs=ask_out,
        )
        note_btn.click(
            lambda n: get_assistant().add_note(n),
            inputs=note_input, outputs=note_status,
        )
        recall_btn.click(
            lambda q: get_assistant().recall(q),
            inputs=recall_input, outputs=recall_out,
        )
        stats_btn.click(
            lambda: get_assistant().get_stats(),
            outputs=stats_out,
        )
        report_btn.click(
            lambda: get_assistant().generate_report(),
            outputs=report_out,
        )

    return demo


if __name__ == "__main__":
    demo = build_ui()
    print("🚀 启动智能文档问答助手: http://localhost:7860")
    demo.launch(server_name="127.0.0.1", server_port=7860)
