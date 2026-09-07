#!/usr/bin/env bash
# =============================================================================
# D14A verify/smoke — 发布包安装后健康 + 真实 SDK 验证（contract §9，fail-closed）
# 用法: bash verify.sh --embed-pid <pid> [--embed-socket <path>]
# 校验项:
#   1. systemd --user is-active
#   2. gateway socket 存在且 holder PID == systemd MainPID（holder PID 无法解析
#      或与 MainPID 不等均 FAIL；socket/proc UID 一致仅作附加防线，不作替代）
#   3. cmdline 不含源码 checkout 与个人 venv
#   4. 真实 memory.embed → dim=768（非 fake；embedding.sock 必须就绪，否则 FAIL）
#   5. 校验 embedding server 进程实际加载 SDK .so 的 SHA-256 == contract 冻结值
#      （SDK 由 embedding server 加载，非 gateway；--embed-pid 必填，缺失即 FAIL）
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$SELF_DIR/.." && pwd)"
INSTALL_PREFIX="${INSTALL_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory-d14a}"
EMBED_SOCK=""
EMBED_PID=""

while [ $# -gt 0 ]; do
  case "$1" in
    --embed-socket) EMBED_SOCK="$2"; shift 2 ;;
    --embed-pid) EMBED_PID="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
[ -n "$EMBED_SOCK" ] || EMBED_SOCK="/tmp/kylin-d14a-embed.sock"

log() { echo "[d14a-verify] $*"; }
die() { echo "[d14a-verify] FAIL: $*" >&2; exit 1; }
pass() { echo "[d14a-verify] PASS: $*"; }

# fail-closed：--embed-pid 必填（独立 embedding server 实际加载 SDK 的 maps/hash
# Gate 无法在不指定该 PID 的情况下验证，缺失即 FAIL）
[ -n "$EMBED_PID" ] || die "--embed-pid 必填：独立 embedding server 实际加载 SDK 的 maps/hash Gate 无法验证"

# 0. 被测路径必须来自 install_prefix（拒绝从开发包目录验证）
[ "$PKG_DIR" = "$INSTALL_PREFIX" ] \
  || die "verify 应从安装前缀运行（PKG_DIR=$PKG_DIR != INSTALL_PREFIX=$INSTALL_PREFIX）"

# 1. 服务 active
systemctl --user is-active --quiet "$UNIT_NAME" || die "服务未 active"
pass "service active"

# 2. socket + holder PID == MainPID（contract §8.5）
PID="$(systemctl --user show -p MainPID --value "$UNIT_NAME")"
[ "$PID" != "0" ] || die "MainPID 无效"
SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock"
[ -S "$SOCK" ] || die "socket 不存在: $SOCK"
HOLDER_PID="$(ss -xlpn 2>/dev/null | grep "$SOCK" | grep -oP 'pid=\K[0-9]+' | head -1 || true)"
# fail-closed：holder PID 必须可解析且与 unit MainPID 精确相等（contract §8.5）；
# 解析失败或不等均直接 FAIL，不得以 socket/proc UID 一致作为替代成功路径
[ -n "$HOLDER_PID" ] || die "无法解析 socket holder PID: $SOCK"
[ "$HOLDER_PID" = "$PID" ] || die "socket holder PID($HOLDER_PID) != systemd MainPID($PID)"
# 附加防线（非替代）：socket 属主 uid 与 MainPID 属主一致
SOCK_UID="$(stat -c %u "$SOCK")"
PROC_UID="$(stat -c %u /proc/$PID 2>/dev/null || true)"
[ "$SOCK_UID" = "$PROC_UID" ] || die "socket uid($SOCK_UID) != proc uid($PROC_UID)"
pass "socket holder = MainPID=$PID"

# 3. cmdline 不含源码 checkout 与个人 venv（contract §5/§8.5）
CMDLINE="$(tr '\0' ' ' < /proc/$PID/cmdline)"
echo "$CMDLINE" | grep -q "$INSTALL_PREFIX/runtime/python/bin/python" \
  || die "cmdline 未指向发布包 venv: $CMDLINE"
echo "$CMDLINE" | grep -qiE "(\.venv|d4d-venv|/home/[^/]+/kylinOS-agent-memory)" \
  && die "cmdline 含开发 venv/源码路径" || true
pass "cmdline 指向发布包 venv（无开发目录依赖）"

# 4. 真实 memory.embed → dim=768（fail-closed：embedding.sock 必须就绪）
[ -S "$EMBED_SOCK" ] || die "embedding.sock 未就绪: $EMBED_SOCK（无法完成真实 SDK smoke）"
PY="$INSTALL_PREFIX/runtime/python/bin/python"
EMBED_RESULT="$("$PY" - <<PYEOF 2>&1 || true
import socket, struct, json, time
def send(sock, obj):
    data = json.dumps(obj).encode()
    sock.sendall(struct.pack(">I", len(data)) + data)
    n = struct.unpack(">I", sock.recv(4))[0]
    return json.loads(sock.recv(n).decode())
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect("$EMBED_SOCK")
t0 = time.time()
r = send(s, {"protocol_version":"1.0","method":"memory.embed","request_id":"verify","trace_id":"v","deadline_ms":10000,"payload":{"text":"D14A verify real SDK smoke"}})
dt = (time.time()-t0)*1000
d = r.get("data", {})
print(json.dumps({"status": r.get("status"), "dim": d.get("dimension"), "len": len(d.get("vector", [])), "latency_ms": round(dt,1), "degraded": r.get("degraded", d.get("degraded", False))}))
s.close()
PYEOF
)"
echo "$EMBED_RESULT" | grep -q '"status": "ok"' \
  || die "memory.embed 非 ok: $EMBED_RESULT"
echo "$EMBED_RESULT" | grep -q '"dim": 768' \
  || die "memory.embed dim != 768: $EMBED_RESULT"
echo "$EMBED_RESULT" | grep -q '"degraded": false' \
  || die "memory.embed 处于降级（fake fallback）: $EMBED_RESULT"
log "memory.embed: $EMBED_RESULT"
pass "真实 SDK memory.embed dim=768"

# 5. 校验 embedding server 进程实际加载 SDK .so 的 SHA（contract §6；
#    --embed-pid 已在顶部必填校验，此 Gate 无条件执行）
SDK_SO="/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0"
SDK_EXPECT_SHA="028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48"
[ -d /proc/$EMBED_PID ] || die "embedding server PID 无效: $EMBED_PID"
grep -Fq "$SDK_SO" /proc/$EMBED_PID/maps || die "embedding server 未加载 SDK .so: $SDK_SO"
ACTUAL_SHA="$(sha256sum "$SDK_SO" | awk '{print $1}')"
[ "$ACTUAL_SHA" = "$SDK_EXPECT_SHA" ] \
  || die "SDK 实际 SHA 不匹配: expected=$SDK_EXPECT_SHA actual=$ACTUAL_SHA"
pass "embedding server SDK 实际加载 SHA 校验通过"

echo "[d14a-verify] ALL PASS"