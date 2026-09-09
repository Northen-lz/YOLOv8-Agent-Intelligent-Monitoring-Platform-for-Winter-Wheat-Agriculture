# HelloAgents —— 通用智能体框架 + 产品库（monorepo）

把「通用智能体框架」和「具体产品」分离：框架是**公共依赖包**，新产品在它之上构建
（产品互不 import）；旧混合包已存档可对照。

```
HelloAgents/
├── framework/          # ★ 通用框架（import ha_framework，pip 可装，领域无关）
├── products/           # ★ 产品库（各产品并列，第一代 = wheat 小麦监测平台）
│   ├── README.md       #   如何用框架新建一个产品
│   └── wheat/          #   YOLOv8-Agent 冬小麦智能监测平台
├── archive/            # 历史留档（旧 hello_agents 混合包完整快照 + CODE_GUIDE）
├── docs/interview/     # 
├── langchain_demo/     # LangChain 演示（面试演示，独立于框架）
└── .env                # 共享密钥（LLM/Qdrant/Neo4j；不入库）
```

## 布局逻辑

| 目录 | 角色 | import 名 |
|---|---|---|
| `framework/` | 公共框架包：Agent 范式、记忆/RAG、工具系统、协议、RL/评估 | `ha_framework` |
| `products/wheat/` | 第一个产品：小麦领域代码 + Gradio UI | `wheat` |
| `archive/hello_agents_v1_agri/` | 拆分前旧包完整快照（可 import 对照） | `hello_agents` |

约定：**产品包之间不互相 import**；要共享的能力上提进 `ha_framework`。
领域内部用相对导入、领域引用框架用 `from ha_framework…` 绝对导入。

## 快速开始（小麦产品）

```bash
# 1) 安装通用框架（base 环境；小麦与未来产品共用）
pip install -e ./framework

# 2) 启动平台（浏览器 → http://127.0.0.1:7865；局域网手机 http://<电脑IP>:7865）
cd products/wheat
D:\pyhon\ana\ana3\python.exe run_ui.py     # 或双击 run_ui.bat
```

功能与使用说明见 [products/wheat/README.md](products/wheat/README.md)，
框架能力与打包见 [framework/README.md](framework/README.md)。

## 校验

```bash
# 框架独立可导入（任意目录）
python -c "import ha_framework; from ha_framework import SimpleAgent, RAGTool, MemoryTool, Config"

# 产品构建冒烟（不 launch）
cd products/wheat && python -c "import wheat; from wheat.app import build_ui; build_ui()"

# 旧包存档对照
cd archive/hello_agents_v1_agri && python -c "import hello_agents; print(hello_agents.__file__)"
```
