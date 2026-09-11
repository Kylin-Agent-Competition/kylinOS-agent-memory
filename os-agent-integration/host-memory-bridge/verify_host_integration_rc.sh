#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
INSTALL_ROOT="$DATA_HOME/kylin-memory-host-integration"
HOOK="$INSTALL_ROOT/lib/libkylin-memory-prechat.so"
LAUNCHER="$INSTALL_ROOT/bin/kylin-memory-aiassistant-launcher"
CONTEXT="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/active-context.txt"
LOG="$HOME/.local/state/kylin-memory/host-integration/prechat.log"
APP_DESKTOP="$DATA_HOME/applications/kylin-aiassistant.desktop"
AUTOSTART_DESKTOP="$CONFIG_HOME/autostart/kylin-aiassistant-autostart.desktop"
MEMORY_DROPIN="$CONFIG_HOME/systemd/user/kylin-memory.service.d/99-host-integration-rc.conf"
MEMORY_SERVER_LINK="$HOME/.local/bin/kylin-memory-server"
IPC_CLIENT="$INSTALL_ROOT/bin/ipc_call.py"

fail=0
pass() { printf '[PASS] %s\n' "$*"; }
bad() { printf '[FAIL] %s\n' "$*"; fail=1; }

[ -x "$LAUNCHER" ] && pass "sandbox launcher installed" || bad "sandbox launcher missing"
[ -r "$HOOK" ] && pass "pre-chat hook installed" || bad "pre-chat hook missing"
[ -f "$APP_DESKTOP" ] && grep -Fq -- "--command=\"$LAUNCHER\"" "$APP_DESKTOP" \
    && pass "application desktop override" || bad "application desktop override"
[ -f "$AUTOSTART_DESKTOP" ] && grep -Fq -- "--command=\"$LAUNCHER\"" "$AUTOSTART_DESKTOP" \
    && grep -Fq -- '-- --silence' "$AUTOSTART_DESKTOP" \
    && pass "autostart desktop override" || bad "autostart desktop override"

BASE_MEMORY_SERVER="$(readlink -f "$MEMORY_SERVER_LINK" 2>/dev/null || true)"
if [ -n "$BASE_MEMORY_SERVER" ] && [ -f "$MEMORY_DROPIN" ] \
    && grep -Fq -- "ExecStart=\"$BASE_MEMORY_SERVER\" " "$MEMORY_DROPIN"; then
    pass "memory service uses resolved D14A launcher"
else
    bad "memory service drop-in does not use resolved D14A launcher"
fi

if systemctl --user is-active --quiet kylin-memory.service; then pass "memory service active"; else bad "memory service inactive"; fi
PREFERENCE_LIST_OUTPUT="$(/usr/bin/python3 "$IPC_CLIENT" preference.list '{"user_id":"local-user"}' 2>/dev/null || true)"
if PREFERENCE_LIST_OUTPUT="$PREFERENCE_LIST_OUTPUT" /usr/bin/python3 - <<'PYSMOKE'
import json, os
try:
    obj = json.loads(os.environ.get("PREFERENCE_LIST_OUTPUT", ""))
except json.JSONDecodeError:
    raise SystemExit(1)
raise SystemExit(0 if obj.get("status") == "ok" else 1)
PYSMOKE
then
    pass "preference.list handler reachable"
else
    bad "preference.list handler unreachable"
fi
if systemctl --user is-active --quiet kylin-memory-host-bridge.service; then pass "host bridge active"; else bad "host bridge inactive"; fi
if systemctl --user is-active --quiet kylin-memory-context-sync.service; then pass "context sync active"; else bad "context sync inactive"; fi

if [ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock" ]; then
    pass "memory UDS exists"
else
    bad "memory UDS missing"
fi

if [ -e "$CONTEXT" ]; then
    perm="$(stat -c '%a' "$CONTEXT" 2>/dev/null || true)"
    [ "$perm" = "600" ] && pass "active context mode=600" || bad "active context mode=$perm (expected 600)"
else
    bad "active context file missing"
fi

if command -v nm >/dev/null 2>&1; then
    HOOK_NM_OUTPUT="$(nm -D --defined-only "$HOOK" 2>/dev/null || true)"
else
    HOOK_NM_OUTPUT=""
fi
if [[ "$HOOK_NM_OUTPUT" == *'_ZN4kyai9assistant11OsAssistant9chatAsyncERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE'* ]]; then
    pass "chatAsync interposer symbol"
else
    bad "chatAsync interposer symbol"
fi

if [ "$MODE" = "--runtime" ]; then
    APP_PID="$(pgrep -n -f '^/usr/bin/kylin-aiassistant( |$)' || true)"
    if [ -z "$APP_PID" ]; then
        bad "AI Assistant is not running"
    else
        ENV_PRELOAD="$(tr '\0' '\n' < "/proc/$APP_PID/environ" 2>/dev/null | sed -n 's/^LD_PRELOAD=//p')"
        ENV_CONTEXT="$(tr '\0' '\n' < "/proc/$APP_PID/environ" 2>/dev/null | sed -n 's/^MEMORY_ACTIVE_CONTEXT=//p')"
        if [ "$ENV_PRELOAD" = "$HOOK" ]; then
            pass "running AI Assistant has RC LD_PRELOAD"
        else
            bad "running AI Assistant is not hooked (log out/in may still be required)"
        fi
        if [ "$ENV_CONTEXT" = "$CONTEXT" ]; then
            pass "running AI Assistant uses runtime context"
        else
            bad "running AI Assistant context path mismatch"
        fi
        if grep -q "final-loaded pid=$APP_PID" "$LOG" 2>/dev/null; then
            pass "hook constructor observed for running assistant"
        else
            bad "hook constructor log missing for pid=$APP_PID"
        fi
    fi
fi

exit "$fail"
