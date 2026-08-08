#!/usr/bin/env bash
# D2-C 证据收集与打包脚本
#
# 用法:
#   ./d2c_evidence_collector.sh env      # 收集环境信息 (生成/复用 RUN_ID)
#   ./d2c_evidence_collector.sh pack     # 打包所有 D2-C 证据 (仅收集本轮 RUN_ID 文件)
#
# RUN_ID 说明:
#   本脚本引入 RUN_ID (时间戳) 用于区分不同实验轮次, 三项实验与打包统一复用。
#   RUN_ID 存储在 ${STATE_DIR}/d2c_run_id, 可通过 D2C_RUN_ID 环境变量覆盖。
#   推荐工作流:
#     export D2C_RUN_ID="$(date +%Y%m%d_%H%M%S)"
#     ./d2c_evidence_collector.sh env
#     ./d2c_postturn_isend_counter.sh start "${D2C_RUN_ID}"
#     ./d2c_prechat_context_probe.sh baseline "${D2C_RUN_ID}"
#     ./d2c_tool_event_observer.sh start "${D2C_RUN_ID}"
#     ./d2c_evidence_collector.sh pack
#
# 安全声明: 只读收集, 不修改任何系统文件

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

RUN_ID_FILE="${STATE_DIR}/d2c_run_id"

# 获取或生成 RUN_ID: 优先 D2C_RUN_ID 环境变量, 其次状态文件, 最后新建时间戳
get_or_init_run_id() {
    if [ -n "${D2C_RUN_ID:-}" ]; then
        echo "${D2C_RUN_ID}" > "${RUN_ID_FILE}"
        echo "${D2C_RUN_ID}"
    elif [ -f "${RUN_ID_FILE}" ]; then
        cat "${RUN_ID_FILE}"
    else
        local new_id
        new_id="$(date +%Y%m%d_%H%M%S)"
        echo "${new_id}" > "${RUN_ID_FILE}"
        echo "${new_id}"
    fi
}

RUN_ID="$(get_or_init_run_id)"
EVIDENCE_DIR="${OUT_DIR}/d2c_evidence_${RUN_ID}"
ENV_FILE="${EVIDENCE_DIR}/environment.json"

DB_PATH="${USER_HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"

# 检测虚拟化环境 (禁止硬编码, 使用 systemd-detect-virt / dmidecode / dmesg 自检测)
detect_virt() {
    local virt=""
    # 1) systemd-detect-virt (首选, 通常不需要 root)
    if command -v systemd-detect-virt >/dev/null 2>&1; then
        virt="$(systemd-detect-virt 2>/dev/null || true)"
        if [ -n "${virt}" ] && [ "${virt}" != "none" ]; then
            echo "${virt}"
            return
        fi
    fi
    # 2) dmidecode (需要 root, 使用 sudo -n 避免密码挂起; 若已是 root 则直接执行)
    if command -v dmidecode >/dev/null 2>&1; then
        local mfr product
        mfr="$(sudo -n dmidecode -s system-manufacturer 2>/dev/null || true)"
        if [ -z "${mfr}" ]; then
            mfr="$(dmidecode -s system-manufacturer 2>/dev/null || true)"
        fi
        product="$(sudo -n dmidecode -s system-product-name 2>/dev/null || true)"
        if [ -z "${product}" ]; then
            product="$(dmidecode -s system-product-name 2>/dev/null || true)"
        fi
        if [ -n "${mfr}" ] || [ -n "${product}" ]; then
            echo "${mfr:-unknown} / ${product:-unknown}"
            return
        fi
    fi
    # 3) dmesg 查找 DMI / Hypervisor 信息
    if command -v dmesg >/dev/null 2>&1; then
        local dmi_line
        dmi_line="$(dmesg 2>/dev/null | grep -iE 'Hypervisor detected|DMI:|KVM|VirtualBox|VMware|QEMU|Xen' | head -n 1 || true)"
        if [ -n "${dmi_line}" ]; then
            echo "${dmi_line}"
            return
        fi
    fi
    # 4) /proc/cpuinfo hypervisor flag (最后兜底)
    if grep -qE 'hypervisor' /proc/cpuinfo 2>/dev/null; then
        echo "hypervisor-flag-detected (unknown type)"
        return
    fi
    echo "unknown"
}

