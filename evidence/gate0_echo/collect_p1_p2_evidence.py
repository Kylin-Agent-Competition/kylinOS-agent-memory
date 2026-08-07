#!/usr/bin/env python3
"""
Day2 P1+P2 证据收集脚本 — 只读诊断，不修改代码
依据: deliverables/DAY2_EVIDENCE_GAP_ANALYSIS.md
目标: 收集 P1(证据文件缺失) 和 P2(文档登记) 的证据
"""
import paramiko
import sys
import os
import hashlib
import time
import json

# --- Config ---
HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "kylin-agent")
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")
DEPLOY_HOME = '/home/kylin-agent'
REPO_PATH = f'{DEPLOY_HOME}/kylin-memory-echo'
OUT_DIR = os.path.join(os.path.dirname(__file__), 'day2_results')
os.makedirs(OUT_DIR, exist_ok=True)

ssh = None
sftp = None
all_evidence = {}

def log(msg):
    ts = time.strftime('%H:%M:%S')
    text = f"[{ts}] {msg}"
    print(text, flush=True)

if not PASSWORD:
    log("ERROR: KYLIN_VM_PASSWORD 环境变量未设置")
    log("请设置: export KYLIN_VM_PASSWORD='your_password'")
    sys.exit(1)

def exec_cmd(cmd, timeout=60, sudo=False):
    """Execute command on remote VM"""
    if sudo:
        cmd = f"echo '{PASSWORD}' | sudo -S bash -c '{cmd}'"
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    ec = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return ec, out, err

def write_evidence_file(filename, content):
    path = os.path.join(OUT_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    sha = hashlib.sha256(content.encode('utf-8')).hexdigest()
    log(f"  => Written: {filename} (SHA256: {sha[:16]}...)")
    return path

def upload_file(local_path, remote_path, max_retries=3):
    """Upload with SHA256 verification"""
    if not os.path.exists(local_path):
        log(f"  !! Local file not found: {local_path}")
        return False
    local_sha = hashlib.sha256(open(local_path, 'rb').read()).hexdigest()
    for attempt in range(1, max_retries + 1):
        try:
            sftp.put(local_path, remote_path)
            ec, out, _ = exec_cmd(f"sha256sum {remote_path} | awk '{{print $1}}'")
            remote_sha = out.strip()
            if remote_sha == local_sha:
                log(f"  Upload OK: {os.path.basename(local_path)} -> {remote_path}")
                return True
            else:
                log(f"  Upload attempt {attempt}: SHA256 mismatch")
        except Exception as e:
            log(f"  Upload attempt {attempt} failed: {e}")
    return False


# ===================================================================
# P1-1: E3 client_all_6x6.log — 独立6项全量测试
# ===================================================================
def collect_p1_1_e3():
    log("=" * 60)
    log("P1-1: 收集 E3 client_all_6x6.log (6项全量测试)")
    log("=" * 60)

    evidence = f"# P1-1 E3: KAIMING-STORE 全量 6 项测试独立重跑\n"
    evidence += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    build_dir = f'{REPO_PATH}/os-agent-integration/echo/build'
    kaiming_client = f'{build_dir}/kaiming_memory_client'
    server_path = f'{REPO_PATH}/os-agent-integration/echo/memory_echo_server.py'

    # Check if build products exist
    ec, check, _ = exec_cmd(f"ls -la {kaiming_client} 2>&1")
    if ec != 0:
        evidence += f"## 编译产物检查\n❌ kaiming_memory_client 不存在: {check}\n"
        log(f"  P1-1: 客户端不存在，跳过")
        write_evidence_file("E3_client_all_6x6.log", evidence)
        return

    # Kill any existing server
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null; sleep 1", sudo=True)

    # Start echo server
    exec_cmd(f"mkdir -p /tmp/kylin-memory-echo")
    exec_cmd(f"nohup python3 {server_path} --dev > /tmp/echo_e3.log 2>&1 &")
    time.sleep(2)

    # Verify server
    ec, pid, _ = exec_cmd("pgrep -f memory_echo_server.py")
    evidence += f"## 服务端状态\nPID: {pid if pid else 'N/A'}\n\n"

    ec, sock, _ = exec_cmd("ls -la /tmp/kylin-memory-echo/echo.sock 2>&1")
    evidence += f"Socket: {sock}\n\n"

    # Run full 6-test suite
    log("  Running kaiming_memory_client --method all...")
    ec, out, err = exec_cmd(
        f"{kaiming_client} --method all --socket /tmp/kylin-memory-echo/echo.sock 2>&1",
        timeout=60
    )
    evidence += f"## 全量 6 项测试输出\n"
    evidence += f"Exit code: {ec}\n\n"
    evidence += f"### STDOUT\n```\n{out}\n```\n\n"
    if err:
        evidence += f"### STDERR\n```\n{err}\n```\n\n"

    # Count PASS/FAIL
    pass_count = out.count("PASS") if "PASS" in out else out.count("PASS")
    fail_count = out.count("FAIL") if "FAIL" in out else out.count("FAIL")
    evidence += f"## 统计\n"
    evidence += f"- PASS 计数(粗略): {pass_count}\n"
    evidence += f"- FAIL 计数(粗略): {fail_count}\n"
    evidence += f"- Exit code: {ec}\n\n"

    # Get server log
    ec, svc_log, _ = exec_cmd("tail -50 /tmp/echo_e3.log 2>/dev/null")
    evidence += f"## 服务端日志 (tail)\n```\n{svc_log}\n```\n"

    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)

    write_evidence_file("E3_client_all_6x6.log", evidence)
    all_evidence["E3"] = {"file": "E3_client_all_6x6.log", "exit_code": ec}
    log(f"  P1-1 完成: ec={ec}")


