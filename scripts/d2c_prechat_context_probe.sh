#!/usr/bin/env bash
# D2-C 实验 B: H2C-PreChat Memory Context 注入三路隔离探针
#
# 目标: 验证 Memory Context 注入后, UI/聊天库/模型请求三路隔离
# 关联: AGT-005 (Memory Context 注入, NOT_OBSERVED/E0·E2)
# 依据: 02 文档 §4.1 Pre-Chat 检索注入, §7.3 原文污染红线
#
# 用法:
#   ./d2c_prechat_context_probe.sh baseline        # 记录实验前基线
#   ./d2c_prechat_context_probe.sh capture-start   # 启动模型请求捕获
#   ./d2c_prechat_context_probe.sh capture-stop    # 停止捕获
#   ./d2c_prechat_context_probe.sh collect         # 三路证据采集
#
# 安全声明: 只读观察脚本, 不修改 AI 助手进程、数据库或配置
# 标记字符串由 D2C_RUN_ID 生成，避免历史 Run 命中当前实验。
# KYSEC: 如需执行, 对本脚本设置单文件 verified

set -euo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${PROBE_DIR}/out"
mkdir -p "${OUT_DIR}"

# 确定实际登录用户的 HOME (避免 sudo 下 $HOME 变成 /root)
# 优先级: SUDO_USER -> AI 进程 owner -> 当前 $HOME
get_user_home() {
    if [ -n "${SUDO_USER:-}" ]; then
        local uhome
        uhome="$(eval echo "~${SUDO_USER}" 2>/dev/null || true)"
        if [ -d "${uhome}" ]; then
            echo "${uhome}"
            return
        fi
    fi
    # 通过 AI 进程的 /proc/<pid>/environ 反查 HOME
    local apid
    apid="$(pgrep -f "/files/bin/kylin-aiassistant" 2>/dev/null | head -n 1 || true)"
    if [ -n "${apid}" ] && [ -r "/proc/${apid}/environ" ]; then
        local ehome
        ehome="$(tr '\0' '\n' < "/proc/${apid}/environ" 2>/dev/null \
            | grep '^HOME=' | cut -d= -f2- || true)"
        if [ -n "${ehome}" ] && [ -d "${ehome}" ]; then
            echo "${ehome}"
            return
        fi
    fi
    echo "${HOME}"
}
USER_HOME="$(get_user_home)"

# 状态文件统一放到真实用户 HOME 下, 避免 sudo 与非 sudo 混用时权限冲突
STATE_DIR="${USER_HOME}/.d2c-probe-state"
mkdir -p "${STATE_DIR}"

META_FILE="${STATE_DIR}/prechat_capture.meta"
CAPTURE_PID_FILE="${STATE_DIR}/prechat_capture.pid"
BASELINE_META_FILE="${STATE_DIR}/prechat_baseline.meta"

require_run_id() {
    if [ -z "${D2C_RUN_ID:-}" ]; then
        echo "ERROR: D2C_RUN_ID is required; one Canonical Run must be shared by every D2-C probe" >&2
        exit 2
    fi
    case "${D2C_RUN_ID}" in
        *[!A-Za-z0-9_.-]*|'')
            echo "ERROR: D2C_RUN_ID may contain only A-Z, a-z, 0-9, _, . and -" >&2
            exit 2
            ;;
    esac
    printf '%s' "${D2C_RUN_ID}"
}

RUN_ID="$(require_run_id)"
TIMESTAMP="${RUN_ID}"
MARKER="[D2C-PRECHAT-${RUN_ID}]"
USER_TEXT="${MARKER} 帮我回忆上次讨论的麒麟记忆系统架构。"
BASELINE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.baseline.json"
CAPTURE_LOG_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.capture.log"
STRACE_FILTER_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.strace_filtered.log"
AUDIT_SOURCE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.gateway_audit.jsonl"
DB_MESSAGE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.db_message.txt"
UI_SCREENSHOT_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.ui_screenshot.png"

DB_PATH="${USER_HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"
AI_PROC_NAME="kylin-aiassistant"

# 安全地将字符串转为非负整数: 去掉非数字和多余换行, 空值默认 0
to_int() {
    local raw="$1"
    local cleaned
    cleaned="$(printf '%s' "${raw}" | tail -n 1 | tr -cd '0-9')"
    if [ -z "${cleaned}" ]; then
        printf '0'
    else
        printf '%s' "${cleaned}"
    fi
}

