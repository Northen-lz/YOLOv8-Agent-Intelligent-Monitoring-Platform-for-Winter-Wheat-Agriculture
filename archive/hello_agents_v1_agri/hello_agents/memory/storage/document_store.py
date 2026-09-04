# -*- coding: utf-8 -*-
"""
Hello-Agents SQLite 文档存储
对齐文档第八章 8.2 存储后端层：SQLiteDocumentStore（结构化持久化）

职责：
- 建表与索引（记忆项 + 会话/用户/类型索引）
- 记忆项增 / 查 / 删 / 清空 / 计数
- 会话级与类型级过滤查询

输出日志对齐文档（PDF 页 235）：
[OK] SQLite 数据库表和索引创建完成
[OK] SQLite 文档存储初始化完成: ./memory_data/memory.db
"""

import json
import logging
import os
import sqlite3
from typing import List, Optional

from ..base import MemoryItem

logger = logging.getLogger(__name__)


class SQLiteDocumentStore:
    """SQLite 文档存储 - 结构化持久化记忆项"""

    def __init__(self, database_path: Optional[str] = None):
        self.database_path = database_path or "./memory_data/memory.db"
        # 确保父目录存在
        parent = os.path.dirname(os.path.abspath(self.database_path))
        os.makedirs(parent, exist_ok=True)

        self.conn = sqlite3.connect(self.database_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._initialize_db()
        print(f"[OK] SQLite 文档存储初始化完成: {self.database_path}")

    # ---------------- 初始化 ----------------

    def _initialize_db(self):
        """建表 + 索引"""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id          TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    importance  REAL NOT NULL DEFAULT 0.5,
                    timestamp   TEXT NOT NULL,
                    metadata    TEXT NOT NULL DEFAULT '{}',
                    user_id     TEXT NOT NULL DEFAULT 'default_user',
                    session_id  TEXT NOT NULL DEFAULT 'default'
                )
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_session "
                "ON memory_items (session_id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_user "
                "ON memory_items (user_id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_type "
                "ON memory_items (memory_type)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_timestamp "
                "ON memory_items (timestamp)"
            )
        print("[OK] SQLite 数据库表和索引创建完成")

    # ---------------- 写入 ----------------

    def add(self, memory_item: MemoryItem) -> str:
        """添加一条记忆"""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO memory_items
                (id, memory_type, content, importance, timestamp, metadata,
                 user_id, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_item.id,
                    memory_item.memory_type,
                    memory_item.content,
                    memory_item.importance,
                    memory_item.timestamp.isoformat(),
                    json.dumps(memory_item.metadata, ensure_ascii=False),
                    memory_item.user_id,
                    memory_item.session_id,
                ),
            )
        return memory_item.id

    def add_many(self, memory_items: List[MemoryItem]) -> List[str]:
        """批量添加"""
        ids = []
        with self.conn:
            for item in memory_items:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_items
                    (id, memory_type, content, importance, timestamp, metadata,
                     user_id, session_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.memory_type,
                        item.content,
                        item.importance,
                        item.timestamp.isoformat(),
                        json.dumps(item.metadata, ensure_ascii=False),
                        item.user_id,
                        item.session_id,
                    ),
                )
                ids.append(item.id)
        return ids

    # ---------------- 查询 ----------------

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """按ID获取记忆"""
        row = self.conn.execute(
            "SELECT * FROM memory_items WHERE id = ?", (memory_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def get_by_session(self, session_id: str) -> List[MemoryItem]:
        """按会话查询（对齐文档会话索引）"""
        rows = self.conn.execute(
            "SELECT * FROM memory_items WHERE session_id = ? "
            "ORDER BY timestamp ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_by_type(self, memory_type: str) -> List[MemoryItem]:
        """按记忆类型查询"""
        rows = self.conn.execute(
            "SELECT * FROM memory_items WHERE memory_type = ? "
            "ORDER BY timestamp ASC",
            (memory_type,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> List[MemoryItem]:
        """关键词模糊检索（兜底检索）"""
        rows = self.conn.execute(
            "SELECT * FROM memory_items WHERE content LIKE ? "
            "ORDER BY importance DESC, timestamp DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def list_all(self, limit: int = 100) -> List[MemoryItem]:
        """列出全部记忆（按时间倒序）"""
        rows = self.conn.execute(
            "SELECT * FROM memory_items ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    # ---------------- 删除 ----------------

    def delete(self, memory_id: str) -> bool:
        """按ID删除"""
        with self.conn:
            cur = self.conn.execute(
                "DELETE FROM memory_items WHERE id = ?", (memory_id,)
            )
        return cur.rowcount > 0

    def delete_by_session(self, session_id: str) -> int:
        """按会话删除，返回删除条数"""
        with self.conn:
            cur = self.conn.execute(
                "DELETE FROM memory_items WHERE session_id = ?", (session_id,)
            )
        return cur.rowcount

    def clear_all(self) -> int:
        """清空所有记忆，返回删除条数"""
        with self.conn:
            cur = self.conn.execute("DELETE FROM memory_items")
        return cur.rowcount

    def count(self) -> int:
        """记忆总数"""
        return self.conn.execute(
            "SELECT COUNT(*) FROM memory_items"
        ).fetchone()[0]

    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    # ---------------- 内部 ----------------

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem.from_dict(
            {
                "id": row["id"],
                "content": row["content"],
                "memory_type": row["memory_type"],
                "importance": row["importance"],
                "timestamp": row["timestamp"],
                "metadata": json.loads(row["metadata"]),
            }
        )

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
