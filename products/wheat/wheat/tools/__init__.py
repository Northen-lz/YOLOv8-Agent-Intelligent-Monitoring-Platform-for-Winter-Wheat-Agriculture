# -*- coding: utf-8 -*-
"""小麦平台 · 领域工具包

农业工具继承框架的 BaseTool：from ha_framework.tools.base import BaseTool。
"""
from .agriculture import (  # noqa: F401
    AgricultureKnowledgeTool,
    AuthorInfoTool,
    DroughtPredictionTool,
    ExperimentAnalysisTool,
    ImageInfoTool,
    ReportGenerationTool,
    WheatDetectionTool,
)

__all__ = [
    "WheatDetectionTool",
    "DroughtPredictionTool",
    "AgricultureKnowledgeTool",
    "ExperimentAnalysisTool",
    "ReportGenerationTool",
    "AuthorInfoTool",
    "ImageInfoTool",
]
