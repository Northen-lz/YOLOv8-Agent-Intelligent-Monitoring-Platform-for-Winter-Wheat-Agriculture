# -*- coding: utf-8 -*-
"""
Wizard —— 攒案流程状态机（产品心脏，纯 Python 确定性驱动）

步骤：0 访谈 → 1 市场 → 2 人群 → 3 定位 → 4 品牌资产 → 5 攒案提案页

- demo 模式：brief 直接来自内置演示品牌，跳过逐题访谈（step 直接到 1）
- manual 模式：逐题访谈（INTERVIEW_QUESTIONS 共 4 题），答完进 step 1
每个模块先经「顾问生成草稿」→ UI 展示 → 用户「定稿」进下一步 或「换角度重写」。
攒案出提案页由 DeckAgent 完成（DeckBuilderTool 汇总已定稿模块）。
"""
from .brief_store import INTERVIEW_QUESTIONS


def interview_total() -> int:
    return len(INTERVIEW_QUESTIONS)


def describe_step(step: int, mode: str = "manual", brief_ready: bool = False) -> str:
    """把当前步骤渲染成给用户的进度说明"""
    if step == 0:
        if mode == "demo":
            return "演示模式已载入内置品牌 brief，可直接开始（点下一步收 brief）。"
        return "访谈模式：请逐题回答品牌信息（答完自动进入市场研究）。"
    if step == 5:
        return "所有前置模块已定稿，点「攒案出提案页」生成可放映的提案页与全案汇总。"
    return "当前模块已生成草稿，请查看并选择：定稿进入下一步 / 换角度重写。"


def next_step_after_accept(step: int) -> int:
    """模块定稿后推进的下一步"""
    return min(step + 1, 5)
