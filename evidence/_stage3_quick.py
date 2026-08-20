#!/usr/bin/env python3
"""阶段3精简快速测试: Hook集成 + 协议Echo + 异常路径 + strace (无sudo/apt)"""
import os, sys, json, hashlib, time
from datetime import datetime, timezone, timedelta

SGT = timezone(timedelta(hours=8))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VM_HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
VM_PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
VM_USER = os.environ.get("KYLIN_VM_USER", "kylin-agent")
VM_PASS = os.environ.get("KYLIN_VM_PASSWORD", "")
REMOTE_BASE = "/home/kylin-agent/kylin-memory-echo"
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
    print("ERROR: paramiko"); sys.exit(1)

print(f"[{datetime.now(SGT):%H:%M:%S}] Stage3 Quick Test Started")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASS, timeout=60, banner_timeout=60)
sftp = ssh.open_sftp()
print("  Connected OK")

def q(cmd, t=15):
    """Execute command, avoid nohup to prevent channel hang"""
    _, o, e = ssh.exec_command(cmd, timeout=t)
    ec = o.channel.recv_exit_status()
    return ec, o.read().decode("utf-8", errors="replace"), e.read().decode("utf-8", errors="replace")

def sp(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))

results = {"stage": "3_quick", "started_at": datetime.now(SGT).isoformat(),
           "steps": {}, "diagnostics": {}, "hook_tests": [],
           "protocol_tests": [], "error_tests": [], "errors_found": []}

ECHO_SOCK = "/tmp/kylin-memory-echo/echo.sock"
HOOK_SO = f"{REMOTE_BASE}/lib/libconnect_hook.so"
ECHO_BIN = f"{REMOTE_BASE}/bin/kylin-memory-echo-server"
PID_DIR = "/tmp/.kylin-ai-runtime-unix/99999"

# ============================================================
# STEP 0: Quick VM state check
# ============================================================
sp("\n=== STEP 0: Quick VM check ===")

# Check hook .so + LD_PRELOAD
ec, out, _ = q(f"file {HOOK_SO} 2>&1 && echo --- && LD_PRELOAD={HOOK_SO} echo HOOK_LOAD_OK 2>&1 || echo HOOK_LOAD_FAIL", 10)
sp(f"  Hook check: {out.strip()[:200]}")
if "HOOK_LOAD_OK" in out:
    results["diagnostics"]["hook_ld_preload"] = "PASS"
elif "HOOK_LOAD_FAIL" in out:
    results["diagnostics"]["hook_ld_preload"] = "FAIL"
    results["errors_found"].append("S3-BLOCK-001: LD_PRELOAD still fails on existing hook .so")

# Check strace
ec, out, _ = q("which strace 2>/dev/null && echo HAS || echo NO", 5)
has_strace = "HAS" in out
results["diagnostics"]["strace"] = "avail" if has_strace else "missing"

# Check kylin-aiassistant binary
KI_BIN = "/home/kylin-agent/openkylin-build/kylin-aiassistant/kylin-aiassistant"
ec, out, _ = q(f"test -f {KI_BIN} && echo BIN_OK && ls -lh {KI_BIN} | awk '{{print $5}}' || echo NO_BIN", 5)
has_ki = "BIN_OK" in out
sp(f"  kylin-aiassistant: {'OK' if has_ki else 'MISSING'}")

# ============================================================
# STEP 1: Start Echo Server
# ============================================================
sp("\n=== STEP 1: Start Echo Server ===")

# Kill old, clean socket
q("pkill -f 'memory_echo_server' 2>/dev/null; fuser -k /tmp/kylin-memory-echo/echo.sock 2>/dev/null; rm -f /tmp/kylin-memory-echo/echo.sock; sleep 1; echo DONE", 8)
time.sleep(1)

q("mkdir -p /tmp/kylin-memory-echo /tmp/.kylin-ai-runtime-unix/99999", 3)

ec, out, _ = q(f"nohup python3 {ECHO_BIN} --dev > {REMOTE_BASE}/logs/echo_q.log 2>&1 & echo PID=$!", 8)
sp(f"  Start: {out.strip()}")

