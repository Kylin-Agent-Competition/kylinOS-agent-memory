#!/usr/bin/env bash
# D2-C 实验 C: H2C-Tool 真实 Tool 事件观察只读脚本
#
# 目标: 捕获真实 Tool 成功/失败/取消事件, 验证 Prompt Skill 不被误判
# 关联: AGT-004 (真实 Tool Result, PARTIAL/E2·E4), TD-007
# 依据: 02 文档 §10.3 Tool Result Adapter, §16.15 步骤 14
#
# 用法:
#   ./d2c_tool_event_observer.sh start   # 启动 Tool 事件观察
#   ./d2c_tool_event_observer.sh stop    # 停止观察并生成报告
#
# 安全声明: 只读观察脚本, 不修改 AI 助手进程、数据库或配置
# KYSEC: 如需执行, 对本脚本设置单文件 verified

set -euo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${PROBE_DIR}/out"
mkdir -p "${OUT_DIR}"

# 状态文件统一放到 $HOME 下, 避免 sudo 与非 sudo 混用时权限冲突
STATE_DIR="${HOME}/.d2c-probe-state"
mkdir -p "${STATE_DIR}"

TIMESTAMP_FILE="${STATE_DIR}/tool_last_timestamp"
META_FILE="${STATE_DIR}/tool_capture.meta"
PID_FILE="${STATE_DIR}/tool_capture.pid"

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
RAW_LOG_FILE="${OUT_DIR}/tool_${TIMESTAMP}.raw.log"
LOG_FILE="${OUT_DIR}/tool_${TIMESTAMP}.log"
SUMMARY_FILE="${OUT_DIR}/tool_${TIMESTAMP}.summary.json"

AI_PROC_NAME="kylin-aiassistant"

# AI Runtime 服务进程名 (Tool 执行结果通过 Runtime 回调上报)
AI_RUNTIME_NAME="kylin-ai-runtime"

# Tool 事件关键词 (基于源码 sendToolMessage 等)
TOOL_KEYWORDS="sendToolMessage|tool_call|tool_result|tool_use|tool_name|tool_call_id|function_call"

# Prompt Skill 关键词 (用于验证不被误判)
PROMPT_SKILL_KEYWORDS="translate|翻译|polish|润色|summarize|总结|rewrite|改写"

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

find_runtime_pid() {
    # 定位 kylin-ai-runtime 进程 (Tool 执行结果回调经 Runtime 上报)
    local pid
    pid="$(pgrep -f "${AI_RUNTIME_NAME}" 2>/dev/null | head -n 1 || true)"
    if [ -n "${pid}" ]; then
        echo "${pid}"
    fi
}

reload_paths() {
    local ts_from_meta=""
    if [ -f "${META_FILE}" ]; then
        ts_from_meta="$(grep '^timestamp=' "${META_FILE}" | cut -d= -f2-)"
    fi
    if [ -n "${ts_from_meta}" ]; then
        TIMESTAMP="${ts_from_meta}"
    fi
    RAW_LOG_FILE="${OUT_DIR}/tool_${TIMESTAMP}.raw.log"
    LOG_FILE="${OUT_DIR}/tool_${TIMESTAMP}.log"
    SUMMARY_FILE="${OUT_DIR}/tool_${TIMESTAMP}.summary.json"
}

