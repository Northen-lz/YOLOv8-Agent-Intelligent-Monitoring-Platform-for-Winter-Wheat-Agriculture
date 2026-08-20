# -*- coding: utf-8 -*-
"""
AuthorAgent —— 项目作者介绍 Agent

读取 knowledge/author_info.txt，回答关于系统开发者、项目技术路线、
技术栈等问题。LLM 未配置或不可用时自动降级为关键词匹配的直接回答。
"""

from ..core.agent import Agent
from ..core.llm import HelloAgentsLLM
from ..tools.agriculture.author_tool import AuthorInfoTool

AUTHOR_SYSTEM_PROMPT = (
    "你代表「YOLOv8-Agent 农业智能监测平台」回答关于开发者与项目的介绍。"
    "请优先基于作者信息文件中的内容作答，语言亲切、结构清晰，"
    "可分点介绍：作者简介、技术方向、项目经历、使用框架、开发技术。"
)


class AuthorAgent(Agent):

    def __init__(self, name="author", llm=None, system_prompt=None, info_path=None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm,
                         system_prompt=system_prompt or AUTHOR_SYSTEM_PROMPT)
        self.author_tool = AuthorInfoTool(path=info_path)

    def run(self, question="", *args, **kwargs):
        # 兼容 run(input="...") / run("...")
        if not question and "input" in kwargs:
            question = kwargs.get("input")
        if not question and args:
            question = str(args[0])
        question = str(question or "").strip()
        if not question:
            question = "介绍系统开发者"

        info = self.author_tool.run(question=question)
        try:
            answer = self.llm.chat([{"role": "system", "content": self.system_prompt},
                                    {"role": "user",
                                     "content": f"用户问题: {question}\n\n作者信息:\n{info}"}])
            if answer:
                return str(answer)
        except Exception:
            pass
        # 降级：直接返回命中的作者信息
        return info
