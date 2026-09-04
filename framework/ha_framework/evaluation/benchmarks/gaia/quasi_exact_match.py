# -*- coding: utf-8 -*-
"""
GAIA 准精确匹配（对齐文档第十二章 12.3.1）

纯逻辑模块，只依赖标准库 re，无外部依赖。

归一化规则（文档 12.3.1）：
- 数字：去千分位逗号（1,234 → 1234）、去单位（5 kg → 5、72°F → 72）、去 % 与 $
- 字符串：小写、去冠词（a/an/the）、折叠空白、去末尾标点
- 列表：逗号 / " and " / & / ; 分隔，逐项归一化后字母序排序

典型用法：
    >>> normalize_answer("The Cat is  on the roof.")
    'cat is on roof'
    >>> quasi_exact_match("1,234", "1234")
    True
    >>> quasi_exact_match("72°F", "72")
    True
"""

import re
from typing import Optional

# 数字后常见单位/后缀（归一化时剥离）
_NUMBER_WITH_UNIT = re.compile(r"(-?\d+(?:\.\d+)?)\s*[a-zA-Z°%$€£¥]*$")
# 千分位逗号
_THOUSANDS = re.compile(r"(?<=\d),(?=\d)")
# 冠词
_ARTICLE = re.compile(r"\b(a|an|the)\b")
# 空白折叠
_WS = re.compile(r"\s+")
# 末尾标点
_TRAILING_PUNCT = re.compile(r"[.,;:!?]+$")
# 纯数字千分位格式（1,234,567 不当作列表）
_PURE_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# 列表分隔符
_LIST_SEP = re.compile(r"\s*,\s*|\s*;\s*|\s*&\s*|\s+and\s+")


def normalize_answer(answer: Optional[str]) -> str:
    """把答案规范化为可比较的字符串（文档 12.3.1 归一化规则）。"""
    if answer is None:
        return ""
    answer = str(answer).strip()
    if not answer:
        return ""
    # 去掉代码块围栏
    answer = _strip_fence(answer)
    if not answer:
        return ""

    # 列表型：先切分、逐项归一化、字母序排序
    if _looks_like_list(answer):
        items = [
            _normalize_item(i)
            for i in _split_list(answer)
        ]
        items = [i for i in items if i]
        return " | ".join(sorted(items)) if items else ""

    return _normalize_item(answer)


def _strip_fence(answer: str) -> str:
    stripped = answer.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        for lang in ("python", "json"):
            if stripped.startswith(lang):
                stripped = stripped[len(lang):]
                break
        stripped = stripped.strip()
    return stripped


def _looks_like_list(answer: str) -> bool:
    """判定是否为列表型答案（纯千分位数字不误判为列表）。"""
    if _PURE_NUMBER.fullmatch(answer):
        return False
    return ("," in answer) or (" and " in answer) or ("&" in answer) or (";" in answer)


def _split_list(answer: str) -> list:
    return [p.strip() for p in _LIST_SEP.split(answer) if p.strip()]


def _normalize_item(item: str) -> str:
    item = item.strip().lower()
    # 去千分位逗号（1,234 → 1234）
    item = _THOUSANDS.sub("", item)
    # 去 $ 与 %
    item = item.replace("$", "").replace("%", "")
    # 去冠词
    item = _ARTICLE.sub(" ", item)
    # 折叠空白
    item = _WS.sub(" ", item).strip()
    # 去末尾标点（72°F. → 72°F）
    item = _TRAILING_PUNCT.sub("", item).strip()
    # 数字后去单位/后缀（5 kg → 5、72°F → 72）
    item = _strip_unit(item)
    # 数值字面量规范化（007 → 7、1.50 → 1.5）
    item = _numericize(item)
    return item


def _strip_unit(item: str) -> str:
    """数字答案剥离尾部单位/后缀。"""
    m = _NUMBER_WITH_UNIT.fullmatch(item)
    if m:
        return m.group(1)
    return item


def _numericize(item: str) -> str:
    """数值字面量规范化：整型去前导零、小数去尾零（不经过 float，避免大数丢精度）。"""
    if re.fullmatch(r"-?\d+", item):
        return str(int(item))
    m = re.fullmatch(r"(-?\d+)\.(\d+)", item)
    if m:
        int_part, dec_part = m.group(1), m.group(2).rstrip("0")
        if not dec_part:
            return str(int(int_part))
        return f"{int_part}.{dec_part}"
    return item


def quasi_exact_match(pred: Optional[str], truth: Optional[str]) -> bool:
    """准精确匹配：两端归一化后相等（文档 12.3.1）。"""
    npred = normalize_answer(pred)
    ntruth = normalize_answer(truth)
    if not ntruth or not npred:
        return False
    return npred == ntruth


def partial_match(pred: Optional[str], truth: Optional[str]) -> bool:
    """部分匹配：列表型答案取交集非空；非列表回退为完全匹配。"""
    npred = normalize_answer(pred)
    ntruth = normalize_answer(truth)
    if npred == ntruth:
        return True
    if not npred or not ntruth:
        return False
    pred_items = set(npred.split(" | ")) if " | " in npred else {npred}
    truth_items = set(ntruth.split(" | ")) if " | " in ntruth else {ntruth}
    return bool(pred_items & truth_items)
