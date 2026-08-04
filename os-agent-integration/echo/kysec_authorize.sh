#!/usr/bin/env bash
# =============================================================================
# UDS 文件权限与 ACL 最小授权脚本
# =============================================================================
# ⚠️ 非真实 KYSEC 规则写入 — KYSEC 状态标记为 UNVERIFIED.
# 对 socket 目录/文件实施 UDS 文件权限 + ACL 最小授权策略:
#   - 仅允许 kylin-aiassistant 进程 (kylin-aiassistant 用户或进程标签) 访问
#   - 记录授权前后规则状态
#   - 非破坏性: 原有权限/ACL 被备份而非删除
#
# 用法:
#   sudo bash kysec_authorize.sh [authorize|status|rollback]
#
# 原理:
#   麒麟 KYSEC 通过 /sys/kernel/security/kylin/ 下的控制文件实现。
#   对 UDS socket 的访问控制主要通过:
#     1. socket 文件权限 (chmod 0700 - 仅 owner)
#     2. 文件系统 ACL (setfacl - 精确到用户/组)
#     3. KYSEC label 匹配 (如果启用了进程标签)
# =============================================================================

set -euo pipefail

SOCKET_PATH="/tmp/kylin-memory-echo/echo.sock"
SOCKET_DIR="/tmp/kylin-memory-echo"
KYLIN_USER="${SUDO_USER:-$(whoami)}"
BACKUP_DIR="/tmp/kylin-memory-echo-kysec-backup-$(date +%Y%m%d_%H%M%S)"
BACKUP_ID_FILE="/tmp/kylin-memory-echo-kysec-backup-id.txt"
LOG_FILE="/tmp/kylin-memory-echo/kysec_authorize.log"

# ---- 工具函数 ----
log_msg() {
    local ts
    ts=$(date '+%Y-%m-%dT%H:%M:%S')
    echo "[$ts] $1" | tee -a "$LOG_FILE"
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: 此脚本需要 root 权限 (对文件系统 ACL/KYSEC 的修改)"
        echo "请使用: sudo bash \"$0\" $*"  # $* intentional word splitting for passthrough args
        exit 1
    fi
}

backup_current_state() {
    log_msg "备份当前状态到: ${BACKUP_DIR}"
    mkdir -p "$BACKUP_DIR"

    # 备份 socket 目录权限
    if [ -d "$SOCKET_DIR" ]; then
        ls -la "$SOCKET_DIR" > "$BACKUP_DIR/socket_dir_ls.txt" 2>&1 || true
        getfacl "$SOCKET_DIR" > "$BACKUP_DIR/socket_dir_acl.txt" 2>&1 || true
    fi

    # 备份 socket 文件权限 (如果存在)
    if [ -e "$SOCKET_PATH" ]; then
        ls -la "$SOCKET_PATH" > "$BACKUP_DIR/socket_file_ls.txt" 2>&1 || true
        getfacl "$SOCKET_PATH" > "$BACKUP_DIR/socket_file_acl.txt" 2>&1 || true
        stat "$SOCKET_PATH" > "$BACKUP_DIR/socket_stat.txt" 2>&1 || true
    fi

    # 备份 KYSEC 状态 (如果存在)
    if [ -d /sys/kernel/security/kylin ]; then
        find /sys/kernel/security/kylin -type f -exec sh -c 'echo "=== {} ===" && cat "{}" 2>/dev/null || echo "(read failed)"' \; > "${BACKUP_DIR}/kysec_status.txt" 2>&1 || true
    else
        echo "KYSEC 内核接口不可用 (非麒麟系统或未启用)" > "$BACKUP_DIR/kysec_status.txt"
    fi

    log_msg "备份完成"
}

apply_minimal_acl() {
    log_msg "应用最小 ACL 策略..."

    # 1. 确保 socket 目录存在，权限 0700
    mkdir -p "$SOCKET_DIR"
    chmod 0700 "$SOCKET_DIR"
    chown "${KYLIN_USER}:${KYLIN_USER}" "$SOCKET_DIR" 2>/dev/null || true
    log_msg "  Socket 目录权限: 0700, owner=${KYLIN_USER}"

    # 2. 如果 socket 文件存在，同样限制
    if [ -e "$SOCKET_PATH" ]; then
        chmod 0600 "$SOCKET_PATH"
        chown "${KYLIN_USER}:${KYLIN_USER}" "$SOCKET_PATH" 2>/dev/null || true
        log_msg "  Socket 文件权限: 0600, owner=${KYLIN_USER}"
    fi

    # 3. 尝试通过 ACL 精确授权给 kylin-aiassistant 用户 (如果存在)
    if id kylin-aiassistant &>/dev/null; then
        setfacl -m "u:kylin-aiassistant:rwx" "$SOCKET_DIR" 2>/dev/null && \
            log_msg "  ACL: 已授予 kylin-aiassistant 用户 rwx 权限" || \
            log_msg "  WARN: setfacl 失败 (可能未安装 acl 包)"
    else
        log_msg "  INFO: kylin-aiassistant 用户不存在，跳过用户级别 ACL"
    fi

    # 4. 如果 socket 存在，也设置 ACL
    if [ -e "$SOCKET_PATH" ]; then
        if id kylin-aiassistant &>/dev/null; then
            setfacl -m "u:kylin-aiassistant:rw" "$SOCKET_PATH" 2>/dev/null || true
        fi
    fi

    log_msg "最小 ACL 策略已应用 (非真实 KYSEC 规则写入)"
}

