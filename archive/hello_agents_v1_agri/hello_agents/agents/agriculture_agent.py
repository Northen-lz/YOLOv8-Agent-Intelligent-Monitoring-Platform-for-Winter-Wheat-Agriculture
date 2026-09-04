# -*- coding: utf-8 -*-
"""
AgricultureExpertAgent —— 农业知识专家 Agent

基于 ReAct 推理循环回答农业领域问题：
- 为什么冬小麦会发生干旱？
- YOLOv8 为什么适合植物检测？
- 如何提高冬小麦产量？
通过 AgricultureKnowledgeTool 检索知识库，结合 LLM 组织答案。
"""

import os
import sys

from ..core.config import Config
from ..core.llm import HelloAgentsLLM
from ..tools.agriculture.agriculture_mcp_server import build_agriculture_server
from ..tools.agriculture.knowledge_tool import AgricultureKnowledgeTool
from ..tools.agriculture.experiment_tool import ExperimentAnalysisTool
from ..tools.builtin.calculator import CalculatorTool
from ..tools.builtin.image_caption_tool import ImageCaptionTool
from ..tools.builtin.memory_tool import MemoryTool
from ..tools.builtin.note_tool import NoteTool
from ..tools.builtin.protocol_tools import MCPTool
from ..tools.builtin.rag_tool import RAGTool
from ..tools.builtin.terminal_tool import TerminalTool
from ..tools.registry import ToolRegistry
from .react_agent import ReActAgent

EXPERT_SYSTEM_PROMPT = (
    "你是一名农业智能监测领域的知识专家，擅长冬小麦种植、干旱胁迫、"
    "计算机视觉（YOLOv8）与智能体技术。"
    "回答问题时请先检索农业知识库获取依据，再结合自己的理解给出清晰、"
    "有条理、面向农户或农业技术人员的回答。不要编造数据。\n\n"
    "【知识检索路由（强制）】农业知识类问题（生育期/需水/干旱机理/防治等）：\n"
    "- 第一步优先调用 rag 工具做向量语义检索（召回更准）；\n"
    "- 若 rag 返回『Qdrant 服务未连接』或『未检索到相关知识』，"
    "再改用 knowledge_tool 做关键词检索兜底；\n"
    "- 拿到 Observation 中的真实知识片段后再 Answer，引用时标注来源。\n"
    "【强制规则】当用户询问『用了哪些模型 / 哪个检测或分类模型最佳 / 实验对比 / "
    "评估指标 / accuracy / 数据集规模多大』等实验相关问题时：\n"
    "- 第一步必须先输出 Action 调用 experiment_analysis 工具，禁止直接 Answer；\n"
    "- 检测/分类模型相关问题 → Action: experiment_analysis({\"action\":\"models\"})\n"
    "- 分类器评估指标 → Action: experiment_analysis({\"action\":\"eval\"})\n"
    "- 数据集规模 → Action: experiment_analysis({\"action\":\"data\"})\n"
    "- 拿到 Observation 里的真实数据后再 Answer；回答中出现的模型名、指标数值、"
    "数据集数量必须来自工具返回或知识库，绝不编造。\n\n"
    "【强制规则】当用户询问『某城市天气 / 气温 / 降雨 / 湿度 / 是否适合灌溉作业』"
    "等实时天气问题时：\n"
    "- 第一步必须先输出且只输出一行 Action：\n"
    "  Action: weather_get_weather_by_city({\"city\": \"城市名\"})\n"
    "  示例：Action: weather_get_weather_by_city({\"city\": \"北京\"})\n"
    "- 在这行 Action 之外禁止输出任何天气数据、禁止编造温度/湿度/风力——"
    "你不掌握实时天气，编造会让农户做出错误决策；\n"
    "- 等 Observation 返回真实天气后，再基于它组织 Answer；"
    "若返回『查询天气失败』，如实告知天气服务当前不可用。\n\n"
    "【增强工具】除知识检索与实验分析外，还可使用：\n"
    "- memory：跨会话记忆。用户说『记住…』『还记得上次…』时，先 action=search 检索已有记忆，再 action=add 保存重要信息。\n"
    "- note：结构化笔记（结论/待办/阻断项），支持 create/read/search；用户说『记个笔记』『我的待办』时调用。\n"
    "- calculator：数学计算、单位换算、面积/产量估算。\n"
    "- terminal：在项目目录内执行只读命令查看文件（ls/cat/grep/find），如查询 outputs/ 下的报告与模型目录。\n"
    "- rag：向量知识库检索（需本机 Qdrant 服务）。若工具返回『Qdrant 服务未连接』，请如实告知用户当前无法做向量检索，并改用 knowledge_tool 知识库。\n"
    "- image_caption：本地视觉模型（Ollama Qwen2.5-VL）图片语义理解。用户上传/提到一张图片并想了解其内容（如照片里有什么、截图/图表的布局与文字、田间作物长势）时调用，返回自然语言描述。需本机 Ollama 服务；若返回『无法连接 Ollama』请如实告知并建议用户先启动 Ollama、拉取 qwen2.5vl:3b。CPU 推理约 30~90 秒。\n"
    "- agri_*（MCP 通信协议工具，第 10 章）：经 MCP 协议访问农业数据服务器。\n"
    "  - agri_query_models：列出全部检测/分类模型并标注最佳（与 experiment_analysis 等价，走 MCP 协议路径）；\n"
    "  - agri_query_eval：分类器真实评估指标（读 CSV）；\n"
    "  - agri_query_data：数据集规模统计；\n"
    "  - agri_search_knowledge：农业知识库关键词检索（query 参数）；\n"
    "  - agri_get_platform_info：平台与环境信息。\n"
    "  【注意】实验/模型/数据类问题优先用 experiment_analysis（更快更全）；当实验用 agri_* 工具时同样可接受——两者数据同源。\n"
    "- weather_get_weather_by_city（MCP 天气服务器，stdio）：查询城市实时天气/气温/湿度。用户问某城市天气/气温/是否适合灌溉作业时调用（city 参数）。需 wttr.in 联网；离线时返回『查询天气失败』，请如实告知。"
)


