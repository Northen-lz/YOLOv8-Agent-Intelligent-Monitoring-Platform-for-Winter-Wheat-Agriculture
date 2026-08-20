# -*- coding: utf-8 -*-
"""
阶段 4 验证：Agent 层离线 mock 测试（不依赖真实 LLM / 真实模型）

覆盖：
- ReActAgent 升级后的真循环（Action 解析 → 工具执行 → Observation → Answer）
- FunctionCallingAgent max_tool_calls 多步循环（向后兼容单次）
- WheatVisionAgent 检测→干旱→统计→LLM 解释 管线
- AgricultureExpertAgent ReAct 知识检索
- AnalysisAgent 综合评价管线
- AuthorAgent LLM 回答 + 降级
- ReportAgent 数据整理 + 报告落盘调用
- ManagerAgent 多 Agent 编排（stub specialists，验证路由顺序）

运行: python examples/agriculture/test_agents_mock.py
"""

import json
import os
import sys
import tempfile

# 隔离测试副作用：记忆/笔记/会话写入临时目录，避免污染项目 outputs/memory_data
_TEST_TMP = tempfile.mkdtemp(prefix="agents_mock_")
os.environ["MEMORY_DB_PATH"] = os.path.join(_TEST_TMP, "memory.db")
os.environ["NOTE_DIR"] = os.path.join(_TEST_TMP, "notes")
os.environ["CONVERSATIONS_DIR"] = os.path.join(_TEST_TMP, "conversations")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from hello_agents.tools.registry import ToolRegistry
from hello_agents.tools.agent_tool import AgentTool
from hello_agents.agents.react_agent import ReActAgent
from hello_agents.agents.function_call_agent import FunctionCallingAgent
from hello_agents.agents.wheat_agent import WheatVisionAgent
from hello_agents.agents.agriculture_agent import AgricultureExpertAgent
from hello_agents.agents.analysis_agent import AnalysisAgent
from hello_agents.agents.author_agent import AuthorAgent
from hello_agents.agents.report_agent import ReportAgent
from hello_agents.agents.manager_agent import ManagerAgent

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  ✔ {name}")
    else:
        FAIL.append(name)
        print(f"  ✘ {name}  {detail}")


