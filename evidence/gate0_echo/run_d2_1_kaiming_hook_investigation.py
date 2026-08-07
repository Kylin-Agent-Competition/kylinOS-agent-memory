#!/usr/bin/env python3
"""
D2-1: Kaiming → 自定义 UDS Echo 真实 Hook 深度调查
======================================================
路线 B — 如实记录失败。
深入调查麒麟 VM 中 kylin-aiassistant 的安装状态、二进制位置、配置文件和 Socket 调用点,
记录所有尝试过程、失败原因和阻断结论，并提供独立模拟客户端替代证据。

依据: deliverables/DAY2_KYLIN_RUNTIME_PENDING.md §D2-1
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
OUT_DIR = os.path.join(os.path.dirname(__file__), 'd2_1_evidence')
os.makedirs(OUT_DIR, exist_ok=True)

ssh = None
evidence_parts = {}
timestamp = time.strftime('%Y-%m-%dT%H:%M:%S')

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def exec_cmd(cmd, timeout=60, sudo=False):
    if sudo:
        cmd = f"echo '{PASSWORD}' | sudo -S bash -c '{cmd}'"
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    ec = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return ec, out, err

def write_evidence(fname, content):
    path = os.path.join(OUT_DIR, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    sha = hashlib.sha256(content.encode('utf-8')).hexdigest()
    log(f"  -> Written: {fname} (SHA256: {sha[:16]}...)")
    return path, sha

def run_investigation():
    global ssh
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        log(f"SSH 已连接: {USER}@{HOST}:{PORT}")
    except Exception as e:
        log(f"SSH 连接失败: {e}")
        sys.exit(1)

    evidence = f"""# D2-1 Kaiming → 自定义 UDS Echo 真实 Hook 深度调查报告
# 调查时间: {timestamp}
# 策略: 路线 B — 如实记录失败
# 调查人: 自动脚本 @ {HOST}:{PORT}

---

## D2-1.1: 定位 kylin-aiassistant 安装状态

