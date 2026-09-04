# -*- coding: utf-8 -*-
"""
detection_log —— 平台检测流水记录（JSONL 追加式）

每次检测（对话图片 / 批量检测）追加一条记录到 Config.DETECTION_LOG_FILE：
    {"ts": 时间戳, "time": "MM-DD HH:MM:SS", "image_count": 1,
     "wheat_count": n, "drought_count": m, "avg_conf": 0.82,
     "annotated": 标注图路径, "note": "对话·小麦"}

用途：数据看板的「时间趋势图」+「最近检测结果流」。
（stats.json 只有累计值没有时序，无法画趋势；本文件补上逐条时序。）

设计：追加写不锁文件（单进程 Gradio），读时容错——文件缺失 / 单行损坏 / 类型异常
一律安全降级为空记录，绝不抛异常影响主流程。
"""

import json
import os
import time

import pandas as pd

from .config import Config

DETECTION_LOG_FILE = Config.DETECTION_LOG_FILE


def append(image_count=0, wheat_count=0, drought_count=0,
           avg_conf=None, annotated=None, note="") -> bool:
    """追加一条检测记录，返回是否写入成功（失败静默）"""
    rec = {
        "ts": time.time(),
        "time": time.strftime("%m-%d %H:%M:%S"),
        "image_count": int(image_count or 0),
        "wheat_count": int(wheat_count or 0),
        "drought_count": int(drought_count or 0),
        "avg_conf": round(float(avg_conf or 0), 4),
        "annotated": annotated or "",
        "note": note or "",
    }
    try:
        os.makedirs(os.path.dirname(DETECTION_LOG_FILE), exist_ok=True)
        with open(DETECTION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def read() -> list:
    """读取全部记录（旧→新）。文件缺失 / 损坏行 → 跳过，绝不抛异常"""
    if not os.path.exists(DETECTION_LOG_FILE):
        return []
    out = []
    try:
        with open(DETECTION_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    continue
    except OSError:
        return []
    return out


def recent(limit=10) -> list:
    """最近 N 条（新→旧）"""
    return list(reversed(read()))[:limit]


def trend_df():
    """
    趋势图数据：按时间顺序，把「图像/小麦/干旱」累计为三条折线。
    返回 DataFrame（列 time=datetime / metric / count），无记录时返回 None。
    """
    rows = read()
    if not rows:
        return None
    cum = {"image": 0, "wheat": 0, "drought": 0}
    points = []
    for r in rows:
        cum["image"] += int(r.get("image_count", 0) or 0)
        cum["wheat"] += int(r.get("wheat_count", 0) or 0)
        cum["drought"] += int(r.get("drought_count", 0) or 0)
        for metric in ("image", "wheat", "drought"):
            points.append({"time": r["ts"], "metric": metric, "count": cum[metric]})
    df = pd.DataFrame(points)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df
