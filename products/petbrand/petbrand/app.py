# -*- coding: utf-8 -*-
"""
爪案（petbrand）· 猫狗品牌全案策划台 —— Gradio 攒案界面（文档工作台 UI）

四页（电脑顶部页签 / 手机底部栏自适应）：
  ① 策划工作台   左=攒案步骤(可点回跳)+当前模块操作(吸顶常驻,不随草稿下滑)；中=引导+顾问对话；右=模块草稿全文
  ② 全案看板     简报卡 / 攒案路径 / 各模块状态与摘要
  ③ 提案预览     deck 内嵌 iframe（浅色文档版⇄深色放映版）+ 下载 HTML / Markdown / Word
  ④ 案历史       新建（演示/访谈，自选类型）、列表带类型/进度/置顶/当前高亮、重命名/置顶/删除确认

攒案状态存模块级 _ST（单进程）。事件统一输出 _OUT（顺序固定，见 build_ui 注释）。
运行: python -m petbrand.app  或 run_ui.py（默认 http://127.0.0.1:7866）
"""

import html as _html
import os

import gradio as gr

from .core.config import Config
from .core.case_store import CaseStore
from .core.case_plans import TYPE_CHOICES
from .core.brief_store import (BriefStore, load_demo_brief, INTERVIEW_QUESTIONS)
from .core.wizard import interview_total

# 全局攒案状态（单进程内持久）
_ST = {
    "case_id": "",
    "step": 0,
    "mode": "",
    "interview_idx": 0,
    "deck_html_path": "",
    "deck_md_path": "",
    "deck_docx_path": "",
    "history": [],
}
# ④ 案列表 label → case_id 映射（每次刷新重建，兼容 Radio 返回 label 或 value）
_CASE_LABELS: dict = {}
_CONFIRM_CASE: str = ""

_TYPE_SHORT = {"brand": "品牌全案", "campaign": "推广活动", "launch": "新品上市", "promo": "大促节点"}
_MODE_SHORT = {"demo": "演示", "manual": "访谈"}


# ---------------- Agent 懒加载 ----------------
_MANAGER = None


def get_manager():
    global _MANAGER
    if _MANAGER is None:
        from .agents.brand_consultant_agent import BrandConsultantAgent
        _MANAGER = BrandConsultantAgent()
    return _MANAGER


# ---------------- 状态辅助 ----------------

def _cur_case() -> "CaseStore":
    return CaseStore(_ST["case_id"]) if _ST.get("case_id") else None


def _progress_of(store: "CaseStore") -> str:
    """'已定稿 x/n'"""
    try:
        mods = store.plan_modules
        done = sum(1 for m in mods if store.get_section(m["key"]).get("status") == "final")
        return f"已定稿 {done}/{len(mods)}"
    except Exception:
        return "已定稿 -"


def _case_choices_raw() -> list:
    try:
        return CaseStore().list_cases()
    except Exception:
        return []


def _case_choices() -> list:
    """返回给 Radio 的 [(label, case_id), ...]；同时更新 label→id 映射"""
    global _CASE_LABELS
    _CASE_LABELS = {}
    rows = []
    cur = _ST.get("case_id", "")
    for c in _case_choices_raw():
        label = c["name"]
        if c.get("pinned"):
            label = "★ " + label
        if c["case_id"] == cur:
            label += "（正在编辑）"
        type_s = _TYPE_SHORT.get(c["type"], c["type"])
        mode_s = _MODE_SHORT.get(c["mode"], c["mode"])
        try:
            prog = _progress_of(CaseStore(c["case_id"]))
        except Exception:
            prog = ""
        label += f"｜{type_s}｜{mode_s}｜{prog}｜更新 {c.get('updated', '')[:10]}"
        _CASE_LABELS[label] = c["case_id"]
        rows.append((label, c["case_id"]))
    return rows


def _cur_case_md() -> str:
    """①页顶部的当前案状态条"""
    c = _cur_case()
    if c is None:
        return "**尚未开案** —— 到「④ 案历史」选策划案类型，载入演示品牌或访谈开案。"
    plan = c.plan
    labels = c.step_labels()
    step = min(c.get_step(), len(labels) - 1)
    mods = c.plan_modules
    done = sum(1 for m in mods if c.get_section(m["key"]).get("status") == "final")
    pin = "★ " if c.meta.get("pinned") else ""
    return (f"**{pin}{c.name}** · {_MODE_SHORT.get(c.mode, c.mode)} · {plan['label']}  "
            f"`已定稿 {done}/{len(mods)}` · 当前：{labels[step]}")


# ---------------- 攒案动作（核心逻辑，返回文本；事件包壳见 build_ui） ----------------

def _module_ctx(case) -> str:
    return "\n\n".join(
        f"【{s['title']}】\n{s['content']}"
        for s in case.finalized_sections()
    )


def _probe_deck(case_id: str):
    """若该案已攒过案，重新指向其磁盘 deck 产物（切案后预览即时可用）"""
    for key, fn in (("deck_html_path", "提案页.html"), ("deck_md_path", "全案汇总.md"),
                    ("deck_docx_path", "全案汇总.docx")):
        _ST[key] = ""
        if case_id:
            p = os.path.join(Config.DECK_DIR, case_id, fn)
            if os.path.exists(p):
                _ST[key] = p


