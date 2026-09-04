# YOLOv8-Agent 冬小麦农业智能监测平台（产品）

小麦产品跑在通用框架 **ha_framework**（仓库根 `framework/`，`pip install -e` 已装）之上。
本产品**只包含领域代码**：小麦/干旱 Agent、农业工具、知识库、Gradio UI。
通用能力（LLM 客户端、Agent 范式、记忆/RAG、工具系统、协议）一律 `import ha_framework…`。

> 这是 monorepo 拆分后的**第一个产品**。旧混合包（含 PDF 助手）已完整存档到
> `archive/hello_agents_v1_agri/`，可对照；本目录功能与旧版一致，仅替换了 import。

---

## 目录

```
products/wheat/
├── run_ui.py / run_ui.bat   # 一键启动（0.0.0.0 + 可选 cpolar + 登录保护）
├── requirements.txt         # 本机运行依赖（gradio 等）
├── wheat/                   # ★ 产品包（import wheat）
│   ├── core/config.py       #   小麦 Config：继承框架 + 农业常量/产品路径
│   ├── core/…               #   会话/统计/检测日志存储（领域存储）
│   ├── agents/              #   6 个领域 Agent + Manager 编排
│   ├── tools/agriculture/   #   7 个农业工具 + 2 个 MCP 服务端
│   ├── knowledge/           #   5 篇领域知识文本（关键词检索/可灌向量库）
│   └── app.py               #   Gradio UI（python -m wheat.app 运行）
├── outputs/  memory_data/   # 运行时数据（会话/标注图/报告/stats/记忆库）
├── tools/cpolar/            # 公网隧道客户端（局域网可忽略）
├── deploy/                  # 云服务器部署（pack_deploy/server_setup/systemd）
├── scripts/                 # 灌库脚本（Qdrant 知识库 / 语义记忆+Neo4j 图谱）
└── docs/                    # agriculture-platform.md（平台完整说明）
```

## 启动

**本机 / 手机局域网访问**（绑定 0.0.0.0）：

```bat
cd products/wheat
D:\pyhon\ana\ana3\python.exe run_ui.py        :: 或双击 run_ui.bat
:: 浏览器 → http://127.0.0.1:7865；同一 WiFi 手机 → http://<电脑IP>:7865
```

- 只需本机访问：`set HELLO_AGENTS_UI_HOST=127.0.0.1`
- 公网暴露强烈建议开启登录保护：`set UI_AUTH_USER=xxx` + `set UI_AUTH_PASS=yyy`
- 公网隧道：装 cpolar 后 `cpolar start hello-agents-7865`（run_ui.bat 会自动尝试拉起
  `tools/cpolar/bin/cpolar.exe`）
- 不经 run_ui 直接跑（仅本机，需在 products/wheat 目录）：`python -m wheat.app`

## 首次准备

- 框架已 editable 安装到 base 环境（仓库根 `pip install -e ./framework`）。
- 领域依赖见 `requirements.txt`；图片检测/干旱需外部 YOLO 权重
  （`D:\pyhon\vscode-xiaomai`，Config 走绝对路径，迁移不受影响）。
- 知识问答默认走零依赖关键词检索；要向量检索先起 Qdrant 再灌库：

```bat
cd products/wheat
D:\pyhon\ana\ana3\python.exe scripts\seed_rag_knowledge.py   :: Qdrant 知识库
D:\pyhon\ana\ana3\python.exe scripts\seed_rag_graph.py       :: 语义记忆 + Neo4j 图谱（需 Neo4j）
```

## 云部署

买好阿里/腾讯云轻量 2核4G Ubuntu 后，按 `deploy/README.md` 操作：
先重新执行 `python products/wheat/deploy/pack_deploy.py`（本仓库已拆分，旧 tar 包失效需重打），
再上传解压到 `/opt/hello-agents` 运行 `server_setup.sh`。

## 从旧包对照

- 旧平台完整快照：`archive/hello_agents_v1_agri/`
- 平台功能详解：`docs/agriculture-platform.md`（原 docs/ 移入本目录）
