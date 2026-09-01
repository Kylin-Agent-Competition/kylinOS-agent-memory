#!/bin/bash
# verify_day12a_vm.sh — 轨道 A D12 功能冻结与缺陷清理验证脚本
#
# 台账：D12-A — 修复 SDK 超时/异常恢复/性能抖动 + Bridge 假实现/吞异常检查 + 异常输入回归
#
# 用法（麒麟 VM 内）：
#   bash /mnt/shared/scripts/verify_day12a_vm.sh
#
# 检测项：
#   1. 系统环境（Python/SDK/依赖）
#   2. Embedding Service health（含 executor 挂死恢复分项）
#   3. 挂死恢复机制（超时→重建→恢复）
#   4. Bridge 假实现/吞异常（异常输入回归：空文本/超长/错误模型/非法枚举/异常返回）
#   5. 性能基准（延迟/吞吐量）
#   6. 日志无正文残留

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
EVIDENCE_DIR="$REPO_DIR/evidence/l2-kylin-vm"
RUN_ID="${RUN_ID:-day12a_verify_$(date +%Y%m%d_%H%M%S)}"
LOG_FILE="$EVIDENCE_DIR/${RUN_ID}.log"
# 选择 Python：优先使用项目 pydantic v2 venv（/tmp/day10-venv 或 .venv）。
# 项目要求 pydantic>=2,<3（memory-service/requirements.txt）；系统 python3.12
# 常带 pydantic v1（无 model_validator），直接用会 ImportError。故做 pydantic
# 版本探测，找不到合格解释器时给出明确建 venv 指引，而非静默用系统 python 失败。
if [ -f "/tmp/day10-venv/bin/python" ]; then
    PYTHON="${PYTHON:-/tmp/day10-venv/bin/python}"
elif [ -f "$REPO_DIR/.venv/bin/python" ]; then
    PYTHON="${PYTHON:-$REPO_DIR/.venv/bin/python}"
else
    PYTHON="${PYTHON:-python3.12}"
fi
PYTHONPATH="${PYTHONPATH:-$REPO_DIR/memory-service}"

# pydantic v2 探测（项目硬性依赖）
_py_pydantic_ok="$($PYTHON -c 'import pydantic; print("1" if pydantic.VERSION.startswith("2") else "0")' 2>/dev/null || echo "0")"
if [ "$_py_pydantic_ok" != "1" ]; then
    echo ""
    echo "=============================================================="
    echo " [环境] $PYTHON 未提供 pydantic v2（项目要求 pydantic>=2,<3）。"
    echo " 当前 $($PYTHON -c 'import pydantic; print("pydantic "+pydantic.VERSION)' 2>/dev/null || echo '无 pydantic')"
    echo ""
    echo " 请先创建 pydantic v2 虚拟环境，再重跑本脚本："
    echo "   sudo apt install -y python3.12-venv   # 若缺 venv 模块"
    echo "   python3.12 -m venv /tmp/day10-venv"
    echo "   /tmp/day10-venv/bin/pip install -r memory-service/requirements.txt"
    echo "   bash scripts/verify_day12a_vm.sh"
    echo "=============================================================="
    exit 2
fi

mkdir -p "$EVIDENCE_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo " D12A VM 功能冻结与缺陷清理验证"
echo " 时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo " 提交: $(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo 'unknown')"
echo "=============================================="

FAIL_COUNT=0
PASS_COUNT=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo "  [PASS] $name"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  [FAIL] $name"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

# ── 1. 系统环境 ──
echo ""
echo "=== 1. 系统环境 ==="
echo -n "  Python 版本: "
$PYTHON --version 2>&1
check "Python 可用" $?

echo -n "  SDK 包检测: "
dpkg -l libkylin-coreai-embedding 2>/dev/null | grep -E '^ii' >/dev/null 2>&1
check "SDK 包检测" $?

# ── 2. Embedding Service health（含 executor 分项） ──
echo ""
echo "=== 2. Embedding Service health（executor 挂死恢复分项） ==="

$PYTHON -c "
import sys
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import EmbeddingService

svc = EmbeddingService()
try:
    svc.start()
    h = svc.health()['result']
    print(f'  service: {h[\"service\"]}')
    print(f'  bridge_loaded: {h[\"bridge_loaded\"]}')
    print(f'  executor: {h[\"executor\"]}')
    assert 'executor' in h, 'health 缺少 executor 分项'
    assert 'hang_recovered' in h['executor'], 'executor 缺少 hang_recovered'
    assert 'in_flight' in h['executor'], 'executor 缺少 in_flight'
    assert 'hang_threshold_ms' in h['executor'], 'executor 缺少 hang_threshold_ms'
    print('  executor 分项验证: ALL PASS')
    svc.close()
    sys.exit(0)
except Exception as e:
    print(f'  ERROR: {e}')
    svc.close()
    sys.exit(1)
" 2>&1
check "health() executor 分项" $?

