# -*- coding: utf-8 -*-
"""
Hello-Agents ANP 协议实现（Agent Network Protocol）

文档说明：ANP 目前为概念性协议框架，这里做轻量的内存模拟：
- ANPDiscovery   服务发现中心（注册 / 发现 / 能力匹配）
- ANPNetwork     智能体网络（节点连接 / 网络统计）
- AgentService   服务描述数据模型
- register_service / discover_service  模块级便捷函数

核心概念（表 10.8）：
- 服务发现：按 service_type / capabilities 查找
- 服务注册：register_service 注册新节点
- 网络管理：ANPNetwork 建立节点连接
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentService:
    """ANP 服务描述（对齐文档服务发现中心的核心数据模型）"""
    service_id: str
    service_name: str
    service_type: str
    capabilities: List[str] = field(default_factory=list)
    endpoint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        return (f"AgentService(id={self.service_id}, name={self.service_name}, "
                f"type={self.service_type}, endpoint={self.endpoint})")


class ANPDiscovery:
    """服务发现中心 - 维护已注册的智能体服务"""

    def __init__(self):
        # service_id -> AgentService
        self._services: Dict[str, AgentService] = {}

    # ---------------- 注册 ----------------

    def register(self, service: AgentService) -> AgentService:
        """注册一个服务"""
        self._services[service.service_id] = service
        print(f"✅ 服务注册: {service.service_name} (id={service.service_id}, "
              f"type={service.service_type})")
        return service

    def add_service(
            self,
            service_id: str,
            service_name: str,
            service_type: str,
            capabilities: Optional[List[str]] = None,
            endpoint: str = "",
            metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentService:
        """便捷注册：按字段创建并注册服务"""
        service = AgentService(
            service_id=service_id,
            service_name=service_name,
            service_type=service_type,
            capabilities=capabilities or [],
            endpoint=endpoint,
            metadata=metadata or {},
        )
        return self.register(service)

    # ---------------- 发现 ----------------

    def discover_services(
            self,
            service_type: Optional[str] = None,
            query: Optional[str] = None,
    ) -> List[AgentService]:
        """
        发现服务（文档 10.4.2）。

        Args:
            service_type: 按服务类型过滤（如 "nlp" / "compute" / "api"）
            query: 按服务名 / 能力关键词模糊匹配
        """
        results = []
        for service in self._services.values():
            if service_type and service.service_type != service_type:
                continue
            if query:
                haystack = f"{service.service_name} {' '.join(service.capabilities)}"
                if query.lower() not in haystack.lower():
                    continue
            results.append(service)
        return results

    def list_all_services(self) -> List[AgentService]:
        """列出所有已注册服务"""
        return list(self._services.values())

    def get(self, service_id: str) -> Optional[AgentService]:
        """按 service_id 获取服务"""
        return self._services.get(service_id)

    def stats(self) -> Dict[str, Any]:
        """服务发现中心统计"""
        by_type: Dict[str, int] = {}
        for s in self._services.values():
            by_type[s.service_type] = by_type.get(s.service_type, 0) + 1
        return {"total_services": len(self._services), "by_type": by_type}


class ANPNetwork:
    """智能体网络 - 节点连接与管理（对齐文档 10.4.2 构建 Agent 网络）"""

    def __init__(self, network_id: str):
        self.network_id = network_id
        # node_id -> endpoint
        self.nodes: Dict[str, str] = {}
        # 无向边集合 (a, b) 规范排序后存储
        self.edges: set = set()

    def add_node(self, node_id: str, endpoint: str = ""):
        """添加节点"""
        self.nodes[node_id] = endpoint
        return node_id

    def remove_node(self, node_id: str):
        """移除节点及关联边"""
        if node_id in self.nodes:
            del self.nodes[node_id]
        self.edges = {e for e in self.edges if node_id not in e}

    def connect_nodes(self, node_a: str, node_b: str):
        """在两个节点之间建立连接（根据能力匹配）"""
        if node_a not in self.nodes or node_b not in self.nodes:
            print(f"⚠️ 连接失败: 节点不存在 ({node_a} / {node_b})")
            return False
        edge = tuple(sorted([node_a, node_b]))
        self.edges.add(edge)
        print(f"🔗 已连接: {node_a} <-> {node_b}")
        return True

    def get_connected_nodes(self, node_id: str) -> List[str]:
        """获取与指定节点相连的节点"""
        return [n for edge in self.edges if node_id in edge
                for n in edge if n != node_id]

    def get_network_stats(self) -> Dict[str, Any]:
        """获取网络统计（文档 10.4.2 stats['total_nodes']）"""
        return {
            "network_id": self.network_id,
            "total_nodes": len(self.nodes),
            "total_connections": len(self.edges),
            "nodes": list(self.nodes.keys()),
            "edges": [list(e) for e in sorted(self.edges)],
        }

    def __repr__(self):
        return (f"ANPNetwork(id={self.network_id}, "
                f"nodes={len(self.nodes)}, connections={len(self.edges)})")


# ---------------- 模块级便捷函数 ----------------

def register_service(
        discovery: ANPDiscovery,
        service_id: str,
        service_name: str,
        service_type: str,
        capabilities: Optional[List[str]] = None,
        endpoint: str = "",
        metadata: Optional[Dict[str, Any]] = None,
) -> AgentService:
    """
    注册 Agent 服务（文档 10.4.2 用法）。

    用法：
        register_service(
            discovery=discovery,
            service_id="nlp_agent_1",
            service_name="NLP处理专家A",
            service_type="nlp",
            capabilities=["text_analysis", "sentiment_analysis", "ner"],
            endpoint="http://localhost:8001",
            metadata={"load": 0.3, "price": 0.01, "version": "1.0.0"}
        )
    """
    return discovery.add_service(
        service_id=service_id,
        service_name=service_name,
        service_type=service_type,
        capabilities=capabilities,
        endpoint=endpoint,
        metadata=metadata,
    )


def discover_service(
        discovery: ANPDiscovery,
        service_type: Optional[str] = None,
        query: Optional[str] = None,
) -> List[AgentService]:
    """
    发现服务（文档 10.4.2 用法）。

    用法：
        nlp_services = discover_service(discovery, service_type="nlp")
    """
    return discovery.discover_services(service_type=service_type, query=query)
