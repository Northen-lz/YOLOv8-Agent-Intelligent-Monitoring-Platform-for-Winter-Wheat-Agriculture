# -*- coding: utf-8 -*-
"""
农业知识图谱种子脚本（语义记忆 + Neo4j 图）

把 hello_agents/knowledge/ 下的文本知识灌入「语义记忆」双库：
- Qdrant 向量库（集合 hello_agents_vectors，memory_type="semantic"）
- Neo4j 图谱（Entity 节点 + RELATES 关系边）

再写入一份**人工整理的农业本体关系**（冬小麦生育期 / 需水关键期 / 干旱危害等），
使「干旱影响哪些生育期」这类关联推理题能通过图检索（1-hop 邻居）命中。
若 Qdrant/Neo4j 未启动，脚本会明确提示并安全退出。

用法（需先启动 Qdrant + Neo4j）：
    python scripts/seed_rag_graph.py
"""

import glob
import os
import sys

# 确保可导入 hello_agents 包（从项目根）
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from hello_agents.core.config import Config
from hello_agents.memory.base import MemoryConfig, MemoryItem
from hello_agents.memory.rag.document import _split_paragraphs_with_headings
from hello_agents.memory.types.semantic import SemanticMemory

USER_ID = "agriculture_user"

# 人工整理农业本体（三元组：源实体 -关系-> 目标实体）
# 实体/关系均取自 knowledge/*.txt 的真实内容，不编造
ONTOLOGY = [
    # 生育期结构
    ("冬小麦", "生育期包含", "播种期"),
    ("冬小麦", "生育期包含", "出苗期"),
    ("冬小麦", "生育期包含", "分蘖期"),
    ("冬小麦", "生育期包含", "越冬期"),
    ("冬小麦", "生育期包含", "返青期"),
    ("冬小麦", "生育期包含", "拔节期"),
    ("冬小麦", "生育期包含", "抽穗开花期"),
    ("冬小麦", "生育期包含", "灌浆成熟期"),
    # 需水关键期
    ("拔节期", "需水关键期", "干旱"),
    ("抽穗开花期", "需水关键期", "干旱"),
    ("灌浆成熟期", "需水关键期", "干旱"),
    ("拔节期", "需水需肥高峰期", "冬小麦"),
    # 干旱危害链
    ("干旱", "显著降低", "结实率"),
    ("高温干旱", "造成", "灌浆不足"),
    ("高温干旱", "造成", "千粒重下降"),
    ("水分亏缺", "表现为", "气孔关闭"),
    ("水分亏缺", "导致", "光合速率下降"),
    ("干旱胁迫", "导致", "减产"),
    ("干旱胁迫", "监测手段", "叶绿素荧光"),
    ("干旱胁迫", "监测手段", "土壤墒情"),
    ("叶绿素荧光", "反映", "PSII功能状态"),
    ("Fv/Fm", "衡量", "胁迫程度"),
    # 产量与灌溉
    ("产量", "构成要素", "亩穗数"),
    ("产量", "构成要素", "穗粒数"),
    ("产量", "构成要素", "千粒重"),
    ("节水灌溉", "优先保证", "拔节期"),
    ("节水灌溉", "优先保证", "灌浆期"),
]


def main():
    semantic = SemanticMemory(config=MemoryConfig())
    # 触发懒加载构造，并检查双库连接
    try:
        vs = semantic.vector_store
        gs = semantic.graph_store
    except Exception as e:
        print(f"⚠️ 语义记忆后端构造失败: {e}")
        return 1
    if getattr(vs, "connected", True) is False:
        print("⚠️ Qdrant 未连接（localhost:6333），无法灌语义记忆。")
        print("   请先启动 Qdrant 容器。")
        return 1
    if getattr(gs, "connected", True) is False:
        print("⚠️ Neo4j 未连接（bolt://localhost:7687），无法灌图谱。")
        print("   请先启动 Neo4j 容器。")
        return 1

    # 幂等：先清空该用户的旧语义记忆（向量 + 图谱），再重灌
    try:
        old_vec = vs.delete_by_filter(user_id=USER_ID, memory_type="semantic")
        print(f"🧹 已清空旧语义向量（删除返回值: {old_vec}）")
    except Exception as e:
        print(f"⚠️ 清空旧语义向量失败（继续）: {e}")
    try:
        old_graph = gs.clear(user_id=USER_ID)
        print(f"🧹 已清空旧图谱节点（{old_graph}）")
    except Exception as e:
        print(f"⚠️ 清空旧图谱失败（继续）: {e}")

    # ---- 1. 把知识文本按标题分段，逐段灌入语义记忆（Qdrant+Neo4j 双写）----
    knowledge_dir = Config.KNOWLEDGE_DIR
    files = sorted(glob.glob(os.path.join(knowledge_dir, "*.txt")))
    if not files:
        print(f"⚠️ 未在 {knowledge_dir} 找到任何 .txt 知识文件")
        return 1

    total_memories = 0
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            content = fh.read()
        sections = _split_paragraphs_with_headings(content)
        src = os.path.basename(f)
        n = 0
        for sec in sections:
            mid = semantic.add(MemoryItem(
                content=sec["content"],
                memory_type="semantic",
                importance=0.7,
                metadata={"user_id": USER_ID, "source": src},
            ))
            if mid:
                n += 1
        print(f"  {src:28s} -> 灌入 {n} 段语义记忆")
        total_memories += n

    # ---- 2. 写入人工整理的本体关系（MERGE 实体 + RELATES 边）----
    for a, rel, b in ONTOLOGY:
        try:
            gs.upsert_entity(a, user_id=USER_ID)
            gs.upsert_entity(b, user_id=USER_ID)
            gs.create_relation(a, rel, b, user_id=USER_ID)
        except Exception as e:
            print(f"  ⚠️ 关系 {a}-{rel}->{b} 写入失败: {e}")
    print(f"✅ 本体关系写入完成：{len(ONTOLOGY)} 条")

    # ---- 3. 统计 ----
    stats = gs.get_graph_stats(user_id=USER_ID)
    print(f"\n✅ 图谱灌入完成：语义记忆 {total_memories} 段；"
          f"图谱实体 {stats['entities']} 个 / 关系 {stats['relations']} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
