#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# AI Runtime 版本快照采集脚本
# 功能: 采集当前系统所有 AI Runtime 软件包的精确版本、架构、
#       SHA-256，并输出不可变 manifest 文件
# 用途: 作为回退基线参照，提供版本比对能力
# 输出: packaging/original-packages/package-manifest-<timestamp>.txt
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/packaging/original-packages"
MANIFEST_TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
MANIFEST_FILE="${BACKUP_DIR}/package-manifest-${MANIFEST_TIMESTAMP}.txt"
MANIFEST_LATEST="${BACKUP_DIR}/package-manifest-latest.txt"

mkdir -p "$BACKUP_DIR"

PKG_WHITELIST=(
    "kylin-ai-runtime"
    "libkysdk-ai-common"
    "libkylin-coreai-embedding"
    "libkylin-ondevice-embedding-engine"
    "libkylin-ondevice-traditional-ai-engine-plugin"
    "kylin-ai-abstract-models"
    "kylin-gte-base-model"
    "kytensor-client"
    "kytensor-server"
    "kytensor-python"
    "onnxruntime-backend"
    "libkysdk-vector-engine-client"
    "kylin-ai-vector-engine"
)

{
    echo "# Kylin AI Runtime Package Manifest"
    echo "# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "# Host: $(hostname)"
    echo "# OS: $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"
    echo "# Arch: $(uname -m)"
    echo "# Commit: $(cd "${REPO_ROOT}" && git rev-parse HEAD 2>/dev/null || echo 'N/A')"
    echo "#"
    echo "# Format: <package-name>|<version>|<architecture>|<sha256>|<status>|<cache-path>"
    echo "#"
} > "$MANIFEST_FILE"

PASS=0
FAIL=0

for pkg in "${PKG_WHITELIST[@]}"; do
    PKG_INFO=$(dpkg -l "$pkg" 2>/dev/null | grep -E "^[a-z]i" || echo "")
    if [ -z "$PKG_INFO" ]; then
        echo "${pkg}|N/A|N/A|N/A|NOT_INSTALLED|N/A" >> "$MANIFEST_FILE"
        ((++FAIL))
        continue
    fi

    VERSION=$(echo "$PKG_INFO" | awk '{print $3}')
    ARCH=$(echo "$PKG_INFO" | awk '{print $4}')

    DEB_PATH=$(find /var/cache/apt/archives -name "${pkg}_${VERSION}_${ARCH}.deb" 2>/dev/null | head -1 || echo "N/A")

    if [ "$DEB_PATH" != "N/A" ] && [ -f "$DEB_PATH" ]; then
        SHA256=$(sha256sum "$DEB_PATH" | awk '{print $1}')
        STATUS="CACHED"
    else
        SHA256="N/A"
        STATUS="NOT_CACHED"
    fi

    printf "%s|%s|%s|%s|%s|%s\n" "$pkg" "$VERSION" "$ARCH" "$SHA256" "$STATUS" "$DEB_PATH" >> "$MANIFEST_FILE"
    ((++PASS))
done

cp "$MANIFEST_FILE" "$MANIFEST_LATEST"

echo ""
echo "=== Package Snapshot Complete ==="
echo "  Passed:  $PASS packages captured"
echo "  Failed:  $FAIL packages not found"
echo "  Manifest: $MANIFEST_FILE"
echo ""
echo "NOTE: This script captures version metadata only."
echo "To backup actual .deb files, use:"
echo "  mkdir -p ${BACKUP_DIR}/deb-backup-${MANIFEST_TIMESTAMP}"
echo "  for pkg in ${PKG_WHITELIST[*]}; do"
echo "    find /var/cache/apt/archives -name \"\${pkg}_*.deb\" -exec cp {} ${BACKUP_DIR}/deb-backup-${MANIFEST_TIMESTAMP}/ \;"
echo "  done"
