#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# AI Runtime 软件包安全回退脚本
# 功能: 基于 manifest 文件精确回退所有 AI Runtime 软件包
# 前提:
#   1. 必须先执行 snapshot_package_versions.sh 生成 manifest
#   2. 必须有与 manifest 对应的 .deb 备份
#   3. 必须进入维护模式 (sudo mm-cli -o)
# 注意事项:
#   - 任意包失败立即中止
#   - 安装前校验 SHA-256
#   - 安装后逐包验证
#   - 输出最终状态判断
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/packaging/original-packages"
MANIFEST_FILE="${BACKUP_DIR}/package-manifest-latest.txt"
BACKUP_ID=""

# ---- 1. 前置条件检查 ----
echo "[ROLLBACK] Pre-flight checks..."

# 1.1 维护模式检查
if ! systemctl is-system-running 2>/dev/null | grep -qE "maintenance|degraded|stopped"; then
    echo "WARNING: System appears to be in normal runlevel."
    echo "Rollback should be performed in maintenance mode."
    echo "Enter maintenance mode: sudo mm-cli -o"
    read -p "Continue anyway? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
fi

# 1.2 manifest 文件检查
if [ ! -f "$MANIFEST_FILE" ]; then
    echo "ERROR: Manifest file not found: $MANIFEST_FILE"
    echo "Run snapshot_package_versions.sh first to generate a manifest."
    exit 1
fi
echo "  [OK] Manifest: $MANIFEST_FILE"

# 1.3 提取 backup_id (时间戳)
BACKUP_ID=$(basename "$(readlink -f "$MANIFEST_FILE")" | sed 's/package-manifest-//' | sed 's/\.txt$//')
echo "  [OK] Backup ID: $BACKUP_ID"
DEB_BACKUP_DIR="${BACKUP_DIR}/deb-backup-${BACKUP_ID}"

# ---- 2. 停止相关 Runtime 服务 ----
echo "[ROLLBACK] Stopping AI Runtime services..."
if systemctl --user is-active --quiet kylin-memory.service 2>/dev/null; then
    systemctl --user stop kylin-memory.service
    echo "  [OK] Stopped kylin-memory service"
fi

# ---- 3. 解析 manifest 并校验 ----
echo "[ROLLBACK] Parsing and validating manifest..."
declare -A PKG_VERSIONS
declare -A PKG_ARCHS
declare -A PKG_SHA256S

