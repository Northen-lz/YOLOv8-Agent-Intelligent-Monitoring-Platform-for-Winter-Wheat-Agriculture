# -*- coding: utf-8 -*-
"""
智能体性能评估模块（文档第十二章）

三大评估场景（12.1.3）：
- BFCL       工具调用评估（AST 匹配）
- GAIA       通用助手评估（准精确匹配）
- 数据生成    AIME 生成质量评估（LLM Judge + Win Rate）

公开接口（对齐参考代码）：
    from hello_agents.evaluation import BFCLDataset, BFCLEvaluator, ...
    from hello_agents.evaluation import GAIADataset, GAIAEvaluator, ...
    from hello_agents.evaluation import LLMJudge, WinRateEvaluator, AIDataset, AIMEGenerator
"""

from . import benchmarks  # noqa: F401
from .benchmarks import bfcl, gaia  # noqa: F401
from . import data_generation  # noqa: F401

# BFCL 纯逻辑层（离线可用）
from .benchmarks.bfcl.ast_matcher import (  # noqa: F401
    ast_match,
    extract_call_dicts,
    find_call_expressions,
    match_call_texts,
    match_calls,
    parse_function_call,
)
from .benchmarks.bfcl.dataset import BFCLDataset  # noqa: F401
from .benchmarks.bfcl.evaluator import (  # noqa: F401
    FUNCTION_CALLING_SYSTEM_PROMPT,
    BFCLEvaluator,
)
from .benchmarks.bfcl.metrics import BFCLMetrics, compute_metrics  # noqa: F401

# GAIA 纯逻辑层（离线可用）
from .benchmarks.gaia.dataset import GAIADataset  # noqa: F401
from .benchmarks.gaia.evaluator import GAIA_SYSTEM_PROMPT, GAIAEvaluator  # noqa: F401
from .benchmarks.gaia.metrics import GAIA_Metrics  # noqa: F401
from .benchmarks.gaia.quasi_exact_match import (  # noqa: F401
    normalize_answer,
    partial_match,
    quasi_exact_match,
)

# 数据生成质量（聚合纯逻辑离线可用；评估需 LLM）
from .data_generation import (  # noqa: F401
    AIDataset,
    AIMEGenerator,
    LLMJudge,
    LLMJudgeEvaluator,
    WinRateEvaluator,
)

__all__ = [
    # BFCL 纯逻辑
    "ast_match",
    "extract_call_dicts",
    "find_call_expressions",
    "match_call_texts",
    "match_calls",
    "parse_function_call",
    "BFCLDataset",
    "BFCLEvaluator",
    "FUNCTION_CALLING_SYSTEM_PROMPT",
    "BFCLMetrics",
    "compute_metrics",
    # GAIA 纯逻辑
    "normalize_answer",
    "partial_match",
    "quasi_exact_match",
    "GAIA_Metrics",
    "GAIADataset",
    "GAIAEvaluator",
    "GAIA_SYSTEM_PROMPT",
    # 数据生成质量
    "AIDataset",
    "AIMEGenerator",
    "LLMJudge",
    "LLMJudgeEvaluator",
    "WinRateEvaluator",
]
