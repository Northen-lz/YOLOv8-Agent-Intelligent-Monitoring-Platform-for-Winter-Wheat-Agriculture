# -*- coding: utf-8 -*-
"""
GAIA 指标聚合（对齐文档第十二章 12.3.1）

纯逻辑模块：从 detailed_results（每样本 dict）聚合出评估指标。
- exact_match_rate   精确匹配率 = 完全匹配样本 / 总样本
- partial_match_rate 部分匹配率 = 部分匹配样本 / 总样本
- level_wise_accuracy 按 Level(1/2/3) 分层的准确率
- drop_rate          掉线率 = 出错/无答案样本占比（模型未完成任务）
- average_steps      平均推理步数（若追踪了 steps 字段）

输入：每样本 dict 需包含
    sample_id / level / question / predicted / expected /
    success(bool) / partial(bool) / steps(Optional[int]) / error(Optional[str])
"""

from typing import Any, Dict, List


def compute_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合 detailed_results 为标准指标字典。"""
    total = len(results)
    if total == 0:
        return {
            "exact_match_rate": 0.0,
            "partial_match_rate": 0.0,
            "level_wise_accuracy": {},
            "drop_rate": 0.0,
            "average_steps": 0.0,
            "total_samples": 0,
            "correct_samples": 0,
        }

    exact_ok = sum(1 for r in results if r.get("success"))
    partial_ok = sum(1 for r in results if r.get("partial"))
    dropped = sum(1 for r in results if r.get("error") or not (r.get("predicted") or "").strip())

    steps = [r["steps"] for r in results if isinstance(r.get("steps"), (int, float))]
    average_steps = sum(steps) / len(steps) if steps else 0.0

    # 按 Level 分层
    levels: Dict[int, List[int]] = {}
    for r in results:
        lv = r.get("level") or 0
        levels.setdefault(lv, [0, 0])  # [correct, total]
        levels[lv][1] += 1
        if r.get("success"):
            levels[lv][0] += 1
    level_wise_accuracy = {
        int(lv): {
            "exact_match_rate": (c / t) if t else 0.0,
            "correct": c,
            "total": t,
        }
        for lv, (c, t) in sorted(levels.items())
    }

    return {
        "exact_match_rate": exact_ok / total,
        "partial_match_rate": partial_ok / total,
        "level_wise_accuracy": level_wise_accuracy,
        "drop_rate": dropped / total,
        "average_steps": average_steps,
        "total_samples": total,
        "correct_samples": exact_ok,
        "partial_samples": partial_ok,
    }


class GAIA_Metrics:
    """GAIA 指标计算器（面向对象封装，文档 12.3.1）。"""

    def __init__(self) -> None:
        self.results: List[Dict[str, Any]] = []

    def add_result(self, result: Dict[str, Any]) -> "GAIA_Metrics":
        self.results.append(result)
        return self

    def compute(self) -> Dict[str, Any]:
        return compute_metrics(self.results)
