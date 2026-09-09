# -*- coding: utf-8 -*-
"""
Hello-Agents 记忆工具（MemoryTool）
MemoryTool

设计（"统一入口，分发处理"）：
- execute(action, **kwargs) 通过 action 参数指定具体操作
- 支持操作：add / search / summary / stats / update / remove / forget / consolidate / clear_all
- 会话ID自动管理 + 感知记忆文件模态推断

操作参数（对齐文档）：
- add:    content, memory_type, importance, file_path, modality, **metadata
- search: query, limit, memory_type(s), min_importance
- forget: strategy, threshold, max_age_days
- consolidate: from_type, to_type, importance_threshold
"""

import os
from datetime import datetime
from typing import List, Optional

from ...core.config import Config
from ...memory.base import MemoryConfig
from ...memory.manager import MemoryManager
from ..base import BaseTool

# 记忆类型中文标签（对齐文档格式化输出）
_TYPE_LABELS = {
    "working": "工作记忆",
    "episodic": "情景记忆",
    "semantic": "语义记忆",
    "perceptual": "感知记忆",
}


class MemoryTool(BaseTool):
    """记忆工具 - 为Agent提供记忆功能"""

    def __init__(
            self,
            user_id: str = "default_user",
            memory_config: Optional[MemoryConfig] = None,
            memory_types: Optional[List[str]] = None,
    ):
        super().__init__(
            name="memory",
            description="记忆工具 - 可以存储和检索对话历史、知识和经验",
        )

        # 初始化记忆管理器
        self.user_id = user_id
        self.memory_config = memory_config or MemoryConfig()
        self.memory_types = memory_types or ["working", "episodic", "semantic"]

        self.memory_manager = MemoryManager(
            config=self.memory_config,
            user_id=user_id,
            enable_working="working" in self.memory_types,
            enable_episodic="episodic" in self.memory_types,
            enable_semantic="semantic" in self.memory_types,
            enable_perceptual="perceptual" in self.memory_types,
        )

        # 会话ID（自动管理）
        self.current_session_id: Optional[str] = None

    # ---------------- 统一入口 ----------------

    def execute(self, action: str = "search", **kwargs) -> str:
        """执行记忆操作"""
        handlers = {
            "add": self._add_memory,
            "search": self._search_memory,
            "summary": self._get_summary,
            "stats": self._get_stats,
            "update": self._update_memory,
            "remove": self._remove_memory,
            "forget": self._forget,
            "consolidate": self._consolidate,
            "clear_all": self._clear_all,
        }
        handler = handlers.get((action or "").strip().lower())
        if handler is None:
            return f"❌ 不支持的操作: {action}（可选: {', '.join(handlers)}）"
        try:
            return handler(**kwargs)
        except Exception as e:
            return f"❌ 操作 {action} 执行失败: {str(e)}"

    # 兼容 BaseTool.run（SimpleAgent 兜底路径）
    def run(self, *args, **kwargs) -> str:
        if kwargs:
            return self.execute(**kwargs)
        if args:
            # 兼容文档写法：run({"action": "add", ...}) 传单个参数字典
            if isinstance(args[0], dict):
                return self.execute(**args[0])
            return self.execute(*args)
        return self.execute("summary")

    # ---------------- 操作1：add ----------------

    def _add_memory(
            self,
            content: str = "",
            memory_type: str = "working",
            importance: float = 0.5,
            file_path: str = None,
            modality: str = None,
            **metadata,
    ) -> str:
        """添加记忆"""
        if not content:
            return "❌ 添加记忆失败: 内容不能为空"

        # 会话ID自动管理
        if self.current_session_id is None:
            self.current_session_id = (
                f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )

        # 感知记忆文件支持：自动推断模态
        if memory_type == "perceptual" and file_path:
            inferred = modality or self._infer_modality(file_path)
            metadata.setdefault("modality", inferred)
            metadata.setdefault("raw_data", file_path)

        # 补充上下文信息
        metadata.update({
            "session_id": self.current_session_id,
            "timestamp": datetime.now().isoformat(),
        })

        memory_id = self.memory_manager.add_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata,
            auto_classify=False,
        )
        if not memory_id:
            return f"❌ 添加记忆失败: 记忆类型 '{memory_type}' 不可用"
        return f"✅ 记忆已添加 (ID: {memory_id[:8]}...)"

    @staticmethod
    def _infer_modality(file_path: str) -> str:
        """根据文件扩展名推断模态"""
        ext = os.path.splitext(file_path or "")[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            return "image"
        if ext in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
            return "audio"
        if ext in (".mp4", ".avi", ".mov", ".mkv"):
            return "video"
        return "text"

    # ---------------- 操作2：search ----------------

    def _search_memory(
            self,
            query: str,
            limit: int = 5,
            memory_types: Optional[List[str]] = None,
            memory_type: str = None,
            min_importance: float = 0.1,
    ) -> str:
        """搜索记忆"""
        # 参数标准化：支持单数/复数形式
        if memory_type and not memory_types:
            memory_types = [memory_type]

        results = self.memory_manager.retrieve_memories(
            query=query,
            limit=limit,
            memory_types=memory_types,
            min_importance=min_importance,
        )
        if not results:
            return f"🔍 未找到与 '{query}' 相关的记忆"

        formatted_results = [f"🔍 找到 {len(results)} 条相关记忆:"]
        for i, memory in enumerate(results, 1):
            label = _TYPE_LABELS.get(memory.memory_type, memory.memory_type)
            preview = (memory.content[:80] + "..."
                       if len(memory.content) > 80 else memory.content)
            formatted_results.append(
                f"{i}. [{label}] {preview} "
                f"(重要性: {memory.importance:.2f})"
            )
        return "\n".join(formatted_results)

    # ---------------- 操作3：forget ----------------

    def _forget(
            self,
            strategy: str = "importance_based",
            threshold: float = 0.1,
            max_age_days: int = 30,
    ) -> str:
        """遗忘记忆（支持多种策略）"""
        count = self.memory_manager.forget_memories(
            strategy=strategy,
            threshold=threshold,
            max_age_days=max_age_days,
        )
        return f"🧹 已遗忘 {count} 条记忆（策略: {strategy}）"

    # ---------------- 操作4：consolidate ----------------

    def _consolidate(
            self,
            from_type: str = "working",
            to_type: str = "episodic",
            importance_threshold: float = 0.7,
    ) -> str:
        """整合记忆（将重要的短期记忆提升为长期记忆）"""
        count = self.memory_manager.consolidate_memories(
            from_type=from_type,
            to_type=to_type,
            importance_threshold=importance_threshold,
        )
        label_from = _TYPE_LABELS.get(from_type, from_type)
        label_to = _TYPE_LABELS.get(to_type, to_type)
        return f"🔄 已整合 {count} 条记忆（{label_from} → {label_to}）"

    # ---------------- 其他操作 ----------------

    def _get_summary(self, **kwargs) -> str:
        """获取记忆摘要"""
        stats = self.memory_manager.get_stats()
        lines = ["📊 记忆摘要:"]
        for mt, count in stats.items():
            label = _TYPE_LABELS.get(mt, mt)
            lines.append(f"  - {label}: {count} 条")
        return "\n".join(lines)

    def _get_stats(self, **kwargs) -> str:
        """获取统计信息"""
        stats = self.memory_manager.get_stats()
        lines = ["📈 记忆统计:"]
        for mt, count in stats.items():
            label = _TYPE_LABELS.get(mt, mt)
            lines.append(f"  - {label}: {count} 条")
        lines.append(f"  - 会话: {self.current_session_id or '未创建'}")
        return "\n".join(lines)

    def _update_memory(self, memory_id: str, **fields) -> str:
        """更新记忆"""
        for mt, memory in self.memory_manager.memory_types.items():
            try:
                if memory.update(memory_id, **fields):
                    return f"✅ 记忆已更新 (ID: {memory_id[:8]}...)"
            except NotImplementedError:
                continue
        return f"❌ 未找到记忆: {memory_id}"

    def _remove_memory(self, memory_id: str, **kwargs) -> str:
        """删除记忆"""
        for mt, memory in self.memory_manager.memory_types.items():
            try:
                if memory.remove(memory_id):
                    return f"🗑️ 记忆已删除 (ID: {memory_id[:8]}...)"
            except NotImplementedError:
                continue
        return f"❌ 未找到记忆: {memory_id}"

    def _clear_all(self, **kwargs) -> str:
        """清空所有记忆"""
        cleared = self.memory_manager.clear_all()
        parts = "，".join(f"{_TYPE_LABELS.get(k, k)} {v} 条" for k, v in cleared.items())
        return f"🧨 已清空全部记忆: {parts}"