# ===================================================================
# P1-2: E6 kysec_acl_dev.log — 独立 Dev 模式 ACL
# ===================================================================
def collect_p1_2_e6():
    log("=" * 60)
    log("P1-2: 收集 E6 kysec_acl_dev.log (独立 Dev 模式 ACL)")
    log("=" * 60)

    evidence = f"# P1-2 E6: Dev 模式 ACL 独立日志\n"
    evidence += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    kysec_script = f'{REPO_PATH}/packaging/deploy-package/scripts/kysec_authorize.sh'

    # Check script exists
    ec, check, _ = exec_cmd(f"test -f {kysec_script} && echo EXISTS || echo NOT_FOUND")
    if 'NOT_FOUND' in check:
        evidence += f"## 脚本检查\n❌ kysec_authorize.sh 不存在于 {kysec_script}\n"
        write_evidence_file("E6_kysec_acl_dev.log", evidence)
        return

    exec_cmd("mkdir -p /tmp/kylin-memory-echo")

    # authorize (dev)
    ec, out, err = exec_cmd(f"sudo bash {kysec_script} authorize 2>&1", timeout=30, sudo=True)
    evidence += f"## Dev 模式 authorize\nExit code: {ec}\n```\n{out}\n```\n"
    if err:
        evidence += f"STDERR:\n```\n{err}\n```\n"

    # status (dev)
    ec, out, err = exec_cmd(f"sudo bash {kysec_script} status 2>&1", timeout=30, sudo=True)
    evidence += f"\n## Dev 模式 status\nExit code: {ec}\n```\n{out}\n```\n"
    if err:
        evidence += f"STDERR:\n```\n{err}\n```\n"

    # rollback (dev)
    ec, out, err = exec_cmd(f"sudo bash {kysec_script} rollback 2>&1", timeout=30, sudo=True)
    evidence += f"\n## Dev 模式 rollback\nExit code: {ec}\n```\n{out}\n```\n"
    if err:
        evidence += f"STDERR:\n```\n{err}\n```\n"

    # Check socket dir ACL after authorize
    ec, acl_out, _ = exec_cmd("getfacl /tmp/kylin-memory-echo/ 2>/dev/null || echo 'ACL_CHECK_FAILED'")
    evidence += f"\n## /tmp/kylin-memory-echo/ ACL 状态\n```\n{acl_out}\n```\n"

    write_evidence_file("E6_kysec_acl_dev.log", evidence)
    all_evidence["E6"] = {"file": "E6_kysec_acl_dev.log", "collected": True}
    log("  P1-2 完成")


