#!/usr/bin/env bash
# =============================================================================
# D14A Release Package Builder — 在麒麟 VM 上构建正式 A 轨发布包
# =============================================================================
# 依据: docs/day14/00_d14a_release_package_contract.md（FROZEN_DRAFT v1）
# 用法（在麒麟 VM 内，具备 python3-dev + cmake + 真实 SDK 环境）:
#   bash packaging/release/build_release_package.sh \
#       --source-commit <sha> \
#       [--python3 /usr/bin/python3.12] \
#       [--dist-dir <dist 根目录，默认 <repo>/dist>]
#
# 产物:
#   <dist>/kylin-memory-a-d14a-<version>/
#   ├── bin/kylin-memory-server        (可重定位 launcher)
#   ├── runtime/app/                   (memory-service 模块级复制 + migrations)
#   ├── runtime/bridge/                (kylin_embedding*.so)
#   ├── runtime/python/                (内嵌 venv，重定位)
#   ├── config/config.toml.example
#   ├── systemd/                       (unit + install/uninstall/verify)
#   ├── VERSION  manifest.json  SHA256SUMS
#
# 契约 Gate: source_commit 必须与 git HEAD 一致；worktree 必须 clean。
# =============================================================================

set -euo pipefail

# ── 参数 ──
SOURCE_COMMIT=""
PYTHON3="${PYTHON3:-/usr/bin/python3.12}"
PACKAGE_VERSION="0.1.0-d14a"
PACKAGE_NAME="kylin-memory-a-d14a"

while [ $# -gt 0 ]; do
  case "$1" in
    --source-commit) SOURCE_COMMIT="$2"; shift 2 ;;
    --python3) PYTHON3="$2"; shift 2 ;;
    --dist-dir) DIST_DIR="$2"; shift 2 ;;
    --version) PACKAGE_VERSION="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# 默认输出到本地盘（vboxsf 不支持符号链接，venv 无法在其上保留 python symlink）
DIST_DIR="${DIST_DIR:-/tmp/kylin-d14a-dist}"
DIST="$DIST_DIR/${PACKAGE_NAME}-${PACKAGE_VERSION}"

log() { echo "[d14a-build] $*"; }
die() { echo "[d14a-build] ERROR: $*" >&2; exit 1; }

# ── Phase 0: Git 身份 Gate（contract §1） ──
CUR_COMMIT="$(git -C "$REPO_DIR" rev-parse HEAD)"
[ -n "$SOURCE_COMMIT" ] || die "--source-commit 必填（= 打包时 main HEAD）"
# 展开为完整 SHA 后比较（支持短 SHA 输入）
FULL_COMMIT="$(git -C "$REPO_DIR" rev-parse "$SOURCE_COMMIT^{commit}" 2>/dev/null)" \
  || die "无法解析 source_commit: $SOURCE_COMMIT"
[ "$CUR_COMMIT" = "$FULL_COMMIT" ] || die "source_commit($SOURCE_COMMIT) 与 HEAD($CUR_COMMIT) 不一致"
[ -z "$(git -C "$REPO_DIR" status --porcelain)" ] || die "worktree 非 clean，禁止打包"

# ── Phase 0: 环境 Gate ──
[ -x "$PYTHON3" ] || die "python3 不存在: $PYTHON3"
"$PYTHON3" -c "import sys; assert sys.version_info >= (3,10)" \
  || die "Python 必须 >= 3.10"
[ -f "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0" ] \
  || die "真实 SDK .so 不存在（D14A 前置系统依赖）"

# ── Phase 1: 构建 cpp-bridge（pybind11 模块） ──
log "构建 cpp-bridge…"
"$PYTHON3" -m venv /tmp/kylin-d14a-build-venv
# memory-service 运行时依赖（contract §2 runtime/python）+ pybind11 构建依赖
/tmp/kylin-d14a-build-venv/bin/pip install --quiet \
  -r "$REPO_DIR/memory-service/requirements.txt" pybind11
BRIDGE_BUILD="$REPO_DIR/cpp-bridge/build-d14a-release"
cmake -S "$REPO_DIR/cpp-bridge" -B "$BRIDGE_BUILD" \
  -Dpybind11_DIR="$(/tmp/kylin-d14a-build-venv/bin/python -m pybind11 --cmakedir)"
