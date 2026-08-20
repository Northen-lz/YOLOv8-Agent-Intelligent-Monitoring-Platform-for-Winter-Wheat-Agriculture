# -*- coding: utf-8 -*-
"""
阶段2 验证：四种记忆类型 + 存储后端（Qdrant/Neo4j）

运行: python examples/stage2_memory_types.py
依赖: Docker 中 qdrant + neo4j 容器运行中
"""
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hello_agents.memory import MemoryConfig, MemoryItem
from hello_agents.memory.types import (
    WorkingMemory,
    EpisodicMemory,
    SemanticMemory,
    PerceptualMemory,
)

TEST_USER = "stage2_test_user"
TEST_SESSION = "stage2_test_session"


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def make_item(content, mtype="general", importance=0.6, **meta):
    m = {"session_id": TEST_SESSION, "user_id": TEST_USER}
    m.update(meta)
    return MemoryItem(content=content, memory_type=mtype,
                      importance=importance, metadata=m)


def test_working():
    section("[1] 工作记忆 WorkingMemory（纯内存 + TTL + 容量）")
    cfg = MemoryConfig(working_memory_capacity=3, working_memory_ttl=60)
    wm = WorkingMemory(cfg)

    wm.add(make_item("用户名字叫张三", importance=0.9))
    wm.add(make_item("张三是一名Python开发者", importance=0.8))
    wm.add(make_item("张三喜欢羽毛球运动", importance=0.5))
    wm.add(make_item("李四是前端工程师", importance=0.7))  # 触发容量管理
    print(f"  容量=3, 添加4条后剩余: {wm.count()}")
    assert wm.count() <= 3

    hits = wm.retrieve("张三", limit=3)
    print(f"  检索'张三' 返回 {len(hits)} 条:")
    for h in hits:
        print(f"    - {h.content[:40]} (importance={h.importance:.1f})")
    assert len(hits) >= 1 and "张三" in hits[0].content

    # TTL 过期
    print("  -- TTL 过期测试 --")
    old = make_item("过期记忆测试内容", importance=0.5)
    old.timestamp = datetime.now() - timedelta(minutes=61)
    wm.memories.append(old)
    before = wm.count()
    wm.retrieve("过期记忆")  # 触发清理
    print(f"  过期清理: {before} -> {wm.count()}")
    assert wm.count() < before
    print("  ✅ 工作记忆验证通过")


def test_episodic():
    section("[2] 情景记忆 EpisodicMemory（SQLite + Qdrant）")
    em = EpisodicMemory()
    # 清理历史测试数据
    em.clear()

    for content, imp, day in [
        ("今天完成了记忆系统第八章学习", 0.8, 0),
        ("昨天和团队评审了RAG设计方案", 0.7, 1),
        ("上周修复了向量检索的bug", 0.6, 7),
    ]:
        item = make_item(content, mtype="episodic", importance=imp,
                         session_id=TEST_SESSION, user_id=TEST_USER)
        item.timestamp = datetime.now() - timedelta(days=day)
        em.add(item)
    print(f"  添加3条, count={em.count()}")

    hits = em.retrieve("记忆系统学习", limit=3, user_id=TEST_USER)
    print(f"  检索'记忆系统学习' 返回 {len(hits)} 条:")
    for h in hits:
        print(f"    - [{h.timestamp.strftime('%m-%d')}] {h.content[:40]}")
    assert len(hits) >= 1

    # 会话历史
    history = em.get_history(TEST_SESSION)
    print(f"  会话历史 {len(history)} 条")
    assert len(history) == 3

    em.clear()
    print("  ✅ 情景记忆验证通过")


def test_semantic():
    section("[3] 语义记忆 SemanticMemory（Qdrant + Neo4j + 实体提取）")
    sm = SemanticMemory()
    sm.clear()

    sm.add(make_item("张三是一名Python开发者，擅长机器学习", importance=0.9))
    sm.add(make_item("李四是一名前端工程师，精通React框架", importance=0.8))
    sm.add(make_item("张三和李四一起开发智能Agent项目", importance=0.7))

    # 检查图谱实体
    stats = sm.graph_store.get_graph_stats(user_id=TEST_USER)
    print(f"  Neo4j 图谱: 实体 {stats['entities']} 个, 关系 {stats['relations']} 条")
    assert stats["entities"] >= 3

    hits = sm.retrieve("Python开发者擅长什么", limit=3, user_id=TEST_USER)
    print(f"  检索'Python开发者' 返回 {len(hits)} 条:")
    for h in hits:
        print(f"    - {h.content[:40]}")
    assert len(hits) >= 1 and "张三" in hits[0].content

    sm.clear()
    print("  ✅ 语义记忆验证通过")


def test_perceptual():
    section("[4] 感知记忆 PerceptualMemory（简化多模态）")
    pm = PerceptualMemory()
    pm.clear()

    pm.add(make_item("会议室的照片", importance=0.5,
                     modality="image", file_path="/data/meeting.jpg",
                     description="会议室里一群人开会"))
    pm.add(make_item("欢迎致词音频", importance=0.4,
                     modality="audio", file_path="/data/welcome.mp3",
                     description="开幕式的欢迎致词"))
    pm.add(make_item("这是智能Agent的介绍文档", importance=0.6))

    print(f"  count={pm.count()}")

    # 文本检索（应命中文本类）
    text_hits = pm.retrieve("智能Agent", limit=3, user_id=TEST_USER)
    print(f"  文本检索'智能Agent': {len(text_hits)} 条")
    assert len(text_hits) >= 1

    # 图像模态检索（跨模态：用文本描述检索图像）
    img_hits = pm.retrieve("一群人开会", limit=3, user_id=TEST_USER,
                           target_modality="image")
    print(f"  图像模态检索'一群人开会': {len(img_hits)} 条")
    for h in img_hits:
        print(f"    - [{h.metadata.get('modality')}] {h.content[:30]} "
              f"(path={h.metadata.get('file_path')})")
    assert len(img_hits) >= 1 and img_hits[0].metadata.get("modality") == "image"

    pm.clear()
    print("  ✅ 感知记忆验证通过")


def main():
    t0 = time.time()
    test_working()
    test_episodic()
    test_semantic()
    test_perceptual()
    print("\n" + "=" * 60)
    print(f"✅ 阶段2 四种记忆类型验证全部通过！耗时 {time.time()-t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
