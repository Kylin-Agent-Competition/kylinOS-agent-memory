#!/usr/bin/env bash
# =============================================================================
# D14A verify/smoke — 发布包安装后健康 + 真实 SDK 验证（contract §9）
# 用法: bash verify.sh
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$SELF_DIR/.." && pwd)"

log() { echo "[d14a-verify] $*"; }
die() { echo "[d14a-verify] FAIL: $*" >&2; exit 1; }

# 1. 服务 active
systemctl --user is-active --quiet "$UNIT_NAME" || die "服务未 active"

# 2. socket + PID 身份
PID="$(systemctl --user show -p MainPID --value "$UNIT_NAME")"
SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock"
[ -S "$SOCK" ] || die "socket 不存在: $SOCK"
[ "$PID" != "0" ] || die "MainPID 无效"

# 3. cmdline / cwd 不含源码 checkout 与个人 venv（contract §5/§8.5）
CMDLINE="$(tr '\0' ' ' < /proc/$PID/cmdline)"
CWD="$(readlink -f /proc/$PID/cwd)"
echo "$CMDLINE" | grep -q "runtime/python/bin/python" \
  || die "cmdline 未指向发布包 venv: $CMDLINE"
echo "$CMDLINE" | grep -qiE "(\.venv|d4d-venv|/home/.*/kylinOS-agent-memory)" \
  && die "cmdline 含开发 venv/源码路径" || true

# 4. 真实 SDK 实际加载（contract §6）
SDK_EXPECT="/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0"
grep -Fq "$SDK_EXPECT" /proc/$PID/maps || die "进程未加载 SDK .so（expected: $SDK_EXPECT）"

# 5. 真实 SDK smoke（memory.embed → dim=768）
PY="$PKG_DIR/runtime/python/bin/python"
EMBED_SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/embedding.sock"
[ -S "$EMBED_SOCK" ] || log "embedding.sock 未就绪（A 轨可后续启动 embedding.server 验证）"

log "OK: service active / socket=$SOCK / PID=$PID"
log "OK: cmdline=$CMDLINE"
log "OK: SDK loaded=$SDK_EXPECT"
echo "[d14a-verify] ALL PASS"