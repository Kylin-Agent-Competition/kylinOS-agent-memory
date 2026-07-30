#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# KYSEC 单文件 verified 放行脚本（安全增强版）
# 功能: 对项目构建产物设置 KYSEC verified 标记
# 限制:
#   - 只允许项目 build/ 目录下的 ELF 可执行文件
#   - 拒绝符号链接、系统目录
#   - 保存修改前状态
#   - 记录可追溯的操作日志
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOGFILE="${HOME}/.local/state/kylin-memory/kysec_allow.log"

mkdir -p "$(dirname "$LOGFILE")"

usage() {
    echo "Usage: $0 <binary_path>"
    echo ""
    echo "Restrictions:"
    echo "  - Only ELF executables under ${REPO_ROOT}/build/ are allowed"
    echo "  - Symlinks are rejected"
    echo "  - System directories (/usr, /bin, /lib, /opt) are rejected"
    echo ""
    echo "Example: $0 ${REPO_ROOT}/build/test_embedding"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

BIN="$1"

# ---- 1. 解析为绝对路径，拒绝符号链接 ----
BIN_REAL=$(realpath "$BIN" 2>/dev/null || echo "")
if [ -z "$BIN_REAL" ]; then
    echo "ERROR: Cannot resolve path: $BIN"
    exit 1
fi

if [ "$BIN" != "$BIN_REAL" ]; then
    echo "ERROR: Symlinks are not allowed:"
    echo "  Given:    $BIN"
    echo "  Resolved: $BIN_REAL"
    exit 1
fi

# ---- 2. 目标必须在项目 build/ 目录下 ----
if [[ ! "$BIN_REAL" =~ ^${REPO_ROOT}/build/ ]]; then
    echo "ERROR: Binary must be under ${REPO_ROOT}/build/"
    echo "  Given: $BIN_REAL"
    exit 1
fi

# ---- 3. 拒绝系统目录 ----
SYSTEM_DIRS=("/usr/" "/bin/" "/lib" "/lib64" "/opt/" "/etc/" "/boot/" "/sys/" "/proc/")
for sd in "${SYSTEM_DIRS[@]}"; do
    if [[ "$BIN_REAL" =~ ^${sd} ]]; then
        echo "ERROR: System directory not allowed: $sd"
        exit 1
    fi
done

# ---- 4. 检查为 ELF 可执行文件 ----
if [ ! -f "$BIN_REAL" ]; then
    echo "ERROR: File not found: $BIN_REAL"
    exit 1
fi

if [ ! -x "$BIN_REAL" ]; then
    echo "ERROR: File is not executable: $BIN_REAL"
    exit 1
fi

FILE_TYPE=$(file -b "$BIN_REAL" 2>/dev/null || echo "unknown")
if ! echo "$FILE_TYPE" | grep -q "ELF"; then
    echo "ERROR: Not an ELF binary: $FILE_TYPE"
    exit 1
fi

# ---- 5. 保存修改前 KYSEC 状态 ----
PREV_STATE=$(sudo kysec_get -n exectl "$BIN_REAL" 2>/dev/null || echo "unknown")
SHA256=$(sha256sum "$BIN_REAL" | awk '{print $1}')

# ---- 6. 执行放行 ----
echo "[KYSEC] Target: $BIN_REAL"
echo "[KYSEC] Type: $(file -b "$BIN_REAL")"
echo "[KYSEC] SHA-256: $SHA256"
echo "[KYSEC] Previous state: $PREV_STATE"

sudo kysec_set -n exectl -v verified "$BIN_REAL"

# ---- 7. 验证修改后状态 ----
NEW_STATE=$(sudo kysec_get -n exectl "$BIN_REAL" 2>/dev/null || echo "unknown")
if [ "$NEW_STATE" = "verified" ]; then
    echo "[KYSEC] SUCCESS: verified"
else
    echo "[KYSEC] WARNING: State after set is '$NEW_STATE', expected 'verified'"
fi

# ---- 8. 记录操作日志 ----
COMMIT=$(cd "${REPO_ROOT}" && git rev-parse HEAD 2>/dev/null || echo "N/A")
{
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "  binary: $BIN_REAL"
    echo "  sha256: $SHA256"
    echo "  prev_state: $PREV_STATE"
    echo "  new_state: $NEW_STATE"
    echo "  commit: $COMMIT"
    echo "  host: $(hostname)"
    echo "  user: $(whoami)"
    echo "---"
} >> "$LOGFILE"

echo ""
echo "[KYSEC] To revert this change:"
echo "  sudo kysec_set -n exectl -v default \"$BIN_REAL\""
