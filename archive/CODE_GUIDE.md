# HelloAgents 代码详解（模块级）

本文档按架构分层，逐文件说明每个部分的**作用、关键类/函数、在系统中的位置**。
配套总览见根目录 [README.md](../README.md)，平台运行细节见 [agriculture-platform.md](agriculture-platform.md)。

```
调用链总览：
用户输入 → run_ui.py 启动 → hello_agents/app.py (Gradio UI)
        → ManagerAgent 编排 → 子 Agent（WheatVision/AgricultureExpert/Analysis/Report/Author）
        → 工具（检测/干旱/知识/实验/报告/记忆/RAG/MCP...）
        → 底层：core/llm.py (DeepSeek) + memory/ (Qdrant/Neo4j/SQLite) + protocols/
```

---

## 一、框架对外 API（`hello_agents/__init__.py`）

框架唯一的对外出口，约 40 个公开符号，可通过 `from hello_agents import X` 直接使用：

| 类别 | 导出符号 |
|---|---|
| **Agent** | `SimpleAgent` `ReActAgent` `FunctionCallingAgent` `CodebaseMaintainer` `WheatVisionAgent` `AgricultureExpertAgent` `AnalysisAgent` `ReportAgent` `AuthorAgent` `ManagerAgent` |
| **核心** | `Agent`（基类）`HelloAgentsLLM` `Config` `Message` `HelloAgentsError/LLMError/AgentError/ToolError` |
| **工具** | `BaseTool/Tool/ToolParameter` `ToolRegistry` `AgentTool` + 12 个具体工具 |
| **记忆/上下文** | `MemoryManager/MemoryConfig/MemoryItem` `ContextBuilder/ContextConfig/ContextPacket` |
| **高级能力** | `rl`（强化学习）`evaluation`（评估） |

> 对应智能体 PM 的「交付物」概念：这套 `__init__.py` 就是框架的**对外接口清单**——别人用你的框架时只需 import 这一层。

---

## 二、入口与 UI 层

### `run_ui.py` —— 平台启动入口（推荐使用）
- 一键启动农业平台，绑定 `0.0.0.0` → 同一 WiFi 手机可直连 `http://<电脑IP>:7865`
- 在 import 前设 `HELLO_AGENTS_UI_HOST=0.0.0.0`，可选 `UI_AUTH_USER/PASS` 登录保护
- 调 `hello_agents.app.build_ui()` → `demo.launch()`
- `run_ui.bat` 为 Windows 双击版

### `hello_agents/app.py` —— 农业平台 Gradio 界面（核心 UI）
类 Dify 的单对话界面，功能全在这一层：
- **消息框**（MultimodalTextbox）：文本 + 图片上传
- **ManagerAgent 编排**：文本消息 → 调度子 Agent；图片 → wheat_vision 逐张分析，工具步骤流式渲染（thread+queue 生成器）
- **左侧边栏**：➕新对话 / 📖使用示例 / 📊数据统计 / 🔬专业检测（批量）/ ⚙️设置（置信度滑块）
- **会话管理**：历史列表（📌置顶/最近两组）、置顶/重命名/删除、调回含图片的历史
- **关键函数**：`build_ui()`（组装界面）、`respond()`（消息处理主循环）、`switch_panel()`（面板互斥）、`batch_detect()`（批量检测）
- 涉及大量 gradio 5.45 的 DOM/前端 hack（组件可见性、侧边栏弹窗定位、强制浅色主题）

### `app.py`（根目录）—— 第八章 PDF 学习助手（独立应用）
- 独立于农业平台，7860 端口。`PDFLearningAssistant`：上传 PDF → RAG 索引 + 记忆记录 → 智能问答（MQE/HyDE）→ 读书笔记 → 复习回忆 → 学习报告
- 演示 RAG + Memory 组合的经典助手范式

---

## 三、核心层（`hello_agents/core/`）

