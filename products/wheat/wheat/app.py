# -*- coding: utf-8 -*-
"""
YOLOv8-Agent 农业智能监测平台 —— Gradio对话式智能体界面

单个对话界面（对齐 Dify 智能体交互范式）：
- 消息框支持上传 / 拖拽田间图片（MultimodalTextbox）
- 上传图片发送 → 自动调用 wheat_vision 逐张分析，工具调用步骤流式展示
- 文本消息由 ManagerAgent 多 Agent 编排处理（知识问答 / 综合评价 / 报告生成 / 作者介绍）
- 生成报告时在对话下方提供 md/docx/pdf 下载

左侧边栏（功能导航 + 会话管理）：
- ➕ 新对话（第一个功能）/ 📊 数据统计 / 📖 使用示例 / 🔬 专业检测（批量）/ ⚙️ 设置
- 📂 会话记录分「📌 置顶」「最近」两组，选中后 ⋯ 弹出 置顶/重命名/删除 小卡片

运行: python -m wheat.app   然后浏览器访问 http://localhost:7865
（端口默认 7865，可用 HELLO_AGENTS_UI_PORT 覆盖）
"""

import json
import os
import queue
import threading
import time

import gradio as gr

from .core.config import Config
from .core import conversation_store
from .core import stats_store
from .core import detection_log
from .core import notifications_store
from .core import feedback_store
from .core import news as news_mod

# 全局 Agent 实例（懒初始化：首次调用才加载模型，避免 import 即加载）
_MANAGER = None
_WHEAT = None

# 当前会话 id（模块级，respond 自动保存与历史 UI 共享）
_CURRENT_CONV = {"id": None}

# ⋯ 操作卡片展开状态
_MORE_OPEN = {"v": False}
# RAG 查询增强（MQE/HyDE）运行时开关：初始跟随 env 默认，UI 图标按钮可切换
_RAG_BOOST = {"on": bool(Config.RAG_ENABLE_MQE)}
# 批量检测单批上限（防止大并发拖垮本地 CPU 推理）
_BATCH_MAX_FILES = 50


def get_manager():
    """懒初始化 ManagerAgent（共享同一个 wheat 实例，命中其图片结果缓存）"""
    global _MANAGER
    if _MANAGER is None:
        from .agents.manager_agent import ManagerAgent
        _MANAGER = ManagerAgent(max_tool_calls=5, wheat_agent=get_wheat())
    return _MANAGER


def get_wheat():
    """懒初始化 WheatVisionAgent（模型首次 analyze 时才加载）"""
    global _WHEAT
    if _WHEAT is None:
        from .agents.wheat_agent import WheatVisionAgent
        _WHEAT = WheatVisionAgent()
    return _WHEAT


# ---------------- 文档入库（RAG 知识库） ----------------

# 可灌入 RAG 知识库的文档扩展名
_DOC_EXTS = {".txt", ".md", ".pdf", ".docx", ".doc", ".csv", ".json"}
# 共享 RAGTool 实例（collection=agriculture_kb，与 agriculture_expert 检索同一知识库）
_RAG_TOOL = None


def _is_doc(path):
    """是否为可灌入 RAG 知识库的文档文件"""
    return os.path.splitext(path)[1].lower() in _DOC_EXTS


def get_rag_tool():
    """懒初始化共享 RAGTool（懒连接，Qdrant 离线时 add_document 会返回提示而非崩溃）"""
    global _RAG_TOOL
    if _RAG_TOOL is None:
        from ha_framework.tools.builtin.rag_tool import RAGTool
        _RAG_TOOL = RAGTool(knowledge_base_path=Config.KNOWLEDGE_DIR,
                            collection_name="agriculture_kb")
    return _RAG_TOOL


# ---------------- 对话逻辑 ----------------

def _parse_message(message):
    """MultimodalTextbox 返回 {text, files}；兼容纯字符串"""
    if isinstance(message, dict):
        return (message.get("text") or "").strip(), list(message.get("files") or [])
    return str(message or "").strip(), []


def _render_step(step, max_len=1200):
    """把一次工具调用渲染为一条助手 Markdown 消息（类 Dify 工具步骤）

    注：gradio 5.45 Chatbot 输出端不支持 message content block/dict，
    一律用纯字符串（Markdown 标签行 + 结果）。
    """
    tool = step.get("tool", "tool")
    result = step.get("result") or ""
    args = step.get("arguments") or {}

    # 报告工具：解析 JSON，展示生成的文件名（不暴露完整路径）
    if tool == "report":
        try:
            parsed = json.loads(result)
            paths = parsed.get("paths", {})
            result = "已生成报告：\n" + "\n".join(
                f"- {k}: `{os.path.basename(p)}`" for k, p in paths.items())
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    elif isinstance(args, dict) and args.get("image_path"):
        result = f"输入图片: `{os.path.basename(args['image_path'])}`\n\n" + result

    if len(result) > max_len:
        result = result[:max_len] + "\n…"
    return {"role": "assistant", "content": f"🛠 **{tool}**\n\n{result}"}


def _collect_report_paths(steps):
    """从工具步骤里收集生成的报告文件路径"""
    paths = []
    for s in steps or []:
        if s.get("tool") != "report":
            continue
        try:
            parsed = json.loads(s["result"])
            paths.extend(p for p in parsed.get("paths", {}).values())
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return [p for p in paths if os.path.exists(p)]


def _record_wheat_stats(w, image_path):
    """从 WheatVisionAgent 最近结构化结果累计小麦株数 / 干旱株数。

    用 image_path 校验 last_results 确属当前图（识别门控后 analyze 会刷新
    last_results；非小麦路径不走 analyze，避免把旧图数据误计）。
    """
    last = getattr(w, "last_results", None) or {}
    det = last.get("detection") or {}
    if str(det.get("image_path", "")) != str(image_path):
        return
    dr = last.get("drought") or {}
    try:
        stats_store.record(
            wheat_count=int(det.get("count", 0) or 0),
            drought_count=int(dr.get("drought_count", 0) or 0),
        )
    except (TypeError, ValueError):
        pass


def _log_wheat_detection(w, image_path, note=""):
    """把一次「小麦检测」追加进检测流水（看板趋势图 + 最近检测流）。

    复用 w.last_results 的结构化结果（与 _record_wheat_stats 同一份数据，
    含 avg_conf / annotated_path）；image_path 校验确保数据确属当前图。
    """
    last = getattr(w, "last_results", None) or {}
    det = last.get("detection") or {}
    dr = last.get("drought") or {}
    if str(det.get("image_path", "")) != str(image_path):
        return detection_log.append(image_count=1, note=note)
    try:
        return detection_log.append(
            image_count=1,
            wheat_count=int(det.get("count", 0) or 0),
            drought_count=int(dr.get("drought_count", 0) or 0),
            avg_conf=float(det.get("avg_conf", 0) or 0),
            annotated=det.get("annotated_path") or "",
            note=note,
        )
    except (TypeError, ValueError):
        return detection_log.append(image_count=1, note=note)


def respond(history, message, conf, progress=gr.Progress(track_tqdm=False)):
    """对话主流程：图片分析 + 文档入库 + Manager 编排，工具步骤流式输出

    参数顺序与 gradio wiring `[chatbot, textbox, conf]` 一致：
    history=聊天历史（Chatbot 输入，已由 gradio preprocess 成 dict 列表），
    message=MultimodalTextbox 值 {text, files}，conf=置信度。
    files 分流：图片走视觉流程；文档（txt/md/pdf/docx/csv/json）自动灌入 RAG 知识库。
    progress=gradio 自动注入的处理中进度提示（避免用户误以为画面卡顿）。

    输出 5 槽：[chatbot, textbox, report_file, history_list, status]。
    图片走快速路径（use_vision=False，跳过 Ollama 视觉门控直接 YOLO 判定）：
    - 同一张图不再被 recognize + run 双重识别（过去「不确定」图会调两次 Ollama 30~90s）
    - 状态栏实时显示「正在分析图片 i/N」「正在生成回答」等进度。
    """
    history = list(history or [])
    text, files = _parse_message(message)
    conf = float(conf or 0.5)

    # 文件分流：文档 → 入库；其余 → 图片视觉流程
    files = [f for f in files if f]
    doc_files = [f for f in files if _is_doc(f)]
    image_files = [f for f in files if f not in doc_files]

    def emit(h, status, hl=gr.update()):
        """5 槽输出：chatbot / textbox(清空) / report_file(不动) / 会话列表 / 状态栏"""
        return h, gr.update(value=None), gr.update(), hl, gr.update(value=status)

    # 用户消息（文本 + 内嵌文件）。
    # gradio 5.45 Chatbot 用"文件元组"展示附件：(path, 说明文字)
    if len(files) == 1 and text:
        history.append({"role": "user", "content": (files[0], text)})
    else:
        if text:
            history.append({"role": "user", "content": text})
        for i, f in enumerate(files):
            tag = "📄 文档" if f in doc_files else "📷 图片"
            history.append({"role": "user", "content": (f, f"{tag} {i + 1}")})
    if not text and not files:
        history.append({"role": "user", "content": "（上传了一张田间图片）"})
    yield emit(history, "⏳ 正在处理…")

    q = queue.Queue()

    def worker():
        try:
            vision_texts, general_texts, doc_results = [], [], []
            # 0) 上传文档 → 灌入 RAG 知识库（txt/md/pdf/docx/csv/json）
            #    复用 RAGTool.execute("add_document")：Qdrant 在线则索引分块，离线返回友好提示
            for d in doc_files:
                res = get_rag_tool().execute(action="add_document", file_path=d)
                q.put(("step", {"tool": "rag_add_document",
                                "arguments": {"file_path": d},
                                "result": res}))
                doc_results.append(res)

            # 1) 逐张图片：识别门控（快速路径）+ 分流；同步累计平台统计
            total_img = len(image_files)
            for i, f in enumerate(image_files):
                w = get_wheat()
                q.put(("status", f"🖼 正在分析图片 {i + 1}/{total_img}…"))
                gate = w.recognize(f, conf=conf, use_vision=False)
                stats_store.record(image_count=1)  # 累计检测图像数（含非小麦）
                if gate["is_wheat"]:
                    # 小麦图 → 完整小麦智能分析
                    # recognize 门控结论已并入 wheat_vision 结果，不再单独渲染（避免刷屏）
                    out = w.run(f, conf=conf, use_vision=False)
                    q.put(("step", {"tool": "wheat_vision",
                                    "arguments": {"image_path": f, "conf": conf},
                                    "result": out}))
                    # 检测标注图（画框结果）作为独立 assistant 图片消息展示
                    ann = getattr(w, "annotated_path", None)
                    if ann and os.path.exists(ann):
                        q.put(("image", ann))
                    vision_texts.append(out)
                    # 累计小麦株数 / 干旱株数（结构化结果，缓存命中一致）
                    _record_wheat_stats(w, f)
                    # 追加检测流水（看板趋势 + 最近检测流）
                    _log_wheat_detection(w, f, note="对话·小麦")
                else:
                    # 非小麦图 → 常规图片信息分析 + 聊天
                    # recognize 门控结论并入 image_info 结果，不再单独渲染
                    out = w.run(f, conf=conf, use_vision=False)
                    q.put(("step", {"tool": "image_info",
                                    "arguments": {"image_path": f},
                                    "result": "未检测到小麦，按常规图片信息分析：\n" + out}))
                    general_texts.append(out)
                    detection_log.append(image_count=1, note="对话·非小麦")

            # 2) 组装 Manager 提示：用户问题 + 已完成的图片分析 + 文档入库结果
            parts = []
            if text:
                parts.append("用户问题：" + text)
            if doc_results:
                parts.append(
                    "用户上传了新文档并已灌入 RAG 知识库（若返回 Qdrant 未连接提示则入库失败）：\n"
                    + "\n".join(doc_results)
                    + "\n回答涉及这些文档内容的问题时，请优先调用 rag 工具检索新知识后回答。")
            if vision_texts:
                parts.append(
                    "以下是已完成的【小麦田间图片分析】（wheat_vision 结果），请据此回答用户；"
                    "这些图片已分析完毕，不要再调用 wheat_vision/image_info 重新检测；"
                    "如需综合评价请调用 analysis，如需生成报告请调用 report(format=\"all\")：")
                parts.extend(f"[小麦图片{i + 1}]\n{t}" for i, t in enumerate(vision_texts))
            if general_texts:
                parts.append(
                    "用户上传的【非小麦图片】已做常规图片信息分析，请据此进行常规图片信息说明并正常聊天；"
                    "这些图片已判定不含小麦，不要再调用 wheat_vision/image_info：")
                parts.extend(f"[常规图片{i + 1}]\n{t}" for i, t in enumerate(general_texts))
            if not parts:
                parts.append("你好，介绍一下你能做什么")

            # 3) Manager 多 Agent 编排
            q.put(("status", "🧠 正在生成回答…"))
            manager = get_manager()
            answer = manager.run("\n\n".join(parts), on_step=lambda s: q.put(("step", s)))
            q.put(("final", answer))
        except Exception as e:  # noqa: BLE001
            q.put(("error", str(e)))

    threading.Thread(target=worker, daemon=True).start()

    while True:
        kind, payload = q.get()
        if kind == "step":
            history.append(_render_step(payload))
            yield emit(history, "⏳ 处理中…")
        elif kind == "image":
            history.append({"role": "assistant",
                            "content": (payload, "🖼 检测结果标注图")})
            yield emit(history, "⏳ 处理中…")
        elif kind == "status":
            yield emit(history, payload)
        elif kind == "final":
            history.append({"role": "assistant", "content": payload})
            files_out = _collect_report_paths(get_manager().steps)
            # 自动保存当前会话（无则新建），刷新侧边栏并高亮当前会话
            conv_id = conversation_store.save(history, conv_id=_CURRENT_CONV["id"])
            _CURRENT_CONV["id"] = conv_id
            yield emit(history, "✅ 处理完成",
                       hl=gr.update(choices=conversation_store.listbox_choices(), value=conv_id))
            break
        elif kind == "error":
            history.append({"role": "assistant", "content": f"❌ {payload}"})
            conv_id = conversation_store.save(history, conv_id=_CURRENT_CONV["id"])
            _CURRENT_CONV["id"] = conv_id
            yield emit(history, "❌ 处理失败",
                       hl=gr.update(choices=conversation_store.listbox_choices(), value=conv_id))
            break


