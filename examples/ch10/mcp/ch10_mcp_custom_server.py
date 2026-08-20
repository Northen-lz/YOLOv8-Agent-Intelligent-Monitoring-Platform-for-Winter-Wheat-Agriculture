# -*- coding: utf-8 -*-
"""
第十章 自定义 MCP 服务器（镜像参考仓库 my_mcp_server.py，用 MCPServer 封装）
对齐文档 10.1.4：server.add_tool() / @server.tool() / @server.resource() / @server.prompt()

作为 stdio 子进程运行：
    python examples/ch10/mcp/ch10_mcp_custom_server.py

配合 ch10_mcp_custom_client.py 使用（客户端用 stdio 传输拉起本进程）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import MCPServer

# 创建 MCP 服务器（FastMCP 封装）
server = MCPServer("hello-agent-mcp-server", description="我的自定义 MCP 服务器")


@server.tool()
def add(a: float, b: float) -> float:
    """Add two numbers"""
    return a + b


@server.tool()
def subtract(a: float, b: float) -> float:
    """Subtract two numbers"""
    return a - b


@server.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers"""
    return a * b


@server.tool()
def divide(a: float, b: float) -> float:
    """Divide two numbers"""
    if b == 0:
        raise ValueError("除数不能为 0")
    return a / b


# 添加文本工具（对齐文档 my_mcp_server 的 get_time 等思路）
@server.tool()
def say_hello(name: str) -> str:
    """Say hello to someone"""
    return f"你好, {name}！"


# 资源（MCP Resources）：暴露静态信息
@server.resource("config://app")
def get_config() -> str:
    """应用配置信息"""
    return '{"name": "hello-agent-mcp-server", "version": "1.0.0", "author": "HelloAgents"}'


# 提示词模板（MCP Prompts）
@server.prompt()
def summarize_agent(agent_name: str) -> str:
    """生成对智能体的总结提示"""
    return f"请总结一下智能体「{agent_name}」的功能与特性。"


if __name__ == "__main__":
    # stdio 传输启动（被客户端 stdio_client 拉起时不要打印其他内容到 stdout）
    print("🚀 自定义 MCP 服务器已启动（stdio 传输）", file=__import__("sys").stderr)
    server.run()
