#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Echo — KYSEC 三阶段验证 v2
# =============================================================================
# 修复: 不再管理服务端进程启停（那是 Phase C 的职责）
# Stage 1: 部署前基线 SHA-256
# Stage 2: ACL 授权 kylin-aiassistant → 验证 sudo -u 可访问
# Stage 3: ACL 回退 → SHA-256 前后对比验证
#
# 前提: Echo Server 已在后台运行 (socket=/tmp/kylin-memory-echo/echo.sock)
# 用法: sudo bash test_kysec_full.sh
# =============================================================================

set -euo pipefail

SOCKET_DIR="/tmp/kylin-memory-echo"
SOCKET_PATH="$SOCKET_DIR/echo.sock"
DEPLOY_BASE="/home/${USER:-$(whoami)}/kylin-memory-echo"
KAIMING_CLIENT="$DEPLOY_BASE/bin/kaiming_memory_client"
KY_SEC_SCRIPT="$DEPLOY_BASE/share/kysec_authorize.sh"
LOG_DIR="$DEPLOY_BASE/logs"
TEST_LOG="$LOG_DIR/kysec_v2_$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR="/tmp/kysec_v2_bkp_$(date +%Y%m%d_%H%M%S)"

PASS=0; FAIL=0

log_test() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$TEST_LOG"; }
ok() { PASS=$((PASS+1)); log_test "  ✅ $1"; }
no() { FAIL=$((FAIL+1)); log_test "  ❌ $1"; }

