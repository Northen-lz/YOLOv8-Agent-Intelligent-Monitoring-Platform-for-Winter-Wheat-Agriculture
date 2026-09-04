# -*- coding: utf-8 -*-
"""
Hello-Agents 强化学习模块（文档第十一章 Agentic-RL）
四层架构（11.1.4）：
- 数据集层     datasets   GSM8K 数学推理数据集 + 格式转换
- 奖励函数层   rewards    准确率 / 长度惩罚 / 步骤奖励 + 工厂函数
- 训练器层     trainers   SFTTrainerWrapper / GRPOTrainerWrapper（真实 TRL，惰性导入）
- 工具函数     utils      答案提取 / 比较 / 步骤检测

训练相关依赖（trl/transformers/peft/torch）均为惰性导入：
base 环境导入本模块不报错，仅实际训练 / 评估时要求依赖可用。
"""

from .datasets import (
    GSM8KDataset,
    create_rl_dataset,
    create_sft_dataset,
    format_math_dataset,
)
from .rewards import (
    AccuracyReward,
    CombinedReward,
    LengthPenaltyReward,
    MathRewardFunction,
    StepReward,
    create_accuracy_reward,
    create_combined_reward,
    create_length_penalty_reward,
    create_reward,
    create_step_reward,
)
from .trainers import (
    GRPOTrainerWrapper,
    SFTTrainerWrapper,
    evaluate_math_model,
    get_device,
)
from .utils import (
    answer_matches_any,
    compare_answers,
    extract_answer,
    extract_steps,
)

__all__ = [
    # 数据集层
    "GSM8KDataset",
    "format_math_dataset",
    "create_sft_dataset",
    "create_rl_dataset",
    # 奖励函数层
    "MathRewardFunction",
    "AccuracyReward",
    "LengthPenaltyReward",
    "StepReward",
    "CombinedReward",
    "create_accuracy_reward",
    "create_length_penalty_reward",
    "create_step_reward",
    "create_combined_reward",
    "create_reward",
    # 训练器层
    "SFTTrainerWrapper",
    "GRPOTrainerWrapper",
    "evaluate_math_model",
    # 工具函数
    "extract_answer",
    "compare_answers",
    "extract_steps",
    "answer_matches_any",
    "get_device",
]
