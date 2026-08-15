#!/usr/bin/env bash
#
# verify_day8_vm.sh — 轨道 A Day8 麒麟 VM 验证脚本
#
# 用途：从共享文件夹 /mnt/shared 检出 Day8 分支（feat/day8-knowledge-extraction），
#       在麒麟 VM 内执行 L2 全量 pytest（KYLIN_L2=1），并生成证据日志
#       evidence/l2-kylin-vm/day8_verify_latest.log（含元数据头 + Step1 原始输出）。
#
# 用法（麒麟 VM，宿主手动执行）:
#   cd /mnt/shared && bash scripts/verify_day8_vm.sh
#
# 退出码：0 = 全部通过；非 0 = 有失败（脚本会在失败处继续并汇总）。
#
# 依赖：
#   - 共享文件夹已挂载（/mnt/shared = WSL 仓库根目录，vboxsf）
#   - VM 内 python3 可用；venv 缺失时自动重建到 /tmp/day8-venv
#   - LD_LIBRARY_PATH 需含 /usr/lib/kylin-ai/depends（SDK 依赖）

# 自清理：vboxsf/autocrlf 可能给脚本注入 CRLF，先移除行尾 \r 再执行
if head -1 "$0" | grep -q $'\r'; then
  tmpf="$(mktemp)"
  sed 's/\r$//' "$0" > "$tmpf"
  exec bash "$tmpf" "$@"
fi

set -u

REPO=/mnt/shared
VENV=/tmp/day8-venv
FAILURES=0
# 证据门禁：先做 Step 1 干净工作区检查（此时日志尚未写入），检查通过后再启动 tee
EVIDENCE_LOG="$REPO/evidence/l2-kylin-vm/day8_verify_latest.log"
EVIDENCE_TMP="$REPO/evidence/l2-kylin-vm/.day8_verify_tmp.log"

log()  { printf '\n===== %s =====\n' "$*"; }
pass() { printf '  [PASS] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*"; FAILURES=$((FAILURES+1)); }

cd "$REPO" || { echo "无法进入 $REPO（共享文件夹未挂载？）"; exit 2; }

# ── Step 1：干净工作区 + 分支/被测 commit（证据门禁：tested_commit 绑定） ──
log "Step 1: 仓库状态（证据头）"
STEP1_OUTPUT="$(git rev-parse --abbrev-ref HEAD 2>&1)
$(git rev-parse HEAD 2>&1)
$(git status --short 2>&1 | head -20)"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COMMIT="$(git rev-parse HEAD)"

# 检查 Day8 分支（允许本地分支名与远端不一致时提示但继续）
if [ "$BRANCH" != "feat/day8-knowledge-extraction" ]; then
  echo "  [WARN] 当前分支 $BRANCH ≠ feat/day8-knowledge-extraction（请确认被测代码）"
fi

mkdir -p "$REPO/evidence/l2-kylin-vm"
# 写入证据头（Step 1 原始输出先落盘，满足"证据硬门禁 = 最终 L2 日志必须含 Step1 原始输出"）
{
  echo "================================================================"
  echo "Day8 A 轨 L2 证据 — 知识结构化抽取（六类 + 失败/取消 Tool 策略 + 失败降级测试）"
  echo "branch: $BRANCH"
  echo "tested_commit: $COMMIT"
  echo "command: PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:\$LD_LIBRARY_PATH KYLIN_L2=1 $VENV/bin/python -m pytest memory-service/tests/ -v"
  echo "environment: 麒麟桌面 V11 x86_64（VirtualBox VM，Runtime 1.3.0，Embedding SDK 1.2.0.0-0k0.4）"
  echo "================================================================"
  echo "[Step1] $(date -Is)"
  echo "$STEP1_OUTPUT"
  echo "================================================================"
} > "$EVIDENCE_TMP"

# ── Step 2：venv 准备（/tmp 易失，缺失则重建） ──
log "Step 2: Python venv ($VENV)"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" && "$VENV/bin/pip" install -q -r "$REPO/memory-service/requirements.txt" \
    && pass "venv 重建完成" || fail "venv 重建失败"
else
  pass "venv 已存在"
fi

# ── Step 3：L2 全量 pytest（KYLIN_L2=1，含真实 SDK 用例） ──
log "Step 3: L2 全量 pytest（麒麟 VM）"
PYTHONPATH="$REPO/cpp-bridge/build:$REPO/memory-service" \
LD_LIBRARY_PATH="/usr/lib/kylin-ai/depends:${LD_LIBRARY_PATH:-}" \
KYLIN_L2=1 "$VENV/bin/python" -m pytest "$REPO/memory-service/tests/" -v \
  >> "$EVIDENCE_TMP" 2>&1
TEST_EXIT=$?
if [ "$TEST_EXIT" -eq 0 ]; then
  pass "L2 pytest 退出码 0"
else
  fail "L2 pytest 退出码 $TEST_EXIT"
fi

# ── Step 4：汇总 + 落盘最终证据 ──
log "Step 4: 汇总"
tail -5 "$EVIDENCE_TMP"
mv "$EVIDENCE_TMP" "$EVIDENCE_LOG"

if [ "$FAILURES" -eq 0 ]; then
  echo ""
  echo "✅ Day8 L2 全部通过 → 证据已落盘：$EVIDENCE_LOG"
  exit 0
else
  echo ""
  echo "❌ Day8 L2 存在 $FAILURES 项失败 → 证据已落盘：$EVIDENCE_LOG"
  exit 1
fi