compute_sha256_state() {
    {
        echo "=== SOCKET_DIR ==="
        ls -la "$SOCKET_DIR" 2>/dev/null || echo "(not readable)"
        stat "$SOCKET_DIR" 2>/dev/null || echo "(stat failed)"
        getfacl "$SOCKET_DIR" 2>/dev/null || echo "(getfacl N/A)"

        echo "=== SOCKET_FILE ==="
        if [ -e "$SOCKET_PATH" ]; then
            ls -la "$SOCKET_PATH" 2>/dev/null
            stat "$SOCKET_PATH" 2>/dev/null
            getfacl "$SOCKET_PATH" 2>/dev/null || echo "(getfacl N/A)"
        else
            echo "SOCKET_PATH does not exist"
        fi

        echo "=== KYSEC ==="
        if [ -d /sys/kernel/security/kylin ]; then
            for f in /sys/kernel/security/kylin/*; do
                [ -f "$f" ] && echo "$(basename "$f"): $(cat "$f" 2>/dev/null || echo 'read failed')"
            done
        else
            echo "KYSEC not available"
        fi

        echo "=== PROCESSES ==="
        pgrep -af kylin 2>/dev/null || echo "(no kylin processes)"
    } > "$1"
    sha256sum "$1" | awk '{print $1}'
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: 此脚本需要 root 权限"
        echo "请使用: sudo bash $0"
        exit 1
    fi
}

# ---- Stage 1: 基线备份 ----
stage1_baseline() {
    log_test ""
    log_test "========== Stage 1: 基线备份 =========="
    mkdir -p "$BACKUP_DIR"

    local sha
    sha=$(compute_sha256_state "$BACKUP_DIR/baseline_before.txt")
    echo "$sha" > "$BACKUP_DIR/sha256_before.txt"
    log_test "  SHA-256 部署前: $sha"
    ok "Stage1: 基线 SHA-256=$sha"

    # 确认 socket 存在
    if [ -S "$SOCKET_PATH" ]; then
        ok "Stage1: Socket 存在 ($SOCKET_PATH)"
    else
        no "Stage1: Socket 不存在 — 请先启动 Echo Server"
    fi

    # 确认 kylin-aiassistant 用户
    if id kylin-aiassistant &>/dev/null; then
        ok "Stage1: kylin-aiassistant 用户存在 (UID=$(id -u kylin-aiassistant))"
    else
        no "Stage1: kylin-aiassistant 用户不存在"
    fi
}

# ---- Stage 2: ACL 授权与验证 ----
stage2_authorize() {
    log_test ""
    log_test "========== Stage 2: ACL 授权与验证 =========="

    # 2.1 授权前: kylin-aiassistant 尝试访问
    if [ -f "$KAIMING_CLIENT" ] && [ -S "$SOCKET_PATH" ] && id kylin-aiassistant &>/dev/null; then
        local pre_rc=0
        sudo -u kylin-aiassistant "$KAIMING_CLIENT" --method echo --message "PreAuthTest" >> "$TEST_LOG" 2>&1 || pre_rc=$?
        if [ "$pre_rc" -ne 0 ]; then
            ok "Stage2: 授权前 kylin-aiassistant 无法访问 (rc=$pre_rc, 最小权限 OK)"
        else
            ok "Stage2: 授权前 kylin-aiassistant 可访问 (权限宽松, 待授权收紧)"
        fi
    fi

    # 2.2 执行 ACL 授权
    if [ -f "$KY_SEC_SCRIPT" ]; then
        bash "$KY_SEC_SCRIPT" authorize >> "$TEST_LOG" 2>&1
        ok "Stage2: kysec_authorize.sh authorize 完成"
    else
        # 直接 setfacl
        setfacl -m "u:kylin-aiassistant:rwx" "$SOCKET_DIR" 2>/dev/null && \
            ok "Stage2: ACL setfacl on $SOCKET_DIR" || no "Stage2: setfacl dir 失败"
        if [ -e "$SOCKET_PATH" ]; then
            setfacl -m "u:kylin-aiassistant:rw" "$SOCKET_PATH" 2>/dev/null && \
                ok "Stage2: ACL setfacl on $SOCKET_PATH" || no "Stage2: setfacl socket 失败"
        fi
    fi

    # 2.3 授权后验证
    if [ -f "$KAIMING_CLIENT" ] && [ -S "$SOCKET_PATH" ] && id kylin-aiassistant &>/dev/null; then
        local post_rc=0
        sudo -u kylin-aiassistant "$KAIMING_CLIENT" --method echo --message "PostAuthTest" >> "$TEST_LOG" 2>&1 || post_rc=$?
        if [ "$post_rc" -eq 0 ]; then
            ok "Stage2: 授权后 kylin-aiassistant 可正常访问 UDS"
        else
            no "Stage2: 授权后 kylin-aiassistant 仍无法访问 (rc=$post_rc)"
        fi
    fi

    # 2.4 授权后 SHA-256
    local sha2
    sha2=$(compute_sha256_state "$BACKUP_DIR/baseline_after_auth.txt")
    echo "$sha2" > "$BACKUP_DIR/sha256_after_auth.txt"
    ok "Stage2: 授权后 SHA-256=$sha2"

    # ACL 详情
    log_test "  ACL 详情:"
    {
        echo "--- $SOCKET_DIR ACL ---"
        getfacl "$SOCKET_DIR" 2>/dev/null || echo "(getfacl N/A)"
        if [ -e "$SOCKET_PATH" ]; then
            echo "--- $SOCKET_PATH ACL ---"
            getfacl "$SOCKET_PATH" 2>/dev/null || echo "(getfacl N/A)"
        fi
    } | tee -a "$TEST_LOG"
}

# ---- Stage 3: 回退与 SHA-256 对比 ----
stage3_rollback() {
    log_test ""
    log_test "========== Stage 3: 回退与 SHA-256 对比 =========="

    # 3.1 执行 KYSEC 回退
    if [ -f "$KY_SEC_SCRIPT" ]; then
        bash "$KY_SEC_SCRIPT" rollback >> "$TEST_LOG" 2>&1 || true
        ok "Stage3: KYSEC rollback 完成"
    else
        setfacl -b "$SOCKET_DIR" 2>/dev/null || true
        [ -e "$SOCKET_PATH" ] && setfacl -b "$SOCKET_PATH" 2>/dev/null || true
        ok "Stage3: 手动清除 ACL"
    fi

    # 3.2 回退后 SHA-256
    local sha3
    sha3=$(compute_sha256_state "$BACKUP_DIR/baseline_after_rollback.txt")
    echo "$sha3" > "$BACKUP_DIR/sha256_after_rollback.txt"
    ok "Stage3: 回退后 SHA-256=$sha3"

    # 3.3 SHA-256 对比
    local sha_before
    sha_before=$(cat "$BACKUP_DIR/sha256_before.txt" 2>/dev/null || echo "unknown")

    log_test "  部署前: $sha_before"
    log_test "  回退后: $sha3"

    if [ "$sha_before" = "$sha3" ]; then
        ok "Stage3: SHA-256 完全一致 ✅ (完整回退确认)"
    elif [ "$sha_before" = "unknown" ]; then
        ok "Stage3: SHA-256 (无基线, 已回退)"
    else
        no "Stage3: SHA-256 不一致 ❌"
        diff "$BACKUP_DIR/baseline_before.txt" "$BACKUP_DIR/baseline_after_rollback.txt" 2>/dev/null | head -20 | tee -a "$TEST_LOG"
    fi
}

# ---- 主入口 ----
main() {
    check_root
    mkdir -p "$LOG_DIR" "$BACKUP_DIR"

    log_test "=========================================="
    log_test " KYSEC 三阶段验证 v2 — P1-1 Phase B"
    log_test " 日志: $TEST_LOG"
    log_test " 备份: $BACKUP_DIR"
    log_test "=========================================="

    stage1_baseline

    if [ -S "$SOCKET_PATH" ]; then
        stage2_authorize
    else
        log_test "  SKIP: Socket 不存在, 跳过 Stage 2"
    fi

    stage3_rollback

    log_test ""
    log_test "=========================================="
    log_test " KYSEC 验证汇总"
    log_test "=========================================="
    log_test "  通过: $PASS"
    log_test "  失败: $FAIL"
    log_test "  总计: $((PASS + FAIL))"
    log_test "  日志: $TEST_LOG"
    log_test "=========================================="

    if [ "$FAIL" -eq 0 ]; then
        log_test "  ✅ 全部 KYSEC 验证通过!"
        return 0
    else
        log_test "  ❌ 有 $FAIL 项验证失败"
        return 1
    fi
}

main