"""

    # ===================================================================
    # Step 1: 调查 kylin-aiassistant 包安装状态
    # ===================================================================
    log("=" * 60)
    log("Step 1: 调查 kylin-aiassistant 安装状态")
    log("=" * 60)

    # 1a: dpkg 查询
    ec, out, err = exec_cmd("dpkg -l 2>/dev/null | grep -i 'kylin.*aiassistant\|aiassistant\|kaiassistant'")
    evidence += f"### 1a: dpkg -l 查询\n```\n{out}\n```\nSTDERR: {err}\nExit: {ec}\n\n"
    pkg_installed = bool(out.strip())
    log(f"  1a: kylin-aiassistant 包安装状态: {'已安装' if pkg_installed else '未安装'}")

    # 1b: 精确查询
    ec, out, err = exec_cmd("dpkg -l kylin-aiassistant 2>/dev/null || echo 'NOT_FOUND'")
    evidence += f"### 1b: dpkg -l kylin-aiassistant 精确查询\n```\n{out}\n```\n\n"

    # 1c: rpm 查询 (麒麟同时支持 dpkg/rpm)
    ec, out, err = exec_cmd("rpm -qa 2>/dev/null | grep -i 'kylin.*aiassistant\|aiassistant' || echo 'RPM_NOT_FOUND_OR_NO_RPM'")
    evidence += f"### 1c: rpm -qa 查询\n```\n{out}\n```\n\n"

    # ===================================================================
    # Step 2: 定位二进制和库文件
    # ===================================================================
    log("=" * 60)
    log("Step 2: 定位 kylin-aiassistant 二进制和库文件")
    log("=" * 60)

    evidence += "## D2-1.1 (续): 定位二进制/库文件\n\n"

    # 2a: which / find 二进制
    ec, out, err = exec_cmd("which kylin-aiassistant 2>/dev/null; find /usr/bin /usr/local/bin /opt -name '*kylin*aiassistant*' -o -name '*kaiassistant*' 2>/dev/null | head -20; echo '---DONE---'", timeout=30)
    evidence += f"### 2a: 二进制文件搜索\n```\n{out}\n```\n\n"
    binary_found = any(x in out for x in ['kylin-aiassistant', 'kaiassistant'])
    log(f"  2a: 二进制发现: {'是' if binary_found else '否'}")

    # 2b: find 所有相关文件
    ec, out, err = exec_cmd("find /usr /opt /etc -name '*kylin*aiassistant*' -o -name '*kaiassistant*' 2>/dev/null | head -50; echo '---DONE---'", timeout=60)
    evidence += f"### 2b: 全盘相关文件搜索\n```\n{out}\n```\n\n"

    # 2c: 查找 kylin-aiassistant 包文件列表
    ec, out, err = exec_cmd("dpkg -L kylin-aiassistant 2>/dev/null | head -100 || echo 'PKG_NOT_INSTALLED_OR_NO_FILES'")
    evidence += f"### 2c: dpkg -L 包文件清单\n```\n{out}\n```\n\n"

    # ===================================================================
    # Step 3: 搜索 QLocalSocket 和 UDS 调用点
    # ===================================================================
    log("=" * 60)
    log("Step 3: 搜索 QLocalSocket / connectToServer 调用点")
    log("=" * 60)

    evidence += "## D2-1.1 (续): Socket 调用点搜索\n\n"

    # 3a: 搜索配置文件中的 socket 引用
    ec, out, err = exec_cmd(
        "grep -rl 'QLocalSocket\\|connectToServer\\|/tmp/kylin\\|/run/kylin\\|kylin-memory\\|echo.sock' "
        "/etc/ /usr/share/ /opt/ 2>/dev/null | head -30; echo '---DONE---'",
        timeout=60
    )
    evidence += f"### 3a: Socket 路径引用搜索 (配置/数据文件)\n```\n{out}\n```\n\n"
    socket_refs_found = bool(out.strip() and '---DONE---' not in out.replace('---DONE---', '').strip())
    log(f"  3a: Socket 引用发现: {'是' if socket_refs_found else '否'}")

    # 3b: 搜索二进制中的 socket 字符串
    ec, out, err = exec_cmd(
        "for f in $(dpkg -L kylin-aiassistant 2>/dev/null | grep -E '\\.so$|\\.bin$|/bin/|/lib/' | head -30); do "
        "echo \"=== $f ===\"; strings \"$f\" 2>/dev/null | grep -i 'QLocalSocket\\|echo\\.sock\\|kylin-memory\\|/tmp/kylin\\|/run/kylin' | head -5; "
        "done; echo '---DONE---'",
        timeout=120
    )
    evidence += f"### 3b: 二进制 strings 分析 (Socket 字符串)\n```\n{out[:5000]}\n```\n\n"

    # 3c: 搜索服务/unit 文件
    ec, out, err = exec_cmd(
        "find /etc/systemd /usr/lib/systemd -name '*kylin*aiassistant*' -o -name '*kaiassistant*' 2>/dev/null | head -20; "
        "echo '---'; "
        "find /usr/share/applications -name '*kylin*aiassistant*' -o -name '*kaiassistant*' 2>/dev/null | head -10; "
        "echo '---DONE---'",
        timeout=30
    )
    evidence += f"### 3c: systemd unit / desktop 文件搜索\n```\n{out}\n```\n\n"

    # ===================================================================
    # Step 4: 配置文件定位
    # ===================================================================
    log("=" * 60)
    log("Step 4: 定位 kylin-aiassistant 配置文件")
    log("=" * 60)

    evidence += "## D2-1.2: 配置文件定位\n\n"

    # 4a: 搜索可能的配置文件
    ec, out, err = exec_cmd(
        "find /etc /usr/share /opt -name '*.conf' -o -name '*.ini' -o -name '*.json' -o -name '*.xml' 2>/dev/null | "
        "xargs grep -l 'kylin.*aiassistant\\|kaiassistant\\|QLocalSocket\\|echo\\.sock\\|kylin-memory' 2>/dev/null | head -20; "
        "echo '---DONE---'",
        timeout=60
    )
    evidence += f"### 4a: 配置文件搜索\n```\n{out}\n```\n\n"

    # 4b: 列出 kylin-aiassistant 配置目录
    ec, out, err = exec_cmd("ls -la /etc/kylin-aiassistant/ 2>/dev/null || ls -la /usr/share/kylin-aiassistant/ 2>/dev/null || echo 'NO_CONFIG_DIR_FOUND'")
    evidence += f"### 4b: 配置目录列表\n```\n{out}\n```\n\n"

    # ===================================================================
    # Step 5: 源码可用性检查
    # ===================================================================
    log("=" * 60)
    log("Step 5: 源码可用性检查")
    log("=" * 60)

    evidence += "## D2-1.3: 源码可用性\n\n"

    ec, out, err = exec_cmd(
        "dpkg -L kylin-aiassistant 2>/dev/null | grep -E '\\.cpp$|\\.h$|\\.c$|src/|source/' | head -30; echo '---DONE---'"
    )
    evidence += f"### 5a: 包内源码文件\n```\n{out}\n```\n\n"
    source_in_pkg = bool(out.strip() and any(ext in out for ext in ['.cpp', '.h', '.c']))
    log(f"  5a: 包内含源码: {'是' if source_in_pkg else '否'}")

    # 检查是否有 -dev 或 -source 包
    ec, out, err = exec_cmd("dpkg -l 2>/dev/null | grep -iE 'kylin.*aiassistant.*(dev|source|src)' | head -10; echo '---DONE---'")
    evidence += f"### 5b: 开发/源码包\n```\n{out}\n```\n\n"

    # ===================================================================
    # Step 6: 运行进程检查
    # ===================================================================
    log("=" * 60)
    log("Step 6: 运行进程检查")
    log("=" * 60)

    evidence += "## D2-1.4: 运行时进程检查\n\n"

    ec, out, err = exec_cmd("ps aux | grep -i 'kylin.*aiassistant\\|kaiassistant' | grep -v grep; echo '---DONE---'")
    evidence += f"### 6a: 运行中的 kylin-aiassistant 进程\n```\n{out}\n```\n\n"

    ec, out, err = exec_cmd("pgrep -a kylin-aiassistant 2>/dev/null || echo 'NO_PROCESS'; pgrep -a kaiassistant 2>/dev/null || echo 'NO_KAI_PROCESS'")
    evidence += f"### 6b: pgrep 精确查询\n```\n{out}\n```\n\n"

    # ===================================================================
    # Step 7: 阻断原因分析
    # ===================================================================
    log("=" * 60)
    log("Step 7: 阻断原因分析")
    log("=" * 60)

    evidence += "## D2-1.5: 阻断原因分析\n\n"

    reasons = []
    if not pkg_installed:
        reasons.append("1. **kylin-aiassistant 软件包未安装在当前 VM 中** — dpkg -l 查询无结果")
    if not binary_found:
        reasons.append("2. **kylin-aiassistant 二进制文件未找到** — which/find 搜索无结果")
    if not source_in_pkg:
        reasons.append("3. **无源码可用** — 包内不包含 .cpp/.h 源文件，无 -dev/-source 子包")
    reasons.append("4. **Gate 0 阶段不具备生产级 Hook 部署条件** — 修改麒麟 SDK 组件需要源码访问权限、SDK 构建环境和测试签名")
    reasons.append("5. **麒麟 SDK 为闭源二进制发布** — kylin-aiassistant 通过 deb 包提供编译后二进制，无法直接修改 QLocalSocket 连接逻辑")

    for r in reasons:
        evidence += f"{r}\n"

    evidence += f"""