class AgricultureExpertAgent(ReActAgent):

    def __init__(self, name="agriculture_expert", llm=None, system_prompt=None,
                 knowledge_dir=None):
        if llm is None:
            llm = HelloAgentsLLM()
        registry = ToolRegistry()
        self.knowledge_tool = AgricultureKnowledgeTool(knowledge_dir=knowledge_dir)
        registry.register_tool(self.knowledge_tool)
        self.experiment_tool = ExperimentAnalysisTool()
        registry.register_tool(self.experiment_tool)
        # ---- 第 7-12 章内置通用工具：注册进农业知识专家 ----
        # memory：SQLite 跨会话记忆（Qdrant 未启动时自动降级关键词检索）
        # 语义记忆 semantic（Qdrant+Neo4j 混合检索）已懒加载接入——
        # 之前刻意避开是因其急切构造外部存储；现在惰性构造 + 离线降级，可安全启用。
        self.memory_tool = MemoryTool(
            user_id="agriculture_user",
            memory_types=["working", "episodic", "semantic"],
        )
        registry.register_tool(self.memory_tool)
        # note：结构化笔记（Markdown+YAML，持久化到 outputs/notes）
        self.note_tool = NoteTool(workspace=Config.NOTE_DIR)
        registry.register_tool(self.note_tool)
        # calculator：数学计算
        self.calculator_tool = CalculatorTool()
        registry.register_tool(self.calculator_tool)
        # terminal：项目目录内只读命令（白名单+沙箱）
        self.terminal_tool = TerminalTool(workspace=Config.PROJECT_ROOT)
        registry.register_tool(self.terminal_tool)
        # rag：向量知识库检索（需本机 Qdrant 服务，未启动时返回友好提示）
        self.rag_tool = RAGTool(
            knowledge_base_path=Config.KNOWLEDGE_DIR,
            collection_name="agriculture_kb",
        )
        registry.register_tool(self.rag_tool)
        # image_caption：本地视觉模型（Ollama Qwen2.5-VL）图片语义描述
        # 需本机 Ollama 服务 + qwen2.5vl:3b 模型；未启动时返回友好提示
        self.image_caption_tool = ImageCaptionTool()
        registry.register_tool(self.image_caption_tool)
        # ---- 第 10 章通信协议：MCP 工具（Memory 传输 + stdio 双服务器）----
        # ReActAgent 不像 SimpleAgent.add_tool 那样自动展开 MCPTool，需手动 expand 注册。
        # 1) 农业自定义 MCP（Memory 传输，进程内直连，零外部依赖）：
        #    把平台已有能力（模型/评估/数据集/知识库）协议化为 agri_* 工具。
        # 2) 天气 MCP（stdio 拉起 tools/agriculture/weather_mcp_server.py）：weather_get_weather_by_city，
        #    需 wttr.in 联网；服务器启动失败/离线时展开跳过，不影响其他工具。
        try:
            self.agri_mcp = MCPTool(
                name="agri",
                description="农业数据 MCP 服务器（模型清单/评估指标/数据集规模/知识库检索）",
                server=build_agriculture_server(),
            )
            for t in self.agri_mcp.expand():
                registry.register_tool(t)
            print(f"✅ 农业 MCP 服务器已展开 {len(registry.list_all()) - 8} 个 agri_* 工具")
        except Exception as e:
            print(f"⚠️ 农业 MCP 展开失败（不影响其他工具）: {e}")
        try:
            weather_script = os.path.join(
                Config.PROJECT_ROOT, "hello_agents", "tools", "agriculture", "weather_mcp_server.py")
            self.weather_mcp = MCPTool(
                name="weather",
                description="天气查询 MCP 服务器（城市实时天气/气温/湿度）",
                server_command=[sys.executable, weather_script],
            )
            for t in self.weather_mcp.expand():
                registry.register_tool(t)
            print("✅ 天气 MCP 服务器已展开 weather_get_weather_by_city 工具")
        except Exception as e:
            print(f"⚠️ 天气 MCP 展开失败（不影响其他工具）: {e}")
        super().__init__(name=name, llm=llm,
                         system_prompt=system_prompt or EXPERT_SYSTEM_PROMPT,
                         tool_registry=registry)
        # ReAct 提示中已包含工具描述