# ---------------- 侧边栏：面板切换 / 统计卡片 ----------------

# ---------------- 数据看板：KPI / 趋势 / 最近检测流 ----------------

def _kpi_card(label, value, sub=""):
    """深色 KPI 小卡（青系渐变 + 发光数字）"""
    sub_html = (f'<div style="font-size:11px;color:#4a6a85;margin-top:4px;">{sub}</div>'
                if sub else "")
    return (f'<div style="flex:1;min-width:132px;background:linear-gradient(180deg,'
            f'rgba(6,182,212,.14), rgba(56,189,248,.05));'
            f'border:1px solid rgba(56,189,248,.22);border-radius:14px;'
            f'padding:16px 14px;text-align:center;box-shadow:0 0 20px rgba(6,182,212,.07);">'
            f'<div style="font-size:12.5px;color:#7fb3d9;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:24px;font-weight:700;color:#e0f2fe;line-height:1.2;'
            f'text-shadow:0 0 14px rgba(6,182,212,.35);">{value}</div>'
            f'{sub_html}</div>')


def render_kpi_row() -> str:
    """看板 KPI 行：累计检测 / 小麦 / 干旱 / 最近检测时间"""
    s = stats_store.get_stats()
    recs = detection_log.recent(1)
    latest = recs[0].get("time") if recs else s.get("updated_at", "")
    cards = [
        _kpi_card("📸 累计检测图像", s["total_images"], "含小麦与非小麦"),
        _kpi_card("🌾 累计识别小麦", s["total_wheat"], "YOLOv8 检测框总数"),
        _kpi_card("💧 累计干旱株数", s["total_drought"], "干旱分类命中"),
        _kpi_card("⏱ 最近检测", latest or "—", "最后一条检测时间"),
    ]
    return ('<div style="display:flex;flex-wrap:wrap;gap:12px;padding:4px 0;">'
            + "".join(cards) + "</div>")


def render_recent_gallery(limit=8) -> list:
    """最近检测标注图（小麦图）：(标注图路径, 说明) → gr.Gallery 点击可放大"""
    items = []
    for r in detection_log.recent(limit):
        ann = r.get("annotated", "")
        if not ann or not os.path.exists(ann):
            continue
        cap = (f"{r.get('time', '')} · {r.get('note', '')} · "
               f"小麦{r.get('wheat_count', 0)} / 干旱{r.get('drought_count', 0)}")
        items.append((ann, cap))
    return items


def render_recent_empty() -> str:
    """最近检测空状态提示"""
    return ('<div style="color:#4a6a85;padding:20px 16px;text-align:center;'
            'border:1px dashed rgba(56,189,248,.2);border-radius:12px;">'
            '🛰 暂无检测记录 —— 到「💬 对话」或「🔬 批量检测」跑一张田间图片，'
            '这里会展示标注图（点击可放大）。</div>')


def refresh_dashboard():
    """↻ 刷新看板：重读 stats.json + detection_log.jsonl 渲染 KPI/趋势/最近标注图"""
    gallery = render_recent_gallery()
    return (gr.update(value=render_kpi_row()),
            gr.update(value=detection_log.trend_df()),
            gr.update(value=gallery, visible=bool(gallery)),
            gr.update(visible=not bool(gallery)))


def _hide_more():
    """离开对话页时收起 ⋯ 弹出层（避免浮在其它页面上）"""
    return (gr.update(visible=False), gr.update(visible=False))


def toggle_rag_boost():
    """切换 RAG 查询增强（MQE/HyDE）：开 → 检索更准但更慢；关 → 快速检索"""
    _RAG_BOOST["on"] = not _RAG_BOOST["on"]
    Config.RAG_BOOST_OVERRIDE = _RAG_BOOST["on"]
    on = _RAG_BOOST["on"]
    return gr.update(value=("🔍" if on else "⚡"),
                     variant="primary" if on else "secondary")


# ---------------- 批量专业检测 ----------------

def _fd_path(fd):
    """文件输入 → 本地路径（兼容 str / dict / FileData）"""
    if isinstance(fd, str):
        return fd
    if isinstance(fd, dict):
        return fd.get("path") or fd.get("file") or fd.get("name") or ""
    return getattr(fd, "path", None) or getattr(fd, "name", None) or ""


def _batch_table(rows) -> str:
    head = "| 图片 | 小麦 | 株数 | 干旱率 | 干旱株数 | 状态 |"
    sep = "|:---|---:|---:|---:|---:|---|"
    body = []
    for r in rows:
        body.append(f"| {r['name']} | {r['wheat']} | {r['count']} | {r['rate']} | "
                    f"{r['drought']} | {r['status']} |")
    return f"### 🔬 批量检测结果\n\n{head}\n{sep}\n" + "\n".join(body)


def batch_detect(files, conf):
    """批量小麦专业检测（流式进度 + 预计剩余时间 + 50 张上限）。

    快速路径：直接 YOLO 检测做识别门控（跳过 Ollama 视觉大模型，每张省 30~90s），
    命中检测缓存的图再补干旱分类。逐张 yield 进度，避免"一直加载"的错觉。
    """
    files = list(files or [])
    if not files:
        yield (gr.update(value="⚠ 请先上传至少一张图片。"),
               gr.update(value=[]),
               "⚠ 未选择图片",
               gr.update(), gr.update())
        return
    conf = float(conf or 0.5)

    total = len(files)
    if total > _BATCH_MAX_FILES:
        files = files[:_BATCH_MAX_FILES]
        trunc_note = f"> ⚠ 单批最多处理 **{_BATCH_MAX_FILES}** 张，已截取前 {_BATCH_MAX_FILES} 张。\n\n"
    else:
        trunc_note = ""

    rows, ann_paths = [], []
    n_img = n_wheat = n_drought = 0
    t0 = time.time()

    for idx, fd in enumerate(files):
        p = _fd_path(fd)
        if not p or not os.path.exists(p):
            continue
        n_img += 1
        stats_store.record(image_count=1)
        try:
            w = get_wheat()
            # 批量快速路径：跳过识别门控的视觉兜底（Ollama 每张 30~90s），
            # 直接用 YOLO 检测结果判小麦（检测快、准确，且 analyze 会命中同一缓存）。
            detection = w._detect(p, conf)
            if not detection.get("count", 0):
                detection_log.append(image_count=1, note="批量·非小麦")
                rows.append({"name": os.path.basename(p), "wheat": "否", "count": 0,
                             "rate": "—", "drought": 0, "status": "未检测到小麦，跳过"})
            else:
                results = w.analyze(p, conf)  # 命中 _detect_cache，只补干旱分类
                det, dr = results.get("detection", {}), results.get("drought", {})
                ann = det.get("annotated_path")
                if ann and os.path.exists(ann):
                    ann_paths.append(ann)
                cnt = int(det.get("count", 0) or 0)
                drc = int(dr.get("drought_count", 0) or 0)
                n_wheat += cnt
                n_drought += drc
                stats_store.record(wheat_count=cnt, drought_count=drc)
                _log_wheat_detection(w, p, note="批量·小麦")
                rows.append({"name": os.path.basename(p), "wheat": "✅ 是", "count": cnt,
                             "rate": f"{float(dr.get('drought_rate', 0) or 0):.1%}",
                             "drought": drc, "status": "已完成"})
        except Exception as e:  # noqa: BLE001
            rows.append({"name": os.path.basename(p), "wheat": "—", "count": 0,
                         "rate": "—", "drought": 0, "status": f"失败: {e}"})

        # 实时进度 + 预计剩余时间（按已完成图的平均耗时外推）
        done = idx + 1
        elapsed = time.time() - t0
        eta_s = (elapsed / done * (total - done)) if done else 0
        md_progress = (f"### 🔬 批量检测中\n\n> ⏳ 已处理 **{done}/{total}** 张，"
                       f"预计剩余 **约 {eta_s:.0f}s**\n\n" + _batch_table(rows))
        yield (gr.update(value=md_progress),
               gr.update(value=list(ann_paths)),
               f"⏳ 处理中 {done}/{total}，剩余约 {eta_s:.0f}s",
               gr.update(), gr.update())

    elapsed = time.time() - t0
    md = trunc_note + _batch_table(rows)
    md += (f"\n\n本次共检测 **{n_img}** 张，识别小麦 **{n_wheat}** 株、其中干旱 **{n_drought}** 株，"
           f"耗时 **{elapsed:.0f}s**。（已累计进「📊 数据看板」）")
    notifications_store.add(
        "📊", "批量检测完成",
        f"{n_img} 张 · 小麦 {n_wheat} 株 / 干旱 {n_drought} 株 · 耗时 {elapsed:.0f}s")
    yield (gr.update(value=md),
           gr.update(value=ann_paths),
           f"✅ 批量检测完成：{n_img} 张，小麦 {n_wheat} 株 / 干旱 {n_drought} 株，耗时 {elapsed:.0f}s",
           gr.update(value=_badge_html()),
           gr.update(value=notifications_store.render_html()))


# ---------------- 历史会话处理 ----------------

def new_chat(chatbot):
    """保存当前会话（若非空）并开启新对话：清空对话区、收起 ⋯ 弹出层。

    返回 6 槽：chatbot / report_file / history_list / more_btn / action_card / status。
    """
    saved = ""
    if chatbot:
        conv_id = conversation_store.save(chatbot, conv_id=_CURRENT_CONV["id"])
        saved = bool(conv_id)
    _CURRENT_CONV["id"] = None
    _MORE_OPEN["v"] = False
    return (gr.update(value=[], visible=True),
            gr.update(value=None, visible=False),
            gr.update(choices=conversation_store.listbox_choices(), value=None),
            gr.update(visible=False), gr.update(visible=False),
            "✅ 已开启新对话" + ("，原对话已保存" if saved else ""))


