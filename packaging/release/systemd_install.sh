#!/usr/bin/env bash
# =============================================================================
# D14A systemd --user install（无源码/无个人 venv 依赖，整包安装到 install_prefix）
# 用法: bash install.sh install
# 方案（contract §1/§4 冻结）：整包复制到 <install_prefix>，launcher 留在包内，
#   ~/.local/bin/kylin-memory-server 仅做 symlink → <prefix>/bin/kylin-memory-server。
#   unit ExecStart 指向 <prefix>/bin/kylin-memory-server（固定前缀，不依赖 $0 重定位）。
# 升级回退（PR#152 D14A R2）：在覆盖任何既有状态前，先把旧 install_prefix / 旧 unit /
#   旧 launcher（普通文件或 symlink）捕获进确定性私有事务目录
#   ${XDG_STATE_HOME:-$HOME/.local/state}/kylin-memory/d14a-install-txn（0700），
#   并以 txn.meta 显式记录“被捕获的是哪个旧状态”；uninstall rollback 依据该元数据
#   精确恢复，不再使用 *.bak.<timestamp> 猜测。事务目录位于 install_prefix 之外。
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
# 发布包根（安装来源）。PKG_DIR 允许环境覆盖（与 INSTALL_PREFIX 同级的测试缝，
# 供隔离测试把完整性 Gate 指向临时构造的发布包；生产打包后运行不覆盖）。
PKG_DIR="${PKG_DIR:-$(cd "$SELF_DIR/.." && pwd)}"
# contract §1: install_prefix（默认 $XDG_DATA_HOME/kylin-memory-d14a）
INSTALL_PREFIX="${INSTALL_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory-d14a}"
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
BIN_SYMLINK="$HOME/.local/bin/kylin-memory-server"

# 契约 §6 冻结的 SDK identity（与 build_release_package.sh manifest 一致）
EXPECT_PACKAGE_NAME="kylin-memory-a-d14a"
EXPECT_SDK_SO_PATH="/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0"
EXPECT_SDK_VERSION="1.2.0.0-0k0.4"
EXPECT_SDK_SHA="028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48"

log() { echo "[d14a-install] $*"; }
die() { echo "[d14a-install] ERROR: $*" >&2; exit 1; }

# =============================================================================
# 全量、双向、fail-closed 的包完整性 Gate（contract §10）
#   - 解析 SHA256SUMS（<sha256>  <relpath>），拒绝空清单/重复/绝对路径/路径穿越/空路径
#   - 对 SHA256SUMS 中全部文件在 <PKG_DIR> 下逐一按磁盘实际 sha256 校验（不信任 manifest hash）
#   - 双向一致：manifest.files 键集 == SHA256SUMS 文件集，且 size 与磁盘一致
#   - manifest identity：package_name/package_version/source_commit/SDK identity 与契约冻结值一致
#   - VERSION 文件内容 == manifest.package_version
#   任何一项不满足即非零退出，且不产生任何复制/迁移/systemd 副作用。
#   用法：verify_package_integrity <pkg_dir>，成功返回 0，失败调用 die 退出。
# =============================================================================
verify_package_integrity() {
  local pkg="$1"
  local sums="$pkg/SHA256SUMS"
  local manifest="$pkg/manifest.json"
  local version_file="$pkg/VERSION"

  [ -f "$sums" ] || die "发布包缺失 SHA256SUMS"
  [ -f "$manifest" ] || die "发布包缺失 manifest.json"
  [ -f "$version_file" ] || die "发布包缺失 VERSION"

  "$PYTHON3" - "$manifest" "$version_file" "$pkg" \
    "$EXPECT_PACKAGE_NAME" "$EXPECT_SDK_SO_PATH" "$EXPECT_SDK_VERSION" "$EXPECT_SDK_SHA" \
    <<'PYEOF' || die "包完整性 Gate 失败（详见上方错误）"
import json, sys, os, hashlib, re

manifest_path, version_path, pkg = sys.argv[1], sys.argv[2], sys.argv[3]
exp_name, exp_so, exp_ver, exp_sha = sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7]
sha_path = os.path.join(pkg, "SHA256SUMS")