for i in range(15):
    time.sleep(1)
    ec, out, _ = q("test -S /tmp/kylin-memory-echo/echo.sock && echo READY || echo WAITING", 5)
    if "READY" in out:
        sp(f"  Echo READY ({i+1}s)")
        results["steps"]["echo_server"] = "OK"
        break
else:
    sp("  Echo FAILED after 15s!")
    results["steps"]["echo_server"] = "FAIL"
    # Try to see error
    ec, out, _ = q("tail -5 /home/kylin-agent/kylin-memory-echo/logs/echo_q.log 2>/dev/null", 5)
    sp(f"  Log: {out.strip()[:200]}")

q(f"touch {PID_DIR}/assistant.sock", 3)

# ============================================================
# STEP 2: C test client compilation
# ============================================================
sp("\n=== STEP 2: C test client ===")

c_code = """#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>
int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr,"usage: %s <socket>\\n",argv[0]); return 1; }
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) { perror("socket"); return 1; }
    struct sockaddr_un addr; memset(&addr,0,sizeof(addr));
    addr.sun_family = AF_UNIX; strncpy(addr.sun_path, argv[1], sizeof(addr.sun_path)-1);
    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        fprintf(stderr, "connect fail: %s\\n", strerror(errno)); return 1;
    }
    const char msg[] = "{\\"method\\":\\"health\\"}";
    uint32_t len = htonl((uint32_t)strlen(msg));
    write(fd, &len, 4); write(fd, msg, strlen(msg));
    uint32_t rlen;
    if (read(fd, &rlen, 4) == 4) {
        rlen = ntohl(rlen); char buf[4096]; memset(buf,0,sizeof(buf));
        int n = read(fd, buf, rlen<4096?rlen:4095);
        if (n > 0) printf("OK:%s\\n", buf); else printf("NO_DATA\\n");
    } else { printf("NO_HDR\\n"); }
    close(fd); return 0;
}
"""
with sftp.open(f"{REMOTE_BASE}/share/ctest.c", 'w') as f:
    f.write(c_code)

ec, out, err = q(f"gcc -O2 -Wall -o {REMOTE_BASE}/bin/ctest {REMOTE_BASE}/share/ctest.c 2>&1", 10)
if ec == 0:
    sp("  C client compiled OK")
