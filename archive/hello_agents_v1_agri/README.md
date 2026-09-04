# hello_agents v1（农业混合版）— 存档

这是「通用框架 + YOLO 小麦农业平台」混合在一个包里的**旧版完整快照**，
在仓库拆分为 `framework/ha_framework`（通用框架）+ `products/wheat`（小麦产品）之前留存，
用于历史对照、必要时回滚或 import 参照。

- 存档时间：拆分动作执行前（2026-09）
- 内容：整个 `hello_agents/` 包的逐文件副本（含当时未提交改动与 `detection_log.py`）
- 对照文档：`../CODE_GUIDE.md`（旧代码详解）

## 如何 import 对照

本目录内的包名仍为 `hello_agents`，需要时可把它加进 `sys.path` 单独引用：

```bash
cd archive/hello_agents_v1_agri
python -c "import sys; sys.path.insert(0, '.'); import hello_agents; print(hello_agents.__file__)"
```

> 注意：此旧版与新的 `ha_framework` **不同名**，互不冲突，可同时存在于进程。
> 运行它的 Gradio 界面会向本目录的 `../outputs`（若存在）写运行时数据，属历史行为，不再维护。
