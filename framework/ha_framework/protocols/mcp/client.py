# -*- coding: utf-8 -*-
"""
Hello-Agents MCP 客户端（MCPClient）

基于已安装的 mcp SDK 官方客户端 API 实现，支持 5 种传输方式（表 10.4）：
- memory            内存传输（单元测试 / 内置演示服务器）
- stdio             标准输入输出传输（本地开发）
- http              远程 HTTP（StreamableHTTP 传输）
- sse               Server-Sent Events 传输
- streamable_http   流式 HTTP 传输

用法（对齐文档）：
    async with MCPClient(["npx", "-y", "@modelcontextprotocol/server-filesystem", "."]) as client:
        tools = await client.list_tools()
        result = await client.call_tool("read_file", {"path": "my_README.md"})
"""

import os
from typing import Any, Dict, List, Optional, Union

from datetime import timedelta

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from .utils import parse_context


class MCPClient:
    """MCP 客户端 - 支持多种传输方式的统一接口"""

    def __init__(
            self,
            server_command: Optional[Union[list, str]] = None,
            url: Optional[str] = None,
            transport_type: Optional[str] = None,
            server: Any = None,
            **kwargs: Any,
    ):
        """
        Args:
            server_command: 启动服务器的命令列表（stdio 传输）
                MCPClient(["python", "my_mcp_server.py"])
                MCPClient(["npx", "-y", "@modelcontextprotocol/server-filesystem", "."])
            url: 远程服务器地址（http / sse / streamable_http 传输）
            transport_type: 显式指定传输方式
                "memory" / "stdio" / "http" / "sse" / "streamable_http"
            server: 进程内 FastMCP/MCPServer 实例（memory 传输，内置演示服务器用）
        """
        self.server_command = server_command
        self.url = url
        self.server = server

        # 传输方式自动判定
        if transport_type:
            self.transport_type = transport_type
        elif server is not None:
            self.transport_type = "memory"
        elif isinstance(server_command, (list, tuple)):
            self.transport_type = "stdio"
        elif url is not None:
            self.transport_type = "http"
        else:
            self.transport_type = "memory"

        self._transport_ctx = None      # 底层传输上下文（stdio/http/sse/memory）
        self._session_ctx = None        # ClientSession 上下文（外部传输需要）
        self._session: Optional[ClientSession] = None

    # ---------------- 连接管理 ----------------

    async def __aenter__(self):
        if self.transport_type == "memory":
            # 进程内会话（已自动初始化）
            mcp_server = self.server
            if mcp_server is None:
                # 缺省：内置演示服务器（MCPTool 默认传入）
                from . import get_demo_server
                mcp_server = get_demo_server()
            # 兼容 MCPServer 包装 / 原生 FastMCP / 底层 Server
            raw = getattr(mcp_server, "_mcp_server", mcp_server)
            self._transport_ctx = create_connected_server_and_client_session(raw)
        elif self.transport_type == "stdio":
            command = self.server_command[0] if isinstance(self.server_command, list) else "python"
            args = self.server_command[1:] if isinstance(self.server_command, list) else []
            env = dict(os.environ)
            # Windows 下保证 UTF-8 编码，避免中文内容乱码
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUNBUFFERED", "1")
            params = StdioServerParameters(command=command, args=args, env=env)
            self._transport_ctx = stdio_client(params)
        elif self.transport_type in ("http", "streamable_http"):
            self._transport_ctx = streamable_http_client(self.url)
        elif self.transport_type == "sse":
            self._transport_ctx = sse_client(self.url)
        else:
            raise ValueError(f"不支持的传输方式: {self.transport_type}")

        entered = await self._transport_ctx.__aenter__()

        if self.transport_type == "memory":
            # memory 传输直接产出已初始化的 ClientSession
            self._session = entered
        else:
            # stdio/http/sse 产出 (read, write) 流，需用 ClientSession 包裹
            read_stream, write_stream = entered
            self._session_ctx = ClientSession(
                read_stream, write_stream,
                read_timeout_seconds=timedelta(seconds=30),
            )
            self._session = await self._session_ctx.__aenter__()
            await self._session.initialize()
        return self

    async def __aexit__(self, *exc):
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(*exc)
            self._session_ctx = None
        if self._transport_ctx is not None:
            await self._transport_ctx.__aexit__(*exc)
            self._transport_ctx = None
        self._session = None

    async def close(self):
        """关闭连接"""
        await self.__aexit__(None, None, None)

    # ---------------- 工具（Tools） ----------------

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        发现服务器提供的所有工具。

        返回: [{"name": str, "description": str, "inputSchema": {...}}, ...]
        """
        result = await self._session.list_tools()
        tools = result.tools if hasattr(result, "tools") else result
        return [
            {
                "name": getattr(t, "name", "?"),
                "description": getattr(t, "description", "") or "",
                "inputSchema": getattr(t, "inputSchema", {}) or {},
            }
            for t in tools
        ]

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """
        调用工具（标准化接口）。

        文档用法：
            result = await client.call_tool("read_file", {"path": "my_README.md"})
        """
        result = await self._session.call_tool(name, arguments or {})
        if getattr(result, "isError", False):
            error_text = parse_context(result)
            raise RuntimeError(f"工具 '{name}' 执行失败: {error_text}")
        return parse_context(result)

    # ---------------- 资源（Resources） ----------------

    async def list_resources(self) -> List[Dict[str, Any]]:
        """列出可用资源"""
        result = await self._session.list_resources()
        resources = result.resources if hasattr(result, "resources") else result
        return [
            {
                "uri": str(getattr(r, "uri", "")),
                "name": getattr(r, "name", "") or "",
                "description": getattr(r, "description", "") or "",
            }
            for r in resources
        ]

    async def read_resource(self, uri: str) -> str:
        """读取资源内容"""
        result = await self._session.read_resource(uri)
        return parse_context(result)

    # ---------------- 提示（Prompts） ----------------

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """列出可用提示模板"""
        result = await self._session.list_prompts()
        prompts = result.prompts if hasattr(result, "prompts") else result
        return [
            {
                "name": getattr(p, "name", "?"),
                "description": getattr(p, "description", "") or "",
            }
            for p in prompts
        ]

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """获取提示模板内容"""
        result = await self._session.get_prompt(name, arguments or {})
        messages = getattr(result, "messages", None)
        if messages is None:
            return parse_context(result)
        # 拼接每条 prompt 消息内容
        parts = []
        for msg in messages:
            content = getattr(msg, "content", None)
            if content is not None and hasattr(content, "text"):
                parts.append(content.text)
        return "\n".join(parts)

    def __repr__(self):
        return f"MCPClient(transport={self.transport_type!r})"
