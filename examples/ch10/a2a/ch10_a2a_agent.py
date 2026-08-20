# -*- coding: utf-8 -*-
"""
第十章 10_A2ATool_Simple —— 协调者 Agent + A2ATool 调用远程智能体
镜像参考 code/chapter10/10_A2ATool_Simple.py。

需联网/LLM key（.env 中配置）。A2A 服务器部分在脚本内自动启动。

运行：python examples/ch10/a2a/ch10_a2a_agent.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents import A2ATool, SimpleAgent
from hello_agents.protocols import A2A_AVAILABLE, A2AServer


def main():
    print("=" * 56)
    print("协调者 Agent + A2ATool 调用远程研究员")
    print("=" * 56)

    # ---- 1. 在后台线程启动 A2A 研究员服务器 ----
    server = A2AServer(
        name="researcher",
        description="研究员Agent，可以搜索和分析资料",
    )

    @server.skill("research")
    def research(topic):
        return (f"【研究结果】关于「{topic}」：多智能体系统通过分工协作，"
                f"可显著提升复杂任务的完成效率与质量。")

    thread = threading.Thread(target=server.run, kwargs={"port": 5000}, daemon=True)
    thread.start()
    time.sleep(0.5)
    print("  ✅ A2A 研究员服务器已启动: http://localhost:5000")

    # ---- 2. 创建 A2ATool（对齐文档用法） ----
    researcher_tool = A2ATool(
        name="researcher",
        description="研究员Agent，可以搜索和分析资料",
        agent_url="http://localhost:5000",
    )

    # ---- 3. 创建协调者 Agent（对齐文档 10.3.1） ----
    coordinator = SimpleAgent(
        name="Coordinator",
        system_prompt=(
            "你是一个智能体协调者，负责调度下属智能体完成任务。"
            "当需要调研资料时，调用 researcher 工具。"
        ),
        enable_tool_calling=True,
    )
    coordinator.add_tool(researcher_tool)
    print(f"  ✅ 协调者 Agent 已创建，工具: {coordinator.list_tools()}")

    # ---- 4. 让 LLM 自动调用 A2ATool ----
    question = "请调研一下 多智能体系统 的应用场景"
    print(f"\n用户问题: {question}\n")
    answer = coordinator.run(question)
    print("\n" + "=" * 56)
    print("协调者回答:")
    print(answer)


if __name__ == "__main__":
    main()