cmd_start() {
    reload_paths
    local pid
    pid="$(find_ai_pid)"
    if [ -z "${pid}" ]; then
        echo "ERROR: 未找到 ${AI_PROC_NAME} 进程" >&2
        exit 1
    fi
    echo "INFO: AI 助手 PID = ${pid}"

    # 同时定位 kylin-ai-runtime (Tool 执行结果回调经 Runtime 上报)
    local runtime_pid
    runtime_pid="$(find_runtime_pid)"
    if [ -n "${runtime_pid}" ]; then
        echo "INFO: AI Runtime PID = ${runtime_pid} (将同时跟踪以捕获 Tool 回调)"
    else
        echo "WARN: 未找到 ${AI_RUNTIME_NAME} 进程, 仅跟踪 AI 主进程 (可能漏掉 Tool 回调证据)"
    fi

    if [ -f "${PID_FILE}" ]; then
        echo "ERROR: 已有捕获任务运行中" >&2
        exit 1
    fi

    # 每次 start 生成新时间戳
    TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    TIMESTAMP="$(get_or_set_timestamp "${TIMESTAMP}")"
    reload_paths

    echo "INFO: 启动 Tool 事件观察 (strace 原始日志) -> ${RAW_LOG_FILE}"
    echo "INFO: strace 直接写入原始日志 (不经过 grep 管道), stop 时离线过滤"
    echo "INFO: 捕获范围: write,writev,sendmsg,sendto,recvmsg,read,poll (扩至常见 IPC)"

    # strace 独立 nohup 直接写原始日志文件
    # - 同时 attach 到 AI 主进程 + Runtime 服务进程 (strace 支持多个 -p)
    # - -f 跟踪子进程/线程
    # - -s 32768 (含 tool_call 大 JSON)
    # - -yy 打印 socket 路径
    local strace_args=(-p "${pid}" -f -s 32768 -yy \
        -e trace=write,writev,sendmsg,sendto,recvmsg,read,poll)
    if [ -n "${runtime_pid}" ] && [ "${runtime_pid}" != "${pid}" ]; then
        strace_args=(-p "${pid}" -p "${runtime_pid}" -f -s 32768 -yy \
            -e trace=write,writev,sendmsg,sendto,recvmsg,read,poll)
    fi

    nohup strace "${strace_args[@]}" \
        > "${RAW_LOG_FILE}" 2>&1 </dev/null &
    local cap_pid=$!
    disown "${cap_pid}" 2>/dev/null || true

    sleep 2
    if ! kill -0 "${cap_pid}" 2>/dev/null; then
        echo "ERROR: strace 启动失败, 请检查 strace 是否可用 (sudo apt install strace) 或是否需要 sudo 权限" >&2
        echo "HINT: 如果 strace -p 需要 root 或 ptrace_scope=2, 使用: sudo $0 start" >&2
        echo "HINT: 可临时放宽:  sudo sysctl -w kernel.yama.ptrace_scope=0" >&2
        exit 1
    fi
    local attached=""
    attached="$(ps -o args= -p "${cap_pid}" 2>/dev/null | grep -o -- "-p *${pid}" || true)"
    if [ -z "${attached}" ]; then
        echo "WARN: strace PID=${cap_pid} 已启动, 但无法确认 attach 到 AI PID=${pid}; 请检查日志是否增长" >&2
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

    echo "${cap_pid}" > "${PID_FILE}"
    cat > "${META_FILE}" <<EOF
strace_pid=${cap_pid}
ai_pid=${pid}
runtime_pid=${runtime_pid:-}
raw_log=${RAW_LOG_FILE}
filtered_log=${LOG_FILE}
timestamp=${TIMESTAMP}
started_at=$(date '+%Y-%m-%d %H:%M:%S')
EOF

    echo "INFO: strace 进程 PID = ${cap_pid} (已脱离终端, 可以继续输入命令)"
    echo ""
    echo "=============================================="
    echo " 请按顺序执行以下场景:"
    echo "=============================================="
    echo "  [场景 C2] 成功 Tool: 触发一个会成功的 Tool"
    echo "           (如打开应用、查询天气)"
    echo "  [场景 C3] 失败 Tool: 触发一个会失败的 Tool"
    echo "           (如打开不存在的应用)"
    echo "  [场景 C4] 取消 Tool: 触发 Tool 后点击停止"
    echo "  [场景 C5] Prompt Skill 对照: 触发翻译/润色/总结"
    echo "=============================================="
    echo ""
    echo "  完成后运行: $0 stop"
}

