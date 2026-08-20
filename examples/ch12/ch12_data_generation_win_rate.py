# -*- coding: utf-8 -*-
"""
第十二章 09 —— Win Rate 数据生成质量评估
镜像参考仓库 code/chapter12/09_data_generation_win_rate.py

通过「生成题 vs AIME 真题」成对对比（LLM 判定胜负）评估生成质量：
- Win Rate ≈ 50%：生成质量与真题相当（理想）
- Win Rate > 50%：优于真题（可能是评估偏差）
- Win Rate < 50%：低于真题（需要改进）

需 .env。未生成数据时用内置示例题目演示：
    python examples/ch12/ch12_data_generation_win_rate.py
    python examples/ch12/ch12_data_generation_win_rate.py --data data_generation/generated_data/aime_generated.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.evaluation import AIDataset, WinRateEvaluator

# 内置示例生成题（无生成数据时的演示用）
_DEMO_PROBLEMS = [
    {
        "problem_id": "demo_1",
        "problem": "Find the number of positive integers less than 200 that are divisible by 7.",
        "answer": 28,
        "solution": "The largest multiple of 7 below 200 is 196=7×28, so there are 28.",
    },
    {
        "problem_id": "demo_2",
        "problem": "A fair coin is tossed 6 times. What is the probability that exactly 3 heads appear?",
        "answer": 20,
        "solution": "Number of outcomes with exactly 3 heads is C(6,3)=20; total 2^6=64.",
    },
    {
        "problem_id": "demo_3",
        "problem": "Let x and y be positive integers with x + y = 50. Find the maximum value of xy.",
        "answer": 625,
        "solution": "By AM-GM, xy ≤ ((x+y)/2)^2 = 25^2 = 625.",
    },
]


def _load_problems(path):
    if not path or not os.path.exists(path):
        print("  ⚠️ 未找到生成数据文件，使用内置示例题目演示")
        return _DEMO_PROBLEMS
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Win Rate 数据生成质量评估")
    parser.add_argument("--data", default=None, help="生成数据 JSON 文件路径")
    parser.add_argument("--num-comparisons", type=int, default=5, help="对比次数")
    args = parser.parse_args()

    print("=" * 60)
    print("第十二章 09 —— Win Rate 数据生成质量评估")
    print("=" * 60)

    # 1. 加载生成题
    generated = _load_problems(args.data)
    print(f"\n[1] 加载 {len(generated)} 道生成题")

    # 2. 加载 AIME 真题（HF 下载失败自动离线兜底）
    reference = AIDataset().load()
    print(f"[2] 加载 {len(reference)} 道 AIME 真题（来源: {AIDataset().get_statistics()['data_source']}）")

    # 3. 成对对比评估
    evaluator = WinRateEvaluator(reference_problems=reference)
    result = evaluator.evaluate(generated, num_comparisons=args.num_comparisons)

    print(f"\n[3] 对比 {result['total_comparisons']} 次:")
    print(f"    胜率 Win Rate: {result['win_rate']:.0%}（{result['wins']} 胜）")
    print(f"    平局率 Tie Rate: {result['tie_rate']:.0%}（{result['ties']} 平）")
    print(f"    败率 Loss Rate: {result['loss_rate']:.0%}（{result['losses']} 负）")
    print(f"    质量评级: {WinRateEvaluator.quality_rating(result['win_rate'])}")

    # 4. 查看单次对比示例
    if result.get("comparisons"):
        c = result["comparisons"][0]
        print(f"\n[4] 示例对比: 判定={c['result']}")
        print(f"    生成题: {c['generated_problem'][:70]}...")
        print(f"    真题:   {c['reference_problem'][:70]}...")

    # 5. 保存结果
    os.makedirs("evaluation_results", exist_ok=True)
    out = "evaluation_results/win_rate_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[5] 结果已保存: {out}")


if __name__ == "__main__":
    main()
