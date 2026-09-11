#!/usr/bin/env bash
# Post-D15D Host Memory Integration RC installer.
# Installs only the user-scoped host-integration layer. The D14A Memory Service
# must already be installed. This RC does not modify the official assistant ELF.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
OS_AGENT_DIR="$(cd "$SELF_DIR/.." && pwd)"
MODE="${1:-install}"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
INSTALL_ROOT="$DATA_HOME/kylin-memory-host-integration"
BIN_DIR="$INSTALL_ROOT/bin"
LIB_DIR="$INSTALL_ROOT/lib"
STATE_DIR="$STATE_HOME/kylin-memory/host-integration"
BACKUP_DIR="$STATE_DIR/backups"
USER_UNIT_DIR="$CONFIG_HOME/systemd/user"
MEMORY_DROPIN_DIR="$USER_UNIT_DIR/kylin-memory.service.d"
APP_DIR="$DATA_HOME/applications"
AUTOSTART_DIR="$CONFIG_HOME/autostart"
APP_DESKTOP="$APP_DIR/kylin-aiassistant.desktop"
AUTOSTART_DESKTOP="$AUTOSTART_DIR/kylin-aiassistant-autostart.desktop"
SYSTEM_AUTOSTART="/etc/xdg/autostart/kylin-aiassistant-autostart.desktop"
HOOK_DST="$LIB_DIR/libkylin-memory-prechat.so"
LAUNCHER_DST="$BIN_DIR/kylin-memory-aiassistant-launcher"
MARKER="$STATE_DIR/installed-v1"

log() { printf '[host-integration] %s\n' "$*"; }
die() { printf '[host-integration] ERROR: %s\n' "$*" >&2; exit 1; }

[ "$MODE" = "install" ] || die "usage: $0 [install]"
[ "$(uname -s)" = "Linux" ] || die "Linux is required"
[ -n "${XDG_RUNTIME_DIR:-}" ] || die "XDG_RUNTIME_DIR is not set; run inside the desktop user session"
command -v systemctl >/dev/null || die "systemctl not found"
command -v python3 >/dev/null || die "python3 not found"
command -v kaiming >/dev/null || die "kaiming not found"
KAIMING_BIN="/opt/kaiming-tools/bin/kaiming"
[ -x "$KAIMING_BIN" ] || KAIMING_BIN="$(command -v kaiming)"
EXPECTED_ASSISTANT_SHA256="86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6"
MEMORY_SERVER_LINK="$HOME/.local/bin/kylin-memory-server"
[ -x "$MEMORY_SERVER_LINK" ] \
    || die "base Memory Service is not installed at ~/.local/bin/kylin-memory-server"
BASE_MEMORY_SERVER="$(readlink -f "$MEMORY_SERVER_LINK" 2>/dev/null || true)"
[ -n "$BASE_MEMORY_SERVER" ] && [ -x "$BASE_MEMORY_SERVER" ] \
    || die "cannot resolve executable base Memory Service launcher from $MEMORY_SERVER_LINK"

mkdir -p "$BIN_DIR" "$LIB_DIR" "$STATE_DIR" "$BACKUP_DIR" \
    "$USER_UNIT_DIR" "$MEMORY_DROPIN_DIR" "$APP_DIR" "$AUTOSTART_DIR"
chmod 700 "$INSTALL_ROOT" "$BIN_DIR" "$LIB_DIR" "$STATE_DIR" "$BACKUP_DIR"

# Preserve pre-existing user overrides only on the first RC install. Reinstalling
# this RC must never overwrite the original backup with our generated files.
backup_once() {
    local src="$1" name="$2"
    if [ -e "$BACKUP_DIR/$name" ] || [ -e "$BACKUP_DIR/$name.absent" ]; then
        return
    fi
    if [ -e "$src" ]; then
        cp -a "$src" "$BACKUP_DIR/$name"
    else
        : > "$BACKUP_DIR/$name.absent"
    fi
}
backup_once "$APP_DESKTOP" "kylin-aiassistant.desktop"
backup_once "$AUTOSTART_DESKTOP" "kylin-aiassistant-autostart.desktop"
backup_once "$MEMORY_DROPIN_DIR/99-host-integration-rc.conf" "99-host-integration-rc.conf"