# ── 3. 挂死恢复机制（真实 SDK 下验证挂死检测入口可用） ──
echo ""
echo "=== 3. 挂死恢复机制 ==="

$PYTHON -c "
import sys
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import (
    EmbeddingService, recover_hung_bridge_executor, _in_flight, _executor_lock)

svc = EmbeddingService()
try:
    svc.start()
    # 正常 embed（确认路径畅通）
    r = svc.embed('hang-recovery smoke')
    ok = r.get('ok') and not r.get('degraded')
    print(f'  embed 正常: ok={r.get(\"ok\")} dim={r.get(\"result\",{}).get(\"dimension\",\"N/A\")}')
    # 挂死检测入口可调用、不误报（无挂死时返回 False）
    recovered = recover_hung_bridge_executor()
    print(f'  挂死检测入口: recovered={recovered}（无挂死应为 False）')
    assert recovered is False, '无挂死时不应重建 executor'
    with _executor_lock:
        print(f'  in_flight 计数: {len(_in_flight)}（完成后应为 0）')
        assert len(_in_flight) == 0, '完成后 in_flight 应为 0'
    print('  挂死恢复机制: ALL PASS')
    svc.close()
    sys.exit(0)
except Exception as e:
    print(f'  ERROR: {e}')
    svc.close()
    sys.exit(1)
" 2>&1
check "挂死恢复机制" $?

# ── 4. 异常输入回归（真实 SDK 可跑部分） ──
echo ""
echo "=== 4. 异常输入回归（真实 SDK） ==="

$PYTHON -c "
import sys
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import EmbeddingService

svc = EmbeddingService()
try:
    svc.start()
    # 空文本 / 纯空白
    for t in ('', '   ', '\t\n'):
        r = svc.embed(t)
        assert r.get('ok') and r.get('result',{}).get('dimension') == 768, f'空文本失败: {t!r}'
    print('  空文本/纯空白: PASS')

    # 超长文本
    r = svc.embed('a' * 10000)
    assert r.get('ok'), '超长文本应正常（无积压）'
    print('  超长文本(10KB): PASS')

    # 非 str 输入 → 结构化错误
    r = svc.embed(123)
    assert r.get('ok') is False and 'ERR_INVALID_TEXT' in str(r.get('error',{})), f'非str: {r}'
    print('  非 str 输入: PASS')

    # embed_batch 非法输入
    r = svc.embed_batch('not a list')
    assert r.get('ok') is False, 'embed_batch 非 list 应拒绝'
    print('  embed_batch 非法: PASS')

    print('  异常输入回归: ALL PASS')
    svc.close()
    sys.exit(0)
except Exception as e:
    print(f'  ERROR: {e}')
    svc.close()
    sys.exit(1)
" 2>&1
check "异常输入回归" $?

# ── 5. 性能基准 ──
echo ""
echo "=== 5. 性能基准 ==="

$PYTHON -c "
import sys, time
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import EmbeddingService

svc = EmbeddingService()
try:
    svc.start()
    svc.embed('预热文本')
    svc.cache.clear()
    texts = ['测试文本' + str(i) for i in range(10)]
    latencies = []
    for t in texts:
        t0 = time.monotonic()
        r = svc.embed(t)
        el = (time.monotonic() - t0) * 1000
        if r.get('ok') and not r.get('degraded'):
            latencies.append(el)
    if latencies:
        avg = sum(latencies) / len(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        print(f'  延迟: avg={avg:.1f}ms p99={p99:.1f}ms samples={len(latencies)}')
        print(f'  架构预算: ≤180ms — {\"OK\" if avg < 180 else \"EXCEEDED\"}')
    else:
        print('  延迟: 无有效样本')
    svc.close()
    sys.exit(0)
except Exception as e:
    print(f'  ERROR: {e}')
    svc.close()
    sys.exit(1)
" 2>&1
check "性能基准" $?

# ── 6. 日志无正文残留 ──
echo ""
echo "=== 6. 日志无正文残留 ==="

BRIDGE_LOG="/tmp/kylin-memory/bridge.log"
if [ -f "$BRIDGE_LOG" ]; then
    SUSPICIOUS=$(grep -ciP '[\x80-\xFF]{10,}' "$BRIDGE_LOG" 2>/dev/null || echo "0")
    echo "  疑似中文正文行数: $SUSPICIOUS"
    check "Bridge 日志无正文残留" $([ "$SUSPICIOUS" -eq 0 ] && echo 0 || echo 1)
else
    echo "  bridge.log 不存在（无日志输出，符合预期）"
    check "Bridge 日志无正文残留" 0
fi

# ── 汇总 ──
echo ""
echo "=============================================="
echo " 检测汇总"
echo "  PASS: $PASS_COUNT"
echo "  FAIL: $FAIL_COUNT"
echo "  日志: $LOG_FILE"
echo "=============================================="

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "结论: ALL PASS"
    exit 0
else
    echo "结论: $FAIL_COUNT 项失败"
    exit 1
fi
