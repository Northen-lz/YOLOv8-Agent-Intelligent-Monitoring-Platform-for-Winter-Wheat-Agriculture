# -*- coding: utf-8 -*-
"""
Hello-Agents 训练器层
对齐文档第十一章 11.1.4「训练器层」+ 11.3/11.4 SFT 与 GRPO 训练

基于 TRL + PEFT + Accelerate 的真实训练（文档技术选型）：
- SFTTrainerWrapper:  监督微调（trl.SFTTrainer + SFTConfig + peft LoRA）
- GRPOTrainerWrapper: 群组相对策略优化（trl.GRPOTrainer，PEFT 时 ref 模型
  通过禁用 adapter 对照基础模型计算 KL，零额外显存——适配 2GB 显卡）

兼容 trl 1.9.x API（processing_class / SFTConfig max_length / GRPOConfig
max_completion_length），并保留对旧版 trl（tokenizer= / ref_model=）的降级。

所有重型依赖（trl / transformers / peft / torch）均为惰性导入：
base 环境（CPU torch / 无 trl）导入本模块不报错，仅实际训练 / 评估时要求依赖可用。
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_device() -> str:
    """自动选择设备：有 GPU 用 cuda，否则 cpu"""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def get_torch_dtype(device: str):
    """按设备选择 dtype：GPU 用 bf16（Ampere+ 支持），CPU 用 fp32"""
    try:
        import torch
        if device == "cuda" and torch.cuda.is_available():
            if torch.cuda.get_device_capability(0)[0] >= 8:
                return torch.bfloat16
            return torch.float16
    except Exception:
        pass
    return None  # 默认 fp32


def _dtype_kwargs(dtype):
    """按 transformers 版本选择 dtype 参数名（>=4.57 用 dtype，旧版 torch_dtype）"""
    if dtype is None:
        return {}
    try:
        import transformers
        from packaging import version
        if version.parse(transformers.__version__) >= version.parse("4.57.0"):
            return {"dtype": dtype}
        return {"torch_dtype": dtype}
    except Exception:
        return {"torch_dtype": dtype}


def _init_with_filtered_kwargs(cls, **kwargs):
    """
    构造时只传入类构造函数接受的参数（兼容不同版本的 trl/transformers API）。

    被静默丢弃的参数会打印警告，避免配置项无声失效（如 GRPOConfig 在
    trl 1.9 无 max_prompt_length 字段）。
    """
    import inspect
    sig = inspect.signature(cls.__init__)
    valid = {}
    dropped = []
    for k, v in kwargs.items():
        if k in sig.parameters:
            valid[k] = v
        else:
            dropped.append(k)
    if dropped:
        logger.warning(
            f"{getattr(cls, '__name__', cls)} 忽略不支持的参数: "
            f"{', '.join(sorted(dropped))}"
        )
    return cls(**valid)


def _base_model_name(model_dir: str) -> str:
    """从 adapter_config.json 读取基础模型名；失败时回退为目录本身"""
    try:
        import json
        with open(os.path.join(model_dir, "adapter_config.json"),
                  "r", encoding="utf-8") as f:
            cfg = json.load(f)
        base = cfg.get("base_model_name_or_path")
        if base:
            return base
    except Exception:
        pass
    return model_dir


def _load_model(model_name: str, device: str, use_lora: bool = False,
                lora_r: int = 8, lora_alpha: int = 16,
                lora_target_modules: Optional[List[str]] = None):
    """
    加载模型（支持 LoRA 微调产物目录）。

    Args:
        model_name: 模型名或本地目录（含 adapter_config.json 时按 PeftModel 加载）
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, PeftModel, get_peft_model

    dtype = get_torch_dtype(device)
    kwargs = _dtype_kwargs(dtype)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    is_adapter_dir = (
        use_lora and os.path.isdir(model_name)
        and os.path.exists(os.path.join(model_name, "adapter_config.json"))
    )
    if is_adapter_dir:
        # LoRA 微调产物：先加载基础模型再套 adapter。
        # 纯 adapter 目录（无基座权重，如 _save_model 合并失败时产物）从
        # adapter_config.json 的 base_model_name_or_path 解析基础模型名。
        base_name = _base_model_name(model_name)
        base = AutoModelForCausalLM.from_pretrained(base_name, **kwargs)
        model = PeftModel.from_pretrained(base, model_name)
        model = model.to(device)
        return model, tokenizer

    model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)
    if use_lora:
        modules = lora_target_modules or ["q_proj", "v_proj"]
        lora_config = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            target_modules=modules,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)
    model = model.to(device)
    return model, tokenizer


