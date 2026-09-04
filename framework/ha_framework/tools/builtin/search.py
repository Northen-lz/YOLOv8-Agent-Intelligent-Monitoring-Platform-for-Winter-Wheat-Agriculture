# -*- coding: utf-8 -*-
"""
多源搜索工具
"""

import requests

from ..base import BaseTool


class SearchTool(BaseTool):
    """互联网信息搜索工具"""

    def __init__(self):
        super().__init__(
            name="search",
            description="用于互联网信息搜索",
        )

    def run(self, *args, **kwargs) -> str:
        """搜索互联网信息（返回字符串，对齐 BaseTool.run 协议）"""
        query = kwargs.get("query")
        if query is None and args:
            query = args[0]
        if not query:
            return "❌ 搜索失败: 查询内容不能为空"

        try:
            url = "https://www.baidu.com/s"
            params = {"wd": query}
            response = requests.get(url, params=params, timeout=5)
            response.encoding = "utf-8"
            return response.text[:500]
        except Exception as e:
            return f"❌ 搜索失败: {e}"
