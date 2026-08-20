# -*- coding: utf-8 -*-
"""Hello-Agents 工具包（对齐文档：from hello_agents.tools import MemoryTool, RAGTool, ...）"""

from .base import BaseTool, Tool, ToolParameter
from .builtin import (
    A2ATool,
    ANPTool,
    BFCLEvaluationTool,
    GAIAEvaluationTool,
    LLMJudgeTool,
    MemoryTool,
    MCPTool,
    NoteTool,
    RAGTool,
    RLTrainingTool,
    SearchTool,
    TerminalTool,
    WinRateTool,
)
from .agent_tool import AgentTool
from .agriculture import (
    WheatDetectionTool,
    DroughtPredictionTool,
    AgricultureKnowledgeTool,
    ExperimentAnalysisTool,
    ReportGenerationTool,
    AuthorInfoTool,
    ImageInfoTool,
)
from .registry import ToolRegistry

__all__ = [
    "BaseTool",
    "Tool",
    "ToolParameter",
    "ToolRegistry",
    "MemoryTool",
    "NoteTool",
    "RAGTool",
    "SearchTool",
    "TerminalTool",
    "MCPTool",
    "A2ATool",
    "ANPTool",
    "RLTrainingTool",
    # 第十二章评估工具
    "BFCLEvaluationTool",
    "GAIAEvaluationTool",
    "LLMJudgeTool",
    "WinRateTool",
    # 农业智能监测平台工具
    "AgentTool",
    "WheatDetectionTool",
    "DroughtPredictionTool",
    "AgricultureKnowledgeTool",
    "ExperimentAnalysisTool",
    "ReportGenerationTool",
    "AuthorInfoTool",
    "ImageInfoTool",
]
