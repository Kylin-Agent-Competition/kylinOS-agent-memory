#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../../scripts/run_d2_vector_smoke.sh
source "${PROJECT_ROOT}/scripts/run_d2_vector_smoke.sh"

TEST_TEMP="$(mktemp -d "${TMPDIR:-/tmp}/d2-vector-safety.XXXXXX")"
TEST_TEMP="$(realpath -e "${TEST_TEMP}")"
trap 'rm -rf -- "${TEST_TEMP}"' EXIT

TESTS_PASSED=0

pass_test() {
    printf 'D2_VECTOR_SAFETY_TEST name=%s result=PASS\n' "$1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

expect_success() {
    local name="$1"
    shift
    if ("$@" >/dev/null 2>&1); then
        pass_test "${name}"
        return
    fi
    printf 'D2_VECTOR_SAFETY_TEST name=%s result=FAIL expected=success\n' "${name}" >&2
    exit 1
}

expect_failure() {
    local name="$1"
    shift
    if ("$@" >/dev/null 2>&1); then
        printf 'D2_VECTOR_SAFETY_TEST name=%s result=FAIL expected=failure\n' "${name}" >&2
        exit 1
    fi
    pass_test "${name}"
}

reset_run_contract() {
    RUN_ID="abc123"
    COLLECTION="d2_vector_smoke_${RUN_ID}"
    APP_ID="d2-vector-smoke"
    SERVICE_UNIT="d2-vector-engine.service"
    TEST_ROOT="${HOME}/d2-b-vector-smoke-${RUN_ID}"
    TEST_ROOT_CANONICAL=""
    MANIFEST_FILE="${TEST_ROOT}/${MANIFEST_NAME}"
    MANIFEST_TEMP=""
    MANIFEST_HASH=""
    MANIFEST_CREATED_AT_UTC=""
    MANIFEST_CLEANUP_TOKEN=""
    CLEANUP_LOCK_FILE="${TEST_ROOT}/.d2-vector-smoke.cleanup.lock"
    CLEANUP_LOCK_TEMP=""
    CLEANUP_LOCK_FD=""
    CLEANUP_LOCK_HELD=false
    SERVICE_ENGINE_PID=""
    DATABASE_CANONICAL=""
    DATABASE_IDENTITY=""
    DATABASE_DEVICE=""
    DATABASE_INODE=""
    DATABASE_SIZE_AT_RESERVATION=""
    DATABASE_SHA256_AT_RESERVATION=""
}

run_database_check() {
    reset_run_contract
    DB_FILE="$1"
    check_database_path
}

run_argument_check() {
    ACTION=""
    PHASE=""
    DB_FILE=""
    RUN_ID=""
    COLLECTION=""
    SDK_SOURCE=""
    BINARY=""
    APP_ID="${DEFAULT_APP_ID}"
    SERVICE_UNIT="${DEFAULT_SERVICE_UNIT}"
    parse_arguments "$@"
}

HOME="${TEST_TEMP}/home"
export HOME
mkdir -p "${HOME}/d2-b-vector-smoke-abc123"
mkdir -p "${HOME}/.local/share/kylin-ai-vector-engine"

VALID_DB="${HOME}/d2-b-vector-smoke-abc123/runtime.db"
OUTSIDE_DB="${HOME}/outside.db"
DEFAULT_DB="${HOME}/${DEFAULT_DATABASE_RELATIVE}"
DEFAULT_ALIAS="${HOME}/d2-b-vector-smoke-abc123/default-hardlink.db"
SYMLINK_DB="${HOME}/d2-b-vector-smoke-abc123/symlink.db"
printf 'valid\n' >"${VALID_DB}"
printf 'outside\n' >"${OUTSIDE_DB}"
printf 'default\n' >"${DEFAULT_DB}"
ln "${DEFAULT_DB}" "${DEFAULT_ALIAS}"
ln -s "${VALID_DB}" "${SYMLINK_DB}"

CLEANUP_AUTH_HELPER="${TEST_TEMP}/d2_cleanup_manifest_test"
CLEANUP_RUNTIME_HELPER="${TEST_TEMP}/d2_cleanup_runtime_test"
CXX="${CXX:-g++}"
if ! command -v "${CXX}" >/dev/null 2>&1; then
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_authorization_helper_build result=FAIL reason=compiler_missing\n' >&2
    exit 1
fi
"${CXX}" \
    -std=c++17 \
    -Wall \
    -Wextra \
    -Wpedantic \
    -Werror \
    "${PROJECT_ROOT}/tests/vector-engine/d2_cleanup_manifest_test.cpp" \
    -o "${CLEANUP_AUTH_HELPER}"
pass_test "cleanup_authorization_helper_build"
"${CXX}" \
    -std=c++17 \
    -Wall \
    -Wextra \
    -Wpedantic \
    -Werror \
    "${PROJECT_ROOT}/tests/vector-engine/d2_cleanup_runtime_test.cpp" \
    -o "${CLEANUP_RUNTIME_HELPER}"
pass_test "cleanup_runtime_identity_helper_build"

AUTHORIZATION_LINE="$(
    grep -n 'D2Cleanup::ValidateManifest' \
        "${PROJECT_ROOT}/tests/vector-engine/d2_vector_smoke.cpp" | cut -d: -f1
)"
RUNTIME_IDENTITY_LINE="$(
    grep -n 'D2Cleanup::ValidateRuntimeIdentity' \
        "${PROJECT_ROOT}/tests/vector-engine/d2_vector_smoke.cpp" | cut -d: -f1
)"
CLIENT_CREATE_LINE="$(
    grep -n 'VectorDB::Database::Create' \
        "${PROJECT_ROOT}/tests/vector-engine/d2_vector_smoke.cpp" | head -n 1 | cut -d: -f1
)"
if [[ "${AUTHORIZATION_LINE}" =~ ^[0-9]+$ &&
      "${RUNTIME_IDENTITY_LINE}" =~ ^[0-9]+$ &&
      "${CLIENT_CREATE_LINE}" =~ ^[0-9]+$ &&
      "${AUTHORIZATION_LINE}" -lt "${RUNTIME_IDENTITY_LINE}" &&
      "${RUNTIME_IDENTITY_LINE}" -lt "${CLIENT_CREATE_LINE}" ]]; then
    pass_test "cleanup_authorization_precedes_client_creation"
