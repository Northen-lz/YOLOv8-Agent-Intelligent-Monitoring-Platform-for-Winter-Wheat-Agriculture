# -*- coding:utf-8 -*-

"""
异步工具执行器
"""

import asyncio

from .base import BaseTool



class AsyncToolExecutor:


    def __init__(self):

        self.tools = []



    def add_tool(
            self,
            tool:BaseTool
    ):

        self.tools.append(tool)



    async def execute_tool(
            self,
            tool,
            data
    ):


        loop = asyncio.get_event_loop()


        result = await loop.run_in_executor(

            None,

            tool.run,

            data

        )


        return result



    async def run(
            self,
            data
    ):


        tasks = []


        for tool in self.tools:


            task = self.execute_tool(

                tool,

                data

            )


            tasks.append(task)



        results = await asyncio.gather(

            *tasks

        )


        return results