# -*- coding: utf-8 -*-
"""
LLM Judge 数据生成质量评估（对齐文档第十二章 12.4.3）

从 4 个维度评估 AIME 生成题目质量，每维 1-5 分：
- correctness     正确性：题目与答案是否正确
- clarity         清晰度：表述是否清晰无歧义
- difficulty_match 难度匹配：是否符合 AIME 水平
- completeness    完整性：题目（题干+答案+解析）是否完整

聚合指标（纯逻辑，离线可测）：
- 平均分 / 及格率（≥3.5）/ 优秀率（≥4.5）
- quality_rating：≥4 优秀 / ≥3 良好 / ≥2 一般 / 较差

用法（对齐参考 08）：
    judge = LLMJudge(llm=llm)
    result = judge.evaluate_single(problem)
    # → {correctness, clarity, difficulty_match, completeness, average_score, feedback}
"""

import json
import re
from typing import Any, Dict, List, Optional

from ...core.llm import HelloAgentsLLM

# LLM Judge 评估提示词（要求输出纯 JSON）
JUDGE_PROMPT = """You are an expert evaluator of AIME (American Invitational Mathematics Examination) problem quality.

Evaluate the given problem on 4 dimensions, each scored from 1 to 5:
1. correctness: Whether the problem statement and its answer are correct.
2. clarity: Whether the problem statement is clear and unambiguous.
3. difficulty_match: Whether the difficulty matches the AIME level (medium to hard, multi-step).
4. completeness: Whether the problem is complete (statement + answer + solution).

Problem:
{problem}

Answer:
{answer}

Solution:
{solution}

Output strictly in the following JSON format, no extra text:
{{"correctness": <int 1-5>, "clarity": <int 1-5>, "difficulty_match": <int 1-5>, "completeness": <int 1-5>, "feedback": "<brief English feedback>"}}"""


class LLMJudgeEvaluator:
    """LLM Judge 评估器。"""

    def __init__(self, llm: Optional[HelloAgentsLLM] = None,
                 judge_model: Optional[str] = None,
                 max_retries: int = 2):
        """
        Args:
            llm: LLM 实例（None 时创建默认 HelloAgentsLLM，可传 judge_model 指定）。
            judge_model: 指定评估模型名（仅在 llm 为 None 时生效）。
            max_retries: 单题评估失败最大重试次数。
        """
        if llm is None:
            if judge_model:
                self.llm = HelloAgentsLLM(model_name=judge_model)
            else:
                self.llm = HelloAgentsLLM()
        else:
            self.llm = llm
        self.max_retries = max_retries

    # ---------------- 单题评估 ----------------

    def evaluate_single(self, problem: Dict[str, Any]) -> Dict[str, Any]:
        """评估单道题目，返回 4 维评分 + 平均分 + 评语。"""
        prompt = self._build_prompt(problem)
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.llm.invoke([{"role": "user", "content": prompt}])
                parsed = self._parse_response(response)
                parsed["average_score"] = round(
                    (parsed["correctness"] + parsed["clarity"]
                     + parsed["difficulty_match"] + parsed["completeness"]) / 4, 2
                )
                return parsed
            except Exception as e:  # noqa: BLE001
                last_error = e
        raise RuntimeError(f"LLM Judge 评估失败（重试 {self.max_retries} 次）: {last_error}")

    # ---------------- 批量评估 ----------------

    def evaluate_batch(self, problems: List[Dict[str, Any]],
                       max_samples: Optional[int] = None) -> Dict[str, Any]:
        """批量评估，返回 scores 列表 + 统计信息。

        单题失败不中断整体：以 error 标记入表。
        """
        items = problems[:max_samples] if max_samples else list(problems)
        scores: List[Dict[str, Any]] = []
        for p in items:
            try:
                scores.append(self.evaluate_single(p))
            except Exception as e:  # noqa: BLE001
                scores.append({
                    "correctness": 0, "clarity": 0,
                    "difficulty_match": 0, "completeness": 0,
                    "average_score": 0.0,
                    "feedback": f"评估失败: {e}", "error": str(e),
                })
        return {
            "scores": scores,
            "statistics": self.compute_statistics(scores),
        }

    # ================================================================
    # 纯逻辑：统计与质量评级（离线可测）
    # ================================================================

    @staticmethod
    def compute_statistics(scores: List[Dict[str, Any]]) -> Dict[str, float]:
        """聚合评分列表为统计指标（平均分 / 及格率≥3.5 / 优秀率≥4.5）。"""
        n = len(scores)
        if n == 0:
            return {
                "avg_correctness": 0.0, "avg_clarity": 0.0,
                "avg_difficulty": 0.0, "avg_completeness": 0.0,
                "avg_overall": 0.0, "pass_rate": 0.0,
                "excellent_rate": 0.0, "count": 0,
            }
        avg = lambda key: sum(s.get(key, 0) for s in scores) / n  # noqa: E731
        pass_rate = sum(1 for s in scores if s.get("average_score", 0) >= 3.5) / n
        excellent_rate = sum(1 for s in scores if s.get("average_score", 0) >= 4.5) / n
        return {
            "avg_correctness": avg("correctness"),
            "avg_clarity": avg("clarity"),
            "avg_difficulty": avg("difficulty_match"),
            "avg_completeness": avg("completeness"),
            "avg_overall": avg("average_score"),
            "pass_rate": pass_rate,
            "excellent_rate": excellent_rate,
            "count": n,
        }

    @staticmethod
    def quality_rating(avg_overall: float) -> str:
        """根据总体平均分给出质量评级（文档 12.4.3）。"""
        if avg_overall >= 4.0:
            return "优秀 - 题目质量很高，可以直接使用"
        if avg_overall >= 3.0:
            return "良好 - 题目质量可用，建议人工审核"
        if avg_overall >= 2.0:
            return "一般 - 题目质量一般，需要大幅改进"
        return "较差 - 题目质量差，需要重新生成"

    # ================================================================
    # 内部辅助
    # ================================================================

    def _build_prompt(self, problem: Dict[str, Any]) -> str:
        return JUDGE_PROMPT.format(
            problem=problem.get("problem", ""),
            answer=problem.get("answer", ""),
            solution=problem.get("solution", "No solution provided"),
        )

    @staticmethod
    def _parse_response(response: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON，提取 4 维评分与评语。"""
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        data = None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    data = None
        if not isinstance(data, dict):
            raise ValueError(f"无法解析 LLM 评估结果: {response[:200]}")

        def _clamp_score(v: Any, default: int = 3) -> int:
            try:
                val = int(float(v))
            except (TypeError, ValueError):
                return default
            return max(1, min(5, val))

        scores = {
            "correctness": _clamp_score(data.get("correctness")),
            "clarity": _clamp_score(data.get("clarity")),
            "difficulty_match": _clamp_score(data.get("difficulty_match")),
            "completeness": _clamp_score(data.get("completeness")),
        }
        scores["feedback"] = str(data.get("feedback", ""))[:500]
        return scores


# 对齐参考示例 08 的命名
LLMJudge = LLMJudgeEvaluator
