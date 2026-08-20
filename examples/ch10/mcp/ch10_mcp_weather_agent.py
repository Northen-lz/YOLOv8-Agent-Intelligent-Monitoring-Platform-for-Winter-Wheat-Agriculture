# -*- coding: utf-8 -*-
"""
第十章 14_weather_agent —— 天气助手 Agent（SimpleAgent + MCPTool stdio）
镜像参考 code/chapter10/14_weather_agent.py。

需联网 + LLM key（.env 中配置）。

运行：python examples/ch10/mcp/ch10_mcp_weather_agent.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents import MCPTool, SimpleAgent

SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ch10_mcp_weather_server.py",
)


def main():
    print("=" * 56)
    print("天气助手 Agent（SimpleAgent + MCPTool stdio 连接天气服务器）")
    print("=" * 56)

    # ---- 1. 创建 MCPTool（stdio 传输拉起天气服务器） ----
    weather_tool = MCPTool(
        name="weather",
        description="天气查询工具，可以查询城市天气",
        server_command=[__import__("sys").executable, SERVER_SCRIPT],
    )

    # ---- 2. 创建天气助手 Agent ----
    agent = SimpleAgent(
        name="WeatherAgent",
        system_prompt=(
            "你是一个天气助手，可以查询各城市天气。"
            "当用户询问天气时，请调用 weather_get_weather_by_city 工具。"
        ),
        enable_tool_calling=True,
    )
    agent.add_tool(weather_tool)  # 自动展开
    print(f"  ✅ Agent 可用工具: {agent.list_tools()}")

    # ---- 3. 让 LLM 自动调用天气工具 ----
    question = "北京现在天气怎么样？"
    print(f"\n用户问题: {question}\n")
    answer = agent.run(question)
    print("\n" + "=" * 56)
    print("Agent 回答:")
    print(answer)


if __name__ == "__main__":
    main()