cmake --build "$BRIDGE_BUILD" -j"$(nproc)"

# ── Phase 2: 组装发布包目录 ──
rm -rf "$DIST"
mkdir -p "$DIST/runtime" "$DIST/bin" "$DIST/config"

# 2.1 runtime/app（memory-service 模块级复制，排除 tests/cache）
python3 - "$REPO_DIR/memory-service" "$DIST/runtime/app" << 'PYEOF'
import shutil, sys, os
src, dst = sys.argv[1], sys.argv[2]
shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
    "tests", "__pycache__", "*.pyc", ".pytest_cache", "__pycache__"))
for root, dirs, files in os.walk(dst):
    for d in list(dirs):
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d))
PYEOF

# 2.2 runtime/bridge
mkdir -p "$DIST/runtime/bridge"
cp "$BRIDGE_BUILD"/kylin_embedding*.so "$DIST/runtime/bridge/"

# 2.3 runtime/app/migrations（发布包内 Alembic 迁移）
python3 - "$REPO_DIR/migrations" "$DIST/runtime/app/migrations" << 'PYEOF'
import shutil, sys, os, re
src, dst = sys.argv[1], sys.argv[2]
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
# 使 env.py 可重定位（确定性重写，非字符串替换）：
# 打包后 migrations 位于 <prefix>/runtime/app/migrations；memory-service 位于
# <prefix>/runtime/app。env.py 运行 cwd = <prefix>/runtime/app（install 时 cd 到该目录），
# 且 alembic -c migrations/alembic.ini 已把 script_location 指向 migrations/。
# 因此只需把 db.schema 所在目录（= cwd = <prefix>/runtime/app）加入 sys.path。
env_py = os.path.join(dst, "env.py")
c = open(env_py).read()
# 删除原两处 sys.path.insert（其 parents[N] 相对位置已不适用）
c = re.sub(r'^\s*sys\.path\.insert\(0, str\(Path\(__file__\)\.resolve\(\)\.parents\[[01]\].*?\)\)\s*$',
           '', c, flags=re.M)
# 在 from db.schema import 之前插入确定性 sys.path（cwd 即 runtime/app）
anchor = "from db.schema import metadata"
assert anchor in c, "env.py 缺少 from db.schema import metadata"
c = c.replace(anchor,
              "import os\n"
              "sys.path.insert(0, os.path.abspath(os.getcwd()))  # <prefix>/runtime/app\n\n"
              + anchor)
open(env_py, "w").write(c)
print("env.py rewritten deterministically")
PYEOF

# 2.4 内嵌 venv（重定位；tar 保留符号链接，规避 vboxsf 无法创建 symlink）
mkdir -p "$DIST/runtime/python"
tar -C /tmp/kylin-d14a-build-venv -cf - . | tar -C "$DIST/runtime/python" -xf -
sed -i 's/^command = .*/command = (relocatable)/' "$DIST/runtime/python/pyvenv.cfg"

# 2.5 bin/kylin-memory-server（可重定位 launcher）
cat > "$DIST/bin/kylin-memory-server" << 'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
SELF="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$SELF/runtime/app:$SELF/runtime/bridge"
exec "$SELF/runtime/python/bin/python" -m app "$@"
LAUNCHER
chmod 0755 "$DIST/bin/kylin-memory-server"

# 2.6 config example
cp "$REPO_DIR/config/environment.example" "$DIST/config/config.toml.example" 2>/dev/null \
  || cat > "$DIST/config/config.toml.example" << 'CFG'
[socket]
path = "$XDG_RUNTIME_DIR/kylin-memory/memory.sock"

[database]
path = "~/.local/share/kylin-memory/kylin_memory.db"

[deadline]
default_ms = 5000
retrieve_ms = 150

[outbox]
poll_interval_s = 1
max_retries = 3

[embedding]
model = "default"

[log]
level = "INFO"
CFG

