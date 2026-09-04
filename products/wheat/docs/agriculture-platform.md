# YOLOv8-Agent 农业智能监测平台 —— 构建与手动重跑清单

在 HelloAgents 通用 Agent 框架上二次扩展：原有 YOLOv8 冬小麦检测 + 干旱 ONNX 分类系统（**位于 `D:\pyhon\vscode-xiaomai`，未修改**）保持不变，仅在 Agent 层叠加智能理解/分析/调用/解释/决策能力。

## 目录结构

```
hello_agents/
├── agents/
│   ├── react_agent.py            # 【升级】真 ReAct 循环（Thought/Action/Observation）
│   ├── function_call_agent.py    # 【升级】max_tool_calls 多步循环 + on_step 回调
│   ├── wheat_agent.py            # WheatVisionAgent：识别门控 + 检测+干旱→LLM 解释 / 常规图分析
│   ├── agriculture_agent.py      # AgricultureExpertAgent：农业知识问答（ReAct，已挂载通用工具）
│   ├── analysis_agent.py         # AnalysisAgent：综合检测+干旱+问题→评价
│   ├── report_agent.py           # ReportAgent：结构化数据→三格式报告
│   ├── author_agent.py           # AuthorAgent：作者/技术栈问答
│   └── manager_agent.py          # ManagerAgent：Function Calling 多 Agent 编排
├── tools/
│   ├── agent_tool.py             # AgentTool：把子 Agent 包装成 BaseTool（编排核心）
│   ├── agriculture/              # 7 个工具（检测/干旱/知识/实验/报告/作者/图片信息）
│   └── builtin/                  # 【扩展】零外部服务通用工具：memory/note/calculator/terminal/rag
├── knowledge/                    # 5 个领域知识文本（可编辑，已按论文补充作者与实验数据）
├── core/config.py                # 新增 NOTE_DIR / PROJECT_ROOT 等配置（env 可覆盖）
├── app.py                        # Gradio 类 Dify 对话界面（python -m hello_agents.app）
└── docs/agriculture-platform.md  # 本文件：平台构建与运行说明
```

## 识别门控（图片分流）

上传图片后先经 **WheatVisionAgent.recognize()** 用 YOLOv8 检测判定是否含小麦：

- **检测到小麦穗头（count>0）** → 进入小麦智能分析管线：检测统计 + 干旱分类 + 自然语言解释 + 可生成报告
- **未检测到小麦（count==0）** → 按常规图片处理：ImageInfoTool 提取尺寸/亮度/色彩/主色调/复杂度 → 常规图片信息说明 + 正常聊天

门控在 `WheatVisionAgent.run()` 内部同样生效（Manager 的 wheat_vision 子 Agent 复用），且检测结果按 `(image_path, conf)` 缓存，识别与分析不重复推理。

## 模型与实验数据查询

平台默认使用**最佳模型**（`Config` 中显式标注，env 可覆盖）：

| 用途 | 最佳模型 | 路径 |
|---|---|---|
| 穗头检测 | **yolov8s** | `models/detector/yolov8s/weights/best.pt` |
| 干旱分类 | **exp_augmented2_s** | `models/classifier/exp_augmented2_s/weights/best.onnx` |

`models/` 下其余（yolo8n/yolo10n/yolo11n、exp_augmented2）为实验对比版。对话中可直接向知识专家查询真实实验数据（`AgricultureExpertAgent` 已注册 `ExperimentAnalysisTool`，纯读目录/CSV，不加载模型）：

- 「你们用了哪些模型 / 哪个检测模型最佳」→ `experiment_analysis(action="models")` 模型清单 + 最佳标注
- 「分类器评估结果 / accuracy 对比」→ `action="eval"` 读 `outputs/classifier_model_comparison.csv`
- 「数据集多大 / 有多少张」→ `action="data"` 数据集规模统计

## 检测标注图展示

小麦图片检出后，界面会在对话中**直接展示 YOLOv8 画框标注图**（`results[0].plot()` 生成，BGR 保存到 `outputs/detections/<原名>_annotated_c{conf}.jpg`，属本平台 outputs/，不动外部系统）：

- 识别为小麦 → `wheat_vision` 分析步骤后追加一条 `🖼 检测结果标注图` 图片消息
- 实现链：`WheatDetectionTool.detect(save_annotated=True)` → `WheatVisionAgent.annotated_path` → `app.respond` 的 `("image", path)` 队列消息 → Chatbot 文件元组渲染
- 标注图随会话 JSON 一起持久化，调回历史时仍可回显

## 零外部服务工具（已挂载进农业知识专家）

