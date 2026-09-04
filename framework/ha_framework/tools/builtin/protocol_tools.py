# -*- coding: utf-8 -*-
"""
Hello-Agents 协议工具包装器
对齐文档第十章 10.1.4「工具封装层」：MCPTool / A2ATool / ANPTool

统一继承 BaseTool，提供一致的 run() 方法，让智能体以相同的方式使用三种协议：
- MCPTool   访问 MCP 服务器工具（支持自动展开为独立工具）
- A2ATool   调用远程 A2A 智能体的技能
- ANPTool   服务发现 / 注册 / 负载均衡
"""

import asyncio
import re
from typing import Any, Dict, List, Optional

from ...protocols.anp import ANPDiscovery
from ...protocols.a2a.implementation import A2AClient
from ...protocols.mcp.client import MCPClient
from ...protocols.mcp.utils import create_context, parse_context
from ..base import BaseTool, ToolParameter

# ================================================================
# MCP 工具
# ================================================================


class MCPTool(BaseTool):
    """
    MCP 工具包装器。

    文档用法：
        # 方式1：内置演示服务器（Memory 传输，无需配置）
        mcp_tool = MCPTool()
        result = mcp_tool.run({
            "action": "call_tool", "tool_name": "add",
            "arguments": {"a": 10, "b": 20}
        })

        # 方式2：连接外部 MCP 服务器（stdio）
        fs_tool = MCPTool(
            name="filesystem",
            description="访问本地文件系统",
            server_command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "."]
        )

    自动展开：MCPTool 添加到 Agent 时（add_tool），会把服务器提供的所有工具
    展开为独立工具（前缀 {name}_），例如 calculator_add / calculator_multiply。
    """

    def __init__(
            self,
            name: str = "mcp",
            description: str = "MCP工具 - 访问外部工具和资源",
            server_command: Optional[List[str]] = None,
            server=None,
    ):
        super().__init__(name=name, description=description)
        self.server_command = server_command
        # 传输方式：
        # - server 提供 → Memory 传输（进程内 FastMCP/MCPServer，零外部进程）
        # - server_command 提供 → stdio 传输（子进程拉起外部服务器）
        # - 都没有 → 内置演示服务器（Memory 传输）
        self.server = server
        self._transport = "stdio" if server_command else "memory"

    # ---------------- 客户端构建 ----------------

    def _make_client(self) -> MCPClient:
        if self._transport == "stdio":
            return MCPClient(server_command=list(self.server_command))
        if self.server is not None:
            return MCPClient(server=self.server)
        from ...protocols.mcp import get_demo_server
        return MCPClient(server=get_demo_server())

    async def _connect_and(self, action: str, **params) -> Any:
        """异步连接服务器并执行操作"""
        client = self._make_client()
        try:
            async with client:
                if action == "list_tools":
                    return await client.list_tools()
                if action == "list_resources":
                    return await client.list_resources()
                if action == "read_resource":
                    return await client.read_resource(params.get("uri", ""))
                if action == "list_prompts":
                    return await client.list_prompts()
                if action == "get_prompt":
                    return await client.get_prompt(
                        params.get("name", ""), params.get("arguments", {})
                    )
                # 默认 call_tool
                return await client.call_tool(
                    params.get("tool_name", ""),
                    params.get("arguments", {}),
                )
        except Exception as e:
            return f"❌ MCP 调用失败: {e}"

    # ---------------- 统一入口 ----------------

    def run(self, *args, **kwargs) -> str:
        """
        执行 MCP 操作（对齐文档：run({"action": ..., ...})）。

        支持操作：
        - list_tools / list_resources / list_prompts     发现
        - call_tool / read_resource / get_prompt         调用
        """
        if args and isinstance(args[0], dict):
            params = dict(args[0])
        else:
            params = dict(kwargs)
        action = params.pop("action", "call_tool")
        result = asyncio.run(self._connect_and(action, **params))

        # 结果格式化
        if action == "list_tools":
            return create_context(result)
        if action == "list_resources":
            return "\n".join(
                f"- {r['uri']}: {r['name']} {r['description']}" for r in result
            ) or "暂无资源"
        if action == "list_prompts":
            return "\n".join(f"- {p['name']}: {p['description']}" for p in result) or "暂无提示"
        return parse_context(result)

    # ---------------- 自动展开 ----------------

    def _fetch_tools(self) -> List[Dict[str, Any]]:
        """连接服务器获取工具列表（供 expand 使用）"""
        result = asyncio.run(self._connect_and("list_tools"))
        if isinstance(result, str) and result.startswith("❌"):
            return []
        return result

    def expand(self) -> List["_ExpandedMCPTool"]:
        """
        自动展开：把服务器提供的所有工具展开为独立工具。
        由 Agent.add_tool() 检测到 expand() 时自动调用。
        """
        tools = self._fetch_tools()
        expanded = []
        for tool in tools:
            expanded.append(_ExpandedMCPTool(
                parent=self,
                server_tool_name=tool.get("name", ""),
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", {}) or {},
            ))
        return expanded

    def _call_tool(self, server_tool_name: str, arguments: Dict[str, Any]) -> str:
        """展开工具调用的内部入口（同步）"""
        result = asyncio.run(self._connect_and(
            "call_tool", tool_name=server_tool_name, arguments=arguments,
        ))
        if isinstance(result, str) and result.startswith("❌"):
            return result
        return parse_context(result)


