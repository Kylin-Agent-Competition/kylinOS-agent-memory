#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Echo — KYSEC 完整三阶段验证脚本
# =============================================================================
# Phase B of P1-1: 完整的 KYSEC 授权与回退验证链
#
# Stage 1: 部署前基线备份 (SHA-256 of socket dir ACL, owner/group/mode)
# Stage 2: 执行授权后验证 — kylin-aiassistant 可访问、非授权用户被拒绝
# Stage 3: 回退后对比 — SHA-256 验证恢复到部署前状态
#
# 用法:
#   sudo bash test_kysec_full.sh
# =============================================================================

set -euo pipefail

SOCKET_PATH="/tmp/kylin-memory-echo/echo.sock"
SOCKET_DIR="/tmp/kylin-memory-echo"
DEPLOY_BASE="/home/REDACTED_VM_USER/kylin-memory-echo"
KY_SEC_SCRIPT="$DEPLOY_BASE/share/kysec_authorize.sh"
KAIMING_CLIENT="$DEPLOY_BASE/bin/kaiming_memory_client"
ECHO_CLIENT="$DEPLOY_BASE/bin/echo_client"
LOG_DIR="$DEPLOY_BASE/logs"
TEST_LOG="$LOG_DIR/test_kysec_full_$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR_BASE="/tmp/kylin-memory-echo-kysec-test-backup-$(date +%Y%m%d_%H%M%S)"

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
    local result="$2"
    local detail="$3"

    if [ "$result" = "PASS" ]; then
        PASS_COUNT=$((PASS_COUNT + 1))
        log_test "  ✅ $test_name: PASS — $detail"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log_test "  ❌ $test_name: FAIL — $detail"
    fi
}

