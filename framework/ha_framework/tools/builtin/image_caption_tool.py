# -*- coding: utf-8 -*-
"""
ImageCaptionTool —— 本地视觉模型图片描述工具（基于 Ollama + Qwen2.5-VL）

把任意图片（照片/截图/UI/图表/田间图…）交给本机 Ollama 运行的视觉语言模型，
返回自然语言描述，供 LLM 理解图片的语义内容——弥补纯文本模型（DeepSeek）看不到图、
以及 ImageInfoTool 只能拿尺寸/颜色等统计量的局限。

依赖：本机已安装 Ollama 并 `ollama pull qwen2.5vl:3b`。Ollama 服务默认 127.0.0.1:11434，
CPU 推理（本机 MX570 2GB 显存太小，torch 为 cpu 版），每张图约 30~90 秒。

设计：
- 图片经 base64 内嵌进 prompt（qwen2.5vl 原生支持 image_url data URI）
- 通过 urllib 调用 Ollama /api/generate，零新 Python 依赖
- Ollama 未运行 / 模型未拉取 / 请求失败 → 返回友好错误提示，不抛异常
- 可指定 question 自定义提问（默认"详细描述这张图片的内容"）
"""

import base64
import json
import mimetypes
import os
import urllib.request
from typing import List

from ..base import BaseTool, ToolParameter

_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:3b")
_MAX_IMG_BYTES = 6 * 1024 * 1024  # 图片超过 6MB 压缩后再送，控制请求体
_MAX_TOKENS = 512

# 图片 → data URI 的 media type
_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".tif": "image/tiff", ".tiff": "image/tiff",
}


def _encode_image(path: str) -> tuple:
    """读取图片为 base64（Ollama qwen2.5vl 的 images 参数要求**纯 base64**，
    不带 `data:image/...;base64,` 前缀，否则返回 Bad Request）。
    过大时先用 PIL 缩小。返回 (base64_str, mime)。"""
    ext = os.path.splitext(path)[1].lower()
    mime = _MIME.get(ext) or (mimetypes.guess_type(path)[0] or "image/jpeg")
    with open(path, "rb") as f:
        data = f.read()
    if len(data) > _MAX_IMG_BYTES:
        try:
            from PIL import Image
            import io
            im = Image.open(path).convert("RGB")
            im.thumbnail((1024, 1024))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            data = buf.getvalue()
            mime = "image/jpeg"
        except Exception:  # noqa: BLE001  PIL 失败则原样发送
            pass
    return base64.b64encode(data).decode(), mime


class ImageCaptionTool(BaseTool):
    """本地视觉模型（Ollama + Qwen2.5-VL）图片描述工具"""

    name = "image_caption"
    description = (
        "用本地视觉模型（Ollama Qwen2.5-VL）理解任意图片的语义内容并返回自然语言描述，"
        "可描述照片内容、截图/UI 布局、图表、作物长势等。"
        "用法: image_caption(image_path=\"图片路径\") 或 image_caption(image_path=\"路径\", "
        "question=\"你想问图片的什么问题\")。需要本机 Ollama 服务与 qwen2.5vl:3b 模型，"
        "未启动时返回提示。CPU 推理较慢（约 30~90 秒）。"
    )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("image_path", "string", "图片文件路径", required=True),
            ToolParameter("question", "string", "针对图片的自定义问题（可选）",
                          required=False, default=""),
        ]

    # ---------------- 调用 ----------------

    @staticmethod
    def describe(image_path: str, question: str = "") -> dict:
        """核心：把图片送给 Ollama 视觉模型，返回描述结果 dict"""
        p = str(image_path)
        if not os.path.exists(p):
            return {"error": f"图片文件不存在: {p}"}
        img_b64, _ = _encode_image(p)

        prompt = (question or "请详细描述这张图片的内容，包括主体、场景、文字、"
                            "布局等尽可能多的细节。").strip()
        body = {
            "model": _OLLAMA_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"num_predict": _MAX_TOKENS, "temperature": 0.2},
        }
        req = urllib.request.Request(
            _OLLAMA_URL + "/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            return {"error": f"无法连接 Ollama（{_OLLAMA_URL}）：{reason}。"
                             "请先启动 Ollama 服务并拉取模型 `ollama pull qwen2.5vl:3b`。"}
        except (TimeoutError, OSError) as e:
            return {"error": f"Ollama 请求超时/失败：{e}"}
        if out.get("error"):
            return {"error": str(out["error"])}
        text = (out.get("response") or "").strip()
        if not text:
            return {"error": "Ollama 返回了空响应，请检查模型是否可用。"}
        return {"description": text, "model": _OLLAMA_MODEL,
                "path": p, "duration_s": round(float(out.get("total_duration", 0)) / 1e9, 1)}

    # ---------------- 主入口 ----------------

    def run(self, image_path=None, question="", *args, **kwargs) -> str:
        if not image_path and "input" in kwargs:
            image_path = kwargs.get("input")
        if isinstance(args and args[0], dict):
            image_path = image_path or args[0].get("image_path")
            question = question or args[0].get("question") or ""
        elif not image_path and args:
            image_path = args[0]
        if not image_path:
            return json.dumps({"error": "请提供图片路径 image_path"}, ensure_ascii=False)

        result = self.describe(str(image_path), question)
        if result.get("error"):
            return json.dumps({"error": result["error"]}, ensure_ascii=False)
        lines = [f"图片语义描述（{result['model']}，耗时 {result['duration_s']}s）：",
                 result["description"]]
        return "\n".join(lines)
