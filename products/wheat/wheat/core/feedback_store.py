# -*- coding: utf-8 -*-
"""
feedback_store —— 用户反馈（本地 JSON 追加存储）

反馈视图：类型 + 内容 + 联系方式 → add() 落盘，UI 提示成功（无外链、离线可用）。
文件：Config.DATA_ROOT/outputs/feedback.json（追加式数组）
"""

import json
import os
import time

from .config import Config

FEEDBACK_FILE = os.path.join(Config.DATA_ROOT, "outputs", "feedback.json")

_TYPES = ["建议", "问题", "报告 Bug", "其它"]


def add(fb_type: str, content: str, contact: str = "") -> dict:
    """追加一条反馈，返回 {"ok": bool, "msg": str}"""
    fb_type = (fb_type or "").strip()
    content = (content or "").strip()
    if not content:
        return {"ok": False, "msg": "反馈内容不能为空"}
    if fb_type not in _TYPES:
        fb_type = "其它"
    rec = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": fb_type,
        "content": content[:2000],
        "contact": (contact or "").strip()[:200],
    }
    try:
        os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
        items = []
        if os.path.exists(FEEDBACK_FILE):
            try:
                with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                    items = json.load(f)
            except (json.JSONDecodeError, OSError):
                items = []
        if not isinstance(items, list):
            items = []
        items.append(rec)
        items = items[-500:]
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        return {"ok": True, "msg": "✅ 感谢反馈！已记录到本地。"}
    except OSError:
        return {"ok": False, "msg": "❌ 写入失败，请重试。"}