else
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_authorization_precedes_client_creation result=FAIL\n' >&2
    exit 1
fi
PRE_DROP_RUNTIME_LINE="$(
    grep -n 'const auto runtime_identity = ValidateCleanupRuntimeIdentity(options);' \
        "${PROJECT_ROOT}/tests/vector-engine/d2_vector_smoke.cpp" |
        head -n 1 | cut -d: -f1
)"
DROP_COLLECTION_LINE="$(
    grep -n 'client->DropCollection(options.collection)' \
        "${PROJECT_ROOT}/tests/vector-engine/d2_vector_smoke.cpp" |
        cut -d: -f1
)"
if [[ "${PRE_DROP_RUNTIME_LINE}" =~ ^[0-9]+$ &&
      "${DROP_COLLECTION_LINE}" =~ ^[0-9]+$ &&
      "${PRE_DROP_RUNTIME_LINE}" -lt "${DROP_COLLECTION_LINE}" ]]; then
    pass_test "cleanup_runtime_identity_revalidated_before_drop"
else
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_runtime_identity_revalidated_before_drop result=FAIL\n' >&2
    exit 1
fi

expect_success "database_valid_under_approved_root" run_database_check "${VALID_DB}"
expect_failure "database_rejects_outside_root" run_database_check "${OUTSIDE_DB}"
if [[ -L "${SYMLINK_DB}" ]]; then
    expect_failure "database_rejects_symlink" run_database_check "${SYMLINK_DB}"
else
    printf 'D2_VECTOR_SAFETY_TEST name=database_rejects_symlink result=SKIP reason=host_did_not_create_symlink\n'
fi
expect_failure "database_rejects_default_file_identity" run_database_check "${DEFAULT_ALIAS}"
expect_failure "database_rejects_relative_path" run_argument_check \
    --action run --phase prepare --run-id abc123 --db-file relative.db \
    --binary /tmp/probe

expect_success "collection_derives_from_run_id" run_argument_check \
    --action run --phase prepare --run-id abc123 --db-file /tmp/db \
    --binary /tmp/probe
expect_failure "collection_rejects_non_d2_name" run_argument_check \
    --action run --phase prepare --run-id abc123 --db-file /tmp/db \
    --binary /tmp/probe --collection unrelated