def select_conv(choice, chatbot):
    """保存当前会话，调回所选历史会话。

    分组标题行（@group:*）不可选中，仅展示分组名。
    返回 6 槽：chatbot / report_file / history_list / more_btn / action_card / status。
    """
    if not choice:
        return (gr.update(value=chatbot, visible=True),
                gr.update(value=None, visible=False),
                gr.update(choices=conversation_store.listbox_choices(), value=None),
                gr.update(visible=False), gr.update(visible=False), "")
    # 分组标题行（@group:*）点击时忽略，保持当前会话选中态
    if isinstance(choice, str) and choice.startswith("@group:"):
        return (gr.update(value=chatbot, visible=True),
                gr.update(value=None, visible=False),
                gr.update(choices=conversation_store.listbox_choices(),
                          value=_CURRENT_CONV["id"]),
                gr.update(visible=bool(_CURRENT_CONV["id"])), gr.update(visible=False),
                f"🔖 {choice.split(':', 1)[1]}")
    if chatbot:
        conversation_store.save(chatbot, conv_id=_CURRENT_CONV["id"])
    messages = conversation_store.load(choice)
    _CURRENT_CONV["id"] = choice
    _MORE_OPEN["v"] = False
    return (gr.update(value=messages, visible=True),
            gr.update(value=None, visible=False),
            gr.update(choices=conversation_store.listbox_choices(), value=choice),
            gr.update(visible=True), gr.update(visible=False),
            "✅ 已调回历史会话")


def toggle_more():
    """⋯ 按钮：展开 / 收起 置顶·重命名·删除 小卡片"""
    _MORE_OPEN["v"] = not _MORE_OPEN["v"]
    return gr.update(visible=_MORE_OPEN["v"])


def pin_conv():
    """置顶 / 取消置顶当前会话"""
    cid = _CURRENT_CONV["id"]
    if not cid:
        return (gr.update(choices=conversation_store.listbox_choices(), value=None),
                gr.update(visible=False), "⚠ 请先选择要置顶的会话")
    ok = conversation_store.toggle_pin(cid)
    return (gr.update(choices=conversation_store.listbox_choices(), value=cid),
            gr.update(visible=False),
            "✅ 已置顶 / 取消置顶" if ok else "⚠ 会话不存在")


def rename_conv(new_title):
    """重命名当前会话"""
    cid = _CURRENT_CONV["id"]
    title = (new_title or "").strip()
    if not cid:
        return (gr.update(choices=conversation_store.listbox_choices(), value=None),
                gr.update(value=""), gr.update(visible=False), "⚠ 请先选择要重命名的会话")
    if not title:
        return (gr.update(choices=conversation_store.listbox_choices(), value=cid),
                gr.update(value=""), gr.update(visible=False), "⚠ 请输入新标题")
    ok = conversation_store.rename(cid, title)
    return (gr.update(choices=conversation_store.listbox_choices(), value=cid),
            gr.update(value=""), gr.update(visible=False),
            "✅ 已重命名" if ok else "⚠ 会话不存在")


def delete_conv(chatbot):
    """删除当前会话（若是当前对话则清空界面）；收起 ⋯ 弹出层"""
    cid = _CURRENT_CONV["id"]
    if not cid:
        return (gr.update(value=chatbot, visible=True),
                gr.update(value=None, visible=False),
                gr.update(choices=conversation_store.listbox_choices(), value=None),
                gr.update(visible=False), gr.update(visible=False),
                "⚠ 请先选择要删除的会话")
    ok = conversation_store.delete(cid)
    _CURRENT_CONV["id"] = None
    _MORE_OPEN["v"] = False
    return (gr.update(value=[], visible=True),
            gr.update(value=None, visible=False),
            gr.update(choices=conversation_store.listbox_choices(), value=None),
            gr.update(visible=False), gr.update(visible=False),
            "✅ 已删除会话" if ok else "⚠ 会话不存在")


# ---------------- 界面组装 ----------------

def _instance_diff_note() -> str:
    """本实例 vs 本地电脑完整版的差异说明（放在使用示例第一排，重点显示）。

    部署形态不同 → 能力有差异。逐项实测当前可达性（端口/模型/数据），不硬编码，
    保证与本实例实际能力一致。服务器=云端精简镜像版；本地=完整外部系统。
    """
    import glob
    import socket

    is_server = os.name == "posix"  # 服务器 Ubuntu(Linux)；本地 Windows
    variant = "云端服务器版" if is_server else "本地电脑完整版"
    other = "本地电脑完整版" if is_server else "云端服务器版"
    where = "阿里云 2核4G · 手机访问" if is_server else "Windows · 完整外部系统"

    def _port(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.2):
                return True
        except OSError:
            return False

    def _st(ok: bool) -> str:
        return "✅ 在线" if ok else "❌ 关"

    ollama = _port(11434)
    qdrant = _port(6333)
    neo4j = _port(7687)

    def _variants(sub, ext):
        base = os.path.join(Config.AGRICULTURE_MODELS_DIR, sub)
        if not os.path.isdir(base):
            return []
        return [d for d in sorted(os.listdir(base))
                if os.path.exists(os.path.join(base, d, "weights", "best" + ext))]

    det = _variants("detector", ".pt")
    cls = _variants("classifier", ".onnx")

    data_dir = Config.AGRICULTURE_DATA_DIR
    n_data = sum(len(glob.glob(os.path.join(data_dir, "**", f"*.{ext}"),
                               recursive=True)) if os.path.isdir(data_dir) else 0
                 for ext in ("jpg", "png"))

    note = (
        f"> ⚠️ **本实例 = {variant}**（{where}）\n"
        f"> 与 **{other}** 的能力差异（部署形态不同所致）与影响：\n>\n"
        f"> 1. **模型与数据**：本实例 **{len(det) + len(cls)} 个模型权重**（检测 {len(det)} · "
        f"分类 {len(cls)}）、训练图片 **{n_data} 张**。云端版部署包只拷『最佳检测+最佳分类』2 个权重、"
        f"不打包训练图片（省体积），本地完整版含全部实验对比版 + 4 万张训练图 → 问『用了哪些模型 / "
        f"数据集多大』时云端结果比本地少。\n"
        f"> 2. **本地视觉 Ollama**：本实例 **{_st(ollama)}**。云端版默认关（4G 内存防 OOM）→ "
        f"『图里有什么』不可用，小麦检测的视觉兜底自动降级为 YOLOv8 检测，**检测/干旱/报告主流程不受影响**。\n"
        f"> 3. **语义记忆图谱 Neo4j**：本实例 **{_st(neo4j)}**。云端版默认关（防 OOM）→ "
        f"实体关系记忆降级为 Qdrant 向量检索。\n"
        f"> 4. **RAG 向量库 Qdrant**：本实例 **{_st(qdrant)}**。云端版常开 → 知识库问答正常；本地按需启动。\n"
        f"> 5. **天气查询**：两侧均需联网（wttr.in），云端脚本已补齐 → 可用。\n"
        f"> 6. **大模型 DeepSeek / 计算器 / 笔记 / 记忆 / 终端 / 知识检索**：纯本地逻辑 + DeepSeek API，两侧一致。\n"
        f"> 7. **速度**：云端 2核4G CPU 推理比本地慢，高峰期内存接近上限。\n>\n"
        f"> **原因**：云端版是『电脑关机也能用』的精简部署——只带平台必需模型、默认关闭高内存可选服务"
        f"（Ollama/Neo4j）防 OOM；检测/干旱/报告/知识/天气/记忆/笔记/批量检测等核心功能不受影响。\n"
    )
    return note


_USAGE_TEXT = _instance_diff_note() + """**使用示例**

**🔬 田间图片分析**
- 上传 / 拖拽**小麦田间图**并发送 → 自动检测株数、干旱率，展示**检测标注图**并给出分析
- 上传**其他图片** → 自动识别为「不含小麦」，按常规图片说明与正常聊天
- 对任意图片提问「图里有什么」→ 本地视觉模型（Ollama Qwen2.5-VL）语义理解（CPU 推理约 30~90s）

**📄 文档知识库**
- 上传 **txt / md / pdf / docx / csv / json** 并发送 → 自动灌入 RAG 知识库，之后提问即可检索到文档内容（需本机 Qdrant 服务）
- 发送框右侧 **🔍 / ⚡** 开关切换 RAG 查询增强（MQE/HyDE）：🔍 更准更慢，⚡ 更快

**🧠 智能问答**
- 提问「为什么冬小麦会发生干旱胁迫？」→ 农业知识专家（RAG 检索增强）回答
- 提问「用了哪些模型 / 哪个检测模型最佳 / 数据集多大」→ 实验数据查询
- 说「记住… / 还记得上次…」→ 跨会话记忆（SQLite 持久化，离线可用）
- 说「记个笔记 / 我的待办 / 查看笔记」→ 结构化笔记
- 输入「帮我算 150 亩×8.6 kg/亩 产量」→ 内置计算器
- 说「北京天气怎么样」→ 天气查询（MCP，需联网）

**📊 平台功能**
- **数据统计**：累计检测 / 株数 / 干旱 / 实验准确率；↻ 刷新，📌 固定到聊天界面顶部
- **专业检测**：批量上传多张图片，只做小麦检测 + 干旱分析
- **设置**：调整置信度阈值、查看系统 Agent 技术栈详情
- 分析小麦图片后说「生成一份报告」→ 生成 md / docx / pdf 下载"""

_SETTINGS_DETAIL = """**系统详情（Agent 技术栈）**

平台基于**多智能体编排**架构，各 Agent 分工协作完成农业监测问答：

| Agent | 职责 |
|---|---|
| **ManagerAgent** | 总调度：分析请求并分发给最合适的子 Agent |
| **WheatVisionAgent** | 视觉识别：YOLOv8 小麦检测 + 干旱分类（识别门控） |
| **AgricultureExpertAgent** | 农业知识专家：ReAct 推理 + RAG 检索增强回答 |
| **AnalysisAgent** | 综合检测与干旱结果，给出评价与建议 |
| **ReportAgent** | 生成《冬小麦智能监测报告》（md / docx / pdf） |
| **AuthorAgent** | 介绍开发者 / 技术路线 |

**关键技术**：多 Agent 编排（Manager 调度）· ReAct 推理循环 · 工具调用（Function Calling）· 记忆系统（SQLite 跨会话 + 语义记忆）· RAG 检索增强（MQE 多查询扩展 + HyDE 假设文档嵌入）· 通信协议 MCP（农业数据 / 天气）· 本地视觉理解（Ollama Qwen2.5-VL）"""

# gradio 5.45 深/浅色完全由前端 `prefers-color-scheme` 决定（后端没有 theme_mode 开关）。
# 在页面 <head> 注入脚本：把该媒体查询恒替换为"浅色命中"并吞掉其 change 监听，
# 再兜底剥离已添加的 .dark，保证应用永远默认浅色、不跟随系统深色。
_FORCE_LIGHT_HEAD = r"""
<script>
(function () {
  try {
    var _origMM = window.matchMedia && window.matchMedia.bind(window);
    window.matchMedia = function (q) {
      if (String(q).indexOf('prefers-color-scheme') !== -1) {
        return {
          matches: false, media: String(q), onchange: null,
          addEventListener: function () {}, removeEventListener: function () {},
          addListener: function () {}, removeListener: function () {},
          dispatchEvent: function () { return false; }
        };
      }
      return _origMM ? _origMM(q) : null;
    };
    function strip() {
      if (document.body) document.body.classList.remove('dark');
      if (document.documentElement) document.documentElement.classList.remove('dark');
    }
    strip();
    if (window.MutationObserver) {
      new MutationObserver(function (ms) {
        for (var i = 0; i < ms.length; i++) {
          var t = ms[i];
          if (t.type === 'attributes' && t.attributeName === 'class' &&
              t.target.classList && t.target.classList.contains('dark')) strip();
        }
      }).observe(document.documentElement, { attributes: true, subtree: true, attributeFilter: ['class'] });
    }
    setTimeout(strip, 0);
    setTimeout(strip, 500);
  } catch (e) {}
})();
</script>
"""