# 获取 git commit SHA (失败时 exit 1)
get_commit_sha() {
    local sha
    if ! sha="$(git -C "${PROBE_DIR}/.." rev-parse HEAD 2>/dev/null)"; then
        echo "ERROR: 无法获取 git commit SHA (git -C \"${PROBE_DIR}/..\" rev-parse HEAD 失败)" >&2
        exit 1
    fi
    echo "${sha}"
}

# 使用 python3 json.dump() 生成合法 JSON, 并立即用 json.loads() 校验
write_env_json() {
    local os_first_line uname_str ai_proc_status db_status commit_sha virt_info
    os_first_line="$(head -n 1 /etc/kylin-build 2>/dev/null || head -n 1 /etc/os-release 2>/dev/null || echo N/A)"
    uname_str="$(uname -a)"
    ai_proc_status="$(pgrep -fa kylin-aiassistant || echo not-running)"
    db_status=absent
    if [ -f "${DB_PATH}" ]; then
        db_status=exists
    fi
    commit_sha="$(get_commit_sha)"
    virt_info="$(detect_virt)"

    python3 - "${ENV_FILE}" "${RUN_ID}" "${os_first_line}" "${uname_str}" \
        "${ai_proc_status}" "${db_status}" "${commit_sha}" "${virt_info}" <<'PYEOF'
import json
import sys

env_file = sys.argv[1]
run_id = sys.argv[2]
os_first_line = sys.argv[3]
uname_str = sys.argv[4]
ai_proc_status = sys.argv[5]
db_status = sys.argv[6]
commit_sha = sys.argv[7]
virt_info = sys.argv[8]

data = {
    "task_id": "D2-C-OSAGENT-SPIKE",
    "run_id": run_id,
    "timestamp": run_id,
    "os": {
        "kylin_build": os_first_line,
        "uname": uname_str,
    },
    "host_app": {
        "process": ai_proc_status,
        "database": db_status,
    },
    "commit": commit_sha,
    "virtualization": virt_info,
    "reviewer": "D(周子腾); E(谢嘉然)补审",
    "probe_scripts_version": "D2-C v1.1",
}

# 写入 JSON (ensure_ascii=False 保留中文, indent=2 美化)
with open(env_file, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

# 立即校验: 重新读取并解析, 不合法则抛异常退出
with open(env_file, "r", encoding="utf-8") as f:
    json.loads(f.read())
PYEOF
}

cmd_env() {
    mkdir -p "${EVIDENCE_DIR}"
    write_env_json
    echo "RUN_ID=${RUN_ID}"
    echo "环境信息已保存: ${ENV_FILE}"
    cat "${ENV_FILE}"
}

# 校验必填证据: 单个文件 (缺失直接 exit 1)
require_file() {
    local desc="$1"
    local path="$2"
    if [ ! -f "${path}" ]; then
        echo "ERROR: 必填证据缺失: ${desc}" >&2
        echo "  期望路径: ${path}" >&2
        exit 1
    fi
    echo "  ✓ ${desc}: ${path}"
}

# 校验必填证据: glob 匹配 (至少一个文件, 缺失直接 exit 1)
require_glob() {
    local desc="$1"
    local pattern="$2"
    local found=""
    # shellcheck disable=SC2086  # glob 需要展开
    found="$(ls -1 ${pattern} 2>/dev/null | head -n 1 || true)"
    if [ -z "${found}" ]; then
        echo "ERROR: 必填证据缺失: ${desc}" >&2
        echo "  期望模式: ${pattern}" >&2
        exit 1
    fi
    echo "  ✓ ${desc}: ${found}"
}

cmd_pack() {
    mkdir -p "${EVIDENCE_DIR}"

    # 1. 生成环境信息 (python3 json.dump + json.loads 校验)
    write_env_json

    # 2. 复制 PostTurn 证据 (仅本轮 RUN_ID, 避免混入历史实验文件)
    mkdir -p "${EVIDENCE_DIR}/postturn"
    # shellcheck disable=SC2086  # glob 需要展开
    cp ${OUT_DIR}/postturn_${RUN_ID}*.log "${EVIDENCE_DIR}/postturn/" 2>/dev/null || true
    # shellcheck disable=SC2086
    cp ${OUT_DIR}/postturn_${RUN_ID}*.summary.json "${EVIDENCE_DIR}/postturn/" 2>/dev/null || true
    # shellcheck disable=SC2086
    cp ${OUT_DIR}/postturn_${RUN_ID}*.db_snapshots.json "${EVIDENCE_DIR}/postturn/" 2>/dev/null || true

    # 3. 复制 PreChat 证据 (仅本轮 RUN_ID)
    mkdir -p "${EVIDENCE_DIR}/prechat"
    cp "${OUT_DIR}/prechat_${RUN_ID}.baseline.json" "${EVIDENCE_DIR}/prechat/" 2>/dev/null || true
    cp "${OUT_DIR}/prechat_${RUN_ID}.ui_screenshot.png" "${EVIDENCE_DIR}/prechat/" 2>/dev/null || true
    cp "${OUT_DIR}/prechat_${RUN_ID}.db_message.txt" "${EVIDENCE_DIR}/prechat/" 2>/dev/null || true
    cp "${OUT_DIR}/prechat_${RUN_ID}.model_request.jsonl" "${EVIDENCE_DIR}/prechat/" 2>/dev/null || true

    # 4. 复制 Tool 证据 (仅本轮 RUN_ID)
    mkdir -p "${EVIDENCE_DIR}/tool"
    # shellcheck disable=SC2086
    cp ${OUT_DIR}/tool_${RUN_ID}*.log "${EVIDENCE_DIR}/tool/" 2>/dev/null || true
    # shellcheck disable=SC2086
    cp ${OUT_DIR}/tool_${RUN_ID}*.summary.json "${EVIDENCE_DIR}/tool/" 2>/dev/null || true

    # 5. 校验 11 项必填证据 (任何缺失直接 exit 1)
    echo "=============================================="
    echo " 必填证据校验 (RUN_ID=${RUN_ID})"
    echo "=============================================="
    require_file  "environment.json"        "${EVIDENCE_DIR}/environment.json"
    require_glob  "PostTurn 原始日志"        "${EVIDENCE_DIR}/postturn/postturn_${RUN_ID}*.log"
    require_glob  "PostTurn summary"        "${EVIDENCE_DIR}/postturn/postturn_${RUN_ID}*.summary.json"
    require_glob  "PostTurn 数据库快照"      "${EVIDENCE_DIR}/postturn/postturn_${RUN_ID}*.db_snapshots.json"
    require_file  "PreChat baseline"        "${EVIDENCE_DIR}/prechat/prechat_${RUN_ID}.baseline.json"
    require_file  "PreChat 截图"            "${EVIDENCE_DIR}/prechat/prechat_${RUN_ID}.ui_screenshot.png"
    require_file  "PreChat 数据库导出"      "${EVIDENCE_DIR}/prechat/prechat_${RUN_ID}.db_message.txt"
    require_file  "PreChat 请求证据"        "${EVIDENCE_DIR}/prechat/prechat_${RUN_ID}.model_request.jsonl"
    require_glob  "Tool 原始日志"           "${EVIDENCE_DIR}/tool/tool_${RUN_ID}*.log"
    require_glob  "Tool summary"            "${EVIDENCE_DIR}/tool/tool_${RUN_ID}*.summary.json"

    # 6. JSON 完整性校验 (打包前对所有 .json 文件用 python3 json.loads 校验)
    echo "=============================================="
    echo " JSON 完整性校验"
    echo "=============================================="
    local json_failed=0
    while IFS= read -r -d '' jf; do
        if ! python3 -c "import json,sys; json.loads(open(sys.argv[1],encoding='utf-8').read())" "${jf}" 2>/dev/null; then
            echo "ERROR: JSON 校验失败: ${jf}" >&2
            json_failed=1
        else
            echo "  ✓ ${jf}"
        fi
    done < <(find "${EVIDENCE_DIR}" -type f -name '*.json' -print0)
    if [ "${json_failed}" -ne 0 ]; then
        echo "ERROR: 存在非法 JSON 文件, 打包终止" >&2
        exit 1
    fi

    # 7. 生成 README
    {
        echo "# D2-C 证据包"
        echo ""
        echo "- task_id: D2-C-OSAGENT-SPIKE"
        echo "- run_id: ${RUN_ID}"
        echo "- timestamp: ${RUN_ID}"
        echo "- 状态: 待 Reviewer 核对"
        echo ""
        echo "## 内容"
        echo ""
        echo "- environment.json — 环境信息 (OS、宿主版本、Commit SHA、虚拟化自检测)"
        echo "- postturn/ — H2C-PostTurn is_end 唯一性验证证据"
        echo "- prechat/ — H2C-PreChat Context 注入三路隔离证据"
        echo "- tool/ — H2C-Tool 真实 Tool 事件观察证据"
        echo "- checksums.sha256 — 全文件 SHA256 校验和 (递归)"
        echo ""
        echo "## Reviewer 核对项"
        echo ""
        echo "1. 日志是否来自当前 Commit"
        echo "2. 环境是否真实 (银河麒麟虚拟机, 虚拟化类型自检测非硬编码)"
        echo "3. 是否有失败被忽略"
        echo "4. 通过标准是否满足"
    } > "${EVIDENCE_DIR}/README.md"

    # 8. 生成校验和 (递归子目录, 排除 checksums.sha256 自身, 失败时 exit 1)
    echo "=============================================="
    echo " 生成 SHA256 校验和 (递归)"
    echo "=============================================="
    (
        cd "${EVIDENCE_DIR}"
        find . -type f ! -name checksums.sha256 -print0 \
            | sort -z \
            | xargs -0 sha256sum > checksums.sha256
    ) || {
        echo "ERROR: SHA256 校验和生成失败" >&2
        exit 1
    }
    echo "  ✓ checksums.sha256 已生成"

    # 9. 校验 checksums.sha256 (第 11 项必填证据)
    require_file "checksums.sha256" "${EVIDENCE_DIR}/checksums.sha256"

    # 10. 打包
    local tarball="${OUT_DIR}/d2c_evidence_${RUN_ID}.tar.gz"
    (
        cd "${OUT_DIR}"
        tar -czf "${tarball}" "d2c_evidence_${RUN_ID}"
    )

    echo "=============================================="
    echo " 证据包打包完成"
    echo "=============================================="
    echo "  RUN_ID:  ${RUN_ID}"
    echo "  目录:    ${EVIDENCE_DIR}"
    echo "  压缩:    ${tarball}"
    echo ""
    echo "  下一步:"
    echo "  1. 上传脱敏后的证据到 evidence/l2-kylin-vm/d2c/"
    echo "  2. 更新 evidence/index.yaml"
    echo "  3. 更新 01 文档能力矩阵 AGT-004/005"
    echo "=============================================="
}

case "${1:-}" in
    env)
        cmd_env
        ;;
    pack)
        cmd_pack
        ;;
    *)
        echo "用法: $0 {env|pack}"
        echo ""
        echo "  env  - 收集环境信息 (生成/复用 RUN_ID)"
        echo "  pack - 打包所有 D2-C 证据 (仅收集本轮 RUN_ID 文件)"
        echo ""
        echo "  RUN_ID 可通过 D2C_RUN_ID 环境变量指定, 否则自动生成时间戳并持久化"
        echo "  三项实验应使用同一 RUN_ID, 例如:"
        echo "    export D2C_RUN_ID=\"\$(date +%Y%m%d_%H%M%S)\""
        echo "    ./d2c_postturn_isend_counter.sh start \"\${D2C_RUN_ID}\""
        echo "    ./d2c_prechat_context_probe.sh baseline \"\${D2C_RUN_ID}\""
        echo "    ./d2c_tool_event_observer.sh start \"\${D2C_RUN_ID}\""
        exit 1
        ;;
esac
