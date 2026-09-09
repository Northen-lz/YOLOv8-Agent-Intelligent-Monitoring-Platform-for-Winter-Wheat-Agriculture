# -*- coding: utf-8 -*-
"""
爪案（petbrand）· 猫狗品牌全案策划 Agent —— 一键启动脚本

与 python -m petbrand.app 的区别：
- 绑定 0.0.0.0 -> 同一 WiFi 的手机可直连 http://<电脑IP>:<port>
- 支持可选登录保护 UI_AUTH_USER / UI_AUTH_PASS（公网暴露强烈建议开启）

用法（products/petbrand 目录）：
    D:/pyhon/ana/ana3/python.exe run_ui.py

环境变量：
    PETBRAND_UI_HOST     默认 0.0.0.0（只需本机访问可设 127.0.0.1）
    PETBRAND_UI_PORT     默认 7866（避免与小麦 7865 冲突）
    UI_AUTH_USER / UI_AUTH_PASS   同时设置则启用登录保护
"""
import os
import sys

# 产品根目录（Config 数据根/知识库/场景/攒案产物等都相对它解析）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_PROJECT_ROOT)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
# 让 ha_framework 的记忆/RAG 等数据根也落到产品目录（须在任何 import 之前设置）
os.environ.setdefault("HA_DATA_ROOT", _PROJECT_ROOT)

# 在 import build_ui 之前设置，让平台以 0.0.0.0 暴露
os.environ.setdefault("PETBRAND_UI_HOST", "0.0.0.0")


def main():
    from petbrand.app import build_ui

    demo = build_ui()
    port = int(os.getenv("PETBRAND_UI_PORT", "7866"))
    host = os.getenv("PETBRAND_UI_HOST", "0.0.0.0")
    inbrowser = os.getenv("PETBRAND_UI_INBROWSER", "1").lower() in ("1", "true", "yes")
    kwargs = dict(server_name=host, server_port=port, inbrowser=inbrowser)

    user = os.getenv("UI_AUTH_USER", "").strip()
    pwd = os.getenv("UI_AUTH_PASS", "").strip()
    if user and pwd:
        kwargs["auth"] = (user, pwd)
        print(f"[run_ui] 登录保护已启用（账号 {user}）")
    else:
        print("[run_ui] 未启用登录保护（如需设置 UI_AUTH_USER/UI_AUTH_PASS）")

    print(f"[run_ui] 爪案·品牌全案平台启动 http://{host}:{port}（局域网直连 http://<电脑IP>:{port}）")
    demo.launch(**kwargs)


if __name__ == "__main__":
    main()
