# -*- coding: utf-8 -*-
"""
BrandModuleAgent —— 品牌模块 Agent 基类

各模块 Agent 共享：知识检索取依据（BrandKnowledgeTool.fetch）+ LLM 组稿。
generate() 产出该模块的 markdown 正文；具体方法论文案由子类 system 提示约束。
输入统一为品牌简报文本 + 可选前置模块上下文（保证前后口径一致）。
"""

from typing import Dict, List

from ha_framework.core.agent import Agent
from ha_framework.core.llm import HelloAgentsLLM
from ..tools.petresearch.knowledge_tool import BrandKnowledgeTool


class BrandModuleAgent(Agent):
    """模块 Agent 基类：知识依据 + 确定性组稿"""

    # 子类覆盖：检索关键词 / 系统提示
    KNOWLEDGE_QUERIES: List[str] = []
    MODULE_TITLE = "模块"

    def __init__(self, name: str, llm=None, system_prompt: str = "", knowledge_dir: str = None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm, system_prompt=system_prompt)
        self._kb = BrandKnowledgeTool(knowledge_dir=knowledge_dir)

    def fetch_kb(self, queries: List[str] = None) -> str:
        """把多组检索到的知识拼接为 grounding 文本（找不到就返回空）"""
        blocks = []
        for q in (queries or self.KNOWLEDGE_QUERIES):
            got = self._kb.fetch(q, top_k=2)
            if got:
                blocks.append(got)
        return "\n\n".join(blocks)

    def generate(self, brief_md: str, context_md: str = "", angle: str = "") -> str:
        """核心组稿：依据知识 + 简报 + 上下文，产出该模块 markdown 正文"""
        kb = self.fetch_kb()
        user = [
            "【你的任务】基于下列「品牌简报 + 参考资料」产出"
            f"《{self.MODULE_TITLE}》模块内容。只输出正文（markdown），不要任何开场白与解释。",
            "",
            "【品牌简报】",
            brief_md,
        ]
        if context_md:
            user += ["", "【前置模块（须与其口径一致）】", context_md[:4000]]
        if angle:
            user += ["", "【本稿切入角度】", angle]
        if kb:
            user += ["", "【可引用知识（演示口径，引用时注明来源；无实证数据不要编造精确数字）】", kb[:4000]]
        user += ["", "【格式要求】", self.FORMAT]
        answer = self.llm.chat([{"role": "system", "content": self.system_prompt},
                                {"role": "user", "content": "\n".join(user)}])
        return str(answer).strip() if answer is not None else "（模块生成失败，请换角度重写）"

    @property
    def FORMAT(self) -> str:
        return "用简洁中文，标题即结论，分点陈述，控制在 600 字内。"
