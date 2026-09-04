# -*- coding: utf-8 -*-
"""
WheatDetectionTool —— 冬小麦 YOLOv8 目标检测工具

直接加载外部视觉系统（vscode-xiaomai）的 YOLOv8 权重，自包含完成推理，
不修改、不 import 外部系统的任何脚本。
- 模型：Config.WHEAT_DETECT_MODEL（默认 yolov8s/best.pt，单类 wheat_head）
- 返回：{count, avg_conf, boxes, confidences, class_counts, image_width, image_height, time_ms}
"""

import os
import time
from typing import Any, Dict, List

from ...core.config import Config
from ha_framework.tools.base import BaseTool, ToolParameter


class WheatDetectionTool(BaseTool):
    """YOLOv8 冬小麦穗头检测工具"""

    name = "wheat_detection"
    description = ("对田间 RGB 图像执行 YOLOv8 冬小麦穗头检测，返回检测框、株数、置信度。"
                   "用法: wheat_detection(image_path=\"图片路径\", conf=0.5)")

    def __init__(self, model_path: str = None, name: str = None, description: str = None):
        super().__init__(name=name, description=description)
        self.model_path = model_path or Config.WHEAT_DETECT_MODEL
        self._model = None  # 懒加载

    # ---------------- 模型加载 ----------------

    def _load_model(self):
        """懒加载 ultralytics YOLO（首次调用时）"""
        if self._model is not None:
            return self._model
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"检测模型不存在: {self.model_path}\n"
                "请检查 Config.WHEAT_DETECT_MODEL 或设置环境变量 WHEAT_DETECT_MODEL")
        # torch>=2.6 默认 weights_only=True，旧格式 .pt（含自定义类）需放行
        import torch
        if getattr(torch, "_ha_wheat_patched", False) is False:
            _orig = torch.load
            def _load(*args, **kwargs):
                kwargs.setdefault("weights_only", False)
                return _orig(*args, **kwargs)
            torch.load = _load
            torch._ha_wheat_patched = True
        from ultralytics import YOLO
        self._model = YOLO(self.model_path)
        return self._model

    # ---------------- 推理 ----------------

    def detect(self, image_path: str, conf: float = 0.5,
               save_annotated: bool = False) -> Dict[str, Any]:
        """执行检测，返回结构化结果。

        save_annotated=True 时用 results.plot() 生成画框标注图（BGR），保存到
        Config.DETECTION_ANNOTATE_DIR，文件名确定性 <basename>_annotated_c{conf:.2f}.jpg
        （同图同阈值覆盖，与 detect 缓存语义一致）；结果 dict 增加 annotated_path。
        """
        import cv2
        t0 = time.time()
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")
        h, w = img.shape[:2]

        model = self._load_model()
        results = model(img, conf=conf, verbose=False)

        annotated_path = None
        if save_annotated:
            try:
                annotated = results[0].plot()  # BGR ndarray，含检测框
                annotate_dir = Config.DETECTION_ANNOTATE_DIR
                os.makedirs(annotate_dir, exist_ok=True)
                base = os.path.splitext(os.path.basename(image_path))[0]
                annotated_path = os.path.join(
                    annotate_dir, f"{base}_annotated_c{float(conf):.2f}.jpg")
                cv2.imwrite(annotated_path, annotated)
            except Exception:  # noqa: BLE001 —— 标注图失败不影响检测结果
                annotated_path = None

        boxes, confidences, class_ids = [], [], []
        class_counts: Dict[str, int] = {}
        names = getattr(model, "names", {})
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int).tolist()
                c = float(box.conf.item())
                cls_id = int(box.cls.item()) if box.cls is not None else 0
                boxes.append([x1, y1, x2, y2])
                confidences.append(round(c, 4))
                class_ids.append(cls_id)
                cls_name = names.get(cls_id, str(cls_id))
                class_counts[cls_name] = class_counts.get(cls_name, 0) + 1

        return {
            "count": len(boxes),
            "avg_conf": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "boxes": boxes,
            "confidences": confidences,
            "class_ids": class_ids,
            "class_counts": class_counts,
            "image_width": w,
            "image_height": h,
            "image_path": image_path,
            "model_path": self.model_path,
            "annotated_path": annotated_path,
            "time_ms": round((time.time() - t0) * 1000, 1),
        }

    # ---------------- BaseTool 接口 ----------------

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("image_path", "string", "田间 RGB 图片路径", required=True),
            ToolParameter("conf", "number", "置信度阈值", required=False, default=0.5),
        ]

    def run(self, *args, **kwargs) -> str:
        if not args and "input" in kwargs:
            raw = kwargs.pop("input")
            if isinstance(raw, dict):
                kwargs.update(raw)
            else:
                kwargs["image_path"] = raw
        elif len(args) >= 1:
            if isinstance(args[0], dict):
                kwargs.update(args[0])
            elif not kwargs.get("image_path"):
                kwargs["image_path"] = args[0]

        image_path = kwargs.get("image_path") or ""
        conf = kwargs.get("conf", 0.5)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5

        if not image_path:
            return "❌ wheat_detection 检测失败: 请提供 image_path 图片路径"
        try:
            result = self.detect(str(image_path), conf)
        except Exception as e:
            return f"❌ wheat_detection 检测失败: {e}"
        return (
            f"小麦检测结果: 共 {result['count']} 株, 平均置信度 {result['avg_conf']}, "
            f"耗时 {result['time_ms']}ms。类别分布: {result['class_counts']}"
        )
