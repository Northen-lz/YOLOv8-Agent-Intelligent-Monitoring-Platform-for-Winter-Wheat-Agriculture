# -*- coding: utf-8 -*-
"""
阶段 5 验证：真实集成（真 LLM DeepSeek + 真 YOLOv8/ONNX 模型）全流程

依次验证：
1. WheatVisionAgent：真实田间图 → YOLOv8 检测 + 干旱分类 + LLM 自然语言解释
2. AgricultureExpertAgent：ReAct + 知识库检索 + LLM 组织答案
3. AnalysisAgent：真实检测/干旱结果 → 综合评价
4. ReportAgent：真实结果 → md/docx/pdf 三格式落盘
5. ManagerAgent：总调度（"介绍系统开发者"→author 子 Agent）

运行: cd d:/AI_Project/HelloAgents && python examples/agriculture/run_integration.py
前置: base 环境已装 gradio/ultralytics/onnxruntime/python-docx/reportlab，.env 已配 DeepSeek
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# 真实模型路径
DETECT_IMG = r"D:\pyhon\vscode-xiaomai\data\xiaomai\wheat500\images\train\00ac89bb-a4e6-444a-92e5-4ec5243de209.png"
DETECT_MODEL = r"D:\pyhon\vscode-xiaomai\models\detector\yolov8s\weights\best.pt"
DROUGHT_MODEL = r"D:\pyhon\vscode-xiaomai\models\classifier\exp_augmented2_s\weights\best.onnx"

from hello_agents.agents.wheat_agent import WheatVisionAgent
from hello_agents.agents.agriculture_agent import AgricultureExpertAgent
from hello_agents.agents.analysis_agent import AnalysisAgent
from hello_agents.agents.report_agent import ReportAgent
from hello_agents.agents.manager_agent import ManagerAgent


def main():
    print("=" * 60)
    print("[1/5] WheatVisionAgent 真实模型 + 真实 LLM")
    print("=" * 60)
    agent = WheatVisionAgent(detect_model_path=DETECT_MODEL, drought_model_path=DROUGHT_MODEL)
    out = agent.run(DETECT_IMG, conf=0.5)
    print(f"  检测株数: {agent.last_results['detection']['count']}  "
          f"平均置信度: {agent.last_results['detection']['avg_conf']:.3f}")
    print(f"  干旱率: {agent.last_results['drought']['drought_rate']:.3f}")
    print(f"  检测耗时: {agent.last_results['detection']['time_ms']:.0f} ms")
    print("\n--- LLM 自然语言解释 ---")
    print(out)
    vision_text = agent._format_results(agent.last_results)

    print("\n" + "=" * 60)
    print("[2/5] AgricultureExpertAgent ReAct + 知识库 + 真实 LLM")
    print("=" * 60)
    expert = AgricultureExpertAgent()
    exp_out = expert.run("为什么冬小麦会发生干旱胁迫？")
    print(exp_out)

    print("\n" + "=" * 60)
    print("[3/5] AnalysisAgent 真实结果综合评价")
    print("=" * 60)
    analysis = AnalysisAgent()
    ana_out = analysis.run(
        detection=agent.last_results["detection"],
        drought=agent.last_results["drought"],
        user_question="当前是否需要立即灌溉？")
    print(ana_out)

    print("\n" + "=" * 60)
    print("[4/5] ReportAgent 真实结果三格式落盘")
    print("=" * 60)
    report = ReportAgent()
    rep_out = report.run(
        data={"detection": agent.last_results["detection"],
              "drought": agent.last_results["drought"],
              "risk_analysis": str(ana_out),
              "suggestions": "及时灌溉，关注墒情"},
        format="all",
        title="冬小麦智能监测报告-实时")
    print(rep_out[:600])
    print("\n已生成文件:")
    for fmt, p in report.last_report.get("paths", {}).items():
        print(f"  - {fmt}: {p} 存在={os.path.exists(p)}")

    print("\n" + "=" * 60)
    print("[5/5] ManagerAgent 总调度（author 子 Agent）")
    print("=" * 60)
    manager = ManagerAgent(max_tool_calls=5)
    mgr_out = manager.run("请介绍一下本系统的开发者与项目情况")
    print(mgr_out)

    print("\n" + "=" * 60)
    print("✅ 阶段 5 真实集成全部完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