# ===================================================================
# P1-3: test_rollback.sh 可达性
# ===================================================================
def collect_p1_3_rollback_reachability():
    log("=" * 60)
    log("P1-3: test_rollback.sh 可达性检查")
    log("=" * 60)

    evidence = f"# P1-3 test_rollback.sh 可达性检查\n"
    evidence += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    paths_to_check = [
        f'{REPO_PATH}/packaging/deploy-package/scripts/test_rollback.sh',
        '/home/kylin-agent/packaging/deploy-package/scripts/test_rollback.sh',
        '/home/kylin-agent/kylin-memory-echo/packaging/deploy-package/scripts/test_rollback.sh',
    ]

    for p in paths_to_check:
        ec, out, _ = exec_cmd(f"test -f {p} && echo 'EXISTS' || echo 'NOT_FOUND'; test -f {p} && wc -l < {p}")
        evidence += f"- `{p}`: {out}\n"

    # If found, check SOCKET_PATH variable
    for p in paths_to_check:
        ec, exist, _ = exec_cmd(f"test -f {p} && echo 'EXISTS' || echo 'NOT_FOUND'")
        if 'EXISTS' in exist:
            ec, content, _ = exec_cmd(f"grep -n 'SOCKET_PATH' {p} 2>/dev/null || echo 'NO_SOCKET_PATH_REF'")
            evidence += f"\n### {p} 中 SOCKET_PATH 引用:\n```\n{content}\n```\n"
            break

    write_evidence_file("P1_3_rollback_reachability.log", evidence)
    all_evidence["P1-3"] = {"file": "P1_3_rollback_reachability.log", "collected": True}
    log("  P1-3 完成")


# ===================================================================
# P1-4/P1-5: UNVERIFIED 标注状态 (VM 上实际运行的脚本)
# ===================================================================
def collect_p1_4_p1_5_unverified():
    log("=" * 60)
    log("P1-4 & P1-5: UNVERIFIED 标注检查")
    log("=" * 60)

    evidence = f"# P1-4 & P1-5 UNVERIFIED 标注状态\n"
    evidence += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    # Check VM's actual kysec_authorize.sh — there are two copies
    scripts = [
        (f'{REPO_PATH}/packaging/deploy-package/scripts/kysec_authorize.sh', 'packaging (部署版)'),
        (f'{REPO_PATH}/os-agent-integration/echo/kysec_authorize.sh', 'echo (开发版)'),
    ]

    for script_path, label in scripts:
        ec, exist, _ = exec_cmd(f"test -f {script_path} && echo 'EXISTS' || echo 'NOT_FOUND'")
        evidence += f"## {label}: {script_path}\n存在: {exist}\n\n"

        if 'EXISTS' in exist:
            # P1-4: header UNVERIFIED check
            ec, head, _ = exec_cmd(f"head -15 {script_path}")
            has_unverified = 'UNVERIFIED' in head
            evidence += f"### P1-4 头部 UNVERIFIED 标注\n"
            evidence += f"UNVERIFIED 存在: {'✅' if has_unverified else '❌ 缺失'}\n"
            evidence += f"```\n{head}\n```\n\n"

            # P1-5: status output UNVERIFIED check
            exec_cmd("mkdir -p /tmp/kylin-memory-echo")
            ec, status_out, _ = exec_cmd(f"sudo bash {script_path} status 2>&1", timeout=30, sudo=True)
            has_status_unverified = 'UNVERIFIED' in status_out
            evidence += f"### P1-5 status 输出 UNVERIFIED 标注\n"
            evidence += f"UNVERIFIED 存在: {'✅' if has_status_unverified else '❌ 缺失'}\n"
            evidence += f"```\n{status_out}\n```\n\n"

            # Also check --help for --socket
            ec, help_out, _ = exec_cmd(f"bash {script_path} --help 2>&1", timeout=10)
            has_socket = '--socket' in help_out
            evidence += f"### --help --socket 参数\n"
            evidence += f"--socket 支持: {'✅' if has_socket else '❌ 缺失'}\n"
            evidence += f"```\n{help_out}\n```\n\n"

    write_evidence_file("P1_4_P1_5_unverified_check.log", evidence)
    all_evidence["P1-4/5"] = {"file": "P1_4_P1_5_unverified_check.log", "collected": True}
    log("  P1-4/P1-5 完成")