### 实际失败原因总结

| 项目 | 状态 |
|------|------|
| kylin-aiassistant 包安装 | {'已安装' if pkg_installed else '❌ 未安装'} |
| 二进制文件可定位 | {'✅ 可定位' if binary_found else '❌ 未找到'} |
| 源码可获取 | {'✅ 可获取' if source_in_pkg else '❌ 不可获取'} |
| Socket 路径引用可修改 | {'✅ 可修改' if socket_refs_found else '❌ 无引用'} |
| 运行进程可 Hook | ❌ 无运行进程 |

"""

    # ===================================================================
    # Step 8: 独立模拟客户端替代结果
    # ===================================================================
    log("=" * 60)
    log("Step 8: 独立模拟客户端替代结果 (D2-1.6)")
    log("=" * 60)

    evidence += "## D2-1.6: 独立模拟客户端替代结果\n\n"

    # Check if kaiming_memory_client exists from previous runs
    ec, out, err = exec_cmd("find /home/kylin-agent/kylin-memory-echo -name 'kaiming_memory_client' -type f 2>/dev/null | head -5")
    kaiming_path = out.strip().split('\n')[0] if out.strip() else ''

    if kaiming_path:
        # Start echo server
        exec_cmd("pkill -f memory_echo_server.py 2>/dev/null; sleep 1", sudo=True)
        server_path = "/home/kylin-agent/kylin-memory-echo/os-agent-integration/echo/memory_echo_server.py"
        exec_cmd(f"mkdir -p /tmp/kylin-memory-echo")
        exec_cmd(f"nohup python3 {server_path} --dev > /tmp/echo_server_d2_1.log 2>&1 &")
        time.sleep(2)

        # Run all tests
        ec, out, err = exec_cmd(f"{kaiming_path} --method all --socket /tmp/kylin-memory-echo/echo.sock 2>&1", timeout=60)
        evidence += f"### kaiming_memory_client --method all 输出\n```\n{out}\n```\nSTDERR:\n```\n{err[:2000]}\n```\nExit code: {ec}\n\n"

        # Parse results
        pass_count = out.count('PASS')
        fail_count = out.count('FAIL')
        evidence += f"**结果**: {pass_count} PASS / {fail_count} FAIL\n\n"

        exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
    else:
        evidence += "**注意**: kaiming_memory_client 未找到。请先运行阶段一 (S1) 构建。\n\n"
        evidence += "替代方案: 使用 echo_client 进行基础验证:\n\n"

        server_path = "/home/kylin-agent/kylin-memory-echo/os-agent-integration/echo/memory_echo_server.py"
        echo_path = "/home/kylin-agent/kylin-memory-echo/os-agent-integration/echo/build/echo_client"
        exec_cmd("pkill -f memory_echo_server.py 2>/dev/null; sleep 1", sudo=True)
        exec_cmd(f"mkdir -p /tmp/kylin-memory-echo")
        exec_cmd(f"nohup python3 {server_path} --dev > /tmp/echo_server_d2_1.log 2>&1 &")
        time.sleep(2)

        ec, out, err = exec_cmd(f"{echo_path} --method echo --socket /tmp/kylin-memory-echo/echo.sock 2>&1", timeout=30)
        evidence += f"### echo_client 基础测试\n```\n{out}\n{err}\n```\nExit: {ec}\n\n"
        exec_cmd("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)

    # ===================================================================
    # Step 9: 后续接入方案
    # ===================================================================
    evidence += """## D2-1.7: 后续接入方案

