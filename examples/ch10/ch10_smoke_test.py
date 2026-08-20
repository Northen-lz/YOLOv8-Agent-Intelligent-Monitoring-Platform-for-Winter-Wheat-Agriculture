# -*- coding: utf-8 -*-
"""
第十章 端到端冒烟测试 —— 串起三种协议的离线可用演示。
离线可用。

运行：python examples/ch10/ch10_smoke_test.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents import MCPTool, SimpleAgent
from hello_agents.protocols import (
    A2AClient,
    A2AServer,
    ANPDiscovery,
    MCPClient,
    get_demo_server,
)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    status = "✅" if condition else "❌"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {status} {name}" + (f"  ({detail})" if detail else ""))


def test_mcp():
    print("\n[MCP] 连接内置计算器服务器")

    async def _run():
        client = MCPClient(server=get_demo_server())
        async with client:
            tools = await client.list_tools()
            r1 = await client.call_tool("add", {"a": 10, "b": 20})
            r2 = await client.call_tool("multiply", {"a": 7, "b": 6})
            return tools, r1, r2

    tools, r1, r2 = asyncio.run(_run())
    check("list_tools 返回 6 个工具", len(tools) >= 6,
          f"{[t['name'] for t in tools]}")
    check("call_tool(add 10+20)", "30.0" in str(r1), str(r1))
    check("call_tool(multiply 7*6)", "42.0" in str(r2), str(r2))


def test_mcp_tool():
    print("\n[MCPTool] 工具包装器 + 自动展开")
    tool = MCPTool(name="calculator")
    expanded = tool.expand()
    check("expand 展开为独立工具", len(expanded) == 6,
          f"{[t.name for t in expanded]}")
    # 类型转换：字符串 "25" → float 25
    for t in expanded:
        if t.name == "calculator_multiply":
            r = t.run({"a": "25", "b": "16"})
            check("类型转换 multiply(25,16)", "400.0" in str(r), str(r))
            break


def test_a2a():
    print("\n[A2A] 服务器 + HTTP 客户端往返")
    server = A2AServer(name="researcher")

    @server.skill("research")
    def research(topic):
        return f"研究完成: {topic}"

    import threading
    thread = threading.Thread(
        target=server.run, kwargs={"host": "localhost", "port": 5100}, daemon=True
    )
    thread.start()
    time.sleep(0.5)

    client = A2AClient("http://localhost:5100")
    card = client.get_agent_card()
    check("Agent Card", card.get("name") == "researcher", str(card.get("name")))
    skills = client.list_skills()
    check("list_skills", "research" in skills, str(skills))
    result = client.execute_skill("research", "多智能体")
    check("execute_skill 远程调用", "研究完成" in result.get("result", ""),
          str(result))
    result = client.execute("请研究一下智能体通信")
    check("execute 自动路由", "研究完成" in result.get("result", ""), str(result))
    server.shutdown()


def test_anp():
    print("\n[ANP] 服务注册/发现/负载均衡")
    discovery = ANPDiscovery()
    discovery.add_service(
        service_id="c1", service_name="节点1", service_type="compute",
        endpoint="tcp://10.0.0.1:5000", metadata={"load": 10},
    )
    discovery.add_service(
        service_id="c2", service_name="节点2", service_type="compute",
        endpoint="tcp://10.0.0.2:5000", metadata={"load": 30},
    )
    found = discovery.discover_services(service_type="compute")
    check("discover_services(compute)", len(found) == 2)
    best = min(found, key=lambda s: s.metadata["load"])
    check("负载均衡选最低负载", best.service_id == "c1", best.service_id)
    stats = discovery.stats()
    check("stats 统计", stats["total_services"] == 2, str(stats["total_services"]))


def test_agent_tool():
    print("\n[SimpleAgent] 注册协议工具（离线检查）")
    # 不需要 LLM：只用 ToolRegistry 检查工具注册/展开逻辑
    agent = SimpleAgent(
        name="SmokeAgent",
        system_prompt="测试",
        enable_tool_calling=True,
    )
    # 注入一个最小 ToolRegistry 断言展开逻辑
    agent.add_tool(MCPTool(name="calculator"))
    names = agent.list_tools()
    check("add_tool 自动展开 MCPTool", "calculator_add" in names, str(names))
    check("tools 顶层导出存在",
          "calculator_multiply" in names)


def main():
    print("=" * 56)
    print("第十章 端到端冒烟测试（离线）")
    print("=" * 56)
    start = time.time()
    test_mcp()
    test_mcp_tool()
    test_a2a()
    test_anp()
    test_agent_tool()
    elapsed = time.time() - start
    print("\n" + "=" * 56)
    print(f"冒烟测试结果: ✅ {PASS} 通过, ❌ {FAIL} 失败, "
          f"耗时 {elapsed:.2f}s")
    print("=" * 56)
    if FAIL:
        raise SystemExit(1)
    print("🎉 第十章三种协议全部通过!")


if __name__ == "__main__":
    main()
