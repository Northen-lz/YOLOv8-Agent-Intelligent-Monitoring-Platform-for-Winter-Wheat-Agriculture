# -*- coding: utf-8 -*-
"""打包小麦产品的云部署包：产品代码 + 框架源码 + .env + 模型权重 + 服务器脚本 → tar.gz

说明（monorepo 拆分后）：
- 服务器不安装 ha_framework 的 pip 包，而是把 framework/ha_framework 源码目录
  一并打进 tar 包解压到运行根 —— run_ui.py 会把自己的目录插入 sys.path，
  因此 /opt/hello-agents 下同时 import wheat（产品）与 ha_framework（框架）都能命中。
- 部署包只装小麦产品所需依赖，见 deploy/requirements.txt。

用法（仓库根运行，DEST 落在 deploy/ 内）：
    D:\\pyhon\\ana\\ana3\\python.exe products\\wheat\\deploy\\pack_deploy.py

产物:
    products/wheat/deploy/hello-agents-server.tar.gz  （解压后目录名 hello-agents-server/，
    上传到服务器后解压到 /opt/hello-agents 即可运行 server_setup.sh）
"""
import os
import shutil
import tarfile
import tempfile

# 仓库根 = deploy/../.. （products/wheat/deploy -> 仓库根）
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PRODUCT_ROOT = os.path.join(REPO_ROOT, "products", "wheat")
WHEAT_PKG = os.path.join(PRODUCT_ROOT, "wheat")
FRAMEWORK_PKG = os.path.join(REPO_ROOT, "framework", "ha_framework")
# 外部视觉系统根目录（只读取模型权重/评估CSV，不改任何代码）
EXT = r"D:\pyhon\vscode-xiaomai"

DEST = os.path.join(PRODUCT_ROOT, "deploy", "hello-agents-server.tar.gz")
TMP = os.path.join(tempfile.gettempdir(), "ha-pack-root")

# 从产品根拷入打包根目录的文件/目录（服务器 sys.path 根）
PROJECT_COPY = [
    ("wheat", "wheat"),
    (os.path.join(PRODUCT_ROOT, "run_ui.py"), "run_ui.py"),
]
# 框架源码（服务器直接用 sys.path 导入，无需 pip 安装）
FRAMEWORK_COPY = ("ha_framework", "ha_framework")
# 从仓库根拷入共享密钥（LLM key / Qdrant / Neo4j / 嵌入方案）
ENV_SRC = os.path.join(REPO_ROOT, ".env")

# 从 deploy/ 拷入的服务器初始化文件
DEPLOY_COPY = [
    ("requirements.txt", "requirements.txt"),
    ("server_setup.sh", "server_setup.sh"),
    ("hello-agents.service", "hello-agents.service"),
]

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

    for src, rel in PROJECT_COPY:
        if not os.path.exists(src):
            print(f"[warn] 缺少 {src}，跳过")
            continue
        if os.path.isdir(src):
            _copytree(src, os.path.join(TMP, rel))
        else:
            shutil.copy2(src, os.path.join(TMP, rel))

    # 框架源码目录
    if not os.path.isdir(FRAMEWORK_PKG):
        print(f"[warn] 缺少框架源码 {FRAMEWORK_PKG}，跳过")
    else:
        _copytree(FRAMEWORK_PKG, os.path.join(TMP, FRAMEWORK_COPY[0]))

    # 共享 .env
    if os.path.exists(ENV_SRC):
        shutil.copy2(ENV_SRC, os.path.join(TMP, ".env"))
    else:
        print("[warn] 缺少仓库根 .env，跳过（服务器将无法读 LLM key）")

    for name, rel in DEPLOY_COPY:
        s = os.path.join(PRODUCT_ROOT, "deploy", name)
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
