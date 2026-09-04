# -*- coding: utf-8 -*-
"""
Win Rate 数据生成质量评估（对齐文档第十二章 12.4.4）

通过「生成题目 vs AIME 真题」成对对比评估生成质量：
- Win Rate = 50%：生成质量与真题相当（理想情况）
- Win Rate > 50%：生成质量优于真题（可能是评估偏差）
- Win Rate < 50%：生成质量低于真题（需要改进）

聚合逻辑（纯逻辑，离线可测）：win_rate + tie_rate + loss_rate = 100%。

用法（对齐参考 09）：
    evaluator = WinRateEvaluator(llm=llm, reference_problems=reference_problems)
    results = evaluator.evaluate(generated_problems=..., num_comparisons=20)
    # → {win_rate, tie_rate, loss_rate, total_comparisons, wins, ties, losses, comparisons}
"""

import json
import random
import re
from typing import Any, Dict, List, Optional

from ...core.llm import HelloAgentsLLM

# 成对对比提示词（problem_a = 生成题，problem_b = 真题）
COMPARISON_PROMPT = """You are comparing the quality of two AIME (American Invitational Mathematics Examination) problems.

Problem A:
{problem_a}

Problem B:
{problem_b}

Judge which problem has higher quality, considering correctness, clarity, difficulty appropriateness, and originality.

Output strictly one of the following three words, no extra text:
- "generated"  if Problem A is better (Problem A wins)
- "reference"  if Problem B is better (Problem B wins)
- "tie"        if they are of similar quality"""


class WinRateEvaluator:
    """Win Rate 评估器。"""

    def __init__(self, llm: Optional[HelloAgentsLLM] = None,
                 reference_problems: Optional[List[Dict[str, Any]]] = None,
                 judge_model: Optional[str] = None,
                 max_retries: int = 2,
                 seed: Optional[int] = None):
        """
        Args:
            llm: LLM 实例（None 时创建默认 HelloAgentsLLM）。
            reference_problems: AIME 真题列表（默认 AIDataset().load()，见 dataset.py）。
            judge_model: 指定评估模型名（仅在 llm 为 None 时生效）。
            seed: 随机种子（可复现）。
        """
        if llm is None:
            self.llm = HelloAgentsLLM(model_name=judge_model) if judge_model else HelloAgentsLLM()
        else:
            self.llm = llm

        if reference_problems is None:
            from .dataset import AIDataset
            reference_problems = AIDataset().load()
        self.reference_problems = reference_problems or []
        self.max_retries = max_retries
        if seed is not None:
            random.seed(seed)

    # ---------------- 主流程 ----------------

    def evaluate(self, generated_problems: List[Dict[str, Any]],
                 num_comparisons: int = 20) -> Dict[str, Any]:
        """执行 num_comparisons 次成对对比并聚合结果。"""
        if not generated_problems:
            return self._aggregate([])
        if not self.reference_problems:
            raise ValueError("参考数据集为空，无法进行 Win Rate 对比")

        comparisons: List[Dict[str, Any]] = []
        for _ in range(num_comparisons):
            gen = random.choice(generated_problems)
            ref = random.choice(self.reference_problems)
            result, reason = self._compare_single(gen, ref)
            comparisons.append({
                "generated_problem": gen.get("problem", ""),
                "reference_problem": ref.get("problem", ""),
                "result": result,
                "reason": reason,
            })
        return self._aggregate(comparisons)

    # ================================================================
    # 纯逻辑：聚合与质量评级（离线可测）
    # ================================================================

    @staticmethod
    def _aggregate(comparisons: List[Dict[str, Any]]) -> Dict[str, Any]:
        """把 comparisons 聚合为统计结果。"""
        total = len(comparisons)
        wins = sum(1 for c in comparisons if c.get("result") == "generated")
        ties = sum(1 for c in comparisons if c.get("result") == "tie")
        losses = sum(1 for c in comparisons if c.get("result") == "reference")
        denominator = total or 1
        return {
            "win_rate": wins / denominator,
            "tie_rate": ties / denominator,
            "loss_rate": losses / denominator,
            "total_comparisons": total,
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "comparisons": comparisons,
        }

    @staticmethod
    def quality_rating(win_rate: float) -> str:
        """根据 Win Rate 给出质量评级（文档 12.4.4）。"""
        if 0.45 <= win_rate <= 0.55:
            return "优秀 - 生成质量接近AIME真题水平"
        if 0.35 <= win_rate < 0.45:
            return "良好 - 生成质量可用，但略低于真题"
        if 0.25 <= win_rate < 0.35:
            return "一般 - 生成质量一般，需要改进"
        return "较差 - 生成质量差，需要大幅改进"

    # ================================================================
    # 内部辅助
    # ================================================================

    def _compare_single(self, generated: Dict[str, Any],
                        reference: Dict[str, Any]) -> tuple:
        """单次成对对比，返回 (result, reason)。失败时默认 tie。"""
        prompt = COMPARISON_PROMPT.format(
            problem_a=generated.get("problem", ""),
            problem_b=reference.get("problem", ""),
        )
        for _ in range(self.max_retries):
            try:
                response = self.llm.invoke([{"role": "user", "content": prompt}])
                result = self._parse_winner(response)
                return result, response.strip()[:200]
            except Exception:  # noqa: BLE001
                continue
        return "tie", "对比失败，按平局处理"

    @staticmethod
    def _parse_winner(response: str) -> str:
        """从 LLM 回复解析 winner（generated / reference / tie）。"""
        text = response.strip().lower()
        if '"winner"' in text:
            try:
                data = json.loads(text)
                winner = str(data.get("winner", "")).lower()
                if winner in ("generated", "reference", "tie"):
                    return winner
            except json.JSONDecodeError:
                pass
        m = re.search(r"(generated|reference|tie)", text)
        if m:
            return m.group(1)
        raise ValueError(f"无法解析对比结果: {response[:200]}")