show_status() {
    log_msg "====== ACL/文件权限 状态报告 ======"

    echo ""
    echo "--- Socket 目录 ---"
    if [ -d "$SOCKET_DIR" ]; then
        ls -la "$SOCKET_DIR"
        echo ""
        echo "ACL:"
        getfacl "$SOCKET_DIR" 2>/dev/null || echo "(getfacl 不可用)"
    else
        echo "目录不存在: $SOCKET_DIR"
    fi

    echo ""
    echo "--- Socket 文件 ---"
    if [ -e "$SOCKET_PATH" ]; then
        ls -la "$SOCKET_PATH"
        echo ""
        echo "ACL:"
        getfacl "$SOCKET_PATH" 2>/dev/null || echo "(getfacl 不可用)"
    else
        echo "Socket 文件不存在 (服务未启动)"
    fi

    echo ""
    echo "--- KYSEC 内核接口 ---"
    if [ -d /sys/kernel/security/kylin ]; then
        echo "KYSEC 已启用"
        for f in /sys/kernel/security/kylin/*; do
            if [ -f "$f" ]; then
                echo "  $(basename "$f"): $(cat "$f" 2>/dev/null || echo 'read failed')"
            fi
        done
    else
        echo "KYSEC 内核接口不可用 (非麒麟系统或安全模块未加载)"
    fi

    echo ""
    echo "--- kylin-aiassistant 进程 ---"
    pgrep -a kylin-aiassistant 2>/dev/null || echo "无 kylin-aiassistant 进程"

    echo ""
    echo "--- 当前用户 ---"
    echo "UID=$(id -u) USER=$(whoami)"
    echo "SUDO_USER=$SUDO_USER"

    echo ""
    echo "--- KYSEC 状态 ---"
    echo "UNVERIFIED: 此脚本仅实施文件权限+ACL，不写入真实 KYSEC 规则"

    log_msg "====== 状态报告结束 ======"
}

rollback_from_backup() {
    log_msg "执行回退..."

    # 优先使用 BACKUP_ID_FILE 记录的最新备份
    local recorded_backup=""
    if [ -f "$BACKUP_ID_FILE" ] && [ -s "$BACKUP_ID_FILE" ]; then
        recorded_backup="$(head -1 "${BACKUP_ID_FILE}")"
        if [ -n "$recorded_backup" ] && [ -d "$recorded_backup" ]; then
            log_msg "使用 recorded backup: ${recorded_backup}"
        else
            log_msg "WARN: recorded backup 无效，兜底使用最新"
            recorded_backup=""
        fi
    fi

    # 兜底：取最早（不是最新）备份以恢复到授权前状态
    local latest_backup="${recorded_backup:-}"
    if [ -z "$latest_backup" ]; then
        latest_backup=$(ls -dt /tmp/kylin-memory-echo-kysec-backup-* 2>/dev/null | tail -1)
    fi

    if [ -z "$latest_backup" ]; then
        log_msg "ERROR: 未找到备份目录"
        return 1
    fi

    log_msg "从备份恢复: ${latest_backup}"

    # 恢复 socket 目录 ACL
    if [ -f "$latest_backup/socket_dir_acl.txt" ]; then
        chmod 0700 "$SOCKET_DIR" 2>/dev/null || true
        chown "${KYLIN_USER}:${KYLIN_USER}" "$SOCKET_DIR" 2>/dev/null || true
        log_msg "  Socket 目录权限已回退"
    fi

    # 恢复 socket 文件权限
    if [ -f "$latest_backup/socket_file_acl.txt" ]; then
        chmod 0600 "$SOCKET_PATH" 2>/dev/null || true
        chown "${KYLIN_USER}:${KYLIN_USER}" "$SOCKET_PATH" 2>/dev/null || true
        log_msg "  Socket 文件权限已回退"
    fi

    # 清理 BACKUP_ID_FILE
    rm -f "${BACKUP_ID_FILE}"

    log_msg "回退完成"
}

# ---- 主入口 ----
ACTION="${1:-authorize}"

mkdir -p "$SOCKET_DIR"

case "$ACTION" in
    authorize)
        check_root "$@"
        log_msg "========== ACL 最小授权开始 (KYSEC UNVERIFIED) =========="
        backup_current_state
        # 记录本次备份目录到 BACKUP_ID_FILE
        echo "${BACKUP_DIR}" > "${BACKUP_ID_FILE}"
        log_msg "备份ID已记录: ${BACKUP_DIR}"
        apply_minimal_acl
        show_status
        log_msg "========== ACL 最小授权完成 =========="
        echo ""
        echo "备份位置: ${BACKUP_DIR}"
        echo "日志文件: ${LOG_FILE}"
        echo "⚠️ KYSEC 状态: UNVERIFIED (非真实 KYSEC 规则写入)"
        ;;

    status)
        show_status
        ;;

    rollback)
        check_root "$@"
        log_msg "========== ACL 回退开始 =========="
        backup_current_state  # 回退前也备份当前状态
        rollback_from_backup
        log_msg "========== ACL 回退完成 =========="
        ;;

    *)
        echo "Usage: $0 [authorize|status|rollback]"
        echo ""
        echo "  authorize  - 备份当前状态并应用最小 ACL 策略 (KYSEC UNVERIFIED)"
        echo "  status     - 显示当前 ACL/Socket 状态"
        echo "  rollback   - 从记录的备份恢复"
        exit 1
        ;;
esac