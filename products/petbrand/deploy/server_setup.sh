#!/usr/bin/env bash
# ============================================================
# 爪案（petbrand）—— 服务器一键初始化（Ubuntu 22.04 / 24.04，root 运行）
#
# 前置：把 petbrand-server.tar.gz 上传并解压到 /opt/petbrand
#   sudo mkdir -p /opt/petbrand
#   sudo tar -xzf petbrand-server.tar.gz -C /opt --strip-components=1
#
# 运行：
#   sudo bash /opt/petbrand/server_setup.sh
#
# 可选：
#   UI_USER=xxx   UI 登录账号（默认 admin）
#   UI_PASS=xxx   指定 UI 密码（不指定则自动生成并打印）
#   NO_START=1    只装依赖+做 import 冒烟，不起服务（调试用）
# ============================================================
set -euo pipefail

APP_DIR="/opt/petbrand"
UI_USER="${UI_USER:-admin}"
UI_PASS="${UI_PASS:-$(openssl rand -hex 8)}"
NO_START="${NO_START:-0}"

log(){ echo -e "\033[1;32m[SETUP]\033[0m $*"; }
warn(){ echo -e "\033[1;33m[WARN]\033[0m $*"; }

if [ "$(id -u)" != "0" ]; then
  echo "请用 root 运行: sudo bash /opt/petbrand/server_setup.sh"; exit 1
fi
if [ ! -d "$APP_DIR" ]; then
  echo "缺少 $APP_DIR —— 请先解压部署包到该目录"; exit 1
fi

export DEBIAN_FRONTEND=noninteractive

log "=== 1/5 系统软件包 ==="
apt-get update -y
apt-get install -y python3 python3-venv python3-pip openssl

log "=== 2/5 目录与运行用户 ==="
id -u www-data >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin www-data
mkdir -p "$APP_DIR/outputs" "$APP_DIR/memory_data"
cd "$APP_DIR"

log "=== 3/5 Python venv + 依赖（阿里云镜像） ==="
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install -U pip wheel
"$APP_DIR/venv/bin/pip" install -i https://mirrors.aliyun.com/pypi/simple/ \
  -r "$APP_DIR/requirements.txt"

log "=== import 冒烟：build_ui 可组装（不起服务） ==="
"$APP_DIR/venv/bin/python" -c "from petbrand.app import build_ui; build_ui(); print('[smoke] build_ui OK')"
"$APP_DIR/venv/bin/python" -c "from petbrand.tools.petresearch.docx_export import HAS_DOCX; print('[smoke] python-docx available:', HAS_DOCX)"

if [ "$NO_START" = "1" ]; then
  warn "NO_START=1 —— 未启动服务。"
  exit 0
fi

log "=== 4/5 登录保护 + systemd ==="
cat > /etc/petbrand-ui.env <<EOF
UI_AUTH_USER=$UI_USER
UI_AUTH_PASS=$UI_PASS
EOF
chmod 600 /etc/petbrand-ui.env
chmod 600 "$APP_DIR/.env"
cp "$APP_DIR/petbrand.service" /etc/systemd/system/petbrand.service
systemctl daemon-reload

log "=== 5/5 权限与启动 ==="
chown -R www-data:www-data "$APP_DIR"
systemctl enable petbrand >/dev/null 2>&1 || true
systemctl restart petbrand
sleep 12
systemctl --no-pager --full status petbrand || true

IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<服务器IP>")
log "============================================================"
log "部署完成！爪案访问:  http://${IP}:7865  (与小麦共用单口，见 agent-switch.sh)"
log "登录账号:  ${UI_USER}"
log "登录密码:  ${UI_PASS}"
log "提示：petbrand.service 绑定 7865，与 hello-agents 互斥 —— 启动前须先停小麦"
log "     （bash /opt/agent-switch.sh petbrand）。7865 已放行安全组，无需再放新端口。"
log "     改密码：编辑 /etc/petbrand-ui.env 后 systemctl restart petbrand"
log "============================================================"
