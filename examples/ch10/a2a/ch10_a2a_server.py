# -*- coding: utf-8 -*-
"""
第十章 09_A2A_Server —— A2A 智能体 HTTP 服务器（镜像参考 09_A2A_Server.py）
离线可用。基于 stdlib http.server 自实现，零新增依赖。

启动：python examples/ch10/a2a/ch10_a2a_server.py   （监听 http://localhost:5000）
配合 ch10_a2a_client.py 在另一个终端使用。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import A2A_AVAILABLE, A2AServer

HOST = "localhost"
PORT = 5000


def main():
    print("=" * 56)
    print("A2A 研究员智能体服务器")
    print("=" * 56)
    if not A2A_AVAILABLE:
        print("  [轻量模式] a2a-sdk 未安装，使用 stdlib 自实现（等价 API）")

    # 创建 A2A 服务器（镜像参考：researcher Agent，研究/分析资料）
    server = A2AServer(
        name="researcher",
        description="研究员Agent，可以搜索和分析资料",
        version="1.0.0",
        capabilities={"skills": ["research", "analyze"], "max_tokens": 4096},
    )

    @server.skill("research")
    def research(topic):
        """研究指定主题，返回研究结果"""
        return (f"【研究结果】关于「{topic}」的调研报告："
                f"已找到 {3} 篇相关资料，关键结论是 {topic} 在智能体领域"
                f"具有重要应用价值。")

    @server.skill("analyze")
    def analyze(text):
        """分析一段文字"""
        return (f"【分析结果】对「{text[:30]}...」的分析："
                f"文字长度 {len(text)} 字，情感倾向中性，"
                f"建议重点关注其技术可行性。")

    print(f"  服务器名: {server.name}")
    print(f"  技能: {list(server.skills.keys())}")
    print(f"  Agent Card: {server.get_agent_card()['description']}")
    print(f"\n🚀 正在 {HOST}:{PORT} 上启动 A2A 服务器 (Ctrl+C 停止)...")
    server.run(host=HOST, port=PORT)


if __name__ == "__main__":
    main()
