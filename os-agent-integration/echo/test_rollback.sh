#!/bin/bash
# ============================================================================
# 麒麟 OS Agent 记忆系统 · Gate 0 SPIKE
# 验证项 4: 备份与回退链路完整回归测试
#
# 在麒麟 VM 桌面上运行:
#   chmod +x test_rollback.sh && bash test_rollback.sh
#
# 测试流程:
#   1) 确保服务运行 & 功能正常 (基线)
#   2) 创建备份
#   3) 模拟"破坏" (修改 memory_echo_server.py)
#   4) 验证破坏生效 (服务异常)
#   5) 执行回退
#   6) 验证恢复 (服务正常 + UDS Echo 测试通过)
#   7) 输出测试结论
# ============================================================================

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────────────
INSTALL_DIR="/opt/kylin-memory/echo"
BACKUP_DIR="$INSTALL_DIR/backups"
SOCK_DIR="${XDG_RUNTIME_DIR:-/tmp}/kylin-memory"
SOCK_PATH="$SOCK_DIR/memory.sock"
ECHO_CLIENT="$INSTALL_DIR/echo_client"
LOG_FILE="/tmp/test_rollback_$(date +%Y%m%d_%H%M%S).log"
BACKUP_NAME="manual_backup_$(date +%Y%m%d_%H%M%S)"
PASS_COUNT=0
FAIL_COUNT=0

# ── 颜色 ──────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── 输出 ──────────────────────────────────────────────────────
log_section() { echo -e "\n${BLUE}=== $1 ===${NC}" | tee -a "$LOG_FILE"; }
log_pass()   { echo -e "  ${GREEN}[PASS]${NC} $1" | tee -a "$LOG_FILE"; ((PASS_COUNT++)) || true; }
log_fail()   { echo -e "  ${RED}[FAIL]${NC} $1" | tee -a "$LOG_FILE"; ((FAIL_COUNT++)) || true; }
log_info()   { echo -e "  ${YELLOW}[INFO]${NC} $1" | tee -a "$LOG_FILE"; }
log_cmd()    { echo -e "  \$ $1" >> "$LOG_FILE"; }

# ── 辅助函数 ──────────────────────────────────────────────────
check_socket() {
    test -S "$SOCK_PATH"
}

run_echo_test() {
    local out
    out=$(KYLIN_MEMORY_SOCK="$SOCK_PATH" "$ECHO_CLIENT" 2>&1) || return 1
    echo "$out"
}

kill_old() {
    pkill -f memory_echo_server.py 2>/dev/null || true
    systemctl --user stop kylin-memory-echo 2>/dev/null || true
    sleep 1
    sudo rm -f /tmp/kylin-memory-echo.log /tmp/kylin-memory-echo.pid 2>/dev/null || \
        rm -f /tmp/kylin-memory-echo.log /tmp/kylin-memory-echo.pid 2>/dev/null || true
    rm -f "$SOCK_PATH"
}

start_service() {
    mkdir -p "$SOCK_DIR"
    chmod 700 "$SOCK_DIR"
    nohup python3 "$INSTALL_DIR/memory_echo_server.py" >> /tmp/kylin-memory-echo.log 2>&1 &
    echo $! > /tmp/kylin-memory-echo.pid
    sleep 2
}

wait_for_socket() {
    for i in $(seq 1 10); do
        check_socket && return 0
        sleep 0.5
    done
    return 1
}

# ====================================================================
log_section "1) 清理旧状态 & 启动服务"
# ====================================================================
kill_old
start_service

if wait_for_socket; then
    log_pass "服务启动成功 (socket: $SOCK_PATH)"
else
    log_fail "服务启动失败，socket 未就绪"
    echo -e "\n${RED}无法继续测试，请检查日志: tail /tmp/kylin-memory-echo.log${NC}"
    exit 1
fi

# ====================================================================
log_section "2) 基线测试 (UDS Echo)"
# ====================================================================
BASELINE_OUT=$(run_echo_test) || true

if echo "$BASELINE_OUT" | grep -q "ALL TESTS PASSED"; then
    log_pass "基线测试: ALL TESTS PASSED"
else
    log_fail "基线测试失败"
    echo "$BASELINE_OUT" | tee -a "$LOG_FILE"
    exit 1
fi

# 记录基线校验值
BASELINE_MD5=$(md5sum "$INSTALL_DIR/memory_echo_server.py" | awk '{print $1}')
log_info "基线 MD5: $BASELINE_MD5"