def _assemble_deck() -> str:
    case = _cur_case()
    if case is None:
        return "请先开案。"
    result = get_manager().deck_agent.assemble(case.case_id)
    _probe_deck(case.case_id)
    docx_note = os.path.basename(_ST["deck_docx_path"]) if _ST.get("deck_docx_path") else "（未生成，需 python-docx）"
    return (f"✅ 提案页与全案已生成（{result['brand_name']}）\n"
            f"- 提案页：`{os.path.basename(result['html'])}`（浅色文档版，预览内可切深色放映 / 打印 PDF）\n"
            f"- 全案汇总：`{os.path.basename(result['md'])}`\n"
            f"- Word：`{docx_note}`\n"
            f"去「③ 提案预览」查看与下载。产物目录：`{Config.DECK_DIR}/{case.case_id}`")


def _gen_draft_for_step() -> str:
    """为当前步骤生成模块草稿，返回要追加的助手消息"""
    case = _cur_case()
    step = _ST["step"]
    mod = case.module_of_step(step) if case else None
    if case is None or mod is None:
        return "当前步骤不需要生成模块：先在「④ 案历史」选类型并开案，再进入对应模块生成。"
    key = mod["key"]
    brief_md = case.brief().to_prompt()
    ctx = _module_ctx(case)
    sec = get_manager().generate_module(key, brief_md, context_md=ctx, module=mod)
    case.save_section(key, sec["title"], sec["content"], status="draft")
    check = get_manager().self_check(key, sec["content"])
    note = "满意点左栏「定稿本模块并下一步」；想换角度就把要求写进『换角度提示』再点重写。"
    return (f"### {sec['title']}（草稿）\n\n{sec['content']}\n\n"
            f"---\n**顾问自检**：{check}\n{note}")


def _rewrite_draft(angle: str) -> str:
    case = _cur_case()
    step = _ST["step"]
    mod = case.module_of_step(step) if case else None
    if case is None or mod is None:
        return "当前没有可重写的模块。"
    key = mod["key"]
    hint = (angle or "").strip() or "换一个更有冲击力的切入角度"
    brief_md = case.brief().to_prompt()
    ctx = _module_ctx(case)
    sec = get_manager().generate_module(key, brief_md, context_md=ctx, angle=hint, module=mod)
    case.save_section(key, sec["title"], sec["content"], status="draft")
    check = get_manager().self_check(key, sec["content"])
    return (f"### {sec['title']}（草稿 · 按「{hint}」重写）\n\n{sec['content']}\n\n"
            f"---\n**顾问自检**：{check}")


def _accept_current() -> str:
    case = _cur_case()
    step = _ST["step"]
    mod = case.module_of_step(step) if case else None
    if case is None or mod is None:
        return "当前无待定稿模块。"
    key = mod["key"]
    if not case.get_section(key).get("content"):
        return "还没有草稿，先点「生成模块草稿」。"
    case.mark_final(key)
    case.touch()
    next_step = step + 1
    _ST["step"] = next_step
    case.set_step(next_step)
    labels = case.step_labels()
    msg = f"✅ **{mod['title']}** 已定稿，进入「{labels[min(next_step, len(labels) - 1)]}」。"
    if next_step == case.assemble_step():
        msg += "\n\n所有前置模块已齐，正在一键攒案…\n" + _assemble_deck()
    return msg


def _goto(step: int) -> str:
    """跳转到某步骤（0 访谈 / 1..n 模块 / assemble 攒案）；demo 案不可停留 0。返回提示语"""
    case = _cur_case()
    if case is None:
        return ""
    if step == 0 and case.mode != "manual":
        step = 1  # demo 案没有访谈流程，回落到第一步
    labels = case.step_labels()
    step = max(0, min(int(step), len(labels) - 1))
    _ST["step"] = step
    case.set_step(step)
    target = labels[step]
    if step == case.assemble_step():
        return f"已切到「{target}」。所有模块定稿后点左栏「攒案出提案页 / 刷新」；改内容请回到对应模块重写。"
    mod = case.module_of_step(step)
    if not mod:
        return f"已切到「{target}」。"
    sec = case.get_section(mod["key"])
    if sec.get("content"):
        status = "已定稿" if sec.get("status") == "final" else "草稿待定稿"
        return f"已切到「{target}」（{status}）。右侧为当前内容，可重写或直接定稿。"
    return f"已切到「{target}」。点左栏「生成模块草稿」开始产出。"


def _append(role: str, content: str):
    _ST["history"].append({"role": role, "content": content})


_QA_PRIMARY_FIELD = {
    0: "brand_name",
    1: "price_band",
    2: "target_hint",
    3: "goals",
}


def _primary_field(idx: int, case, answer: str):
    """把访谈答案按题目主题落到 brief 一个主字段（全文同时进 interview 逐字留档）"""
    key = _QA_PRIMARY_FIELD.get(idx)
    if key:
        bs = case.brief()
        old = bs.get(key)
        bs.set(key, answer if not old else f"{old}；{answer}")


