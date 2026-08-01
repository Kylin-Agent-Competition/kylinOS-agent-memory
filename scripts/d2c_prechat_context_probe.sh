#!/usr/bin/env bash
# D2-C 实验 B: H2C-PreChat Memory Context 注入三路隔离探针
#
# 目标: 验证 Memory Context 注入后, UI/聊天库/模型请求三路隔离
# 关联: AGT-005 (Memory Context 注入, UNTESTED/E0·E2)
# 依据: 02 文档 §4.1 Pre-Chat 检索注入, §7.3 原文污染红线
#
# 用法:
#   ./d2c_prechat_context_probe.sh baseline        # 记录实验前基线
#   ./d2c_prechat_context_probe.sh capture-start   # 启动模型请求捕获
#   ./d2c_prechat_context_probe.sh capture-stop    # 停止捕获
#   ./d2c_prechat_context_probe.sh collect         # 三路证据采集
#
# 安全声明: 只读观察脚本, 不修改 AI 助手进程、数据库或配置
# 标记字符串: [D2C-MARKER-PRECHAT-001] 用于在三路证据中检索
# KYSEC: 如需执行, 对本脚本设置单文件 verified

set -euo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${PROBE_DIR}/out"
mkdir -p "${OUT_DIR}"

TIMESTAMP_FILE="${OUT_DIR}/.prechat_last_timestamp"
META_FILE="${OUT_DIR}/prechat_capture.meta"
CAPTURE_PID_FILE="${OUT_DIR}/prechat_capture.pid"
MARKER="[D2C-MARKER-PRECHAT-001]"

get_or_set_timestamp() {
    if [ -n "${1:-}" ]; then
        echo "${1}" > "${TIMESTAMP_FILE}"
        echo "${1}"
    elif [ -f "${TIMESTAMP_FILE}" ]; then
        cat "${TIMESTAMP_FILE}"
    else
        date +%Y%m%d_%H%M%S
    fi
}

TIMESTAMP="$(get_or_set_timestamp)"
BASELINE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.baseline.json"
CAPTURE_LOG_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.capture.log"
MODEL_REQUEST_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.model_request.jsonl"
DB_MESSAGE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.db_message.txt"
UI_SCREENSHOT_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.ui_screenshot.png"

DB_PATH="${HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"
AI_PROC_NAME="kylin-aiassistant"

find_ai_pid() {
    pgrep -f "${AI_PROC_NAME}" | head -n 1 || true
}

# 重新解析文件路径 (capture-stop / collect 调用时从 meta/timestamp_file 恢复)
reload_paths() {
    local ts_from_meta=""
    if [ -f "${META_FILE}" ]; then
        ts_from_meta="$(grep '^timestamp=' "${META_FILE}" | cut -d= -f2-)"
    fi
    if [ -n "${ts_from_meta}" ]; then
        TIMESTAMP="${ts_from_meta}"
    fi
    BASELINE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.baseline.json"
    CAPTURE_LOG_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.capture.log"
    MODEL_REQUEST_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.model_request.jsonl"
    DB_MESSAGE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.db_message.txt"
    UI_SCREENSHOT_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.ui_screenshot.png"
}

