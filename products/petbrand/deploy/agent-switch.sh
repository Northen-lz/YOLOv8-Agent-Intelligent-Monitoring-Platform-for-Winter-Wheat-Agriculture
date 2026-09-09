#!/usr/bin/env bash
# ============================================================
# 单端口热切换器：http://<公网IP>:7865 在「爪案(petbrand)」与「小麦(hello-agents)」间来回切换
#
# 两个服务都绑定同一个对外端口 7865（已在云安全组放行）；同一时刻只跑一个，
# 本脚本保证互斥：切到目标前先停掉并禁用另一个，只启用目标，重启目标使新配置生效。
#
# 用法（root）:
#   bash /opt/agent-switch.sh petbrand    # 停小麦 → 启爪案（公网 7865 变爪案登录页）
#   bash /opt/agent-switch.sh wheat       # 停爪案 → 启小麦（公网 7865 变小麦登录页）
#   bash /opt/agent-switch.sh status      # 查看两服务状态与当前占用
#   bash /opt/agent-switch.sh stop        # 两个都停（维护用）
#
# 说明：切换会让公网 7865 短暂不可用数十秒（服务重启加载时间，爪案约15s、小麦含torch约1分钟）。
# ============================================================
set -euo pipefail

PET_UNIT=petbrand          # 爪案
WHEAT_UNIT=hello-agents    # 小麦
PORT=7865

switch_on(){  # $1=run-unit  $2=stop-unit
  local run="$1" stop="$2"
  systemctl stop "$stop" >/dev/null 2>&1 || true      # 先放掉端口（同步等待退出）
  systemctl disable "$stop" >/dev/null 2>&1 || true    # 禁用被切掉的服务，防重启时双启
  systemctl enable "$run" >/dev/null 2>&1 || true
  systemctl restart "$run"                             # 重启目标，应用最新单元/配置
  systemctl is-active "$stop" >/dev/null 2>&1 && systemctl stop "$stop" >/dev/null 2>&1 || true
}

do_status(){
  for u in "$PET_UNIT" "$WHEAT_UNIT"; do
    st=$(systemctl is-active "$u" 2>/dev/null || echo inactive)
    en=$(systemctl is-enabled "$u" 2>/dev/null || echo unknown)
    printf '%-13s active=%-9s enabled=%s\n' "$u" "$st" "$en"
  done
  echo "--- 谁占 0.0.0.0:$PORT ---"
  ss -ltnp 2>/dev/null | grep ":$PORT " || echo "（无服务监听 7865）"
}

case "${1:-status}" in
  petbrand) systemctl daemon-reload; switch_on "$PET_UNIT" "$WHEAT_UNIT"; echo "[switch] 爪案已上线 http://<公网IP>:$PORT"; do_status;;
  wheat)    systemctl daemon-reload; switch_on "$WHEAT_UNIT" "$PET_UNIT"; echo "[switch] 小麦已上线 http://<公网IP>:$PORT"; do_status;;
  stop)     systemctl disable --now "$PET_UNIT" >/dev/null 2>&1 || true; systemctl disable --now "$WHEAT_UNIT" >/dev/null 2>&1 || true; echo "[switch] 两个服务均已停止"; do_status;;
  status|*) do_status;;
esac
