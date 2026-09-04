# -*- coding: utf-8 -*-
"""
YOLOv8-Agent 冬小麦农业智能监测平台 —— 产品包

领域代码（Agent/工具/知识/UI）都在这一个包内，通用能力来自 ha_framework。
镜像布局刻意保留旧 hello_agents 的目录结构，使领域内部相对导入改动最小。

导出对齐旧版顶层（ManagerAgent 等），方便从外部引用；
Gradio 界面按需加载：from wheat.app import build_ui（不在此导入，避免连带 gradio）。
"""

from .core.config import Config  # noqa: F401
from .agents.wheat_agent import WheatVisionAgent  # noqa: F401
from .agents.agriculture_agent import AgricultureExpertAgent  # noqa: F401
from .agents.analysis_agent import AnalysisAgent  # noqa: F401
from .agents.report_agent import ReportAgent  # noqa: F401
from .agents.author_agent import AuthorAgent  # noqa: F401
from .agents.manager_agent import ManagerAgent  # noqa: F401
from .tools import (  # noqa: F401
    AgricultureKnowledgeTool,
    AuthorInfoTool,
    DroughtPredictionTool,
    ExperimentAnalysisTool,
    ImageInfoTool,
    ReportGenerationTool,
    WheatDetectionTool,
)

__all__ = [
    "Config",
    "WheatVisionAgent",
    "AgricultureExpertAgent",
    "AnalysisAgent",
    "ReportAgent",
    "AuthorAgent",
    "ManagerAgent",
    "WheatDetectionTool",
    "DroughtPredictionTool",
    "AgricultureKnowledgeTool",
    "ExperimentAnalysisTool",
    "ReportGenerationTool",
    "AuthorInfoTool",
    "ImageInfoTool",
]
