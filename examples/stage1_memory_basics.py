# -*- coding: utf-8 -*-
"""
阶段1 验证：记忆系统基础（MemoryItem / MemoryConfig / SQLiteDocumentStore）

运行: python examples/stage1_memory_basics.py
"""
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hello_agents.memory import MemoryConfig, MemoryItem
from hello_agents.memory.storage import SQLiteDocumentStore


def main():
    print("=" * 60)
    print("阶段1验证：记忆系统基础数据结构 + SQLite 存储")
    print("=" * 60)

    # 1. MemoryItem 创建
    print("\n[1] 创建 MemoryItem ...")
    item = MemoryItem(
        content="我叫张三，是一名Python开发者",
        memory_type="semantic",
        importance=0.9,
        metadata={"session_id": "s1", "user_id": "user123"},
    )
    print("  id:", item.id)
    print("  type:", item.memory_type)
    print("  importance:", item.importance)
    print("  session:", item.session_id, "| user:", item.user_id)
    assert item.importance == 0.9

    # 序列化往返
    data = item.to_dict()
    restored = MemoryItem.from_dict(data)
    assert restored.id == item.id
    assert restored.content == item.content
    print("  ✅ 序列化/反序列化往返成功")

    # 2. MemoryConfig
    print("\n[2] MemoryConfig 配置 ...")
    cfg = MemoryConfig()
    print(f"  working_capacity={cfg.working_memory_capacity}, "
          f"ttl={cfg.working_memory_ttl}min, db={cfg.database_path}")
    print(f"  qdrant={cfg.qdrant_url}, collection={cfg.qdrant_collection}, "
          f"vector_size={cfg.qdrant_vector_size}")
    print(f"  embed_type={cfg.embed_model_type}, model={cfg.embed_model_name}")

    # 3. SQLite 存储
    print("\n[3] SQLiteDocumentStore ...")
    tmp_db = os.path.join(tempfile.gettempdir(), "memory_stage1_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    store = SQLiteDocumentStore(tmp_db)

    # 批量添加
    items = [
        MemoryItem(content="张三喜欢Python编程", memory_type="semantic",
                   importance=0.8, metadata={"session_id": "s1", "user_id": "user123"}),
        MemoryItem(content="今天学习了记忆系统架构", memory_type="episodic",
                   importance=0.7, metadata={"session_id": "s1", "user_id": "user123"}),
        MemoryItem(content="前端工程师李四擅长React", memory_type="semantic",
                   importance=0.6, metadata={"session_id": "s2", "user_id": "user123"}),
    ]
    ids = store.add_many(items)
    print(f"  添加 {len(ids)} 条记忆, count={store.count()}")

    # 会话查询
    s1 = store.get_by_session("s1")
    print(f"  会话 s1 记忆数: {len(s1)}")
    assert len(s1) == 2

    # 类型查询
    sem = store.get_by_type("semantic")
    print(f"  semantic 类型记忆数: {len(sem)}")

    # 关键词检索
    hits = store.search("Python")
    print(f"  关键词 'Python' 命中: {len(hits)} 条")
    assert len(hits) >= 1

    # ID 查询
    got = store.get(ids[0])
    assert got is not None and got.content == items[0].content
    print("  ✅ ID 查询成功")

    # 删除
    deleted = store.delete(ids[2])
    print(f"  删除一条: {deleted}, count={store.count()}")
    assert deleted

    # 清空
    cleared = store.clear_all()
    print(f"  清空: {cleared} 条, count={store.count()}")
    assert store.count() == 0

    store.close()
    os.remove(tmp_db)
    print("\n" + "=" * 60)
    print("✅ 阶段1基础验证全部通过！")
    print("=" * 60)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\n耗时: {time.time() - t0:.1f}s")
