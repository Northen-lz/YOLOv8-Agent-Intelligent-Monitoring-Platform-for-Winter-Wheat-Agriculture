# -*- coding: utf-8 -*-
"""
AgentTool —— 把 Agent 包装为 BaseTool

多 Agent 协作核心：ManagerAgent 用 AgentTool 把各领域子 Agent 注册进
ToolRegistry，使子 Agent 成为可被 LLM 函数调用调度的一等"工具"。

用法:
    from ha_framework.tools.agent_tool import AgentTool
    registry.register_tool(AgentTool(wheat_vision_agent))
"""

from typing import Any

from .base import BaseTool


class AgentTool(BaseTool):

    def __init__(self, agent, name: str = None, description: str = None):
        self._agent = agent
        desc = description or getattr(agent, "description", None) or (
            f"调用子 Agent「{agent.name}」处理相应任务。输入应能描述该任务。")
        super().__init__(name=name or agent.name, description=desc)

    @property
    def agent(self):
        return self._agent

    def run(self, *args, **kwargs) -> str:
        """透传调用子 Agent 的 run()，返回其文本结果"""
        try:
            if args and kwargs:
                return str(self._agent.run(args[0], **kwargs))
            if kwargs:
                # 归一化常见文本参数名 → 位置参数。多数子 Agent 的 run() 只接受
                # user_input 位置参数（如 ReActAgent.run(user_input)），Manager 的
                # FunctionCallingAgent 常用 {"input"/"query"/"question": ...} 传参，
                # 直接透传会 TypeError。其余 kwargs 仍按命名参数透传。
                text = ""
                for k in ("input", "query", "question", "text", "message",
                          "user_input", "content", "input_text", "prompt"):
                    if kwargs.get(k) is not None:
                        text = kwargs.pop(k)
                        break
                if text:
                    return str(self._agent.run(text, **kwargs))
                return str(self._agent.run(**kwargs))
            if args:
                return str(self._agent.run(args[0]))
            return str(self._agent.run(""))
        except Exception as e:
            return f"❌ 子 Agent「{self._agent.name}」执行失败: {e}"
