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

# 确定实际登录用户的 HOME (避免 sudo 下 $HOME 变成 /root)
get_user_home() {
    if [ -n "${SUDO_USER:-}" ]; then
        local uhome
        uhome="$(eval echo "~${SUDO_USER}" 2>/dev/null || true)"
        if [ -d "${uhome}" ]; then
            echo "${uhome}"
            return
        fi
    fi
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

# 状态文件 (PID/meta/timestamp) 统一放到真实用户 HOME 下, 避免 sudo/非sudo 混用割裂
STATE_DIR="${USER_HOME}/.d2c-probe-state"
mkdir -p "${STATE_DIR}"

TIMESTAMP_FILE="${STATE_DIR}/postturn_last_timestamp"
PID_FILE="${STATE_DIR}/postturn_capture.pid"
META_FILE="${STATE_DIR}/postturn_capture.meta"

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

DB_PATH="${USER_HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"

# AI 助手进程名
AI_PROC_NAME="kylin-aiassistant"

# 安全地将字符串转为非负整数: 去掉非数字和多余换行, 空值默认 0
to_int() {
    local raw="$1"
    # 取最后一行（抵制 grep -c ... || echo 0 导致的双行输出），去除非数字字符
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
    # 麒麟 V11 实际进程 cmdline: /opt/apps/cn.kylin.kylin-aiassistant/files/bin/kylin-aiassistant
    # bash launcher cmdline:    /bin/bash /opt/apps/kaiming/bin/cn.kylin.kylin-aiassistant ...
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

# AI Runtime 服务进程名 (模型请求 + 流式回调 is_end 在这里产生)
AI_RUNTIME_NAME="kylin-ai-runtime"

find_runtime_pid() {
    # 定位 kylin-ai-runtime 进程 (模型推理服务, 拥有 assistant.sock)
    local pid
    pid="$(pgrep -f "${AI_RUNTIME_NAME}" 2>/dev/null | head -n 1 || true)"
    if [ -n "${pid}" ]; then
        echo "${pid}"
    fi
}

cmd_start() {
    local pid
    pid="$(find_ai_pid)"
    if [ -z "${pid}" ]; then
        echo "ERROR: 未找到 ${AI_PROC_NAME} 进程, 请先启动 AI 助手" >&2
        exit 1
    fi
    echo "INFO: AI 助手 PID = ${pid}"

    # 同时定位 kylin-ai-runtime (模型推理服务, is_end 流式回调在此产生)
    local runtime_pid
    runtime_pid="$(find_runtime_pid)"
    if [ -n "${runtime_pid}" ]; then
        echo "INFO: AI Runtime PID = ${runtime_pid} (将同时跟踪以捕获 is_end 流式回调)"
    else
        echo "WARN: 未找到 ${AI_RUNTIME_NAME} 进程, 仅跟踪 AI 主进程 (可能漏掉 is_end 流式回调)"
    fi

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
    echo "INFO: 捕获范围: write,writev,sendmsg,sendto,recvmsg,read,poll (扩至常见 IPC)"

    # strace 独立 nohup 直接写日志文件
    # - 同时 attach 到 AI 主进程 + Runtime 服务进程 (strace 支持多个 -p)
    # - -f 跟踪子进程/线程
    # - -s 16384 (覆盖 memory_context 大 JSON)
    # - -yy (打印 socket 路径/文件描述符类型, 便于调试)
    local strace_args=(-p "${pid}" -f -s 16384 -yy \
        -e trace=write,writev,sendmsg,sendto,recvmsg,read,poll)
    if [ -n "${runtime_pid}" ] && [ "${runtime_pid}" != "${pid}" ]; then
        strace_args=(-p "${pid}" -p "${runtime_pid}" -f -s 16384 -yy \
            -e trace=write,writev,sendmsg,sendto,recvmsg,read,poll)
    fi

    nohup strace "${strace_args[@]}" \
        > "${LOG_FILE}" 2>&1 </dev/null &
    local cap_pid=$!
    disown "${cap_pid}" 2>/dev/null || true

    # 验证 strace 进程已启动且确实 attach 到目标 AI PID
    sleep 2
    if ! kill -0 "${cap_pid}" 2>/dev/null; then
        echo "ERROR: strace 启动失败, 请检查 strace 是否可用 (sudo apt install strace) 或是否需要 sudo 权限" >&2
        echo "HINT: 如果 strace -p 需要 root 或 ptrace_scope=2, 使用: sudo $0 start" >&2
        echo "HINT: 可临时放宽:  sudo sysctl -w kernel.yama.ptrace_scope=0" >&2
        exit 1
    fi
    # 再确认 strace 正在监控目标 PID (含 runtime_pid 时两个都要校验)
    local attached=""
    attached="$(ps -o args= -p "${cap_pid}" 2>/dev/null | grep -o -- "-p *${pid}" || true)"
    if [ -z "${attached}" ]; then
        echo "WARN: strace PID=${cap_pid} 启动, 但无法确认 attach 到 AI PID=${pid}; 请在聊天后检查日志大小" >&2
    else
        echo "INFO: 已确认 strace attach 到 AI PID=${pid}"
    fi
    if [ -n "${runtime_pid}" ] && [ "${runtime_pid}" != "${pid}" ]; then
        local attached_rt=""
        attached_rt="$(ps -o args= -p "${cap_pid}" 2>/dev/null | grep -o -- "-p *${runtime_pid}" || true)"
        if [ -n "${attached_rt}" ]; then
            echo "INFO: 已确认 strace attach 到 Runtime PID=${runtime_pid}"
        else
            echo "WARN: 无法确认 strace attach 到 Runtime PID=${runtime_pid} (可能已成功, ps 输出截断)"
        fi
    fi

    # 写入 PID 和元信息 (strace PID + 目标 AI PID + Runtime PID + 日志路径 + 时间戳)
    echo "${cap_pid}" > "${PID_FILE}"
    cat > "${META_FILE}" <<EOF
strace_pid=${cap_pid}
ai_pid=${pid}
runtime_pid=${runtime_pid:-}
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
    # 只清理本次采集 PID 的子进程；不得以进程名宽匹配误杀并行采集任务。
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

    # grep -c 当无匹配时 exit code=1, 直接 `|| echo 0` 会产生双行输出;
    # 统一用 to_int() 清洗为单行非负整数
    #
    # 关键: 同一次 is_end 事件会被 kylin-ai-runtime 写入 3 个地方:
    #   1) write(1</dev/null>)                    — stdout (丢弃)
    #   2) write(4<.../kylin-ai-runtime.log>)     — 本地日志文件 (副本)
    #   3) sendmsg(N<...assistant.sock>)          — DBus 业务回调 (真正的事件)
    # 只有 sendmsg 到 assistant.sock 的才是真正的 TurnFinalized 业务事件,
    # 所以优先精确匹配 "sendmsg + assistant.sock + is_end" 的行。
    # chatCallback 关键词实际不存在, 真正的 DBus signal 名是 ChatResult。
    local raw_chat raw_endf raw_endt raw_upd
    local chat_callback_count is_end_false_count is_end_true_count update_bubble_count
    local match_mode="precise"
    raw_chat="$(grep -cE 'sendmsg.*assistant\.sock.*ChatResult'       "${LOG_FILE}" 2>/dev/null || echo 0)"
    raw_endf="$(grep -cE 'sendmsg.*assistant\.sock.*is_end.*false'    "${LOG_FILE}" 2>/dev/null || echo 0)"
    raw_endt="$(grep -cE 'sendmsg.*assistant\.sock.*is_end.*true'     "${LOG_FILE}" 2>/dev/null || echo 0)"
    raw_upd="$(grep -cE 'sendmsg.*assistant\.sock.*updateBubble'      "${LOG_FILE}" 2>/dev/null || echo 0)"
    chat_callback_count="$(to_int "${raw_chat}")"
    is_end_false_count="$(to_int "${raw_endf}")"
    is_end_true_count="$(to_int  "${raw_endt}")"
    update_bubble_count="$(to_int   "${raw_upd}")"

    # 如果精确匹配 (sendmsg+assistant.sock) 全为 0, 回退到宽松匹配
    # (兼容 assistant.sock 路径变化或 -s 截断导致 sendmsg 行不含 is_end 的情况)
    local total_hits=0
    total_hits=$(( chat_callback_count + is_end_false_count + is_end_true_count + update_bubble_count ))
    if [ "${total_hits}" -eq 0 ]; then
        match_mode="fallback"
        echo "WARN: 精确匹配 (sendmsg+assistant.sock) 0 命中; 回退到宽松匹配"
        raw_chat="$(grep -cE 'ChatResult'                                          "${LOG_FILE}" 2>/dev/null || echo 0)"
        raw_endf="$(grep -cE 'is_end.*false|is_end":false|is_end=false'            "${LOG_FILE}" 2>/dev/null || echo 0)"
        raw_endt="$(grep -cE 'is_end.*true|is_end":true|is_end=true'               "${LOG_FILE}" 2>/dev/null || echo 0)"
        raw_upd="$(grep -c 'updateBubble'                                          "${LOG_FILE}" 2>/dev/null || echo 0)"
        chat_callback_count="$(to_int "${raw_chat}")"
        is_end_false_count="$(to_int "${raw_endf}")"
        is_end_true_count="$(to_int  "${raw_endt}")"
        update_bubble_count="$(to_int   "${raw_upd}")"
        total_hits=$(( chat_callback_count + is_end_false_count + is_end_true_count + update_bubble_count ))
    fi

    # 如果宽松匹配仍为 0, 给出调试建议
    if [ "${total_hits}" -eq 0 ]; then
        echo "WARN: 宽松匹配也为 0; 尝试搜索所有含 chat / bubble / end 字样的系统调用"
        local fallback
        fallback="$(grep -ciE 'chat|bubble|end|stream|token' "${LOG_FILE}" 2>/dev/null || true)"
        fallback="$(to_int "${fallback}")"
        if [ "${fallback}" -gt 0 ]; then
            echo "INFO: 放宽匹配命中 ${fallback} 行 (说明有相关流量, 只是关键词不同; 可人工 inspect)"
        else
            echo "WARN: 放宽匹配也为 0, 很可能 strace 未真正 attach 到 AI 进程"
            echo "HINT: 1) 下次 start 前先 killall -9 strace 清理残留; 2) 改用 sudo 运行 start;"
            echo "HINT: 3) sudo sysctl -w kernel.yama.ptrace_scope=0; 4) 确认 AI PID 确实正确:"
            echo "HINT:    pgrep -af kylin-aiassistant  (挑含 /files/bin/ 的实际进程)"
        fi
    fi

    # fallback 模式下计数可能包含 3x 重复 (stdout + log + dbus), 不再自动除以 3
    # 保留原始计数不变, 仅在 stdout 打印提示供人工核对
    if [ "${match_mode}" = "fallback" ]; then
        echo "WARN: fallback模式计数可能包含3x重复(stdout+log+dbus)，请人工核对"
    fi

    # 保存原始计数 (precise 模式下 raw == count; fallback 模式下 raw 保留未去重的值)
    raw_is_end_false_count="${is_end_false_count}"
    raw_is_end_true_count="${is_end_true_count}"

    cat > "${SUMMARY_FILE}" <<EOF
{
  "experiment": "H2C-PostTurn",
  "timestamp": "${TIMESTAMP}",
  "log_file": "$(basename "${LOG_FILE}")",
  "raw_log_bytes": ${log_size},
  "match_mode": "${match_mode}",
  "metrics": {
    "ChatResult_signal_count": ${chat_callback_count},
    "is_end_false_count": ${is_end_false_count},
    "is_end_true_count": ${is_end_true_count},
    "updateBubble_count": ${update_bubble_count},
    "raw_is_end_false_count": ${raw_is_end_false_count},
    "raw_is_end_true_count": ${raw_is_end_true_count}
  },
  "expected": {
    "is_end_true_count": 1,
    "is_end_false_count": ">=1"
  },
  "pass_criteria": {
    "H2C-PostTurn-1": $([ "${is_end_true_count}" -eq 1 ] && echo true || echo false),
    "H2C-PostTurn-2": $([ "${is_end_false_count}" -ge 1 ] && echo true || echo false)
  },
  "match_mode": "${match_mode}",
  "dedupe_basis": "precise模式仅统计sendmsg到assistant.sock的DBus回调; fallback模式保留原始计数不自动去重"
}
EOF

    echo "=============================================="
    echo " H2C-PostTurn 计数报告"
    echo "=============================================="
    echo "  原始日志字节:         ${log_size}"
    echo "  匹配模式:             ${match_mode}"
    echo "  ChatResult 信号:     ${chat_callback_count}"
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

# diagnose: 当 stop 报告 0 命中时, 用来排查 strace 到底抓到了什么
# 用法: ./d2c_postturn_isend_counter.sh diagnose [log_file]
#   不传 log_file 则使用最近一次的 LOG_FILE
cmd_diagnose() {
    local target_log="${1:-}"
    if [ -z "${target_log}" ]; then
        local ts
        ts="$(get_or_set_timestamp)"
        target_log="${OUT_DIR}/postturn_${ts}.log"
    fi
    if [ ! -f "${target_log}" ]; then
        echo "ERROR: 日志文件不存在: ${target_log}" >&2
        echo "HINT: 请传入日志路径, 或先运行 start/stop" >&2
        exit 1
    fi

    local size
    size="$(wc -c < "${target_log}" 2>/dev/null || echo 0)"
    size="$(to_int "${size}")"
    local lines
    lines="$(wc -l < "${target_log}" 2>/dev/null || echo 0)"
    lines="$(to_int "${lines}")"

    echo "=============================================="
    echo " strace 日志诊断"
    echo "=============================================="
    echo "  文件:     ${target_log}"
    echo "  大小:     ${size} bytes"
    echo "  行数:     ${lines}"
    echo ""

    if [ "${size}" -lt 200 ]; then
        echo "⚠ 日志过小 (${size} bytes), 说明 strace 虽然启动了, 但"
        echo "  目标 AI 进程在聊天期间未产生被跟踪的系统调用。"
        echo "  常见原因:"
        echo "  1) 聊天流量走子进程/线程 (strace -f 应能捕获, 已加);"
        echo "  2) 聊天流量走 mmap 共享内存而非 write/sendmsg;"
        echo "  3) AI 助手把请求委托给独立的 services 子进程 (kaiming services)"
        echo ""
        echo "  完整日志内容如下:"
        echo "  --------------------------------------------"
        cat "${target_log}"
        echo "  --------------------------------------------"
        echo ""
        echo "  建议: 运行下面的命令列出所有 kylin 相关进程, 找出"
        echo "        真正处理模型请求的那个进程, 重新 start:"
        echo "    pgrep -af kylin"
        echo "    pgrep -af 'ai-runtime|aiservice|kylin-ai'"
        echo ""
        echo "  也可以全进程跟踪 5 秒看哪个进程有 IPC 流量:"
        echo "    for p in \$(pgrep -f kylin); do"
        echo "      echo \"=== PID \$p ===\""
        echo "      sudo timeout 5 strace -p \$p -f -e trace=write,sendmsg,recvmsg -c 2>&1 | tail -20"
        echo "    done"
    else
        echo "✓ 日志大小正常 (${size} bytes), 前 20 行预览:"
        echo "  --------------------------------------------"
        head -n 20 "${target_log}" | sed 's/^/  /'
        echo "  --------------------------------------------"
        echo ""
        echo "  系统调用类型分布:"
        # 提取系统调用名 (strace 输出格式: PID syscall(args) = ret)
        grep -oE '^[0-9]+ +[a-zA-Z0-9_]+' "${target_log}" 2>/dev/null \
            | awk '{print $2}' | sort | uniq -c | sort -rn | head -15 \
            | sed 's/^/    /'
        echo ""
        echo "  含 chat/is_end/bubble 关键词的行 (前 10):"
        grep -nE 'chat|is_end|bubble|stream|token' "${target_log}" 2>/dev/null \
            | head -10 | sed 's/^/    /'
    fi
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
    diagnose)
        cmd_diagnose "${2:-}"
        ;;
    *)
        echo "用法: $0 {start|stop|dbcheck|diagnose [log_file]}"
        echo ""
        echo "  start    - 启动日志捕获"
        echo "  stop     - 停止捕获并生成计数报告"
        echo "  dbcheck  - 查询 RECORD 表快照"
        echo "  diagnose - 分析最近一次日志, 排查 0 命中原因"
        exit 1
        ;;
esac