# Copy the small Python bridge and launcher. Runtime content is kept outside the
# source checkout so the user can delete/move the checkout after installation.
install -m 0700 "$SELF_DIR/host_memory_bridge.py" "$BIN_DIR/host_memory_bridge.py"
install -m 0700 "$SELF_DIR/memory_context_sync.py" "$BIN_DIR/memory_context_sync.py"
install -m 0700 "$SELF_DIR/ipc_call.py" "$BIN_DIR/ipc_call.py"
install -m 0700 "$SELF_DIR/kylin-memory-aiassistant-launcher" "$LAUNCHER_DST"

# A release package may supply a prebuilt, verified SO through this variable.
# Source-checkout RC installs fall back to a local C++17 build.
if [ -n "${KYLIN_MEMORY_PRECHAT_SO:-}" ]; then
    [ -f "$KYLIN_MEMORY_PRECHAT_SO" ] || die "KYLIN_MEMORY_PRECHAT_SO does not exist"
    install -m 0500 "$KYLIN_MEMORY_PRECHAT_SO" "$HOOK_DST"
else
    command -v g++ >/dev/null || die "g++ not found and KYLIN_MEMORY_PRECHAT_SO was not supplied"
    SRC="$OS_AGENT_DIR/prechat-hook/memory_prechat_final.cpp"
    [ -f "$SRC" ] || die "missing hook source: $SRC"
    TMP_SO="$(mktemp --suffix=.so)"
    trap 'rm -f "$TMP_SO"' EXIT
    g++ -std=c++17 -shared -fPIC -O2 -Wall -Wextra -Wpedantic \
        "$SRC" -ldl -o "$TMP_SO"
    install -m 0500 "$TMP_SO" "$HOOK_DST"
    rm -f "$TMP_SO"
    trap - EXIT
fi

# Fail before touching desktop/systemd activation if the exact validated host
# binary is not present. The interposer targets this 3.0.67 ABI and must not be
# enabled blindly on an upgraded Assistant.
ASSISTANT_HASH_OUTPUT="$(
    "$KAIMING_BIN" run --command=/usr/bin/sha256sum \
        cn.kylin.kylin-aiassistant -- /usr/bin/kylin-aiassistant 2>&1 || true
)"
[[ "$ASSISTANT_HASH_OUTPUT" == *"$EXPECTED_ASSISTANT_SHA256"* ]] \
    || die "unsupported Kylin AI Assistant binary; expected SHA-256 $EXPECTED_ASSISTANT_SHA256"
log "assistant binary identity: PASS"

# Prove the *installed* hook path can be loaded inside Kaiming and that the
# runtime context directory is visible there. This catches KYSEC/path/mount
# failures before the user's normal Assistant launch is overridden.
PROBE_DIR="${XDG_RUNTIME_DIR}/kylin-memory"
PROBE_CONTEXT="$PROBE_DIR/host-integration-install-probe.txt"
PROBE_LOG="$STATE_DIR/install-prechat-probe.log"
PROBE_WRAPPER="$BIN_DIR/.host-integration-install-probe"
PROBE_TOKEN="kylin-memory-host-integration-probe-$$"
mkdir -p "$PROBE_DIR"
printf '%s\n' "$PROBE_TOKEN" > "$PROBE_CONTEXT"
chmod 0600 "$PROBE_CONTEXT"
rm -f "$PROBE_LOG"
cat > "$PROBE_WRAPPER" <<PROBE
#!/bin/bash
set -eu
HOOK="$HOOK_DST"
CONTEXT="$PROBE_CONTEXT"
LOG="$PROBE_LOG"
TOKEN="$PROBE_TOKEN"
[ -r "\$HOOK" ] || exit 21
[ "\$(cat "\$CONTEXT" 2>/dev/null)" = "\$TOKEN" ] || exit 22
export LD_PRELOAD="\$HOOK"
export MEMORY_PRECHAT_LOG="\$LOG"
export MEMORY_ACTIVE_CONTEXT="\$CONTEXT"
exec /usr/bin/true
PROBE
chmod 0700 "$PROBE_WRAPPER"
if ! "$KAIMING_BIN" run --command="$PROBE_WRAPPER" \
    cn.kylin.kylin-aiassistant -- >/dev/null 2>&1; then
    rm -f "$PROBE_WRAPPER" "$PROBE_CONTEXT"
    die "Kaiming installed-hook probe failed (wrapper/context visibility or loader policy)"
