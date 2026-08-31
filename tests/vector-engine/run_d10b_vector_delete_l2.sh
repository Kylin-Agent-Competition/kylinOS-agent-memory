#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# D10-B Vector 精确删除宿主验证。调用方提供已连接麒麟 Vector Engine 的
# 经 KySec 信任的 vector_bridge_cli 二进制；本脚本只创建并清理 d10b_ 前缀的
# 临时集合。

set -euo pipefail

binary=""
collection="d10b_delete_l2_${RANDOM}_$$"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
collection_created=0

fail() {
    printf 'D10B_L2 结果=失败 原因=%s\n' "$1" >&2
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
            printf '%s\n' '用法：run_d10b_vector_delete_l2.sh --binary /绝对路径/vector_bridge_cli [--collection d10b_*]'
            exit 0
            ;;
        *)
            fail "未知参数:$1"
            ;;
    esac
done

[[ -n "$binary" && "$binary" = /* && -x "$binary" ]] || fail "二进制必须为可执行的绝对路径"
[[ "$collection" =~ ^d10b_[A-Za-z0-9_]+$ ]] || fail "集合必须使用 d10b_ 前缀"

cleanup() {
    local status=$?
    trap - EXIT
    if [[ "$collection_created" -eq 0 ]]; then
        exit "$status"
    fi
    if "$binary" drop_collection "$collection" >/dev/null 2>&1; then
        printf 'D10B_L2 清理=通过 集合=%s\n' "$collection"
    else
        printf 'D10B_L2 清理=失败 集合=%s\n' "$collection" >&2
    fi
    exit "$status"
}
trap cleanup EXIT

assert_ok() {
    local name="$1"
    local output="$2"
    python3 -c '
import json, sys
name, output = sys.argv[1:]
payload = json.loads(output)
if payload.get("ok") is not True:
    raise SystemExit(f"D10B_L2 名称={name} 结果=失败 输出={output}")
print(f"D10B_L2 名称={name} 结果=通过")
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
    raise SystemExit(f"D10B_L2 名称={name} 结果=失败 输出={output}")
actual = ["{}:{}".format(item["id"], item["version_id"]) for item in payload.get("hits", [])]
wanted = [] if not expected else expected.split(",")
if actual != wanted:
    raise SystemExit(f"D10B_L2 名称={name} 结果=失败 期望={wanted} 实际={actual}")
print(f"D10B_L2 名称={name} 结果=通过 命中={actual}")
' "$name" "$output" "$expected"
}

assert_fail_closed() {
    local name="$1"
    local payload="$2"
    local status="$3"
    [[ "$status" -ne 0 ]] || fail "$name 必须失败关闭"
    python3 -c '
import json, sys
name, payload = sys.argv[1:]
value = json.loads(payload)
if value.get("ok") is not False:
    raise SystemExit(f"D10B_L2 名称={name} 结果=失败 输出={payload}")
print(f"D10B_L2 名称={name} 结果=通过")
' "$name" "$payload"
}

printf 'D10B_L2_元数据 已测提交=%s\n' "$(git -C "$repo_root" rev-parse HEAD)"
printf 'D10B_L2_元数据 桥接源码哈希=%s\n' "$(sha256sum "$repo_root/tests/vector-engine/vector_bridge_cli.cpp" | awk '{print $1}')"
printf 'D10B_L2_元数据 运行器哈希=%s\n' "$(sha256sum "$script_dir/run_d10b_vector_delete_l2.sh" | awk '{print $1}')"

create_output="$("$binary" create_collection "$collection" 2)"
assert_ok "创建集合" "$create_output"
collection_created=1

insert_output="$({
    printf '%s\n' '{"ids":[101,102,201],"vectors":[[1.0,0.0],[0.9,0.1],[1.0,0.0]],"user_ids":["user-a","user-a","user-b"],"version_ids":["v1","v2","v1"],"scene_ids":["","",""],"memory_statuses":["active","active","active"],"deleted_flags":[false,false,false]}'
} | "$binary" insert "$collection")"
assert_ok "写入删除测试数据" "$insert_output"

delete_output="$({
    printf '%s\n' '{"user_id":"user-a","ids":[102],"version_ids":["v2"]}'
} | "$binary" delete "$collection")"
assert_ok "同用户精确删除" "$delete_output"

user_a_query="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":[],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "删除后仅保留同用户未选记录" "$user_a_query" "101:v1"

user_b_query="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-b","allowed_scene_ids":[],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "删除不影响其他用户" "$user_b_query" "201:v1"

cross_user_delete_output="$({
    printf '%s\n' '{"user_id":"user-a","ids":[201],"version_ids":["v1"]}'
} | "$binary" delete "$collection")"
assert_ok "跨用户 ID 不得删除其他用户记录" "$cross_user_delete_output"
user_b_after_cross_user_query="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-b","allowed_scene_ids":[],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "跨用户 ID 删除后其他用户记录仍存在" "$user_b_after_cross_user_query" "201:v1"

version_mismatch_delete_output="$({
    printf '%s\n' '{"user_id":"user-a","ids":[101],"version_ids":["v999"]}'
} | "$binary" delete "$collection")"
assert_ok "版本不匹配不得删除记录" "$version_mismatch_delete_output"
user_a_after_version_mismatch_query="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":[],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "版本不匹配删除后原记录仍存在" "$user_a_after_version_mismatch_query" "101:v1"

replay_delete_output="$({
    printf '%s\n' '{"user_id":"user-a","ids":[102],"version_ids":["v2"]}'
} | "$binary" delete "$collection")"
assert_ok "重复删除保持可重放" "$replay_delete_output"
user_a_after_replay_query="$({
    printf '%s\n' '{"vector":[1.0,0.0],"filter":{"user_id":"user-a","allowed_scene_ids":[],"include_unscoped":true,"allowed_memory_statuses":["active"],"exclude_deleted":true}}'
} | "$binary" search "$collection" 10 5000)"
assert_hits "重复删除不恢复已删除记录" "$user_a_after_replay_query" "101:v1"

set +e
empty_selector_output="$({ printf '%s\n' '{"user_id":"user-a","ids":[],"version_ids":[]}'; } | "$binary" delete "$collection" 2>&1)"
empty_selector_status=$?
unknown_field_output="$({ printf '%s\n' '{"user_id":"user-a","ids":[101],"version_ids":["v1"],"任意表达式":"id in [201]"}'; } | "$binary" delete "$collection" 2>&1)"
unknown_field_status=$?
unpaired_version_output="$({ printf '%s\n' '{"user_id":"user-a","ids":[101,102],"version_ids":["v1"]}'; } | "$binary" delete "$collection" 2>&1)"
unpaired_version_status=$?
set -e
assert_fail_closed "空选择器" "$empty_selector_output" "$empty_selector_status"
assert_fail_closed "未知字段" "$unknown_field_output" "$unknown_field_status"
assert_fail_closed "未配对版本" "$unpaired_version_output" "$unpaired_version_status"

trap - EXIT
"$binary" drop_collection "$collection" >/dev/null || fail "清理失败"
printf 'D10B_L2 结果=通过 集合=%s 清理=完成\n' "$collection"