expect_failure "run_id_rejects_uppercase" run_argument_check \
    --action run --phase prepare --run-id ABC123 --db-file /tmp/db \
    --binary /tmp/probe
expect_success "verify_cleanup_phase_is_read_only_entrypoint" run_argument_check \
    --action run --phase verify-cleanup --run-id abc123 --db-file /tmp/db \
    --binary /tmp/probe

reset_run_contract
DB_FILE="${VALID_DB}"
check_database_path >/dev/null
BINARY_HASH="$(printf '1%.0s' {1..64})"
PROJECT_COMMIT="$(printf '2%.0s' {1..40})"
PROBE_SOURCE_HASH="$(printf '3%.0s' {1..64})"
RUNNER_SOURCE_HASH="$(printf '4%.0s' {1..64})"
ABI_PATCH_HASH="$(printf '5%.0s' {1..64})"
ABI_ASSERTS_HASH="$(printf '6%.0s' {1..64})"
CURRENT_INVOCATION_ID="$(printf '7%.0s' {1..32})"
PHASE="prepare"
expect_failure "manifest_rejects_missing" validate_manifest "true"
write_manifest >/dev/null
PHASE="verify"
expect_failure "manifest_rejects_unowned_prepare" validate_manifest "true"
PHASE="prepare"
finalize_manifest_after_prepare >/dev/null
PHASE="verify"
expect_success "manifest_accepts_exact_identity" validate_manifest "true"
if [[ "${MANIFEST_HASH}" =~ ^[[:xdigit:]]{64}$ ]]; then
    pass_test "manifest_records_sha256"
else
    printf 'D2_VECTOR_SAFETY_TEST name=manifest_records_sha256 result=FAIL\n' >&2
    exit 1
fi
ORIGINAL_BINARY_HASH="${BINARY_HASH}"
BINARY_HASH="$(printf '8%.0s' {1..64})"
expect_failure "manifest_rejects_binary_hash_mismatch" validate_manifest "true"
BINARY_HASH="${ORIGINAL_BINARY_HASH}"
PROJECT_COMMIT="$(printf '9%.0s' {1..40})"
expect_failure "manifest_rejects_project_commit_mismatch" validate_manifest "true"
PROJECT_COMMIT="$(printf '2%.0s' {1..40})"

ORIGINAL_DB="${TEST_TEMP}/original-runtime.db"
mv -- "${VALID_DB}" "${ORIGINAL_DB}"
printf 'replacement\n' >"${VALID_DB}"
check_database_path >/dev/null
expect_failure "manifest_rejects_replaced_database" validate_manifest "true"
rm -- "${VALID_DB}"
mv -- "${ORIGINAL_DB}" "${VALID_DB}"
check_database_path >/dev/null

CURRENT_INVOCATION_ID="$(printf '8%.0s' {1..32})"
PHASE="verify"
finalize_manifest_after_verify >/dev/null
expect_success "manifest_records_verified_state" \
    validate_manifest "true" "verified" "false"

PHASE="cleanup"
CLEANUP_LOCK_ENTRANTS="${TEST_TEMP}/cleanup-lock-entrants"
CLEANUP_LOCK_READY="${TEST_TEMP}/cleanup-lock-ready"
CLEANUP_LOCK_RELEASE="${TEST_TEMP}/cleanup-lock-release"
first_concurrent_cleanup() {
    acquire_cleanup_lock >/dev/null
    require_cleanup_lock_held
    printf 'first\n' >>"${CLEANUP_LOCK_ENTRANTS}"
    : >"${CLEANUP_LOCK_READY}"
    local attempts=0
    while [[ ! -e "${CLEANUP_LOCK_RELEASE}" && "${attempts}" -lt 200 ]]; do
        sleep 0.01
        attempts=$((attempts + 1))
    done
    if [[ ! -e "${CLEANUP_LOCK_RELEASE}" ]]; then
        return 1
    fi
    require_cleanup_lock_held
    release_cleanup_lock
}

(
    first_concurrent_cleanup
) >/dev/null 2>&1 &
FIRST_CLEANUP_PID=$!
for _ in {1..200}; do
    if [[ -e "${CLEANUP_LOCK_READY}" ]]; then
        break
    fi
    sleep 0.01
done
if [[ ! -e "${CLEANUP_LOCK_READY}" ]]; then
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_lock_first_process_ready result=FAIL\n' >&2
    exit 1
