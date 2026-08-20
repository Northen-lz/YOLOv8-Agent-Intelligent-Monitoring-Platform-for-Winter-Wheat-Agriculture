from hello_agents.core.agent import Agent


agent = Agent(
    "Assistant"
)


result = agent.run(
    "什么是Agent?"
)



print(result)