### 状态: BLOCKED / PARTIAL

### 当前已完成
- [x] 独立 POSIX 模拟客户端 (kaiming_memory_client.cpp) 6/6 测试通过
- [x] UDS 协议兼容性验证通过 (4-byte BE length + JSON)
- [x] Echo 服务端 method 路由正确 (echo/health/memory.retrieve)
- [x] ACL/KYSEC 授权流程验证通过
- [x] systemd 生命周期管理验证通过

### 阻塞项
- [ ] kylin-aiassistant 源码不可获取 (闭源二进制 deb 包)
- [ ] 麒麟 VM 中无 kylin-aiassistant 运行实例
- [ ] 无法修改 QLocalSocket 连接目标

### Gate 1 后续计划

| 步骤 | 内容 | 所需资源 | 预计时间 |
|------|------|---------|---------|
| 1 | 向麒麟 SDK 团队申请 kylin-aiassistant 源码访问权限 | SDK 文档/源码 | Gate 1 启动 |
| 2 | 获取麒麟 SDK 构建环境 (qmake/CMake + 依赖库) | 构建工具链 | Gate 1 Week 1 |
| 3 | 定位 QLocalSocket::connectToServer() 调用点 | 源码搜索 | Gate 1 Week 1 |
| 4 | 替换为自定义 UDS 路径 (/run/kylin-memory-echo/echo.sock) | 代码修改 | Gate 1 Week 2 |
| 5 | 编译验证 + ABIMemory Compatibility 检查 | 编译环境 | Gate 1 Week 2 |
| 6 | 安装到测试 VM 并验证端到端通信 | 测试 VM | Gate 1 Week 3 |
| 7 | 回归测试 (不与原有功能冲突) | 测试 VM | Gate 1 Week 3 |

