#!/usr/bin/env python3
"""PR#57 L2 麒麟宿主验证驱动（feat/d4-phase0-ipc-alignment @ HEAD）。

在麒麟 VirtualBox V11 虚拟机（127.0.0.1:2222，kylin-agent）上执行 L2-A1~A3 / B1~B3 / C1~C2 / D1，
收集 raw 证据到 evidence/l2-kylin-vm/pr57_l2_20260824/。

前置：KYLIN_VM_PASSWORD 环境变量已设置。
"""
import os
import sys
import json
import re
import socket
import hashlib
import subprocess
import datetime
import time
import tarfile
import io

import paramiko

# ── 连接配置（凭证从环境变量读取，禁止硬编码） ──
HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "kylin-agent")
PW = os.environ.get("KYLIN_VM_PASSWORD", "").strip()

# ── VM 侧路径 ──
REPO = "/home/kylin-agent/l2-verify-pr57"          # 干净验证工作区
PY = "/home/kylin-agent/d4d-venv/bin/python"       # 含 pytest 9.1.1 的 venv（Python 3.12）
BUILD = "/home/kylin-agent/featday9-embedding-throughput/cpp-bridge/build"  # kylin_embedding .so
DEPENDS = "/usr/lib/kylin-ai/depends"
SDK_SO = "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0"
SDK_SO_LINK = "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1"
XDG = "/run/user/1000"
KDIR = f"{XDG}/kylin-memory"
MEM_SOCK = f"{KDIR}/memory.sock"
EMB_SOCK = f"{KDIR}/embedding.sock"
A1_SOCK = f"{KDIR}/l2a1-test.sock"

# ── 本地证据目录 ──
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "pr57_l2_20260824")
os.makedirs(OUT_DIR, exist_ok=True)

ENV_PREFIX = (f"XDG_RUNTIME_DIR={XDG} "
              f"PYTHONPATH={REPO}/memory-service:{BUILD} "
              f"LD_LIBRARY_PATH={DEPENDS}")

# ── 结果记录器 ──
_records = []


def now_iso():
    return datetime.datetime.now().isoformat()


def git_head():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10, cwd=ROOT)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def git_branch():
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True, timeout=10, cwd=ROOT)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def record(item, cmd, ec, out, err, verdict=""):
    rec = {"ts": now_iso(), "item": item, "cmd": cmd, "exit": ec,
           "out": out, "err": err, "verdict": verdict}
    _records.append(rec)
    print(f"  [{item}] exit={ec} {verdict}")


def save_evidence(commit_sha, branch):
    jsonl = os.path.join(OUT_DIR, "pr57_l2_evidence.jsonl")
    with open(jsonl, "w", encoding="utf-8") as f:
        for rec in _records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    md = os.path.join(OUT_DIR, "PR57_L2_RESULTS_20260824.md")
    lines = [
        "# PR#57 L2 麒麟宿主验证结果（2026-08-24）",
        "",
        f"- **project**: kylin-os-agent-memory",
        f"- **task**: PR#57 L2 麒麟宿主验证（ALIGN-005 + envelope + 错误码语义 + 降级 + 证据脱敏）",
        f"- **branch**: {branch}",
        f"- **commit_sha**: {commit_sha}",
        f"- **environment**: Kylin V11 x86_64, 127.0.0.1:2222, kylin-agent",
        f"- **result**: 见各 item verdict",
        "",
    ]
    for rec in _records:
        lines.append(f"## {rec['item']}  {rec['verdict']}")
        lines.append(f"`{rec['cmd']}`")
        lines.append(f"```\n# exit={rec['exit']}\n{rec['out'].rstrip()}")
        if rec["err"].strip():
            lines.append(f"\n# stderr:\n{rec['err'].rstrip()}")
        lines.append("```\n")
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[OK] evidence jsonl -> {jsonl}")
    print(f"[OK] evidence md    -> {md}")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_tar():
    """本地 git archive memory-service → tar 字节。"""
    repo_local = os.path.abspath(os.path.join(ROOT, "..", ".."))
    tar_path = os.path.join(OUT_DIR, "memory-service.tar")
    subprocess.run(["git", "archive", "--format=tar", "-o", tar_path,
                    "HEAD", "memory-service"], check=True, cwd=repo_local)
    with open(tar_path, "rb") as f:
        return tar_path, f.read()


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PW, timeout=30)
    return c


