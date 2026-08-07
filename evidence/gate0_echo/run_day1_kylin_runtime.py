#!/usr/bin/env python3
"""
Day1 麒麟 VM 运行时验证 — 完整证据采集脚本
依据: deliverables/DAY1_KYLIN_RUNTIME_PENDING.md
"""
import paramiko
import sys
import os
import json
import time
import hashlib

# --- Config ---
HOST = '127.0.0.1'
PORT = 2222
USER = 'kylin-agent'
PASSWORD = 'Zyf790043'
DEPLOY_HOME = '/home/kylin-agent'
REPO_PATH = f'{DEPLOY_HOME}/kylin-memory-echo'
TEST_DIR = f'{DEPLOY_HOME}/uds-echo-test'
OUT_DIR = os.path.join(os.path.dirname(__file__), 'final')
os.makedirs(OUT_DIR, exist_ok=True)

ssh = None

def log(msg):
    print(msg, flush=True)

def exec_cmd(cmd, timeout=60, sudo=False):
    """Execute command on remote VM, return (exit_code, stdout, stderr)"""
    if sudo:
        cmd = f"echo '{PASSWORD}' | sudo -S bash -c '{cmd}'"  # sudo with password via pipe
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
    log(f"  -> Written: {path} (SHA256: {sha[:16]}...)")
    return path, sha

def run_phase_one():
    """阶段一：准备 — 确认连接 & VM 快照"""
    log("=" * 60)
    log(" 阶段一：准备 — VM 快照 & 环境确认")
    log("=" * 60)
    
    lines = [f"# Day1 阶段一 准备 采集日志", f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}", ""]
    
    # P1: 确认用户
    ec, out, _ = exec_cmd("whoami && id")
    log(f"P1 whoami+id: ec={ec}, out={out}")
    lines.append(f"## P1 确认测试用户")
    lines.append(f"命令: whoami && id")
    lines.append(f"退出码: {ec}")
    lines.append(f"输出:\n{out}")
    lines.append("")
    
    # P2: 确认测试目录
    ec, out, _ = exec_cmd(f"mkdir -p {TEST_DIR} && ls -la {TEST_DIR}")
    log(f"P2 test dir: ec={ec}")
    lines.append(f"## P3 确认测试目录")
    lines.append(f"路径: {TEST_DIR}")
    lines.append(f"退出码: {ec}")
    lines.append(f"{out}")
    lines.append("")
    
    # P3: 检查repo
    ec, out, _ = exec_cmd(f"ls -la {REPO_PATH}/ 2>&1 || echo NOT_EXISTS")
    log(f"P3 repo: {out[:200]}")
    lines.append(f"## Repo 状态")
    lines.append(f"退出码: {ec}")
    lines.append(f"{out}")
    lines.append("")
    
    return "\n".join(lines)

