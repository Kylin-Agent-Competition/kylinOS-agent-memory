#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# Memory Service 卸载脚本
# 用途：停止并移除 systemd --user 服务和相关配置
# 使用：./tools/uninstall_memory_service.sh [--purge-data] [--purge-config]
# 注意：默认保留用户数据，--purge-data 可清理所有数据
# ============================================================

SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="kylin-memory.service"
PURGE_DATA=false

for arg in "$@"; do
    case "$arg" in
        --purge-data)
            PURGE_DATA=true
            ;;
        --purge-config)
            PURGE_DATA=true
            ;;
    esac
done

echo "[UNINSTALL] Kylin Memory Service"

# ---- 1. 保存卸载前状态 ----
echo "[UNINSTALL] Capturing pre-uninstall state..."
PRE_ACTIVE="unknown"
if systemctl --user is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    PRE_ACTIVE="active"
else
    PRE_ACTIVE="inactive"
fi
echo "  Pre-uninstall service state: $PRE_ACTIVE"

# ---- 2. 停止服务 ----
echo "[UNINSTALL] Stopping service..."
if systemctl --user stop "$SERVICE_NAME" 2>/dev/null; then
    echo "  [OK] Service stopped"
else
    echo "  [INFO] Service was not running (already stopped)"
fi

# ---- 3. 禁用服务 ----
echo "[UNINSTALL] Disabling service..."
if systemctl --user disable "$SERVICE_NAME" 2>/dev/null; then
    echo "  [OK] Service disabled"
else
    echo "  [INFO] Service was not enabled"
fi

# ---- 4. 删除 unit 文件 ----
echo "[UNINSTALL] Removing unit file..."
if rm -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}"; then
    echo "  [OK] Unit file removed"
else
    echo "  [FAIL] Failed to remove unit file"
    exit 1
fi

# ---- 5. 清理残留启用链接 ----
RESIDUAL_DIRS=(
    "${SYSTEMD_USER_DIR}/default.target.wants"
    "${SYSTEMD_USER_DIR}/multi-user.target.wants"
)
for dir in "${RESIDUAL_DIRS[@]}"; do
    if [ -L "${dir}/${SERVICE_NAME}" ]; then
        rm -f "${dir}/${SERVICE_NAME}"
        echo "  [OK] Removed residual symlink: ${dir}/${SERVICE_NAME}"
    fi
done

# ---- 6. 重载 systemd ----
echo "[UNINSTALL] Reloading systemd daemon..."
systemctl --user daemon-reload
echo "  [OK] Daemon reloaded"

# ---- 7. 验证卸载结果 ----
echo "[UNINSTALL] Verifying uninstall..."
UNINSTALL_OK=0

# 7.1 确认服务未 active
if systemctl --user is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "  [FAIL] Service is still active"
    UNINSTALL_OK=1
else
    echo "  [PASS] Service is not active"
fi

# 7.2 确认服务未 enabled
if systemctl --user is-enabled "$SERVICE_NAME" 2>/dev/null; then
    echo "  [WARN] Service may still be enabled (is-enabled returned success)"
    UNINSTALL_OK=1
else
    echo "  [PASS] Service is not enabled"
fi

# 7.3 确认 unit 文件已删除
if [ -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}" ]; then
    echo "  [FAIL] Unit file still exists"
    UNINSTALL_OK=1
else
    echo "  [PASS] Unit file removed"
fi

# ---- 8. 配置目录处理 ----
if $PURGE_DATA; then
    echo "[UNINSTALL] Purging config and data directories..."
    rm -rf "${HOME}/.config/kylin-memory/"
    rm -rf "${HOME}/.local/share/kylin-memory/"
    rm -rf "${HOME}/.local/state/kylin-memory/"
    echo "  [OK] Config and data purged"
else
    echo "[UNINSTALL] Keeping user data (use --purge-data to remove)"
fi

# ---- 9. 最终结果 ----
if [ "$UNINSTALL_OK" -eq 0 ]; then
    echo ""
    echo "=== Uninstall Complete ==="
    echo "Note: User data directories preserved (use --purge-data to remove)."
else
    echo ""
    echo "=== Uninstall Completed with Warnings ==="
    echo "Please review the warnings above."
    exit 1
fi
