# -*- coding: utf-8 -*-
"""GAIA 基准（文档第十二章 12.3）——通用助手准精确匹配评估"""

from .dataset import GAIADataset
from .evaluator import GAIA_SYSTEM_PROMPT, GAIAEvaluator
from .metrics import GAIA_Metrics, compute_metrics
from .quasi_exact_match import normalize_answer, partial_match, quasi_exact_match

__all__ = [
    "normalize_answer",
    "partial_match",
    "quasi_exact_match",
    "GAIA_Metrics",
    "compute_metrics",
    "GAIADataset",
    "GAIAEvaluator",
    "GAIA_SYSTEM_PROMPT",
]
