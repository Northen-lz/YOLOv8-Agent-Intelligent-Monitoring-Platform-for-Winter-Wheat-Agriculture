# -*- coding: utf-8 -*-
"""打包部署包：代码 + .env + 模型权重 + 评估CSV + 服务器初始化脚本 → tar.gz

用法（在项目根目录运行）:
    D:\\pyhon\\ana\\ana3\\python.exe deploy\\pack_deploy.py

产物:
    deploy/hello-agents-server.tar.gz  （解压后目录名 hello-agents-server/，
    上传到服务器后解压到 /opt/hello-agents 即可运行 server_setup.sh）
"""
import os
import shutil
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 外部视觉系统根目录（只读取模型权重/评估CSV，不改任何代码）
EXT = r"D:\pyhon\vscode-xiaomai"

DEST = os.path.join(ROOT, "deploy", "hello-agents-server.tar.gz")
TMP = os.path.join(tempfile.gettempdir(), "ha-pack-root")

# 从项目根拷入打包根目录的文件/目录
PROJECT_COPY = ["hello_agents", "run_ui.py", ".env"]

# 从 deploy/ 拷入的服务器初始化文件
DEPLOY_COPY = [
    ("requirements.txt", "requirements.txt"),
    ("server_setup.sh", "server_setup.sh"),
    ("hello-agents.service", "hello-agents.service"),
]

# 天气 MCP 服务器已随 hello_agents/ 整体打包（tools/agriculture/weather_mcp_server.py）

# 外部视觉系统 → 打包根 xiaomai/ 镜像（模拟 vscode-xiaomai 目录结构，供路径覆盖）
XIAOMAI_COPY = [
    (os.path.join(EXT, "models", "detector", "yolov8s", "weights", "best.pt"),
     os.path.join("xiaomai", "models", "detector", "yolov8s", "weights", "best.pt")),
    (os.path.join(EXT, "models", "classifier", "exp_augmented2_s", "weights", "best.onnx"),
     os.path.join("xiaomai", "models", "classifier", "exp_augmented2_s", "weights", "best.onnx")),
    (os.path.join(EXT, "outputs", "classifier_model_comparison.csv"),
     os.path.join("xiaomai", "outputs", "classifier_model_comparison.csv")),
]

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache"}


def _copytree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in SKIP_DIRS:
            continue
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            _copytree(s, d)
        else:
            shutil.copy2(s, d)


def main():
    if os.path.isdir(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP)

    for name in PROJECT_COPY:
        s = os.path.join(ROOT, name)
        if not os.path.exists(s):
            print(f"[warn] 项目缺少 {name}，跳过")
            continue
        if os.path.isdir(s):
            _copytree(s, os.path.join(TMP, name))
        else:
            shutil.copy2(s, os.path.join(TMP, name))

    for name, rel in DEPLOY_COPY:
        s = os.path.join(ROOT, "deploy", name)
        if not os.path.exists(s):
            print(f"[warn] 部署脚本缺少 {name}，跳过")
            continue
        shutil.copy2(s, os.path.join(TMP, rel))

    for src, rel in XIAOMAI_COPY:
        if not os.path.exists(src):
            print(f"[warn] 外部系统缺少 {src}，跳过")
            continue
        d = os.path.join(TMP, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(src, d)


    if os.path.exists(DEST):
        os.remove(DEST)
    with tarfile.open(DEST, "w:gz") as tf:
        tf.add(TMP, arcname="hello-agents-server")

    size_mb = os.path.getsize(DEST) / 1024 / 1024
    print(f"[ok] 部署包已生成: {DEST}  ({size_mb:.1f} MB)")
    shutil.rmtree(TMP)


if __name__ == "__main__":
    main()
