#!/usr/bin/env bash
# =============================================================================
# D14A package smoke — 自动化可重复发布链验证（复审最低条件第 5 条）
# 默认场景 clean（既有全链路）: install → migration → service start → verify(real
#   SDK) → restart → rollback（clean-state，回退后无 prefix/unit/symlink/事务残留）
# 独立场景 upgrade-rollback（PR#152 D14A R2）: 预置 old prefix（含唯一旧版本标记）、
#   old unit、old launcher（--old-launcher file|symlink 可切换）→ install 新包 →
#   transactional rollback → 逐项断言旧 prefix 标记文件、旧 unit 字节、旧 launcher
#   内容或 symlink target 一致，且不残留新 prefix / 事务目录。
# 用法: bash package_smoke.sh [--package <pkg-dir>] [--prefix <install-prefix>]
#       [--scenario clean|upgrade-rollback] [--old-launcher file|symlink]
# 前置: 真实 SDK 已装；当前用户 systemd --user 可用；embedding.server 由外部提供
#       （本 smoke 通过已注册的 embedding.sock 或本地启动验证真实 SDK）
# 退出码: 0 = 全链 PASS；非 0 = 失败
# =============================================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR=""
SCENARIO="clean"
OLD_LAUNCHER="file"
while [ $# -gt 0 ]; do
  case "$1" in
    --package) PKG_DIR="$2"; shift 2 ;;
    --prefix) INSTALL_PREFIX="$2"; shift 2 ;;
    --scenario) SCENARIO="$2"; shift 2 ;;
    --old-launcher) OLD_LAUNCHER="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
PKG_DIR="${PKG_DIR:-$SELF_DIR/..}"
PKG_DIR="$(cd "$PKG_DIR" && pwd)"
case "$SCENARIO" in
  clean|upgrade-rollback) ;;
  *) echo "未知场景: $SCENARIO（支持 clean / upgrade-rollback）" >&2; exit 2 ;;
esac
case "$OLD_LAUNCHER" in
  file|symlink) ;;
  *) echo "未知 old-launcher: $OLD_LAUNCHER（支持 file / symlink）" >&2; exit 2 ;;
esac

log() { echo "[d14a-smoke] $*"; }
die() { echo "[d14a-smoke] FAIL: $*" >&2; exit 1; }

UNIT_NAME="kylin-memory"
SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock"
# embedding.sock 用独立 /tmp 路径，避免被 systemd RuntimeDirectory(kylin-memory) 清理
EMBED_SOCK="/tmp/kylin-d14a-embed.sock"

# ── 0. 前置：包完整 + 真 SDK ──
[ -f "$PKG_DIR/manifest.json" ] || die "package 缺失 manifest.json: $PKG_DIR"
[ -x "$PKG_DIR/bin/kylin-memory-server" ] || die "package 缺失 launcher"
[ -f "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0" ] \
  || die "真实 SDK 缺失"
log "package: $PKG_DIR"