def _save_model(model, tokenizer, output_dir: str, device: str):
    """保存模型（合并 LoRA 权重）与 tokenizer"""
    os.makedirs(output_dir, exist_ok=True)
    try:
        from peft import PeftModel
        if isinstance(model, PeftModel):
            merged = model.merge_and_unload()
            merged.save_pretrained(output_dir)
        else:
            model.save_pretrained(output_dir)
    except Exception:
        model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    return output_dir


# ================================================================
# SFT 训练器
# ================================================================

class SFTTrainerWrapper:
    """
    监督微调训练器（文档 11.3）。

    用法（对齐参考示例）：
        wrapper = SFTTrainerWrapper()
        result = wrapper.train(
            dataset=sft_dataset,
            model_name="Qwen/Qwen3-0.6B",
            output_dir="./models/sft_model",
            num_epochs=3,
            batch_size=4,
            use_lora=True,
            lora_r=16,
            lora_alpha=32,
        )
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def train(self, dataset, model_name: str, output_dir: str,
              num_epochs: int = 3, batch_size: int = 4,
              learning_rate: float = 5e-5, use_lora: bool = True,
              lora_r: Optional[int] = None, lora_rank: Optional[int] = None,
              lora_alpha: int = 16, max_length: int = 1024,
              weight_decay: float = 0.01, warmup_ratio: float = 0.1,
              save_steps: int = 500, logging_steps: int = 100,
              **kwargs) -> Dict[str, Any]:
        """执行 SFT 训练（真实 trl.SFTTrainer + peft LoRA）"""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import LoraConfig, get_peft_model

        device = get_device()
        dtype = get_torch_dtype(device)
        rank = lora_r if lora_r is not None else (lora_rank or 8)

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        dtype_kwargs = _dtype_kwargs(dtype)
        model = AutoModelForCausalLM.from_pretrained(model_name, **dtype_kwargs)

        if use_lora:
            modules = kwargs.get("lora_target_modules") or ["q_proj", "v_proj"]
            lora_config = LoraConfig(
                r=rank, lora_alpha=lora_alpha, target_modules=modules,
                lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
            )
            model = get_peft_model(model, lora_config)
        model = model.to(device)

        # 数据集必须有 text 列（SFT 格式已生成）
        train_ds = self._prepare_dataset(dataset, model_name)

        try:
            # ---- trl 1.9.x：SFTTrainer + SFTConfig ----
            from trl import SFTConfig, SFTTrainer
            args = _init_with_filtered_kwargs(
                SFTConfig,
                output_dir=output_dir,
                num_train_epochs=num_epochs,
                per_device_train_batch_size=batch_size,
                learning_rate=learning_rate,
                weight_decay=weight_decay,
                warmup_ratio=warmup_ratio,
                max_length=max_length,
                dataset_text_field="text",
                save_steps=save_steps,
                logging_steps=logging_steps,
                report_to=[],
                save_total_limit=1,
                bf16=(device == "cuda"),
                remove_unused_columns=False,
            )
            trainer = SFTTrainer(
                model=model, args=args, train_dataset=train_ds,
                processing_class=tokenizer,
            )
        except (TypeError, ImportError):
            # ---- 旧版 trl / transformers Trainer 降级 ----
            from transformers import Trainer, TrainingArguments
            args = TrainingArguments(
                output_dir=output_dir,
                num_train_epochs=num_epochs,
                per_device_train_batch_size=batch_size,
                learning_rate=learning_rate,
                weight_decay=weight_decay,
                warmup_ratio=warmup_ratio,
                save_steps=save_steps,
                logging_steps=logging_steps,
                report_to=[],
                save_total_limit=1,
                fp16=(device == "cuda"),
                remove_unused_columns=False,
            )
            trainer = Trainer(
                model=model, args=args, train_dataset=train_ds,
                tokenizer=tokenizer,
            )

        train_result = trainer.train()

        save_path = _save_model(model, tokenizer, output_dir, device)
        final_loss = float(train_result.training_loss)
        num_samples = len(train_ds)

        return {
            "status": "completed",
            "algorithm": "sft",
            "output_dir": save_path,
            "model_path": save_path,
            "num_samples": num_samples,
            "num_epochs": num_epochs,
            "final_loss": round(final_loss, 6),
            "device": device,
        }

    def _prepare_dataset(self, dataset, model_name: str):
        """把 SFT 数据集转成含 text 列的 HF Dataset"""
        try:
            from datasets import Dataset
            rows = [dict(s) for s in dataset]
            # 确保有 text 列
            if rows and "text" not in rows[0] and "prompt" in rows[0]:
                for r in rows:
                    r["text"] = r.get("prompt", "") + r.get("completion", "")
            return Dataset.from_list(rows)
        except Exception:
            return dataset


# ================================================================
# GRPO 训练器
# ================================================================

class GRPOTrainerWrapper:
    """
    群组相对策略优化训练器（文档 11.4）。

    核心（文档 11.4.3）：
    - 对每个问题生成 num_generations 个答案（组）
    - 计算组内相对奖励 r_i - r̄（减少方差）
    - KL 散度惩罚防止偏离参考模型

    显存优化（2GB 显卡）：policy 模型上 GPU（bf16），reference 模型放 CPU。
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def train(self, dataset, model_name: str, output_dir: str,
              num_epochs: int = 1, batch_size: int = 2,
              learning_rate: float = 1e-5, use_lora: bool = True,
              lora_r: Optional[int] = None, lora_rank: Optional[int] = None,
              lora_alpha: int = 16, num_generations: int = 4,
              max_new_tokens: int = 256, temperature: float = 0.8,
              kl_coef: float = 0.05, clip_range: float = 0.2,
              max_length: int = 512,
              reward_fn: Optional[Callable] = None,
              reward_type: str = "accuracy",
              **kwargs) -> Dict[str, Any]:
        """执行 GRPO 训练（真实 trl.GRPOTrainer）"""
        import torch
        from trl import GRPOConfig, GRPOTrainer

        device = get_device()
        dtype = get_torch_dtype(device)

        # 加载 policy 模型（GPU bf16 + LoRA）。
        # 显存优化：PEFT 时 trl 将 ref_model 置 None，KL 通过禁用 adapter
        # 对照基础模型计算（trl 1.9 自动处理），零额外显存。
        model, tokenizer = _load_model(
            model_name, device, use_lora=use_lora,
            lora_r=(lora_r if lora_r is not None else (lora_rank or 8)),
            lora_alpha=lora_alpha,
            lora_target_modules=kwargs.get("lora_target_modules"),
        )

        # 奖励函数
        if reward_fn is None:
            from .rewards import create_reward
            reward_fn = create_reward(reward_type)

        # 数据集列重命名：TRL 需要 "prompt" 列
        train_ds = self._prepare_dataset(dataset)

        config = _init_with_filtered_kwargs(
            GRPOConfig,
            output_dir=output_dir,
            num_train_epochs=num_epochs,
            per_device_train_batch_size=batch_size,
            learning_rate=learning_rate,
            beta=kl_coef,
            num_generations=num_generations,
            generation_batch_size=num_generations,  # trl 1.9 要求被 num_generations 整除
            max_completion_length=max_new_tokens,   # trl 1.9 的生成长度参数
            max_prompt_length=max_length,
            temperature=temperature,
            report_to=[],
            remove_unused_columns=False,
            save_total_limit=1,
            bf16=(device == "cuda"),
        )

        try:
            # ---- trl 1.9.x：processing_class，无 ref_model 参数 ----
            trainer = GRPOTrainer(
                model=model,
                args=config,
                reward_funcs=[reward_fn],
                train_dataset=train_ds,
                processing_class=tokenizer,
            )
        except TypeError:
            # ---- 旧版 trl 降级：tokenizer= / ref_model= ----
            kwargs_for_trainer = {
                "model": model,
                "args": config,
                "reward_funcs": [reward_fn],
                "train_dataset": train_ds,
            }
            try:
                trainer = GRPOTrainer(
                    **kwargs_for_trainer, tokenizer=tokenizer)
            except TypeError:
                # 最老版本需要 ref_model 参数：用策略模型的 CPU 副本
                ref = _load_model(
                    model_name, "cpu", use_lora=False)[0]
                trainer = GRPOTrainer(
                    **kwargs_for_trainer, ref_model=ref,
                    tokenizer=tokenizer)

        trainer.train()

        save_path = _save_model(model, tokenizer, output_dir, device)
        num_samples = len(train_ds)

        # 训练日志中提取平均奖励（无则给 0）
        avg_reward = kwargs.get("average_reward", 0.0)
        try:
            history = trainer.state.log_history
            rewards = [h.get("reward", None) for h in history]
            rewards = [r for r in rewards if r is not None]
            if rewards:
                avg_reward = float(sum(rewards) / len(rewards))
        except Exception:
            pass

        return {
            "status": "completed",
            "algorithm": "grpo",
            "output_dir": save_path,
            "model_path": save_path,
            "num_samples": num_samples,
            "num_epochs": num_epochs,
            "average_reward": round(avg_reward, 6),
            "device": device,
        }

    def _prepare_dataset(self, dataset):
        """把 RL 数据集转成含 prompt 列的 HF Dataset"""
        try:
            from datasets import Dataset
            rows = [dict(s) for s in dataset]
            # 保证有 prompt / ground_truth 列
            if rows and "prompt" not in rows[0]:
                for r in rows:
                    r["prompt"] = r.get("question", "")
            return Dataset.from_list(rows)
        except Exception:
            return dataset


