# -*- coding: utf-8 -*-
"""打包爪案（petbrand）的云部署包：产品代码 + 场景 + 框架源码 + .env + 服务器脚本 → tar.gz

说明（monorepo 拆分后，与 products/wheat/deploy/pack_deploy.py 同构）：
- 服务器不 pip 安装 ha_framework，而是把 framework/ha_framework 源码目录一并打进 tar，
  run_ui.py 把运行根插入 sys.path —— /opt/petbrand 下同时 import petbrand、ha_framework 均命中。
- 服务器依赖只装爪案所需，见 deploy/requirements.txt（已按 framework import-time 硬需求收窄，
  gradio 5.45 + starlette 0.47.3 + mcp 1.29 为实测可 launch 组合）。
- .env 从仓库根拷贝（LLM key 等，含金量高，解压后 chmod 600，勿提交仓库）。

用法（仓库根运行）：
    D:\\pyhon\\ana\\ana3\\python.exe products\\petbrand\\deploy\\pack_deploy.py

产物:
    products/petbrand/deploy/petbrand-server.tar.gz
    （解压后目录名 petbrand-server/，上传服务器后解压到 /opt/petbrand 再跑 server_setup.sh）
"""
import os
import shutil
import tarfile
import tempfile

# 仓库根 = deploy/../../..（products/petbrand/deploy -> 仓库根）
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PRODUCT_ROOT = os.path.join(REPO_ROOT, "products", "petbrand")
PETBRAND_PKG = os.path.join(PRODUCT_ROOT, "petbrand")
FRAMEWORK_PKG = os.path.join(REPO_ROOT, "framework", "ha_framework")

DEST = os.path.join(PRODUCT_ROOT, "deploy", "petbrand-server.tar.gz")
TMP = os.path.join(tempfile.gettempdir(), "petbrand-pack-root")

# 从产品根拷入打包根（= 服务器运行根 /opt/petbrand）的文件/目录
PROJECT_COPY = [
    (PETBRAND_PKG, "petbrand"),                       # 产品包
    (os.path.join(PRODUCT_ROOT, "run_ui.py"), "run_ui.py"),
    (os.path.join(PRODUCT_ROOT, "scenarios"), "scenarios"),  # 内置演示品牌 brief
]
# 框架源码（服务器直接 sys.path 导入，无需 pip）
FRAMEWORK_COPY = ("ha_framework", "ha_framework")
# 从仓库根拷入共享密钥（LLM key / Qdrant / Neo4j / 嵌入方案）
ENV_SRC = os.path.join(REPO_ROOT, ".env")

# 从 deploy/ 拷入的服务器初始化文件
DEPLOY_COPY = [
    ("requirements.txt", "requirements.txt"),
    ("server_setup.sh", "server_setup.sh"),
    ("petbrand.service", "petbrand.service"),
]

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", "outputs"}


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
        os.chmod(os.path.join(TMP, ".env"), 0o600)
    else:
        print("[warn] 缺少仓库根 .env，跳过（服务器将无法读 LLM key）")

    for name, rel in DEPLOY_COPY:
        s = os.path.join(PRODUCT_ROOT, "deploy", name)
        if not os.path.exists(s):
            print(f"[warn] 部署脚本缺少 {name}，跳过")
            continue
        shutil.copy2(s, os.path.join(TMP, rel))

    if os.path.exists(DEST):
        os.remove(DEST)
    with tarfile.open(DEST, "w:gz") as tf:
        tf.add(TMP, arcname="petbrand-server")

    size_mb = os.path.getsize(DEST) / 1024 / 1024
    print(f"[ok] 部署包已生成: {DEST}  ({size_mb:.2f} MB)")
    shutil.rmtree(TMP)


if __name__ == "__main__":
    main()
