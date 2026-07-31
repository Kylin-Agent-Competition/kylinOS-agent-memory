#!/usr/bin/env bash
# D2-C 实验 A: H2C-PostTurn is_end 唯一性计数只读脚本
#
# 目标: 验证普通聊天流式回答中, 唯一 is_end=true 触发一次 TurnFinalizedEvent
# 关联: AGT-002 (普通聊天流式完成, HOST_VERIFIED/E4)
# 依据: 02 文档 §4.2 Post-Turn 观察接入, §16.15 步骤 14
#
# 用法:
#   ./d2c_postturn_isend_counter.sh start    # 启动日志捕获
#   ./d2c_postturn_isend_counter.sh stop     # 停止捕获并生成计数报告
#   ./d2c_postturn_isend_counter.sh dbcheck  # 数据库落库验证
#
# 安全声明: 只读观察脚本, 不修改 AI 助手进程、数据库或配置
# KYSEC: 如需执行, 对本脚本设置单文件 verified (不全局关闭 KYSEC)

set -euo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${PROBE_DIR}/out"
mkdir -p "${OUT_DIR}"

# 状态文件: 持久化 start 时的信息供 stop 读取
PID_FILE="${OUT_DIR}/postturn_capture.pid"
STATE_FILE="${OUT_DIR}/postturn_capture.state"

DB_PATH="${HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"

# AI 助手进程名
AI_PROC_NAME="kylin-aiassistant"

find_ai_pid() {
    pgrep -f "${AI_PROC_NAME}" | head -n 1 || true
}

cmd_start() {
    local pid
    pid="$(find_ai_pid)"
    if [ -z "${pid}" ]; then
        echo "ERROR: 未找到 ${AI_PROC_NAME} 进程, 请先启动 AI 助手" >&2
        exit 1
    fi
    echo "INFO: AI 助手 PID = ${pid}"

    if [ -f "${PID_FILE}" ]; then
        echo "ERROR: 已有捕获任务运行中 (PID 文件存在: ${PID_FILE})" >&2
        exit 1
    fi

    local ts log_file raw_log
    ts="$(date +%Y%m%d_%H%M%S)"
    log_file="${OUT_DIR}/postturn_${ts}.log"
    raw_log="${OUT_DIR}/postturn_${ts}.raw.log"

    # 检查 strace 权限
    if ! strace -p "${pid}" -e trace=write -c -o /dev/null 2>/dev/null; then
        echo "WARN: strace 附加失败, 可能需要 sudo 权限" >&2
        echo "WARN: 请以 sudo 运行本脚本: sudo $0 start" >&2
        echo "INFO: 仍将尝试启动, 若失败请改用 sudo" >&2
    fi

    echo "INFO: 启动 strace 原始捕获 -> ${raw_log}"
    # 使用 strace 跟踪系统调用, 输出到原始日志 (不过滤, 不触发 pipefail)
    # -s 4096 设置字符串最大长度
    # -f 跟踪子进程
    # -e trace=write,recvmsg 只跟踪写入和消息接收
    nohup strace -p "${pid}" -f -s 4096 -e trace=write,recvmsg 2>&1 > "${raw_log}" &
    local strace_pid=$!

    echo "INFO: 启动关键词过滤 -> ${log_file}"
    # 从原始日志中过滤关键词 (独立进程, 不影响 strace)
    tail -f "${raw_log}" 2>/dev/null \
        | grep --line-buffered -E 'is_end|chatCallback|updateBubble' > "${log_file}" 2>&1 &
    local grep_pid=$!

    # 等待 2 秒验证 strace 进程存活
    sleep 2
    if ! kill -0 "${strace_pid}" 2>/dev/null; then
        echo "WARN: strace 进程已退出 (PID ${strace_pid})" >&2
        echo "WARN: 可能原因: 权限不足 (ptrace_scope=1) 或进程不存在" >&2
        echo "WARN: 解决: 以 sudo 运行: sudo $0 start" >&2
        echo "INFO: 即使 strace 失败, 数据库验证仍可用: $0 dbcheck" >&2
    fi

    # 持久化状态: 双 PID + 文件路径 + 时间戳
    cat > "${PID_FILE}" <<EOF
STRACE_PID=${strace_pid}
GREP_PID=${grep_pid}
EOF
    cat > "${STATE_FILE}" <<EOF
STRACE_PID=${strace_pid}
GREP_PID=${grep_pid}
LOG_FILE=${log_file}
RAW_LOG=${raw_log}
TIMESTAMP=${ts}
AI_PID=${pid}
START_TIME=$(date -Iseconds)
EOF

    echo "INFO: strace PID = ${strace_pid}, grep PID = ${grep_pid}"
    echo "INFO: 现在请在 AI 助手中发起一次普通文本问答"
    echo "INFO: 完成后运行: $0 stop"
}