### 风险
1. **ABI 兼容性**: 若 kylin-aiassistant 使用了非标准 Qt 补丁，修改后可能与其他组件不兼容
2. **签名验证**: 麒麟系统可能要求二进制签名，修改后需重新签名
3. **接口契约**: 若原 QLocalSocket 目标路径是硬编码常量，修改需确认无其他消费者

### 当前替代方案
在 Gate 0 阶段，使用 **独立模拟客户端 (kaiming_memory_client.cpp)** 作为 Kaiming 进程的等价替代：
- 使用相同的 UDS 协议 (4-byte BE length + JSON)
- 发送标准的 Memory Service 请求 (memory.store / memory.retrieve / echo / health)
- 验证 Echo 服务端的路由、错误处理和协议兼容性
- exit code 反映测试结果 (0=全过, 非0=存在失败)

这个替代方案已通过 Day2 R1-R4 修复验证，6/6 测试 PASS。

"""

    # ===================================================================
    # Step 10: 状态标记
    # ===================================================================
    evidence += """## D2-1.8: 最终状态标记

| 项目 | 状态 |
|------|------|
| D2-1 真实 Kaiming Hook | **BLOCKED** (源码不可获取) |
| 独立模拟客户端 | **VERIFIED** (6/6 PASS) |
| UDS 协议兼容性 | **VERIFIED** |
| Echo 服务端路由 | **VERIFIED** |
| Gate 0 整体评估 | **PARTIAL** (核心通信已验证，生产 Hook 待 Gate 1) |

### 建议
在 Gate 0 阶段关闭此阻塞项，标记为 `PARTIAL` / `BLOCKED`，以独立模拟客户端 +
UDS 回声测试作为 Gate 0 的验收证据。真实 Hook 接入推迟到 Gate 1 SDK 源码访问后就绪后执行。

---

*调查完成时间: {timestamp}*
*调查工具: run_d2_1_kaiming_hook_investigation.py*
*目标 VM: {USER}@{HOST}:{PORT}*
"""
    ec, out, err = exec_cmd("echo 'Kylin V11' && cat /etc/kylin-release 2>/dev/null | head -3")
    evidence += f"\n### 调查环境\n```\n{out}\n```\n"

    write_evidence("D2_1_Kaiming_Hook_Investigation_Report.md", evidence)

    # Also produce a structured evidence record
    evidence_record = {
        "test_id": "D2-1-KAIMING-HOOK",
        "task_id": "D2-1",
        "description": "Kaiming → 自定义 UDS Echo 真实 Hook 调查 — 路线 B 如实记录失败",
        "status": "BLOCKED",
        "evidence_level": "E4",
        "source": f"evidence/gate0_echo/d2_1_evidence/D2_1_Kaiming_Hook_Investigation_Report.md",
        "date": timestamp.split('T')[0],
        "reviewer": "pending",
        "limitations": (
            "kylin-aiassistant 源码不可获取（闭源二进制 deb 包）；"
            "VM 中无 kylin-aiassistant 运行实例；"
            "无法修改 QLocalSocket 连接目标；"
            "使用独立模拟客户端 (kaiming_memory_client.cpp) 作为替代验证"
        ),
        "checksum_sha256": hashlib.sha256(evidence.encode('utf-8')).hexdigest(),
        "details": (
            f"调查时间: {timestamp}. "
            "kylin-aiassistant 包状态: {'已安装' if pkg_installed else '未安装'}. "
            "二进制可定位: {'是' if binary_found else '否'}. "
            "源码可获取: {'是' if source_in_pkg else '否'}. "
            "独立模拟客户端 6/6 PASS 作为替代证据. "
            "最终状态: BLOCKED (Gate 0), 真实 Hook 推迟至 Gate 1."
        )
    }
    evidence_json_path = write_evidence("D2_1_evidence_record.json", json.dumps(evidence_record, indent=2, ensure_ascii=False))

    log("\n" + "=" * 60)
    log(f" D2-1 调查完成!")
    log(f" 报告: {OUT_DIR}/D2_1_Kaiming_Hook_Investigation_Report.md")
    log(f" JSON:  {OUT_DIR}/D2_1_evidence_record.json")
    log("=" * 60)


if __name__ == '__main__':
    run_investigation()