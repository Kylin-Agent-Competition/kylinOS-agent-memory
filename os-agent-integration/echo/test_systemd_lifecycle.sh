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
# 回退路径: CMake 构建产物可能在 build/ 子目录下 (Issue R3-A)
KAIMING_CLIENT_FALLBACK="${DEPLOY_BASE}/os-agent-integration/echo/build/kaiming_memory_client"
KAIMING_CLIENT_FALLBACK2="${DEPLOY_BASE}/build/kaiming_memory_client"
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
    log_test "[PACKAGED_UNIT_VALIDATION] 开始检查仓库正式 Unit..."

    # R3-b fix: 测试必须使用仓库正式 Unit packaging/systemd/kylin-memory-echo.service
    # 动态生成 Unit 仅保留为人工诊断工具，不计入正式 PASS
    local _unit_validated=false

    if [ -f "${SYSTEMD_DST}" ]; then
        # 已安装的 Unit — 检查是否来自仓库正式模板
        local _installed_user
        _installed_user=$(grep '^User=' "${SYSTEMD_DST}" | cut -d= -f2 | tr -d ' ')
        if [ "${_installed_user}" = "__USERNAME__" ]; then
            log_test "  ❌ PACKAGED_UNIT_VALIDATION=FAIL: 已安装 Unit 仍含 __USERNAME__ 占位符 (未替换)"
            no "PACKAGED_UNIT_VALIDATION=FAIL (占位符未替换)"
        else
            ok "Unit 文件已安装且用户名已替换: ${SYSTEMD_DST} (User=${_installed_user})"
            _unit_validated=true
        fi
    elif [ -f "${SYSTEMD_SRC}" ]; then
        # 仓库正式 Unit 存在 — 替换占位符并安装
        log_test "  使用仓库正式 Unit: ${SYSTEMD_SRC}"
        # 检查 __USERNAME__ 占位符
        if grep -q '__USERNAME__' "${SYSTEMD_SRC}"; then
            sed "s/__USERNAME__/${KUSER}/g" "${SYSTEMD_SRC}" > "${SYSTEMD_DST}"
            chmod 644 "${SYSTEMD_DST}"
            ok "PACKAGED_UNIT_VALIDATION=PASS: 仓库正式 Unit 已安装 (${SYSTEMD_SRC} -> ${SYSTEMD_DST}, User=${KUSER})"
            _unit_validated=true
        else
            cp "${SYSTEMD_SRC}" "${SYSTEMD_DST}"
            ok "PACKAGED_UNIT_VALIDATION=PASS: 仓库正式 Unit 已安装 (无占位符)"
            _unit_validated=true
        fi
    else
        # 仓库正式 Unit 缺失 — FAIL
        log_test "  ❌ PACKAGED_UNIT_VALIDATION=FAIL: 仓库正式 Unit 不存在 (${SYSTEMD_SRC})"
        log_test "  ⚠️  请确保 packaging/systemd/kylin-memory-echo.service 已部署到服务器"
        no "PACKAGED_UNIT_VALIDATION=FAIL (仓库正式 Unit 缺失)"

        # 动态生成 Unit 仅作为人工诊断工具 (不计入正式 PASS)
        log_test "  [诊断] 动态生成临时 Unit 供人工调试 (此步骤不计入 PASS)..."
        cat > "${SYSTEMD_DST}" << UNITEOF
[Unit]
Description=Kylin Memory Echo Server — 动态生成 (诊断用, 非正式 Unit)
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

# UNVERIFIED: 动态生成 Unit，非仓库正式版本

[Install]
WantedBy=default.target
UNITEOF
        log_test "  [诊断] 动态 Unit 已生成: ${SYSTEMD_DST} (不计入 PACKAGED_UNIT_VALIDATION)"
    fi

    # systemd-analyze verify (如果 systemd 版本支持)
    if ${_unit_validated} && command -v systemd-analyze &>/dev/null; then
        if systemd-analyze verify "${SYSTEMD_DST}" >> "${TEST_LOG}" 2>&1; then
            ok "PACKAGED_UNIT_VALIDATION: systemd-analyze verify PASS"
        else
            log_test "  ⚠️  systemd-analyze verify 警告 (非致命, 见日志)"
        fi
    fi
}

