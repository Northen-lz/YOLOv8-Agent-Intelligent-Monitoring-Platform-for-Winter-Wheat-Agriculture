# -*- coding: utf-8 -*-
"""
ManagerAgent —— 多 Agent 协作编排层（YOLOv8-Agent 平台大脑）

将 5 个领域子 Agent（wheat_vision / agriculture_expert / analysis / report / author）
经 AgentTool 注册为可函数调用调度的工具。基于用户请求：
- 图片/检测请求 → 调度 wheat_vision，必要时串联 analysis
- 农业知识问题 → 调度 agriculture_expert
- 报告生成     → 调度 wheat_vision / analysis → report
- 开发者介绍   → 调度 author
最后由 Manager 汇总为最终回答。
"""

from ..core.llm import HelloAgentsLLM
from ..core.message import Message
from ..tools.registry import ToolRegistry
from ..tools.agent_tool import AgentTool
from .function_call_agent import FunctionCallingAgent
from .wheat_agent import WheatVisionAgent
from .agriculture_agent import AgricultureExpertAgent
from .analysis_agent import AnalysisAgent
from .report_agent import ReportAgent
from .author_agent import AuthorAgent

MANAGER_GUIDANCE = """你是「YOLOv8-Agent 农业智能监测平台」的总调度智能体，负责把用户请求分配给最合适的领域子 Agent，并汇总为最终回答。

子 Agent 分工：
- wheat_vision: 对田间图片做 YOLOv8 检测 + 干旱分类，返回株数/置信度/干旱率与自然语言分析。需要图片路径 image_path。
- agriculture_expert: 农业领域知识问答（冬小麦生长周期/干旱胁迫/YOLOv8 原理/产量管理等），以及城市实时天气查询（内部会调用天气 MCP 工具获取实时天气，需联网）。
- analysis: 综合检测与干旱结果，给出综合评价与建议。
- report: 生成《冬小麦智能监测报告》（md/docx/pdf）。需先有分析内容作为 content，format 传 "all" 可同时生成三种格式。
- author: 介绍系统开发者、项目技术路线、技术栈。

调度规则：
1. 用户给出图片路径或要求"分析图片/检测"→ 调用 wheat_vision(image_path=图片路径)；若还要求评价或建议，把其结果继续交给 analysis。
2. 用户问"为什么/如何/原理/产量/干旱"等知识问题 → 调用 agriculture_expert。
3. 用户要求"生成报告" → 先调用 wheat_vision（或 analysis）拿到结果，再把结果文本作为 report 的 content 调用 report。
4. 用户问"开发者/作者/技术栈/项目" → 调用 author。
5. 用户询问"某城市天气/气温/降雨/湿度" → 调用 agriculture_expert（把用户问题文本作为输入），由其内部天气工具返回实时天气，禁止直接编造天气数据。
6. 不需要工具时直接回答。

多步调用时，请把上一步工具的结果带入下一步的参数。"""


class ManagerAgent(FunctionCallingAgent):

    description = "总调度 Agent：根据用户请求调用视觉/知识/分析/报告/作者子 Agent"

    def __init__(self, name="manager", llm=None, max_tool_calls=5,
                 wheat_agent=None, expert_agent=None, analysis_agent=None,
                 report_agent=None, author_agent=None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm, tool_registry=ToolRegistry(),
                         max_tool_calls=max_tool_calls)

        # 子 Agent（默认共享 Manager 的 LLM 实例）
        self.wheat_agent = wheat_agent or WheatVisionAgent(llm=llm)
        self.expert_agent = expert_agent or AgricultureExpertAgent(llm=llm)
        self.analysis_agent = analysis_agent or AnalysisAgent(llm=llm)
        self.report_agent = report_agent or ReportAgent(llm=llm)
        self.author_agent = author_agent or AuthorAgent(llm=llm)

        # 注册为可调度的工具
        self.tool_registry.register_tool(AgentTool(
            self.wheat_agent, name="wheat_vision",
            description="对田间图片做 YOLOv8 检测与干旱分类，返回株数/置信度/干旱率与自然语言分析。参数: image_path(必填), conf(可选0.5)"))
        self.tool_registry.register_tool(AgentTool(
            self.expert_agent, name="agriculture_expert",
            description="农业领域知识问答与城市实时天气查询。参数: input(用户问题文本，必填)"))
        self.tool_registry.register_tool(AgentTool(
            self.analysis_agent, name="analysis",
            description="综合检测与干旱结果给出综合评价与建议。参数: input_text(监测结果文本), user_question(可选)"))
        self.tool_registry.register_tool(AgentTool(
            self.report_agent, name="report",
            description="生成《冬小麦智能监测报告》。参数: content(分析结果文本), format(可选 md|docx|pdf|all，all 生成三格式)"))
        self.tool_registry.register_tool(AgentTool(
            self.author_agent, name="author",
            description="介绍系统开发者/项目/技术栈。参数: question(问题)"))

        self.system_prompt = MANAGER_GUIDANCE

    def _system_prompt(self) -> str:
        return (
            MANAGER_GUIDANCE + "\n\n"
            "可用子 Agent 工具:\n" + self.get_tools_description() + "\n"
            "需要调用时返回 JSON：{\"name\":\"工具名\",\"arguments\":{...}}\n"
            "多步任务请逐步返回 JSON（每步一个），不要一次输出多个 JSON。"
        )

    def run(self, user_input, on_step=None):
        self.messages.append(Message(role="user", content=user_input))
        return self._run_multi_call(self._system_prompt(), on_step=on_step)
