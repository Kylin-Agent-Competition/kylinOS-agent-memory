#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Service — systemd --user 安装/重启/回退/状态脚本（D11D 草案）
# =============================================================================
# 用法:
#   bash install_kylin_memory.sh install  [--python <venv-python>] [--repo <repo-dir>] [--socket <path>]
#   bash install_kylin_memory.sh restart
#   bash install_kylin_memory.sh status
#   bash install_kylin_memory.sh rollback [--keep-unit]   # 停止+禁用；默认删除本脚本安装的 wrapper 与 unit（先备份）
#
# 依据:
#   - 部署冻结: deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md
#   - D4D 麒麟 VM L2 人工验证第 3 步: evidence/l2-kylin-vm/d4d_vm_verify_20260821/d4d_vm_l2_manual_verify_20260821.md（commit ed9949c）
#   - unit 冻结骨架: packaging/systemd/kylin-memory.service（本脚本不修改）
#
# ✅ 状态: HOST_VERIFIED —— 已在 D11D 专用麒麟 VM（Kylin-V11-2603-D11D-47af2fa-Test，
#    origin/main@47af2fa）执行 L2 通过：install/restart/rollback/reinstall/socket/journal，
#    证据见 evidence/l2-kylin-vm/d11d_vm_service_l2_20260902.md（index.yaml: D11D-L2-SERVICE-LIFECYCLE）。
#    正式发行环境（生产 Kylin）systemd 仍未验证。
# =============================================================================

set -euo pipefail

UNIT_NAME="kylin-memory"
UNIT_SRC="$(cd "$(dirname "$0")" && pwd)/kylin-memory.service"
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
BIN_DST="$HOME/.local/bin/kylin-memory-server"

ACTION="${1:-install}"
shift || true
PYTHON_BIN="${PYTHON_BIN:-}"
REPO_DIR="${REPO_DIR:-}"
SOCKET_PATH="${SOCKET_PATH:-}"
KEEP_UNIT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --python) PYTHON_BIN="$2"; shift 2 ;;
    --repo) REPO_DIR="$2"; shift 2 ;;
    --socket) SOCKET_PATH="$2"; shift 2 ;;
    --keep-unit) KEEP_UNIT=1; shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[kylin-memory-install] $*"; }
die() { echo "[kylin-memory-install] ERROR: $*" >&2; exit 1; }

resolve_socket() {
  if [ -n "$SOCKET_PATH" ]; then
    echo "$SOCKET_PATH"
  else
    echo "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock"
  fi
}

preflight() {
  if [ -z "$REPO_DIR" ]; then
    for cand in "$PWD" "$PWD/../.." "$HOME/kylinOS-agent-memory"; do
      if [ -f "$cand/memory-service/app.py" ]; then REPO_DIR="$cand"; break; fi
    done
  fi
  [ -n "$REPO_DIR" ] && [ -f "$REPO_DIR/memory-service/app.py" ] \
    || die "未找到 memory-service/app.py（可用 --repo 指定）"
  if [ -z "$PYTHON_BIN" ]; then
    for cand in "$HOME/d4d-venv/bin/python" "$HOME/.venv/bin/python"; do
      [ -x "$cand" ] && { PYTHON_BIN="$cand"; break; }
    done
  fi
  [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ] || die "未找到 venv python（可用 --python 指定）"
  [ -f "$UNIT_SRC" ] || die "未找到 unit 文件: $UNIT_SRC"
  # TD-DEPLOY-001 教训：安装 unit 前先确认运行时依赖齐备，避免先装后缺二进制/依赖
  "$PYTHON_BIN" -c "import sqlalchemy, alembic, pydantic" \
    || die "venv 缺少依赖（sqlalchemy/alembic/pydantic），请先: $PYTHON_BIN -m pip install -r $REPO_DIR/memory-service/requirements.txt"
}

wait_socket() {
  local sock="$1" i
  for i in $(seq 1 20); do
    [ -S "$sock" ] && return 0
    sleep 0.5
  done
  return 1
}

status_check() {
  systemctl --user is-active --quiet "$UNIT_NAME" || die "服务未处于 active (running)"
  local sock; sock="$(resolve_socket)"
  wait_socket "$sock" || die "socket 未就绪: $sock"
  log "socket OK: $sock"
  systemctl --user status "$UNIT_NAME" --no-pager | head -6
  # 日志就绪断言（允许短暂延迟后重试）
  local i
  for i in $(seq 1 10); do
    if journalctl --user -u "$UNIT_NAME" -n 100 --no-pager 2>/dev/null | grep -q "Memory Service 就绪"; then
      log "journal: Memory Service 就绪 已出现"
      return 0
    fi
    sleep 0.5
  done
  log "WARN: 日志中未匹配到 'Memory Service 就绪'（请人工核对 journalctl --user -u $UNIT_NAME）"
}

do_install() {
  preflight
  mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
  # 3.1 创建 ExecStart 入口 wrapper（unit 骨架 ExecStart=%h/.local/bin/kylin-memory-server，不改 unit 冻结文件）
  printf '#!/bin/bash\nexec %q %q "$@"\n' "$PYTHON_BIN" "$REPO_DIR/memory-service/app.py" > "$BIN_DST"
  chmod +x "$BIN_DST"
  # 3.2 备份既有 unit 后安装并启动
  if [ -f "$UNIT_DST" ]; then
    cp -f "$UNIT_DST" "$UNIT_DST.bak.$(date +%Y%m%d_%H%M%S)"
    log "已备份既有 unit: $UNIT_DST.bak.*"
  fi
  cp -f "$UNIT_SRC" "$UNIT_DST"
  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT_NAME"
  sleep 2
  # 3.3 状态/socket/日志
  status_check
  # 3.4 重启验证
  log "重启验证…"
  systemctl --user restart "$UNIT_NAME"
  sleep 2
  status_check
  log "安装完成：wrapper=$BIN_DST unit=$UNIT_DST"
}

do_restart() {
  systemctl --user restart "$UNIT_NAME"
  sleep 2
  status_check
}

do_status() {
  status_check
}

do_rollback() {
  systemctl --user stop "$UNIT_NAME" 2>/dev/null || true
  systemctl --user disable "$UNIT_NAME" 2>/dev/null || true
  if [ "$KEEP_UNIT" -eq 0 ]; then
    rm -f "$BIN_DST"
    rm -f "$UNIT_DST"
    systemctl --user daemon-reload
    log "回退完成：已停止并禁用 ${UNIT_NAME}，已删除 wrapper 与 unit"
  else
    log "回退完成：已停止并禁用 ${UNIT_NAME}（--keep-unit：保留 wrapper 与 unit）"
  fi
  systemctl --user is-active --quiet "$UNIT_NAME" && die "回退后服务仍为 active" || true
}

case "$ACTION" in
  install) do_install ;;
  restart) do_restart ;;
  status) do_status ;;
  rollback) do_rollback ;;
  *) echo "用法: $0 {install|restart|status|rollback} [选项]" >&2; exit 2 ;;
esac