find_ai_pid() {
    # 优先选择真正的 AI 助手主进程, 排除 bash launcher 包装进程
    # 实际进程 cmdline: /opt/apps/cn.kylin.kylin-aiassistant/files/bin/kylin-aiassistant
    # bash launcher:    /bin/bash /opt/apps/kaiming/bin/cn.kylin.kylin-aiassistant ...
    local pids
    pids="$(pgrep -f "${AI_PROC_NAME}" 2>/dev/null || true)"
    if [ -z "${pids}" ]; then
        true
        return
    fi
    local best_pid=""
    # 1) 优先: cmdline 含 /files/bin/kylin-aiassistant (真实二进制路径)
    for p in ${pids}; do
        local cmdline
        cmdline="$(tr '\0' ' ' < /proc/"${p}"/cmdline 2>/dev/null || true)"
        case "${cmdline}" in
            */files/bin/kylin-aiassistant*)
                best_pid="${p}"
                break
                ;;
        esac
    done
    # 2) 次选: cmdline 不以 /bin/bash 开头 (排除 launcher)
    if [ -z "${best_pid}" ]; then
        for p in ${pids}; do
            local cmdline
            cmdline="$(tr '\0' ' ' < /proc/"${p}"/cmdline 2>/dev/null || true)"
            case "${cmdline}" in
                /bin/bash\ *|/bin/sh\ *)
                    continue
                    ;;
                *)
                    best_pid="${p}"
                    break
                    ;;
            esac
        done
    fi
    # 3) 兜底: 取第一个 PID
    if [ -n "${best_pid}" ]; then
        echo "${best_pid}"
    else
        echo "${pids}" | head -n 1
    fi
}

set_paths_for_current_run() {
    TIMESTAMP="${RUN_ID}"
    BASELINE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.baseline.json"
    CAPTURE_LOG_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.capture.log"
    STRACE_FILTER_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.strace_filtered.log"
    AUDIT_SOURCE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.gateway_audit.jsonl"
    DB_MESSAGE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.db_message.txt"
    UI_SCREENSHOT_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.ui_screenshot.png"
}

# meta 只可用于验证当前 Run 的捕获状态，文件路径始终由 RUN_ID 重新推导。
reload_paths() {
    local ts_from_meta="" run_id_from_meta=""
    if [ -f "${META_FILE}" ]; then
        ts_from_meta="$(grep '^timestamp=' "${META_FILE}" | cut -d= -f2-)"
        run_id_from_meta="$(grep '^run_id=' "${META_FILE}" | cut -d= -f2-)"
        if [ "${run_id_from_meta}" != "${RUN_ID}" ] || [ "${ts_from_meta}" != "${RUN_ID}" ]; then
            echo "ERROR: refusing stale PreChat meta; expected run_id=${RUN_ID}, got ${run_id_from_meta:-missing}" >&2
            exit 1
        fi
    fi
    set_paths_for_current_run
}

require_current_baseline() {
    local baseline_run_id=""
    if [ -f "${BASELINE_META_FILE}" ]; then
        baseline_run_id="$(grep '^run_id=' "${BASELINE_META_FILE}" | cut -d= -f2-)"
    fi
    if [ "${baseline_run_id}" != "${RUN_ID}" ] || [ ! -f "${BASELINE_FILE}" ]; then
        echo "ERROR: current-Run baseline is required; run baseline with D2C_RUN_ID=${RUN_ID} first" >&2
        return 1
    fi
}

cmd_baseline() {
    set_paths_for_current_run

    local pid
    pid="$(find_ai_pid)"
    if [ -z "${pid}" ]; then
        echo "ERROR: 未找到 ${AI_PROC_NAME} 进程" >&2
        exit 1
    fi

    local rowid_max="N/A"
    if [ -f "${DB_PATH}" ]; then
        rowid_max="$(sqlite3 "${DB_PATH}" "SELECT MAX(rowid) FROM RECORD;" 2>/dev/null || echo "N/A")"
    fi

    # 基线与 RUN_ID 一起保存；没有可用 rowid 时 collect 必须 fail closed。
    cat > "${BASELINE_META_FILE}" <<EOF
run_id=${RUN_ID}
baseline_rowid=${rowid_max}
EOF

    cat > "${BASELINE_FILE}" <<EOF
{
  "experiment": "H2C-PreChat",
  "run_id": "${RUN_ID}",
  "timestamp": "${TIMESTAMP}",
  "marker": "${MARKER}",
  "ai_pid": "${pid}",
  "db_path": "${DB_PATH}",
  "record_rowid_max_before": "${rowid_max}",
  "expected_user_text": "${USER_TEXT}"
}
EOF

    echo "=============================================="
    echo " H2C-PreChat 基线记录"
    echo "=============================================="
    echo "  AI 助手 PID:        ${pid}"
    echo "  RECORD rowid 最大值: ${rowid_max}"
    echo "  标记字符串:          ${MARKER}"
    echo ""
    echo "  请在 AI 助手中输入:"
    echo "    ${USER_TEXT}"
    echo ""
    echo "  基线: ${BASELINE_FILE}"
    echo "=============================================="
}