| 文件 | 作用 |
|---|---|
| `config.py` | **全局配置**。`Config` 类从环境变量/.env 读取：LLM 三件套（API_KEY/BASE_URL/MODEL_ID）、路径（知识库/会话/报告/统计）、`EMBED_MODEL_TYPE`、`RAG_ENABLE_MQE/HYDE` 开关等。**改 .env 后须重启进程生效**（模块级缓存） |
| `llm.py` | **LLM 统一调用接口**。`HelloAgentsLLM`：封装 OpenAI 兼容 API（DeepSeek），含系统提示/历史管理/工具 schema 注入；多提供商自动检测 |
| `message.py` | **消息系统**。`Message`：role 限定 user/assistant/system/tool，Agent 间传递的标准消息格式 |
| `agent.py` | **Agent 基类**。`Agent`：持有 llm + tool_registry，维护 `_history/messages`，提供 `add_message/get_history/clear_history/run`。所有 Agent 的祖先 |
| `exceptions.py` | **异常体系**。`HelloAgentsError`（根）→ `LLMError/AgentError/ToolError`（LLM/Agent/工具三路错误分类） |
| `conversation_store.py` | **对话持久化**。按会话存 JSON 到 `outputs/conversations/`：save/load/delete/rename/toggle_pin/list；消息内容序列化（文本↔文件元组往返）；`listbox_choices()` 生成侧边栏「置顶/最近」分组选项 |
| `stats_store.py` | **平台统计**。`outputs/stats.json` 持久化累计检测图数/识别株数/干旱株数；`get_stats()` 叠加实验指标（准确率 77.97%、验证损失），CSV 缺失回退论文常量 |

---

## 四、Agent 层（`hello_agents/agents/`）—— 12 种智能体

### 通用推理范式（4 种）
| 文件 | 作用 |
|---|---|
| `simple_agent.py` | `SimpleAgent`：最简 Agent，基础对话 + 可选 `[TOOL_CALL:工具:参数]` 格式工具调用（对齐第七章 7.4.1） |
| `react_agent.py` | `ReActAgent`：**真 ReAct 循环**——解析 LLM 输出的 `Action: 工具(参数)`，工具结果回填为 Observation，最多 max_steps 步。**推理范式升级的关键** |
| `function_call_agent.py` | `FunctionCallingAgent`：JSON 工具调用格式；默认单次（向后兼容），传 `max_tool_calls` 升级为多步循环 + `on_step` 回调 |
| `reflection_agent.py` | `ReflectionAgent`：先生成再自我反思修正的两段式推理 |
| `plan_solve_agent.py` | `PlanAndSolveAgent`：先规划再逐步求解 |

### 长程任务（1 种）
| 文件 | 作用 |
|---|---|
| `codebase_maintainer.py` | `CodebaseMaintainer`：第九章长程智能体示例，整合 ContextBuilder + NoteTool + TerminalTool + MemoryTool 实现跨会话的代码库维护任务 |

### 农业平台专用（6 种，核心业务链路）
| 文件 | 作用 |
|---|---|
| `wheat_agent.py` | `WheatVisionAgent`：**视觉识别 Agent**。`recognize()` 三级识别门控（规则门→视觉门→检测兜底）判断是否含小麦；是则调 YOLOv8 检测穗头 + ONNX 逐株干旱分类 + 生成标注图；`_detect_cache` 避免重复推理 |
| `agriculture_agent.py` | `AgricultureExpertAgent`：**农业知识专家**（ReAct）。挂载最多 14 个工具：知识检索/实验查询/零外部服务通用工具 + 农业 MCP（5 个 agri_*）+ 天气 MCP；EXPERT_SYSTEM_PROMPT 强制「知识类问题先走 RAG 向量检索」 |
| `analysis_agent.py` | `AnalysisAgent`：**综合评价**——检测+干旱结果+用户问题 → 数量是否正常/干旱风险/管理建议 |
| `report_agent.py` | `ReportAgent`：**报告生成**——结构化数据 →《冬小麦智能监测报告》md/docx/pdf 三格式 |
| `author_agent.py` | `AuthorAgent`：**作者介绍**——读 `knowledge/author_info.txt`，LLM 不可用降级为关键词直接回答 |
| `manager_agent.py` | `ManagerAgent`：**平台大脑**——用 AgentTool 把 5 个子 Agent 注册成可函数调用调度的工具，按用户请求编排：图片→wheat_vision 串联 analysis；文本→知识/报告/作者等 |

> **设计主线**：通用范式（ReAct/FC）+ 领域专用（农业 6 个）+ 编排中枢（Manager）——这是多 Agent 系统的标准分层。

---

## 五、工具层（`hello_agents/tools/`）

### 基础设施（5 个）
| 文件 | 作用 |
|---|---|
| `base.py` | `BaseTool` 工具基类：`run(parameters: Dict) -> str` 约定 + `ToolParameter` 参数定义 + `to_openai_schema()` 供 LLM function-calling |
| `registry.py` | `ToolRegistry` 工具注册表：register/get/list/按 schema 注入 LLM |
| `chain.py` | `ToolChain` 工具链管理 |
| `agent_tool.py` | `AgentTool`：**把子 Agent 包装成 BaseTool**——多 Agent 编排的核心机制 |
| `async_executor.py` | `AsyncToolExecutor` 异步工具执行器 |

