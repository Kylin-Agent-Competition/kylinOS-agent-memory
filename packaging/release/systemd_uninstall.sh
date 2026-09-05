#!/usr/bin/env bash
# =============================================================================
# D14A systemd --user uninstall / rollback（无源码/无个人 venv 依赖）
# 用法: bash uninstall.sh rollback [--keep-unit] [--keep-prefix]
#   默认删除 install_prefix、恢复 unit/symlink 备份。
#   --keep-prefix: 保留已安装的发布包目录（仅停止/禁用服务 + 移除 symlink/unit）
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
BIN_SYMLINK="$HOME/.local/bin/kylin-memory-server"
INSTALL_PREFIX="${INSTALL_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory-d14a}"
KEEP_UNIT=0
KEEP_PREFIX=0

[ "${1:-}" = "rollback" ] || { echo "用法: $0 rollback [--keep-unit] [--keep-prefix]" >&2; exit 2; }
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --keep-unit) KEEP_UNIT=1; shift ;;
    --keep-prefix) KEEP_PREFIX=1; shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[d14a-rollback] $*"; }

systemctl --user stop "$UNIT_NAME" 2>/dev/null || true
systemctl --user disable "$UNIT_NAME" 2>/dev/null || true

# ── 移除 symlink（恢复备份或删除） ──
if [ -e "$BIN_SYMLINK" ] || [ -L "$BIN_SYMLINK" ]; then
  rm -f "$BIN_SYMLINK"
  log "已移除 symlink: $BIN_SYMLINK"
fi

# ── unit 恢复备份或删除 ──
if [ "$KEEP_UNIT" -eq 0 ]; then
  local_unit_bak="$(ls -1t "$UNIT_DST".bak.* 2>/dev/null | head -1 || true)"
  if [ -n "$local_unit_bak" ] && [ -f "$local_unit_bak" ]; then
    mv -f "$local_unit_bak" "$UNIT_DST"
    log "已恢复原 unit: $(basename "$local_unit_bak")"
  else
    rm -f "$UNIT_DST"
    log "已删除 unit: $UNIT_DST"
  fi
  rm -f "$UNIT_DST".bak.*
  systemctl --user daemon-reload
else
  log "已停止并禁用 ${UNIT_NAME}（--keep-unit）"
fi

# ── 移除 install_prefix ──
if [ "$KEEP_PREFIX" -eq 0 ] && [ -d "$INSTALL_PREFIX" ]; then
  rm -rf "$INSTALL_PREFIX"
  log "已移除 install_prefix: $INSTALL_PREFIX"
  # 清理备份 prefix
  rm -rf "$INSTALL_PREFIX".bak.*
fi

systemctl --user is-active --quiet "$UNIT_NAME" \
  && { echo "[d14a-rollback] ERROR: 服务仍 active" >&2; exit 1; } || true

log "回退完成：服务已停止/禁用，symlink 已移除，prefix 处理完成"