def die(msg): sys.exit("完整性Gate: " + msg)

# ── 1. 解析 SHA256SUMS（fail-closed） ──
entries = []          # (relpath, sha256)
seen_paths = {}
try:
    sha_lines = open(sha_path, encoding="utf-8").read().splitlines()
except OSError as e:
    die("读取 SHA256SUMS 失败: %s" % e)
for lineno, line in enumerate(sha_lines, 1):
    if not line.strip():
        continue
    parts = line.split()
    if len(parts) != 2:
        die("SHA256SUMS 行 %d 格式非法（须 `sha256  relpath`）：%r" % (lineno, line))
    sha, rel = parts[0], parts[1]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        die("SHA256SUMS 行 %d 哈希非法：%r" % (lineno, sha))
    if rel in seen_paths:
        die("SHA256SUMS 出现重复路径：%r" % rel)
    seen_paths[rel] = sha
    entries.append((rel, sha))
if not entries:
    die("SHA256SUMS 为空清单（fail-closed）")

# ── 2. SHA256SUMS 语法防穿越/防绝对路径 ──
for rel, _sha in entries:
    if rel.startswith("/"):
        die("绝对路径禁止: %r" % rel)
    norm = os.path.normpath(rel)
    if norm != rel or rel in (".", "..") or norm.startswith("../") or norm == "..":
        die("路径穿越/非法相对路径: %r" % rel)

# ── 3. 载入 manifest ──
try:
    manifest = json.load(open(manifest_path, encoding="utf-8"))
except Exception as e:
    die("manifest.json 解析失败: %s" % e)

# ── 4. 双向一致：manifest.files 键集 == SHA256SUMS 文件集 ──
man_files = manifest.get("files", {})
sum_set = set(rel for rel, _ in entries)
man_set = set(man_files.keys())
missing_in_sum = man_set - sum_set
unmanaged_in_sum = sum_set - man_set
if missing_in_sum:
    die("manifest 声明但 SHA256SUMS 未覆盖: %s" % sorted(missing_in_sum))
if unmanaged_in_sum:
    die("SHA256SUMS 含 manifest 未登记文件: %s" % sorted(unmanaged_in_sum))

# ── 5. 全量 sha256 + size 校验（SHA256SUMS 全集，且与 manifest.files 双向一致） ──
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

for rel, expect_sha in entries:
    p = os.path.join(pkg, rel)
    if not os.path.isfile(p):
        die("受管理文件缺失: %r" % rel)
    if sha256(p) != expect_sha:
        die("哈希不符: %r" % rel)
    mf = man_files[rel]
    if int(mf.get("size", -1)) != os.path.getsize(p):
        die("size 不符: %r" % rel)
    if mf.get("sha256") != expect_sha:
        die("manifest.sha256 与 SHA256SUMS 不一致: %r" % rel)

# ── 6. manifest identity ──
if manifest.get("package_name") != exp_name:
    die("package_name 不符: expected=%r actual=%r" % (exp_name, manifest.get("package_name")))
if not manifest.get("package_version"):
    die("package_version 缺失")
if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit", ""))):
    die("source_commit 非法（须 40 位 SHA）: %r" % manifest.get("source_commit"))
sdk = manifest.get("sdk") or {}
if sdk.get("so_path") != exp_so:
    die("sdk.so_path 不符: expected=%r actual=%r" % (exp_so, sdk.get("so_path")))
if sdk.get("version") != exp_ver:
    die("sdk.version 不符: expected=%r actual=%r" % (exp_ver, sdk.get("version")))
if sdk.get("sha256") != exp_sha:
    die("sdk.sha256 不符（冻结值）: expected=%r actual=%r" % (exp_sha, sdk.get("sha256")))

# ── 7. VERSION 文件内容 == manifest.package_version ──
actual_version = open(version_path, encoding="utf-8").read().strip()
if actual_version != manifest.get("package_version"):
    die("VERSION(%r) != manifest.package_version(%r)" %
        (actual_version, manifest.get("package_version")))

print("包完整性 Gate: PASS（%d 文件，双向一致，identity 绑定）" % len(entries))
PYEOF
}

