# -*- coding: utf-8 -*-
"""
DroughtPredictionTool —— 冬小麦干旱状态分类工具（ONNX）

自包含调用外部系统的干旱 ONNX 分类模型，支持两种输入：
1. (image_path, boxes)：对检测出的每株小麦 crop 逐株分类（crop→灰度→32x32→3ch→NCHW）
2. feature_vector=[32维]：直接对荧光特征向量分类（reshape (4,8) → 上采样 32x32 → 3ch）
输出: {drought_count, control_count, drought_rate, per_crop: [{label, confidence}]}
"""

import os
from typing import Any, Dict, List

from ...core.config import Config
from ha_framework.tools.base import BaseTool, ToolParameter


class DroughtPredictionTool(BaseTool):
    """冬小麦干旱分类工具（ONNX）"""

    name = "drought_prediction"
    description = ("对冬小麦图像或荧光特征执行干旱状态分类（control 正常 / drought 干旱）。"
                   "用法: drought_prediction(image_path=\"图片\", boxes=[[x1,y1,x2,y2],...]) "
                   "或 drought_prediction(feature_vector=[32个数值])")

    def __init__(self, model_path: str = None, name: str = None, description: str = None):
        super().__init__(name=name, description=description)
        self.model_path = model_path or Config.DROUGHT_CLS_MODEL
        self._session = None
        self._input_name = None

    # ---------------- 模型加载 ----------------

    def _load_model(self):
        if self._session is not None:
            return self._session
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"干旱分类模型不存在: {self.model_path}\n"
                "请检查 Config.DROUGHT_CLS_MODEL 或设置环境变量 DROUGHT_CLS_MODEL")
        import onnxruntime as ort
        self._session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name
        return self._session

    # ---------------- 预处理（复刻外部系统 preprocess_crop） ----------------

    @staticmethod
    def _preprocess_crop(crop_bgr) -> Any:
        """BGR crop → [1,3,32,32] NCHW float32（灰度三通道复制）"""
        import cv2
        import numpy as np
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (32, 32))
        arr = gray.astype(np.float32) / 255.0
        arr = np.stack([arr] * 3, axis=-1)   # [32,32,3]
        arr = np.expand_dims(arr, axis=0)     # [1,32,32,3]
        return np.transpose(arr, (0, 3, 1, 2))  # [1,3,32,32]

    @staticmethod
    def _feature_to_image(features: List[float]) -> Any:
        """32 维荧光特征 → (4,8) → 上采样 32x32 → 3ch NCHW"""
        import numpy as np
        import skimage.transform
        arr = np.asarray(features, dtype=np.float32)
        if arr.size != 32:
            raise ValueError(f"荧光特征应为 32 维, 实际 {arr.size}")
        feat = arr.reshape(4, 8)
        up = skimage.transform.resize(feat, (32, 32), mode="reflect", preserve_range=True)
        up = up.astype(np.float32)
        # 归一化到 [0,1]（按外部系统图像化流程）
        lo, hi = up.min(), up.max()
        up = (up - lo) / (hi - lo) if hi > lo else up * 0.0
        up = np.stack([up] * 3, axis=-1)
        up = np.expand_dims(up, axis=0)
        return np.transpose(up, (0, 3, 1, 2))

    @staticmethod
    def _safe_softmax(logits):
        import numpy as np
        logits = logits - np.max(logits)
        exp = np.exp(logits)
        return exp / np.sum(exp)

    # ---------------- 推理 ----------------

    def classify_crop(self, crop_bgr) -> Dict[str, Any]:
        """单株 crop 分类，返回 {label, confidence, probs}"""
        session = self._load_model()
        tensor = self._preprocess_crop(crop_bgr)
        raw = session.run(None, {self._input_name: tensor})[0][0]
        probs = self._safe_softmax(raw)
        label = "drought" if probs[1] > probs[0] else "control"
        return {"label": label, "confidence": round(float(probs[1] if label == "drought" else probs[0]), 4)}

    def predict(self, image_path: str = None, boxes: List[list] = None,
                feature_vector: List[float] = None) -> Dict[str, Any]:
        """对图片的检测框逐株分类，或对荧光特征向量分类"""
        import cv2

        if feature_vector is not None:
            session = self._load_model()
            tensor = self._feature_to_image(list(feature_vector))
            raw = session.run(None, {self._input_name: tensor})[0][0]
            probs = self._safe_softmax(raw)
            label = "drought" if probs[1] > probs[0] else "control"
            return {
                "label": label,
                "confidence": round(float(probs[1] if label == "drought" else probs[0]), 4),
                "per_crop": [],
                "drought_count": 1 if label == "drought" else 0,
                "control_count": 1 if label == "control" else 0,
                "drought_rate": round(1.0 if label == "drought" else 0.0, 4),
                "total_classified": 1,
                "model_path": self.model_path,
            }

        if not image_path:
            raise ValueError("请提供 image_path 或 feature_vector")
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")

        boxes = boxes or []
        per_crop = []
        for i, b in enumerate(boxes):
            x1, y1, x2, y2 = [int(v) for v in b[:4]]
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            res = self.classify_crop(crop)
            per_crop.append({"box": [x1, y1, x2, y2], **res})

        drought = sum(1 for r in per_crop if r["label"] == "drought")
        total = len(per_crop)
        return {
            "per_crop": per_crop,
            "drought_count": drought,
            "control_count": total - drought,
            "drought_rate": round(drought / total, 4) if total else 0.0,
            "total_classified": total,
            "model_path": self.model_path,
        }

    # ---------------- BaseTool 接口 ----------------

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("image_path", "string", "田间图片路径", required=False),
            ToolParameter("boxes", "string", "检测框列表 [[x1,y1,x2,y2],...]", required=False),
            ToolParameter("feature_vector", "string", "32 维荧光特征向量", required=False),
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
            elif not kwargs.get("image_path") and not kwargs.get("feature_vector"):
                kwargs["image_path"] = args[0]

        import json
        image_path = kwargs.get("image_path") or ""
        boxes = kwargs.get("boxes")
        if isinstance(boxes, str):
            try:
                boxes = json.loads(boxes)
            except (json.JSONDecodeError, TypeError):
                boxes = None
        feature_vector = kwargs.get("feature_vector")
        if isinstance(feature_vector, str):
            try:
                feature_vector = json.loads(feature_vector)
            except (json.JSONDecodeError, TypeError):
                feature_vector = None

        if not image_path and feature_vector is None:
            return "❌ drought_prediction 失败: 请提供 image_path(和boxes) 或 feature_vector"
        try:
            result = self.predict(image_path=str(image_path) if image_path else None,
                                  boxes=boxes, feature_vector=feature_vector)
        except Exception as e:
            return f"❌ drought_prediction 分类失败: {e}"
        return (
            f"干旱预测结果: 共分类 {result['total_classified']} 株, "
            f"其中干旱 {result['drought_count']} 株, 正常 {result['control_count']} 株, "
            f"干旱率 {result['drought_rate']}。"
        )