cmd_stop() {
    if [ ! -f "${PID_FILE}" ]; then
        echo "ERROR: 未找到运行中的捕获任务" >&2
        exit 1
    fi

    # 读取双 PID
    local strace_pid grep_pid
    strace_pid="$(grep '^STRACE_PID=' "${PID_FILE}" | cut -d= -f2)"
    grep_pid="$(grep '^GREP_PID=' "${PID_FILE}" | cut -d= -f2)"

    # 从状态文件读取日志文件路径
    local log_file ts
    if [ -f "${STATE_FILE}" ]; then
        log_file="$(grep '^LOG_FILE=' "${STATE_FILE}" | cut -d= -f2-)"
        ts="$(grep '^TIMESTAMP=' "${STATE_FILE}" | cut -d= -f2-)"
    else
        echo "ERROR: 状态文件不存在, 无法确定日志文件路径" >&2
        exit 1
    fi

    local summary_file="${OUT_DIR}/postturn_${ts}.summary.json"

    echo "INFO: 停止 grep 进程 ${grep_pid}"
    kill "${grep_pid}" 2>/dev/null || true
    pkill -P "${grep_pid}" 2>/dev/null || true

    echo "INFO: 停止 strace 进程 ${strace_pid}"
    kill "${strace_pid}" 2>/dev/null || true
    pkill -P "${strace_pid}" 2>/dev/null || true
    # 也杀掉所有 tail -f 和 strace 残留子进程
    pkill -f "tail -f.*postturn_" 2>/dev/null || true
    pkill -f "strace -p.*kylin-aiassistant" 2>/dev/null || true
    rm -f "${PID_FILE}" "${STATE_FILE}"

    if [ ! -f "${log_file}" ]; then
        echo "ERROR: 日志文件不存在: ${log_file}" >&2
        echo "ERROR: strace 可能因权限不足未捕获到数据" >&2
        echo "INFO: 数据库落库验证仍可执行: $0 dbcheck" >&2
        echo "INFO: 如需 strace 捕获, 请以 sudo 重新运行: sudo $0 start" >&2
        exit 1
    fi

    # 如果日志文件为空, 也给出警告 (grep 过滤后可能没有匹配)
    if [ ! -s "${log_file}" ]; then
        echo "WARN: 日志文件为空 (没有匹配到 is_end/chatCallback/updateBubble)" >&2
        echo "WARN: strace 可能捕获了数据但关键词不匹配" >&2
        echo "INFO: 可查看原始日志: ${OUT_DIR}/postturn_${ts}.raw.log" >&2
    fi

    echo "INFO: 生成计数报告 -> ${summary_file}"

    local chat_callback_count is_end_false_count is_end_true_count update_bubble_count
    chat_callback_count="$(grep -c 'chatCallback' "${log_file}" 2>/dev/null || echo 0)"
    is_end_false_count="$(grep -c 'is_end.*false\|is_end":false\|is_end=false' "${log_file}" 2>/dev/null || echo 0)"
    is_end_true_count="$(grep -c 'is_end.*true\|is_end":true\|is_end=true' "${log_file}" 2>/dev/null || echo 0)"
    update_bubble_count="$(grep -c 'updateBubble' "${log_file}" 2>/dev/null || echo 0)"

    cat > "${summary_file}" <<EOF
{
  "experiment": "H2C-PostTurn",
  "timestamp": "${ts}",
  "log_file": "$(basename "${log_file}")",
  "metrics": {
    "chatCallback_count": ${chat_callback_count},
    "is_end_false_count": ${is_end_false_count},
    "is_end_true_count": ${is_end_true_count},
    "updateBubble_count": ${update_bubble_count}
  },
  "expected": {
    "is_end_true_count": 1,
    "is_end_false_count": ">=1"
  },
  "pass_criteria": {
    "H2C-PostTurn-1": $([ "${is_end_true_count}" -eq 1 ] && echo true || echo false),
    "H2C-PostTurn-2": $([ "${is_end_false_count}" -ge 1 ] && echo true || echo false)
  }
}
EOF

    echo "=============================================="
    echo " H2C-PostTurn 计数报告"
    echo "=============================================="
    echo "  chatCallback 关键词: ${chat_callback_count}"
    echo "  is_end=false:        ${is_end_false_count}"
    echo "  is_end=true:         ${is_end_true_count}  (期望: 1)"
    echo "  updateBubble:        ${update_bubble_count}"
    echo ""
    if [ "${is_end_true_count}" -eq 1 ]; then
        echo "  ✓ H2C-PostTurn-1 通过: is_end=true 唯一"
    else
        echo "  ✗ H2C-PostTurn-1 失败: is_end=true 计数=${is_end_true_count} (期望 1)"
    fi
    echo ""
    echo " 报告: ${summary_file}"
    echo "=============================================="
}

