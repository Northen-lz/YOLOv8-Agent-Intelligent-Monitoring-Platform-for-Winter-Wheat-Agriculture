# -*- coding: utf-8 -*-
"""
Hello-Agents 通用框架包（拆分后 · 领域无关）

只包含通用智能体能力：Agent 推理范式、工具体系、记忆/RAG、上下文工程、
通信协议（MCP/A2A/ANP）、强化学习（rl）、评估（evaluation）。
领域/产品代码不再放在本包 —— 产品在各自目录中 import 本框架并扩展
（例：products/wheat）。

顶层导出（对齐文档：from ha_framework import SimpleAgent, HelloAgentsLLM, ...）
"""

from .agents.simple_agent import SimpleAgent
from .agents.codebase_maintainer import CodebaseMaintainer
from .agents.function_call_agent import FunctionCallingAgent
from .agents.react_agent import ReActAgent
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

# 强化学习模块（第十一章，惰性导入，base 环境可用数据集/奖励层）
from . import rl  # noqa: E402

# 智能体性能评估模块（第十二章）
from . import evaluation  # noqa: E402

__all__ = [
    "SimpleAgent",
    "CodebaseMaintainer",
    "FunctionCallingAgent",
    "ReActAgent",
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
