#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# 当前 AI 软件包备份脚本
# 用途：备份当前安装的所有 AI Runtime 软件包信息
# 使用：在麒麟虚拟机执行 ./tools/backup_current_packages.sh
# 输出清单：packaging/original-packages/installed-versions.txt
# ============================================================

PROJECT_DIR="${HOME}/projects/kylin-memory-sdk"
BACKUP_DIR="${PROJECT_DIR}/packaging/original-packages"
mkdir -p "$BACKUP_DIR"

OUTPUT_FILE="${BACKUP_DIR}/installed-versions.txt"

echo "=== Kylin AI Package Baseline Snapshot ===" > "$OUTPUT_FILE"
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUTPUT_FILE"
echo "Host: $(hostname)" >> "$OUTPUT_FILE"
echo "OS: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "--- dpkg -l (AI Runtime 相关) ---" >> "$OUTPUT_FILE"
dpkg -l 2>/dev/null | grep -E "kylin-ai|kytensor|onnx|vector|embedding|libkyai" >> "$OUTPUT_FILE" || echo "(none found)" >> "$OUTPUT_FILE"

echo "" >> "$OUTPUT_FILE"
echo "--- apt list --installed (AI Runtime 相关) ---" >> "$OUTPUT_FILE"
apt list --installed 2>/dev/null | grep -E "kylin-ai|kytensor|onnx|vector|embedding|libkyai" >> "$OUTPUT_FILE" || echo "(none found)" >> "$OUTPUT_FILE"

echo "" >> "$OUTPUT_FILE"
echo "--- System Info ---" >> "$OUTPUT_FILE"
uname -m >> "$OUTPUT_FILE"

echo ""
echo "[BACKUP] Package inventory saved to: $OUTPUT_FILE"
echo "[BACKUP] To backup .deb files, copy them from /var/cache/apt/archives/"
echo ""
echo "[BACKUP] Recommended: copy relevant .deb files to ${BACKUP_DIR}/"
echo "  find /var/cache/apt/archives -name '*kylin-ai*.deb' -exec cp {} ${BACKUP_DIR}/ \;"
echo "  find /var/cache/apt/archives -name '*kytensor*.deb' -exec cp {} ${BACKUP_DIR}/ \;"
echo "  find /var/cache/apt/archives -name '*onnx*.deb' -exec cp {} ${BACKUP_DIR}/ \;"
echo "  find /var/cache/apt/archives -name '*vector*.deb' -exec cp {} ${BACKUP_DIR}/ \;"
echo "  find /var/cache/apt/archives -name '*embedding*.deb' -exec cp {} ${BACKUP_DIR}/ \;"
echo "  find /var/cache/apt/archives -name '*libkyai*.deb' -exec cp {} ${BACKUP_DIR}/ \;"