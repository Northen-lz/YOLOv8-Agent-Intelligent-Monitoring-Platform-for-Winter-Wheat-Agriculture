# -*- coding: utf-8 -*-
"""
第十一章 03 —— LoRA 配置说明
镜像参考仓库 code/chapter11/03_lora_configuration.py

离线可跑：展示与对比 LoRA 超参数（无需 peft/torch）。
运行：python examples/ch11/ch11_lora_configuration.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# LoRA 超参配置（对齐文档 11.3.3 表 11.3）
CONFIGS = {
    "轻量档（快速冒烟）": {
        "r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "target_modules": ["q_proj", "v_proj"],
        "bias": "none",
        "task_type": "CAUSAL_LM",
        "说明": "参数少、训练快，适合 2GB 显存验证流程",
    },
    "标准档（推荐）": {
        "r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.1,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "bias": "none",
        "task_type": "CAUSAL_LM",
        "说明": "覆盖全部注意力投影，效果更稳（文档 11.3.3 默认）",
    },
    "强档（追求效果）": {
        "r": 32,
        "lora_alpha": 64,
        "lora_dropout": 0.1,
        "target_modules": [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        "bias": "none",
        "task_type": "CAUSAL_LM",
        "说明": "全模块注入，效果上限高，显存占用大",
    },
}


def _est_trainable(model_params=6e8, r=8, n_modules=2):
    """粗估可训练参数量：每条 LoRA 通路 ≈ r×2 个矩阵"""
    return round(r * 2 * model_params * n_modules / 1e6, 1)


def main():
    print("=" * 60)
    print("第十一章 03 —— LoRA 配置说明")
    print("=" * 60)
    print("\nLoRA 关键超参（文档 11.3.3）：")
    print("  - r:          低秩维度（LoRA 秩），越大表达能力越强、参数量越大")
    print("  - lora_alpha: 缩放系数（lora_alpha / r），控制更新幅度")
    print("  - dropout:    防止过拟合")
    print("  - target_modules: 注入 LoRA 的目标模块")

    print("\n三档配置对比（以 Qwen3-0.6B 为例）:")
    print(f"{'配置':<22}{'r':<5}{'alpha':<8}{'估计可训练参数量':<18}")
    print("-" * 60)
    for name, cfg in CONFIGS.items():
        est = _est_trainable(
            r=cfg["r"],
            n_modules=len(cfg["target_modules"]),
        )
        print(f"{name:<20}{cfg['r']:<5}{cfg['lora_alpha']:<8}{est:<18}M")
    print()
    for name, cfg in CONFIGS.items():
        print(f"\n[{name}] {cfg['说明']}")
        print(json.dumps(
            {k: v for k, v in cfg.items() if k != "说明"},
            ensure_ascii=False, indent=2))

    print("\n✅ LoRA 配置说明完成")


if __name__ == "__main__":
    main()
