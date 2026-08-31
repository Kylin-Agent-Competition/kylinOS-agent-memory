#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# D8-B L2 Vector knowledge metadata probe. The caller supplies a KySec-trusted
# vector_bridge_cli binary connected to the target Kylin Vector Engine service.

set -euo pipefail

binary=""
collection="d8b_knowledge_filter_l2_${RANDOM}_$$"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

fail() {
    printf 'D8B_L2 result=FAIL reason=%s\n' "$1" >&2
    exit 1
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
            printf '%s\n' 'Usage: run_d8b_knowledge_filter_l2.sh --binary /absolute/path/to/vector_bridge_cli [--collection d8b_*]'
            exit 0
            ;;
        *)
            fail "unknown_argument:$1"
            ;;
    esac
done

[[ -n "$binary" && "$binary" = /* && -x "$binary" ]] || fail "binary_must_be_an_executable_absolute_path"
[[ "$collection" =~ ^d8b_[A-Za-z0-9_]+$ ]] || fail "collection_must_use_d8b_prefix"

cleanup() {
    local status=$?
    trap - EXIT
    if "$binary" drop_collection "$collection" >/dev/null 2>&1; then
        printf 'D8B_L2 cleanup=PASS collection=%s\n' "$collection"
    else
        printf 'D8B_L2 cleanup=FAIL collection=%s\n' "$collection" >&2
    fi
    exit "$status"
}
trap cleanup EXIT

assert_hits() {
    local name="$1"
    local output="$2"
    local expected="$3"
    python3 -c '
import json, sys
name, output, expected = sys.argv[1:]
payload = json.loads(output)
if payload.get("ok") is not True:
    raise SystemExit(f"D8B_L2 name={name} result=FAIL payload={output}")
actual = [f"{item['"'"'id'"'"']}:{item['"'"'version_id'"'"']}" for item in payload.get("hits", [])]
wanted = [] if not expected else expected.split(",")
if actual != wanted:
    raise SystemExit(f"D8B_L2 name={name} result=FAIL expected={wanted} actual={actual}")
print(f"D8B_L2 name={name} result=PASS hits={actual}")
' "$name" "$output" "$expected"
}

printf 'D8B_L2_META tested_commit=%s\n' "$(git -C "$repo_root" rev-parse HEAD)"
printf 'D8B_L2_META bridge_sha256=%s\n' "$(sha256sum "$repo_root/tests/vector-engine/vector_bridge_cli.cpp" | awk '{print $1}')"

create_output="$("$binary" create_collection "$collection" 2)"
python3 -c 'import json,sys; assert json.loads(sys.argv[1]).get("ok") is True' "$create_output" || fail "create_collection"

insert_output="$({
    printf '%s\n' '{"ids":[201,202,203,204],"vectors":[[1.0,0.0],[0.9,0.1],[0.8,0.2],[0.7,0.3]],"user_ids":["user-a","user-a","user-a","user-a"],"version_ids":["v1","v2","v1","v1"],"scene_ids":["","","",""],"memory_statuses":["active","active","deprecated","active"],"deleted_flags":[false,false,false,false],"object_types":["knowledge","knowledge","knowledge","knowledge"],"knowledge_types":["workflow","fact","workflow","workflow"],"primary_categories":["operations","operations","development","operations"],"source_event_ids":["event-1","event-1","event-2","event-2"]}'
} | "$binary" insert "$collection")"
python3 -c 'import json,sys; assert json.loads(sys.argv[1]).get("ok") is True' "$insert_output" || fail "insert"

workflow_event_one="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":[],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true,"object_types":["knowledge"],"knowledge_types":["workflow"],"primary_categories":["operations"],"source_event_ids":["event-1"],"version_ids":["v1"]}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "type_category_source_version_status" "$workflow_event_one" "201:v1"

workflow_event_two="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":[],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true,"object_types":["knowledge"],"knowledge_types":["workflow"],"primary_categories":["operations"],"source_event_ids":["event-2"],"version_ids":["v1"]}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "source_separates_knowledge" "$workflow_event_two" "204:v1"

trap - EXIT
"$binary" drop_collection "$collection" >/dev/null || fail "cleanup_failed"
printf 'D8B_L2 result=PASS collection=%s cleanup=complete\n' "$collection"