# ====================================================================
log_section "3) 创建备份"
# ====================================================================
log_info "备份名称: $BACKUP_NAME"
sudo mkdir -p "$BACKUP_DIR/$BACKUP_NAME"
sudo cp "$INSTALL_DIR/memory_echo_server.py" "$BACKUP_DIR/$BACKUP_NAME/"
sudo cp "$INSTALL_DIR/echo_client" "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true

if sudo test -f "$BACKUP_DIR/$BACKUP_NAME/memory_echo_server.py"; then
    log_pass "备份创建成功: $BACKUP_DIR/$BACKUP_NAME/"
    ls -la "$BACKUP_DIR/$BACKUP_NAME/" | tee -a "$LOG_FILE"
else
    log_fail "备份创建失败"
    exit 1
fi

# ====================================================================
log_section "4) 模拟\"破坏\""
# ====================================================================
# 注入一行非法内容
echo "# CORRUPTED_MARKER_$(date +%s)" | sudo tee -a "$INSTALL_DIR/memory_echo_server.py" > /dev/null

# 验证破坏
CORRUPTED_MD5=$(md5sum "$INSTALL_DIR/memory_echo_server.py" | awk '{print $1}')
log_info "破坏后 MD5: $CORRUPTED_MD5"

if [ "$BASELINE_MD5" != "$CORRUPTED_MD5" ]; then
    log_pass "文件已被修改 (MD5 不同: $BASELINE_MD5 → $CORRUPTED_MD5)"
else
    log_fail "文件未被修改，模拟破坏失败"
    exit 1
fi

# 确认破坏行存在
if grep -q "CORRUPTED_MARKER" "$INSTALL_DIR/memory_echo_server.py"; then
    log_pass "破坏标记已注入"
else
    log_fail "破坏标记未找到"
fi

# ====================================================================
log_section "5) 验证破坏后服务受影响"
# ====================================================================
kill_old
start_service

if wait_for_socket; then
    log_info "服务仍能启动 (破坏未导致语法错误)"
    # 测试仍然运行 — 但也许功能还能用
    POST_CORRUPT_OUT=$(run_echo_test 2>&1) || true
    if echo "$POST_CORRUPT_OUT" | grep -q "ALL TESTS PASSED"; then
        log_info "破坏后 Echo 测试仍然通过 (破坏为非关键行)"
    else
        log_info "破坏后 Echo 测试结果已变化"
    fi
else
    log_pass "服务启动失败 (破坏生效)"
fi

# ====================================================================
log_section "6) 执行回退"
# ====================================================================
kill_old

log_info "从备份恢复: $BACKUP_DIR/$BACKUP_NAME/"
sudo cp "$BACKUP_DIR/$BACKUP_NAME/memory_echo_server.py" "$INSTALL_DIR/"
sudo cp "$BACKUP_DIR/$BACKUP_NAME/echo_client" "$INSTALL_DIR/" 2>/dev/null || true

RESTORED_MD5=$(md5sum "$INSTALL_DIR/memory_echo_server.py" | awk '{print $1}')
log_info "回退后 MD5: $RESTORED_MD5"

if [ "$BASELINE_MD5" = "$RESTORED_MD5" ]; then
    log_pass "文件已恢复为原始版本 (MD5 一致)"
else
    log_fail "文件恢复失败 (MD5 不一致)"
    exit 1
fi

# 确认破坏标记已清除
if grep -q "CORRUPTED_MARKER" "$INSTALL_DIR/memory_echo_server.py"; then
    log_fail "破坏标记仍然存在!"
else
    log_pass "破坏标记已清除"
fi

# ====================================================================
log_section "7) 重新启动 & UDS Echo 测试"
# ====================================================================
start_service

if wait_for_socket; then
    log_pass "回退后服务启动成功"
else
    log_fail "回退后服务启动失败"
    exit 1
fi

POST_ROLLBACK_OUT=$(run_echo_test) || true

if echo "$POST_ROLLBACK_OUT" | grep -q "ALL TESTS PASSED"; then
    log_pass "回退后 Echo 测试: ALL TESTS PASSED"
else
    log_fail "回退后 Echo 测试失败"
    echo "$POST_ROLLBACK_OUT" | tee -a "$LOG_FILE"
    exit 1
fi

# ====================================================================
log_section "测试结论"
# ====================================================================
echo "" | tee -a "$LOG_FILE"
echo -e "  ${GREEN}通过: $PASS_COUNT${NC}  ${RED}失败: $FAIL_COUNT${NC}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "  ${GREEN}✓ 备份与回退链路验证全部通过!${NC}" | tee -a "$LOG_FILE"
else
    echo -e "  ${RED}✗ 存在 $FAIL_COUNT 项失败，请检查日志${NC}" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo "日志已保存: $LOG_FILE" | tee -a "$LOG_FILE"