### 通用内置工具（`tools/builtin/`，零外部服务可用）
| 文件 | 作用 |
|---|---|
| `memory_tool.py` | `MemoryTool`：跨会话记忆，`memory_types=["working","episodic","semantic"]`，Qdrant 离线自动降级 SQLite 关键词检索 |
| `note_tool.py` | `NoteTool`：结构化笔记（Markdown+YAML），持久化到 `outputs/notes/` |
| `rag_tool.py` | `RAGTool`：向量知识库检索，`_check_ready` 预检，Qdrant 未连返回友好提示 |
| `calculator.py` | `CalculatorTool`：数学计算/单位换算/产量估算 |
| `terminal_tool.py` | `TerminalTool`：白名单+沙箱的安全命令执行 |
| `search.py` | `SearchTool`：互联网搜索（运行时保持离线设计，未采用） |
| `image_caption_tool.py` | `ImageCaptionTool`：本地 Ollama + Qwen2.5-VL 图片语义描述（弥补纯文本 LLM 看不到图） |
| `protocol_tools.py` | `MCPTool`/`A2ATool`/`ANPTool`：**三种通信协议的统一工具包装层**——让 Agent 用一致方式调用 |
| `rl_training_tool.py` | `RLTrainingTool`：RL 训练统一入口（数据集/奖励/SFT/GRPO/评估） |
| `bfcl_evaluation_tool.py` | `BFCLEvaluationTool`：BFCL 工具调用一键评估 |
| `gaia_evaluation_tool.py` | `GAIAEvaluationTool`：GAIA 通用能力一键评估 |
| `llm_judge_tool.py` | `LLMJudgeTool`：LLM Judge 数据质量评估 |
| `win_rate_tool.py` | `WinRateTool`：Win Rate 成对对比评估 |

### 农业领域工具（`tools/agriculture/`）
| 文件 | 作用 |
|---|---|
| `wheat_detection.py` | `WheatDetectionTool`：加载外部视觉系统 YOLOv8 权重自包含推理穗头检测；`save_annotated=True` 生成标注图 |
| `drought_prediction.py` | `DroughtPredictionTool`：ONNX 干旱分类，逐株 crop→灰度→32×32→NCHW 预处理 |
| `knowledge_tool.py` | `AgricultureKnowledgeTool`：领域知识关键词加权轻量检索（离线可用） |
| `experiment_tool.py` | `ExperimentAnalysisTool`：实验数据分析（models/eval/data 三种动作，纯读目录/CSV） |
| `report_tool.py` | `ReportGenerationTool`：报告生成 md/docx/pdf（缺库降级） |
| `author_tool.py` | `AuthorInfoTool`：作者/项目信息问答 |
| `image_info_tool.py` | `ImageInfoTool`：常规图片信息提取（尺寸/亮度/色彩/主色调/复杂度）——非小麦路径 |
| `agriculture_mcp_server.py` | 农业自定义 MCP 服务器（进程内 Memory 传输），把平台已有能力包装成 5 个 agri_* 协议工具 |
| `weather_mcp_server.py` | 天气 MCP 服务器（stdio 子进程，调 wttr.in），城市实时天气 |

---

## 六、记忆系统（`hello_agents/memory/`）

| 文件 | 作用 |
|---|---|
| `base.py` | 记忆基础数据结构：`MemoryItem`（标准化记忆项）/`MemoryConfig`/`BaseMemory`（通用接口） |
| `embedding.py` | **统一嵌入服务**：`LocalTransformerEmbedding`（sentence-transformers，语义强）+ `TFIDFEmbedding`（sklearn，轻量兜底，当前默认 `EMBED_MODEL_TYPE=tfidf`，避免 OOM）；`create_embedding_model_with_fallback` 优先本地失败降级 |
| `manager.py` | `MemoryManager`：统一的记忆操作入口 |
| `types/working.py` | 工作记忆：纯内存 + TTL（短期） |
| `types/episodic.py` | 情景记忆：SQLite 持久化 + Qdrant 向量 + 关键词检索兜底（跨会话经验） |
| `types/semantic.py` | 语义记忆：Qdrant 向量 + Neo4j 图，懒加载后端（离线自动降级） |
| `types/perceptual.py` | 感知记忆：简化多模态 |
| `rag/document.py` | RAG 文档处理：多格式 → Markdown → 智能分块 |
| `rag/pipeline.py` | RAG 检索管道：索引→嵌入→**高级检索（MQE 多查询扩展 / HyDE 假设文档嵌入）** |
| `storage/qdrant_store.py` | Qdrant 向量库后端（1.19 API：query_points/retrieve/scroll） |
| `storage/neo4j_store.py` | Neo4j 图数据库后端（实体+RELATES 关系，1-hop 邻居召回） |
| `storage/document_store.py` | SQLite 文档存储（结构化持久化） |

