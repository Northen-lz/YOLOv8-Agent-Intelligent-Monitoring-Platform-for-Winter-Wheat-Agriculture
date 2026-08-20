# -*- coding: utf-8 -*-
"""
第十章 02_Connect2MCP —— 连接 MCP 服务器（memory 传输 + 内置演示服务器）
镜像参考 code/chapter10/02_Connect2MCP.py 的 async with + await 风格。
离线可用。

运行：python examples/ch10/mcp/ch10_mcp_client.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import MCPClient, get_demo_server


async def main():
    print("=" * 56)
    print("连接内置演示 MCP 服务器（memory 传输）")
    print("=" * 56)

    # server=get_demo_server() → 进程内 FastMCP（memory 传输，无需外部进程）
    client = MCPClient(server=get_demo_server())

    async with client:
        # 1. 列出所有工具
        print("\n[1] list_tools")
        tools = await client.list_tools()
        for t in tools:
            print(f"  - {t['name']}: {t['description']}")

        # 2. 调用工具
        print("\n[2] call_tool(calculator)")
        for args in ({"a": 10, "b": 20}, {"a": 7, "b": 3}):
            result = await client.call_tool("add", args)
            print(f"    add({args}) -> {result}")
        result = await client.call_tool("multiply", {"a": 6, "b": 7})
        print(f"    multiply(a=6, b=7) -> {result}")
        result = await client.call_tool("get_system_info", {})
        print(f"    get_system_info() -> {result}")

        # 3. 资源（MCP Resources）
        print("\n[3] list_resources")
        resources = await client.list_resources()
        print(f"    资源数: {len(resources)}")
        for r in resources:
            print(f"    - {r['uri']}: {r['name']}")

        # 4. 提示词模板（MCP Prompts）
        print("\n[4] list_prompts")
        prompts = await client.list_prompts()
        print(f"    提示词数: {len(prompts)}")

    print("\n✅ MCP 客户端连接成功，已断开连接")


if __name__ == "__main__":
    asyncio.run(main())
