# -*- coding: utf-8 -*-
"""
notifications_store —— 本地通知中心（JSON 持久化）

事件型轻量通知（本期挂接：批量检测完成 / 看图识别完成；后续可扩）：
- add(kind, title, detail)  追加一条未读通知
- list_all()                全部通知（新→旧）
- unread_count()            未读数（自上次已读时间戳后新增）
- mark_read()               全部标记已读（进入通知视图时调用）
- clear()                   清空全部
文件：Config.DATA_ROOT/outputs/notifications.json
"""

import json
import os
import time

from .config import Config

NOTIF_FILE = os.path.join(Config.DATA_ROOT, "outputs", "notifications.json")


def _read() -> dict:
    if not os.path.exists(NOTIF_FILE):
        return {"read_ts": 0.0, "items": []}
    try:
        with open(NOTIF_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"read_ts": 0.0, "items": []}
        data.setdefault("items", [])
        data.setdefault("read_ts", 0.0)
        return data
    except (json.JSONDecodeError, OSError, TypeError):
        return {"read_ts": 0.0, "items": []}


def _write(data: dict):
    try:
        os.makedirs(os.path.dirname(NOTIF_FILE), exist_ok=True)
        with open(NOTIF_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def add(kind: str, title: str, detail: str = "") -> dict:
    """追加一条通知，kind 用 emoji 前缀便于展示"""
    data = _read()
    data["items"].append({
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": kind or "🔔",
        "title": title or "",
        "detail": detail or "",
    })
    # 仅保留最近 200 条，防止文件无限增长
    data["items"] = data["items"][-200:]
    _write(data)
    return data


def list_all(limit: int = 100) -> list:
    """通知列表，新→旧"""
    return list(reversed(_read().get("items", [])))[:max(1, int(limit))]


def unread_count() -> int:
    data = _read()
    read_ts = float(data.get("read_ts", 0.0) or 0.0)
    return sum(1 for it in data.get("items", []) if float(it.get("ts", 0)) > read_ts)


def mark_read() -> int:
    """全部已读，返回被标记条数"""
    data = _read()
    data["read_ts"] = time.time()
    _write(data)
    return len(data.get("items", []))


def clear() -> int:
    data = {"read_ts": time.time(), "items": []}
    _write(data)
    return 0


def render_html(items=None, limit: int = 100) -> str:
    """渲染为资讯卡 HTML（空态友好提示）"""
    items = list_all(limit) if items is None else items
    if not items:
        return ('<div class="nt-empty">🔕 暂无通知 —— 完成一次「批量检测」或「看图识别」后，'
                '结果会出现在这里。</div>')
    rows = []
    for it in items:
        detail = ""
        if it.get("detail"):
            detail = f'<div class="nt-detail">{it.get("detail")}</div>'
        rows.append(
            '<div class="nt-item">'
            '<div class="nt-row">'
            f'<span class="nt-kind">{it.get("kind", "🔔")}</span>'
            f'<span class="nt-title">{it.get("title", "")}</span>'
            f'<span class="nt-time">{it.get("time", "")}</span>'
            '</div>' + detail + '</div>')
    return "".join(rows)
