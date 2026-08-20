# -*- coding: utf-8 -*-
"""
第十一章 07 —— 模型评估与对比
镜像参考仓库 code/chapter11/07_model_evaluation.py

评估基线模型，并对比 SFT / GRPO 微调产物（文档 11.5 评估指标体系）。
需训练环境 env_rl：
    conda run -n env_rl python examples/ch11/ch11_model_evaluation.py
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
    print("   conda run -n env_rl python examples/ch11/ch11_model_evaluation.py")
    sys.exit(1)

from hello_agents.tools import RLTrainingTool

# 候选模型目录（按需修改；缺失的会自动跳过）
MODELS = [
    {"label": "基线", "path": "Qwen/Qwen3-0.6B", "use_lora": False},
    {"label": "SFT", "path": "./models/ch11_sft_model", "use_lora": True},
    {"label": "GRPO", "path": "./models/ch11_grpo_model", "use_lora": True},
]


def main():
    print("=" * 60)
    print("第十一章 07 —— 模型评估与对比")
    print("=" * 60)

    tool = RLTrainingTool()
    print(f"\n[0] 设备: {tool.device}")

    rows = []
    for m in MODELS:
        path = m["path"]
        if not os.path.exists(path) and not path.startswith(("Qwen/", "http")):
            print(f"\n- 跳过 {m['label']}: 模型目录不存在 {path}")
            continue
        print(f"\n[{m['label']}] {path} ...")
        try:
            r = json.loads(tool.run({
                "action": "evaluate",
                "model_path": path,
                "max_samples": 10,
                "use_lora": m["use_lora"],
                "return_details": True,
            }))
            rows.append((m["label"], r))
            print(f"   accuracy={r['accuracy']}, avg_reward={r['average_reward']}, "
                  f"avg_steps={r['average_steps']}, format={r['format_correctness']}")
        except Exception as e:
            print(f"   评估失败: {e}")

    if rows:
        print("\n" + "=" * 60)
        print("对比总结:")
        print(f"{'模型':<8}{'accuracy':<12}{'avg_reward':<14}{'avg_steps':<12}{'format'}")
        for label, r in rows:
            print(f"{label:<8}{r['accuracy']:<12}{r['average_reward']:<14}"
                  f"{r['average_steps']:<12}{r['format_correctness']}")

    print("\n✅ 模型评估完成")


if __name__ == "__main__":
    main()
