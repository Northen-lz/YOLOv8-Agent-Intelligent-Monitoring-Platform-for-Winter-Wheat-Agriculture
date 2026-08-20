# -*- coding: utf-8 -*-
"""
Hello-Agents 框架包

顶层导出（对齐文档：from hello_agents import SimpleAgent, HelloAgentsLLM, ...）
"""

from .agents.simple_agent import SimpleAgent
from .agents.codebase_maintainer import CodebaseMaintainer
from .agents.function_call_agent import FunctionCallingAgent
from .agents.react_agent import ReActAgent
from .agents.wheat_agent import WheatVisionAgent
from .agents.agriculture_agent import AgricultureExpertAgent
from .agents.analysis_agent import AnalysisAgent
from .agents.report_agent import ReportAgent
from .agents.author_agent import AuthorAgent
from .agents.manager_agent import ManagerAgent
from .core.agent import Agent
from .core.config import Config
from .core.exceptions import (
    HelloAgentsError,
    LLMError,
    AgentError,
    ToolError,
)
from .core.llm import HelloAgentsLLM
from .core.message import Message
from .memory import MemoryConfig, MemoryItem, MemoryManager
from .context import ContextBuilder, ContextConfig, ContextPacket
from .tools.base import BaseTool, Tool, ToolParameter
from .tools.builtin import (
    BFCLEvaluationTool,
    GAIAEvaluationTool,
    LLMJudgeTool,
    MemoryTool,
    NoteTool,
    RAGTool,
    SearchTool,
    TerminalTool,
    MCPTool,
    A2ATool,
    ANPTool,
    RLTrainingTool,
    WinRateTool,
)
from .tools.registry import ToolRegistry
from .tools.agent_tool import AgentTool
from .tools.agriculture import (
    AuthorInfoTool,
    AgricultureKnowledgeTool,
    DroughtPredictionTool,
    ExperimentAnalysisTool,
    ImageInfoTool,
    ReportGenerationTool,
    WheatDetectionTool,
)

# 强化学习模块（第十一章，惰性导入，base 环境可用数据集/奖励层）
from . import rl  # noqa: E402

# 智能体性能评估模块（第十二章）
from . import evaluation  # noqa: E402

__all__ = [
    "SimpleAgent",
    "CodebaseMaintainer",
    "FunctionCallingAgent",
    "ReActAgent",
    "WheatVisionAgent",
    "AgricultureExpertAgent",
    "AnalysisAgent",
    "ReportAgent",
    "AuthorAgent",
    "ManagerAgent",
    "Agent",
    "Config",
    "HelloAgentsError",
    "LLMError",
    "AgentError",
    "ToolError",
    "HelloAgentsLLM",
    "Message",
    "BaseTool",
    "Tool",
    "ToolParameter",
    "ToolRegistry",
    "AgentTool",
    "WheatDetectionTool",
    "DroughtPredictionTool",
    "AgricultureKnowledgeTool",
    "ExperimentAnalysisTool",
    "ReportGenerationTool",
    "AuthorInfoTool",
    "ImageInfoTool",
    "MemoryTool",
    "NoteTool",
    "RAGTool",
    "SearchTool",
    "TerminalTool",
    "MCPTool",
    "A2ATool",
    "ANPTool",
    "RLTrainingTool",
    "BFCLEvaluationTool",
    "GAIAEvaluationTool",
    "LLMJudgeTool",
    "WinRateTool",
    "rl",
    "evaluation",
    "ContextBuilder",
    "ContextConfig",
    "ContextPacket",
    "MemoryConfig",
    "MemoryItem",
    "MemoryManager",
]
