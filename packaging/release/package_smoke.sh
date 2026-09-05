#!/usr/bin/env bash
# =============================================================================
# D14A package smoke — 自动化可重复发布链验证（复审最低条件第 5 条）
# 覆盖: install → migration → service start → verify(real SDK) → restart → rollback
# 用法: bash package_smoke.sh [--package <pkg-dir>] [--prefix <install-prefix>]
# 前置: 真实 SDK 已装；当前用户 systemd --user 可用；embedding.server 由外部提供
#       （本 smoke 通过已注册的 embedding.sock 或本地启动验证真实 SDK）
# 退出码: 0 = 全链 PASS；非 0 = 失败
# =============================================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --package) PKG_DIR="$2"; shift 2 ;;
    --prefix) INSTALL_PREFIX="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
PKG_DIR="${PKG_DIR:-$SELF_DIR/..}"
PKG_DIR="$(cd "$PKG_DIR" && pwd)"

log() { echo "[d14a-smoke] $*"; }
die() { echo "[d14a-smoke] FAIL: $*" >&2; exit 1; }

UNIT_NAME="kylin-memory"
SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock"
EMBED_SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/embedding.sock"

# ── 0. 前置：包完整 + 真 SDK ──
[ -f "$PKG_DIR/manifest.json" ] || die "package 缺失 manifest.json: $PKG_DIR"
[ -x "$PKG_DIR/bin/kylin-memory-server" ] || die "package 缺失 launcher"
[ -f "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0" ] \
  || die "真实 SDK 缺失"
log "package: $PKG_DIR"

# ── 1. 清理旧状态，隔离 prefix ──
INSTALL_PREFIX="$INSTALL_PREFIX"
export INSTALL_PREFIX
if [ -d "$INSTALL_PREFIX" ]; then
  log "清理旧 prefix: $INSTALL_PREFIX"
  rm -rf "$INSTALL_PREFIX"
fi
rm -f "$SOCK"

# ── 2. 启动 embedding.server（真实 SDK，用于 verify 的 memory.embed） ──
# embedding server 需在 install 前启动（verify 用）；从 package venv 启动，
# PYTHONPATH 用包内路径（安装前后包内容一致）
export PYTHONPATH="$PKG_DIR/runtime/app:$PKG_DIR/runtime/bridge"
"$PKG_DIR/runtime/python/bin/python" -m embedding.server \
  --socket "$EMBED_SOCK" \
  > /tmp/d14a-smoke-embed.log 2>&1 &
EMBED_PID=$!
# wait socket
for i in $(seq 1 30); do [ -S "$EMBED_SOCK" ] && break; sleep 1; done
[ -S "$EMBED_SOCK" ] || die "embedding.server socket 未就绪"

# ── 3. install（含 migration + enable --now + restart 二次 status） ──
log "执行 install…"
bash "$PKG_DIR/systemd/install.sh" install || die "install 失败"

# ── 4. verify（fail-closed：PID==MainPID / SDK SHA / memory.embed）
#    从已安装的 INSTALL_PREFIX 运行 verify（验证发布链的最终安装形态） ──
log "执行 verify…"
bash "$INSTALL_PREFIX/systemd/verify.sh" --embed-socket "$EMBED_SOCK" --embed-pid "$EMBED_PID" || die "verify 失败"

# ── 5. restart 再 verify ──
log "restart 后再次 verify…"
systemctl --user restart "$UNIT_NAME"
sleep 3
bash "$INSTALL_PREFIX/systemd/verify.sh" --embed-socket "$EMBED_SOCK" --embed-pid "$EMBED_PID" || die "restart 后 verify 失败"

# ── 6. rollback ──
log "执行 rollback…"
bash "$PKG_DIR/systemd/uninstall.sh" rollback || die "rollback 失败"
systemctl --user is-active --quiet "$UNIT_NAME" \
  && die "rollback 后服务仍 active" || true
[ -e "$HOME/.local/bin/kylin-memory-server" ] \
  && die "rollback 后 symlink 仍存在" || true
[ -d "$INSTALL_PREFIX" ] && die "rollback 后 install_prefix 仍存在" || true

# ── 7. 清理 embedding server ──
kill "$EMBED_PID" 2>/dev/null || true

log "ALL PASS: install → migration → start → verify(real SDK) → restart → rollback"
echo "[d14a-smoke] ALL PASS"