cmd_capture_start() {
    set_paths_for_current_run
    require_current_baseline
    local pid
    pid="$(find_ai_pid)"
    if [ -z "${pid}" ]; then
        echo "ERROR: 未找到 ${AI_PROC_NAME} 进程" >&2
        exit 1
    fi
    echo "INFO: AI 助手 PID = ${pid}"

    if [ -f "${CAPTURE_PID_FILE}" ]; then
        echo "ERROR: 已有捕获任务运行中" >&2
        exit 1
    fi

    echo "INFO: 启动模型请求捕获 (strace IPC 跟踪) -> ${CAPTURE_LOG_FILE}"
    echo "INFO: strace 直接写入原始日志; capture-stop 仅生成诊断 strace_filtered.log，不充当网关 JSONL"
    echo "INFO: 捕获范围: write,writev,sendmsg,sendto,recvmsg,read,poll (扩至常见 IPC)"

    # strace 独立 nohup 直接写原始日志文件
    # - 仅 attach 到真实 AI 助手主进程；Runtime 不是此智能体请求的已验证承载通道。
    # - -f 跟踪子进程/线程
    # - -s 32768 (覆盖 memory_context 大 JSON)
    # - -yy (打印 socket 路径/文件描述符类型)
    local strace_args=(-p "${pid}" -f -s 32768 -yy \
        -e trace=write,writev,sendmsg,sendto,recvmsg,read,poll)

    nohup strace "${strace_args[@]}" \
        > "${CAPTURE_LOG_FILE}" 2>&1 </dev/null &
    local cap_pid=$!
    disown "${cap_pid}" 2>/dev/null || true

    sleep 2
    if ! kill -0 "${cap_pid}" 2>/dev/null; then
        echo "ERROR: strace 启动失败, 请检查 strace 是否可用 (sudo apt install strace) 或是否需要 sudo 权限" >&2
        echo "HINT: 如果 strace -p 需要 root 或 ptrace_scope=2, 使用: sudo $0 capture-start" >&2
        echo "HINT: 可临时放宽:  sudo sysctl -w kernel.yama.ptrace_scope=0" >&2
        exit 1
    fi
    # 确认 attach
    local attached=""
    attached="$(ps -o args= -p "${cap_pid}" 2>/dev/null | grep -o -- "-p *${pid}" || true)"
    if [ -z "${attached}" ]; then
        echo "WARN: strace PID=${cap_pid} 已启动, 但无法确认 attach 到 AI PID=${pid}; 聊天后请检查日志是否增长" >&2
    else
        echo "INFO: 已确认 strace attach 到 AI PID=${pid}"
    fi
    echo "${cap_pid}" > "${CAPTURE_PID_FILE}"
    cat > "${META_FILE}" <<EOF
strace_pid=${cap_pid}
ai_pid=${pid}
capture_log=${CAPTURE_LOG_FILE}
strace_filtered_log=${STRACE_FILTER_FILE}
timestamp=${TIMESTAMP}
run_id=${RUN_ID}
started_at=$(date '+%Y-%m-%d %H:%M:%S')
EOF

    echo "INFO: strace 进程 PID = ${cap_pid} (已脱离终端, 可以继续输入命令)"
    echo "INFO: 现在请在 AI 助手中输入带标记的文本"
}

