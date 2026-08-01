#!/usr/bin/env bash
set -euo pipefail

# D2 Vector Engine smoke runner for the Kylin 0k0.7 client ABI.
#
# Build and execution are deliberately separate because KySec trust is tied to
# an exact binary hash. This script never changes trust, restarts a service, or
# installs packages.

readonly EXPECTED_CLIENT_VERSION="1.2.0.0-0k0.7"
readonly EXPECTED_ENGINE_VERSION="1.2.0.1-0k0.11"
readonly EXPECTED_SDK_COMMIT="2213447ef765e709e93f94d4177f4417478fe8ea"
readonly DEFAULT_SERVICE_UNIT="d2-vector-engine.service"
readonly DEFAULT_APP_ID="d2-vector-smoke"
readonly COLLECTION_PREFIX="d2_vector_smoke_"
readonly TEST_ROOT_PREFIX="d2-b-vector-smoke-"
readonly MANIFEST_NAME="d2-vector-smoke.manifest"
readonly DEFAULT_DATABASE_RELATIVE=".local/share/kylin-ai-vector-engine/default.db"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly PROBE_SOURCE="${PROJECT_ROOT}/tests/vector-engine/d2_vector_smoke.cpp"
readonly ABI_PATCH="${PROJECT_ROOT}/tests/vector-engine/compat/kysdk-vector-engine-client-1.2.0.0-0k0.7.patch"
readonly ABI_ASSERTS="${PROJECT_ROOT}/tests/vector-engine/compat/d2_legacy_abi_asserts.h"

ACTION=""
PHASE=""
DB_FILE=""
APP_ID="${DEFAULT_APP_ID}"
RUN_ID=""
COLLECTION=""
SERVICE_UNIT="${DEFAULT_SERVICE_UNIT}"
SDK_SOURCE=""
BINARY=""
BUILD_DIR=""
RUNTIME_LIBRARY=""
CURRENT_INVOCATION_ID=""
TEST_ROOT=""
TEST_ROOT_CANONICAL=""
MANIFEST_FILE=""
MANIFEST_TEMP=""
MANIFEST_PREPARE_INVOCATION_ID=""
DATABASE_CANONICAL=""
DATABASE_IDENTITY=""
BINARY_HASH=""
PROJECT_COMMIT=""
PROBE_SOURCE_HASH=""
RUNNER_SOURCE_HASH=""
ABI_PATCH_HASH=""
ABI_ASSERTS_HASH=""

