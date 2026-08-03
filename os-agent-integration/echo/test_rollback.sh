#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Echo — 测试资源清理脚本
# =============================================================================
# ⚠️ 不是完整原版恢复 — 仅清理测试写入的文件/目录/systemd unit
# 测试完整生命周期: 部署 → 验证 → 资源清理 → 验证恢复
#
# 用法:
#   bash test_rollback.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE_BASE="/home/$(whoami)/kylin-memory-echo"
SOCKET_PATH="/tmp/kylin-memory-echo/echo.sock"
SOCKET_DIR="/tmp/kylin-memory-echo"
LOG_DIR="$REMOTE_BASE/logs"
TEST_LOG="$LOG_DIR/test_rollback_$(date +%Y%m%d_%H%M%S).log"
SERVER_PID=""
CLIENT_BIN="$REMOTE_BASE/bin/echo_client"

PASS_COUNT=0
FAIL_COUNT=0

# ---- 工具函数 ----
log_test() {
    local ts
    ts=$(date '+%Y-%m-%dT%H:%M:%S')
    echo "[$ts] $1" | tee -a "$TEST_LOG"
}

record_result() {
    local test_name="$1"
    local result="$2"  # PASS or FAIL
    local detail="$3"

    if [ "$result" = "PASS" ]; then
        PASS_COUNT=$((PASS_COUNT + 1))
        log_test "  ✅ $test_name: PASS — $detail"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log_test "  ❌ $test_name: FAIL — $detail"
    fi
}

cleanup_server() {
    if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        log_test "正在停止 Echo Server (PID=$SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    # 清理残留 socket
    rm -f "$SOCKET_PATH"
}