cmd_capture_stop() {
    if [ ! -f "${CAPTURE_PID_FILE}" ]; then
        echo "ERROR: 未找到运行中的捕获任务" >&2
        exit 1
    fi
    reload_paths
    # 不从 meta 恢复路径，避免旧 Run 或伪造路径被当前 Run 消费。
    local cap_pid
    cap_pid="$(cat "${CAPTURE_PID_FILE}")"

    echo "INFO: 停止 strace 进程 ${cap_pid}"
    kill "${cap_pid}" 2>/dev/null || true
    pkill -P "${cap_pid}" 2>/dev/null || true
    # 只清理本次采集 PID 的子进程；不得以进程名宽匹配误杀并行采集任务。
    sleep 0.5
    rm -f "${CAPTURE_PID_FILE}"

    local log_size=0
    if [ -f "${CAPTURE_LOG_FILE}" ]; then
        log_size="$(wc -c < "${CAPTURE_LOG_FILE}" 2>/dev/null || echo 0)"
    fi
    echo "INFO: 原始捕获日志大小: ${log_size} bytes"

    # 离线过滤仅产生诊断日志，绝不能伪装成协议解码的 JSONL。
    # 注: MARKER 含方括号，必须用 grep -F (固定字符串) 匹配。
    # memory_context 关键词扩到常见变体 (驼峰/中文/前缀名)
    echo "INFO: 从原始日志离线过滤关键词 -> ${STRACE_FILTER_FILE}"
    if [ -f "${CAPTURE_LOG_FILE}" ]; then
        {
            # 1) 固定字符串匹配 marker (含 [], 不能用正则)
            grep -F "${MARKER}" "${CAPTURE_LOG_FILE}" 2>/dev/null || true
            # 2) 正则匹配其他关键词 (message_type/chat/model_request/memory 常见变体)
            grep -E 'message_type|"chat"|model_request|memory[_-]?[Cc]ontext|MemoryContext|记忆上下文|记忆\s*上下|prompt|system_prompt|context' \
                "${CAPTURE_LOG_FILE}" 2>/dev/null || true
        } | sort -u > "${STRACE_FILTER_FILE}" 2>/dev/null || true
    fi

    local line_count=0
    if [ -f "${STRACE_FILTER_FILE}" ]; then
        line_count="$(wc -l < "${STRACE_FILTER_FILE}" || echo 0)"
    fi
    # 如果 grep 过滤仍为 0, 退一步: 只过滤 sendmsg+assistant.sock 的所有行 (DBus 回调)
    if [ "${line_count}" -eq 0 ] && [ -f "${CAPTURE_LOG_FILE}" ]; then
        echo "WARN: 关键词过滤 0 行, 退化为提取所有 sendmsg 到 assistant.sock 的 DBus 行"
        grep -E 'sendmsg.*assistant\.sock' "${CAPTURE_LOG_FILE}" \
            > "${STRACE_FILTER_FILE}" 2>/dev/null || true
        if [ -f "${STRACE_FILTER_FILE}" ]; then
            line_count="$(wc -l < "${STRACE_FILTER_FILE}" || echo 0)"
        fi
    fi

    echo "=============================================="
    echo " 模型请求捕获完成"
    echo "=============================================="
    echo "  原始日志: ${CAPTURE_LOG_FILE}"
    echo "  过滤行数: ${line_count}"
    echo "  诊断输出: ${STRACE_FILTER_FILE}"
    if [ "${line_count}" -eq 0 ] && [ -f "${CAPTURE_LOG_FILE}" ]; then
        local raw_total
        raw_total="$(wc -l < "${CAPTURE_LOG_FILE}" 2>/dev/null || echo 0)"
        echo "  HINT: 原始日志 ${raw_total} 行, 但关键词未命中; 可能字段名与预期不同"
        echo "        建议人工快速浏览: tail -n 200 ${CAPTURE_LOG_FILE} | head -n 100"
    fi
    echo "=============================================="
}

