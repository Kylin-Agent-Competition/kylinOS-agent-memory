#!/usr/bin/env python3
"""采集麒麟 VM 环境基线信息 - Day1-1 环境冻结脚本 (Transport direct)"""
import os, sys, datetime, socket, paramiko

HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "kylin-agent")
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "").strip()
LOG_FILE = os.path.join(os.path.dirname(__file__), "environment.log")

if not PASSWORD:
    print("ERROR: KYLIN_VM_PASSWORD 环境变量未设置")
    sys.exit(1)

# Use Transport directly (SSHClient.connect() has algorithm compat issues)
transport = paramiko.Transport((HOST, PORT))
try:
    transport.connect(username=USER, password=PASSWORD)
except Exception as e:
    print(f"CONNECTION FAILED: {e}")
    sys.exit(1)

def run(transport, cmd, timeout=15):
    """Execute command via Transport.open_session()"""
    chan = transport.open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    chan.settimeout(timeout)
    out = b""
    while True:
        try:
            data = chan.recv(4096)
            if not data:
                break
            out += data
        except socket.timeout:
            break
        except EOFError:
            break
    code = chan.recv_exit_status()
    chan.close()
    return code, out.decode("utf-8", errors="replace").strip(), ""

ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
code, whoami, _ = run(transport, "whoami")
code, hostname, _ = run(transport, "hostname")

lines = []
lines.append("=" * 60)
lines.append(" 麒麟 OS Agent 记忆系统 — Day 1 环境基线冻结")
lines.append("=" * 60)
lines.append(f"采集时间: {ts}")
lines.append(f"执行用户: {whoami}")
lines.append(f"执行主机: {hostname}")
lines.append(f"PR21 HEAD: dbac3b69e9ed79b5a837a58a9291bb7e30667f39")
lines.append("=" * 60)
lines.append("")

checks = [
    ("[1/15] 麒麟系统版本 (uname -a)", "uname -a"),
    ("[2/15] 操作系统发行版", "cat /etc/os-release"),
    ("[3/15] 麒麟 VM 快照编号", "echo '需手动填写: VirtualBox 快照名称与创建时间'"),
    ("[4/15] Python 版本", "python3 --version"),
    ("[5/15] g++ 版本", "g++ --version 2>&1 | head -1"),
    ("[6/15] CMake 版本", "cmake --version 2>&1 | head -1"),
    ("[7/15] systemd 版本", "systemctl --version 2>&1 | head -2"),
    ("[8/15] Kaiming/麒灵宿主版本", "dpkg -l 2>/dev/null | grep kylin-aiassistant || echo '未安装'"),
    ("[9/15] kylin-ai-runtime 版本", "dpkg -l 2>/dev/null | grep kylin-ai-runtime || echo '未安装'"),
    ("[10/15] Embedding SDK 版本", "dpkg -l 2>/dev/null | grep kylin-coreai-embedding || echo '未安装'"),
    ("[11/15] KYSEC 当前状态", "cat /sys/kernel/security/kylin/status 2>/dev/null || echo 'KYSEC 不可用'"),
    ("[12/15] 测试用户 (id)", "id"),
    ("[13/15] 测试目录 (pwd)", "pwd"),
    ("[14/15] 原始 Socket、unit 和进程状态",
     "echo '---SOCKS---'; ss -lnpx 2>/dev/null | grep -i kylin || echo '无kylin相关socket'; "
     "echo '---UNITS---'; systemctl list-units --all 2>/dev/null | grep -i kylin || echo '无kylin相关unit'; "
     "echo '---DIR---'; ls -la /run/kylin-memory-echo/ 2>/dev/null || echo 'Socket目录不存在'; "
     "echo '---SERVICE---'; ls -la /etc/systemd/system/kylin-memory-echo.service 2>/dev/null || echo 'Unit不存在'"),
    ("[15/15] 仓库当前 checked-out commit", "git rev-parse HEAD 2>/dev/null || echo 'NOT_IN_GIT_REPO'"),
]

for label, cmd in checks:
    lines.append(label)
    code, out, err = run(transport, cmd)
    for line in out.split("\n"):
        lines.append(line.strip())
    lines.append(f"(exit_code={code})")
    lines.append("")

lines.append("=" * 60)
lines.append(" 环境信息采集完成 — 待 Review 确认后冻结为 Day 1 基线")
lines.append("=" * 60)

content = "\n".join(lines)
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write(content)

print(f"DONE: environment.log written ({len(content)} bytes)")
transport.close()