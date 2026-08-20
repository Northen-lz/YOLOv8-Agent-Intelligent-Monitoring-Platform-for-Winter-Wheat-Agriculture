# -*- coding: utf-8 -*-
"""
第十二章 01 —— 基础智能体（说明为何要评估）
镜像参考仓库 code/chapter12/01_basic_agent.py

用 SimpleAgent 做一个工具调用型任务，直观展示「模型说什么 ≠ 模型做对什么」：
- 同一个函数调用问题，模型可能给出不同形式的答案
- 需要评估器（BFCL/GAIA）用规范化匹配客观判定对错

需 .env（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID）：
    python examples/ch12/ch12_basic_agent_example.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hello_agents import SimpleAgent, HelloAgentsLLM


def main():
    print("=" * 60)
    print("第十二章 01 —— 基础智能体（为何要评估）")
    print("=" * 60)

    # 1. 创建带函数调用系统提示词的基础智能体（无工具，仅 LLM 对话）
    system_prompt = (
        "你是一个会调用函数解决任务的智能助手。当需要获取天气时，"
        "请输出函数调用：get_weather(city='城市名', date='日期')。"
    )
    agent = SimpleAgent(
        name="BasicAgent",
        llm=HelloAgentsLLM(),
        system_prompt=system_prompt,
    )

    # 2. 问一个函数调用任务
    question = "明天（2025-06-01）北京天气怎么样？请直接输出函数调用。"
    print(f"\n[问题] {question}")
    reply = agent.run(question)
    print(f"[模型回复] {reply}")

    # 3. 说明：为什么需要评估器
    print("\n" + "-" * 60)
    print("为什么需要评估？")
    print("  1. 模型回复格式不稳定：可能是 JSON、代码块或纯文本")
    print("  2. 同一个调用有无数等价写法：参数顺序、引号、2+3↔5")
    print("  3. 肉眼判断不客观：函数名错了、参数值错了，人眼容易漏")
    print("-" * 60)
    print("接下来用 BFCL（工具调用评估）客观判定这类任务的对错：")
    print("    python examples/ch12/ch12_bfcl_quick_start.py")
    print("    python examples/ch12/ch12_bfcl_custom_evaluation.py")


if __name__ == "__main__":
    main()