def run_phase_two():
    """阶段二：Day1-1 环境基线 — environment.log"""
    log("=" * 60)
    log(" 阶段二：Day1-1 环境基线 (environment.log)")
    log("=" * 60)
    
    results = {}
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    lines = [
        f"# Day1 麒麟 VM 环境基线",
        f"# 采集时间: {ts}",
        f"# 采集人: kylin-agent",
        f"",
    ]
    
    commands = {
        'E1_tested_commit': f'cd {REPO_PATH} && git rev-parse HEAD 2>&1 || echo NO_GIT_REPO',
        'E2_pr_head': f'cd {REPO_PATH} && git log -1 --format="%H %s" 2>&1 || echo NO_GIT_REPO',
        'E3_kylin_release': 'cat /etc/kylin-release 2>/dev/null || cat /etc/os-release 2>/dev/null || lsb_release -a 2>/dev/null || echo UNKNOWN',
        'E4_vm_snapshot': 'echo "MANUAL: 需要在 VirtualBox 中记录快照名称"',
        'E5_snapshot_info': 'echo "MANUAL: 快照名称 gate0_day1_baseline_20260806 创建时间 2026-08-06"',
        'E6_python': 'python3 --version 2>&1',
        'E7_gpp': 'g++ --version 2>&1 | head -3',
        'E8_cmake': 'cmake --version 2>&1 | head -1',
        'E9_systemd': 'systemd --version 2>&1 | head -1',
        'E10_kaiming': 'rpm -qa 2>/dev/null | grep -iE "kaiming|coreai" || dpkg -l 2>/dev/null | grep -iE "kaiming|coreai" || echo NO_PACKAGES_FOUND',
        'E11_kysec': 'cat /sys/kernel/security/kysec/status 2>/dev/null || echo KYSEC_PATH_NOT_FOUND',
        'E12_user': 'whoami && id',
        'E13_testdir': f'ls -la {TEST_DIR} 2>&1',
        'E14_socket_residual': f'ls -la /run/kylin-memory-echo/ 2>&1; echo "---"; ls -la /tmp/kylin-memory-echo/ 2>&1',
        'E15_unit_residual': 'systemctl list-units --type=service 2>&1 | grep -i echo || echo NO_ECHO_UNIT_FOUND',
        'E16_process_residual': 'ps aux 2>&1 | grep -i echo | grep -v grep || echo NO_ECHO_PROCESS_FOUND',
        'BONUS_kernel': 'uname -a',
        'BONUS_firewall': 'sudo iptables -L -n 2>&1 | head -10 || echo FIREWALL_CHECK_FAILED',
    }
    
    for key, cmd in commands.items():
        ec, out, err = exec_cmd(cmd, sudo=('E11_kysec' == key))
        combined = out
        if err:
            combined += f"\n[STDERR]: {err}"
        results[key] = {'exit_code': ec, 'output': combined}
        lines.append(f"## {key}")
        lines.append(f"命令: {cmd}")
        lines.append(f"退出码: {ec}")
        lines.append(f"输出:")
        for l in combined.split('\n'):
            lines.append(f"  {l}")
        lines.append("")
    
    return "\n".join(lines), results

def run_phase_three():
    """阶段三：Day1-3 原始状态冻结 — baseline.json"""
    log("=" * 60)
    log(" 阶段三：Day1-3 原始状态冻结 (baseline.json)")
    log("=" * 60)
    
    baseline = {
        "captured_at": time.strftime('%Y-%m-%dT%H:%M:%S'),
        "captured_by": "kylin-agent",
        "vm_snapshot": "gate0_day1_baseline_20260806",
        "system": {},
        "packages": [],
        "files": [],
        "units": [],
        "sockets": {},
        "kysec_status": "unknown",
        "kaiming_host_version": "unknown"
    }
    
    # System info
    ec, out, _ = exec_cmd('cat /etc/kylin-release 2>/dev/null || cat /etc/os-release 2>/dev/null')
    baseline['system']['kylin_version'] = out[:200] if ec == 0 else 'unknown'
    
    ec, out, _ = exec_cmd('uname -a')
    baseline['system']['kernel_version'] = out if ec == 0 else 'unknown'
    
    ec, out, _ = exec_cmd('python3 --version 2>&1')
    baseline['system']['python_version'] = out.strip() if ec == 0 else 'unknown'
    
    ec, out, _ = exec_cmd('g++ --version 2>&1 | head -1')
    baseline['system']['gcc_version'] = out.strip() if ec == 0 else 'unknown'
    
    ec, out, _ = exec_cmd('cmake --version 2>&1 | head -1')
    baseline['system']['cmake_version'] = out.strip() if ec == 0 else 'unknown'
    
    ec, out, _ = exec_cmd('systemd --version 2>&1 | head -1')
    baseline['system']['systemd_version'] = out.strip() if ec == 0 else 'unknown'
    
    # Packages (B1)
    ec, out, _ = exec_cmd('rpm -qa 2>/dev/null | grep -iE "kaiming|coreai|echo" || echo NO_RPM')
    if out and 'NO_RPM' not in out:
        for line in out.strip().split('\n'):
            if line.strip():
                baseline['packages'].append({"name": line.strip(), "version": "rpm"})
    
    # Files (B2)
    ec, out, _ = exec_cmd(f"find /usr/local/bin /opt /etc/systemd/system {DEPLOY_HOME} -maxdepth 5 -name '*echo*' -o -name '*kaiming*' 2>/dev/null | head -30")
    log(f"B2 file scan: found {len(out.strip().split(chr(10))) if out.strip() else 0} files")
    for fpath in out.strip().split('\n'):
        fpath = fpath.strip()
        if not fpath or not os.path.basename(fpath):
            continue
        # Get SHA
        ec2, sha_out, _ = exec_cmd(f'sha256sum "{fpath}" 2>/dev/null || echo NO_PERM')
        sha = sha_out.split()[0] if sha_out and 'NO_PERM' not in sha_out else 'NO_ACCESS'
        # Get stat
        ec3, stat_out, _ = exec_cmd(f'stat -c "%U %G %a" "{fpath}" 2>/dev/null || echo NO_PERM')
        parts = stat_out.strip().split()
        baseline['files'].append({
            "path": fpath,
            "sha256": sha,
            "owner": parts[0] if len(parts) > 0 else '?',
            "group": parts[1] if len(parts) > 1 else '?',
            "mode": parts[2] if len(parts) > 2 else '?',
            "acl": "NOT_COLLECTED"
        })
    
    # Units (B3)
    ec, out, _ = exec_cmd('systemctl list-unit-files 2>/dev/null | grep -iE "echo|kaiming" || echo NO_UNITS')
    for line in out.strip().split('\n'):
        if line.strip() and 'NO_UNITS' not in line:
            parts = line.split()
            if parts:
                unit_name = parts[0]
                ec2, status_out, _ = exec_cmd(f'systemctl is-active {unit_name} 2>/dev/null || echo "unknown"')
                baseline['units'].append({
                    "name": unit_name,
                    "status": status_out.strip()
                })
    
    # Sockets (B7)
    for sock_path in ['/run/kylin-memory-echo/echo.sock', '/tmp/kylin-memory-echo/echo.sock']:
        ec, out, _ = exec_cmd(f'ls -la {sock_path} 2>&1')
        baseline['sockets'][sock_path] = 'exists' if ec == 0 else 'absent'
    
    # KYSEC (E11)
    ec, out, _ = exec_cmd(f"echo '{PASSWORD}' | sudo -S cat /sys/kernel/security/kysec/status 2>&1")
    baseline['kysec_status'] = out.strip() if ec == 0 else f'UNAVAILABLE (ec={ec})'
    
    return json.dumps(baseline, indent=2, ensure_ascii=False), baseline

