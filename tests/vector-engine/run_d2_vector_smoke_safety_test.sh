#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../../scripts/run_d2_vector_smoke.sh
source "${PROJECT_ROOT}/scripts/run_d2_vector_smoke.sh"

TEST_TEMP="$(mktemp -d "${TMPDIR:-/tmp}/d2-vector-safety.XXXXXX")"
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
    DATABASE_CANONICAL=""
    DATABASE_IDENTITY=""
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

expect_success "database_valid_under_approved_root" run_database_check "${VALID_DB}"
expect_failure "database_rejects_outside_root" run_database_check "${OUTSIDE_DB}"
if [[ -L "${SYMLINK_DB}" ]]; then
    expect_failure "database_rejects_symlink" run_database_check "${SYMLINK_DB}"
else
    printf 'D2_VECTOR_SAFETY_TEST name=database_rejects_symlink result=SKIP reason=host_did_not_create_symlink\n'
fi
expect_failure "database_rejects_default_file_identity" run_database_check "${DEFAULT_ALIAS}"

expect_success "collection_derives_from_run_id" run_argument_check \
    --action run --phase prepare --run-id abc123 --db-file /tmp/db \
    --binary /tmp/probe
expect_failure "collection_rejects_non_d2_name" run_argument_check \
    --action run --phase prepare --run-id abc123 --db-file /tmp/db \
    --binary /tmp/probe --collection unrelated
expect_failure "run_id_rejects_uppercase" run_argument_check \
    --action run --phase prepare --run-id ABC123 --db-file /tmp/db \
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
write_manifest >/dev/null
PHASE="verify"
expect_success "manifest_accepts_exact_identity" validate_manifest
ORIGINAL_BINARY_HASH="${BINARY_HASH}"
BINARY_HASH="$(printf '8%.0s' {1..64})"
expect_failure "manifest_rejects_binary_hash_mismatch" validate_manifest
BINARY_HASH="${ORIGINAL_BINARY_HASH}"
PROJECT_COMMIT="$(printf '9%.0s' {1..40})"
expect_failure "manifest_rejects_project_commit_mismatch" validate_manifest

printf 'D2_VECTOR_SAFETY_TEST result=PASS tests=%d\n' "${TESTS_PASSED}"
