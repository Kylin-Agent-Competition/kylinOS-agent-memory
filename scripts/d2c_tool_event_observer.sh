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

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PID_FILE="${OUT_DIR}/tool_capture.pid"
LOG_FILE="${OUT_DIR}/tool_${TIMESTAMP}.log"
SUMMARY_FILE="${OUT_DIR}/tool_${TIMESTAMP}.summary.json"

AI_PROC_NAME="kylin-aiassistant"

# Tool 事件关键词 (基于源码 sendToolMessage 等)
TOOL_KEYWORDS="sendToolMessage|tool_call|tool_result|tool_use|tool_name|tool_call_id|function_call"

# Prompt Skill 关键词 (用于验证不被误判)
PROMPT_SKILL_KEYWORDS="translate|翻译|polish|润色|summarize|总结|rewrite|改写"

find_ai_pid() {
    pgrep -f "${AI_PROC_NAME}" | head -n 1 || true
}

cmd_start() {
    local pid
    pid="$(find_ai_pid)"
    if [ -z "${pid}" ]; then
        echo "ERROR: 未找到 ${AI_PROC_NAME} 进程" >&2
        exit 1
    fi
    echo "INFO: AI 助手 PID = ${pid}"

    if [ -f "${PID_FILE}" ]; then
        echo "ERROR: 已有捕获任务运行中" >&2
        exit 1
    fi

    echo "INFO: 启动 Tool 事件观察 -> ${LOG_FILE}"
    # 跟踪 write/recvmsg, 过滤 Tool 与 Prompt Skill 关键词
    nohup strace -p "${pid}" -f -s 8192 -e trace=write,recvmsg 2>&1 \
        | grep --line-buffered -E "${TOOL_KEYWORDS}|${PROMPT_SKILL_KEYWORDS}" \
        > "${LOG_FILE}" &

    local cap_pid=$!
    echo "${cap_pid}" > "${PID_FILE}"
    echo "INFO: 捕获进程 PID = ${cap_pid}"
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
    local cap_pid
    cap_pid="$(cat "${PID_FILE}")"

    echo "INFO: 停止捕获进程 ${cap_pid}"
    kill "${cap_pid}" 2>/dev/null || true
    pkill -P "${cap_pid}" 2>/dev/null || true
    rm -f "${PID_FILE}"

    if [ ! -f "${LOG_FILE}" ]; then
        echo "ERROR: 日志文件不存在: ${LOG_FILE}" >&2
        exit 1
    fi

    echo "INFO: 生成 Tool 事件报告 -> ${SUMMARY_FILE}"

    # 统计各类事件
    local tool_call_count tool_result_count send_tool_count
    tool_call_count="$(grep -cE 'tool_call|tool_use|function_call' "${LOG_FILE}" || echo 0)"
    tool_result_count="$(grep -cE 'tool_result' "${LOG_FILE}" || echo 0)"
    send_tool_count="$(grep -cE 'sendToolMessage' "${LOG_FILE}" || echo 0)"

    # Prompt Skill 关键词出现次数 (用于验证不被误判)
    local prompt_skill_count
    prompt_skill_count="$(grep -cE "${PROMPT_SKILL_KEYWORDS}" "${LOG_FILE}" || echo 0)"

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
