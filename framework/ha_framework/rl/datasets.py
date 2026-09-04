# -*- coding: utf-8 -*-
"""
Hello-Agents 数据集层
对齐文档第十一章 11.2.1「GSM8K 数学推理数据集」+ 11.2.3「自定义数据集」

GSM8K 数据格式转换（图 11.4）：
- 原始格式:  {question, answer}（answer 含解题步骤 + "#### 答案"）
- SFT 格式:  {prompt, completion, text}   监督微调用（含完整解题过程）
- RL 格式:   {prompt, ground_truth, question, full_answer}  强化学习用（只给最终答案）

离线兜底：`datasets` 库或网络不可用时，回退到内置微型样本集，
保证 load_dataset 在 base 环境也能跑通（图 11.3 数据集层）。
"""

import re
from typing import Any, Dict, List, Optional


def _normalize_max_samples(max_samples) -> Optional[int]:
    """字符串/数值 max_samples 强转；非数值或 ≤0 视为 None（不限制）

    SimpleAgent 解析出的 max_samples 可能是字符串（如 "50"/"全部"），
    直接用于切片会抛 TypeError。
    """
    if max_samples is None:
        return None
    try:
        n = int(max_samples)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


# ================================================================
# 内置兜底样本（离线可用）
# ================================================================

_FALLBACK_SAMPLES: List[Dict[str, str]] = [
    {
        "question": "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?",
        "answer": "Natalia sold 48/2 = <<48/2=24>>24 clips in May.\nNatalia sold 48+24 = <<48+24=72>>72 clips altogether in April and May.\n#### 72",
    },
    {
        "question": "Weng earns $12 an hour for babysitting. Yesterday, she just did 50 minutes of babysitting. How much did she earn?",
        "answer": "Weng earns 12/60 = <<12/60=0.2>>0.2 dollars per minute.\nShe earned 50 * 0.2 = <<50*0.2=10>>10 dollars.\n#### 10",
    },
    {
        "question": "Betty is saving money for a new wallet which costs $100. Betty has only half of the money she needs. Her parents decided to give her $15 for that purpose, and her grandparents twice as much as her parents. How much more money does Betty need to buy the wallet?",
        "answer": "Betty has half of the money she needs: $100/2 = $50.\nParents give her $15.\nGrandparents give her $15*2 = $30.\nTotal she has now: $50+$15+$30 = $95.\nShe needs $100 - $95 = $5 more.\n#### 5",
    },
    {
        "question": "If there are 3 cars in the parking lot and 2 more cars arrive, how many cars are in the parking lot?",
        "answer": "There are 3 cars initially.\n2 more arrive: 3+2 = <<3+2=5>>5.\n#### 5",
    },
    {
        "question": "Janet's ducks lay 16 eggs per day. She eats three for breakfast every morning and bakes muffins for her friends every day with four. She sells the remainder at the farmers' market daily for $2 per fresh duck egg. How much in dollars does she make every day at the farmers' market?",
        "answer": "Janet sells 16 - 3 - 4 = <<16-3-4=9>>9 duck eggs per day.\nShe makes 9 * $2 = $<<9*2=18>>18 every day.\n#### 18",
    },
]


# ================================================================
# 对话模板
# ================================================================

def _apply_chat_template(question: str, model_name: Optional[str] = None) -> str:
    """构造对话格式 prompt（默认 Qwen 模板，文档 11.2.1）"""
    model_name = (model_name or "").lower()
    if "qwen" in model_name or not model_name:
        # Qwen 模板：<|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n
        return (f"<|im_start|>user\n{question}<|im_end|>\n"
                f"<|im_start|>assistant\n")
    # 通用对话模板兜底
    return f"Question: {question}\n\nLet's solve this step by step:\n"


def _parse_gsm8k_answer(answer: str):
    """
    解析 GSM8K 原始答案 -> (最终答案, 干净推理文本)。

    原始格式："Natalia sold 48/2 = <<48/2=24>>24 clips...\n#### 72"
    处理后：   ("72", "Natalia sold 48/2 = 24 clips...")
    """
    answer = (answer or "").strip()
    m = re.search(r"####\s*([-\d][\d.,]*)", answer)
    final = m.group(1).replace(",", "") if m else None
    # 去掉 "#### 答案" 标记行
    reasoning = re.sub(r"####.*$", "", answer, flags=re.M).strip()
    # 去掉 <<...>> 内联计算标记
    reasoning = re.sub(r"<<[^>]*>>", "", reasoning).strip()
    return final, reasoning


# ================================================================
# 简化数据集包装（无 datasets 库时使用）
# ================================================================

class _SimpleDataset:
    """无 datasets 库时的最小 Dataset 接口（离线兜底）"""

    def __init__(self, data: List[Dict[str, Any]]):
        self._data = data

    @property
    def column_names(self) -> List[str]:
        return list(self._data[0].keys()) if self._data else []

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, idx):
        if isinstance(idx, int):
            return self._data[idx]
        if isinstance(idx, slice):
            return self._data[idx]
        raise TypeError(f"不支持的索引类型: {type(idx)}")

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def __iter__(self):
        return iter(self._data)


def _to_dataset(data: List[Dict[str, Any]]):
    """转成 datasets.Dataset；库不可用时用 _SimpleDataset"""
    try:
        from datasets import Dataset
        return Dataset.from_list(data)
    except Exception:
        return _SimpleDataset(data)


# ================================================================
# GSM8K 数据集
# ================================================================