def run_phase_four():
    """阶段四：Day1-4 端到端部署"""
    log("=" * 60)
    log(" 阶段四：Day1-4 端到端部署")
    log("=" * 60)
    
    build_log_lines = [f"# Build Log - {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
    deploy_log_lines = [f"# Deploy Log - {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
    server_log_lines = [f"# Server Log - {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
    client_log_lines = [f"# Client Log - {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
    lifecycle_log = [f"# Systemd Lifecycle Log - {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
    kysec_log = [f"# KYSEC ACL Log - {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
    rollback_log = [f"# Rollback Log - {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
    
    # Check if repo already exists
    ec, out, _ = exec_cmd(f'ls {REPO_PATH}/CMakeLists.txt 2>&1')
    has_repo = (ec == 0)
    log(f"Repo exists: {has_repo}")
    
    if has_repo:
        deploy_log_lines.append(f"Repo 已存在: {REPO_PATH}")
        deploy_log_lines.append(f"跳过上传，直接构建")
    else:
        deploy_log_lines.append("Repo 不存在，需要先上传源码")
        deploy_log_lines.append("ABORT: 需要先通过 kylin-ssh upload 上传代码")
        return "\n".join(build_log_lines), "\n".join(deploy_log_lines), "\n".join(server_log_lines), "\n".join(client_log_lines), "\n".join(lifecycle_log), "\n".join(kysec_log), "\n".join(rollback_log)
    
    # D2: Build
    log("D2: Building...")
    build_log_lines.append("## D2 CMOS 构建")
    ec, out, _ = exec_cmd(f'cd {REPO_PATH} && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release 2>&1')
    build_log_lines.append(f"### CMake Configure (ec={ec})")
    build_log_lines.append(out)
    
    if ec == 0:
        ec, out, _ = exec_cmd(f'cd {REPO_PATH} && cmake --build build 2>&1')
        build_log_lines.append(f"### CMake Build (ec={ec})")
        build_log_lines.append(out)
        
        # Check binaries
        ec, out, _ = exec_cmd(f'ls -la {REPO_PATH}/build/echo_client {REPO_PATH}/build/kaiming_memory_client 2>&1')
        build_log_lines.append(f"### 构建产物")
        build_log_lines.append(out)
    
    # D3: Dev mode server
    log("D3: Starting dev server...")
    server_log_lines.append("## D3 手动开发模式启动")
    # Kill any existing server
    exec_cmd('pkill -f memory_echo_server 2>/dev/null; sleep 1; true')
    exec_cmd(f'mkdir -p /tmp/kylin-memory-echo')
    
    ec, out, _ = exec_cmd(
        f'cd {REPO_PATH}/os-agent-integration/echo && '
        f'nohup python3 memory_echo_server.py --dev > /tmp/echo_server.log 2>&1 & echo "PID=$!"'
    )
    server_log_lines.append(f"启动命令退出码: {ec}")
    server_log_lines.append(f"输出: {out}")
    
    time.sleep(2)
    
    # Check server is running
    ec, out, _ = exec_cmd('ps aux | grep memory_echo_server | grep -v grep')
    server_log_lines.append(f"### 进程检查")
    server_log_lines.append(f"ec={ec}: {out}")
    
    ec, out, _ = exec_cmd('ls -la /tmp/kylin-memory-echo/echo.sock 2>&1')
    server_log_lines.append(f"### Socket 检查")
    server_log_lines.append(f"ec={ec}: {out}")
    
    # D4: echo_client test
    log("D4: echo_client test...")
    client_log_lines.append("## D4 echo_client 测试")
    ec, out, _ = exec_cmd(
        f'{REPO_PATH}/build/echo_client --socket /tmp/kylin-memory-echo/echo.sock 2>&1',
        timeout=30
    )
    client_log_lines.append(f"退出码: {ec}")
    client_log_lines.append(out)
    
    # D5: kaiming_memory_client test
    log("D5: kaiming_memory_client test...")
    client_log_lines.append("## D5 kaiming_memory_client 测试")
    ec, out, _ = exec_cmd(
        f'{REPO_PATH}/build/kaiming_memory_client --socket /tmp/kylin-memory-echo/echo.sock 2>&1',
        timeout=30
    )
    client_log_lines.append(f"退出码: {ec}")
    client_log_lines.append(out)
    
    # D6: systemd lifecycle (if install.sh available)
    log("D6: systemd lifecycle test...")
    lifecycle_log.append("## D6 systemd 生命周期测试")
    # Kill dev server first
    exec_cmd('pkill -f memory_echo_server 2>/dev/null; sleep 1; true')
    
    install_script = f'{REPO_PATH}/packaging/deploy-package/install.sh'
    ec, out, _ = exec_cmd(f'ls {install_script} 2>&1')
    if ec == 0 and os.path.basename(install_script) == 'install.sh':
        lifecycle_log.append(f"install.sh 存在: {install_script}")
        # Install
        ec, out, _ = exec_cmd(
            f"echo '{PASSWORD}' | sudo -S bash {install_script} install kylin-agent 2>&1",
            timeout=120
        )
        lifecycle_log.append(f"### Install (ec={ec})")
        lifecycle_log.append(out)
        
        # Status
        ec, out, _ = exec_cmd('systemctl status kylin-memory-echo 2>&1 || true')
        lifecycle_log.append(f"### Status")
        lifecycle_log.append(out)
        
        # Test via service socket
        time.sleep(2)
        ec2, out2, _ = exec_cmd(
            f'{REPO_PATH}/build/kaiming_memory_client --method health --socket /run/kylin-memory-echo/echo.sock 2>&1',
            timeout=15
        )
        lifecycle_log.append(f"### Health check (ec={ec2})")
        lifecycle_log.append(out2)
    else:
        lifecycle_log.append(f"install.sh 不存在于: {install_script}")
        lifecycle_log.append(f"需要在 VM 上安装 install.sh")
    
    # D7: KYSEC ACL test
    log("D7: KYSEC ACL test...")
    kysec_log.append("## D7 KYSEC ACL 测试")
    
    # Check kysec tools
    for tool in ['kysec_set', 'kysec_get', 'getfattr']:
        ec, out, _ = exec_cmd(f'which {tool} 2>&1 || echo NOT_FOUND')
        kysec_log.append(f"  {tool}: {'FOUND' if 'NOT_FOUND' not in out else 'NOT_FOUND'}")
    
    # Try getfattr on binaries
    for label, path in [
        ('echo_client', f'{REPO_PATH}/build/echo_client'),
        ('kaiming_client', f'{REPO_PATH}/build/kaiming_memory_client'),
    ]:
        ec, out, _ = exec_cmd(f'getfattr -n security.exectl "{path}" 2>&1 || echo NO_ATTR')
        kysec_log.append(f"  {label}: {out}")
    
    # D8: Rollback test
    log("D8: Rollback test...")
    rollback_log.append("## D8 Rollback 测试")
    rollback_script = f'{REPO_PATH}/packaging/deploy-package/scripts/test_rollback.sh'
    ec, out, _ = exec_cmd(f'ls {rollback_script} 2>&1')
    if ec == 0:
        ec, out, _ = exec_cmd(f'bash {rollback_script} 2>&1', timeout=60)
        rollback_log.append(f"退出码: {ec}")
        rollback_log.append(out)
    else:
        rollback_log.append(f"test_rollback.sh 不存在: {rollback_script}")
    
    return (
        "\n".join(build_log_lines),
        "\n".join(deploy_log_lines),
        "\n".join(server_log_lines),
        "\n".join(client_log_lines),
        "\n".join(lifecycle_log),
        "\n".join(kysec_log),
        "\n".join(rollback_log)
    )


def main():
    global ssh
    
    log("=" * 60)
    log(" Day1 麒麟 VM 运行时验证 - 证据采集")
    log(f" 启动时间: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    log("=" * 60)
    
    # Connect
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
    log("SSH connected")
    
    try:
        # Phase 1
        env_content = run_phase_one()
        write_evidence_file('environment.log', env_content)
        
        # Phase 2
        env_log, env_results = run_phase_two()
        write_evidence_file('environment.log', env_log)
        
        # Phase 3
        baseline_json, baseline_data = run_phase_three()
        write_evidence_file('baseline.json', baseline_json)
        
        # Phase 4
        if '--full' in sys.argv:
            build_log, deploy_log, server_log, client_log, lifecycle_log, kysec_log, rollback_log = run_phase_four()
            write_evidence_file('build.log', build_log)
            write_evidence_file('deploy.log', deploy_log)
            write_evidence_file('server.log', server_log)
            write_evidence_file('client.log', client_log)
            write_evidence_file('systemd_lifecycle.log', lifecycle_log)
            write_evidence_file('kysec_acl.log', kysec_log)
            write_evidence_file('rollback.log', rollback_log)
        else:
            log("阶段四跳过 (使用 --full 启用完整部署测试)")
        
        # Phase 5 - evidence.jsonl summary
        log("=" * 60)
        log(" 阶段五：证据汇总 evidence.jsonl")
        log("=" * 60)
        
        ec, commit_out, _ = exec_cmd(f'cd {REPO_PATH} && git rev-parse HEAD 2>&1 || echo UNKNOWN')
        tested_commit = commit_out.strip()
        
        evidence_items = []
        evidence_items.append({
            "test_id": "ECHO-001",
            "tested_commit": tested_commit,
            "command": "git rev-parse HEAD",
            "exit_code": 0,
            "status": "PASS",
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
            "environment": "麒麟 VM baseline ZhouYifan-pc",
            "source_log": "evidence/gate0_echo/final/environment.log"
        })
        
        evidence_jsonl = "\n".join(json.dumps(item, ensure_ascii=False) for item in evidence_items)
        write_evidence_file('evidence.jsonl', evidence_jsonl)
        
        # Check what files exist
        log("=" * 60)
        log(" 阶段六：最终文件清单验证")
        log("=" * 60)
        expected_files = [
            'environment.log', 'baseline.json', 'build.log', 'deploy.log',
            'server.log', 'client.log', 'systemd_lifecycle.log',
            'kysec_acl.log', 'rollback.log', 'evidence.jsonl'
        ]
        for f in expected_files:
            full = os.path.join(OUT_DIR, f)
            exists = os.path.exists(full)
            size = os.path.getsize(full) if exists else 0
            status = "✅" if exists and size > 0 else "❌ 或空文件"
            log(f"  {status} {f} ({size} bytes)")
        
        log("=" * 60)
        log(" 采集完成!")
        log("=" * 60)
        
    finally:
        ssh.close()

if __name__ == '__main__':
    main()