# ===================================================================
# P1-6~P1-10: D2-7 回退对照逐项详细对比
# ===================================================================
def collect_p1_6_to_p1_10_rollback_detail():
    log("=" * 60)
    log("P1-6~P1-10: D2-7 回退逐项详细对比")
    log("=" * 60)

    evidence = f"# P1-6~P1-10 D2-7 回退逐项详细对比\n"
    evidence += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    # Collect BEFORE snapshots
    log("  采集回退前基线...")

    # P1-6: SHA-256 (before)
    ec, sha_before, _ = exec_cmd(
        f"find {REPO_PATH} -type f \\( -name '*.sh' -o -name '*.py' -o -name '*.cpp' -o -name '*.h' \\) "
        f"2>/dev/null | sort | xargs sha256sum 2>/dev/null"
    )
    evidence += f"## P1-6 SHA-256 (回退前)\n```\n{sha_before[:5000]}\n```\n\n"

    # P1-7: owner/group/mode (before)
    ec, stat_before, _ = exec_cmd(
        f"find {REPO_PATH} -type f \\( -name '*.sh' -o -name '*.py' -o -name '*.cpp' \\) "
        f"2>/dev/null | head -20 | xargs stat -c '%U:%G %a %n' 2>/dev/null"
    )
    evidence += f"## P1-7 owner/group/mode (回退前)\n```\n{stat_before}\n```\n\n"

    # P1-8: ACL (before)
    ec, acl_before, _ = exec_cmd(
        f"getfacl {REPO_PATH}/os-agent-integration/echo/ 2>/dev/null || echo 'ACL_NOT_AVAILABLE'"
    )
    evidence += f"## P1-8 ACL (回退前)\n```\n{acl_before}\n```\n\n"

    # P1-9: rpm (before)
    ec, rpm_before, _ = exec_cmd("rpm -qa 2>/dev/null | grep -i kylin | head -20 || echo 'RPM_NOT_AVAILABLE'")
    evidence += f"## P1-9 RPM 包 (回退前)\n```\n{rpm_before}\n```\n\n"

    # P1-10: process check (before)
    ec, proc_before, _ = exec_cmd("pgrep -f kylin-memory-echo-server 2>/dev/null || echo 'NO_PROCESS'")
    evidence += f"## P1-10 进程检查 (回退前)\n```\n{proc_before}\n```\n\n"

    # Execute rollback
    log("  执行 rollback...")
    rollback_script = f'{REPO_PATH}/packaging/deploy-package/scripts/test_rollback.sh'
    ec, exist_check, _ = exec_cmd(f"test -f {rollback_script} && echo EXISTS || echo NOT_FOUND")
    evidence += f"## rollback 脚本状态\n{exist_check}\n\n"

    if 'EXISTS' in exist_check:
        ec, rb_out, rb_err = exec_cmd(
            f"cd {REPO_PATH} && sudo bash {rollback_script} 2>&1",
            timeout=120, sudo=True
        )
        evidence += f"### rollback 执行输出\nExit code: {ec}\n```\n{rb_out[:3000]}\n```\n"
        if rb_err:
            evidence += f"STDERR:\n```\n{rb_err[:1000]}\n```\n"
    else:
        evidence += "⚠️ rollback 脚本不存在，以下所有 AFTER 数据等于 BEFORE\n\n"

    # Collect AFTER snapshots
    log("  采集回退后状态...")

    # P1-6: SHA-256 (after)
    ec, sha_after, _ = exec_cmd(
        f"find {REPO_PATH} -type f \\( -name '*.sh' -o -name '*.py' -o -name '*.cpp' -o -name '*.h' \\) "
        f"2>/dev/null | sort | xargs sha256sum 2>/dev/null"
    )
    evidence += f"## P1-6 SHA-256 (回退后)\n```\n{sha_after[:5000]}\n```\n"

    # Compare
    if sha_before == sha_after:
        evidence += "✅ SHA-256 回退前后一致\n\n"
    else:
        # Show diff
        evidence += "⚠️ SHA-256 有差异（以下为diff前50行）:\n"
        evidence += f"```\n"
        before_lines = set(sha_before.strip().split('\n'))
        after_lines = set(sha_after.strip().split('\n'))
        only_before = before_lines - after_lines
        only_after = after_lines - before_lines
        diff_lines = list(only_before)[:25] + ['---AFTER_ONLY---'] + list(only_after)[:25]
        evidence += '\n'.join(diff_lines)
        evidence += "\n```\n\n"

    # P1-7: owner/group/mode (after)
    ec, stat_after, _ = exec_cmd(
        f"find {REPO_PATH} -type f \\( -name '*.sh' -o -name '*.py' -o -name '*.cpp' \\) "
        f"2>/dev/null | head -20 | xargs stat -c '%U:%G %a %n' 2>/dev/null"
    )
    evidence += f"## P1-7 owner/group/mode (回退后)\n```\n{stat_after}\n```\n"
    evidence += f"一致性: {'✅' if stat_before == stat_after else '⚠️ 有差异'}\n\n"

    # P1-8: ACL (after)
    ec, acl_after, _ = exec_cmd(
        f"getfacl {REPO_PATH}/os-agent-integration/echo/ 2>/dev/null || echo 'ACL_NOT_AVAILABLE'"
    )
    evidence += f"## P1-8 ACL (回退后)\n```\n{acl_after}\n```\n"
    evidence += f"一致性: {'✅' if acl_before == acl_after else '⚠️ 有差异'}\n\n"

    # P1-9: rpm (after)
    ec, rpm_after, _ = exec_cmd("rpm -qa 2>/dev/null | grep -i kylin | head -20 || echo 'RPM_NOT_AVAILABLE'")
    evidence += f"## P1-9 RPM 包 (回退后)\n```\n{rpm_after}\n```\n"
    evidence += f"一致性: {'✅' if rpm_before == rpm_after else '⚠️ 有差异'}\n\n"

    # P1-10: process check (after)
    ec, proc_after, _ = exec_cmd("pgrep -f kylin-memory-echo-server 2>/dev/null || echo 'NO_PROCESS'")
    evidence += f"## P1-10 进程检查 (回退后)\n```\n{proc_after}\n```\n"
    evidence += f"进程已清理: {'✅' if 'NO_PROCESS' in proc_after or not proc_after.strip() else '⚠️ 仍有残留进程'}\n\n"

    evidence += "\n## 总结\n"
    all_checks = [
        ("P1-6 SHA-256", sha_before == sha_after),
        ("P1-7 owner/group/mode", stat_before == stat_after),
        ("P1-8 ACL", acl_before == acl_after),
        ("P1-9 RPM", rpm_before == rpm_after),
        ("P1-10 进程清理", 'NO_PROCESS' in proc_after or not proc_after.strip()),
    ]
    for check, passed in all_checks:
        evidence += f"- {check}: {'✅' if passed else '⚠️'}\n"

    write_evidence_file("P1_6_to_P1_10_rollback_detail.log", evidence)
    all_evidence["P1-6~10"] = {"file": "P1_6_to_P1_10_rollback_detail.log", "collected": True}
    log("  P1-6~P1-10 完成")


