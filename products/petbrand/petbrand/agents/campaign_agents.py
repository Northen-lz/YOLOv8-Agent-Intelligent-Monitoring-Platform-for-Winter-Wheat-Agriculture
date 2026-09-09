# -*- coding: utf-8 -*-
"""
CampaignAgent —— 非「品牌全案」类型的类型专属模块 Agent（按 kind 参数化）

- CreativeModuleAgent：产出「创意类」模块 —— 传播主题与大创意(campaign) / 上市概念与首发创意(launch) / 促销主题与机制(promo)
- PlanModuleAgent：    产出「执行类」模块 —— 内容·媒介·预算·KPI(campaign) / 三阶段打法与预算(launch) / 流量波段与预算(promo)

spec.title 与 core.case_plans 里对应模块的 title 保持一致（烟测断言）。
基类 BrandModuleAgent.FORMAT 是无 setter 的 property，故按 kind 的格式只能经子类 @property 返回。
MODULE_TITLE / KNOWLEDGE_QUERIES 是普通类属性，可安全设为实例属性。
"""
from ._module_base import BrandModuleAgent

# ---------------- 创意类 spec ----------------
_CREATIVE_SPECS = {
    "campaign": {
        "title": "传播主题与大创意",
        "system": (
            "你是一名宠物品牌传播战役创意总监。基于《受众洞察》《传播定位基点》口径，"
            "提出可贯穿内容/媒介/预算的一句话传播总主题（大创意），并落到分人群可执行的内容与活动。"
            "引用知识须标明演示口径，禁止编造无出处精确数字。"
        ),
        "queries": ["传播主题 大创意 战役 内容 活动", "内容 活动玩法 UGC 达人 事件",
                    "种草 内容 抖音 小红书 私域", "节点 引爆 跨界 话题"],
        "format": (
            "用简洁中文，标题即结论，控制在 700 字内。\n"
            "固定用这些二级标题：\n"
            "## 传播总主题\n"
            "## 大创意与内容主线\n"
            "## 分人群内容与活动玩法\n"
            "## 传播节奏与媒介配比建议"
        ),
    },
    "launch": {
        "title": "上市概念与首发创意",
        "system": (
            "你是一名宠物品牌新品上市策划。设计上市概念、首发大事件与预热创意、首销转化打法，"
            "须承接《上市定位切口》。引用知识须标明演示口径，禁止编造无出处精确数字。"
        ),
        "queries": ["上市 新品 首发 概念 事件", "预热期 创意 悬念 预约 发布",
                    "首销 转化 冷启动 尝鲜 复购", "上市 主张 卖点 演绎"],
        "format": (
            "用简洁中文，标题即结论，控制在 700 字内。\n"
            "固定用这些二级标题：\n"
            "## 上市概念\n"
            "## 首发大事件与预热创意\n"
            "## 核心卖点演绎\n"
            "## 首销转化与冷启动打法"
        ),
    },
    "promo": {
        "title": "促销主题与机制",
        "system": (
            "你是一名宠物品牌大促策划。设计一次大促（如 618/双11/宠物节）的主题、促销机制组合、"
            "货品与内容承接、主推人群转化抓手，承接《大促定位基点》。引用知识须标明演示口径，禁止编造无出处精确数字。"
        ),
        "queries": ["大促 促销 主题 机制 折扣", "促销 机制 满减 赠品 会员 玩法",
                    "货品 内容 承接 转化 主推", "节点 蓄水 返场 直播"],
        "format": (
            "用简洁中文，标题即结论，控制在 700 字内。\n"
            "固定用这些二级标题：\n"
            "## 大促主题\n"
            "## 促销机制组合\n"
            "## 货品与内容承接\n"
            "## 主推人群与转化抓手"
        ),
    },
}

# ---------------- 执行类 spec ----------------
_PLAN_SPECS = {
    "campaign": {
        "title": "内容·媒介·预算·KPI",
        "system": (
            "你是一名宠物品牌媒介与整合营销计划经理。承接《传播主题与大创意》，产出媒介组合、"
            "预算分配、排期节奏与 KPI/复盘机制。引用知识须标明演示口径，禁止编造无出处精确数字。"
        ),
        "queries": ["媒介组合 预算 投放 排期", "KPI 内容 分发 转化 复盘",
                    "媒介 达人 直播 私域 配比", "蓄水 引爆 收官 节奏"],
        "format": (
            "用简洁中文，标题即结论，控制在 700 字内。\n"
            "固定用这些二级标题：\n"
            "## 媒介组合与资源配比\n"
            "## 预算分配\n"
            "## 排期与节奏\n"
            "## KPI 与复盘机制"
        ),
    },
    "launch": {
        "title": "三阶段打法与预算",
        "system": (
            "你是一名宠物品牌新品上市操盘手。把上市拆为预热/发布/首销三阶段，给出每阶段动作、"
            "渠道与媒介配比、预算分配与 KPI。引用知识须标明演示口径，禁止编造无出处精确数字。"
        ),
        "queries": ["预热期 发布期 首销 转化 三阶段", "上市 预算 渠道 排期 KPI",
                    "新品 冷启动 尝鲜 复购", "黄金 72 小时 事件 达人"],
        "format": (
            "用简洁中文，标题即结论，控制在 700 字内。\n"
            "固定用这些二级标题：\n"
            "## 三阶段打法（预热/发布/首销转化）\n"
            "## 渠道与媒介配比\n"
            "## 预算分配\n"
            "## KPI 与风险预案"
        ),
    },
    "promo": {
        "title": "流量波段与预算",
        "system": (
            "你是一名宠物品牌大促流量操盘手。承接《促销主题与机制》，按蓄水/爆发/返场三波段规划"
            "流量采买结构、预算分配与拉新/转化 KPI。引用知识须标明演示口径，禁止编造无出处精确数字。"
        ),
        "queries": ["蓄水 爆发 返场 波段", "流量 采买 结构 预算 拉新 转化",
                    "大促 竞价 达人 直播 站内 站外", "加购 收藏 会员 复购 GMV"],
        "format": (
            "用简洁中文，标题即结论，控制在 700 字内。\n"
            "固定用这些二级标题：\n"
            "## 波段规划（蓄水/爆发/返场）\n"
            "## 流量采买与结构\n"
            "## 预算分配\n"
            "## 拉新与转化 KPI"
        ),
    },
}


class _KindAgent(BrandModuleAgent):
    """kind 参数化基类：system / title / 检索词 / 格式随 spec 变化"""
    _ROLE = ""
    _SPECS = {}

    def __init__(self, kind: str, name: str = None, llm=None, knowledge_dir=None):
        spec = self._SPECS.get(kind)
        if spec is None:
            raise ValueError(f"未知 {self._ROLE} kind: {kind}（可用 {list(self._SPECS)}）")
        super().__init__(name=name or f"{kind}_{self._ROLE}", llm=llm,
                         system_prompt=spec["system"], knowledge_dir=knowledge_dir)
        self.kind = kind
        self._spec = spec
        # 普通类属性可直接用实例属性遮蔽（fetch_kb / generate 经 self 读取）
        self.MODULE_TITLE = spec["title"]
        self.KNOWLEDGE_QUERIES = spec["queries"]

    @property
    def FORMAT(self) -> str:
        """基类 FORMAT 是 property（无 setter），只能在子类以 property 覆盖"""
        return self._spec["format"]


class CreativeModuleAgent(_KindAgent):
    _ROLE = "creative"
    _SPECS = _CREATIVE_SPECS


class PlanModuleAgent(_KindAgent):
    _ROLE = "plan"
    _SPECS = _PLAN_SPECS
