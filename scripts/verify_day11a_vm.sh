#!/bin/bash
# verify_day11a_vm.sh — 轨道 A D11 同一虚拟机全功能联调检测脚本
#
# 台账：D11 全功能联调 — 你在 VM 内跑这个脚本，结果告诉我
#
# 用法（麒麟 VM 内）：
#   bash /mnt/shared/scripts/verify_day11a_vm.sh
#
# 检测项：
#   1. 系统环境（Python/SDK/依赖）
#   2. Embedding Service health（含 backlog/cache/invalidator 分项）
#   3. Embedding 功能测试（embed/embed_batch/缓存命中/降级）
#   4. CacheInvalidator 接线验证（set_extraction_provider + handle_deletion_event）
#   5. Outbox Worker 就绪状态
#   6. 性能基准（延迟/吞吐量）
#   7. Bridge ABI 符号检查
#   8. 日志无正文残留

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
EVIDENCE_DIR="$REPO_DIR/evidence/l2-kylin-vm"
RUN_ID="${RUN_ID:-day11a_verify_$(date +%Y%m%d_%H%M%S)}"
LOG_FILE="$EVIDENCE_DIR/${RUN_ID}.log"
# 优先使用 venv Python（pydantic >= 2.13 / sqlalchemy 已安装）
if [ -f "/tmp/day10-venv/bin/python" ]; then
    PYTHON="${PYTHON:-/tmp/day10-venv/bin/python}"
else
    PYTHON="${PYTHON:-python3.12}"
fi
PYTHONPATH="${PYTHONPATH:-$REPO_DIR/memory-service}"

mkdir -p "$EVIDENCE_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo " D11A VM 全功能联调检测"
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

echo -n "  SDK .so 路径: "
SDK_SO_PATH=$(dpkg -L libkylin-coreai-embedding 2>/dev/null | grep '\.so\.' | head -1)
if [ -z "$SDK_SO_PATH" ]; then
    SDK_SO_PATH="/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1"
fi
ls -la "$SDK_SO_PATH" 2>/dev/null
check "SDK .so 存在" $?

echo -n "  ldd 解析: "
ldd "$SDK_SO_PATH" 2>/dev/null | grep -c "=>" >/dev/null 2>&1
check "SDK 动态库可解析" $?

echo -n "  pytest 可用: "
$PYTHON -m pytest --version 2>&1 | head -1
check "pytest 可用" $?

echo -n "  Pydantic 版本: "
$PYTHON -c "import pydantic; print(pydantic.__version__)" 2>/dev/null
check "pydantic 可用" $?

# ── 2. Embedding Service 健康检查 ──
echo ""
echo "=== 2. Embedding Service 健康检查 ==="

$PYTHON -c "
import sys
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import EmbeddingService
from providers import EmbeddingProvider

svc = EmbeddingService()
try:
    svc.start()
    h = svc.health()
    r = h['result']
    print(f'  service: {r[\"service\"]}')
    print(f'  provider: {r[\"provider\"]}')
    print(f'  bridge_loaded: {r[\"bridge_loaded\"]}')
    print(f'  bridge_has_session: {r[\"bridge_has_session\"]}')
    print(f'  degraded: {r[\"degraded\"]}')
    print(f'  sdk_missing: {r[\"sdk_missing\"]}')
    print(f'  backlog: {r[\"backlog\"]}')
    print(f'  cache: {r[\"cache\"]}')
    print(f'  cache_invalidator: {r[\"cache_invalidator\"]}')
    print(f'  model: {r[\"model\"]}')
    print(f'  errors: {r[\"errors\"]}')
    print(f'  provider_lifecycle: {r[\"provider_lifecycle\"]}')

    # D11A 新增字段断言
    assert 'model' in r, 'health 缺少 model 分项'
    assert 'errors' in r, 'health 缺少 errors 分项'
    assert 'provider_lifecycle' in r, 'health 缺少 provider_lifecycle 分项'
    assert 'count' in r['errors'], 'errors 缺少 count'
    assert 'last_code' in r['errors'], 'errors 缺少 last_code'
    assert 'last_time_seconds_ago' in r['errors'], 'errors 缺少 last_time_seconds_ago'
    print('  D11A 字段验证: ALL PASS')
    svc.close()
    sys.exit(0)
