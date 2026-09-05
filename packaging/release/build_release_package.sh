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
import shutil, sys, os
src, dst = sys.argv[1], sys.argv[2]
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
# 使 env.py 可重定位：migrations 与 memory-service 同在 runtime/app 下
env_py = os.path.join(dst, "env.py")
c = open(env_py).read()
c = c.replace(
    'sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory-service"))',
    'sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # <prefix>/runtime/app')
c = c.replace(
    'sys.path.insert(0, str(Path(__file__).resolve().parents[1]))',
    'sys.path.insert(0, str(Path(__file__).resolve().parents[0]))')
open(env_py, "w").write(c)
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
cp "$REPO_DIR/packaging/systemd/kylin-memory.service" "$DIST/systemd/"
cp "$REPO_DIR/packaging/release/systemd_install.sh" "$DIST/systemd/install.sh"
cp "$REPO_DIR/packaging/release/systemd_uninstall.sh" "$DIST/systemd/uninstall.sh"
cp "$REPO_DIR/packaging/release/systemd_verify.sh" "$DIST/systemd/verify.sh"

# 2.8 VERSION
echo "$PACKAGE_VERSION" > "$DIST/VERSION"

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