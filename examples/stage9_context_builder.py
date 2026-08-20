# -*- coding: utf-8 -*-
"""
第九章 Stage 1 验证脚本：ContextBuilder（文档 9.3.4 完整使用示例）

覆盖：
- GSSC 流水线 build()：Gather → Select → Structure → Compress
- 系统指令 + 对话历史 + 记忆检索 多源汇集
- 分区模板 [Role & Policies]/[Task]/[Evidence]/[Context]/[Output]
- 压缩兜底（小 max_tokens 触发 _compress）

运行：python examples/stage9_context_builder.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

from hello_agents.context import ContextBuilder, ContextConfig
from hello_agents.core.message import Message
from hello_agents.tools import MemoryTool


def main():
    print("=" * 80)
    print("Stage 1: ContextBuilder - GSSC 流水线验证")
    print("=" * 80)

    # 1. 初始化记忆工具（独立 user_id 避免污染）
    user_id = f"stage9_cb_{int(time.time())}"
    memory_tool = MemoryTool(user_id=user_id)

    # 2. 添加记忆（文档 9.3.4）
    memory_tool.run({
        "action": "add",
        "content": "用户正在开发数据分析工具,使用Python和Pandas",
        "memory_type": "semantic",
        "importance": 0.8,
    })
    memory_tool.run({
        "action": "add",
        "content": "已完成CSV读取模块的开发",
        "memory_type": "episodic",
        "importance": 0.7,
    })

    # 3. 准备对话历史（带递增时间戳，验证时间顺序）
    base = datetime.now()
    conversation_history = [
        Message(content="我正在开发一个数据分析工具", role="user",
                timestamp=base + timedelta(seconds=1)),
        Message(content="很好!数据分析工具通常需要处理大量数据。您计划使用什么技术栈?",
                role="assistant", timestamp=base + timedelta(seconds=2)),
        Message(content="我打算使用Python和Pandas,已经完成了CSV读取模块", role="user",
                timestamp=base + timedelta(seconds=3)),
        Message(content="不错的选择!Pandas在数据处理方面非常强大。接下来您可能需要考虑数据清洗和转换。",
                role="assistant", timestamp=base + timedelta(seconds=4)),
    ]

    # 4. 创建 ContextBuilder（文档配置）
    config = ContextConfig(
        max_tokens=3000,
        reserve_ratio=0.2,
        min_relevance=0.2,
        enable_compression=True,
    )
    builder = ContextBuilder(memory_tool=memory_tool, rag_tool=None, config=config)

    # 5. 构建上下文
    print("\n" + "=" * 80)
    print("构建的上下文:")
    print("=" * 80)
    context = builder.build(
        user_query="如何优化Pandas的内存占用?",
        conversation_history=conversation_history,
        system_instructions=(
            "你是一位资深的Python数据工程顾问。你的回答需要:"
            "1) 提供具体可行的建议 2) 解释技术原理 3) 给出代码示例"
        ),
    )
    print(context)
    print("=" * 80)

    # 6. 断言：分区完整
    for sec in ["[Role & Policies]", "[Task]", "[Context]", "[Output]"]:
        assert sec in context, f"缺少分区 {sec}"
    print("✅ 分区模板完整")

    # 7. 断言：对话历史按时间顺序
    ctx_body = context.split("[Context]")[1].split("[Output]")[0]
    hist = ["我正在开发", "很好!", "我打算使用", "不错的选择!"]
    positions = [ctx_body.find(h) for h in hist]
    assert all(a < b for a, b in zip(positions, positions[1:])), "历史顺序错乱"
    print("✅ 对话历史按时间顺序保留")

    # 8. 压缩测试：极小 max_tokens 触发 _compress
    print("\n" + "-" * 80)
    print("压缩测试 (max_tokens=120):")
    print("-" * 80)
    tight = ContextBuilder(
        memory_tool=memory_tool,
        config=ContextConfig(max_tokens=120, enable_compression=True),
    )
    compressed = tight.build(
        user_query="如何优化Pandas的内存占用?",
        conversation_history=conversation_history,
    )
    token_count = builder._count_tokens(compressed)
    assert token_count <= 120, f"压缩后仍超限: {token_count} tokens"
    print(f"✅ 压缩生效: 最终 {token_count} tokens ≤ 120")
    print(compressed[:200])

    print("\n🎉 Stage 1 验证全部通过")


if __name__ == "__main__":
    main()