fi
rm -f "$PROBE_WRAPPER" "$PROBE_CONTEXT"
grep -q '\[memory-prechat\] final-loaded pid=' "$PROBE_LOG" \
    || die "installed pre-chat hook did not load inside Kaiming (check KYSEC trust/policy)"
command -v nm >/dev/null || die "nm not found; cannot verify pre-chat hook ABI"
HOOK_NM_OUTPUT="$(nm -D --defined-only "$HOOK_DST" 2>/dev/null || true)"
[[ "$HOOK_NM_OUTPUT" == *'_ZN4kyai9assistant11OsAssistant9chatAsyncERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE'* ]] \
    || die "installed pre-chat hook does not export the validated chatAsync ABI"
log "Kaiming installed-hook/context visibility: PASS"

# RC activation: preference/forget handlers are still candidate/validation
# routes at main@e62d525e. Keep this as a reversible user drop-in rather than
# silently changing the frozen base unit.
{
    printf '%s\n' '[Service]' 'ExecStart='
    printf 'ExecStart="%s" --socket %%t/kylin-memory/memory.sock --no-migrate --register-preference-handlers --register-forget-handlers\n' \
        "$BASE_MEMORY_SERVER"
} > "$MEMORY_DROPIN_DIR/99-host-integration-rc.conf"
chmod 0600 "$MEMORY_DROPIN_DIR/99-host-integration-rc.conf"

cat > "$USER_UNIT_DIR/kylin-memory-host-bridge.service" <<UNIT
[Unit]
Description=Kylin Memory Host Chat Bridge (post-D15D RC)
After=kylin-memory.service
Requires=kylin-memory.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 "$BIN_DIR/host_memory_bridge.py"
Restart=on-failure
RestartSec=2
UMask=0077
NoNewPrivileges=yes

[Install]
WantedBy=default.target
UNIT

cat > "$USER_UNIT_DIR/kylin-memory-context-sync.service" <<UNIT
[Unit]
Description=Kylin Memory Active Context Sync (post-D15D RC)
After=kylin-memory.service
Requires=kylin-memory.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 "$BIN_DIR/memory_context_sync.py"
Restart=on-failure
RestartSec=2
UMask=0077
NoNewPrivileges=yes

[Install]
WantedBy=default.target
UNIT
chmod 0600 \
    "$USER_UNIT_DIR/kylin-memory-host-bridge.service" \
    "$USER_UNIT_DIR/kylin-memory-context-sync.service"

