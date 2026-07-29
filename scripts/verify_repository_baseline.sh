#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

echo "=============================================="
echo " 仓库基线结构验证"
echo "=============================================="
echo ""

check_file() {
    local file="$1"
    local desc="${2:-$1}"
    if [ -f "${PROJECT_ROOT}/${file}" ]; then
        echo "  ✓ ${desc}"
    else
        echo "  ✗ ${desc} 缺失: ${file}"
        ERRORS=$((ERRORS + 1))
    fi
}

check_dir() {
    local dir="$1"
    local desc="${2:-$dir}"
    if [ -d "${PROJECT_ROOT}/${dir}" ]; then
        echo "  ✓ ${desc}"
    else
        echo "  ✗ ${desc} 缺失: ${dir}"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "[1/7] 根目录关键文件"
check_file "README.md"
check_file "LICENSE"
check_file "NOTICE"
check_file "CONTRIBUTING.md"
check_file "SECURITY.md"
check_file "CHANGELOG.md"
check_file ".gitignore"
check_file ".gitattributes"
check_file ".editorconfig"
echo ""

echo "[2/7] 模块目录"
check_dir "memory-service"
check_file "memory-service/README.md"
check_dir "cpp-bridge"
check_file "cpp-bridge/README.md"
check_dir "memory-client"
check_file "memory-client/README.md"
check_dir "os-agent-integration"
check_file "os-agent-integration/README.md"
check_dir "os-agent-integration/patches"
check_file "os-agent-integration/patches/README.md"
echo ""

echo "[3/7] 基础设施目录"
check_dir "migrations"
check_file "migrations/README.md"
check_dir "config"
check_file "config/environment.example"
check_dir "packaging"
check_file "packaging/README.md"
check_dir "packaging/systemd"
check_file "packaging/systemd/README.md"
check_dir "packaging/kaiming"
check_file "packaging/kaiming/README.md"
check_dir "scripts"
check_file "scripts/README.md"
check_file "scripts/check_kylin_environment.sh"
check_file "scripts/verify_repository_baseline.sh"
check_dir "tests"
check_file "tests/README.md"
check_dir "datasets"
check_file "datasets/README.md"
check_dir "evaluation"
check_file "evaluation/README.md"
check_dir "evidence"
check_file "evidence/README.md"
check_file "evidence/index.yaml"
check_dir "deliverables"
check_file "deliverables/README.md"
echo ""

echo "[4/7] 文档目录"
check_dir "docs"
check_file "docs/README.md"
check_dir "docs/baseline"
check_file "docs/baseline/README.md"
check_dir "docs/architecture"
check_file "docs/architecture/README.md"
check_dir "docs/api"
check_file "docs/api/README.md"
check_dir "docs/deployment"
check_file "docs/deployment/README.md"
check_dir "docs/testing"
check_file "docs/testing/README.md"
check_dir "docs/security"
check_file "docs/security/README.md"
check_dir "docs/user-guide"
check_file "docs/user-guide/README.md"
check_dir "docs/project-management"
check_file "docs/project-management/README.md"
check_dir "docs/adr"
check_file "docs/adr/README.md"
check_dir "docs/technical-debt"
check_file "docs/technical-debt/TECHNICAL_DEBT_REGISTER.md"
echo ""

echo "[5/7] GitHub 协作文件"
check_dir ".github"
check_file ".github/CODEOWNERS"
check_file ".github/pull_request_template.md"
check_dir ".github/workflows"
check_file ".github/workflows/baseline-check.yml"
check_dir ".github/ISSUE_TEMPLATE"
check_file ".github/ISSUE_TEMPLATE/task.yml"
check_file ".github/ISSUE_TEMPLATE/bug.yml"
check_file ".github/ISSUE_TEMPLATE/blocker.yml"
check_file ".github/ISSUE_TEMPLATE/technical-debt.yml"
echo ""

echo "[6/7] 脚本语法检查"
for script in "${PROJECT_ROOT}/scripts/"*.sh; do
    if [ -f "$script" ]; then
        if bash -n "$script" 2>&1; then
            echo "  ✓ $(basename "$script") 语法正确"
        else
            echo "  ✗ $(basename "$script") 语法错误"
            ERRORS=$((ERRORS + 1))
        fi
    fi
done
echo ""

echo "[7/7] 高风险文件扫描"
DANGEROUS_EXTS="pem key crt env iso vdi vmdk ova ovf so dll dylib onnx engine db sqlite sqlite3"
for ext in $DANGEROUS_EXTS; do
    FOUND=$(find "${PROJECT_ROOT}" -name "*.${ext}" -not -path '*/.git/*' 2>/dev/null || true)
    if [ -n "$FOUND" ]; then
        echo "  ✗ 发现高风险文件:"
        echo "$FOUND" | while read -r f; do echo "    $f"; done
        ERRORS=$((ERRORS + 1))
    fi
done
echo "  高风险文件扩展名扫描完成"

echo ""
echo "=============================================="
if [ $ERRORS -eq 0 ]; then
    echo " 仓库基线结构验证通过 (0 错误)"
    exit 0
else
    echo " 仓库基线结构验证失败 (${ERRORS} 错误)"
    exit 1
fi