`AgricultureExpertAgent` 除知识检索/实验查询外，还注册了第 7-12 章的 5 个通用工具（`hello_agents/tools/builtin/`），全部**零外部服务可用**（Qdrant/Neo4j 未启动时自动降级，不崩）：

| 工具 | 作用 | 对话触发 |
|---|---|---|
| `memory` | 跨会话记忆：working（内存）+ episodic（SQLite 持久化，Qdrant 离线时关键词检索兜底） | 「记住…」「还记得上次…」 |
| `note` | 结构化笔记（Markdown+YAML，`outputs/notes/`） | 「记个笔记」「我的待办」 |
| `calculator` | 数学计算/单位换算/产量估算 | 「帮我算 150 亩×8.6kg/亩」 |
| `terminal` | 项目目录内只读命令（白名单+沙箱） | 「看看 outputs 下的报告」 |
| `rag` | 向量知识库检索（需本机 Qdrant 服务；未启动返回友好提示并改用 knowledge 检索） | 知识库深度问答 |
| `image_caption` | 本地视觉模型（Ollama Qwen2.5-VL）图片语义描述：照片/截图/图表/作物长势均可 | 「描述这张图 / 图里有什么」 |

**`image_caption`（本地视觉，2026-08-12 新增）**：主 LLM 为 DeepSeek（纯文本，看不到图）。本机已装 Ollama + `qwen2.5vl:3b`（CPU 推理，MX570 2GB 显存过小，torch 为 cpu 版），工具用 urllib 调 `OLLAMA_URL/api/generate`（默认 `http://127.0.0.1:11434`），图片 base64 内嵌（>6MB 先 PIL 缩到 1024 宽）。每张图约 30~90s。Ollama 未启动/未拉模型 → 返回友好提示，不抛异常。若未装 Ollama：`winget install Ollama.Ollama` → 启动服务 → `ollama pull qwen2.5vl:3b`。环境变量：`OLLAMA_URL` / `OLLAMA_VISION_MODEL` 可覆盖。

> **Qdrant 未启动时的行为**：存储层连接失败不再 raise（`qdrant_store.py`/`neo4j_store.py` 容错降级），
> MemoryTool 的 episodic 记忆仍写入 SQLite 并按关键词可检索；RAGTool 的 search/stats 返回明确提示。
> 想启用 RAG 向量检索：先启动 Qdrant（`docker run -p 6333:6333 qdrant/qdrant`），再运行：

```bash
python scripts/seed_rag_knowledge.py   # 把 knowledge/*.txt 灌入 agriculture_kb 集合
```

