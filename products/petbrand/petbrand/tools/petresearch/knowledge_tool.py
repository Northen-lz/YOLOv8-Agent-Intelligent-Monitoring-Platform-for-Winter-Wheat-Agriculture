# -*- coding: utf-8 -*-
"""
BrandKnowledgeTool —— 品牌策划领域知识检索工具

读取 petbrand/knowledge/ 下的领域知识文本，基于关键词加权打分做轻量检索
（零外部依赖，离线可用）。内容覆盖：中国养宠市场/人群分层/定位方法论/
品牌资产打法/提案骨架。各模块 Agent 生成前用它取依据，避免纯编造。
"""

import os
import re
from typing import Dict, List

from ...core.config import Config
from ha_framework.tools.base import BaseTool, ToolParameter


class BrandKnowledgeTool(BaseTool):
    """品牌策划知识检索工具（关键词加权检索）"""

    name = "brand_knowledge"
    description = ("检索品牌策划领域知识库（中国养宠市场/人群分层/定位方法论/品牌资产打法/提案骨架）。"
                   "用法: brand_knowledge(query=\"用户问题\")，返回相关知识点，供品牌策划作答前取依据。")

    _STOPWORDS = {
        "什么", "为什么", "如何", "怎么", "请问", "我们", "你们", "需要", "可以",
        "以及", "进行", "一个", "一种", "这个", "那个", "因为", "所以", "但是",
        "而且", "如果", "就是", "用来", "用于", "表示", "根据", "通过", "基于",
        "不是", "不会", "没有", "知道", "说明", "认为", "品牌", "策划", "方案",
    }

    _SYNONYMS = {
        "人群": ["人群", "画像", "用户", "铲屎官", "养宠人", "白领", "家长"],
        "市场": ["市场", "大盘", "行业", "宠物经济", "规模"],
        "猫": ["养猫", "猫奴", "猫咪", "猫经济"],
        "狗": ["养狗", "狗狗", "犬", "狗经济"],
        "竞品": ["竞品", "竞争对手", "品牌梯队", "格局"],
        "渠道": ["渠道", "天猫", "京东", "拼多多", "抖音", "小红书", "私域", "直播"],
        "定位": ["定位", "STP", "价值主张", "卖点", "差异化", "定位语"],
        "人群细分": ["分层", "人群分层", "新手", "进阶", "价格敏感"],
        "成分": ["成分", "配方", "原料", "溯源", "透明", "检测"],
        "情感": ["情感", "陪伴", "家人", "关系", "治愈", "人宠"],
        "故事": ["品牌故事", "创始", "人设", "口吻", "调性"],
        "口号": ["口号", "tagline", "slogan", "品牌名", "命名", "VI"],
        "内容": ["内容", "种草", "KOC", "选题", "内容化"],
        "场景": ["场景", "独居", "陪伴", "多宠", "露营", "节日"],
        "传播": ["传播", "宣传", "战役", "大创意", "总主题", "big idea"],
        "媒介": ["媒介", "投放", "预算", "排期", "达人", "直播", "资源位"],
        "大促": ["大促", "促销", "满减", "折扣", "节点", "蓄水", "爆发", "返场", "GMV"],
        "上市": ["上市", "新品", "首发", "预热", "发布", "首销", "冷启动", "预约", "三阶段"],
    }

    def __init__(self, knowledge_dir: str = None, name: str = None, description: str = None):
        super().__init__(name=name, description=description)
        self.knowledge_dir = knowledge_dir or Config.KNOWLEDGE_DIR
        self._sections: List[Dict[str, str]] = []
        self._load()

    def _load(self):
        """加载 knowledge/ 下所有 .txt，按 '## 标题' 切分为知识点"""
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
            for sec in self._split_sections(fname, text):
                self._sections.append(sec)

    @staticmethod
    def _split_sections(fname: str, text: str) -> List[Dict[str, str]]:
        sections = []
        blocks = re.split(r"^##\s+(.+?)\s*$", text, flags=re.M)
        for i in range(1, len(blocks), 2):
            title = blocks[i].strip()
            body = blocks[i + 1].strip() if i + 1 < len(blocks) else ""
            if body:
                sections.append({"file": fname, "title": title, "body": body})
        return sections

    def search(self, query: str, top_k: int = 3) -> Dict[str, object]:
        """关键词加权检索：标题命中权 2、正文命中权 1"""
        terms = self._extract_terms(query)
        if not terms:
            return {"results": [], "query": query, "reason": "无法提取检索关键词"}
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
        """提取检索词：命中的同义词组 + 去停用词后的双字词"""
        terms = []
        for keyword, variants in self._SYNONYMS.items():
            if keyword in query or any(v in query for v in variants):
                terms.append(keyword)
        _cjk = re.compile(r"[一-鿿]")
        cleaned = re.sub(r"[\s，。？、：；!！？\-（）()\"']", "", query)
        for i in range(len(cleaned) - 1):
            t = cleaned[i:i + 2]
            if t in self._STOPWORDS:
                continue
            if not _cjk.search(t):
                continue
            terms.append(t)
        return list(dict.fromkeys(t for t in terms if len(t) >= 2))

    # ---------------- BaseTool 接口 ----------------

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("query", "string", "要检索的品牌策划问题", required=True),
            ToolParameter("top_k", "integer", "返回知识点数量", required=False, default=3),
        ]

    def run(self, *args, **kwargs) -> str:
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
        if not str(query).strip():
            return "❌ brand_knowledge 检索失败: 查询内容不能为空"

        try:
            result = self.search(str(query).strip(), int(top_k))
        except Exception as e:
            return f"❌ brand_knowledge 检索失败: {e}"

        results = result.get("results", [])
        if not results:
            return "知识库中未找到与问题直接相关的内容，请换个问法。"
        lines = [f"【{results[0]['title']}】"]
        for item in results:
            lines.append(f"- {item['title']}（{item['file']}，相关度 {item['score']}）")
            lines.append(item["content"][:400])
        return "\n".join(lines)

    def fetch(self, query: str, top_k: int = 3) -> str:
        """供 Agent 直接取原文（非 BaseTool 调用路径），返回精简拼接文本"""
        try:
            result = self.search(query, top_k)
        except Exception:
            return ""
        return "\n\n".join(f"[{r['title']}]\n{r['content']}" for r in result.get("results", []))
