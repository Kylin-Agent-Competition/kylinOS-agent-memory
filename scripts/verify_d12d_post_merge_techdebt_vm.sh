#!/usr/bin/env bash
# D12D post-merge VM verification for TD-KYSEC-001, TD-DEPLOY-001, TD-049, and TD-055.
# Default mode is read-only. --service-restart is the sole state-changing option.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_NAME="kylin-memory"
SOCKET_PATH="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kylin-memory/memory.sock"
OUT_FILE=""
RESTART_SERVICE=0
REQUIRED_FAILURES=0

usage() {
  cat <<'EOF'
Usage: scripts/verify_d12d_post_merge_techdebt_vm.sh [--output FILE] [--service-restart]

Default mode reads VM, service, KySec, filesystem and UDS state only.
--service-restart restarts the user service after the read-only checks.

This script never writes KySec policy, installs packages, runs rollback, creates users,
or reboots the VM. Record the target, real KySec CLI syntax and rollback procedure before
performing any of those actions manually.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output)
      [ "$#" -ge 2 ] || { echo "--output requires a file" >&2; exit 2; }
      OUT_FILE="$2"
      shift 2
      ;;
    --service-restart)
      RESTART_SERVICE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -n "$OUT_FILE" ]; then
  mkdir -p "$(dirname "$OUT_FILE")"
  exec > >(tee "$OUT_FILE") 2>&1
fi

section() {
  printf '\n===== %s =====\n' "$1"
}

observe() {
  "$@" || printf 'OBSERVATION_FAILED_RC=%s command=%q\n' "$?" "$1"
}

require() {
  if "$@"; then
    printf 'REQUIRED_ASSERTION=PASS command=%q\n' "$1"
  else
    local rc=$?
    REQUIRED_FAILURES=$((REQUIRED_FAILURES + 1))
    printf 'REQUIRED_ASSERTION=FAIL rc=%s command=%q\n' "$rc" "$1" >&2
  fi
}

require_mode() {
  local path="$1" expected_mode="$2" observed_mode
  if ! observed_mode="$(stat -c '%a' "$path")"; then
    printf 'PERMISSION_ASSERTION=FAIL path=%q reason=stat_failed\n' "$path" >&2
    return 1
  fi
  if [ "$observed_mode" != "$expected_mode" ]; then
    printf 'PERMISSION_ASSERTION=FAIL path=%q expected_mode=%s observed_mode=%s\n' \
      "$path" "$expected_mode" "$observed_mode" >&2
    return 1
  fi
  printf 'PERMISSION_ASSERTION=PASS path=%q mode=%s\n' "$path" "$observed_mode"
}

scan_sensitive_markers() {
  local journal_rc grep_rc marker_count
  local -a pipeline_status

  # Never emit matching journal lines: --output may persist stdout/stderr as Evidence.
  # Operators needing the original line must inspect the local journal separately.
  set +e
  journalctl --user -u "$UNIT_NAME" -n 100 --no-pager 2>/dev/null | \
    grep -Eiq 'password|token|api[_-]?key|secret|private.?key'
  pipeline_status=("${PIPESTATUS[@]}")
  journal_rc=${pipeline_status[0]}
  grep_rc=${pipeline_status[1]}
  set -e

  if [ "$journal_rc" -ne 0 ]; then
    printf 'sensitive_marker_scan=UNAVAILABLE journalctl_rc=%s\n' "$journal_rc" >&2
    return 1
  fi
  if [ "$grep_rc" -eq 0 ]; then
    marker_count=1
  elif [ "$grep_rc" -eq 1 ]; then
    marker_count=0
  else
    printf 'sensitive_marker_scan=UNAVAILABLE grep_rc=%s\n' "$grep_rc" >&2
    return 1
  fi

  printf 'sensitive_marker_count=%s\n' "$marker_count"
  [ "$marker_count" -eq 0 ]
}

uds_call() {
  python3 - "$SOCKET_PATH" <<'PY'
import json
import socket
import struct
import sys

sock_path = sys.argv[1]
request = {
    "protocol_version": "1.0",
    "request_id": "d12d-post-merge-retrieve",
    "trace_id": "d12d-post-merge-trace",
    "method": "memory.retrieve",
    "deadline_ms": 1000,
    "payload": {"query": "D12D post-merge verification"},
}
body = json.dumps(request, ensure_ascii=False).encode("utf-8")
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(3)
    client.connect(sock_path)
    client.sendall(struct.pack(">I", len(body)) + body)
    header = client.recv(4)
    if len(header) != 4:
        raise RuntimeError("response header is incomplete")
    size = struct.unpack(">I", header)[0]
    if size > 65536:
        raise RuntimeError("response exceeds frozen IPC limit")
    payload = b""
    while len(payload) < size:
        chunk = client.recv(size - len(payload))
        if not chunk:
            raise RuntimeError("response body is incomplete")
        payload += chunk
response = json.loads(payload.decode("utf-8"))
if response.get("status") != "ok":
    raise RuntimeError("memory.retrieve returned non-ok status")
data = response.get("data")
if not isinstance(data, dict) or "context" not in data:
    raise RuntimeError("memory.retrieve response misses context")
print(json.dumps({
    "status": response["status"],
    "context_count": len(data["context"]),
    "degraded": data.get("degraded"),
    "reason": data.get("reason"),
}, ensure_ascii=False, sort_keys=True))
PY
}

