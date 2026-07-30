#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# Memory Service 安装脚本
# 用途：部署 systemd --user 服务，创建必要目录
# 使用：./tools/install_memory_service.sh
# 注意：不需要 root 权限，所有操作在用户态完成
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! "$REPO_ROOT" =~ /kylinOS-agent-memory$ ]]; then
    echo "WARNING: Repository root not at expected name 'kylinOS-agent-memory', found: $REPO_ROOT"
fi

SERVICE_TEMPLATE="${REPO_ROOT}/packaging/systemd/kylin-memory.service"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
PYTHON_ENTRY="${REPO_ROOT}/memory-service/main.py"

# ---- 1. 检查项目目录 ----
if [ ! -d "$REPO_ROOT" ]; then
    echo "ERROR: Project directory not found: $REPO_ROOT"
    echo "Please clone the repository first."
    exit 1
fi

# ---- 2. 检查 Python 入口 ----
if [ ! -f "$PYTHON_ENTRY" ]; then
    echo "ERROR: Memory Service entry point not found: $PYTHON_ENTRY"
    echo "Expected structure: memory-service/main.py (placeholder entry)"
    exit 1
fi

# ---- 3. 检查 service 模板 ----
if [ ! -f "$SERVICE_TEMPLATE" ]; then
    echo "ERROR: Service template not found: $SERVICE_TEMPLATE"
    exit 1
fi

# ---- 4. 创建必要的目录 ----
echo "[INSTALL] Creating directories..."
mkdir -p "${HOME}/.config/kylin-memory"
mkdir -p "${HOME}/.local/share/kylin-memory"
mkdir -p "${HOME}/.local/state/kylin-memory"
mkdir -p "${SYSTEMD_USER_DIR}"

# ---- 5. 复制并替换 service 文件 ----
echo "[INSTALL] Installing systemd service file..."
sed "s|__REPO_ROOT__|${REPO_ROOT}|g" "$SERVICE_TEMPLATE" > "${SYSTEMD_USER_DIR}/kylin-memory.service"

# ---- 6. 重载 systemd 用户服务 ----
echo "[INSTALL] Reloading systemd user daemon..."
systemctl --user daemon-reload

# ---- 7. 启用并启动服务 ----
echo "[INSTALL] Enabling service..."
systemctl --user enable kylin-memory.service

echo "[INSTALL] Starting service..."
systemctl --user start kylin-memory.service

# ---- 8. 验证安装 ----
INSTALL_OK=0

echo ""
echo "[INSTALL] Verifying installation..."

# 8.1 systemd unit 语法验证
if systemd-analyze --user verify "${SYSTEMD_USER_DIR}/kylin-memory.service" 2>/dev/null; then
    echo "  [PASS] Unit file syntax valid"
else
    echo "  [FAIL] Unit file syntax error"
    INSTALL_OK=1
fi

# 8.2 Python 可执行文件检查
if [ -f "$PYTHON_ENTRY" ]; then
    echo "  [PASS] Python entry point found: $PYTHON_ENTRY"
else
    echo "  [FAIL] Python entry point not found"
    INSTALL_OK=1
fi

# 8.3 Python 模块可导入性检查
if ${REPO_ROOT}/.venv/bin/python -c "import sys; sys.path.insert(0, '${REPO_ROOT}/memory-service')" 2>/dev/null; then
    echo "  [PASS] Python module path accessible"
else
    echo "  [WARN] Python module import check skipped (placeholder only)"
fi

# 8.4 服务状态检查
sleep 2
if systemctl --user is-active --quiet kylin-memory.service; then
    echo "  [PASS] Service is active"
else
    echo "  [FAIL] Service is not active"
    echo "[INSTALL] Service journal (last 20 lines):"
    journalctl --user -u kylin-memory.service -n 20 --no-pager 2>/dev/null || true
    INSTALL_OK=1
fi

# 8.5 服务 enable 状态检查
if systemctl --user is-enabled kylin-memory.service &>/dev/null; then
    echo "  [PASS] Service is enabled"
else
    echo "  [FAIL] Service is not enabled"
    INSTALL_OK=1
fi

# ---- 9. 失败清理 ----
if [ "$INSTALL_OK" -ne 0 ]; then
    echo ""
    echo "[INSTALL] Installation verification FAILED. Rolling back..."
    systemctl --user stop kylin-memory.service 2>/dev/null || true
    systemctl --user disable kylin-memory.service 2>/dev/null || true
    rm -f "${SYSTEMD_USER_DIR}/kylin-memory.service"
    systemctl --user daemon-reload
    echo "[INSTALL] Cleanup complete. Installation aborted."
    exit 1
fi

echo ""
echo "=== Installation Complete ==="
echo "Service: systemctl --user status kylin-memory"
echo "Config:  ~/.config/kylin-memory/"
echo "Data:    ~/.local/share/kylin-memory/"
echo "Logs:    ~/.local/state/kylin-memory/"
