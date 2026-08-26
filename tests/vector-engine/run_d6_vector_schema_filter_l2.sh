#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# D6-B L2 Vector schema/filter probe.  The caller supplies a KySec-trusted
# vector_bridge_cli binary connected to the Kylin user Vector Engine service.

set -euo pipefail

binary=""
collection="d6b_schema_filter_l2_${RANDOM}_$$"

fail() {
    printf 'D6B_L2 result=FAIL reason=%s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: run_d6_vector_schema_filter_l2.sh --binary /absolute/path/to/vector_bridge_cli [--collection d6b_*]
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --binary)
            binary="${2:-}"
            shift 2
            ;;
        --collection)
            collection="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            fail "unknown_argument:$1"
            ;;
    esac
done

[[ -n "$binary" && "$binary" = /* && -x "$binary" ]] || fail "binary_must_be_an_executable_absolute_path"
[[ "$collection" =~ ^d6b_[A-Za-z0-9_]+$ ]] || fail "collection_must_use_d6b_prefix"

cleanup() {
    "$binary" drop_collection "$collection" >/dev/null 2>&1 || true
}
trap cleanup EXIT

assert_ok() {
    local name="$1"
    local output="$2"
    python3 -c '
import json, sys
name, output = sys.argv[1], sys.argv[2]
payload = json.loads(output)
if payload.get("ok") is not True:
    raise SystemExit(f"D6B_L2 name={name} result=FAIL payload={output}")
print(f"D6B_L2 name={name} result=PASS")
' "$name" "$output"
}

assert_hits() {
    local name="$1"
    local output="$2"
    local expected="$3"
    python3 -c '
import json, sys
name, output, expected = sys.argv[1:]
payload = json.loads(output)
if payload.get("ok") is not True:
    raise SystemExit(f"D6B_L2 name={name} result=FAIL payload={output}")
actual = ["{}:{}".format(hit["id"], hit["version_id"]) for hit in payload.get("hits", [])]
wanted = [] if not expected else expected.split(",")
if actual != wanted:
    raise SystemExit(f"D6B_L2 name={name} result=FAIL expected={wanted} actual={actual}")
print(f"D6B_L2 name={name} result=PASS hits={actual}")
' "$name" "$output" "$expected"
}

create_output="$("$binary" create_collection "$collection" 2)"
assert_ok "create_collection" "$create_output"

insert_output="$({
    printf '%s\n' '{"ids":[101,102,103,104,105,106],"vectors":[[1.0,0.0],[0.9,0.1],[1.0,0.0],[1.0,0.0],[0.8,0.2],[0.7,0.3]],"user_ids":["user-a","user-a","user-b","user-a","user-a","user-a"],"version_ids":["v1","v2","v3","v4","v5","v6"],"scene_ids":["lab","office","lab","lab","","lab"],"memory_statuses":["active","active","active","active","active","inactive"],"deleted_flags":[false,false,false,true,false,false]}'
} | "$binary" insert "$collection")"
assert_ok "insert_filterable_metadata" "$insert_output"

active_a_output="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":["lab"],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "user_scene_unscoped_status_deleted_filter" "$active_a_output" "101:v1,105:v5"

# 删除过滤是不可绕过的服务端门禁；伪造 false 不得暴露 104:v4。
deleted_bypass_output="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":["lab"],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":false}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "deleted_filter_fail_closed" "$deleted_bypass_output" "101:v1,105:v5"

active_b_output="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-b","allowed_scene_ids":["lab"],"include_unscoped":false,"allowed_memory_statuses":["active"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "cross_user_isolation" "$active_b_output" "103:v3"

inactive_output="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":["lab"],"include_unscoped":false,"allowed_memory_statuses":["inactive"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "lifecycle_status_filter" "$inactive_output" "106:v6"

set +e
invalid_output="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":""}}'
} | "$binary" search "$collection" 10 5000 2>&1)"
invalid_status=$?
set -e
[[ "$invalid_status" -ne 0 ]] || fail "empty_user_filter_must_fail"
python3 -c '
import json, sys
payload = json.loads(sys.argv[1])
if payload.get("ok") is not False or "user_id" not in payload.get("message", ""):
    raise SystemExit(f"D6B_L2 name=empty_user_filter result=FAIL payload={sys.argv[1]}")
print("D6B_L2 name=empty_user_filter result=PASS")
' "$invalid_output"

set +e
unknown_filter_output="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","unexpected_filter_key":true}}'
} | "$binary" search "$collection" 10 5000 2>&1)"
unknown_filter_status=$?
set -e
[[ "$unknown_filter_status" -ne 0 ]] || fail "unknown_filter_key_must_fail"
python3 -c '
import json, sys
payload = json.loads(sys.argv[1])
if payload.get("ok") is not False or "unknown filter" not in payload.get("message", ""):
    raise SystemExit(f"D6B_L2 name=unknown_filter_key_fail_closed result=FAIL payload={sys.argv[1]}")
print("D6B_L2 name=unknown_filter_key_fail_closed result=PASS")
' "$unknown_filter_output"

printf 'D6B_L2 result=PASS collection=%s cleanup=scheduled\n' "$collection"
