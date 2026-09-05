#!/usr/bin/env bash
# =============================================================================
# D14A systemd --user uninstall / rollback（无源码/无个人 venv 依赖）
# 用法: bash uninstall.sh rollback [--keep-unit]
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
BIN_DST="$HOME/.local/bin/kylin-memory-server"
KEEP_UNIT=0

[ "${1:-}" = "rollback" ] || { echo "用法: $0 rollback [--keep-unit]" >&2; exit 2; }
shift || true
[ "${1:-}" = "--keep-unit" ] && KEEP_UNIT=1

systemctl --user stop "$UNIT_NAME" 2>/dev/null || true
systemctl --user disable "$UNIT_NAME" 2>/dev/null || true

if [ "$KEEP_UNIT" -eq 0 ]; then
  local_unit_bak="$(ls -1t "$UNIT_DST".bak.* 2>/dev/null | head -1 || true)"
  local_bin_bak="$(ls -1t "$BIN_DST".bak.* 2>/dev/null | head -1 || true)"
  if [ -n "$local_unit_bak" ] && [ -f "$local_unit_bak" ]; then
    mv -f "$local_unit_bak" "$UNIT_DST"
  else
    rm -f "$UNIT_DST"
  fi
  if [ -n "$local_bin_bak" ] && [ -f "$local_bin_bak" ]; then
    mv -f "$local_bin_bak" "$BIN_DST"
  else
    rm -f "$BIN_DST"
  fi
  rm -f "$UNIT_DST".bak.* "$BIN_DST".bak.*
  systemctl --user daemon-reload
  echo "[d14a-rollback] 已停止并禁用 ${UNIT_NAME}，恢复安装前状态"
else
  echo "[d14a-rollback] 已停止并禁用 ${UNIT_NAME}（--keep-unit）"
fi

systemctl --user is-active --quiet "$UNIT_NAME" && { echo "[d14a-rollback] ERROR: 服务仍 active" >&2; exit 1; } || true