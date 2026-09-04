#!/usr/bin/env bash
set -euo pipefail

# D13A 一键正式运行入口。需要在麒麟 VM 上执行，并由操作者先启动
# Memory Service；不会自动安装依赖、重启服务或删除任何数据库。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="${DAY13A_PYTHON:-python3}"
RUN_ID="${DAY13A_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_COUNT="${DAY13A_RUN_COUNT:-3}"
BASELINE_MODE="${DAY13A_BASELINE_MODE:-full}"
IPC_SOCKET="${DAY13A_IPC_SOCKET:-}"
TEXTS="${DAY13A_TEXTS:-1000}"
IPC_REQUESTS="${DAY13A_IPC_REQUESTS:-2000}"
OUTBOX_EVENTS="${DAY13A_OUTBOX_EVENTS:-5000}"
IPC_PAYLOAD=${DAY13A_IPC_PAYLOAD:-'{"schema_version":"1.0","user_id":"day13a-benchmark"}'}

if [[ -z "${IPC_SOCKET}" ]]; then
  echo "必须设置 DAY13A_IPC_SOCKET（指向已启动的真实 Gateway UDS）" >&2
  exit 2
fi
if [[ -z "${DAY13A_SDK_SO:-}" ]]; then
  echo "正式 D13A 必须设置 DAY13A_SDK_SO，以记录实际加载 SDK .so 的路径与 SHA-256" >&2
  exit 2
fi
if [[ -z "${DAY13A_MODEL_VERSION:-${KYLIN_EMBEDDING_MODEL_VERSION:-}}" && -z "${DAY13A_MODEL_SHA256:-${KYLIN_EMBEDDING_MODEL_SHA256:-}}" ]]; then
  echo "正式 D13A 必须设置 DAY13A_MODEL_VERSION 或 DAY13A_MODEL_SHA256，以记录模型身份" >&2
  exit 2
fi
if [[ "${BASELINE_MODE}" != "partial" && "${BASELINE_MODE}" != "full" ]]; then
  echo "DAY13A_BASELINE_MODE 必须为 partial 或 full" >&2
  exit 2
fi

export PYTHONPATH="${ROOT_DIR}/memory-service:${ROOT_DIR}/scripts${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1
export KYLIN_EMBEDDING_SDK_SO_PATH="${DAY13A_SDK_SO}"
export KYLIN_EMBEDDING_MODEL_VERSION="${DAY13A_MODEL_VERSION:-${KYLIN_EMBEDDING_MODEL_VERSION:-}}"
export KYLIN_EMBEDDING_MODEL_SHA256="${DAY13A_MODEL_SHA256:-${KYLIN_EMBEDDING_MODEL_SHA256:-}}"

EXPECTED_COMMIT="${DAY13A_EXPECTED_COMMIT:-$(git -C "${ROOT_DIR}" rev-parse HEAD)}"
EXPECTED_BRANCH="${DAY13A_EXPECTED_BRANCH:-$(git -C "${ROOT_DIR}" branch --show-current)}"
if [[ -z "${EXPECTED_COMMIT}" || -z "${EXPECTED_BRANCH}" ]]; then
  echo "无法冻结 D13A 被测 Git commit/branch；请在具名分支的 Git worktree 执行" >&2
  exit 2
fi
RUN_ROOT="${DAY13A_OUTPUT_DIR:-${TMPDIR:-/tmp}/kylin-day13a/${EXPECTED_COMMIT}/${RUN_ID}}"
RUN_ROOT="$(realpath -m "${RUN_ROOT}")"
if [[ "${RUN_ROOT}" == "${ROOT_DIR}" || "${RUN_ROOT}" == "${ROOT_DIR}/"* ]]; then
  echo "正式 D13A 输出目录必须位于 Git worktree 外：${RUN_ROOT}" >&2
  exit 2
fi
mkdir -p "${RUN_ROOT}"

assert_worktree_clean() {
  if [[ -n "$(git -C "${ROOT_DIR}" status --porcelain)" ]]; then
    echo "D13A runner 检测到 Git worktree 已变更，拒绝继续：${ROOT_DIR}" >&2
    exit 2
  fi
}

run_one() {
  local run_dir="$1"
  mkdir -p "${run_dir}/raw"

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/bench_utils.py" \
    --repo-root "${ROOT_DIR}" --output "${run_dir}/environment.json" \
    --expected-commit "${EXPECTED_COMMIT}" --expected-branch "${EXPECTED_BRANCH}"
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/bench_utils.py" \
    --validate-formal-environment "${run_dir}/environment.json" \
    --expected-commit "${EXPECTED_COMMIT}" --expected-branch "${EXPECTED_BRANCH}"

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_embedding.py" \
    --texts "${TEXTS}" --concurrency 1 4 8 --warmup 50 \
    --output-dir "${run_dir}"

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_bridge.py" \
    --texts "${TEXTS}" --concurrency 1 4 8 --warmup 50 \
    --so-path "${DAY13A_SDK_SO}" --output-dir "${run_dir}"

  IPC_ARGS=()
  if [[ -n "${DAY13A_IPC_PID:-}" ]]; then
    IPC_ARGS+=(--pid "${DAY13A_IPC_PID}")
  fi
  for ipc_method in echo memory.retrieve; do
    ipc_dir="${run_dir}/ipc_${ipc_method//./_}"
    "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_ipc.py" \
      --socket "${IPC_SOCKET}" --method "${ipc_method}" \
      --payload "${IPC_PAYLOAD}" \
      --requests "${IPC_REQUESTS}" --concurrency 1 4 8 16 --warmup 50 \
      "${IPC_ARGS[@]}" \
      --output-dir "${ipc_dir}"
  done

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/benchmark_outbox.py" \
    --db "${run_dir}/outbox.sqlite3" --events "${OUTBOX_EVENTS}" \
    --output-dir "${run_dir}"

  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/bench_utils.py" \
    --merge-run "${run_dir}" --mode "${BASELINE_MODE}" \
    --expected-commit "${EXPECTED_COMMIT}" --expected-branch "${EXPECTED_BRANCH}"
  assert_worktree_clean
  echo "D13A run complete: ${run_dir}"
}

if ! [[ "${RUN_COUNT}" =~ ^[1-9][0-9]*$ ]]; then
  echo "DAY13A_RUN_COUNT 必须是正整数" >&2
  exit 2
fi
if [[ "${RUN_COUNT}" == "1" ]]; then
  run_one "${RUN_ROOT}/run_01"
else
  for index in $(seq 1 "${RUN_COUNT}"); do
    run_one "${RUN_ROOT}/run_$(printf '%02d' "${index}")"
  done
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/bench_utils.py" \
    --merge-collection "${RUN_ROOT}" --mode "${BASELINE_MODE}" \
    --expected-commit "${EXPECTED_COMMIT}" --expected-branch "${EXPECTED_BRANCH}"
fi
