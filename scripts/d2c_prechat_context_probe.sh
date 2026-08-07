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

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
MARKER="[D2C-MARKER-PRECHAT-001]"

BASELINE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.baseline.json"
MODEL_REQUEST_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.model_request.jsonl"
DB_MESSAGE_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.db_message.txt"
UI_SCREENSHOT_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.ui_screenshot.png"
CAPTURE_PID_FILE="${OUT_DIR}/prechat_capture.pid"
CAPTURE_LOG_FILE="${OUT_DIR}/prechat_${TIMESTAMP}.capture.log"

DB_PATH="${HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"
AI_PROC_NAME="kylin-aiassistant"

find_ai_pid() {
    pgrep -f "${AI_PROC_NAME}" | head -n 1 || true
}

cmd_baseline() {
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

    echo "INFO: 启动模型请求捕获 (strace write 跟踪) -> ${MODEL_REQUEST_FILE}"
    # 使用 strace 跟踪 socket 写入, 捕获 chatAsync 入参
    # 过滤包含标记字符串的行
    nohup strace -p "${pid}" -f -s 8192 -e trace=write 2>&1 \
        | grep --line-buffered -E "${MARKER}|chatAsync|model_request|memory_context" \
        > "${MODEL_REQUEST_FILE}" &

    local cap_pid=$!
    echo "${cap_pid}" > "${CAPTURE_PID_FILE}"
    echo "INFO: 捕获进程 PID = ${cap_pid}"
    echo "INFO: 现在请在 AI 助手中输入带标记的文本"
}

cmd_capture_stop() {
    if [ ! -f "${CAPTURE_PID_FILE}" ]; then
        echo "ERROR: 未找到运行中的捕获任务" >&2
        exit 1
    fi
    local cap_pid
    cap_pid="$(cat "${CAPTURE_PID_FILE}")"

    echo "INFO: 停止捕获进程 ${cap_pid}"
    kill "${cap_pid}" 2>/dev/null || true
    pkill -P "${cap_pid}" 2>/dev/null || true
    rm -f "${CAPTURE_PID_FILE}"

    local line_count=0
    if [ -f "${MODEL_REQUEST_FILE}" ]; then
        line_count="$(wc -l < "${MODEL_REQUEST_FILE}" || echo 0)"
    fi

    echo "=============================================="
    echo " 模型请求捕获完成"
    echo "=============================================="
    echo "  捕获行数: ${line_count}"
    echo "  输出文件: ${MODEL_REQUEST_FILE}"
    echo "=============================================="
}

cmd_collect() {
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