fi
pass_test "cleanup_lock_first_process_ready"

(
    acquire_cleanup_lock >/dev/null
    require_cleanup_lock_held
    printf 'second\n' >>"${CLEANUP_LOCK_ENTRANTS}"
    release_cleanup_lock
) >/dev/null 2>&1 &
SECOND_CLEANUP_PID=$!
if wait "${SECOND_CLEANUP_PID}"; then
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_lock_rejects_concurrent_process result=FAIL\n' >&2
    exit 1
fi
pass_test "cleanup_lock_rejects_concurrent_process"
: >"${CLEANUP_LOCK_RELEASE}"
if ! wait "${FIRST_CLEANUP_PID}"; then
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_lock_first_process_completes result=FAIL\n' >&2
    exit 1
fi
pass_test "cleanup_lock_first_process_completes"
if [[ "$(wc -l <"${CLEANUP_LOCK_ENTRANTS}")" -eq 1 &&
      "$(<"${CLEANUP_LOCK_ENTRANTS}")" == "first" ]]; then
    pass_test "cleanup_lock_allows_only_one_probe_entry"
else
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_lock_allows_only_one_probe_entry result=FAIL\n' >&2
    exit 1
fi

acquire_cleanup_lock >/dev/null
authorize_manifest_for_cleanup >/dev/null
LOCK_SCOPE_PROBE="${TEST_TEMP}/cleanup-lock-scope-probe"
LOCK_SCOPE_MARKER="${TEST_TEMP}/cleanup-lock-scope-marker"
cat >"${LOCK_SCOPE_PROBE}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ -e "/proc/self/fd/${D2_TEST_LOCK_FD}" ]]; then
    exit 1
fi
printf 'probe-entered\n' >"${D2_TEST_LOCK_SCOPE_MARKER}"
EOF
chmod 0755 "${LOCK_SCOPE_PROBE}"
ORIGINAL_BINARY_PATH="${BINARY}"
BINARY="${LOCK_SCOPE_PROBE}"
D2_TEST_LOCK_FD="${CLEANUP_LOCK_FD}"
D2_TEST_LOCK_SCOPE_MARKER="${LOCK_SCOPE_MARKER}"
export D2_TEST_LOCK_FD D2_TEST_LOCK_SCOPE_MARKER
run_probe >/dev/null
require_cleanup_lock_held
BINARY="${ORIGINAL_BINARY_PATH}"
unset D2_TEST_LOCK_FD D2_TEST_LOCK_SCOPE_MARKER
if [[ "$(<"${LOCK_SCOPE_MARKER}")" == "probe-entered" ]]; then
    pass_test "cleanup_lock_spans_probe_without_child_fd_leak"
else
    printf 'D2_VECTOR_SAFETY_TEST name=cleanup_lock_spans_probe_without_child_fd_leak result=FAIL\n' >&2
    exit 1
fi
expect_success "cleanup_authorization_accepts_claimed_manifest" \
    "${CLEANUP_AUTH_HELPER}" \
    "${MANIFEST_FILE}" \
    "${MANIFEST_CLEANUP_TOKEN}" \
    "${CURRENT_INVOCATION_ID}" \
    "${RUN_ID}" \
    "${COLLECTION}" \
    "${APP_ID}" \
    "${DB_FILE}"

RUNTIME_PROC_ROOT="${TEST_TEMP}/runtime-proc"
RUNTIME_SYSTEMCTL="${TEST_TEMP}/runtime-systemctl"
RUNTIME_SHA256SUM="${TEST_TEMP}/runtime-sha256sum"
RUNTIME_SELF_EXE="${TEST_TEMP}/runtime-probe-image"
RUNTIME_SOCKET="${TEST_TEMP}/kylin-ai-vector-engine.sock"
RUNTIME_MAIN_PID=4242
RUNTIME_ENGINE_PID=4243
RUNTIME_SOCKET_INODE=98765

mkdir -p \
    "${RUNTIME_PROC_ROOT}/net" \
    "${RUNTIME_PROC_ROOT}/${RUNTIME_MAIN_PID}/task/${RUNTIME_MAIN_PID}" \
    "${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/task/${RUNTIME_ENGINE_PID}" \
    "${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/fd"
