# -*- coding: utf-8 -*-
"""
stats_store —— 平台累计统计 + 实验指标（JSON 文件持久化）

累计统计（动态，随每次检测实时累计，写入 Config.STATS_FILE）：
- total_images   累计检测图像数（含识别为小麦与非小麦的图）
- total_wheat    累计识别的小麦株数（检测框总数）
- total_drought  累计干旱株数
- updated_at     最近一次更新时间

实验指标（只读真实实验数据，不编造）：
- experiment_accuracy  实验准确率：读分类器对比 CSV 中默认分类器（yolov8s-cls = exp_augmented2_s）的 accuracy
- final_val_loss       最终验证损失：同行的 val_loss
  CSV 缺失时回退论文表 5-4 记录值（77.97% / 0.44898，与平台默认模型一致）。
"""

import csv
import json
import os
import time

from .config import Config

STATS_FILE = Config.STATS_FILE

# 论文表 5-4 记录的默认分类器指标（yolov8s-cls = exp_augmented2_s，本平台默认）
_DEFAULT_ACC = 0.7797
_DEFAULT_LOSS = 0.44898


def _default_stats() -> dict:
    return {"total_images": 0, "total_wheat": 0, "total_drought": 0, "updated_at": ""}


def _read() -> dict:
    if not os.path.exists(STATS_FILE):
        return _default_stats()
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        base = _default_stats()
        for k in ("total_images", "total_wheat", "total_drought"):
            base[k] = int(data.get(k, 0))
        base["updated_at"] = data.get("updated_at", "")
        return base
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return _default_stats()


def _write(data: dict):
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def record(image_count=0, wheat_count=0, drought_count=0) -> dict:
    """累计一次检测结果（读改写），返回更新后统计"""
    data = _read()
    try:
        data["total_images"] += int(image_count or 0)
        data["total_wheat"] += int(wheat_count or 0)
        data["total_drought"] += int(drought_count or 0)
    except (TypeError, ValueError):
        pass
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write(data)
    return data


def _experiment_metrics() -> tuple:
    """默认分类器（yolov8s-cls/exp_augmented2_s）的 accuracy 与 val_loss（真实 CSV）"""
    acc, loss = _DEFAULT_ACC, _DEFAULT_LOSS
    p = Config.EXPERIMENT_EVAL_CSV
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if "yolov8s-cls" in (r.get("model") or ""):
                        acc = float(r.get("accuracy") or acc)
                        vl = r.get("val_loss")
                        if vl:
                            loss = float(vl)
                        break
        except (OSError, csv.Error, ValueError, TypeError):
            pass
    return acc, loss


def get_stats() -> dict:
    """累计统计 + 实验指标（准确率 / 最终验证损失）"""
    data = _read()
    acc, loss = _experiment_metrics()
    data["experiment_accuracy"] = acc
    data["final_val_loss"] = loss
    return data
