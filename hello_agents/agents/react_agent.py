# -*- coding: utf-8 -*-
"""
ReActAgent —— 真正的 Thought / Action / Observation 推理循环

升级自原"仅提示词无循环"的版本：
- 循环解析 LLM 输出中的 `Action: 工具名(参数)`（或 JSON 形态）调用工具
- 工具结果以 Observation 回填，最多 max_steps 步
- 无 Action 或出现 Answer 时返回最终回答

对齐文档：Thought（推理）→ Action（行动/工具调用）→ Observation（观察结果）→ Answer（回答）
"""

import json
import re
from typing import Any, Dict, Optional

from ..core.agent import Agent
from ..core.message import Message

DEFAULT_REACT_PROMPT = """你是一个使用 ReAct 模式推理的智能体。

请严格按以下格式逐步推理：

Thought: 分析当前问题，决定下一步行动
Action: 工具名(参数)     ← 需要调用工具时使用
Observation: 工具返回的结果（无需自己写，由系统提供）
...（可多轮循环）...
Thought: 我已经获得了足够的信息
Answer: 最终回答

要求：
- 需要工具时，Action 写为 `Action: 工具名(参数)` 或 JSON `Action: {"name":"工具名","arguments":{...}}`
- 不需要工具或已得到答案时，直接以 `Answer:` 开头给出最终回答
- 不要编造工具不存在的功能
"""


class ReActAgent(Agent):

    def __init__(
            self,
            name="ReActAgent",
            llm=None,
            system_prompt: Optional[str] = None,
            tool_registry=None,
            max_steps: int = 5,
    ):
        prompt = system_prompt or DEFAULT_REACT_PROMPT
        if tool_registry is not None:
            prompt += "\n\n可用工具:\n" + tool_registry.get_tools_description()
        super().__init__(name=name, system_prompt=prompt, llm=llm,
                         tool_registry=tool_registry)
        self.max_steps = max_steps

    # ---------------- 解析 ----------------

    def _extract_action(self, text: str) -> Optional[Dict[str, Any]]:
        """从 LLM 输出提取 Action；无 Action 返回 None"""
        if not text:
            return None
        # 清理 markdown 符号（** / ` / #），避免干扰 Action 前缀与函数名匹配；
        # 注意保留下划线 _（工具名 weather_get_weather_by_city 含下划线）
        clean = re.sub(r"[`*\#]", "", text)
        decoder = json.JSONDecoder()
        # 兼容多种 Action 前缀写法（Action / Action 调用 / 调用 Action），半角或全角冒号
        # 1) JSON 形态: Action: {"name":"x","arguments":{...}}
        #    用 raw_decode 从冒号后解析完整 JSON，正确处理嵌套花括号
        m = re.search(r"[Aa]ction[^\n:：]{0,14}[:：]\s*(\{)", clean)
        if m:
            try:
                d, _ = decoder.raw_decode(clean[m.start(1):])
                if isinstance(d, dict) and d.get("name"):
                    return {"name": str(d["name"]),
                            "arguments": d.get("arguments") or {}}
            except (json.JSONDecodeError, ValueError):
                pass
        # 2) 函数调用形态: Action: tool_name(arg1, arg2=...)
        m = re.search(
            r"[Aa]ction[^\n:：]{0,14}[:：]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)",
            clean)
        if m:
            return {"name": m.group(1).strip(), "arguments": m.group(2).strip()}
        # 3) 裸 JSON 形态（无 Action 前缀）: {"name":"x","arguments":{...}}
        m = re.search(r'"name"\s*:\s*"', clean)
        if m:
            start = clean.rfind("{", 0, m.start())
            if start >= 0:
                try:
                    d, _ = decoder.raw_decode(clean[start:])
                    if isinstance(d, dict) and d.get("name"):
                        return {"name": str(d["name"]),
                                "arguments": d.get("arguments") or {}}
                except (json.JSONDecodeError, ValueError):
                    pass
        return None

    def _extract_answer(self, text: str) -> Optional[str]:
        """提取 Answer 内容；无则返回 None"""
        m = re.search(r"Answer\s*:\s*(.+)", text, re.S)
        if m:
            return m.group(1).strip()
        return None

    def _execute_action(self, action: Dict[str, Any]) -> str:
        """执行工具，返回 Observation 文本"""
        name = action.get("name")
        args = action.get("arguments") or {}
        if not name:
            return "工具调用缺少 name 字段"
        tool = self.tool_registry.get_tool(name) if self.tool_registry else None
        if tool is None:
            available = self.tool_registry.list_all() if self.tool_registry else []
            return f"❌ 工具不存在: {name}（可用: {available}）"
        try:
            # 兼容 arguments 是 JSON 字符串（如 Action: tool({"a":1}) 解析出字符串）
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    if isinstance(parsed, dict):
                        args = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(args, dict):
                return str(tool.run(**args))
            return str(tool.run(args))
        except Exception as e:
            return f"❌ 工具 {name} 执行失败: {e}"

    # ---------------- 主循环 ----------------

    def run(self, user_input):
        self.add_message(Message(role="user", content=user_input))
        messages = [{"role": "system", "content": self.system_prompt}]
        for m in self.messages:
            if m.content:
                messages.append({"role": m.role, "content": m.content})

        for _ in range(self.max_steps):
            response = self.llm.chat(messages)
            if response is None:
                return "（模型无输出）"
            response = str(response)

            action = self._extract_action(response)
            if action is None:
                # 无 Action → 最终回答
                answer = self._extract_answer(response) or response
                self.add_message(Message(role="assistant", content=answer))
                return answer

            observation = self._execute_action(action)
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"Observation: {observation}\n\n请继续推理。若已有答案，请以 Answer: 开头给出最终回答。",
            })

        # 达到最大步数仍未结束 → 让模型基于现有观察收尾
        final = self.llm.chat(messages)
        final = str(final) if final is not None else "（已达最大推理步数，模型无输出）"
        answer = self._extract_answer(final) or final
        self.add_message(Message(role="assistant", content=answer))
        return answer
