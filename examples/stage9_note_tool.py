# -*- coding: utf-8 -*-
"""
第九章 Stage 2 验证脚本：NoteTool（文档 9.4 结构化笔记）

覆盖：
- create / read / update / search / list / summary / delete 七种操作
- Markdown + YAML 存储格式（文件头 YAML 元数据）
- notes_index.json 索引 + 重启重建（跨会话持久化）
- 文档 9.4.4 场景：记录项目进展 / 阻塞点

运行：python examples/stage9_note_tool.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hello_agents.tools import NoteTool


def main():
    print("=" * 80)
    print("Stage 2: NoteTool - 结构化笔记验证")
    print("=" * 80)

    workspace = os.path.join(tempfile.mkdtemp(), "project_notes")
    notes = NoteTool(workspace=workspace)

    # 1. create：记录任务状态（文档 9.4.4 场景）
    nid_state = notes.run({
        "action": "create",
        "title": "重构项目 - 第一阶段",
        "content": "已完成数据模型层的重构,测试覆盖率达到85%。下一步将重构业务逻辑层。",
        "note_type": "task_state",
        "tags": ["refactoring", "phase1"],
    })
    print(f"✅ 创建任务状态笔记: {nid_state}")

    # 2. create：记录阻塞点
    nid_blocker = notes.run({
        "action": "create",
        "title": "依赖冲突问题",
        "content": "发现某些第三方库版本不兼容,需要解决。影响范围:业务逻辑层的3个模块。",
        "note_type": "blocker",
        "tags": ["dependency", "urgent"],
    })
    print(f"✅ 创建阻塞点笔记: {nid_blocker}")

    # 3. read：读取笔记（验证 YAML + Markdown 分离）
    note = notes.run({"action": "read", "note_id": nid_state})
    assert "数据模型层" in note["content"]
    assert note["metadata"]["type"] == "task_state"
    print(f"✅ 读取笔记: '{note['metadata']['title']}' (type={note['metadata']['type']})")

    # 4. search：关键词搜索
    results = notes.run({"action": "search", "query": "依赖", "limit": 3})
    assert len(results) == 1 and results[0]["note_id"] == nid_blocker
    print(f"✅ 搜索'依赖': {[r['title'] for r in results]}")

    # 5. list：按类型过滤
    blockers = notes.run({"action": "list", "note_type": "blocker"})
    assert len(blockers) == 1
    print(f"✅ 列出 blocker 笔记: {[b['title'] for b in blockers]}")

    # 6. update：解决阻塞后标记为 conclusion（文档 9.4.5 最佳实践）
    result = notes.run({
        "action": "update",
        "note_id": nid_blocker,
        "note_type": "conclusion",
        "tags": ["resolved"],
    })
    assert "已更新" in result
    assert notes.run({"action": "read", "note_id": nid_blocker})["metadata"]["type"] == "conclusion"
    print("✅ 更新笔记: blocker → conclusion")

    # 7. summary：笔记摘要统计
    summary = notes.run({"action": "summary"})
    print(f"📊 笔记摘要: {summary}")
    assert summary["total_notes"] == 2
    assert summary["type_distribution"].get("conclusion") == 1
    assert summary["type_distribution"].get("task_state") == 1
    print("✅ 摘要统计正确")

    # 8. 跨会话持久化：重启后索引重建
    notes_reload = NoteTool(workspace=workspace)
    assert notes_reload.run({"action": "summary"})["total_notes"] == 2
    print("✅ 重启后索引重建成功（跨会话持久化）")

    # 9. delete：删除笔记
    result = notes.run({"action": "delete", "note_id": nid_state})
    assert "已删除" in result
    assert notes.run({"action": "summary"})["total_notes"] == 1
    print(f"✅ 删除笔记: {result}")

    # 10. 展示磁盘上的存储格式
    import glob
    md_file = glob.glob(os.path.join(workspace, "note_*.md"))[0]
    with open(md_file, "r", encoding="utf-8") as f:
        raw = f.read()
    print("\n--- 笔记文件格式（Markdown + YAML） ---")
    print(raw)

    print("\n🎉 Stage 2 验证全部通过")


if __name__ == "__main__":
    main()
