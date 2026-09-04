# -*- coding:utf-8 -*-
"""
工具注册管理（对齐文档第七章 7.5.1 ToolRegistry）

支持两种注册方式：
1. register_tool(Tool对象) - 复杂工具
2. register_function(name, description, func) - 简单函数工具
"""

from typing import Any, Callable, Dict, List

from .base import Tool


class ToolRegistry:

    def __init__(self):
        # 保存所有工具对象
        self.tools: Dict[str, Tool] = {}
        # 保存函数工具
        self._functions: Dict[str, Dict[str, Any]] = {}
        # 兼容旧属性
        self._tools = self.tools

    # ---------------- 注册 ----------------

    def register(self, tool: Tool):
        """兼容旧接口：等价于 register_tool"""
        self.register_tool(tool)

    def register_tool(self, tool: Tool):
        """注册Tool对象"""
        if tool.name in self.tools:
            print(f"⚠️ 警告: 工具 '{tool.name}' 已存在，将被覆盖。")
        self.tools[tool.name] = tool
        print(f"✅ 工具 '{tool.name}' 已注册。")

    def register_function(self, name: str, description: str, func: Callable[[str], str]):
        """直接注册函数作为工具（简便方式）"""
        if name in self._functions:
            print(f"⚠️ 警告: 工具 '{name}' 已存在，将被覆盖。")
        self._functions[name] = {
            "description": description,
            "func": func,
        }
        print(f"✅ 工具 '{name}' 已注册。")

    # ---------------- 查询 ----------------

    def get(self, name):
        """兼容旧接口：获取工具"""
        return self.get_tool(name)

    def get_tool(self, name):
        """获取工具"""
        if name in self.tools:
            return self.tools[name]
        return self._functions.get(name)

    def list_tools(self) -> List[Tool]:
        """查看所有工具（返回工具对象列表，兼容旧接口返回 values 列表）"""
        return list(self.tools.values())

    def list_all(self) -> List[Any]:
        """列出所有工具名称"""
        return list(self.tools.keys()) + list(self._functions.keys())

    def remove(self, name):
        """兼容旧接口：删除工具"""
        self.unregister(name)

    def unregister(self, name):
        """删除工具"""
        if name in self.tools:
            del self.tools[name]
        if name in self._functions:
            del self._functions[name]

    # ---------------- 描述与执行 ----------------

    def get_tools_description(self) -> str:
        """获取所有可用工具的格式化描述字符串"""
        descriptions = []
        for tool in self.tools.values():
            descriptions.append(f"- {tool.name}: {tool.description}")
        for name, info in self._functions.items():
            descriptions.append(f"- {name}: {info['description']}")
        return "\n".join(descriptions) if descriptions else "暂无可用工具"

    def execute_tool(self, tool_name: str, input_data: str) -> str:
        """
        执行工具。
        input_data 可以是字符串（传给 run）或 kwargs 字典
        """
        tool = self.get_tool(tool_name)
        if tool is None:
            return f"❌ 错误: 未找到工具 '{tool_name}'"

        # 函数工具：直接调用
        if isinstance(tool, dict):
            return str(tool["func"](input_data))

        # Tool对象：支持字典或字符串参数
        if isinstance(input_data, dict):
            return tool.run(**input_data)
        return tool.run(input_data)

    def to_openai_schema(self) -> List[Dict[str, Any]]:
        """转换为 OpenAI function calling schema 列表"""
        schemas = []
        for tool in self.tools.values():
            if hasattr(tool, "to_openai_schema"):
                schemas.append(tool.to_openai_schema())
        return schemas