printf '%s\n' "${RUNTIME_ENGINE_PID}" \
    >"${RUNTIME_PROC_ROOT}/${RUNTIME_MAIN_PID}/task/${RUNTIME_MAIN_PID}/children"
: >"${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/task/${RUNTIME_ENGINE_PID}/children"
printf '/usr/bin/bash\0' \
    >"${RUNTIME_PROC_ROOT}/${RUNTIME_MAIN_PID}/cmdline"
write_runtime_engine_cmdline() {
    local database="$1"
    printf '/usr/bin/kylin-ai-vector-engine\0--database\0%s\0' "${database}" \
        >"${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/cmdline"
}
write_runtime_socket_table() {
    printf 'Num RefCount Protocol Flags Type St Inode Path\n' \
        >"${RUNTIME_PROC_ROOT}/net/unix"
    printf '00000000: 00000002 00000000 00010000 0001 01 %s %s\n' \
        "${RUNTIME_SOCKET_INODE}" "${RUNTIME_SOCKET}" \
        >>"${RUNTIME_PROC_ROOT}/net/unix"
}
write_runtime_systemctl() {
    local invocation_id="$1"
    local active_state="${2:-active}"
    cat >"${RUNTIME_SYSTEMCTL}" <<EOF
#!/usr/bin/env bash
printf 'LoadState=loaded\nActiveState=${active_state}\nInvocationID=${invocation_id}\nMainPID=${RUNTIME_MAIN_PID}\n'
EOF
    chmod 0755 "${RUNTIME_SYSTEMCTL}"
}
write_runtime_sha256sum() {
    local executable_hash="$1"
    cat >"${RUNTIME_SHA256SUM}" <<EOF
#!/usr/bin/env bash
printf '${executable_hash}  %s\n' "\$1"
EOF
    chmod 0755 "${RUNTIME_SHA256SUM}"
}
run_runtime_identity_check() {
    "${CLEANUP_RUNTIME_HELPER}" \
        "${MANIFEST_FILE}" \
        "${MANIFEST_CLEANUP_TOKEN}" \
        "${CURRENT_INVOCATION_ID}" \
        "${RUN_ID}" \
        "${COLLECTION}" \
        "${APP_ID}" \
        "${DB_FILE}" \
        "${RUNTIME_PROC_ROOT}" \
        "${RUNTIME_SYSTEMCTL}" \
        "${RUNTIME_SHA256SUM}" \
        "${RUNTIME_SELF_EXE}" \
        "${RUNTIME_SOCKET}"
}

printf 'runtime-probe-image\n' >"${RUNTIME_SELF_EXE}"
chmod 0755 "${RUNTIME_SELF_EXE}"
write_runtime_engine_cmdline "${DB_FILE}"
write_runtime_socket_table
ln -s "socket:[${RUNTIME_SOCKET_INODE}]" \
    "${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/fd/9"
write_runtime_systemctl "${CURRENT_INVOCATION_ID}"
write_runtime_sha256sum "${BINARY_HASH}"
expect_success "cleanup_runtime_identity_accepts_live_process" \
    run_runtime_identity_check

write_runtime_sha256sum "$(printf '9%.0s' {1..64})"
expect_failure "cleanup_runtime_identity_rejects_actual_binary_hash" \
    run_runtime_identity_check
write_runtime_sha256sum "${BINARY_HASH}"

write_runtime_systemctl "$(printf '9%.0s' {1..32})"
expect_failure "cleanup_runtime_identity_rejects_actual_invocation_id" \
    run_runtime_identity_check
write_runtime_systemctl "${CURRENT_INVOCATION_ID}"

write_runtime_systemctl "${CURRENT_INVOCATION_ID}" "inactive"
expect_failure "cleanup_runtime_identity_rejects_inactive_service" \
    run_runtime_identity_check
write_runtime_systemctl "${CURRENT_INVOCATION_ID}"

write_runtime_engine_cmdline "${OUTSIDE_DB}"
expect_failure "cleanup_runtime_identity_rejects_engine_database" \
    run_runtime_identity_check
write_runtime_engine_cmdline "${DB_FILE}"

rm -- "${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/fd/9"
ln -s 'socket:[12345]' \
    "${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/fd/9"
expect_failure "cleanup_runtime_identity_rejects_socket_owner" \
    run_runtime_identity_check
