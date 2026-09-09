# -*- coding:utf-8 -*-
"""
工具基类

设计：
- run(parameters: Dict) -> str   执行工具，接受字典参数
- get_parameters() -> List       工具参数定义（内省能力）
- execute(action, **kwargs)      统一分发入口（第八章 MemoryTool/RAGTool 使用）
- 为兼容旧工具，run 同时支持 *args 直接传参
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ToolParameter:
    """工具参数定义"""

    def __init__(self, name, type="string", description="", required=True, default=None):
        self.name = name
        self.type = type
        self.description = description
        self.required = required
        self.default = default


class BaseTool(ABC):

    def __init__(self, name=None, description=None):
        # 兼容两种写法：
        # 1. super().__init__(name="xxx", description="xxx") —— 文档写法
        # 2. 子类直接声明类属性 name/description —— 简化写法
        self.name = name if name is not None else getattr(type(self), "name", None)
        self.description = (
            description
            if description is not None
            else getattr(type(self), "description", "")
        )
        if not self.name:
            raise ValueError("工具必须指定 name")

    @abstractmethod
    def run(self, *args, **kwargs):
        """
        工具执行方法
        """
        pass

    def get_parameters(self) -> List[ToolParameter]:
        """
        获取工具参数定义（默认空列表，子类可覆盖）
        """
        return []

    def execute(self, action=None, **kwargs) -> str:
        """
        统一分发入口。
        默认转发到 run；MemoryTool/RAGTool 等支持多操作的子类会覆盖此方法。
        """
        return self.run(*kwargs.get("_args", ()), **kwargs)

    def to_openai_schema(self) -> Dict[str, Any]:
        """
        转换为 OpenAI function calling schema 格式
        """
        parameters = self.get_parameters()
        properties = {}
        required = []
        for param in parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.default is not None:
                prop["description"] = f"{param.description} (默认: {param.default})"
            if param.type == "array":
                prop["items"] = {"type": "string"}
            properties[param.name] = prop
            if param.required:
                required.append(param.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def __str__(self):
        return f"Tool:{self.name}"


# 别名：文档第八章使用 Tool 命名
Tool = BaseTool