def run(c, cmd, timeout=60):
    """执行远程命令；bounded 读取，防止长驻前台进程导致无限阻塞。"""
    _, o, e = c.exec_command(cmd, timeout=timeout + 10)
    o.channel.settimeout(timeout)
    e.channel.settimeout(timeout)
    try:
        out = o.read().decode(errors="replace")
    except socket.timeout:
        out = "<READ_TIMEOUT: channel did not close within %ss>" % timeout
        # 关闭通道避免泄漏
        o.channel.close()
    try:
        err = e.read().decode(errors="replace")
    except socket.timeout:
        err = ""
    try:
        ec = o.channel.recv_exit_status()
    except Exception:
        ec = -1
    return ec, out, err


def upload_bytes(c, data, remote, retries=3):
    """SFTP 上传 + 远程 SHA256 校验（零静默失败）。"""
    local_sha = hashlib.sha256(data).hexdigest()
    for i in range(retries):
        sftp = c.open_sftp()
        sftp.putfo(io.BytesIO(data), remote, confirm=True)
        sftp.close()
        _, out, _ = run(c, f"sha256sum {remote}")
        remote_sha = out.strip().split()[0] if out.strip() else ""
        if remote_sha == local_sha:
            print(f"  [upload] {remote} sha256 OK ({local_sha[:12]})")
            return True
        print(f"  [upload] retry {i+1}: local={local_sha[:12]} remote={remote_sha[:12]}")
        time.sleep(1)
    raise RuntimeError(f"upload verify failed: {remote}")


def upload_file(c, local, remote):
    with open(local, "rb") as f:
        return upload_bytes(c, f.read(), remote)


def main(only=None):
    if not PW:
        print("ERROR: KYLIN_VM_PASSWORD 未设置"); sys.exit(1)

    commit_sha = git_head()
    branch = git_branch()
    print("=" * 70)
    print("PR#57 L2 麒麟宿主验证")
    print(f"  branch={branch}")
    print(f"  HEAD={commit_sha}")
    if only:
        print(f"  filter={','.join(only)}")
    print("=" * 70)

    c = connect()
    print("[OK] SSH connected")

    # 1. 准备干净工作区
    run(c, f"rm -rf {REPO}; mkdir -p {REPO}")
    tar_path, tar_data = build_tar()
    upload_bytes(c, tar_data, f"{REPO}/memory-service.tar")
    ec, out, err = run(c, f"cd {REPO} && tar xf memory-service.tar && ls memory-service")
    print(f"[prepare] extract exit={ec}:\n{out}")
    upload_file(c, os.path.join(OUT_DIR, "uds_client.py"), f"{REPO}/uds_client.py")
    upload_file(c, os.path.join(OUT_DIR, "active_listener.py"), f"{REPO}/active_listener.py")
    # echo_client.cpp 用于 L2-B3 真实 C++ 客户端
    upload_file(c, os.path.join(ROOT, "..", "..", "os-agent-integration",
                                "echo", "echo_client.cpp"), f"{REPO}/echo_client.cpp")

    # 2. 环境身份证据
    ec, out, err = run(c, "uname -a; id; echo XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR")
    record("ENV_identity", "uname -a; id", ec, out, err)
    ec, out, err = run(c, f"ls -ld {XDG} {KDIR} 2>&1; ls -la {KDIR} 2>&1")
    record("ENV_kdir_pre", f"ls -ld {KDIR}", ec, out, err)

    # 3. 各 L2 项（单项失败不中断整体，记录异常）
    steps = [("L2-A1", l2_a1), ("L2-A2", l2_a2), ("L2-A3", l2_a3),
             ("L2-B1", l2_b1), ("L2-B2", l2_b2), ("L2-B3", l2_b3),
             ("L2-C1", l2_c1), ("L2-C2", l2_c2), ("L2-D1", l2_d1)]
    for name, fn in steps:
        if only and name not in only:
            continue
        try:
            fn(c)
        except Exception as exc:  # noqa: BLE001 - 单项失败记录，不中断
            _records.append({"ts": now_iso(), "item": name,
                             "cmd": "<driver exception>", "exit": -1,
                             "out": "", "err": str(exc), "verdict": "DRIVER_ERROR"})
            print(f"  [{name}] DRIVER_ERROR: {exc}")

    c.close()
    save_evidence(commit_sha, branch)
    print("\nDONE")


