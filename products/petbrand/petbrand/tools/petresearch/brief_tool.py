# -*- coding: utf-8 -*-
"""
BriefTool —— 品牌简报（brief）读取工具

供 Manager/模块 Agent 在对话里查看当前案子的品牌简报；也用于列出内置演示品牌。
简报内容由 BriefStore 落盘管理，本工具只读+展示（写入走 BriefStore/访谈流程）。
"""

import os
from typing import Dict, List

from ...core.brief_store import BriefStore, load_demo_brief
from ...core.case_store import CaseStore
from ha_framework.tools.base import BaseTool, ToolParameter


class BriefTool(BaseTool):
    """查看当前案子的品牌简报 / 内置演示品牌"""

    name = "brief_tool"
    description = ("查看当前品牌简报或内置演示品牌。用法: brief_tool(action=\"get\", case_dir=\"...\") 返回品牌简报文本；"
                   "brief_tool(action=\"demo\") 返回内置演示品牌。")

    def __init__(self, name: str = None, description: str = None):
        super().__init__(name=name, description=description)
        self.demo_brief = None

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("action", "string", "get=当前简报 / demo=演示品牌", required=True),
            ToolParameter("case_dir", "string", "case 目录（action=get 时需要）", required=False, default=""),
        ]

    def run(self, *args, **kwargs) -> str:
        if not args and "input" in kwargs:
            raw = kwargs.pop("input")
            if isinstance(raw, dict):
                kwargs.update(raw)
            else:
                kwargs["action"] = str(raw)
        elif len(args) >= 1 and not kwargs.get("action"):
            kwargs["action"] = args[0]

        action = kwargs.get("action") or "get"
        case_dir = kwargs.get("case_dir") or ""

        if action == "demo":
            try:
                return load_demo_brief().get("scenario_note", "") + "\n" + self._brief_text(load_demo_brief())
            except Exception as e:
                return f"❌ 读取演示品牌失败: {e}"

        if not case_dir or not os.path.isdir(case_dir):
            return "❌ 请提供有效的 case_dir（当前案子的目录）。"
        try:
            store = CaseStore("", root=os.path.dirname(case_dir))
            store.case_id = os.path.basename(case_dir)
            store.dir = case_dir
            return self._brief_text(BriefStore(case_dir).data)
        except Exception as e:
            return f"❌ 读取品牌简报失败: {e}"

    @staticmethod
    def _brief_text(brief: Dict[str, str]) -> str:
        from ...core.brief_store import BRIEF_LABELS
        lines = ["【品牌简报 Brand Brief】"]
        for key, label in BRIEF_LABELS.items():
            val = brief.get(key) or ""
            if val:
                lines.append(f"- {label}：{val}")
        return "\n".join(lines)
