# -*- coding: utf-8 -*-
"""Hello-Agents 智能体层（对齐文档：from hello_agents.agents import SimpleAgent, ...）"""

from .codebase_maintainer import CodebaseMaintainer
from .function_call_agent import FunctionCallingAgent
from .simple_agent import SimpleAgent
from .react_agent import ReActAgent
from .wheat_agent import WheatVisionAgent
from .agriculture_agent import AgricultureExpertAgent
from .analysis_agent import AnalysisAgent
from .report_agent import ReportAgent
from .author_agent import AuthorAgent
from .manager_agent import ManagerAgent

__all__ = [
    "CodebaseMaintainer",
    "FunctionCallingAgent",
    "SimpleAgent",
    "ReActAgent",
    # 农业智能监测平台（YOLOv8-Agent）
    "WheatVisionAgent",
    "AgricultureExpertAgent",
    "AnalysisAgent",
    "ReportAgent",
    "AuthorAgent",
    "ManagerAgent",
]
