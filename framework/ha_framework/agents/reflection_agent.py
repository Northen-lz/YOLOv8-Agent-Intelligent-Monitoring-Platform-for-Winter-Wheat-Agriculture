# -*- coding:utf-8 -*-

"""
Reflection Agent实现
"""

from ..core.agent import Agent



class ReflectionAgent(Agent):


    def __init__(
            self,
            name="ReflectionAgent"
    ):


        super().__init__(

            name=name,

            system_prompt=
            "你是一个能够自我检查和优化答案的智能助手"

        )



    def run(
            self,
            user_input
    ):


        # 第一次生成

        first_answer = super().run(

            user_input

        )


        # 反思优化

        reflection_prompt = f"""

请检查下面的回答：

问题：
{user_input}


初始回答：
{first_answer}


请完成：

1. 找出问题

2. 提出改进建议

3. 输出优化后的最终答案


"""


        final_answer = super().run(

            reflection_prompt

        )


        return final_answer