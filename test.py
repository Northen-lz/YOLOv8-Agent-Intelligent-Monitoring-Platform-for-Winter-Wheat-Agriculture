from hello_agents import RLTrainingTool
from hello_agents.tools.registry import ToolRegistry

# 1) 注册进工具注册表 —— 与 MemoryTool 完全相同的路径
r = ToolRegistry()
r.register_tool(RLTrainingTool())
print('① 工具清单 :', r.list_all())

# 2) 经注册表执行 —— 这正是 Agent 内部调用工具的路径 (simple_agent._execute_tool)
print('② 经注册表执行 device:', r.get_tool('rl_training').run({'action':'device'}))

# 3) 转 OpenAI schema —— 可被 LLM function-calling 调用
print('③ OpenAI schema 工具名:', RLTrainingTool().to_openai_schema()['function']['name'])
