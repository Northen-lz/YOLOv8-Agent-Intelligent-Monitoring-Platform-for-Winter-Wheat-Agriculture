# -*- coding: utf-8 -*-
"""
第十二章 02 —— BFCL 工具调用评估（一键快速上手）
镜像参考仓库 code/chapter12/02_bfcl_quick_start.py

用 BFCLEvaluationTool 一键评估：加载数据集 → 创建带函数调用提示词的智能体 →
AST 匹配评估 → 导出 BFCL 官方格式 → 生成 markdown 报告。

无需传 agent（工具自动用默认 LLM 创建），小样本冒烟：
    python examples/ch12/ch12_bfcl_quick_start.py

参数（可选）：
    --category simple_python|multiple|parallel|irrelevance
    --samples 3
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.tools import BFCLEvaluationTool


def main():
    parser = argparse.ArgumentParser(description="BFCL 一键评估")
    parser.add_argument("--category", default="simple_python",
                        help="评估类别（simple_python/multiple/parallel/irrelevance）")
    parser.add_argument("--samples", type=int, default=3, help="样本数（0=全部）")
    args = parser.parse_args()

    print("=" * 60)
    print("第十二章 02 —— BFCL 一键评估")
    print(f"类别: {args.category} | 样本数: {args.samples}")
    print("=" * 60)

    tool = BFCLEvaluationTool()
    results = tool.run(
        category=args.category,
        max_samples=args.samples,
        run_official_eval=False,      # 冒烟跳过 bfcl 官方评估
        model_name="Qwen/Qwen3-8B",
    )

    print("\n" + "-" * 60)
    print(f"🎯 总体准确率: {results['overall_accuracy']:.2%}"
          f"（{results['correct_samples']}/{results['total_samples']}）")
    print(f"   AST 匹配率: {results['ast_match_rate']:.2%}")
    print(f"   参数准确率: {results['parameter_accuracy']:.2%}")
    print(f"   数据来源: {results['data_source']}")
    if results.get("report_path"):
        print(f"   报告: {results['report_path']}")

    print("\n💡 说明：这里用离线兜底样本演示流程。接入真实 BFCL 数据可传")
    print("   local_data_path=... 或配置 bfcl_eval 目录（见 ch12_bfcl_custom_evaluation.py）。")


if __name__ == "__main__":
    main()
