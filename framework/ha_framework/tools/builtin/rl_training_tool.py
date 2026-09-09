# -*- coding: utf-8 -*-
"""
Hello-Agents 强化学习训练工具（RLTrainingTool）
「端到端流水线」统一接口层

设计（"统一入口，分发处理"）：
- run({"action": ..., ...}) 传入字典参数，返回 JSON 字符串（对齐参考示例）
- 支持操作：load_dataset / create_reward / train / evaluate
- 额外：register_dataset(name, dataset) / register_reward_function(name, fn)
        （文档 11.2.3 自定义数据集 / 奖励函数注册使用）

训练 / 评估内部惰性导入（trl/transformers/peft），
设备自动选择：有 GPU（cuda）→ CPU（降级可用）。
"""

import json
from typing import Any, Dict, List, Optional

from ..base import BaseTool
from ...rl import create_reward, get_device


class RLTrainingTool(BaseTool):
    """强化学习训练工具 - 数据集加载、奖励设计、SFT/GRPO 训练与评估"""

    def __init__(self, name: str = "rl_training", description: str = ""):
        if not description:
            description = (
                "强化学习训练工具 - 加载数据集、创建奖励函数、"
                "执行 SFT/GRPO 训练与模型评估（Agentic-RL）"
            )
        super().__init__(name=name, description=description)

        # 注册表（文档 11.2.3）
        self._datasets: Dict[str, Any] = {}
        self._reward_functions: Dict[str, Any] = {}
        # 最近加载的数据集（供 train 缺省使用）
        self._loaded_dataset: Optional[Any] = None
        self.device = get_device()

    # ================================================================
    # 统一入口
    # ================================================================

    def execute(self, action: str = "load_dataset", **kwargs) -> str:
        """执行 RL 操作，返回 JSON 字符串"""
        handlers = {
            "load_dataset": self._load_dataset,
            "create_reward": self._create_reward,
            "train": self._train,
            "evaluate": self._evaluate,
            "register_dataset": self._register_dataset,
            "register_reward_function": self._register_reward_function,
            "list_registrations": self._list_registrations,
            "device": self._device_info,
        }
        handler = handlers.get((action or "").strip().lower())
        if handler is None:
            result = {
                "status": "error",
                "message": f"不支持的操作: {action}"
                           f"（可选: {', '.join(handlers)}）",
            }
            return self._to_json(result)
        try:
            result = handler(**kwargs)
            return self._to_json(result)
        except Exception as e:
            return self._to_json({"status": "error", "message": str(e)})

    # 兼容 BaseTool.run（参考示例：run({"action": "load_dataset", ...})）
    def run(self, *args, **kwargs) -> str:
        if kwargs:
            return self.execute(**kwargs)
        if args and isinstance(args[0], dict):
            return self.execute(**args[0])
        return self.execute("device")

    # ================================================================
    # 操作 1：load_dataset
    # ================================================================

    def _load_dataset(
            self,
            format: str = "rl",
            split: str = "train",
            max_samples: Optional[int] = None,
            model_name: Optional[str] = None,
            dataset: Optional[Any] = None,
            register_name: Optional[str] = None,
            **kwargs,
    ) -> Dict[str, Any]:
        """
        加载数据集并转换为训练格式（文档 11.2）。

        Args:
            format: sft | rl
            split: train | test
            max_samples: 限制样本数
            model_name: 对话模板所用模型名
            dataset: 自定义 {question, answer} 数据集（None 时加载 GSM8K）
        """
        from ...rl import create_rl_dataset, create_sft_dataset

        format = (format or "rl").lower()
        if dataset is not None:
            if format == "sft":
                data = create_sft_dataset(dataset=dataset, model_name=model_name)
            else:
                data = create_rl_dataset(dataset=dataset, model_name=model_name)
        else:
            if format == "sft":
                data = create_sft_dataset(
                    split=split, max_samples=max_samples, model_name=model_name)
            else:
                data = create_rl_dataset(
                    split=split, max_samples=max_samples, model_name=model_name)

        # 保存供后续 train 使用
        rows = list(data)
        name = register_name or "default"
        self._datasets[name] = data
        self._loaded_dataset = data

        keys = list(rows[0].keys()) if rows else []
        result = {
            "status": "success",
            "dataset_size": len(rows),
            "sample_keys": keys,
            "format": format,
            "split": split,
        }
        if rows:
            result["sample"] = rows[0]
        if self.device != "cuda":
            result["note"] = "离线兜底数据或 CPU 模式（未检测到 GPU）"
        return result

    # ================================================================
    # 操作 2：create_reward
    # ================================================================

    def _create_reward(
            self,
            reward_type: str = "accuracy",
            tolerance: float = 1e-4,
            penalty_weight: float = 0.001,
            target_length: int = 200,
            max_length: int = 512,
            step_bonus: float = 0.1,
            max_steps: int = 10,
            components: Optional[List[Dict[str, Any]]] = None,
            register_name: Optional[str] = None,
            **kwargs,
    ) -> Dict[str, Any]:
        """
        创建奖励函数（文档 11.2.2）。

        Args:
            reward_type: accuracy | length_penalty | step | combined
            components: combined 类型的组件配置列表
        """
        reward_type = (reward_type or "accuracy").lower()
        if reward_type == "combined" and not components:
            # 默认组合：准确率 + 长度惩罚 + 步骤奖励（文档 11.2.2 三者平衡）
            components = self._default_combined_components(
                penalty_weight=penalty_weight, target_length=target_length,
                step_bonus=step_bonus, max_steps=max_steps,
            )
        if reward_type == "combined":
            fn = create_reward("combined", components=components,
                               tolerance=tolerance)
            config = {"components": components}
        else:
            # 只传该类型工厂接受的参数
            rw_kwargs = dict(tolerance=tolerance)
            if reward_type == "length_penalty":
                rw_kwargs.update(
                    penalty_weight=penalty_weight,
                    target_length=target_length,
                    max_length=max_length,
                )
            elif reward_type == "step":
                rw_kwargs.update(step_bonus=step_bonus, max_steps=max_steps)
            fn = create_reward(reward_type, **rw_kwargs)
            config = {
                "penalty_weight": penalty_weight,
                "target_length": target_length,
                "max_length": max_length,
                "step_bonus": step_bonus,
                "max_steps": max_steps,
            }

        name = register_name or f"reward_{reward_type}"
        self._reward_functions[name] = fn

        # 试算演示（文档 11.2.2 使用示例）
        demo = fn(completions=[
            "Step 1: 48/2 = 24. Step 2: 48+24 = 72. Final Answer: 72",
            "I think the answer is 99.",
        ], ground_truth=["72", "72"])

        return {
            "status": "success",
            "reward_type": reward_type,
            "description": str(fn),
            "config": config,
            "registered_name": name,
            "demo_rewards": demo,
        }

    # ================================================================
    # 操作 3：train
    # ================================================================

    def _train(
            self,
            algorithm: str = "sft",
            model_name: str = "Qwen/Qwen3-0.6B",
            output_dir: str = "./models/rl_output",
            dataset: Optional[Any] = None,
            dataset_name: Optional[str] = None,
            split: str = "train",
            max_samples: Optional[int] = None,
            num_epochs: int = 1,
            batch_size: int = 2,
            learning_rate: float = 5e-5,
            use_lora: bool = True,
            lora_r: Optional[int] = None,
            lora_rank: Optional[int] = None,
            lora_alpha: int = 16,
            max_length: int = 512,
            # GRPO 专属参数
            num_generations: int = 4,
            max_new_tokens: int = 256,
            temperature: float = 0.8,
            kl_coef: float = 0.05,
            clip_range: float = 0.2,
            # 奖励
            reward_type: str = "accuracy",
            reward_config: Optional[Dict[str, Any]] = None,
            custom_reward: Optional[Any] = None,
            use_wandb: bool = False,
            use_tensorboard: bool = False,
            **kwargs,
    ) -> Dict[str, Any]:
        """
        执行 SFT / GRPO 训练（文档 11.3 / 11.4）。

        Args:
            algorithm: sft | grpo
            dataset: 已转换的数据集（None 时用注册表或加载 GSM8K）
            custom_reward: 已注册奖励函数名 或 可直接调用的奖励函数
        """
        algorithm = (algorithm or "sft").lower()

        # 1. 准备数据集
        train_data = self._resolve_dataset(
            dataset=dataset, dataset_name=dataset_name,
            split=split, max_samples=max_samples,
            format="sft" if algorithm == "sft" else "rl",
        )

        # 2. 准备奖励函数（仅 GRPO 需要）
        reward_fn = None
        if algorithm == "grpo":
            reward_fn = self._resolve_reward(
                custom_reward=custom_reward,
                reward_type=reward_type,
                reward_config=reward_config,
            )

        # 3. 执行训练
        common = dict(
            dataset=train_data,
            model_name=model_name,
            output_dir=output_dir,
            num_epochs=num_epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            use_lora=use_lora,
            lora_r=lora_r,
            lora_rank=lora_rank,
            lora_alpha=lora_alpha,
            max_length=max_length,
        )
        if algorithm == "sft":
            from ...rl import SFTTrainerWrapper
            result = SFTTrainerWrapper().train(**common)
        elif algorithm == "grpo":
            from ...rl import GRPOTrainerWrapper
            result = GRPOTrainerWrapper().train(
                **common,
                num_generations=num_generations,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                kl_coef=kl_coef,
                clip_range=clip_range,
                reward_fn=reward_fn,
                reward_type=reward_type,
            )
        else:
            raise ValueError(f"未知算法: {algorithm}（可选: sft / grpo）")

        result["status"] = "completed"
        return result

    # ================================================================
    # 操作 4：evaluate
    # ================================================================

    def _evaluate(
            self,
            model_path: str,
            dataset: Optional[Any] = None,
            max_samples: int = 50,
            use_lora: bool = False,
            metrics: Optional[List[str]] = None,
            k: int = 3,
            return_details: bool = False,
            max_new_tokens: int = 256,
            **kwargs,
    ) -> Dict[str, Any]:
        """评估模型（文档 11.5 评估指标体系）"""
        from ...rl import evaluate_math_model
        return evaluate_math_model(
            model_path=model_path,
            dataset=dataset,
            max_samples=max_samples,
            use_lora=use_lora,
            metrics=metrics,
            k=k,
            return_details=return_details,
            max_new_tokens=max_new_tokens,
        )

    # ================================================================
    # 注册操作（文档 11.2.3）
    # ================================================================

    def _register_dataset(self, name: str, dataset: Any, **kwargs) -> Dict[str, Any]:
        """注册自定义数据集"""
        if not name:
            raise ValueError("注册数据集必须指定 name")
        self._datasets[name] = dataset
        try:
            rows = list(dataset)
        except TypeError:
            rows = []
        keys = list(rows[0].keys()) if rows else []
        return {"status": "success", "registered_dataset": name, "keys": keys}

    def _register_reward_function(self, name: str, fn: Any, **kwargs) -> Dict[str, Any]:
        """注册自定义奖励函数"""
        if not name:
            raise ValueError("注册奖励函数必须指定 name")
        if not callable(fn):
            raise ValueError("注册的奖励函数必须是可调用对象")
        self._reward_functions[name] = fn
        return {"status": "success", "registered_reward": name,
                "type": type(fn).__name__}

    def _list_registrations(self, **kwargs) -> Dict[str, Any]:
        """列出已注册的数据集与奖励函数"""
        return {
            "status": "success",
            "datasets": list(self._datasets.keys()),
            "reward_functions": list(self._reward_functions.keys()),
            "loaded_dataset": (self._loaded_dataset is not None),
        }

    def _device_info(self, **kwargs) -> Dict[str, Any]:
        """查询训练设备"""
        return {"status": "success", "device": self.device,
                "note": "CUDA 可用" if self.device == "cuda" else "CPU 模式"}

    # ================================================================
    # 内部辅助
    # ================================================================

    def _resolve_dataset(self, dataset, dataset_name, split,
                         max_samples, format: str):
        """解析训练数据集：显式 dataset > 注册名 > 最近加载 > 加载 GSM8K"""
        if dataset is not None:
            return self._slice(dataset, max_samples)
        if dataset_name and dataset_name in self._datasets:
            return self._slice(self._datasets[dataset_name], max_samples)
        if self._loaded_dataset is not None:
            return self._slice(self._loaded_dataset, max_samples)

        # 兜底：加载 GSM8K
        from ...rl import create_rl_dataset, create_sft_dataset
        if format == "sft":
            data = create_sft_dataset(split=split, max_samples=max_samples)
        else:
            data = create_rl_dataset(split=split, max_samples=max_samples)
        return data

    @staticmethod
    def _slice(dataset, max_samples):
        """截取前 max_samples 个样本（对 iterable 数据集安全）

        SimpleAgent 解析出的 max_samples 可能是字符串（如 "50"/"全部"），
        先做数值强转；非数值或 ≤0 视为不限制。
        """
        if max_samples is None:
            return dataset
        try:
            n = int(max_samples)
        except (TypeError, ValueError):
            return dataset
        if n <= 0:
            return dataset
        return list(dataset)[:n]

    def _resolve_reward(self, custom_reward, reward_type,
                        reward_config: Optional[Dict[str, Any]]):
        """解析奖励函数：自定义 > 注册名 > 内置类型"""
        if custom_reward is not None:
            if isinstance(custom_reward, str) and custom_reward in self._reward_functions:
                return self._reward_functions[custom_reward]
            if callable(custom_reward):
                return custom_reward
            raise ValueError(f"自定义奖励不可用: {custom_reward}")
        reward_type = (reward_type or "accuracy").lower()
        cfg = dict(reward_config or {})
        if reward_type == "combined" and "components" not in cfg:
            # 对齐 _create_reward 的默认组合，避免缺 components 崩溃
            cfg["components"] = self._default_combined_components()
        return create_reward(reward_type, **cfg)

    @staticmethod
    def _default_combined_components(penalty_weight=0.001, target_length=200,
                                     step_bonus=0.1, max_steps=10):
        """combined 奖励的默认组件（准确率 + 长度惩罚 + 步骤奖励）"""
        return [
            {"type": "accuracy", "weight": 1.0},
            {"type": "length_penalty", "weight": 0.5,
             "penalty_weight": penalty_weight, "target_length": target_length},
            {"type": "step", "weight": 0.3,
             "step_bonus": step_bonus, "max_steps": max_steps},
        ]

    @staticmethod
    def _to_json(obj: Dict[str, Any]) -> str:
        """转 JSON 字符串（对齐参考示例返回结构）"""
        return json.dumps(obj, ensure_ascii=False, default=str)


if __name__ == "__main__":
    # 简单自测（离线，无需训练依赖）
    tool = RLTrainingTool()
    print(tool.run({"action": "device"}))
    print(tool.run({"action": "load_dataset", "format": "rl",
                    "split": "train", "max_samples": 5}))
    print(tool.run({"action": "create_reward", "reward_type": "combined"}))