cmd_import_audit() {
    local source_file="${2:-}"
    set_paths_for_current_run
    require_current_baseline
    if [ -z "${source_file}" ] || [ ! -f "${source_file}" ]; then
        echo "ERROR: formal redacted gateway audit JSONL file is required" >&2
        exit 1
    fi
    python3 - "${source_file}" "${AUDIT_SOURCE_FILE}" "${RUN_ID}" "${MARKER}" <<'PY'
import json
import pathlib
import sys

source_path, audit_out = map(pathlib.Path, sys.argv[1:3])
run_id, marker = sys.argv[3:5]
required = {"run_id", "timestamp", "source", "request_id", "user_marker", "memory_context_present", "context_sha256", "field_names"}
allowed = required | {"schema_version", "model", "redaction"}
secret_keys = {"api_key", "authorization", "password", "secret", "token", "private_key", "credential"}

def validate_safe(value, path="$"):
    if isinstance(value, str):
        if len(value) > 8192:
            raise SystemExit(f"ERROR: {path} exceeds the audit string limit")
    elif isinstance(value, list):
        if len(value) > 100:
            raise SystemExit(f"ERROR: {path} exceeds the audit list limit")
        for index, child in enumerate(value):
            validate_safe(child, f"{path}[{index}]")
    elif isinstance(value, dict):
        if len(value) > 50:
            raise SystemExit(f"ERROR: {path} exceeds the audit object limit")
        for key, child in value.items():
            if not isinstance(key, str):
                raise SystemExit(f"ERROR: {path} has a non-string field name")
            if key.casefold() in secret_keys:
                raise SystemExit(f"ERROR: {path}.{key} is a sensitive field")
            validate_safe(child, f"{path}.{key}")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise SystemExit(f"ERROR: {path} has an unsupported audit value")

records = []
for number, raw in enumerate(source_path.read_text(encoding="utf-8").splitlines(), 1):
    if not raw.strip():
        continue
    item = json.loads(raw)
    if not isinstance(item, dict) or not required <= item.keys():
        raise SystemExit(f"ERROR: line {number} lacks required audit fields")
    if set(item) - allowed:
        raise SystemExit(f"ERROR: line {number} has undeclared fields; refusing possible raw or sensitive data")
    if item["source"] != "kylin-bot-gateway":
        raise SystemExit(f"ERROR: line {number} is not a formal kylin-bot gateway audit record")
    validate_safe(item)
    if item["run_id"] != run_id:
        continue
    if item["user_marker"] != marker:
        continue
    digest = item["context_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        raise SystemExit(f"ERROR: line {number} has invalid context_sha256")
    if not isinstance(item["timestamp"], str) or not item["timestamp"] or not isinstance(item["request_id"], str) or not item["request_id"] or not isinstance(item["memory_context_present"], bool) or not isinstance(item["field_names"], list):
        raise SystemExit(f"ERROR: line {number} has invalid audit field types")
    records.append(item)
if not records:
    raise SystemExit("ERROR: no matching formal gateway audit record for marker")
payload = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in records) + "\n"
pathlib.Path(audit_out).write_text(payload, encoding="utf-8")
print(f"INFO: imported {len(records)} formal redacted gateway audit record(s)")
PY
    echo "INFO: formal audit source: ${AUDIT_SOURCE_FILE}"
    echo "INFO: formal gateway audit evidence: ${AUDIT_SOURCE_FILE}"
}

