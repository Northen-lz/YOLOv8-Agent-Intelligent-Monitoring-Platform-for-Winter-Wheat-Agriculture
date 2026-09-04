# -*- coding: utf-8 -*-
"""
Hello-Agents 记忆系统基础数据结构
对齐文档第八章 8.2.4：MemoryItem / MemoryConfig / BaseMemory

记忆系统四层架构的"基础设施层"（文档 PDF 页 232）：
- MemoryItem   - 记忆数据结构（标准化记忆项）
- MemoryConfig - 配置管理（系统参数设置）
- BaseMemory   - 记忆基类（通用接口定义）
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import Config


class MemoryItem:
    """记忆数据结构 - 标准化记忆项

    文档未完整给出此类代码，按文档各处使用到的字段规范实现：
    - memory.content / memory.memory_type / memory.importance
    - memory.timestamp / memory.metadata / memory.id
    """

    def __init__(
            self,
            content: str,
            memory_type: str = "general",
            importance: float = 0.5,
            id: Optional[str] = None,
            timestamp: Optional[datetime] = None,
            metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = id or str(uuid.uuid4())
        self.content = content
        self.memory_type = memory_type
        self.importance = max(0.0, min(1.0, float(importance)))
        self.timestamp = timestamp or datetime.now()
        self.metadata = metadata or {}

    # ---------------- 序列化 ----------------

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（用于 SQLite/JSON 持久化）"""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """从字典恢复（数据库读取）"""
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=data.get("memory_type", "general"),
            importance=data.get("importance", 0.5),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata") or {},
        )

    # ---------------- 便捷属性 ----------------

    @property
    def session_id(self) -> str:
        """会话ID（存于 metadata）"""
        return self.metadata.get("session_id", "default")

    @property
    def user_id(self) -> str:
        """用户ID（存于 metadata）"""
        return self.metadata.get("user_id", "default_user")

    def __str__(self) -> str:
        content_preview = self.content[:80] + "..." if len(self.content) > 80 else self.content
        return (
            f"[{self.memory_type}] {content_preview} "
            f"(重要性: {self.importance:.2f})"
        )

    def __repr__(self) -> str:
        return f"MemoryItem(id={self.id[:8]}, type={self.memory_type})"


class MemoryConfig:
    """记忆系统配置管理

    从 .env 读取（对齐文档 PDF 页 234-235 配置块），
    也支持代码中直接传参覆盖。
    """

    def __init__(
            self,
            working_memory_capacity: Optional[int] = None,
            working_memory_ttl: Optional[int] = None,
            database_path: Optional[str] = None,
            qdrant_url: Optional[str] = None,
            qdrant_api_key: Optional[str] = None,
            qdrant_collection: Optional[str] = None,
            qdrant_vector_size: Optional[int] = None,
            neo4j_uri: Optional[str] = None,
            neo4j_username: Optional[str] = None,
            neo4j_password: Optional[str] = None,
            embed_model_type: Optional[str] = None,
            embed_model_name: Optional[str] = None,
            **kwargs,
    ):
        # 工作记忆：容量 + TTL（分钟）
        self.working_memory_capacity = (
            working_memory_capacity or Config.WORKING_MEMORY_CAPACITY or 50
        )
        self.working_memory_ttl = (
            working_memory_ttl or Config.WORKING_MEMORY_TTL or 60
        )

        # SQLite 文档存储
        self.database_path = database_path or Config.MEMORY_DB_PATH

        # Qdrant 向量数据库
        self.qdrant_url = qdrant_url or Config.QDRANT_URL
        self.qdrant_api_key = qdrant_api_key or Config.QDRANT_API_KEY
        self.qdrant_collection = qdrant_collection or Config.QDRANT_COLLECTION
        self.qdrant_vector_size = (
            qdrant_vector_size or Config.QDRANT_VECTOR_SIZE
        )

        # Neo4j 图数据库
        self.neo4j_uri = neo4j_uri or Config.NEO4J_URI
        self.neo4j_username = neo4j_username or Config.NEO4J_USERNAME
        self.neo4j_password = neo4j_password or Config.NEO4J_PASSWORD

        # 嵌入方案
        self.embed_model_type = (
            embed_model_type or Config.EMBED_MODEL_TYPE or "local"
        )
        self.embed_model_name = embed_model_name or Config.EMBED_MODEL_NAME

    def __str__(self) -> str:
        return (
            f"MemoryConfig(working_capacity={self.working_memory_capacity}, "
            f"ttl={self.working_memory_ttl}min, db={self.database_path})"
        )


class BaseMemory(ABC):
    """记忆基类 - 定义所有记忆类型的通用接口

    对齐文档：MemoryManager 统一调用各类型的 add / retrieve。
    各记忆类型拥有自己的存储后端与检索算法。
    """

    def __init__(self, config: Optional[MemoryConfig] = None, storage_backend=None):
        self.config = config or MemoryConfig()
        # 共享的存储后端（由 MemoryManager 注入，可选）
        self.storage_backend = storage_backend

    @abstractmethod
    def add(self, memory_item: MemoryItem) -> str:
        """添加一条记忆，返回记忆ID"""
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        """检索记忆，返回按相关度排序的 MemoryItem 列表"""
        raise NotImplementedError

    def update(self, memory_id: str, **fields) -> bool:
        """更新记忆（默认不支持，子类可覆盖）"""
        raise NotImplementedError("该记忆类型不支持更新")

    def remove(self, memory_id: str) -> bool:
        """删除记忆（默认不支持，子类可覆盖）"""
        raise NotImplementedError("该记忆类型不支持删除")

    def clear(self) -> int:
        """清空记忆（默认不支持，子类可覆盖）"""
        raise NotImplementedError("该记忆类型不支持清空")

    def __str__(self) -> str:
        return f"{self.__class__.__name__}"