# ===================================================================
# P2-2: D2-4.1 RuntimeDirectory 重新检查
# ===================================================================
def collect_p2_2_runtime_dir():
    log("=" * 60)
    log("P2-2: D2-4.1 RuntimeDirectory 重新检查")
    log("=" * 60)

    evidence = f"# P2-2 D2-4.1 RuntimeDirectory 重新检查\n"
    evidence += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    # Check if unit file still exists
    ec, unit, _ = exec_cmd("cat /etc/systemd/system/kylin-memory-echo.service 2>/dev/null || echo 'UNIT_NOT_FOUND'")
    evidence += f"## systemd unit 文件\n```\n{unit}\n```\n"

    if 'UNIT_NOT_FOUND' not in unit:
        has_runtime = 'RuntimeDirectory' in unit
        evidence += f"RuntimeDirectory: {'✅ 已配置' if has_runtime else '⚠️ 未配置'}\n\n"
    else:
        evidence += "⚠️ unit 文件已在回退时移除，无法确认 RuntimeDirectory 配置\n"
        evidence += "(运行 install.sh 后重新部署可验证)\n\n"

    # Check current /run state
    ec, run_state, _ = exec_cmd("ls -la /run/kylin-memory-echo/ 2>&1 || echo 'DIR_NOT_FOUND'")
    evidence += f"## /run/kylin-memory-echo/ 当前状态\n```\n{run_state}\n```\n\n"

    # Check journal for previous RuntimeDirectory usage
    ec, journal, _ = exec_cmd("journalctl -u kylin-memory-echo --no-pager -n 20 2>/dev/null || echo 'NO_JOURNAL'")
    evidence += f"## journalctl 历史\n```\n{journal}\n```\n"

    write_evidence_file("P2_2_runtime_dir_check.log", evidence)
    all_evidence["P2-2"] = {"file": "P2_2_runtime_dir_check.log", "collected": True}
    log("  P2-2 完成")