def _on_qa(text: str) -> str:
    """访谈答题（step0/manual）或自由提问"""
    text = (text or "").strip()
    case = _cur_case()
    if not text:
        return ""
    if case is None:
        _append("user", text)
        _append("assistant", "还没有案子。请到「④ 案历史」载入演示品牌开案，或用访谈模式开新案。")
        return "ok"
    if _ST["mode"] == "manual" and _ST["step"] == 0:
        _append("user", text)
        idx = _ST["interview_idx"]
        q = INTERVIEW_QUESTIONS[idx]
        if text not in ("跳过", "skip", "略过"):
            _primary_field(idx, case, text)
            case.brief().add_interview(q[1], text)
        _ST["interview_idx"] = idx + 1
        if _ST["interview_idx"] < interview_total():
            nxt = INTERVIEW_QUESTIONS[_ST["interview_idx"]]
            _append("assistant", f"收到。\n\n**Q{_ST['interview_idx'] + 1}/{interview_total()}** {nxt[1]}")
        else:
            _ST["step"] = 1
            case.set_step(1)
            first = case.plan_modules[0]["title"]
            _append("assistant", f"**访谈完成，品牌简报已就绪。** 开始攒案：点「生成模块草稿」产出 **{first}**。\n\n"
                                 + case.brief().to_prompt())
        return "ok"
    # 自由提问 → 顾问编排
    _append("user", text)
    try:
        answer = get_manager().run(text)
    except Exception as e:
        answer = f"（顾问暂时无法回答：{e}）"
    _append("assistant", str(answer))
    return "ok"


def _refresh_guide() -> str:
    """常驻操作指引：随攒案状态与策划案类型动态提示『现在该做什么』"""
    case = _cur_case()
    if case is None:
        return (
            "**操作指引 · 三步开跑**\n"
            "1. 到 **「④ 案历史」**：在 **策划案类型** 下拉选要的形状"
            "（品牌全案 / 宣传推广 / 新品上市 / 大促节点），点 **载入演示品牌开案**"
            "（零输入看效果），或填案名点 **访谈模式开案**。\n"
            "2. 回到本页：左侧点攒案步骤，或点左栏 **生成模块草稿**。\n"
            "3. 满意就 **定稿并下一步**，攒完自动出提案页 → 到「③ 提案预览」查看 / 下载。\n\n"
            "> 想换方向：在『换角度提示』写想法再点 **重写**；非访谈时下方输入框可自由提问。"
        )
    plan = case.plan
    n_mod = len(plan["modules"])
    step = _ST["step"]
    total = interview_total()
    if step == 0:
        idx = _ST["interview_idx"]
        first = plan["modules"][0]["title"]
        return (
            f"**攒案进度 · 访谈 {min(idx + 1, total)}/{total} 题**\n"
            f"本次为 **{plan['label']}**。逐题回答顾问问题（不想答发「跳过」），"
            f"答满 {total} 题自动进入 **{first}**。"
        )
    if 1 <= step <= n_mod:
        mod = case.module_of_step(step)
        title = mod["title"]
        sec = case.get_section(mod["key"])
        if not sec.get("content"):
            return (
                f"**攒案进度 · 第 {step}/{n_mod} 步 —— {title}（尚未生成）**\n"
                f"点左栏 **生成模块草稿**；草稿出现后满意 → **定稿并下一步**，"
                f"想改 → 在『换角度提示』写明方向 → **重写**。"
            )
        status = "已定稿" if sec.get("status") == "final" else "草稿待你定稿"
        return (
            f"**攒案进度 · 第 {step}/{n_mod} 步 —— {title}（{status}）**\n"
            f"{'已是最终版，可重写后再定稿覆盖。' if status == '已定稿' else '右侧为该模块草稿与顾问自检。'}"
            "满意 → **定稿并下一步**；要改 → 在『换角度提示』写明方向 → **重写**。"
        )
    return (
        f"**攒案进度 · {n_mod} 个模块已全部定稿（{plan['label']}）**\n"
        "点左栏 **攒案出提案页 / 刷新** 汇总 → 到「③ 提案预览」看成品（可浅色/深色切换、打印 PDF、下 Word）。\n"
        "想改某模块：左侧点对应步骤回到该模块重写。"
    )


def _module_card_md() -> str:
    """右侧「当前模块卡」内容：状态 + 全文 + 引导"""
    case = _cur_case()
    if case is None:
        return "尚未开案。\n\n到「④ 案历史」开案后，这里会显示当前模块的草稿 / 定稿全文。"
    step = _ST["step"]
    n_mod = len(case.plan_modules)
    if step == 0:
        return (f"**当前 · 访谈收 brief**\n\n在对话区逐题回答顾问问题"
                f"（{min(_ST['interview_idx'] + 1, interview_total())}/{interview_total()}）。\n\n"
                f"**案名**：{case.name} · {_MODE_SHORT.get(case.mode, case.mode)}")
    if step == case.assemble_step():
        mods = case.plan_modules
        done = sum(1 for m in mods if case.get_section(m["key"]).get("status") == "final")
        fin = [m["title"] for m in mods if case.get_section(m["key"]).get("status") == "final"]
        pending = [m["title"] for m in mods if case.get_section(m["key"]).get("status") != "final"]
        txt = f"**一键攒案（已定稿 {done}/{len(mods)}）**\n\n"
        if done == len(mods):
            txt += "- 模块已齐，点左栏「攒案出提案页 / 刷新」生成提案页。\n"
        else:
            txt += "- 待定稿：" + "、".join(pending) + "\n"
        txt += "\n**攒案路径**\n" + "\n".join(
            f"- {'✓ ' if t in fin else '○ '}{t}" for t in [m["title"] for m in mods])
        return txt
    mod = case.module_of_step(step)
    if not mod:
        return ""
    sec = case.get_section(mod["key"])
    content = sec.get("content", "")
    status = {"final": "✓ 已定稿", "draft": "· 草稿（待定稿）"}.get(sec.get("status"), "— 未生成")
    title = sec.get("title") or mod["title"]
    head = f"**第 {step}/{n_mod} 步 · {title}**  `{status}`"
    if not content:
        return head + "\n\n本步尚未生成。点左栏「生成模块草稿」，顾问将结合简报与已定稿内容产出。"
    return head + "\n\n---\n\n" + content