# 完整性 Gate 最先执行（早于任何复制/迁移/systemd 副作用）
PYTHON3="${PYTHON3:-/usr/bin/python3}"
verify_package_integrity "$PKG_DIR"

# ── 入参解析：install（默认完整安装） / _integrity-gate（仅执行完整性 Gate） ──
MODE="${1:-install}"
if [ "$MODE" = "_integrity-gate" ]; then
  log "仅执行完整性 Gate（_integrity-gate）"
  exit 0
fi
if [ "$MODE" != "install" ]; then
  die "未知模式: $MODE（支持 install / _integrity-gate）"
fi

# ── 0. 包内存在性预检（fail-closed，contract §3/§7；哈希由上方 Gate 负责） ──
[ -x "$PKG_DIR/runtime/python/bin/python" ] || die "包内 venv 缺失: runtime/python"
[ -f "$PKG_DIR/runtime/app/app.py" ] || die "包内 app 缺失: runtime/app"
[ -n "$(ls "$PKG_DIR"/runtime/bridge/kylin_embedding*.so 2>/dev/null)" ] \
  || die "包内 bridge 缺失: runtime/bridge"
[ -f "$PKG_DIR/runtime/app/migrations/alembic.ini" ] \
  || die "包内迁移缺失: runtime/app/migrations"

# ── 1. 前置系统依赖校验（contract §3，fail-closed：版本 + SHA-256） ──
# 测试缝（仅隔离测试用）：D14A_SYSTEM_SDK_* 可覆盖“系统前置校验”所检查的 SDK
# 路径/版本/SHA；生产打包后未设置这些变量，一律回落下方冻结值。完整性 Gate 始终
# 以冻结常量校验 manifest 中的 SDK identity，本测试缝不放松冻结身份。
SDK_SO_PATH="${D14A_SYSTEM_SDK_SO_PATH:-$EXPECT_SDK_SO_PATH}"
SDK_VERSION="${D14A_SYSTEM_SDK_VERSION:-$EXPECT_SDK_VERSION}"
SDK_SHA256="${D14A_SYSTEM_SDK_SHA256:-$EXPECT_SDK_SHA}"
[ -f "$SDK_SO_PATH" ] || die "前置依赖缺失: $SDK_SO_PATH"
ACTUAL_SHA="$(sha256sum "$SDK_SO_PATH" | awk '{print $1}')"
[ "$ACTUAL_SHA" = "$SDK_SHA256" ] \
  || die "SDK SHA-256 不匹配: expected=$SDK_SHA256 actual=$ACTUAL_SHA"
ACTUAL_VER="$(dpkg-query -W -f='${Version}' libkylin-coreai-embedding 2>/dev/null || echo 'unknown')"
[ "$ACTUAL_VER" = "$SDK_VERSION" ] \
  || die "SDK 版本不匹配: expected=$SDK_VERSION actual=$ACTUAL_VER"

# ── 2. 事务捕获：覆盖任何既有状态前，先备份旧状态（升级回退，PR#152 D14A R2） ──
# TXN_DIR 是确定性、私有的事务目录（0700），位于 install_prefix 之外（默认 state home）。
# 其中 txn.meta 以键=值显式记录“恰好一个旧状态”：
#   旧 prefix（目录级 mv 搬迁）、旧 unit（字节备份）、旧 launcher（none/file/symlink）。
# 安装中途失败时本事务保留，可被 uninstall.sh rollback 精确恢复。
TXN_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/kylin-memory/d14a-install-txn"

