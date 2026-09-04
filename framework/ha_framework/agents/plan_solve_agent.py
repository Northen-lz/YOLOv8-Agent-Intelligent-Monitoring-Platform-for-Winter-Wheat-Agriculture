# -*- coding:utf-8 -*-

"""
Plan And Solve Agent实现
"""

from ..core.agent import Agent



class PlanAndSolveAgent(Agent):


    def __init__(
            self,
            name="PlanAndSolveAgent"
    ):


        super().__init__(

            name=name,

            system_prompt="""

你是一个规划执行型智能助手。

面对复杂任务：

1. 先制定解决计划

2. 再按照计划执行

3. 最后输出结果


"""

        )



    def run(
            self,
            user_input
    ):


        prompt=f"""

请使用Plan-and-Solve方式解决问题。


用户任务：

{user_input}


请按照格式：

Plan:

1.
2.
3.


Solve:

根据计划执行，并给出最终结果。


"""


        return super().run(

            prompt

        )