_SIDEBAR_CSS = """
/* 全局：更大更清晰的文字（参考图宽松舒适风格） */
body, .gradio-container, .main, textarea, input, select, button, .prose {
    font-size: 15px !important;
    line-height: 1.6 !important;
}
.gradio-container { max-width: 1400px !important; }
h1 { font-size: 22px !important; margin-bottom: 2px !important; }

/* 侧边栏整体：浅灰白背景、更宽内边距 */
#history-list {
    background: #f9fafb !important;
}

/* 侧边栏标题（左上角） */
#sidebar-title h3 { font-size: 19px !important; margin: 0 0 2px !important; line-height: 1.35 !important; }
#sidebar-title h4, #sidebar-title h5 { color: #6b7280 !important; font-size: 13px !important; margin: 0 !important; }

/* 左侧功能按钮：小图标 + 名称左对齐（⋯ 弹出按钮除外，单独 fixed 定位）
   不加粗、按钮间距缩小，保持侧边栏紧凑 */
#left-panel button:not(#more-btn) {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 8px !important;
    text-align: left !important;
    width: 100% !important;
    font-weight: 400 !important;
    margin: 1px 0 !important;
    padding: 8px 12px !important;
}

/* 侧边栏会话列表：去掉 radio 圆点，选项变成可点击的列表行 */
#history-list .wrap { gap: 0 !important; }
#history-list label {
    display: block !important;
    padding: 10px 14px !important;
    border-radius: 8px !important;
    margin: 3px 6px !important;
    cursor: pointer !important;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-size: 14.5px !important;
    color: #1f2937 !important;
}
#history-list label:hover { background: #eef0f2 !important; }
#history-list input[type="radio"] { display: none !important; }
#history-list label:has(input:checked) {
    background: #ffffff !important;
    box-shadow: 0 1px 2px rgba(16,24,40,0.06), 0 1px 3px rgba(16,24,40,0.1) !important;
    font-weight: 600 !important;
    border: 1px solid #e5e7eb !important;
}
/* 选中会话名称右侧的 ⋯ 由浮动的 more-btn 提供（JS 定位到选中行右侧），无需 ::after */

/* 分组标题行（@group:*）：灰色小字、无选中态、点击无效 */
#history-list label:has(input[value^="@group:"]) {
    pointer-events: none !important;
    cursor: default !important;
    color: #9ca3af !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.4px !important;
    padding: 8px 14px 2px !important;
    margin: 8px 6px 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-bottom: 1px solid #e5e7eb !important;
    border-radius: 0 !important;
}
#history-list label:has(input[value^="@group:"]):hover {
    background: transparent !important;
}
#history-list label:has(input[value^="@group:"]) input[type="radio"] {
    display: none !important;
}

/* ⋯ 按钮 + 操作小卡片：弹出在选中会话右侧。
   二者放主区顶层（避开侧边栏 transform 包含块与 overflow 裁剪），JS 按选中行
   视口坐标用 fixed 定位。隐藏时甩到屏幕外（JS 用 setProperty(...) 'important' 覆盖）。 */
#more-btn, #action-card {
    position: fixed !important;
    top: -9999px;
    left: -9999px;
    z-index: 2000 !important;
}
#more-btn {
    width: 32px !important;
    min-width: 32px !important;
    height: 32px !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 8px rgba(16,24,40,.14) !important;
    font-size: 16px !important;
    line-height: 1 !important;
}
/* gradio 用 .hidden 类隐藏按钮；ID+important 会让按钮永远显示，
   必须再用「ID+类+important」把它压回去，否则隐藏后 ⋯ 仍浮在屏上 */
#more-btn.hidden { display: none !important; }
#action-card {
    width: 100px !important;
    min-width: 0 !important;   /* 压掉 gradio Column 的内联 min-width: min(320px,100%)，否则宽度永远≥320 */
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 4px !important;
    box-shadow: 0 4px 12px rgba(16,24,40,.16) !important;
    padding: 3px !important;
    margin: 0 !important;
}
/* 操作卡片按钮（不换行、不截断，三行文字各占一行） */
#action-card button {
    padding: 3.5px 5px !important;
    margin: 1px 0 !important;
    font-size: 10px !important;
    white-space: nowrap !important;
}
/* 统计卡片工具栏图标按钮（↻ 刷新 / 📌 固定 / ✕ 关闭）：窄小、不撑满行 */
#stats-refresh, #stats-pin, #stats-close {
    width: auto !important;
    min-width: 42px !important;
    padding: 0 12px !important;
}
/* RAG 查询增强开关：纯图标小按钮（紧邻发送区右侧），状态靠图标+底色区分 */
#boost-btn {
    align-self: stretch !important;
    width: 40px !important;
    min-width: 40px !important;
    min-height: 38px !important;
    border-radius: 9px !important;
    font-size: 15px !important;
    padding: 0 !important;
}
"""

# ============================================================
# UI/UX Pro Max · 墨绿青科技 深色仪表盘层
# 覆盖 _SIDEBAR_CSS 的浅色配色为深色（布局 hack 全部保留，后续同优先级规则胜出）。
# 实现：gradio 5.45 主题变量注入在 `:root`（浅色）/ `:root .dark`（深色），
# 保留 _FORCE_LIGHT_HEAD 恒为浅色，再在本层把 :root 变量改成深色值，
# 即可稳定得到深色仪表盘（不碰 gradio 脆弱的 .dark 模式）。去掉整层即可回退。
# ============================================================
_DARK_CSS = """
/* ---- ① 主题变量：浅色 :root 覆盖为蓝黑深色（青→蓝同色系） ---- */
:root {
    --background-fill-primary: #0b1220;
    --background-fill-secondary: #111f33;
    --background-fill-secondary-hover: #15263d;
    --body-text-color: #e3ecf6;
    --body-text-color-subdued: #7fa8cf;
    --color-accent: #06b6d4;
    --color-accent-base: #38bdf8;
    --color-accent-soft: rgba(6, 182, 212, .16);
    --border-color-primary: rgba(56, 189, 248, .18);
    --border-color-accent-subdued: rgba(6, 182, 212, .28);
    --block-background-fill: #111f33;
    --block-border-color: rgba(56, 189, 248, .18);
    --block-title-text-color: #e3ecf6;
    --block-title-background-fill: transparent;
    --block-label-text-color: #7fa8cf;
    --block-label-background-fill: transparent;
    --block-info-text-color: #4a6a85;
    --input-background-fill: #0d1729;
    --input-background-fill-focus: #0f1d33;
    --input-border-color: rgba(56, 189, 248, .24);
    --input-text-color: #e3ecf6;
    --input-placeholder-color: #3d5a75;
    --button-primary-background-fill: #06b6d4;
    --button-primary-background-fill-hover: #22d3ee;
    --button-primary-text-color: #041018;
    --button-secondary-background-fill: #15263d;
    --button-secondary-background-fill-hover: #1a2f4b;
    --button-secondary-text-color: #a5c8e8;
    --button-secondary-text-color-hover: #dbeafe;
    --table-background-fill: #0d1729;
    --table-even-background-fill: #101f35;
    --table-odd-background-fill: #111f33;
    --table-border-color: rgba(56, 189, 248, .16);
    --table-text-color: #c9d8e8;
    --table-row-focus: rgba(6, 182, 212, .12);
    --panel-background-fill: #111f33;
    --checkbox-background-color: #0d1729;
    --checkbox-background-color-selected: #06b6d4;
    --checkbox-label-background-fill: #111f33;
    --checkbox-label-background-fill-hover: #15263d;
    --checkbox-label-background-fill-selected: rgba(6, 182, 212, .14);
    --slider-color: #06b6d4;
    --error-background-fill: rgba(248, 113, 113, .12);
}

/* ---- ② 容器：蓝黑渐变底 + 顶部青蓝辉光 ---- */
body, .gradio-container, .main, textarea, input, select, button, .prose {
    color: #e3ecf6 !important;
}
.gradio-container {
    background:
        radial-gradient(1100px 520px at 12% -12%, rgba(6, 182, 212, .12), transparent 55%),
        radial-gradient(900px 480px at 100% -6%, rgba(59, 130, 246, .10), transparent 52%),
        #0b1220 !important;
    border: 1px solid rgba(56, 189, 248, .16) !important;
    border-radius: 20px !important;
    box-shadow: 0 0 46px rgba(6, 182, 212, .06) !important;
}
h1, h2, h3 { color: #e3ecf6 !important; text-shadow: 0 0 18px rgba(56, 189, 248, .20) !important; }
h4, h5 { color: #a5c8e8 !important; }
.prose p, .prose li { color: #c9d8e8 !important; }
.prose strong { color: #dbeafe !important; }
.prose table, .prose th, .prose td { border-color: rgba(56, 189, 248, .16) !important; }

/* ---- ③ 顶部导航 Tab：四页同色系渐变（青→天蓝→蓝→靛蓝），选中辉光 ---- */
.tab-button { color: #8aa6c0 !important; letter-spacing: .4px !important; }
.tab-button:hover { color: #dbeafe !important; background: rgba(56, 189, 248, .07) !important; }

#tab-dashboard-button.selected {
    color: #22d3ee !important;
    border-bottom-color: #06b6d4 !important;
    background: transparent !important;
    text-shadow: 0 0 14px rgba(6, 182, 212, .55) !important;
}
#tab-chat-button.selected {
    color: #7dd3fc !important;
    border-bottom-color: #0ea5e9 !important;
    background: transparent !important;
    text-shadow: 0 0 14px rgba(14, 165, 233, .55) !important;
}
#tab-batch-button.selected {
    color: #93c5fd !important;
    border-bottom-color: #3b82f6 !important;
    background: transparent !important;
    text-shadow: 0 0 14px rgba(59, 130, 246, .55) !important;
}
#tab-settings-button.selected {
    color: #a5b4fc !important;
    border-bottom-color: #6366f1 !important;
    background: transparent !important;
    text-shadow: 0 0 14px rgba(99, 102, 241, .55) !important;
}

/* ---- ④ 会话历史列（覆盖 _SIDEBAR_CSS 浅色） ---- */
#sidebar-title h3 { color: #dbeafe !important; text-shadow: 0 0 16px rgba(56, 189, 248, .30) !important; }
#sidebar-title h4, #sidebar-title h5 { color: #7fa8cf !important; }
#history-list { background: transparent !important; }
#history-list label { color: #c9d8e8 !important; }
#history-list label:hover { background: #15263d !important; }
#history-list label:has(input:checked) {
    background: #182c46 !important;
    border-color: rgba(56, 189, 248, .45) !important;
    box-shadow: 0 0 14px rgba(56, 189, 248, .16) !important;
    color: #dbeafe !important;
}
#history-list label:has(input[value^="@group:"]) {
    color: #3d5a75 !important;
    border-bottom-color: rgba(56, 189, 248, .14) !important;
}
#left-panel button:not(#more-btn):hover { background: #1a2f4b !important; color: #dbeafe !important; }

/* ---- ⑤ 弹出层（⋯ 菜单 / 操作卡） ---- */
#more-btn {
    background: #15263d !important;
    border: 1px solid rgba(56, 189, 248, .25) !important;
    color: #dbeafe !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, .45) !important;
}
#action-card {
    background: #131f33 !important;
    border: 1px solid rgba(56, 189, 248, .22) !important;
    box-shadow: 0 8px 26px rgba(0, 0, 0, .5) !important;
}
#action-card button:hover { background: #1a2f4b !important; color: #dbeafe !important; }

/* ---- ⑥ 功能面板：深色卡片 ---- */
#usage-panel, #stats-panel, #batch-panel, #settings-panel {
    background: #111f33 !important;
    border: 1px solid rgba(56, 189, 248, .18) !important;
    border-radius: 16px !important;
    padding: 18px !important;
    box-shadow: 0 0 22px rgba(6, 182, 212, .05) !important;
}
#batch-panel .gr-gallery { border-radius: 14px !important; }

/* ---- ⑦ 对话区：气泡深色化 ---- */
#chat-area { border-radius: 16px !important; overflow: hidden !important; }
#chat-area .bot { background: #0f1c2e !important; border-color: rgba(56, 189, 248, .14) !important; }
#chat-area .user { background: #0e3550 !important; border-color: rgba(6, 182, 212, .22) !important; }

/* ---- ⑧ 增强检索开关 / 交互反馈 ---- */
#boost-btn {
    background: #0e3550 !important;
    color: #dbeafe !important;
    border: 1px solid rgba(6, 182, 212, .25) !important;
}
#boost-btn:hover { box-shadow: 0 0 0 2px rgba(6, 182, 212, .35) !important; }
button, label, [role="button"] { cursor: pointer !important; }
button:focus-visible, input:focus-visible, textarea:focus-visible,
select:focus-visible, [tabindex]:focus-visible {
    outline: 2px solid #38bdf8 !important;
    outline-offset: 2px !important;
}

/* ---- ⑨ 细节点缀：滚动条 + 手机端适配 ---- */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: #0b1220 !important; }
::-webkit-scrollbar-thumb { background: #1a2f4b !important; border-radius: 6px !important; }
::-webkit-scrollbar-thumb:hover { background: #1f3a5c !important; }

/* ---- ⑩ 移动端（≤768px）：竖排堆叠 + 触控尺寸 + iOS 防缩放 ---- */
@media (max-width: 768px) {
    /* Tab 栏可横滚；选项加大触控高度 */
    .tabs { overflow-x: auto !important; }
    .tab-button {
        white-space: nowrap !important;
        min-height: 44px !important;
        padding: 10px 12px !important;
        font-size: 13px !important;
    }
    /* 输入类 ≥16px：避免 iOS 聚焦自动放大页面 */
    textarea, input, select { font-size: 16px !important; }

    /* 容器贴边：去掉外边距与圆角 */
    .gradio-container {
        margin: 0 !important;
        border-radius: 0 !important;
        border-left: none !important;
        border-right: none !important;
        box-shadow: none !important;
    }

    /* 对话页：历史列堆到顶部（限高滚动），聊天主区在下方 */
    #chat-row { flex-direction: column !important; gap: 6px !important; }
    #chat-row > * { min-width: 0 !important; width: 100% !important; }
    #left-panel { max-height: 32vh !important; overflow-y: auto !important; }
    #chat-area { height: 60vh !important; max-height: 60vh !important; }

    /* 看板：趋势 + 最近检测两列竖排 */
    #dash-row { flex-direction: column !important; }
    #dash-row > * { min-width: 0 !important; width: 100% !important; }

    /* 触控目标 ≥44px（部分已有固定宽度，仅提升高度） */
    button:not(#boost-btn):not(#more-btn) { min-height: 44px !important; }
    #boost-btn { min-height: 44px !important; }
    #more-btn { width: 40px !important; height: 40px !important; }
    #history-list label { padding: 12px 14px !important; }

    /* KPI 卡间距收紧，两列排布更紧凑 */
    #dash-kpis > div { gap: 8px !important; }
}
"""


