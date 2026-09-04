# -*- coding: utf-8 -*-
"""
Hello-Agents MCP 协议模块
对齐文档第十章 10.1.4 protocols/mcp/

导出：MCPClient / MCPServer
内置：演示服务器（MCPTool 默认连接，Memory 传输）
"""

import platform

from mcp.server.fastmcp import FastMCP

from .client import MCPClient
from .server import MCPServer

__all__ = ["MCPClient", "MCPServer"]

# ---------------- 内置演示服务器 ----------------

_demo_server = None


def get_demo_server() -> FastMCP:
    """
    内置演示服务器（计算器 + 系统信息），MCPTool() 默认连接（Memory 传输）。

    提供 6 个工具（对齐文档 10.2.4）：
        add / subtract / multiply / divide / greet / get_system_info
    """
    global _demo_server
    if _demo_server is not None:
        return _demo_server

    demo = FastMCP("demo-server")

    @demo.tool()
    def add(a: float, b: float) -> float:
        """加法计算器：计算 a + b"""
        return a + b

    @demo.tool()
    def subtract(a: float, b: float) -> float:
        """减法计算器：计算 a - b"""
        return a - b

    @demo.tool()
    def multiply(a: float, b: float) -> float:
        """乘法计算器：计算 a * b"""
        return a * b

    @demo.tool()
    def divide(a: float, b: float) -> float:
        """除法计算器：计算 a / b"""
        if b == 0:
            raise ValueError("除数不能为零")
        return a / b

    @demo.tool()
    def greet(name: str) -> str:
        """友好问候"""
        return f"你好，{name}！很高兴见到你 👋"

    @demo.tool()
    def get_system_info() -> str:
        """获取系统信息"""
        import datetime
        info = {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return f"系统: {info['platform']}\nPython: {info['python']}\n时间: {info['time']}"

    _demo_server = demo
    return demo
