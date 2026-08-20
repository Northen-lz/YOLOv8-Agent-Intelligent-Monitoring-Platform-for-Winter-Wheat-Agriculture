# -*- coding: utf-8 -*-
"""
第十章 09_A2A_Client —— A2A 客户端（镜像参考 09_A2A_Client.py）
离线可用。

先启动服务器：python examples/ch10/a2a/ch10_a2a_server.py
再运行本客户端：python examples/ch10/a2a/ch10_a2a_client.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import A2A_AVAILABLE, A2AClient

SERVER_URL = "http://localhost:5000"


def main():
    print("=" * 56)
    print(f"连接 A2A 服务器: {SERVER_URL}")
    print("=" * 56)
    if not A2A_AVAILABLE:
        print("  [轻量模式] a2a-sdk 未安装，使用 stdlib 自实现（等价 API）")

    client = A2AClient(SERVER_URL)

    # 1. 获取 Agent Card
    print("\n[1] 获取 Agent Card")
    card = client.get_agent_card()
    print(f"  name: {card.get('name')}")
    print(f"  description: {card.get('description')}")

    # 2. 列出技能
    print("\n[2] 列出技能")
    skills = client.list_skills()
    print(f"  技能列表: {skills}")

    # 3. 调用具体技能
    print("\n[3] 调用技能 research")
    result = client.execute_skill("research", "多智能体系统")
    print(f"  -> {result}")

    # 4. 自动路由调用
    print("\n[4] 自动路由 execute('请分析这段代码的质量')")
    result = client.execute("请分析这段代码的质量")
    print(f"  -> {result}")

    print("\n✅ A2A 客户端调用完成")


if __name__ == "__main__":
    main()
