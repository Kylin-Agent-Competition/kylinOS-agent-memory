#!/bin/bash
# ============================================================================
# 麒麟 OS Agent 记忆系统 · Gate 0 SPIKE
# KYSEC 最小授权脚本
#
# 用法:
#   ./kysec_authorize.sh status    # 检查当前 KYSEC 状态
#   ./kysec_authorize.sh verify    # 设置 verified 模式（最小授权）
#   ./kysec_authorize.sh relax     # 临时放宽（回退后可重试）
#   ./kysec_authorize.sh restore   # 恢复到之前状态
#
# 红线 [03 §8.1]:
#   - KYSEC 只对单个二进制设 verified
#   - 禁止全局关闭 KYSEC
#   - 禁止 apt upgrade/dist-upgrade/autoremove
# ============================================================================

set -euo pipefail

BINARY_PATH="/opt/kylin-memory/echo/echo_client"
KYSEC_STATE_FILE="/tmp/kylin_memory_kysec_state"
LOG_FILE="/tmp/kylin_memory_kysec.log"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[KYSEC]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn()  { echo -e "${YELLOW}[KYSEC]${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[KYSEC]${NC} $*" | tee -a "$LOG_FILE"; }

# ── 检查 KYSEC 是否可用 ──────────────────────────────────────
check_kysec_available() {
    if command -v getfattr &>/dev/null; then
        return 0
    fi
    log_warn "getfattr not found, checking /etc/kysec..."
    if [ -f /etc/kysec/kysec.conf ] || [ -d /etc/kysec ]; then
        return 0
    fi
    log_info "KYSEC tools not detected (may run on non-KYSEC system, this is OK for SPIKE)"
    return 0  # SPIKE 阶段不阻塞
}

# ── 获取当前 KYSEC 状态 ──────────────────────────────────────
cmd_status() {
    echo "=== KYSEC Status ==="
    echo "Date: $(date)"
    echo ""

    # 检查 systemd --user 已加载的 service
    echo "systemd user services:"
    systemctl --user list-units --type=service --no-pager 2>/dev/null | grep -i kysec || echo "  (none found)"
    echo ""

    # 检查二进制属性
    if [ -f "$BINARY_PATH" ]; then
        echo "Binary: $BINARY_PATH"
        ls -la "$BINARY_PATH"
        echo ""
        if command -v getfattr &>/dev/null; then
            echo "Extended attributes:"
            getfattr -d "$BINARY_PATH" 2>/dev/null || echo "  (none)"
        fi
    else
        echo "Binary not found: $BINARY_PATH (not yet built)"
    fi

    echo ""
    echo "Process list (kylin-memory):"
    ps aux | grep kylin-memory | grep -v grep || echo "  (none running)"

    echo ""
    echo "Socket status:"
    SOCK="${XDG_RUNTIME_DIR:-/tmp}/kylin-memory/memory.sock"
    if [ -S "$SOCK" ]; then
        echo "  Socket: $SOCK EXISTS"
        ls -la "$SOCK"
    else
        echo "  Socket: $SOCK NOT FOUND"
    fi
}

# ── 最小授权: 对单个二进制设 verified ─────────────────────────
cmd_verify() {
    log_info "Applying minimal KYSEC authorization for $BINARY_PATH"

    # 保存当前状态
    cmd_status > "$KYSEC_STATE_FILE" 2>/dev/null || true
    log_info "State saved to $KYSEC_STATE_FILE"

    if [ ! -f "$BINARY_PATH" ]; then
        log_error "Binary not found: $BINARY_PATH"
        log_info "Please build first: ./deploy_echo.sh build"
        return 1
    fi

    # 方案 A: 使用 setfattr 设置 verified 属性
    if command -v setfattr &>/dev/null; then
        log_info "Attempting setfattr verified on $BINARY_PATH"
        sudo setfattr -n security.kysec -v verified "$BINARY_PATH" 2>/dev/null && {
            log_info "KYSEC verified set via setfattr"
            return 0
        } || {
            log_warn "setfattr failed (may not be KYSEC kernel)"
        }
    fi

    # 方案 B: KYSEC 白名单目录（麒麟 V11 常见路径）
    KYSEC_DIRS=(
        "/etc/kysec/whitelist.d"
        "/etc/kysec/allow.d"
        "/etc/kysec/trusted.d"
    )
    for dir in "${KYSEC_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            WHITELIST_FILE="$dir/99-kylin-memory-echo.conf"
            log_info "Adding whitelist entry: $WHITELIST_FILE"
            echo "# Kylin Memory Echo Client (Gate 0 SPIKE)" | sudo tee "$WHITELIST_FILE"
            echo "path=$BINARY_PATH" | sudo tee -a "$WHITELIST_FILE"
            echo "action=allow" | sudo tee -a "$WHITELIST_FILE"
            log_info "Whitelist entry created"
        fi
    done

    # 方案 C: 使用 chmod +x + 确认权限
    log_info "Ensuring executable permissions"
    sudo chmod 755 "$BINARY_PATH"

    log_info "KYSEC minimal authorization applied"
    log_warn "SPIKE NOTE: Full KYSEC verification requires kernel-level KYSEC support."
    log_warn "If echo_client is blocked, check: dmesg | grep -i kysec"
}

# ── 临时放宽（用于调试，回退前用 restore 恢复） ──────────────
cmd_relax() {
    log_warn "Temporarily relaxing KYSEC restrictions"

    cmd_status > "$KYSEC_STATE_FILE" 2>/dev/null || true

    # 方案 A: 移除 verified 标记（如果存在）
    if command -v setfattr &>/dev/null; then
        sudo setfattr -x security.kysec "$BINARY_PATH" 2>/dev/null || true
    fi

    # 方案 B: 移除白名单
    for dir in /etc/kysec/whitelist.d /etc/kysec/allow.d /etc/kysec/trusted.d; do
        sudo rm -f "$dir/99-kylin-memory-echo.conf" 2>/dev/null || true
    done

    log_info "KYSEC restrictions relaxed (temporary, use 'restore' to revert)"
}

# ── 恢复 KYSEC 状态 ──────────────────────────────────────────
cmd_restore() {
    log_info "Restoring KYSEC state"

    if [ -f "$KYSEC_STATE_FILE" ]; then
        log_info "Previous state was:"
        cat "$KYSEC_STATE_FILE"
    else
        log_warn "No previous state file found"
    fi

    # 恢复默认：重新设置 verified
    if [ -f "$BINARY_PATH" ]; then
        cmd_verify
    fi

    # 清理临时文件
    rm -f "$KYSEC_STATE_FILE"

    log_info "KYSEC state restored"
}

# ── 主入口 ────────────────────────────────────────────────────
check_kysec_available

case "${1:-status}" in
    status)  cmd_status ;;
    verify)  cmd_verify ;;
    relax)   cmd_relax ;;
    restore) cmd_restore ;;
    *)
        echo "Usage: $0 {status|verify|relax|restore}"
        echo ""
        echo "  status   - Check current KYSEC status"
        echo "  verify   - Apply minimal KYSEC authorization (single binary)"
        echo "  relax    - Temporarily relax restrictions"
        echo "  restore  - Restore previous KYSEC state"
        exit 1
        ;;
esac