cmd_baseline() {
    # 每次 baseline 生成新时间戳, 作为后续 capture / collect 共用
    TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    TIMESTAMP="$(get_or_set_timestamp "${TIMESTAMP}")"
    reload_paths

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

    cat > "${BASELINE_FILE}" <<EOF
{
  "experiment": "H2C-PreChat",
  "timestamp": "${TIMESTAMP}",
  "marker": "${MARKER}",
  "ai_pid": "${pid}",
  "db_path": "${DB_PATH}",
  "record_rowid_max_before": "${rowid_max}",
  "note": "请在 AI 助手中输入包含 ${MARKER} 的文本"
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
    echo "    ${MARKER} 帮我回忆上次讨论的麒麟记忆系统架构。"
    echo ""
    echo "  基线: ${BASELINE_FILE}"
    echo "=============================================="
}

cmd_capture_start() {
    reload_paths
    local pid
    pid="$(find_ai_pid)"
    if [ -z "${pid}" ]; then
        echo "ERROR: 未找到 ${AI_PROC_NAME} 进程" >&2
        exit 1
    fi

    if [ -f "${CAPTURE_PID_FILE}" ]; then
        echo "ERROR: 已有捕获任务运行中" >&2
        exit 1
    fi

    echo "INFO: 启动模型请求捕获 (strace write 跟踪) -> ${CAPTURE_LOG_FILE}"
    echo "INFO: strace 直接写入原始日志 (不经过 grep 管道), capture-stop 时离线生成 MODEL_REQUEST_FILE"

    # strace 独立 nohup 直接写原始日志文件, 不经过 shell 管道
    # 避免 grep 管道导致终端阻塞, 并保证 $! 为 strace 自身 PID
    nohup strace -p "${pid}" -f -s 8192 -e trace=write \
        > "${CAPTURE_LOG_FILE}" 2>&1 </dev/null &
    local cap_pid=$!
    disown "${cap_pid}" 2>/dev/null || true

    sleep 1
    if ! kill -0 "${cap_pid}" 2>/dev/null; then
        echo "ERROR: strace 启动失败, 请检查 strace 是否可用 (sudo apt install strace) 或是否需要 sudo 权限" >&2
        echo "HINT: 如果 strace -p 需要 root, 使用: sudo $0 capture-start" >&2
        exit 1
    fi

    echo "${cap_pid}" > "${CAPTURE_PID_FILE}"
    cat > "${META_FILE}" <<EOF
strace_pid=${cap_pid}
ai_pid=${pid}
capture_log=${CAPTURE_LOG_FILE}
model_request_file=${MODEL_REQUEST_FILE}
timestamp=${TIMESTAMP}
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
    # 从 meta 文件恢复 capture_log / model_request 路径
    local cap_pid capture_log_from_meta model_request_from_meta
    cap_pid="$(cat "${CAPTURE_PID_FILE}")"
    if [ -f "${META_FILE}" ]; then
        capture_log_from_meta="$(grep '^capture_log=' "${META_FILE}" | cut -d= -f2-)"
        model_request_from_meta="$(grep '^model_request_file=' "${META_FILE}" | cut -d= -f2-)"
        [ -n "${capture_log_from_meta}" ] && CAPTURE_LOG_FILE="${capture_log_from_meta}"
        [ -n "${model_request_from_meta}" ] && MODEL_REQUEST_FILE="${model_request_from_meta}"
    fi

    echo "INFO: 停止 strace 进程 ${cap_pid}"
    kill "${cap_pid}" 2>/dev/null || true
    pkill -P "${cap_pid}" 2>/dev/null || true
    pkill -f "strace -p.*kylin" 2>/dev/null || true
    sleep 0.5
    rm -f "${CAPTURE_PID_FILE}"

    local log_size=0
    if [ -f "${CAPTURE_LOG_FILE}" ]; then
        log_size="$(wc -c < "${CAPTURE_LOG_FILE}" 2>/dev/null || echo 0)"
    fi
    echo "INFO: 原始捕获日志大小: ${log_size} bytes"

    # 离线过滤: 从原始 strace 日志 grep 生成 MODEL_REQUEST_FILE
    echo "INFO: 从原始日志离线过滤关键词 -> ${MODEL_REQUEST_FILE}"
    if [ -f "${CAPTURE_LOG_FILE}" ]; then
        grep -E "${MARKER}|chatAsync|model_request|memory_context" "${CAPTURE_LOG_FILE}" \
            > "${MODEL_REQUEST_FILE}" 2>/dev/null || true
    fi

    local line_count=0
    if [ -f "${MODEL_REQUEST_FILE}" ]; then
        line_count="$(wc -l < "${MODEL_REQUEST_FILE}" || echo 0)"
    fi

    echo "=============================================="
    echo " 模型请求捕获完成"
    echo "=============================================="
    echo "  原始日志: ${CAPTURE_LOG_FILE}"
    echo "  过滤行数: ${line_count}"
    echo "  输出文件: ${MODEL_REQUEST_FILE}"
    echo "=============================================="
}

cmd_collect() {
    reload_paths
    echo "=============================================="
    echo " H2C-PreChat 三路证据采集"
    echo "=============================================="

    # 路径 1: UI 截图 (人工触发或 kylin-screenshot)
    echo ""
    echo "[1/3] UI 路径截图"
    echo "  请手动截图 AI 助手当前对话界面, 保存为:"
    echo "  ${UI_SCREENSHOT_FILE}"
    echo "  或运行: kylin-screenshot -s ${UI_SCREENSHOT_FILE}"
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
        sqlite3 "${DB_PATH}" \
            "SELECT rowid, sessionID, msgIndex, message, operateTime FROM RECORD WHERE message LIKE '%${MARKER}%';" \
            > "${DB_MESSAGE_FILE}" 2>/dev/null || true

        local db_match_count
        db_match_count="$(wc -l < "${DB_MESSAGE_FILE}" || echo 0)"
        echo "  匹配行数: ${db_match_count}"
        echo "  输出文件: ${DB_MESSAGE_FILE}"

        # 检查是否包含 memory_context 字样 (污染检测)
        local pollution_check
        pollution_check="$(grep -c 'memory_context\|MemoryContext\|记忆上下文' "${DB_MESSAGE_FILE}" || echo 0)"
        if [ "${pollution_check}" -eq 0 ]; then
            echo "  ✓ H2C-PreChat-2 通过: 数据库 message 不含 Memory Context"
        else
            echo "  ✗ H2C-PreChat-2 失败: 数据库 message 疑似含 Memory Context (污染)"
        fi
    fi

    # 路径 3: 模型请求
    echo ""
    echo "[3/3] 模型请求路径检查"
    if [ ! -f "${MODEL_REQUEST_FILE}" ]; then
        echo "  ✗ 模型请求文件不存在, 请先运行 capture-start/capture-stop"
    else
        local model_match_count
        model_match_count="$(grep -c "${MARKER}" "${MODEL_REQUEST_FILE}" || echo 0)"
        echo "  含标记的请求行数: ${model_match_count}"

        local memory_in_request
        memory_in_request="$(grep -c 'memory_context\|MemoryContext\|记忆上下文' "${MODEL_REQUEST_FILE}" || echo 0)"
        if [ "${memory_in_request}" -gt 0 ]; then
            echo "  ✓ H2C-PreChat-3 通过: 模型请求含 Memory Context"
        else
            echo "  ! H2C-PreChat-3 未确认: 模型请求未观察到 Memory Context"
            echo "    (可能 Hook 点 A 未注入或 MemoryClient 未连接)"
        fi
    fi

    echo ""
    echo "=============================================="
    echo " 证据采集完成"
    echo "=============================================="
    echo "  UI 截图:       ${UI_SCREENSHOT_FILE}"
    echo "  数据库 message: ${DB_MESSAGE_FILE}"
    echo "  模型请求:       ${MODEL_REQUEST_FILE}"
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
    collect)
        cmd_collect
        ;;
    *)
        echo "用法: $0 {baseline|capture-start|capture-stop|collect}"
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
