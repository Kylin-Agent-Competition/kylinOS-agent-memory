#!/bin/bash
# collect_d11a_evidence.sh — D11A 麒麟 VM 证据采集与回填脚本
#
# 用法（麒麟 VM 内）：
#   bash /mnt/shared/scripts/collect_d11a_evidence.sh
#
# 功能：
#   1. 运行 D11A 全量检测（verify_day11a_vm.sh）
#   2. 运行 D11A 全量测试（test_d11a_all.py）
#   3. 计算证据日志 SHA256
#   4. 输出回填 index.yaml 所需字段

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
EVIDENCE_DIR="$REPO_DIR/evidence/l2-kylin-vm"
RUN_ID="${RUN_ID:-d11a_evidence_$(date +%Y%m%d_%H%M%S)}"
LOG_FILE="$EVIDENCE_DIR/${RUN_ID}.log"
PYTHON="${PYTHON:-/tmp/day10-venv/bin/python}"
PYTHONPATH="${PYTHONPATH:-$REPO_DIR/memory-service}"

mkdir -p "$EVIDENCE_DIR"

echo "=============================================="
echo " D11A 证据采集脚本"
echo " RUN_ID: $RUN_ID"
echo " 时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo " 提交: $(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo 'unknown')"
echo "=============================================="

# ── 1. 运行 VM 全量检测 ──
echo ""
echo "=== 1. 运行 VM 全量检测 ==="
VM_LOG="$EVIDENCE_DIR/${RUN_ID}_vm_verify.log"
RUN_ID="$RUN_ID" bash "$SCRIPT_DIR/verify_day11a_vm.sh" 2>&1 | tee "$VM_LOG"
VM_EXIT=$?

# ── 2. 运行全量测试 ──
echo ""
echo "=== 2. 运行全量测试 ==="
TEST_LOG="$EVIDENCE_DIR/${RUN_ID}_test_all.log"
PYTHONPATH="$PYTHONPATH" $PYTHON "$SCRIPT_DIR/test_d11a_all.py" 2>&1 | tee "$TEST_LOG"
TEST_EXIT=$?

# ── 3. 计算 SHA256 ──
echo ""
echo "=== 3. 证据文件 SHA256 ==="
VM_SHA256=$(sha256sum "$VM_LOG" | cut -d' ' -f1)
TEST_SHA256=$(sha256sum "$TEST_LOG" | cut -d' ' -f1)
echo "  VM 检测日志: $VM_SHA256"
echo "  全量测试日志: $TEST_SHA256"

# ── 4. 输出回填模板 ──
echo ""
echo "=== 4. index.yaml 回填模板 ==="
echo ""
echo "将以下内容复制到 evidence/index.yaml 的 D11A-L2-VERIFY 条目："
echo ""
cat << YAML
  - id: "D11A-L2-VERIFY"
    task_id: "D11A"
    description: "D11A 麒麟 VM 全功能联调验证——health 增强（model/errors/lifecycle）+ Outbox 桥接 + VM 检测 + 全量测试"
    status: "HOST_VERIFIED"
    evidence_level: "E4"
    source: "evidence/l2-kylin-vm/${RUN_ID}_vm_verify.log"
    tested_commit: "$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo 'PENDING')"
    date: "$(date +%Y-%m-%d)"
    reviewer: "pending"
    runtime_result: "$([ "$VM_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')"
    review_status: "PENDING"
    merge_qualified: false
    limitations: "kylin_embedding pybind11 模块需编译后方可执行真实 SDK 调用；未编译时所有 embed 路径返回 degraded 降级（行为正确）；全链路 Vector 消费（R-9）pending，consumer 当前仅处理 memory.deletion 事件类型"
    checksum_sha256: "$VM_SHA256"
    details: |
      VM 检测结果: $([ "$VM_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')
      全量测试结果: $([ "$TEST_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')
      日志: evidence/l2-kylin-vm/${RUN_ID}_vm_verify.log
      全量测试: evidence/l2-kylin-vm/${RUN_ID}_test_all.log
YAML

# ── 汇总 ──
echo ""
echo "=============================================="
echo " 证据采集汇总"
echo "  VM 检测: $([ "$VM_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')"
echo "  全量测试: $([ "$TEST_EXIT" -eq 0 ] && echo 'PASS' || echo 'FAIL')"
echo "  RUN_ID: $RUN_ID"
echo "  日志: $LOG_FILE"
echo "=============================================="

if [ "$VM_EXIT" -eq 0 ] && [ "$TEST_EXIT" -eq 0 ]; then
    echo "结论: ALL PASS，可回填 index.yaml"
    exit 0
else
    echo "结论: 有失败项，请检查日志后重试"
    exit 1
fi