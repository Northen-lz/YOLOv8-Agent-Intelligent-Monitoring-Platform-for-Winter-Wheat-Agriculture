# -*- coding: utf-8 -*-
"""
第十二章 04 —— BFCL 评估流水线（命令行工具）
镜像参考仓库 code/chapter12/04_bfcl_pipeline.py

完整流水线：加载数据集 → 评估 → 导出官方格式 → 复制到 result/<model>/ →
尝试 bfcl 官方评估（未安装时警告跳过）→ 生成 markdown 报告。

用法：
    python examples/ch12/ch12_bfcl_pipeline.py --category simple_python --samples 3
    python examples/ch12/ch12_bfcl_pipeline.py --category parallel --samples 5 --model-name "Qwen/Qwen3-8B"
    python examples/ch12/ch12_bfcl_pipeline.py --local-data ./my_data.json  # 自定义数据
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.tools import BFCLEvaluationTool


def main():
    parser = argparse.ArgumentParser(description="BFCL 评估流水线")
    parser.add_argument("--category", default="simple_python",
                        help="评估类别（simple_python/multiple/parallel/irrelevance）")
    parser.add_argument("--samples", type=int, default=5, help="样本数（0=全部）")
    parser.add_argument("--model-name", default="Qwen/Qwen3-8B",
                        help="模型名（用于 result/ 目录与报告）")
    parser.add_argument("--local-data", default=None, help="自定义本地 BFCL 数据文件")
    parser.add_argument("--official-eval", action="store_true",
                        help="尝试 bfcl 官方评估命令（默认跳过）")
    args = parser.parse_args()

    print("=" * 60)
    print("第十二章 04 —— BFCL 评估流水线")
    print(f"类别: {args.category} | 样本: {args.samples} | 模型: {args.model_name}")
    print("=" * 60)

    tool = BFCLEvaluationTool()
    results = tool.run(
        category=args.category,
        max_samples=args.samples,
        run_official_eval=args.official_eval,
        model_name=args.model_name,
        local_data_path=args.local_data,
    )

    print("\n" + "-" * 60)
    print(f"🎯 准确率: {results['overall_accuracy']:.2%}"
          f"（{results['correct_samples']}/{results['total_samples']}）")
    print(f"   F1: {results['f1_score']:.2%} | 错误率: {results['error_rate']:.2%}")
    print(f"   输出文件: {results['output_file']}")
    print(f"   报告: {results['report_path']}")


if __name__ == "__main__":
    main()