# ---------------- 看板 / 预览 ----------------

def _board_markdown() -> str:
    case = _cur_case()
    if case is None:
        return "**尚未开案**。到「④ 案历史」选类型开案后，这里汇总显示简报与攒案进展。"
    plan = case.plan
    mods = case.plan_modules
    fin = case.finalized_sections()
    brief_md = case.brief().to_prompt()
    parts = [f"### {case.name}（{_MODE_SHORT.get(case.mode, case.mode)} · {plan['label']}）",
             f"**攒案路径**：{' → '.join(m['title'] for m in mods)}", "",
             "#### 品牌简报", brief_md, "",
             "#### 各模块状态"]
    for m in mods:
        sec = case.get_section(m["key"])
        st = {"final": "✓ 已定稿", "draft": "· 草稿"}.get(sec.get("status"), "— 未生成")
        parts.append(f"- {m['title']}　`{st}`")
        if sec.get("content"):
            snippet = sec["content"].replace("\n", " ")[:120]
            parts.append(f"  - {snippet}…")
    parts.append("")
    if fin:
        parts.append("#### 已定稿全文")
        for sec in fin:
            parts.append(f"**{sec['title']}**")
            parts.append(sec["content"])
    else:
        parts.append("尚无定稿模块，去「① 策划工作台」逐模块攒。")
    return "\n\n".join(parts)


def _deck_iframe() -> str:
    """把 deck HTML 塞进 iframe srcdoc（隔离样式、支持滚动与页内切换/打印）"""
    p = _ST.get("deck_html_path") or ""
    if p and os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                doc = f.read()
        except Exception:
            doc = ""
        if doc:
            safe = _html.escape(doc, quote=True)
            return (f'<iframe class="pb-frame" title="提案页预览" '
                    f'srcdoc="{safe}"></iframe>'
                    f'<p class="pb-frame-hint">浅色文档版为默认；点击预览页内右下「深色放映版」切换，'
                    f'「打印 / 存为 PDF」可在浏览器另存为 PDF。</p>')
    return "<p class='pb-frame-hint'>尚未攒案。完成各模块定稿后触发攒案，即可在此内嵌预览提案页。</p>"


# ---------------- 开案 / 切案 / 删案 / 管理 ----------------

def _open_demo(case_type="brand") -> str:
    store = CaseStore()
    case_id = store.create("爪局 PawChess（演示）", mode="demo", case_type=case_type)
    bs = BriefStore(store.dir)
    demo = load_demo_brief()
    for k, v in demo.items():
        if k in bs.data:
            bs.data[k] = str(v)
    bs.save()
    store.set_step(1)
    _reset_case(case_id, step=1, mode="demo")
    plan = store.plan
    first = plan["modules"][0]["title"]
    note = plan.get("demo_note", "")
    msg = (f"已载入**演示品牌「爪局 PawChess」**，按 **{plan['label']}** 攒案。"
           f"{note}\n\n{bs.to_prompt()}\n\n开始攒案：点「生成模块草稿」产出 **{first}**。")
    _append("assistant", msg)
    return "ok"


def _open_manual(name: str, case_type="brand") -> str:
    name = (name or "").strip() or "新策划案"
    store = CaseStore()
    case_id = store.create(name, mode="manual", case_type=case_type)
    store.set_step(0)
    _reset_case(case_id, step=0, mode="manual")
    plan = store.plan
    q = INTERVIEW_QUESTIONS[0]
    _append("assistant", f"**访谈模式已开始**（{name} · {plan['label']}）。请逐题作答，共 {interview_total()} 题。\n\n"
                         f"**Q1/{interview_total()}** {q[1]}\n\n（在下方输入框作答后回车；不想答就发「跳过」）")
    return "ok"


def _reset_case(case_id: str, step: int, mode: str):
    _probe_deck(case_id)
    _ST.update(case_id=case_id, step=step, mode=mode, interview_idx=0,
               deck_html_path=_ST["deck_html_path"], deck_md_path=_ST["deck_md_path"],
               deck_docx_path=_ST["deck_docx_path"], history=[])


def _select_case(case_id: str) -> str:
    if not case_id:
        return ""
    try:
        c = CaseStore(case_id)
    except Exception:
        return ""
    if not os.path.isdir(c.dir):
        return ""
    step = min(c.get_step(), len(c.step_labels()) - 1)
    _reset_case(case_id, step=step, mode=c.mode)
    labels = c.step_labels()
    _append("assistant", f"已打开案子 **{c.name}**（{_MODE_SHORT.get(c.mode, c.mode)} · {c.plan['label']}），"
                         f"自动定位到当前进度 {c.get_step()}/{c.assemble_step()}：{labels[step]}。\n\n"
                         f"可回看 / 重写该步，或继续推进攒案。")
    return "ok"


def _delete_case(case_id: str) -> str:
    if case_id:
        CaseStore().delete(case_id)
    if _ST.get("case_id") == case_id:
        _reset_case("", 0, "")
    return f"已删除（{case_id}）。"


# ---------------- 攒案工程路径（rail 步进） ----------------

