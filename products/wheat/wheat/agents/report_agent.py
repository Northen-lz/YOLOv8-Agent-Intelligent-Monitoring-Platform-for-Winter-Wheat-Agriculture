# -*- coding: utf-8 -*-
"""
ReportAgent —— 农业报告生成 Agent

将检测/干旱分析结果组织为《冬小麦智能监测报告》并落盘。
支持 Markdown / Word / PDF 三格式（缺库降级为 md）。

输入形态：
- 结构化: run(data={"detection":{...},"drought":{...},"risk_analysis":"...","suggestions":"..."})
- 文本:   run(content="检测...干旱率...") 自动从文本提取关键指标
"""

import json
import re
from typing import Any, Dict

from ha_framework.core.agent import Agent
from ha_framework.core.llm import HelloAgentsLLM
from ..tools.agriculture.report_tool import ReportGenerationTool

REPORT_METRIC_PATTERNS = {
    "count": [r"株数[:：]\s*(\d+)", r"检测到[^\d]*?(\d+)\s*株"],
    "avg_conf": [r"置信度[:：]\s*([\d.]+)"],
    "drought_rate": [r"干旱率[:：]?\s*([\d.]+)"],
    "drought_count": [r"干旱[:：]?\s*(\d+)\s*株"],
    "control_count": [r"正常[:：]?\s*(\d+)\s*株"],
}


class ReportAgent(Agent):

    def __init__(self, name="report", llm=None, output_dir=None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm)
        self.report_tool = ReportGenerationTool(output_dir=output_dir)

    # ---------------- 数据整理 ----------------

    @classmethod
    def _extract_metrics(cls, text: str) -> Dict[str, Any]:
        """从分析文本中正则提取关键指标"""
        metrics: Dict[str, Any] = {}
        for key, patterns in REPORT_METRIC_PATTERNS.items():
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    metrics[key] = float(m.group(1))
                    break
        return metrics

    @classmethod
    def _build_report_data(cls, data=None, content="") -> Dict[str, Any]:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = None
        if isinstance(data, dict) and (data.get("detection") or data.get("drought")):
            report_data = dict(data)
            if content and not report_data.get("risk_analysis"):
                report_data["risk_analysis"] = content
            # 归一化图像尺寸/路径（build_markdown 从 image 段与顶层读取）
            det = report_data.get("detection") or {}
            img = report_data.setdefault("image", {})
            if "image_width" in det and "width" not in img:
                img["width"] = det["image_width"]
            if "image_height" in det and "height" not in img:
                img["height"] = det["image_height"]
            if det.get("image_path") and not report_data.get("image_path"):
                report_data["image_path"] = det["image_path"]
            return report_data

        # 文本形态：提取指标，组织报告
        text = content or (data.get("content") if isinstance(data, dict) else "") or ""
        metrics = cls._extract_metrics(text)
        detection = {}
        if "count" in metrics:
            detection["count"] = int(metrics["count"])
        if "avg_conf" in metrics:
            detection["avg_conf"] = round(metrics["avg_conf"], 4)
        drought = {}
        for k in ("drought_rate", "drought_count", "control_count"):
            if k in metrics:
                drought[k] = metrics[k]
        return {
            "detection": detection,
            "drought": drought,
            "risk_analysis": text,
            "suggestions": "",
        }

    # ---------------- 主入口 ----------------

    def run(self, data=None, content="", format="md", title=None, filename=None,
            *args, **kwargs):
        # 兼容 run(input="...") / run("文本")
        if not content and "input" in kwargs:
            content = kwargs.get("input")
        if not content and args:
            content = str(args[0])
        if isinstance(data, dict) and data.get("content") and not content:
            content = data["content"]

        report_data = self._build_report_data(data, content)
        if not report_data.get("detection") and not report_data.get("drought") \
                and not report_data.get("risk_analysis"):
            return "❌ 报告生成失败: 缺少监测数据（请提供 data 或 content）"

        try:
            out = self.report_tool.run(data=report_data, format=format,
                                       title=title, filename=filename)
            self.last_report = json.loads(out) if isinstance(out, str) else out
        except Exception as e:
            return f"❌ 报告生成失败: {e}"
        return out

    @property
    def last_report(self) -> Dict[str, Any]:
        return getattr(self, "_last_report", {})

    @last_report.setter
    def last_report(self, value):
        self._last_report = value
