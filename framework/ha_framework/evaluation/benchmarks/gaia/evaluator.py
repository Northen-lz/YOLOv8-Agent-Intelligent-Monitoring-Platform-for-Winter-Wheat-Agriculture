# -*- coding: utf-8 -*-
"""
GAIAEvaluator 评估器（对齐文档第十二章 12.3.4 / 12.3.5）

对每个样本：调 ``agent.run(question)`` → 提取 ``FINAL ANSWER:`` → 准精确匹配。

提取策略（文档 12.3.4）：
1. ``FINAL ANSWER:`` 优先（GAIA 官方模板）
2. 中文 ``答案：`` / ``Answer:`` 兜底
3. 无标记时取最后一行

用法（对齐参考 05）：
    evaluator = GAIAEvaluator(dataset=dataset, level=1)
    results = evaluator.evaluate(agent, max_samples=2)
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from .metrics import compute_metrics
from .quasi_exact_match import partial_match, quasi_exact_match

# GAIA 官方系统提示词（文档 12.3.5 强调必须使用）
GAIA_SYSTEM_PROMPT = """You are a general AI assistant. I will ask you a question. Report your thoughts, and finish your answer with the following template: FINAL ANSWER: [YOUR FINAL ANSWER].
YOUR FINAL ANSWER should be a number OR as few words as possible OR a comma separated list of numbers and/or strings.
If you are asked for a number, don't use comma to write your number neither use units such as $ or percent sign unless specified otherwise.
If you are asked for a string, don't use articles, neither abbreviations (e.g. for cities), and write the digits in plain text unless specified otherwise.
If you are asked for a comma separated list, apply the above rules depending of whether the element to be put in the list is a number or a string."""

# 答案标记（按优先级）
_ANSWER_MARKERS = [
    "FINAL ANSWER:",
    "Final answer:",
    "final answer:",
    "最后答案：",
    "答案：",
    "Answer:",
]


class GAIAEvaluator:
    """GAIA 评估器。"""

    def __init__(self, dataset, level: Optional[int] = None):
        """
        Args:
            dataset: GAIADataset 实例。
            level: 评估级别（1/2/3，None 表示数据集全部）。
        """
        self.dataset = dataset
        self.level = level

    # ---------------- 主流程 ----------------

    def evaluate(self, agent, max_samples: Optional[int] = None) -> Dict[str, Any]:
        """对数据集跑评估，返回聚合结果 + 每样本详情。"""
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

            predicted = self._extract_answer(response)
            expected = sample.get("final_answer", "")
            exact = quasi_exact_match(predicted, expected)
            partial = partial_match(predicted, expected)

            detailed_results.append({
                "sample_id": sample.get("task_id", ""),
                "level": sample.get("level", 1),
                "question": sample.get("question", ""),
                "predicted": predicted,
                "expected": expected,
                "success": exact,
                "partial": partial,
                "error": error,
            })

        metrics = compute_metrics(detailed_results)
        return {
            "exact_match_rate": metrics["exact_match_rate"],
            "partial_match_rate": metrics["partial_match_rate"],
            "correct_samples": metrics["correct_samples"],
            "partial_samples": metrics["partial_samples"],
            "total_samples": metrics["total_samples"],
            "drop_rate": metrics["drop_rate"],
            "average_steps": metrics["average_steps"],
            "level_metrics": metrics["level_wise_accuracy"],
            "detailed_results": detailed_results,
        }

    # ---------------- 导出 ----------------

    def export_results(self, results: Dict[str, Any],
                       output_file: Optional[str] = None) -> str:
        """把评估结果导出为 JSON。"""
        output_file = output_file or "./evaluation_results/gaia_custom_result.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        return output_file

    def export_to_gaia_format(self, results: Dict[str, Any],
                              path: Optional[str] = None,
                              include_reasoning: bool = True) -> str:
        """导出为 GAIA 官方提交格式（JSONL：{task_id, answer}）。"""
        path = path or "./evaluation_results/gaia_submission.jsonl"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for detail in results.get("detailed_results", []):
                entry: Dict[str, Any] = {
                    "task_id": detail.get("sample_id", ""),
                    "answer": detail.get("predicted", ""),
                }
                if include_reasoning:
                    entry["reasoning"] = detail.get("question", "")
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path

    # ---------------- 内部辅助 ----------------

    def _build_prompt(self, sample: Dict[str, Any]) -> str:
        """GAIA 直接问问题即可（智能体已带官方系统提示词）。"""
        return sample.get("question", "")

    @staticmethod
    def _extract_answer(text: str) -> str:
        """提取 FINAL ANSWER（文档 12.3.4 三种格式）。"""
        text = (text or "").strip()
        if not text:
            return ""

        for marker in _ANSWER_MARKERS:
            idx = text.rfind(marker)
            if idx != -1:
                ans = text[idx + len(marker):].strip()
                return GAIAEvaluator._clean_answer(ans)

        # 无标记：取最后非空行
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            return GAIAEvaluator._clean_answer(lines[-1])
        return ""

    @staticmethod
    def _clean_answer(ans: str) -> str:
        """清理答案：去 markdown 粗体 / 代码围栏 / 行尾杂质。"""
        ans = re.sub(r"\*\*(.*?)\*\*", r"\1", ans)
        ans = re.sub(r"```[a-z]*", "", ans).strip("`")
        # 若取到整个剩余文本多行，取第一行（答案应紧跟标记）
        ans = ans.splitlines()[0].strip() if ans else ""
        return ans