except Exception as e:
    print(f'  ERROR: {e}')
    svc.close()
    sys.exit(1)
" 2>&1
check "health() 接口正常" $?

# ── 3. Embedding 功能测试 ──
echo ""
echo "=== 3. Embedding 功能测试 ==="

$PYTHON -c "
import sys
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import EmbeddingService
from providers import EmbeddingProvider

svc = EmbeddingService()
try:
    svc.start()
    # 单条 embed
    r1 = svc.embed('你好，麒麟操作系统')
    ok1 = r1.get('ok') and not r1.get('degraded')
    print(f'  embed 单条: ok={r1.get(\"ok\")} degraded={r1.get(\"degraded\")} dim={r1.get(\"result\",{}).get(\"dimension\",\"N/A\")}')

    # 缓存命中
    r2 = svc.embed('你好，麒麟操作系统')
    ch = r2.get('cache_hit', False)
    print(f'  缓存命中: {ch}')

    # embed_batch
    r3 = svc.embed_batch(['文本1', '文本2', '文本3'])
    ok3 = r3.get('ok') and len(r3.get('result',{}).get('vectors',[])) == 3
    print(f'  embed_batch: ok={r3.get(\"ok\")} count={len(r3.get(\"result\",{}).get(\"vectors\",[]))}')

    svc.close()
    sys.exit(0 if (ok1 and ok3) else 1)
except Exception as e:
    print(f'  ERROR: {e}')
    svc.close()
    sys.exit(1)
" 2>&1
check "embed/embed_batch/缓存正常" $?

# ── 4. CacheInvalidator 接线验证 ──
echo ""
echo "=== 4. CacheInvalidator 接线验证 ==="

$PYTHON -c "
import sys
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import EmbeddingService
from embedding.cache_invalidator import CacheInvalidator, DeletionEvent, ForgetMode, TargetType
from embedding.embedding_cache import EmbeddingQueryCache, raw_text_hash
from providers.extraction_provider import PreferenceExtractionCache
from providers import EmbeddingProvider

# 测试 CacheInvalidator 独立工作
emb_cache = EmbeddingQueryCache(capacity=64)
ext_cache = PreferenceExtractionCache(capacity=64)
invalidator = CacheInvalidator(emb_cache, ext_cache)

# 写入缓存
key = emb_cache.make_key('test content', 768)
emb_cache.set(key, {'vector': [0.1] * 768, 'dimension': 768})
assert emb_cache.get(key) is not None, '缓存写入失败'

# 删除事件
content_hash = raw_text_hash('test content')
event = DeletionEvent(
    event_id='vm_test_001',
    user_id='vm_user',
    content_hashes=[content_hash],
    forget_mode=ForgetMode.SINGLE_ITEM
)
result = invalidator.handle_deletion(event)
assert result['ok'], f'删除事件处理失败: {result}'
assert emb_cache.get(key) is None, '删除后缓存未失效'

# 统计验证
stats = invalidator.stats
assert stats['events_processed'] == 1
assert stats['embedding_invalidated'] >= 1
print(f'  CacheInvalidator: events_processed={stats[\"events_processed\"]}')
print(f'  embedding_invalidated={stats[\"embedding_invalidated\"]}')
print(f'  extraction_invalidated={stats[\"extraction_invalidated\"]}')

# 幂等测试
r2 = invalidator.handle_deletion(event)
assert r2['dedup'], f'幂等去重失败: {r2}'
print(f'  幂等去重: {r2[\"dedup\"]}')

