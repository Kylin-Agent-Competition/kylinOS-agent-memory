#!/usr/bin/env bash
set -euo pipefail

# D1-B Vector Engine baseline runner.
#
# This runner performs environment and dependency preflight checks, builds the
# committed C++ probe in a temporary directory, and runs exactly one probe
# phase. It never restarts the Vector Engine service automatically.

readonly DEFAULT_SERVICE_UNIT="kylin-ai-vector-engine.service"
readonly DEFAULT_APP_ID="d1-vector-baseline"
readonly DEFAULT_COLLECTION="d1_vector_baseline"
readonly PKG_CONFIG_MODULE="kysdk-vector-engine-client"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly PROBE_SOURCE="${PROJECT_ROOT}/tests/vector-engine/d1_vector_baseline.cpp"

PHASE=""
DB_FILE=""
APP_ID="${DEFAULT_APP_ID}"
COLLECTION="${DEFAULT_COLLECTION}"
SERVICE_UNIT="${DEFAULT_SERVICE_UNIT}"
PREVIOUS_INVOCATION_ID=""
CURRENT_INVOCATION_ID=""
BUILD_DIR=""

log() {
    local step="$1"
    local result="$2"
    local detail="$3"
    detail="${detail//$'\n'/ }"
    detail="${detail//$'\r'/ }"
    detail="${detail//\"/\'}"
    printf 'D1_VECTOR_RUNNER step=%s result=%s detail="%s"\n' \
        "${step}" "${result}" "${detail}"
}

fail() {
    local step="$1"
    local detail="$2"
    log "${step}" "FAIL" "${detail}"
    exit 1
}

pass() {
    local step="$1"
    local detail="$2"
    log "${step}" "PASS" "${detail}"
}

usage() {
    cat <<'EOF'
Usage:
  scripts/run_d1_vector_baseline.sh \
    --phase <prepare|verify|cleanup> \
    --db-file <absolute-path> \
    [--app-id <id>] \
    [--collection <name>] \
    [--service-unit <systemd-user-unit>] \
    [--previous-invocation-id <id>]

Persistence workflow:
  1. Run this script with --phase prepare.
  2. Save the complete output.
  3. Manually restart the user service:
       systemctl --user restart kylin-ai-vector-engine.service
  4. Run this script with --phase verify, identical arguments, and:
       --previous-invocation-id <prepare-output-invocation-id>
  5. Save the complete output before optionally running --phase cleanup.

The script does not install packages, start/restart services, write evidence
files, or upload results.
EOF
}

require_value() {
    local option="$1"
    local remaining="$2"
    if [[ "${remaining}" -lt 2 ]]; then
        fail "arguments" "missing value for ${option}"
    fi
}

