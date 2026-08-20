# 第十一章 Agentic-RL —— 验证与环境抉择指南

本指南回答三个问题:
1. **第十一章的代码在本系统的什么位置、如何起关联?**
2. **我该如何验证第十一章的代码?**(全流程)
3. **虚拟环境我该如何抉择?**(本机 5 个 conda 环境)

配套脚本:本目录 `ch11_*.py`(镜像参考 `code/chapter11/` 的 00-08 示例)+ `config.json` + `accelerate_configs/`。

---

## 一、第十一章与系统代码的关联

第十一章不是孤立脚本,它是**挂在本框架上的一个模块 + 一个工具**:

```
HelloAgents 框架 (本系统)
│
├── hello_agents/
│   ├── __init__.py                     ← 顶层导出 RLTrainingTool + rl 子模块
│   ├── tools/
│   │   ├── base.py                     ← BaseTool 基类 (第七章 7.5.1)
│   │   ├── builtin/
│   │   │   ├── rl_training_tool.py     ← RLTrainingTool (统一接口层, 第十一章新增)
│   │   │   └── memory/rag/terminal/mcp/a2a...  ← 与之平级的其他工具
│   │   └── registry.py                 ← ToolRegistry, SimpleAgent 用它注册工具
│   └── rl/                             ← 第十一章四层架构 (11.1.4)
│       ├── datasets.py                 ← 数据集层
│       ├── rewards.py                  ← 奖励函数层
│       ├── trainers.py                 ← 训练器层 (SFT/GRPO, 惰性导入 trl)
│       └── utils.py                    ← 答案提取/比较辅助
│
└── examples/ch11/*.py                  ← 示例脚本 = 参考 code/chapter11 的镜像
                                          (验证入口, 不是独立实现)
```

**关联的 4 个关键点:**

1. **`RLTrainingTool` 继承 `BaseTool`** —— 和 MemoryTool/RAGTool/MCPTool 完全平级,同样有 `run()`/`execute()` 统一接口、`to_openai_schema()`。经 `builtin/__init__.py` + `hello_agents/__init__.py` 进入框架顶层导出:
   ```python
   from hello_agents import RLTrainingTool, rl   # 与 from hello_agents import MemoryTool 一样
   ```
2. **它是一层分发壳** —— `RLTrainingTool._train()` 只做参数解析与分派:按 `algorithm` 调 `SFTTrainerWrapper`/`GRPOTrainerWrapper`,按优先级解析数据集/奖励函数,再调 `hello_agents/rl/` 里的真实实现。**示例脚本 → 工具 → rl 模块**,不跨框架边界。
3. **`rl` 子模块惰性导入** —— `import hello_agents` 不加载 torch/trl,只有训练/评估时才 `import trl`。这是"base 能跑离线层、训练才需 env_rl"的设计原因。
4. **示例脚本与框架的接入点是 `sys.path` bootstrap** —— 每例开头 `sys.path.insert(0, dirname×3)` 到项目根再 `from hello_agents.tools import RLTrainingTool`。**删掉这行示例就 import 不到框架**。

**一句话:第十一章 = 框架的一个新工具(`RLTrainingTool`)+ 一个新子模块(`hello_agents.rl`);示例脚本只是验证入口。验证示例脚本 = 验证框架的 rl 模块;rl 模块里真正的训练依赖 env_rl 的 trl/transformers。**

---

## 二、全流程验证(照顺序走,每步有明确判据)

### 阶段 A:离线层验证(base 环境,秒级,验证框架代码本身)

不碰 GPU、不碰 trl,证明 `hello_agents/rl/` 四层在框架里可用:

```bash
cd D:/AI_Project/HelloAgents

# A1. 框架能否导入第十一章 (最根本的关联验证)
python -c "from hello_agents import RLTrainingTool, rl; print(RLTrainingTool.__mro__)"

# A2. 奖励层 (→ rewards.py + utils.py)
python examples/ch11/ch11_reward_functions.py

# A3. 数据集层 (→ datasets.py, 离线兜底样本)
python examples/ch11/ch11_dataset_loading.py

# A4. 工具层 (→ RLTrainingTool 分发正确, 无需训练依赖)
python -c "from hello_agents import RLTrainingTool; print(RLTrainingTool().run({'action':'device'})); print(RLTrainingTool().run({'action':'create_reward','reward_type':'combined'}))"

# A5. 配置演示 (→ LoRA 参数 / accelerate 配置, 纯打印)
python examples/ch11/ch11_lora_configuration.py
python examples/ch11/ch11_distributed_training.py
```

