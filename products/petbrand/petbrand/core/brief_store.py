# -*- coding: utf-8 -*-
"""
BriefStore —— 品牌简报（brief）存取

一个案子对应一份 brief：品牌基本信息，是全案所有模块的共同输入。
两种来源：
- 内置演示品牌：scenarios/demo_catdog_brand.json（开箱即用）
- 真实品牌访谈：按 INTERVIEW_QUESTIONS 逐题收集，存进 brief['interview']

brief 本身是普通 dict，key 固定，便于各模块 Agent 组 prompt。
"""
import json
import os

from .config import Config

# brief 的固定字段（未知字段可省略，生成时给默认/占位）
BRIEF_FIELDS = [
    "brand_name",          # 品牌名（可能待起名）
    "category",            # 品类定位描述（如 猫狗全品类电商/App）
    "products",            # 主营品项
    "price_band",          # 价格带
    "channels",            # 销售/传播渠道
    "goals",               # 本次全案的商业目标
    "target_hint",         # 目标人群线索（可选）
    "differentiators_hint",# 差异化/已有优势线索（可选）
    "assets_existing",     # 已有品牌资产（名/视觉/物料等，可选）
    "stage",               # 所处阶段（0起盘/成长/成熟）
]

# 访谈模式的问题（顾问逐题收集，全部答完 brief 即齐）
INTERVIEW_QUESTIONS = [
    ("品牌名与主营品项", "你的品牌叫什么？主营卖什么（猫粮/狗粮/零食/玩具/用品/App…）？"),
    ("价格带与渠道", "定价在什么区间？主要在哪些渠道卖（天猫/京东/拼多多/抖音/私域）？"),
    ("目标人群与优势", "目标用户是哪种养宠人（养猫还是养狗/新手还是进阶/什么价位敏感度）？目前有什么产品/内容上的优势？"),
    ("商业目标与现状", "这一阶段最想要什么（品牌立起来/打爆品/起私域/拿融资）？已有品牌资产（名字/LOGO/账号）吗？"),
]

BRIEF_LABELS = {
    "brand_name": "品牌名",
    "category": "品类定位",
    "products": "主营品项",
    "price_band": "价格带",
    "channels": "渠道",
    "goals": "商业目标",
    "target_hint": "目标人群",
    "differentiators_hint": "差异化优势",
    "assets_existing": "已有资产",
    "stage": "所处阶段",
}


def default_brief() -> dict:
    """空 brief（全字段占位为空字符串）"""
    return {f: "" for f in BRIEF_FIELDS}


def load_demo_brief() -> dict:
    """读内置演示品牌 brief（文件缺失时给一份内置兜底示例）"""
    path = Config.DEMO_BRAND_FILE
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if data and data.get("brand_name"):
        return data
    return _FALLBACK_DEMO()


def _FALLBACK_DEMO() -> dict:
    return {
        "brand_name": "爪局 PawChess",
        "category": "猫狗全品类新锐品牌（电商 + App）",
        "products": "主粮/冻干零食/牵引出行/智能饮水器/猫狗社区 App",
        "price_band": "中端（主粮 89-159 元区间）",
        "channels": "天猫/京东旗舰店 + 抖音/小红书种草 + 微信私域",
        "goals": "从 0 起盘：立住「人宠平等陪伴」的品牌心智，首年打爆 1-2 个 SKU 并沉淀私域",
        "target_hint": "一二线城市 25-35 岁养猫/养狗白领与新晋铲屎官",
        "differentiators_hint": "「科学喂养 + 情感陪伴」双主线，强调看得见的成分与家人式陪伴",
        "assets_existing": "暂无品牌资产，名字/LOGO/口号均待起",
        "stage": "0起盘",
    }


class BriefStore:
    """单个案子的 brief 读写（JSON 落盘到 case 目录）"""

    def __init__(self, case_dir: str):
        self.path = os.path.join(case_dir, "brief.json")
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        return default_brief()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: str = "") -> str:
        return (self.data.get(key) or "") if self.data.get(key) is not None else default

    def set(self, key: str, value: str):
        if key not in BRIEF_FIELDS:
            return
        self.data[key] = str(value or "").strip()
        self.save()

    def interview_done(self) -> bool:
        """演示模式或人工填全 brief 视为完成"""
        return bool(self.get("brand_name")) and bool(self.get("goals"))

    def to_prompt(self) -> str:
        """把 brief 渲染成各模块 Agent 可读的文本块"""
        lines = ["【品牌简报 Brand Brief】"]
        for key in BRIEF_FIELDS:
            val = self.get(key)
            if not val:
                continue
            label = BRIEF_LABELS.get(key, key)
            lines.append(f"- {label}：{val}")
        if self.data.get("interview"):
            lines.append("- 访谈补充：")
            for q, a in self.data["interview"]:
                if a:
                    lines.append(f"  · {q} → {a}")
        return "\n".join(lines)

    def add_interview(self, question: str, answer: str):
        self.data.setdefault("interview", []).append([question, answer])
        self.save()