# ⋯ 菜单弹出定位脚本：more-btn / action-card 是主区顶层组件（fixed），
# 按「当前选中会话行」的视口坐标定位到其右侧（行中心对齐 ⋯，卡片紧随 ⋯ 下方）。
# 二者都在主区，不依赖侧边栏（.sidebar 的 transform 会构成 fixed 包含块、overflow 会裁剪）。
_MORE_POSITION_JS = r"""() => {
  try {
    // CSS 里 top/left 有 -9999px 兜底，须用 'important' 覆盖，否则内联样式赢不过 !important
    const setPos = (el, x, y) => {
      if (el.style.left !== x + 'px') el.style.setProperty('left', x + 'px', 'important');
      if (el.style.top !== y + 'px') el.style.setProperty('top', y + 'px', 'important');
      if (el.style.position !== 'fixed') el.style.setProperty('position', 'fixed', 'important');
    };
    const place = () => {
      const list = document.querySelector('#history-list');
      if (!list) return;
      const more = document.querySelector('#more-btn');
      const card = document.querySelector('#action-card');
      if (!more && !card) return;   // 两个弹出层都还没挂载（gradio 懒挂载）
      const checked = list.querySelector('input:checked');
      const row = checked ? checked.closest('label') : null;
      if (!row) return;             // 无选中会话 → 不动（隐藏由 gradio 的 visible 控制）
      const rr = row.getBoundingClientRect();
      const left = rr.right + 8;
      const cy = rr.top + rr.height / 2;
      // ⋯ 只要挂载就预定位到选中行右侧；显示/隐藏交给 gradio 的 visible（.hidden → display:none）
      if (more) setPos(more, left, cy - 16);
      // 小卡片仅在可见时定位（点了 ⋯ 才展开）
      if (card && getComputedStyle(card).display !== 'none') {
        const cardH = card.offsetHeight || 86;
        let t = cy + 16;
        const maxT = Math.max(0, window.innerHeight - cardH - 12);
        if (t > maxT) t = maxT;
        setPos(card, left, t);
      }
    };
    // 关键：gradio 的 visible=False 组件一开始不在 DOM，选中会话/展开卡片时才会挂载。
    // 所以 observer 必须立刻挂上（不能等 #action-card 存在），靠 childList 捕获挂载瞬间，
    // 靠 style/class 捕获可见性切换。
    const obs = new MutationObserver(place);
    obs.observe(document.body, { subtree: true, childList: true,
                                attributes: true, attributeFilter: ['style', 'class'] });
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    place();
    // 兜底轮询：radio 选中态是 DOM 属性（checked），MutationObserver 的属性过滤器看不到，
    // 400ms 周期重算保证任何时候都对齐当前选中行；5 分钟后停掉避免长期空转。
    const iv = setInterval(place, 400);
    setTimeout(() => clearInterval(iv), 300000);
    setTimeout(place, 500);
    setTimeout(place, 1500);
  } catch (e) {}
}"""


def build_ui():
    with gr.Blocks(
        title="YOLOv8-Agent 农业智能监测平台",
        theme=gr.themes.Soft(
            primary_hue=gr.themes.colors.cyan,
            secondary_hue=gr.themes.colors.blue,
            neutral_hue=gr.themes.colors.slate,
        ),
        css=_SIDEBAR_CSS + _DARK_CSS,
        head=_FORCE_LIGHT_HEAD,
    ) as demo:
        # ================= 顶部导航：四页 =================
        with gr.Tabs(elem_id="main-tabs"):
            # ---------- ① 数据看板（默认落地页） ----------
            with gr.TabItem("📊 数据看板", elem_id="tab-dashboard") as tab_dashboard:
                gr.Markdown(
                    "### 🛰 农业监测数据看板\n"
                    "实时 KPI + 检测趋势 + 最近检测流。在「💬 对话」或「🔬 批量检测」"
                    "分析田间图片后自动累计。",
                    elem_id="dash-header",
                )
                dashboard_kpis = gr.HTML(render_kpi_row(), elem_id="dash-kpis")
                with gr.Row(elem_id="dash-row"):
                    with gr.Column(scale=3, elem_id="dash-trend-col"):
                        gr.Markdown("#### 📈 检测趋势（累计）")
                        trend_chart = gr.LinePlot(
                            value=detection_log.trend_df(),
                            x="time", y="count", color="metric",
                            height=300,
                            elem_id="dash-trend",
                        )
                    with gr.Column(scale=2, elem_id="dash-recent-col"):
                        gr.Markdown("#### 🕓 最近检测（点击标注图可查看大图）")
                        recent_gallery = gr.Gallery(
                            value=render_recent_gallery(),
                            label=None,
                            columns=2, height=300, object_fit="cover",
                            preview=True,  # 点击缩略图 → 放大查看详细检测标注
                            elem_id="dash-recent",
                        )
                        recent_empty = gr.HTML(render_recent_empty())
                dash_refresh = gr.Button("↻ 刷新看板", elem_id="dash-refresh-btn",
                                         variant="secondary")

            # ---------- ② 对话 ----------
            with gr.TabItem("💬 对话", elem_id="tab-chat"):
                with gr.Row(elem_id="chat-row"):
                    # 会话历史列
                    with gr.Column(scale=1, min_width=240, elem_id="left-panel"):
                        gr.Markdown("### 🌾 YOLOv8-Agent 农业智能监测平台",
                                    elem_id="sidebar-title")
                        new_btn = gr.Button("➕ 新对话", variant="primary")
                        history_list = gr.Radio(
                            conversation_store.listbox_choices(),
                            label="📂 会话记录",
                            info="置顶 / 最近，点击即调回",
                            elem_id="history-list",
                            interactive=True,
                        )
                        status = gr.Markdown("")
                    # 对话主区
                    with gr.Column(scale=3, elem_id="chat-main"):
                        chatbot = gr.Chatbot(type="messages", height=520,
                                             label="与农业监测智能体对话",
                                             elem_id="chat-area")
                        report_file = gr.File(label="📄 报告下载", interactive=False,
                                              visible=False)
                        _boost_init_on = bool(Config.RAG_ENABLE_MQE)
                        with gr.Row():
                            textbox = gr.MultimodalTextbox(
                                file_types=["image", ".txt", ".md", ".pdf", ".docx",
                                            ".doc", ".csv", ".json"],
                                file_count="multiple",
                                placeholder="输入消息",
                                lines=2,
                                scale=10,
                            )
                            boost_btn = gr.Button(
                                value="🔍" if _boost_init_on else "⚡",
                                scale=0,
                                elem_id="boost-btn",
                                variant="primary" if _boost_init_on else "secondary",
                            )

            # ---------- ③ 批量检测 ----------
            with gr.TabItem("🔬 批量检测", elem_id="tab-batch") as tab_batch:
                gr.Markdown("### 🔬 批量小麦专业检测\n"
                            "上传多张图片（单批最多 **50 张**），直接 YOLOv8 快速检测 → "
                            "仅对含小麦的图片做干旱分类，并累计进数据看板。\n"
                            "> ⚡ 处理中实时显示进度与预计剩余时间。")
                batch_files = gr.Files(file_types=["image"], file_count="multiple",
                                       label="📤 选择 / 拖拽多张图片")
                batch_go = gr.Button("🚀 开始批量检测", variant="primary")
                batch_result = gr.Markdown("")
                batch_gallery = gr.Gallery(label="🖼 检测标注图（仅小麦）", columns=4,
                                           height=260, object_fit="cover")

            # ---------- ④ 设置 ----------
            with gr.TabItem("⚙️ 设置", elem_id="tab-settings") as tab_settings:
                gr.Markdown("### ⚙️ 平台设置")
                conf = gr.Slider(0.1, 1.0, value=0.5, step=0.05,
                                 label="置信度阈值",
                                 info="图片检测与干旱分类的置信度阈值（对话图片与批量检测共用）")
                gr.Markdown("---")
                gr.Markdown(_SETTINGS_DETAIL)
                gr.Markdown("---")
                gr.Markdown("### 📖 使用指南")
                gr.Markdown(_USAGE_TEXT, elem_id="usage-panel")

        # ---- ⋯ 弹出层（fixed，放 Blocks 顶层避开 tab 容器 transform/裁剪）----
        more_btn = gr.Button("⋯", visible=False, elem_id="more-btn")
        with gr.Column(visible=False, elem_id="action-card") as action_card:
            pin_btn = gr.Button("📌 置顶")
            with gr.Row():
                rename_box = gr.Textbox(placeholder="输入新标题…", show_label=False, scale=2)
                rename_btn = gr.Button("重命名", scale=1)
            del_btn = gr.Button("🗑 删除会话", variant="stop")

        # ---- 对话事件（respond 输出 5 槽：chatbot / textbox / report_file /
        #      history_list[自动保存刷新+高亮] / status[实时处理状态]）----
        textbox.submit(respond, [chatbot, textbox, conf],
                       [chatbot, textbox, report_file, history_list, status])
        # RAG 查询增强（MQE/HyDE）开关：写入 Config 运行时覆盖，RAGTool 优先读取
        boost_btn.click(toggle_rag_boost, None, [boost_btn])

        # ---- 会话管理事件 ----
        new_btn.click(new_chat, [chatbot],
                      [chatbot, report_file, history_list, more_btn, action_card, status])
        history_list.select(select_conv, [history_list, chatbot],
                            [chatbot, report_file, history_list, more_btn, action_card, status])
        more_btn.click(toggle_more, None, [action_card])
        pin_btn.click(pin_conv, None, [history_list, action_card, status])
        rename_btn.click(rename_conv, [rename_box],
                         [history_list, rename_box, action_card, status])
        del_btn.click(delete_conv, [chatbot],
                      [chatbot, report_file, history_list, more_btn, action_card, status])

        # ---- 批量检测 ----
        batch_go.click(batch_detect, [batch_files, conf],
                       [batch_result, batch_gallery, status])

        # ---- 数据看板：刷新按钮 + 页面加载时同步（KPI + 趋势 + 最近图集 + 空态）----
        _dash_outputs = [dashboard_kpis, trend_chart, recent_gallery, recent_empty]
        dash_refresh.click(refresh_dashboard, None, _dash_outputs)
        demo.load(refresh_dashboard, None, _dash_outputs)

        # ---- 离开对话页时收起 ⋯ 弹出层（避免浮在其它页上）----
        tab_dashboard.select(_hide_more, None, [more_btn, action_card])
        tab_batch.select(_hide_more, None, [more_btn, action_card])
        tab_settings.select(_hide_more, None, [more_btn, action_card])

        # ---- 注入 ⋯ 菜单弹出定位脚本（选中会话右侧弹出）----
        demo.load(None, js=_MORE_POSITION_JS)
    return demo



