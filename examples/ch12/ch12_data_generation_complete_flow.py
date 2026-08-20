# -*- coding: utf-8 -*-
"""
第十二章 07 —— 数据生成完整流程（生成 + LLM Judge + Win Rate）
镜像参考仓库 code/chapter12/07_data_generation_complete_flow.py

端到端演示 AIME 数据质量闭环：
1. AIMEGenerator 生成 AIME 风格题目（带参考样例引导）
2. LLMJudgeEvaluator 从 4 维度评分生成质量
3. WinRateEvaluator 与 AIME 真题成对对比（胜率）

小样本冒烟（默认 3 题 / 3 次对比），需 .env：
    python examples/ch12/ch12_data_generation_complete_flow.py

参数（可选）：
    --num-generate 3     # 生成题目数
    --num-compare 3      # Win Rate 对比次数
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.evaluation import (
    AIMEGenerator,
    LLMJudge,
    WinRateEvaluator,
)


def main():
    parser = argparse.ArgumentParser(description="AIME 数据生成完整流程")
    parser.add_argument("--num-generate", type=int, default=3, help="生成题目数")
    parser.add_argument("--num-compare", type=int, default=3, help="Win Rate 对比次数")
    args = parser.parse_args()

    print("=" * 60)
    print("第十二章 07 —— 数据生成完整流程")
    print("=" * 60)

    # 1. 生成 AIME 风格题目
    print(f"\n[1] 生成 {args.num_generate} 道 AIME 风格题目...")
    generator = AIMEGenerator(delay_seconds=0.5)
    problems = generator.generate_batch(args.num_generate)
    print(f"    生成完成: {len(problems)} 题")

    # 2. LLM Judge 质量评分
    print(f"\n[2] LLM Judge 质量评分...")
    judge = LLMJudge()
    judge_result = judge.evaluate_batch(problems, max_samples=len(problems))
    stats = judge_result["statistics"]
    print(f"    总体平均: {stats['avg_overall']:.2f}/5"
          f" | 及格率: {stats['pass_rate']:.0%}"
          f" | 评级: {LLMJudge.quality_rating(stats['avg_overall'])}")

    # 3. Win Rate 与真题对比
    print(f"\n[3] Win Rate 与 AIME 真题对比（{args.num_compare} 次）...")
    winrate = WinRateEvaluator()
    wr_result = winrate.evaluate(problems, num_comparisons=args.num_compare)
    print(f"    Win Rate: {wr_result['win_rate']:.0%}"
          f" | 平局: {wr_result['tie_rate']:.0%}"
          f" | 败率: {wr_result['loss_rate']:.0%}")

    print("\n" + "-" * 60)
    print(f"✅ 完整流程跑通。Win Rate {wr_result['win_rate']:.0%} ≈ 50% 表示")
    print("   生成质量与真题相当；<50% 需要改进生成提示词或人工筛选。")
    print("\n分步运行（独立脚本）:")
    print("   python examples/ch12/ch12_data_generation_llm_judge.py")
    print("   python examples/ch12/ch12_data_generation_win_rate.py")


if __name__ == "__main__":
    main()
