# -*- coding:utf-8 -*-

"""
计算工具
"""

from ..base import BaseTool



class CalculatorTool(BaseTool):


    def __init__(self):

        super().__init__(

            name="calculator",

            description="用于执行数学计算"

        )



    def run(self, expression):

        try:

            result = eval(expression)

            return result


        except Exception as e:

            return f"计算错误:{e}"