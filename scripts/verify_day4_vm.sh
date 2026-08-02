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

set -u

REPO=/mnt/shared
VENV=/tmp/day4-venv
FAILURES=0

log()  { printf '\n===== %s =====\n' "$*"; }
pass() { printf '  [PASS] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*"; FAILURES=$((FAILURES+1)); }

cd "$REPO" || { echo "无法进入 $REPO（共享文件夹未挂载？）"; exit 2; }

# ── 第 1 步：干净工作区证据（P0-1） ──
log "Step 1: git 状态证据 (P0-1)"
# vboxsf 共享文件夹 stat 缓存会导致 git 误报文件修改：
# 先强制刷新 index stat（只更新 stat 信息，不改内容），再检查状态
git update-index --refresh >/dev/null 2>&1 || true
git rev-parse HEAD
git status --porcelain
if git diff --exit-code >/dev/null 2>&1; then
  pass "WORKTREE_CLEAN=1"
else
  fail "WORKTREE_CLEAN=0（工作区有未提交修改）"
fi
if git diff --cached --exit-code >/dev/null 2>&1; then
  pass "INDEX_CLEAN=1"
else
  fail "INDEX_CLEAN=0（暂存区有未提交修改）"
fi

# ── 第 2 步：venv + pybind11 ──
log "Step 2: venv + pybind11"
if [ ! -f "$VENV/bin/activate" ]; then
  echo "  (重建 venv: $VENV)"
  python3 -m venv "$VENV" || { fail "venv 创建失败"; exit 2; }
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -c 'import pybind11' 2>/dev/null || pip install pybind11
python -m pybind11 --cmakedir >/dev/null 2>&1 && pass "pybind11 可用" || fail "pybind11 不可用"

# ── 第 3 步：CMake 构建 + CTest（P0-2/P0-3/P1-2/P1-3 编译验证） ──
log "Step 3: CMake 构建 + CTest"
cd "$REPO/cpp-bridge" || exit 2
rm -rf build
if cmake -B build -Dpybind11_DIR="$(python -m pybind11 --cmakedir)" >/tmp/day4_cmake.log 2>&1; then
  pass "cmake configure OK"
else
  fail "cmake configure 失败（见 /tmp/day4_cmake.log）"
fi
if cmake --build build -j2 >>/tmp/day4_cmake.log 2>&1; then
  pass "cmake build OK"
else
  fail "cmake build 失败（见 /tmp/day4_cmake.log）"
fi
if ctest --test-dir build --output-on-failure >/tmp/day4_ctest.log 2>&1; then
  pass "ctest 全部通过"
else
  fail "ctest 有失败（见 /tmp/day4_ctest.log）"
fi
grep -E "Test #|tests passed" /tmp/day4_ctest.log | sed 's/^/    /'

# ── 第 4 步：pytest 统一收集（P0-4） ──
log "Step 4: pytest 统一收集 (P0-4)"
cd "$REPO"
export PYTHONPATH="$REPO/cpp-bridge/build:$REPO/memory-service"
export LD_LIBRARY_PATH="/usr/lib/kylin-ai/depends:${LD_LIBRARY_PATH:-}"
if python -m pytest memory-service/tests/test_embedding_provider_import.py \
    memory-service/tests/test_exception_mapping.py \
    memory-service/tests/test_load_idempotent.py -v >/tmp/day4_pytest.log 2>&1; then
  pass "pytest 全部通过"
else
  fail "pytest 有失败（见 /tmp/day4_pytest.log）"
fi
grep -E "PASSED|FAILED|SKIPPED|passed|failed" /tmp/day4_pytest.log | sed 's/^/    /'

# ── 第 5 步：真实 SDK 冒烟（P1-1 回归） ──
log "Step 5: 真实 SDK 冒烟"
if python memory-service/tests/run_smoke.py >/tmp/day4_smoke.log 2>&1; then
  pass "smoke 全部通过"
else
  fail "smoke 有失败（见 /tmp/day4_smoke.log）"
fi
grep -E "\[PASS\]|\[FAIL\]|结果" /tmp/day4_smoke.log | sed 's/^/    /'

# ── 第 6 步：Provider 错误映射真实路径（P1-1） ──
log "Step 6: Provider 错误映射 (P1-1)"
python - "$REPO" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/memory-service")
from providers import EmbeddingProvider, ProviderError, ProviderErrorCode
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

# ── 汇总 ──
log "汇总"
if [ "$FAILURES" -eq 0 ]; then
  echo "全部验证通过（FAILURES=0）"
  exit 0
else
  echo "存在 $FAILURES 项失败，请检查上方 [FAIL] 与对应日志"
  exit 1
fi