cleanup_legacy() {
    log_test ""
    log_test "========== 清理旧路径残留 =========="
    # 使用 systemctl stop 停止服务，禁止使用 pkill -f 误杀其他用户/并行测试进程
    systemctl stop "${SERVICE}" 2>/dev/null || true
    # 通过 MainPID 确认服务已停止
    local main_pid
    main_pid=$(systemctl show -p MainPID "${SERVICE}" 2>/dev/null | cut -d= -f2)
    if [ -n "$main_pid" ] && [ "$main_pid" != "0" ]; then
        # 如果 MainPID 仍非零,等待其退出
        sleep 2
        if kill -0 "$main_pid" 2>/dev/null; then
            no "服务进程未停止 (MainPID=$main_pid)"
        fi
    fi
    rm -f "${LEGACY_SOCKET_PATH}" 2>/dev/null || true
    rm -rf /tmp/kylin-memory-echo 2>/dev/null || true
    sleep 1
    ok "旧路径残留已通过 systemctl stop 清理 (非 pkill)"
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
    # R3-a fix: 拆分为独立结果 SYSTEMD_SERVER_LIFECYCLE / CPP_CLIENT_OVER_SYSTEMD / PYTHON_DIAGNOSTIC_FALLBACK
    log_test ""
    log_test "--- Step 8: UDS 通信 (RuntimeDirectory socket) ---"

    # -- 服务端启停验证 (SYSTEMD_SERVER_LIFECYCLE) --
    log_test "  [SYSTEMD_SERVER_LIFECYCLE] 服务端启停验证..."
    local _svc_active
    _svc_active=$(systemctl is-active "${SERVICE}" 2>/dev/null || echo "unknown")
    if [ "${_svc_active}" = "active" ]; then
        ok "SYSTEMD_SERVER_LIFECYCLE=PASS (systemd 报告 active)"
    else
        no "SYSTEMD_SERVER_LIFECYCLE=FAIL (systemd 报告 ${_svc_active})"
    fi

    # -- 自动发现 kaiming_memory_client 实际路径 --
    local _actual_client=""
    for _cand in "${KAIMING_CLIENT}" "${KAIMING_CLIENT_FALLBACK}" "${KAIMING_CLIENT_FALLBACK2}"; do
        if [ -f "${_cand}" ] && [ -x "${_cand}" ]; then
            _actual_client="${_cand}"
            break
        fi
    done
    if [ -z "${_actual_client}" ]; then
        _actual_client=$(find "${DEPLOY_BASE}" -name kaiming_memory_client -type f -executable 2>/dev/null | head -1 || true)
    fi

    if [ -n "${_actual_client}" ] && [ -f "${_actual_client}" ]; then
        log_test "    Using client: ${_actual_client}"
        local _test_sock="${SOCKET_PATH}"
        if [ ! -S "${_test_sock}" ]; then
            _test_sock="${LEGACY_SOCKET_PATH}"
        fi
        if [ ! -S "${_test_sock}" ]; then
            no "CPP_CLIENT_OVER_SYSTEMD=FAIL (无可用 socket)"
        else
            log_test "    Using socket: ${_test_sock}"

            # KYSEC 授权 (如果可用)
            local _kysec_script=""
            for _ks in "${DEPLOY_BASE}/kysec_authorize.sh" \
                       "${DEPLOY_BASE}/packaging/deploy-package/scripts/kysec_authorize.sh" \
                       "/home/${KUSER}/kysec_authorize.sh"; do
                if [ -f "${_ks}" ]; then _kysec_script="${_ks}"; break; fi
            done
            if [ -n "${_kysec_script}" ]; then
                log_test "    Running kysec authorize for socket=${_test_sock}..."
                bash "${_kysec_script}" authorize --socket "${_test_sock}" >> "${TEST_LOG}" 2>&1 || true
            fi

            # 以服务用户身份运行客户端
            local _uid_cmd=""
            if [ "$(id -u)" = "0" ] && [ -n "${KUSER}" ] && [ "${KUSER}" != "root" ]; then
                _uid_cmd="sudo -u ${KUSER}"
                log_test "    Running as ${KUSER} (socket owner)"
            fi

            local _cpp_echo_fail=0 _cpp_health_fail=0
            local _py_diag_needed=0

            # -- C++ 客户端 echo 验证 (CPP_CLIENT_OVER_SYSTEMD) --
            if ${_uid_cmd} "${_actual_client}" --method echo --socket "${_test_sock}" >> "${TEST_LOG}" 2>&1; then
                ok "CPP_CLIENT_OVER_SYSTEMD: echo PASS"
            else
                no "CPP_CLIENT_OVER_SYSTEMD: echo FAIL"
                _cpp_echo_fail=1
                _py_diag_needed=1
            fi

            # -- C++ 客户端 health 验证 (CPP_CLIENT_OVER_SYSTEMD) --
            if ${_uid_cmd} "${_actual_client}" --method health --socket "${_test_sock}" >> "${TEST_LOG}" 2>&1; then
                ok "CPP_CLIENT_OVER_SYSTEMD: health PASS"
            else
                no "CPP_CLIENT_OVER_SYSTEMD: health FAIL"
                _cpp_health_fail=1
                _py_diag_needed=1
            fi

            # -- Python diagnostic fallback (PYTHON_DIAGNOSTIC_FALLBACK) --
            # 仅诊断信息，不计入 C++ PASS/FAIL
            # Python fallback 成功不得修改 C++ 测试结果
            if [ "${_py_diag_needed}" -eq 1 ]; then
                log_test "  [PYTHON_DIAGNOSTIC_FALLBACK] C++ Client 失败, 执行 Python 诊断 (不计入 C++ 结果)..."
                local _py_diag_echo_ok=0 _py_diag_health_ok=0

                if python3 -c "
import socket, struct, json, sys
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(10)
try:
    sock.connect('${_test_sock}')
    req = json.dumps({'protocol_version':'1.0','request_id':'sysd_r1','trace_id':'sysd_t1','method':'echo','deadline_ms':5000,'payload':{'message':'SystemdLifecycleTest'}}).encode()
    sock.sendall(struct.pack('>I', len(req)) + req)
    hdr = sock.recv(4)
    rlen = struct.unpack('>I', hdr)[0]
    body = b''
    while len(body) < rlen:
        body += sock.recv(rlen - len(body))
    resp = json.loads(body.decode())
    sys.exit(0 if resp.get('status') == 'ok' else 1)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(2)
finally:
    sock.close()
" >> "${TEST_LOG}" 2>&1; then
                    _py_diag_echo_ok=1
                fi

                if python3 -c "
import socket, struct, json, sys
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(10)
try:
    sock.connect('${_test_sock}')
    req = json.dumps({'protocol_version':'1.0','request_id':'sysd_h1','trace_id':'sysd_th','method':'health','deadline_ms':5000,'payload':{}}).encode()
    sock.sendall(struct.pack('>I', len(req)) + req)
    hdr = sock.recv(4)
    rlen = struct.unpack('>I', hdr)[0]
    body = b''
    while len(body) < rlen:
        body += sock.recv(rlen - len(body))
    resp = json.loads(body.decode())
    sys.exit(0 if resp.get('status') == 'ok' else 1)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(2)
finally:
    sock.close()
" >> "${TEST_LOG}" 2>&1; then
                    _py_diag_health_ok=1
                fi

                if [ "${_py_diag_echo_ok}" -eq 1 ] && [ "${_py_diag_health_ok}" -eq 1 ]; then
                    log_test "  [PYTHON_DIAGNOSTIC_FALLBACK] Python 诊断: echo PASS, health PASS (仅供诊断, C++ 结果不受影响)"
                else
                    log_test "  [PYTHON_DIAGNOSTIC_FALLBACK] Python 诊断: echo=$(if [ "${_py_diag_echo_ok}" -eq 1 ]; then echo PASS; else echo FAIL; fi), health=$(if [ "${_py_diag_health_ok}" -eq 1 ]; then echo PASS; else echo FAIL; fi) (仅供诊断)"
                fi
            else
                log_test "  [PYTHON_DIAGNOSTIC_FALLBACK] NOT NEEDED (C++ Client 全部通过)"
            fi

            # kysec 回退
            if [ -n "${_kysec_script}" ] && [ -x "${_kysec_script}" ]; then
                bash "${_kysec_script}" rollback --socket "${_test_sock}" >> "${TEST_LOG}" 2>&1 || true
            fi
        fi
    else
        no "CPP_CLIENT_OVER_SYSTEMD=FAIL (Kaiming 客户端不可用: ${KAIMING_CLIENT}, ${KAIMING_CLIENT_FALLBACK}, ${KAIMING_CLIENT_FALLBACK2})"
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

    # 卸载验证: 只有 systemctl status 输出包含 "could not be found" 才算 PASS
    # 原来的 ! ... grep -q 取反逻辑错误导致两个分支都执行 ok(), 修复为基于真实结果判断
    # R3-B fix: Kylin systemd 255 在 daemon-reload 后 status 可能返回
    # "could not be found" / "not-found" / "not be found" 等多种变体
    local _status_out
    _status_out=$(systemctl status "${SERVICE}" --no-pager 2>&1) || true
    if echo "${_status_out}" | grep -qE "could not be found|not-found|not be found"; then
        ok "systemd 已确认注销服务"
    else
        no "systemd 状态异常: 服务未正确注销 (status output: $(echo "${_status_out}" | head -1))"
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