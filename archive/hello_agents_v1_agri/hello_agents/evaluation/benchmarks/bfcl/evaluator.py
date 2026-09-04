# -*- coding: utf-8 -*-
"""
BFCLEvaluator 评估器（对齐文档第十二章 12.2.5）

对每个样本：构造提示词（函数定义 + 问题）→ 调 ``agent.run`` → 提取函数调用 →
AST 匹配 ground_truth → 聚合指标。

提取支持三种格式（文档 12.2.5）：
- JSON 数组（``[{"name": ..., "arguments": {...}}]``）
- 代码块（`` ```python func(...) ``` ``）
- 纯函数调用文本（``func(a=1, b=2)``）

用法（对齐参考 03）：
    evaluator = BFCLEvaluator(dataset=dataset, category="simple_python")
    results = evaluator.evaluate(agent, max_samples=5)
"""

import json
import os
from typing import Any, Dict, List, Optional

from .ast_matcher import extract_call_dicts, match_calls
from .metrics import compute_metrics

# 函数调用系统提示词（对齐参考 04，要求模型输出纯 JSON）
FUNCTION_CALLING_SYSTEM_PROMPT = """你是一个专业的函数调用助手。

你的任务是：根据用户的问题和提供的函数定义，生成正确的函数调用。

输出格式要求：
1. 必须是纯JSON格式，不要添加任何解释文字
2. 使用JSON数组格式：[{"name": "函数名", "arguments": {"参数名": "参数值"}}]
3. 如果需要调用多个函数，在数组中添加多个对象
4. 如果不需要调用函数，返回空数组：[]

示例：
用户问题：查询北京的天气
可用函数：get_weather(city: str)
正确输出：[{"name": "get_weather", "arguments": {"city": "北京"}}]

注意：
- 只输出JSON，不要添加"好的"、"我来帮你"等额外文字
- 参数值必须与函数定义的类型匹配
- 参数名必须与函数定义完全一致
"""


class BFCLEvaluator:
    """BFCL 评估器。"""

    def __init__(self, dataset, category: str = "simple_python",
                 evaluation_mode: str = "ast"):
        """
        Args:
            dataset: BFCLDataset 实例。
            category: 评估类别。
            evaluation_mode: 匹配方式（当前仅 "ast"，保留参数以对齐接口）。
        """
        self.dataset = dataset
        self.category = category
        self.evaluation_mode = evaluation_mode

    # ---------------- 主流程 ----------------

    def evaluate(self, agent, max_samples: Optional[int] = 5) -> Dict[str, Any]:
        """对数据集跑评估，返回聚合结果 + 每样本详情。

        Args:
            agent: 具备 ``run(prompt) -> str`` 的智能体（SimpleAgent）。
            max_samples: 限制样本数（None/0 表示全部）。
        """
        data = self.dataset.load()
        if max_samples:
            data = data[:max_samples]

        detailed_results: List[Dict[str, Any]] = []
        for sample in data:
            prompt = self._build_prompt(sample)
            error = None
            try:
                response = agent.run(prompt)
            except Exception as e:  # noqa: BLE001
                response = ""
                error = str(e)

            pred_calls = self._extract_function_calls(response)
            expected_calls = self._extract_function_calls(sample.get("ground_truth", ""))
            success = match_calls(pred_calls, expected_calls)
            name_match = self._names_match(pred_calls, expected_calls)

            detailed_results.append({
                "sample_id": sample.get("id", ""),
                "category": self.category,
                "question": sample.get("question", ""),
                "predicted": response,
                "expected": sample.get("ground_truth", ""),
                "predicted_calls": pred_calls,
                "expected_calls": expected_calls,
                "success": success,
                "name_match": name_match,
                "param_match": success,
                "error": error,
            })

        metrics = compute_metrics(detailed_results)
        return {
            "total_samples": metrics["total_samples"],
            "correct_samples": metrics["correct_samples"],
            "overall_accuracy": metrics["accuracy"],
            "ast_match_rate": metrics["ast_match_rate"],
            "parameter_accuracy": metrics["parameter_accuracy"],
            "f1_score": metrics["f1_score"],
            "error_rate": metrics["error_rate"],
            "category_accuracies": metrics["category_statistics"],
            "detailed_results": detailed_results,
        }

    # ---------------- 导出 ----------------

    def export_results(self, results: Dict[str, Any],
                       output_file: Optional[str] = None) -> str:
        """把评估结果导出为 JSON。"""
        output_file = output_file or "./evaluation_results/bfcl_custom_result.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        return output_file

    def export_to_bfcl_format(self, results: Dict[str, Any],
                              output_file: Optional[str] = None) -> str:
        """导出为 BFCL 官方评估格式（JSONL：每行 {question, answer: [{name, arguments}]}）。"""
        output_file = output_file or "./evaluation_results/bfcl_official/BFCL_v4_result.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            for detail in results.get("detailed_results", []):
                answer = []
                for call in detail.get("predicted_calls", []):
                    answer.append({
                        "name": call.get("name", ""),
                        "arguments": call.get("arguments", {}).get("keywords", {}),
                    })
                f.write(json.dumps({
                    "question": detail.get("question", ""),
                    "answer": answer,
                }, ensure_ascii=False) + "\n")
        return output_file

    # ---------------- 内部辅助 ----------------

    def _build_prompt(self, sample: Dict[str, Any]) -> str:
        """构造单样本提示词：函数定义 + 问题。"""
        return (
            f"可用函数定义：\n{sample.get('function', '')}\n\n"
            f"用户问题：{sample.get('question', '')}\n\n"
            f"请根据问题生成正确的函数调用，只输出 JSON 数组格式。"
        )

    @staticmethod
    def _extract_function_calls(text: str) -> List[Dict[str, Any]]:
        """从回复中提取函数调用（复用 ast_matcher 的三格式提取）。"""
        return extract_call_dicts(text)

    @staticmethod
    def _names_match(pred_calls: List[Dict[str, Any]],
                     true_calls: List[Dict[str, Any]]) -> bool:
        """函数名集合是否一致（顺序无关）。"""
        pred_names = sorted(c.get("name", "") for c in pred_calls)
        true_names = sorted(c.get("name", "") for c in true_calls)
        return pred_names == true_names