log() {
    local step="$1"
    local result="$2"
    local detail="$3"
    detail="${detail//$'\n'/ }"
    detail="${detail//$'\r'/ }"
    detail="${detail//\"/\'}"
    printf 'D2_VECTOR_RUNNER step=%s result=%s detail="%s"\n' \
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
Build an untrusted fixed-path probe:
  scripts/run_d2_vector_smoke.sh \
    --action build \
    --sdk-source <absolute-clean-or-dirty-checkout> \
    --binary <absolute-new-output-path>

After an operator verifies the hash and grants temporary KySec trust, run:
  scripts/run_d2_vector_smoke.sh \
    --action run \
    --phase <prepare|verify|cleanup> \
    --run-id <6-32-lowercase-letters-or-digits> \
    --db-file <absolute-path> \
    --binary <absolute-trusted-probe-path> \
    [--app-id <id>] \
    [--collection <name>] \
    [--service-unit <systemd-user-unit>]

For run, the approved test root is fixed to:
  $HOME/d2-b-vector-smoke-<run-id>
The database must be a canonical regular file below that root. The collection
must exactly equal d2_vector_smoke_<run-id>. Prepare creates a hash-bound
manifest in the test root; verify and cleanup must match that same manifest.

This runner never installs dependencies, changes KySec trust, starts/restarts
services, copies databases, writes evidence, or performs Git operations on the
project checkout.
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
            --action)
                require_value "$1" "$#"
                ACTION="$2"
                shift 2
                ;;
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
            --run-id)
                require_value "$1" "$#"
                RUN_ID="$2"
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
            --sdk-source)
                require_value "$1" "$#"
                SDK_SOURCE="$2"
                shift 2
                ;;
            --binary)
                require_value "$1" "$#"
                BINARY="$2"
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

    case "${ACTION}" in
        build|run)
            ;;
        "")
            fail "arguments" "--action is required"
            ;;
        *)
            fail "arguments" "unsupported action: ${ACTION}"
            ;;
    esac

    if [[ -z "${BINARY}" || "${BINARY}" != /* ]]; then
        fail "arguments" "--binary must be an absolute path"
    fi

    if [[ "${ACTION}" == "build" ]]; then
        if [[ -z "${SDK_SOURCE}" || "${SDK_SOURCE}" != /* ]]; then
            fail "arguments" "--sdk-source must be an absolute path for build"
        fi
        if [[ -n "${PHASE}" || -n "${DB_FILE}" || -n "${RUN_ID}" ||
              -n "${COLLECTION}" ]]; then
            fail "arguments" "build does not accept run-phase or collection options"
        fi
        return
    fi

    case "${PHASE}" in
        prepare|verify|cleanup)
            ;;
        "")
            fail "arguments" "--phase is required for run"
            ;;
        *)
            fail "arguments" "unsupported phase: ${PHASE}"
            ;;
    esac
    if [[ -z "${DB_FILE}" || "${DB_FILE}" != /* ]]; then
        fail "arguments" "--db-file must be an absolute path for run"
    fi
    if [[ -n "${SDK_SOURCE}" ]]; then
        fail "arguments" "--sdk-source is only valid for build"
    fi
    if [[ -z "${APP_ID}" ]]; then
        fail "arguments" "--app-id cannot be empty"
    fi
    if [[ ! "${RUN_ID}" =~ ^[a-z0-9]{6,32}$ ]]; then
        fail "arguments" \
            "--run-id must contain 6-32 lowercase ASCII letters or digits"
    fi
    local expected_collection="${COLLECTION_PREFIX}${RUN_ID}"
    if [[ -z "${COLLECTION}" ]]; then
        COLLECTION="${expected_collection}"
    fi
    if [[ "${COLLECTION}" != "${expected_collection}" ]]; then
        fail "arguments" \
            "--collection must exactly equal ${expected_collection}"
    fi
    if [[ ! "${SERVICE_UNIT}" =~ ^[A-Za-z0-9][A-Za-z0-9_.@:-]*\.service$ ]]; then
        fail "arguments" "--service-unit must be a valid systemd .service unit name"
    fi
    TEST_ROOT="${HOME}/${TEST_ROOT_PREFIX}${RUN_ID}"
    MANIFEST_FILE="${TEST_ROOT}/${MANIFEST_NAME}"
}

cleanup_build_dir() {
    if [[ -z "${BUILD_DIR}" || ! -d "${BUILD_DIR}" ]]; then
        return
    fi
    local temp_root="${TMPDIR:-/tmp}"
    case "${BUILD_DIR}" in
        "${temp_root%/}"/d2-vector-smoke.*)
            rm -rf -- "${BUILD_DIR}"
            ;;
        *)
            log "cleanup_build_dir" "FAIL" \
                "refusing to remove unexpected path: ${BUILD_DIR}"
            ;;
    esac
}

cleanup_manifest_temp() {
    if [[ -n "${MANIFEST_TEMP}" && -f "${MANIFEST_TEMP}" ]]; then
        rm -- "${MANIFEST_TEMP}"
    fi
}

cleanup_temporary_files() {
    cleanup_build_dir
    cleanup_manifest_temp
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

package_version() {
    local package_name="$1"
    dpkg-query -W -f='${Version}' "${package_name}" 2>/dev/null || true
}

check_runtime_packages() {
    require_command dpkg-query
    require_command ldconfig

    local client_version
    local engine_version
    local ldconfig_output

    client_version="$(package_version libkysdk-vector-engine-client)"
    engine_version="$(package_version kylin-ai-vector-engine)"
    if [[ "${client_version}" != "${EXPECTED_CLIENT_VERSION}" ]]; then
        fail "client_version" \
            "expected ${EXPECTED_CLIENT_VERSION}; detected ${client_version:-missing}"
    fi
    if [[ "${engine_version}" != "${EXPECTED_ENGINE_VERSION}" ]]; then
        fail "engine_version" \
            "expected ${EXPECTED_ENGINE_VERSION}; detected ${engine_version:-missing}"
    fi
    pass "runtime_versions" \
        "client=${client_version}; engine=${engine_version}"

    ldconfig_output="$(ldconfig -p 2>/dev/null)"
    RUNTIME_LIBRARY="$(
        awk '$1 == "libkysdk-vector-engine-client.so.1" { print $NF; exit }' \
            <<<"${ldconfig_output}"
    )"
    if [[ -z "${RUNTIME_LIBRARY}" || ! -f "${RUNTIME_LIBRARY}" ]]; then
        fail "runtime_library" \
            "libkysdk-vector-engine-client.so.1 was not found by ldconfig"
    fi
    pass "runtime_library" "${RUNTIME_LIBRARY}"
}

check_project_inputs() {
    require_command git
    require_command sha256sum
    local path
    for path in "${PROBE_SOURCE}" "${ABI_PATCH}" "${ABI_ASSERTS}"; do
        if [[ ! -f "${path}" || ! -r "${path}" ]]; then
            fail "project_input" "missing or unreadable: ${path}"
        fi
    done
    if [[ ! -d "${PROJECT_ROOT}/.git" ]]; then
        fail "project_input" "project root is not a Git checkout: ${PROJECT_ROOT}"
    fi
    PROJECT_COMMIT="$(git -C "${PROJECT_ROOT}" rev-parse HEAD)"
    if [[ ! "${PROJECT_COMMIT}" =~ ^[[:xdigit:]]{40}$ ]]; then
        fail "project_input" "project returned an invalid commit ID"
    fi
    PROBE_SOURCE_HASH="$(sha256sum "${PROBE_SOURCE}" | awk '{print $1}')"
    RUNNER_SOURCE_HASH="$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')"
    ABI_PATCH_HASH="$(sha256sum "${ABI_PATCH}" | awk '{print $1}')"
    ABI_ASSERTS_HASH="$(sha256sum "${ABI_ASSERTS}" | awk '{print $1}')"
    pass "project_identity" \
        "project_commit=${PROJECT_COMMIT}; probe_source_sha256=${PROBE_SOURCE_HASH}; runner_source_sha256=${RUNNER_SOURCE_HASH}; abi_patch_sha256=${ABI_PATCH_HASH}; abi_asserts_sha256=${ABI_ASSERTS_HASH}"
}

build_probe() {
    require_command git
    require_command g++
    require_command install
    require_command mktemp
    require_command nice
    require_command sha256sum

    if [[ ! -d "${SDK_SOURCE}/.git" ]]; then
        fail "sdk_source" "not a Git checkout: ${SDK_SOURCE}"
    fi
    local source_commit
    source_commit="$(git -C "${SDK_SOURCE}" rev-parse HEAD)"
    if [[ "${source_commit}" != "${EXPECTED_SDK_COMMIT}" ]]; then
        fail "sdk_source" \
            "expected commit ${EXPECTED_SDK_COMMIT}; detected ${source_commit}"
    fi
    if [[ -e "${BINARY}" ]]; then
        fail "binary_output" \
            "refusing to overwrite existing path because KySec trust is hash-bound: ${BINARY}"
    fi
    local output_parent
    output_parent="$(dirname -- "${BINARY}")"
    if [[ ! -d "${output_parent}" || ! -w "${output_parent}" ]]; then
        fail "binary_output" "output parent is missing or not writable: ${output_parent}"
    fi

    BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/d2-vector-smoke.XXXXXX")"
    local sdk_copy="${BUILD_DIR}/sdk"
    local temp_binary="${BUILD_DIR}/d2_vector_smoke"

    git clone --quiet --no-hardlinks "${SDK_SOURCE}" "${sdk_copy}"
    git -C "${sdk_copy}" checkout --quiet "${EXPECTED_SDK_COMMIT}"
    git -C "${sdk_copy}" apply --unidiff-zero --check "${ABI_PATCH}"
    git -C "${sdk_copy}" apply --unidiff-zero "${ABI_PATCH}"
    git -C "${sdk_copy}" diff --check
    pass "sdk_compatibility" \
        "clean clone patched for installed 0k0.7 ABI; source=${EXPECTED_SDK_COMMIT}"

    local include_dir="${sdk_copy}/include/kysdk-vector-engine-client"
    if ! nice -n 10 g++ \
        -std=c++17 \
        -Wall \
        -Wextra \
        -Wpedantic \
        -Werror \
        -include "${ABI_ASSERTS}" \
        "${PROBE_SOURCE}" \
        -o "${temp_binary}" \
        -isystem "${include_dir}" \
        "${RUNTIME_LIBRARY}"; then
        fail "probe_build" "g++ failed to build the D2 Vector Engine probe"
    fi

    install -m 0755 "${temp_binary}" "${BINARY}"
    local binary_hash
    binary_hash="$(sha256sum "${BINARY}" | awk '{print $1}')"
    pass "probe_build" \
        "binary=${BINARY}; sha256=${binary_hash}; trust must be granted separately"
}

check_binary_trust() {
    require_command sha256sum
    if [[ ! -f "${BINARY}" || ! -x "${BINARY}" ]]; then
        fail "binary" "missing or non-executable probe: ${BINARY}"
    fi
    if [[ ! -x /usr/sbin/kyexectl ]]; then
        fail "kysec" "/usr/sbin/kyexectl is missing or non-executable"
    fi

    local trust_state
    trust_state="$(/usr/sbin/kyexectl -g "${BINARY}")"
    if [[ "${trust_state}" != *": verified" ]]; then
        fail "kysec" "probe is not temporarily trusted: ${trust_state}"
    fi
    BINARY_HASH="$(sha256sum "${BINARY}" | awk '{print $1}')"
    pass "binary" "path=${BINARY}; sha256=${BINARY_HASH}; kysec=verified"
}

check_database_path() {
    require_command realpath
    require_command stat
    if [[ ! -f "${DB_FILE}" || ! -r "${DB_FILE}" ]]; then
        fail "database_path" \
            "service-managed database is missing or unreadable: ${DB_FILE}"
    fi
    if [[ -L "${DB_FILE}" ]]; then
        fail "database_path" "database path must not be a symbolic link: ${DB_FILE}"
    fi
    if [[ ! -d "${TEST_ROOT}" ]]; then
        fail "database_path" "approved D2 test root is missing: ${TEST_ROOT}"
    fi
    if [[ -L "${TEST_ROOT}" ]]; then
        fail "database_path" "approved D2 test root must not be a symbolic link: ${TEST_ROOT}"
    fi

    TEST_ROOT_CANONICAL="$(realpath -e -- "${TEST_ROOT}")"
    DATABASE_CANONICAL="$(realpath -e -- "${DB_FILE}")"
    if [[ "${TEST_ROOT_CANONICAL}" != "${TEST_ROOT}" ]]; then
        fail "database_path" \
            "approved D2 test root must already be canonical: ${TEST_ROOT}"
    fi
    if [[ "${DATABASE_CANONICAL}" != "${DB_FILE}" ]]; then
        fail "database_path" \
            "database path must already be canonical: ${DB_FILE}; canonical=${DATABASE_CANONICAL}"
    fi
    case "${DATABASE_CANONICAL}" in
        "${TEST_ROOT_CANONICAL}"/*)
            ;;
        *)
            fail "database_path" \
                "database is outside approved D2 test root: ${TEST_ROOT_CANONICAL}"
            ;;
    esac

    DATABASE_IDENTITY="$(stat -Lc '%d:%i' -- "${DATABASE_CANONICAL}")"
    local default_database="${HOME}/${DEFAULT_DATABASE_RELATIVE}"
    if [[ -e "${default_database}" ]]; then
        local default_canonical
        local default_identity
        default_canonical="$(realpath -e -- "${default_database}")"
        default_identity="$(stat -Lc '%d:%i' -- "${default_canonical}")"
        if [[ "${DATABASE_CANONICAL}" == "${default_canonical}" ||
              "${DATABASE_IDENTITY}" == "${default_identity}" ]]; then
            fail "database_path" \
                "refusing the default Vector Engine database by path or file identity"
        fi
    fi

    DB_FILE="${DATABASE_CANONICAL}"
    MANIFEST_FILE="${TEST_ROOT_CANONICAL}/${MANIFEST_NAME}"
    pass "database_path" \
        "canonical=${DATABASE_CANONICAL}; identity=${DATABASE_IDENTITY}; approved_root=${TEST_ROOT_CANONICAL}; default_db_rejected=true"
}

write_manifest() {
    require_command chmod
    require_command ln
    require_command mktemp
    if [[ -e "${MANIFEST_FILE}" || -L "${MANIFEST_FILE}" ]]; then
        fail "manifest_write" \
            "refusing to overwrite an existing run manifest: ${MANIFEST_FILE}"
    fi

    MANIFEST_TEMP="$(mktemp "${TEST_ROOT_CANONICAL}/.d2-vector-smoke.manifest.XXXXXX")"
    chmod 0600 "${MANIFEST_TEMP}"
    {
        printf 'format_version=1\n'
        printf 'run_id=%s\n' "${RUN_ID}"
        printf 'database_path=%s\n' "${DATABASE_CANONICAL}"
        printf 'database_identity=%s\n' "${DATABASE_IDENTITY}"
        printf 'collection=%s\n' "${COLLECTION}"
        printf 'app_id=%s\n' "${APP_ID}"
        printf 'binary_sha256=%s\n' "${BINARY_HASH}"
        printf 'project_commit=%s\n' "${PROJECT_COMMIT}"
        printf 'probe_source_sha256=%s\n' "${PROBE_SOURCE_HASH}"
        printf 'runner_source_sha256=%s\n' "${RUNNER_SOURCE_HASH}"
        printf 'abi_patch_sha256=%s\n' "${ABI_PATCH_HASH}"
        printf 'abi_asserts_sha256=%s\n' "${ABI_ASSERTS_HASH}"
        printf 'sdk_source_commit=%s\n' "${EXPECTED_SDK_COMMIT}"
        printf 'service_unit=%s\n' "${SERVICE_UNIT}"
        printf 'prepare_invocation_id=%s\n' "${CURRENT_INVOCATION_ID}"
    } >"${MANIFEST_TEMP}"

    if ! ln -- "${MANIFEST_TEMP}" "${MANIFEST_FILE}"; then
        fail "manifest_write" \
            "atomic manifest creation failed; a competing file may exist"
    fi
    rm -- "${MANIFEST_TEMP}"
    MANIFEST_TEMP=""
    pass "manifest_write" \
        "path=${MANIFEST_FILE}; run_id=${RUN_ID}; project_commit=${PROJECT_COMMIT}; binary_sha256=${BINARY_HASH}; prepare_invocation_id=${CURRENT_INVOCATION_ID}"
}

MANIFEST_VALUE=""

read_manifest_value() {
    local key="$1"
    local -a matches=()
    mapfile -t matches < <(awk -v prefix="${key}=" \
        'index($0, prefix) == 1 { print substr($0, length(prefix) + 1) }' \
        "${MANIFEST_FILE}")
    if [[ "${#matches[@]}" -ne 1 ]]; then
        fail "manifest_read" \
            "manifest key must occur exactly once: ${key}; count=${#matches[@]}"
    fi
    MANIFEST_VALUE="${matches[0]}"
}

expect_manifest_value() {
    local key="$1"
    local expected="$2"
    read_manifest_value "${key}"
    if [[ "${MANIFEST_VALUE}" != "${expected}" ]]; then
        fail "manifest_mismatch" \
            "key=${key}; expected=${expected}; actual=${MANIFEST_VALUE}"
    fi
}

validate_manifest() {
    require_command awk
    if [[ ! -f "${MANIFEST_FILE}" || ! -r "${MANIFEST_FILE}" ]]; then
        fail "manifest_read" "run manifest is missing or unreadable: ${MANIFEST_FILE}"
    fi
    if [[ -L "${MANIFEST_FILE}" ]]; then
        fail "manifest_read" "run manifest must not be a symbolic link: ${MANIFEST_FILE}"
    fi

    expect_manifest_value "format_version" "1"
    expect_manifest_value "run_id" "${RUN_ID}"
    expect_manifest_value "database_path" "${DATABASE_CANONICAL}"
    expect_manifest_value "database_identity" "${DATABASE_IDENTITY}"
    expect_manifest_value "collection" "${COLLECTION}"
    expect_manifest_value "app_id" "${APP_ID}"
    expect_manifest_value "binary_sha256" "${BINARY_HASH}"
    expect_manifest_value "project_commit" "${PROJECT_COMMIT}"
    expect_manifest_value "probe_source_sha256" "${PROBE_SOURCE_HASH}"
    expect_manifest_value "runner_source_sha256" "${RUNNER_SOURCE_HASH}"
    expect_manifest_value "abi_patch_sha256" "${ABI_PATCH_HASH}"
    expect_manifest_value "abi_asserts_sha256" "${ABI_ASSERTS_HASH}"
    expect_manifest_value "sdk_source_commit" "${EXPECTED_SDK_COMMIT}"
    expect_manifest_value "service_unit" "${SERVICE_UNIT}"

    read_manifest_value "prepare_invocation_id"
    if [[ ! "${MANIFEST_VALUE}" =~ ^[[:xdigit:]]{32}$ ]]; then
        fail "manifest_mismatch" "prepare_invocation_id is not 32 hexadecimal characters"
    fi
    MANIFEST_PREPARE_INVOCATION_ID="${MANIFEST_VALUE}"
    pass "manifest_validate" \
        "phase=${PHASE}; path=${MANIFEST_FILE}; all identity fields match; prepare_invocation_id=${MANIFEST_PREPARE_INVOCATION_ID}"
}

check_service_database() {
    local main_pid
    local process_pid
    local argument
    local engine_seen
    local database_seen
    local -a process_pids=()
    local -a process_args=()

    main_pid="$(
        systemctl --user show "${SERVICE_UNIT}" --property=MainPID --value
    )"
    if [[ ! "${main_pid}" =~ ^[1-9][0-9]*$ ]]; then
        fail "service_database" "service returned invalid MainPID: ${main_pid}"
    fi

    process_pids=("${main_pid}")
    if [[ -r "/proc/${main_pid}/task/${main_pid}/children" ]]; then
        for process_pid in $(<"/proc/${main_pid}/task/${main_pid}/children"); do
            process_pids+=("${process_pid}")
        done
    fi

    for process_pid in "${process_pids[@]}"; do
        if [[ ! -r "/proc/${process_pid}/cmdline" ]]; then
            continue
        fi
        process_args=()
        while IFS= read -r -d '' argument; do
            process_args+=("${argument}")
        done <"/proc/${process_pid}/cmdline"
        engine_seen=false
        database_seen=false
        for argument in "${process_args[@]}"; do
            if [[ "${argument##*/}" == "kylin-ai-vector-engine" ]]; then
                engine_seen=true
            fi
            if [[ "${argument}" == "${DB_FILE}" ]]; then
                database_seen=true
            fi
        done
        if [[ "${engine_seen}" == true && "${database_seen}" == true ]]; then
            pass "service_database" \
                "engine_pid=${process_pid}; preloaded_db=${DB_FILE}"
            return
        fi
    done

    fail "service_database" \
        "no engine process for ${SERVICE_UNIT} holds ${DB_FILE}"
}

