# -*- coding: utf-8 -*-
"""
BrandAssetAgent —— 品牌资产与创意师

产出《品牌资产》模块：候选品牌名 / 品牌口号 / VI 方向 / 品牌故事 / 人设口吻。
须与前置《品牌定位》的定位语口径一致。
"""
from ._module_base import BrandModuleAgent

ASSET_SYSTEM = (
    "你是一名宠物品牌创意总监，擅长从 0 起盘一个品牌的名字/口号/VI 方向/故事/人设。"
    "基调：暖而有态度，把宠物当作平等家人；成分透明 + 陪伴情感双主线。"
    "若简报已有品牌名，命名聚焦「起盘优化与验证」，不必硬换；若暂无则给出候选。"
    "引用知识须标明演示口径。"
)

ASSET_FORMAT = (
    "用简洁中文，标题即结论，控制在 700 字内。\n"
    "固定用这些二级标题：\n"
    "## 候选品牌名\n"
    "## 品牌口号\n"
    "## VI 方向\n"
    "## 品牌故事\n"
    "## 人设口吻\n"
    "候选名给 2-3 个（各一句理由）；口号给 2-3 句；VI 讲色彩/气质/视觉关键词与应用示例；"
    "故事 150-200 字可被念出。"
)


class BrandAssetAgent(BrandModuleAgent):
    MODULE_TITLE = "品牌资产"
    KNOWLEDGE_QUERIES = ["品牌 命名 口号 VI 故事 人设 口吻", "品牌资产 一致性 checklist"]

    def __init__(self, name="brand_asset", llm=None, knowledge_dir=None):
        super().__init__(name=name, llm=llm, system_prompt=ASSET_SYSTEM, knowledge_dir=knowledge_dir)

    @property
    def FORMAT(self) -> str:
        return ASSET_FORMAT
