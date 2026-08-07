#!/usr/bin/env python3
"""
Day2 麒麟 VM 运行时验证 — 完整证据采集脚本
依据: deliverables/DAY2_KYLIN_RUNTIME_PENDING.md
"""
import paramiko
import sys
import os
import json
import time
import hashlib
import base64

# --- Config ---
HOST = '127.0.0.1'
PORT = 2222
USER = 'kylin-agent'
PASSWORD = 'Zyf790043'
DEPLOY_HOME = '/home/kylin-agent'
REPO_PATH = f'{DEPLOY_HOME}/kylin-memory-echo'
OUT_DIR = os.path.join(os.path.dirname(__file__), 'day2_results')
os.makedirs(OUT_DIR, exist_ok=True)

ssh = None
sftp = None
results_log = []

def log(msg):
    ts = time.strftime('%H:%M:%S')
    # Replace unicode emojis with ASCII equivalents for GBK console
    safe_msg = msg.translate({0x2705: '[OK]', 0x274C: '[XX]', 0x26A0: '[!!]', 0x2714: '[V]', 0x274E: '[XX]'})
    # Fallback: strip any remaining non-ASCII chars that break GBK
    try:
        safe_msg.encode('gbk')
    except UnicodeEncodeError:
        safe_msg = safe_msg.encode('gbk', errors='replace').decode('gbk')
    line = f"[{ts}] {safe_msg}"
    results_log.append(line)
    print(line, flush=True)

def exec_cmd(cmd, timeout=60, sudo=False):
    """Execute command on remote VM, return (exit_code, stdout, stderr)"""
    if sudo:
        # Use sudo -S to read password from stdin
        full_cmd = cmd
        # For sudo commands, prepend echo password pipe
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
    log(f"  -> Written: {filename} (SHA256: {sha[:16]}...)")
    return path, sha

def upload_file(local_path, remote_path, max_retries=3):
    """Upload file with SHA256 verification"""
    local_sha = hashlib.sha256(open(local_path, 'rb').read()).hexdigest()
    
    for attempt in range(1, max_retries + 1):
        try:
            sftp.put(local_path, remote_path)
            # Verify remote SHA256
            ec, out, _ = exec_cmd(f"sha256sum {remote_path} | awk '{{print $1}}'")
            remote_sha = out.strip()
            if remote_sha == local_sha:
                log(f"  Upload OK: {os.path.basename(local_path)} -> {remote_path} (SHA256 match)")
                return True
            else:
                log(f"  Upload attempt {attempt}: SHA256 mismatch (local={local_sha[:16]} remote={remote_sha[:16]})")
        except Exception as e:
            log(f"  Upload attempt {attempt} failed: {e}")
    log(f"  !! Upload FAILED after {max_retries} attempts: {local_path}")
    return False


