#!/usr/bin/env python3
"""阶段3全面修复+测试: 诊断S3-BLOCK-001, VM重编译hook, socat, 完整Hook+协议+异常测试"""
import os, sys, json, hashlib, time
from datetime import datetime, timezone, timedelta

SGT = timezone(timedelta(hours=8))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VM_HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
VM_PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
VM_USER = os.environ.get("KYLIN_VM_USER", "kylin-agent")
VM_PASS = os.environ.get("KYLIN_VM_PASSWORD", "")
REMOTE_BASE = "/home/kylin-agent/kylin-memory-echo"
LOCAL_ECHO = os.path.join(PROJECT_ROOT, "os-agent-integration", "echo")
LOCAL_PATCHES = os.path.join(PROJECT_ROOT, "os-agent-integration", "patches")
LOCAL_EVIDENCE = os.path.join(PROJECT_ROOT, "evidence", "l2-kylin-vm", "d4_openkylin_remediation")

def sha256_local(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

try:
    import paramiko
except ImportError:
    print("ERROR: paramiko not available"); sys.exit(1)

print(f"[{datetime.now(SGT):%H:%M:%S}] Stage3 Comprehensive Test Started")
print(f"  Target: {VM_HOST}:{VM_PORT} as {VM_USER}")

results = {
    "stage": "3_comprehensive",
    "started_at": datetime.now(SGT).isoformat(),
    "steps": {},
    "diagnostics": {},
    "hook_tests": [],
    "protocol_tests": [],
    "error_tests": [],
    "errors_found": []
}

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASS, timeout=60, banner_timeout=60)
    print("  Connected OK")
except Exception as ex:
    print(f"  FAILED: {ex}" + str(ex)); sys.exit(1)

sftp = ssh.open_sftp()

def q(cmd, t=30):
    """短命令执行(避免nohup后台阻塞通道)"""
    _, o, e = ssh.exec_command(cmd, timeout=t)
    ec = o.channel.recv_exit_status()
    return ec, o.read().decode("utf-8", errors="replace"), e.read().decode("utf-8", errors="replace")

