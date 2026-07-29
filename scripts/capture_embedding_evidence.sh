#!/usr/bin/env bash
# ============================================================
# 采集 Embedding SDK 真实证据到 evidence/ 目录
# 在麒麟 VM 上运行：bash scripts/capture_embedding_evidence.sh
# ============================================================
set -euo pipefail

EVIDENCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/evidence"
mkdir -p "${EVIDENCE_DIR}"

echo "=============================================="
echo " Embedding SDK 证据采集"
echo " 目标: ${EVIDENCE_DIR}"
echo " 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

SDK_SO="/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1"

# ── 1. nm -D 完整输出 ──
echo ""
echo "[1/6] nm -D 符号表"
if [ -f "${SDK_SO}" ]; then
    nm -D "${SDK_SO}" > "${EVIDENCE_DIR}/nm_D_output.txt" 2>&1
    echo "  已保存: ${EVIDENCE_DIR}/nm_D_output.txt ($(wc -l < "${EVIDENCE_DIR}/nm_D_output.txt") 行)"
    # 同时提取 C API 符号 (T = 已定义导出符号)
    grep " T " "${EVIDENCE_DIR}/nm_D_output.txt" > "${EVIDENCE_DIR}/nm_D_exported_T.txt" || true
    echo "  导出符号数: $(wc -l < "${EVIDENCE_DIR}/nm_D_exported_T.txt")"
else
    echo "  ❌ ${SDK_SO} 不存在，跳过"
fi

# ── 2. SDK 版本信息 ──
echo ""
echo "[2/6] SDK 包信息"
dpkg -l libkylin-coreai-embedding 2>/dev/null | tail -1 > "${EVIDENCE_DIR}/sdk_dpkg.txt" || true
dpkg -l kylin-ai-runtime      2>/dev/null | tail -1 > "${EVIDENCE_DIR}/runtime_dpkg.txt" || true
dpkg -l kytensor-server       2>/dev/null | tail -1 > "${EVIDENCE_DIR}/kytensor_server_dpkg.txt" || true
echo "  SDK:     $(cat "${EVIDENCE_DIR}/sdk_dpkg.txt")"
echo "  Runtime: $(cat "${EVIDENCE_DIR}/runtime_dpkg.txt")"
echo "  Kytensor:$(cat "${EVIDENCE_DIR}/kytensor_server_dpkg.txt")"

# ── 3. .so 文件属性 ──
echo ""
echo "[3/6] .so 文件属性"
ls -la "${SDK_SO}" > "${EVIDENCE_DIR}/so_fileinfo.txt" 2>&1
file "${SDK_SO}" >> "${EVIDENCE_DIR}/so_fileinfo.txt" 2>&1
ldd "${SDK_SO}" >> "${EVIDENCE_DIR}/so_fileinfo.txt" 2>&1 || true
cat "${EVIDENCE_DIR}/so_fileinfo.txt"

# ── 4. 模型仓库目录 ──
echo ""
echo "[4/6] 模型仓库目录"
ls /usr/share/kylin-ai/model-repository/ > "${EVIDENCE_DIR}/model_repository_ls.txt" 2>&1 || true
echo "  已保存: ${EVIDENCE_DIR}/model_repository_ls.txt"

# ── 5. 系统信息 ──
echo ""
echo "[5/6] 系统信息"
uname -a > "${EVIDENCE_DIR}/uname.txt" 2>&1
cat /etc/os-release > "${EVIDENCE_DIR}/os_release.txt" 2>&1 || true
echo "  已保存"

# ── 6. 关键符号清单（供代码生成使用） ──
echo ""
echo "[6/6] 生成 C API 符号索引"
if [ -f "${EVIDENCE_DIR}/nm_D_exported_T.txt" ]; then
    # 过滤出以 text_embedding 或 embedding_ 开头的导出符号
    grep -E "^[0-9a-f]+ T (text_embedding_|embedding_)" "${EVIDENCE_DIR}/nm_D_output.txt" \
        > "${EVIDENCE_DIR}/api_symbols.txt" 2>&1 || true
    echo "  C API 符号数: $(wc -l < "${EVIDENCE_DIR}/api_symbols.txt")"
    cat "${EVIDENCE_DIR}/api_symbols.txt"
fi

echo ""
echo "=============================================="
echo " 采集完成。证据保存在: ${EVIDENCE_DIR}"
echo " 请在主机侧执行:"
echo "   git add evidence/ && git commit -m \"chore: capture embedding SDK evidence from VM\""
echo "=============================================="