**判据**:A1 打印出 `[..., BaseTool, ...]`(挂在框架工具体系下);A2/A3 无 ImportError 且有样本输出;A4 返回 JSON 含 `device`/`demo_rewards`;A5 打印 LoRA/accelerate 配置。

### 阶段 B:训练器层验证(env_rl,GPU,分钟级,验证真实训练)

模型已缓存,所有命令带离线变量:

```bash
# B1. env_rl 就绪: torch 必须 ≥2.6 (trl 1.x 硬性要求) + cuda True
D:/pyhon/ana/ana3/envs/env_rl/python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"

# B2. 冒烟首选 (~10 分钟): SFT 10样本 → GRPO 5样本 → 评估
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
  D:/pyhon/ana/ana3/envs/env_rl/python.exe examples/ch11/ch11_quick_test.py

# B3. 单步训练 (可选, 对应 04/05 示例)
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
  D:/pyhon/ana/ana3/envs/env_rl/python.exe examples/ch11/ch11_sft_training.py
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
  D:/pyhon/ana/ana3/envs/env_rl/python.exe examples/ch11/ch11_grpo_training.py

# B4. 评估 (→ trainers.py 的 evaluate_math_model, 对比 基线/SFT/GRPO)
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
  D:/pyhon/ana/ana3/envs/env_rl/python.exe examples/ch11/ch11_model_evaluation.py

# B5. 端到端 (config.json 驱动, 100样本×2epoch ≈ 1h)
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
  D:/pyhon/ana/ana3/envs/env_rl/python.exe examples/ch11/ch11_complete_pipeline.py
```

**判据**:

| 步骤 | 预期 | 含义 |
|---|---|---|
| B1 | `2.13.0+cu126 True` | env_rl 就绪 |
| B2 | SFT loss ~1.67 单调下降;GRPO avg_reward ~0.167;评估有输出 | 三条训练路径全通 |
| B3 | `./models/ch11_sft_model/`、`ch11_grpo_model/` 落盘 | 模型可保存 |
| B4 | 基线 0.2 / SFT 0.0 / GRPO 0.2 + format 0.0 | 评估函数工作(低准确率是小样本 + `<think>` 截断,正常) |
| B5 | `./models/ch11_pipeline/` + accuracy ~0.33 | 端到端闭环 |

### 阶段 C:框架集成验证(证明"第十一章是本系统能力")

```bash
# C1. 经框架 Agent 体系调用: 和 MemoryTool 一样经 ToolRegistry 注册
python -c "
from hello_agents import RLTrainingTool
from hello_agents.tools.registry import ToolRegistry
r = ToolRegistry(); r.register_tool(RLTrainingTool())
print(r.get_tools())
print(RLTrainingTool().to_openai_schema()['function']['name'])  # 'rl_training'
"
```

**判据**:`rl_training` 出现在工具清单里、能转成 OpenAI schema——即第十一章代码可被 `SimpleAgent`(`agents/simple_agent.py`)注册为一项能力,与 MemoryTool/RAGTool 无异。

---

## 三、虚拟环境抉择(本机 5 个环境)

### 环境清单

