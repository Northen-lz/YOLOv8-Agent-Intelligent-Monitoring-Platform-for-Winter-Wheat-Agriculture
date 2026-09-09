# -*- coding: utf-8 -*-
"""
DeckBuilderTool —— 攒案汇总器（确定性，不调用 LLM）

把已定稿模块 + 品牌简报汇总成：
  1) 提案页 HTML（深色提案风格、分节卡片、可滚动放映）
  2) 全案汇总 Markdown（便于复制/二次编辑）
输出到 outputs/decks/<case_id>/。

对 markdown 做轻量渲染（标题/加粗/列表/引用/分隔），不依赖第三方 md 库。
"""

import html
import os
import re
import time
from typing import Dict, List

from ...core.config import Config
from ...core.case_store import CaseStore
from ...core.brief_store import BRIEF_LABELS
from ha_framework.tools.base import BaseTool, ToolParameter


def _md_to_html(text: str) -> str:
    """轻量 markdown → HTML：##/###/列表/加粗/引用/行内代码/分隔/空行分段"""
    out = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("### "):
            out.append(f"<h3>{_inline(line.lstrip()[4:])}</h3>")
        elif line.lstrip().startswith("## "):
            out.append(f"<h2>{_inline(line.lstrip()[3:])}</h2>")
        elif line.lstrip().startswith("# "):
            out.append(f"<h1>{_inline(line.lstrip()[2:])}</h1>")
        elif re.match(r"^\s*[-*]\s+", line):
            out.append(f"<li>{_inline(re.sub(r'^\s*[-*]\s+', '', line))}</li>")
        elif re.match(r"^\s*\d+[.、)]\s+", line):
            out.append(f"<li>{_inline(re.sub(r'^\s*\d+[.、)]\s+', '', line))}</li>")
        elif line.strip().startswith(">"):
            out.append(f'<blockquote>{_inline(line.strip()[1:].strip())}</blockquote>')
        elif line.strip() == "---":
            out.append('<hr>')
        else:
            out.append(f"<p>{_inline(line)}</p>")
    return "\n".join(out)


def _inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


class DeckBuilderTool(BaseTool):
    """把已定稿模块汇总成提案页 HTML + 全案 Markdown"""

    name = "deck_builder"
    description = ("把当前案子的品牌简报与已定稿模块（按策划案类型）汇总生成可放映提案页 HTML 与全案 Markdown。"
                   "用法: deck_builder(case_dir=\"<case目录>\")，返回生成文件路径。")

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("case_dir", "string", "case 目录（必填）", required=True),
        ]

    def build(self, case_id: str) -> Dict[str, str]:
        """确定性构建：返回 {html, md, 路径}"""
        store = CaseStore(case_id)
        plan = store.plan
        brief = store.brief().data
        sections = store.finalized_sections()
        deck_dir = os.path.join(Config.DECK_DIR, case_id)
        os.makedirs(deck_dir, exist_ok=True)

        html_path = os.path.join(deck_dir, "提案页.html")
        md_path = os.path.join(deck_dir, "全案汇总.md")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self._render_html(brief, sections, store.name, plan))
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self._render_md(brief, sections, store.name, plan))
        return {
            "html": html_path,
            "md": md_path,
            "name": store.name,
            "brand_name": brief.get("brand_name") or "（品牌）",
        }

    @staticmethod
    def _brief_badges(brief: Dict[str, str]) -> str:
        items = []
        for key, label in BRIEF_LABELS.items():
            val = brief.get(key)
            if val:
                items.append(f"<span class='chip'>{label}：{html.escape(str(val))}</span>")
        return "\n".join(items)

    def _render_html(self, brief, sections, case_name, plan) -> str:
        # 模块标题 fallback：类型模块表（正常 title 已存进 section json）
        plan_titles = {m["key"]: m["title"] for m in plan.get("modules", [])}
        sec_blocks = []
        for sec in sections:
            title = sec.get("title") or plan_titles.get(sec.get("key"), sec.get("key"))
            sec_blocks.append(
                f"<section><h2>{html.escape(str(title))}</h2>"
                f"<div class='body'>{_md_to_html(sec.get('content') or '')}</div></section>"
            )
        # 从定位类模块里提取一句话作副标（若存在定位语）
        tag = ""
        for sec in sections:
            m = re.search(r"定位语[：:]\s*[「“]?(.+?)[」”]?[\n]", sec.get("content") or "")
            if m:
                tag = html.escape(m.group(1))
                break

        kicker = plan.get("cover_kicker") or f"{plan.get('label', '策划')}提案 · 爪案 petbrand"
        tag_fallback = plan.get("tagline_fallback") or f"对话式攒案 · {plan.get('label', '策划案')}"
        next_steps = "\n".join(f"<p>{html.escape(x)}</p>" for x in plan.get("next_steps", []))
        css = _DECK_CSS
        brand = html.escape(str(brief.get("brand_name") or case_name))
        title = html.escape(str(case_name))
        return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 提案页</title><style>{css}</style></head>
