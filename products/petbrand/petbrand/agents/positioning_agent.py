# -*- coding: utf-8 -*-
"""
PositioningAgent —— 品牌定位策略师

产出《品牌定位》模块：目标人群选定 / 品类切口 / 差异化卖点 / 价值主张 / 定位语。
"""
from ._module_base import BrandModuleAgent

POSITIONING_SYSTEM = (
    "你是一名资深品牌策略师，擅长从 0 起盘品牌的定位设计（STP + 价值主张）。"
    "要求：人群聚焦、切口小而打得动、差异可被证明、定位语口语化有态度。"
    "必须与前置《市场与竞品》《人群洞察》口径一致，不得自相矛盾。"
    "引用知识须标明演示口径，禁止编造无出处精确数字。"
)

POSITIONING_FORMAT = (
    "用简洁中文，标题即结论，控制在 650 字内。\n"
    "固定用这些二级标题：\n"
    "## 目标人群选定\n"
    "## 品类切口\n"
    "## 差异化卖点\n"
    "## 价值主张\n"
    "## 定位语\n"
    "定位语给出 2-3 个候选，每个一句话，其中一个推荐。"
)


class PositioningAgent(BrandModuleAgent):
    MODULE_TITLE = "品牌定位"
    KNOWLEDGE_QUERIES = ["品牌 定位 方法论 人群 卖点 差异化 定位语", "定位 价值主张 一致性 自检"]

    def __init__(self, name="positioning", llm=None, knowledge_dir=None):
        super().__init__(name=name, llm=llm, system_prompt=POSITIONING_SYSTEM, knowledge_dir=knowledge_dir)

    @property
    def FORMAT(self) -> str:
        return POSITIONING_FORMAT