def sp(text):
    """Safe print for GBK console"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))

def upload_file(local, remote):
    sftp.put(local, remote)
    try:
        st = sftp.stat(remote)
        sp(f"  Upload: {os.path.basename(local)} ({st.st_size} bytes)")
        return st.st_size
    except:
        sp(f"  Upload: {os.path.basename(local)} (stat failed)")
        return 0

# ============================================================
# PHASE 0: VM诊断
# ============================================================
sp("\n" + "="*60)
sp("PHASE 0: VM Diagnostics")
sp("="*60)

ec, out, _ = q("uname -a && cat /etc/.kyinfo 2>/dev/null | head -5", 10)
sp(f"  System: {out.strip()[:300]}")

ec, out, _ = q("which gcc && gcc --version 2>&1 | head -2", 10)
sp(f"  gcc: {out.strip()[:200]}")
results["diagnostics"]["gcc"] = out.strip()[:200]

ec, out, _ = q("which python3 && python3 --version 2>&1", 10)
sp(f"  python3: {out.strip()}")
results["diagnostics"]["python3"] = out.strip()

ec, out, _ = q("which strace 2>/dev/null && echo HAS_STRACE || echo NO_STRACE", 10)
results["diagnostics"]["strace"] = "available" if "HAS_STRACE" in out else "missing"

ec, out, _ = q("which socat 2>/dev/null && echo HAS_SOCAT || echo NO_SOCAT", 10)
results["diagnostics"]["socat"] = "available" if "HAS_SOCAT" in out else "missing"

ec, out, _ = q("ldd --version 2>&1 | head -1", 10)
results["diagnostics"]["ldd"] = out.strip()[:200]

# Check LD_PRELOAD capability
sp("\n  --- LD_PRELOAD capability ---")
ec, out, _ = q("echo 'int main(){return 0;}' | gcc -xc -o /tmp/_test_ld - 2>&1 && echo COMPILE_OK", 10)
sp(f"  Test compile: {out.strip()[:100]}")

ec, out, _ = q(f"test -f {REMOTE_BASE}/lib/libconnect_hook.so && echo HOOK_EXISTS || echo NO_HOOK", 5)
sp(f"  Hook .so exists: {'YES' if 'EXISTS' in out else 'NO'}")

if "HOOK_EXISTS" in out or "EXISTS" in out:
    ec, out, _ = q(f"file {REMOTE_BASE}/lib/libconnect_hook.so && ldd {REMOTE_BASE}/lib/libconnect_hook.so 2>&1", 10)
    sp(f"  Hook .so details: {out.strip()[:400]}")
    results["diagnostics"]["hook_so_file"] = out.strip()[:400]

    # Try LD_PRELOAD with test binary - CRITICAL DIAGNOSTIC
    ec, out, err = q(f"LD_PRELOAD={REMOTE_BASE}/lib/libconnect_hook.so /tmp/_test_ld 2>&1; echo EXIT=$?", 10)
    sp(f"  LD_PRELOAD test: {out.strip()[:300]} | {err.strip()[:300]}")
    if "failed to map segment" in out or "failed to map segment" in err:
        results["errors_found"].append("S3-BLOCK-001: LD_PRELOAD hook .so failed to map segment - 需VM本地重编译")
        sp("  >>> CONFIRMED: S3-BLOCK-001 - Hook .so incompatible, needs VM recompile")

# ============================================================
# PHASE 1: 在VM上重编译 libconnect_hook.so
# ============================================================
sp("\n" + "="*60)
sp("PHASE 1: VM-native recompile libconnect_hook.so")
sp("="*60)

# Read local hook source
hook_src_path = os.path.join(LOCAL_PATCHES, "libconnect_hook.c")
if not os.path.exists(hook_src_path):
    sp(f"  FATAL: Hook source not found at {hook_src_path}")
    results["steps"]["hook_recompile"] = "FATAL_SOURCE_MISSING"
else:
    with open(hook_src_path, "r", encoding="utf-8") as f:
        hook_source = f.read()

    # Upload source to VM
    remote_hook_c = f"{REMOTE_BASE}/share/libconnect_hook.c"
    with sftp.open(remote_hook_c, 'w') as f:
        f.write(hook_source)
    sp(f"  Source uploaded: {remote_hook_c}")

    # Create output dirs
    q(f"mkdir -p {REMOTE_BASE}/lib {REMOTE_BASE}/bin {REMOTE_BASE}/share {REMOTE_BASE}/logs", 5)

    # Compile on VM
    ec, out, err = q(
        f"gcc -shared -fPIC -O2 -ldl -o {REMOTE_BASE}/lib/libconnect_hook.so {REMOTE_BASE}/share/libconnect_hook.c 2>&1",
        15
    )
    sp(f"  gcc exit={ec}")
    if ec != 0:
        sp(f"  STDERR: {err[:500]}")
        results["steps"]["hook_recompile"] = f"FAIL (exit={ec})"
        results["errors_found"].append(f"S3-RECOMPILE-FAIL: gcc exit={ec}: {err[:200]}")
    else:
        # Verify
        ec, out, _ = q(f"file {REMOTE_BASE}/lib/libconnect_hook.so", 10)
        sp(f"  Binary: {out.strip()[:200]}")
        ec, out, _ = q(f"nm -D {REMOTE_BASE}/lib/libconnect_hook.so | grep ' T connect'", 10)
        sp(f"  connect symbol: {'FOUND' if 'connect' in out else 'MISSING'}")

        # CRITICAL: Test LD_PRELOAD on VM-compiled .so
        ec, out, err = q(f"LD_PRELOAD={REMOTE_BASE}/lib/libconnect_hook.so /tmp/_test_ld 2>&1; echo EXIT=$?", 10)
        combined = out + err
        if "failed to map segment" in combined:
            sp(f"  >>> STILL FAILS: S3-BLOCK-001 persists even after VM recompile!")
            results["steps"]["hook_recompile"] = "RECOMPILED_BUT_STILL_INCOMPATIBLE"
            results["errors_found"].append("S3-BLOCK-001-PERSISTS: VM重编译后仍LD_PRELOAD加载失败")
        else:
            sp(f"  LD_PRELOAD test: SUCCESS! (exit info: {combined.strip()[:200]})")
            results["steps"]["hook_recompile"] = "OK"

            # Quick hook function test
            ec, out, _ = q(f"CONNECT_HOOK_DEBUG=1 LD_PRELOAD={REMOTE_BASE}/lib/libconnect_hook.so /tmp/_test_ld 2>&1", 10)
            sp(f"  Hook debug output: {out.strip()[:200]}")

# ============================================================
# PHASE 2: 尝试安装 socat
# ============================================================
sp("\n" + "="*60)
sp("PHASE 2: Install socat if possible")
sp("="*60)

ec, out, _ = q("which socat 2>/dev/null && echo HAS_SOCAT || echo NO_SOCAT", 5)
if "NO_SOCAT" in out:
    sp("  Attempting socat install...")
    # Try multiple methods
    ec, out, _ = q("sudo apt-get update -qq 2>&1 | tail -3 && sudo apt-get install -y socat 2>&1 | tail -5", 30)
    if ec != 0:
        sp(f"  apt-get failed: {out.strip()[:200]}")
        # Try pkcon
        ec, out, _ = q("pkcon install -y socat 2>&1 | tail -5", 30)
        sp(f"  pkcon: {out.strip()[:200]}")

    ec, out, _ = q("which socat 2>/dev/null && echo HAS_SOCAT || echo NO_SOCAT", 5)
    has_socat = "HAS_SOCAT" in out
else:
    has_socat = True
    sp("  socat already available")

results["diagnostics"]["socat_installed"] = has_socat

# ============================================================
# PHASE 3: 启动Echo Server
# ============================================================
sp("\n" + "="*60)
sp("PHASE 3: Start Echo Server")
sp("="*60)

q("pkill -f 'memory_echo_server' 2>/dev/null; sleep 1; echo done", 5)

echo_local = os.path.join(LOCAL_ECHO, "memory_echo_server.py")
echo_remote = f"{REMOTE_BASE}/bin/kylin-memory-echo-server"
if os.path.exists(echo_local):
    upload_file(echo_local, echo_remote)
    q(f"chmod +x {echo_remote}", 5)
else:
    sp(f"  WARN: Echo server not found at {echo_local}")

q("mkdir -p /tmp/kylin-memory-echo /tmp/.kylin-ai-runtime-unix", 5)

# Kill any process using echo.sock port
q("fuser -k /tmp/kylin-memory-echo/echo.sock 2>/dev/null; rm -f /tmp/kylin-memory-echo/echo.sock; echo done", 5)
time.sleep(1)

# Start echo server
ec, out, _ = q(
    f"nohup python3 {echo_remote} --dev > {REMOTE_BASE}/logs/echo_s3.log 2>&1 & echo PID=$!",
    10
)
sp(f"  Start: {out.strip()}")

echo_ready = False
for i in range(15):
    time.sleep(1)
    ec, out, _ = q("test -S /tmp/kylin-memory-echo/echo.sock && echo READY || echo WAITING", 5)
    if "READY" in out:
        sp(f"  Echo server READY after {i+1}s")
        echo_ready = True
        break
if not echo_ready:
    sp("  Echo server FAILED to start after 15s!")
    ec, out, _ = q(f"tail -20 {REMOTE_BASE}/logs/echo_s3.log 2>/dev/null", 10)
    sp(f"  Echo log: {out.strip()[:500]}")
results["steps"]["echo_server"] = "OK" if echo_ready else "FAIL"

ECHO_SOCK = "/tmp/kylin-memory-echo/echo.sock"
HOOK_SO = f"{REMOTE_BASE}/lib/libconnect_hook.so"
PID_DIR = "/tmp/.kylin-ai-runtime-unix/99999"
q(f"mkdir -p {PID_DIR}; touch {PID_DIR}/assistant.sock", 5)

# ============================================================
# PHASE 4: C测试客户端编译
# ============================================================
sp("\n" + "="*60)
sp("PHASE 4: Compile C test client on VM")
sp("="*60)

c_code = r"""#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr,"usage: %s <socket_path>\n",argv[0]); return 1; }
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) { perror("socket"); return 1; }
    struct sockaddr_un addr;
    memset(&addr,0,sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, argv[1], sizeof(addr.sun_path)-1);
    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        fprintf(stderr, "connect(%s): %s\n", argv[1], strerror(errno));
        return 1;
    }
    const char msg[] = "{\"method\":\"health\"}";
    uint32_t len = htonl((uint32_t)strlen(msg));
    write(fd, &len, 4);
    write(fd, msg, strlen(msg));
    uint32_t rlen;
    if (read(fd, &rlen, 4) == 4) {
        rlen = ntohl(rlen);
        char buf[4096];
        memset(buf, 0, sizeof(buf));
        int n = read(fd, buf, rlen < 4096 ? rlen : 4095);
        if (n > 0) printf("OK:%s\n", buf);
        else printf("NO_DATA\n");
    } else {
        printf("NO_HDR\n");
    }
    close(fd);
    return 0;
}
"""
with sftp.open(f"{REMOTE_BASE}/share/ctest.c", 'w') as f:
    f.write(c_code)

ec, out, err = q(f"gcc -O2 -Wall -o {REMOTE_BASE}/bin/ctest {REMOTE_BASE}/share/ctest.c 2>&1", 10)
sp(f"  Compile exit={ec}")
if ec == 0:
    ec, out, _ = q(f"file {REMOTE_BASE}/bin/ctest", 5)
    sp(f"  Binary: {out.strip()[:150]}")
    results["steps"]["c_client"] = "OK"
else:
    sp(f"  FAIL: {err[:300]}")
    results["steps"]["c_client"] = f"FAIL: {err[:200]}"

CTEST = f"{REMOTE_BASE}/bin/ctest"

# ============================================================
# PHASE 5: Hook集成测试 (C客户端 + LD_PRELOAD)
# ============================================================
sp("\n" + "="*60)
sp("PHASE 5: Hook Integration Tests (C client)")
sp("="*60)

hook_tests = [
    # (name, command, expect_exit_zero)
    ("H1_direct_echo", f"{CTEST} {ECHO_SOCK}", True),
    ("H2_hook_redirect", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock", True),
    ("H3_no_hook_bad_path", f"timeout 3 {CTEST} /tmp/nonexistent-xyz.sock 2>&1 || echo EXPECTED_FAIL", False),
    ("H4_bare_passthrough", f"LD_PRELOAD={HOOK_SO} {CTEST} {ECHO_SOCK}", True),
    ("H5_custom_match", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=mock-test CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} /tmp/mock-test-target.sock", True),
    ("H6_no_match_passthrough", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=ZZZ_NO_MATCH LD_PRELOAD={HOOK_SO} {CTEST} {ECHO_SOCK}", True),
    # Rapid reconnection tests
    ("H7_rapid_1", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1", True),
    ("H8_rapid_2", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1", True),
    ("H9_rapid_3", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1", True),
]

hook_passed = 0
hook_failed = 0
for t_name, t_cmd, expect_pass in hook_tests:
    ec, out, err = q(t_cmd, 15)
    combined = out + err
    if expect_pass:
        ok = (ec == 0)
    else:
        ok = (ec != 0)  # expect non-zero
    status = "PASS" if ok else "FAIL"
    if ok:
        hook_passed += 1
    else:
        hook_failed += 1
    detail = combined[:200].replace('\n', ' | ')
    sp(f"  {t_name}: {status} (exit={ec}) {detail}")
    results["hook_tests"].append({
        "name": t_name, "exit": ec, "status": status, "detail": detail[:300]
    })

results["hook_summary"] = f"{hook_passed}/{hook_passed+hook_failed} PASS"
sp(f"\n  Hook tests: {results['hook_summary']}")

# ============================================================
# PHASE 6: Memory协议Echo测试（6步正向 + 异常E1-E3）
# ============================================================
sp("\n" + "="*60)
sp("PHASE 6: Memory Protocol Echo Tests")
sp("="*60)

# We use socat if available, otherwise use C client with --protocol mode
if has_socat:
    sp("  Using socat for protocol tests")
    
    proto_tests = [
        ("P1_retrieve", '{"method":"memory.retrieve","params":{"query":"test_keyword","top_k":5},"jsonrpc":"2.0","id":"p1"}'),
        ("P2_store", '{"method":"memory.store","params":{"content":"test memory content","metadata":{"source":"integration_test","timestamp":"2026-08-08"}},"jsonrpc":"2.0","id":"p2"}'),
        ("P3_forget", '{"method":"memory.forget","params":{"memory_id":"test_id_xyz"},"jsonrpc":"2.0","id":"p3"}'),
        ("P4_health", '{"method":"health"}'),
        ("P5_large", '{"method":"memory.store","params":{"content":"' + 'X'*8000 + '","metadata":{}},"jsonrpc":"2.0","id":"p5"}'),
        ("P6_malformed", 'not valid json {{{'),
    ]

    proto_passed = 0
    for p_name, payload in proto_tests:
        esc = payload.replace("'", "'\\''")
        ec, out, err = q(f"echo '{esc}' | timeout 5 socat - UNIX-CONNECT:{ECHO_SOCK} 2>&1", 10)
        combined = out + err
        ok = (ec == 0)
        if ok:
            proto_passed += 1
        sp(f"  {p_name}: {'PASS' if ok else 'FAIL'} (exit={ec}) {combined[:150].strip()}")
        results["protocol_tests"].append({
            "name": p_name, "exit": ec, "status": "PASS" if ok else "FAIL",
            "output": combined[:300]
        })
else:
    sp("  socat unavailable - using C client binary for protocol verification")
    # Create a multi-protocol C test binary
    proto_c = r"""#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>