# ---- 测试用例 ----
test_phase1_baseline() {
    log_test ""
    log_test "========== Phase 1: 基线采集 =========="

    # 1.1 系统状态
    log_test "[1.1] 系统信息"
    uname -a | tee -a "$TEST_LOG"
    log_test "主机名: $(hostname)"
    log_test "当前用户: $(whoami)"
    record_result "系统信息采集" "PASS" "已完成基线采集"

    # 1.2 KYSEC 状态 (回退前)
    log_test "[1.2] KYSEC 回退前状态"
    if [ -d /sys/kernel/security/kylin ]; then
        for f in /sys/kernel/security/kylin/*; do
            if [ -f "$f" ]; then
                val=$(cat "$f" 2>/dev/null || echo "read failed")
                log_test "  KYSEC $(basename "$f"): $val"
            fi
        done
    else
        log_test "  KYSEC 内核接口不可用 (非麒麟系统)"
    fi
    record_result "KYSEC 基线采集" "PASS" "已完成"

    # 1.3 进程基线
    log_test "[1.3] 进程基线"
    pgrep -a kylin || log_test "  无 kylin 相关进程"
    record_result "进程基线采集" "PASS" "已完成"
}

test_phase2_build_and_start() {
    log_test ""
    log_test "========== Phase 2: 构建与启动 =========="

    # 2.1 构建客户端
    log_test "[2.1] 构建 Echo Client..."
    if [ ! -f "$REMOTE_BASE/echo_client.cpp" ]; then
        log_test "  WARN: echo_client.cpp 不存在，尝试从当前目录复制..."
        cp "$SCRIPT_DIR/echo_client.cpp" "$REMOTE_BASE/" 2>/dev/null || true
    fi

    if g++ -std=c++17 -O2 "$REMOTE_BASE/echo_client.cpp" -o "$CLIENT_BIN" 2>>"$TEST_LOG"; then
        record_result "客户端构建" "PASS" "编译成功"
    else
        record_result "客户端构建" "FAIL" "编译失败，详见日志"
        return 1
    fi

    # 2.2 检查服务端
    SERVER_SCRIPT="$REMOTE_BASE/bin/kylin-memory-echo-server"
    if [ ! -f "$SERVER_SCRIPT" ]; then
        log_test "  WARN: 服务端脚本不存在，复制..."
        cp "$SCRIPT_DIR/memory_echo_server.py" "$SERVER_SCRIPT" 2>/dev/null || true
        chmod +x "$SERVER_SCRIPT"
    fi

    # 2.3 创建 socket 目录
    mkdir -p "$SOCKET_DIR"
    chmod 0700 "$SOCKET_DIR"

    # 2.4 启动服务端
    log_test "[2.2] 启动 Echo Server..."
    cleanup_server  # 先清理旧进程
    python3 "$SERVER_SCRIPT" > "$LOG_DIR/server_stdout.log" 2> "$LOG_DIR/server_stderr.log" &
    SERVER_PID=$!
    log_test "  服务端 PID=$SERVER_PID"

    # 等待服务端就绪
    sleep 1
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        record_result "服务端启动" "PASS" "PID=$SERVER_PID"
    else
        record_result "服务端启动" "FAIL" "进程未存活"
        log_test "  服务端 stderr:"
        cat "$LOG_DIR/server_stderr.log" 2>/dev/null | tail -20 | tee -a "$TEST_LOG"
        return 1
    fi

    # 等待 socket 创建
    for i in $(seq 1 10); do
        if [ -e "$SOCKET_PATH" ]; then
            log_test "  Socket 已创建: $SOCKET_PATH"
            break
        fi
        sleep 0.5
    done

    if [ -e "$SOCKET_PATH" ]; then
        record_result "Socket 文件创建" "PASS" "$SOCKET_PATH 存在"
    else
        record_result "Socket 文件创建" "FAIL" "10次检查未发现 socket"
    fi
}

test_phase3_uds_echo() {
    log_test ""
    log_test "========== Phase 3: UDS 收发测试 =========="

    local rc

    # 3.1 echo 方法
    log_test "[3.1] 测试 echo 方法..."
    if "$CLIENT_BIN" --method echo --message "Hello麒麟" >> "$TEST_LOG" 2>&1; then
        record_result "UDS echo 往返" "PASS" "echo 方法成功"
    else
        record_result "UDS echo 往返" "FAIL" "客户端返回非零"
    fi

    # 3.2 health 方法
    log_test "[3.2] 测试 health 方法..."
    if "$CLIENT_BIN" --method health >> "$TEST_LOG" 2>&1; then
        record_result "UDS health 查询" "PASS" "服务端健康"
    else
        record_result "UDS health 查询" "FAIL" "客户端返回非零"
    fi

    # 3.3 memory.retrieve 方法
    log_test "[3.3] 测试 memory.retrieve 方法..."
    if "$CLIENT_BIN" --method memory.retrieve --message "软件最佳实践" >> "$TEST_LOG" 2>&1; then
        record_result "UDS memory.retrieve" "PASS" "空上下文返回正常"
    else
        record_result "UDS memory.retrieve" "FAIL" "客户端返回非零"
    fi

    # 3.4 未知方法 - 连接失败/超时/JOSN解析失败必须判定FAIL
    # 只有收到 status=="error" 的结构化响应才能PASS
    log_test "[3.4] 测试未知方法 (预期错误响应)..."
    local unknown_output
    unknown_output=$("$CLIENT_BIN" --method "nonexistent.method" 2>&1) || true
    if echo "$unknown_output" | grep -q '"status"[[:space:]]*:[[:space:]]*"error"'; then
        record_result "UDS 未知方法降级" "PASS" "收到status=error响应"
    elif echo "$unknown_output" | grep -qi "connection refused\|no such file\|timeout\|operation not permitted"; then
        record_result "UDS 未知方法降级" "FAIL" "连接失败: $unknown_output"
    else
        record_result "UDS 未知方法降级" "FAIL" "未收到预期error响应: $unknown_output"
    fi
}

test_phase4_kysec() {
    log_test ""
    log_test "========== Phase 4: KYSEC 最小授权验证 =========="

    local kysec_script="$REMOTE_BASE/share/kysec_authorize.sh"
    if [ ! -f "$kysec_script" ]; then
        kysec_script="$SCRIPT_DIR/kysec_authorize.sh"
    fi

    # 4.1 授权前状态
    log_test "[4.1] KYSEC 授权前状态..."
    sudo bash "$kysec_script" status >> "$TEST_LOG" 2>&1 || true

    # 4.2 执行授权
    log_test "[4.2] 执行 KYSEC 最小授权..."
    if sudo bash "$kysec_script" authorize >> "$TEST_LOG" 2>&1; then
        record_result "KYSEC 授权执行" "PASS" "授权脚本完成"
    else
        record_result "KYSEC 授权执行" "FAIL" "授权脚本返回非零"
    fi

    # 4.3 授权后状态
    log_test "[4.3] KYSEC 授权后状态..."
    sudo bash "$kysec_script" status >> "$TEST_LOG" 2>&1 || true

    # 4.4 验证 UDS 在授权后仍可访问
    log_test "[4.4] 验证授权后 UDS 仍可访问..."
    if "$CLIENT_BIN" --method echo --message "AfterKYSEC" >> "$TEST_LOG" 2>&1; then
        record_result "KYSEC 后 UDS 可访问" "PASS" "授权后通信正常"
    else
        record_result "KYSEC 后 UDS 可访问" "FAIL" "授权后通信失败"
    fi

    # 4.5 记录 Socket ACL
    log_test "[4.5] Socket 最终 ACL..."
    ls -la "$SOCKET_DIR" >> "$TEST_LOG" 2>&1
    getfacl "$SOCKET_DIR" 2>/dev/null >> "$TEST_LOG" || echo "(getfacl 不可用)" >> "$TEST_LOG"

    if [ -e "$SOCKET_PATH" ]; then
        ls -la "$SOCKET_PATH" >> "$TEST_LOG" 2>&1
        getfacl "$SOCKET_PATH" 2>/dev/null >> "$TEST_LOG" || echo "(getfacl 不可用)" >> "$TEST_LOG"
    fi
}

test_phase5_rollback() {
    log_test ""
    log_test "========== Phase 5: 测试资源清理 =========="

    # 5.1 停止服务端
    log_test "[5.1] 停止 Echo Server..."
    cleanup_server
    if ! kill -0 "${SERVER_PID:-}" 2>/dev/null; then
        record_result "服务端停止" "PASS" "进程已终止"
    else
        record_result "服务端停止" "FAIL" "进程仍在运行"
    fi

    # 5.2 清理 socket 文件
    log_test "[5.2] 清理 socket 文件..."
    rm -f "$SOCKET_PATH"
    if [ ! -e "$SOCKET_PATH" ]; then
        record_result "Socket 清理" "PASS" "socket 文件已删除"
    else
        record_result "Socket 清理" "FAIL" "socket 文件仍存在"
    fi

    # 5.3 KYSEC 回退
    log_test "[5.3] KYSEC 回退..."
    local kysec_script="$REMOTE_BASE/share/kysec_authorize.sh"
    if [ ! -f "$kysec_script" ]; then
        kysec_script="$SCRIPT_DIR/kysec_authorize.sh"
    fi

    if sudo bash "$kysec_script" rollback >> "$TEST_LOG" 2>&1; then
        record_result "KYSEC 回退执行" "PASS" "回退完成"
    else
        record_result "KYSEC 回退执行" "FAIL" "回退脚本返回非零"
    fi

    # 5.4 验证回退后系统状态
    log_test "[5.4] 验证回退后状态..."
    if [ ! -e "$SOCKET_PATH" ]; then
        record_result "回退后 socket 清理" "PASS" "socket 不存在(已清理)"
    else
        record_result "回退后 socket 清理" "FAIL" "socket 仍存在"
    fi

    # 5.5 验证 KYSEC 回退后状态
    log_test "[5.5] 回退后 KYSEC 状态..."
    sudo bash "$kysec_script" status >> "$TEST_LOG" 2>&1 || true
    record_result "回退后 KYSEC 状态" "PASS" "状态已记录"
}

test_phase6_summary() {
    log_test ""
    log_test "=========================================="
    log_test " 测试汇总"
    log_test "=========================================="
    log_test "  通过: $PASS_COUNT"
    log_test "  失败: $FAIL_COUNT"
    log_test "  总计: $((PASS_COUNT + FAIL_COUNT))"
    log_test "=========================================="

    if [ "$FAIL_COUNT" -eq 0 ]; then
        log_test "  ✅ 全部测试通过!"
        return 0
    else
        log_test "  ❌ 有 $FAIL_COUNT 项测试失败"
        return 1
    fi
}

# ---- 主流程 ----
main() {
    mkdir -p "$LOG_DIR"

    log_test "=========================================="
    log_test " Kylin Memory Echo — 测试资源清理"
    log_test " 开始时间: $(date '+%Y-%m-%dT%H:%M:%S')"
    log_test " 日志文件: $TEST_LOG"
    log_test "=========================================="

    test_phase1_baseline

    if test_phase2_build_and_start; then
        test_phase3_uds_echo
        test_phase4_kysec
    else
        log_test "Phase 2 失败，跳过后续测试"
    fi

    test_phase5_rollback
    test_phase6_summary

    log_test ""
    log_test "完整日志: $TEST_LOG"
    log_test "服务端日志: $LOG_DIR/server_stdout.log"
    log_test "服务端错误: $LOG_DIR/server_stderr.log"
}

# 确保退出时清理
trap cleanup_server EXIT

main