# ============================================================================
# 浅绿参考风 UI 层（覆盖上方旧深色 build_ui 与 CSS 常量）
# dock 布局 / 视图切换 / 对话欢迎态 / 行业资讯 / 询问示例 / 看图识别页 /
# 通知中心 / 反馈表单。均在本模块执行末尾定义，__main__ 运行时取到新绑定。
# ============================================================================

# ---- 主题：浅绿 CSS 覆盖旧深色层 ----
_UI_CSS = None


def _load_light_css() -> str:
    global _UI_CSS
    if _UI_CSS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "main.css")
        try:
            with open(p, "r", encoding="utf-8") as f:
                _UI_CSS = f.read()
        except OSError:
            _UI_CSS = ""
    return _UI_CSS


_SIDEBAR_CSS = _load_light_css()   # 覆盖旧浅灰 CSS
_DARK_CSS = ""                      # 关闭深色覆盖层（保留 _FORCE_LIGHT_HEAD 恒浅色）

# dock 激活高亮 + 视图入场动画：观察各视图 visible 变化 → 点亮对应 nav，
# 并对「切入的视图」挂 .ha-view-in 触发 CSS 过渡（240ms 淡入 + 上浮 8px）。
_UI_BOOT_JS = r"""() => {
  const map = {'view-chat':'nav-chat','view-single':'nav-single','view-batch':'nav-batch',
               'view-dash':'nav-dash','view-set':'nav-set','view-notif':'nav-notif',
               'view-feedback':'nav-feedback'};
  const names = Object.values(map);
  const isVis = (id) => {
    const el = document.getElementById(id);
    return !!(el && el.style && getComputedStyle(el).display !== 'none');
  };
  const curView = () => {
    for (const v of Object.keys(map)) if (isVis(v)) return v;
    return null;
  };
  const curNav = () => { const v = curView(); return v ? map[v] : null; };
  let lastView = null;                       // null → 首屏 chat 也走一次入场
  const paint = () => {
    const cur = curNav();
    names.forEach(n => { const b = document.getElementById(n);
      if (b) b.classList.toggle('dock-active', n === cur); });
  };
  const animateView = (v) => {
    const el = document.getElementById(v);
    if (!el) return;
    el.classList.remove('ha-view-in');
    void el.offsetWidth;                     // 强制 reflow，保证同视图重复进入也能重放
    el.classList.add('ha-view-in');
    setTimeout(() => { el.classList.remove('ha-view-in'); }, 320);
  };
  const onAny = () => {
    const v = curView();
    paint();
    if (v && v !== lastView) { animateView(v); lastView = v; }
  };
  window.paint = paint;
  const obs = new MutationObserver(onAny);
  // childList 必须监听：gradio 对从未显示过的视图列是「懒挂载」，切页靠插入/移除
  // DOM 节点（而非仅改现有节点 style），不监听 childList 就看不到这次切换。
  obs.observe(document.body, {subtree:true, attributes:true, childList:true,
                              attributeFilter:['style','class']});
  window.addEventListener('load', onAny);
  setTimeout(onAny, 200); setTimeout(onAny, 600); setTimeout(onAny, 1600);
}"""

# 资讯自动重试拉取：本机经代理的国际源会整体翻转，首屏/手动刷新可能落在无网窗口。
# 页面加载 ~9s 后开始，每 ~9s 点一次「刷新资讯」，一旦头栏不再显示「离线示例」即停
# （命中后 news 缓存 30 分钟，后续刷新即时返回，不再消耗网络）；welcome 关闭也停。
_NEWS_AUTOFETCH_JS = r"""() => {
  setTimeout(() => {
    let tries = 0;
    const btn = () => document.getElementById('news-refresh');
    const welcomeHidden = () => {
      const w = document.getElementById('welcome');
      return !w || getComputedStyle(w).display === 'none';
    };
    const offlineTag = () => {
      const h = document.getElementById('news-headbar');
      return !!h && (h.innerText || '').indexOf('离线示例') >= 0;
    };
    const step = () => {
      if (tries >= 8) return;              // 最多约 80s，仍未命中则交由用户手动刷新
      tries += 1;
      const b = btn();
      if (!b || welcomeHidden() || !offlineTag()) return;  // 已进对话 / 已拉到真实资讯 → 停
      b.click();
      setTimeout(step, 9000);              // 留足服务端单轮(≤~4s)+网络余量再试
    };
    step();
  }, 9000);
}"""

# 对话历史列收叠：body.ha-hist-collapsed 隐藏 #left-panel、露出左缘展开把手，状态存 localStorage。
# 用 document 级事件委托绑定 #hist-fold/#hist-open：gradio 切页会卸载/重挂 chat 视图，
# 若在按钮上直接 onclick 绑一次，切走再切回后新节点没有监听器，收叠就失灵了。
_HIST_TOGGLE_JS = r"""() => {
  const KEY = 'ha_hist_open';
  const collapse = () => { document.body.classList.add('ha-hist-collapsed');
    try { localStorage.setItem(KEY, '0'); } catch (e) {} };
  const expand = () => { document.body.classList.remove('ha-hist-collapsed');
    try { localStorage.setItem(KEY, '1'); } catch (e) {} };
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t || !t.id) return;
    if (t.id === 'hist-fold') collapse();
    else if (t.id === 'hist-open') expand();
  });
  // 首屏按记忆恢复收叠态（等到历史列挂载就绪）
  const iv = setInterval(() => {
    if (document.getElementById('hist-fold')) {
      clearInterval(iv);
      try { if (localStorage.getItem(KEY) === '0') collapse(); } catch (e) {}
    }
  }, 250);
}"""

# ============ 模块级常量文案 ============
_HERO_HTML = (
    '<div class="hero-box">'
    '<div class="hero-avatar">🌾</div>'
    '<div class="hero-texts">'
    '<div class="hero-hi">我是小麦AI助手</div>'
    '<div class="hero-role">YOLOv8-Agent · 冬小麦智能监测平台</div>'
    '<div class="hero-greet">如果您有小麦田间监测、长势、干旱或农业知识的问题，欢迎随时向我提问～</div>'
    '</div></div>')

_ABOUT_INNER_HTML = (
    '<div class="panel-card-head"><span class="pc-title">🤝 关于我们</span></div>'
    '<div class="about-body">小麦AI助手专注 <b>冬小麦田间监测</b>：由 '
    '<b>YOLOv8 检测 + 干旱分类 + DeepSeek 大模型 + RAG</b> 驱动，'
    '支持图片长势/干旱分析、农业知识问答、批量检测、数据看板与监测报告生成，'
    '基于 HelloAgents/ha_framework 构建。</div>'
    '<div style="margin:8px 0;">'
    '<span class="about-tag">🖼 看图识别</span><span class="about-tag">🔬 批量检测</span>'
    '<span class="about-tag">💬 知识问答</span><span class="about-tag">📄 报告生成</span></div>'
    '<div class="about-pending">⚠ 病虫害识别模型<b>待训练</b>，即将上线（当前暂不支持病虫害图片识别）</div>'
    '<div class="about-foot">🛰 检测能力现支持：小麦植株检测 · 干旱分类 · 长势解读</div>')

# 询问示例池（发进对话的问题，供「刷新」抽取 3 条）
_SAMPLE_QUESTIONS = [
    "如何提高小麦产量？",
    "常见的小麦病虫害有哪些？如何防治？",
    "小麦干旱胁迫会有什么表现？",
    "批量检测一次最多能传几张图？",
    "数据看板里的趋势是怎么统计的？",
    "如何生成一份小麦监测报告？",
    "看图识别和批量检测有什么区别？",
    "怎么把 PDF 文档灌进知识库？",
]

# 会话列表：沿用 conversation_store.listbox_choices() 的 置顶/最近 分组形式
# （无需额外过滤/收藏，降低与模块级会话管理函数耦合）


# ============ 行业资讯渲染 ============
def _news_items_html(items) -> str:
    if not items:
        return '<div id="news-empty">暂无最新资讯（网络不可用时显示离线示例）</div>'
    parts = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        srcs = " · ".join(x for x in (str(it.get("source", "") or ""),
                                      str(it.get("date", "") or "")) if x)
        inner = ('<span class="news-arrow">›</span>'
                 f'<span class="news-title">{title}</span>'
                 f'<span class="news-src">{srcs}</span>')
        if it.get("url"):
            parts.append(f'<a class="news-item" href="{it["url"]}" '
                         f'target="_blank" rel="noopener noreferrer">{inner}</a>')
        else:
            parts.append(f'<div class="news-item">{inner}</div>')
    return "".join(parts)


def _news_head_html(items) -> str:
    """资讯卡头单行：标题 + （离线时紧跟标题右侧的小号「离线示例」）+ 右上更新时间。"""
    offline = bool(items) and all(it.get("offline") for it in items)
    tag = '<span class="offline-tag">离线示例</span>' if offline else ""
    return (f'<div class="news-headbar"><span class="pc-title">📰 行业资讯</span>{tag}'
            f'<span class="news-upd">更新于 {time.strftime("%H:%M")}</span></div>')


def _fetch_news_live():
    """联网取 5 条资讯（命中新鲜缓存即时返回；联网失败不写缓存，返回离线示例）。

    本机经 Clash 代理到国际源会 ~几十秒级整体翻转（深挖日志确认 urllib 超时、而
    api.deepseek.com 直连正常）。单轮请求可能落在「dead 窗口」拿不到真实条目，
    因此页面加载后由 _NEWS_AUTOFETCH_JS 每 ~9s 自动再点一次「刷新」，直到某一轮
    落在健康窗拉到真数据并写入 30 分钟缓存为止；命中后后续刷新全部即时读缓存。
    """
    return news_mod.fetch_news(limit=5, timeout=4)


def _news_init():
    """首屏资讯：缓存新鲜→毫秒返回；否则联网抓取（单轮，失败降级离线示例）。

    首帧占位仍由 build_ui 里组件初始值（缓存/离线 HTML）提供，本函数联网返回后再
    覆盖，因此既不白屏也不会把联网丢给用户手动点「刷新」。若仍离线，_NEWS_AUTOFETCH_JS
    会在后台隔 9s 自动重试直至拉到真实资讯。
    """
    items = _fetch_news_live()
    return gr.update(value=_news_items_html(items)), gr.update(value=_news_head_html(items))


