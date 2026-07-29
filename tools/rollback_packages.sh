#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# AI Runtime 软件包回退脚本
# 用途：从备份 .deb 恢复所有 AI Runtime 软件包到基线版本
# 使用：在麒麟虚拟机维护模式内执行 ./tools/rollback_packages.sh
# 前提：需要预先备份 .deb 文件到 packaging/original-packages/
# 注意：需要进入维护模式（sudo mm-cli -o），不要用 mm-cli -c -n
# ============================================================

PROJECT_DIR="${HOME}/projects/kylin-memory-sdk"
BACKUP_DIR="${PROJECT_DIR}/packaging/original-packages"

echo "================================================"
echo "  AI Runtime Package Rollback Script"
echo "  Backup dir: $BACKUP_DIR"
echo "================================================"
echo ""

if [ ! -d "$BACKUP_DIR" ]; then
    echo "ERROR: Backup directory not found: $BACKUP_DIR"
    echo "Run backup_current_packages.sh first."
    exit 1
fi

DEB_COUNT=$(find "$BACKUP_DIR" -name "*.deb" 2>/dev/null | wc -l)
echo "Found $DEB_COUNT .deb files in backup directory."
echo ""

if [ "$DEB_COUNT" -eq 0 ]; then
    echo "WARNING: No .deb files found. Only version metadata is available."
    echo "Proceeding with inventory check only..."
    cat "${BACKUP_DIR}/installed-versions.txt" 2>/dev/null || echo "(no inventory file)"
    exit 1
fi

# ---- 确认操作 ----
echo "This will REINSTALL all AI Runtime packages from backup."
echo "Make sure you are in maintenance mode (sudo mm-cli -o)."
echo ""
read -p "Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "[ROLLBACK] Installing packages from $BACKUP_DIR ..."

for deb in "$BACKUP_DIR"/*.deb; do
    if [ -f "$deb" ]; then
        echo "  Installing: $(basename "$deb")"
        sudo dpkg -i "$deb" 2>&1 || echo "  WARNING: dpkg failed for $(basename "$deb"), continuing..."
    fi
done

echo ""
echo "[ROLLBACK] Fixing dependencies..."
sudo apt install -f -y 2>&1 || echo "  WARNING: apt install -f had issues"

echo ""
echo "[ROLLBACK] Verifying installed versions..."
dpkg -l | grep -E "kylin-ai|kytensor|onnx|vector|embedding|libkyai" || echo "(none found)"

echo ""
echo "=== Rollback Complete ==="
echo "Please reboot: sudo reboot"
echo "After reboot, verify: systemctl --user status kylin-memory"