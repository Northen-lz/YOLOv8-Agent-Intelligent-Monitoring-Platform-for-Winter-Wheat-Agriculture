# -*- coding: utf-8 -*-
"""
第十一章 00 —— 快速训练冒烟测试
镜像参考仓库 code/chapter11/00_quick_test.py

10 样本 SFT + 5 样本 GRPO + 评估，用 2GB 显存快速验证全流程。
需训练环境 env_rl：
    conda run -n env_rl python examples/ch11/ch11_quick_test.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import torch
    import trl  # noqa: F401
except ImportError as e:
    print("❌ 缺少训练依赖。请在 env_rl 环境运行：")
    print("   conda run -n env_rl python examples/ch11/ch11_quick_test.py")
    sys.exit(1)

from hello_agents.tools import RLTrainingTool


def main():
    print("=" * 60)
    print("第十一章 00 —— 快速训练冒烟测试")
    print("=" * 60)

    tool = RLTrainingTool()
    print(f"\n[0] 设备: {tool.device}")

    # 1. SFT 冒烟（10 样本）
    print("\n[1] SFT 冒烟训练（10 样本）...")
    r = json.loads(tool.run({
        "action": "load_dataset", "format": "sft", "split": "train",
        "max_samples": 10,
    }))
    print(f"    数据集: {r['dataset_size']} 样本")
    r = json.loads(tool.run({
        "action": "train", "algorithm": "sft",
        "model_name": "Qwen/Qwen3-0.6B", "output_dir": "./models/ch11_sft_model",
        "max_samples": 10, "num_epochs": 1, "batch_size": 1,
        "learning_rate": 5e-5, "use_lora": True,
        "lora_r": 8, "lora_alpha": 16, "max_length": 512,
    }))
    print(f"    SFT: status={r['status']}, loss={r.get('final_loss')}")

    # 2. GRPO 冒烟（5 样本）
    print("\n[2] GRPO 冒烟训练（5 样本）...")
    r = json.loads(tool.run({
        "action": "load_dataset", "format": "rl", "split": "train",
        "max_samples": 5,
    }))
    r = json.loads(tool.run({
        "action": "train", "algorithm": "grpo",
        "model_name": "Qwen/Qwen3-0.6B", "output_dir": "./models/ch11_grpo_model",
        "max_samples": 5, "num_epochs": 1, "batch_size": 1,
        "learning_rate": 1e-5, "use_lora": True,
        "lora_r": 8, "lora_alpha": 16, "max_length": 512,
        "num_generations": 2, "max_new_tokens": 128,
        "temperature": 0.8, "kl_coef": 0.05, "clip_range": 0.2,
        "reward_type": "accuracy",
    }))
    print(f"    GRPO: status={r['status']}, avg_reward={r.get('average_reward')}")

    # 3. 评估冒烟
    print("\n[3] 评估冒烟（10 样本）...")
    r = json.loads(tool.run({
        "action": "evaluate", "model_path": "./models/ch11_sft_model",
        "max_samples": 10, "use_lora": True, "return_details": True,
    }))
    print(f"    评估: accuracy={r['accuracy']}, avg_reward={r['average_reward']}")

    print("\n✅ 快速冒烟测试全部完成")


if __name__ == "__main__":
    main()
