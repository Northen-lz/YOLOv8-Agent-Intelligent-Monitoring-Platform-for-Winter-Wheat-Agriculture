# -*- coding: utf-8 -*-
"""
第十一章 06 —— 端到端强化学习流水线
镜像参考仓库 code/chapter11/06_complete_pipeline.py

由 config.json 驱动：加载数据集 → 创建奖励 → 训练（SFT/GRPO）→ 评估。
需训练环境 env_rl：
    conda run -n env_rl python examples/ch11/ch11_complete_pipeline.py
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
    print("   conda run -n env_rl python examples/ch11/ch11_complete_pipeline.py")
    sys.exit(1)

from hello_agents.tools import RLTrainingTool


def main():
    print("=" * 60)
    print("第十一章 06 —— 端到端强化学习流水线")
    print("=" * 60)

    # 读取配置文件
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"\n[0] 配置: {cfg['algorithm']} / {cfg['model_name']}")

    tool = RLTrainingTool()
    print(f"    设备: {tool.device}")

    # 1. 加载数据集
    r = json.loads(tool.run({
        "action": "load_dataset",
        "format": cfg["format"],
        "split": cfg["split"],
        "max_samples": cfg["max_samples"],
        "model_name": cfg["model_name"],
    }))
    print(f"\n[1] 数据集: {r['dataset_size']} 样本, keys={r['sample_keys']}")

    # 2. 创建奖励函数
    r = json.loads(tool.run({
        "action": "create_reward",
        "reward_type": cfg["reward_type"],
        **cfg.get("reward_config", {}),
    }))
    print(f"\n[2] 奖励函数: {r['reward_type']}, demo={r['demo_rewards']}")

    # 3. 训练
    r = json.loads(tool.run({
        "action": "train",
        "algorithm": cfg["algorithm"],
        "model_name": cfg["model_name"],
        "output_dir": cfg["output_dir"],
        "max_samples": cfg["max_samples"],
        "num_epochs": cfg["num_epochs"],
        "batch_size": cfg["batch_size"],
        "learning_rate": cfg["learning_rate"],
        "use_lora": cfg["use_lora"],
        "lora_r": cfg["lora_r"],
        "lora_alpha": cfg["lora_alpha"],
        "max_length": cfg["max_length"],
        "num_generations": cfg.get("num_generations", 4),
        "max_new_tokens": cfg.get("max_new_tokens", 128),
        "temperature": cfg.get("temperature", 0.8),
        "kl_coef": cfg.get("kl_coef", 0.05),
        "clip_range": cfg.get("clip_range", 0.2),
        "reward_type": cfg["reward_type"],
        "reward_config": cfg.get("reward_config"),
    }))
    print(f"\n[3] 训练结果: {r}")

    # 4. 评估
    eval_cfg = cfg.get("evaluate", {})
    r = json.loads(tool.run({
        "action": "evaluate",
        "model_path": cfg["output_dir"],
        "max_samples": eval_cfg.get("max_samples", 20),
        "use_lora": eval_cfg.get("use_lora", True),
        "return_details": False,
    }))
    print(f"\n[4] 评估结果: {r}")

    print("\n✅ 端到端流水线完成")


if __name__ == "__main__":
    main()
