# HelloAgents —— 智能体全栈项目

从零构建的**通用智能体框架**，并落地到「YOLOv8-Agent 农业智能监测平台」的完整项目。
覆盖智能体的**设计、训练、评估、部署、复盘**全链路，输出形态对齐「智能体产品经理」岗位的交付物
（Skill / Prompt / Markdown 知识库 / 可部署的智能体）。

---

## 一、项目全貌（架构总览）

```
HelloAgents/
├── hello_agents/                       # ★ 核心：通用智能体框架（可复用底座）
│   ├── agents/                         #   12 种智能体实现
│   │   ├── simple_agent.py             #     最简 Agent（单轮问答 + 工具调用）
│   │   ├── react_agent.py              #     ReAct 推理循环（Thought/Action/Observation）
│   │   ├── function_call_agent.py      #     Function Calling 多步循环 + on_step 回调
│   │   ├── manager_agent.py            #     多 Agent 编排（调度子 Agent）
│   │   ├── plan_solve_agent.py         #     规划-求解 Agent
│   │   ├── reflection_agent.py         #     反思增强 Agent
│   │   ├── codebase_maintainer.py      #     代码库维护 Agent
│   │   ├── wheat_agent.py              #     小麦视觉识别 Agent（识别门控）
│   │   ├── agriculture_agent.py        #     农业知识专家（ReAct + 检索路由 + MCP）
│   │   ├── analysis_agent.py           #     综合评价 Agent
│   │   ├── report_agent.py             #     报告生成 Agent（md/docx/pdf）
│   │   └── author_agent.py             #     作者/技术栈问答 Agent
│   ├── tools/                          #   工具体系
│   │   ├── base.py / registry.py       #     BaseTool 抽象 + 工具注册表
│   │   ├── chain.py / agent_tool.py    #     工具链 + 子 Agent 包装成工具
│   │   ├── agriculture/                #     农业工具：检测/干旱/知识/实验/报告/图片
│   │   └── builtin/                    #     通用工具：memory/note/calculator/terminal/rag
│   │                                  #       + MCP 协议工具 + 4 个评估工具 + RL 训练工具
│   ├── memory/                         #   记忆系统
│   │   ├── types/                      #     working / episodic / semantic / perceptual
│   │   ├── rag/                        #     检索增强生成（document / pipeline）
│   │   └── storage/                    #     Qdrant 向量库 / Neo4j 图库 / 文档存储（离线自动降级）
│   ├── protocols/                      #   智能体通信协议
│   │   ├── mcp/                        #     MCP 模型上下文协议（client/server）
│   │   ├── a2a/                        #     Agent-to-Agent 协议
│   │   └── anp/                        #     Agent 网络协议
│   ├── rl/                             #   强化学习训练（SFT/GRPO：数据集/奖励函数/训练器）
│   ├── evaluation/                     #   智能体评估
│   │   ├── benchmarks/bfcl/            #     工具调用评估（AST 匹配）
│   │   ├── benchmarks/gaia/            #     通用能力评估（准精确匹配）
│   │   └── data_generation/            #     数据生成质量（LLM Judge / Win Rate）
│   ├── context/                        #   上下文构建
│   ├── core/                           #   核心支撑（LLM 客户端/配置/会话存储/统计/异常）
│   ├── knowledge/                      # ★ 领域知识库：5 个 Markdown 文本（可编辑）
│   └── app.py                          # ★ YOLOv8-Agent 平台 Gradio 对话界面
│
├── run_ui.py / run_ui.bat              # ★ 一键启动：局域网手机直连 + 登录保护
├── deploy/                             # ★ 云服务器部署（打包 + 初始化脚本 + systemd 自启）
├── evaluation_results/                 # ★ 智能体评估结果（BFCL/GAIA/Judge/WinRate 报告）
├── app.py                              #   第八章 PDF 学习助手（独立应用，7860 端口）
├── models/                             #   模型权重（RL 训练产出 + 嵌入模型）
├── outputs/                            #   运行产物（报告 / 标注图 / 会话历史 / 统计）
├── memory_data/                        #   SQLite 记忆库
├── tools/cpolar                        #   cpolar 公网隧道客户端（免安装版）
├── examples/                           #   开发期章节配套示例与测试
└── .env                                #   LLM API 配置（DeepSeek）
```

---

## 二、核心成果清单

