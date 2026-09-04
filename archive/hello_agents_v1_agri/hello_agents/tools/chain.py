# -*- coding:utf-8 -*-

"""
工具链管理
"""

from .base import BaseTool



class ToolChain:


    def __init__(self):

        self.tools = []



    def add_tool(
            self,
            tool:BaseTool
    ):

        """
        添加工具
        """

        self.tools.append(tool)



    def run(
            self,
            input_data
    ):

        """
        按顺序执行工具
        """

        result = input_data


        for tool in self.tools:


            result = tool.run(

                result

            )


        return result



    def list_tools(self):

        return [

            tool.name

            for tool in self.tools

        ]