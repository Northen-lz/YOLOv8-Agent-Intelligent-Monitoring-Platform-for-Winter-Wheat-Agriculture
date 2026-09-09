# 爪案（petbrand）· 猫狗品牌全案策划 Agent

基于通用框架 **ha_framework**（仓库根 `framework/`，已 `pip install -e`）的**第二个产品**。
像一位"品牌顾问"，用**对话式攒案**产出你要的那一类策划案——**开案时自选类型**：

- **品牌全案 · 从 0 起盘**：市场与竞品 → 人群洞察 → 品牌定位 → 品牌资产
- **宣传推广活动案**：受众洞察 → 传播定位基点 → 传播主题与大创意 → 内容·媒介·预算·KPI
- **新品上市案**：上市人群洞察 → 上市定位切口 → 上市概念与首发创意 → 三阶段打法与预算
- **大促节点案**：大促受众洞察 → 大促定位基点 → 促销主题与机制 → 流量波段与预算

每类都逐模块「草稿→定稿」，攒完后一键汇总成**可放映提案页 + 全案 Markdown**。

- 内置拟真演示品牌「爪局 PawChess」→ 开箱即用跑通全流程
- 访谈模式 → 逐题收集真实品牌信息，可服务真实客户
- 纯 LLM（DeepSeek）+ 内置知识，无外部视觉/大模型依赖

## 启动

```bat
cd products/petbrand
D:\pyhon\ana\ana3\python.exe run_ui.py        :: 或双击 run_ui.bat
:: 浏览器 → http://127.0.0.1:7866
```

## 攒案流程

```
在「④ 案历史」选策划案类型开案（demo 内置 brief / 访谈收真实 brief）
  → 按所选类型依次攒 4 个模块（草稿→自检→定稿）
    · 品牌全案：市场与竞品 → 人群洞察 → 品牌定位 → 品牌资产
    · 宣传推广：受众洞察 → 传播定位基点 → 传播主题与大创意 → 内容·媒介·预算·KPI
    · 新品上市：上市人群洞察 → 上市定位切口 → 上市概念与首发创意 → 三阶段打法与预算
    · 大促节点：大促受众洞察 → 大促定位基点 → 促销主题与机制 → 流量波段与预算
  → 一键攒案 → 提案页 HTML + 全案 Markdown（outputs/decks/<case_id>/）
```

## 目录

```
products/petbrand/
├── run_ui.py / run_ui.bat / requirements.txt
├── petbrand/                 # ★ 产品包（import petbrand）
│   ├── core/config.py        #   Config 继承框架 + 产品路径
│   ├── core/{brief_store,case_store,wizard}.py
│   ├── agents/               #   8 个 Agent（顾问经理 + 市场/人群/定位/资产/创意/执行/提案）
│   ├── tools/petresearch/    #   知识检索 / brief / 提案汇总 3 工具
│   ├── knowledge/            #   8 篇领域知识（市场/人群/定位/资产 + 传播/上市/大促打法）
│   └── app.py                #   Gradio 深色四页 UI
├── scenarios/                #   内置演示品牌 brief
├── outputs/                  #   攒案产物（cases/ 工程 + decks/ 提案页）
└── docs/                     # （可选）平台说明
```

## 复用 ha_framework

`Agent / FunctionCallingAgent`、`HelloAgentsLLM`、`BaseTool / ToolParameter / AgentTool / ToolRegistry`、
`Config`。知识问答零外部依赖（关键词检索兜底），可配 Qdrant 语义检索升级。