class FakeLLM:
    """按序返回预设响应；支持 chat(messages) / chat() 两种调用形态"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages=None):
        self.calls.append(messages)
        if not self.responses:
            return None
        return self.responses.pop(0)


# ---------------- 1. 基础工具桩 ----------------

class EchoTool:
    name = "echo"
    description = "原样返回输入"

    def run(self, *args, **kwargs):
        if kwargs:
            return "ECHO:" + json.dumps(kwargs, ensure_ascii=False)
        return "ECHO:" + str(args[0] if args else "")


class FakeDetectTool:
    """WheatVisionAgent 检测桩"""

    def detect(self, image_path, conf=0.5, save_annotated=False):
        return {
            "count": 3, "avg_conf": 0.87, "image_path": str(image_path),
            "image_width": 1920, "image_height": 1080,
            "boxes": [[10, 20, 30, 40], [50, 60, 70, 80], [90, 100, 110, 120]],
            "confidences": [0.91, 0.85, 0.86],
            "class_ids": [0, 0, 0], "class_counts": {"wheat_head": 3},
            "annotated_path": os.path.join(
                "outputs", "detections",
                f"{os.path.splitext(os.path.basename(str(image_path)))[0]}_annotated_c{float(conf):.2f}.jpg")
                if save_annotated else None,
            "time_ms": 141.2,
        }


class FakeDroughtTool:
    """WheatVisionAgent 干旱桩"""

    def predict(self, image_path=None, boxes=None, feature_vector=None):
        n = len(boxes) if boxes else 0
        return {
            "label": "drought" if n else "control",
            "confidence": 0.62,
            "total_classified": n,
            "drought_count": 1,
            "control_count": max(0, n - 1),
            "drought_rate": (1.0 / n) if n else 0.0,
            "per_crop": [
                {"index": i, "label": "drought" if i == 0 else "control", "confidence": 0.6 + 0.05 * i}
                for i in range(n)
            ],
        }


class FakeReportTool:
    """ReportAgent 报告桩"""

    def __init__(self):
        self.calls = []

    def run(self, data=None, format="md", title=None, filename=None, **kw):
        self.calls.append({"data": data, "format": format})
        fname = filename or "report_test.md"
        return json.dumps({
            "formats_generated": ["md", "docx", "pdf"],
            "title": title or "报告",
            "paths": {fmt: f"outputs/reports/{fname}.{fmt}" for fmt in ("md", "docx", "pdf")},
            "notices": [],
        }, ensure_ascii=False)


# ---------------- 2. ReActAgent 真循环 ----------------

print("\n[1] ReActAgent 真循环")


def test_react():
    # 两轮：第一次 Action(knowledge_tool)，第二次 Answer
    llm = FakeLLM([
        'Thought: 需要检索知识库\nAction: {"name":"knowledge_tool","arguments":{"query":"干旱原因"}}',
        "Thought: 已有足够信息\nAnswer: 干旱主要由水分胁迫引起。",
    ])
    agent = AgricultureExpertAgent(llm=llm)  # ReAct + 真知识工具
    out = agent.run("冬小麦为什么会干旱？")
    check("ReAct 工具执行+Answer返回", "水分胁迫" in str(out), str(out))
    # Observation 回填进 LLM 对话消息
    check("ReAct 记录工具调用 Observation", any(
        isinstance(call, list) and any(
            isinstance(m, dict) and m.get("content", "").startswith("Observation")
            for m in call)
        for call in llm.calls))


# 函数调用形态 Action: tool("...")
def test_react_function_form():
    llm = FakeLLM([
        'Action: echo("hello")',
        "Answer: 收到 hello",
    ])
    reg = ToolRegistry()
    reg.register_tool(EchoTool())
    agent = ReActAgent(name="r2", llm=llm, tool_registry=reg)
    out = agent.run("测试")
    check("ReAct 函数调用形态", "ECHO:hello" in str(out) or "收到 hello" in str(out), str(out))


# 无 Action 直接 Answer
def test_react_direct_answer():
    llm = FakeLLM(["Answer: 直接回答无需工具"])
    agent = ReActAgent(name="r3", llm=llm)
    out = agent.run("你好")
    check("ReAct 直接回答", "直接回答无需工具" in str(out), str(out))


# ---------------- 3. FunctionCallingAgent 多步循环 ----------------

print("\n[2] FunctionCallingAgent 多步循环")


def test_function_calling_single():
    # max_tool_calls=None → 保持单次（向后兼容）
    llm = FakeLLM([
        '{"name":"echo","arguments":{"msg":"a"}}',
        "最终回答",
    ])
    reg = ToolRegistry()
    reg.register_tool(EchoTool())
    agent = FunctionCallingAgent(name="fc", llm=llm, tool_registry=reg)
    out = agent.run("问题")
    check("FC 单次工具+终答", "ECHO" in str(out) or "最终回答" in str(out), str(out))


def test_function_calling_multi():
    # max_tool_calls=3 → 两次工具调用 + 终答
    class RecEcho(EchoTool):
        def __init__(self):
            self.calls = []

        def run(self, *args, **kwargs):
            self.calls.append(dict(kwargs))
            return super().run(*args, **kwargs)

    rec = RecEcho()
    llm = FakeLLM([
        '{"name":"echo","arguments":{"step":"1"}}',
        '{"name":"echo","arguments":{"step":"2"}}',
        "两轮工具调用完毕，综合回答",
    ])
    reg = ToolRegistry()
    reg.register_tool(rec)
    agent = FunctionCallingAgent(name="fc2", llm=llm, tool_registry=reg, max_tool_calls=3)
    out = agent.run("多步")
    check("FC 多步循环 2 次工具调用", len(rec.calls) == 2, str(rec.calls))
    check("FC 无工具调用也收尾", "两轮工具调用完毕" in str(out), str(out))


def test_function_calling_none_response():
    # LLM 返回 None 兜底
    llm = FakeLLM([])
    reg = ToolRegistry()
    agent = FunctionCallingAgent(name="fc3", llm=llm, tool_registry=reg, max_tool_calls=2)
    out = agent.run("无输出")
    check("FC 空响应兜底", "LLM 返回为空" in str(out), str(out))


# ---------------- 3b. 识别门控 ----------------

def test_recognize_gate():
    """count>0 → 小麦；count==0 → 常规图片分析"""
    class ZeroDetect(FakeDetectTool):
        def detect(self, image_path, conf=0.5, save_annotated=False):
            d = super().detect(image_path, conf, save_annotated)
            d.update({"count": 0, "boxes": [], "confidences": [],
                      "class_counts": {}, "avg_conf": 0.0})
            return d

    # 小麦分支
    llm = FakeLLM(["检测到 3 株冬小麦，长势良好。"])
    w = WheatVisionAgent(llm=llm)
    w.detect_tool = FakeDetectTool()
    w.drought_tool = FakeDroughtTool()
    gate = w.recognize("field.png")
    check("门控 小麦图 is_wheat=True", gate["is_wheat"] and gate["count"] == 3, str(gate))
    out = w.run("field.png")
    check("门控 小麦分支完整分析", "3 株" in str(out), str(out))

    # 非小麦分支（图片信息 + 聊天）
    llm2 = FakeLLM(["这是一张常规图片，主色调为绿色。"])
    w2 = WheatVisionAgent(llm=llm2)
    w2.detect_tool = ZeroDetect()
    w2.drought_tool = FakeDroughtTool()
    gate2 = w2.recognize("sky.png")
    check("门控 非小麦图 is_wheat=False", gate2["is_wheat"] is False, str(gate2))
    out2 = w2.run("sky.png")
    check("门控 非小麦走常规分析", "常规" in str(out2), str(out2))


# ---------------- 3c. ImageInfoTool ----------------

def test_image_info_tool():
    import cv2
    import numpy as np
    import tempfile
    from hello_agents.tools.agriculture import ImageInfoTool

    tmp = tempfile.mkdtemp()
    green = np.zeros((200, 300, 3), np.uint8)
    green[:, :, 1] = 150
    p = os.path.join(tmp, "green.png")
    cv2.imwrite(p, green)
    info = ImageInfoTool.extract(p)
    check("ImageInfo 尺寸提取", info.get("width") == 300 and info.get("height") == 200)
    check("ImageInfo 主色调=绿", any(c["name"] == "绿色" for c in info.get("dominant_colors", [])))
    check("ImageInfo 可读文本", "主色调" in ImageInfoTool.format_text(info))


# ---------------- 3d. 实验数据查询（models/eval/data） ----------------

def test_experiment_actions():
    """离线：仅扫描真实目录/读 CSV，不加载模型"""
    from hello_agents.tools.agriculture import ExperimentAnalysisTool
    t = ExperimentAnalysisTool()

    out = t.run(action="models")
    check("实验-模型清单含检测最佳", "yolov8s" in out and "最佳" in out, out[:80])
    check("实验-模型清单含分类最佳", "exp_augmented2_s" in out, out[:80])
    check("实验-模型清单含对比版", "yolov8n" in out or "yolo11n" in out, out[:80])

    ev = t.run(action="eval")
    check("实验-评估指标含表头", "accuracy" in ev and "model" in ev, ev[:80])
    check("实验-评估指标含分类器", "yolov8s-cls" in ev, ev[:80])

    da = t.run(action="data")
    check("实验-数据集含 wheat500", "wheat500" in da, da[:80])
    check("实验-数据集含干旱数据", "wheat_drought_data" in da, da[:80])

    st = t.run(action="stats", detections='{"count": 3, "boxes": [[0,0,10,10],[10,10,20,20],[20,20,30,30]], "confidences": [0.9,0.8,0.7], "image_width": 100, "image_height": 100}')
    parsed = json.loads(st)
    check("实验-stats 统计", parsed.get("count") == 3 and parsed.get("coverage", 0) > 0, st[:80])


# ---------------- 4. WheatVisionAgent 管线 ----------------

print("\n[3] WheatVisionAgent 检测→干旱→统计→解释")


def test_wheat_vision():
    llm = FakeLLM(["检测到 3 株冬小麦，平均置信度 87%，1 株存在干旱风险。"])
    agent = WheatVisionAgent(llm=llm)
    agent.detect_tool = FakeDetectTool()
    agent.drought_tool = FakeDroughtTool()

    results = agent.analyze("demo.png", conf=0.5)
    check("Wheat 检测株数=3", results["detection"]["count"] == 3)
    check("Wheat 干旱率≈0.333", abs(results["drought"]["drought_rate"] - 1 / 3) < 1e-9)
    check("Wheat 统计含均匀度", "uniformity" in results["stats"])

    out = agent.run("demo.png")
    check("Wheat LLM 解释返回", "3 株" in str(out), str(out))
    check("Wheat 错误路径(无路径)", "image_path" in agent.run())


def test_wheat_annotate():
    """小麦分析后暴露检测标注图路径；非小麦不暴露"""
    llm = FakeLLM(["检测到 3 株冬小麦。"])
    w = WheatVisionAgent(llm=llm)
    w.detect_tool = FakeDetectTool()
    w.drought_tool = FakeDroughtTool()
    w.run("field.png")
    check("Wheat 小麦分支暴露标注图", isinstance(w.annotated_path, str)
          and "annotated" in w.annotated_path, str(w.annotated_path))

    class ZeroDetect(FakeDetectTool):
        def detect(self, image_path, conf=0.5, save_annotated=False):
            d = super().detect(image_path, conf, save_annotated)
            d.update({"count": 0, "boxes": [], "confidences": [],
                      "class_counts": {}, "avg_conf": 0.0})
            return d

    llm2 = FakeLLM(["常规图片信息。"])
    w2 = WheatVisionAgent(llm=llm2)
    w2.detect_tool = ZeroDetect()
    w2.drought_tool = FakeDroughtTool()
    w2.run("sky.png")
    check("Wheat 非小麦不暴露标注图", w2.annotated_path is None, str(w2.annotated_path))


def test_conversation_store():
    """会话存储：保存/调回/重命名/置顶/删除/文件元组往返（临时目录）"""
    from hello_agents.core import conversation_store as cs
    d = tempfile.mkdtemp()
    old = cs.CONVERSATIONS_DIR
    cs.CONVERSATIONS_DIR = d
    try:
        msgs = [
            {"role": "user", "content": "分析这张小麦图"},
            {"role": "user", "content": ("/tmp/a.png", "📷 图片 1")},
            {"role": "assistant", "content": "🛠 **wheat_vision**\n\n检测到 3 株"},
            {"role": "assistant", "content": ("/tmp/b.jpg", "🖼 检测结果标注图")},
        ]
        cid = cs.save(msgs)
        check("会话-保存返回id", bool(cid), cid)
        check("会话-标题取首条文本", cs.list_conversations()[0]["title"] == "分析这张小麦图")
        back = cs.load(cid)
        check("会话-消息往返一致", back == msgs, str(back)[:100])
        check("会话-文件元组往返", any(isinstance(m["content"], tuple)
              and m["content"][1] == "🖼 检测结果标注图" for m in back))
        cs.rename(cid, "重命名")
        check("会话-重命名", cs.list_conversations()[0]["title"] == "重命名")
        cs.toggle_pin(cid)
        check("会话-置顶", cs.list_conversations()[0]["pinned"] is True)
        # 置顶 + 未置顶各一 → 侧边栏应分「📌 置顶」「最近」两组
        cid2 = cs.save([{"role": "user", "content": "第二段对话"}])
        labels = [lbl for lbl, _ in cs.listbox_choices()]
        check("会话-分组含置顶", "📌 置顶" in labels, str(labels))
        check("会话-分组含最近", "最近" in labels, str(labels))
        check("会话-置顶组在前", labels.index("📌 置顶") < labels.index("最近"), str(labels))
        check("会话-分组行不可选中", any(v.startswith("@group:") for _, v in cs.listbox_choices()))
        cs.delete(cid2)
        check("会话-空消息不落盘", cs.save([]) == "")
        cs.delete(cid)
        check("会话-删除", cs.list_conversations() == [])
        check("会话-删除后load空", cs.load(cid) == [])
    finally:
        cs.CONVERSATIONS_DIR = old


# ---------------- 5. AgricultureExpertAgent（已在上文 ReAct 覆盖知识检索） ----------------

# ---------------- 6. AnalysisAgent 综合评价 ----------------

print("\n[4] AnalysisAgent 综合评价")


def test_analysis():
    llm = FakeLLM(["综合评价：当前区域冬小麦数量正常，存在中度干旱风险。"])
    agent = AnalysisAgent(llm=llm)
    input_text = agent._build_input(
        detection={"count": 3, "avg_conf": 0.87},
        drought={"total_classified": 3, "drought_count": 1, "drought_rate": 0.333})
    check("Analysis 文本构建含干旱率", "0.333" in input_text, input_text)
    out = agent.run(detection={"count": 3}, drought={"drought_rate": 0.333},
                    user_question="是否该立即灌溉？")
    check("Analysis LLM 评价返回", "综合评价" in str(out), str(out))
    check("Analysis 空输入报错", "分析失败" in agent.run())


# ---------------- 7. AuthorAgent ----------------

print("\n[5] AuthorAgent 作者介绍")


def test_author():
    llm = FakeLLM(["本项目由开发者张三牵头，使用 HelloAgents 框架构建。"])
    agent = AuthorAgent(llm=llm)
    out = agent.run("介绍一下开发者")
    check("Author LLM 回答", "张三" in str(out), str(out))


def test_author_fallback():
    class BoomLLM:
        def chat(self, messages=None):
            raise RuntimeError("LLM 不可用")

    agent = AuthorAgent(llm=BoomLLM())
    out = agent.run("介绍一下开发者")
    check("Author 降级返回作者信息", len(str(out)) > 0, str(out)[:80])


# ---------------- 8. ReportAgent ----------------

print("\n[6] ReportAgent 报告生成")


def test_report_structured():
    fake_tool = FakeReportTool()
    agent = ReportAgent(llm=FakeLLM([]))
    agent.report_tool = fake_tool
    out = agent.run(data={"detection": {"count": 3, "avg_conf": 0.87},
                          "drought": {"drought_count": 1, "drought_rate": 0.333},
                          "risk_analysis": "中度干旱风险", "suggestions": "及时灌溉"},
                    format="md")
    parsed = json.loads(out) if isinstance(out, str) else out
    check("Report 三格式生成", parsed.get("formats_generated") == ["md", "docx", "pdf"], str(out)[:120])
    check("Report last_report 缓存", agent.last_report.get("title") is not None)


def test_report_text_extract():
    agent = ReportAgent(llm=FakeLLM([]))
    data = agent._build_report_data(content="检测到 12 株小麦，平均置信度 0.83，其中干旱 4 株，正常 8 株，干旱率 0.333")
    check("Report 文本提取株数=12", data["detection"].get("count") == 12, str(data))
    check("Report 文本提取干旱率=0.333", abs(data["drought"].get("drought_rate", 0) - 0.333) < 0.001, str(data))
    check("Report 缺数据报错", "报告生成失败" in agent.run())


# ---------------- 9. ManagerAgent 多 Agent 编排 ----------------

print("\n[7] ManagerAgent 多 Agent 编排")


class StubSpecialist:
    """模拟子 Agent：记录被调用，返回固定文本"""

    def __init__(self, name, reply):
        self.name = name
        self.reply = reply
        self.calls = []

    def run(self, *args, **kwargs):
        self.calls.append(kwargs or {"pos": args[0] if args else ""})
        return f"[{self.name}] " + self.reply


def test_manager_routing():
    wheat = StubSpecialist("wheat_vision", "检测到 3 株，干旱 1 株")
    analysis = StubSpecialist("analysis", "建议及时灌溉")
    report = StubSpecialist("report", "报告已生成")
    author = StubSpecialist("author", "开发者张三")

    # FakeLLM 按序返回：先调度 wheat_vision → 再 analysis → 终答
    llm = FakeLLM([
        '{"name":"wheat_vision","arguments":{"image_path":"field.png"}}',
        '{"name":"analysis","arguments":{"input_text":"检测到 3 株，干旱 1 株"}}',
        "综合结论：该区域存在轻度干旱风险，建议关注灌溉。",
    ])
    manager = ManagerAgent(llm=llm, max_tool_calls=4,
                           wheat_agent=wheat, expert_agent=StubSpecialist("expert", ""),
                           analysis_agent=analysis, report_agent=report, author_agent=author)
    out = manager.run("请分析这张田间图片 field.png 并给出建议")

    check("Manager 调度 wheat_vision", len(wheat.calls) == 1, str(wheat.calls))
    check("Manager 调度 analysis", len(analysis.calls) == 1, str(analysis.calls))
    check("Manager 未误调 report/author",
          len(report.calls) == 0 and len(author.calls) == 0, f"report={report.calls} author={author.calls}")
    check("Manager 汇总终答", "综合结论" in str(out), str(out))


def test_manager_report_flow():
    wheat = StubSpecialist("wheat_vision", "检测到 5 株，无干旱")
    report = StubSpecialist("report", "《报告》已输出 md/docx/pdf")
    llm = FakeLLM([
        '{"name":"wheat_vision","arguments":{"image_path":"f.png"}}',
        '{"name":"report","arguments":{"content":"检测到 5 株，无干旱"}}',
        "报告已生成完毕。",
    ])
    manager = ManagerAgent(llm=llm, max_tool_calls=4,
                           wheat_agent=wheat, expert_agent=StubSpecialist("expert", ""),
                           analysis_agent=StubSpecialist("analysis", ""),
                           report_agent=report, author_agent=StubSpecialist("author", ""))
    out = manager.run("生成一份监测报告")
    check("Manager 报告链 wheat→report", len(wheat.calls) == 1 and len(report.calls) == 1,
          f"wheat={len(wheat.calls)} report={len(report.calls)}")
    check("Manager 报告链终答", "报告已生成完毕" in str(out), str(out))


def test_agent_tool_wrap():
    stub = StubSpecialist("wheat_vision", "ok")
    tool = AgentTool(stub, name="wheat_vision",
                     description="对田间图片做检测与干旱分类")
    check("AgentTool 描述透传", tool.description.startswith("对田间图片"), tool.description)
    check("AgentTool run(kwargs) 透传", tool.run(image_path="a.png") == "[wheat_vision] ok")
    check("AgentTool run(str) 透传", tool.run("a.png") == "[wheat_vision] ok")


# ---------------- 6. 第 7-12 章内置通用工具（零外部服务） ----------------

def test_builtin_tools_registered():
    """6 个通用工具（memory/note/calculator/terminal/rag/image_caption）注册进 AgricultureExpertAgent"""
    from hello_agents.core.config import Config
    from hello_agents.tools.builtin.memory_tool import MemoryTool
    from hello_agents.tools.builtin.note_tool import NoteTool
    from hello_agents.tools.builtin.calculator import CalculatorTool
    from hello_agents.tools.builtin.terminal_tool import TerminalTool
    from hello_agents.tools.builtin.rag_tool import RAGTool
    from hello_agents.tools.builtin.image_caption_tool import ImageCaptionTool

    agent = AgricultureExpertAgent(llm=FakeLLM([]))
    names = sorted(agent.tool_registry.tools.keys())
    for t in ["memory", "note", "calculator", "terminal", "rag", "image_caption"]:
        check(f"内置工具已注册 {t}", t in names, names)

    # 工具对象已实例化为 Agent 属性
    check("agent.memory_tool", isinstance(agent.memory_tool, MemoryTool))
    check("agent.note_tool", isinstance(agent.note_tool, NoteTool))
    check("agent.calculator_tool", isinstance(agent.calculator_tool, CalculatorTool))
    check("agent.terminal_tool", isinstance(agent.terminal_tool, TerminalTool))
    check("agent.rag_tool", isinstance(agent.rag_tool, RAGTool))
    check("agent.image_caption_tool", isinstance(agent.image_caption_tool, ImageCaptionTool))

    # ReAct 提示已自动包含这些工具描述
    desc = agent.tool_registry.get_tools_description()
    check("ReAct 提示含 memory", "memory" in desc)
    check("ReAct 提示含 rag", "rag" in desc)


def test_image_caption_offline():
    """ImageCaptionTool：无图片/缺文件/Ollama 未启动均返回友好提示（不抛异常）"""
    import hello_agents.tools.builtin.image_caption_tool as ict_mod
    from hello_agents.tools.builtin.image_caption_tool import ImageCaptionTool

    tool = ImageCaptionTool()
    out = tool.run()
    check("image_caption 无参返回提示", "请提供图片路径" in out, out[:60])
    out = tool.run(image_path=os.path.join(tempfile.mkdtemp(), "nope.png"))
    check("image_caption 缺文件返回提示", "图片文件不存在" in out, out[:60])

    # Ollama 不可达（换一个肯定连不上的端口）→ 友好错误而非崩溃
    orig = ict_mod._OLLAMA_URL
    ict_mod._OLLAMA_URL = "http://127.0.0.1:1"
    try:
        out = tool.run(image_path=r"D:\AI_Project\HelloAgents\image copy.png")
    finally:
        ict_mod._OLLAMA_URL = orig
    check("image_caption Ollama 未启动降级", "无法连接 Ollama" in out, out[:80])
    check("image_caption 降级含启动提示", "ollama pull" in out, "")


def test_memory_tool_offline():
    """MemoryTool 无 Qdrant 时：SQLite 持久化 + 关键词检索兜底可用"""
    from hello_agents.memory.base import MemoryConfig
    from hello_agents.tools.builtin.memory_tool import MemoryTool

    mc = MemoryConfig(database_path=os.path.join(tempfile.mkdtemp(), "mem.db"))
    mt = MemoryTool(user_id="test_user", memory_config=mc,
                    memory_types=["working", "episodic"])
    out = mt.execute("add", content="冬小麦拔节期对水分需求较高，干旱会抑制分蘖成穗。",
                     memory_type="episodic", importance=0.8)
    check("记忆 add 离线可用", out.startswith("✅"), out[:50])
    res = mt.execute("search", query="拔节期 水分", limit=3)
    check("记忆 search 离线可用", "冬小麦" in res, res[:80])
    stats = mt.execute("stats")
    check("记忆 stats 离线可用", "记忆" in stats or "条" in stats, stats[:60])


def test_note_calculator_terminal_offline():
    """NoteTool / CalculatorTool / TerminalTool 零外部服务可用"""
    from hello_agents.tools.builtin.note_tool import NoteTool
    from hello_agents.tools.builtin.calculator import CalculatorTool
    from hello_agents.tools.builtin.terminal_tool import TerminalTool

    ws = os.path.join(tempfile.mkdtemp(), "notes")
    nt = NoteTool(workspace=ws)
    nid = nt.execute("create", title="待办清单", content="- [ ] 核验干旱率\n- [x] 导出报告")
    check("笔记 create 返回 id", isinstance(nid, str) and nid.startswith("note_"), str(nid)[:40])
    read = nt.execute("read", note_id=nid)
    meta = read.get("metadata", read) if isinstance(read, dict) else {}
    check("笔记 read 含标题", "待办清单" in meta.get("title", ""), str(read)[:60])
    listed = nt.execute("list")
    check("笔记 list 含新笔记", "待办清单" in str(listed), str(listed)[:80])

    calc = CalculatorTool()
    r = calc.run("150 * 8.6")
    check("计算器 150*8.6", abs(float(r) - 1290.0) < 1e-6, str(r))

    tt = TerminalTool(workspace=os.path.join(tempfile.mkdtemp(), "proj"))
    res = tt.execute("ls")
    check("终端 ls 离线可用", isinstance(res, str) and res != "", res[:40])


def test_rag_tool_offline_degrade():
    """RAGTool 无 Qdrant 时：构造安全 + search/stats 返回友好提示"""
    from hello_agents.core.config import Config
    from hello_agents.tools.builtin.rag_tool import RAGTool

    rag = RAGTool(knowledge_base_path=Config.KNOWLEDGE_DIR,
                  collection_name="agriculture_kb_test",
                  rag_namespace="agriculture_kb_test")
    out = rag.execute("search", query="冬小麦干旱")
    check("rag search 降级提示", "Qdrant" in out or "未检索" in out, out[:60])
    stats = rag.execute("stats")
    # 环境无关断言：Qdrant 在线 → 返回真实统计；离线 → 返回降级提示，均算通过
    store = rag._get_pipeline("agriculture_kb_test")["store"]
    if getattr(store, "connected", True) is False:
        check("rag stats 降级提示", "Qdrant" in stats, stats[:60])
    else:
        check("rag stats 在线统计", "分块总数" in stats or "集合" in stats, stats[:60])


def test_mcp_tools():
    """第 10 章通信协议：农业自定义 MCP（Memory）+ 天气 MCP（stdio）展开注册"""
    from hello_agents.agents.agriculture_agent import AgricultureExpertAgent

    agent = AgricultureExpertAgent(llm=FakeLLM([]))
    names = set(agent.tool_registry.tools.keys())

    # 1) 农业自定义 MCP 服务器（Memory 传输，进程内，零外部依赖）——
    #    必须注册且工具真实可用（读真实模型目录/CSV/知识库）
    for name in ["agri_query_models", "agri_query_eval", "agri_query_data",
                 "agri_search_knowledge", "agri_get_platform_info"]:
        check(f"MCP agri_* 已注册 {name}", name in names, sorted(names))

    models = agent.tool_registry.get_tool("agri_query_models").run()
    check("MCP agri_query_models 返回真实模型", "yolov8s" in models, models[:80])

    kb = agent.tool_registry.get_tool("agri_search_knowledge").run(query="小麦拔节")
    check("MCP agri_search_knowledge 返回知识", "小麦" in kb or "知识" in kb or "检索" in kb, kb[:80])

    # 2) 天气 MCP 服务器（stdio 拉起 ch10 服务器）——
    #    展开只做本地子进程握手不联网，应注册；但子进程异常时静默跳过，故软检查：
    #    存在则断言调用返回天气或明确的失败提示（不依赖外网内容），不存在则提示。
    if "weather_get_weather_by_city" in names:
        weather = agent.tool_registry.get_tool("weather_get_weather_by_city").run(city="北京")
        ok = ("天气" in weather or "°C" in weather or "失败" in weather
              or "wttr" in weather or "错误" in weather)
        check("MCP weather 调用返回天气/失败提示", ok, weather[:80])
    else:
        print("  ℹ️ weather_get_weather_by_city 未注册（stdio 子进程不可用，跳过断言）")


def test_stats_store():
    """平台累计统计：累计记录 / 持久化 / 实验指标（临时目录）"""
    from hello_agents.core import stats_store as ss
    d = tempfile.mkdtemp()
    old = ss.STATS_FILE
    ss.STATS_FILE = os.path.join(d, "stats.json")
    try:
        ss.record(image_count=1)
        ss.record(image_count=2, wheat_count=3, drought_count=1)
        s = ss.get_stats()
        check("统计-累计检测图像数", s["total_images"] == 3, str(s))
        check("统计-累计小麦株数", s["total_wheat"] == 3, str(s))
        check("统计-累计干旱株数", s["total_drought"] == 1, str(s))
        check("统计-持久化", os.path.exists(ss.STATS_FILE), ss.STATS_FILE)
        check("统计-实验准确率", abs(s["experiment_accuracy"] - 0.7797) < 1e-4,
              str(s["experiment_accuracy"]))
        check("统计-最终验证损失", abs(s["final_val_loss"] - 0.44898) < 1e-4,
              str(s["final_val_loss"]))
        # 重新读取（文件持久化往返）
        s2 = ss.get_stats()
        check("统计-重读一致", s2 == s, str(s2))
    finally:
        ss.STATS_FILE = old


# ---------------- 执行 ----------------

def main():
    for fn in [test_react, test_react_function_form, test_react_direct_answer,
               test_function_calling_single, test_function_calling_multi,
               test_function_calling_none_response,
               test_recognize_gate, test_image_info_tool, test_experiment_actions,
               test_wheat_vision, test_wheat_annotate, test_conversation_store,
               test_stats_store,
               test_analysis, test_author, test_author_fallback,
               test_report_structured, test_report_text_extract,
               test_manager_routing, test_manager_report_flow, test_agent_tool_wrap,
               test_builtin_tools_registered, test_image_caption_offline,
               test_memory_tool_offline,
               test_note_calculator_terminal_offline, test_rag_tool_offline_degrade,
               test_mcp_tools]:
        try:
            fn()
        except Exception as e:
            FAIL.append(fn.__name__)
            print(f"  ✘ {fn.__name__} 异常: {e!r}")

    print(f"\n结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        print("失败项:", FAIL)
        sys.exit(1)
    print("✅ 阶段 4 Agent 层 mock 验证全部通过")


if __name__ == "__main__":
    main()