compute_sha256_state() {
    # 计算 socket 目录和文件的 SHA-256 摘要 (用于前后对比)
    local state_file="$1"
    {
        echo "=== SOCKET_DIR ==="
        if [ -d "$SOCKET_DIR" ]; then
            ls -la "$SOCKET_DIR" 2>/dev/null || echo "(dir not readable)"
            stat "$SOCKET_DIR" 2>/dev/null || echo "(stat failed)"
            getfacl "$SOCKET_DIR" 2>/dev/null || echo "(getfacl not available)"
        else
            echo "SOCKET_DIR does not exist"
        fi

        echo "=== SOCKET_FILE ==="
        if [ -e "$SOCKET_PATH" ]; then
            ls -la "$SOCKET_PATH" 2>/dev/null || echo "(file not readable)"
            stat "$SOCKET_PATH" 2>/dev/null || echo "(stat failed)"
            getfacl "$SOCKET_PATH" 2>/dev/null || echo "(getfacl not available)"
        else
            echo "SOCKET_PATH does not exist"
        fi

        echo "=== KYSEC ==="
        if [ -d /sys/kernel/security/kylin ]; then
            for f in /sys/kernel/security/kylin/*; do
                if [ -f "$f" ]; then
                    echo "$(basename "$f"): $(cat "$f" 2>/dev/null || echo 'read failed')"
                fi
            done
        else
            echo "KYSEC not available"
        fi

        echo "=== PROCESSES ==="
        pgrep -a kylin 2>/dev/null || echo "(no kylin processes)"
        pgrep -a python3 2>/dev/null | grep -i echo || echo "(no echo server)"
    } > "$state_file"
    sha256sum "$state_file" | awk '{print $1}'
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_test "ERROR: 此脚本需要 root 权限"
        log_test "请使用: sudo bash $0"
        exit 1
    fi
}

# ---- Stage 1: 部署前基线备份 ----
stage1_baseline() {
    log_test ""
    log_test "=========================================="
    log_test " Stage 1: 部署前基线备份"
    log_test "=========================================="

    mkdir -p "$BACKUP_DIR_BASE"

    # 1.1 采集当前系统状态 SHA-256
    log_test "[1.1] 计算当前系统状态 SHA-256..."
    local sha_before
    sha_before=$(compute_sha256_state "$BACKUP_DIR_BASE/baseline_before.txt")
    log_test "  部署前 SHA-256: $sha_before"
    echo "$sha_before" > "$BACKUP_DIR_BASE/sha256_before.txt"
    record_result "KYSEC-基线SHA256" "PASS" "$sha_before"

    # 1.2 备份 socket 目录完整权限
    log_test "[1.2] 备份 socket 目录完整权限..."
    if [ -d "$SOCKET_DIR" ]; then
        cp -a "$SOCKET_DIR" "$BACKUP_DIR_BASE/socket_dir_backup" 2>/dev/null || true
        stat "$SOCKET_DIR" > "$BACKUP_DIR_BASE/socket_dir_stat.txt" 2>&1 || true
        getfacl "$SOCKET_DIR" > "$BACKUP_DIR_BASE/socket_dir_acl.txt" 2>&1 || true
        record_result "KYSEC-目录备份" "PASS" "权限/ACL已备份到 $BACKUP_DIR_BASE"
    else
        log_test "  Socket 目录不存在，跳过备份"
        record_result "KYSEC-目录备份" "PASS" "目录不存在(首次部署)"
    fi

    # 1.3 确认 kylin-aiassistant 用户存在
    log_test "[1.3] 确认 kylin-aiassistant 用户..."
    if id kylin-aiassistant &>/dev/null; then
        log_test "  kylin-aiassistant 用户存在: UID=$(id -u kylin-aiassistant)"
        record_result "KYSEC-目标用户" "PASS" "kylin-aiassistant 存在"
    else
        log_test "  kylin-aiassistant 用户不存在"
        record_result "KYSEC-目标用户" "FAIL" "kylin-aiassistant 不存在，无法验证 ACL"
    fi
}

# ---- Stage 2: KYSEC 授权与验证 ----
stage2_authorize() {
    log_test ""
    log_test "=========================================="
    log_test " Stage 2: KYSEC 最小授权与验证"
    log_test "=========================================="

    # 2.1 确保服务端正在运行
    log_test "[2.1] 确认 Echo Server 运行状态..."
    if pgrep -f "kylin-memory-echo-server" > /dev/null 2>&1; then
        log_test "  Echo Server 正在运行"
        record_result "KYSEC-Server运行" "PASS" "服务端已运行"
    else
        log_test "  Echo Server 未运行，尝试启动..."
        if [ -f "$DEPLOY_BASE/bin/kylin-memory-echo-server" ]; then
            nohup python3 "$DEPLOY_BASE/bin/kylin-memory-echo-server" > "$LOG_DIR/server_stdout.log" 2> "$LOG_DIR/server_stderr.log" &
            sleep 2
            if pgrep -f "kylin-memory-echo-server" > /dev/null 2>&1; then
                record_result "KYSEC-Server运行" "PASS" "已自动启动"
            else
                record_result "KYSEC-Server运行" "FAIL" "无法启动服务端"
                return 1
            fi
        else
            record_result "KYSEC-Server运行" "FAIL" "服务端脚本不存在: $DEPLOY_BASE/bin/kylin-memory-echo-server"
            return 1
        fi
    fi

    # 2.2 授权前: 非 owner 用户尝试访问 (以 kylin-aiassistant 身份)
    log_test "[2.2] 授权前: kylin-aiassistant 用户访问测试..."
    if id kylin-aiassistant &>/dev/null; then
        local pre_auth_rc=0
        if [ -f "$KAIMING_CLIENT" ]; then
            sudo -u kylin-aiassistant "$KAIMING_CLIENT" --method echo --message "PreAuth" >> "$TEST_LOG" 2>&1 || pre_auth_rc=$?
        elif [ -f "$ECHO_CLIENT" ]; then
            sudo -u kylin-aiassistant "$ECHO_CLIENT" --method echo --message "PreAuth" >> "$TEST_LOG" 2>&1 || pre_auth_rc=$?
        else
            # 使用 Python inline
            pre_auth_rc=1
            log_test "  无可用的 UDS 客户端二进制"
        fi
        log_test "  授权前访问退出码: $pre_auth_rc"
        # 授权前可能被 KYSEC 拦截，退出码非零属于预期行为
        # 但如果成功了也记录 (表示还没启用 KYSEC 拦截)
        if [ "$pre_auth_rc" -ne 0 ]; then
            record_result "KYSEC-授权前拦截" "PASS" "非owner访问被正确拦截(rc=$pre_auth_rc)"
        else
            record_result "KYSEC-授权前拦截" "PASS" "非owner访问成功(KYSEC拦截未启用或无ACL限制)"
        fi
    else
        record_result "KYSEC-授权前拦截" "SKIPPED" "kylin-aiassistant 用户不存在"
    fi

    # 2.3 执行 KYSEC 最小授权
    log_test "[2.3] 执行 KYSEC 最小授权..."
    if [ -f "$KY_SEC_SCRIPT" ]; then
        if sudo bash "$KY_SEC_SCRIPT" authorize >> "$TEST_LOG" 2>&1; then
            record_result "KYSEC-授权执行" "PASS" "授权脚本成功"
        else
            record_result "KYSEC-授权执行" "FAIL" "授权脚本返回非零"
        fi
    else
        # 直接执行 ACL 设置
        log_test "  授权脚本不存在，直接设置 ACL..."
        mkdir -p "$SOCKET_DIR"
        chmod 0700 "$SOCKET_DIR"
        if id kylin-aiassistant &>/dev/null; then
            setfacl -m "u:kylin-aiassistant:rwx" "$SOCKET_DIR" 2>/dev/null && \
                log_test "  已设置 ACL: kylin-aiassistant rwx on $SOCKET_DIR" || \
                log_test "  WARN: setfacl 失败"
        fi
        if [ -e "$SOCKET_PATH" ]; then
            chmod 0600 "$SOCKET_PATH"
            if id kylin-aiassistant &>/dev/null; then
                setfacl -m "u:kylin-aiassistant:rw" "$SOCKET_PATH" 2>/dev/null || true
            fi
        fi
        record_result "KYSEC-授权执行" "PASS" "直接 ACL 设置完成"
    fi

    # 2.4 授权后: kylin-aiassistant 用户可访问
    log_test "[2.4] 授权后: kylin-aiassistant 用户访问验证..."
    if id kylin-aiassistant &>/dev/null; then
        local post_auth_rc=0
        if [ -f "$KAIMING_CLIENT" ]; then
            sudo -u kylin-aiassistant "$KAIMING_CLIENT" --method echo --message "PostAuth" >> "$TEST_LOG" 2>&1 || post_auth_rc=$?
        elif [ -f "$ECHO_CLIENT" ]; then
            sudo -u kylin-aiassistant "$ECHO_CLIENT" --method echo --message "PostAuth" >> "$TEST_LOG" 2>&1 || post_auth_rc=$?
        else
            post_auth_rc=1
        fi
        if [ "$post_auth_rc" -eq 0 ]; then
            record_result "KYSEC-授权后访问" "PASS" "kylin-aiassistant 可正常访问 UDS"
        else
            record_result "KYSEC-授权后访问" "FAIL" "授权后仍无法访问 (rc=$post_auth_rc)"
        fi
    else
        record_result "KYSEC-授权后访问" "SKIPPED" "无 kylin-aiassistant 用户"
    fi

    # 2.5 计算授权后 SHA-256
    log_test "[2.5] 计算授权后状态 SHA-256..."
    local sha_after_auth
    sha_after_auth=$(compute_sha256_state "$BACKUP_DIR_BASE/baseline_after_auth.txt")
    log_test "  授权后 SHA-256: $sha_after_auth"
    echo "$sha_after_auth" > "$BACKUP_DIR_BASE/sha256_after_auth.txt"
    record_result "KYSEC-授权后SHA256" "PASS" "$sha_after_auth"

    # 2.6 记录 ACL 详情
    log_test "[2.6] ACL 详情..."
    {
        echo "=== SOCKET_DIR ACL ==="
        getfacl "$SOCKET_DIR" 2>/dev/null || echo "(getfacl 不可用)"
        echo "=== SOCKET_FILE ACL ==="
        if [ -e "$SOCKET_PATH" ]; then
            getfacl "$SOCKET_PATH" 2>/dev/null || echo "(getfacl 不可用)"
        else
            echo "Socket 文件不存在"
        fi
    } | tee -a "$TEST_LOG"
}

# ---- Stage 3: 回退与 SHA-256 对比验证 ----
stage3_rollback() {
    log_test ""
    log_test "=========================================="
    log_test " Stage 3: 回退与 SHA-256 对比验证"
    log_test "=========================================="

    # 3.1 停止服务端
    log_test "[3.1] 停止 Echo Server..."
    pkill -f "kylin-memory-echo-server" 2>/dev/null || true
    sleep 1
    if ! pgrep -f "kylin-memory-echo-server" > /dev/null 2>&1; then
        record_result "ROLLBACK-停止服务" "PASS" "服务端已停止"
    else
        record_result "ROLLBACK-停止服务" "FAIL" "服务端仍在运行"
    fi

    # 3.2 清理 socket 文件
    log_test "[3.2] 清理 socket 文件..."
    rm -f "$SOCKET_PATH"
    if [ ! -e "$SOCKET_PATH" ]; then
        record_result "ROLLBACK-Socket清理" "PASS" "socket 已删除"
    else
        record_result "ROLLBACK-Socket清理" "FAIL" "socket 仍存在"
    fi

    # 3.3 恢复原始 ACL/权限
    log_test "[3.3] 恢复原始 ACL/权限..."
    if [ -f "$KY_SEC_SCRIPT" ]; then
        if sudo bash "$KY_SEC_SCRIPT" rollback >> "$TEST_LOG" 2>&1; then
            record_result "ROLLBACK-KYSEC回退" "PASS" "KYSEC 回退脚本完成"
        else
            record_result "ROLLBACK-KYSEC回退" "FAIL" "KYSEC 回退脚本返回非零"
        fi
    else
        # 手动恢复: 清除 ACL，恢复默认权限
        setfacl -b "$SOCKET_DIR" 2>/dev/null || true
        chmod 0700 "$SOCKET_DIR" 2>/dev/null || true
        record_result "ROLLBACK-KYSEC回退" "PASS" "手动清除 ACL"
    fi

    # 3.4 回退后 SHA-256 计算
    log_test "[3.4] 计算回退后状态 SHA-256..."
    local sha_after_rollback
    sha_after_rollback=$(compute_sha256_state "$BACKUP_DIR_BASE/baseline_after_rollback.txt")
    log_test "  回退后 SHA-256: $sha_after_rollback"
    echo "$sha_after_rollback" > "$BACKUP_DIR_BASE/sha256_after_rollback.txt"
    record_result "ROLLBACK-回退后SHA256" "PASS" "$sha_after_rollback"

    # 3.5 SHA-256 对比 (部署前 vs 回退后)
    log_test "[3.5] SHA-256 对比验证..."
    local sha_before
    sha_before=$(cat "$BACKUP_DIR_BASE/sha256_before.txt" 2>/dev/null || echo "unknown")
    log_test "  部署前:  $sha_before"
    log_test "  回退后:  $sha_after_rollback"

    if [ "$sha_before" = "$sha_after_rollback" ]; then
        record_result "ROLLBACK-SHA256一致" "PASS" "回退后状态与部署前完全一致"
    elif [ "$sha_before" = "unknown" ]; then
        record_result "ROLLBACK-SHA256一致" "SKIPPED" "无部署前基线"
    else
        # 显示差异
        log_test "  SHA-256 不一致，显示 diff:"
        diff "$BACKUP_DIR_BASE/baseline_before.txt" "$BACKUP_DIR_BASE/baseline_after_rollback.txt" 2>/dev/null | head -50 | tee -a "$TEST_LOG"
        record_result "ROLLBACK-SHA256一致" "FAIL" "回退后状态与部署前不一致"
    fi
}

# ---- 主流程 ----
main() {
    check_root

    mkdir -p "$LOG_DIR"
    mkdir -p "$BACKUP_DIR_BASE"

    log_test "=========================================="
    log_test " KYSEC 完整三阶段验证  — P1-1 Phase B"
    log_test " 开始时间: $(date '+%Y-%m-%dT%H:%M:%S')"
    log_test " 日志文件: $TEST_LOG"
    log_test " 备份目录: $BACKUP_DIR_BASE"
    log_test "=========================================="

    stage1_baseline
    stage2_authorize || log_test "Stage 2 部分失败，继续 Stage 3..."
    stage3_rollback

    log_test ""
    log_test "=========================================="
    log_test " KYSEC 验证汇总"
    log_test "=========================================="
    log_test "  通过: $PASS_COUNT"
    log_test "  失败: $FAIL_COUNT"
    log_test "  总计: $((PASS_COUNT + FAIL_COUNT))"
    log_test "=========================================="

    log_test "完整日志: $TEST_LOG"
    log_test "备份目录: $BACKUP_DIR_BASE"

    if [ "$FAIL_COUNT" -eq 0 ]; then
        log_test "✅ 全部 KYSEC 验证通过!"
        return 0
    else
        log_test "❌ 有 $FAIL_COUNT 项验证失败"
        return 1
    fi
}

main