# -*- coding: utf-8 -*-
"""
ConsumerInsightAgent —— 消费者洞察师

产出《人群洞察》模块：主人群选定 / 画像 / 痛点与决策链路 / 情感需求与内容偏好。
"""
from ._module_base import BrandModuleAgent

INSIGHT_SYSTEM = (
    "你是一名宠物行业消费者洞察分析师，擅长把人群分层落到可指导定位与内容的洞察。"
    "从「养猫/养狗 × 新手/进阶 × 价格敏感度」入手，聚焦简报里品牌的目标人群线索。"
    "引用知识须标明演示口径，禁止编造无出处精确数字。"
)

INSIGHT_FORMAT = (
    "用简洁中文，标题即结论，分点陈述，控制在 600 字内。\n"
    "固定用这些二级标题：\n"
    "## 主人群\n"
    "## 人群画像\n"
    "## 痛点与决策链路\n"
    "## 情感需求与内容偏好"
)


class ConsumerInsightAgent(BrandModuleAgent):
    MODULE_TITLE = "人群洞察"
    KNOWLEDGE_QUERIES = ["养宠 人群 画像 铲屎官 新手 进阶", "养猫 白领 独居 陪伴", "养狗 新手 家庭 决策"]

    def __init__(self, name="consumer_insight", llm=None, knowledge_dir=None):
        super().__init__(name=name, llm=llm, system_prompt=INSIGHT_SYSTEM, knowledge_dir=knowledge_dir)

    @property
    def FORMAT(self) -> str:
        return INSIGHT_FORMAT