PACKAGES_TO_INSTALL=()
while IFS='|' read -r pkg version arch sha256 status cache_path; do
    [[ "$pkg" =~ ^# ]] && continue
    [[ -z "$pkg" ]] && continue

    if [ "$status" = "NOT_INSTALLED" ] || [ "$status" = "N/A" ]; then
        echo "  [SKIP] $pkg not in baseline (status: $status)"
        continue
    fi

    PKG_VERSIONS["$pkg"]="$version"
    PKG_ARCHS["$pkg"]="$arch"
    PKG_SHA256S["$pkg"]="$sha256"

    DEB_PATH="${DEB_BACKUP_DIR}/${pkg}_${version}_${arch}.deb"
    if [ ! -f "$DEB_PATH" ]; then
        DEB_PATH=$(find "$BACKUP_DIR" -name "${pkg}_${version}_${arch}.deb" 2>/dev/null | head -1 || echo "")
    fi

    if [ -z "$DEB_PATH" ] || [ ! -f "$DEB_PATH" ]; then
        echo "  [FAIL] .deb not found for $pkg ($version, $arch)"
        exit 1
    fi

    ACTUAL_SHA256=$(sha256sum "$DEB_PATH" | awk '{print $1}')
    if [ "$sha256" != "N/A" ] && [ "$ACTUAL_SHA256" != "$sha256" ]; then
        echo "  [FAIL] SHA-256 mismatch for $pkg:"
        echo "         Expected: $sha256"
        echo "         Actual:   $ACTUAL_SHA256"
        exit 1
    fi

    PACKAGES_TO_INSTALL+=("$DEB_PATH")
    echo "  [OK] $pkg = $version ($arch) [SHA-256: ${sha256:0:16}...]"
done < "$MANIFEST_FILE"

if [ ${#PACKAGES_TO_INSTALL[@]} -eq 0 ]; then
    echo "ERROR: No valid packages to install."
    exit 1
fi
echo "  Total packages to install: ${#PACKAGES_TO_INSTALL[@]}"

# ---- 4. 确认操作 ----
echo ""
echo "================================================"
echo "  READY TO ROLLBACK ${#PACKAGES_TO_INSTALL[@]} packages"
echo "  Backup ID: $BACKUP_ID"
echo "================================================"
echo ""
read -p "Type 'ROLLBACK' to confirm: " CONFIRM
if [ "$CONFIRM" != "ROLLBACK" ]; then
    echo "Aborted."
    exit 0
fi

# ---- 5. 执行安装 (任意失败立即中止) ----
echo "[ROLLBACK] Installing packages..."
FAILED_PKGS=()
for deb in "${PACKAGES_TO_INSTALL[@]}"; do
    PKG_NAME=$(basename "$deb" | sed 's/_.*//')
    echo "  Installing: $PKG_NAME ($(basename "$deb"))"
    if ! sudo dpkg -i "$deb" 2>&1; then
        echo "  [FAIL] dpkg installation failed for $PKG_NAME"
        FAILED_PKGS+=("$PKG_NAME")
    fi
done

if [ ${#FAILED_PKGS[@]} -gt 0 ]; then
    echo ""
    echo "[ROLLBACK] FAILED packages: ${FAILED_PKGS[*]}"
    echo "Rollback aborted. System is in indeterminate state."
    exit 1
fi

# ---- 6. 固定版本以防止 apt upgrade 升级 ----
echo "[ROLLBACK] Holding packages at baseline versions..."
for pkg in "${!PKG_VERSIONS[@]}"; do
    sudo apt-mark hold "$pkg" 2>/dev/null || echo "  [WARN] Could not hold $pkg"
done

# ---- 7. 安装后逐包验证 ----
echo "[ROLLBACK] Verifying installed packages..."
ROLLBACK_OK=0
for pkg in "${!PKG_VERSIONS[@]}"; do
    EXPECTED_VERSION="${PKG_VERSIONS[$pkg]}"
    EXPECTED_ARCH="${PKG_ARCHS[$pkg]}"

    INSTALLED_INFO=$(dpkg -l "$pkg" 2>/dev/null | grep -E "^[a-z]i" || echo "")
    if [ -z "$INSTALLED_INFO" ]; then
        echo "  [FAIL] $pkg not installed"
        ROLLBACK_OK=1
        continue
    fi

    INSTALLED_VERSION=$(echo "$INSTALLED_INFO" | awk '{print $3}')
    INSTALLED_ARCH=$(echo "$INSTALLED_INFO" | awk '{print $4}')

    if [ "$INSTALLED_VERSION" != "$EXPECTED_VERSION" ]; then
        echo "  [FAIL] $pkg version mismatch: expected $EXPECTED_VERSION, got $INSTALLED_VERSION"
        ROLLBACK_OK=1
    elif [ "$INSTALLED_ARCH" != "$EXPECTED_ARCH" ] && [ "$EXPECTED_ARCH" != "all" ]; then
        echo "  [FAIL] $pkg arch mismatch: expected $EXPECTED_ARCH, got $INSTALLED_ARCH"
        ROLLBACK_OK=1
    else
        echo "  [OK] $pkg = $INSTALLED_VERSION ($INSTALLED_ARCH)"
    fi
done

# ---- 8. Smoke Test ----
echo "[ROLLBACK] Running smoke tests..."

if command -v kytensor-server &>/dev/null; then
    echo "  [OK] kytensor-server binary found"
else
    echo "  [WARN] kytensor-server not found"
fi

EMBEDDING_LIB="/usr/lib/libkylin-coreai-embedding.so"
if [ -f "$EMBEDDING_LIB" ]; then
    echo "  [OK] Embedding library found: $EMBEDDING_LIB"
else
    echo "  [WARN] Embedding library not found"
fi

VECTOR_LIB="/usr/lib/libkysdk-vector-engine-client.so"
if [ -f "$VECTOR_LIB" ]; then
    echo "  [OK] Vector client library found: $VECTOR_LIB"
else
    echo "  [WARN] Vector client library not found"
fi

# ---- 9. 最终结果 ----
echo ""
if [ "$ROLLBACK_OK" -eq 0 ]; then
    echo "ROLLBACK_COMPLETE=PASS"
    echo "Backup ID: $BACKUP_ID"
    echo "All ${#PACKAGES_TO_INSTALL[@]} packages verified."
    echo "Please reboot: sudo reboot"
else
    echo "ROLLBACK_COMPLETE=FAIL"
    echo "Some packages failed verification. Review output above."
    exit 1
fi