# `kaiming run` strips arbitrary host environment variables. Therefore the
# desktop entries tell Kaiming to execute our wrapper *inside* the sandbox; the
# wrapper then sets LD_PRELOAD and execs the untouched official binary.
DESKTOP_LAUNCHER=${LAUNCHER_DST//\\/\\\\}
DESKTOP_LAUNCHER=${DESKTOP_LAUNCHER//\"/\\\"}

cat > "$APP_DESKTOP" <<DESKTOP
[Desktop Entry]
Type=Application
Name=AI Assistant
Name[zh_CN]=AI 助手
Comment=Kylin AI Assistant with local Memory RC integration
Icon=kylin-ai-assistant
Exec=$KAIMING_BIN run --command="$DESKTOP_LAUNCHER" cn.kylin.kylin-aiassistant --
Terminal=false
StartupNotify=true
DESKTOP
chmod 0644 "$APP_DESKTOP"

if [ -f "$SYSTEM_AUTOSTART" ]; then
    cp "$SYSTEM_AUTOSTART" "$AUTOSTART_DESKTOP"
    python3 - "$AUTOSTART_DESKTOP" "$KAIMING_BIN" "$LAUNCHER_DST" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
kaiming = sys.argv[2]
launcher = sys.argv[3].replace('\\', '\\\\').replace('"', '\\"')
new_exec = f'Exec={kaiming} run --command="{launcher}" cn.kylin.kylin-aiassistant -- --silence'
lines = path.read_text(encoding='utf-8').splitlines()
out = []
replaced = False
for line in lines:
    if line.startswith('Exec='):
        out.append(new_exec)
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(new_exec)
path.write_text('\n'.join(out) + '\n', encoding='utf-8')
PY
else
    cat > "$AUTOSTART_DESKTOP" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Ai assistant
Name[zh_CN]=AI 助手
Icon=kylin-ai-assistant
Exec=$KAIMING_BIN run --command="$DESKTOP_LAUNCHER" cn.kylin.kylin-aiassistant -- --silence
Terminal=false
X-GNOME-Autostart-enabled=true
DESKTOP
fi
chmod 0644 "$AUTOSTART_DESKTOP"

: > "$MARKER"
chmod 0600 "$MARKER"

systemctl --user daemon-reload
systemctl --user enable kylin-memory.service >/dev/null 2>&1 || true
systemctl --user restart kylin-memory.service

MEMORY_SOCKET="${XDG_RUNTIME_DIR}/kylin-memory/memory.sock"
for _ in $(seq 1 20); do
    if systemctl --user is-active --quiet kylin-memory.service && [ -S "$MEMORY_SOCKET" ]; then
        break
    fi
    sleep 0.5
done
systemctl --user is-active --quiet kylin-memory.service \
    || die "Memory Service did not become active after RC drop-in"
[ -S "$MEMORY_SOCKET" ] || die "Memory Service UDS did not become ready: $MEMORY_SOCKET"

# Smoke the candidate preference route that both bridge and context-sync require.
# A merely-active process/socket is insufficient if another later drop-in has
# overridden our handler-registration flags.
PREFERENCE_LIST_OUTPUT="$(
    /usr/bin/python3 "$BIN_DIR/ipc_call.py" preference.list '{"user_id":"local-user"}' 2>/dev/null || true
)"
if ! PREFERENCE_LIST_OUTPUT="$PREFERENCE_LIST_OUTPUT" /usr/bin/python3 - <<'PYSMOKE'
import json, os
try:
    obj = json.loads(os.environ.get("PREFERENCE_LIST_OUTPUT", ""))
except json.JSONDecodeError:
    raise SystemExit(1)
raise SystemExit(0 if obj.get("status") == "ok" else 1)
PYSMOKE
then
    die "preference.list IPC smoke failed; RC handler profile is not effective"
fi
log "preference.list IPC smoke: PASS"

# `enable --now` does not restart an already-active unit during an RC reinstall.
# Explicit restart guarantees the just-installed bridge/sync code is the code
# actually running before this installer returns success.
systemctl --user enable kylin-memory-host-bridge.service kylin-memory-context-sync.service >/dev/null
systemctl --user restart kylin-memory-host-bridge.service kylin-memory-context-sync.service
sleep 1
systemctl --user is-active --quiet kylin-memory-host-bridge.service \
    || die "host bridge failed to stay active"
systemctl --user is-active --quiet kylin-memory-context-sync.service \
    || die "context sync failed to stay active"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

log "installed at $INSTALL_ROOT"
log "Memory Service + bridge + context-sync are enabled."
log "The current already-running AI Assistant is not killed or modified."
log "Log out and log back in once so the XDG autostart override launches the hooked assistant."
log "Then run: $SELF_DIR/verify_host_integration_rc.sh --runtime"
