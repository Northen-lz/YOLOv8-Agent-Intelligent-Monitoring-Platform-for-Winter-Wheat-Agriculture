# -*- coding: utf-8 -*-
"""
AnalysisAgent —— 检测结果分析 Agent

输入：YOLO 检测结果 + 干旱预测结果 + 用户问题
输出：综合评价（数量是否正常、是否存在干旱风险）+ 管理建议

支持两种输入形态：
- 结构化: run(detection={...}, drought={...}, user_question="...")
- 文本:    run(input_text="检测...干旱率...", user_question="...")
"""

from typing import Optional

from ..core.llm import HelloAgentsLLM
from ..core.agent import Agent

ANALYSIS_SYSTEM_PROMPT = (
    "你是一名农业监测分析专家。请综合冬小麦检测结果与干旱预测结果，"
    "给出结构化的综合评价与建议，格式如下：\n\n"
    "综合评价：\n当前区域冬小麦数量{正常/偏多/偏少}，"
    "但部分区域存在干旱风险。\n\n"
    "风险分析：\n（结合干旱率说明风险程度与可能原因）\n\n"
    "建议：\n- （可操作管理建议 1）\n- （可操作管理建议 2）\n- （可操作管理建议 3）\n\n"
    "请基于提供的数据作答，不要编造数字。"
)


class AnalysisAgent(Agent):

    def __init__(self, name="analysis", llm=None, system_prompt=None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm,
                         system_prompt=system_prompt or ANALYSIS_SYSTEM_PROMPT)

    @staticmethod
    def _build_input(detection=None, drought=None, input_text="") -> str:
        if input_text:
            return input_text
        parts = []
        if detection:
            parts.append("检测结果:")
            parts.append(f"- 株数: {detection.get('count', '-')}")
            parts.append(f"- 平均置信度: {detection.get('avg_conf', '-')}")
            if detection.get("class_counts"):
                parts.append(f"- 类别分布: {detection['class_counts']}")
        if drought:
            parts.append("干旱预测结果:")
            parts.append(f"- 分类株数: {drought.get('total_classified', '-')}")
            parts.append(f"- 干旱株数: {drought.get('drought_count', '-')}")
            parts.append(f"- 干旱率: {drought.get('drought_rate', '-')}")
        return "\n".join(parts)

    def run(self, detection=None, drought=None, user_question="", input_text="", *args, **kwargs):
        # 兼容 run(input="text")
        if not input_text and "input" in kwargs:
            input_text = kwargs.get("input")
        if not input_text and args:
            input_text = str(args[0])

        data_input = self._build_input(detection, drought, input_text)
        if not data_input.strip():
            return "❌ 分析失败: 请提供检测/干旱结果或文本"

        prompt = (
            f"{'用户问题: ' + str(user_question) + chr(10) if user_question else ''}"
            f"以下是监测数据:\n{data_input}"
        )
        answer = self.llm.chat([{"role": "system", "content": self.system_prompt},
                                {"role": "user", "content": prompt}])
        return str(answer) if answer is not None else f"（分析结果如下）\n{data_input}"
