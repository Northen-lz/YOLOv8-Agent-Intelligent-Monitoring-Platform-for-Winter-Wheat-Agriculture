# -*- coding: utf-8 -*-
"""
DeckAgent —— 提案呈现师（攒案汇总）

确定性调用 DeckBuilderTool：把已定稿模块 + 品牌简报汇总成提案页 HTML 与全案 Markdown，
落盘 outputs/decks/<case_id>/。本 Agent 不调用 LLM（内容均来自已定稿模块）。
"""
from typing import Dict

from ha_framework.core.agent import Agent
from ha_framework.core.llm import HelloAgentsLLM
from ..tools.petresearch.deck_builder import DeckBuilderTool

DECK_SYSTEM = (
    "你负责把已定稿模块攒成一份可直接路演的提案页。内容已在定稿模块中，"
    "你不新增观点，只做结构化汇总与呈现顺序整理。"
)


class DeckAgent(Agent):
    MODULE_TITLE = "提案页"

    def __init__(self, name="deck", llm=None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm, system_prompt=DECK_SYSTEM)
        self.builder = DeckBuilderTool()

    def assemble(self, case_dir: str) -> Dict[str, str]:
        """确定性汇总：返回 {html, md, name, brand_name}"""
        return self.builder.build(case_dir)

    def run(self, *args, **kwargs) -> str:
        return self.builder.run(*args, **kwargs)
