# -*- coding: utf-8 -*-
"""
CaseStore —— 案子（攒案工程）存储

一个案子 = outputs/cases/<case_id>/ 下的一个工程目录：
  meta.json   案名/模式(demo|manual)/步骤/时间
  brief.json  （由 BriefStore 管理）
  sections/   每个已生成模块：<module_key>.json（title/content/status=final|draft/角度）
攒案完成后，DeckBuilderTool 把已定稿模块汇总成提案页放 outputs/decks/<case_id>/。
"""
import json
import os
import time

from .config import Config
from .case_plans import (CASE_PLANS, DEFAULT_TYPE, get_plan, module_of,
                         step_labels_for, assemble_step_for)

MODULES = {
    "market": "市场与竞品",
    "insight": "人群洞察",
    "positioning": "品牌定位",
    "asset": "品牌资产",
    # deck 为汇总产物，不入 sections
}

MODULE_ORDER = ["market", "insight", "positioning", "asset"]

# 攒案步骤（0 访谈 / 1 市场 / 2 人群 / 3 定位 / 4 品牌资产 / 5 攒案出提案页）
STEP_LABELS = [
    "① 收 brief（品牌访谈）",
    "② 市场与竞品",
    "③ 人群洞察",
    "④ 品牌定位",
    "⑤ 品牌资产（口号/VI/故事）",
    "⑥ 一键攒案 → 提案页",
]


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class CaseStore:
    def __init__(self, case_id: str = "", root: str = ""):
        self.root = root or Config.CASES_DIR
        os.makedirs(self.root, exist_ok=True)
        self.case_id = case_id
        self.dir = os.path.join(self.root, case_id) if case_id else ""
        self.meta = {}
        if case_id and os.path.isdir(self.dir):
            self._load_meta()

    # ---------------- 列案 ----------------
    def list_cases(self) -> list:
        """按更新时间倒序返回 [{case_id,name,mode,updated,pinned}]"""
        items = []
        for name in os.listdir(self.root):
            d = os.path.join(self.root, name)
            meta_p = os.path.join(d, "meta.json")
            if not os.path.isdir(d) or not os.path.exists(meta_p):
                continue
            try:
                with open(meta_p, encoding="utf-8") as f:
                    m = json.load(f)
            except (OSError, ValueError):
                continue
            items.append({
                "case_id": name,
                "name": m.get("name") or name,
                "mode": m.get("mode", "manual"),
                "type": m.get("type", DEFAULT_TYPE),
                "updated": m.get("updated", ""),
                "pinned": bool(m.get("pinned")),
            })
        items.sort(key=lambda x: (not x["pinned"], x["updated"]), reverse=True)
        return items

    # ---------------- 新建 / 打开 / 删除 ----------------
    def create(self, name: str, mode: str = "demo", case_type: str = "brand",
               case_id: str = "") -> str:
        """新建案子：type 归一化（未知→brand）；case_id 同秒重复时自动追加 _n 防覆盖"""
        case_type = case_type if case_type in CASE_PLANS else DEFAULT_TYPE
        base = case_id or "case_" + time.strftime("%Y%m%d_%H%M%S")
        case_id, n = base, 1
        while os.path.isdir(os.path.join(self.root, case_id)):
            n += 1
            case_id = f"{base}_{n}"
        d = os.path.join(self.root, case_id)
        os.makedirs(os.path.join(d, "sections"), exist_ok=True)
        meta = {
            "name": name,
            "mode": mode,
            "type": case_type,
            "step": 0,
            "created": now_ts(),
            "updated": now_ts(),
            "pinned": False,
        }
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        self.case_id, self.dir, self.meta = case_id, d, meta
        return case_id

    def _load_meta(self):
        try:
            with open(os.path.join(self.dir, "meta.json"), encoding="utf-8") as f:
                self.meta = json.load(f)
        except (OSError, ValueError):
            self.meta = {}

    def _save_meta(self):
        self.meta["updated"] = now_ts()
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)

    def delete(self, case_id: str):
        import shutil
        d = os.path.join(self.root, case_id)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        # 顺带清理该案子的提案页
        deck_dir = os.path.join(Config.DECK_DIR, case_id)
        if os.path.isdir(deck_dir):
            shutil.rmtree(deck_dir, ignore_errors=True)

    def touch(self):
        self._save_meta()

    def rename(self, new_name: str) -> str:
        """重命名案子（name 字段）"""
        new_name = (new_name or "").strip()
        if new_name:
            self.meta["name"] = new_name
        self._save_meta()
        return self.meta.get("name", self.case_id)

    def set_pinned(self, pinned: bool):
        self.meta["pinned"] = bool(pinned)
        self._save_meta()

    def toggle_pinned(self) -> bool:
        self.meta["pinned"] = not bool(self.meta.get("pinned"))
        self._save_meta()
        return bool(self.meta["pinned"])

    # ---------------- 步骤 ----------------
    def get_step(self) -> int:
        return int(self.meta.get("step", 0))

    def set_step(self, step: int):
        self.meta["step"] = step
        self._save_meta()

    @property
    def name(self) -> str:
        return self.meta.get("name", self.case_id)

    @property
    def mode(self) -> str:
        return self.meta.get("mode", "manual")

    @property
    def type(self) -> str:
        t = self.meta.get("type", DEFAULT_TYPE)
        return t if t in CASE_PLANS else DEFAULT_TYPE

    @property
    def plan(self) -> dict:
        return get_plan(self.type)

    @property
    def plan_modules(self) -> list:
        return self.plan["modules"]

    def module_of_step(self, step: int) -> dict:
        """step 1..len(plan_modules) → 模块 dict；否则 None"""
        return module_of(self.plan, step)

    def assemble_step(self) -> int:
        return assemble_step_for(self.plan)

    def step_labels(self) -> list:
        return step_labels_for(self.plan)

    def title_for(self, key: str) -> str:
        for m in self.plan_modules:
            if m["key"] == key:
                return m["title"]
        return MODULES.get(key, key)

    # ---------------- brief ----------------
    def brief(self):
        from .brief_store import BriefStore
        return BriefStore(self.dir)

    # ---------------- sections ----------------
    def save_section(self, key: str, title: str, content: str, status: str = "draft",
                     angle: str = ""):
        sec = {
            "key": key,
            "title": title,
            "content": content,
            "status": status,
            "angle": angle,
            "updated": now_ts(),
        }
        with open(os.path.join(self.dir, "sections", f"{key}.json"), "w", encoding="utf-8") as f:
            json.dump(sec, f, ensure_ascii=False, indent=2)
        return sec

    def get_section(self, key: str) -> dict:
        p = os.path.join(self.dir, "sections", f"{key}.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        return {"key": key, "title": self.title_for(key), "content": "", "status": "draft"}

    def mark_final(self, key: str):
        sec = self.get_section(key)
        sec["status"] = "final"
        with open(os.path.join(self.dir, "sections", f"{key}.json"), "w", encoding="utf-8") as f:
            json.dump(sec, f, ensure_ascii=False, indent=2)

    def finalized_sections(self) -> list:
        """按本案子策划案类型的模块顺序返回已定稿模块（旧案 type 兜底 brand）"""
        out = []
        for mod in self.plan_modules:
            sec = self.get_section(mod["key"])
            if sec.get("content") and sec.get("status") == "final":
                out.append(sec)
        return out
