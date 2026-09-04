# -*- coding: utf-8 -*-
"""
Hello-Agents A2A 协议实现（Agent-to-Agent Protocol）
对齐文档第十章 10.3

文档说明：A2A 现有实现大部分为 Sample Code，且 Python 实现较为繁琐，
因此这里采用「模拟协议思想」的轻量自实现：
- A2AServer 基于 stdlib http.server 暴露 HTTP 端点
- A2AClient 基于 urllib 调用远程智能体技能
- 若已安装官方 a2a-sdk，则 A2A_AVAILABLE 为 True（本项目未安装）

核心概念（表 10.7）：
- Task / Artifact 抽象 → 简化为 skill 技能调用
- 点对点通信 → HTTP JSON 传输
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

# 官方 a2a-sdk 是否可用（本项目未安装，走自实现模拟路径）
try:
    import a2a  # noqa: F401
    A2A_AVAILABLE = True
except Exception:
    A2A_AVAILABLE = False


class A2AServer:
    """A2A 智能体服务器 - 提供技能调用与点对点协作能力"""

    def __init__(
            self,
            name: str,
            description: str = "",
            version: str = "1.0.0",
            capabilities: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.description = description
        self.version = version
        self.capabilities = capabilities or {}
        # 技能注册表：skill 名 -> callable(text) -> str
        self.skills: Dict[str, Callable[[str], str]] = {}
        self._httpd: Optional[ThreadingHTTPServer] = None

    # ---------------- 技能注册 ----------------

    def skill(self, name: str):
        """
        注册技能（装饰器）。

        文档用法：
            @calculator.skill("add")
            def add_numbers(query: str) -> str:
                ...
        """
        def decorator(fn: Callable[[str], str]) -> Callable[[str], str]:
            self.skills[name] = fn
            return fn
        return decorator

    # ---------------- 技能路由 ----------------

    # 常见技能的中文/英文别名（提升自然语言路由鲁棒性，对齐文档"按文本自动匹配技能"）
    _SKILL_ALIASES = {
        "add": ["加", "+", "加法", "sum"],
        "subtract": ["减", "-", "减法", "minus"],
        "multiply": ["乘", "*", "乘法", "乘以", "times"],
        "divide": ["除", "/", "除法", "除以", "divide"],
        "research": ["研究", "调研", "搜索", "research"],
        "analyze": ["分析", "评估", "评价", "剖析", "analyze"],
        "search": ["搜索", "查询", "查找", "search"],
        "summarize": ["总结", "摘要", "归纳", "summarize"],
        "translate": ["翻译", "translate"],
        "write": ["写", "写作", "撰写", "起草", "write"],
    }

    def _route(self, text: str) -> str:
        """
        根据文本自动匹配技能（供 A2ATool / A2AClient.execute 使用）。
        匹配规则：
        1. 技能名作为关键词出现在文本中（如 "research AI..." 含 research）
        2. 文本以技能名开头
        3. 常见算术符号/中文别名（如 "+"→add、"/"→divide）
        4. 都匹配不上时兜底使用第一个技能
        """
        if not text:
            return ""
        text_lower = text.lower()
        # 1/2. 技能名关键词
        for skill_name in self.skills:
            if text_lower.startswith(skill_name.lower()) or skill_name.lower() in text_lower:
                return skill_name
        # 3. 算术符号/别名启发式
        for skill_name, keywords in self._SKILL_ALIASES.items():
            if skill_name in self.skills and any(k in text_lower for k in keywords):
                return skill_name
        # 4. 兜底：第一个技能
        if self.skills:
            return next(iter(self.skills))
        return ""

    def execute(self, text: str) -> Dict[str, Any]:
        """自动路由执行（文档 10.3.3 客户端 execute）"""
        skill_name = self._route(text)
        return self.execute_skill(skill_name, text)

    def execute_skill(self, skill_name: str, text: str) -> Dict[str, Any]:
        """显式指定技能执行"""
        if skill_name not in self.skills:
            return {"result": f"❌ 技能 '{skill_name}' 不存在，可用: {list(self.skills.keys())}"}
        try:
            result = self.skills[skill_name](text)
        except Exception as e:
            return {"result": f"❌ 技能执行失败: {e}"}
        return {"result": result}

    # ---------------- Agent Card ----------------

    def get_agent_card(self) -> Dict[str, Any]:
        """获取智能体描述卡片（对齐 A2A agent card）"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "skills": list(self.skills.keys()),
        }

    # ---------------- HTTP 服务 ----------------

    def run(self, host: str = "localhost", port: int = 5000):
        """
        启动 A2A HTTP 服务器（阻塞）。

        文档用法：
            researcher.run(host="localhost", port=5000)
        """
        server = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                # 精简日志，避免刷屏
                pass

            def _send_json(self, obj: Dict[str, Any], status: int = 200):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_body(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", 0))
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                try:
                    return json.loads(raw.decode("utf-8"))
                except Exception:
                    return {}

            def do_GET(self):
                if self.path == "/" or self.path == "/agent-card":
                    self._send_json(server.get_agent_card())
                elif self.path == "/skills":
                    self._send_json({"skills": list(server.skills.keys())})
                else:
                    self._send_json({"error": f"未知路径: {self.path}"}, status=404)

            def do_POST(self):
                data = self._read_body()
                if self.path == "/execute_skill":
                    skill = data.get("skill", "")
                    text = data.get("text", "")
                    self._send_json(server.execute_skill(skill, text))
                elif self.path == "/execute":
                    text = data.get("text", "")
                    self._send_json(server.execute(text))
                else:
                    self._send_json({"error": f"未知路径: {self.path}"}, status=404)

        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        print(f"✅ A2A 智能体 '{self.name}' 已启动: http://{host}:{port}")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            self._httpd.server_close()

    def shutdown(self):
        """关闭服务器"""
        if self._httpd is not None:
            threading.Thread(target=self._httpd.shutdown, daemon=True).start()
            self._httpd.server_close()
            self._httpd = None


class A2AClient:
    """A2A 智能体客户端 - 调用远程智能体的技能"""

    def __init__(self, base_url: str):
        """
        Args:
            base_url: A2A 服务器地址，如 "http://localhost:5000"
        """
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str) -> Dict[str, Any]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---------------- 技能调用 ----------------

    def execute_skill(self, skill: str, text: str) -> Dict[str, Any]:
        """
        显式调用远程智能体的技能。

        文档用法：
            response = client.execute_skill("research", "research AI在医疗领域的应用")
            response.get('result')
        """
        return self._post("/execute_skill", {"skill": skill, "text": text})

    def execute(self, text: str) -> Dict[str, Any]:
        """自动路由调用（A2ATool 使用）"""
        return self._post("/execute", {"text": text})

    def list_skills(self) -> List[str]:
        """列出远程智能体可用技能"""
        try:
            return self._get("/skills").get("skills", [])
        except Exception:
            return []

    def get_agent_card(self) -> Dict[str, Any]:
        """获取远程智能体描述卡片"""
        return self._get("/")

    def __repr__(self):
        return f"A2AClient({self.base_url!r})"
