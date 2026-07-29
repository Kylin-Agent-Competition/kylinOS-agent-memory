#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# 麒麟虚拟机环境自检脚本
# 用途：检查 Memory Service 运行所需的全部环境和依赖
# 使用：在麒麟虚拟机执行 ./tools/env_check.sh
# ============================================================

PASS=0
FAIL=0

check_pass() { echo "  [PASS] $1"; ((PASS++)); }
check_fail() { echo "  [FAIL] $1 - $2"; ((FAIL++)); }

echo "================================================"
echo "  Kylin Memory Environment Check"
echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Host: $(hostname)"
echo "================================================"
echo ""

# ---- 1. OS & Architecture ----
echo "--- 1. OS & Architecture ---"
if [ -f /etc/os-release ]; then
    check_pass "OS: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"')"
else
    check_fail "OS" "/etc/os-release not found"
fi
check_pass "Architecture: $(uname -m)"

# ---- 2. Python ----
echo ""
echo "--- 2. Python ---"
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    check_pass "$PY_VER"
else
    check_fail "python3" "not found"
fi

# ---- 3. AI Runtime Packages ----
echo ""
echo "--- 3. AI Runtime Packages ---"
PKG_LIST=(
    "kylin-ai-runtime"
    "libkysdk-ai-common"
    "libkylin-coreai-embedding"
    "libkylin-ondevice-embedding-engine"
    "kylin-ai-abstract-models"
    "kylin-gte-base-model"
    "kytensor-client"
    "kytensor-server"
    "kytensor-python"
    "onnxruntime-backend"
    "libkysdk-vector-engine-client"
    "kylin-ai-vector-engine"
)

for pkg in "${PKG_LIST[@]}"; do
    VER=$(dpkg -l "$pkg" 2>/dev/null | grep "^ii" | awk '{print $3}' || echo "")
    if [ -n "$VER" ]; then
        check_pass "$pkg = $VER"
    else
        check_fail "$pkg" "not installed or version unknown"
    fi
done

# ---- 4. Kaiming (麒灵 AI 助手) ----
echo ""
echo "--- 4. Kaiming ---"
KAIMING_BIN="/opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/3.0.67/files/bin/kylin-aiassistant"
if [ -f "$KAIMING_BIN" ]; then
    check_pass "Kaiming binary: $KAIMING_BIN"
else
    check_fail "Kaiming binary" "$KAIMING_BIN not found"
fi

KAIMING_DB="${HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"
if [ -f "$KAIMING_DB" ]; then
    check_pass "Chat database: $KAIMING_DB"
else
    check_fail "Chat database" "$KAIMING_DB not found"
fi

# ---- 5. Runtime Paths ----
echo ""
echo "--- 5. Runtime Paths ---"
DEPENDS="/usr/lib/kylin-ai/depends"
if [ -d "$DEPENDS" ]; then
    check_pass "Runtime depends: $DEPENDS"
else
    check_fail "Runtime depends" "$DEPENDS not found"
fi

MODELS="/usr/share/kylin-ai/model-repository"
if [ -d "$MODELS" ]; then
    check_pass "Model repository: $MODELS"
else
    check_fail "Model repository" "$MODELS not found"
fi

MODELS_APP="/opt/appdata/kylin-ai/model-repository"
if [ -d "$MODELS_APP" ]; then
    check_pass "App model repository: $MODELS_APP"
else
    check_fail "App model repository" "$MODELS_APP not found"
fi

# ---- 6. Kytensor ----
echo ""
echo "--- 6. Kytensor ---"
if curl -s http://127.0.0.1:8000/health &>/dev/null || curl -s http://127.0.0.1:8000/ &>/dev/null; then
    check_pass "Kytensor HTTP: 127.0.0.1:8000 (reachable)"
else
    check_fail "Kytensor HTTP" "127.0.0.1:8000 not reachable (may be OK if not running)"
fi

# ---- 7. Project Directories ----
echo ""
echo "--- 7. Project Directories ---"
PROJECT_DIR="${HOME}/projects/kylin-memory-sdk"
if [ -d "$PROJECT_DIR" ]; then
    check_pass "Project dir: $PROJECT_DIR"
else
    check_fail "Project dir" "$PROJECT_DIR not found"
fi

MEM_DIRS=(
    "${HOME}/.config/kylin-memory"
    "${HOME}/.local/share/kylin-memory"
    "${HOME}/.local/state/kylin-memory"
)

for d in "${MEM_DIRS[@]}"; do
    if [ -d "$d" ]; then
        check_pass "Memory dir: $d"
    else
        echo "  [INFO] $d does not exist yet (will be created by install script)"
    fi
done

# ---- 8. Build Tools ----
echo ""
echo "--- 8. Build Tools ---"
DEV_TOOLS=("g++" "cmake" "ninja" "git" "pkg-config" "python3-dev" "sqlite3")
for tool in "${DEV_TOOLS[@]}"; do
    if command -v "$tool" &>/dev/null; then
        check_pass "$tool available"
    else
        echo "  [INFO] $tool not found (may need to install development packages)"
    fi
done

# ---- 9. KYSEC Status ----
echo ""
echo "--- 9. KYSEC ---"
if command -v kysec_set &>/dev/null; then
    check_pass "kysec_set available"
else
    check_fail "kysec_set" "command not found"
fi

# ---- Summary ----
echo ""
echo "================================================"
echo "  Summary: $PASS PASSED, $FAIL FAILED"
echo "================================================"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Some checks failed. Review the items above."
    echo "For missing packages, enter maintenance mode and install:"
    echo "  sudo mm-cli -o"
    echo "  sudo apt install -y <packages...>"
    echo "  sudo mm-cli -c -a"
    echo "  sudo reboot"
fi