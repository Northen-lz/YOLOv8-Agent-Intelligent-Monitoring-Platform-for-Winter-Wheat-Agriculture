# -*- coding: utf-8 -*-
"""
第十章 05_UseMCPToolInAgent —— SimpleAgent + MCPTool 自动展开
镜像参考 code/chapter10/05_UseMCPToolInAgent.py。

需联网/LLM key（.env 中配置）。

运行：python examples/ch10/mcp/ch10_mcp_tool_agent.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents import MCPTool, SimpleAgent


def main():
    print("=" * 56)
    print("SimpleAgent + MCPTool（自动展开为独立工具）")
    print("=" * 56)

    # ---- 1. 创建 MCPTool（默认连接内置计算器服务器，memory 传输） ----
    mcp_tool = MCPTool(
        name="calculator",
        description="计算工具，可以进行数学运算",
    )

    # ---- 2. 创建 Agent 并添加工具（自动展开） ----
    agent = SimpleAgent(
        name="CalculatorAgent",
        system_prompt=(
            "你是一个计算智能体，擅长数学计算。"
            "当需要计算时，请调用 calculator_add / calculator_multiply 等工具，"
            "参数格式为命名参数，例如 "
            "[TOOL_CALL:calculator_add:a=123,b=456]。"
        ),
        enable_tool_calling=True,
    )
    agent.add_tool(mcp_tool)  # 触发 expand() 自动展开
    print(f"  ✅ Agent 可用工具: {agent.list_tools()}")

    # ---- 3. 让 LLM 自动调用展开后的工具 ----
    question = "计算 123 + 456 的结果"
    print(f"\n用户问题: {question}\n")
    answer = agent.run(question)
    print("\n" + "=" * 56)
    print("Agent 回答:")
    print(answer)


if __name__ == "__main__":
    main()
