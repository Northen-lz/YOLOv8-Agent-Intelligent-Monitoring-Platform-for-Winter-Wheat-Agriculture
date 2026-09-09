# -*- coding:utf-8 -*-
"""
Agent基类
- 支持外部传入 llm 实例与 tool_registry
- 维护对话历史 self._history / self.messages
- 提供 add_message / get_history / clear_history
"""

from typing import List, Optional

from .llm import HelloAgentsLLM
from .message import Message


class Agent:

    def __init__(
            self,
            name,
            system_prompt="你是一个智能助手",
            llm: Optional[HelloAgentsLLM] = None,
            tool_registry=None,
    ):
        self.name = name
        self.system_prompt = system_prompt

        # 使用外部传入的 LLM 实例，否则自动创建
        self.llm = llm if llm is not None else HelloAgentsLLM()

        # 工具注册中心（可选）
        self.tool_registry = tool_registry

        # 对话历史（兼容旧属性 self.messages）
        self.messages: List[Message] = []
        self._history: List[Message] = self.messages

    def add_message(self, message: Message):
        """添加一条消息到历史"""
        self.messages.append(message)

    def get_history(self) -> List[Message]:
        """获取完整对话历史"""
        return self.messages

    def clear_history(self):
        """清空对话历史"""
        self.messages = []
        self._history = self.messages

    def run(self, user_input):
        message = Message(role="user", content=user_input)
        self.add_message(message)

        response = self.llm.chat(
            [
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": user_input,
                },
            ]
        )

        self.add_message(Message(role="assistant", content=response))
        return response
