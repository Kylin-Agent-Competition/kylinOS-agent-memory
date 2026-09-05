#!/usr/bin/env bash
# =============================================================================
# D14A systemd --user install（无源码/无个人 venv 依赖，整包安装到 install_prefix）
# 用法: bash install.sh install
# 方案（contract §1/§4 冻结）：整包复制到 <install_prefix>，launcher 留在包内，
#   ~/.local/bin/kylin-memory-server 仅做 symlink → <prefix>/bin/kylin-memory-server。
#   unit ExecStart 指向 <prefix>/bin/kylin-memory-server（固定前缀，不依赖 $0 重定位）。
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$SELF_DIR/.." && pwd)"          # 发布包根（安装来源）
# contract §1: install_prefix（默认 $XDG_DATA_HOME/kylin-memory-d14a）
INSTALL_PREFIX="${INSTALL_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory-d14a}"
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
BIN_SYMLINK="$HOME/.local/bin/kylin-memory-server"

log() { echo "[d14a-install] $*"; }
die() { echo "[d14a-install] ERROR: $*" >&2; exit 1; }

# ── 0. 包内完整性预检（fail-closed，contract §3/§7） ──
[ -f "$PKG_DIR/manifest.json" ] || die "发布包缺失 manifest.json"
[ -f "$PKG_DIR/SHA256SUMS" ] || die "发布包缺失 SHA256SUMS"
[ -f "$PKG_DIR/VERSION" ] || die "发布包缺失 VERSION"
[ -x "$PKG_DIR/runtime/python/bin/python" ] || die "包内 venv 缺失: runtime/python"
[ -f "$PKG_DIR/runtime/app/app.py" ] || die "包内 app 缺失: runtime/app"
[ -n "$(ls "$PKG_DIR"/runtime/bridge/kylin_embedding*.so 2>/dev/null)" ] \
  || die "包内 bridge 缺失: runtime/bridge"
[ -f "$PKG_DIR/runtime/app/migrations/alembic.ini" ] \
  || die "包内迁移缺失: runtime/app/migrations"

# ── 1. 前置系统依赖校验（contract §3，fail-closed：版本 + SHA-256） ──
SDK_SO="/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0"
SDK_EXPECT_SHA="028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48"
SDK_EXPECT_VER="1.2.0.0-0k0.4"
[ -f "$SDK_SO" ] || die "前置依赖缺失: $SDK_SO"
ACTUAL_SHA="$(sha256sum "$SDK_SO" | awk '{print $1}')"
[ "$ACTUAL_SHA" = "$SDK_EXPECT_SHA" ] \
  || die "SDK SHA-256 不匹配: expected=$SDK_EXPECT_SHA actual=$ACTUAL_SHA"
ACTUAL_VER="$(dpkg-query -W -f='${Version}' libkylin-coreai-embedding 2>/dev/null || echo 'unknown')"
[ "$ACTUAL_VER" = "$SDK_EXPECT_VER" ] \
  || die "SDK 版本不匹配: expected=$SDK_EXPECT_VER actual=$ACTUAL_VER"

# ── 2. 包自身校验（contract §10：manifest 中声明的 SHA 与包内实际文件一致） ──
# 校验核心文件（bridge/app.py/VERSION）哈希与 manifest 一致
PYTHON3="${PYTHON3:-/usr/bin/python3}"
"$PYTHON3" - "$PKG_DIR/manifest.json" "$PKG_DIR" <<'PYEOF' || die "manifest 校验失败（无 python3 或哈希不一致）"
import json, hashlib, sys
manifest = json.load(open(sys.argv[1]))
for rel in ("VERSION",
            "runtime/bridge/kylin_embedding.cpython-312-x86_64-linux-gnu.so",
            "runtime/app/app.py"):
    path = sys.argv[2] + "/" + rel
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    got = manifest["files"][rel]["sha256"]
    if h != got:
        sys.exit("hash mismatch: %s" % rel)
print("manifest core files verified")
PYEOF

# ── 3. 整包安装到 install_prefix（tar 保留符号链接，规避 vboxsf 限制） ──
if [ -d "$INSTALL_PREFIX" ]; then
  mv -f "$INSTALL_PREFIX" "$INSTALL_PREFIX.bak.$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$INSTALL_PREFIX"