class GSM8KDataset:
    """
    GSM8K 数学推理数据集（文档 11.2.1，表 11.2）。

    训练集 7473 样本 / 测试集 1319 样本，2-8 步小学数学应用题。
    支持离线兜底：datasets 库或网络不可用时回退内置样本。

    用法：
        ds = GSM8KDataset()
        raw = ds.load(split="train", max_samples=100)
        sft_data = ds.to_sft(max_samples=100)
        rl_data  = ds.to_rl(max_samples=100)
    """

    def __init__(self, dataset_name: str = "gsm8k", config_name: str = "main",
                 cache_dir: Optional[str] = None):
        self.dataset_name = dataset_name
        self.config_name = config_name
        self.cache_dir = cache_dir
        self._raw = None          # 原始 {question, answer} 列表
        self._split = None
        self._used_fallback = False

    @property
    def used_fallback(self) -> bool:
        """是否使用了内置兜底数据"""
        return self._used_fallback

    # ---------------- 加载 ----------------

    def load(self, split: str = "train", max_samples: Optional[int] = None):
        """
        加载 GSM8K 数据集。

        Args:
            split: "train" 或 "test"
            max_samples: 限制样本数；None 使用全部
        """
        try:
            from datasets import load_dataset
            ds = load_dataset(
                self.dataset_name, self.config_name, split=split,
                cache_dir=self.cache_dir,
            )
            self._raw = list(ds)
            self._used_fallback = False
        except Exception:
            # 离线兜底：内置样本（test 与 train 用同一组微型样本）
            self._raw = list(_FALLBACK_SAMPLES)
            self._used_fallback = True
        self._split = split

        self._raw = self._raw[:_normalize_max_samples(max_samples)]
        return self

    # ---------------- 格式转换 ----------------

    def to_sft(self, max_samples: Optional[int] = None,
               model_name: Optional[str] = None):
        """转 SFT 格式 {prompt, completion, text}"""
        if self._raw is None:
            self.load()
        raw = self._raw[:_normalize_max_samples(max_samples)]
        rows = []
        for item in raw:
            question = item.get("question", "")
            answer = item.get("answer", "")
            final, reasoning = _parse_gsm8k_answer(answer)
            prompt = _apply_chat_template(question, model_name)
            if final:
                completion = f"{reasoning}\nFinal Answer: {final}"
            else:
                completion = reasoning
            rows.append({
                "prompt": prompt,
                "completion": completion,
                "text": prompt + completion,
            })
        return _to_dataset(rows)

    def to_rl(self, max_samples: Optional[int] = None,
              model_name: Optional[str] = None):
        """转 RL 格式 {prompt, ground_truth, question, full_answer}"""
        if self._raw is None:
            self.load()
        raw = self._raw[:_normalize_max_samples(max_samples)]
        rows = []
        for item in raw:
            question = item.get("question", "")
            answer = item.get("answer", "")
            final, _ = _parse_gsm8k_answer(answer)
            rows.append({
                "prompt": _apply_chat_template(question, model_name),
                "ground_truth": final or "",
                "question": question,
                "full_answer": answer,
            })
        return _to_dataset(rows)

    def __len__(self) -> int:
        return len(self._raw) if self._raw is not None else 0


# ================================================================
# 通用格式转换（文档 11.2.3 自定义数据集）
# ================================================================

def format_math_dataset(dataset, format_type: str = "sft",
                        model_name: Optional[str] = None):
    """
    把 {question, answer} 数据集转换为训练格式（文档 11.2.3）。

    Args:
        dataset: 包含 question / answer 字段的数据集
                 （datasets.Dataset 或可迭代的 dict 列表）
        format_type: "sft" 或 "rl"
        model_name: 模型名（用于选择对话模板）

    Returns:
        SFT -> {prompt, completion, text}
        RL  -> {prompt, ground_truth, question, full_answer}
    """
    # 统一取出原始行
    if hasattr(dataset, "to_list"):
        rows = list(dataset.to_list())
    else:
        rows = list(dataset)

    converted = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        question = item.get("question", "")
        answer = item.get("answer", "")
        if format_type == "sft":
            final, reasoning = _parse_gsm8k_answer(answer)
            prompt = _apply_chat_template(question, model_name)
            completion = f"{reasoning}\nFinal Answer: {final}" if final else reasoning
            converted.append({
                "prompt": prompt,
                "completion": completion,
                "text": prompt + completion,
            })
        elif format_type == "rl":
            final, _ = _parse_gsm8k_answer(answer)
            converted.append({
                "prompt": _apply_chat_template(question, model_name),
                "ground_truth": final or "",
                "question": question,
                "full_answer": answer,
            })
        else:
            raise ValueError(f"未知格式: {format_type}（可用: sft / rl）")
    return _to_dataset(converted)


def create_sft_dataset(dataset=None, split: str = "train",
                       max_samples: Optional[int] = None,
                       model_name: Optional[str] = None):
    """
    创建 SFT 格式数据集（文档 11.1.4 数据集层工厂函数）。

    Args:
        dataset: 自定义 {question, answer} 数据集；None 时加载 GSM8K
    """
    if dataset is None:
        return GSM8KDataset().load(split, max_samples).to_sft(
            max_samples=max_samples, model_name=model_name)
    return format_math_dataset(dataset, format_type="sft", model_name=model_name)


def create_rl_dataset(dataset=None, split: str = "train",
                      max_samples: Optional[int] = None,
                      model_name: Optional[str] = None):
    """
    创建 RL 格式数据集（文档 11.1.4 数据集层工厂函数）。
    """
    if dataset is None:
        return GSM8KDataset().load(split, max_samples).to_rl(
            max_samples=max_samples, model_name=model_name)
    return format_math_dataset(dataset, format_type="rl", model_name=model_name)
