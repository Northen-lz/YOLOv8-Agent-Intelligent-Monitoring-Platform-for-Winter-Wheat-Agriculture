# -*- coding: utf-8 -*-
"""
FunctionCallingAgent

实现: Agent + Tool调用（Function Calling 机制，JSON 工具调用格式）
- 默认单次工具调用（向后兼容）；传 max_tool_calls 时升级为多步循环：
  连续调用工具直至模型不再返回 JSON 工具调用或达到上限
"""

import json

from ..core.agent import Agent
from ..core.message import Message


class FunctionCallingAgent(Agent):

    def __init__(self, name, llm, tool_registry, max_tool_calls=None):
        super().__init__(name=name)
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_tool_calls = max_tool_calls

    def get_tools_description(self):
        """获取工具描述"""
        tools = [
            {"name": tool.name, "description": tool.description}
            for tool in self.tool_registry.list_tools()
        ]
        return json.dumps(tools, ensure_ascii=False)

    def _system_prompt(self) -> str:
        return (
            "你是一个支持函数调用的智能Agent。\n"
            f"可用工具:\n{self.get_tools_description()}\n"
            "如果需要工具，请严格返回 JSON：\n"
            '{"name":"工具名称","arguments":{"参数":"值"}}\n'
            "如果不需要工具，直接回答。"
        )

    def run(self, user_input):
        """执行一次对话（带工具调用能力，多轮历史自动累积）"""
        # 1. 保存用户消息
        self.messages.append(Message(role="user", content=user_input))
        system_prompt = self._system_prompt()

        if self.max_tool_calls is None:
            return self._run_single_call(user_input, system_prompt)
        return self._run_multi_call(system_prompt)

    # ---------------- 单次工具调用（原行为） ----------------

    def _run_single_call(self, user_input, system_prompt: str):
        response = self._chat_with_context(system_prompt)
        if response is None:
            return "❌ LLM 返回为空，请重试"

        self.steps = []
        try:
            function_call = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            self.messages.append(Message(role="assistant", content=response))
            return response

        tool_name = function_call.get("name")
        arguments = self._parse_arguments(function_call.get("arguments"))
        if not tool_name:
            self.messages.append(Message(role="assistant", content=response))
            return response

        result = self._execute(tool_name, arguments)
        self.steps.append({"tool": tool_name, "arguments": arguments,
                           "result": result["message"]})
        if result.get("terminal"):
            return result["message"]

        # 工具结果再次交给LLM
        final_prompt = (
            f"用户问题:\n{user_input}\n\n"
            f"工具执行结果:\n{result['message']}\n\n"
            "请根据结果回答用户。"
        )
        final_answer = self.llm.chat([{"role": "user", "content": final_prompt}])
        if final_answer is None:
            final_answer = f"（工具结果如下）\n{result['message']}"
        self.messages.append(Message(role="assistant", content=final_answer))
        return final_answer

    # ---------------- 多步工具调用循环 ----------------

    def _run_multi_call(self, system_prompt: str, on_step=None):
        """多步工具调用循环。

        on_step(step_dict) 可选回调：每次工具执行后触发，step_dict 含
        {tool, arguments, result}，供 UI 流式渲染工具调用步骤。
        """
        messages = [{"role": "system", "content": system_prompt}]
        for m in self.messages:
            if m.content:
                messages.append({"role": m.role, "content": m.content})

        self.steps = []
        for _ in range(self.max_tool_calls):
            response = self.llm.chat(messages)
            if response is None:
                return "❌ LLM 返回为空，请重试"

            try:
                function_call = json.loads(response)
            except (json.JSONDecodeError, TypeError):
                # 非 JSON → 最终回答
                self.messages.append(Message(role="assistant", content=response))
                return response

            tool_name = function_call.get("name")
            arguments = self._parse_arguments(function_call.get("arguments"))
            if not tool_name:
                self.messages.append(Message(role="assistant", content=response))
                return response

            result = self._execute(tool_name, arguments)
            step = {"tool": tool_name, "arguments": arguments,
                    "result": result["message"]}
            self.steps.append(step)
            if on_step is not None:
                try:
                    on_step(step)
                except Exception:
                    pass
            if result.get("terminal"):
                return result["message"]

            # 工具结果回填，继续循环
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"工具执行结果:\n{result['message']}\n\n"
                           "请根据结果回答用户；如还需调用其他工具，继续返回 JSON。",
            })

        # 达到上限 → 让模型收尾
        final = self.llm.chat(messages)
        final = str(final) if final is not None else "（已达最大工具调用次数）"
        self.messages.append(Message(role="assistant", content=final))
        return final

    # ---------------- 工具执行 ----------------

    @staticmethod
    def _parse_arguments(arguments):
        """兼容 arguments 为 dict 或 JSON 字符串"""
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                return json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _execute(self, tool_name: str, arguments: dict) -> dict:
        """执行工具；返回 {message, terminal}。terminal=True 表示无需继续。"""
        tool = self.tool_registry.get(tool_name)
        if tool is None:
            available = [t.name for t in self.tool_registry.list_tools()]
            msg = f"❌ 工具不存在: {tool_name}（可用: {available}）"
            self.messages.append(Message(role="assistant", content=msg))
            return {"message": msg, "terminal": True}

        try:
            result = tool.run(**arguments)
            if not isinstance(result, str):
                try:
                    result = json.dumps(result, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    result = str(result)
            return {"message": str(result), "terminal": False}
        except Exception as e:
            msg = f"❌ 工具 {tool_name} 执行失败: {e}"
            self.messages.append(Message(role="assistant", content=msg))
            return {"message": msg, "terminal": True}

    def _chat_with_context(self, system_prompt):
        """按历史消息构造 chat 消息序列（系统提示 + 全部历史）"""
        messages = [{"role": "system", "content": system_prompt}]
        for m in self.messages:
            if not m.content:
                continue
            messages.append({"role": m.role, "content": m.content})
        return self.llm.chat(messages)
