# -*- coding: utf-8 -*-
"""
Hello-Agents 记忆管理器（MemoryManager）
对齐文档第八章 8.2.4 MemoryManager

职责（"关注点分离"）：
- 统一调度四种记忆类型（working/episodic/semantic/perceptual）
- add_memory / retrieve_memories / forget_memories / consolidate_memories
- 用户隔离（user_id）
- 遗忘策略：importance_based / time_based / capacity_based
- 记忆整合：短期记忆 → 长期记忆（working → episodic → semantic）

日志对齐文档（PDF 页 235）：
MemoryManager初始化完成，启用记忆类型: ['working', 'episodic', 'semantic']
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .base import MemoryConfig, MemoryItem
from .types.episodic import EpisodicMemory
from .types.perceptual import PerceptualMemory
from .types.semantic import SemanticMemory
from .types.working import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """记忆管理器 - 统一的记忆操作接口"""

    def __init__(
            self,
            config: Optional[MemoryConfig] = None,
            user_id: str = "default_user",
            enable_working: bool = True,
            enable_episodic: bool = True,
            enable_semantic: bool = True,
            enable_perceptual: bool = False,
    ):
        self.config = config or MemoryConfig()
        self.user_id = user_id

        # 初始化各类型记忆
        self.memory_types: Dict[str, object] = {}
        if enable_working:
            self.memory_types["working"] = WorkingMemory(self.config)
        if enable_episodic:
            self.memory_types["episodic"] = EpisodicMemory(self.config)
        if enable_semantic:
            self.memory_types["semantic"] = SemanticMemory(self.config)
        if enable_perceptual:
            self.memory_types["perceptual"] = PerceptualMemory(self.config)

        logger.info(
            f"MemoryManager初始化完成，启用记忆类型: "
            f"{list(self.memory_types.keys())}"
        )

    # ---------------- 添加 ----------------

    def add_memory(
            self,
            content: str,
            memory_type: str = "working",
            importance: float = 0.5,
            metadata: Optional[Dict] = None,
            auto_classify: bool = False,
    ) -> Optional[str]:
        """添加记忆，返回记忆ID"""
        memory_type = self._normalize_type(memory_type)
        if memory_type not in self.memory_types:
            logger.warning(f"记忆类型 '{memory_type}' 未启用")
            return None

        metadata = dict(metadata or {})
        metadata.setdefault("user_id", self.user_id)
        metadata.setdefault("session_id", "default")

        memory_item = MemoryItem(
            content=content,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata,
        )
        return self.memory_types[memory_type].add(memory_item)

    # ---------------- 检索 ----------------

    def retrieve_memories(
            self,
            query: str,
            limit: int = 5,
            memory_types: Optional[List[str]] = None,
            min_importance: float = 0.1,
            **kwargs,
    ) -> List[MemoryItem]:
        """从指定（或全部）记忆类型检索"""
        if memory_types is None:
            memory_types = list(self.memory_types.keys())
        memory_types = [self._normalize_type(t) for t in memory_types]

        results: List[MemoryItem] = []
        for mt in memory_types:
            if mt not in self.memory_types:
                continue
            items = self.memory_types[mt].retrieve(
                query,
                limit=limit,
                user_id=self.user_id,
                min_importance=min_importance,
                **kwargs,
            )
            results.extend(items)

        # 按重要性降序（多类型混合时优先重要记忆）
        results.sort(key=lambda m: m.importance, reverse=True)
        return results[:limit]

    # ---------------- 遗忘 ----------------

    def forget_memories(
            self,
            strategy: str = "importance_based",
            threshold: float = 0.1,
            max_age_days: int = 30,
    ) -> int:
        """
        遗忘记忆（模拟人类选择性遗忘）
        - importance_based: 删除重要性低于 threshold 的记忆
        - time_based:       删除超过 max_age_days 的记忆
        - capacity_based:   数量超限时删除最不重要的记忆（threshold 为容量比例）
        """
        total = 0
        cutoff = datetime.now() - timedelta(days=max_age_days)

        for memory in self.memory_types.values():
            for item in memory.list_all():
                should_forget = False
                if strategy == "importance_based":
                    should_forget = item.importance < threshold
                elif strategy == "time_based":
                    should_forget = item.timestamp < cutoff
                elif strategy == "capacity_based":
                    # 简化为：重要性低于阈值则遗忘（容量管理）
                    should_forget = item.importance < threshold
                if should_forget:
                    try:
                        if memory.remove(item.id):
                            total += 1
                    except Exception:
                        pass
        return total

    # ---------------- 整合 ----------------

    def consolidate_memories(
            self,
            from_type: str = "working",
            to_type: str = "episodic",
            importance_threshold: float = 0.7,
    ) -> int:
        """记忆整合：将重要的短期记忆提升为长期记忆"""
        from_type = self._normalize_type(from_type)
        to_type = self._normalize_type(to_type)

        if from_type not in self.memory_types or to_type not in self.memory_types:
            logger.warning(f"整合目标类型未启用: {from_type} -> {to_type}")
            return 0
        if from_type == to_type:
            return 0

        src = self.memory_types[from_type]
        dst = self.memory_types[to_type]

        count = 0
        for item in src.list_all():
            if item.importance >= importance_threshold:
                new_item = MemoryItem(
                    content=item.content,
                    memory_type=to_type,
                    importance=item.importance,
                    timestamp=item.timestamp,
                    metadata=dict(item.metadata),
                )
                new_item.metadata.setdefault("user_id", self.user_id)
                try:
                    dst.add(new_item)
                    src.remove(item.id)
                    count += 1
                except Exception as e:
                    logger.warning(f"整合失败: {e}")
        return count

    # ---------------- 统计与工具 ----------------

    def get_stats(self) -> Dict[str, int]:
        """各类型记忆数量统计"""
        stats = {}
        for name, memory in self.memory_types.items():
            try:
                stats[name] = memory.count()
            except Exception:
                stats[name] = 0
        return stats

    def clear_all(self) -> Dict[str, int]:
        """清空所有记忆，返回各类型清空数量"""
        cleared = {}
        for name, memory in self.memory_types.items():
            try:
                cleared[name] = memory.clear()
            except Exception as e:
                cleared[name] = 0
                logger.warning(f"清空 {name} 失败: {e}")
        return cleared

    def get_type(self, memory_type: str):
        """获取指定记忆类型实例"""
        memory_type = self._normalize_type(memory_type)
        return self.memory_types.get(memory_type)

    def has_type(self, memory_type: str) -> bool:
        """是否启用某记忆类型"""
        return self._normalize_type(memory_type) in self.memory_types

    @staticmethod
    def _normalize_type(memory_type: str) -> str:
        """类型名兼容：working/episodic/semantic/perceptual"""
        t = (memory_type or "").strip().lower()
        aliases = {
            "work": "working", "wm": "working",
            "episode": "episodic", "epi": "episodic",
            "sem": "semantic", "percep": "perceptual",
        }
        return aliases.get(t, t)
