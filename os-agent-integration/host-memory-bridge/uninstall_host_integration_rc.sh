#!/usr/bin/env bash
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
INSTALL_ROOT="$DATA_HOME/kylin-memory-host-integration"
STATE_DIR="$STATE_HOME/kylin-memory/host-integration"
BACKUP_DIR="$STATE_DIR/backups"
USER_UNIT_DIR="$CONFIG_HOME/systemd/user"
MEMORY_DROPIN_DIR="$USER_UNIT_DIR/kylin-memory.service.d"
APP_DESKTOP="$DATA_HOME/applications/kylin-aiassistant.desktop"
AUTOSTART_DESKTOP="$CONFIG_HOME/autostart/kylin-aiassistant-autostart.desktop"

restore_or_remove() {
    local dst="$1" name="$2"
    if [ -f "$BACKUP_DIR/$name" ]; then
        mkdir -p "$(dirname "$dst")"
        cp -a "$BACKUP_DIR/$name" "$dst"
    elif [ -f "$BACKUP_DIR/$name.absent" ]; then
        rm -f "$dst"
    else
        # No backup metadata means this RC does not have authority to replace an
        # unknown user file. Only remove known project-specific unit names below.
        printf '[host-integration] WARNING: no backup state for %s; left unchanged\n' "$dst" >&2
    fi
}

systemctl --user disable --now \
    kylin-memory-host-bridge.service \
    kylin-memory-context-sync.service >/dev/null 2>&1 || true

rm -f \
    "$USER_UNIT_DIR/kylin-memory-host-bridge.service" \
    "$USER_UNIT_DIR/kylin-memory-context-sync.service"

restore_or_remove "$MEMORY_DROPIN_DIR/99-host-integration-rc.conf" "99-host-integration-rc.conf"
restore_or_remove "$APP_DESKTOP" "kylin-aiassistant.desktop"
restore_or_remove "$AUTOSTART_DESKTOP" "kylin-aiassistant-autostart.desktop"

rm -rf "$INSTALL_ROOT"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/active-context.txt"

systemctl --user daemon-reload
if systemctl --user list-unit-files kylin-memory.service >/dev/null 2>&1; then
    systemctl --user restart kylin-memory.service >/dev/null 2>&1 || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
fi

# Backups describe one installation transaction. Remove them only after all
# restores above succeeded, so a later reinstall captures the then-current user
# state rather than restoring stale first-install files.
rm -rf "$STATE_DIR"

printf '[host-integration] uninstalled. Log out/in to return the assistant to the original autostart path.\n'