def _rail_meta() -> list:
    """返回 rail 按钮的元信息：{idx,label,active,visible,mark}（最多 6 个）"""
    case = _cur_case()
    out = []
    if case is None:
        for idx in range(6):
            out.append({"idx": idx, "label": "", "active": False, "visible": False, "mark": ""})
        return out
    labels = case.step_labels()
    step = _ST["step"]
    mods = case.plan_modules
    manual = case.mode == "manual"
    interview_label = "收 brief（品牌访谈）" if manual else "访谈（演示已预填）"
    out.append({"idx": 0, "label": interview_label, "active": step == 0, "visible": True, "mark": ""})
    for i, m in enumerate(mods, start=1):
        st = case.get_section(m["key"]).get("status")
        mark = "✓ " if st == "final" else ("· " if st == "draft" else "○ ")
        out.append({"idx": i, "label": m["title"], "active": step == i, "visible": True, "mark": mark})
    asb = case.assemble_step()
    out.append({"idx": asb, "label": labels[-1], "active": step == asb, "visible": True, "mark": ""})
    return out


def _rail_updates() -> tuple:
    """rail 6 个按钮的更新（顺序固定 interview/模块×4/攒案）"""
    ups = []
    for meta in _rail_meta():
        ups.append(gr.update(
            value=meta["mark"] + meta["label"],
            variant="primary" if meta["active"] else "secondary",
            visible=meta["visible"],
        ))
    while len(ups) < 6:
        ups.append(gr.update(visible=False))
    return tuple(ups[:6])


# ---------------- 下载路径辅助 ----------------

def _deck_downloads() -> tuple:
    """返回三个下载按钮的更新（HTML / MD / DOCX）——有文件则可下载"""
    def _u(p):
        if p and os.path.exists(p):
            return gr.update(value=p, interactive=True)
        return gr.update(value=None, interactive=False)
    return (_u(_ST.get("deck_html_path") or ""),
            _u(_ST.get("deck_md_path") or ""),
            _u(_ST.get("deck_docx_path") or ""))


def _resolve_case(x) -> str:
    """Radio/Dropdown 可能返回 label 或 value，统一解析成 case_id"""
    if not x:
        return ""
    if x in _CASE_LABELS.values():
        return str(x)
    if x in _CASE_LABELS:
        return _CASE_LABELS[x]
    return str(x)


# =====================================================================
#  主题与布局 CSS
# =====================================================================

_CSS = r"""
/* ============ 爪案 petbrand · 浅色文档工作台 ============ */
/* 1) 覆盖 Gradio 主题令牌（!important 压过内联主题变量） */
.gradio-container-5-45-0, .gradio-container, gradio-app {
  --body-background-fill: #f6f7f5 !important;
  --background-fill-primary: #f6f7f5 !important;
  --background-fill-secondary: #eef1ee !important;
  --block-background-fill: #ffffff !important;
  --block-border-color: #e7ebe8 !important;
  --block-label-text-color: #66706a !important;
  --block-title-text-color: #232a26 !important;
  --body-text-color: #232a26 !important;
  --body-text-color-subdued: #66706a !important;
  --border-color-primary: #e7ebe8 !important;
  --border-color-accent: #2e6b4f !important;
  --color-accent: #2e6b4f !important;
  --color-accent-soft: #eaf3ee !important;
  --link-text-color: #2e6b4f !important;
  --input-background-fill: #ffffff !important;
  --input-border-color: #dfe5e1 !important;
  --button-primary-background-fill: #2e6b4f !important;
  --button-primary-background-fill-hover: #265b41 !important;
  --button-primary-border-color: #2e6b4f !important;
  --button-primary-text-color: #ffffff !important;
  --button-secondary-background-fill: #ffffff !important;
  --button-secondary-background-fill-hover: #eaf3ee !important;
  --button-secondary-border-color: #dfe5e1 !important;
  --button-secondary-text-color: #232a26 !important;
}

/* 2) 页面骨架 */
.gradio-container {
  max-width: 1440px !important;
  margin: 0 auto !important;
  padding: 20px 26px 72px !important;
}
.gradio-container .main { max-width: none !important; }

/* 顶部品牌栏 */
.pb-brand { margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid #e7ebe8; }
.pb-brand .prose h1 {
  display: flex; align-items: center; gap: 12px;
  font-size: 24px; font-weight: 800; letter-spacing: .01em; color: #232a26; margin: 0;
}
.pb-brand .prose h1::before {
  content: ''; width: 22px; height: 22px; flex: none; border-radius: 7px;
  background: linear-gradient(135deg, #2e6b4f, #5aa87f);
  box-shadow: 0 2px 6px rgba(46, 107, 79, .28);
}
.pb-brand .prose p { color: #66706a; font-size: 13px; margin: 6px 0 0; }

/* 当前案状态条 & 指引卡 */
.pb-caseline { background: #fff; border: 1px solid #e7ebe8; border-radius: 10px; margin-bottom: 12px; }
.pb-guide { background: #fff; border: 1px solid #e7ebe8; border-radius: 10px; margin-bottom: 10px; }
.pb-caseline .prose, .pb-guide .prose, .pb-board .prose, .pb-module .prose {
  padding: 10px 14px; font-size: 13.5px;
}

/* 3) 顶部 Tabs：文档式下划线 */
.tabs { margin-top: 4px; }
.tab-wrapper button {
  position: relative; background: transparent !important; color: #66706a;
  font-size: 14px; font-weight: 500; padding: 8px 4px; margin: 0 20px 0 0;
  border: none !important; border-radius: 0 !important; cursor: pointer;
  transition: color .18s ease;
}
.tab-wrapper button:hover { color: #232a26; }
.tab-wrapper button.selected { color: #2e6b4f; font-weight: 600; }
.tab-wrapper button.selected::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: 2px; height: 2px;
  background: #2e6b4f; border-radius: 2px;
}

/* 4) 组件抛光 */
.chat-wrap { border-radius: 12px; border: 1px solid #e7ebe8 !important; background: #fff !important; }
button, .pb-caselist label { cursor: pointer; }
button {
  transition: color .18s ease, background-color .18s ease, border-color .18s ease, box-shadow .18s ease;
}
:is(button, input, select, textarea, [role='radio']):focus-visible {
  outline: 2px solid #2e6b4f; outline-offset: 2px;
}

/* 5) 手机：底部固定页签条 + 内容避让 */
@media (max-width: 760px) {
  .gradio-container { padding: 12px 12px 96px !important; }
  .tab-wrapper {
    position: fixed; z-index: 40; left: 0; right: 0; bottom: 0;
    display: flex; justify-content: space-around; align-items: center;
    background: #ffffff; border-top: 1px solid #e7ebe8;
    padding: 6px 4px calc(6px + env(safe-area-inset-bottom, 0px));
    box-shadow: 0 -8px 24px rgba(20, 28, 24, .08);
  }
  .tab-wrapper button { margin: 0; padding: 6px 8px; font-size: 12px; }
  .tab-wrapper button.selected::after { display: none; }
  .tab-wrapper button::before {
    content: ''; position: absolute; top: 1px; left: 50%; width: 5px; height: 5px;
    border-radius: 50%; transform: translateX(-50%);
    background: transparent; transition: background .18s ease;
  }
  .tab-wrapper button.selected::before { background: #2e6b4f; }
  .pb-brand .prose h1 { font-size: 20px; }
}

/* 6) 动效偏好 */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}
"""

