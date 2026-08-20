# -*- coding: utf-8 -*-
"""
第十章 13_ANPLoadBalancing —— ANP 负载均衡（镜像参考 13_ANPLoadBalancing.py）
离线可用。

实现文档 10.4.2「负载均衡」：从服务发现中心选择负载最低的服务器。

运行：python examples/ch10/anp/ch10_anp_load_balancing.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import ANPDiscovery


def select_server(discovery: ANPDiscovery, service_type: str):
    """选择负载最低的服务器（文档 10.4.2 负载均衡）"""
    services = discovery.discover_services(service_type=service_type)
    if not services:
        return None
    return min(services, key=lambda s: s.metadata.get("load", 0))


def main():
    print("=" * 56)
    print("ANP 负载均衡：10 个请求分发到负载最低的服务器")
    print("=" * 56)

    # ---- 1. 注册 3 台服务器，初始负载不同 ----
    discovery = ANPDiscovery()
    for i in range(1, 4):
        discovery.add_service(
            service_id=f"compute-00{i}",
            service_name=f"计算服务器{i}",
            service_type="compute",
            capabilities=["计算"],
            endpoint=f"tcp://10.0.0.{i}:5000",
            metadata={"load": random.randint(0, 50)},
        )
    print("\n初始服务器列表:")
    for s in discovery.list_all_services():
        print(f"  [{s.service_id}] load={s.metadata['load']}")

    # ---- 2. 依次分发 10 个请求 ----
    print("\n请求分发记录:")
    stats = {}
    for i in range(1, 11):
        server = select_server(discovery, "compute")
        # 模拟请求：负载 +10（处理了一个任务）
        server.metadata["load"] += 10
        stats[server.service_id] = stats.get(server.service_id, 0) + 1
        print(f"  请求#{i:02d} → {server.service_id} "
              f"(load={server.metadata['load']})")

    # ---- 3. 最终负载均衡效果 ----
    print("\n最终负载均衡效果:")
    for s in discovery.list_all_services():
        print(f"  [{s.service_id}] 收到 {stats.get(s.service_id, 0)} 个请求, "
              f"当前 load={s.metadata['load']}")

    # 断言：负载差异应较小（均衡）
    loads = [s.metadata["load"] for s in discovery.list_all_services()]
    print(f"\n  负载列表: {loads}，最大差异: {max(loads) - min(loads)}")
    assert max(loads) - min(loads) <= 20, "负载均衡效果异常"
    print("\n✅ ANP 负载均衡验证通过")


if __name__ == "__main__":
    main()