def _refresh_news():
    """刷新资讯：联网抓取（缓存命中即时；单轮，失败降级离线示例）"""
    items = _fetch_news_live()
    return gr.update(value=_news_items_html(items)), gr.update(value=_news_head_html(items))


# ============ 看板：浅色渲染 ============
def _kpi_light(label, value, sub=""):
    sub_html = (f'<div class="kc-sub">{sub}</div>' if sub else "")
    return ('<div class="kpi-card"><div class="kc-label">{}</div>'
            '<div class="kc-value">{}</div>{}</div>'.format(label, value, sub_html))


def render_kpi_light() -> str:
    s = stats_store.get_stats()
    recs = detection_log.recent(1)
    latest = recs[0].get("time") if recs else s.get("updated_at", "")
    cards = [
        _kpi_light("📸 累计检测图像", s["total_images"], "含小麦与非小麦"),
        _kpi_light("🌾 累计识别小麦", s["total_wheat"], "YOLOv8 检测框"),
        _kpi_light("💧 累计干旱株数", s["total_drought"], "干旱分类命中"),
        _kpi_light("⏱ 最近检测", latest or "—", "最后一条检测时间"),
    ]
    return ('<div style="display:flex;flex-wrap:wrap;gap:12px;padding:4px 0;">'
            + "".join(cards) + "</div>")


def render_recent_empty_light() -> str:
    return ('<div style="color:#8ba07a;padding:18px 14px;text-align:center;'
            'border:1px dashed #cfdfbc;border-radius:12px;">'
            '🛰 暂无检测记录 —— 到「💬 对话」上传田间图片或「🔬 批量检测」跑一批，'
            '这里会展示标注图（点击可放大）。</div>')


def refresh_dash_light():
    gallery = render_recent_gallery()
    return (gr.update(value=render_kpi_light()),
            gr.update(value=detection_log.trend_df()),
            gr.update(value=gallery, visible=bool(gallery)),
            gr.update(value=render_recent_empty_light(), visible=not bool(gallery)))


# ============ 通知 badge / 列表 ============
def _badge_html() -> str:
    n = notifications_store.unread_count()
    if n <= 0:
        return ""
    return ('<div style="margin:6px 2px 2px;font-size:12px;color:#fff;text-align:center;'
            'background:#d94f4f;border-radius:999px;padding:2px 8px;display:inline-block;">'
            f'🔔 {n} 条未读</div>')


# ============ 单图识别页 ============
def single_detect(image_path, conf):
    """看图识别：单张田间图 → 检测 + 干旱分类 + 标注图 + 摘要（累计进看板）"""
    p = _fd_path(image_path)
    if not p or not os.path.exists(p):
        yield (gr.update(value="⚠ 请先上传一张田间图片。"),
               gr.update(value=[]),
               "⚠ 未选择图片", gr.update(), gr.update())
        return
    conf = float(conf or 0.5)
    n_wheat = n_drought = 0
    ann_paths = []
    try:
        stats_store.record(image_count=1)
        w = get_wheat()
        detection = w._detect(p, conf)
        if not detection.get("count", 0):
            detection_log.append(image_count=1, note="看图·非小麦")
            md = "### 🖼 看图识别结果\n\n未检测到小麦植株，按常规图片处理（可在「对话」中上传继续提问）。"
        else:
            results = w.analyze(p, conf)
            det, dr = results.get("detection", {}), results.get("drought", {})
            ann = det.get("annotated_path")
            if ann and os.path.exists(ann):
                ann_paths.append(ann)
            cnt = int(det.get("count", 0) or 0)
            drc = int(dr.get("drought_count", 0) or 0)
            n_wheat, n_drought = cnt, drc
            stats_store.record(wheat_count=cnt, drought_count=drc)
            _log_wheat_detection(w, p, note="看图·小麦")
            rate = float(dr.get("drought_rate", 0) or 0)
            verdict = "💧 存在干旱风险" if dr.get("total_classified") and rate > 0 else "✅ 未见明显干旱"
            md = (f"### 🖼 看图识别结果\n\n"
                  f"- 检测到小麦植株 **{cnt}** 株（置信度均值 {det.get('avg_conf', 0):.2f}）\n"
                  f"- 干旱分类：判定 **{dr.get('verdict', verdict)}**\n"
                  f"- 分类株数 {dr.get('total_classified', cnt)} · 干旱株数 **{drc}** · "
                  f"干旱率 **{rate:.1%}**\n\n"
                  f"> 已累计进「📊 数据看板」。更深入的长势解读可在「💬 对话」上传该图并追问。")
    except Exception as e:  # noqa: BLE001
        md = f"### ❌ 识别失败\n\n{e}"
    notifications_store.add("🖼", "看图识别完成",
                            f"检测小麦 {n_wheat} 株 / 干旱 {n_drought} 株")
    yield (gr.update(value=md),
           gr.update(value=ann_paths),
           f"✅ 识别完成：小麦 {n_wheat} 株 / 干旱 {n_drought} 株",
           gr.update(value=_badge_html()),
           gr.update(value=notifications_store.render_html()))


