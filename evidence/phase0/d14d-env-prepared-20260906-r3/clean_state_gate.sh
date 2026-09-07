#!/bin/sh
# D14D Phase0 clean-state Gate (fail-closed)
# Deterministic: scans ROOT for residue; any hit => CLEAN_STATE_FAIL + exit != 0.
# usage: clean_state_gate.sh <ROOT>
set -u
ROOT="${1:-}"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "usage: clean_state_gate.sh <ROOT>"
  echo "GATE_INVALID_ROOT"
  exit 2
fi
pc=0; mp=0; sl=0; au=0; ms=0; vc=0; bc=0; dc=0
[ -d "$ROOT/kylinOS-agent-memory" ] && pc=1
mp=$(ls -d "$ROOT"/.local/share/kylin-memory* 2>/dev/null | wc -l)
[ -x "$ROOT/.local/bin/kylin-memory-server" ] && sl=1
systemctl --user is-active kylin-memory >/dev/null 2>&1 && au=1
[ -S "/run/user/$(id -u)/kylin-memory/memory.sock" ] && ms=1
vc=$(find "$ROOT" -maxdepth 3 -type d -name .venv -print 2>/dev/null | wc -l)
bc=$(find "$ROOT" -maxdepth 3 -type d -name 'build*' -print 2>/dev/null | wc -l)
dc=$(find "$ROOT" -maxdepth 3 -type d -name kylin-memory-d14a -print 2>/dev/null | wc -l)
printf 'project_checkout_count=%s\n' "$pc"
printf 'memory_install_prefix_count=%s\n' "$mp"
printf 'stale_launcher_count=%s\n' "$sl"
printf 'active_memory_unit_count=%s\n' "$au"
printf 'memory_socket_count=%s\n' "$ms"
printf 'venv_count=%s\n' "$vc"
printf 'build_dir_count=%s\n' "$bc"
printf 'd14a_workdir_count=%s\n' "$dc"
if [ "$pc" -eq 0 ] && [ "$mp" -eq 0 ] && [ "$sl" -eq 0 ] && [ "$au" -eq 0 ] && [ "$ms" -eq 0 ] && [ "$vc" -eq 0 ] && [ "$bc" -eq 0 ] && [ "$dc" -eq 0 ]; then
  echo "CLEAN_STATE_PASS"
  exit 0
fi
echo "CLEAN_STATE_FAIL"
exit 1