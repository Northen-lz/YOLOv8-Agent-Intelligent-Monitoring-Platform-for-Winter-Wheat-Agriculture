# -*- coding: utf-8 -*-
"""
第十二章 05 —— GAIA 通用助手评估（一键快速上手）
镜像参考仓库 code/chapter12/05_gaia_quick_start.py

用 GAIAEvaluationTool 一键评估通用 AI 助手能力（准精确匹配）：
- 加载 GAIA 数据集（受限数据集，无权限自动离线兜底）
- 用 GAIA 官方系统提示词创建智能体（FINAL ANSWER: 格式）
- 准精确匹配评估 + 导出官方提交 JSONL + 提交指南 + 报告

无需传 agent（工具自动创建），小样本冒烟：
    python examples/ch12/ch12_gaia_quick_start.py

参数（可选）：
    --level 1        # 仅评估 Level 1
    --samples 2      # 样本数（None=全部）
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.tools import GAIAEvaluationTool


def main():
    parser = argparse.ArgumentParser(description="GAIA 一键评估")
    parser.add_argument("--level", type=int, default=None, help="评估级别（1/2/3，默认全部）")
    parser.add_argument("--samples", type=int, default=2, help="样本数（默认 2）")
    args = parser.parse_args()

    print("=" * 60)
    print("第十二章 05 —— GAIA 一键评估")
    print(f"Level: {args.level} | 样本数: {args.samples}")
    print("=" * 60)

    tool = GAIAEvaluationTool()
    results = tool.run(level=args.level, max_samples=args.samples)

    print("\n" + "-" * 60)
    print(f"🎯 精确匹配率: {results['exact_match_rate']:.2%}"
          f"（{results['correct_samples']}/{results['total_samples']}）")
    print(f"   部分匹配率: {results['partial_match_rate']:.2%}")
    print(f"   数据来源: {results['data_source']}")
    if results.get("report_path"):
        print(f"   报告: {results['report_path']}")

    print("\n💡 GAIA 是受限数据集：有 HF_TOKEN + 权限时自动用真实数据；")
    print("   否则用离线兜底样本演示流程。提交官方排行榜见 SUBMISSION_GUIDE.md。")


if __name__ == "__main__":
    main()
