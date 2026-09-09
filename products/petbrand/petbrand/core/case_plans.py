# -*- coding: utf-8 -*-
"""
策划案类型注册中心（纯数据）—— 一个案子选定一种类型，攒案模块 / 步骤标签 / 提案封面随之切换。

纯数据模块：禁止 import 本产品 core/agents/框架（防止循环依赖）。
- CASE_PLANS  类型 key → plan
- module 项：{key, title, role, agent?|kind?}
    role="base"     → 复用既有角色 Agent（agent ∈ market/insight/positioning/asset）
    role="creative" → CreativeModuleAgent(kind=…)（传播主题/上市概念/促销主题 等创意模块）
    role="plan"     → PlanModuleAgent(kind=…)（媒介预算/三阶段打法/流量波段 等执行模块）
- brand 的 cover_kicker / tagline_fallback / md_head / next_steps 与旧 deck 文案**逐字一致**，
  保证旧案（无 type 字段）重新出提案页时与历史输出 byte 级一致。
"""

# 中文数字序号（攒案步骤标签前缀，预留扩展）
_CH_NUM = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
STEP0_LABEL = "① 收 brief（品牌访谈）"
ASSEMBLE_LABEL = "一键攒案 → 提案页"

CASE_PLANS = {
    "brand": {
        "key": "brand",
        "label": "品牌全案 · 从0起盘",
        "desc": "从 0 立住一个品牌：市场→人群→定位→品牌资产。",
        "cover_kicker": "品牌全案提案 · 爪案 petbrand",
        "tagline_fallback": "对话式攒案 · 定位与人群出发",
        "md_head": "品牌全案汇总",
        "demo_note": "",
        "next_steps": [
            "1. 拍板品牌名候选与人群聚焦；2. 确认定位语进入 VI 与内容深化；3.（v2）展开预算与首年 GTM 排期。",
        ],
        "modules": [
            {"key": "market",      "title": "市场与竞品",   "role": "base", "agent": "market"},
            {"key": "insight",     "title": "人群洞察",     "role": "base", "agent": "insight"},
            {"key": "positioning", "title": "品牌定位",     "role": "base", "agent": "positioning"},
            {"key": "asset",       "title": "品牌资产（口号/VI/故事）", "role": "base", "agent": "asset"},
        ],
    },
    "campaign": {
        "key": "campaign",
        "label": "宣传推广活动案",
        "desc": "围绕一次传播战役：受众→传播定位基点→传播主题与大创意→内容·媒介·预算·KPI。",
        "cover_kicker": "宣传推广活动提案 · 爪案 petbrand",
        "tagline_fallback": "对话式攒案 · 一场能落地复盘传播战役",
        "md_head": "宣传推广活动案汇总",
        "demo_note": "（演示口径：视作该品牌已具一定产品与内容基础后，发起一次完整传播战役。）",
        "next_steps": [
            "1. 拍板传播总主题与大创意；",
            "2. 确认媒介组合与预算分配；",
            "3. 拆成可执行的排期与 KPI 复盘看板。",
        ],
        "modules": [
            {"key": "insight",           "title": "受众洞察",         "role": "base", "agent": "insight"},
            {"key": "positioning",       "title": "传播定位基点",     "role": "base", "agent": "positioning"},
            {"key": "campaign_creative", "title": "传播主题与大创意", "role": "creative", "kind": "campaign"},
            {"key": "campaign_plan",     "title": "内容·媒介·预算·KPI", "role": "plan", "kind": "campaign"},
        ],
    },
    "launch": {
        "key": "launch",
        "label": "新品上市案",
        "desc": "新品上市打法：人群→上市定位切口→上市概念与首发创意→三阶段打法与预算。",
        "cover_kicker": "新品上市提案 · 爪案 petbrand",
        "tagline_fallback": "对话式攒案 · 从概念到首销的上市作战",
        "md_head": "新品上市案汇总",
        "demo_note": "（演示口径：视作该品牌在起盘期推出首个核心新品（如主粮/冻干）的完整上市打法。）",
        "next_steps": [
            "1. 拍板上市概念与首发大事件；",
            "2. 确认预热/发布/首销三阶段预算；",
            "3. 定首批种子人群与上市 KPI。",
        ],
        "modules": [
            {"key": "insight",         "title": "上市人群洞察",       "role": "base", "agent": "insight"},
            {"key": "positioning",     "title": "上市定位切口",       "role": "base", "agent": "positioning"},
            {"key": "launch_concept",  "title": "上市概念与首发创意", "role": "creative", "kind": "launch"},
            {"key": "launch_plan",     "title": "三阶段打法与预算",   "role": "plan", "kind": "launch"},
        ],
    },
    "promo": {
        "key": "promo",
        "label": "大促节点案",
        "desc": "一次大促节点的作战：受众→大促定位基点→促销主题与机制→流量波段与预算。",
        "cover_kicker": "大促节点提案 · 爪案 petbrand",
        "tagline_fallback": "对话式攒案 · 一个节点从蓄水到返场的打法",
        "md_head": "大促节点案汇总",
        "demo_note": "（演示口径：视作该品牌已具稳定产品矩阵后，在一次大促节点（如 618/双 11/宠物节）的作战方案。）",
        "next_steps": [
            "1. 拍板大促主题与促销机制组合；",
            "2. 确认蓄水/爆发/返场波段与预算；",
            "3. 定流量结构与拉新/转化 KPI。",
        ],
        "modules": [
            {"key": "insight",     "title": "大促受众洞察",    "role": "base", "agent": "insight"},
            {"key": "positioning", "title": "大促定位基点",    "role": "base", "agent": "positioning"},
            {"key": "promo_theme", "title": "促销主题与机制",  "role": "creative", "kind": "promo"},
            {"key": "promo_plan",  "title": "流量波段与预算",  "role": "plan", "kind": "promo"},
        ],
    },
}

PLAN_ORDER = ["brand", "campaign", "launch", "promo"]
DEFAULT_TYPE = "brand"

# gradio Dropdown choices：(label, value)
TYPE_CHOICES = [(CASE_PLANS[t]["label"], t) for t in PLAN_ORDER]


def get_plan(plan_type) -> dict:
    """plan_type 缺失/未知 → brand plan（向后兼容旧案）"""
    return CASE_PLANS.get(plan_type or DEFAULT_TYPE) or CASE_PLANS[DEFAULT_TYPE]


def is_known_type(plan_type) -> bool:
    return plan_type in CASE_PLANS


def module_of(plan: dict, step: int):
    """step 1..len(modules) → 该步模块 dict；越界/0 → None"""
    modules = plan["modules"]
    if 1 <= step <= len(modules):
        return modules[step - 1]
    return None


def assemble_step_for(plan: dict) -> int:
    """攒案(汇总)步骤下标 = 模块数 + 1（本产品恒为 4 模块 → 5）"""
    return len(plan["modules"]) + 1


def step_labels_for(plan: dict) -> list:
    """攒案步骤标签（恒 6 项）：① 收 brief + ②..⑤ 各模块 + ⑥ 一键攒案"""
    labels = [STEP0_LABEL]
    for i, mod in enumerate(plan["modules"], start=2):
        num = _CH_NUM[i - 1] if i - 1 < len(_CH_NUM) else f"{i}."
        labels.append(f"{num} {mod['title']}")
    labels.append(f"{_CH_NUM[len(labels)]} {ASSEMBLE_LABEL}")
    return labels


def flow_line(plan: dict) -> str:
    """攒案路径一句话（看板展示用）"""
    return " → ".join(m["title"] for m in plan["modules"])
