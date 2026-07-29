#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# Memory Service 卸载脚本
# 用途：停止并移除 systemd --user 服务和相关配置
# 使用：./tools/uninstall_memory_service.sh
# 注意：不删除数据目录（~/.local/share/kylin-memory/）
# ============================================================

echo "[UNINSTALL] Stopping service..."
systemctl --user stop kylin-memory.service 2>/dev/null || true

echo "[UNINSTALL] Disabling service..."
systemctl --user disable kylin-memory.service 2>/dev/null || true

echo "[UNINSTALL] Removing service file..."
rm -f "${HOME}/.config/systemd/user/kylin-memory.service"

echo "[UNINSTALL] Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "[UNINSTALL] Cleaning config directory..."
rm -rf "${HOME}/.config/kylin-memory/"

echo ""
echo "=== Uninstall Complete ==="
echo "Note: Data in ~/.local/share/kylin-memory/ was NOT deleted."
echo "To fully remove data, run: rm -rf ~/.local/share/kylin-memory/"