# -*- coding: utf-8 -*-
"""
WheatVisionAgent —— 冬小麦视觉分析 Agent

覆盖"冬小麦视觉分析"与"干旱分析"两个功能点：
- 连接已有 YOLOv8 检测模型（不重新训练），对田间 RGB 图片检测穗头
- 连接已有干旱 ONNX 分类模型，对检测出的植株逐株判断干旱状态
- 将模型输出交给 LLM 转换为自然语言解释

运行模式：代码驱动管线（确定性），LLM 仅负责结果解释。
"""

from ..core.llm import HelloAgentsLLM
from ..tools.agriculture.wheat_detection import WheatDetectionTool
from ..tools.agriculture.drought_prediction import DroughtPredictionTool
from ..tools.agriculture.experiment_tool import ExperimentAnalysisTool
from ..tools.agriculture.image_info_tool import ImageInfoTool
from ..tools.builtin.image_caption_tool import ImageCaptionTool
from ..tools.registry import ToolRegistry
from .function_call_agent import FunctionCallingAgent

# ---------------- 识别门控常量（基于实测样本调优） ----------------
# 灰度图基本不是小麦田（小麦/绿色植被是彩色的）；彩色度低接近单色/灰调
_RULE_GRAYSCALE_NOT_WHEAT = True
_RULE_MIN_COLORFULNESS = 0.2
# 视觉兜底提问：要求模型只回答 是/否
_VISION_GATE_QUESTION = "这张图片中是否有冬小麦植株或麦穗？请只回答 是 或 否。"

WHEAT_SYSTEM_PROMPT = (
    "你是一名冬小麦田间智能监测分析专家。基于系统提供的 YOLOv8 检测与干旱分类结果，"
    "用自然语言向农户解释当前区域冬小麦长势。\n"
    "输出格式参考：\n"
    "检测冬小麦植株数量：{N}株\n"
    "平均置信度：{X}%\n"
    "干旱植株占比：{Y}%\n"
    "检测结果：当前区域冬小麦分布{均匀/较均匀/稀疏/密集}\n"
    "干旱预测结果：{干旱/正常}\n"
    "可能原因：根据知识解释干旱可能成因（如水分胁迫、灌溉不足等）\n"
    "建议：给出 2-3 条可操作管理建议。\n"
    "请基于真实数据作答，不要编造不存在的数字。"
)

# 常规图片聊天提示（识别为非小麦图片时使用）
GENERAL_IMAGE_PROMPT = (
    "你是一个通用图片信息分析助手。用户上传了一张图片，经冬小麦检测模型识别后"
    "判定为【不含小麦】的常规图片。请基于系统提取的图片基本信息（尺寸/格式/亮度/"
    "色彩/主色调/复杂度），客观描述这张图片的特征，并根据用户问题展开聊天。"
    "注意：不要编造图片中实际不可见的具体内容，只依据提供的图片信息作答。"
)