> **RAG 已启用（2026-08-12）**：Docker 容器（qdrant/neo4j）已设 `--restart unless-stopped` 随 Docker Desktop 自动启动；
> `.env` 的 `EMBED_MODEL_TYPE=tfidf`（sklearn 384 维，OOM 安全；sentence-transformers 语义更强但本机需 ≥2GB 空闲内存）。
> 已灌入 5 文件/9 分块并通过检索验证。改 .env 后需重启 `python -m hello_agents.app`。
>
> **RAG 检索质量与五项优化（2026-08-13）**：
>
> 1. **RAG 向量优先路由**：农业知识专家（`agriculture_agent.py`）提示词新增【知识检索路由（强制）】——知识类问题先走 `rag` 向量检索，Qdrant 未连接/未命中时再回退 `knowledge_tool` 关键词检索。
> 2. **检索质量修复（关键经验）**：384 维 TFIDF（`char_wb` 2-3 元）对中文**纯向量检索本质偏弱**——粗块(1000)与细块(350)纯检索分数都只有 ~0.2 噪音级、top1 常错。**唯一出过好成绩（0.6+、答案正确）的组合是「粗块 1000/200 + MQE/HyDE 开启」**。故 `seed_rag_knowledge.py` 用粗块（9 分块）、`.env` 默认 `RAG_ENABLE_MQE=1 / RAG_ENABLE_HYDE=1`（每条检索额外 2-3 次 LLM 调用换召回；需要更快可改 0，接受召回下降）。实测「小麦拔节期需水量 / 冬小麦产量由什么构成 / 什么是水分敏感期」的 `ask` 答案全部正确且引用真实知识（拔节期土壤含水量 70-80%、耗水模系数 32.2%、产量=亩穗数×穗粒数×千粒重、拔节至抽穗是水分敏感期）。
> 3. **语义记忆接入**：`SemanticMemory` 改为懒加载（嵌入/Qdrant/Neo4j/spaCy 首次 add/retrieve 才构造，离线自动降级），`MemoryTool` 内存类型扩为 `["working","episodic","semantic"]`——「干旱影响哪些生育期」混合检索正确命中「干旱胁迫定义 + 抽穗开花期对水分敏感/防卡脖旱」。
> 4. **知识图谱 + 1-hop 检索**：`Neo4jGraphStore.find_memories_for_entities` 新增 `OPTIONAL MATCH (q)-[:RELATES]->(nb)` 邻居召回（邻居 0.5×基础分）；`seed_rag_graph.py` 灌入 46 段语义记忆 + 27 条本体三元组（388 实体/793 关系，全部取自 knowledge/*.txt 真实内容）。
> 5. **MQE/HyDE 开关**：`Config.RAG_ENABLE_MQE/HYDE`（env 可覆盖），`rag` 工具单次调用仍可显式传 `enable_mqe/enable_hyde` 覆盖全局。
>
> 语义记忆与图谱种子脚本：`python scripts/seed_rag_graph.py`（需 Qdrant + Neo4j 均在 Docker 运行）。

## 通信协议启用（MCP，2026-08-13）

农业知识专家已接入**两个 MCP 服务器**（第 10 章协议层，`MCPTool.expand()` 手动展开注册——`AgricultureExpertAgent` 继承 `ReActAgent`，不像 `SimpleAgent.add_tool()` 自动展开）：

| MCP 服务器 | 传输 | 展开工具 | 能力 |
| --- | --- | --- | --- |
| **农业自定义**（`hello_agents/tools/agriculture/agriculture_mcp_server.py`） | **Memory**（进程内，零外部依赖） | `agri_query_models` / `agri_query_eval` / `agri_query_data` / `agri_search_knowledge` / `agri_get_platform_info` | 把平台已有能力（`ExperimentAnalysisTool`/`AgricultureKnowledgeTool`）协议化，与实验/知识工具**数据同源** |
| **天气**（`hello_agents/tools/agriculture/weather_mcp_server.py`） | **stdio**（子进程，wttr.in 联网） | `weather_get_weather_by_city(city)` | 城市实时天气/气温/湿度，对干旱防治/灌溉决策有真实价值 |

**实现要点**：
- `MCPTool` 新增可选 `server=` 参数（`hello_agents/tools/builtin/protocol_tools.py`）连进程内 FastMCP（Memory 传输），不传时行为不变（stdio/内置演示服务器）——ch10 回归无破坏
- 天气 MCP 的 `expand()` 只做本地子进程 stdio 握手（不访问 wttr.in），离线也能注册工具；仅实际调用才联网，失败返回「查询天气失败」容错
- 任一个 MCP 展开失败都静默跳过，不影响平台原有 8 个工具

**对话触发示例**：「北京天气怎么样？」→ `weather_get_weather_by_city`；「用 MCP 查一下有哪些模型」→ `agri_query_models`。实验/模型/数据类问题仍优先走 `experiment_analysis`（更快更全），`agri_*` 走 MCP 协议路径演示通信协议价值。

## 文件浏览器（对话区下方折叠面板）

界面内直接**浏览文件系统目录**，无需记忆终端命令：`hello_agents/app.py` 的 `build_ui` 用 `gr.FileExplorer`（gradio 5.45）挂了两个只读浏览器：

- **🌾 项目根目录**：`Config.PROJECT_ROOT`（`outputs/`、`knowledge/`、`hello_agents/` 源码等）
- **🔬 外部检测系统**：`Config.AGRICULTURE_SYSTEM_DIR`（`D:/pyhon/vscode-xiaomai`，只读，不修改）

**选中文件**（`FileExplorer.change` → `preview_file()`）自动分流：

- 图片（png/jpg/gif/webp 等）→ 右侧 `gr.Image` 预览
- 文本（md/json/csv/yaml/py/html/log 等）→ `gr.Markdown` 代码块展示（超 6000 字符截断并提示）
- 其他类型（模型权重等）→ 提示不支持预览，统一由「📥 下载文件」`gr.File` 提供下载

## 左侧功能导航（2026-08-12 界面改版）

标题「🌾 YOLOv8-Agent 农业智能监测平台」移至侧边栏左上角，副标题文案已删除。左侧边栏自上而下：

1. **➕ 新对话**（功能第一位）
2. **📖 使用示例**：点击在对话区顶部显示/收起使用示例面板（原底部静态使用示例已移除）
3. **📊 数据统计**：点击在对话区置顶弹出统计卡片（✕ 可关闭），动态读取 `outputs/stats.json` + 真实实验 CSV，含 5 项指标：
   - 📸 累计检测图像数（含非小麦，每次图片分析/批量检测 +1）
   - 🌾 累计识别小麦株数（检测框总数，实时累计）
   - 💧 累计干旱株数（干旱分类株数，实时累计）
   - 🎯 实验准确率（读 `classifier_model_comparison.csv` 默认分类器 yolov8s-cls 行，CSV 缺失回退论文表 5-4 的 77.97%）
   - 📉 最终验证损失（同行 val_loss，回退 0.44898）
   - 统计实现：`hello_agents/core/stats_store.py`（`record(image_count, wheat_count, drought_count)` 原子读改写，env 可用 `STATS_FILE` 覆盖路径）
4. **🔬 专业检测**：批量上传多张图片 → 逐张识别门控，**只对含小麦的图**做 YOLOv8 检测 + 干旱分类，输出 Markdown 表格 + 小麦标注图 Gallery，并同步累计进数据统计（`batch_detect`，同步调用无流式，不涉及 LLM）
5. **⚙️ 设置**：置信度阈值滑块（对话图片与批量检测共用）

会话记录（置顶 / 最近两组）下方有 ⋯ 菜单，见下节。**面板互斥**：使用示例 / 数据统计 / 专业检测 三面板同时只显示一个（`switch_panel`，再次点击收起），不占用聊天区输入位置。

## 对话历史管理

「➕ 新对话」会把当前对话**自动保存**到 `outputs/conversations/<id>.json`（`hello_agents/core/conversation_store.py`，纯文件操作）；每次问答结束（respond final/error）也会自动保存到当前会话。界面左侧为**常驻边栏**（`gr.Sidebar` + `gr.Radio`，类 ChatGPT/Dify 侧边栏，CSS 去 radio 圆点改为列表行），管理全部历史：

- **点击即调回**：点击列表中的某会话 → 恢复其完整消息（含图片/标注图消息），并高亮为当前会话
- **📌 置顶**：置顶会话靠前显示（标签带 📌，当前会话高亮）
- **✏️ 重命名**：在边栏输入框输入新标题后点击「重命名」
- **🗑 删除**：删除会话文件并清空当前界面
- 会话标题默认取首条用户文本（带图消息取其说明文字），消息内容以 `{"kind":"text|file",...}` 结构存 JSON，加载时还原为 str / 文件元组

**置顶 / 最近 两组**：`listbox_choices()` 现在分「📌 置顶」「最近」两组（`@group:置顶` / `@group:最近` 前缀 value 标识分组行），置顶会话在最上、其余按时间倒序，**只显示名称**。分组标题行在 UI 中渲染为灰色小字（CSS 用 `:has(input[value^="@group:"])` 匹配），点击不触发调回（`select_conv` 忽略）。选中某会话后其**右侧**弹出 ⋯ 按钮，点击在选中行右侧弹出 **置顶 / 重命名 / 删除** 小卡片（不占用聊天界面，也不占会话列表布局）；选中态为白色高亮块 + 浅边框。

**⋯ 弹出定位（2026-08-12）**：`more_btn`（⋯）与 `action-card`（小卡片）是**主区顶层组件**，不在侧边栏内——gradio `.sidebar` 带 `transform`（构成 fixed 包含块）且 `.sidebar-content` 为 `overflow-y:auto`（横向溢出被裁剪），侧边栏内绝对定位无法"右侧弹出"。`demo.load(None, js=_MORE_POSITION_JS)` 注入定位脚本。

**关键坑（已修复）**：gradio 5.45 的 `visible=False` 组件**不会挂载进 DOM**（首次显示时才挂载）。旧脚本用 `if (!card) return setTimeout(arm, 200)` 等 `#action-card` 出现再挂 MutationObserver——而卡片要点 ⋯ 才会挂载，于是 observer 永远没挂上，选中会话后 `more_btn` 即使被显示也停在 CSS 兜底 `-9999px`，表现为"选中会话看不到 ⋯"。修复：

1. **observer 立即挂载**（不再等 `#action-card`），用 `childList` 捕获 gradio 把 `more_btn`/`action_card` 挂进 DOM 的瞬间；`style/class` 属性过滤捕获可见性切换
2. **400ms 轮询兜底**（`setInterval(place, 400)`，5 分钟后自动停）：radio 选中态是 DOM 属性（`checked`），MutationObserver 的属性过滤器看不到，轮询保证任何时机都对齐当前选中行
3. **CSS 隐藏修复**：`#more-btn` 用 `display:flex !important` 会让 gradio 的 `.hidden{display:none}` 失效（ID+important 赢过类选择器），须加 `#more-btn.hidden{display:none !important}` 压回去，否则隐藏后 ⋯ 仍浮在屏上

定位逻辑：把二者按选中行**视口坐标**用 `position:fixed` 定位（⋯ 垂直居中于行右侧 `row.right+8`，卡片紧随其下方，底部越界自动钳制），随滚动/缩放/轮询重新定位；CSS `top/left:-9999px` 兜底 + JS `setProperty(..., 'important')` 覆盖（普通内联样式赢不过 CSS `!important`）。组件事件跟随 DOM 节点，置顶/重命名/删除 handler 不受影响。

**主题强制浅色（2026-08-12）**：gradio 5.45 的深/浅色**完全由前端 `prefers-color-scheme` 驱动**（`Index-NgTca28F.js` 的 `De()`/`ze()`：读 URL 参数 `__theme`，缺省走 `window.matchMedia("(prefers-color-scheme: dark)")`，深色 = 给根元素加 `.dark` class；`Blocks.__init__` 里**没有** `theme_mode` 开关）。后端想"永远默认浅色、不跟随系统"，最干净的做法是 `gr.Blocks(..., head=_FORCE_LIGHT_HEAD)` 往页面 `<head>` 注入脚本（前端 `Se(p.head)` 用 DOMParser 解析并 `appendChild` 执行）：

1. 替换 `window.matchMedia`：`prefers-color-scheme` 查询恒返回 `matches:false`，且 `addEventListener` 吞掉 → gradio 初始化时解析为浅色，且监听不挂（系统后来切深色也不触发）
2. `MutationObserver` 兜底：任何元素被加上 `.dark` 立刻剥离（覆盖"脚本比 `De()` 后跑"或残留监听等时序）
3. 初始与延迟各 `strip()` 一次

验证：Chrome headless `--force-dark-mode`（模拟系统深色）下，对照组 body 出现 `class="dark"`，注入脚本后消失；真实 app `/config` 的 `head` 字段含脚本，force-dark 下无 `.dark`、浅色下界面正常渲染。

## 环境（base 环境 py3.13）

```bash
# 必要依赖（已装，供参考）
python -m pip install ultralytics onnxruntime python-docx reportlab gradio
# LLM 需 .env 配置 DeepSeek（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID）
```

## 运行方式

> 清理说明：原验证脚本（离线 mock 测试 / 真实集成 / HTTP 端到端 / ch10·ch12 回归）
> 已随项目整理移除，历史版本保存在 git 中（`git log --diff-filter=D` 可回溯）。

### ① 启动平台（类 Dify 对话界面）

```bash
python -m hello_agents.app
# 浏览器打开 http://127.0.0.1:7865（端口可用 HELLO_AGENTS_UI_PORT 覆盖；
# 勿用 python app.py —— 那是根目录的第八章 PDF 学习助手，占用 7860）
# 在消息框上传/拖拽图片后发送：
#  - 小麦田间图 → 自动识别 → 检测/干旱分析 → 可继续输入"生成报告"下载三格式
#  - 其他图片   → 自动识别为不含小麦 → 常规图片信息说明 + 正常聊天
# 纯文本消息 → 知识问答 / 综合评价 / 报告生成 / 作者介绍
```

### ② 灌库（RAG 知识库 / 知识图谱）

```bash
python scripts/seed_rag_knowledge.py   # RAG 向量库（需 Qdrant）
python scripts/seed_rag_graph.py       # 知识图谱（需 Qdrant + Neo4j 均在 Docker）
```

## 外部系统与模型路径

| 项 | 路径（可用 env 覆盖） |
|---|---|
| 检测模型 | `D:\pyhon\vscode-xiaomai\models\detector\yolov8s\weights\best.pt` |
| 干旱 ONNX | `D:\pyhon\vscode-xiaomai\models\classifier\exp_augmented2_s\weights\best.onnx` |
| 知识库 | `hello_agents/knowledge/` |
| 报告输出 | `outputs/reports/` |

外部视觉系统代码一律不 import（硬编码了其他项目路径/Streamlit 依赖）；工具自包含加载模型并复刻 `preprocess_crop` 预处理。

## 作者信息

`hello_agents/knowledge/author_info.txt` 已按论文填写真实作者信息（罗政，黄冈师范学院·计算机与人工智能学院，人工智能专业）；
`experiment_info.txt` 同步补入论文真实实验数据（分类数据集 17328 个样本、增强后 69310、四版本检测对比表、增强前后分类 Top-1 Accuracy 61.80%→76.13%、ONNX 5.5MB 等）。
`AuthorAgent`/Manager 的 author 子 Agent 据此回答，`ExperimentAnalysisTool` 仍读真实 CSV/目录。