cmd_dbcheck() {
    if [ ! -f "${DB_PATH}" ]; then
        echo "ERROR: 聊天数据库不存在: ${DB_PATH}" >&2
        exit 1
    fi

    echo "INFO: 查询聊天数据库 RECORD 表"
    local ts db_snapshot_file
    ts="$(date +%Y%m%d_%H%M%S)"
    db_snapshot_file="${OUT_DIR}/postturn_${ts}.db_snapshots.json"

    local rowid_min rowid_max row_count
    rowid_min="$(sqlite3 "${DB_PATH}" "SELECT MIN(rowid) FROM RECORD;" 2>/dev/null || echo "N/A")"
    rowid_max="$(sqlite3 "${DB_PATH}" "SELECT MAX(rowid) FROM RECORD;" 2>/dev/null || echo "N/A")"
    row_count="$(sqlite3 "${DB_PATH}" "SELECT COUNT(*) FROM RECORD;" 2>/dev/null || echo "N/A")"

    # 最新 5 条记录, 从 message JSON 中提取 author 和 message 内容
    local latest_records
    latest_records="$(sqlite3 -separator ' | ' "${DB_PATH}" \
        "SELECT rowid,
                json_extract(message, '$.author') as author,
                json_extract(message, '$.isEnd') as is_end,
                length(message) as msg_len,
                substr(json_extract(message, '$.message'), 1, 80) as preview
         FROM RECORD ORDER BY rowid DESC LIMIT 5;" 2>/dev/null)"

    # 统计用户消息和 Bot 回复数量
    local user_count bot_count
    user_count="$(sqlite3 "${DB_PATH}" \
        "SELECT COUNT(*) FROM RECORD WHERE json_extract(message, '$.author') = 'User';" 2>/dev/null || echo "0")"
    bot_count="$(sqlite3 "${DB_PATH}" \
        "SELECT COUNT(*) FROM RECORD WHERE json_extract(message, '$.author') = 'Bot';" 2>/dev/null || echo "0")"

    # 统计 isEnd=true 的记录数 (即回合结束事件)
    local is_end_count
    is_end_count="$(sqlite3 "${DB_PATH}" \
        "SELECT COUNT(*) FROM RECORD WHERE json_extract(message, '$.isEnd') = 1;" 2>/dev/null || echo "0")"

    cat > "${db_snapshot_file}" <<EOF
{
  "experiment": "H2C-PostTurn-dbcheck",
  "timestamp": "${ts}",
  "db_path": "${DB_PATH}",
  "record_table": {
    "rowid_min": "${rowid_min}",
    "rowid_max": "${rowid_max}",
    "row_count": "${row_count}",
    "user_messages": ${user_count},
    "bot_messages": ${bot_count},
    "is_end_true_count": ${is_end_count}
  },
  "note": "实验前后对比 rowid 变化, 期望新增 2 行 (用户+助手); isEnd=true 对应 TurnFinalizedEvent",
  "latest_records": [
$(echo "${latest_records}" | while IFS= read -r line; do
    echo "    \"${line}\","
done | sed '$ s/,$//')
  ]
}
EOF

    echo "=============================================="
    echo " RECORD 表快照"
    echo "=============================================="
    echo "  rowid 范围: ${rowid_min} ~ ${rowid_max}"
    echo "  总行数:     ${row_count}"
    echo "  用户消息:   ${user_count}"
    echo "  Bot 回复:   ${bot_count}"
    echo "  isEnd=true: ${is_end_count}  (对应 TurnFinalizedEvent)"
    echo ""
    echo "  最新 5 条记录:"
    echo "  rowid | author | isEnd | len | preview"
    echo "  ------|--------|-------|-----|--------"
    echo "${latest_records}" | while IFS= read -r line; do
        echo "  ${line}"
    done
    echo ""
    echo " 快照: ${db_snapshot_file}"
    echo "=============================================="
}

case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    dbcheck)
        cmd_dbcheck
        ;;
    *)
        echo "用法: $0 {start|stop|dbcheck}"
        echo ""
        echo "  start   - 启动日志捕获"
        echo "  stop    - 停止捕获并生成计数报告"
        echo "  dbcheck - 查询 RECORD 表快照"
        exit 1
        ;;
esac
