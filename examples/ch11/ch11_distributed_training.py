# -*- coding: utf-8 -*-
"""
第十一章 08 —— 分布式训练配置说明
镜像参考仓库 code/chapter11/08_distributed_training.py

本机为单卡（MX570 2GB），仅展示 accelerate 分布式配置（讲解用，不实际训练）。
需训练环境 env_rl（仅导入依赖做校验）：
    conda run -n env_rl python examples/ch11/ch11_distributed_training.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

ACCELERATE_CONFIGS = {
    "ddp.yaml": (
        "DistributedDataParallel 多卡数据并行\n"
        "  compute_environment: LOCAL_MACHINE\n"
        "  distributed_type: MULTI_GPU\n"
        "  num_machines: 1\n"
        "  num_processes: 4          # 使用的 GPU 数\n"
        "  mixed_precision: bf16\n"
    ),
    "zero2.yaml": (
        "DeepSpeed ZeRO-2：优化器状态分片\n"
        "  compute_environment: LOCAL_MACHINE\n"
        "  distributed_type: DEEPSPEED\n"
        "  num_processes: 4\n"
        "  mixed_precision: bf16\n"
        "  deepspeed_config:\n"
        "    zero_stage: 2\n"
        "    offload_optimizer_device: cpu\n"
    ),
    "zero3.yaml": (
        "DeepSpeed ZeRO-3：全参数分片（最大显存节省）\n"
        "  compute_environment: LOCAL_MACHINE\n"
        "  distributed_type: DEEPSPEED\n"
        "  num_processes: 4\n"
        "  mixed_precision: bf16\n"
        "  deepspeed_config:\n"
        "    zero_stage: 3\n"
        "    offload_optimizer_device: cpu\n"
        "    offload_param_device: cpu\n"
    ),
}


def main():
    print("=" * 60)
    print("第十一章 08 —— 分布式训练配置说明")
    print("=" * 60)

    print("\n[1] 本机 GPU 信息:")
    try:
        import torch
        print(f"  torch: {torch.__version__}")
        print(f"  CUDA 可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  GPU: {torch.cuda.get_device_name(0)}")
            print(f"  显存: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    except ImportError:
        print("  torch 未安装（请在 env_rl 环境运行）")

    print("\n[2] accelerate 配置（写入 examples/ch11/accelerate_configs/）:")
    for name, content in ACCELERATE_CONFIGS.items():
        print(f"\n--- {name} ---")
        print(content)

    print("\n[3] 使用方式:")
    print("  accelerate launch --config_file accelerate_configs/ddp.yaml \\")
    print("      examples/ch11/ch11_grpo_training.py")

    print("\n✅ 分布式配置说明完成（本机单卡无需实际分布式训练）")


if __name__ == "__main__":
    main()