rm -- "${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/fd/9"
ln -s "socket:[${RUNTIME_SOCKET_INODE}]" \
    "${RUNTIME_PROC_ROOT}/${RUNTIME_ENGINE_PID}/fd/9"

expect_failure "cleanup_authorization_rejects_missing_manifest" \
    "${CLEANUP_AUTH_HELPER}" \
    "" \
    "${MANIFEST_CLEANUP_TOKEN}" \
    "${CURRENT_INVOCATION_ID}" \
    "${RUN_ID}" \
    "${COLLECTION}" \
    "${APP_ID}" \
    "${DB_FILE}"
expect_failure "cleanup_authorization_rejects_wrong_token" \
    "${CLEANUP_AUTH_HELPER}" \
    "${MANIFEST_FILE}" \
    "$(printf 'a%.0s' {1..64})" \
    "${CURRENT_INVOCATION_ID}" \
    "${RUN_ID}" \
    "${COLLECTION}" \
    "${APP_ID}" \
    "${DB_FILE}"

COPIED_MANIFEST="${TEST_TEMP}/copied-cleanup.manifest"
cp -- "${MANIFEST_FILE}" "${COPIED_MANIFEST}"
chmod 0600 "${COPIED_MANIFEST}"
expect_failure "cleanup_authorization_rejects_copied_manifest_path" \
    "${CLEANUP_AUTH_HELPER}" \
    "${COPIED_MANIFEST}" \
    "${MANIFEST_CLEANUP_TOKEN}" \
    "${CURRENT_INVOCATION_ID}" \
    "${RUN_ID}" \
    "${COLLECTION}" \
    "${APP_ID}" \
    "${DB_FILE}"

REAL_MANIFEST="${TEST_TEMP}/real-cleanup.manifest"
mv -- "${MANIFEST_FILE}" "${REAL_MANIFEST}"
ln -s "${REAL_MANIFEST}" "${MANIFEST_FILE}"
expect_failure "cleanup_authorization_rejects_manifest_symlink" \
    "${CLEANUP_AUTH_HELPER}" \
    "${MANIFEST_FILE}" \
    "${MANIFEST_CLEANUP_TOKEN}" \
    "${CURRENT_INVOCATION_ID}" \
    "${RUN_ID}" \
    "${COLLECTION}" \
    "${APP_ID}" \
    "${DB_FILE}"
rm -- "${MANIFEST_FILE}"
mv -- "${REAL_MANIFEST}" "${MANIFEST_FILE}"

finalize_manifest_after_cleanup >/dev/null
release_cleanup_lock
expect_failure "cleanup_authorization_rejects_consumed_manifest" \
    "${CLEANUP_AUTH_HELPER}" \
    "${MANIFEST_FILE}" \
    "$(printf 'a%.0s' {1..64})" \
    "${CURRENT_INVOCATION_ID}" \
    "${RUN_ID}" \
    "${COLLECTION}" \
    "${APP_ID}" \
    "${DB_FILE}"
expect_success "manifest_records_cleaned_state" \
    validate_manifest "true" "cleaned" "true"
PHASE="verify-cleanup"
expect_success "cleaned_manifest_allows_read_only_verification" \
    validate_manifest "true" "cleaned" "true"
PHASE="cleanup"

PROBE_MARKER="${TEST_TEMP}/probe-executed"
STALE_COLLECTION_SENTINEL="${TEST_TEMP}/stale-collection-sentinel"
printf 'new-collection-data\n' >"${STALE_COLLECTION_SENTINEL}"
attempt_repeated_cleanup() {
    validate_manifest "true" "prepared|verified" "false"
    printf 'executed\n' >"${PROBE_MARKER}"
    printf 'modified\n' >"${STALE_COLLECTION_SENTINEL}"
}
expect_failure "manifest_rejects_repeated_cleanup_before_probe" \
    attempt_repeated_cleanup
if [[ ! -e "${PROBE_MARKER}" &&
      "$(<"${STALE_COLLECTION_SENTINEL}")" == "new-collection-data" ]]; then
    pass_test "stale_manifest_preserves_recreated_collection"
else
    printf 'D2_VECTOR_SAFETY_TEST name=stale_manifest_preserves_recreated_collection result=FAIL\n' >&2
    exit 1
fi

printf 'D2_VECTOR_SAFETY_TEST result=PASS tests=%d\n' "${TESTS_PASSED}"