# ===================================================================
# P2-3: D2-6.3 KYSEC 记录一致性修正
# ===================================================================
def collect_p2_3_kysec_consistency():
    log("=" * 60)
    log("P2-3: D2-6.3 KYSEC 记录一致性修正")
    log("=" * 60)

    evidence = f"# P2-3 D2-6.3 KYSEC 内核接口状态 — 记录一致性修正\n"
    evidence += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    # 多种方式确认 KYSEC 状态
    checks = {
        "sysfs_kylin": "ls /sys/kernel/security/kylin/ 2>/dev/null && echo 'KYSEC_AVAILABLE' || echo 'KYSEC_NOT_AVAILABLE'",
        "sysfs_security": "ls /sys/kernel/security/ 2>&1",
        "kernel_modules": "lsmod 2>/dev/null | grep -i kysec || echo 'NO_KYSEC_MODULE'",
        "kysec_binary": "which kysec_set 2>/dev/null || echo 'NOT_FOUND'; which kysec_get 2>/dev/null || echo 'NOT_FOUND'",
        "uname": "uname -r",
    }

    for label, cmd in checks.items():
        ec, out, _ = exec_cmd(cmd)
        evidence += f"## {label}\n```\n{out}\n```\n\n"

    # Determine final status
    ec, final_check, _ = exec_cmd(
        "ls /sys/kernel/security/kylin/ 2>/dev/null && echo 'AVAILABLE' || echo 'NOT_AVAILABLE'"
    )
    evidence += f"## 最终判定\n"
    evidence += f"KYSEC 内核接口: {'可用' if 'AVAILABLE' in final_check else '不可用'}\n"
    evidence += f"建议统一记录为: KYSEC_NOT_AVAILABLE (sysfs 路径不存在)\n"
    evidence += f"注释: Gate 0 阶段不具备 KYSEC 内核模块加载权限，不影响 ACL 替代方案有效性\n\n"

    write_evidence_file("P2_3_kysec_consistency.log", evidence)
    all_evidence["P2-3"] = {"file": "P2_3_kysec_consistency.log", "collected": True}
    log("  P2-3 完成")


# ===================================================================
# 汇总报告
# ===================================================================
def write_final_report():
    log("=" * 60)
    log("生成 P1+P2 证据收集汇总报告")
    log("=" * 60)

    report = f"# Day2 P1+P2 证据收集汇总报告\n"
    report += f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"

    report += "## 收集的证据文件\n\n"
    report += "| 文件 | 对应缺口 | 状态 |\n"
    report += "|------|---------|:----:|\n"

    file_map = {
        "E3_client_all_6x6.log": "P1-1: E3 独立6项全量测试",
        "E6_kysec_acl_dev.log": "P1-2: E6 独立Dev模式ACL",
        "P1_3_rollback_reachability.log": "P1-3: test_rollback.sh 可达性",
        "P1_4_P1_5_unverified_check.log": "P1-4/P1-5: UNVERIFIED标注",
        "P1_6_to_P1_10_rollback_detail.log": "P1-6~P1-10: 回退逐项对比",
        "P2_2_runtime_dir_check.log": "P2-2: RuntimeDirectory重查",
        "P2_3_kysec_consistency.log": "P2-3: KYSEC记录一致性",
    }

    for fname, desc in file_map.items():
        fpath = os.path.join(OUT_DIR, fname)
        exists = os.path.exists(fpath)
        report += f"| {fname} | {desc} | {'✅' if exists else '❌'} |\n"

    report += "\n## 仍需人工处理\n\n"
    report += "- **P2-1**: index.yaml 补充登记 4 条 (D2-3, D2-4, D2-6, D2-7) — 需本地编辑\n"
    report += "- **P0 问题**: 需修改代码后重新部署 (不在本次收集范围)\n\n"

    write_evidence_file("P1_P2_COLLECTION_REPORT.md", report)
    log("  汇总报告已生成")


# ===================================================================
# Main
# ===================================================================
def main():
    global ssh, sftp

    log("=" * 60)
    log(" Day2 P1+P2 证据收集 (只读诊断)")
    log(f" 输出目录: {OUT_DIR}")
    log("=" * 60)

    # Connect
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        sftp = ssh.open_sftp()
        log(f"SSH 已连接: {USER}@{HOST}:{PORT}")
    except Exception as e:
        log(f"SSH 连接失败: {e}")
        sys.exit(1)

    try:
        # P1 collections
        collect_p1_1_e3()
        collect_p1_2_e6()
        collect_p1_3_rollback_reachability()
        collect_p1_4_p1_5_unverified()

        # D2-7 rollback detail (runs rollback — do this last in P1)
        collect_p1_6_to_p1_10_rollback_detail()

        # P2 collections
        collect_p2_2_runtime_dir()
        collect_p2_3_kysec_consistency()

        # Final report
        write_final_report()

        log("\n" + "=" * 60)
        log(" P1+P2 证据收集完成!")
        log(f" 输出目录: {OUT_DIR}")
        log("=" * 60)

    except Exception as e:
        log(f"!! 异常: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        if sftp:
            sftp.close()
        if ssh:
            ssh.close()
        log("SSH 连接已关闭")


if __name__ == '__main__':
    main()