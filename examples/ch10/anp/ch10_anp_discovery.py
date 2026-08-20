# -*- coding: utf-8 -*-
"""
第十章 11_ANPInit —— ANP 服务注册、发现与网络（镜像参考 11_ANPInit.py）
离线可用。

运行：python examples/ch10/anp/ch10_anp_discovery.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hello_agents.protocols import (
    ANPDiscovery,
    ANPNetwork,
    discover_service,
    register_service,
)


def main():
    print("=" * 56)
    print("ANP 服务注册与发现")
    print("=" * 56)

    # ---- 1. 创建服务发现中心 ----
    discovery = ANPDiscovery()
    print("\n[1] 创建服务发现中心 ✅")

    # ---- 2. 注册服务（模块级函数，对齐文档用法） ----
    print("\n[2] 注册服务")
    register_service(
        discovery,
        service_id="node-001",
        service_name="计算节点1",
        service_type="compute",
        capabilities=["计算", "运算"],
        endpoint="tcp://10.0.0.1:5000",
        metadata={"load": 10, "location": "北京"},
    )
    register_service(
        discovery,
        service_id="node-002",
        service_name="计算节点2",
        service_type="compute",
        capabilities=["计算", "存储"],
        endpoint="tcp://10.0.0.2:5000",
        metadata={"load": 30, "location": "上海"},
    )
    register_service(
        discovery,
        service_id="storage-001",
        service_name="存储节点1",
        service_type="storage",
        capabilities=["存储"],
        endpoint="tcp://10.0.0.3:6000",
        metadata={"capacity": "1TB"},
    )
    print("  已注册 3 个服务")

    # ---- 3. 服务发现（模块级函数） ----
    print("\n[3] 服务发现")
    compute_services = discover_service(discovery, service_type="compute")
    print(f"  发现 compute 类型服务 {len(compute_services)} 个:")
    for s in compute_services:
        print(f"    - [{s.service_id}] {s.service_name} @ {s.endpoint}")

    # 按能力关键词发现
    storage_services = discovery.discover_services(query="存储")
    print(f"  按关键词'存储'发现 {len(storage_services)} 个服务")
    for s in storage_services:
        print(f"    - [{s.service_id}] {s.service_name} (type={s.service_type})")

    # ---- 4. 服务发现中心统计 ----
    print("\n[4] 服务发现中心统计")
    stats = discovery.stats()
    print(f"  总服务数: {stats['total_services']}")
    print(f"  按类型分布: {stats['by_type']}")

    # ---- 5. ANP 网络（节点连接关系） ----
    print("\n[5] ANP 网络")
    network = ANPNetwork(network_id="net-001")
    network.add_node("node-001", "tcp://10.0.0.1:5000")
    network.add_node("node-002", "tcp://10.0.0.2:5000")
    network.add_node("storage-001", "tcp://10.0.0.3:6000")
    network.connect_nodes("node-001", "node-002")
    network.connect_nodes("node-001", "storage-001")
    stats = network.get_network_stats()
    print(f"  网络ID: {stats['network_id']}")
    print(f"  节点数: {stats['total_nodes']}")
    print(f"  连接数: {stats['total_connections']}")
    print(f"  节点列表: {[n for n in stats['nodes']]}")

    print("\n✅ ANP 服务注册与发现运行完毕")


if __name__ == "__main__":
    main()