<body>
<nav class="deckbar" aria-label="工具栏">
  <span class="deckbar-brand">爪案 petbrand</span>
  <span class="deckbar-actions">
    <button type="button" id="btnTheme">深色放映版</button>
    <button type="button" onclick="window.print()">打印 / 存为 PDF</button>
  </span>
</nav>
<div class="page">
<header class="cover">
  <div class="kicker">{kicker}</div>
  <h1>{brand}</h1>
  <p class="tagline">{tag or tag_fallback}</p>
  <div class="meta">{time.strftime('%Y-%m-%d')} · 演示口径数据</div>
</header>
<main>
  <section><h2>品牌简报</h2><div class="chips">{self._brief_badges(brief)}</div></section>
  {''.join(sec_blocks)}
  <section class="end"><h2>下一步</h2><div class="body">
{next_steps}
</div></section>
</main>
<footer>由 爪案 petbrand · 猫狗品牌全案策划台 生成（数据为演示口径，商用请以真实调研核校）</footer>
</div>
<script>
(function(){{
  var b=document.getElementById('btnTheme'), dark=true;
  function sync(){{ b.textContent = dark ? '深色放映版' : '浅色文档版'; }}
  b.addEventListener('click', function(){{
    dark=!dark;
    document.body.classList.toggle('dark', dark);
    sync();
  }});
  sync();
}})();
</script>
</body></html>"""

    @staticmethod
    def _render_md(brief, sections, case_name, plan) -> str:
        lines = [f"# {case_name} · {plan.get('md_head', '策划案汇总')}", ""]
        lines.append("> 对话式攒案产物 · 演示口径数据，商用前请以真实调研核校")
        lines.append("")
        lines.append("## 品牌简报")
        for key, label in BRIEF_LABELS.items():
            val = brief.get(key)
            if val:
                lines.append(f"- **{label}**：{val}")
        lines.append("")
        for sec in sections:
            lines.append(f"## {sec.get('title')}")
            lines.append("")
            lines.append(sec.get("content") or "")
            lines.append("")
        return "\n".join(lines)

    def run(self, *args, **kwargs) -> str:
        if not args and "input" in kwargs:
            raw = kwargs.pop("input")
            if isinstance(raw, dict):
                kwargs.update(raw)
            else:
                kwargs["case_dir"] = str(raw)
        elif len(args) >= 1 and not kwargs.get("case_dir"):
            kwargs["case_dir"] = args[0]

        case_dir = kwargs.get("case_dir") or ""
        if not case_dir:
            return "❌ deck_builder 生成失败: 缺少 case_dir"
        case_id = os.path.basename(os.path.normpath(case_dir))
        try:
            result = self.build(case_id)
        except Exception as e:
            return f"❌ deck_builder 生成失败: {e}"
        n_mod = len(CaseStore(case_id).plan_modules)
        return (f"✅ 提案页与全案汇总已生成：\n"
                f"- 提案页：`{os.path.basename(result['html'])}`\n"
                f"- 全案汇总：`{os.path.basename(result['md'])}`\n"
                f"（{result['brand_name']}，共 {n_mod} 模块定稿）")


_DECK_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
/* ---------- 双主题变量：浅色文档版（默认） / body.dark = 深色放映版 ---------- */
:root{
  --bg:#f6f7f5; --card:#ffffff; --ink:#232a26; --sub:#5c6b63;
  --line:#e7ebe8; --brand:#2e6b4f; --accent:#1f5139; --chipbg:#eef3f0;
  --foot:#8a9690; --kicker:#2e6b4f; --quote:#bcd7c9; --codebg:#eef3f0;
  --coverbg:#ffffff;
}
body.dark{
  --bg:#0d1420; --card:#131b28; --ink:#e7ecf3; --sub:#94a2b6;
  --line:#202c3f; --brand:#66d3a6; --accent:#c4f2df; --chipbg:#1b2639;
  --foot:#5f6c82; --kicker:#66d3a6; --quote:#0f2433; --codebg:#1b2639;
  --coverbg:#0f1726;
}
body{
  background:var(--bg); color:var(--ink);
  font-family:'Inter','PingFang SC','Microsoft YaHei',-apple-system,'Segoe UI',system-ui,sans-serif;
  line-height:1.75; -webkit-font-smoothing:antialiased;
  transition:background .2s ease,color .2s ease;
}
.page{max-width:940px;margin:0 auto;padding:0 28px 40px}
.deckbar{
  position:fixed; z-index:50; left:50%; transform:translateX(-50%); bottom:18px;
  display:flex; align-items:center; gap:12px;
  background:var(--card); border:1px solid var(--line); color:var(--sub);
  padding:6px 8px 6px 16px; border-radius:999px;
  box-shadow:0 8px 28px rgba(16,24,20,.14); font-size:12px;
}
.deckbar-brand{font-weight:600;color:var(--ink);letter-spacing:.3px}
.deckbar-actions{display:flex;gap:6px}
.deckbar button{
  border:1px solid var(--line); background:transparent; color:var(--sub);
  border-radius:999px; padding:5px 12px; font-size:12px; cursor:pointer;
  font-family:inherit; transition:all .15s ease;
}
.deckbar button:hover{color:var(--accent);border-color:var(--brand);background:var(--chipbg)}
.cover{background:var(--coverbg);padding:64px 8px 40px;border-bottom:1px solid var(--line)}
.kicker{letter-spacing:.22em;font-size:12.5px;color:var(--kicker);margin-bottom:18px;font-weight:600}
.cover h1{font-size:clamp(30px,5.2vw,52px);color:var(--ink);font-weight:800;letter-spacing:.01em;line-height:1.15}
.tagline{font-size:clamp(15px,2vw,19px);color:var(--brand);margin-top:14px;font-weight:500}
.meta{font-size:12.5px;color:var(--foot);margin-top:22px}
main{max-width:940px;margin:0 auto;padding:8px 8px 20px}
section{padding:30px 0;border-bottom:1px solid var(--line)}
section h2{font-size:12.5px;letter-spacing:.2em;color:var(--kicker);margin-bottom:12px;font-weight:700}
.body h1{font-size:22px;color:var(--ink);margin:14px 0 8px;letter-spacing:.2px}
.body h2{font-size:18px;color:var(--ink);margin:18px 0 8px}
.body h3{font-size:15.5px;color:var(--ink);margin:14px 0 6px;opacity:.92}
.body p{margin:8px 0}
.body li{margin:5px 0 5px 22px}
.body blockquote{border-left:3px solid var(--kicker);color:var(--sub);padding:6px 14px;margin:10px 0;background:var(--quote)}
.body hr{border:none;border-top:1px dashed var(--line);margin:16px 0}
.body b{color:var(--accent);font-weight:600}
.body code{background:var(--codebg);padding:1px 6px;border-radius:5px;color:var(--accent);font-size:.92em}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{background:var(--chipbg);border:1px solid var(--line);color:var(--ink);border-radius:999px;padding:5px 13px;font-size:12.5px}
.end .body p{font-size:14.5px}
footer{max-width:940px;margin:0 auto;padding:18px 8px 90px;color:var(--foot);font-size:12px}
/* ---------- 打印（浅色文档化输出） ---------- */
@media print{
  body{background:#fff !important;color:#1a1f1c !important}
  .deckbar{display:none !important}
  .page{max-width:none;padding:0}
  .cover{padding-top:0}
  section{break-inside:avoid;page-break-inside:avoid}
}
@media (max-width:640px){
  .page{padding:0 16px 30px}
  .deckbar{width:auto;left:12px;right:12px;transform:none;justify-content:space-between;bottom:8px}
  .cover{padding:40px 2px 28px}
}
"""
