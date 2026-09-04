# -*- coding: utf-8 -*-
"""
RAG 知识库种子脚本
把 wheat/knowledge/ 下的文本知识（作者/实验/干旱/小麦生长/YOLO）灌入
Qdrant 向量库（集合 agriculture_kb），供 AgricultureExpertAgent 的 rag 工具检索。

通用能力来自 ha_framework（pip install -e ./framework 后可直接 import）；
领域路径（知识库/集合名）由 wheat.core.config.Config 提供。

用法（products/wheat 目录，需先启动 Qdrant 服务）：
    python scripts/seed_rag_knowledge.py

若 Qdrant 未启动，脚本会给出明确提示并安全退出（不报错）。
"""

import glob
import os
import sys

# 确保可导入 wheat 产品包（scripts/ 上一级 = products/wheat）；
# ha_framework 由 pip editable 安装，任意目录可直接 import。
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from wheat.core.config import Config
from ha_framework.tools.builtin.rag_tool import RAGTool


def main():
    knowledge_dir = Config.KNOWLEDGE_DIR
    files = sorted(glob.glob(os.path.join(knowledge_dir, "*.txt")))
    if not files:
        print(f"⚠️ 未在 {knowledge_dir} 找到任何 .txt 知识文件")
        return 1

    print(f"📂 知识目录: {knowledge_dir}（共 {len(files)} 个文件）")

    rag = RAGTool(
        knowledge_base_path=Config.KNOWLEDGE_DIR,
        collection_name="agriculture_kb",
        rag_namespace="agriculture_kb",
    )

    # 预检：Qdrant 未连接则直接说明
    store = rag._get_pipeline("agriculture_kb")["store"]
    if getattr(store, "connected", True) is False:
        print("⚠️ Qdrant 向量服务未连接（localhost:6333），无法灌入知识库。")
        print("   请先启动 Qdrant，例如：")
        print("     docker run -p 6333:6333 qdrant/qdrant")
        print("   或在已有本地 Qdrant 时设置 QDRANT_URL 环境变量。")
        return 1

    # 细粒度重灌：先清空该集合内已有的 RAG 分块（memory_type="rag_chunk"），
    # 再以较小 chunk 重新灌入，避免重复叠加 / 块太粗召回不准。
    # （collection 专用于 agriculture_kb，清空 rag_chunk 即清空本集合）
    try:
        store = rag._get_pipeline("agriculture_kb")["store"]
        before = store.count()
        if before > 0:
            removed = store.delete_by_filter(memory_type="rag_chunk")
            print(f"🧹 已清空旧 RAG 分块 {before} 条（删除返回值: {removed}）")
    except Exception as e:
        print(f"⚠️ 清空旧分块失败（继续重灌）: {e}")

    total_chunks = 0
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            content = fh.read()
        if not content.strip():
            continue
        result = rag.execute(
            "add_text",
            content=content,
            source=os.path.relpath(f, Config.PROJECT_ROOT),
            # 粗块 1000/200：实测对 384 维 TFIDF（char_wb 2-3 元）效果最佳。
            # 细块 350/60 反而召回变差——中文短文本下小块相似度分不清，
            # 粗块 + MQE/HyDE 查询扩展是唯一出过好成绩（0.68+）的组合。
            chunk_size=1000,
            chunk_overlap=200,
        )
        print(f"  {os.path.basename(f):28s} -> {result}")
        # 统计分块数（add_text 返回 "✅ 已添加知识，生成 N 个分块"）
        try:
            total_chunks += int(result.split("生成")[-1].split("个")[0].strip())
        except Exception:
            pass

    print(f"\n✅ 灌入完成：{len(files)} 个文件 / 共 {total_chunks} 个分块")
    print(rag.execute("stats", rag_namespace="agriculture_kb"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