class WheatVisionAgent(FunctionCallingAgent):

    def __init__(self, name="wheat_vision", llm=None, system_prompt=None,
                 detect_model_path=None, drought_model_path=None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm, tool_registry=ToolRegistry())
        self.system_prompt = system_prompt or WHEAT_SYSTEM_PROMPT
        self.detect_tool = WheatDetectionTool(model_path=detect_model_path)
        self.drought_tool = DroughtPredictionTool(model_path=drought_model_path)
        self.image_info_tool = ImageInfoTool()
        # 视觉兜底：仅识别门控「规则不确定」时真正调用，Ollama 不可用自动降级
        self.vision_tool = ImageCaptionTool()
        self.tool_registry.register_tool(self.detect_tool)
        self.tool_registry.register_tool(self.drought_tool)
        self.last_results = {}
        # 同图同阈值缓存：识别门控/管线/Manager 编排共用，避免重复加载推理模型
        self._cache = {}
        self._detect_cache = {}
        # 视觉兜底结果缓存：同一张图在「识别门控 + 完整管线」里只调一次 Ollama
        # （Ollama 每张 30~90s，重复调用是对话/批量「一直加载」的最大元凶）
        self._vision_cache = {}
        # 最近一次小麦分析的检测标注图路径（供 UI 展示；非小麦分析置 None）
        self.annotated_path = None

    def _detect(self, image_path: str, conf: float) -> dict:
        """检测结果缓存（识别门控与完整分析共享）；统一生成标注图"""
        key = (str(image_path), float(conf))
        if key not in self._detect_cache:
            self._detect_cache[key] = self.detect_tool.detect(
                image_path, conf, save_annotated=True)
        return self._detect_cache[key]

    # ---------------- 识别门控：规则先筛 + 视觉兜底 + 检测确认 ----------------

    def _rule_gate(self, image_path: str) -> str:
        """零成本规则先筛：明确非小麦 → "not_wheat"；疑似 → "uncertain"。

        纯 ImageInfoTool（OpenCV/NumPy 统计，零模型），用于快速过滤明显
        非小麦图片（灰度/单色/无色），避免对正常图片跑 YOLOv8 误检出结果。
        """
        try:
            info = self.image_info_tool.extract(image_path)
            if info.get("error"):
                return "uncertain"  # 无法读取 → 交给后续判断
            colors = [c.get("name", "") for c in info.get("dominant_colors", [])]
            has_vegetation = any(n in colors for n in ("绿色", "黄色", "棕色"))
            if _RULE_GRAYSCALE_NOT_WHEAT and info.get("is_grayscale") and not has_vegetation:
                return "not_wheat"
            if not has_vegetation and info.get("colorfulness", 1.0) < _RULE_MIN_COLORFULNESS:
                return "not_wheat"
            return "uncertain"
        except Exception:  # noqa: BLE001 —— 规则判断失败不阻塞，交给后续
            return "uncertain"

    def _vision_gate(self, image_path: str) -> str:
        """视觉兜底：问 Ollama qwen2.5vl「图中是否有小麦」。

        结果按图缓存（识别门控与完整管线共享，一张图只调一次 Ollama）；
        任何失败 → unavailable（容错，不阻塞主流程）。
        """
        path = str(image_path)
        if path in self._vision_cache:
            return self._vision_cache[path]
        result = "unavailable"
        try:
            res = self.vision_tool.describe(image_path, question=_VISION_GATE_QUESTION)
            if not res.get("error"):
                text = str(res.get("description", "")).strip()
                if not text:
                    result = "unavailable"
                elif "否" in text:
                    result = "not_wheat"
                elif "是" in text:
                    result = "wheat"
                else:
                    result = "unavailable"  # 回答不明确 → 降级给检测确认
        except Exception:  # noqa: BLE001
            result = "unavailable"
        self._vision_cache[path] = result
        return result

    def recognize(self, image_path: str, conf: float = 0.5, use_vision: bool = True) -> dict:
        """识别门控（三级）：规则先筛 → [可选]视觉兜底 → 检测确认。

        use_vision=False 跳过视觉兜底（Ollama 每张 30~90s），直接 规则 + YOLO 检测确认，
        供对话 / 批量等时延敏感场景走快速路径——YOLO 检测同样准确且快得多。

        返回 dict：{is_wheat, count, reason, detection?}
        reason 记录判定来源（rule/vision/detect），供 UI 渲染说明。
        """
        path = str(image_path)
        conf = float(conf)

        # 1) 规则先筛：明确非小麦 → 直接跳过检测（修复：正常图片不再出检测结果）
        rule = self._rule_gate(path)
        if rule == "not_wheat":
            return {"is_wheat": False, "count": 0, "reason": "rule"}

        # 2) 规则不确定 → 视觉兜底（仅 use_vision 且 Ollama 可用时）
        if rule == "uncertain" and use_vision:
            vision = self._vision_gate(path)
            if vision == "not_wheat":
                return {"is_wheat": False, "count": 0, "reason": "vision"}
            if vision == "wheat":
                detection = self._detect(path, conf)
                return {"is_wheat": True, "count": detection.get("count", 0),
                        "detection": detection, "reason": "vision"}
            # unavailable → 落到 3）检测确认

        # 3) 规则疑似小麦（或视觉不可用 / 快速路径跳过视觉） → YOLOv8 检测确认
        detection = self._detect(path, conf)
        count = detection.get("count", 0)
        return {"is_wheat": count > 0, "count": count, "detection": detection,
                "reason": "detect"}

    def analyze(self, image_path: str, conf: float = 0.5) -> dict:
        """执行检测 + 干旱分类，返回结构化结果（同图同阈值命中缓存）"""
        key = (str(image_path), float(conf))
        if key in self._cache:
            results = self._cache[key]
            self.last_results = results
            return results
        detection = self._detect(image_path, conf)
        boxes = detection.get("boxes", [])
        drought = self.drought_tool.predict(image_path, boxes=boxes)
        stats = ExperimentAnalysisTool.stats({
            **detection,
            "drought_count": drought.get("drought_count", 0),
            "control_count": drought.get("control_count", 0),
        })
        results = {"detection": detection, "drought": drought, "stats": stats}
        self._cache[key] = results
        self.last_results = results
        return results

    @staticmethod
    def _format_results(results: dict) -> str:
        det, dr, st = results["detection"], results["drought"], results["stats"]
        lines = [
            f"图片路径: {det.get('image_path', '')}",
            f"检测模型: {det.get('model_path', '-')}",
            f"图像尺寸: {det.get('image_width', '-')}×{det.get('image_height', '-')} 像素",
            f"检测株数: {det.get('count', 0)}",
            f"平均置信度: {det.get('avg_conf', 0):.4f}",
            f"类别分布: {det.get('class_counts', {})}",
            f"分类株数: {dr.get('total_classified', 0)}",
            f"干旱株数: {dr.get('drought_count', 0)}",
            f"正常株数: {dr.get('control_count', 0)}",
            f"干旱率: {dr.get('drought_rate', 0):.4f}",
        ]
        if "density_per_10k_px" in st:
            lines.append(f"植株密度: {st['density_per_10k_px']} 株/万像素")
        if "uniformity" in st:
            lines.append(f"空间均匀度: {st['uniformity']}")
        if "coverage" in st:
            lines.append(f"覆盖率: {st['coverage']}")
        return "\n".join(lines)

    def run(self, image_path=None, conf=0.5, use_vision=True, *args, **kwargs):
        """识别门控 + 分析：
        - 识别为小麦 → 完整小麦智能分析（检测+干旱+LLM 解释）
        - 未识别为小麦 → 常规图片信息分析 + 正常聊天
        use_vision=False 走快速路径（跳过 Ollama 视觉兜底，直接 YOLO 判定）。
        """
        # 兼容 run(input="path") / run("path")
        if not image_path and "input" in kwargs:
            image_path = kwargs.get("input")
        if not image_path and args:
            image_path = args[0]
        if not image_path:
            return "❌ 请提供要分析的图片路径 image_path"
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5

        try:
            gate = self.recognize(str(image_path), conf, use_vision=use_vision)
        except Exception as e:
            return f"❌ 图片识别失败: {e}"

        # 非小麦图片 → 常规图片信息分析 + 聊天
        if not gate["is_wheat"]:
            return self._analyze_general(str(image_path), conf, gate)

        try:
            results = self.analyze(str(image_path), conf)
        except Exception as e:
            return f"❌ 视觉分析失败: {e}"

        self.annotated_path = results["detection"].get("annotated_path")
        data_text = self._format_results(results)
        prompt = (
            f"请基于以下 YOLOv8 检测与干旱分类结果，给出自然语言分析：\n\n{data_text}"
        )
        answer = self.llm.chat([{"role": "system", "content": self.system_prompt},
                                {"role": "user", "content": prompt}])
        return str(answer) if answer is not None else (
            f"（视觉分析结果如下）\n{data_text}")

    def _analyze_general(self, image_path: str, conf: float, gate: dict) -> str:
        """非小麦图片：提取图片信息 + 常规聊天"""
        self.annotated_path = None
        try:
            info = self.image_info_tool.extract(image_path)
        except Exception as e:  # noqa: BLE001
            return f"（未检测到小麦植株，常规图片信息提取失败: {e}）"
        info_text = ImageInfoTool.format_text(info)
        reason = gate.get("reason", "detect")
        if reason == "rule":
            judge = "图片色彩特征判定为不含小麦（非田间绿色/黄色场景）"
        elif reason == "vision":
            judge = "视觉模型判定图片中不含小麦植株或麦穗"
        else:
            judge = f"检测到 {gate.get('count', 0)} 株小麦穗头"
        prompt = (
            f"识别结果: 未检测到小麦植株（{judge}）。\n\n"
            f"图片信息:\n{info_text}\n\n"
            f"请对这张常规图片进行信息说明，并与用户正常聊天。"
        )
        try:
            answer = self.llm.chat([{"role": "system", "content": GENERAL_IMAGE_PROMPT},
                                    {"role": "user", "content": prompt}])
            if answer:
                return f"（未检测到小麦，按常规图片分析）\n{answer}"
        except Exception:
            pass
        return f"（未检测到小麦，以下为常规图片信息）\n{info_text}"