# ── 服务启停辅助 ──

def start_server(c, tag):
    """在 embedding.sock 上后台启动 embedding server，返回 (exit, log)。"""
    run(c, f"pkill -f 'embedding.server' 2>/dev/null; sleep 1; rm -f {EMB_SOCK} 2>/dev/null", timeout=15)
    cmd = (f"cd {REPO}/memory-service && nohup env XDG_RUNTIME_DIR={XDG} "
           f"PYTHONPATH={REPO}/memory-service:{BUILD} LD_LIBRARY_PATH={DEPENDS} "
           f"{PY} -m embedding.server > /tmp/embed_{tag}.log 2>&1 < /dev/null & echo PID=$!")
    ec, out, err = run(c, cmd, timeout=20)
    time.sleep(6)
    ec2, out2, err2 = run(c, f"cat /tmp/embed_{tag}.log 2>&1; echo '---'; ss -lnpx 2>/dev/null | grep embedding.sock || echo NO_LISTEN")
    return ec2, out2, err2


def stop_server(c):
    run(c, f"pkill -f 'embedding.server' 2>/dev/null; sleep 1; rm -f {EMB_SOCK} 2>/dev/null", timeout=15)


def embed_req(text):
    return json.dumps({"protocol_version": "1.0", "request_id": "req-l2",
                       "trace_id": "trc-l2", "method": "memory.embed",
                       "deadline_ms": 5000, "payload": {"text": text}},
                      ensure_ascii=False)


# ── L2-A1：active socket 拒绝 unlink ──

def l2_a1(c):
    print("\n=== L2-A1: active socket 拒绝 unlink ===")
    # 0. 清理残留 path，准备受控 active listener（仅清理受控 A1_SOCK，不触碰正式 MEM_SOCK）
    run(c, f"pkill -f 'active_listener' 2>/dev/null; rm -f {A1_SOCK} 2>/dev/null", timeout=15)
    listener = (f"nohup {PY} {REPO}/active_listener.py {A1_SOCK} "
                f"> /tmp/l2_a1_listener.log 2>&1 < /dev/null & echo PID=$!")
    ec, out, err = run(c, listener, timeout=15)
    time.sleep(2)
    ec, out, err = run(c, f"cat /tmp/l2_a1_listener.log 2>&1; echo '---'; ss -lnpx 2>/dev/null | grep l2a1-test.sock || echo NO_LISTEN")
    record("L2-A1_active_listener", f"nohup python active_listener.py {A1_SOCK}", ec, out, err)
    # 1. 尝试以 embedding.server 绑定 active 受控 socket（env 前置 + timeout 10 兜底防挂死）
    cmd = (f"cd {REPO}/memory-service && {ENV_PREFIX} timeout 10 {PY} -m embedding.server --socket {A1_SOCK}")
    ec, out, err = run(c, cmd, timeout=20)
    combined = out + err
    refused = ("active socket already listening" in combined and "refusing to unlink" in combined)
    record("L2-A1_attempt_unlink_active", cmd, ec, out, err, "PASS" if refused else "FAIL")
    # 2. 验证 active listener 仍存活、受控 socket 未被抢占
    ec, out, err = run(c, f"ss -lnpx 2>/dev/null | grep l2a1-test.sock || echo NO_A1_SOCK; echo '---'; ps -ef | grep 'active_listener' | grep -v grep")
    alive = ("active_listener" in out and "NO_A1_SOCK" not in out)
    record("L2-A1_post_listener_alive", "ss|grep l2a1-test.sock; ps|grep active_listener", ec, out, err,
           "PASS" if alive else "FAIL")
    # 3. 清理受控 listener（仅清理受控 A1_SOCK）
    run(c, f"pkill -f 'active_listener' 2>/dev/null; rm -f {A1_SOCK} 2>/dev/null", timeout=15)


