#!/usr/bin/env bash
# Host-side CLI regression test. Run on a POSIX host with bash.
set -euo pipefail

source_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

fake_bin="${tmp_dir}/bin"
repo_root="${tmp_dir}/repo"
mkdir -p "${fake_bin}" "${tmp_dir}/home/.d2c-probe-state" "${tmp_dir}/home/d2c-probe/out" "${repo_root}/scripts"
cp "${source_repo_root}/scripts/d2c_postturn_isend_counter.sh" \
  "${source_repo_root}/scripts/d2c_tool_event_observer.sh" \
  "${source_repo_root}/scripts/d2c_prechat_context_probe.sh" "${repo_root}/scripts/"
export HOME="${tmp_dir}/home"
export PATH="${fake_bin}:${PATH}"

cat > "${fake_bin}/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "${fake_bin}/pgrep" <<'EOF'
#!/usr/bin/env bash
# Keep the public CLI test independent from a real AI assistant running on the host.
exit 1
EOF
chmod +x "${fake_bin}/sleep" "${fake_bin}/pgrep"

test_pids=()
cleanup_processes() {
  local pid
  for pid in "${test_pids[@]:-}"; do
    kill "${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
  done
}
trap 'cleanup_processes; rm -rf "${tmp_dir}"' EXIT

assert_exited() {
  local pid="$1"
  if kill -0 "${pid}" 2>/dev/null; then
    echo "target capture process ${pid} is still alive after stop" >&2
    return 1
  fi
}

assert_alive() {
  local pid="$1"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "unrelated parallel capture ${pid} was terminated" >&2
    return 1
  fi
}

run_stop() {
  local script_name="$1"
  local pid_file="$2"
  local meta_file="$3"
  local log_file="$4"

  /bin/sleep 60 &
  local target_pid=$!
  # This argv shape is deliberately what the old broad pkill -f pattern matched.
  bash -c 'exec -a "strace -p 9999 kylin-aiassistant" /bin/sleep 60' &
  local unrelated_pid=$!
  test_pids+=("${target_pid}" "${unrelated_pid}")

  printf '%s\n' "${target_pid}" > "${HOME}/.d2c-probe-state/${pid_file}"
  : > "${log_file}"
  case "${script_name}" in
    d2c_postturn_isend_counter.sh)
      printf 'log_file=%s\ntimestamp=%s\n' "${log_file}" "20260809_000000" \
        > "${HOME}/.d2c-probe-state/${meta_file}"
      ;;
    d2c_tool_event_observer.sh)
      printf 'raw_log=%s\nfiltered_log=%s\ntimestamp=%s\n' \
        "${log_file}" "${log_file}.filtered" "20260809_000000" \
        > "${HOME}/.d2c-probe-state/${meta_file}"
      ;;
  esac
  local stop_output
  if ! stop_output="$("${repo_root}/scripts/${script_name}" stop 2>&1)"; then
    printf '%s\n' "${stop_output}" >&2
    return 1
  fi

  assert_exited "${target_pid}"
  assert_alive "${unrelated_pid}"
}

run_stop "d2c_postturn_isend_counter.sh" "postturn_capture.pid" "postturn_capture.meta" "${HOME}/d2c-probe/out/postturn.log"
run_stop "d2c_tool_event_observer.sh" "tool_capture.pid" "tool_capture.meta" "${HOME}/d2c-probe/out/tool.log"

# The PreChat command name differs, but its cleanup must have the same scope.
/bin/sleep 60 &
prechat_target_pid=$!
bash -c 'exec -a "strace -p 9998 kylin-aiassistant" /bin/sleep 60' &
prechat_unrelated_pid=$!
test_pids+=("${prechat_target_pid}" "${prechat_unrelated_pid}")
printf '%s\n' "${prechat_target_pid}" > "${HOME}/.d2c-probe-state/prechat_capture.pid"
: > "${HOME}/d2c-probe/out/prechat.log"
printf 'capture_log=%s\nmodel_request_file=%s\ntimestamp=%s\n' \
  "${HOME}/d2c-probe/out/prechat.log" \
  "${HOME}/d2c-probe/out/prechat_20260809_000000.model_request.jsonl" \
  "20260809_000000" > "${HOME}/.d2c-probe-state/prechat_capture.meta"
if ! prechat_stop_output="$("${repo_root}/scripts/d2c_prechat_context_probe.sh" capture-stop 2>&1)"; then
  printf '%s\n' "${prechat_stop_output}" >&2
  exit 1
fi
assert_exited "${prechat_target_pid}"
assert_alive "${prechat_unrelated_pid}"

# A keyword hit in strace output is not protocol-decoded model-request proof.
printf 'regression\n' > "${HOME}/.d2c-probe-state/prechat_last_timestamp"
printf '%s memory_context\n' '[D2C-MARKER-PRECHAT-001]' \
  > "${repo_root}/scripts/out/prechat_20260809_000000.model_request.jsonl"
prechat_output="$("${repo_root}/scripts/d2c_prechat_context_probe.sh" collect 2>&1)"
if grep -F 'H2C-PreChat-3 通过' <<< "${prechat_output}" >/dev/null; then
  echo "unverified strace keyword hit was reported as PreChat PASS" >&2
  exit 1
fi
grep -F 'H2C-PreChat-3 未确认' <<< "${prechat_output}" >/dev/null
