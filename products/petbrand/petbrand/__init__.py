# -*- coding: utf-8 -*-
"""
爪案（petbrand）· 猫狗品牌全案策划 Agent —— 产品包

基于通用框架 ha_framework（Agent/LLM/工具/记忆），镜像 products/wheat 的产品模板：
- 对话式攒案：顾问 Agent 一步步引导，产出 定位/人群/品牌资产 等模块并定稿
- 内置拟真演示品牌可开箱即用；也支持访谈真实品牌（brief 由访谈收集）
- 一键攒案：把已定稿模块汇总成可放映提案页 HTML + 全案 Markdown

导出对齐 wheat 顶层：Config / 各 Agent / build_ui。
Gradio 界面按需加载：from petbrand.app import build_ui（不在此 import，避免连带 gradio）。
"""

from .core.config import Config  # noqa: F401
from .agents.market_researcher_agent import MarketResearcherAgent  # noqa: F401
from .agents.consumer_insight_agent import ConsumerInsightAgent  # noqa: F401
from .agents.positioning_agent import PositioningAgent  # noqa: F401
from .agents.brand_asset_agent import BrandAssetAgent  # noqa: F401
from .agents.campaign_agents import CreativeModuleAgent, PlanModuleAgent  # noqa: F401
from .agents.deck_agent import DeckAgent  # noqa: F401
from .agents.brand_consultant_agent import BrandConsultantAgent  # noqa: F401
from .tools import (  # noqa: F401
    BrandKnowledgeTool,
    BriefTool,
    DeckBuilderTool,
)

__all__ = [
    "Config",
    "MarketResearcherAgent",
    "ConsumerInsightAgent",
    "PositioningAgent",
    "BrandAssetAgent",
    "CreativeModuleAgent",
    "PlanModuleAgent",
    "DeckAgent",
    "BrandConsultantAgent",
    "BrandKnowledgeTool",
    "BriefTool",
    "DeckBuilderTool",
]
