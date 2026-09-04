# -*- coding: utf-8 -*-
"""
Hello-Agents 通信协议模块
对齐文档第十章 10.1.4

三种协议：
- MCP   (Model Context Protocol)   智能体与工具的标准通信
- A2A   (Agent-to-Agent Protocol)  智能体间的点对点协作
- ANP   (Agent Network Protocol)   大规模智能体网络

统一导出：
    from ha_framework.protocols import MCPClient, MCPServer
    from ha_framework.protocols import A2AServer, A2AClient, A2A_AVAILABLE
    from ha_framework.protocols import ANPDiscovery, ANPNetwork, register_service, discover_service
"""

from .a2a import A2A_AVAILABLE, A2AClient, A2AServer
from .anp import ANPDiscovery, ANPNetwork, discover_service, register_service
from .mcp import MCPClient, MCPServer, get_demo_server

__all__ = [
    # MCP
    "MCPClient",
    "MCPServer",
    "get_demo_server",
    # A2A
    "A2AServer",
    "A2AClient",
    "A2A_AVAILABLE",
    # ANP
    "ANPDiscovery",
    "ANPNetwork",
    "register_service",
    "discover_service",
]
