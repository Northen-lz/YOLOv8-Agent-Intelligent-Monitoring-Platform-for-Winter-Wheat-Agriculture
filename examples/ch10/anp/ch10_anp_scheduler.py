# -*- coding: utf-8 -*-
"""
第十章 12_ANPTaskDistribution —— 任务分发 Agent + ANPTool 智能选择节点
镜像参考 code/chapter10/12_ANPTaskDistribution.py。

需联网/LLM key（.env 中配置）。

运行：python examples/ch10/anp/ch10_anp_scheduler.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents import ANPTool, SimpleAgent
from hello_agents.protocols import ANPDiscovery


def main():
    print("=" * 56)
    print("任务分发 Agent + ANPTool 智能选择计算节点")
    print("=" * 56)

    # ---- 1. 创建服务发现中心并注册计算节点 ----
    discovery = ANPDiscovery()
    for i, (node_id, location, load) in enumerate([
        ("node-a", "北京", 30),
        ("node-b", "上海", 10),
        ("node-c", "深圳", 20),
    ], 1):
        discovery.add_service(
            service_id=node_id,
            service_name=f"计算节点{node_id}",
            service_type="compute",
            capabilities=["计算", "运算"],
            endpoint=f"tcp://10.0.0.{i}:5000",
            metadata={"load": load, "location": location},
        )
    print(f"  ✅ 已注册 3 个计算节点: "
          f"{[s.service_id for s in discovery.list_all_services()]}")

    # ---- 2. 创建 ANPTool（对齐文档用法，传入 discovery 共享数据） ----
    anp_tool = ANPTool(
        name="service_discovery",
        description="服务发现工具，可以查找和选择计算节点",
        discovery=discovery,
    )

    # ---- 3. 创建任务分发 Agent ----
    scheduler = SimpleAgent(
        name="Scheduler",
        system_prompt=(
            "你是一个任务分发智能体。当需要分发计算任务时，"
            "先调用 service_discovery 工具（action=discover_services）"
            "列出可用节点，再用 action=select_best_server 选择负载最低的节点，"
            "格式: [TOOL_CALL:service_discovery:action=select_best_server,service_type=compute]"
        ),
        enable_tool_calling=True,
    )
    scheduler.add_tool(anp_tool)
    print(f"  ✅ 任务分发 Agent 已创建，工具: {scheduler.list_tools()}")

    # ---- 4. 让 LLM 自动调用 ANPTool ----
    task = "请分发一个图像识别任务到合适的计算节点"
    print(f"\n用户任务: {task}\n")
    answer = scheduler.run(task)
    print("\n" + "=" * 56)
    print("分发结果:")
    print(answer)


if __name__ == "__main__":
    main()
