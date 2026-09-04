# -*- coding: utf-8 -*-
"""
conversation_store —— 对话历史持久化（JSON 文件）

把 Gradio Chatbot 的 messages（dict 列表）按会话存到 Config.CONVERSATIONS_DIR：
- 支持 保存 / 加载调回 / 删除 / 重命名 / 置顶 / 列表
- message content 序列化：字符串 → {"kind":"text","text":...}；
  文件元组 (path, alt) → {"kind":"file","path":...,"alt":...}（加载时还原）
- 纯文件操作，不加载模型、不触碰外部视觉系统
"""

import json
import os
import re
import time

from .config import Config

CONVERSATIONS_DIR = Config.CONVERSATIONS_DIR
_MAX_TITLE_LEN = 20


# ---------------- 内部工具 ----------------

def _conv_path(conv_id: str) -> str:
    return os.path.join(CONVERSATIONS_DIR, f"{conv_id}.json")


def _to_storage(content):
    """chatbot message content → 可 JSON 序列化的存储结构"""
    if isinstance(content, tuple) and len(content) == 2:
        return {"kind": "file", "path": content[0], "alt": content[1]}
    if isinstance(content, dict) and "path" in content:  # FileDataDict 防御
        return {"kind": "file", "path": content["path"], "alt": content.get("alt_text")}
    if isinstance(content, list) and content:  # 防御：list 只取首元素
        return _to_storage(content[0])
    return {"kind": "text", "text": content if isinstance(content, str) else str(content)}


def _from_storage(item):
    """存储结构 → chatbot message content（str / 文件元组）"""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if item.get("kind") == "file":
            p = item.get("path") or ""
            alt = item.get("alt")
            return (p, alt) if alt else (p,)
        if item.get("kind") == "text":
            return item.get("text", "")
        if "path" in item:  # 防御旧格式
            return (item["path"], item.get("alt_text")) if item.get("alt_text") else (item["path"],)
    return str(item)


def _messages_to_storage(messages) -> list:
    out = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        out.append({"role": m.get("role", "user"),
                    "content": _to_storage(m.get("content"))})
    return out


def _messages_from_storage(stored) -> list:
    return [{"role": m.get("role", "user"),
             "content": _from_storage(m.get("content"))}
            for m in stored or []]


def _default_title(messages) -> str:
    """标题 = 首条用户文本消息前 N 字；带图消息取 alt 文本；仅图片用占位"""
    for m in messages or []:
        if m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str) and c.strip():
            t = re.sub(r"\s+", " ", c.strip())
            return t[:_MAX_TITLE_LEN] + ("…" if len(t) > _MAX_TITLE_LEN else "")
        if isinstance(c, tuple) and len(c) == 2 and isinstance(c[1], str) and c[1].strip():
            t = re.sub(r"\s+", " ", c[1].strip())
            return t[:_MAX_TITLE_LEN] + ("…" if len(t) > _MAX_TITLE_LEN else "")
        return "📷 图片对话"
    return "新对话"


def _now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


_id_seq = [0]


def _new_id() -> str:
    """会话 id：秒级时间戳 + pid + 进程内自增，避免同一秒多次保存碰撞覆盖"""
    _id_seq[0] += 1
    return time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}-{_id_seq[0]}"


# ---------------- 对外 API ----------------

def save(messages, conv_id: str = None) -> str:
    """保存（或更新）一个会话，返回会话 id。空消息不落盘。"""
    messages = [m for m in (messages or []) if isinstance(m, dict) and m.get("content")]
    if not messages:
        return conv_id or ""
    conv_id = conv_id or _new_id()
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
    now = _now_str()
    data = {}
    path = _conv_path(conv_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    data.update({
        "id": conv_id,
        "title": data.get("title") or _default_title(messages),
        "created_at": data.get("created_at") or now,
        "updated_at": now,
        "pinned": bool(data.get("pinned", False)),
        "messages": _messages_to_storage(messages),
    })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return conv_id


def load(conv_id: str) -> list:
    """加载会话消息（还原为 chatbot 消息 dict 列表）；不存在返回 []"""
    path = _conv_path(conv_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return _messages_from_storage(data.get("messages", []))


def delete(conv_id: str) -> bool:
    path = _conv_path(conv_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def rename(conv_id: str, title: str) -> bool:
    title = (title or "").strip()
    path = _conv_path(conv_id)
    if not os.path.exists(path) or not title:
        return False
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["title"] = title
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return True


def toggle_pin(conv_id: str) -> bool:
    path = _conv_path(conv_id)
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["pinned"] = not bool(data.get("pinned", False))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return True


def list_conversations() -> list:
    """全部会话元信息，置顶优先、按 updated_at 降序"""
    if not os.path.isdir(CONVERSATIONS_DIR):
        return []
    convs = []
    for fn in os.listdir(CONVERSATIONS_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(CONVERSATIONS_DIR, fn), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        convs.append({
            "id": data.get("id", fn[:-5]),
            "title": data.get("title", "未命名对话"),
            "updated_at": data.get("updated_at", ""),
            "pinned": bool(data.get("pinned", False)),
            "msg_count": len(data.get("messages", [])),
        })
    convs.sort(key=lambda c: (not c["pinned"], c["updated_at"]), reverse=True)
    return convs


def _conv_choice(c) -> tuple:
    """单个会话的选项 (标签, id)。分组已承担时间维度，行内不再重复时间。"""
    return (c["title"], c["id"])


def listbox_choices() -> list:
    """侧边栏会话列表选项：[(显示标签, id)]，分「📌 置顶」「最近」两组，只显示名称。

    分组标题行以 ``@group:`` 前缀的 value 标识（不可选中，UI 渲染为灰字小节）；
    真实会话 id 是 ``YYYYMMDD-HHMMSS-pid``，不会与 ``@group:*`` 冲突。
    """
    convs = list_conversations()
    pinned = [c for c in convs if c["pinned"]]
    recent = [c for c in convs if not c["pinned"]]

    out = []
    if pinned:
        out.append(("📌 置顶", "@group:置顶"))
        out.extend(_conv_choice(c) for c in pinned)
    if recent:
        out.append(("最近", "@group:最近"))
        out.extend(_conv_choice(c) for c in recent)
    return out