else:
    sp(f"  C client FAIL: {err[:200]}")
    results["errors_found"].append(f"C-CLIENT-COMPILE-FAIL: {err[:100]}")
    # fallback: use existing ctest binary
    ec, out, _ = q(f"test -f {REMOTE_BASE}/bin/ctest && echo EXISTS || echo NOT", 5)
    if "NOT" in out:
        # Use simple Python client as last resort
        sp("  Falling back to Python client...")
        py_code = """#!/usr/bin/env python3
import socket, struct, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    s.connect(sys.argv[1])
    msg = b'{"method":"health"}'
    s.send(struct.pack('>I', len(msg)) + msg)
    hdr = s.recv(4)
    if len(hdr) == 4:
        rlen = struct.unpack('>I', hdr)[0]
        resp = s.recv(rlen)
        print(resp.decode())
    s.close()
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
        with sftp.open(f"{REMOTE_BASE}/bin/ctest.py", 'w') as f:
            f.write(py_code)
        q(f"chmod +x {REMOTE_BASE}/bin/ctest.py", 3)
        CTEST = f"python3 {REMOTE_BASE}/bin/ctest.py"
        results["steps"]["c_client"] = "python_fallback"
    else:
        CTEST = f"{REMOTE_BASE}/bin/ctest"
        results["steps"]["c_client"] = "reuse_existing"
else:
    CTEST = f"{REMOTE_BASE}/bin/ctest"
    results["steps"]["c_client"] = "OK"

# ============================================================
# STEP 3: Hook Integration Tests (9 tests)
# ============================================================
sp("\n=== STEP 3: Hook Integration Tests ===")

hook_tests = [
    ("H1_direct", f"{CTEST} {ECHO_SOCK}", True),
    ("H2_redirect", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock", True),
    ("H3_bad_path", f"timeout 3 sh -c '{CTEST} /tmp/nonexist-xyz.sock || true'", False),
    ("H4_bare_passthrough", f"LD_PRELOAD={HOOK_SO} {CTEST} {ECHO_SOCK}", True),
    ("H5_custom_match", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=mock-target CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} /tmp/mock-target-test.sock", True),
    ("H6_no_match_passthrough", f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=ZZZ_NO_MATCH LD_PRELOAD={HOOK_SO} {CTEST} {ECHO_SOCK}", True),
    ("H7_rapid1", f"CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1", True),
    ("H8_rapid2", f"CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1", True),
    ("H9_rapid3", f"CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1", True),
]

passed = 0; failed = 0
for name, cmd, expect_pass in hook_tests:
    ec, out, err = q(cmd, 10)
    if expect_pass:
        ok = (ec == 0)
    else:
        ok = (ec != 0)
    status = "PASS" if ok else "FAIL"
    if ok: passed += 1
    else: failed += 1
    detail = (out + err)[:200].replace('\n', ' | ')
    sp(f"  {name}: {status} (exit={ec}) {detail}")
    results["hook_tests"].append({"name": name, "exit": ec, "status": status, "detail": detail[:300]})

results["hook_summary"] = f"{passed}/{passed+failed} PASS"
sp(f"\n  Hook: {results['hook_summary']}")

# ============================================================
# STEP 4: Memory Protocol Echo Tests (6协议 + 异常E1-E3)
# ============================================================
sp("\n=== STEP 4: Protocol Echo + Error Tests ===")

# Create multi-protocol C test binary
proto_c = """#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>
void send_recv(int fd, const char* p) {
    uint32_t len = htonl((uint32_t)strlen(p));
    write(fd, &len, 4); write(fd, p, strlen(p));
    uint32_t rlen;
    if (read(fd, &rlen, 4) == 4) {
        rlen = ntohl(rlen); char buf[8192]; memset(buf,0,sizeof(buf));
        int n = read(fd, buf, rlen<8192?rlen:8191);
        printf("ECHO:%.*s\\n", n, buf);
    } else { printf("NO_HDR\\n"); }
}
int main(int argc, char** argv) {
    if (argc < 2) return 1;
    const char* tests[] = {
        "{\\"method\\":\\"memory.retrieve\\",\\"params\\":{\\"query\\":\\"test_q\\",\\"top_k\\":5},\\"jsonrpc\\":\\"2.0\\",\\"id\\":\\"p1\\"}",
        "{\\"method\\":\\"memory.store\\",\\"params\\":{\\"content\\":\\"integration test\\",\\"metadata\\":{\\"source\\":\\"s3_test\\"}},\\"jsonrpc\\":\\"2.0\\",\\"id\\":\\"p2\\"}",
        "{\\"method\\":\\"memory.forget\\",\\"params\\":{\\"memory_id\\":\\"test_id_123\\"},\\"jsonrpc\\":\\"2.0\\",\\"id\\":\\"p3\\"}",
        "{\\"method\\":\\"health\\"}",
        NULL
    };
    for (int i = 0; tests[i]; i++) {
        int fd = socket(AF_UNIX, SOCK_STREAM, 0);
        struct sockaddr_un addr; memset(&addr,0,sizeof(addr));
        addr.sun_family = AF_UNIX; strncpy(addr.sun_path, argv[1], sizeof(addr.sun_path)-1);
        if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            fprintf(stderr,"connect fail\\n"); return 1;
        }
        send_recv(fd, tests[i]); close(fd);
    }
    return 0;
}
"""
with sftp.open(f"{REMOTE_BASE}/share/ptest.c", 'w') as f:
    f.write(proto_c)

ec, out, err = q(f"gcc -O2 -Wall -o {REMOTE_BASE}/bin/ptest {REMOTE_BASE}/share/ptest.c 2>&1", 10)
if ec == 0:
    PTEST = f"{REMOTE_BASE}/bin/ptest"
    sp("  Protocol C client compiled OK")

    # Test 1: Direct protocol test
    sp("  P1-P4: Direct protocol batch...")
    ec, out, err = q(f"{PTEST} {ECHO_SOCK} 2>&1", 10)
    proto_ok = (ec == 0)
    sp(f"    {'PASS' if proto_ok else 'FAIL'} (exit={ec})")
    for line in (out + err).split('\n'):
        if line.strip():
            sp(f"    {line.strip()[:200]}")
    results["protocol_tests"].append({"name": "protocol_batch_direct", "exit": ec,
        "status": "PASS" if proto_ok else "FAIL"})

    # Test 2: Protocol via hook redirect
    sp("  P1-P4: Via hook redirect...")
    ec, out, err = q(
        f"CONNECT_HOOK_DEBUG=1 CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {PTEST} {PID_DIR}/assistant.sock 2>&1",
        10
    )
    hook_proto_ok = (ec == 0)
    sp(f"    {'PASS' if hook_proto_ok else 'FAIL'} (exit={ec})")
    for line in (out + err).split('\n'):
        if line.strip():
            sp(f"    {line.strip()[:200]}")
    results["protocol_tests"].append({"name": "protocol_batch_hook", "exit": ec,
        "status": "PASS" if hook_proto_ok else "FAIL"})
    results["protocol_summary"] = f"direct={'PASS' if proto_ok else 'FAIL'}, hook={'PASS' if hook_proto_ok else 'FAIL'}"
else:
    sp(f"  Protocol client compile FAIL: {err[:200]}")
    results["protocol_summary"] = "COMPILE_FAILED"

# ============================================================
# STEP 5: Error Path Tests (E1, E2, E3)
# ============================================================
sp("\n=== STEP 5: Error Path Tests ===")

# E1: Server down
sp("  E1: Server down...")
q("pkill -f 'memory_echo_server' 2>/dev/null; sleep 2; echo done", 6)
time.sleep(2)

ec, out, err = q(f"timeout 5 {CTEST} {ECHO_SOCK} 2>&1 || echo E1_EXPECTED_FAIL", 10)
e1_ok = (ec != 0)
sp(f"  E1: {'PASS' if e1_ok else 'FAIL'} (no server, expect fail)")

ec, out, err = q(
    f"CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1 || echo E1_HOOK_FAIL_EXPECTED",
    10
)
sp(f"  E1_hook: {'PASS' if ec != 0 else 'FAIL'}")
results["error_tests"].append({"name": "E1_server_down", "status": "PASS" if e1_ok else "FAIL"})

# Restart echo
q(f"nohup python3 {ECHO_BIN} --dev > {REMOTE_BASE}/logs/echo_q2.log 2>&1 & echo PID=$!", 8)
for i in range(10):
    time.sleep(1)
    ec, out, _ = q("test -S /tmp/kylin-memory-echo/echo.sock && echo READY || echo WAITING", 5)
    if "READY" in out:
        sp(f"  Echo restarted ({i+1}s)")
        break

# E2: Rapid reconnect 10x
sp("  E2: Rapid reconnect 10x...")
e2_ok = True
for i in range(10):
    ec, out, err = q(
        f"CONNECT_HOOK_MATCH=kylin-ai-runtime-unix CONNECT_HOOK_REDIRECT={ECHO_SOCK} LD_PRELOAD={HOOK_SO} {CTEST} {PID_DIR}/assistant.sock 2>&1",
        8
    )
    if ec != 0:
        sp(f"  E2[{i}]: FAIL (exit={ec})")
        e2_ok = False
        break
sp(f"  E2: {'PASS' if e2_ok else 'FAIL'}")
results["error_tests"].append({"name": "E2_rapid_reconnect", "status": "PASS" if e2_ok else "FAIL"})

# E3: Large payload
sp("  E3: Large payload (10KB+)...")
# Use echo via socat approach if available (no socat on VM)
# Use Python socket approach
large_test = """import socket, struct, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('""" + ECHO_SOCK + """')
pld = '{"method":"memory.store","params":{"content":"' + 'A'*10240 + '","metadata":{}}}'
b = pld.encode()
s.send(struct.pack('>I', len(b)) + b)
hdr = s.recv(4)
if len(hdr) == 4:
    rlen = struct.unpack('>I', hdr)[0]
    resp = s.recv(rlen).decode()
    print('OK:' + resp[:100])