> **容错降级是这套系统最突出的工程点**：Qdrant/Neo4j 未启动时全部自动降级不崩（`connected=False` + 上层 catch），平台离线可跑。

---

## 七、上下文工程（`hello_agents/context/builder.py`）

`ContextBuilder` 实现 **GSSC 流水线**（Gather-Select-Structure-Compress）：
- `ContextPacket`：候选信息包
- `ContextConfig`：构建配置
- 作用：把碎片信息整理成 Agent 可用的结构化上下文（对齐第九章 9.3）

---

## 八、通信协议（`hello_agents/protocols/`）

| 目录 | 作用 |
|---|---|
| `mcp/` | **MCP 模型上下文协议**：`MCPServer`（FastMCP 封装）+ `MCPClient`（stdio/Memory 多传输）+ `utils.py`（create_context/parse_context）。农业平台接入了两个 MCP 服务器 |
| `a2a/` | **A2A 智能体协作协议**：`A2AServer`（提供技能）+ `A2AClient`（调用远程技能） |
| `anp/` | **ANP 智能体网络协议**：`ANPDiscovery`（服务发现中心）+ `ANPNetwork`（节点网络）+ `AgentService` |

> 三种协议通过 `protocol_tools.py` 统一包装成 BaseTool，Agent 用一致的方式调用——这是「协议中立」的设计。

---

## 九、强化学习（`hello_agents/rl/`）—— 第十一章

| 文件 | 作用 |
|---|---|
| `datasets.py` | 数据集层：`GSM8KDataset` 数学推理数据集 + SFT/RL 格式转换（离线兜底） |
| `rewards.py` | 奖励函数层：`AccuracyReward`（准确率）/`LengthPenaltyReward`（长度惩罚）/`StepReward`（步骤）/`CombinedReward`（组合） |
| `trainers.py` | 训练器层：`SFTTrainerWrapper`（监督微调）+ `GRPOTrainerWrapper`（群组相对策略优化）+ `evaluate_math_model` |
| `utils.py` | 答案提取/步骤检测/答案比较工具 |

> 训练产物在 `models/ch11_*`（3 套权重）。需独立 `env_rl` 环境（torch≥2.6/trl 1.9.2），运行需 `HF_HUB_OFFLINE`。

---

## 十、评估系统（`hello_agents/evaluation/`）—— 第十二章

| 目录 | 作用 |
|---|---|
| `benchmarks/bfcl/` | **BFCL 工具调用评估**：`ast_matcher.py`（AST 等价匹配核心，纯逻辑）/`dataset.py`（本地>仓库>离线三源加载）/`evaluator.py`/`metrics.py` |
| `benchmarks/gaia/` | **GAIA 通用能力评估**：`quasi_exact_match.py`（准精确匹配归一化）/`dataset.py`/`evaluator.py`/`metrics.py` |
| `data_generation/` | **数据生成质量**：`aime_generator.py`（AIME 数学题生成）/`llm_judge.py`（4 维 1-5 分 LLM 裁判）/`win_rate.py`（生成 vs 真题成对对比）/`dataset.py` |

> 评估结果在 `evaluation_results/`（4 份报告），对应 `tools/builtin/` 里的 4 个一键评估工具。这是「智能体迭代闭环」的验证层。

---

## 十一、知识库（`hello_agents/knowledge/`）—— 5 个领域文本

| 文件 | 内容 | 对应交付物概念 |
|---|---|---|
| `wheat_growth.txt` | 小麦生育期/需水规律/水分敏感期（来源可溯源） | 业务知识库 |
| `drought_knowledge.txt` | 干旱胁迫定义/影响/防治 | 业务知识库 |
| `yolo_knowledge.txt` | YOLOv8 架构细节 | 技术知识库 |
| `experiment_info.txt` | 论文真实实验数据（数据集/模型对比/指标） | 一手数据资产 |
| `author_info.txt` | 作者/指导教师/技术路线 | 项目背书 |

> **这就是智能体 PM 岗位的「Markdown 交付物」**：Agent 通过 RAG（`scripts/seed_rag_knowledge.py` 灌库）或关键词检索（`knowledge_tool`）调用这些文本回答问题。

---

## 十二、维护与部署（`scripts/` + `deploy/`）