| # | 成果 | 说明 | 位置 |
|---|------|------|------|
| 1 | **通用智能体框架** | 12 种 Agent + 工具体系 + 四类记忆 + RAG + 知识图谱 + MCP/A2A/ANP 协议 + RL 训练 + 评估，构成完整可复用底座 | `hello_agents/` |
| 2 | **YOLOv8-Agent 农业监测平台** | 识别门控、多 Agent 编排、RAG 知识问答、三格式报告、对话历史管理（置顶/重命名/删除）、数据统计、批量检测 | `hello_agents/app.py` + `run_ui.py` |
| 3 | **智能体评估体系** | BFCL 工具调用 / GAIA 通用能力 / 数据生成质量三场景，产出 4 份评估报告 | `hello_agents/evaluation/` + `evaluation_results/` |
| 4 | **RL 强化学习训练** | SFT + GRPO 全流程，3 套训练模型权重 | `hello_agents/rl/` + `models/ch11_*` |
| 5 | **云服务器部署方案** | 一键打包 tar.gz + 服务器初始化脚本 + systemd 自启 + 登录保护，手机随时可访问 | `deploy/` |
| 6 | **手机访问** | 局域网 0.0.0.0 直连 + cpolar 公网隧道 | `run_ui.py` + `tools/cpolar` |
| 7 | **知识库交付物** | 5 个领域 Markdown 文本（小麦生长/干旱/实验/检测/作者），即智能体 PM 岗位的「Markdown 交付物」 | `hello_agents/knowledge/` |
| 8 | **验证体系** | 97 项离线 mock 测试 + 真实集成验证 + HTTP 端到端测试 | `examples/agriculture/` |

---

## 三、快速上手

```bash
# ① 启动农业平台（默认 7865 端口，局域网手机可直连）
python run_ui.py

# ② 仅本机访问
python -m hello_agents.app

# ③ 给 RAG 知识库灌库（首次或更新 knowledge/ 后）
python examples/agriculture/seed_rag_knowledge.py

# ④ 跑智能体评估（BFCL/GAIA/数据生成）
python examples/ch12/ch12_quick_test.py

# ⑤ 云部署（详见 deploy/README.md）
python deploy/pack_deploy.py
```

> 注意：根目录 `app.py` 是第八章 PDF 学习助手（7860 端口），与农业平台无关。
> LLM 调用需 `.env` 配置 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID`。

---

## 四、目录速查

| 目录/文件 | 一句话说明 | 能否删除 |
|---|---|---|
| `hello_agents/` | 核心框架 + 平台，**项目主体** | ❌ 不可删 |
| `deploy/` | 云部署打包与脚本 | ❌ 保留（成果） |
| `evaluation_results/` | 评估报告 | ❌ 保留（成果） |
| `hello_agents/knowledge/` | 领域知识库（Markdown 交付物） | ❌ 保留 |
| `run_ui.py / run_ui.bat` | 平台启动入口 | ❌ 保留 |
| `.env` | API 密钥配置 | ❌ 不可删 |
| `models/` | 模型权重（约 3.9G） | ⚠️ 保留（RL 训练重资产） |
| `outputs/` | 报告/标注图/会话/统计 | ⚠️ 运行数据，保留为演示 |
| `memory_data/` | SQLite 记忆库 | ⚠️ 运行数据 |
| `tools/cpolar/` | 公网隧道客户端（19M） | ⚠️ 可选（手机公网访问用） |
| `examples/` | 章节示例与测试脚本 | ⚠️ 可清理（见删除清单） |
| 根目录 `app.py` | PDF 学习助手（独立） | ⚠️ 可选保留 |
| 根目录杂项 | `main.py`/`test.py`/`image_view.jpg`/日志 | ✅ 可删（垃圾） |

---

## 五、技术栈

Python 3.13 · Gradio（UI）· DeepSeek（LLM）· YOLOv8 / ONNX（视觉检测）·
Qdrant（向量库）· Neo4j（图数据库）· SQLite · MCP/A2A/ANP（通信协议）·
TRL（SFT/GRPO 训练）· BFCL/GAIA（智能体评估）

---

## 六、环境与依赖

- 主环境：`base`（py3.13），`python` 直接运行
- RL 训练需独立 `env_rl` 环境（torch≥2.6 / trl 1.9.2 / mcp 1.29），运行需 `HF_HUB_OFFLINE`
- Qdrant/Neo4j 通过 Docker 运行（`docker run -p 6333:6333 qdrant/qdrant`），未启动时平台自动降级不崩溃
- 关键版本约束：`starlette < 0.48`（否则 Gradio launch 报错）
