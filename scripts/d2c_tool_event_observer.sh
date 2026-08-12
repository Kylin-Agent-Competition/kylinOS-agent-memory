#!/usr/bin/env bash
# D2-C 实验 C: H2C-Tool 真实 Tool 事件观察只读脚本
#
# 目标: 捕获真实 Tool 成功/失败/取消事件, 验证 Prompt Skill 不被误判
# 关联: AGT-004 (真实 Tool Result, PARTIAL/E2·E4), TD-007 (OPEN)
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

# 状态文件统一放到真实用户 HOME 下, 避免 sudo 与非 sudo 混用时权限冲突
STATE_DIR="${USER_HOME}/.d2c-probe-state"
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

# Tool 事件关键词 (基于 D2-C 实验 C 实测发现的麒麟 AI 助手真实结构)
# 麒麟 AI 助手不使用 OpenAI 风格的 tool_call/function_call, 而是用:
#   - DBus 方法 "chat"        : 用户消息发送通道 (assistant.sock)
#   - DBus 信号 "ChatResult"  : 模型流式回调 (assistant.sock)
#   - DBus 方法 "stop_chat"   : 取消场景的独立方法
#   - intentionrecognition.cpp: runtime 内部的意图识别模块 (真正触发"Tool"动作)
#   - enable_search           : 搜索增强 (HTTP POST 到模型 API)
TOOL_KEYWORDS="ChatResult|stop_chat|intentionrecognition|enable_search"

# OpenAI 风格关键词 (用于验证麒麟确实不使用这套, 预期 0 命中)
OPENAI_TOOL_KEYWORDS="tool_call|tool_result|tool_use|tool_name|tool_call_id|function_call|sendToolMessage"

# Prompt Skill 关键词 (用于验证不被误判; 同时支持原文和八进制转义搜索)
PROMPT_SKILL_KEYWORDS="translate|polish|summarize|rewrite"
# 中文关键词 (strace 会把中文编码为八进制 \NNN, 用 python3 还原后搜索)
PROMPT_SKILL_CN_KEYWORDS="翻译|润色|总结|改写"

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
    # - 仅 attach 到真实 AI 助手主进程；Runtime 不是 Tool 事件的已验证来源。
    # - -f 跟踪子进程/线程
    # - -s 32768 (含 tool_call 大 JSON)
    # - -yy 打印 socket 路径
    local strace_args=(-p "${pid}" -f -s 32768 -yy \
        -e trace=write,writev,sendmsg,sendto,recvmsg,read,poll)

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
    echo "${cap_pid}" > "${PID_FILE}"
    cat > "${META_FILE}" <<EOF
strace_pid=${cap_pid}
ai_pid=${pid}
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
    # 只清理本次采集 PID 的子进程；不得以进程名宽匹配误杀并行采集任务。
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

    # 统计真实 DBus 事件 (基于实验实测发现的麒麟 AI 助手结构)
    local raw_chat_signal raw_stop raw_intent raw_enable_search
    raw_chat_signal="$(grep -c 'ChatResult'           "${RAW_LOG_FILE}" 2>/dev/null || echo 0)"
    raw_stop="$(grep -c 'stop_chat'                   "${RAW_LOG_FILE}" 2>/dev/null || echo 0)"
    raw_intent="$(grep -c 'intentionrecognition'      "${RAW_LOG_FILE}" 2>/dev/null || echo 0)"
    raw_enable_search="$(grep -c 'enable_search'      "${RAW_LOG_FILE}" 2>/dev/null || echo 0)"
    local chat_signal_count stop_chat_count intent_count enable_search_count
    chat_signal_count="$(to_int "${raw_chat_signal}")"
    stop_chat_count="$(to_int "${raw_stop}")"
    intent_count="$(to_int "${raw_intent}")"
    enable_search_count="$(to_int "${raw_enable_search}")"

    # 验证 OpenAI 风格关键词确实为 0 (证明麒麟不使用这套架构)
    local raw_openai
    raw_openai="$(grep -cE "${OPENAI_TOOL_KEYWORDS}" "${RAW_LOG_FILE}" 2>/dev/null || echo 0)"
    local openai_keyword_count
    openai_keyword_count="$(to_int "${raw_openai}")"

    # 统计 Prompt Skill 关键词 (英文原文 + 中文八进制解码)
    local raw_ps_en raw_ps_cn
    raw_ps_en="$(grep -cE "${PROMPT_SKILL_KEYWORDS}" "${RAW_LOG_FILE}" 2>/dev/null || echo 0)"
    local prompt_skill_en_count
    prompt_skill_en_count="$(to_int "${raw_ps_en}")"
    # 中文关键词需要还原八进制 \NNN 后搜索 (strace 默认把非 ASCII 编码为八进制)
    local prompt_skill_cn_count=0
    if command -v python3 >/dev/null 2>&1; then
        local ps_cn_hits
        ps_cn_hits="$(python3 - "${RAW_LOG_FILE}" <<'PYEOF' 2>/dev/null || echo 0
