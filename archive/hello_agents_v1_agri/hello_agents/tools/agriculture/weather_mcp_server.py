# -*- coding: utf-8 -*-
"""
天气 MCP 服务器（用 MCPServer 封装）
镜像参考 code/chapter10/14_weather_mcp_server.py。

需联网（调用 wttr.in 天气 API）。
作为 stdio 子进程运行：python hello_agents/tools/agriculture/weather_mcp_server.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import requests
from hello_agents.protocols import MCPServer

# 创建天气 MCP 服务器（对齐文档用法）
server = MCPServer("weather", description="天气查询 MCP 服务器")


def get_weather(city: str) -> str:
    """查询城市天气"""
    try:
        url = f"https://wttr.in/{city}?format=j1"
        data = requests.get(url, timeout=10).json()
        current = data.get("current_condition", [{}])[0]
        desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
        return (
            f"{city} 当前天气: {desc}, "
            f"温度 {current.get('temp_C')}°C, "
            f"体感 {current.get('FeelsLikeC')}°C, "
            f"湿度 {current.get('humidity')}%"
        )
    except Exception as e:
        return f"查询天气失败: {e}"


@server.tool()
def get_weather_by_city(city: str) -> str:
    """查询指定城市的天气"""
    return get_weather(city)


if __name__ == "__main__":
    import sys
    print("🚀 天气 MCP 服务器已启动（stdio 传输）", file=sys.stderr)
    server.run()