cmd_collect() {
    set_paths_for_current_run
    echo "=============================================="
    echo " H2C-PreChat 三路证据采集"
    echo "=============================================="

    # 路径 1: UI 截图（使用已验证的桌面截图方式或宿主 VM 截图）
    echo ""
    echo "[1/3] UI 路径截图"
    echo "  请手动截图 AI 助手当前对话界面, 保存为:"
    echo "  ${UI_SCREENSHOT_FILE}"
    echo "  使用当前桌面可用的截图工具，或将宿主 VM 截图复制到该路径"
    echo "  (等待 10 秒, 若文件存在则继续)"
    sleep 10
    if [ -f "${UI_SCREENSHOT_FILE}" ]; then
        echo "  ✓ UI 截图已保存"
    else
        echo "  ! UI 截图未保存, 请手动补充"
    fi

    # 路径 2: 聊天数据库 message
    echo ""
    echo "[2/3] 聊天库 RECORD.message 查询"
    if [ ! -f "${DB_PATH}" ]; then
        echo "  ✗ 数据库不存在: ${DB_PATH}"
    else
        # 只允许本 Run 的基线；缺失或不可用基线一律 NOT_VERIFIED。
        local baseline_rowid="N/A"
        if require_current_baseline; then
            baseline_rowid="$(grep '^baseline_rowid=' "${BASELINE_META_FILE}" | cut -d= -f2-)"
        fi

        if [ "${baseline_rowid}" = "N/A" ] || [ -z "${baseline_rowid}" ]; then
            echo "  ! H2C-PreChat-2 NOT_VERIFIED: current-Run baseline_rowid 不可用；拒绝查询历史记录"
            : > "${DB_MESSAGE_FILE}"
        else
            echo "  baseline_rowid = ${baseline_rowid} (仅查询此后新增的记录)"
            sqlite3 "${DB_PATH}" \
                "SELECT rowid, sessionID, msgIndex, message, operateTime FROM RECORD WHERE rowid > ${baseline_rowid} AND message LIKE '%${MARKER}%';" \
                > "${DB_MESSAGE_FILE}" 2>/dev/null || true
        fi

        local raw_dbm
        raw_dbm="$(wc -l < "${DB_MESSAGE_FILE}" 2>/dev/null || echo 0)"
        local db_match_count
        db_match_count="$(to_int "${raw_dbm}")"
        echo "  匹配行数: ${db_match_count}"
        echo "  输出文件: ${DB_MESSAGE_FILE}"

        # 同时验证当前 Run 的用户 message 精确等于预期原始输入，且无 Memory Context 污染。
        local raw_pol
        raw_pol="$(grep -cE 'memory_context|MemoryContext|记忆上下文' "${DB_MESSAGE_FILE}" 2>/dev/null || echo 0)"
        local pollution_check
        pollution_check="$(to_int "${raw_pol}")"
        local expected_count
        expected_count="$(to_int "$(grep -cF "\"message\":\"${USER_TEXT}\"" "${DB_MESSAGE_FILE}" 2>/dev/null || echo 0)")"
        if [ "${baseline_rowid}" = "N/A" ] || [ -z "${baseline_rowid}" ]; then
            true
        elif [ "${db_match_count}" -eq 0 ] || [ "${expected_count}" -eq 0 ]; then
            echo "  ✗ H2C-PreChat-2 失败: 未找到本轮精确原始用户 message"
        else
            if [ "${pollution_check}" -eq 0 ]; then
                echo "  ✓ H2C-PreChat-2 通过: 数据库 message 不含 Memory Context"
            else
                echo "  ✗ H2C-PreChat-2 失败: 数据库 message 疑似含 Memory Context (污染)"
            fi
        fi
    fi

    # 路径 3: 模型请求
    echo ""
    echo "[3/3] 正式 Gateway Audit 路径检查"
    if [ ! -f "${AUDIT_SOURCE_FILE}" ]; then
        echo "  ! H2C-PreChat-3 未确认: 正式当前 Run Gateway Audit 不存在"
    else
        local raw_mm raw_mir
        # MARKER 含 [], 必须 grep -F (固定字符串), 不能用正则
        raw_mm="$(grep -cF "${MARKER}" "${AUDIT_SOURCE_FILE}" 2>/dev/null || echo 0)"
        local model_match_count
        model_match_count="$(to_int "${raw_mm}")"
        echo "  含标记的请求行数: ${model_match_count}"

        raw_mir="$(grep -c '"memory_context_present"[[:space:]]*:[[:space:]]*true' \
            "${AUDIT_SOURCE_FILE}" 2>/dev/null || echo 0)"
        local memory_in_request
        memory_in_request="$(to_int "${raw_mir}")"
        if [ "${memory_in_request}" -gt 0 ]; then
            echo "  PASS H2C-PreChat-3: formal redacted gateway audit confirms Memory Context"
        else
            echo "  ! H2C-PreChat-3 未确认: 模型请求未观察到 Memory Context"
            echo "    (可能 Hook 点 A 未注入 或 MemoryClient 未连接 或 关键词仍需扩展)"
            # 辅助: 打印正式 audit 内容提示（最多 10 行）
            local fl
            fl="$(wc -l < "${AUDIT_SOURCE_FILE}" 2>/dev/null || echo 0)"
            if [ "${fl}" -gt 0 ]; then
                echo "    提示: ${AUDIT_SOURCE_FILE} 共 ${fl} 行, 截取前 10 行供人工定位:"
                head -n 10 "${AUDIT_SOURCE_FILE}" 2>/dev/null | sed 's/^/    > /' || true
            fi
        fi
    fi

    echo ""
    echo "=============================================="
    echo " 证据采集完成"
    echo "=============================================="
    echo "  UI 截图:       ${UI_SCREENSHOT_FILE}"
    echo "  数据库 message: ${DB_MESSAGE_FILE}"
    echo "  strace 诊断:    ${STRACE_FILTER_FILE}"
    echo "  Gateway Audit:  ${AUDIT_SOURCE_FILE}"
    echo "=============================================="
}

case "${1:-}" in
    baseline)
        cmd_baseline
        ;;
    capture-start)
        cmd_capture_start
        ;;
    capture-stop)
        cmd_capture_stop
        ;;
    import-audit)
        cmd_import_audit "$@"
        ;;
    collect)
        cmd_collect
        ;;
    *)
        echo "Usage: $0 {baseline|capture-start|capture-stop|import-audit FILE.jsonl|collect}"
        echo ""
        echo "  baseline       - 记录实验前基线"
        echo "  capture-start  - 启动模型请求捕获"
        echo "  capture-stop   - 停止捕获"
        echo "  collect        - 三路证据采集"
        echo ""
        echo "  标记字符串: ${MARKER}"
        exit 1
        ;;
esac
