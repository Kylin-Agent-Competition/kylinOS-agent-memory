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

TIMESTAMP_FILE="${OUT_DIR}/.postturn_last_timestamp"
PID_FILE="${OUT_DIR}/postturn_capture.pid"
META_FILE="${OUT_DIR}/postturn_capture.meta"

# 每次 start 生成一个时间戳并持久化, stop/dbcheck 复用
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
LOG_FILE="${OUT_DIR}/postturn_${TIMESTAMP}.log"
SUMMARY_FILE="${OUT_DIR}/postturn_${TIMESTAMP}.summary.json"
DB_SNAPSHOT_FILE="${OUT_DIR}/postturn_${TIMESTAMP}.db_snapshots.json"

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

    # 启动时生成新时间戳
    TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    TIMESTAMP="$(get_or_set_timestamp "${TIMESTAMP}")"
    LOG_FILE="${OUT_DIR}/postturn_${TIMESTAMP}.log"

    echo "INFO: 启动 strace 日志捕获 -> ${LOG_FILE}"
    echo "INFO: strace 直接写入原始日志 (不经过 grep 管道), stop 时离线统计"

    # strace 独立 nohup 直接写日志文件, 不经过 shell 管道
    # 这样 $! 拿到的是 strace 自身 PID, 且进程完全脱离终端
    nohup strace -p "${pid}" -f -s 4096 -e trace=write,recvmsg \
        > "${LOG_FILE}" 2>&1 </dev/null &
    local cap_pid=$!
    disown "${cap_pid}" 2>/dev/null || true

    # 验证 strace 进程已启动
    sleep 1
    if ! kill -0 "${cap_pid}" 2>/dev/null; then
        echo "ERROR: strace 启动失败, 请检查 strace 是否可用 (sudo apt install strace) 或是否需要 sudo 权限" >&2
        echo "HINT: 如果 strace -p 需要 root, 使用: sudo $0 start" >&2
        exit 1
    fi

    # 写入 PID 和元信息 (strace PID + 目标 AI PID + 日志路径 + 时间戳)
    echo "${cap_pid}" > "${PID_FILE}"
    cat > "${META_FILE}" <<EOF
strace_pid=${cap_pid}
ai_pid=${pid}
log_file=${LOG_FILE}
timestamp=${TIMESTAMP}
started_at=$(date '+%Y-%m-%d %H:%M:%S')
EOF

    echo "INFO: strace 进程 PID = ${cap_pid} (已脱离终端, 可以继续输入命令)"
    echo "INFO: 现在请在 AI 助手中发起一次普通文本问答"
    echo "INFO: 完成后运行: $0 stop"
}

cmd_stop() {
    if [ ! -f "${PID_FILE}" ]; then
        echo "ERROR: 未找到运行中的捕获任务" >&2
        exit 1
    fi
    # 从 meta 文件读取 start 时的时间戳和日志路径, 确保 stop 与 start 一致
    local cap_pid log_file_from_meta ts_from_meta
    cap_pid="$(cat "${PID_FILE}")"
    if [ -f "${META_FILE}" ]; then
        log_file_from_meta="$(grep '^log_file=' "${META_FILE}" | cut -d= -f2-)"
        ts_from_meta="$(grep '^timestamp=' "${META_FILE}" | cut -d= -f2-)"
        if [ -n "${ts_from_meta}" ]; then
            TIMESTAMP="${ts_from_meta}"
            get_or_set_timestamp "${TIMESTAMP}" >/dev/null
            LOG_FILE="${OUT_DIR}/postturn_${TIMESTAMP}.log"
            SUMMARY_FILE="${OUT_DIR}/postturn_${TIMESTAMP}.summary.json"
            DB_SNAPSHOT_FILE="${OUT_DIR}/postturn_${TIMESTAMP}.db_snapshots.json"
        fi
        if [ -n "${log_file_from_meta}" ] && [ -f "${log_file_from_meta}" ]; then
            LOG_FILE="${log_file_from_meta}"
        fi
    fi

    echo "INFO: 停止 strace 进程 ${cap_pid}"
    # 终止 strace 及其可能的子进程
    kill "${cap_pid}" 2>/dev/null || true
    pkill -P "${cap_pid}" 2>/dev/null || true
    # 再给个 SIGTERM 给可能残留的 strace 进程 (strace -f 会 fork 监控子线程)
    pkill -f "strace -p.*kylin" 2>/dev/null || true
    sleep 0.5
    rm -f "${PID_FILE}"

    if [ ! -f "${LOG_FILE}" ]; then
        echo "ERROR: 日志文件不存在: ${LOG_FILE}" >&2
        exit 1
    fi
    local log_size
    log_size="$(wc -c < "${LOG_FILE}" 2>/dev/null || echo 0)"
    echo "INFO: 原始日志大小: ${log_size} bytes"
    echo "INFO: 生成计数报告 -> ${SUMMARY_FILE}"

    local chat_callback_count is_end_false_count is_end_true_count update_bubble_count
    chat_callback_count="$(grep -c 'chatCallback' "${LOG_FILE}" || echo 0)"
    is_end_false_count="$(grep -c 'is_end.*false\|is_end":false\|is_end=false' "${LOG_FILE}" || echo 0)"
    is_end_true_count="$(grep -c 'is_end.*true\|is_end":true\|is_end=true' "${LOG_FILE}" || echo 0)"
    update_bubble_count="$(grep -c 'updateBubble' "${LOG_FILE}" || echo 0)"

    cat > "${SUMMARY_FILE}" <<EOF
{
  "experiment": "H2C-PostTurn",
  "timestamp": "${TIMESTAMP}",
  "log_file": "$(basename "${LOG_FILE}")",
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
    echo " 报告: ${SUMMARY_FILE}"
    echo "=============================================="
}

cmd_dbcheck() {
    if [ ! -f "${DB_PATH}" ]; then
        echo "ERROR: 聊天数据库不存在: ${DB_PATH}" >&2
        exit 1
    fi

    echo "INFO: 查询聊天数据库 RECORD 表"
    local rowid_min rowid_max row_count
    rowid_min="$(sqlite3 "${DB_PATH}" "SELECT MIN(rowid) FROM RECORD;" 2>/dev/null || echo "N/A")"
    rowid_max="$(sqlite3 "${DB_PATH}" "SELECT MAX(rowid) FROM RECORD;" 2>/dev/null || echo "N/A")"
    row_count="$(sqlite3 "${DB_PATH}" "SELECT COUNT(*) FROM RECORD;" 2>/dev/null || echo "N/A")"

    cat > "${DB_SNAPSHOT_FILE}" <<EOF
{
  "experiment": "H2C-PostTurn-dbcheck",
  "timestamp": "${TIMESTAMP}",
  "db_path": "${DB_PATH}",
  "record_table": {
    "rowid_min": "${rowid_min}",
    "rowid_max": "${rowid_max}",
    "row_count": "${row_count}"
  },
  "note": "实验前后对比 rowid 变化, 期望新增 2 行 (用户+助手)"
}
EOF

    echo "=============================================="
    echo " RECORD 表快照"
    echo "=============================================="
    echo "  rowid 范围: ${rowid_min} ~ ${rowid_max}"
    echo "  总行数:     ${row_count}"
    echo ""
    echo " 快照: ${DB_SNAPSHOT_FILE}"
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
