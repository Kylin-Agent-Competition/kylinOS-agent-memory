#!/usr/bin/env bash
#
# verify_day4_vm.sh — 轨道 A Day4 麒麟 VM 一次性验证脚本
#
# 用途：从共享文件夹 /mnt/shared 检出 Day4 分支代码，执行 REWORK 复审要求的
#       全部验证（P0-1 干净状态证据 / P0-2 畸形防御 / P0-3 异常边界 /
#       P0-4 pytest 收集 / P1-1 Provider 错误映射 / 真实 SDK 冒烟）。
#
# 用法（麒麟 VM）:
#   cd /mnt/shared && bash scripts/verify_day4_vm.sh
#
# 退出码：0 = 全部通过；非 0 = 有失败（脚本会在失败处继续并汇总）。
#
# 依赖：
#   - 共享文件夹已挂载（/mnt/shared = WSL 仓库根目录）
#   - python3 可用；venv 缺失时自动重建到 /tmp/day4-venv

# 自清理：vboxsf/autocrlf 可能给脚本注入 CRLF，先移除行尾 \r 再执行
# （bash 会把 "2>&1\r" 解析成独立命令 "2"，导致 "行 N: 2: 未找到命令"）
if head -1 "$0" | grep -q $'\r'; then
  tmpf="$(mktemp)"
  sed 's/\r$//' "$0" > "$tmpf"
  exec bash "$tmpf" "$@"
fi

set -u

REPO=/mnt/shared
VENV=/tmp/day4-venv
FAILURES=0
# P2/P0-EVIDENCE-1: 证据日志由脚本一次性生成（避免手工拼接歧义）
# 注意：先做 Step 1 干净工作区检查（此时日志尚未写入），检查通过后再启动 tee。
EVIDENCE_LOG="$REPO/evidence/l2-kylin-vm/day4_verify_latest.log"
EVIDENCE_TMP="$REPO/evidence/l2-kylin-vm/.day4_verify_tmp.log"