# ── 独立场景：upgrade-rollback（事务化升级回退 smoke，PR#152 D14A R2） ──
# 预置“旧版本”现场（old prefix + 唯一标记文件、old unit、old launcher file/symlink），
# install 新包后由 txn.meta 驱动的事务化 rollback 精确恢复，再逐项字节/目标比对。
# 需要真实 systemd --user 与真实 SDK，属 VM-only 路径。
run_upgrade_rollback() {
  log "scenario=upgrade-rollback（old-launcher=$OLD_LAUNCHER）"
  [ -n "${INSTALL_PREFIX:-}" ] || die "upgrade-rollback 需要 --prefix <install-prefix>"
  # 与 clean 流程一致：导出 INSTALL_PREFIX，使子进程 install.sh/uninstall.sh
  # 捕获/回迁作用于 smoke 预置的旧 prefix（而非回落默认 prefix 触碰真实用户安装）
  export INSTALL_PREFIX
  local txn_dir snap marker unit launcher old_target embed_pid
  txn_dir="${XDG_STATE_HOME:-$HOME/.local/state}/kylin-memory/d14a-install-txn"
  snap="$(dirname "$INSTALL_PREFIX")/kylin-d14a-upgrade-smoke.snap"
  marker="$INSTALL_PREFIX/KYLIN_D14A_OLD_VERSION.marker"
  unit="$HOME/.config/systemd/user/${UNIT_NAME}.service"
  launcher="$HOME/.local/bin/kylin-memory-server"

  # 清理上次残留，构造“旧版本”现场（隔离 prefix，不触碰默认用户 prefix）
  rm -f "$SOCK" "$EMBED_SOCK"
  rm -rf "$txn_dir" "$snap" "$INSTALL_PREFIX"
  rm -f "$unit" "$launcher"
  mkdir -p "$snap" "$INSTALL_PREFIX" "$(dirname "$unit")" "$(dirname "$launcher")"

  # 旧 prefix：写入唯一旧版本标记文件（新包 tar 内容中不存在该文件）
  printf 'KYLIN_D14A_OLD_VERSION marker\n' > "$marker"
  # 旧 unit：可辨识且合法的旧定义（daemon-reload 可接受），内容须与新渲染 unit 不同
  cat > "$unit" <<'UNITEOF'
[Unit]
Description=Kylin Memory Service (D14A old version)
[Service]
Type=simple
ExecStart=/bin/true
[Install]
WantedBy=default.target
UNITEOF
  if [ "$OLD_LAUNCHER" = "symlink" ]; then
    old_target="$INSTALL_PREFIX.old-target/bin/kylin-memory-server"
    mkdir -p "$(dirname "$old_target")"
    ln -s "$old_target" "$launcher"
    printf '%s' "$old_target" > "$snap/launcher-target.ref"
  else
    printf '#!/usr/bin/env bash\n# D14A old launcher (plain file)\n' > "$launcher"
    chmod 0755 "$launcher"
    cp -f "$launcher" "$snap/launcher.ref"
  fi
  cp -f "$unit" "$snap/unit.ref"
  cp -f "$marker" "$snap/marker.ref"

  # 启动 embedding.server（真实 SDK，供升级后服务运行）
  export PYTHONPATH="$PKG_DIR/runtime/app:$PKG_DIR/runtime/bridge"
  "$PKG_DIR/runtime/python/bin/python" -m embedding.server \
    --socket "$EMBED_SOCK" \
    > /tmp/d14a-smoke-embed.log 2>&1 &
  embed_pid=$!
  for i in $(seq 1 30); do [ -S "$EMBED_SOCK" ] && break; sleep 1; done
  [ -S "$EMBED_SOCK" ] || die "embedding.server socket 未就绪"

  # install 新包（内部先事务化捕获旧状态，再安装）
  log "执行 install（升级）…"
  bash "$PKG_DIR/systemd/install.sh" install || die "upgrade install 失败"

  # transactional rollback：依据 txn.meta 精确恢复旧状态
  log "执行 rollback（事务化回退）…"
  bash "$PKG_DIR/systemd/uninstall.sh" rollback || die "upgrade rollback 失败"

  # 逐项断言恢复状态（字节 / symlink target / 无残留）
  cmp -s "$unit" "$snap/unit.ref" || die "rollback 后旧 unit 字节不一致"
  log "PASS: 旧 unit 字节一致"
  if [ "$OLD_LAUNCHER" = "symlink" ]; then
    [ "$(readlink "$launcher")" = "$(cat "$snap/launcher-target.ref")" ] \
      || die "rollback 后旧 symlink target 不一致"
    log "PASS: 旧 launcher symlink target 一致"
  else
    cmp -s "$launcher" "$snap/launcher.ref" || die "rollback 后旧 launcher 字节不一致"
    log "PASS: 旧 launcher（普通文件）字节一致"
  fi
  cmp -s "$marker" "$snap/marker.ref" || die "rollback 后旧 prefix 标记文件不一致"
  [ ! -f "$INSTALL_PREFIX/runtime/app/app.py" ] \
    || die "rollback 后仍残留新 prefix 内容"
  [ ! -d "$txn_dir" ] || die "rollback 后事务目录未清理"
  systemctl --user is-active --quiet "$UNIT_NAME" \
    && die "rollback 后服务仍 active" || true

  kill "$embed_pid" 2>/dev/null || true
  rm -rf "$snap"
  rm -rf "$INSTALL_PREFIX.old-target" 2>/dev/null || true
  log "ALL PASS: upgrade-rollback（old-launcher=$OLD_LAUNCHER）"
}

if [ "$SCENARIO" = "upgrade-rollback" ]; then
  run_upgrade_rollback
  exit 0
fi

# ── 1. 清理旧状态，隔离 prefix ──
INSTALL_PREFIX="$INSTALL_PREFIX"
export INSTALL_PREFIX
if [ -d "$INSTALL_PREFIX" ]; then
  log "清理旧 prefix: $INSTALL_PREFIX"
  rm -rf "$INSTALL_PREFIX"
fi
rm -f "$SOCK" "$EMBED_SOCK"

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