# ── L2-A2：stale socket 清理后正常 bind ──

def l2_a2(c):
    print("\n=== L2-A2: stale socket 清理后正常 bind ===")
    run(c, f"rm -f {EMB_SOCK} 2>/dev/null")
    cmd = f"{PY} -c \"import socket; s=socket.socket(socket.AF_UNIX); s.bind('{EMB_SOCK}'); s.close(); print('STALE_CREATED')\""
    ec, out, err = run(c, cmd)
    record("L2-A2_create_stale", cmd, ec, out, err)
    ec, out, err = run(c, f"ls -la {EMB_SOCK} 2>&1")
    record("L2-A2_stale_exists", f"ls -la {EMB_SOCK}", ec, out, err)
    ec, out, err = start_server(c, "a2")
    record("L2-A2_start_after_stale", "nohup python -m embedding.server（默认路径）", ec, out, err)
    req = embed_req("hello world")
    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
    ec, out, err = run(c, cmd, timeout=30)
    ok = '"status": "ok"' in out
    dim = "dimension" in out
    record("L2-A2_embed_request", cmd, ec, out, err, "PASS" if (ok and dim) else "FAIL")
    stop_server(c)


def _perm_mode(out, needle):
    """从 ls -ld 输出解析含 needle 行的权限位（如 drwx------）。"""
    for line in out.splitlines():
        if needle in line and line.strip().startswith(("d", "l", "-")):
            return line.split()[0]
    return "?"


# ── L2-A3：socket 父目录 0700 收敛（现存 0755 → 启动后 0700，且不改 /tmp/家目录） ──

def l2_a3(c):
    print("\n=== L2-A3: 父目录 0700 收敛（现存 0755 → 启动后 0700）===")
    home = "/home/kylin-agent"
    # 1. 基线权限（KDIR / /tmp / /var/tmp / 家目录）
    ec, out, err = run(c, f"ls -ld {KDIR} 2>&1; echo ---TMP---; ls -ld /tmp /var/tmp 2>&1; echo ---HOME---; ls -ld {home} 2>&1")
    base_tmp = _perm_mode(out, "/var/tmp")
    base_home = _perm_mode(out, home)
    record("L2-A3_baseline_perms", f"ls -ld {KDIR} /tmp /var/tmp {home}", ec, out, err)
    # 2. 模拟遗留：确保现存目录为 0755（验证"收敛"而非"新建"）
    ec, out, err = run(c, f"chmod 0755 {KDIR} 2>&1; ls -ld {KDIR} 2>&1")
    record("L2-A3_force_legacy_0755", f"chmod 0755 {KDIR}", ec, out, err,
           "PASS" if "drwxr-xr-x" in out else "FAIL")
    # 3. 以默认路径启动 embedding server → _ensure_socket_dir 幂等收敛现存目录
    ec, out, err = start_server(c, "a3")
    record("L2-A3_server_start", "start embedding server（默认路径）", ec, out, err)
    # 4. 收敛后校验：KDIR→0700，且 /tmp、家目录不变
    ec, out, err = run(c, f"ls -ld {KDIR} 2>&1; echo ---TMP---; ls -ld /tmp /var/tmp 2>&1; echo ---HOME---; ls -ld {home} 2>&1")
    kdir_ok = _perm_mode(out, KDIR) == "drwx------"
    tmp_ok = _perm_mode(out, "/var/tmp") == base_tmp
    home_ok = _perm_mode(out, home) == base_home
    record("L2-A3_converged_0700", f"ls -ld {KDIR} /tmp /var/tmp {home}", ec, out, err,
           "PASS" if (kdir_ok and tmp_ok and home_ok) else "FAIL")
    stop_server(c)
    # 5. 新建目录 0700（回归）
    run(c, "rm -rf /tmp/l2-a3-fresh")
    cmd = (f"cd {REPO}/memory-service && {ENV_PREFIX} {PY} -c "
           f"\"from embedding.server import EmbeddingUDSServer; "
           f"s=EmbeddingUDSServer('/tmp/l2-a3-fresh/sub/embed.sock'); "
           f"s._ensure_socket_dir(); print('DIR_CREATED')\"")
    ec, out, err = run(c, cmd)
    ec2, out2, err2 = run(c, "ls -ld /tmp/l2-a3-fresh/sub 2>&1")
    record("L2-A3_fresh_dir_0700", cmd, ec2, out + out2, err + err2,
           "PASS" if "drwx------" in out2 else "FAIL")
    run(c, "rm -rf /tmp/l2-a3-fresh")


