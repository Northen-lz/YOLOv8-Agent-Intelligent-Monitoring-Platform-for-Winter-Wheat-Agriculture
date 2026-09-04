# -*- coding: utf-8 -*-
"""
Hello-Agents 结构化笔记工具（NoteTool）
对齐文档第九章 9.4

设计理念（文档 9.4.1）：
- 以 Markdown 文件为载体，头部 YAML 前置元数据记录关键信息
- 正文记录状态、结论、阻塞与行动项等内容
- 人类可读 + 版本控制友好 + 易于回注上下文

存储格式（文档 9.4.2）：
- 每个笔记 = 独立 {note_id}.md 文件（YAML 头 + Markdown 正文）
- 文件名即 ID；notes_index.json 维护元数据索引

七个核心操作（文档 9.4.3）：
  create / read / update / search / list / summary / delete

笔记类型（文档 9.4.5）：
  task_state / conclusion / blocker / action / reference / general
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..base import BaseTool


class NoteTool(BaseTool):
    """结构化笔记工具 - 为长时程任务提供持久化外部记忆"""

    # 合法笔记类型
    NOTE_TYPES = ("task_state", "conclusion", "blocker", "action", "reference", "general")

    def __init__(self, workspace: str = "./notes"):
        super().__init__(
            name="note",
            description="结构化笔记工具 - 支持智能体进行持久化记忆管理（Markdown+YAML）",
        )
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        # 索引文件路径
        self.index_file = os.path.join(self.workspace, "notes_index.json")
        # 笔记 ID 序号（避免删除后 len(index) 复用导致冲突）
        self._id_seq = 0
        # 笔记索引：note_id -> metadata
        self.index: Dict[str, Dict[str, Any]] = {}
        self._load_index()

    # ---------------- 统一入口 ----------------

    def execute(self, action: str = "summary", **kwargs):
        """执行笔记操作（返回结构化数据或字符串）"""
        handlers = {
            "create": self._create_note,
            "read": self._read_note,
            "update": self._update_note,
            "search": self._search_notes,
            "list": self._list_notes,
            "summary": self._summary,
            "delete": self._delete_note,
        }
        handler = handlers.get((action or "").strip().lower())
        if handler is None:
            return f"❌ 不支持的操作: {action}（可选: {', '.join(handlers)}）"
        try:
            return handler(**kwargs)
        except ValueError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"❌ 操作 {action} 执行失败: {e}"

    def run(self, *args, **kwargs):
        """兼容 BaseTool.run，支持文档写法 run({"action": "create", ...})"""
        if kwargs:
            action = kwargs.pop("action", "summary")
            return self.execute(action=action, **kwargs)
        if args:
            if isinstance(args[0], dict):
                params = dict(args[0])
                action = params.pop("action", "summary")
                return self.execute(action=action, **params)
            return self.execute(*args)
        return self.execute("summary")

    # ---------------- 索引管理 ----------------

    def _load_index(self):
        """加载索引文件（不存在/损坏时重建）"""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.index = loaded
                    # 恢复 ID 序号
                    max_seq = -1
                    for note_id in self.index:
                        try:
                            max_seq = max(max_seq, int(note_id.rsplit("_", 1)[-1]))
                        except ValueError:
                            pass
                    self._id_seq = max_seq + 1
                    return
            except Exception as e:
                print(f"[WARNING] 索引加载失败,将重建: {e}")
        # 重建：扫描工作目录中的 .md 文件
        self._rebuild_index()

    def _rebuild_index(self):
        """从工作目录扫描重建索引（直接解析文件，不依赖现有索引）"""
        self.index = {}
        max_seq = -1
        for filename in sorted(os.listdir(self.workspace)):
            if filename.startswith("note_") and filename.endswith(".md"):
                note_id = filename[:-3]
                try:
                    file_path = os.path.join(self.workspace, filename)
                    with open(file_path, "r", encoding="utf-8") as f:
                        raw_content = f.read()
                    metadata, _content = self._parse_markdown(raw_content)
                    metadata["file_path"] = file_path
                    # 外部生成的笔记补默认字段，避免 _summary 等 KeyError
                    metadata.setdefault("id", note_id)
                    metadata.setdefault("type", "general")
                    metadata.setdefault("tags", [])
                    metadata.setdefault("title", note_id)
                    metadata.setdefault("created_at", "")
                    metadata.setdefault("updated_at", "")
                    self.index[note_id] = metadata
                    # 恢复 ID 序号
                    try:
                        max_seq = max(max_seq, int(note_id.rsplit("_", 1)[-1]))
                    except ValueError:
                        pass
                except Exception as e:
                    print(f"[WARNING] 重建索引跳过 {filename}: {e}")
                    continue
        self._id_seq = max_seq + 1
        if self.index:
            self._save_index()

    def _save_index(self):
        """保存索引到 JSON 文件"""
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    # ---------------- 操作1：create ----------------

    def _create_note(
            self,
            title: str,
            content: str,
            note_type: str = "general",
            tags: Optional[List[str]] = None,
    ) -> str:
        """创建笔记

        Args:
            title: 笔记标题
            content: 笔记内容(Markdown格式)
            note_type: 笔记类型(task_state/conclusion/blocker/action/reference/general)
            tags: 标签列表

        Returns:
            str: 笔记ID
        """
        if not title:
            raise ValueError("笔记标题不能为空")
        note_type = self._normalize_type(note_type)

        # 1. 生成唯一ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_id = f"note_{timestamp}_{self._id_seq}"
        self._id_seq += 1

        # 2. 构建元数据
        metadata = {
            "id": note_id,
            "title": title,
            "type": note_type,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        # 3. 构建完整的 Markdown 文件内容
        md_content = self._build_markdown(metadata, content)
        # 4. 保存到文件
        file_path = os.path.join(self.workspace, f"{note_id}.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        # 5. 更新索引
        metadata["file_path"] = file_path
        self.index[note_id] = metadata
        self._save_index()
        return note_id

    def _normalize_type(self, note_type: str) -> str:
        """标准化笔记类型（非法类型回退为 general）"""
        note_type = (note_type or "general").strip().lower()
        return note_type if note_type in self.NOTE_TYPES else "general"

    def _build_markdown(self, metadata: Dict, content: str) -> str:
        """构建 Markdown 文件内容(YAML + 正文)"""
        # YAML 前置元数据
        yaml_header = yaml.dump(metadata, allow_unicode=True, sort_keys=False)
        # 组合格式
        return f"---\n{yaml_header}---\n\n{content}"

    # ---------------- 操作2：read ----------------

    def _read_note(self, note_id: str) -> Dict:
        """读取笔记内容

        Args:
            note_id: 笔记ID

        Returns:
            Dict: 包含元数据和内容的字典
        """
        if note_id not in self.index:
            raise ValueError(f"笔记不存在: {note_id}")
        file_path = self.index[note_id]["file_path"]
        # 读取文件
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
        # 解析 YAML 元数据和 Markdown 正文
        metadata, content = self._parse_markdown(raw_content)
        return {
            "metadata": metadata,
            "content": content,
        }

    def _parse_markdown(self, raw_content: str) -> Tuple[Dict, str]:
        """解析 Markdown 文件(分离 YAML 和正文)"""
        # 查找 YAML 分隔符
        parts = raw_content.split("---\n", 2)
        if len(parts) >= 3:
            # 有 YAML 前置元数据
            yaml_str = parts[1]
            content = parts[2].strip()
            metadata = yaml.safe_load(yaml_str) or {}
        else:
            # 无元数据,全部作为正文
            metadata = {}
            content = raw_content.strip()
        return metadata, content

    # ---------------- 操作3：update ----------------

    def _update_note(
            self,
            note_id: str,
            title: Optional[str] = None,
            content: Optional[str] = None,
            note_type: Optional[str] = None,
            tags: Optional[List[str]] = None,
    ) -> str:
        """更新笔记

        Args:
            note_id: 笔记ID
            title: 新标题(可选)
            content: 新内容(可选)
            note_type: 新类型(可选)
            tags: 新标签(可选)

        Returns:
            str: 操作结果消息
        """
        if note_id not in self.index:
            raise ValueError(f"笔记不存在: {note_id}")
        # 1. 读取现有笔记
        note = self._read_note(note_id)
        metadata = note["metadata"]
        old_content = note["content"]
        # 2. 更新字段
        if title:
            metadata["title"] = title
        if note_type:
            metadata["type"] = self._normalize_type(note_type)
        if tags is not None:
            metadata["tags"] = tags
        if content is not None:
            old_content = content
        # 更新时间戳
        metadata["updated_at"] = datetime.now().isoformat()
        # 3. 重新构建并保存（file_path 从索引获取，解析元数据中不含该字段）
        md_content = self._build_markdown(metadata, old_content)
        file_path = self.index[note_id]["file_path"]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        # 4. 更新索引（补回 file_path，解析元数据中不含该字段）
        metadata["file_path"] = file_path
        self.index[note_id] = metadata
        self._save_index()
        return f"✅ 笔记已更新: {metadata['title']}"

    # ---------------- 操作4：search ----------------

    def _search_notes(
            self,
            query: str,
            limit: int = 10,
            note_type: Optional[str] = None,
            tags: Optional[List[str]] = None,
    ) -> List[Dict]:
        """搜索笔记

        Args:
            query: 搜索关键词
            limit: 返回数量限制
            note_type: 按类型过滤(可选)
            tags: 按标签过滤(可选)

        Returns:
            List[Dict]: 匹配的笔记列表
        """
        results = []
        query_lower = (query or "").lower()
        for note_id, metadata in self.index.items():
            # 类型过滤
            if note_type and metadata.get("type") != note_type:
                continue
            # 标签过滤
            if tags:
                note_tags = set(metadata.get("tags", []))
                if not note_tags.intersection(tags):
                    continue
            # 读取笔记内容
            try:
                note = self._read_note(note_id)
                content = note["content"]
                title = metadata.get("title", "")
                # 在标题和内容中搜索
                if query_lower in title.lower() or query_lower in content.lower():
                    results.append({
                        "note_id": note_id,
                        "title": title,
                        "type": metadata.get("type"),
                        "tags": metadata.get("tags", []),
                        "content": content,
                        "updated_at": metadata.get("updated_at"),
                    })
            except Exception as e:
                print(f"[WARNING] 读取笔记 {note_id} 失败: {e}")
                continue
        # 按更新时间排序
        results.sort(key=lambda x: x["updated_at"] or "", reverse=True)
        return results[:limit]

    # ---------------- 操作5：list ----------------

    def _list_notes(
            self,
            note_type: Optional[str] = None,
            tags: Optional[List[str]] = None,
            limit: int = 20,
    ) -> List[Dict]:
        """列出笔记(按更新时间倒序)

        Args:
            note_type: 按类型过滤(可选)
            tags: 按标签过滤(可选)
            limit: 返回数量限制

        Returns:
            List[Dict]: 笔记元数据列表
        """
        results = []
        for note_id, metadata in self.index.items():
            # 类型过滤
            if note_type and metadata.get("type") != note_type:
                continue
            # 标签过滤
            if tags:
                note_tags = set(metadata.get("tags", []))
                if not note_tags.intersection(tags):
                    continue
            results.append(metadata)
        # 按更新时间排序
        results.sort(key=lambda x: x.get("updated_at", "") or "", reverse=True)
        return results[:limit]

    # ---------------- 操作6：summary ----------------

    def _summary(self) -> Dict[str, Any]:
        """生成笔记摘要统计

        Returns:
            Dict: 统计信息
        """
        total_count = len(self.index)
        # 按类型统计
        type_counts = {}
        for metadata in self.index.values():
            note_type = metadata.get("type", "general")
            type_counts[note_type] = type_counts.get(note_type, 0) + 1
        # 最近更新的笔记
        recent_notes = sorted(
            self.index.values(),
            key=lambda x: x.get("updated_at", "") or "",
            reverse=True,
        )[:5]
        return {
            "total_notes": total_count,
            "type_distribution": type_counts,
            "recent_notes": [
                {
                    "id": note.get("id", ""),
                    "title": note.get("title", ""),
                    "type": note.get("type"),
                    "updated_at": note.get("updated_at"),
                }
                for note in recent_notes
            ],
        }

    # ---------------- 操作7：delete ----------------

    def _delete_note(self, note_id: str) -> str:
        """删除笔记

        Args:
            note_id: 笔记ID

        Returns:
            str: 操作结果消息
        """
        if note_id not in self.index:
            raise ValueError(f"笔记不存在: {note_id}")
        # 1. 删除文件
        file_path = self.index[note_id]["file_path"]
        if os.path.exists(file_path):
            os.remove(file_path)
        # 2. 从索引中移除
        title = self.index[note_id].get("title", note_id)
        del self.index[note_id]
        self._save_index()
        return f"✅ 笔记已删除: {title}"
