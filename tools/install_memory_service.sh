#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# Memory Service 安装脚本
# 用途：部署 systemd --user 服务，创建必要目录
# 使用：./tools/install_memory_service.sh
# 注意：不需要 root 权限，所有操作在用户态完成
# ============================================================

PROJECT_DIR="${HOME}/projects/kylin-memory-sdk"
SERVICE_FILE="${PROJECT_DIR}/packaging/systemd/kylin-memory.service"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

# ---- 1. 检查项目目录 ----
if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERROR: Project directory not found: $PROJECT_DIR"
    echo "Please clone the repository first."
    exit 1
fi

# ---- 2. 创建必要的目录 ----
echo "[INSTALL] Creating directories..."
mkdir -p "${HOME}/.config/kylin-memory"
mkdir -p "${HOME}/.local/share/kylin-memory"
mkdir -p "${HOME}/.local/state/kylin-memory"
mkdir -p "${SYSTEMD_USER_DIR}"

# ---- 3. 复制 service 文件 ----
echo "[INSTALL] Installing systemd service file..."
cp "$SERVICE_FILE" "${SYSTEMD_USER_DIR}/kylin-memory.service"

# ---- 4. 重载 systemd 用户服务 ----
echo "[INSTALL] Reloading systemd user daemon..."
systemctl --user daemon-reload

# ---- 5. 启用并启动服务 ----
echo "[INSTALL] Enabling service..."
systemctl --user enable kylin-memory.service

echo "[INSTALL] Starting service..."
systemctl --user start kylin-memory.service

# ---- 6. 检查状态 ----
echo ""
echo "[INSTALL] Service status:"
systemctl --user status kylin-memory.service --no-pager || true

echo ""
echo "=== Installation Complete ==="
echo "Service: systemctl --user status kylin-memory"
echo "Config:  ~/.config/kylin-memory/"
echo "Data:    ~/.local/share/kylin-memory/"
echo "Logs:    ~/.local/state/kylin-memory/"