# -*- coding: utf-8 -*-
"""
第十一章 01 —— GSM8K 数据集加载与格式转换
镜像参考仓库 code/chapter11/01_dataset_loading.py

离线可用：datasets 库或网络不可用时自动回退内置微型样本。
运行：python examples/ch11/ch11_dataset_loading.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents.rl import GSM8KDataset, create_rl_dataset, create_sft_dataset


def main():
    print("=" * 60)
    print("第十一章 01 —— GSM8K 数学推理数据集加载")
    print("=" * 60)

    # 1. 加载原始数据（question / answer）
    ds = GSM8KDataset().load("train", max_samples=20)
    src = "HuggingFace 真实数据" if not ds.used_fallback else "内置兜底样本（离线）"
    print(f"\n[1] 原始数据: {len(ds)} 样本（来源: {src}）")

    # 2. SFT 格式 {prompt, completion, text}
    sft = create_sft_dataset(split="train", max_samples=5)
    row = list(sft)[0]
    print("\n[2] SFT 格式:")
    print(f"  keys: {list(row.keys())}")
    print(f"  prompt     : {row['prompt'][:70]}...")
    print(f"  completion : {row['completion'][:70]}...")

    # 3. RL 格式 {prompt, ground_truth, question, full_answer}
    rl = create_rl_dataset(split="test", max_samples=5)
    row = list(rl)[0]
    print("\n[3] RL 格式:")
    print(f"  keys: {list(row.keys())}")
    print(f"  ground_truth: {row['ground_truth']}")
    print(f"  prompt      : {row['prompt'][:70]}...")

    # 4. 统计
    print("\n[4] 统计:")
    for name, d in [("SFT", list(sft)), ("RL", list(rl))]:
        print(f"  {name}: {len(d)} 样本")

    print("\n✅ 数据集加载完成")


if __name__ == "__main__":
    main()