| 环境 | Python | torch | 关键依赖 | 定位 | ⚠️ 红线 |
|---|---|---|---|---|---|
| **base** | 3.13 | CPU | transformers 5.14.1、gradio、qdrant、neo4j、mcp 1.29.0 | 日常 / 离线层 / 框架本体 | **绝不降级、绝不动**(gradio+starlette 依赖脆弱,见记忆 `gradio-fastapi-starlette-version`) |
| **env_rl** | 3.11 | **2.13+cu126 (GPU)** | trl 1.9.2、transformers 4.57.6、peft 0.20.0、accelerate 1.14.0、datasets 5.0.1 | **第十一章 GPU 训练专用** | 训练依赖钉死,勿与 base 混用 |
| autogen | — | — | autogen/mcp/a2a | 第十章 / 多智能体 | 与第十一章无关 |
| env_rec | — | — | 记忆 / RAG 相关 | 记忆系统章节 | 与第十一章无关 |
| yolov8 | 3.8 | 2.4.1+cu118 (GPU) | 旧版 | 视觉 / 旧项目 | **py3.8 装不了现代 transformers/trl,不能用于训练栈** |

### 快速决策表

| 你要做什么 | 用哪个环境 | 命令头 |
|---|---|---|
| 改框架代码、跑离线示例(数据集/奖励/配置) | **base** | `python` |
| **跑第十一章训练 / 评估 / 流水线(GPU)** | **env_rl** | `D:/pyhon/ana/ana3/envs/env_rl/python.exe` |
| 跑第十章示例 / 框架集成测试 | **base**(或 autogen,视章节) | `python` |
| 用记忆系统 / RAG | env_rec | 按该章文档 |
| 视觉项目(YOLO) | yolov8 | — |

### 核心规则

1. **GPU 训练只在 env_rl 跑。** base 是 CPU torch + transformers 5.14.1,与 TRL 不兼容(trl 1.x 需要 transformers<5 + torch≥2.6)。
2. **绝不动 base。** gradio/qdrant/starlette 版本链脆弱,任何 `pip install` 都可能毁掉日常栈。训练相关依赖装进 env_rl。
3. **env_rl 是隔离训练沙箱。** 已补装框架导入链(openai、python-dotenv、pyyaml、numpy、neo4j、qdrant-client、mcp==1.29.0、a2a),`from hello_agents import ...` 在 env_rl 也能导入。
4. **yolov8 不可用于第十一章。** 有 GPU torch 但 py3.8 装不了现代 transformers/trl。
5. **文件层面无冲突。** 两环境读同一份 `hello_agents/` 代码;模型缓存(`~/.cache/huggingface`)共享,env_rl 首跑下载一次,之后离线可用。

---

## 四、常见问题排查

| 现象 | 原因 | 解法 |
|---|---|---|
| `ModuleNotFoundError: hello_agents...` | 工作目录不对 | `cd D:/AI_Project/HelloAgents` 再跑 |
| `ConnectTimeout` 卡住 | 未设离线变量 | 所有 env_rl 命令加 `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1` |
| `FSDPModule` ImportError | env_rl 里 torch < 2.6 | 确认 `torch.__version__` 为 2.13.0+cu126(trl 1.x 硬性要求) |
| `generation_batch_size must be divisible by num_generations` | GRPO 配置没对齐 | trainers.py 已自动设 `generation_batch_size=num_generations`;改配置时保持整除 |
| `torch_dtype is deprecated!` | transformers ≥4.57 | 已是警告,trainers.py 用 `_dtype_kwargs` 自动切 `dtype=` |
| OOM(CUDA out of memory) | 2GB 显存吃紧 | 降 `num_generations`(4→2)、`max_new_tokens`(256→128)、`batch_size`(2→1)、`max_length` |
| GRPO 训练无 ref_model 报错 | trl 版本不符 | env_rl 钉死 trl==1.9.2(PEFT 时自动 ref_model=None,零额外显存) |
| 在 base 里 `pip install trl` | 误操作 | **停手**。训练依赖只装 env_rl;base 已装的部分别动 |

---

## 五、参考

- 文档:`C:/Users/35780/Desktop/hello-agents-1.0.3/hello-agents-1.0.3/docs/chapter11/第十一章 Agentic-RL.md`
- 参考代码:`code/chapter11/`(00-08 示例 + config.json + accelerate_configs)
- 框架实现:`hello_agents/rl/`(datasets / rewards / trainers / utils)+ `hello_agents/tools/builtin/rl_training_tool.py`
- 环境记忆:`helloagents-env-rl.md`、`gradio-fastapi-starlette-version.md`
