#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
VERIFIER="$PROJECT_ROOT/scripts/verify_a_day4_day5_vm.sh"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

fail() {
    printf 'A_DAY4_DAY5_VERIFIER_CONFIG_TEST result=FAIL detail=%s\n' "$1" >&2
    exit 1
}

default_output="$(cd "$TEMP_DIR" && bash "$VERIFIER" --print-config)" ||
    fail "default config command failed"

grep -F "repo_root=$PROJECT_ROOT" <<<"$default_output" >/dev/null ||
    fail "default repo root is not derived from the verifier location"
if grep -F '/mnt/shared' <<<"$default_output" >/dev/null; then
    fail "default config still depends on /mnt/shared"
fi
grep -F 'expected_sdk_version=1.2.0.0-0k0.4' <<<"$default_output" >/dev/null ||
    fail "documented SDK baseline is missing"

custom_repo="$TEMP_DIR/custom-source"
custom_venv="$TEMP_DIR/custom-venv"
custom_build="$TEMP_DIR/custom-build"
custom_evidence="$TEMP_DIR/custom-evidence"
custom_output="$(
    A_VM_REPO_ROOT="$custom_repo" \
    A_VM_VENV="$custom_venv" \
    A_VM_BUILD_DIR="$custom_build" \
    A_VM_EVIDENCE_DIR="$custom_evidence" \
        bash "$VERIFIER" --print-config
)" || fail "custom config command failed"

for expected in \
    "repo_root=$custom_repo" \
    "venv=$custom_venv" \
    "build_dir=$custom_build" \
    "evidence_dir=$custom_evidence"; do
    grep -F "$expected" <<<"$custom_output" >/dev/null ||
        fail "custom override missing: $expected"
done

printf 'A_DAY4_DAY5_VERIFIER_CONFIG_TEST result=PASS\n'