# 2.7 systemd 脚本
mkdir -p "$DIST/systemd"
cp "$REPO_DIR/packaging/systemd/kylin-memory.service" "$DIST/systemd/kylin-memory.service"
cp "$REPO_DIR/packaging/release/systemd_install.sh" "$DIST/systemd/install.sh"
cp "$REPO_DIR/packaging/release/systemd_uninstall.sh" "$DIST/systemd/uninstall.sh"
cp "$REPO_DIR/packaging/release/systemd_verify.sh" "$DIST/systemd/verify.sh"
# install 脚本在运行时把 ExecStart 的 %h/.local/bin 渲染为 <install_prefix>/bin

# 2.8 VERSION
echo "$PACKAGE_VERSION" > "$DIST/VERSION"

# ── Phase 2.9: 包内 Alembic migration smoke（BLOCKER 2 复审要求） ──
# 在临时 DB 上执行 upgrade head，证明发布包内迁移链可用（无源码依赖）
log "包内 Alembic migration smoke…"
MIGRATE_DB="/tmp/kylin-d14a-migrate-smoke.db"
rm -f "$MIGRATE_DB"
( cd "$DIST/runtime/app" \
  && KYLIN_MEMORY_DB="$MIGRATE_DB" PYTHONPATH="$DIST/runtime/app" \
     "$DIST/runtime/python/bin/alembic" -c migrations/alembic.ini upgrade head ) \
  || die "包内 Alembic migration smoke 失败"
"$DIST/runtime/python/bin/python" -c \
  "import sqlite3,os; c=sqlite3.connect('$MIGRATE_DB'); print('migrate head:', c.execute('SELECT version_num FROM alembic_version').fetchone()[0])" \
  || die "migration smoke 校验失败"
rm -f "$MIGRATE_DB"
log "包内 Alembic migration smoke: PASS"

# ── Phase 3: manifest + SHA256SUMS ──
python3 - "$DIST" "$PACKAGE_NAME" "$PACKAGE_VERSION" "$SOURCE_COMMIT" << 'PYEOF'
import sys, os, json, hashlib, datetime

dist = sys.argv[1]
name, ver, commit = sys.argv[2], sys.argv[3], sys.argv[4]

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

files = {}
for root, dirs, fnames in os.walk(dist):
    for f in fnames:
        p = os.path.join(root, f)
        rel = os.path.relpath(p, dist)
        files[rel] = {"size": os.path.getsize(p), "sha256": sha256(p)}

# 断言：files 全集与磁盘真实常规文件一致（manifest.json / SHA256SUMS 在建时尚未存在，
# 天然不进入 files/SHA256SUMS；Gate 侧以 manifest.files == SHA256SUMS 双向一致为准，故此处
# 无需也无法把它们包含进来。此断言防 files 与磁盘 walk 集漂移。）
on_disk = set()
for root, dirs, fnames in os.walk(dist):
    for f in fnames:
        on_disk.add(os.path.relpath(os.path.join(root, f), dist))
on_disk -= {"manifest.json", "SHA256SUMS"}
assert set(files) == on_disk, "files 集与磁盘 walk 集不一致"

manifest = {
    "package_name": name,
    "package_version": ver,
    "source_commit": commit,
    "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "target_os": "银河麒麟桌面 V11 2603 x86_64",
    "target_arch": "amd64",
    "sdk": {"so_path": "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0",
            "version": "1.2.0.0-0k0.4",
            "sha256": "028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48"},
    "runtime": {"version": "kylin-ai-runtime 1.2.0.4-0k0.1"},
    "model": {"identity": "ensemble-embd_gte-base_uint8-text", "dimension": 768},
    "files": files,
}
json.dump(manifest, open(os.path.join(dist, "manifest.json"), "w"), indent=2, ensure_ascii=False)

with open(os.path.join(dist, "SHA256SUMS"), "w") as f:
    for rel in sorted(files):
        f.write(f"{files[rel]['sha256']}  {rel}\n")
PYEOF

log "DONE: $DIST"
log "文件数: $(find "$DIST" -type f | wc -l) | 大小: $(du -sh "$DIST" | cut -f1)"
log "manifest: $DIST/manifest.json"
log "SHA256SUMS: $DIST/SHA256SUMS"