section "identity-and-commit"
printf 'tested_commit=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD)"
printf 'branch=%s\n' "$(git -C "$REPO_DIR" branch --show-current)"
printf 'worktree_status=\n'
git -C "$REPO_DIR" status --short
printf 'user=%s uid=%s xdg_runtime_dir=%s\n' "$(id -un)" "$(id -u)" "${XDG_RUNTIME_DIR:-UNSET}"
uname -a

section "td-kysec-001-read-only"
printf 'kernel_cmdline='; cat /proc/cmdline
printf 'lsm='; cat /sys/kernel/security/lsm 2>/dev/null || true
printf 'kysec_modules=\n'
lsmod | grep -Ei 'kysec|ksaf|kycp' || true
printf 'kysec_services=\n'
systemctl --type=service --all | grep -i kysec || true
printf 'kysec_processes=\n'
ps -ef | grep -i '[k]ysec' || true
printf 'securityfs=\n'
observe find /sys/kernel/security/kysec -maxdepth 2 -printf '%M %u:%g %p\n'
printf 'kysec_tools=\n'
for tool in kysec_get kysec_set kysec_auth kysec_policy kysec_kid; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '%s=%s\n' "$tool" "$(command -v "$tool")"
    "$tool" --help 2>&1 | head -20 || true
  fi
done
printf 'tpm_bypass_log=\n'
journalctl -k --no-pager 2>/dev/null | grep -iE 'kysec.*TPM|TPM.*bypass' || true

section "td-deploy-001-readiness"
printf 'wrapper=\n'
observe ls -l "$HOME/.local/bin/kylin-memory-server"
observe head -2 "$HOME/.local/bin/kylin-memory-server"
printf 'unit=\n'
observe systemctl --user cat "$UNIT_NAME"
printf 'python_dependencies=\n'
if [ -x "$HOME/.venv/bin/python" ]; then
  "$HOME/.venv/bin/python" -c 'import sqlalchemy, alembic, pydantic; print("venv_dependencies=ok")'
elif [ -x "$HOME/d4d-venv/bin/python" ]; then
  "$HOME/d4d-venv/bin/python" -c 'import sqlalchemy, alembic, pydantic; print("venv_dependencies=ok")'
else
  echo 'venv_dependencies=NOT_CHECKED no known project venv'
fi
require bash -n "$REPO_DIR/packaging/systemd/install_kylin_memory.sh"

section "td-049-path-and-permissions"
printf 'legacy_socket_candidates=\n'
find /tmp -path '*/kylin-memory/embedding.sock' -type s -printf '%M %u:%g %p\n' 2>/dev/null || true
printf 'service_paths=\n'
observe stat -c '%a %A %U:%G %n' "$HOME/.config/kylin-memory" "$HOME/.local/share/kylin-memory" "$SOCKET_PATH"
observe stat -c '%a %A %U:%G %n' "$HOME/.local/share/kylin-memory/kylin_memory.db"

section "td-055-service-and-uds"
observe systemctl --user show "$UNIT_NAME" -p ActiveState -p SubState -p ExecMainPID

if [ "$RESTART_SERVICE" -eq 1 ]; then
  section "td-055-explicit-service-restart"
  require systemctl --user restart "$UNIT_NAME"
  sleep 2
fi

section "result-boundary"
require systemctl --user is-active "$UNIT_NAME"
require test -S "$SOCKET_PATH"
require require_mode "$HOME/.config/kylin-memory" 700
require require_mode "$HOME/.local/share/kylin-memory" 700
require require_mode "$SOCKET_PATH" 600
require require_mode "$HOME/.local/share/kylin-memory/kylin_memory.db" 600
require uds_call
require scan_sensitive_markers

if [ "$REQUIRED_FAILURES" -ne 0 ]; then
  printf 'RESULT=FAIL required_assertion_failures=%s\n' "$REQUIRED_FAILURES" >&2
  exit 1
fi

echo 'RESULT=PASS all required assertions passed.'
echo 'TD-KYSEC-001 remains In Progress until KySec exec forced blocking and deployment-policy safety are verified.'
echo 'TD-DEPLOY-001 remains Open until controlled install and rollback are run on this tested_commit.'
echo 'TD-049 remains Open until a controlled different-UID fail-closed test is recorded.'
echo 'TD-055 remains Open until OS reboot and a real C-to-D-to-B request are recorded on this tested_commit.'
