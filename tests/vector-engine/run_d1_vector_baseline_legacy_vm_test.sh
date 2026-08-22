#!/usr/bin/env bash
set -euo pipefail

# Host-only regression for the Kylin V11 0k0.7 client/runtime combination.
# It intentionally exercises the public D1 runner CLI instead of sourcing its
# private shell functions. Service restart and persistence verification remain
# separate human-controlled phases.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly PROJECT_ROOT

: "${D1_VECTOR_SDK_SOURCE:?set D1_VECTOR_SDK_SOURCE to the pinned official SDK checkout}"
: "${D1_VECTOR_DB_FILE:?set D1_VECTOR_DB_FILE to the service-managed database path}"
: "${D1_VECTOR_COLLECTION:=d1_legacy_vm_regression}"

if [[ "${KYLIN_L2:-}" != "1" ]]; then
    printf 'SKIP: KYLIN_L2=1 is required for the Kylin host regression\n'
    exit 77
fi

runner=(
    "${PROJECT_ROOT}/scripts/run_d1_vector_baseline.sh"
    --db-file "${D1_VECTOR_DB_FILE}"
    --collection "${D1_VECTOR_COLLECTION}"
    --sdk-source "${D1_VECTOR_SDK_SOURCE}"
    --service-managed-database
)
output="$(mktemp "${TMPDIR:-/tmp}/d1-legacy-vm-regression.XXXXXX")"

test_rc=0
cleanup_rc=0
"${runner[@]}" --phase prepare | tee "${output}" || test_rc=$?

if [[ "${test_rc}" -eq 0 ]]; then
    grep -F 'D1_VECTOR_BASELINE step=score_semantics result=PASS' "${output}" || test_rc=$?
fi

"${runner[@]}" --phase cleanup || cleanup_rc=$?
rm -f "${output}"

if [[ "${test_rc}" -ne 0 ]]; then
    exit "${test_rc}"
fi
exit "${cleanup_rc}"
