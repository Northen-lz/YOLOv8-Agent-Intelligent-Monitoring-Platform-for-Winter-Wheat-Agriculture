# -*- coding: utf-8 -*-
"""
YOLOv8-Agent 小麦农业平台 —— 一键启动脚本（局域网 + 公网 cpolar）

与 python -m wheat.app 的区别：
- 绑定 0.0.0.0 → 同一 WiFi 的手机可直连 http://<电脑IP>:7865
- 支持可选登录保护 UI_AUTH_USER / UI_AUTH_PASS（公网暴露强烈建议开启）

用法（products/wheat 目录）：
    D:\\pyhon\\ana\\ana3\\python.exe run_ui.py

环境变量：
    HELLO_AGENTS_UI_HOST   默认 0.0.0.0（只需本机访问可设 127.0.0.1）
    HELLO_AGENTS_UI_PORT   默认 7865
    UI_AUTH_USER / UI_AUTH_PASS   同时设置则启用登录保护
"""
import os
import sys

# 产品根目录（Config 数据根/知识库/会话/报告等都相对它解析）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_PROJECT_ROOT)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
# 让 ha_framework 的记忆/RAG 等数据根也落到产品目录（须在任何 import 之前设置）
os.environ.setdefault("HA_DATA_ROOT", _PROJECT_ROOT)

# 关键：在 import build_ui 之前设置，让平台以 0.0.0.0 暴露
os.environ.setdefault("HELLO_AGENTS_UI_HOST", "0.0.0.0")


def main():
    from wheat.app import build_ui

    demo = build_ui()
    port = int(os.getenv("HELLO_AGENTS_UI_PORT", "7865"))
    host = os.getenv("HELLO_AGENTS_UI_HOST", "0.0.0.0")
    # 服务器/无图形环境设 HELLO_AGENTS_UI_INBROWSER=0，避免弹浏览器
    inbrowser = os.getenv("HELLO_AGENTS_UI_INBROWSER", "1").lower() in ("1", "true", "yes")
    kwargs = dict(server_name=host, server_port=port, inbrowser=inbrowser)

    user = os.getenv("UI_AUTH_USER", "").strip()
    pwd = os.getenv("UI_AUTH_PASS", "").strip()
    if user and pwd:
        kwargs["auth"] = (user, pwd)
        print(f"[run_ui] 登录保护已启用（账号 {user}）")
    else:
        print("[run_ui] 未启用登录保护（如需设置 UI_AUTH_USER/UI_AUTH_PASS）")

    print(f"[run_ui] 平台启动 http://{host}:{port}（局域网手机直连 http://<电脑IP>:{port}）")
    demo.launch(**kwargs)


if __name__ == "__main__":
    main()
