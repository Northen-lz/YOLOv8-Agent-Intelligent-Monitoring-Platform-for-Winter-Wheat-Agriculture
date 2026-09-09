# -*- coding: utf-8 -*-
"""
Hello-Agents MCP 工具函数
protocols/mcp/utils.py（create_context / parse_context）

- create_context(tools)    把 MCP 服务器工具列表转成给 LLM 的系统提示文本
- parse_context(result)    把 MCP call_tool 返回的 content 块转成纯文本
"""

import json
from typing import Any, Dict, List


def create_context(server_info: Any) -> str:
    """
    构建 MCP 工具的 LLM 上下文描述（对齐文档 10.2.1「上下文构建」）：

    你可以使用以下工具：
    - read_file(path: str): 读取指定路径的文件内容
    - search_code(query: str, language: str): 在代码库中搜索

    Args:
        server_info: MCP 服务器工具列表，元素为
            {"name": str, "description": str, "inputSchema": {...}}
    """
    tools = server_info
    if hasattr(server_info, "tools"):
        tools = server_info.tools

    lines = ["你可以使用以下工具："]
    for tool in tools or []:
        if isinstance(tool, dict):
            name = tool.get("name", "?")
            desc = tool.get("description") or ""
            schema = tool.get("inputSchema") or {}
        else:
            # 兼容 mcp SDK 的 Tool 对象
            name = getattr(tool, "name", "?")
            desc = getattr(tool, "description", "") or ""
            schema = getattr(tool, "inputSchema", {}) or {}

        param_str = _format_params(schema)
        lines.append(f"- {name}({param_str}): {desc}")

    return "\n".join(lines) if tools else "当前没有可用工具。"


def _format_params(schema: Dict[str, Any]) -> str:
    """把 JSON Schema 的 properties 格式化为一串参数描述"""
    props = (schema or {}).get("properties") or {}
    required = (schema or {}).get("required") or []
    parts = []
    for pname, pinfo in props.items():
        ptype = pinfo.get("type", "any") if isinstance(pinfo, dict) else "any"
        parts.append(f"{pname}: {ptype}")
    param_str = ", ".join(parts)
    if required:
        param_str += f" (必填: {', '.join(required)})"
    return param_str


def parse_context(result: Any) -> str:
    """
    把 MCP call_tool / read_resource 的返回值解析成纯文本。

    兼容多种形式：
    - 字符串（如 "30.0"）
    - MCP 的 content 列表（TextContent/ImageContent 等）
    - pydantic 结果对象（CallToolResult / ReadResourceResult）
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, (int, float, bool)):
        return str(result)

    # pydantic 结果对象：含 .content / .contents
    contents = None
    if hasattr(result, "content") and result.content is not None:
        contents = result.content
    elif hasattr(result, "contents") and result.contents is not None:
        contents = result.contents

    if contents is not None:
        parts = []
        for block in contents:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif hasattr(block, "model_dump"):
                # ImageContent / EmbeddedResource 等
                parts.append(str(block.model_dump()))
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)

    # 普通 list / dict
    if isinstance(result, (list, dict)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)

    return str(result)
