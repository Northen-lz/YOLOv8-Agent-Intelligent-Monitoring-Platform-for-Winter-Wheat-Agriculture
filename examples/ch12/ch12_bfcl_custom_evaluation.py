# -*- coding: utf-8 -*-
"""
第十二章 03 —— BFCL 自定义评估流程
镜像参考仓库 code/chapter12/03_bfcl_custom_evaluation.py

手动组合 BFCLDataset + BFCLEvaluator + SimpleAgent：
- 自己创建智能体（可自定义系统提示词 / 传本地数据）
- 逐样本查看评估结果（成功/失败 + 预测/期望）
- 导出 BFCL 官方格式（可用于官方评测 / 排行榜提交）

需 .env：
    python examples/ch12/ch12_bfcl_custom_evaluation.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents import SimpleAgent, HelloAgentsLLM
from hello_agents.evaluation import (
    BFCLDataset,
    BFCLEvaluator,
    FUNCTION_CALLING_SYSTEM_PROMPT,
)


def main():
    print("=" * 60)
    print("第十二章 03 —— BFCL 自定义评估流程")
    print("=" * 60)

    # 1. 数据集（本地目录 > HF > 离线兜底）
    dataset = BFCLDataset(category="simple_python")
    data = dataset.load()
    print(f"\n[1] 数据集: {len(data)} 样本（来源: {dataset.data_source}）")

    # 2. 自定义智能体（用 BFCL 官方函数调用系统提示词）
    agent = SimpleAgent(
        name="BFCL_Agent",
        llm=HelloAgentsLLM(),
        system_prompt=FUNCTION_CALLING_SYSTEM_PROMPT,
        enable_tool_calling=False,   # 评估只关心输出文本，不需要真实执行工具
    )
    print(f"[2] 智能体: {agent.name}（系统提示词已加载）")

    # 3. 评估
    evaluator = BFCLEvaluator(dataset=dataset, category="simple_python")
    results = evaluator.evaluate(agent, max_samples=3)
    print(f"[3] 评估完成: 准确率 {results['overall_accuracy']:.2%}"
          f"（{results['correct_samples']}/{results['total_samples']}）")

    # 4. 逐样本检查（方便调试智能体输出）
    print("\n[4] 逐样本结果:")
    for d in results["detailed_results"]:
        status = "✅" if d["success"] else "❌"
        print(f"  {status} #{d['sample_id']}: 预测={str(d['predicted'])[:60]}")

    # 5. 导出 BFCL 官方格式
    out = evaluator.export_to_bfcl_format(
        results, "./evaluation_results/bfcl_official/BFCL_v4_custom_result.json")
    print(f"\n[5] 已导出官方格式: {out}（可用 bfcl 命令提交官方评测）")


if __name__ == "__main__":
    main()