import re, sys
keywords = ["翻译", "润色", "总结", "改写"]
hits = 0
with open(sys.argv[1], 'r', errors='replace') as f:
    for line in f:
        try:
            decoded = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), line)
        except Exception:
            decoded = line
        for kw in keywords:
            if kw in decoded:
                hits += 1
                break
print(hits)
PYEOF
)"
        prompt_skill_cn_count="$(to_int "${ps_cn_hits}")"
    fi
    local prompt_skill_count=$(( prompt_skill_en_count + prompt_skill_cn_count ))

    # 诊断线索不替代验收事件：所有 Tool Gate 条目保持 NOT_VERIFIED，
    # 直到定位到可审计的结构化事件来源。
    local cancel_captured=false
    if [ "${stop_chat_count}" -gt 0 ]; then
        cancel_captured=true
    fi
    local intent_triggered=false
    if [ "${intent_count}" -gt 0 ]; then
        intent_triggered=true
    fi
    local prompt_skill_not_misjudged=false
    if [ "${openai_keyword_count}" -eq 0 ]; then
        prompt_skill_not_misjudged=true
    fi

    cat > "${SUMMARY_FILE}" <<EOF
{
  "experiment": "H2C-Tool",
  "timestamp": "${TIMESTAMP}",
  "log_file": "$(basename "${LOG_FILE}")",
  "raw_log_bytes": ${log_size},
  "architecture_finding": {
    "uses_openai_tool_call": false,
    "openai_keyword_hits": ${openai_keyword_count},
    "actual_mechism": "DBus chat/ChatResult + intentionrecognition.cpp inside kylin-ai-runtime",
    "note": "麒麟 AI 助手不使用 OpenAI 风格 tool_call/function_call, Tool 动作由 runtime 内部 intentionrecognition 模块直接执行"
  },
  "metrics": {
    "ChatResult_signal_count": ${chat_signal_count},
    "stop_chat_method_count": ${stop_chat_count},
    "intentionrecognition_log_count": ${intent_count},
    "enable_search_request_count": ${enable_search_count},
    "openai_style_keyword_count": ${openai_keyword_count},
    "prompt_skill_keyword_count": ${prompt_skill_count}
  },
  "analysis": {
    "cancel_event_captured": ${cancel_captured},
    "intent_recognition_triggered": ${intent_triggered},
    "prompt_skill_not_misjudged": ${prompt_skill_not_misjudged},
    "tool_event_captured": "NOT_VERIFIED - 未捕获真实 ToolExecutionEvent；架构线索不能替代成功、失败或取消事件"
  },
  "pass_criteria": {
    "H2C-Tool-1": "NOT_VERIFIED (未捕获成功 ToolExecutionEvent)",
    "H2C-Tool-2": "NOT_VERIFIED (未捕获失败 ToolExecutionEvent)",
    "H2C-Tool-3": "NOT_VERIFIED (stop_chat 仅是取消线索，不能证明取消 ToolExecutionEvent)",
    "H2C-Tool-4": "NOT_VERIFIED (关键词计数不能证明 Prompt Skill 未被分类为 Tool)"
  },
  "note": "基于 D2-C 实验 C 实测: 麒麟 AI 助手所有用户输入(含打开应用/翻译)均以 message_type=chat 发送, 无 OpenAI 风格 tool_call 事件",
  "disclaimer": "判定权交由 Reviewer, 脚本仅记录观察结果"
}
EOF

    echo "=============================================="
    echo " H2C-Tool 事件报告"
    echo "=============================================="
    echo "  原始日志字节:              ${log_size}"
    echo ""
    echo "  [麒麟真实机制]"
    echo "  ChatResult 信号:          ${chat_signal_count}  (模型流式回调)"
    echo "  stop_chat 方法:            ${stop_chat_count}  (取消场景)"
    echo "  intentionrecognition 日志: ${intent_count}  (意图识别触发 Tool 动作)"
    echo "  enable_search 请求:        ${enable_search_count}  (搜索增强)"
    echo ""
    echo "  [架构验证]"
    echo "  OpenAI 风格关键词命中:     ${openai_keyword_count}  (预期 0, 证明麒麟不用 tool_call)"
    echo "  Prompt Skill 关键词:       ${prompt_skill_count}  (英文 ${prompt_skill_en_count} + 中文 ${prompt_skill_cn_count})"
    echo ""
    echo "  [观察结果]"
    if [ "${stop_chat_count}" -gt 0 ]; then
        echo "  OBSERVED: stop_chat 线索已捕获 (count=${stop_chat_count}; 不能替代结构化取消 Tool 事件)"
    else
        echo "  NOT_OBSERVED: stop_chat 线索未捕获 (count=0)"
    fi
    echo "  DIAGNOSTIC: OpenAI 风格关键词计数=${openai_keyword_count} (不能证明 H2C-Tool-4)"
    echo "  判定权交由 Reviewer, 脚本仅记录观察结果"
    echo ""
    echo "  H2C-Tool-1/2/3/4: NOT_VERIFIED"
    echo "    原因: 当前诊断仅跟踪真实 AI 助手主进程，尚未定位可审计的结构化 Tool 事件来源。"
    echo ""
    echo "  报告: ${SUMMARY_FILE}"
    echo "  日志: ${LOG_FILE}"
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
