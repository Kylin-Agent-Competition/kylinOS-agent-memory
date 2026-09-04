#!/usr/bin/env bash
set -euo pipefail

# D13A 一键正式运行入口。需要在麒麟 VM 上执行，并由操作者先启动
# Memory Service；不会自动安装依赖、重启服务或删除任何数据库。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DAY13A_PYTHON:-python3}"
RUN_ID="${DAY13A_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_COUNT="${DAY13A_RUN_COUNT:-3}"
IPC_SOCKET="${DAY13A_IPC_SOCKET:-}"
TEXTS="${DAY13A_TEXTS:-1000}"
IPC_REQUESTS="${DAY13A_IPC_REQUESTS:-2000}"
OUTBOX_EVENTS="${DAY13A_OUTBOX_EVENTS:-5000}"

if [[ -z "${IPC_SOCKET}" ]]; then
  echo "必须设置 DAY13A_IPC_SOCKET（指向已启动的真实 Gateway UDS）" >&2
  exit 2
fi

export PYTHONPATH="${ROOT_DIR}/memory-service:${ROOT_DIR}/scripts${PYTHONPATH:+:${PYTHONPATH}}"

run_one() {
  local run_dir="$1"
  mkdir -p "${run_dir}/raw"

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/bench_utils.py" \
    --repo-root "${ROOT_DIR}" --output "${run_dir}/environment.json"

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_embedding.py" \
    --texts "${TEXTS}" --concurrency 1 4 8 --warmup 50 \
    --output-dir "${run_dir}"

  BRIDGE_ARGS=()
  if [[ -n "${DAY13A_SDK_SO:-}" ]]; then
    BRIDGE_ARGS+=(--so-path "${DAY13A_SDK_SO}")
  fi
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_bridge.py" \
    --texts "${TEXTS}" --concurrency 1 4 8 --warmup 50 \
    "${BRIDGE_ARGS[@]}" --output-dir "${run_dir}"

  IPC_ARGS=()
  if [[ -n "${DAY13A_IPC_PID:-}" ]]; then
    IPC_ARGS+=(--pid "${DAY13A_IPC_PID}")
  fi
  for ipc_method in echo memory.retrieve; do
    ipc_dir="${run_dir}/ipc_${ipc_method//./_}"
    "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_ipc.py" \
      --socket "${IPC_SOCKET}" --method "${ipc_method}" \
      --requests "${IPC_REQUESTS}" --concurrency 1 4 8 16 --warmup 50 \
      "${IPC_ARGS[@]}" \
      --output-dir "${ipc_dir}"
  done

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_outbox.py" \
    --db "${run_dir}/outbox.sqlite3" --events "${OUTBOX_EVENTS}" \
    --output-dir "${run_dir}"

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/bench_utils.py" --merge-run "${run_dir}"
  echo "D13A run complete: ${run_dir}"
}

if ! [[ "${RUN_COUNT}" =~ ^[1-9][0-9]*$ ]]; then
  echo "DAY13A_RUN_COUNT 必须是正整数" >&2
  exit 2
fi
if [[ "${RUN_COUNT}" == "1" ]]; then
  run_one "${DAY13A_OUTPUT_DIR:-${ROOT_DIR}/perf/day13a/${RUN_ID}}"
else
  for index in $(seq 1 "${RUN_COUNT}"); do
    run_one "${ROOT_DIR}/perf/day13a/run_$(printf '%02d' "${index}")"
  done
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/bench_utils.py" \
    --merge-collection "${ROOT_DIR}/perf/day13a"
fi