else:
    print('NO_HDR')
s.close()
"""
with sftp.open(f"{REMOTE_BASE}/share/ltest.py", 'w') as f:
    f.write(large_test)
ec, out, err = q(f"python3 {REMOTE_BASE}/share/ltest.py 2>&1", 10)
e3_ok = (ec == 0)
sp(f"  E3: {'PASS' if e3_ok else 'FAIL'} {out.strip()[:150]}")
results["error_tests"].append({"name": "E3_large_payload", "status": "PASS" if e3_ok else "FAIL"})

# ============================================================
# STEP 6: strace kylin-aiassistant
# ============================================================
sp("\n=== STEP 6: strace kylin-aiassistant ===")

if has_strace and has_ki:
    ec, out, err = q(
        f"timeout 5 strace -f -e trace=socket,connect -o /tmp/strace_s3q.log {KI_BIN} --help 2>&1 | head -5; wc -l /tmp/strace_s3q.log 2>/dev/null || echo NO_LOG",
        15
    )
    sp(f"  strace: {out.strip()[:300]}")
    try:
        sftp.get("/tmp/strace_s3q.log", os.path.join(LOCAL_EVIDENCE, "strace_kylin_ai_s3.log"))
        sp("  Downloaded: strace_kylin_ai_s3.log")
        results["steps"]["strace"] = "OK"
    except Exception as e:
        sp(f"  strace dl fail: {e}")
        results["steps"]["strace"] = f"DOWNLOAD_FAILED: {e}"
else:
    results["steps"]["strace"] = "SKIP" if has_ki else "NO_BINARY"

# ============================================================
# STEP 7: Evidence download & report
# ============================================================
sp("\n=== STEP 7: Evidence Download ===")

os.makedirs(LOCAL_EVIDENCE, exist_ok=True)

# Hook .so
try:
    sftp.get(HOOK_SO, os.path.join(LOCAL_EVIDENCE, "libconnect_hook.so"))
    sha = sha256_local(os.path.join(LOCAL_EVIDENCE, "libconnect_hook.so"))
    with open(os.path.join(LOCAL_EVIDENCE, "libconnect_hook.so.sha256"), "w") as f:
        f.write(f"SHA256: {sha}\nBuilt: openkylin V11 x86_64\nTest: Stage3 Quick {datetime.now(SGT).isoformat()}\n")
    sp(f"  Hook .so SHA256: {sha}")
except Exception as e:
    sp(f"  Hook dl: {e}")

# Echo logs
for logname in ["echo_q.log", "echo_q2.log"]:
    try:
        sftp.get(f"{REMOTE_BASE}/logs/{logname}", os.path.join(LOCAL_EVIDENCE, logname))
        sp(f"  {logname}")
    except:
        pass

# strace
try:
    sftp.get("/tmp/strace_s3q.log", os.path.join(LOCAL_EVIDENCE, "strace_kylin_ai_s3.log"))
    sp("  strace_kylin_ai_s3.log")
except:
    pass

results["finished_at"] = datetime.now(SGT).isoformat()
results["status"] = "COMPLETED" if failed == 0 else f"PARTIAL ({passed}/{passed+failed} hook pass)"
out_path = os.path.join(LOCAL_EVIDENCE, "_stage3_quick_results.json")
with open(out_path, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Update MANIFEST
manifest_entries = []
for fn in sorted(os.listdir(LOCAL_EVIDENCE)):
    fp = os.path.join(LOCAL_EVIDENCE, fn)
    if os.path.isfile(fp) and not fn.startswith("MANIFEST"):
        sha = sha256_local(fp)
        manifest_entries.append(f"{sha}  {fn}")
mpath = os.path.join(LOCAL_EVIDENCE, "MANIFEST.sha256")
with open(mpath, "a" if os.path.exists(mpath) else "w") as mf:
    mf.write("\n".join(manifest_entries) + "\n")
sp(f"  MANIFEST: {len(manifest_entries)} entries")

# Cleanup
q("pkill -f 'memory_echo_server' 2>/dev/null; echo done", 3)

sftp.close()
ssh.close()

sp(f"\n{'='*60}")
sp(f"Stage 3 Quick Complete!")
sp(f"  Hook: {results['hook_summary']}")
sp(f"  Protocol: {results.get('protocol_summary', 'N/A')}")
sp(f"  Errors: {len(results['errors_found'])}")
for e in results['errors_found']:
    sp(f"    - {e}")
sp(f"  Results: {out_path}")