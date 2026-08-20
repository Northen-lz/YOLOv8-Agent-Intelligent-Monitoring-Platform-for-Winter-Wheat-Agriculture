# -*- coding: utf-8 -*-
"""
第十章 07_SimpleA2AAgent —— 简单 A2A 智能体（技能 + 自动路由）
离线可用。镜像参考 code/chapter10/07_SimpleA2AAgent.py。

运行：python examples/ch10/a2a/ch10_a2a_calculator.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import A2A_AVAILABLE, A2AServer


def main():
    print("=" * 56)
    print("简单 A2A 计算智能体（进程内技能调用）")
    print("=" * 56)
    if not A2A_AVAILABLE:
        print("  [轻量模式] a2a-sdk 未安装，使用 stdlib 自实现（等价 API）")

    import re

    # 创建 A2A 智能体服务器
    server = A2AServer(
        name="calculator",
        description="A2A计算智能体，擅长数学计算",
        capabilities={"skills": ["add", "subtract", "multiply", "divide"]},
    )

    @server.skill("add")
    def add(text):
        """加法：从文本中提取数字求和，如 '3+4' 或 '计算 3+4'"""
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        return str(float(nums[0]) + float(nums[1]))

    @server.skill("subtract")
    def subtract(text):
        """减法：如 '10-4'"""
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        return str(float(nums[0]) - float(nums[1]))

    @server.skill("multiply")
    def multiply(text):
        """乘法：如 '3*4'"""
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        return str(float(nums[0]) * float(nums[1]))

    @server.skill("divide")
    def divide(text):
        """除法：如 '12/4'"""
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        if float(nums[1]) == 0:
            return "错误:除数不能为 0"
        return str(float(nums[0]) / float(nums[1]))

    # 1. 查看 Agent Card
    print("\n[1] Agent Card")
    card = server.get_agent_card()
    print(f"  name: {card['name']}")
    print(f"  description: {card['description']}")
    print(f"  skills: {card['skills']}")

    # 2. 显式调用技能
    print("\n[2] 显式调用技能")
    print(f"  add('3+4')      -> {server.execute_skill('add', '3+4')}")
    print(f"  multiply('6*7') -> {server.execute_skill('multiply', '6*7')}")

    # 3. 自动路由（按关键词匹配技能）
    print("\n[3] 自动路由")
    for text in ["请帮我算一下 100/4", "计算 50-20 等于多少", "你好"]:
        result = server.execute(text)
        print(f"  '{text}' -> {result}")

    print("\n✅ A2A 计算智能体运行完毕")


if __name__ == "__main__":
    main()
