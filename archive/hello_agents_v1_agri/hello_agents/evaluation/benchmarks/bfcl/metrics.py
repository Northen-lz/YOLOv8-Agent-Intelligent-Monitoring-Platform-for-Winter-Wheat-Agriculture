# -*- coding: utf-8 -*-
"""
BFCL 指标聚合（对齐文档第十二章 12.2.3）

纯逻辑模块：从 ``detailed_results``（每样本 dict）聚合出官方指标。
- accuracy            总体准确率 = 全对样本 / 总样本
- ast_match_rate      AST 完全匹配率（成功样本占比，与 accuracy 同源）
- parameter_accuracy  参数准确率 = 函数名全对样本中参数也全对的比例
- f1_score            函数调用级 F1（把每次调用当作一次检测）
- category_statistics 按类别统计的准确率
- error_rate          解析 / 执行出错样本占比

输入：每样本 dict 需包含
    sample_id / category / question / predicted / expected /
    success(bool) / name_match(bool) / param_match(bool) /
    error(Optional[str]) / predicted_calls(list) / expected_calls(list)
其中 name_match 表示函数名全部匹配，success 表示 AST 全匹配（含参数）。
"""

from typing import Any, Dict, List

from .ast_matcher import ast_match


def compute_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合 detailed_results 为标准指标字典。"""
    total = len(results)
    if total == 0:
        return {
            "accuracy": 0.0,
            "ast_match_rate": 0.0,
            "parameter_accuracy": 0.0,
            "f1_score": 0.0,
            "error_rate": 0.0,
            "category_statistics": {},
            "total_samples": 0,
            "correct_samples": 0,
        }

    success = sum(1 for r in results if r.get("success"))
    name_ok = sum(1 for r in results if r.get("name_match"))
    param_ok = sum(1 for r in results if r.get("param_match"))
    errors = sum(1 for r in results if r.get("error"))

    accuracy = success / total
    parameter_accuracy = param_ok / name_ok if name_ok else 0.0
    error_rate = errors / total

    # 函数调用级 F1：把每次真实调用当作一条正样本，预测调用当作检测结果
    tp = fp = fn = 0
    for r in results:
        pred_calls = r.get("predicted_calls") or []
        true_calls = r.get("expected_calls") or []
        matched: set = set()
        for t in true_calls:
            for p_idx, p in enumerate(pred_calls):
                if p_idx not in matched and ast_match(p, t):
                    matched.add(p_idx)
                    tp += 1
                    break
            else:
                fn += 1
        fp += len(pred_calls) - len(matched)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # 类别统计
    cats: Dict[str, List[int]] = {}
    for r in results:
        cat = r.get("category") or "unknown"
        cats.setdefault(cat, [0, 0])  # [correct, total]
        cats[cat][1] += 1
        if r.get("success"):
            cats[cat][0] += 1
    category_statistics = {
        cat: {
            "accuracy": (c / t) if t else 0.0,
            "correct": c,
            "total": t,
        }
        for cat, (c, t) in sorted(cats.items())
    }

    return {
        "accuracy": accuracy,
        "ast_match_rate": accuracy,
        "parameter_accuracy": parameter_accuracy,
        "f1_score": f1_score,
        "error_rate": error_rate,
        "category_statistics": category_statistics,
        "total_samples": total,
        "correct_samples": success,
        "precision": precision,
        "recall": recall,
    }


class BFCLMetrics:
    """BFCL 指标计算器（面向对象封装，文档 12.2.3）。"""

    def __init__(self) -> None:
        self.results: List[Dict[str, Any]] = []

    def add_result(self, result: Dict[str, Any]) -> "BFCLMetrics":
        """追加一条样本结果，返回 self 以便链式调用。"""
        self.results.append(result)
        return self

    def compute(self) -> Dict[str, Any]:
        """返回聚合指标。"""
        return compute_metrics(self.results)