check_service() {
    require_command systemctl
    local load_state
    local active_state
    local sub_state

    if ! systemctl --user show "${SERVICE_UNIT}" --no-pager >/dev/null 2>&1; then
        fail "service_status" \
            "${SERVICE_UNIT} is unavailable in the current user systemd session"
    fi
    load_state="$(systemctl --user show "${SERVICE_UNIT}" --property=LoadState --value)"
    active_state="$(systemctl --user show "${SERVICE_UNIT}" --property=ActiveState --value)"
    sub_state="$(systemctl --user show "${SERVICE_UNIT}" --property=SubState --value)"
    CURRENT_INVOCATION_ID="$(
        systemctl --user show "${SERVICE_UNIT}" --property=InvocationID --value
    )"

    if [[ "${load_state}" != "loaded" || "${active_state}" != "active" ]]; then
        fail "service_status" \
            "unit=${SERVICE_UNIT}; load=${load_state}; active=${active_state}; sub=${sub_state}"
    fi
    if [[ ! "${CURRENT_INVOCATION_ID}" =~ ^[[:xdigit:]]{32}$ ]]; then
        fail "service_status" "service returned invalid InvocationID"
    fi
    pass "service_status" \
        "unit=${SERVICE_UNIT}; active=${active_state}; sub=${sub_state}; invocation_id=${CURRENT_INVOCATION_ID}"
    check_service_database

    if [[ "${PHASE}" == "verify" ]]; then
        if [[ "${CURRENT_INVOCATION_ID,,}" == "${MANIFEST_PREPARE_INVOCATION_ID,,}" ]]; then
            fail "service_restart" \
                "InvocationID is unchanged; restart ${SERVICE_UNIT} before verify"
        fi
        pass "service_restart" \
            "InvocationID changed from ${MANIFEST_PREPARE_INVOCATION_ID} to ${CURRENT_INVOCATION_ID}"
    fi
}