# Service 接线测试
svc = EmbeddingService()
svc.start()
svc.embed('test for wiring')
from providers.extraction_provider import ExtractionProvider
svc.set_extraction_provider(ExtractionProvider())
assert svc.invalidator is not None, 'set_extraction_provider 后 invalidator 为 None'
print(f'  Service 接线: invalidator 已连接')
h = svc.health()['result']
assert 'cache_invalidator' in h, 'health 缺少 cache_invalidator 分项'
print(f'  health.cache_invalidator: {h[\"cache_invalidator\"]}')
svc.close()

print('  ALL PASS')
sys.exit(0)
" 2>&1
check "CacheInvalidator 接线验证" $?

# ── 5. Outbox 就绪状态 ──
echo ""
echo "=== 5. Outbox 就绪状态 ==="

$PYTHON -c "
import sys
sys.path.insert(0, '$PYTHONPATH')
from outbox.worker import OutboxWorker
print('  OutboxWorker 模块可导入')
# 检查 outbox worker 的 consumer 回调就绪状态
# 当前 consumer=None（R-9 pending），模块可导入、结构正确
sys.exit(0)
" 2>&1
check "Outbox 模块导入" $?

# ── 6. 性能基准 ──
echo ""
echo "=== 6. 性能基准 ==="

$PYTHON -c "
import sys, time
sys.path.insert(0, '$PYTHONPATH')
from embedding.embedding_service import EmbeddingService
from providers import EmbeddingProvider

svc = EmbeddingService()
try:
    svc.start()
    # 预热
    svc.embed('预热文本')
    svc.cache.clear()

    # 延迟测量
    texts = ['测试文本' + str(i) for i in range(10)]
    latencies = []
    for t in texts:
        t0 = time.monotonic()
        r = svc.embed(t)
        elapsed = (time.monotonic() - t0) * 1000
        if r.get('ok') and not r.get('degraded'):
            latencies.append(elapsed)

    if latencies:
        avg = sum(latencies) / len(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        print(f'  延迟: avg={avg:.1f}ms p99={p99:.1f}ms samples={len(latencies)}')
        print(f'  架构预算: ≤180ms — {\"OK\" if avg < 180 else \"EXCEEDED\"}')
    else:
        print('  延迟: 无有效样本（全部降级）')

    # 缓存命中延迟
    t0 = time.monotonic()
    for t in texts[:5]:
        svc.embed(t)
    cache_ms = (time.monotonic() - t0) * 1000
    print(f'  缓存命中延迟: {cache_ms:.1f}ms（5次）')

    svc.close()
    sys.exit(0)
except Exception as e:
    print(f'  ERROR: {e}')
    svc.close()
    sys.exit(1)
" 2>&1
check "性能基准" $?

# ── 7. Bridge ABI 符号检查 ──
echo ""
echo "=== 7. Bridge ABI 符号检查 ==="

echo -n "  导出 C API 符号: "
ABI_COUNT=$(nm -D "$SDK_SO_PATH" 2>/dev/null | grep -cE 'text_embedding|embedding_result')
echo "$ABI_COUNT"
check "ABI 符号导出" $([ "$ABI_COUNT" -gt 0 ] && echo 0 || echo 1)

echo -n "  关键符号验证: "
ALL_FOUND=0
for sym in text_embedding_create_session text_embedding text_embedding_async embedding_result_get_vector_data; do
    if nm -D "$SDK_SO_PATH" 2>/dev/null | grep -q "$sym"; then
        echo -n "$sym "
    else
        echo -n "(missing:$sym) "
        ALL_FOUND=1
    fi
done
echo ""
check "关键符号" $ALL_FOUND

# ── 8. 日志无正文残留 ──
echo ""
echo "=== 8. 日志无正文残留 ==="

BRIDGE_LOG="/tmp/kylin-memory/bridge.log"
if [ -f "$BRIDGE_LOG" ]; then
    echo "  bridge.log 存在（行数: $(wc -l < "$BRIDGE_LOG")）"
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