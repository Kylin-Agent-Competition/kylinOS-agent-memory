#!/bin/bash
# verify_day10_vm.sh — 轨道 A Day10 麒麟 VM 验证脚本
#
# 台账 R52（A 轨 D10）：精准遗忘与删除一致性
#
# 在麒麟 VM 上执行：
#   - L2 全量 pytest（含 D10 新增测试）
#   - 缓存失效接口验证（EmbeddingQueryCache / PreferenceExtractionCache）
#   - CacheInvalidator 删除事件处理验证
#   - 日志与 Bridge 无正文残留检查
#
# 用法（麒麟 VM 内）：
#   bash /mnt/shared/scripts/verify_day10_vm.sh
#
# 依赖：
#   - PYTHONPATH 指向 memory-service 目录
#   - 麒麟 SDK 已安装（libkylin-coreai-embedding 1.2.0.0）
#   - pytest 已安装

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
EVIDENCE_DIR="$REPO_DIR/evidence/l2-kylin-vm"
LOG_FILE="$EVIDENCE_DIR/day10_verify_latest.log"
PYTHON="${PYTHON:-python3.12}"
PYTHONPATH="${PYTHONPATH:-$REPO_DIR/memory-service}"

mkdir -p "$EVIDENCE_DIR"
echo "[Day10 VM Verify] 开始验证 $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee "$LOG_FILE"
echo "commit=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo 'unknown')" >> "$LOG_FILE"

# ── 1. 运行 D10 专项测试 ──
echo "" | tee -a "$LOG_FILE"
echo "=== 1. D10 专项测试（test_embedding_d10.py）===" | tee -a "$LOG_FILE"
cd "$REPO_DIR"
PYTHONPATH="$PYTHONPATH" $PYTHON -m pytest memory-service/tests/test_embedding_d10.py -v 2>&1 | tee -a "$LOG_FILE"
D10_EXIT="${PIPESTATUS[0]}"

# ── 2. D9 回归测试（缓存/合并/积压不变） ──
echo "" | tee -a "$LOG_FILE"
echo "=== 2. D9 回归测试（test_embedding_d9.py）===" | tee -a "$LOG_FILE"
PYTHONPATH="$PYTHONPATH" $PYTHON -m pytest memory-service/tests/test_embedding_d9.py -v 2>&1 | tee -a "$LOG_FILE"
D9_EXIT="${PIPESTATUS[0]}"

# ── 3. L2 全量 pytest（含所有已有测试） ──
echo "" | tee -a "$LOG_FILE"
echo "=== 3. L2 全量 pytest ===" | tee -a "$LOG_FILE"
PYTHONPATH="$PYTHONPATH" $PYTHON -m pytest memory-service/tests/ -v --tb=short 2>&1 | tee -a "$LOG_FILE"
L2_EXIT="${PIPESTATUS[0]}"

# ── 4. 检查 Bridge 日志无正文残留 ──
echo "" | tee -a "$LOG_FILE"
echo "=== 4. Bridge 日志检查（无正文残留）===" | tee -a "$LOG_FILE"
BRIDGE_LOG="/tmp/kylin-memory/bridge.log"
if [ -f "$BRIDGE_LOG" ]; then
    # 检查日志中是否有疑似正文内容（非固定模式）
    SUSPICIOUS=$(grep -ci "text_embedding" "$BRIDGE_LOG" 2>/dev/null || echo "0")
    echo "bridge.log 行数: $(wc -l < "$BRIDGE_LOG"), 含 text_embedding 行数: $SUSPICIOUS" | tee -a "$LOG_FILE"
else
    echo "bridge.log 不存在（无日志输出）" | tee -a "$LOG_FILE"
fi

# ── 5. 汇总 ──
echo "" | tee -a "$LOG_FILE"
echo "=== 结果汇总 ===" | tee -a "$LOG_FILE"
echo "D10 专项测试: $([ "$D10_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')" | tee -a "$LOG_FILE"
echo "D9 回归测试:  $([ "$D9_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')" | tee -a "$LOG_FILE"
echo "L2 全量:     $([ "$L2_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')" | tee -a "$LOG_FILE"

if [ "$D10_EXIT" -eq 0 ] && [ "$D9_EXIT" -eq 0 ] && [ "$L2_EXIT" -eq 0 ]; then
    echo "结论: ALL PASS" | tee -a "$LOG_FILE"
    exit 0
else
    echo "结论: SOME FAILED" | tee -a "$LOG_FILE"
    exit 1
fi