void send_recv(int fd, const char* payload) {
    uint32_t len = htonl((uint32_t)strlen(payload));
    write(fd, &len, 4);
    write(fd, payload, strlen(payload));
    uint32_t rlen;
    if (read(fd, &rlen, 4) == 4) {
        rlen = ntohl(rlen);
        char buf[8192];
        memset(buf, 0, sizeof(buf));
        int n = read(fd, buf, rlen < 8192 ? rlen : 8191);
        printf("OK:%.*s\n", n, buf);
    } else {
        printf("NO_HDR\n");
    }
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr,"usage: %s <socket>\n",argv[0]); return 1; }
    const char* tests[] = {
        "{\"method\":\"memory.retrieve\",\"params\":{\"query\":\"test\",\"top_k\":5},\"jsonrpc\":\"2.0\",\"id\":\"p1\"}",
        "{\"method\":\"memory.store\",\"params\":{\"content\":\"hi\",\"metadata\":{}},\"jsonrpc\":\"2.0\",\"id\":\"p2\"}",
        "{\"method\":\"memory.forget\",\"params\":{\"memory_id\":\"id_x\"},\"jsonrpc\":\"2.0\",\"id\":\"p3\"}",
        "{\"method\":\"health\"}",
        NULL
    };
    int all_ok = 1;
    for (int i = 0; tests[i]; i++) {
        int fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd < 0) { perror("socket"); return 1; }
        struct sockaddr_un addr;
        memset(&addr,0,sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, argv[1], sizeof(addr.sun_path)-1);
        if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            fprintf(stderr,"connect fail: %s\n", strerror(errno));
            all_ok = 0;
            break;
        }
        send_recv(fd, tests[i]);
        close(fd);
    }
    return all_ok ? 0 : 1;
}
"""
    with sftp.open(f"{REMOTE_BASE}/share/ptest.c", 'w') as f:
        f.write(proto_c)
    ec, out, err = q(f"gcc -O2 -Wall -o {REMOTE_BASE}/bin/ptest {REMOTE_BASE}/share/ptest.c 2>&1", 10)
    if ec == 0:
        sp("  Protocol test client compiled OK")
        PTEST = f"{REMOTE_BASE}/bin/ptest"
        ec, out, err = q(f"{PTEST} {ECHO_SOCK} 2>&1", 15)
        combined = out + err
        sp(f"  Protocol batch (direct): exit={ec}")
        # Show each line of output
        for line in combined.split('\n'):
            if line.strip():
                sp(f"    {line.strip()[:200]}")

        # Also test via hook redirect
        sp("  Protocol batch (via hook redirect):")
        ec, out, err = q(
            f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {PTEST} {PID_DIR}/assistant.sock 2>&1",
            15
        )
        combined = out + err
        sp(f"    exit={ec}")
        for line in combined.split('\n'):
            if line.strip():
                sp(f"    {line.strip()[:200]}")

        results["protocol_tests"].append({
            "name": "protocol_batch_direct", "exit": ec, "output": combined[:500]
        })
        results["protocol_summary"] = "via C ptest client"
    else:
        sp(f"  Protocol client compile FAIL: {err[:300]}")
        results["protocol_summary"] = "COMPILE_FAILED"

# ============================================================
# PHASE 7: 异常路径测试
# ============================================================
sp("\n" + "="*60)
sp("PHASE 7: Error Path Tests (E1-E3)")
sp("="*60)

# E1: Echo server down - connect should fail gracefully
sp("  E1: Server down test...")
q("pkill -f 'memory_echo_server' 2>/dev/null; sleep 2; echo done", 5)
time.sleep(2)

ec, out, err = q(f"timeout 5 {CTEST} /tmp/kylin-memory-echo/echo.sock 2>&1 || echo SERVER_DOWN_EXPECTED", 10)
e1_ok = (ec != 0)
sp(f"  E1_server_down: {'PASS' if e1_ok else 'FAIL'} (connect without server -> expect fail)")

# Also test via hook redirect when server is down
ec, out, err = q(
    f"CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1 || echo HOOK_DOWN_EXPECTED",
    10
)
sp(f"  E1_hook_redirect_down: {'PASS' if ec != 0 else 'FAIL'}")

results["error_tests"].append({"name": "E1_server_down", "status": "PASS" if e1_ok else "FAIL"})

# Restart echo server
q(f"nohup python3 {echo_remote} --dev > {REMOTE_BASE}/logs/echo_s3b.log 2>&1 & echo PID=$!", 10)
for i in range(10):
    time.sleep(1)
    ec, out, _ = q("test -S /tmp/kylin-memory-echo/echo.sock && echo READY || echo WAITING", 5)
    if "READY" in out:
        sp(f"  Echo restarted after {i+1}s")
        break

# E2: Rapid reconnection (连续10次)
sp("  E2: Rapid reconnect (10x)...")
e2_all_pass = True
for i in range(10):
    ec, out, err = q(
        f"CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1",
        10
    )
    if ec != 0:
        e2_all_pass = False
        sp(f"  E2_reconnect[{i}]: FAIL (exit={ec})")
        break
sp(f"  E2_rapid_reconnect: {'PASS' if e2_all_pass else 'FAIL'} (10x rapid)")
results["error_tests"].append({"name": "E2_rapid_reconnect", "status": "PASS" if e2_all_pass else "FAIL"})

# E3: Large payload (10KB+) via socat or C
sp("  E3: Large payload (10KB+)...")
big_payload = '{"method":"memory.store","params":{"content":"' + 'A'*10240 + '","metadata":{}},"jsonrpc":"2.0","id":"big"}'
if has_socat:
    ec, out, err = q(f"echo '{big_payload}' | timeout 10 socat - UNIX-CONNECT:{ECHO_SOCK} 2>&1", 15)
    e3_ok = (ec == 0)
else:
    # C large payload test
    large_c = f"""#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>
