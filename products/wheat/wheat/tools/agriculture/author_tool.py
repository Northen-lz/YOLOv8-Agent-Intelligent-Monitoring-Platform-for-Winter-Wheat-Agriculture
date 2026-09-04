# -*- coding: utf-8 -*-
"""
AuthorInfoTool —— 作者/项目信息工具

读取 knowledge/author_info.txt，回答关于系统开发者、项目技术路线、
技术栈的问题。支持关键词定位小节；未命中时返回全文供 LLM 归纳。
"""

import os
from typing import List

from ...core.config import Config
from ha_framework.tools.base import BaseTool, ToolParameter


class AuthorInfoTool(BaseTool):
    """作者与项目信息工具"""

    name = "author_info"
    description = ("检索系统开发者/项目信息（作者简介、技术方向、项目经历、使用框架、开发技术）。"
                   "用法: author_info(question=\"介绍系统开发者\") 或 author_info() 返回全部信息。")

    # 问题关键词 → 小节定位
    _SECTION_KEYWORDS = {
        "姓名": ["姓名", "谁", "作者", "开发者", "介绍"],
        "技术方向": ["技术方向", "方向", "研究方向"],
        "项目经历": ["项目经历", "经历", "做过", "项目"],
        "使用框架": ["框架", "使用框架"],
        "开发技术": ["技术栈", "开发技术", "用什么", "语言", "工具"],
    }

    def __init__(self, path: str = None, name: str = None, description: str = None):
        super().__init__(name=name, description=description)
        self.path = path or os.path.join(Config.KNOWLEDGE_DIR, "author_info.txt")
        self.text = ""
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.text = f.read()
        except (OSError, UnicodeDecodeError):
            self.text = ""

    def _sections(self) -> dict:
        """返回 {小节名: 内容}"""
        import re
        secs = {}
        blocks = re.split(r"^##\s+(.+?)\s*$", self.text, flags=re.M)
        for i in range(1, len(blocks), 2):
            title = blocks[i].strip()
            body = blocks[i + 1].strip() if i + 1 < len(blocks) else ""
            secs[title] = body
        return secs

    # ---------------- BaseTool 接口 ----------------

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("question", "string", "关于作者/项目的问题", required=False, default=""),
        ]

    def run(self, *args, **kwargs) -> str:
        if not args and "input" in kwargs:
            raw = kwargs.pop("input")
            if isinstance(raw, dict):
                kwargs.update(raw)
            else:
                kwargs["question"] = raw
        elif len(args) >= 1 and not kwargs.get("question"):
            kwargs["question"] = args[0]

        question = str(kwargs.get("question") or "").strip()
        if not self.text:
            return "❌ author_info: 未找到作者信息文件 author_info.txt"

        if not question:
            return self.text

        # 定位小节：命中关键词的小节优先
        hit_secs = []
        for section, keywords in self._SECTION_KEYWORDS.items():
            if any(k in question for k in keywords):
                body = self._sections().get(section, "")
                if body:
                    hit_secs.append(f"## {section}\n{body}")
        if hit_secs:
            return "\n\n".join(hit_secs)

        # 未命中 → 返回全文由 LLM 归纳
        return self.text