| 文件 | 作用 |
|---|---|
| `scripts/seed_rag_knowledge.py` | 把 `knowledge/*.txt` 灌入 Qdrant `agriculture_kb` 集合（更新知识库后重跑） |
| `scripts/seed_rag_graph.py` | 灌语义记忆 + 人工农业本体三元组到 Qdrant+Neo4j（需双库运行） |
| `deploy/pack_deploy.py` | 打包代码+模型+评估CSV+.env → `hello-agents-server.tar.gz` |
| `deploy/server_setup.sh` | 服务器初始化：装 Python/依赖/Qdrant/systemd 自启 |
| `deploy/hello-agents.service` | systemd 服务单元（开机自启） |
| `deploy/requirements.txt` | 服务器依赖清单 |
| `deploy/ssh_run.py` / `ssh_upload_stdin.py` | SSH 远程执行/上传工具 |
| `deploy/README.md` | 云部署操作手册 |

---

## 十三、数据产物（不入 git，运行生成）

| 目录 | 内容 |
|---|---|
| `outputs/conversations/` | 对话历史 JSON |
| `outputs/detections/` | 检测标注图 |
| `outputs/reports/` | 监测报告（md/docx/pdf） |
| `outputs/stats.json` | 累计统计 |
| `evaluation_results/` | 评估报告 + BFCL/GAIA/Judge/WinRate 结果 |
| `models/` | RL 训练权重（3.9G）+ 嵌入模型 |
| `memory_data/memory.db` | SQLite 记忆库 |

---

## 十四、各层用到的技术栈速查

> 按代码实际 import 提取。**核心**=平台日常运行必需；**可选/兜底**=特定功能或降级路径才用。

| 层 | 核心第三方库（作用） | 可选/兜底 | 备注 |
|---|---|---|---|
| **入口/UI** | `gradio` 5.45（Web UI：Chatbot/侧边栏/图片上传/批量检测） | 无 | 前端用 CSS/JS 注入调 gradio DOM 行为 |
| **core 地基** | `openai`（DeepSeek 的 OpenAI 兼容接口）、`dotenv`（.env 加载） | 无 | 其余为标准库（json/os/uuid） |
| **agents 智能体** | 无直接第三方 —— 纯编排层 | 无 | 技术体现在**推理范式**：ReAct（Thought/Action/Observation）+ Function Calling（JSON 工具调用）；底层能力全部走 core/llm + tools |
| **tools 工具** | `ultralytics`（YOLOv8 检测）、`onnxruntime`（干旱分类）、`cv2`（OpenCV 读图/画框）、`numpy`、`mcp`（协议工具）、`yaml`（笔记）、`requests`（天气 wttr.in） | `torch`（加载旧 .pt）、`PIL`（图片缩放）、`skimage`（预处理）、`docx`/`reportlab`（报告，缺库降级 md） | 视觉链路最重的层 |
| **memory 记忆** | `qdrant_client` 1.19（向量库）、`sklearn`（TFIDF 嵌入，当前默认）、`sqlite3`（持久化） | `sentence-transformers`（语义嵌入，需≥2GB 内存）、`neo4j`（图库）、`spacy`/`jieba`（实体识别/分词）、`fitz`/`markitdown`（PDF/文档解析） | 强调离线降级：Qdrant/Neo4j 不在也能跑 |
| **context 上下文** | 无第三方 —— 纯 Python 算法 | 无 | GSSC（Gather-Select-Structure-Compress）流水线 |
| **protocols 协议** | `mcp`（MCP 服务器/客户端）、`a2a`（A2A SDK） | 无 | ANP 为纯自定义实现 |
| **rl 强化学习** | `torch`（≥2.6）、`transformers`、`trl` 1.9.2（SFT/GRPO Trainer） | `peft`（LoRA）、`datasets`（HF 数据集）、`packaging`（版本比较） | 独立 `env_rl` 环境，需 GPU/`HF_HUB_OFFLINE` |
| **evaluation 评估** | 纯标准库（`ast`/`re`）—— BFCL/GAIA 匹配逻辑 | `huggingface_hub`（HF 数据集下载，可离线兜底） | 匹配逻辑零外部依赖，可离线评估 |
| **knowledge 知识** | 纯文本（5 个 .txt） | 无 | 灌库靠 `scripts/`（需 Qdrant） |
| **deploy+scripts** | `paramiko`（SSH 远程部署） | 无 | 打包用标准库 tarfile/shutil；`server_setup.sh` 为 bash + systemd |
| **根目录 app.py** | `gradio` | 无 | 独立 PDF 助手，演示 RAG+记忆组合 |