log()  { printf '\n===== %s =====\n' "$*"; }
pass() { printf '  [PASS] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*"; FAILURES=$((FAILURES+1)); }

cd "$REPO" || { echo "无法进入 $REPO（共享文件夹未挂载？）"; exit 2; }

# ── 第 1 步：干净工作区证据（P0-1/P1-1/P1-2） ──
# 注意：先于日志写入执行，确保看到严格干净的工作区
log "Step 1: git 状态证据 (P0-1)"
# vboxsf 共享文件夹 stat 缓存会导致 git 误报文件修改：先强制刷新 index stat
# P0-EVIDENCE: Step 1 原始输出先写入 /tmp/day4_step1.log（tee 到 stdout + 文件）
STEP1_LOG="/tmp/day4_step1.log"
exec > >(tee "$STEP1_LOG") 2>&1
git update-index --refresh >/dev/null 2>&1 || true
git rev-parse HEAD
# P1-2: 必须无任何输出（含未跟踪文件）；仅排除本轮预期证据日志（不掩盖其他文件）
STATUS="$(git status --porcelain --untracked-files=all | grep -vE 'day4_verify_latest\.log$|\.day4_verify_tmp\.log$')"
echo "--- git status --porcelain --untracked-files=all (exit=0) ---"
if [ -n "$STATUS" ]; then
  echo "stdout:"
  echo "$STATUS"
  fail "工作区存在修改、暂存或未跟踪文件（含 ?? 未跟踪文件，非严格干净）"
else
  echo "stdout: <EMPTY>"
  pass "git status --porcelain --untracked-files=all 为空（严格干净，排除证据日志）"
fi
echo "--- git diff --exit-code ---"
if git diff --exit-code >/dev/null 2>&1; then
  echo "exit=0, stdout: <EMPTY>"
  pass "WORKTREE_CLEAN=1"
else
  echo "exit=1, stdout: <EMPTY>"
  fail "WORKTREE_CLEAN=0（工作区有未提交修改）"
fi
echo "--- git diff --cached --exit-code ---"
if git diff --cached --exit-code >/dev/null 2>&1; then
  echo "exit=0, stdout: <EMPTY>"
  pass "INDEX_CLEAN=1"
else
  echo "exit=1, stdout: <EMPTY>"
  fail "INDEX_CLEAN=0（暂存区有未提交修改）"
fi
# Step 1 输出结束：恢复 stdout（后续 tee 到 runtime 日志）；无 TTY 环境（CI/非交互）保持当前 stdout
if [ -e /dev/tty ] && [ -w /dev/tty ]; then
  exec > /dev/tty
fi

# 干净检查通过后，启动 runtime 日志（tee 到 /tmp/day4_runtime.log）
RUNTIME_LOG="/tmp/day4_runtime.log"
{
    echo "# Day4 麒麟 VM 验证原始日志（脚本自动生成，未经手工拼接）"
    echo "# 被测 Commit: $(git rev-parse HEAD)"
    echo "# Date: $(date '+%Y-%m-%d %H:%M:%S')"
} > "$RUNTIME_LOG"
exec > >(tee -a "$RUNTIME_LOG") 2>&1

# ── 第 2 步：venv + pybind11 ──
log "Step 2: venv + pybind11"
if [ ! -f "$VENV/bin/activate" ]; then
  echo "  (重建 venv: $VENV)"
  python3 -m venv "$VENV" || { fail "venv 创建失败"; exit 2; }
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -c 'import pybind11' 2>/dev/null || pip install pybind11
# pytest 用于 Step 4 统一收集（P0-4）
python -c 'import pytest' 2>/dev/null || pip install pytest
python -m pybind11 --cmakedir >/dev/null 2>&1 && pass "pybind11 可用" || fail "pybind11 不可用"

# ── 第 3 步：CMake 构建 + CTest（P0-2/P0-3/P1-2/P1-3 编译验证） ──
log "Step 3: CMake 构建 + CTest"
cd "$REPO/cpp-bridge" || exit 2
rm -rf build   # P1-1: 先删旧 build，确保不误用旧产物
build_ok=0
if cmake -B build -Dpybind11_DIR="$(python -m pybind11 --cmakedir)" >/tmp/day4_cmake.log 2>&1; then
  pass "cmake configure OK"
  build_ok=1
else
  fail "cmake configure 失败（见 /tmp/day4_cmake.log）"
  build_ok=0
fi
if [ "$build_ok" -eq 1 ]; then
  if cmake --build build -j2 >>/tmp/day4_cmake.log 2>&1; then
    pass "cmake build OK"
    build_ok=1
  else
    fail "cmake build 失败（见 /tmp/day4_cmake.log）"
    build_ok=0
  fi
fi
if [ "$build_ok" -eq 1 ]; then
  if ctest --test-dir build --output-on-failure >/tmp/day4_ctest.log 2>&1; then
    pass "ctest 全部通过"
  else
    fail "ctest 有失败（见 /tmp/day4_ctest.log）"
  fi
  grep -E "Test #|tests passed" /tmp/day4_ctest.log | sed 's/^/    /'
else
  fail "构建失败，跳过 ctest（P1-1: 不得运行旧测试产物）"
fi

# ── 第 4 步：pytest 统一收集（P0-4/P1-1） ──
log "Step 4: pytest 统一收集 (P0-4)"
cd "$REPO"
export KYLIN_L2=1   # P1-1: 麒麟 L2 环境，缺 kylin_embedding 必须失败而非 skip
export PYTHONPATH="$REPO/cpp-bridge/build:$REPO/memory-service"
export LD_LIBRARY_PATH="/usr/lib/kylin-ai/depends:${LD_LIBRARY_PATH:-}"

# P1-1: 校验导入的 kylin_embedding 来自当前 build（而非旧 build/site-packages）
python - <<'PY'
from pathlib import Path
import kylin_embedding
actual = Path(kylin_embedding.__file__).resolve()
expected = Path("/mnt/shared/cpp-bridge/build").resolve()
print(f"  kylin_embedding.__file__={actual}")
if expected not in actual.parents:
    raise SystemExit(f"  导入模块不是当前构建产物: actual={actual}, expected_under={expected}")
PY
if [ $? -ne 0 ]; then
  fail "kylin_embedding 模块来源校验失败"
else
  pass "kylin_embedding 来自当前 build"
fi

pytest_ok=1
if python -m pytest memory-service/tests/test_embedding_provider_import.py \
    memory-service/tests/test_exception_mapping.py \
    memory-service/tests/test_provider_failure_recovery.py -v >/tmp/day4_pytest_a.log 2>&1; then
  :
else
  pytest_ok=0
fi
grep -E "PASSED|FAILED|SKIPPED|passed|failed|skipped" /tmp/day4_pytest_a.log | sed 's/^/    /'
if python -m pytest memory-service/tests/test_load_idempotent.py -v >/tmp/day4_pytest_b.log 2>&1; then
  :
else
  pytest_ok=0
fi
grep -E "PASSED|FAILED|SKIPPED|passed|failed|skipped" /tmp/day4_pytest_b.log | sed 's/^/    /'
# P2: 解释器退出析构路径（子进程 start→embed→close→退出，无 Abort/挂起/core dump）
if python -m pytest memory-service/tests/test_interpreter_exit.py -v >/tmp/day4_pytest_c.log 2>&1; then
  :
else
  pytest_ok=0
fi
grep -E "PASSED|FAILED|SKIPPED|passed|failed|skipped" /tmp/day4_pytest_c.log | sed 's/^/    /'
# P1-1: 关键测试出现 skip 必须失败
for logf in /tmp/day4_pytest_a.log /tmp/day4_pytest_b.log /tmp/day4_pytest_c.log; do
  if grep -qE "skipped|[0-9]+ skipped" "$logf"; then
    fail "关键测试被 Skip（$logf），L2 环境不允许跳过"
    pytest_ok=0
  fi
done
if [ "$pytest_ok" -eq 1 ]; then
  pass "pytest 全部通过（三组独立进程，无 Skip）"
else
  fail "pytest 有失败或 Skip（见 /tmp/day4_pytest_a.log / b.log / c.log）"
fi

# ── 第 5 步：真实 SDK 冒烟（P1-1 回归） ──
log "Step 5: 真实 SDK 冒烟"
if python memory-service/tests/run_smoke.py >/tmp/day4_smoke.log 2>&1; then
  pass "smoke 全部通过"
else
  fail "smoke 有失败（见 /tmp/day4_smoke.log）"
fi
grep -E "\[PASS\]|\[FAIL\]|结果" /tmp/day4_smoke.log | sed 's/^/    /'

# ── 第 6 步：Provider 错误映射真实路径（P1-1/P1-3） ──
log "Step 6: Provider 错误映射 (P1-1)"
python - "$REPO" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/memory-service")
from providers import EmbeddingProvider, ProviderError, ProviderErrorCode
# P1-3: ERR_MODEL_INVALID 存在
assert hasattr(ProviderErrorCode, "ERR_MODEL_INVALID"), "ERR_MODEL_INVALID 缺失"
p = EmbeddingProvider(so_path="/tmp/definitely_not_exist.so.1")
try:
    p.start()
    print("  [FAIL] 应抛 ProviderError")
    sys.exit(1)
except ProviderError as e:
    ok = e.code == ProviderErrorCode.ERR_SDK_NOT_LOADED
    print(f"  [{'PASS' if ok else 'FAIL'}] start() -> {e.code.name} (bridge={e.bridge_error})")
    sys.exit(0 if ok else 1)
PYEOF
[ $? -eq 0 ] && pass "Provider 错误映射 OK" || fail "Provider 错误映射失败"

# ── 第 7 步：生命周期路径（P0-1 验收标准，麒麟 VM） ──
log "Step 7: 生命周期路径 (P0-1)"
python - "$REPO" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/memory-service")
from providers import EmbeddingProvider, ProviderError

failures = 0
def check(name, fn):
    global failures
    try:
        fn()
        print(f"  [PASS] {name}")
    except Exception as e:
        failures += 1
        print(f"  [FAIL] {name}: {type(e).__name__}: {e}")

def path1():
    p = EmbeddingProvider()
    p.start()
    p.close()

def path2():
    with EmbeddingProvider() as p:
        pass

def path3():
    p = EmbeddingProvider()
    p.start()
    r = p.embed("test")
    assert r.dimension == 768
    p.close()
    p.start()
    r2 = p.embed("test")
    assert r2.dimension == 768
    p.close()

def path4():
    for i in range(3):
        p = EmbeddingProvider()
        p.start()
        r = p.embed(f"text-{i}")
        assert r.dimension == 768
        p.close()
        del p

check("start→close", path1)
check("with EmbeddingProvider(): pass", path2)
check("start→embed→close→start→embed→close", path3)
check("多个 Provider 顺序创建/启动/关闭", path4)

sys.exit(1 if failures else 0)
PYEOF
[ $? -eq 0 ] && pass "生命周期 4 类路径全部通过" || fail "生命周期路径有失败"

# ── 汇总 ──
log "汇总"
if [ "$FAILURES" -eq 0 ]; then
  echo "全部验证通过（FAILURES=0）"
else
  echo "存在 $FAILURES 项失败，请检查上方 [FAIL] 与对应日志"
fi

# 证据日志合并：Step1 原始输出 + runtime 输出 → 正式路径（历史备份改放 /tmp，见下）
if [ -f "$EVIDENCE_LOG" ]; then
  cp $EVIDENCE_LOG "/tmp/day4_verify_latest.prev.log" 2>/dev/null || true
fi
{
    cat "$STEP1_LOG" 2>/dev/null || true
    echo ""
    echo "===== Runtime 输出（Step 2 起） ====="
    cat "$RUNTIME_LOG" 2>/dev/null || true
} > "$EVIDENCE_LOG"
echo "证据日志: $EVIDENCE_LOG"

if [ "$FAILURES" -eq 0 ]; then
  exit 0
else
  exit 1
fi
