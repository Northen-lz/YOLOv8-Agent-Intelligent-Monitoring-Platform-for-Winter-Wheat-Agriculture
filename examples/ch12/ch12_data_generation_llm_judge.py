# -*- coding: utf-8 -*-
"""
第十二章 08 —— LLM Judge 数据生成质量评估
镜像参考仓库 code/chapter12/08_data_generation_llm_judge.py

从 4 个维度（正确性/清晰度/难度匹配/完整性，1-5分）评估 AIME 生成题目质量：
- 单题评估：看逐维评分 + 评语
- 批量评估：平均分 / 及格率（≥3.5）/ 优秀率（≥4.5）
- 质量评级：≥4 优秀 / ≥3 良好 / ≥2 一般 / 差

需 .env。未生成数据时用内置示例题目演示：
    python examples/ch12/ch12_data_generation_llm_judge.py
    python examples/ch12/ch12_data_generation_llm_judge.py --data data_generation/generated_data/aime_generated.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.evaluation import LLMJudge

# 内置示例生成题（无生成数据时的演示用）
_DEMO_PROBLEMS = [
    {
        "problem_id": "demo_1",
        "problem": "Find the number of positive integers less than 200 that are divisible by 7.",
        "answer": 28,
        "solution": "The largest multiple of 7 below 200 is 196=7×28, so there are 28.",
        "topic": "Number Theory",
    },
    {
        "problem_id": "demo_2",
        "problem": "A fair coin is tossed 6 times. What is the probability that exactly 3 heads appear?",
        "answer": 20,
        "solution": "Number of outcomes with exactly 3 heads is C(6,3)=20; total 2^6=64; "
                    "probability 20/64. (AIME-style integer answer encodes numerator-of-64.)",
        "topic": "Probability",
    },
    {
        "problem_id": "demo_3",
        "problem": "Let x and y be positive integers with x + y = 50. Find the maximum value of xy.",
        "answer": 625,
        "solution": "By AM-GM, xy ≤ ((x+y)/2)^2 = 25^2 = 625, attained at x=y=25.",
        "topic": "Algebra",
    },
]


def _load_problems(path):
    if not path or not os.path.exists(path):
        print("  ⚠️ 未找到生成数据文件，使用内置示例题目演示")
        return _DEMO_PROBLEMS
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="LLM Judge 数据生成质量评估")
    parser.add_argument("--data", default=None, help="生成数据 JSON 文件路径")
    parser.add_argument("--max-samples", type=int, default=None, help="最多评估样本数")
    args = parser.parse_args()

    print("=" * 60)
    print("第十二章 08 —— LLM Judge 数据生成质量评估")
    print("=" * 60)

    problems = _load_problems(args.data)
    print(f"\n[1] 加载 {len(problems)} 道生成题")

    # 2. 单题评估（演示逐维评分）
    judge = LLMJudge()
    print(f"\n[2] 单题评估（第一题）...")
    result = judge.evaluate_single(problems[0])
    print(f"    正确性: {result['correctness']}/5 | 清晰度: {result['clarity']}/5")
    print(f"    难度匹配: {result['difficulty_match']}/5 | 完整性: {result['completeness']}/5")
    print(f"    平均分: {result['average_score']}/5")
    if result.get("feedback"):
        print(f"    评语: {result['feedback'][:100]}")

    # 3. 批量评估 + 统计
    print(f"\n[3] 批量评估（{len(problems)} 题）...")
    batch = judge.evaluate_batch(problems, max_samples=args.max_samples)
    stats = batch["statistics"]
    print(f"    总体平均: {stats['avg_overall']:.2f}/5")
    print(f"    各维平均: 正确性 {stats['avg_correctness']:.2f} | "
          f"清晰度 {stats['avg_clarity']:.2f} | "
          f"难度 {stats['avg_difficulty']:.2f} | 完整性 {stats['avg_completeness']:.2f}")
    print(f"    及格率(≥3.5): {stats['pass_rate']:.1%} | 优秀率(≥4.5): {stats['excellent_rate']:.1%}")
    print(f"    质量评级: {LLMJudge.quality_rating(stats['avg_overall'])}")

    # 4. 保存结果
    os.makedirs("evaluation_results", exist_ok=True)
    out = "evaluation_results/llm_judge_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    print(f"\n[4] 结果已保存: {out}")


if __name__ == "__main__":
    main()