_CSS_EXTRA = """
/* ---------- ① 工作台三栏（左=控制塔 / 中=对话 / 右=草稿全文） ---------- */
.pb-work { gap: 14px; }
.pb-work .pb-rail, .pb-work .pb-main, .pb-work .pb-panel { min-width: 0; }

/* 左栏：攒案步骤 + 当前模块操作（sticky：读长草稿时不随之下滑，操作常驻可见） */
.pb-rail {
  border: 1px solid #e7ebe8; background: #fff; border-radius: 12px; padding: 12px 10px;
  align-self: flex-start; position: sticky; top: 14px;
  max-height: calc(100vh - 28px); overflow-y: auto;
}
.pb-rail .block { box-shadow: none !important; }
.pb-rail .pb-rail-head .prose { padding: 0 2px 6px; font-size: 12.5px; color: #66706a; }

/* 攒案步骤按钮 */
.pb-rail .rail-step-btn {
  width: 100% !important; justify-content: flex-start !important; text-align: left;
  white-space: normal; height: auto; min-height: 36px; line-height: 1.35;
  padding: 6px 11px !important; font-size: 13px !important; border-radius: 8px !important;
  margin: 2px 0 !important;
}
.pb-rail .rail-step-btn.primary { box-shadow: none !important; }

/* 当前模块操作（左栏上部区） */
.pb-rail .rail-acts button {
  width: 100% !important; min-height: 36px; margin: 2px 0 !important; font-size: 13px !important;
}
.pb-rail .rail-acts button.primary { box-shadow: none !important; }
/* 攒案步骤区：与操作同一列，上部以细分隔线衔接成一体 */
.pb-rail .rail-steps { border-top: 1px dashed #e2e8e4; margin-top: 4px; padding-top: 8px; }

/* 右栏模块草稿全文 */
.pb-panel { border: 1px solid #e7ebe8; background: #fff; border-radius: 12px; padding: 12px 14px; }
.pb-panel .block { box-shadow: none !important; }
.pb-module { border: none !important; background: transparent !important; }
.pb-board { border: none; background: transparent; }

/* 中栏引导卡 */
.pb-guide { margin-bottom: 10px; }
.pb-guide .prose blockquote { border-left: 3px solid #2e6b4f; margin: 6px 0; padding: 2px 10px; color: #66706a; }

/* ③ 预览 */
.pb-preview { background: #fff; border: 1px solid #e7ebe8; border-radius: 12px; padding: 10px; }
.pb-preview iframe.pb-frame { width: 100%; height: 76vh; min-height: 460px; border: 1px solid #e7ebe8; border-radius: 10px; background: #fff; }
.pb-frame-hint { color: #8a9690; font-size: 12.5px; margin: 8px 2px 0; }
.pb-dlrow { gap: 10px; }
.pb-dlrow button { flex: 1; }

/* ④ 案历史 */
.pb-history .block { box-shadow: none !important; }
.pb-caselist { border: 1px solid #e7ebe8; background: #fff; border-radius: 12px; padding: 8px 12px; }
.pb-caselist label { cursor: pointer; }
.pb-confirm { border: 1px solid #ecc7c3; background: #fdf2f0; border-radius: 10px; padding: 6px 12px; align-items: center; }
.pb-confirm .prose { font-size: 13px; }

/* 手机：左栏不吸顶；当前模块操作在上、攒案步骤变横排胶囊于下 */
@media (max-width: 900px) {
  .pb-rail { position: static; max-height: none; overflow: visible; padding: 10px; }
  .pb-rail .rail-acts button { min-height: 40px; }
  .pb-rail .rail-steps { display: flex; flex-flow: row wrap; gap: 6px; }
  .pb-rail .rail-steps .block, .pb-rail .rail-steps .form { display: contents; }
  .pb-rail .rail-step-btn { width: auto !important; min-width: max-content; margin: 0 !important; }
  .pb-panel { margin-top: 4px; }
}
"""


