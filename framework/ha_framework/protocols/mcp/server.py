# -*- coding: utf-8 -*-
"""
Hello-Agents MCP 服务器（MCPServer）s

基于已安装的 mcp SDK 内置 FastMCP（mcp.server.fastmcp.FastMCP）做薄封装，
对外提供与文档一致的接口：
- add_tool(fn)            注册普通函数为工具（weather 服务器示例用法）
- tool()/resource()/prompt()  装饰器透传
- run()                   以 stdio 方式启动服务器
- _mcp_server             供 Memory 传输（进程内）复用
"""

from typing import Any, Callable, Optional

from mcp.server.fastmcp import FastMCP


class MCPServer:
    """MCP 服务器 - FastMCP 封装（对齐文档 MCPServer）"""

    def __init__(
            self,
            name: str,
            description: str = "",
            **kwargs: Any,
    ):
        # FastMCP 第一个位置参数是服务器名称
        self._server = FastMCP(name, **kwargs)
        self.name = name
        self.description = description

    # ---------------- 工具注册 ----------------

    def add_tool(self, fn: Callable, name: Optional[str] = None, **kwargs):
        """
        注册普通函数为 MCP 工具。

        文档用法（weather 服务器）：
            weather_server.add_tool(get_weather)
            weather_server.add_tool(list_supported_cities)
        """
        return self._server.add_tool(fn, name=name, **kwargs)

    def tool(self, name: Optional[str] = None, **kwargs):
        """
        装饰器：@server.tool()
        等价于 FastMCP 的 @mcp.tool()
        """
        return self._server.tool(name=name, **kwargs)

    def resource(self, uri: str, **kwargs):
        """装饰器：@server.resource("uri")"""
        return self._server.resource(uri, **kwargs)

    def prompt(self, name: Optional[str] = None, **kwargs):
        """装饰器：@server.prompt()"""
        return self._server.prompt(name=name, **kwargs)

    # ---------------- 运行 ----------------

    def run(self, transport: str = "stdio", **kwargs):
        """
        启动 MCP 服务器（默认 stdio 传输）。

        文档用法（weather 服务器）：
            if __name__ == "__main__":
                weather_server.run()
        """
        return self._server.run(transport=transport, **kwargs)

    @property
    def _mcp_server(self):
        """底层 FastMCP 服务器对象，供 Memory 传输复用"""
        return self._server._mcp_server

    def __repr__(self):
        return f"MCPServer(name={self.name!r}, tools={len(self._server._tool_manager._tools)})"