run_probe() {
    local -a arguments=(
        --phase "${PHASE}"
        --run-id "${RUN_ID}"
        --db-file "${DB_FILE}"
        --app-id "${APP_ID}"
        --collection "${COLLECTION}"
        --service-managed-database
    )

    log "probe_execute" "INFO" \
        "phase=${PHASE}; collection=${COLLECTION}; db_file=${DB_FILE}; app_id=${APP_ID}"
    if ! "${BINARY}" "${arguments[@]}"; then
        fail "probe_execute" "probe phase ${PHASE} failed"
    fi
    pass "probe_execute" "probe phase ${PHASE} completed successfully"

    if [[ "${PHASE}" == "prepare" ]]; then
        log "restart_token" "INFO" "invocation_id=${CURRENT_INVOCATION_ID}"
        log "manual_restart_required" "INFO" \
            "restart ${SERVICE_UNIT}; verify will read the prepare InvocationID from ${MANIFEST_FILE}"
    fi
}

main() {
    parse_arguments "$@"
    trap cleanup_temporary_files EXIT

    log "runner_start" "INFO" "action=${ACTION}; project_root=${PROJECT_ROOT}"
    check_operating_system
    check_project_inputs
    check_runtime_packages

    if [[ "${ACTION}" == "build" ]]; then
        build_probe
        pass "runner_complete" \
            "build completed; no trust, service, database, or evidence state changed"
        return
    fi

    check_binary_trust
    check_database_path
    if [[ "${PHASE}" == "prepare" ]]; then
        if [[ -e "${MANIFEST_FILE}" || -L "${MANIFEST_FILE}" ]]; then
            fail "manifest_precondition" \
                "prepare requires an unused manifest path: ${MANIFEST_FILE}"
        fi
        pass "manifest_precondition" "manifest path is unused: ${MANIFEST_FILE}"
    else
        validate_manifest
    fi
    check_service
    if [[ "${PHASE}" == "prepare" ]]; then
        write_manifest
    fi
    run_probe
    pass "runner_complete" \
        "run completed; no trust, service restart, or evidence upload was performed"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
