#!/usr/bin/env bash
# Unified Kylin VM verification for Track A Day4 and Day5.

set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="${A_VM_REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd -P)}"
VENV="${A_VM_VENV:-/tmp/a-day4-day5-venv}"
BUILD_DIR="${A_VM_BUILD_DIR:-/tmp/a-day4-day5-build}"
EVIDENCE_DIR="${A_VM_EVIDENCE_DIR:-/tmp/a-day4-day5-evidence}"
SDK_SO="${A_VM_SDK_SO:-/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1}"
EXPECTED_SDK_VERSION="${A_VM_EXPECTED_SDK_VERSION:-1.2.0.0-0k0.4}"
PYTHON_HEADER_ROOT="${A_VM_PYTHON_HEADER_ROOT:-}"
MODE=run
FAILURES=0

usage() {
    cat <<'EOF'
Usage: scripts/verify_a_day4_day5_vm.sh [--preflight-only|--print-config]

Environment overrides:
  A_VM_REPO_ROOT          extracted source or Git checkout root
  A_VM_VENV               Python virtual environment directory
  A_VM_BUILD_DIR          out-of-tree CMake build directory
  A_VM_EVIDENCE_DIR       stdout/stderr and JUnit output directory
  A_VM_SDK_SO             embedding SDK shared library path
  A_VM_EXPECTED_SDK_VERSION
                           required libkylin-coreai-embedding version
  A_VM_PYTHON_HEADER_ROOT extracted dev-package root containing usr/include

The runner fails closed when Python.h, the exact SDK package baseline, or any
required embedding SDK symbol is unavailable. It never installs system
packages or changes OSTree/KySec state.
EOF
}

for argument in "$@"; do
    case "$argument" in
        --help|-h)
            usage
            exit 0
            ;;
        --preflight-only)
            MODE=preflight
            ;;
        --print-config)
            MODE=config
            ;;
        *)
            printf 'unknown argument: %s\n' "$argument" >&2
            usage >&2
            exit 2
            ;;
    esac
done

print_config() {
    printf '%s\n' \
        "repo_root=$REPO_ROOT" \
        "venv=$VENV" \
        "build_dir=$BUILD_DIR" \
        "evidence_dir=$EVIDENCE_DIR" \
        "sdk_so=$SDK_SO" \
        "expected_sdk_version=$EXPECTED_SDK_VERSION" \
        "python_header_root=$PYTHON_HEADER_ROOT"
}

if [[ "$MODE" == config ]]; then
    print_config
    exit 0
fi

log() {
    printf '\n===== %s =====\n' "$*"
}

pass() {
    printf '  [PASS] %s\n' "$*"
}

fail() {
    printf '  [FAIL] %s\n' "$*" >&2
    FAILURES=$((FAILURES + 1))
}

require_command() {
    if command -v "$1" >/dev/null 2>&1; then
        pass "command available: $1"
    else
        fail "required command missing: $1"
    fi
}

run_logged() {
    local name=$1
    shift
    log "$name"
    "$@" 2>&1 | tee "$EVIDENCE_DIR/$name.log"
    local rc=${PIPESTATUS[0]}
    printf '%s\n' "$rc" > "$EVIDENCE_DIR/$name.rc"
    if [[ "$rc" -eq 0 ]]; then
        pass "$name"
    else
        fail "$name (rc=$rc)"
    fi
    return "$rc"
}

log "Configuration"
print_config

mkdir -p "$EVIDENCE_DIR"

log "Preflight: source and host"
if [[ -f "$REPO_ROOT/cpp-bridge/CMakeLists.txt" &&
      -f "$REPO_ROOT/memory-service/tests/test_embedding_service_real.py" ]]; then
    pass "Day4/Day5 source tree present"
else
    fail "invalid source tree: $REPO_ROOT"
fi

if grep -qi '^NAME=.*Kylin' /etc/os-release 2>/dev/null; then
    pass "Kylin host detected"
else
    fail "this runner requires a Kylin host"
fi

for command_name in python3 cmake ctest g++ nm dpkg-query; do
    require_command "$command_name"
done

if [[ "$FAILURES" -ne 0 ]]; then
    exit 1
fi

log "Preflight: Python environment"
if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV" || fail "failed to create venv: $VENV"
fi
PYTHON="$VENV/bin/python"

if ! "$PYTHON" -c 'import pybind11, pytest' >/dev/null 2>&1; then
    fail "venv must already contain pybind11 and pytest: $VENV"
else
    pass "venv contains pybind11 and pytest"
fi

PYTHON_INCLUDE="$($PYTHON -c 'import sysconfig; print(sysconfig.get_path("include"))' 2>/dev/null || true)"
if [[ -n "$PYTHON_INCLUDE" && -f "$PYTHON_INCLUDE/Python.h" ]]; then
    pass "Python.h present: $PYTHON_INCLUDE/Python.h"
elif [[ -n "$PYTHON_HEADER_ROOT" &&
        -f "$PYTHON_HEADER_ROOT$PYTHON_INCLUDE/Python.h" ]]; then
    export CPLUS_INCLUDE_PATH="$PYTHON_HEADER_ROOT$PYTHON_INCLUDE:$PYTHON_HEADER_ROOT/usr/include${CPLUS_INCLUDE_PATH:+:$CPLUS_INCLUDE_PATH}"
    pass "Python.h supplied by extracted package root: $PYTHON_HEADER_ROOT"
else
    fail "Python.h missing at ${PYTHON_INCLUDE:-<unknown>}; restore python3.12-dev or set A_VM_PYTHON_HEADER_ROOT"
