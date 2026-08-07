#!/usr/bin/env bash
# Host-side CLI regression test. Run on a POSIX host with bash.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

fake_bin="${tmp_dir}/bin"
mkdir -p "${fake_bin}" "${tmp_dir}/home/.d2c-probe-state" "${tmp_dir}/home/d2c-probe/out"
export HOME="${tmp_dir}/home"
export PATH="${fake_bin}:${PATH}"
export D2C_TEST_COMMAND_LOG="${tmp_dir}/commands.log"

cat > "${fake_bin}/kill" <<'EOF'
#!/usr/bin/env bash
printf 'kill %s\n' "$*" >> "${D2C_TEST_COMMAND_LOG}"
exit 0
EOF
cat > "${fake_bin}/pkill" <<'EOF'
#!/usr/bin/env bash
printf 'pkill %s\n' "$*" >> "${D2C_TEST_COMMAND_LOG}"
if [[ " $* " == *" -f "* ]]; then
  exit 99
fi
exit 0
EOF
cat > "${fake_bin}/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "${fake_bin}/kill" "${fake_bin}/pkill" "${fake_bin}/sleep"

run_stop() {
  local script_name="$1"
  local pid_file="$2"
  local meta_file="$3"
  local log_file="$4"

  : > "${D2C_TEST_COMMAND_LOG}"
  printf '4242\n' > "${HOME}/.d2c-probe-state/${pid_file}"
  : > "${log_file}"
  printf 'log_file=%s\n' "${log_file}" > "${HOME}/.d2c-probe-state/${meta_file}"
  "${repo_root}/scripts/${script_name}" stop >/dev/null 2>&1 || true

  grep -Fx "kill 4242" "${D2C_TEST_COMMAND_LOG}" >/dev/null
  grep -Fx "pkill -P 4242" "${D2C_TEST_COMMAND_LOG}" >/dev/null
  if grep -Eq '^pkill .* -f( |$)' "${D2C_TEST_COMMAND_LOG}"; then
    echo "${script_name} used a broad pkill -f cleanup" >&2
    return 1
  fi
}

run_stop "d2c_postturn_isend_counter.sh" "postturn_capture.pid" "postturn_capture.meta" "${HOME}/d2c-probe/out/postturn.log"
run_stop "d2c_tool_event_observer.sh" "tool_capture.pid" "tool_capture.meta" "${HOME}/d2c-probe/out/tool.log"

# The PreChat command name differs, but its cleanup must have the same scope.
printf '4242\n' > "${HOME}/.d2c-probe-state/prechat_capture.pid"
: > "${HOME}/d2c-probe/out/prechat.log"
printf 'capture_log=%s\n' "${HOME}/d2c-probe/out/prechat.log" > "${HOME}/.d2c-probe-state/prechat_capture.meta"
: > "${D2C_TEST_COMMAND_LOG}"
"${repo_root}/scripts/d2c_prechat_context_probe.sh" capture-stop >/dev/null 2>&1 || true
grep -Fx "kill 4242" "${D2C_TEST_COMMAND_LOG}" >/dev/null
grep -Fx "pkill -P 4242" "${D2C_TEST_COMMAND_LOG}" >/dev/null
if grep -Eq '^pkill .* -f( |$)' "${D2C_TEST_COMMAND_LOG}"; then
  echo "d2c_prechat_context_probe.sh used a broad pkill -f cleanup" >&2
  exit 1
fi

# A keyword hit in strace output is not protocol-decoded model-request proof.
printf 'regression\n' > "${HOME}/.d2c-probe-state/prechat_last_timestamp"
printf '%s memory_context\n' '[D2C-MARKER-PRECHAT-001]' \
  > "${HOME}/d2c-probe/out/prechat_regression.model_request.jsonl"
prechat_output="$("${repo_root}/scripts/d2c_prechat_context_probe.sh" collect 2>&1)"
if grep -F 'H2C-PreChat-3 通过' <<< "${prechat_output}" >/dev/null; then
  echo "unverified strace keyword hit was reported as PreChat PASS" >&2
  exit 1
fi
grep -F 'H2C-PreChat-3 未确认' <<< "${prechat_output}" >/dev/null
