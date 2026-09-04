# -*- coding:utf-8 -*-

"""
Hello-Agents异常体系
"""


class HelloAgentsError(Exception):
    """
    框架基础异常
    """
    pass



class LLMError(HelloAgentsError):
    """
    大模型调用异常
    """
    pass



class AgentError(HelloAgentsError):
    """
    Agent运行异常
    """
    pass



class ToolError(HelloAgentsError):
    """
    工具执行异常
    """
    pass