parse_arguments() {
    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            --phase)
                require_value "$1" "$#"
                PHASE="$2"
                shift 2
                ;;
            --db-file)
                require_value "$1" "$#"
                DB_FILE="$2"
                shift 2
                ;;
            --app-id)
                require_value "$1" "$#"
                APP_ID="$2"
                shift 2
                ;;
            --collection)
                require_value "$1" "$#"
                COLLECTION="$2"
                shift 2
                ;;
            --service-unit)
                require_value "$1" "$#"
                SERVICE_UNIT="$2"
                shift 2
                ;;
            --previous-invocation-id)
                require_value "$1" "$#"
                PREVIOUS_INVOCATION_ID="$2"
                shift 2
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                fail "arguments" "unknown argument: $1"
                ;;
        esac
    done

    case "${PHASE}" in
        prepare|verify|cleanup)
            ;;
        "")
            fail "arguments" "--phase is required"
            ;;
        *)
            fail "arguments" "unsupported phase: ${PHASE}"
            ;;
    esac

    if [[ -z "${DB_FILE}" ]]; then
        fail "arguments" "--db-file is required"
    fi
    if [[ "${DB_FILE}" != /* ]]; then
        fail "arguments" "--db-file must be an absolute path"
    fi
    if [[ -z "${APP_ID}" ]]; then
        fail "arguments" "--app-id cannot be empty"
    fi
    if [[ ! "${COLLECTION}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        fail "arguments" \
            "--collection must start with a letter or underscore and contain only letters, digits, or underscores"
    fi
    if [[ ! "${SERVICE_UNIT}" =~ ^[A-Za-z0-9_.@:-]+\.service$ ]]; then
        fail "arguments" "--service-unit must be a valid systemd .service unit name"
    fi
    if [[ "${PHASE}" == "verify" && -z "${PREVIOUS_INVOCATION_ID}" ]]; then
        fail "arguments" "--previous-invocation-id is required for the verify phase"
    fi
    if [[ -n "${PREVIOUS_INVOCATION_ID}" &&
          ! "${PREVIOUS_INVOCATION_ID}" =~ ^[[:xdigit:]]{32}$ ]]; then
        fail "arguments" "--previous-invocation-id must be a 32-character hexadecimal systemd InvocationID"
    fi
}

cleanup_build_dir() {
    if [[ -n "${BUILD_DIR}" && -d "${BUILD_DIR}" ]]; then
        local temp_root="${TMPDIR:-/tmp}"
        case "${BUILD_DIR}" in
            "${temp_root%/}"/d1-vector-baseline.*)
                rm -rf -- "${BUILD_DIR}"
                ;;
            *)
                log "cleanup_build_dir" "FAIL" \
                    "refusing to remove unexpected path: ${BUILD_DIR}"
                ;;
        esac
    fi
}

require_command() {
    local command_name="$1"
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        fail "dependency_${command_name}" "${command_name} is not installed or not in PATH"
    fi
    pass "dependency_${command_name}" "$(command -v "${command_name}")"
}

check_operating_system() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        fail "os_check" "Linux is required; detected $(uname -s)"
    fi
    if [[ ! -r /etc/os-release ]]; then
        fail "os_check" "/etc/os-release is missing or unreadable"
    fi

    # shellcheck disable=SC1091
    source /etc/os-release
    local identity="${ID:-unknown} ${ID_LIKE:-} ${NAME:-unknown} ${PRETTY_NAME:-unknown}"
    if [[ ! "${identity,,}" =~ kylin ]]; then
        fail "os_check" "Kylin/openKylin is required; detected ${PRETTY_NAME:-unknown}"
    fi
    pass "os_check" "os=${PRETTY_NAME:-unknown}; arch=$(uname -m)"
}

check_database_path() {
    local parent
    parent="$(dirname -- "${DB_FILE}")"

    if [[ "${PHASE}" == "prepare" ]]; then
        if [[ ! -d "${parent}" ]]; then
            fail "database_path" "parent directory does not exist: ${parent}"
        fi
        if [[ ! -w "${parent}" ]]; then
            fail "database_path" "parent directory is not writable: ${parent}"
        fi
        pass "database_path" "prepare target parent is writable: ${parent}"
        return
    fi

    if [[ ! -f "${DB_FILE}" ]]; then
        fail "database_path" "database file does not exist for ${PHASE}: ${DB_FILE}"
    fi
    if [[ ! -r "${DB_FILE}" ]]; then
        fail "database_path" "database file is not readable: ${DB_FILE}"
    fi
    pass "database_path" "existing database file is readable: ${DB_FILE}"
}

check_service() {
    local load_state
    local active_state
    local sub_state
    local fragment_path

    if ! systemctl --user show "${SERVICE_UNIT}" --no-pager >/dev/null 2>&1; then
        fail "service_status" \
            "${SERVICE_UNIT} is unavailable in the current user systemd session"
    fi
    load_state="$(systemctl --user show "${SERVICE_UNIT}" --property=LoadState --value)"
    active_state="$(systemctl --user show "${SERVICE_UNIT}" --property=ActiveState --value)"
    sub_state="$(systemctl --user show "${SERVICE_UNIT}" --property=SubState --value)"
    fragment_path="$(systemctl --user show "${SERVICE_UNIT}" --property=FragmentPath --value)"
    CURRENT_INVOCATION_ID="$(
        systemctl --user show "${SERVICE_UNIT}" --property=InvocationID --value
    )"

    if [[ "${load_state}" != "loaded" || "${active_state}" != "active" ]]; then
        fail "service_status" \
            "${SERVICE_UNIT} is not ready; load=${load_state}, active=${active_state}, sub=${sub_state}"
    fi
    if [[ ! "${CURRENT_INVOCATION_ID}" =~ ^[[:xdigit:]]{32}$ ]]; then
        fail "service_status" \
            "${SERVICE_UNIT} returned an invalid or empty InvocationID"
    fi
    pass "service_status" \
        "unit=${SERVICE_UNIT}; load=${load_state}; active=${active_state}; sub=${sub_state}; fragment=${fragment_path}; invocation_id=${CURRENT_INVOCATION_ID}"

    if [[ "${PHASE}" == "verify" ]]; then
        if [[ "${CURRENT_INVOCATION_ID,,}" == "${PREVIOUS_INVOCATION_ID,,}" ]]; then
            fail "service_restart" \
                "InvocationID is unchanged; restart ${SERVICE_UNIT} before verify"
        fi
        pass "service_restart" \
            "InvocationID changed from ${PREVIOUS_INVOCATION_ID} to ${CURRENT_INVOCATION_ID}"
    fi
}

check_sdk() {
    if ! pkg-config --exists "${PKG_CONFIG_MODULE}"; then
        fail "sdk_pkg_config" \
            "pkg-config module not found: ${PKG_CONFIG_MODULE}"
    fi

    local version
    local cflags
    local libs
    version="$(pkg-config --modversion "${PKG_CONFIG_MODULE}")"
    cflags="$(pkg-config --cflags "${PKG_CONFIG_MODULE}")"
    libs="$(pkg-config --libs "${PKG_CONFIG_MODULE}")"
    pass "sdk_pkg_config" "module=${PKG_CONFIG_MODULE}; version=${version}; cflags=${cflags}; libs=${libs}"
}

build_probe() {
    if [[ ! -f "${PROBE_SOURCE}" ]]; then
        fail "probe_source" "probe source is missing: ${PROBE_SOURCE}"
    fi
    pass "probe_source" "${PROBE_SOURCE}"

    BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/d1-vector-baseline.XXXXXX")"
    local output="${BUILD_DIR}/d1_vector_baseline"
    local -a package_flags=()

    # pkg-config returns compiler/linker tokens separated by shell whitespace.
    # The official package paths do not contain whitespace.
    read -r -a package_flags <<<"$(pkg-config --cflags --libs "${PKG_CONFIG_MODULE}")"

    if ! g++ \
        -std=c++17 \
        -Wall \
        -Wextra \
        -Wpedantic \
        -Werror \
        "${PROBE_SOURCE}" \
        -o "${output}" \
        "${package_flags[@]}"; then
        fail "probe_build" "g++ failed to build the D1 Vector Engine probe"
    fi
    pass "probe_build" "temporary binary built: ${output}"
}

run_probe() {
    local binary="${BUILD_DIR}/d1_vector_baseline"
    log "probe_execute" "INFO" \
        "phase=${PHASE}; collection=${COLLECTION}; db_file=${DB_FILE}; app_id=${APP_ID}"

    if ! "${binary}" \
        --phase "${PHASE}" \
        --db-file "${DB_FILE}" \
        --app-id "${APP_ID}" \
        --collection "${COLLECTION}"; then
        fail "probe_execute" "probe phase ${PHASE} failed"
    fi
    pass "probe_execute" "probe phase ${PHASE} completed successfully"
}

main() {
    parse_arguments "$@"
    trap cleanup_build_dir EXIT

    log "runner_start" "INFO" \
        "phase=${PHASE}; service_unit=${SERVICE_UNIT}; project_root=${PROJECT_ROOT}"

    check_operating_system
    require_command systemctl
    require_command g++
    require_command pkg-config
    require_command mktemp
    check_database_path
    check_service
    check_sdk
    build_probe
    run_probe

    if [[ "${PHASE}" == "prepare" ]]; then
        log "restart_token" "INFO" \
            "invocation_id=${CURRENT_INVOCATION_ID}"
        log "manual_restart_required" "INFO" \
            "save invocation_id=${CURRENT_INVOCATION_ID}; run systemctl --user restart ${SERVICE_UNIT}; pass the saved value to verify with --previous-invocation-id"
    fi
    pass "runner_complete" "phase ${PHASE} completed; no service restart or evidence upload was performed"
}

main "$@"