fi

log "Preflight: embedding SDK baseline"
if [[ -f "$SDK_SO" ]]; then
    pass "SDK shared library present: $SDK_SO"
else
    fail "SDK shared library missing: $SDK_SO"
fi

SDK_VERSION="$(dpkg-query -W -f='${Version}' libkylin-coreai-embedding 2>/dev/null || true)"
if [[ "$SDK_VERSION" == "$EXPECTED_SDK_VERSION" ]]; then
    pass "SDK package version: $SDK_VERSION"
else
    fail "SDK package version mismatch: actual=${SDK_VERSION:-missing}; expected=$EXPECTED_SDK_VERSION"
fi

required_symbols=(
    text_embedding_create_session
    text_embedding_destroy_session
    text_embedding_init_session
    text_embedding_enable_internal_event_loop
    text_embedding
    embedding_result_get_vector_data
    embedding_result_get_vector_length
    embedding_result_get_error_code
    embedding_result_get_error_message
    embedding_result_destroy
)

if [[ -f "$SDK_SO" ]]; then
    SDK_SYMBOLS="$(nm -D --defined-only "$SDK_SO" 2>/dev/null || true)"
    for symbol in "${required_symbols[@]}"; do
        if grep -Eq "[[:space:]]$symbol$" <<<"$SDK_SYMBOLS"; then
            pass "SDK symbol: $symbol"
        else
            fail "required SDK symbol missing: $symbol"
        fi
    done
fi

if [[ "$FAILURES" -ne 0 ]]; then
    printf '\nPreflight failed with %d issue(s); build and tests were not started.\n' "$FAILURES" >&2
    exit 1
fi

if [[ "$MODE" == preflight ]]; then
    printf '\nPreflight passed.\n'
    exit 0
fi

PYBIND11_DIR="$($PYTHON -m pybind11 --cmakedir)"

if ! run_logged cmake-configure \
    cmake -S "$REPO_ROOT/cpp-bridge" -B "$BUILD_DIR" \
        -Dpybind11_DIR="$PYBIND11_DIR" \
        -DPython_EXECUTABLE="$PYTHON" \
        -DPython3_EXECUTABLE="$PYTHON"; then
    printf 'Build aborted after CMake configure failure; stale artifacts were not used.\n' >&2
    exit 1
fi
if ! run_logged cmake-build cmake --build "$BUILD_DIR" --clean-first -j2; then
    printf 'Verification aborted after build failure; tests were not started.\n' >&2
    exit 1
fi
if ! run_logged ctest ctest --test-dir "$BUILD_DIR" --output-on-failure; then
    printf 'Verification aborted after CTest failure; Python host tests were not started.\n' >&2
    exit 1
fi

export KYLIN_L2=1
export PYTHONPATH="$BUILD_DIR:$REPO_ROOT/memory-service"
export LD_LIBRARY_PATH="/usr/lib/kylin-ai/depends:${LD_LIBRARY_PATH:-}"

log "Built module provenance"
MODULE_PATH="$($PYTHON -c 'import pathlib, kylin_embedding; print(pathlib.Path(kylin_embedding.__file__).resolve())' 2>&1)"
if [[ "$MODULE_PATH" == "$BUILD_DIR"/* ]]; then
    pass "kylin_embedding imported from current build: $MODULE_PATH"
else
    fail "kylin_embedding is not from current build: $MODULE_PATH"
    exit 1
fi

run_pytest_group() {
    local name=$1
    shift
    run_logged "$name" "$PYTHON" -m pytest -q "$@" \
        --junitxml="$EVIDENCE_DIR/$name.junit.xml"
}

run_pytest_group day4-local \
    "$REPO_ROOT/memory-service/tests/test_embedding_provider_import.py" \
    "$REPO_ROOT/memory-service/tests/test_provider_failure_recovery.py"
run_pytest_group day4-exception-mapping \
    "$REPO_ROOT/memory-service/tests/test_exception_mapping.py"
run_pytest_group day4-interpreter-exit \
    "$REPO_ROOT/memory-service/tests/test_interpreter_exit.py"
run_pytest_group day4-load-idempotent \
    "$REPO_ROOT/memory-service/tests/test_load_idempotent.py"
run_pytest_group day5-embedding-service-real \
    "$REPO_ROOT/memory-service/tests/test_embedding_service_real.py"
run_logged day4-real-sdk-smoke \
    "$PYTHON" "$REPO_ROOT/memory-service/tests/run_smoke.py"

log "49-test host gate"
if "$PYTHON" "$REPO_ROOT/scripts/check_junit_totals.py" \
    --expected-tests 49 \
    "$EVIDENCE_DIR/day4-exception-mapping.junit.xml" \
    "$EVIDENCE_DIR/day4-interpreter-exit.junit.xml" \
    "$EVIDENCE_DIR/day4-load-idempotent.junit.xml" \
    "$EVIDENCE_DIR/day5-embedding-service-real.junit.xml"
then
    pass "Day4/Day5 real-host gate: 49 passed, 0 skipped"
else
    fail "Day4/Day5 real-host gate did not produce exactly 49 clean results"
fi

log "Summary"
if [[ "$FAILURES" -eq 0 ]]; then
    printf 'A_DAY4_DAY5_VM result=PASS failures=0 evidence=%s\n' "$EVIDENCE_DIR"
    exit 0
fi

printf 'A_DAY4_DAY5_VM result=FAIL failures=%d evidence=%s\n' "$FAILURES" "$EVIDENCE_DIR" >&2
exit 1