def _clear_tb():
    return gr.update(value="")


# =====================================================================
#  UI
# =====================================================================

def build_ui() -> gr.Blocks:
    # 事件统一输出 _OUT，顺序固定 = snap 返回元组：
    # [chatbot, guide, module卡, board, preview, case_line, rail×6, case单选, 确认行, html下载, md下载, docx下载]
    def snap(hist=None, confirm_visible=False):
        return (
            hist if hist is not None else _ST["history"],
            _refresh_guide(),
            _module_card_md(),
            _board_markdown(),
            _deck_iframe(),
            _cur_case_md(),
            *_rail_updates(),
            gr.update(choices=_case_choices()),
            gr.update(visible=confirm_visible),
            *_deck_downloads(),
        )

    with gr.Blocks(title=Config.PRODUCT_TITLE, css=_CSS + _CSS_EXTRA) as demo:
        gr.Markdown(
            f"# 爪案 petbrand\n\n**{Config.PRODUCT_TITLE}** · 开案自选类型（品牌全案 / 宣传推广 / 新品上市 / 大促节点）· 电脑 + 手机自适应",
            elem_classes=["pb-brand"],
        )

        with gr.Tabs():
            # ============ ① 策划工作台 ============
            with gr.Tab("① 策划工作台"):
                case_md = gr.Markdown(_cur_case_md(), elem_classes=["pb-caseline"])
                with gr.Row(elem_classes=["pb-work"]):
                    # 左：一体控制栏 —— 上=当前模块操作，下=攒案步骤（同一列，吸顶常驻）
                    with gr.Column(scale=2, min_width=260, elem_classes=["pb-rail"]):
                        with gr.Column(elem_classes=["rail-acts"]):
                            gr.Markdown("**当前模块操作**", elem_classes=["pb-rail-head"])
                            angle_box = gr.Textbox(label="换角度提示 / 对顾问的要求（可选）",
                                                   placeholder="如：更强调成分溯源 / 人群换成多猫家庭 / 口号更潮…",
                                                   lines=2)
                            gen_btn = gr.Button("生成模块草稿", variant="primary")
                            rewrite_btn = gr.Button("按提示重写")
                            accept_btn = gr.Button("定稿本模块并下一步")
                            deck_btn = gr.Button("攒案出提案页 / 刷新")
                        with gr.Column(elem_classes=["rail-steps"]):
                            gr.Markdown("**攒案步骤**（点某步回看 / 改稿）", elem_classes=["pb-rail-head"])
                            r_btns = [gr.Button("…", size="sm", elem_classes=["rail-step-btn"])
                                      for _ in range(6)]
                    # 中：引导 + 对话 + 提问
                    with gr.Column(scale=5, min_width=380, elem_classes=["pb-main"]):
                        guide_md = gr.Markdown(_refresh_guide(), elem_classes=["pb-guide"])
                        chatbot = gr.Chatbot(height=420, type="messages", elem_classes=["chat-wrap"])
                        with gr.Row():
                            send_box = gr.Textbox(label="回答访谈 / 自由提问",
                                                  placeholder="访谈中回答当前问题；非访谈时当自由提问（回车发送）",
                                                  scale=6, lines=1)
                            send_btn = gr.Button("发送", scale=1)
                    # 右：模块草稿全文（长文本；操作按钮已固定在左栏，不随之下滑）
                    with gr.Column(scale=4, min_width=340, elem_classes=["pb-panel"]):
                        module_md = gr.Markdown(_module_card_md(), elem_classes=["pb-module"])

            # ============ ② 全案看板 ============
            with gr.Tab("② 全案看板"):
                board = gr.Markdown(_board_markdown(), elem_classes=["pb-board"])

            # ============ ③ 提案预览 ============
            with gr.Tab("③ 提案预览"):
                gr.Markdown("攒案完成后，此处**内嵌预览提案页**：默认浅色文档版；预览页内右下可切「深色放映版」并打印为 PDF。")
                preview = gr.HTML(value=_deck_iframe(), elem_classes=["pb-preview"])
                gr.Markdown("**下载**：全案可转 Word(.docx) / Markdown 二次编辑；提案页 HTML 可离线放映。")
                with gr.Row(elem_classes=["pb-dlrow"]):
                    dl_html = gr.DownloadButton("下载 提案页.html", value=None, interactive=False)
                    dl_md = gr.DownloadButton("下载 全案汇总.md", value=None, interactive=False)
                    dl_docx = gr.DownloadButton("下载 全案汇总.docx (Word)", value=None, interactive=False)

            # ============ ④ 案历史 ============
            with gr.Tab("④ 案历史"):
                with gr.Column(elem_classes=["pb-history"]):
                    gr.Markdown("### 新建案子")
                    case_type_dd = gr.Dropdown(choices=TYPE_CHOICES, value="brand",
                                               label="策划案类型（决定攒案模块与提案封面，仅新案生效）",
                                               interactive=True)
                    with gr.Row():
                        demo_btn = gr.Button("载入演示品牌 · 爪局 PawChess 开案", variant="primary", scale=3)
                        manual_name = gr.Textbox(label="访谈模式案名（真实品牌）",
                                                 placeholder="如：某猫粮新品上市 / 咖啡新消费品牌…", scale=4)
                        manual_btn = gr.Button("访谈模式开案", scale=1)
                    gr.Markdown("---")
                    gr.Markdown("### 已有案子")
                    case_radio = gr.Radio(label="选择一个案子（★=置顶 · 正在编辑=当前案）",
                                          choices=[], interactive=True, elem_classes=["pb-caselist"])
                    with gr.Row():
                        open_btn = gr.Button("打开 / 定位到当前步骤")
                        pin_btn = gr.Button("置顶 / 取消置顶")
                        del_btn = gr.Button("删除…")
                    with gr.Row():
                        new_name_tb = gr.Textbox(label="重命名案名", placeholder="输入新案名后点「重命名」", scale=3)
                        rename_btn = gr.Button("重命名", scale=1)
                    with gr.Row(visible=False, elem_classes=["pb-confirm"]) as confirm_row:
                        gr.Markdown("**确认删除？** 将删除该案工程与提案页，不可恢复。")
                        confirm_yes = gr.Button("确认删除", variant="stop")
                        confirm_no = gr.Button("取消")

        # ---------------- 攒案动作包壳 ----------------
        rail0, rail1, rail2, rail3, rail4, rail5 = r_btns
        rail_outs = [rail0, rail1, rail2, rail3, rail4, rail5]
        _OUT = [chatbot, guide_md, module_md, board, preview, case_md,
                *rail_outs, case_radio, confirm_row,
                dl_html, dl_md, dl_docx]

        def on_send(text, cbot):
            _on_qa(text)
            return snap()

        def on_gen(cbot):
            _append("assistant", _gen_draft_for_step())
            return snap()

        def on_rewrite(angle, cbot):
            _append("assistant", _rewrite_draft(angle))
            return snap()

        def on_accept(cbot):
            _append("assistant", _accept_current())
            return snap()

        def on_deck(cbot):
            _append("assistant", _assemble_deck())
            return snap()

        def on_rail_step(i: int):
            msg = _goto(i)
            if msg:
                _append("assistant", msg)
            return snap()

        # ---------------- 开案 / 管理包壳 ----------------
        def on_open_demo(ctype):
            _open_demo(ctype)
            return snap()

        def on_open_manual(name, ctype):
            _open_manual(name, ctype)
            return snap()

        def on_select(choice):
            _select_case(_resolve_case(choice))
            return snap()

        def on_open_btn(choice):
            _select_case(_resolve_case(choice))
            return snap()

        def on_pin(choice):
            cid = _resolve_case(choice)
            if cid:
                CaseStore(cid).toggle_pinned()
                _append("assistant", f"已切换置顶：{CaseStore(cid).name}")
            return snap()

        def on_rename(choice, newname):
            cid = _resolve_case(choice)
            if cid:
                CaseStore(cid).rename(newname or "")
                _append("assistant", f"已重命名：{CaseStore(cid).name}")
            return snap()

        def on_del_ask(choice):
            global _CONFIRM_CASE
            _CONFIRM_CASE = _resolve_case(choice) or ""
            return snap(confirm_visible=bool(_CONFIRM_CASE))

        def on_del_yes():
            global _CONFIRM_CASE
            _delete_case(_CONFIRM_CASE)
            _CONFIRM_CASE = ""
            return snap(confirm_visible=False)

        def on_del_no():
            global _CONFIRM_CASE
            _CONFIRM_CASE = ""
            return snap(confirm_visible=False)

        # ---------------- 事件绑定 ----------------
        send_box.submit(on_send, [send_box, chatbot], _OUT).then(_clear_tb, [], send_box)
        send_btn.click(on_send, [send_box, chatbot], _OUT).then(_clear_tb, [], send_box)
        gen_btn.click(on_gen, [chatbot], _OUT)
        rewrite_btn.click(on_rewrite, [angle_box, chatbot], _OUT)
        accept_btn.click(on_accept, [chatbot], _OUT)
        deck_btn.click(on_deck, [chatbot], _OUT)

        def _bind_rail(i, rb):
            rb.click(lambda k=i: on_rail_step(k), [], _OUT)
        for _i, _rb in enumerate(rail_outs):
            _bind_rail(_i, _rb)

        demo_btn.click(on_open_demo, [case_type_dd], _OUT)
        manual_btn.click(on_open_manual, [manual_name, case_type_dd], _OUT)
        case_radio.change(on_select, [case_radio], _OUT)
        open_btn.click(on_open_btn, [case_radio], _OUT)
        pin_btn.click(on_pin, [case_radio], _OUT)
        rename_btn.click(on_rename, [case_radio, new_name_tb], _OUT).then(_clear_tb, [], new_name_tb)
        del_btn.click(on_del_ask, [case_radio], _OUT)
        confirm_yes.click(on_del_yes, [], _OUT)
        confirm_no.click(on_del_no, [], _OUT)

    return demo


if __name__ == "__main__":
    os.environ.setdefault("PETBRAND_UI_HOST", "127.0.0.1")
    os.environ.setdefault("PETBRAND_UI_PORT", "7866")
    _demo = build_ui()
    _demo.launch(server_name=os.getenv("PETBRAND_UI_HOST", "127.0.0.1"),
                 server_port=int(os.getenv("PETBRAND_UI_PORT", "7866")),
                 inbrowser=os.getenv("PETBRAND_UI_INBROWSER", "1").lower() in ("1", "true", "yes"))