class _ExpandedMCPTool(BaseTool):
    """
    MCP 自动展开后的独立工具（用户不可见）。
    name = "{MCPTool.name}_{server工具名}"，如 calculator_add。
    根据服务器 inputSchema 自动转换参数类型（文档：字符串 → 数值）。
    """

    def __init__(
            self,
            parent: MCPTool,
            server_tool_name: str,
            description: str,
            input_schema: Dict[str, Any],
    ):
        self._parent = parent
        self._server_tool_name = server_tool_name
        self._schema = input_schema or {}
        super().__init__(
            name=f"{parent.name}_{server_tool_name}",
            description=description or f"MCP工具 {server_tool_name}",
        )

    # ---------------- 参数定义 ----------------

    def get_parameters(self) -> List[ToolParameter]:
        """根据 MCP 服务器的 inputSchema 生成参数定义"""
        props = self._schema.get("properties") or {}
        required = set(self._schema.get("required") or [])
        params = []
        for pname, pinfo in props.items():
            if isinstance(pinfo, dict):
                ptype = pinfo.get("type", "string")
                pdesc = pinfo.get("description", "")
            else:
                ptype, pdesc = "string", ""
            # JSON Schema 类型 → 本地 ToolParameter 类型
            local_type = {
                "string": "string",
                "integer": "number",
                "number": "number",
                "boolean": "boolean",
                "array": "array",
                "object": "object",
            }.get(ptype, "string")
            params.append(ToolParameter(
                name=pname,
                type=local_type,
                description=pdesc,
                required=pname in required,
            ))
        return params

    # ---------------- 类型转换 ----------------

    def _convert_types(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """按 inputSchema 的类型定义做字符串→数值等类型转换"""
        props = self._schema.get("properties") or {}
        converted = {}
        for key, value in params.items():
            pinfo = props.get(key) or {}
            ptype = pinfo.get("type", "string") if isinstance(pinfo, dict) else "string"
            if ptype == "number" and isinstance(value, str):
                converted[key] = float(value)
            elif ptype == "integer" and isinstance(value, str):
                converted[key] = int(float(value))
            elif ptype == "boolean" and isinstance(value, str):
                converted[key] = value.strip().lower() in ("true", "1", "yes", "是")
            else:
                converted[key] = value
        return converted

    def _resolve_positional(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        兼容位置传参（对齐文档 10.2.4）：
        SimpleAgent 把 [TOOL_CALL:xxx:123+456] 解析为 {"input": "123+456"}，
        此时参数名不在 schema 中 → 按 schema 参数顺序提取数字填充。
        如 add(a, b) 的 schema → {"a": "123", "b": "456"}。
        """
        props = self._schema.get("properties") or {}
        if not props:
            return params
        if any(k in props for k in params):
            return params  # 已有命名参数，无需解析
        # 取唯一字符串值（位置表达式）
        source = ""
        for v in params.values():
            if isinstance(v, str):
                source = v
                break
        # 单字符串参数：把原文直接映射到该参数（如 greet(name) ← "你好2024"）。
        # 必须先于数值提取分支，否则含数字的原文会被截断成纯数字。
        if len(props) == 1 and source:
            name = next(iter(props))
            pinfo = props[name]
            if isinstance(pinfo, dict) and pinfo.get("type") == "string":
                return {name: source}
        # 数值型参数：提取数字按 schema 顺序填充（如 add(a,b) ← "123+456"）
        nums = re.findall(r"\d+(?:\.\d+)?", source)
        if len(nums) >= len(props):
            for i, name in enumerate(props.keys()):
                params[name] = nums[i]
            return {k: v for k, v in params.items() if k in props}
        # 只保留 schema 定义的参数（丢弃 "input" 占位）
        return {k: v for k, v in params.items() if k in props}

    def run(self, *args, **kwargs) -> str:
        """执行 MCP 工具调用"""
        if args and isinstance(args[0], dict):
            params = dict(args[0])
        elif args and isinstance(args[0], str) and not kwargs:
            # 裸字符串位置参数（如 weather_get_weather_by_city(北京)）：
            # 用占位键交给 _resolve_positional 按 schema 映射到唯一 string 参数
            params = {"_pos": args[0]}
        else:
            params = dict(kwargs)
        params = self._resolve_positional(params)
        converted = self._convert_types(params)
        return self._parent._call_tool(self._server_tool_name, converted)


# ================================================================
# A2A 工具
# ================================================================


class A2ATool(BaseTool):
    """
    A2A 工具包装器 - 调用远程 A2A 智能体的技能。

    文档用法：
        researcher_tool = A2ATool(
            name="researcher",
            description="研究员Agent，可以搜索和分析资料",
            agent_url="http://localhost:5000"
        )
        coordinator.add_tool(researcher_tool)
    """

    def __init__(
            self,
            agent_url: Optional[str] = None,
            name: Optional[str] = None,
            description: Optional[str] = None,
    ):
        super().__init__(
            name=name or "a2a",
            description=description or "A2A智能体工具 - 调用远程智能体的技能",
        )
        self.agent_url = agent_url
        self._client = A2AClient(agent_url) if agent_url else None

    def run(self, *args, **kwargs) -> str:
        """向 A2A 智能体发送文本请求（自动路由到合适的技能）"""
        if not self._client:
            return "❌ A2ATool 未指定 agent_url"

        # 提取文本：兼容 run("文本") / run({"text": ...}) / run({"query": ...}) /
        # run({"action": "ask", "query": ...}) 等
        text = ""
        if args:
            text = args[0] if isinstance(args[0], str) else ""
            if isinstance(args[0], dict):
                params = args[0]
                text = (
                    params.get("text")
                    or params.get("query")
                    or params.get("input")
                    or params.get("message")
                    or ""
                )
        if not text and kwargs:
            params = kwargs
            text = (
                params.get("text")
                or params.get("query")
                or params.get("input")
                or params.get("message")
                or ""
            )
        if not text:
            return "❌ 请提供要发送给 A2A 智能体的文本"

        try:
            result = self._client.execute(text)
        except Exception as e:
            return f"❌ A2A 调用失败: {e}"
        return result.get("result", str(result))


# ================================================================
# ANP 工具
# ================================================================


class ANPTool(BaseTool):
    """
    ANP 工具包装器 - 服务发现 / 注册 / 负载均衡。

    文档用法：
        anp_tool = ANPTool(
            name="service_discovery",
            description="服务发现工具，可以查找和选择计算节点",
            discovery=discovery
        )
        scheduler.add_tool(anp_tool)

    支持操作：
    - register_service:   注册服务
    - discover_services:  发现服务（按 service_type）
    - select_best_server: 选择负载最低的服务器（负载均衡）
    - get_stats:          服务发现中心统计
    - list_services:      列出所有服务
    """

    def __init__(
            self,
            name: str = "service_discovery",
            description: str = "服务发现工具，可以查找和选择计算节点",
            discovery: Optional[ANPDiscovery] = None,
    ):
        super().__init__(name=name, description=description)
        self.discovery = discovery if discovery is not None else ANPDiscovery()

    def run(self, *args, **kwargs) -> str:
        """执行 ANP 操作（对齐文档：run({"action": ..., ...})）"""
        if args and isinstance(args[0], dict):
            params = dict(args[0])
        else:
            params = dict(kwargs)
        action = params.pop("action", "discover_services")

        handlers = {
            "register_service": self._register_service,
            "discover_services": self._discover_services,
            "select_best_server": self._select_best_server,
            "get_stats": self._get_stats,
            "list_services": self._list_services,
        }
        handler = handlers.get(action)
        if handler is None:
            return (f"❌ 未知操作: {action}"
                    "（支持 register_service / discover_services / "
                    "select_best_server / get_stats / list_services）")
        return handler(**params)

    # ---------------- 操作实现 ----------------

    def _register_service(
            self,
            service_id: str,
            service_type: str,
            endpoint: str,
            service_name: Optional[str] = None,
            capabilities: Optional[List[str]] = None,
            metadata: Optional[Dict[str, Any]] = None,
            **kwargs,
    ) -> str:
        """注册服务"""
        service = self.discovery.add_service(
            service_id=service_id,
            service_name=service_name or f"{service_id}",
            service_type=service_type,
            capabilities=capabilities,
            endpoint=endpoint,
            metadata=metadata,
        )
        return (f"✅ 服务已注册: {service.service_name} "
                f"(id={service.service_id}, type={service.service_type})")

    def _discover_services(self, service_type: Optional[str] = None, **kwargs) -> str:
        """发现服务"""
        services = self.discovery.discover_services(service_type=service_type)
        if not services:
            return (f"😕 未找到任何服务"
                    + (f"（type={service_type}）" if service_type else ""))
        lines = [f"🔍 发现 {len(services)} 个服务:"]
        for s in services:
            load = s.metadata.get("load", "-")
            lines.append(
                f"- [{s.service_id}] {s.service_name} "
                f"(type={s.service_type}, endpoint={s.endpoint}, load={load})"
            )
        return "\n".join(lines)

    def _select_best_server(
            self, service_type: Optional[str] = None, **kwargs
    ) -> str:
        """选择负载最低的服务器（对齐文档 10.4.2 负载均衡）"""
        services = self.discovery.discover_services(service_type=service_type)
        if not services:
            return (f"😕 未找到任何服务"
                    + (f"（type={service_type}）" if service_type else ""))
        best = min(services, key=lambda s: s.metadata.get("load", 0))
        return (f"🎯 已选择负载最低的服务器: [{best.service_id}] "
                f"{best.service_name} (load={best.metadata.get('load')}, "
                f"endpoint={best.endpoint})")

    def _get_stats(self, **kwargs) -> str:
        """服务发现中心统计"""
        stats = self.discovery.stats()
        by_type = stats["by_type"] or {}
        type_str = ", ".join(f"{k}={v}" for k, v in by_type.items()) or "无"
        return f"📊 服务发现中心: 共 {stats['total_services']} 个服务 ({type_str})"

    def _list_services(self, **kwargs) -> str:
        """列出所有服务"""
        services = self.discovery.list_all_services()
        if not services:
            return "😕 暂无服务注册"
        return "\n".join(
            f"- [{s.service_id}] {s.service_name} (type={s.service_type})"
            for s in services
        )
