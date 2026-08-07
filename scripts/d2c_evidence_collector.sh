#!/usr/bin/env bash
# D2-C 证据收集与打包脚本
#
# 用法:
#   ./d2c_evidence_collector.sh env      # 收集环境信息
#   ./d2c_evidence_collector.sh pack     # 打包所有 D2-C 证据
#
# 安全声明: 只读收集, 不修改任何系统文件

set -euo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${PROBE_DIR}/out"
mkdir -p "${OUT_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
EVIDENCE_DIR="${OUT_DIR}/d2c_evidence_${TIMESTAMP}"
ENV_FILE="${EVIDENCE_DIR}/environment.json"

DB_PATH="${HOME}/.config/kylin-aiassistant/kylin_aiassistant_database.db"

cmd_env() {
    mkdir -p "${EVIDENCE_DIR}"

    local os_first_line uname_str ai_proc_status db_status commit_sha
    os_first_line="$(head -n 1 /etc/kylin-build 2>/dev/null || head -n 1 /etc/os-release 2>/dev/null || echo N/A)"
    uname_str="$(uname -a)"
    ai_proc_status="$(pgrep -fa kylin-aiassistant || echo not-running)"
    db_status=absent
    if [ -f "${DB_PATH}" ]; then
        db_status=exists
    fi
    commit_sha=unknown
    if [ -d "${PROBE_DIR}/../kylinOS-agent-memory/.git" ]; then
        commit_sha="$(cd "${PROBE_DIR}/../kylinOS-agent-memory" && git rev-parse HEAD 2>/dev/null || echo unknown)"
    fi

    {
        echo '{'
        echo "  \"task_id\": \"D2-C-OSAGENT-SPIKE\","
        echo "  \"timestamp\": \"${TIMESTAMP}\","
        echo "  \"os\": {"
        echo "    \"kylin_build\": \"${os_first_line}\","
        echo "    \"uname\": \"${uname_str}\""
        echo "  },"
        echo "  \"host_app\": {"
        echo "    \"process\": \"${ai_proc_status}\","
        echo "    \"database\": \"${db_status}\""
        echo "  },"
        echo "  \"commit\": \"${commit_sha}\","
        echo "  \"virtualization\": \"VirtualBox (版本号实测)\","
        echo "  \"reviewer\": \"D(周子腾); E(谢嘉然)补审\","
        echo "  \"probe_scripts_version\": \"D2-C v1.0\""
        echo '}'
    } > "${ENV_FILE}"

    echo "环境信息已保存: ${ENV_FILE}"
    cat "${ENV_FILE}"
}

cmd_pack() {
    mkdir -p "${EVIDENCE_DIR}"

    # 复制环境信息
    cmd_env > /dev/null

    # 复制 PostTurn 证据
    mkdir -p "${EVIDENCE_DIR}/postturn"
    cp "${OUT_DIR}"/postturn_*.log "${EVIDENCE_DIR}/postturn/" 2>/dev/null || echo "无 PostTurn 日志"
    cp "${OUT_DIR}"/postturn_*.summary.json "${EVIDENCE_DIR}/postturn/" 2>/dev/null || true
    cp "${OUT_DIR}"/postturn_*.db_snapshots.json "${EVIDENCE_DIR}/postturn/" 2>/dev/null || true

    # 复制 PreChat 证据
    mkdir -p "${EVIDENCE_DIR}/prechat"
    cp "${OUT_DIR}"/prechat_*.baseline.json "${EVIDENCE_DIR}/prechat/" 2>/dev/null || echo "无 PreChat 基线"
    cp "${OUT_DIR}"/prechat_*.ui_screenshot.png "${EVIDENCE_DIR}/prechat/" 2>/dev/null || true
    cp "${OUT_DIR}"/prechat_*.db_message.txt "${EVIDENCE_DIR}/prechat/" 2>/dev/null || true
    cp "${OUT_DIR}"/prechat_*.model_request.jsonl "${EVIDENCE_DIR}/prechat/" 2>/dev/null || true

    # 复制 Tool 证据
    mkdir -p "${EVIDENCE_DIR}/tool"
    cp "${OUT_DIR}"/tool_*.log "${EVIDENCE_DIR}/tool/" 2>/dev/null || echo "无 Tool 日志"
    cp "${OUT_DIR}"/tool_*.summary.json "${EVIDENCE_DIR}/tool/" 2>/dev/null || true

    # 生成 README
    {
        echo "# D2-C 证据包"
        echo ""
        echo "- task_id: D2-C-OSAGENT-SPIKE"
        echo "- timestamp: ${TIMESTAMP}"
        echo "- 状态: 待 Reviewer 核对"
        echo ""
        echo "## 内容"
        echo ""
        echo "- environment.json — 环境信息 (OS、宿主版本、Commit SHA)"
        echo "- postturn/ — H2C-PostTurn is_end 唯一性验证证据"
        echo "- prechat/ — H2C-PreChat Context 注入三路隔离证据"
        echo "- tool/ — H2C-Tool 真实 Tool 事件观察证据"
        echo ""
        echo "## Reviewer 核对项"
        echo ""
        echo "1. 日志是否来自当前 Commit"
        echo "2. 环境是否真实 (银河麒麟虚拟机)"
        echo "3. 是否有失败被忽略"
        echo "4. 通过标准是否满足"
    } > "${EVIDENCE_DIR}/README.md"

    # 生成校验和
    cd "${EVIDENCE_DIR}"
    sha256sum -- * > checksums.sha256 2>/dev/null || true

    # 打包
    local tarball="${OUT_DIR}/d2c_evidence_${TIMESTAMP}.tar.gz"
    cd "${OUT_DIR}"
    tar -czf "${tarball}" "d2c_evidence_${TIMESTAMP}"

    echo "=============================================="
    echo " 证据包打包完成"
    echo "=============================================="
    echo "  目录: ${EVIDENCE_DIR}"
    echo "  压缩: ${tarball}"
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
        echo "  env  - 收集环境信息"
        echo "  pack - 打包所有 D2-C 证据"
        exit 1
        ;;
esac