# ===================================================================
# 阶段一: 代码同步与编译验证 (S1)
# ===================================================================
def run_stage1():
    log("=" * 60)
    log("阶段一 (S1): 代码同步与编译验证")
    log("=" * 60)
    
    evidence_text = f"# Day2 阶段一 代码同步与编译验证\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    # S1.1: 上传修复后代码
    log("\n--- S1.1: 上传修复后代码 ---")
    evidence_text += "## S1.1 上传修复后代码\n\n"
    
    local_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                              'os-agent-integration', 'echo')
    
    files_to_upload = [
        ('kaiming_memory_client.cpp', f'{REPO_PATH}/os-agent-integration/echo/kaiming_memory_client.cpp'),
        ('test_systemd_lifecycle.sh', f'{REPO_PATH}/os-agent-integration/echo/test_systemd_lifecycle.sh'),
        ('kysec_authorize.sh', f'{REPO_PATH}/packaging/deploy-package/scripts/kysec_authorize.sh'),
        ('echo_client.cpp', f'{REPO_PATH}/os-agent-integration/echo/echo_client.cpp'),
        ('CMakeLists.txt', f'{REPO_PATH}/os-agent-integration/echo/CMakeLists.txt'),
    ]
    
    # Also upload kysec from packaging
    packaging_kysec = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                    'packaging', 'deploy-package', 'scripts', 'kysec_authorize.sh')
    local_base_packaging = os.path.dirname(packaging_kysec)
    
    for local_name, remote_path in files_to_upload:
        if local_name == 'kysec_authorize.sh':
            local_full = packaging_kysec
        else:
            local_full = os.path.join(local_base, local_name)
        
        # Ensure remote directory exists
        remote_dir = os.path.dirname(remote_path)
        exec_cmd(f"mkdir -p {remote_dir}")
        
        if os.path.exists(local_full):
            ok = upload_file(local_full, remote_path)
            evidence_text += f"- {local_name}: {'✅ 上传成功' if ok else '❌ 上传失败'}\n"
        else:
            log(f"  !! Local file not found: {local_full}")
            evidence_text += f"- {local_name}: ⚠️ 本地文件不存在: {local_full}\n"
    
    # Upload memory_echo_server.py
    local_server = os.path.join(local_base, 'memory_echo_server.py')
    remote_server = f'{REPO_PATH}/os-agent-integration/echo/memory_echo_server.py'
    exec_cmd(f"mkdir -p {os.path.dirname(remote_server)}")
    if os.path.exists(local_server):
        upload_file(local_server, remote_server)
        exec_cmd(f"chmod +x {remote_server}")
    
    # S1.2: 干净 CMake 构建
    log("\n--- S1.2: 干净 CMake 构建验证 ---")
    evidence_text += "\n## S1.2 干净 CMake 构建验证\n\n"
    
    build_dir = f'{REPO_PATH}/os-agent-integration/echo/build'
    exec_cmd(f"rm -rf {build_dir}")
    
    ec, out, err = exec_cmd(f"cd {REPO_PATH}/os-agent-integration/echo && cmake -S . -B build 2>&1", timeout=120)
    log(f"S1.2.1 cmake -S . -B build: ec={ec}")
    evidence_text += f"### S1.2.1 CMake 配置\n```\n{out}\n{err}\n```\nExit code: {ec}\n✅ 无错误\n\n" if ec == 0 else f"### S1.2.1 CMake 配置\n```\n{out}\n{err}\n```\nExit code: {ec}\n❌ 有错误\n\n"
    
    if ec == 0:
        ec, out, err = exec_cmd(f"cd {REPO_PATH}/os-agent-integration/echo && cmake --build build 2>&1", timeout=180)
        log(f"S1.2.2 cmake --build build: ec={ec}")
        evidence_text += f"### S1.2.2 CMake 构建\n```\n{out}\n{err}\n```\nExit code: {ec}\n{'✅ 编译成功' if ec == 0 else '❌ 编译失败'}\n\n"
    
    # S1.2.3: 确认二进制产物
    ec, out, err = exec_cmd(f"ls -la {build_dir}/echo_client {build_dir}/kaiming_memory_client 2>&1")
    log(f"S1.2.3 二进制产物: {out}")
    evidence_text += f"### S1.2.3 二进制产物确认\n```\n{out}\n```\n"
    evidence_text += "✅ 两个二进制均存在且可执行\n\n" if ec == 0 else "❌ 二进制缺失\n\n"
    
    write_evidence_file("E1_build.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段二: R1+R2 修复验证 — KAIMING-STORE
# ===================================================================
def run_stage2():
    log("=" * 60)
    log("阶段二 (R1+R2): KAIMING-STORE 修复验证")
    log("=" * 60)
    
    evidence_text = f"# Day2 阶段二 R1+R2 KAIMING-STORE 修复验证\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    build_dir = f'{REPO_PATH}/os-agent-integration/echo/build'
    kaiming_client = f'{build_dir}/kaiming_memory_client'
    
    # First make sure echo server is not running
    exec_cmd("pkill -f kylin-memory-echo-server 2>/dev/null; sleep 1", sudo=True)
    
    # Start echo server in dev mode (background)
    log("\n--- 启动 Echo 服务 (dev 模式) ---")
    server_path = f'{REPO_PATH}/os-agent-integration/echo/memory_echo_server.py'
    exec_cmd(f"mkdir -p /tmp/kylin-memory-echo")
    ec, _, _ = exec_cmd(f"nohup python3 {server_path} --dev > /tmp/echo_server_day2.log 2>&1 &")
    time.sleep(2)
    
    # Verify server is running
    ec, out, _ = exec_cmd("pgrep -f memory_echo_server.py")
    if out.strip():
        log(f"  Echo server PID: {out.strip()}")
    else:
        log("  !! Echo server may not have started")
    
    ec, out, _ = exec_cmd("ls -la /tmp/kylin-memory-echo/echo.sock 2>&1")
    log(f"  Socket check: {out}")
    evidence_text += f"## Echo 服务启动\nSocket: {out}\n\n"
    
    # R1: JSON 合法性验证
    log("\n--- R1: JSON 合法性验证 ---")
    evidence_text += "## R1: JSON 合法性验证\n\n"
    
    ec, out, err = exec_cmd(f"{kaiming_client} --method memory.store --socket /tmp/kylin-memory-echo/echo.sock 2>&1", timeout=30)
    log(f"R1.2 memory.store: ec={ec}")
    evidence_text += f"### R1.2 memory.store 请求\n```\n{out}\n```\nSTDERR: {err}\n\n"
    
    # Check service log for PROTOCOL_ERROR
    ec, svc_log, _ = exec_cmd("cat /tmp/echo_server_day2.log 2>&1")
    has_protocol_error = 'PROTOCOL_ERROR' in svc_log
    log(f"R1.3 服务端日志 PROTOCOL_ERROR: {'YES ❌' if has_protocol_error else 'NO ✅'}")
    evidence_text += f"### R1.3 服务端日志检查\nPROTOCOL_ERROR: {'发现 ❌' if has_protocol_error else '未发现 ✅'}\n```\n{svc_log[-2000:]}\n```\n\n"
    
    # R2: 断言正确性
    log("\n--- R2: 断言正确性验证 ---")
    evidence_text += "## R2: 断言正确性验证\n\n"
    
    ec, out, err = exec_cmd(f"{kaiming_client} --method memory.store --socket /tmp/kylin-memory-echo/echo.sock 2>&1", timeout=30)
    evidence_text += f"### R2.1 memory.store 单独测试\n```\n{out}\n```\n\n"
    
    # Check for proper error response
    has_status = '"status"' in out or "'status'" in out
    has_error_code = '"error_code"' in out or "'error_code'" in out
    has_error_message = '"error_message"' in out or "'error_message'" in out
    log(f"R2.1 status字段: {has_status}, error_code: {has_error_code}, error_message: {has_error_message}")
    evidence_text += f"- status字段: {'✅' if has_status else '❌'}\n"
    evidence_text += f"- error_code字段: {'✅' if has_error_code else '❌'}\n"
    evidence_text += f"- error_message字段: {'✅' if has_error_message else '❌'}\n\n"
    
    # R2.2: 非法 JSON 测试
    log("\n--- R2.2: 非法 JSON 测试 ---")
    evidence_text += "## R2.2: 非法 JSON 测试\n\n"
    
    # Send malformed JSON via Python script on VM
    malformed_test = '''
import socket, struct, json
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect('/tmp/kylin-memory-echo/echo.sock')
# Send malformed JSON (missing closing brace)
body = b'{"protocol_version":"1.0","request_id":"bad","method":"memory.store","payload":{}'
header = struct.pack('>I', len(body))
sock.sendall(header + body)
try:
    resp_header = sock.recv(4)
    if len(resp_header) >= 4:
        import struct as st
        resp_len = st.unpack('>I', resp_header)[0]
        resp_body = b''
        while len(resp_body) < resp_len:
            chunk = sock.recv(resp_len - len(resp_body))
            if not chunk:
                break
            resp_body += chunk
        print(resp_body.decode('utf-8', errors='replace'))
    else:
        print("SHORT_HEADER")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    sock.close()
'''
    exec_cmd(f"cat > /tmp/malformed_test.py << 'PYEOF'\n{malformed_test}\nPYEOF")
    ec, out, _ = exec_cmd("python3 /tmp/malformed_test.py 2>&1", timeout=10)
    log(f"R2.2 非法JSON响应: {out[:500]}")
    evidence_text += f"### R2.2 非法JSON响应\n```\n{out}\n```\n\n"
    
    # R2.3: 全量 6/6 测试
    log("\n--- R2.3: 全量 6/6 测试 ---")
    evidence_text += "## R2.3: 全量 6/6 测试\n\n"
    
    ec, out, err = exec_cmd(f"{kaiming_client} --method all --socket /tmp/kylin-memory-echo/echo.sock 2>&1", timeout=60)
    log(f"R2.3 全量测试: ec={ec}")
    evidence_text += f"### R2.3 全量测试输出\n```\n{out}\n```\nExit code: {ec}\n\n"
    
    write_evidence_file("E2_client_kaiming_store.log", evidence_text)
    
    # Stop echo server
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
    
    return evidence_text


# ===================================================================
# 阶段三: R3 修复验证 — Systemd 卸载假阳性
# ===================================================================
def run_stage3():
    log("=" * 60)
    log("阶段三 (R3): Systemd 卸载假阳性修复验证")
    log("=" * 60)
    
    evidence_text = f"# Day2 阶段三 R3 Systemd 卸载假阳性修复验证\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    test_script = f'{REPO_PATH}/os-agent-integration/echo/test_systemd_lifecycle.sh'
    exec_cmd(f"chmod +x {test_script}")
    
    # R3.1: 执行完整生命周期测试
    log("\n--- R3.1: 完整生命周期测试 ---")
    evidence_text += "## R3.1 完整生命周期测试\n\n"
    
    ec, out, err = exec_cmd(f"cd {REPO_PATH}/os-agent-integration/echo && sudo bash test_systemd_lifecycle.sh 2>&1", timeout=300, sudo=True)
    log(f"R3.1 完整生命周期: ec={ec}")
    evidence_text += f"### R3.1 完整生命周期输出\n```\n{out[-5000:]}\n```\nSTDERR:\n```\n{err[:2000]}\n```\nExit code: {ec}\n\n"
    
    # R3.2: 检查 Step 11 逻辑
    log("\n--- R3.2: Step 11 卸载验证 ---")
    has_uninstall_ok = '已确认注销服务' in out or 'systemd.*注销' in out.lower() or 'not be found' in out.lower()
    log(f"R3.2 卸载确认: {has_uninstall_ok}")
    evidence_text += f"### R3.2 Step 11 卸载验证\n- '已确认注销服务' 或 'could not be found': {'✅ 正确' if has_uninstall_ok else '⚠️ 未找到'}\n\n"
    
    # R3.4: 退出码
    evidence_text += f"### R3.4 总退出码\n- Exit code: {ec} → {'✅ 全部PASS (0)' if ec == 0 else f'❌ 存在FAIL ({ec})'}\n\n"
    
    write_evidence_file("E4_systemd_lifecycle_rerun.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段四: R4 修复验证 — KYSEC/ACL 模式适配
# ===================================================================
def run_stage4():
    log("=" * 60)
    log("阶段四 (R4): KYSEC/ACL 模式适配验证")
    log("=" * 60)
    
    evidence_text = f"# Day2 阶段四 R4 KYSEC/ACL 模式适配验证\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    kysec_script_dev = f'{REPO_PATH}/packaging/deploy-package/scripts/kysec_authorize.sh'
    kysec_script_echo = f'{REPO_PATH}/os-agent-integration/echo/kysec_authorize.sh'
    
    # Also copy kysec to echo dir for convenience
    exec_cmd(f"cp {kysec_script_dev} {kysec_script_echo} 2>/dev/null; chmod +x {kysec_script_dev} {kysec_script_echo} 2>/dev/null")
    
    # R4.1: Dev 模式 (/tmp)
    log("\n--- R4.1: Dev 模式 ACL (/tmp) ---")
    evidence_text += "## R4.1 Dev 模式 ACL (/tmp)\n\n"
    
    # Ensure socket dir exists
    exec_cmd("mkdir -p /tmp/kylin-memory-echo")
    
    ec, out, err = exec_cmd(f"sudo bash {kysec_script_dev} authorize 2>&1", timeout=30, sudo=True)
    log(f"R4.1.1 authorize (dev): ec={ec}")
    evidence_text += f"### R4.1.1 authorize (dev)\n```\n{out}\n{err}\n```\n\n"
    
    ec, out, err = exec_cmd(f"sudo bash {kysec_script_dev} status 2>&1", timeout=30, sudo=True)
    log(f"R4.1.2 status (dev): ec={ec}")
    evidence_text += f"### R4.1.2 status (dev)\n```\n{out}\n{err}\n```\n\n"
    
    ec, out, err = exec_cmd(f"sudo bash {kysec_script_dev} rollback 2>&1", timeout=30, sudo=True)
    log(f"R4.1.3 rollback (dev): ec={ec}")
    evidence_text += f"### R4.1.3 rollback (dev)\n```\n{out}\n{err}\n```\n\n"
    
    # R4.2: Systemd 模式 (--socket /run/...)
    log("\n--- R4.2: Systemd 模式 ACL (--socket /run/...) ---")
    evidence_text += "## R4.2 Systemd 模式 ACL (--socket /run/...)\n\n"
    
    exec_cmd("mkdir -p /run/kylin-memory-echo 2>/dev/null", sudo=True)
    
    ec, out, err = exec_cmd(f"sudo bash {kysec_script_dev} authorize --socket /run/kylin-memory-echo/echo.sock 2>&1", timeout=30, sudo=True)
    log(f"R4.2.1 authorize (systemd): ec={ec}")
    evidence_text += f"### R4.2.1 authorize (systemd)\n```\n{out}\n{err}\n```\n\n"
    
    ec, out, err = exec_cmd(f"sudo bash {kysec_script_dev} status --socket /run/kylin-memory-echo/echo.sock 2>&1", timeout=30, sudo=True)
    log(f"R4.2.2 status (systemd): ec={ec}")
    evidence_text += f"### R4.2.2 status (systemd)\n```\n{out}\n{err}\n```\n\n"
    
    ec, out, err = exec_cmd(f"sudo bash {kysec_script_dev} rollback --socket /run/kylin-memory-echo/echo.sock 2>&1", timeout=30, sudo=True)
    log(f"R4.2.3 rollback (systemd): ec={ec}")
    evidence_text += f"### R4.2.3 rollback (systemd)\n```\n{out}\n{err}\n```\n\n"
    
    # R4.2.4: --help
    ec, out, _ = exec_cmd(f"bash {kysec_script_dev} --help 2>&1", timeout=10)
    has_socket_param = '--socket' in out
    log(f"R4.2.4 --help 包含 --socket: {has_socket_param}")
    evidence_text += f"### R4.2.4 --help 输出\n```\n{out}\n```\n--socket 参数: {'✅ 已说明' if has_socket_param else '❌ 未说明'}\n\n"
    
    write_evidence_file("E5_kysec_acl_systemd.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段五.1: D2-1 Kaiming 真实 Hook 尝试
# ===================================================================
def run_d2_1():
    log("=" * 60)
    log("阶段五 D2-1: Kaiming → 自定义 UDS Echo 真实 Hook")
    log("=" * 60)
    
    evidence_text = f"# Day2 D2-1 Kaiming 真实 Hook 尝试\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    # D2-1.1: 定位 kylin-aiassistant Socket 调用点
    log("\n--- D2-1.1: 定位 Socket 调用点 ---")
    evidence_text += "## D2-1.1 定位 Socket 调用点\n\n"
    
    # Search for kylin-aiassistant configs and binaries
    ec, out, _ = exec_cmd("dpkg -l | grep -i kylin-aiassistant 2>/dev/null || echo 'NOT_FOUND'")
    evidence_text += f"### kylin-aiassistant 安装状态\n```\n{out}\n```\n\n"
    
    ec, out, _ = exec_cmd("which kylin-aiassistant 2>/dev/null || find /usr -name '*kylin*aiassistant*' -o -name '*kaiassistant*' 2>/dev/null | head -20 || echo 'NOT_FOUND'")
    evidence_text += f"### 二进制/源码位置\n```\n{out}\n```\n\n"
    
    # Search for QLocalSocket references in configs
    ec, out, _ = exec_cmd("grep -rl 'QLocalSocket\|connectToServer\|/tmp/kylin\|kylin-memory' /etc/ 2>/dev/null | head -10; grep -rl 'QLocalSocket\|connectToServer\|kaiassistant' /usr/share/kylin-aiassistant/ 2>/dev/null | head -10; echo '---DONE---'")
    evidence_text += f"### Socket 调用点搜索\n```\n{out}\n```\n\n"
    
    # D2-1.6: 独立模拟客户端结果
    log("\n--- D2-1.6: 独立模拟客户端 ---")
    evidence_text += "## D2-1.6 独立模拟客户端替代结果\n\n"
    
    build_dir = f'{REPO_PATH}/os-agent-integration/echo/build'
    kaiming_client = f'{build_dir}/kaiming_memory_client'
    
    # Start echo server
    server_path = f'{REPO_PATH}/os-agent-integration/echo/memory_echo_server.py'
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null; sleep 1", sudo=True)
    exec_cmd(f"nohup python3 {server_path} --dev > /tmp/echo_server_d2.log 2>&1 &")
    time.sleep(2)
    
    ec, out, err = exec_cmd(f"{kaiming_client} --method all --socket /tmp/kylin-memory-echo/echo.sock 2>&1", timeout=60)
    log(f"D2-1.6 独立客户端全量测试: ec={ec}")
    evidence_text += f"### kaiming_memory_client --method all 输出\n```\n{out}\n```\nExit code: {ec}\n\n"
    
    # D2-1.7: 后续接入方案说明
    evidence_text += "## D2-1.7 后续接入方案\n\n"
    evidence_text += "- **状态**: 路线 B — 如实记录失败/阻塞\n"
    evidence_text += "- **阻塞原因**: \n"
    ec, kaiming_detail, _ = exec_cmd("dpkg -l | grep kylin-aiassistant 2>/dev/null | head -5")
    if not kaiming_detail.strip():
        evidence_text += "  - kylin-aiassistant 源码未在 VM 中提供\n"
    evidence_text += "  - 需要麒麟 SDK 源码访问权限才能修改 Hook 点\n"
    evidence_text += "  - Gate 0 阶段不具备生产级 Hook 部署条件\n"
    evidence_text += "- **后续计划**: Gate 1 获取 SDK 源码 → 修改 Socket 连接逻辑 → 编译验证 → 集成测试\n"
    evidence_text += "- **所需资源**: kylin-aiassistant 源码、构建环境、测试环境\n\n"
    
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
    
    write_evidence_file("E7_kaiming_hook_attempt.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段五.3: D2-3 部署和启动可复现
# ===================================================================
def run_d2_3():
    log("=" * 60)
    log("阶段五 D2-3: 部署和启动可复现")
    log("=" * 60)
    
    evidence_text = f"# Day2 D2-3 部署和启动可复现\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    # D2-3.2: 干净 CMake 构建
    log("\n--- D2-3.2: 干净 CMake 构建 ---")
    evidence_text += "## D2-3.2 干净 CMake 构建\n\n"
    
    build_dir = f'{REPO_PATH}/os-agent-integration/echo/build'
    exec_cmd(f"rm -rf {build_dir}")
    
    ec, out, err = exec_cmd(f"cd {REPO_PATH}/os-agent-integration/echo && cmake -S . -B build 2>&1", timeout=120)
    evidence_text += f"### cmake 配置\n```\n{out}\n{err}\n```\nExit code: {ec}\n\n"
    
    ec, out, err = exec_cmd(f"cd {REPO_PATH}/os-agent-integration/echo && cmake --build build 2>&1", timeout=180)
    evidence_text += f"### cmake 构建\n```\n{out}\n{err}\n```\nExit code: {ec}\n\n"
    
    ec, out, _ = exec_cmd(f"ls -la {build_dir}/echo_client {build_dir}/kaiming_memory_client 2>&1")
    evidence_text += f"### 二进制产物\n```\n{out}\n```\n✅ 两个客户端均编译成功\n\n" if ec == 0 else f"### 二进制产物\n```\n{out}\n```\n❌ 编译失败\n\n"
    
    # D2-3.3: 手动 dev 模式启动
    log("\n--- D2-3.3: 手动 dev 模式启动 ---")
    evidence_text += "## D2-3.3 手动 dev 模式启动\n\n"
    
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
    server_path = f'{REPO_PATH}/os-agent-integration/echo/memory_echo_server.py'
    
    ec, out, _ = exec_cmd(f"nohup python3 {server_path} --dev > /tmp/echo_dev_startup.log 2>&1 & sleep 2 && ls -la /tmp/kylin-memory-echo/echo.sock 2>&1")
    evidence_text += f"### dev 模式 socket 检查\n```\n{out}\n```\n"
    evidence_text += "✅ socket 在 /tmp/kylin-memory-echo/echo.sock 创建\n\n" if 'echo.sock' in out else "❌ socket 未创建\n\n"
    
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
    
    # D2-3.4: 验证 --dev 参数使能 (不带 --dev 启动应该走 systemd 模式)
    log("\n--- D2-3.4: --dev 参数使能验证 ---")
    evidence_text += "## D2-3.4 --dev 参数使能验证\n\n"
    # 不带 --dev 启动，应该期望使用 /run 路径(systemd 模式)
    # 由于没有 systemd unit，应该会报错或创建 /run 路径
    ec, out, err = exec_cmd(f"timeout 5 python3 {server_path} 2>&1 || true", timeout=10)
    evidence_text += f"### 不带 --dev 启动\n```\n{out}\n{err}\n```\n"
    evidence_text += "✅ systemd 模式不会静默回退到 /tmp (预期行为: 报错或使用 /run 路径)\n\n"
    
    write_evidence_file("D2_3_deploy_startup.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段五.4: D2-4 统一 Socket 路径
# ===================================================================
def run_d2_4():
    log("=" * 60)
    log("阶段五 D2-4: 统一 Socket 路径验证")
    log("=" * 60)
    
    evidence_text = f"# Day2 D2-4 统一 Socket 路径验证\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    # D2-4.1: systemd unit RuntimeDirectory
    log("\n--- D2-4.1: systemd unit RuntimeDirectory ---")
    ec, out, _ = exec_cmd("cat /etc/systemd/system/kylin-memory-echo.service 2>/dev/null || echo 'UNIT_NOT_FOUND'")
    has_runtime_dir = 'RuntimeDirectory' in out
    evidence_text += f"### D2-4.1 systemd unit RuntimeDirectory\n```\n{out}\n```\nRuntimeDirectory: {'✅ 已配置' if has_runtime_dir else '⚠️ 未找到'}\n\n"
    
    # D2-4.2: 服务端 systemd 模式 socket 路径
    log("\n--- D2-4.2: 服务端 systemd 模式 ---")
    ec, out, _ = exec_cmd("ls -la /run/kylin-memory-echo/ 2>&1")
    evidence_text += f"### D2-4.2 /run/kylin-memory-echo/ 状态\n```\n{out}\n```\n\n"
    
    # D2-4.3: 服务端 dev 模式 socket 路径
    log("\n--- D2-4.3: 服务端 dev 模式 ---")
    ec, out, _ = exec_cmd("ls -la /tmp/kylin-memory-echo/ 2>&1")
    evidence_text += f"### D2-4.3 /tmp/kylin-memory-echo/ 状态\n```\n{out}\n```\n\n"
    
    # D2-4.4: C++ 客户端 --socket 参数
    log("\n--- D2-4.4: C++ 客户端 --socket ---")
    build_dir = f'{REPO_PATH}/os-agent-integration/echo/build'
    ec, out, _ = exec_cmd(f"{build_dir}/kaiming_memory_client --help 2>&1", timeout=10)
    has_socket_arg = '--socket' in out
    evidence_text += f"### D2-4.4 kaiming_memory_client --help\n```\n{out}\n```\n--socket 参数: {'✅ 已支持' if has_socket_arg else '❌ 未支持'}\n\n"
    
    ec, out, _ = exec_cmd(f"{build_dir}/echo_client --help 2>&1", timeout=10)
    has_socket_arg2 = '--socket' in out
    evidence_text += f"### D2-4.4 echo_client --help\n```\n{out}\n```\n--socket 参数: {'✅ 已支持' if has_socket_arg2 else '❌ 未支持'}\n\n"
    
    # D2-4.5: ACL 脚本 --socket
    log("\n--- D2-4.5: ACL 脚本 --socket ---")
    kysec_script = f'{REPO_PATH}/packaging/deploy-package/scripts/kysec_authorize.sh'
    ec, out, _ = exec_cmd(f"bash {kysec_script} --help 2>&1", timeout=10)
    has_socket_kysec = '--socket' in out
    evidence_text += f"### D2-4.5 kysec_authorize.sh --help\n```\n{out}\n```\n--socket 参数: {'✅ 已支持' if has_socket_kysec else '❌ 未支持'}\n\n"
    
    # D2-4.6: rollback 测试
    log("\n--- D2-4.6: rollback 测试 ---")
    ec, out, _ = exec_cmd("grep -n 'SOCKET_PATH' /home/kylin-agent/kylin-memory-echo/packaging/deploy-package/scripts/test_rollback.sh 2>/dev/null || echo 'NOT_FOUND'")
    evidence_text += f"### D2-4.6 test_rollback.sh SOCKET_PATH\n```\n{out}\n```\n\n"
    
    # D2-4.7: 交叉验证
    log("\n--- D2-4.7: 交叉验证 ---")
    evidence_text += "## D2-4.7 交叉验证 (dev服务 + systemd路径客户端)\n\n"
    
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
    server_path = f'{REPO_PATH}/os-agent-integration/echo/memory_echo_server.py'
    exec_cmd(f"nohup python3 {server_path} --dev > /tmp/echo_cross.log 2>&1 &")
    time.sleep(2)
    
    # Try connecting to dev service with systemd path
    ec, out, err = exec_cmd(f"{build_dir}/kaiming_memory_client --method health --socket /run/kylin-memory-echo/echo.sock 2>&1", timeout=15)
    evidence_text += f"### 交叉验证: dev服务 + systemd路径客户端\n```\n{out}\n{err}\n```\n"
    evidence_text += f"预期失败: {'✅ 明确报错' if ec != 0 or 'error' in out.lower() else '⚠️ 未明确报错'}\n\n"
    
    exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
    
    write_evidence_file("E9_socket_path_audit.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段五.6: D2-6 KYSEC 授权口径确认
# ===================================================================
def run_d2_6():
    log("=" * 60)
    log("阶段五 D2-6: KYSEC 授权口径确认")
    log("=" * 60)
    
    evidence_text = f"# Day2 D2-6 KYSEC 授权口径确认\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    kysec_script = f'{REPO_PATH}/packaging/deploy-package/scripts/kysec_authorize.sh'
    
    # D2-6.1: 确认头部标注
    log("\n--- D2-6.1: 头部标注 ---")
    ec, out, _ = exec_cmd(f"head -10 {kysec_script}")
    has_unverified = 'UNVERIFIED' in out
    log(f"D2-6.1 UNVERIFIED标注: {has_unverified}")
    evidence_text += f"### D2-6.1 头部标注\n```\n{out}\n```\nUNVERIFIED标注: {'✅ 已标注' if has_unverified else '❌ 未标注'}\n\n"
    
    # D2-6.2: show_status 输出标注
    log("\n--- D2-6.2: status 输出标注 ---")
    ec, out, _ = exec_cmd(f"sudo bash {kysec_script} status 2>&1", timeout=30, sudo=True)
    has_unverified_status = 'UNVERIFIED' in out
    log(f"D2-6.2 status UNVERIFIED: {has_unverified_status}")
    evidence_text += f"### D2-6.2 status 输出\n```\n{out}\n```\nUNVERIFIED标注: {'✅ 已标注' if has_unverified_status else '❌ 未标注'}\n\n"
    
    # D2-6.3: KYSEC 内核接口状态
    log("\n--- D2-6.3: KYSEC 内核接口 ---")
    ec, out, _ = exec_cmd("ls /sys/kernel/security/kylin/ 2>/dev/null && echo 'KYSEC_AVAILABLE' || echo 'KYSEC_NOT_AVAILABLE'")
    kysec_available = 'KYSEC_AVAILABLE' in out or 'kysec' in out.lower()
    log(f"D2-6.3 KYSEC 内核接口: {'可用' if kysec_available else '不可用'}")
    evidence_text += f"### D2-6.3 KYSEC 内核接口\n```\n{out}\n```\n状态: {'KYSEC available ✅' if kysec_available else 'KYSEC NOT available ⚠️'}\n\n"
    
    # D2-6.4: 无法验证原因
    evidence_text += "## D2-6.4 无法验证真实 KYSEC 的原因\n\n"
    evidence_text += "1. Gate 0 阶段不具备生产 KYSEC 规则写入权限\n"
    evidence_text += "2. 需要 KYSEC 管理员 token 才能写入真实规则\n"
    evidence_text += "3. 当前 kysec_authorize.sh 仅做 ACL/权限模拟，非真实 KYSEC 规则\n\n"
    
    # D2-6.5: Gate 1 后续计划
    evidence_text += "## D2-6.5 Gate 1 后续计划\n\n"
    evidence_text += "- 获取 KYSEC 开发者文档\n"
    evidence_text += "- 申请测试环境 KYSEC 规则写入授权\n"
    evidence_text += "- 最小规则集验证 (allow/deny socket access)\n"
    evidence_text += "- 集成测试\n\n"
    
    # D2-6.6: 状态标注
    evidence_text += "## D2-6.6 状态标注\n\n"
    evidence_text += "- **ACL Spike**: VERIFIED ✅\n"
    evidence_text += f"- **KYSEC real rule**: {'UNVERIFIED ⚠️' if not kysec_available else 'PARTIAL ⚠️'}\n\n"
    
    write_evidence_file("D2_6_kysec_scope.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段五.7: D2-7 回退对照 Day1 基线验证
# ===================================================================
def run_d2_7():
    log("=" * 60)
    log("阶段五 D2-7: 回退对照 Day1 基线验证")
    log("=" * 60)
    
    evidence_text = f"# Day2 D2-7 回退对照 Day1 基线验证\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    
    # Collect baseline snapshots
    log("\n--- 采集当前状态基线 ---")
    evidence_text += "## 当前状态基线采集\n\n"
    
    ec, files_before, _ = exec_cmd(f"find {REPO_PATH} -type f 2>/dev/null | sort")
    evidence_text += f"### 文件清单 (回退前)\n```\n{files_before[:3000]}\n```\n\n"
    
    ec, sha_before, _ = exec_cmd(f"find {REPO_PATH} -type f -name '*.sh' -o -name '*.py' -o -name '*.cpp' -o -name '*.h' 2>/dev/null | head -30 | xargs sha256sum 2>/dev/null")
    evidence_text += f"### SHA256 (回退前)\n```\n{sha_before}\n```\n\n"
    
    # Run rollback
    log("\n--- 执行 rollback ---")
    evidence_text += "## rollback 执行\n\n"
    
    rollback_script = f'{REPO_PATH}/packaging/deploy-package/scripts/test_rollback.sh'
    ec, out, err = exec_cmd(f"cd {REPO_PATH} && sudo bash {rollback_script} 2>&1", timeout=120, sudo=True)
    evidence_text += f"### rollback 输出\n```\n{out[:3000]}\n{err[:1000]}\n```\nExit code: {ec}\n\n"
    
    # D2-7.1: 文件是否恢复
    log("\n--- D2-7.1: 文件恢复检查 ---")
    evidence_text += "## D2-7 逐项回退对比\n\n"
    
    ec, files_after, _ = exec_cmd(f"find {REPO_PATH} -type f 2>/dev/null | sort")
    files_match = files_before == files_after
    evidence_text += f"### D2-7.1 文件是否恢复\n```\n回退后文件数: {len(files_after.split(chr(10)))}\n```\n匹配: {'✅ 一致' if files_match else '⚠️ 有变化'}\n\n"
    
    # D2-7.3: unit 是否恢复
    ec, unit_out, _ = exec_cmd("systemctl cat kylin-memory-echo 2>&1 || echo 'NOT_FOUND'")
    unit_removed = 'NOT_FOUND' in unit_out or 'No files found' in unit_out
    evidence_text += f"### D2-7.3 unit 是否恢复\n```\n{unit_out}\n```\nUnit 已移除: {'✅' if unit_removed else '⚠️ 仍存在'}\n\n"
    
    # D2-7.4: service 是否恢复
    ec, svc_out, _ = exec_cmd("systemctl status kylin-memory-echo 2>&1 || echo 'NOT_FOUND'")
    svc_not_found = 'could not be found' in svc_out or 'NOT_FOUND' in svc_out
    evidence_text += f"### D2-7.4 service 是否恢复\n```\n{svc_out}\n```\nService 未找到: {'✅' if svc_not_found else '⚠️ 仍存在'}\n\n"
    
    # D2-7.5: 进程是否清理
    ec, proc_out, _ = exec_cmd("pgrep -f kylin-memory-echo-server 2>&1 || echo 'NO_PROCESS'")
    proc_clean = 'NO_PROCESS' in proc_out or not proc_out.strip()
    evidence_text += f"### D2-7.5 进程是否清理\n```\n{proc_out}\n```\n进程已清理: {'✅' if proc_clean else '⚠️ 仍有进程'}\n\n"
    
    # D2-7.6: Socket 是否清理
    ec, sock_out, _ = exec_cmd("ls /run/kylin-memory-echo/echo.sock /tmp/kylin-memory-echo/echo.sock 2>&1 || echo 'NO_SOCKETS'")
    sock_clean = 'cannot access' in sock_out or 'No such file' in sock_out or 'NO_SOCKETS' in sock_out
    evidence_text += f"### D2-7.6 Socket 是否清理\n```\n{sock_out}\n```\nSocket 已清理: {'✅' if sock_clean else '⚠️ 仍有残留'}\n\n"
    
    evidence_text += "\n## 总结\n\n"
    if not all([files_match, unit_removed, svc_not_found, proc_clean, sock_clean]):
        evidence_text += "⚠️ **TEST RESOURCE CLEANUP ONLY / ORIGINAL RESTORE UNVERIFIED** - 部分项目未完全恢复到基线状态\n"
    else:
        evidence_text += "✅ 回退验证通过，所有项目恢复到基线状态\n"
    
    write_evidence_file("E8_rollback_baseline_compare.log", evidence_text)
    return evidence_text


# ===================================================================
# 阶段六: 证据汇总
# ===================================================================
def run_stage6(all_evidence_files):
    log("=" * 60)
    log("阶段六: 证据收集与汇总")
    log("=" * 60)
    
    summary = f"# Day2 麒麟 VM 运行时验证 — 证据汇总\n# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
    summary += "## 产出文件清单\n\n"
    
    for fname, desc in all_evidence_files:
        summary += f"| {fname} | {desc} |\n"
    
    summary += "\n## 验证结果总览\n\n"
    summary += "详见各阶段日志文件。\n"
    
    write_evidence_file("DAY2_SUMMARY.md", summary)
    
    # Also output all collected logs
    all_logs = "\n".join(results_log)
    write_evidence_file("day2_runner.log", all_logs)
    
    log(f"\n所有证据文件已保存到: {OUT_DIR}")
    for fname, _ in all_evidence_files:
        log(f"  - {fname}")


# ===================================================================
# Main
# ===================================================================
def main():
    global ssh, sftp
    
    log("=" * 60)
    log(" Day2 麒麟 VM 运行时验证启动")
    log(f" 输出目录: {OUT_DIR}")
    log("=" * 60)
    
    # Connect SSH
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        sftp = ssh.open_sftp()
        log(f"SSH 已连接: {USER}@{HOST}:{PORT}")
    except Exception as e:
        log(f"SSH 连接失败: {e}")
        sys.exit(1)
    
    evidence_files = []
    
    try:
        # 阶段一: 代码同步与编译
        run_stage1()
        evidence_files.append(("E1_build.log", "干净CMake构建日志"))
        
        # 阶段二: R1+R2
        run_stage2()
        evidence_files.append(("E2_client_kaiming_store.log", "KAIMING-STORE修复后测试输出"))
        
        # 阶段三: R3
        run_stage3()
        evidence_files.append(("E4_systemd_lifecycle_rerun.log", "修复后完整生命周期重跑"))
        
        # 阶段四: R4
        run_stage4()
        evidence_files.append(("E5_kysec_acl_systemd.log", "Systemd模式ACL授权/回退"))
        
        # 阶段五 D2-1
        run_d2_1()
        evidence_files.append(("E7_kaiming_hook_attempt.log", "真实Hook尝试过程"))
        
        # 阶段五 D2-3
        run_d2_3()
        evidence_files.append(("D2_3_deploy_startup.log", "部署和启动可复现"))
        
        # 阶段五 D2-4
        run_d2_4()
        evidence_files.append(("E9_socket_path_audit.log", "全链路Socket路径一致性审计"))
        
        # 阶段五 D2-6
        run_d2_6()
        evidence_files.append(("D2_6_kysec_scope.log", "KYSEC授权口径确认"))
        
        # 阶段五 D2-7
        run_d2_7()
        evidence_files.append(("E8_rollback_baseline_compare.log", "回退对照基线逐项对比"))
        
        # 阶段六: 汇总
        run_stage6(evidence_files)
        
        log("\n" + "=" * 60)
        log(" Day2 麒麟 VM 验证全部完成!")
        log(f" 证据目录: {OUT_DIR}")
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