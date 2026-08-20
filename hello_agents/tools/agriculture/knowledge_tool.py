# -*- coding: utf-8 -*-
"""
AgricultureKnowledgeTool —— 农业领域知识检索工具

读取 hello_agents/knowledge/ 下的领域知识文本，基于关键词加权打分做
轻量检索（零外部依赖，离线可用）。支持跨文件全库检索。

常用问题示例：
- "为什么冬小麦会发生干旱？"  → 命中 drought_knowledge
- "YOLOv8 为什么适合植物检测？" → 命中 yolo_knowledge
- "如何提高冬小麦产量？"      → 命中 wheat_growth
"""

import os
import re
from typing import Dict, List

from ...core.config import Config
from ..base import BaseTool, ToolParameter


class AgricultureKnowledgeTool(BaseTool):
    """农业知识检索工具（关键词加权检索）"""

    name = "agriculture_knowledge"
    description = ("检索农业领域知识库（冬小麦生长周期/干旱胁迫/YOLOv8 原理/实验信息）。"
                   "用法: agriculture_knowledge(query=\"用户问题\") 或 "
                   "agriculture_knowledge(action=\"search\", query=\"问题\")，返回相关知识点。")

    # 常见功能性双字词（参与打分会产生误命中，检索时剔除）
    _STOPWORDS = {
        "完全", "全无", "无关", "相关", "以及", "进行", "一个", "一种", "这个", "那个",
        "什么", "为什么", "如何", "怎么", "请问", "我们", "你们", "需要", "可以",
        "因为", "所以", "但是", "而且", "如果", "就是", "用来", "用于", "表示",
        "根据", "通过", "基于", "不是", "不会", "没有", "知道", "说明", "认为",
    }

    # 同义词/近义词映射：提高中文检索召回
    _SYNONYMS = {
        "小麦": ["冬小麦", "麦", "麦田"],
        "干旱": ["旱", "水分胁迫", "缺水", "干旱胁迫"],
        "产量": ["丰产", "高产", "千粒重", "穗粒数", "亩穗数"],
        "生育期": ["生长周期", "生育进程", "返青", "拔节", "抽穗", "灌浆", "越冬"],
        "检测": ["目标检测", "识别", "检测框", "bounding box"],
        "置信度": ["置信", "conf", "分数"],
        "特征": ["荧光特征", "荧光参数", "特征向量", "Fv/Fm"],
        "管理": ["防治", "追肥", "灌溉", "水肥"],
        "YOLOv8": ["YOLOv8", "YOLO", "yolov8"],
        "ONNX": ["onnx", "ONNX", "部署"],
        "模型": ["模型", "model"],
        "SVM": ["SVM", "svm"],
        "荧光": ["叶绿素荧光", "荧光"],
        "分类": ["分类", "类别"],
        "病害": ["病虫害", "锈病", "蚜虫", "赤霉病"],
    }

    def __init__(self, knowledge_dir: str = None, name: str = None, description: str = None):
        super().__init__(name=name, description=description)
        self.knowledge_dir = knowledge_dir or Config.KNOWLEDGE_DIR
        self._sections: List[Dict[str, str]] = []
        self._load()

    # ---------------- 加载 ----------------

    def _load(self):
        """加载 knowledge/ 下所有 .txt，按标题切分为知识点"""
        self._sections = []
        if not os.path.isdir(self.knowledge_dir):
            return
        for fname in sorted(os.listdir(self.knowledge_dir)):
            if not fname.endswith(".txt"):
                continue
            path = os.path.join(self.knowledge_dir, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            self._sections.extend(self._split_sections(fname, text))

    @staticmethod
    def _split_sections(fname: str, text: str) -> List[Dict[str, str]]:
        """按 '## 标题' 切分，保留标题与正文"""
        sections = []
        blocks = re.split(r"^##\s+(.+?)\s*$", text, flags=re.M)
        # blocks: [前导, 标题1, 正文1, 标题2, 正文2, ...]
        for i in range(1, len(blocks), 2):
            title = blocks[i].strip()
            body = blocks[i + 1].strip() if i + 1 < len(blocks) else ""
            if body:
                sections.append({"file": fname, "title": title, "body": body})
        return sections

    # ---------------- 检索 ----------------

    def search(self, query: str, top_k: int = 3) -> Dict[str, object]:
        """关键词加权检索，返回 (score, title, body) 排序后的知识点"""
        terms = self._extract_terms(query)
        if not terms:
            return {"results": [], "query": query, "reason": "无法提取检索关键词"}
        # 检索词多时要求更高相关度，避免拉丁双字（ab/bc 等）噪音命中
        min_score = 2 if len(terms) >= 3 else 1
        scored = []
        for sec in self._sections:
            text = sec["title"] + "\n" + sec["body"]
            score = 0
            for t in terms:
                if t in text:
                    score += 2 if t in sec["title"] else 1
            if score >= min_score:
                scored.append((score, sec))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [
            {"score": s, "file": sec["file"], "title": sec["title"], "content": sec["body"]}
            for s, sec in scored[:top_k]
        ]
        return {"results": results, "query": query}

    def _extract_terms(self, query: str) -> List[str]:
        """提取检索词：去停用词后的双字词 + 命中的同义词组"""
        terms = []
        # 同义词组命中原词/词根
        for keyword, variants in self._SYNONYMS.items():
            if keyword in query or any(v in query for v in variants):
                terms.append(keyword)
        # 双字滑动窗口（剔除停用词、纯拉丁/纯数字噪音）
        _cjk = re.compile(r"[一-鿿]")
        cleaned = re.sub(r"[\s，。？、：；!！？\-（）()\"']", "", query)
        for i in range(len(cleaned) - 1):
            t = cleaned[i:i + 2]
            if t in self._STOPWORDS:
                continue
            if not _cjk.search(t):
                continue
            terms.append(t)
        # 去重，保留长度>1 的
        return list(dict.fromkeys(t for t in terms if len(t) >= 2))

    # ---------------- BaseTool 接口 ----------------

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("query", "string", "要检索的农业问题", required=True),
            ToolParameter("top_k", "integer", "返回知识点数量", required=False, default=3),
        ]

    def run(self, *args, **kwargs) -> str:
        """统一入口：兼容 run(input=...) / run("问题") / run({"query": ...})"""
        if not args and "input" in kwargs:
            raw = kwargs.pop("input")
            if isinstance(raw, dict):
                kwargs.update(raw)
            else:
                kwargs["query"] = raw
        elif len(args) >= 1 and not kwargs.get("query"):
            kwargs["query"] = args[0]

        query = kwargs.get("query") or ""
        top_k = kwargs.get("top_k", 3)
        if isinstance(top_k, str):
            try:
                top_k = int(top_k)
            except (TypeError, ValueError):
                top_k = 3

        if not query or not str(query).strip():
            return "❌ agriculture_knowledge 检索失败: 查询内容不能为空"

        try:
            result = self.search(str(query).strip(), top_k)
        except Exception as e:
            return f"❌ agriculture_knowledge 检索失败: {e}"

        results = result.get("results", [])
        if not results:
            return "知识库中未找到与问题直接相关的内容，请换个问法。"
        lines = [f"【{results[0]['title']}】"]
        for item in results:
            lines.append(f"- {item['title']}（{item['file']}，相关度 {item['score']}）")
            lines.append(item["content"][:400])
        return "\n".join(lines)

    def list_topics(self) -> List[str]:
        """列出全部知识点标题"""
        return [f"{s['title']}（{s['file']}）" for s in self._sections]