# ============ 新 build_ui：dock 壳 + 视图切换 ============
def build_ui():
    with gr.Blocks(
        title="YOLOv8-Agent 小麦AI助手",
        theme=gr.themes.Base(),
        css=_SIDEBAR_CSS + _DARK_CSS,
        head=_FORCE_LIGHT_HEAD,
    ) as demo:
        # ============ 左 dock ============
        with gr.Row(elem_id="app-shell", equal_height=False):
            with gr.Column(elem_id="dock", scale=0, min_width=158):
                nav_chat = gr.Button("💬 对话问答", elem_id="nav-chat")
                nav_single = gr.Button("🖼 看图识别", elem_id="nav-single")
                nav_batch = gr.Button("🔬 批量检测", elem_id="nav-batch")
                nav_dash = gr.Button("📊 数据看板", elem_id="nav-dash")
                gr.HTML('<div class="dock-sep"></div>', elem_id="dock-sep")
                nav_set = gr.Button("⚙️ 设置", elem_id="nav-set")
                nav_notif = gr.Button("🔔 通知", elem_id="nav-notif")
                nav_feedback = gr.Button("📮 反馈", elem_id="nav-feedback")
                with gr.Column(elem_id="dock-footer"):
                    notif_badge = gr.HTML(_badge_html(), elem_id="dock-notif")

            # ============ 视图容器 ============
            with gr.Column(elem_id="views", scale=1):
                # ---------- ① 对话问答 ----------
                with gr.Column(elem_id="view-chat", visible=True) as view_chat:
                    with gr.Row(elem_id="chat-row"):
                        # 历史列（可整列收起成左缘细把手）
                        with gr.Column(scale=1, min_width=250, elem_id="left-panel"):
                            gr.HTML(
                                '<div class="hist-head">'
                                '<div id="brand-logo">'
                                '<div class="logo-badge">🌾</div>'
                                '<div><div class="brand-name">小麦AI助手</div>'
                                '<div class="brand-sub">YOLOv8-Agent · 冬小麦监测</div>'
                                '</div></div>'
                                '<button id="hist-fold" type="button" '
                                'title="收起会话历史">‹</button></div>')
                            new_btn = gr.Button("➕ 新建对话", elem_id="new-chat-btn",
                                                variant="primary")
                            history_list = gr.Radio(
                                conversation_store.listbox_choices(),
                                label="📂 会话记录",
                                interactive=True,
                                elem_id="history-list",
                            )
                        # 历史列收起后的展开把手（整列隐藏时留在左缘）
                        gr.HTML('<div id="hist-tab"><button id="hist-open" '
                                'type="button" title="展开会话历史">»</button></div>',
                                elem_id="hist-tab-wrap")
                        # 主区
                        with gr.Column(scale=3, elem_id="chat-main"):
                            chatbot = gr.Chatbot(type="messages", label=None,
                                                 elem_id="chat-area", height=560,
                                                 visible=False)
                            report_file = gr.File(label="📄 报告下载", interactive=False,
                                                  visible=False)
                            with gr.Column(elem_id="welcome", visible=True) as welcome:
                                gr.HTML(_HERO_HTML, elem_id="welcome-hero")
                                # 行业资讯 + 关于我们
                                with gr.Row(elem_id="welcome-cards", equal_height=False):
                                    with gr.Column(scale=11, elem_id="news-card",
                                                   elem_classes=["panel-card"]):
                                        news_head_html = gr.HTML(
                                            _news_head_html(news_mod.cached_or_offline()),
                                            elem_id="news-headbar")
                                        news_list = gr.HTML(
                                            _news_items_html(news_mod.cached_or_offline()),
                                            elem_id="news-list")
                                        news_refresh = gr.Button("↻ 刷新资讯",
                                                                 elem_id="news-refresh",
                                                                 size="sm")
                                    with gr.Column(scale=9, elem_id="about-card",
                                                   elem_classes=["panel-card"]):
                                        gr.HTML(_ABOUT_INNER_HTML)
                                # 询问示例
                                with gr.Column(elem_id="samples-block"):
                                    with gr.Row(elem_id="samples-head"):
                                        with gr.Column(scale=10, elem_id="samples-head-left"):
                                            gr.HTML('<div id="samples-title">你可以这样问我：'
                                                    '</div>')
                                        samples_refresh = gr.Button("↻ 换一批",
                                                                    elem_id="samples-refresh",
                                                                    size="sm")
                                    with gr.Column(elem_id="samples-chips"):
                                        with gr.Row():
                                            sample_q1 = gr.Button(_SAMPLE_QUESTIONS[0],
                                                                  elem_id="sample-q1")
                                            sample_q2 = gr.Button(_SAMPLE_QUESTIONS[1],
                                                                  elem_id="sample-q2")
                                            sample_q3 = gr.Button(_SAMPLE_QUESTIONS[2],
                                                                  elem_id="sample-q3")
                                        with gr.Row():
                                            sample_s1 = gr.Button("试试看图识别",
                                                                  elem_classes=["chip-shortcut"],
                                                                  elem_id="sample-s1")
                                            sample_s2 = gr.Button("打开数据看板",
                                                                  elem_classes=["chip-shortcut"],
                                                                  elem_id="sample-s2")
                                            sample_s3 = gr.Button("去批量检测",
                                                                  elem_classes=["chip-shortcut"],
                                                                  elem_id="sample-s3")
                            # 输入条
                            with gr.Row(elem_id="input-row"):
                                textbox = gr.MultimodalTextbox(
                                    file_types=["image", ".txt", ".md", ".pdf", ".docx",
                                                ".doc", ".csv", ".json"],
                                    file_count="multiple",
                                    placeholder="输入消息，或拖入田间图片分析…",
                                    lines=2,
                                    scale=10,
                                    elem_id="chat-input",
                                )
                                _boost_init_on = bool(Config.RAG_ENABLE_MQE)
                                boost_btn = gr.Button(
                                    value="🔍" if _boost_init_on else "⚡",
                                    scale=0,
                                    elem_id="boost-btn",
                                    variant="primary" if _boost_init_on else "secondary",
                                )
                            chat_status = gr.Markdown("", elem_id="chat-status")

                # ---------- ② 看图识别 ----------
                with gr.Column(elem_id="view-single", visible=False) as view_single:
                    with gr.Column(elem_id="single-panel"):
                        gr.Markdown("### 🖼 看图识别（单张快速检测）\n"
                                    "上传一张田间图片 → 直接 YOLOv8 小麦检测 + 干旱分类，"
                                    "展示标注图与结构化摘要（自动累计进数据看板）。")
                        single_files = gr.Image(type="filepath", label="📤 选择一张田间图片",
                                                image_mode="RGB")
                        single_go = gr.Button("🚀 开始识别", variant="primary",
                                              elem_id="single-go")
                        single_result = gr.Markdown("")
                        single_gallery = gr.Gallery(label="🖼 检测标注图", columns=2,
                                                    height=240, object_fit="cover")
                        single_status = gr.Markdown("", elem_id="single-status")

                # ---------- ③ 批量检测 ----------
                with gr.Column(elem_id="view-batch", visible=False) as view_batch:
                    with gr.Column(elem_id="batch-panel"):
                        gr.Markdown("### 🔬 批量小麦专业检测\n"
                                    "上传多张图片（单批最多 **50 张**），直接 YOLOv8 检测 → "
                                    "仅对含小麦的图片做干旱分类，并累计进数据看板。\n"
                                    "> ⚡ 处理中实时显示进度与预计剩余时间。")
                        batch_files = gr.Files(file_types=["image"], file_count="multiple",
                                               label="📤 选择 / 拖拽多张图片")
                        batch_go = gr.Button("🚀 开始批量检测", variant="primary")
                        batch_result = gr.Markdown("")
                        batch_gallery = gr.Gallery(label="🖼 检测标注图（仅小麦）", columns=4,
                                                   height=240, object_fit="cover")
                        batch_status = gr.Markdown("", elem_id="batch-status")

                # ---------- ④ 数据看板 ----------
                with gr.Column(elem_id="view-dash", visible=False) as view_dash:
                    with gr.Column(elem_id="dash-wrap"):
                        gr.Markdown("### 📊 农业监测数据看板\n"
                                    "实时 KPI + 检测趋势 + 最近检测流（对话 / 看图识别 / "
                                    "批量检测累计）。")
                        dashboard_kpis = gr.HTML(render_kpi_light(), elem_id="dash-kpis")
                        with gr.Row(elem_id="dash-row"):
                            with gr.Column(scale=3, elem_id="dash-trend-col"):
                                gr.Markdown("#### 📈 检测趋势（累计）")
                                trend_chart = gr.LinePlot(
                                    value=detection_log.trend_df(),
                                    x="time", y="count", color="metric",
                                    height=280,
                                    elem_id="dash-trend",
                                )
                            with gr.Column(scale=2, elem_id="dash-recent-col"):
                                gr.Markdown("#### 🕓 最近检测（点击标注图可查看大图）")
                                recent_gallery = gr.Gallery(
                                    value=render_recent_gallery(),
                                    label=None,
                                    columns=2, height=280, object_fit="cover",
                                    preview=True,
                                    elem_id="dash-recent",
                                )
                                recent_empty = gr.HTML(render_recent_empty_light(),
                                                       visible=not bool(render_recent_gallery()))
                        dash_refresh = gr.Button("↻ 刷新看板", variant="secondary",
                                                 elem_id="dash-refresh-btn")

                # ---------- ⑤ 设置 ----------
                with gr.Column(elem_id="view-set", visible=False) as view_set:
                    with gr.Column(elem_id="settings-panel"):
                        gr.Markdown("### ⚙️ 平台设置")
                        conf = gr.Slider(0.1, 1.0, value=0.5, step=0.05,
                                         label="置信度阈值",
                                         info="图片检测与干旱分类的置信度阈值"
                                              "（对话 / 看图 / 批量检测共用）")
                        gr.Markdown("---")
                        gr.Markdown(_SETTINGS_DETAIL)
                        gr.Markdown("---")
                        gr.Markdown("### 📖 使用指南")
                        gr.Markdown(_USAGE_TEXT, elem_id="usage-panel")

                # ---------- ⑥ 通知 ----------
                with gr.Column(elem_id="view-notif", visible=False) as view_notif:
                    with gr.Column(elem_id="notif-panel"):
                        gr.Markdown("### 🔔 本地通知中心\n"
                                    "批量检测 / 看图识别完成等事件会追加到这里。")
                        with gr.Row():
                            notif_mark = gr.Button("✓ 标记已读", variant="secondary")
                            notif_clear = gr.Button("🗑 清空通知", variant="stop")
                        notif_list = gr.HTML(notifications_store.render_html(),
                                             elem_id="notif-list")

                # ---------- ⑦ 反馈 ----------
                with gr.Column(elem_id="view-feedback", visible=False) as view_feedback:
                    with gr.Column(elem_id="feedback-panel"):
                        gr.Markdown("### 📮 意见反馈\n"
                                    "告诉我们遇到的问题或建议（本地保存，无需联网）。")
                        fb_type = gr.Dropdown(["建议", "问题", "报告 Bug", "其它"],
                                              value="建议", label="类型")
                        fb_content = gr.Textbox(lines=4, label="反馈内容",
                                                placeholder="请描述你的建议或遇到的问题…")
                        fb_contact = gr.Textbox(label="联系方式（选填）",
                                                placeholder="邮箱 / 微信 / 手机号，便于回复")
                        fb_submit = gr.Button("提交反馈", variant="primary")
                        fb_result = gr.Markdown("")

        # ============ ⋯ 操作小卡片（fixed 顶层，避免容器裁剪） ============
        more_btn = gr.Button("⋯", visible=False, elem_id="more-btn")
        with gr.Column(visible=False, elem_id="action-card") as action_card:
            pin_btn = gr.Button("📌 置顶 / 取消")
            with gr.Row():
                rename_box = gr.Textbox(placeholder="新标题…", show_label=False, scale=2)
                rename_btn = gr.Button("重命名", scale=1)
            del_btn = gr.Button("🗑 删除会话", variant="stop")

        # ================= 事件 =================
        view_cols = [view_chat, view_single, view_batch, view_dash,
                     view_set, view_notif, view_feedback]

        def _switch(name, hide_more=True):
            ups = [gr.update(visible=(k == name)) for k in
                   ("chat", "single", "batch", "dash", "set", "notif", "feedback")]
            if hide_more:
                ups.extend([gr.update(visible=False), gr.update(visible=False)])
            return ups

        def _open_notif():
            notifications_store.mark_read()
            return (_switch("notif")
                    + [gr.update(value=notifications_store.render_html()),
                       gr.update(value=_badge_html())])

        nav_cfg = [
            (nav_chat, "chat"), (nav_single, "single"), (nav_batch, "batch"),
            (nav_dash, "dash"), (nav_set, "set"), (nav_feedback, "feedback"),
        ]
        for btn, name in nav_cfg:
            btn.click(lambda n=name: _switch(n), None,
                      view_cols + [more_btn, action_card])
        nav_notif.click(_open_notif, None,
                        view_cols + [more_btn, action_card, notif_list, notif_badge])

        # ---- 对话：发送 / 示例提问（欢迎态 → 对话态）----
        _CHAT5 = [chatbot, textbox, report_file, history_list, chat_status]
        _SEND_OUT = [welcome] + _CHAT5

        def _send(history, message, conf):
            for five in respond(history, message, conf):
                c, tb, rep, hl, st = five
                yield [gr.update(visible=False),          # welcome 隐藏
                       gr.update(value=c, visible=True),  # chatbot 显示
                       tb, rep, hl, st]

        textbox.submit(_send, [chatbot, textbox, conf], _SEND_OUT)

        def _ask_q(q, history, conf):
            # 必须是生成器函数（函数体 yield），gradio 才能流式接收；
            # return 一个生成器对象会被当作单值返回 → “needed 6, returned 1” 报错。
            yield from _send(history, {"text": q or "", "files": []}, conf)

        for qc in (sample_q1, sample_q2, sample_q3):
            qc.click(_ask_q, [qc, chatbot, conf], _SEND_OUT)

        # 示例刷新：随机抽 3 条不同问题
        def _sample_refresh():
            import random
            pool = list(_SAMPLE_QUESTIONS)
            random.shuffle(pool)
            three = pool[:3]
            return (gr.update(value=three[0]), gr.update(value=three[1]),
                    gr.update(value=three[2]))

        samples_refresh.click(_sample_refresh, None,
                              [sample_q1, sample_q2, sample_q3])

        # ---- 快捷示例：直接切视图 ----
        shortcut_cfg = [(sample_s1, "single"), (sample_s2, "dash"),
                        (sample_s3, "batch")]
        for btn, name in shortcut_cfg:
            btn.click(lambda n=name: _switch(n), None,
                      view_cols + [more_btn, action_card])

        # ---- 会话管理：复用模块级函数（6 槽）→ 注入 welcome 态（7 槽）----
        _CONV7 = [welcome, chatbot, report_file, history_list,
                  more_btn, action_card, chat_status]

        def _with_welcome(seq6):
            """seq6=[chatbot,report,history,more,action,status] → 7 槽。
            会话有内容 → 对话态（chatbot 显示 / welcome 隐藏）；
            空 / 新建 / 删除后 → 欢迎态（welcome 显示 / chatbot 隐藏）。"""
            c_upd, rep, hl, more, action, st = seq6
            # gradio≥5 的 gr.update(...) 返回 dict，不能 getattr 取 .value → 用 get
            cur = c_upd.get("value") if isinstance(c_upd, dict) else getattr(c_upd, "value", None)
            has = bool(cur)
            if has:
                c_out, w_out = c_upd, gr.update(visible=False)
            else:
                c_out, w_out = gr.update(value=[], visible=False), gr.update(visible=True)
            return [w_out, c_out, rep, hl, more, action, st]

        new_btn.click(lambda h: _with_welcome(new_chat(h)), [chatbot], _CONV7)
        history_list.select(lambda c, h: _with_welcome(select_conv(c, h)),
                            [history_list, chatbot], _CONV7)
        del_btn.click(lambda h: _with_welcome(delete_conv(h)), [chatbot], _CONV7)

        pin_btn.click(pin_conv, None, [history_list, action_card, chat_status])
        rename_btn.click(rename_conv, [rename_box],
                         [history_list, rename_box, action_card, chat_status])
        more_btn.click(toggle_more, None, [action_card])

        # ---- 聊天输入区：RAG 增强开关 ----
        boost_btn.click(toggle_rag_boost, None, [boost_btn])

        # ---- 看图识别 / 批量检测 ----
        _DET5 = [single_result, single_gallery, single_status,
                 notif_badge, notif_list]
        single_go.click(single_detect, [single_files, conf], _DET5)
        batch_go.click(batch_detect, [batch_files, conf],
                       [batch_result, batch_gallery, batch_status,
                        notif_badge, notif_list])

        # ---- 数据看板 ----
        _dash_outs = [dashboard_kpis, trend_chart, recent_gallery, recent_empty]
        dash_refresh.click(refresh_dash_light, None, _dash_outs)

        # ---- 通知视图按钮 ----
        def _notif_mark():
            notifications_store.mark_read()
            return (gr.update(value=notifications_store.render_html()),
                    gr.update(value=_badge_html()))

        def _notif_clear():
            notifications_store.clear()
            return (gr.update(value=notifications_store.render_html()),
                    gr.update(value=_badge_html()))

        notif_mark.click(_notif_mark, None, [notif_list, notif_badge])
        notif_clear.click(_notif_clear, None, [notif_list, notif_badge])

        # ---- 反馈 ----
        fb_submit.click(lambda t, c, ct: _fb_result_update(feedback_store.add(t, c, ct)),
                        [fb_type, fb_content, fb_contact], [fb_result])

        # ---- 行业资讯：点「刷新」才联网；首屏毫秒级出缓存/离线示例 ----
        news_refresh.click(_refresh_news, None, [news_list, news_head_html])

        # ---- 页面初始化 ----
        demo.load(_news_init, None, [news_list, news_head_html])
        demo.load(refresh_dash_light, None, _dash_outs)
        # dock 高亮观察器 + 历史列收叠把手 + ⋯ 菜单弹出定位（加载后注入）
        demo.load(None, js=_UI_BOOT_JS)
        demo.load(None, js=_HIST_TOGGLE_JS)
        demo.load(None, js=_MORE_POSITION_JS)
        # 首屏离线时自动隔 9s 重试拉真实资讯（命中或 welcome 关闭即停）
        demo.load(None, js=_NEWS_AUTOFETCH_JS)
    return demo


def _fb_result_update(res: dict):
    return f"{res.get('msg', '')}（类型：{res['type']}）" if "type" in res else res.get("msg", "")


if __name__ == "__main__":
    demo = build_ui()
    # 默认 7865，避开根目录 app.py（PDF 学习助手）的 7860；可用 HELLO_AGENTS_UI_PORT 覆盖
    port = int(os.getenv("HELLO_AGENTS_UI_PORT", "7865"))
    demo.launch(server_name="127.0.0.1", server_port=port, inbrowser=True)
