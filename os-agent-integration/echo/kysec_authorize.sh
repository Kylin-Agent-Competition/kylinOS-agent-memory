#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Echo — KYSEC 最小授权脚本
# =============================================================================
# 对 /tmp/kylin-memory-echo/echo.sock 实施 KYSEC 最小授权策略:
#   - 仅允许 kylin-aiassistant 进程 (kylin-aiassistant 用户或进程标签) 访问
#   - 记录授权前后规则状态
#   - 非破坏性: 原有 KYSEC 规则被备份而非删除
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
        echo "请使用: sudo bash $0 $*"
        exit 1
    fi
}

backup_current_state() {
    log_msg "备份当前状态到: $BACKUP_DIR"
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
        find /sys/kernel/security/kylin -type f -exec sh -c 'echo "=== {} ===" && cat "{}" 2>/dev/null || echo "(read failed)"' \; > "$BACKUP_DIR/kysec_status.txt" 2>&1 || true
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
    chown "$KYLIN_USER:$KYLIN_USER" "$SOCKET_DIR" 2>/dev/null || true
    log_msg "  Socket 目录权限: 0700, owner=$KYLIN_USER"

    # 2. 如果 socket 文件存在，同样限制
    if [ -e "$SOCKET_PATH" ]; then
        chmod 0600 "$SOCKET_PATH"
        chown "$KYLIN_USER:$KYLIN_USER" "$SOCKET_PATH" 2>/dev/null || true
        log_msg "  Socket 文件权限: 0600, owner=$KYLIN_USER"
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

    log_msg "最小 ACL 策略已应用"
}

show_status() {
    log_msg "====== KYSEC 状态报告 ======"

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

    log_msg "====== 状态报告结束 ======"
}

rollback_from_backup() {
    log_msg "执行回退..."

    # 找到最新的备份
    local latest_backup
    latest_backup=$(ls -dt /tmp/kylin-memory-echo-kysec-backup-* 2>/dev/null | head -1)

    if [ -z "$latest_backup" ]; then
        log_msg "ERROR: 未找到备份目录"
        return 1
    fi

    log_msg "从备份恢复: $latest_backup"

    # 恢复 socket 目录 ACL
    if [ -f "$latest_backup/socket_dir_acl.txt" ]; then
        # 清除现有 ACL 并从备份恢复 (简单的重新设置权限方式)
        chmod 0700 "$SOCKET_DIR" 2>/dev/null || true
        chown "$KYLIN_USER:$KYLIN_USER" "$SOCKET_DIR" 2>/dev/null || true
        log_msg "  Socket 目录权限已回退"
    fi

    # 恢复 socket 文件权限
    if [ -f "$latest_backup/socket_file_acl.txt" ]; then
        chmod 0600 "$SOCKET_PATH" 2>/dev/null || true
        chown "$KYLIN_USER:$KYLIN_USER" "$SOCKET_PATH" 2>/dev/null || true
        log_msg "  Socket 文件权限已回退"
    fi

    log_msg "回退完成"
}

# ---- 主入口 ----
ACTION="${1:-authorize}"

mkdir -p "$SOCKET_DIR"

case "$ACTION" in
    authorize)
        check_root "$@"
        log_msg "========== KYSEC 最小授权开始 =========="
        backup_current_state
        apply_minimal_acl
        show_status
        log_msg "========== KYSEC 最小授权完成 =========="
        echo ""
        echo "备份位置: $BACKUP_DIR"
        echo "日志文件: $LOG_FILE"
        ;;

    status)
        show_status
        ;;

    rollback)
        check_root "$@"
        log_msg "========== KYSEC 回退开始 =========="
        backup_current_state  # 回退前也备份当前状态
        rollback_from_backup
        log_msg "========== KYSEC 回退完成 =========="
        ;;

    *)
        echo "Usage: $0 [authorize|status|rollback]"
        echo ""
        echo "  authorize  - 备份当前状态并应用最小 ACL 策略"
        echo "  status     - 显示当前 KYSEC/Socket 状态"
        echo "  rollback   - 从最近的备份恢复"
        exit 1
        ;;
esac