# ================================================================
# 模型评估（文档 11.5）
# ================================================================

def evaluate_math_model(
        model_path: str,
        dataset=None,
        max_samples: int = 50,
        use_lora: bool = False,
        device: Optional[str] = None,
        metrics: Optional[List[str]] = None,
        k: int = 3,
        return_details: bool = False,
        max_new_tokens: int = 256,
        **kwargs) -> Dict[str, Any]:
    """
    评估模型在数学数据集上的表现（文档 11.5 评估指标体系）。

    指标：accuracy / average_reward / accuracy_at_k / average_length /
          average_steps / format_correctness（文档 11.5.1）
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if device is None:
        device = get_device()

    if dataset is None:
        from .datasets import GSM8KDataset
        dataset = GSM8KDataset().load("test", max_samples).to_rl(
            max_samples=max_samples)
    else:
        from .datasets import _normalize_max_samples
        n = _normalize_max_samples(max_samples)
        if n is not None:
            dataset = list(dataset)[:n]

    rows = list(dataset)
    # 统一列名
    def _get(row, *keys, default=""):
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        return default

    prompts = [_get(r, "prompt", "question") for r in rows]
    truths = [_get(r, "ground_truth", "answer", default="") for r in rows]

    dtype = get_torch_dtype(device)
    dtype_kwargs = _dtype_kwargs(dtype)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    if use_lora and os.path.isdir(model_path) and os.path.exists(
            os.path.join(model_path, "adapter_config.json")):
        from peft import PeftModel
        from transformers import AutoModelForCausalLM as AM
        base = AM.from_pretrained(model_path, **dtype_kwargs)
        model = PeftModel.from_pretrained(base, model_path)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_path, **dtype_kwargs)
    model = model.to(device).eval()

    from .rewards import AccuracyReward
    from .utils import extract_steps
    reward_fn = AccuracyReward()

    gen_kwargs = dict(
        max_new_tokens=max_new_tokens, do_sample=True,
        temperature=0.7, top_p=0.9,
    )
    if device == "cuda":
        gen_kwargs["temperature"] = 0.7

    predictions = []
    with torch.no_grad():
        for prompt in prompts:
            inputs = tokenizer(prompt, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            outputs = model.generate(**inputs, **gen_kwargs)
            pred = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:],
                                    skip_special_tokens=True)
            predictions.append(pred)

    # 逐样本评估
    details = []
    correct_count = 0
    total_reward = 0.0
    total_length = 0.0
    total_steps = 0.0
    format_count = 0.0
    errors = []

    for prompt, truth, pred in zip(prompts, truths, predictions):
        rewards = reward_fn(completions=[pred], ground_truth=[truth])
        reward = rewards[0]
        correct = reward >= 1.0
        correct_count += int(correct)
        total_reward += reward
        total_length += len(pred)
        steps = extract_steps(pred)
        total_steps += steps
        has_final = "final answer" in pred.lower() or "####" in pred
        format_count += int(has_final)

        if not correct and return_details:
            # 错误分类（文档 11.5.3）
            if not has_final:
                etype = "格式错误"
            elif "step" in pred.lower():
                etype = "计算错误"
            else:
                etype = "理解错误"
            errors.append({
                "question": prompt, "prediction": pred,
                "ground_truth": truth, "error_type": etype,
            })
        if return_details:
            details.append({
                "question": prompt, "prediction": pred,
                "ground_truth": truth, "correct": correct,
                "reward": reward, "steps": steps,
            })

    num = len(prompts) or 1
    result = {
        "accuracy": round(correct_count / num, 4),
        "average_reward": round(total_reward / num, 4),
        "num_samples": len(prompts),
        "average_length": round(total_length / num, 1),
        "average_steps": round(total_steps / num, 2),
        "format_correctness": round(format_count / num, 4),
    }
    if return_details:
        result["errors"] = errors
        result["details"] = details
    return result
