#!/usr/bin/env bash
# ============================================================
# YOLOv8-Agent 平台 —— 服务器一键初始化（Ubuntu 22.04 / 24.04，root 运行）
#
# 前置：把 hello-agents-server.tar.gz 上传并解压到 /opt/hello-agents
#   sudo mkdir -p /opt/hello-agents
#   sudo tar -xzf hello-agents-server.tar.gz -C /opt --strip-components=1
#
# 运行：
#   sudo bash /opt/hello-agents/server_setup.sh
#
# 可选环境开关（默认关）：
#   NEO4J=1    启用 Neo4j 图数据库（Docker；4G 内存机型有 OOM 风险，默认关）
#   OLLAMA=1   启用 Ollama 视觉模型 qwen2.5vl:3b（CPU 推理极慢，默认关；
#              Vision 门控会自动降级为 YOLOv8 检测，不影响小麦检测）
#   UI_USER=xxx   UI 登录账号（默认 admin）
#   UI_PASS=xxx   指定 UI 密码（不指定则自动生成并打印）
# ============================================================
set -euo pipefail

APP_DIR="/opt/hello-agents"
NEO4J="${NEO4J:-0}"
OLLAMA="${OLLAMA:-0}"
UI_USER="${UI_USER:-admin}"
UI_PASS="${UI_PASS:-$(openssl rand -hex 8)}"

log(){ echo -e "\033[1;32m[SETUP]\033[0m $*"; }
warn(){ echo -e "\033[1;33m[WARN]\033[0m $*"; }

if [ "$(id -u)" != "0" ]; then
  echo "请用 root 运行: sudo bash /opt/hello-agents/server_setup.sh"; exit 1
fi
if [ ! -d "$APP_DIR" ]; then
  echo "缺少 $APP_DIR —— 请先解压部署包到该目录"; exit 1
fi

export DEBIAN_FRONTEND=noninteractive

log "=== 1/7 系统软件包 ==="
apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl unzip openssl docker.io docker-compose-v2

log "=== 2/7 目录与运行用户 ==="
id -u www-data >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin www-data
mkdir -p "$APP_DIR/outputs" "$APP_DIR/memory_data"
cd "$APP_DIR"

log "=== 3/7 Python venv + 依赖 ==="
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install -U pip wheel
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
log "安装 torch CPU 版（约 200MB，避免误装 CUDA 大包）..."
"$APP_DIR/venv/bin/pip" install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
"$APP_DIR/venv/bin/pip" install ultralytics==8.1.34

log "=== 4/7 数据库与可选服务 ==="
systemctl enable docker --now >/dev/null 2>&1 || true
if ! docker inspect qdrant >/dev/null 2>&1; then
  docker run -d --name qdrant --restart=always -p 6333:6333 qdrant/qdrant:latest
  log "Qdrant 向量库已启动 (localhost:6333)"
fi
if [ "$NEO4J" = "1" ]; then
  if ! docker inspect neo4j >/dev/null 2>&1; then
    docker run -d --name neo4j --restart=always -p 7474:7474 -p 7687:7687 \
      -e NEO4J_AUTH=neo4j/hello-agents-password neo4j:5
    log "Neo4j 图库已启动 (bolt://localhost:7687, neo4j/hello-agents-password)"
  fi
fi
if [ "$OLLAMA" = "1" ]; then
  if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  systemctl enable ollama --now >/dev/null 2>&1 || true
  ollama pull qwen2.5vl:3b || warn "qwen2.5vl:3b 拉取失败（可稍后 ollama pull 重试）"
fi

log "=== 5/7 systemd 服务 ==="
cat > /etc/hello-agents-ui.env <<EOF
UI_AUTH_USER=$UI_USER
UI_AUTH_PASS=$UI_PASS
EOF
chmod 600 /etc/hello-agents-ui.env
cp "$APP_DIR/hello-agents.service" /etc/systemd/system/hello-agents.service
systemctl daemon-reload

log "=== 6/7 权限 ==="
chown -R www-data:www-data "$APP_DIR"

log "=== 7/7 启动 ==="
systemctl enable hello-agents >/dev/null 2>&1 || true
systemctl restart hello-agents
sleep 10
systemctl --no-pager --full status hello-agents || true

IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<服务器IP>")
log "============================================================"
log "部署完成！手机访问:  http://${IP}:7865"
log "登录账号:  ${UI_USER}"
log "登录密码:  ${UI_PASS}"
log "提示：云控制台安全组需放行 TCP 7865（来源 0.0.0.0/0）。"
log "     建议访问一次后，把安全组来源收紧到常用 IP。"
log "============================================================"