# ── L2-B1：真实 SDK 下新 envelope 断言（pytest） ──

def l2_b1(c):
    print("\n=== L2-B1: 真实 SDK 下新 envelope 断言 ===")
    cmd = (f"cd {REPO}/memory-service && KYLIN_L2=1 {ENV_PREFIX} {PY} -m pytest "
           f"tests/test_embedding_service_real.py -v")
    ec, out, err = run(c, cmd, timeout=300)
    record("L2-B1_pytest_real", cmd, ec, out, err, "PASS" if ec == 0 else "FAIL")


# ── L2-B2：错误码语义分类端到端 ──

def l2_b2(c):
    print("\n=== L2-B2: 错误码语义分类端到端 ===")
    ec, out, err = start_server(c, "b2")
    record("L2-B2_server_start", "start embedding server", ec, out, err)

    req = json.dumps({"protocol_version": "1.0", "request_id": "r1", "trace_id": "t1",
                      "method": "memory.unknown", "deadline_ms": 5000, "payload": {}})
    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
    ec, out, err = run(c, cmd, timeout=20)
    record("L2-B2_unknown_method", cmd, ec, out, err,
           "PASS" if "UNSUPPORTED_METHOD" in out else "FAIL")

    req = json.dumps({"protocol_version": "1.0", "method": "memory.embed",
                      "payload": {"text": "x"}})
    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
    ec, out, err = run(c, cmd, timeout=20)
    record("L2-B2_missing_fields", cmd, ec, out, err,
           "PASS" if "INVALID_REQUEST" in out else "FAIL")

    # typed-ID 收敛（H-2）：request_id(dict)/trace_id(int) 非 str → 错误 envelope 恒为 ""（str）
    req = json.dumps({"protocol_version": "1.0", "request_id": {"nested": 1},
                      "trace_id": 456, "method": "memory.embed",
                      "deadline_ms": 5000, "payload": {"text": "x"}})
    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
    ec, out, err = run(c, cmd, timeout=20)
    record("L2-B2_typed_id_converged", cmd, ec, out, err,
           "PASS" if ('"request_id": ""' in out and '"trace_id": ""' in out
                      and "INVALID_REQUEST" in out) else "FAIL")

    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --declared-too-large"
    ec, out, err = run(c, cmd, timeout=20)
    record("L2-B2_frame_too_large", cmd, ec, out, err,
           "PASS" if "PROTOCOL_ERROR" in out else "FAIL")

    req = json.dumps({"protocol_version": "9.9", "request_id": "r", "trace_id": "t",
                      "method": "memory.ping", "deadline_ms": 100, "payload": {}})
    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
    ec, out, err = run(c, cmd, timeout=20)
    record("L2-B2_version_mismatch", cmd, ec, out, err,
           "PASS" if "PROTOCOL_ERROR" in out else "FAIL")

    stop_server(c)


# ── L2-B3：真实客户端字段兼容性 ──

def l2_b3(c):
    print("\n=== L2-B3: 真实客户端字段兼容性 ===")
    ec, out, err = run(c, f"cd {REPO} && g++ -std=c++17 -O2 -o echo_client echo_client.cpp 2>&1 && echo COMPILE_OK || echo COMPILE_FAIL", timeout=120)
    record("L2-B3_compile_echo_client", "g++ echo_client.cpp", ec, out, err,
           "PASS" if "COMPILE_OK" in out else "FAIL")
    if "COMPILE_OK" not in out:
        return
    ec, out, err = start_server(c, "b3")
    record("L2-B3_server_start", "start embedding server", ec, out, err)
    cmd = f"{REPO}/echo_client --method memory.ping --socket {EMB_SOCK} 2>&1"
    ec, out, err = run(c, cmd, timeout=20)
    ok = '"status": "ok"' in out or '"status":"ok"' in out
    record("L2-B3_client_ping", cmd, ec, out, err, "PASS" if ok else "FAIL")
    stop_server(c)


