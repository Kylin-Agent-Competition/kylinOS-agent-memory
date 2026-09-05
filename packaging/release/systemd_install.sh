#!/usr/bin/env bash
# =============================================================================
# D14A systemd --user install（无源码/无个人 venv 依赖）
# 用法: bash install.sh install
# 前置: 本脚本位于发布包 systemd/ 目录；包内已含 runtime/{app,bridge,python}
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$SELF_DIR/.." && pwd)"           # 发布包根
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
BIN_DST="$HOME/.local/bin/kylin-memory-server"

log() { echo "[d14a-install] $*"; }
die() { echo "[d14a-install] ERROR: $*" >&2; exit 1; }

# ── 前置系统依赖校验（contract §3，fail-closed） ──
[ -f "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0" ] \
  || die "前置依赖缺失: libkysdk-coreai-embedding.so.1.0.0"
[ -x "$PKG_DIR/runtime/python/bin/python" ] || die "包内 venv 缺失: runtime/python"
[ -f "$PKG_DIR/runtime/app/app.py" ] || die "包内 app 缺失: runtime/app"
[ -n "$(ls "$PKG_DIR"/runtime/bridge/kylin_embedding*.so 2>/dev/null)" ] \
  || die "包内 bridge 缺失: runtime/bridge"

# ── 服务数据目录（确定 0700） ──
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user" \
  "$HOME/.config/kylin-memory" "$HOME/.local/share/kylin-memory" "$HOME/.local/state/kylin-memory"
chmod 0700 "$HOME/.config/kylin-memory" "$HOME/.local/share/kylin-memory" "$HOME/.local/state/kylin-memory"

# ── launcher（指向发布包，可重定位） ──
if [ -f "$BIN_DST" ]; then
  cp -f "$BIN_DST" "$BIN_DST.bak.$(date +%Y%m%d_%H%M%S)"
fi
cp -f "$PKG_DIR/bin/kylin-memory-server" "$BIN_DST"
chmod 0755 "$BIN_DST"

# ── unit（%h = $HOME，%t = $XDG_RUNTIME_DIR） ──
if [ -f "$UNIT_DST" ]; then
  cp -f "$UNIT_DST" "$UNIT_DST.bak.$(date +%Y%m%d_%H%M%S)"
fi
cp -f "$SELF_DIR/kylin-memory.service" "$UNIT_DST"

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"
sleep 3
systemctl --user is-active --quiet "$UNIT_NAME" || die "服务未 active"

log "安装完成: launcher=$BIN_DST unit=$UNIT_DST"
log "socket: $XDG_RUNTIME_DIR/kylin-memory/memory.sock（或 --socket 覆盖）"