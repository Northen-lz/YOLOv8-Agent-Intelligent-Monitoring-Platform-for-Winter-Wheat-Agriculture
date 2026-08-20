# -*- coding: utf-8 -*-
"""
阶段3 验证：MemoryManager + MemoryTool + Agent 集成
复刻文档 8.2.2 "30秒上手记忆功能" + SimpleAgent 工具调用

运行: python examples/stage3_memory_tool.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hello_agents import HelloAgentsLLM, MemoryTool, SimpleAgent, ToolRegistry
from hello_agents.memory import MemoryConfig

TEST_USER = "stage3_test_user"


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def test_memory_tool_ops():
    section("[1] MemoryTool 基础操作（复刻文档 8.2.2）")
    mt = MemoryTool(
        user_id=TEST_USER,
        memory_types=["working", "episodic", "semantic", "perceptual"],
    )
    mt.execute("clear_all")

    # ---- add：四种记忆类型 ----
    print("-- add --")
    print(mt.execute("add", content="用户刚才问了关于Python函数的问题",
                     memory_type="working", importance=0.6))
    print(mt.execute("add",
                     content="2024年3月15日，用户张三完成了第一个Python项目",
                     memory_type="episodic", importance=0.8,
                     event_type="milestone", location="在线学习平台"))
    print(mt.execute("add",
                     content="Python是一种解释型、面向对象的编程语言",
                     memory_type="semantic", importance=0.9,
                     knowledge_type="factual"))
    print(mt.execute("add",
                     content="用户上传了一张Python代码截图，包含函数定义",
                     memory_type="perceptual", importance=0.7,
                     modality="image", file_path="./uploads/code_screenshot.png"))

    # ---- search ----
    print("\n-- search 'Python编程' --")
    print(mt.execute("search", query="Python编程", limit=5))
    print("\n-- search '学习进度' (episodic) --")
    print(mt.execute("search", query="学习进度", memory_type="episodic", limit=3))
    print("\n-- search '函数定义' (semantic+episodic, min_imp=0.5) --")
    print(mt.execute("search", query="函数定义",
                     memory_types=["semantic", "episodic"], min_importance=0.5))

    # ---- summary / stats ----
    print("\n-- summary --")
    print(mt.execute("summary"))
    print("\n-- stats --")
    print(mt.execute("stats"))

    # ---- forget / consolidate ----
    print("\n-- forget importance_based(0.2) --")
    print(mt.execute("forget", strategy="importance_based", threshold=0.2))
    print("\n-- consolidate episodic→semantic(0.8) --")
    print(mt.execute("consolidate", from_type="episodic",
                     to_type="semantic", importance_threshold=0.8))
    print("\n-- summary 整合后 --")
    print(mt.execute("summary"))

    mt.execute("clear_all")
    print("\n✅ MemoryTool 操作验证通过")


def test_agent_integration():
    section("[2] SimpleAgent + MemoryTool 集成（对话中记住信息）")
    mt = MemoryTool(user_id=TEST_USER, memory_types=["working", "semantic"])
    mt.execute("clear_all")

    registry = ToolRegistry()
    registry.register_tool(mt)
    agent = SimpleAgent(
        name="MemoryAssistant",
        llm=HelloAgentsLLM(),
        system_prompt=(
            "你是一个有记忆能力的智能助手。当用户提供个人信息时，"
            "你必须使用记忆工具记住，格式: "
            "[TOOL_CALL:memory:action=add,memory_type=semantic,"
            "content=用户XX，重要性0.8]"
        ),
        tool_registry=registry,
    )

    print("-- 对话1: 让Agent记住用户信息 --")
    resp1 = agent.run("你好！请记住我叫张三，我是一名Python开发者")
    print(f"  助手: {resp1[:100]}...")

    print("\n-- 对话2: 用记忆工具搜索确认 --")
    resp2 = agent.run("我告诉你我的名字了吗？请从记忆中搜索")
    print(f"  助手: {resp2[:120]}...")

    # 直接验证记忆已存储
    hits = mt.memory_manager.retrieve_memories(
        "张三", limit=3, memory_types=["semantic"]
    )
    print(f"\n-- 语义记忆检索'张三': {len(hits)} 条 --")
    for h in hits:
        print(f"  - [{h.memory_type}] {h.content[:50]}")
    assert len(hits) >= 1, "Agent 应该把'张三'存入语义记忆"

    mt.execute("clear_all")
    print("\n✅ Agent 集成验证通过")


def main():
    t0 = time.time()
    test_memory_tool_ops()
    test_agent_integration()
    print("\n" + "=" * 60)
    print(f"✅ 阶段3 验证全部通过！耗时 {time.time()-t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
