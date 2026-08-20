# -*- coding: utf-8 -*-
"""
第十章 02_Connect2MCP 后半 —— 用 stdio 传输连接自定义 MCP 服务器
镜像参考仓库 my_mcp_client.py 的 async with + await 风格。

离线可用（以子进程方式拉起 examples/ch10/mcp/ch10_mcp_custom_server.py）。
运行：python examples/ch10/mcp/ch10_mcp_custom_client.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import MCPClient

SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ch10_mcp_custom_server.py",
)


async def main():
    print("=" * 56)
    print("通过 stdio 传输连接自定义 MCP 服务器")
    print("=" * 56)

    # server_command 指定 stdio 子进程（python 运行服务器脚本）
    client = MCPClient(
        server_command=[sys.executable, SERVER_SCRIPT],
    )

    async with client:
        # 1. 工具列表
        print("\n[1] list_tools")
        tools = await client.list_tools()
        for t in tools:
            print(f"  - {t['name']}: {t['description']}")

        # 2. 调用数学工具（safe_tool_call：工具报错不会中断客户端）
        print("\n[2] 数学计算")
        print(f"  add(10, 20)      -> {await client.call_tool('add', {'a': 10, 'b': 20})}")
        try:
            await client.call_tool('divide', {'a': 10, 'b': 0})
        except RuntimeError as e:
            print(f"  divide(10, 0)    -> ❌ {e}")

        # 3. 调用文本工具
        print("\n[3] 文本工具")
        print(f"  say_hello('MCP') -> {await client.call_tool('say_hello', {'name': 'MCP'})}")

        # 4. 读取资源
        print("\n[4] read_resource(config://app)")
        print(f"  -> {await client.read_resource('config://app')}")

        # 5. 获取提示词
        print("\n[5] get_prompt(summarize_agent)")
        print(f"  -> {await client.get_prompt('summarize_agent', {'agent_name': 'MCP服务器'})}")

    print("\n✅ stdio 连接成功，已断开连接")


if __name__ == "__main__":
    asyncio.run(main())