tar -C "$PKG_DIR" -cf - . | tar -C "$INSTALL_PREFIX" -xf -
[ -x "$INSTALL_PREFIX/bin/kylin-memory-server" ] || die "安装失败: $INSTALL_PREFIX/bin/kylin-memory-server"

# ── 4. ~/.local/bin 做 symlink → <prefix>/bin/kylin-memory-server ──
mkdir -p "$HOME/.local/bin"
if [ -e "$BIN_SYMLINK" ] && [ ! -L "$BIN_SYMLINK" ]; then
  cp -f "$BIN_SYMLINK" "$BIN_SYMLINK.bak.$(date +%Y%m%d_%H%M%S)"
fi
ln -sfn "$INSTALL_PREFIX/bin/kylin-memory-server" "$BIN_SYMLINK"

# ── 5. 数据目录（确定 0700） ──
mkdir -p "$HOME/.config/systemd/user" \
  "$HOME/.config/kylin-memory" "$HOME/.local/share/kylin-memory" "$HOME/.local/state/kylin-memory"
chmod 0700 "$HOME/.config/kylin-memory" "$HOME/.local/share/kylin-memory" "$HOME/.local/state/kylin-memory"

# ── 6. unit：ExecStart 指向固定 prefix launcher（BLOCKER 1 方案 B） ──
UNIT_SRC="$SELF_DIR/kylin-memory.service"
# 渲染 ExecStart 为 <prefix>/bin/kylin-memory-server
sed "s|%h/.local/bin/kylin-memory-server|$INSTALL_PREFIX/bin/kylin-memory-server|g" \
  "$UNIT_SRC" > "$UNIT_DST"
if [ -f "$UNIT_DST.bak.$(date +%Y%m%d_%H%M%S 2>/dev/null)" ]; then :; fi
systemctl --user daemon-reload

# ── 7. 首次启动前 Alembic 迁移（BLOCKER 2：clean VM 必须 upgrade head） ──
export KYLIN_MEMORY_DB="${KYLIN_MEMORY_DB:-$HOME/.local/share/kylin-memory/kylin_memory.db}"
mkdir -p "$(dirname "$KYLIN_MEMORY_DB")"
log "执行 Alembic 迁移（upgrade head）…"
( cd "$INSTALL_PREFIX/runtime/app" \
  && PYTHONPATH="$INSTALL_PREFIX/runtime/app" \
     "$INSTALL_PREFIX/runtime/python/bin/alembic" \
     -c migrations/alembic.ini upgrade head ) \
  || die "Alembic migration 失败"
# 校验 alembic_version 存在
"$INSTALL_PREFIX/runtime/python/bin/python" - <<'PYEOF' || die "alembic_version 校验失败"
import os, sqlite3
db = os.environ.get("KYLIN_MEMORY_DB", "")
conn = sqlite3.connect(db)
rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
assert rows, "alembic_version 为空"
print("alembic_version:", rows[0][0])
PYEOF

# ── 8. enable --now + wait socket + journal ready + restart 二次 status ──
systemctl --user enable --now "$UNIT_NAME" || die "enable --now 失败"
sleep 3
# wait socket
SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock"
for i in $(seq 1 30); do [ -S "$SOCK" ] && break; sleep 1; done
[ -S "$SOCK" ] || die "socket 未就绪: $SOCK"
# journal ready
for i in $(seq 1 30); do
  if journalctl --user -u "$UNIT_NAME" -n 200 --no-pager 2>/dev/null | grep -q "Memory Service 就绪"; then
    log "journal: Memory Service 就绪 已出现"; break
  fi
  sleep 1
done
systemctl --user is-active --quiet "$UNIT_NAME" || die "服务未 active"

# ── 9. restart 二次 status（contract §7 Step 6） ──
log "restart 验证…"
systemctl --user restart "$UNIT_NAME"
sleep 3
systemctl --user is-active --quiet "$UNIT_NAME" || die "restart 后服务未 active"
[ -S "$SOCK" ] || die "restart 后 socket 丢失"

log "安装完成: prefix=$INSTALL_PREFIX unit=$UNIT_DST symlink=$BIN_SYMLINK"
log "socket: $SOCK"