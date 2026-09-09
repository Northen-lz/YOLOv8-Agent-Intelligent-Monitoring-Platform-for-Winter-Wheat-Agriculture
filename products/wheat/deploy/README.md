# YOLOv8-Agent 小麦平台 · 云服务器完整部署（方案一）

把整个小麦平台（含小麦检测 + 干旱分析 + 报告 + 知识问答）搬到**国内云服务器**，
实现「电脑关机，手机打开网址照样能用」的 24/7 访问。

> ⚠️ **本仓库已拆分为 framework/ + products/wheat/**（2026-09-04 后）。
> 旧 tar 包（`hello-agents-server.tar.gz`，含旧 `hello_agents` 包）已**失效**，
> 上传服务器前务必先在本机重新打包：
> `D:\pyhon\ana\ana3\python.exe products\wheat\deploy\pack_deploy.py`
> 新版部署包含 `wheat/`（产品包）+ `ha_framework/`（框架源码目录，服务器直接
> sys.path 导入，无需 pip 安装），解压后 /opt/hello-agents 下两个 import 均可命中。
