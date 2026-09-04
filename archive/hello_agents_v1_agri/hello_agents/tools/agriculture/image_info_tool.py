# -*- coding: utf-8 -*-
"""
ImageInfoTool —— 常规图片信息提取工具

用于"非小麦图片"路径：当识别门控判定图片不含小麦时，提取图片的
基本信息（尺寸/格式/大小/亮度/彩色度/主色调/边缘复杂度），供
Agent 进行常规图片信息说明与正常聊天（不进入小麦分析管线）。

零模型依赖，纯 OpenCV/NumPy 统计。
"""

import json
import os
from typing import Any, Dict, List, Tuple

from ..base import BaseTool, ToolParameter

# 常用颜色 → 中文名（近似匹配主色调）
_PALETTE: List[Tuple[Tuple[int, int, int], str]] = [
    ((255, 255, 255), "白色"), ((0, 0, 0), "黑色"),
    ((255, 0, 0), "红色"), ((0, 128, 0), "绿色"), ((0, 0, 255), "蓝色"),
    ((255, 255, 0), "黄色"), ((255, 165, 0), "橙色"), ((128, 0, 128), "紫色"),
    ((139, 69, 19), "棕色"), ((255, 192, 203), "粉色"), ((128, 128, 128), "灰色"),
    ((0, 255, 255), "青色"),
]


def _nearest_color(rgb: Tuple[int, int, int]) -> str:
    best, best_d = "未知", float("inf")
    for c, name in _PALETTE:
        d = sum((rgb[i] - c[i]) ** 2 for i in range(3))
        if d < best_d:
            best, best_d = name, d
    return best


class ImageInfoTool(BaseTool):
    """常规图片信息提取（尺寸/格式/亮度/色彩/主色调/复杂度）"""

    name = "image_info"
    description = ("提取图片基本信息（尺寸/格式/大小/亮度/彩色度/主色调/复杂度），"
                   "用于不含小麦图片的常规图片信息说明与聊天。用法: image_info(图片路径)")

    def get_parameters(self) -> List[ToolParameter]:
        return [ToolParameter("image_path", "string", "图片文件路径", required=True)]

    # ---------------- 提取 ----------------

    @staticmethod
    def extract(image_path: str) -> Dict[str, Any]:
        import cv2
        import numpy as np

        p = str(image_path)
        info: Dict[str, Any] = {"path": p}
        if not os.path.exists(p):
            info["error"] = f"图片文件不存在: {p}"
            return info
        info["size_kb"] = round(os.path.getsize(p) / 1024.0, 1)
        info["format"] = os.path.splitext(p)[1].lstrip(".").upper() or "未知"

        img = cv2.imread(p)
        if img is None:
            info["error"] = "无法读取图片（可能不是有效图像文件）"
            return info

        h, w = img.shape[:2]
        info["width"] = w
        info["height"] = h
        info["aspect_ratio"] = round(w / h, 3) if h else None

        bgr = img.astype(np.float32)
        b, g, r = bgr[..., 0], bgr[..., 1], bgr[..., 2]
        # 亮度（0-1）
        info["brightness"] = round(float(bgr.mean() / 255.0), 3)
        # 彩色度：通道间差异均值，越大越鲜艳；近 0 为灰度图
        colorfulness = float((abs(r - g) + abs(g - b) + abs(b - r)).mean() / 255.0)
        info["colorfulness"] = round(colorfulness, 3)
        info["is_grayscale"] = bool(colorfulness < 0.05)
        # 边缘复杂度（Canny 边缘占比）：文字/建筑/人造物通常更高
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        info["edge_density"] = round(float(edges.mean() / 255.0), 3)
        # 主色调（简单分桶聚类：取出现频率最高的几个颜色）
        small = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA).reshape(-1, 3)
        quant = (small // 32 * 32 + 16).astype(int)
        colors, counts = np.unique(quant, axis=0, return_counts=True)
        order = np.argsort(-counts)[:3]
        info["dominant_colors"] = [
            {"rgb": colors[i][::-1].tolist(),  # BGR → RGB
             "name": _nearest_color(tuple(colors[i][::-1])),
             "ratio": round(float(counts[i] / len(quant)), 3)}
            for i in order
        ]
        return info

    # ---------------- 主入口 ----------------

    def run(self, image_path=None, *args, **kwargs) -> str:
        if not image_path and "input" in kwargs:
            image_path = kwargs.get("input")
        if isinstance(args and args[0], dict):
            image_path = image_path or args[0].get("image_path")
        elif not image_path and args:
            image_path = args[0]
        if not image_path:
            return json.dumps({"error": "请提供图片路径 image_path"}, ensure_ascii=False)

        info = self.extract(str(image_path))
        return json.dumps(info, ensure_ascii=False, default=str)

    @staticmethod
    def format_text(info: Dict[str, Any]) -> str:
        """把图片信息渲染成可读文本（供 Agent 阅读）"""
        if info.get("error"):
            return f"图片信息: {info['error']}"
        lines = [
            f"路径: {info.get('path', '-')}",
            f"尺寸: {info.get('width', '-')}×{info.get('height', '-')} 像素"
            f"（宽高比 {info.get('aspect_ratio', '-')}）",
            f"格式: {info.get('format', '-')}，大小: {info.get('size_kb', '-')} KB",
            f"亮度: {info.get('brightness', '-')}（0 黑 ~ 1 白）",
        ]
        if info.get("is_grayscale"):
            lines.append("色调: 灰度图")
        else:
            lines.append(f"色彩丰富度: {info.get('colorfulness', '-')}（越高越鲜艳）")
        if info.get("dominant_colors"):
            dom = "、".join(
                f"{c['name']}({c['ratio']})" for c in info["dominant_colors"])
            lines.append(f"主色调: {dom}")
        lines.append(f"边缘复杂度: {info.get('edge_density', '-')}"
                     "（高 → 文字/建筑等人工元素多）")
        return "\n".join(lines)
