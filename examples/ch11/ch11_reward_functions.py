# -*- coding: utf-8 -*-
"""
第十一章 02 —— 奖励函数设计
镜像参考仓库 code/chapter11/02_reward_functions.py

离线可跑（纯 Python 实现，无需训练依赖）。
运行：python examples/ch11/ch11_reward_functions.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.rl import (
    compare_answers,
    create_accuracy_reward,
    create_combined_reward,
    create_length_penalty_reward,
    create_step_reward,
    extract_answer,
    extract_steps,
)

# 模型输出示例
_COMPLETIONS = [
    "Step 1: 48/2 = 24. Step 2: 48+24 = 72. Final Answer: 72",
    "Step 1: 12/60 = 0.2. Step 2: 50*0.2 = 10. Final Answer: 10",
    "I think the answer is 99.",
    "72",
]
_TRUTHS = ["72", "10", "72", "72"]


def main():
    print("=" * 60)
    print("第十一章 02 —— 奖励函数设计")
    print("=" * 60)

    # 1. 答案提取与比较
    print("\n[1] 答案提取 / 比较:")
    for comp in _COMPLETIONS:
        ans = extract_answer(comp)
        print(f"  extract_answer({comp[:45]}...) -> {ans}")
    print(f"  compare_answers('72.0', '72') -> {compare_answers('72.0', '72')}")
    print(f"  compare_answers('1k', '1000') -> {compare_answers('1k', '1000')}")

    # 2. 三类奖励
    print("\n[2] 三类奖励:")
    acc = create_accuracy_reward()
    lp = create_length_penalty_reward(penalty_weight=0.001, target_length=50)
    sr = create_step_reward(step_bonus=0.1)
    print(f"  准确率奖励    : {acc(completions=_COMPLETIONS, ground_truth=_TRUTHS)}")
    print(f"  长度惩罚奖励  : {lp(completions=_COMPLETIONS, ground_truth=_TRUTHS)}")
    print(f"  步骤奖励      : {sr(completions=_COMPLETIONS, ground_truth=_TRUTHS)}")

    # 3. 组合奖励（三者平衡）
    print("\n[3] 组合奖励（文档 11.2.2 三者平衡）:")
    cmb = create_combined_reward([
        {"type": "accuracy", "weight": 1.0},
        {"type": "length_penalty", "weight": 0.5, "target_length": 50},
        {"type": "step", "weight": 0.3, "step_bonus": 0.1},
    ])
    print(f"  combined: {cmb(completions=_COMPLETIONS, ground_truth=_TRUTHS)}")

    # 4. 步骤检测
    print("\n[4] 步骤检测:")
    print(f"  extract_steps(三行推理) -> {extract_steps('Step 1: x\nStep 2: y\nStep 3: z')}")

    print("\n✅ 奖励函数测试完成")


if __name__ == "__main__":
    main()