# ── L2-C1：SDK 缺失降级 degraded_reason 保留 ──

def l2_c1(c):
    print("\n=== L2-C1: SDK 缺失降级 degraded_reason 保留 ===")
    backup = "/tmp/l2-c1-so-backup"
    run(c, f"mkdir -p {backup}")
    moved = False
    try:
        ec, out, err = run(c, f"echo '{PW}' | sudo -S -p '' mv {SDK_SO} {backup}/ 2>&1")
        record("L2-C1_move_so", f"sudo mv {SDK_SO} {backup}", ec, out, err,
               "PASS" if ec == 0 else "FAIL")
        moved = (ec == 0)
        ec, out, err = start_server(c, "c1")
        record("L2-C1_server_start_no_sdk", "start embedding server（.so 已移走）", ec, out, err)
        req = embed_req("hello")
        cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
        ec, out, err = run(c, cmd, timeout=20)
        ok = ('"status": "ok"' in out and '"degraded": true' in out
              and "degraded_reason" in out and "ERR_SDK_NOT_LOADED" in out)
        record("L2-C1_degraded_embed", cmd, ec, out, err, "PASS" if ok else "FAIL")
        stop_server(c)
    finally:
        if moved:
            ec, out, err = run(c, f"echo '{PW}' | sudo -S -p '' mv {backup}/libkysdk-coreai-embedding.so.1.0.0 {SDK_SO} 2>&1")
            record("L2-C1_restore_so", "sudo mv 还原 .so", ec, out, err,
                   "PASS" if ec == 0 else "FAIL")
            run(c, f"ls -la {SDK_SO} {SDK_SO_LINK} 2>&1")


# ── L2-C2：空输入 / 非法输入 ──

def l2_c2(c):
    print("\n=== L2-C2: 空输入 / 非法输入 ===")
    ec, out, err = start_server(c, "c2")
    record("L2-C2_server_start", "start embedding server", ec, out, err)
    req = embed_req("")
    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
    ec, out, err = run(c, cmd, timeout=20)
    record("L2-C2_empty_string", cmd, ec, out, err,
           "PASS" if '"status": "ok"' in out else "FAIL")
    req = json.dumps({"protocol_version": "1.0", "request_id": "r", "trace_id": "t",
                      "method": "memory.embed", "deadline_ms": 5000, "payload": {"text": 123}})
    cmd = f"{PY} {REPO}/uds_client.py --socket {EMB_SOCK} --request '{req}'"
    ec, out, err = run(c, cmd, timeout=20)
    record("L2-C2_non_string", cmd, ec, out, err,
           "PASS" if "INVALID_REQUEST" in out else "FAIL")
    stop_server(c)


# ── L2-D1：证据收集器脱敏 + HEAD 绑定 ──

def l2_d1(c):
    print("\n=== L2-D1: 证据收集器脱敏 + HEAD 绑定 ===")
    repo_local = os.path.abspath(os.path.join(ROOT, "..", ".."))
    collect = os.path.join(repo_local, "evidence", "phase0", "collect_phase0_evidence.py")
    proc = subprocess.run([sys.executable, collect], capture_output=True, text=True,
                          timeout=180, cwd=repo_local)
    record("L2-D1_collect_run", f"{sys.executable} {collect}",
           proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:],
           "PASS" if proc.returncode == 0 else "FAIL")
    md_path = os.path.join(repo_local, "evidence", "phase0", "phase0_vm_evidence.md")
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            md = f.read()
        redact_ok = ("key=REDACTED" in md) and not re.search(r"key=\d{4,}", md)
        head_ok = git_head() in md  # markdown 头部为 `**commit_sha**: <sha>`，校验 SHA 存在即可
        header_ok = all(k in md for k in ["project", "task", "branch", "commit_sha", "result", "limitations"])
        record("L2-D1_output_check", f"head -c 2000 {md_path}",
               0, md[:2000], "", "PASS" if (redact_ok and head_ok and header_ok) else "FAIL")


if __name__ == "__main__":
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    main(only)
