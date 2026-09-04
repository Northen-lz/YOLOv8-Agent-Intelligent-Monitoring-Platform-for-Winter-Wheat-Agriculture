# ha_framework —— 通用智能体框架（公共包）

领域无关的智能体底座，**只放通用能力，不放任何产品/领域代码**。未来每个新产品都基于它构建。

## 安装

```bash
pip install -e ./framework            # 装核心（轻量）
pip install -e "./framework[rag]"     # 需要向量记忆/RAG 再按需加装
pip install -e "./framework[rl]"      # RL 训练（重，建议 GPU 独立环境）
# 可选组：rag / doc / protocols / rl / eval
```

安装后任意目录可 `import ha_framework`。

## 包内含什么

```
ha_framework/
├── core/       Agent 基类、HelloAgentsLLM（DeepSeek/OpenAI 兼容）、Config（env/.env）、Message、异常
├── agents/     通用推理范式：Simple / ReAct / FunctionCalling / Reflection / PlanAndSolve / CodebaseMaintainer
├── tools/      BaseTool + ToolRegistry + AgentTool（子 Agent 包装成工具，多 Agent 编排核心）
│   └── builtin/  记忆 / 笔记 / RAG / 计算器 / 终端 / 搜索 / 图片描述 / MCP·A2A·ANP 工具 / RL·评估一键工具
├── memory/     四类记忆（working/episodic/semantic/perceptual）+ RAG（MQE/HyDE）+ Qdrant/Neo4j/SQLite（离线降级）
├── context/    ContextBuilder（GSSC 上下文构建流水线）
├── protocols/  MCP / A2A / ANP 三种智能体通信协议
├── rl/         SFT + GRPO 强化学习（数据集 / 奖励函数 / 训练器）
└── evaluation/ BFCL / GAIA / 数据生成质量（LLM Judge / Win Rate）
```

## 如何基于它新建一个产品（模板）

1. 在仓库 `products/` 下建你的产品目录，例如 `products/myapp/`。
2. 产品里建自己的领域包（如 `myapp/`），只放领域 Agent/工具/知识，import 框架能力：

```python
from ha_framework import SimpleAgent, ReActAgent, HelloAgentsLLM, RAGTool, MemoryTool
from ha_framework.tools.base import BaseTool, Tool, ToolParameter   # 领域工具继承它
from ha_framework.tools.agent_tool import AgentTool                 # 多 Agent 编排
from ha_framework.core.config import Config                         # 通用 env/.env 配置
```

3. 若产品有自己的数据路径/模型常量，写一个继承框架 Config 的产品 Config，并把
   `DATA_ROOT` 指到产品目录（示例见 `../products/wheat/wheat/core/config.py`）。
4. 在 `../products/README.md` 登记你的产品。

> 完整示例：小麦产品在 `../products/wheat/`。
> `models/`、`evaluation_results/` 为本机框架演示数据（.gitignored，不入库）。
