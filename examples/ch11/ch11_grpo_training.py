# -*- coding: utf-8 -*-
"""
第十一章 05 —— GRPO 强化学习训练
镜像参考仓库 code/chapter11/05_grpo_training.py

需训练环境 env_rl：
    conda run -n env_rl python examples/ch11/ch11_grpo_training.py

GRPO 核心（文档 11.4）：
- 每个问题生成 num_generations 个答案（组）
- 组内相对奖励 r_i - r̄ 减少方差
- KL 散度惩罚（beta）防止偏离参考模型
2GB 显存优化：policy 上 GPU（bf16），reference 模型放 CPU。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import torch
    import trl  # noqa: F401
except ImportError as e:
    print("❌ 缺少训练依赖。请在 env_rl 环境运行：")
    print("   conda run -n env_rl python examples/ch11/ch11_grpo_training.py")
    sys.exit(1)

from hello_agents.tools import RLTrainingTool


def main():
    print("=" * 60)
    print("第十一章 05 —— GRPO 强化学习训练")
    print("=" * 60)

    tool = RLTrainingTool()
    print(f"\n[0] 训练设备: {tool.device}")

    # 1. 加载 RL 数据集
    r = tool.run({
        "action": "load_dataset",
        "format": "rl",
        "split": "train",
        "max_samples": 5,
    })
    print(f"\n[1] 加载数据集: {r}")

    # 2. 创建组合奖励（准确率 + 长度惩罚 + 步骤）
    r = tool.run({"action": "create_reward", "reward_type": "combined"})
    print(f"\n[2] 奖励函数: {r}")

    # 3. GRPO 训练
    r = tool.run({
        "action": "train",
        "algorithm": "grpo",
        "model_name": "Qwen/Qwen3-0.6B",
        "output_dir": "./models/ch11_grpo_model",
        "max_samples": 5,
        "num_epochs": 1,
        "batch_size": 1,
        "learning_rate": 1e-5,
        "use_lora": True,
        "lora_r": 8,
        "lora_alpha": 16,
        "num_generations": 4,
        "max_new_tokens": 128,
        "temperature": 0.8,
        "kl_coef": 0.05,
        "clip_range": 0.2,
        "max_length": 512,
        "reward_type": "accuracy",
    })
    print(f"\n[3] GRPO 训练结果: {r}")

    print("\n✅ GRPO 训练完成")


if __name__ == "__main__":
    main()
