# -*- coding: utf-8 -*-
"""
第十章 快速体验：三种通信协议一次跑通（镜像参考 code/chapter10/01_TestConnect.py）
离线可用。

运行：python examples/ch10/ch10_quickstart.py
"""
import asyncio
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import hello_agents
from hello_agents.protocols import (
    A2AClient,
    A2A_AVAILABLE,
    A2AServer,
    ANPDiscovery,
    MCPClient,
    get_demo_server,
)


def test_mcp():
    print("=" * 56)
    print("① MCP —— 连接内置计算器服务器（memory 传输）")
    print("=" * 56)

    async def _run():
        client = MCPClient(server=get_demo_server())
        async with client:
            tools = await client.list_tools()
            result = await client.call_tool("add", {"a": 10, "b": 20})
            return tools, result

    tools, result = asyncio.run(_run())
    print(f"  服务器可用工具: {[t['name'] for t in tools]}")
    print(f"  call_tool(add, a=10, b=20) -> {result}")
    assert "30.0" in str(result), f"期望 30.0，实际 {result}"
    print()


def test_anp():
    print("=" * 56)
    print("② ANP —— 服务注册与发现")
    print("=" * 56)
    discovery = ANPDiscovery()
    discovery.add_service(
        service_id="node-001",
        service_name="计算节点1",
        service_type="compute",
        capabilities=["计算", "运算"],
        endpoint="tcp://10.0.0.1:5000",
        metadata={"load": 10, "location": "北京"},
    )
    discovery.add_service(
        service_id="node-002",
        service_name="计算节点2",
        service_type="compute",
        capabilities=["计算", "存储"],
        endpoint="tcp://10.0.0.2:5000",
        metadata={"load": 30, "location": "上海"},
    )
    result = discovery.discover_services(service_type="compute")
    print(f"  发现 {len(result)} 个 compute 服务:")
    for s in result:
        print(f"    - [{s.service_id}] {s.service_name} @ {s.endpoint} "
              f"(load={s.metadata.get('load')})")
    stats = discovery.stats()
    print(f"  服务发现中心统计: {stats['total_services']} 个服务")
    print()


def test_a2a():
    print("=" * 56)
    print("③ A2A —— 创建智能体服务器（进程内调用技能）")
    print("=" * 56)
    if not A2A_AVAILABLE:
        print("  [轻量模式] a2a-sdk 未安装，使用 stdlib 自实现（等价 API）")

    server = A2AServer(name="calculator", description="A2A计算服务器")

    @server.skill("add")
    def add(text):
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        return str(float(nums[0]) + float(nums[1]))

    @server.skill("greet")
    def greet(text):
        return f"你好, {text}!"

    # 进程内直接执行技能
    result = server.execute_skill("add", "123+456")
    print(f"  execute_skill(add, '123+456') -> {result}")
    # 自动路由（按关键词匹配技能）
    routed = server.execute("请帮我计算 10+20 的结果")
    print(f"  execute('请帮我计算 10+20') -> {routed}")
    print()


if __name__ == "__main__":
    print()
    print("HelloAgents 框架版本:", getattr(hello_agents, "__name__", "hello_agents"))
    print("运行时间:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print()
    test_mcp()
    test_anp()
    test_a2a()
    print("✅ 第十章三种协议全部跑通!")