capture_old_state() {
  local stage
  stage="${TXN_DIR}.stage.$$"

  case "$TXN_DIR/" in
    "$INSTALL_PREFIX"/*)
      die "事务目录不得位于 install_prefix 内部: $TXN_DIR（请调整 XDG_STATE_HOME）" ;;
  esac

  OLD_PREFIX_BACKUP=absent
  OLD_UNIT_BACKUP=absent
  OLD_LAUNCHER_KIND=none
  OLD_LAUNCHER_TARGET=""

  # 捕获任一步失败：回迁已搬移的旧 prefix 并终止，不留错向事务。
  # （M-1/M-2：捕获后任一步失败均走此回迁路径，禁止任何 rm -rf 销毁已捕获旧 prefix。
  #  HIGH-1：回迁 mv 再次失败时保留 stage/old-prefix 作为唯一可恢复备份，仅当
  #   未捕获旧 prefix / 回迁成功 / stage 内已无唯一需恢复 old-prefix backup 时才清理。）
  tx_fail() {
    local msg="$1"
    if [ "$OLD_PREFIX_BACKUP" = present ] \
       && [ -d "$stage/old-prefix" ] && [ ! -e "$INSTALL_PREFIX" ]; then
      if mv -f "$stage/old-prefix" "$INSTALL_PREFIX"; then
        # 旧 prefix 已安全回迁：唯一备份已归位，可安全清理 stage
        rm -rf "$stage"
      else
        # 回迁失败：唯一可恢复备份仍保留于 stage/old-prefix，禁止 rm -rf 销毁；
        # 保留 stage 与完整现场，诊断指向真实保留路径（mv 根因已透传至 stderr）
        echo "[d14a-install] CRITICAL: 旧 prefix 回迁失败，唯一备份保留于 $stage/old-prefix（stage 未清理）" >&2
      fi
    else
      # 未捕获旧 prefix / 已无唯一需恢复 old-prefix backup：安全清理 stage
      rm -rf "$stage"
    fi
    die "事务捕获失败: $msg"
  }

  mkdir -p "$(dirname "$TXN_DIR")" || die "无法创建事务父目录: $(dirname "$TXN_DIR")"
  rm -rf "$stage"
  mkdir -p "$stage" || die "无法创建事务暂存目录: $stage"
  chmod 0700 "$stage" || tx_fail "无法设置事务暂存目录权限: $stage"

  # 旧 prefix：目录级搬迁（mv 保持字节/inode 保真，恢复时 mv 回迁）
  if [ -d "$INSTALL_PREFIX" ]; then
    mv -f "$INSTALL_PREFIX" "$stage/old-prefix" \
      || tx_fail "无法搬迁旧 prefix ($INSTALL_PREFIX)"
    OLD_PREFIX_BACKUP=present
    log "事务捕获: 旧 prefix 已搬迁到事务目录"
  fi

  # 旧 unit：普通文件则字节备份（旧代码从不备份 unit）
  if [ -f "$UNIT_DST" ]; then
    cp -f "$UNIT_DST" "$stage/old-unit" \
      || tx_fail "无法备份旧 unit ($UNIT_DST)"
    OLD_UNIT_BACKUP=present
  fi

  # 旧 launcher 三态：symlink 记 target；普通文件字节备份；不存在记 none
  if [ -L "$BIN_SYMLINK" ]; then
    OLD_LAUNCHER_KIND=symlink
    OLD_LAUNCHER_TARGET="$(readlink "$BIN_SYMLINK")" \
      || tx_fail "无法读取旧 launcher symlink target ($BIN_SYMLINK)"
    log "事务捕获: 旧 launcher 为 symlink → $OLD_LAUNCHER_TARGET"
  elif [ -f "$BIN_SYMLINK" ]; then
    cp -f "$BIN_SYMLINK" "$stage/old-launcher" \
      || tx_fail "无法备份旧 launcher ($BIN_SYMLINK)"
    OLD_LAUNCHER_KIND=file
    log "事务捕获: 旧 launcher 为普通文件，已字节备份"
  fi

  # txn.meta：临时文件 + mv 原子落盘
  {
    echo "TXN_FORMAT=1"
    echo "INSTALL_PREFIX=$INSTALL_PREFIX"
    echo "UNIT_PATH=$UNIT_DST"
    echo "BIN_SYMLINK_PATH=$BIN_SYMLINK"
    echo "OLD_PREFIX_BACKUP=$OLD_PREFIX_BACKUP"
    echo "OLD_PREFIX_DIR=$TXN_DIR/old-prefix"
    echo "OLD_UNIT_BACKUP=$OLD_UNIT_BACKUP"
    echo "OLD_UNIT_FILE=$TXN_DIR/old-unit"
    echo "OLD_LAUNCHER_KIND=$OLD_LAUNCHER_KIND"
    echo "OLD_LAUNCHER_FILE=$TXN_DIR/old-launcher"
    echo "OLD_LAUNCHER_TARGET=$OLD_LAUNCHER_TARGET"
  } > "$stage/txn.meta.tmp" || tx_fail "txn.meta 写入失败"
  mv -f "$stage/txn.meta.tmp" "$stage/txn.meta" || tx_fail "txn.meta 落盘失败"

  # 整体切换：本轮捕获成功后才替换既有事务（rm + mv，原子切换；
  # 连续升级时只保留“最近一次旧状态”）。任一步失败均走 tx_fail：
  # 旧 prefix 已捕获成功时自动回迁旧状态（M-1：mv 失败分支禁止 rm -rf "$stage"
  # 销毁已捕获旧 prefix；M-2：finalization/权限步骤失败同样回迁或保留可恢复备份）。
  rm -rf "$TXN_DIR" || tx_fail "无法清理旧事务目录 $TXN_DIR"
  mv -f "$stage" "$TXN_DIR" || tx_fail "无法切换到事务目录 $TXN_DIR"
  chmod 0700 "$TXN_DIR" || tx_fail "无法设置事务目录权限 $TXN_DIR"
  log "事务就绪: $TXN_DIR（old_prefix=$OLD_PREFIX_BACKUP old_unit=$OLD_UNIT_BACKUP old_launcher=$OLD_LAUNCHER_KIND）"
}

capture_old_state

# ── 3. 整包安装到 install_prefix（tar 保留符号链接，规避 vboxsf 限制） ──
mkdir -p "$INSTALL_PREFIX"
tar -C "$PKG_DIR" -cf - . | tar -C "$INSTALL_PREFIX" -xf -
[ -x "$INSTALL_PREFIX/bin/kylin-memory-server" ] || die "安装失败: $INSTALL_PREFIX/bin/kylin-memory-server"

# ── 4. ~/.local/bin 做 symlink → <prefix>/bin/kylin-memory-server ──
mkdir -p "$HOME/.local/bin"
ln -sfn "$INSTALL_PREFIX/bin/kylin-memory-server" "$BIN_SYMLINK"

# ── 5. 数据目录（确定 0700） ──
mkdir -p "$HOME/.config/systemd/user" \
  "$HOME/.config/kylin-memory" "$HOME/.local/share/kylin-memory" "$HOME/.local/state/kylin-memory"
chmod 0700 "$HOME/.config/kylin-memory" "$HOME/.local/share/kylin-memory" "$HOME/.local/state/kylin-memory"

# ── 6. unit：ExecStart 指向固定 prefix launcher（BLOCKER 1 方案 B） ──
UNIT_SRC="$SELF_DIR/kylin-memory.service"
# 渲染 ExecStart 为 <prefix>/bin/kylin-memory-server（旧 unit 已在事务捕获中备份）
sed "s|%h/.local/bin/kylin-memory-server|$INSTALL_PREFIX/bin/kylin-memory-server|g" \
  "$UNIT_SRC" > "$UNIT_DST"
systemctl --user daemon-reload

# ── 7. 首次启动前 Alembic 迁移（BLOCKER 2：clean VM 必须 upgrade head） ──
# 可重定位：使用 <runtime python> -m alembic 模块入口（发布包内不含构建期 venv 的
# console-script；其 shebang 携带构建机绝对路径，不可重定位）
export KYLIN_MEMORY_DB="${KYLIN_MEMORY_DB:-$HOME/.local/share/kylin-memory/kylin_memory.db}"
mkdir -p "$(dirname "$KYLIN_MEMORY_DB")"
log "执行 Alembic 迁移（upgrade head）…"
( cd "$INSTALL_PREFIX/runtime/app" \
  && PYTHONPATH="$INSTALL_PREFIX/runtime/app" \
     "$INSTALL_PREFIX/runtime/python/bin/python" \
     -m alembic -c migrations/alembic.ini upgrade head ) \
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