int main() {{
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un addr;
    memset(&addr,0,sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, "{ECHO_SOCK}", sizeof(addr.sun_path)-1);
    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {{ perror("connect"); return 1; }}
    const char* payload = "{big_payload}";
    uint32_t len = htonl((uint32_t)strlen(payload));
    write(fd, &len, 4);
    write(fd, payload, strlen(payload));
    uint32_t rlen;
    if (read(fd, &rlen, 4) == 4) {{
        rlen = ntohl(rlen);
        char buf[16384];
        memset(buf,0,sizeof(buf));
        int n = read(fd, buf, rlen<16384?rlen:16383);
        printf("OK:%d bytes\\n", n);
    }}
    close(fd);
    return 0;
}}
"""
    with sftp.open(f"{REMOTE_BASE}/share/ltest.c", 'w') as f:
        f.write(large_c)
    ec, out, err = q(f"gcc -O2 -o {REMOTE_BASE}/bin/ltest {REMOTE_BASE}/share/ltest.c 2>&1 && {REMOTE_BASE}/bin/ltest", 15)
    e3_ok = (ec == 0)
sp(f"  E3_large_payload: {'PASS' if e3_ok else 'FAIL'}")
results["error_tests"].append({"name": "E3_large_payload", "status": "PASS" if e3_ok else "FAIL"})

# ============================================================
# PHASE 8: strace kylin-aiassistant
# ============================================================
sp("\n" + "="*60)
sp("PHASE 8: strace kylin-aiassistant")
sp("="*60)

KI_BIN = "/home/kylin-agent/openkylin-build/kylin-aiassistant/kylin-aiassistant"
ec, out, _ = q(f"test -f {KI_BIN} && echo BIN_OK && ls -lh {KI_BIN} | awk '{{print $5}}' || echo NO_BIN", 5)
sp(f"  Binary: {out.strip()}")

ec, out, _ = q("which strace 2>/dev/null && echo HAS_STRACE || echo NO_STRACE", 5)
has_strace = "HAS_STRACE" in out
sp(f"  strace: {'available' if has_strace else 'NOT available'}")

if has_strace and "BIN_OK" in out:
    # Trace connect/socket syscalls
    ec, out, err = q(
        f"timeout 5 strace -f -e trace=socket,connect -o /tmp/strace_s3.log {KI_BIN} --help 2>&1 | head -10; echo STRACE_EXIT=$?; wc -l /tmp/strace_s3.log 2>/dev/null",
        15
    )
    sp(f"  strace result: {out.strip()[:400]}")
    try:
        sftp.get("/tmp/strace_s3.log", os.path.join(LOCAL_EVIDENCE, "strace_kylin_ai_s3.log"))
        sp("  Downloaded: strace_kylin_ai_s3.log")
        results["steps"]["strace"] = "OK"
    except Exception as e:
        sp(f"  strace download failed: {e}")
        results["steps"]["strace"] = "DOWNLOAD_FAILED"
else:
    results["steps"]["strace"] = "SKIP" if "BIN_OK" in out else "NO_BINARY"

# ============================================================
# PHASE 9: 下载证据
# ============================================================
sp("\n" + "="*60)
sp("PHASE 9: Download Evidence")
sp("="*60)

os.makedirs(LOCAL_EVIDENCE, exist_ok=True)

# Hook .so
try:
    sftp.get(HOOK_SO, os.path.join(LOCAL_EVIDENCE, "libconnect_hook.so"))
    sha = sha256_local(os.path.join(LOCAL_EVIDENCE, "libconnect_hook.so"))
    with open(os.path.join(LOCAL_EVIDENCE, "libconnect_hook.so.sha256"), "w") as f:
        f.write(f"SHA256: {sha}\nBuilt: openkylin V11 x86_64 (VM recompile)\nTime: {datetime.now(SGT).isoformat()}\n")
    sp(f"  libconnect_hook.so SHA256: {sha}")
except Exception as e:
    sp(f"  Hook download: {e}")

# Echo logs
for logname in ["echo_s3.log", "echo_s3b.log", "echo_server.log", "echo3.log", "echo_server2.log"]:
    try:
        sftp.get(f"{REMOTE_BASE}/logs/{logname}", os.path.join(LOCAL_EVIDENCE, logname))
        sp(f"  Downloaded: {logname}")
    except:
        pass

# strace
try:
    sftp.get("/tmp/strace_s3.log", os.path.join(LOCAL_EVIDENCE, "strace_kylin_ai_s3.log"))
    sp("  Downloaded: strace_kylin_ai_s3.log")
except:
    pass

# Save results JSON
results["finished_at"] = datetime.now(SGT).isoformat()
results["status"] = "COMPLETED" if hook_failed == 0 else "PARTIAL"
with open(os.path.join(LOCAL_EVIDENCE, "_stage3_comprehensive_results.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Update MANIFEST
manifest_entries = []
for fn in sorted(os.listdir(LOCAL_EVIDENCE)):
    fp = os.path.join(LOCAL_EVIDENCE, fn)
    if os.path.isfile(fp) and not fn.startswith("MANIFEST"):
        sha = sha256_local(fp)
        manifest_entries.append(f"{sha}  {fn}")
manifest_path = os.path.join(LOCAL_EVIDENCE, "MANIFEST.sha256")
existing = set()
if os.path.exists(manifest_path):
    with open(manifest_path) as mf:
        for line in mf:
            parts = line.strip().split("  ", 1)
            if len(parts) == 2:
                existing.add(parts[1])
for entry in manifest_entries:
    fn = entry.split("  ", 1)[1]
    if fn not in existing:
        with open(manifest_path, "a") as mf:
            mf.write(entry + "\n")
sp(f"  MANIFEST updated with {len(manifest_entries)} entries")

# Cleanup - stop echo server
q("pkill -f 'memory_echo_server' 2>/dev/null; echo done", 5)

sftp.close()
ssh.close()

sp(f"\n{'='*60}")
sp(f"Stage 3 Comprehensive Complete!")
sp(f"  Hook tests: {results.get('hook_summary', 'N/A')}")
sp(f"  Protocol tests: {results.get('protocol_summary', 'N/A')}")
sp(f"  Error tests: E1-E3 (see results JSON)")
sp(f"  Errors found: {len(results['errors_found'])}")
for err in results['errors_found']:
    sp(f"    - {err}")
sp(f"  Evidence: {LOCAL_EVIDENCE}")