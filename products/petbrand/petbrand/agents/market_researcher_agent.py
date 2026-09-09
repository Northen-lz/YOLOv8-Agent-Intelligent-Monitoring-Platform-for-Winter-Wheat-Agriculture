# -*- coding: utf-8 -*-
"""
MarketResearcherAgent —— 市场与竞品研究员

产出《市场与竞品》模块：中国养宠市场大盘结论 / 渠道结构 / 竞品格局 / 机会缺口。
"""
from ._module_base import BrandModuleAgent

RESEARCHER_SYSTEM = (
    "你是一名中国宠物市场研究分析师，擅长把行业洞察讲得结论先行、利于策略推导。"
    "分析聚焦猫狗全品类电商/App 赛道。引用知识须标明演示口径，禁止编造无出处精确数字。"
)

# 定位语相关方法
FORMAT_EXTRA = (
    "用简洁中文，标题即结论，分点陈述，控制在 600 字内。\n"
    "固定用这些二级标题：\n"
    "## 一句话结论\n"
    "## 市场大盘\n"
    "## 渠道结构\n"
    "## 竞品格局\n"
    "## 机会缺口"
)


class MarketResearcherAgent(BrandModuleAgent):
    MODULE_TITLE = "市场与竞品"
    KNOWLEDGE_QUERIES = ["宠物市场 大盘 规模 渠道 竞品 机会", "猫狗 电商 抖音 小红书 私域", "主粮 零食 用品 品类机会"]

    def __init__(self, name="market_researcher", llm=None, knowledge_dir=None):
        super().__init__(name=name, llm=llm, system_prompt=RESEARCHER_SYSTEM, knowledge_dir=knowledge_dir)

    @property
    def FORMAT(self) -> str:
        return FORMAT_EXTRA
