# -*- coding: utf-8 -*-
"""
农业自定义 MCP 服务器（Memory 传输，进程内）

把 YOLOv8-Agent 平台**已有能力**包装成 MCP 工具（对齐文档第十章 10.2.4），
供 MCPTool 以 Memory 传输（进程内直连）访问，零外部依赖、不联网、无子进程。

接入方式（AgricultureExpertAgent）：
    MCPTool(name="agri", description=..., server=build_agriculture_server())
    → MCPTool.expand() 自动展开为 agri_query_models / agri_query_eval /
      agri_query_data / agri_search_knowledge / agri_get_platform_info 独立工具

工具实现**复用** ExperimentAnalysisTool / AgricultureKnowledgeTool，
不重复实现读取逻辑，仅做薄封装，让同一能力可同时经"平台工具"与"MCP 协议"两条路径调用。
"""

import platform
import sys

from mcp.server.fastmcp import FastMCP

from .experiment_tool import ExperimentAnalysisTool
from .knowledge_tool import AgricultureKnowledgeTool


def build_agriculture_server() -> FastMCP:
    """
    构建农业 MCP 服务器（懒加载工具实例，进程内 FastMCP 对象）。

    提供 5 个工具：
        query_models        复用 ExperimentAnalysisTool.models()   模型清单 + 最佳标注
        query_eval          复用 ExperimentAnalysisTool.eval_results()  分类评估 CSV
        query_data          复用 ExperimentAnalysisTool.data_summary()  数据集规模
        search_knowledge    复用 AgricultureKnowledgeTool.search(query) 知识库检索
        get_platform_info   平台 / 环境信息（纯字符串）
    """
    agri = FastMCP("agriculture-server")

    # 复用已有工具实例（懒创建：首次调用才实例化，避免构造成本）
    _exp = None
    _kb = None

    def _exp_tool() -> ExperimentAnalysisTool:
        nonlocal _exp
        if _exp is None:
            _exp = ExperimentAnalysisTool()
        return _exp

    def _kb_tool() -> AgricultureKnowledgeTool:
        nonlocal _kb
        if _kb is None:
            _kb = AgricultureKnowledgeTool()
        return _kb

    @agri.tool()
    def query_models() -> str:
        """列出平台全部检测/分类模型并标注最佳（读真实模型目录，不加载模型）"""
        return _exp_tool().models()

    @agri.tool()
    def query_eval() -> str:
        """读取分类器真实评估指标（outputs/classifier_model_comparison.csv）"""
        return _exp_tool().eval_results()

    @agri.tool()
    def query_data() -> str:
        """统计各数据集图片规模（检测/分类训练验证集）"""
        return _exp_tool().data_summary()

    @agri.tool()
    def search_knowledge(query: str, top_k: int = 3) -> str:
        """在农业知识库（knowledge/*.txt）中按关键词检索知识点"""
        result = _kb_tool().search(query, top_k=top_k)
        results = result.get("results", [])
        if not results:
            return f"知识库中未找到与『{query}』相关的内容，请换个问法。"
        lines = [f"🔍 检索到 {len(results)} 条相关知识（来源 knowledge/）："]
        for i, item in enumerate(results, 1):
            title = item.get("title", "")
            content = item.get("content", "")
            lines.append(f"\n[{i}] {title}")
            if content:
                lines.append(content[:200] + ("..." if len(content) > 200 else ""))
        return "\n".join(lines)

    @agri.tool()
    def get_platform_info() -> str:
        """获取平台与环境信息（名称/版本/运行环境；不暴露完整路径）"""
        return (
            f"平台: YOLOv8-Agent 农业智能监测平台\n"
            f"Python: {platform.python_version()}\n"
            f"系统: {platform.platform()}\n"
            f"项目: HelloAgents\n"
            f"知识库: knowledge"
        )

    return agri