cmd_stop() {
    if [ ! -f "${PID_FILE}" ]; then
        echo "ERROR: 未找到运行中的捕获任务" >&2
        exit 1
    fi
    reload_paths
    local cap_pid raw_log_from_meta filtered_log_from_meta
    cap_pid="$(cat "${PID_FILE}")"
    if [ -f "${META_FILE}" ]; then
        raw_log_from_meta="$(grep '^raw_log=' "${META_FILE}" | cut -d= -f2-)"
        filtered_log_from_meta="$(grep '^filtered_log=' "${META_FILE}" | cut -d= -f2-)"
        [ -n "${raw_log_from_meta}" ] && RAW_LOG_FILE="${raw_log_from_meta}"
        [ -n "${filtered_log_from_meta}" ] && LOG_FILE="${filtered_log_from_meta}"
    fi

    echo "INFO: 停止 strace 进程 ${cap_pid}"
    kill "${cap_pid}" 2>/dev/null || true
    pkill -P "${cap_pid}" 2>/dev/null || true
    pkill -f "strace -p.*kylin" 2>/dev/null || true
    sleep 0.5
    rm -f "${PID_FILE}"

    if [ ! -f "${RAW_LOG_FILE}" ]; then
        echo "ERROR: 原始日志文件不存在: ${RAW_LOG_FILE}" >&2
        exit 1
    fi
    local log_size
    log_size="$(wc -c < "${RAW_LOG_FILE}" 2>/dev/null || echo 0)"
    echo "INFO: 原始 strace 日志大小: ${log_size} bytes"

    # 离线过滤: 从原始日志生成过滤后的日志
    echo "INFO: 从原始日志离线过滤 Tool/PromptSkill 关键词 -> ${LOG_FILE}"
    grep -E "${TOOL_KEYWORDS}|${PROMPT_SKILL_KEYWORDS}" "${RAW_LOG_FILE}" \
        > "${LOG_FILE}" 2>/dev/null || true

    echo "INFO: 生成 Tool 事件报告 -> ${SUMMARY_FILE}"

    # 统计各类事件 (to_int 清洗避免 "需要整数表达式")
    local raw_tc raw_tr raw_st raw_ps
    raw_tc="$(grep -cE 'tool_call|tool_use|function_call' "${LOG_FILE}" 2>/dev/null || echo 0)"
    raw_tr="$(grep -cE 'tool_result'                    "${LOG_FILE}" 2>/dev/null || echo 0)"
    raw_st="$(grep -cE 'sendToolMessage'                "${LOG_FILE}" 2>/dev/null || echo 0)"
    raw_ps="$(grep -cE "${PROMPT_SKILL_KEYWORDS}"       "${LOG_FILE}" 2>/dev/null || echo 0)"
    local tool_call_count tool_result_count send_tool_count prompt_skill_count
    tool_call_count="$(to_int "${raw_tc}")"
    tool_result_count="$(to_int "${raw_tr}")"
    send_tool_count="$(to_int "${raw_st}")"
    prompt_skill_count="$(to_int "${raw_ps}")"

    # 判断是否捕获到独立 Tool 事件
    local tool_event_captured=false
    if [ "${tool_call_count}" -gt 0 ] || [ "${send_tool_count}" -gt 0 ]; then
        tool_event_captured=true
    fi

    cat > "${SUMMARY_FILE}" <<EOF
{
  "experiment": "H2C-Tool",
  "timestamp": "${TIMESTAMP}",
  "log_file": "$(basename "${LOG_FILE}")",
  "metrics": {
    "tool_call_count": ${tool_call_count},
    "tool_result_count": ${tool_result_count},
    "sendToolMessage_count": ${send_tool_count},
    "prompt_skill_keyword_count": ${prompt_skill_count}
  },
  "analysis": {
    "tool_event_captured": ${tool_event_captured},
    "prompt_skill_not_misjudged": "需人工核对日志中 Prompt Skill 场景是否生成 tool_call 证据"
  },
  "pass_criteria": {
    "H2C-Tool-1": "需人工核对 success_events 非空",
    "H2C-Tool-2": "需人工核对 failure_events 非空",
    "H2C-Tool-3": "需人工核对 cancelled_events 非空",
    "H2C-Tool-4": "需人工核对 Prompt Skill 未生成 tool_call"
  },
  "note": "本脚本提供日志捕获与关键词统计, 真实事件分类需人工核对日志上下文"
}
EOF

    echo "=============================================="
    echo " H2C-Tool 事件报告"
    echo "=============================================="
    echo "  tool_call 关键词:      ${tool_call_count}"
    echo "  tool_result 关键词:    ${tool_result_count}"
    echo "  sendToolMessage:       ${send_tool_count}"
    echo "  Prompt Skill 关键词:   ${prompt_skill_count}"
    echo ""
    if [ "${tool_event_captured}" = "true" ]; then
        echo "  ✓ 捕获到 Tool 事件信号"
    else
        echo "  ✗ 未捕获到独立 Tool 事件"
        echo "    可能原因: sendToolMessage 路径未确认 (TD-007)"
        echo "    建议: 改用源码分支 instrument 或 DBus 监听"
    fi
    echo ""
    echo "  报告: ${SUMMARY_FILE}"
    echo "  日志: ${LOG_FILE}"
    echo ""
    echo "  注意: 真实事件分类 (成功/失败/取消) 需人工核对日志上下文"
    echo "=============================================="
}

case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    *)
        echo "用法: $0 {start|stop}"
        echo ""
        echo "  start - 启动 Tool 事件观察"
        echo "  stop  - 停止观察并生成报告"
        exit 1
        ;;
esac
