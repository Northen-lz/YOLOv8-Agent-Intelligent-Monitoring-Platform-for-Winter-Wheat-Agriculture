# -*- coding: utf-8 -*-
"""
第十一章 04 —— SFT 监督微调训练
镜像参考仓库 code/chapter11/04_sft_training.py

需训练环境 env_rl（Python 3.11 + CUDA torch + trl/peft/transformers）：
    conda run -n env_rl python examples/ch11/ch11_sft_training.py

首次运行会自动下载 Qwen/Qwen3-0.6B（约 1.2GB）。
2GB 显存：bf16 + LoRA 轻量档 + 小样本即可跑通。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 训练依赖检查（给出友好提示）
try:
    import torch
    import trl  # noqa: F401
except ImportError as e:
    print("❌ 缺少训练依赖。请在 env_rl 环境运行：")
    print("   conda run -n env_rl python examples/ch11/ch11_sft_training.py")
    sys.exit(1)

from hello_agents.tools import RLTrainingTool


def main():
    print("=" * 60)
    print("第十一章 04 —— SFT 监督微调训练")
    print("=" * 60)

    tool = RLTrainingTool()
    print(f"\n[0] 训练设备: {tool.device}")
    if tool.device != "cuda":
        print("    ⚠️ 当前为 CPU 模式，训练会非常慢")

    # 1. 加载 SFT 数据集（GSM8K 训练集，小样本）
    r = tool.run({
        "action": "load_dataset",
        "format": "sft",
        "split": "train",
        "max_samples": 10,
    })
    print(f"\n[1] 加载数据集: {r}")

    # 2. SFT 训练
    r = tool.run({
        "action": "train",
        "algorithm": "sft",
        "model_name": "Qwen/Qwen3-0.6B",
        "output_dir": "./models/ch11_sft_model",
        "max_samples": 10,
        "num_epochs": 1,
        "batch_size": 2,
        "learning_rate": 5e-5,
        "use_lora": True,
        "lora_r": 8,
        "lora_alpha": 16,
        "max_length": 512,
    })
    print(f"\n[2] SFT 训练结果: {r}")

    print("\n✅ SFT 训练完成")


if __name__ == "__main__":
    main()
