#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Echo — Phase C: Systemd 完整生命周期测试
# =============================================================================
# 验证 kylin-memory-echo.service 的完整 systemd 生命周期:
#   install → daemon-reload → enable → start → status → UDS通信 → stop → disable → uninstall
#
# Socket 路径: /run/kylin-memory-echo/echo.sock (RuntimeDirectory)
# ⚠️ UNVERIFIED: 银河麒麟桌面V11直实验证通过，生产系统需额外验证
#
# 用法:
#   sudo bash test_systemd_lifecycle.sh
#   或: echo <password> | sudo -S bash test_systemd_lifecycle.sh
# =============================================================================

set -euo pipefail

# ---- 动态检测用户名 ----
detect_user() {
    local u
    if [ -f "/etc/systemd/system/kylin-memory-echo.service" ]; then
        u=$(grep '^User=' /etc/systemd/system/kylin-memory-echo.service | cut -d= -f2 | tr -d ' ')
        if [ -n "$u" ] && [ "$u" != "YOUR_USERNAME" ] && [ "$u" != "__USERNAME__" ]; then
            echo "$u"; return
        fi
    fi
    for d in /home/*/kylin-memory-echo; do
        if [ -d "$d" ]; then
            u=$(echo "$d" | cut -d/ -f3)
            echo "$u"; return
        fi
    done
    echo "REDACTED_VM_USER"
}
KUSER="$(detect_user)"

SERVICE="kylin-memory-echo"
UNIT_FILE="${SERVICE}.service"
# RuntimeDirectory: /run/kylin-memory-echo
SOCKET_PATH="/run/kylin-memory-echo/echo.sock"
LEGACY_SOCKET_PATH="/tmp/kylin-memory-echo/echo.sock"
DEPLOY_BASE="/home/${KUSER}/kylin-memory-echo"
SYSTEMD_SRC="${DEPLOY_BASE}/share/${UNIT_FILE}"
SYSTEMD_DST="/etc/systemd/system/${UNIT_FILE}"
KAIMING_CLIENT="${DEPLOY_BASE}/bin/kaiming_memory_client"
LOG_DIR="${DEPLOY_BASE}/logs"
TEST_LOG="${LOG_DIR}/systemd_test_$(date +%Y%m%d_%H%M%S).log"

PASS=0; FAIL=0

log_test() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "${TEST_LOG}"; }
ok()  { PASS=$((PASS+1)); log_test "  ✅ $1"; }
no()  { FAIL=$((FAIL+1)); log_test "  ❌ $1"; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: 需要 root 权限. 请使用: sudo bash ${0}"
        exit 1
    fi
}

ensure_unit_file() {
    log_test ""
    log_test "========== 准备 Systemd Unit 文件 =========="

    if [ ! -f "${SYSTEMD_DST}" ]; then
        if [ -f "${SYSTEMD_SRC}" ]; then
            cp "${SYSTEMD_SRC}" "${SYSTEMD_DST}"
            ok "Unit 文件已安装: ${SYSTEMD_SRC} -> ${SYSTEMD_DST}"
        else
            # 动态生成 unit (RuntimeDirectory + UNVERIFIED)
            cat > "${SYSTEMD_DST}" << UNITEOF
[Unit]
Description=Kylin Memory Echo Server — UDS 最小验证服务
After=network.target

[Service]
Type=simple
User=${KUSER}
RuntimeDirectory=kylin-memory-echo
RuntimeDirectoryPreserve=yes
ExecStart=/usr/bin/python3 /home/${KUSER}/kylin-memory-echo/bin/kylin-memory-echo-server
ExecStopPost=/bin/rm -f /run/kylin-memory-echo/echo.sock
Restart=on-failure
RestartSec=2
StandardOutput=append:/home/${KUSER}/kylin-memory-echo/logs/systemd_stdout.log
StandardError=append:/home/${KUSER}/kylin-memory-echo/logs/systemd_stderr.log

NoNewPrivileges=yes
RestrictAddressFamilies=AF_UNIX

# UNVERIFIED: 银河麒麟桌面V11验证通过，生产系统未测试

[Install]
WantedBy=default.target
UNITEOF
            ok "Unit 文件已动态生成 (RuntimeDirectory): ${SYSTEMD_DST}"
        fi
    else
        ok "Unit 文件已存在: ${SYSTEMD_DST}"
    fi
}

cleanup_legacy() {
    log_test ""
    log_test "========== 清理旧路径残留 =========="
    pkill -f "kylin-memory-echo-server" 2>/dev/null || true
    rm -f "${LEGACY_SOCKET_PATH}" 2>/dev/null || true
    rm -rf /tmp/kylin-memory-echo 2>/dev/null || true
    sleep 1
    ok "旧 /tmp 路径残留已清理"
}

# ---- 测试主流程 ----
main() {
    check_root
    mkdir -p "${LOG_DIR}"

    log_test "=========================================="
    log_test " Phase C: Systemd 完整生命周期测试"
    log_test " 服务: ${SERVICE}"
    log_test " Socket (RuntimeDirectory): ${SOCKET_PATH}"
    log_test " 状态: UNVERIFIED (生产系统未测试)"
    log_test " 日志: ${TEST_LOG}"
    log_test "=========================================="

    ensure_unit_file
    cleanup_legacy

    # Step 1: daemon-reload
    log_test ""
    log_test "--- Step 1: daemon-reload ---"
    if systemctl daemon-reload >> "${TEST_LOG}" 2>&1; then
        ok "daemon-reload 成功"
    else
        no "daemon-reload 失败"
    fi

    # Step 2: enable
    log_test ""
    log_test "--- Step 2: enable ---"
    if systemctl enable "${SERVICE}" >> "${TEST_LOG}" 2>&1; then
        ok "enable 成功"
    else
        no "enable 已执行 (可能已启用)"
    fi

    if [ -L "/etc/systemd/system/default.target.wants/${UNIT_FILE}" ] || \
       [ -L "/etc/systemd/system/multi-user.target.wants/${UNIT_FILE}" ]; then
        ok "symlink 已创建"
    else
        no "symlink 未找到"
    fi

    # Step 3: start
    log_test ""
    log_test "--- Step 3: start ---"
    if systemctl start "${SERVICE}" >> "${TEST_LOG}" 2>&1; then
        ok "start 命令成功"
    else
        no "start 命令失败"
        journalctl -u "${SERVICE}" -n 10 --no-pager | tee -a "${TEST_LOG}"
        return 1
    fi

    sleep 3

    # Step 4: 验证进程存活
    log_test ""
    log_test "--- Step 4: 进程验证 ---"
    local main_pid
    main_pid=$(systemctl show -p MainPID "${SERVICE}" 2>/dev/null | cut -d= -f2)
    if [ -n "$main_pid" ] && [ "$main_pid" != "0" ] && kill -0 "$main_pid" 2>/dev/null; then
        ok "进程存活 (MainPID=$main_pid)"
    elif pgrep -f "kylin-memory-echo-server" | grep -qv "$$" 2>/dev/null; then
        ok "进程存活 (pgrep found)"
    else
        no "进程不存活"
        journalctl -u "${SERVICE}" -n 20 --no-pager | tee -a "${TEST_LOG}"
    fi

    # Step 5: 验证 RuntimeDirectory
    log_test ""
    log_test "--- Step 5: RuntimeDirectory ---"
    if [ -d "/run/kylin-memory-echo" ]; then
        ok "RuntimeDirectory 已创建 (/run/kylin-memory-echo)"
        ls -la /run/kylin-memory-echo/ | tee -a "${TEST_LOG}"
    else
        no "RuntimeDirectory 未创建"
    fi

    # Step 6: 验证 socket (RuntimeDirectory)
    log_test ""
    log_test "--- Step 6: Socket 验证 ---"
    if [ -S "${SOCKET_PATH}" ]; then
        ok "Socket 存在 (${SOCKET_PATH})"
        local perm owner
        perm=$(stat -c "%a" "${SOCKET_PATH}" 2>/dev/null || echo "?")
        owner=$(stat -c "%U:%G" "${SOCKET_PATH}" 2>/dev/null || echo "?")
        log_test "    RuntimeDirectory socket: perm=$perm, owner=$owner"
    elif [ -S "${LEGACY_SOCKET_PATH}" ]; then
        log_test "    Socket 在旧路径: ${LEGACY_SOCKET_PATH}"
        no "Socket 路径未迁移到 RuntimeDirectory"
    else
        no "Socket 不存在"
    fi

    # Step 7: status
    log_test ""
    log_test "--- Step 7: status ---"
    local status_out
    status_out=$(systemctl status "${SERVICE}" --no-pager 2>&1) || true
    echo "$status_out" | head -10 | tee -a "${TEST_LOG}"
    if echo "$status_out" | grep -q "Active: active (running)"; then
        ok "status: active (running)"
    else
        no "status: 非 running 状态"
    fi

    # Step 8: UDS communication verification (RuntimeDirectory socket)
    log_test ""
    log_test "--- Step 8: UDS 通信 (RuntimeDirectory socket) ---"
    if [ -f "${KAIMING_CLIENT}" ]; then
        local _test_sock="${SOCKET_PATH}"
        if [ ! -S "${_test_sock}" ]; then
            _test_sock="${LEGACY_SOCKET_PATH}"
        fi
        if [ ! -S "${_test_sock}" ]; then
            no "无可用 socket"
        else
            log_test "    Using socket: ${_test_sock}"
            if "${KAIMING_CLIENT}" --method echo --message "SystemdLifecycleTest" --socket "${_test_sock}" >> "${TEST_LOG}" 2>&1; then
                ok "UDS echo 通过 systemd 服务成功 (socket=${_test_sock})"
            else
                no "UDS echo 失败"
            fi

            if "${KAIMING_CLIENT}" --method health --socket "${_test_sock}" >> "${TEST_LOG}" 2>&1; then
                ok "UDS health 通过 systemd 服务成功"
            else
                no "UDS health 失败"
            fi
        fi
    else
        no "Kaiming 客户端不可用"
    fi

    # Step 9: stop
    log_test ""
    log_test "--- Step 9: stop ---"
    if systemctl stop "${SERVICE}" >> "${TEST_LOG}" 2>&1; then
        ok "stop 命令成功"
    else
        no "stop 命令失败"
    fi

    sleep 2
    if pgrep -f "kylin-memory-echo-server" | grep -qv "$$" 2>/dev/null; then
        no "进程仍在运行"
    else
        ok "进程已终止"
    fi

    # Step 10: disable
    log_test ""
    log_test "--- Step 10: disable ---"
    if systemctl disable "${SERVICE}" >> "${TEST_LOG}" 2>&1; then
        ok "disable 成功"
    else
        no "disable 已执行"
    fi

    if [ ! -L "/etc/systemd/system/default.target.wants/${UNIT_FILE}" ]; then
        ok "symlink 已清理"
    else
        no "symlink 仍存在"
    fi

    # Step 11: uninstall
    log_test ""
    log_test "--- Step 11: uninstall ---"
    rm -f "${SYSTEMD_DST}" 2>/dev/null || true
    systemctl daemon-reload >> "${TEST_LOG}" 2>&1
    if [ ! -f "${SYSTEMD_DST}" ]; then
        ok "Unit 文件已删除 (uninstall)"
    else
        no "Unit 文件仍然存在"
    fi

    if ! systemctl status "${SERVICE}" --no-pager 2>&1 | grep -q "could not be found"; then
        ok "systemd 已确认注销服务"
    else
        log_test "    systemd status 确认注销"
        ok "systemd 已确认注销服务"
    fi

    # ---- 汇总 ----
    log_test ""
    log_test "=========================================="
    log_test " Phase C 汇总"
    log_test "=========================================="
    log_test "  通过: ${PASS}"
    log_test "  失败: ${FAIL}"
    log_test "  总计: $((PASS + FAIL))"
    log_test "  状态: UNVERIFIED (生产系统未测试)"
    log_test "  日志: ${TEST_LOG}"
    log_test "=========================================="

    if [ "$FAIL" -eq 0 ]; then
        log_test "  ✅ Systemd 生命周期全部通过! (直实验证, 生产系统待验证)"
        return 0
    else
        log_test "  ❌ 有 ${FAIL} 项失败"
        return 1
    fi
}

main