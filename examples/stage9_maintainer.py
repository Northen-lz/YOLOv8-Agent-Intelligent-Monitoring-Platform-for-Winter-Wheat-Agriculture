# -*- coding: utf-8 -*-
"""
第九章 Stage 6 验证脚本：代码库维护助手（文档 9.6.4 完整使用示例）

覆盖三层架构整合：
- ContextBuilder（GSSC 上下文构建）
- NoteTool（结构化笔记 / 任务追踪）
- TerminalTool（即时代码库探索）
- MemoryTool（记忆系统）

⚠️ 本脚本会真实调用 LLM（DeepSeek），请确保 .env 已配置 LLM_API_KEY。
    在临时目录运行，避免污染项目根目录。

运行：python examples/stage9_maintainer.py
"""

import json
import os
import shutil
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from hello_agents.agents.codebase_maintainer import CodebaseMaintainer  # noqa: E402


def main():
    print("=" * 80)
    print("Stage 6: CodebaseMaintainer - 长程智能体验证")
    print("=" * 80)

    # 笔记目录放到临时目录，避免污染项目根
    # （保持 cwd 在项目根，确保 .env 中的 LLM_API_KEY 正常加载）
    notes_workspace = os.path.join(tempfile.mkdtemp(prefix="stage9_notes_"), "notes")
    codebase_path = os.path.join(PROJECT_ROOT, "examples", "sample_flask_app")

    # ========== 初始化助手（文档 9.6.4） ==========
    maintainer = CodebaseMaintainer(
        project_name="my_flask_app",
        codebase_path=codebase_path,
        notes_workspace=notes_workspace,
    )

    # ========== 第一天：探索代码库 ==========
    print("\n--- 1. 探索代码库结构 ---")
    response = maintainer.explore()
    print(f"\n🤖 助手: {response[:400]}...")

    # ========== 深入分析某个模块 ==========
    print("\n--- 2. 分析数据模型设计 ---")
    response = maintainer.run("请分析 app/models/ 目录下的数据模型设计")
    print(f"\n🤖 助手: {response[:400]}...")

    # ========== 分析代码质量 ==========
    print("\n--- 3. 整体质量分析 ---")
    response = maintainer.analyze()
    print(f"\n🤖 助手: {response[:400]}...")

    # ========== 规划下一步任务 ==========
    print("\n--- 4. 规划下一步任务 ---")
    response = maintainer.plan_next_steps()
    print(f"\n🤖 助手: {response[:400]}...")

    # ========== 手动创建详细的重构计划 ==========
    print("\n--- 5. 手动创建重构计划 ---")
    maintainer.create_note(
        title="本周重构计划 - Week 1",
        content="""## 目标
完成数据模型层的优化
## 任务清单
- [ ] 为 User.email 添加唯一约束
- [ ] 为 Order 添加 created_at, updated_at 字段
- [ ] 编写数据库迁移脚本
- [ ] 更新相关测试用例
## 风险
- 数据库迁移可能影响线上环境,需要在非高峰期执行""",
        note_type="task_state",
        tags=["refactoring", "week1", "high_priority"],
    )
    print("✅ 已创建详细的重构计划")

    # ========== 检查进度与生成报告 ==========
    print("\n--- 6. 笔记摘要 ---")
    summary = maintainer.note_tool.run({"action": "summary"})
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    assert summary["total_notes"] >= 1, "至少应有一条笔记"
    assert summary["type_distribution"].get("blocker") or summary["type_distribution"].get("action"), \
        "应自动生成 blocker/action 笔记"

    print("\n--- 7. 生成会话报告 ---")
    report = maintainer.generate_report(save_to_file=True)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    assert report["activity"]["commands_executed"] >= 1
    print(f"📄 报告文件: {report.get('report_file')}")

    # ========== 清理临时目录与报告文件 ==========
    shutil.rmtree(notes_workspace, ignore_errors=True)
    for f in os.listdir("."):
        if f.startswith("maintainer_report_"):
            os.remove(f)
    print("\n🎉 Stage 6 验证全部通过")


if __name__ == "__main__":
    main()
