# -*- coding:utf-8 -*-
"""
SimpleAgent实现（对齐文档第七章 7.4.1）

支持：
- 基础对话
- 可选工具调用（[TOOL_CALL:tool_name:parameters] 格式）
- 动态工具管理（add_tool / remove_tool / list_tools）
"""

import json
import re
from typing import List, Optional

from ..core.agent import Agent
from ..core.llm import HelloAgentsLLM
from ..core.message import Message


class SimpleAgent(Agent):

    def __init__(
            self,
            name: str = "SimpleAgent",
            llm: Optional[HelloAgentsLLM] = None,
            system_prompt: Optional[str] = None,
            tool_registry=None,
            enable_tool_calling: bool = True,
    ):
        super().__init__(
            name=name,
            system_prompt=system_prompt or "你是一个简单智能助手，负责回答用户问题",
            llm=llm,
            tool_registry=tool_registry,
        )

        self.enable_tool_calling = (
            enable_tool_calling and tool_registry is not None
        )

    def _get_enhanced_system_prompt(self) -> str:
        """构建增强的系统提示词，包含工具信息（文档 7.4.1）"""
        base_prompt = self.system_prompt or "你是一个有用的AI助手。"
        if not self.enable_tool_calling or not self.tool_registry:
            return base_prompt

        tools_description = self.tool_registry.get_tools_description()
        if not tools_description or tools_description == "暂无可用工具":
            return base_prompt

        tools_section = "\n\n## 可用工具\n"
        tools_section += "你可以使用以下工具来帮助回答问题:\n"
        tools_section += tools_description + "\n"
        tools_section += "\n## 工具调用格式\n"
        tools_section += "当需要使用工具时，请使用以下格式:\n"
        tools_section += "`[TOOL_CALL:{tool_name}:{parameters}]`\n"
        tools_section += "例如:`[TOOL_CALL:calculator:123+456]` 或 "
        tools_section += "`[TOOL_CALL:memory:action=add,content=我叫张三]`\n\n"
        tools_section += "工具调用结果会自动插入到对话中，然后你可以基于结果继续回答。\n"
        return base_prompt + tools_section

    def run(self, input_text: str, max_tool_iterations: int = 3, **kwargs) -> str:
        """运行 SimpleAgent，支持可选工具调用"""
        messages = []
        messages.append({"role": "system", "content": self._get_enhanced_system_prompt()})

        # 历史消息
        for msg in self._history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": input_text})

        # 未启用工具调用：简单对话
        if not self.enable_tool_calling:
            response = self.llm.invoke(messages, **kwargs)
            self.add_message(Message(content=input_text, role="user"))
            if response is None:
                response = "（模型无输出）"
            self.add_message(Message(content=response, role="assistant"))
            return response

        return self._run_with_tools(messages, input_text, max_tool_iterations, **kwargs)

    def _run_with_tools(self, messages: list, input_text: str,
                        max_tool_iterations: int, **kwargs) -> str:
        """支持工具调用的运行逻辑（文档 7.4.1）"""
        current_iteration = 0
        final_response = ""

        while current_iteration < max_tool_iterations:
            response = self.llm.invoke(messages, **kwargs)
            if response is None:
                # 模型 content 为 None（拒绝/推理响应）时归一化，避免后续崩溃
                response = "（模型无输出）"

            tool_calls = self._parse_tool_calls(response)
            if tool_calls:
                clean_response = response
                tool_results = []
                for call in tool_calls:
                    result = self._execute_tool_call(
                        call["tool_name"], call["parameters"]
                    )
                    tool_results.append(result)
                    clean_response = clean_response.replace(call["original"], "")

                messages.append({"role": "assistant", "content": clean_response})
                tool_results_text = "\n\n".join(tool_results)
                messages.append({
                    "role": "user",
                    "content": f"工具执行结果:\n{tool_results_text}\n\n请基于这些结果给出完整的回答。",
                })
                current_iteration += 1
                continue

            # 无工具调用，最终回答
            final_response = response
            break

        # 超过最大迭代次数
        if current_iteration >= max_tool_iterations and not final_response:
            final_response = self.llm.invoke(messages, **kwargs)
        if not final_response:
            final_response = "（模型无输出）"

        self.add_message(Message(content=input_text, role="user"))
        self.add_message(Message(content=final_response, role="assistant"))
        return final_response

    def _parse_tool_calls(self, text: str) -> list:
        """解析文本中的工具调用 [TOOL_CALL:name:params]"""
        if not text:
            return []
        pattern = r'\[TOOL_CALL:([^:]+):([^\]]+)\]'
        matches = re.findall(pattern, text)
        tool_calls = []
        for tool_name, parameters in matches:
            tool_calls.append({
                "tool_name": tool_name.strip(),
                "parameters": parameters.strip(),
                "original": f"[TOOL_CALL:{tool_name}:{parameters}]",
            })
        return tool_calls

    def _execute_tool_call(self, tool_name: str, parameters: str) -> str:
        """执行工具调用"""
        if not self.tool_registry:
            return f"❌ 错误:未配置工具注册表"
        try:
            # 智能参数解析
            if tool_name == "calculator":
                result = self.tool_registry.execute_tool(tool_name, parameters)
            else:
                param_dict = self._parse_tool_parameters(tool_name, parameters)
                tool = self.tool_registry.get_tool(tool_name)
                if tool is None or isinstance(tool, dict):
                    return f"❌ 错误:未找到工具 '{tool_name}'"
                result = tool.run(**param_dict)
            # dict/list 工具结果转为 JSON 文本，避免 repr 后直接塞进提示词
            if isinstance(result, (dict, list)):
                result = json.dumps(result, ensure_ascii=False, default=str)
            return f"🔧 工具 {tool_name} 执行结果:\n{result}"
        except Exception as e:
            return f"❌ 工具调用失败:{str(e)}"

    def _parse_tool_parameters(self, tool_name: str, parameters: str) -> dict:
        """智能解析工具参数"""
        param_dict = {}
        if "=" in parameters:
            if "," in parameters:
                pairs = parameters.split(",")
                for pair in pairs:
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        param_dict[key.strip()] = value.strip()
            else:
                key, value = parameters.split("=", 1)
                param_dict[key.strip()] = value.strip()
        else:
            # 直接传入参数，根据工具类型智能推断
            if tool_name == "search":
                param_dict = {"query": parameters}
            elif tool_name == "memory":
                param_dict = {"action": "search", "query": parameters}
            else:
                param_dict = {"input": parameters}
        return param_dict

    # ---------------- 工具管理便利方法 ----------------

    def add_tool(self, tool):
        """添加工具到Agent

        支持协议工具的自动展开（第十章）：MCPTool 会被展开为服务器提供的
        多个独立工具（如 calculator_add / calculator_multiply）。
        """
        if not self.tool_registry:
            from ..tools.registry import ToolRegistry
            self.tool_registry = ToolRegistry()
            self.enable_tool_calling = True

        if hasattr(tool, "expand"):
            # 协议工具自动展开（对齐文档 10.2.4）
            expanded = tool.expand()
            for t in expanded:
                self.tool_registry.register_tool(t)
            print(f"✅ MCP工具 '{tool.name}' 已展开为 {len(expanded)} 个独立工具")
        else:
            self.tool_registry.register_tool(tool)

    def remove_tool(self, tool_name: str) -> bool:
        """移除工具"""
        if self.tool_registry:
            self.tool_registry.unregister(tool_name)
            return True
        return False

    def list_tools(self) -> list:
        """列出所有可用工具"""
        if self.tool_registry:
            return self.tool_registry.list_all()
        return []

    def has_tools(self) -> bool:
        """检查是否有可用工具"""
        return self.enable_tool_calling and self.tool_registry is not None
