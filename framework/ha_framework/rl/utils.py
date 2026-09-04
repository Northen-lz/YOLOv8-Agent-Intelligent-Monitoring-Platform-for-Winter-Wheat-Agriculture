# -*- coding: utf-8 -*-
"""
Hello-Agents RL 工具函数
对齐文档第十一章 11.2「奖励函数设计」中的答案提取与比较

- extract_answer:   从模型输出中提取最终答案
- compare_answers:  数值归一化比较（72.0 ↔ 72）
- extract_steps:    检测推理步骤数量（供 StepReward 使用）
"""

import re
from typing import List, Optional


def extract_answer(text: str) -> Optional[str]:
    """
    从模型输出中提取最终答案。

    提取顺序（文档 11.2.2）：
    1. "Final Answer:" 后的第一个数字
    2. "####" 标记后的数字
    3. 最后一行的数字
    4. 兜底：全文最后一个数字

    Args:
        text: 模型生成的文本

    Returns:
        提取到的答案字符串；未找到返回 None
    """
    if not text:
        return None

    # 1. Final Answer: 后的数字
    for m in re.finditer(r"[Ff]inal\s+[Aa]nswer\s*[:：]\s*([-\d][\d.,]*)", text):
        candidate = m.group(1).replace(",", "")
        if _is_number(candidate):
            return candidate

    # 2. #### 标记后的数字（GSM8K 标准格式）
    for m in re.finditer(r"####\s*([-\d][\d.,]*)", text):
        candidate = m.group(1).replace(",", "")
        if _is_number(candidate):
            return candidate

    # 3. 最后一行的数字
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if lines:
        last_numbers = re.findall(r"([-\d][\d.,]*)", lines[-1])
        for n in reversed(last_numbers):
            candidate = n.replace(",", "")
            if _is_number(candidate):
                return candidate

    # 4. 兜底：全文最后一个数字
    all_numbers = re.findall(r"([-\d][\d.,]*)", text)
    for n in reversed(all_numbers):
        candidate = n.replace(",", "")
        if _is_number(candidate):
            return candidate

    return None


def extract_steps(text: str) -> int:
    """
    检测推理步骤数量（文档 11.2.2 步骤奖励）。

    检测方法：
    - "Step 1:" / "Step 2:" 等显式标记
    - 换行符数量（近似）
    - 正则匹配推理模式（如 "=" 计算行）

    Args:
        text: 模型生成的文本

    Returns:
        步骤数量
    """
    if not text:
        return 0

    # 显式 "Step N:" 标记
    explicit = re.findall(r"[Ss]tep\s*(\d+)\s*[:：]", text)
    if explicit:
        steps = [int(s) for s in explicit]
        return max(steps)

    # 计算行（含 "=" 的推导式）
    calc_lines = 0
    for line in text.splitlines():
        if "=" in line and re.search(r"\d", line):
            calc_lines += 1
    if calc_lines >= 2:
        return calc_lines

    # 换行分段数（近似步骤）
    segments = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(segments) >= 3:
        return len(segments) - 1

    return 0


def compare_answers(pred: str, truth: str, tolerance: float = 1e-4) -> bool:
    """
    比较预测答案与真实答案（数值归一化 + 容差）。

    - 72.0 与 72 视为相同
    - 1000 与 1k 视为相同
    - 容差内（默认 1e-4）视为正确

    Args:
        pred: 预测答案字符串
        truth: 真实答案字符串
        tolerance: 数值比较容差

    Returns:
        是否视为正确
    """
    if pred is None or truth is None:
        return False

    pred = str(pred).strip().lower()
    truth = str(truth).strip().lower()

    # 原文相等
    if pred == truth:
        return True

    # 千位缩写 1k / 1m
    pred_norm = _normalize_unit(pred)
    truth_norm = _normalize_unit(truth)
    if pred_norm is not None and truth_norm is not None:
        return abs(pred_norm - truth_norm) <= tolerance

    return False


def _is_number(s: str) -> bool:
    """判断字符串是否为可解析数字"""
    try:
        float(s.replace(",", ""))
        return True
    except (ValueError, TypeError):
        return False


def _normalize_unit(s: str) -> Optional[float]:
    """数值归一化：支持 1k/1m 缩写、千分位逗号"""
    s = s.strip()
    mult = 1.0
    if s.endswith("k"):
        mult, s = 1e3, s[:-1]
    elif s.endswith("m"):
        mult, s = 1e6, s[:-1]
    try:
        return float(s.replace(",", "")) * mult
    except (ValueError, TypeError):
        return None


def answer_matches_any(completion: str, ground_truths: List[str],
                       tolerance: float = 1e-4) -> bool:
    """
    模型的输出是否与任意一个真实答案匹配（支持多答案）。

    Args:
        completion: 模型生成文本
        ground_truths: 候选真实答案列表
        tolerance: 数值容差

    Returns:
        是否命中任一答案
    """
    pred = extract_answer(completion)
    if pred is None:
        return False
    return any(compare_answers(pred, t, tolerance) for t in ground_truths)
