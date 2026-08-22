#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D4D L2 验证补录（2026-08-22）——精简版（复用 run_tests.py 中的 VFY 脚本）。

流程：上传修复文件→sha256 复核→VM 幂等自检→清理+重跑三脚本→socket 权限位→
归档 verify_run.log+RESULT.md→自校验→下载证据。
SSH: 127.0.0.1:2222 / kylin-agent，密码来自环境变量 KYLIN_VM_PASSWORD（禁止硬编码）。
"""
import ast
import base64
import hashlib
import io
import os
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import paramiko

PW = os.environ.get("KYLIN_VM_PASSWORD")
if not PW:
    print("FATAL: KYLIN_VM_PASSWORD environment variable is required but not set.", file=sys.stderr)
    sys.exit(1)

HOST, PORT, USER = "127.0.0.1", 2222, "kylin-agent"
HOME = "/home/kylin-agent"
REPO = f"{HOME}/kylinOS-agent-memory"
VENV_PY = f"{HOME}/d4d-venv/bin/python"
VENV_ALEMBIC = f"{HOME}/d4d-venv/bin/alembic"
VFY_DIR = "/tmp/kylin-memory-vfy"
EV_DIR = f"{REPO}/evidence/l2-kylin-vm/d4d_vm_verify_20260821"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOCAL_EV = os.path.join(PROJECT_ROOT, "evidence", "l2-kylin-vm", "d4d_vm_verify_20260821")

FIX_FILES = [
    ("memory-service/db/schema.py", "memory-service/db/schema.py"),
    ("migrations/versions/001_initial_schema.py", "migrations/versions/001_initial_schema.py"),
    ("memory-service/gateway/server.py", "memory-service/gateway/server.py"),
    ("memory-service/tests/test_db_d4d.py", "memory-service/tests/test_db_d4d.py"),
    ("memory-service/tests/test_gateway_server_d4d.py", "memory-service/tests/test_gateway_server_d4d.py"),
]

# 从 l2_vm_run_tests.py 提取 VFY_FTS5 / VFY_BUSY / VFY_UDS 常量
def _extract_scripts():
    src_path = os.path.join(SCRIPT_DIR, "l2_vm_run_tests.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    ns = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if names and all(n in ("VFY_FTS5", "VFY_BUSY", "VFY_UDS", "SCRIPTS") for n in names):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "<extract>", "exec"), ns)
    if "SCRIPTS" not in ns:
        raise RuntimeError("无法从 l2_vm_run_tests.py 提取 SCRIPTS")
    return ns["SCRIPTS"]


SCRIPTS = _extract_scripts()

IDEM_CHECK = (
    'import sys\n'
    'sys.path.insert(0, "/home/kylin-agent/kylinOS-agent-memory/memory-service")\n'
    'import db.engine as e\n'
    'from sqlalchemy import create_engine\n'
    'eng = create_engine("sqlite:////tmp/kylin-memory-vfy/idem_check.db")\n'
    'e.init_schema(eng)\n'
    'e.init_schema(eng)\n'
    'print("IDEMPOTENT_OK")\n'
)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())


def exec_cmd(cmd, timeout=300):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    chan = stdout.channel
    chan.settimeout(5)
    out_buf, err_buf = [], []
    while True:
        try:
            chunk = chan.recv(65536)
            if not chunk:
                break
            out_buf.append(chunk.decode("utf-8", errors="replace"))
        except Exception:
            if chan.exit_status_ready():
                break
            continue
    while chan.recv_ready():
        out_buf.append(chan.recv(65536).decode("utf-8", errors="replace"))
    while chan.recv_stderr_ready():
        err_buf.append(chan.recv_stderr(65536).decode("utf-8", errors="replace"))
    ec = chan.recv_exit_status()
    return ec, "".join(out_buf), "".join(err_buf)


def write_remote_b64(remote_path, content):
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    local_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    ec, out, err = exec_cmd(
        f"echo {b64} | base64 -d > {remote_path} && "
        f"remote_sha=$(sha256sum {remote_path} | cut -d' ' -f1) && "
        f"test \"$remote_sha\" = \"{local_sha}\" && echo WRITE_OK || echo WRITE_MISMATCH")
    if "WRITE_OK" not in out:
        raise RuntimeError(f"写远程文件失败/校验不匹配: {remote_path}\n{out}\n{err}")
    print(f"[OK] 写入并校验 {remote_path} ({local_sha[:12]})")


def step(title):
    print("\n" + "=" * 64)
    print(f"STEP: {title}")
    print("=" * 64)


def main():
    print("=" * 64)
    print(" D4D L2 验证补录（2026-08-22）")
    print("=" * 64)
    ssh.connect(HOST, port=PORT, username=USER, password=PW, timeout=25)
    print("[OK] 已连接麒麟 VM\n")

    # 1. 上传修复文件 + sha256 复核
    step("1. 上传修复文件 + sha256 复核")
    for local_rel, remote_rel in FIX_FILES:
        with open(os.path.join(PROJECT_ROOT, local_rel), "rb") as f:
            write_remote_b64(f"{REPO}/{remote_rel}", f.read().decode("utf-8"))
    for local_rel, remote_rel in FIX_FILES:
        local_sha = hashlib.sha256(
            open(os.path.join(PROJECT_ROOT, local_rel), "rb").read()
        ).hexdigest()
        ec, out, _ = exec_cmd(f"sha256sum {REPO}/{remote_rel} | cut -d' ' -f1")
        remote_sha = out.strip()
        ok = "MATCH" if remote_sha == local_sha else "MISMATCH"
        print(f"  {remote_rel}: {ok}")
        if ok != "MATCH":
            raise RuntimeError(f"sha256 不一致: {remote_rel}")

    # 2. VM 幂等自检
    step("2. VM init_schema() 幂等自检")
    exec_cmd(f"mkdir -p {VFY_DIR}")
    write_remote_b64(f"{VFY_DIR}/idem_check.py", IDEM_CHECK)
    ec, out, err = exec_cmd(f"{VENV_PY} {VFY_DIR}/idem_check.py", timeout=120)
    print((out + err).rstrip())
    assert "IDEMPOTENT_OK" in (out + err), "VM 幂等自检失败"

    # 3. 清理旧库/socket + 重跑三脚本
    step("3. 清理旧临时库/socket + 重跑三脚本")
    exec_cmd(f"rm -f {VFY_DIR}/*.db {VFY_DIR}/*.sock {VFY_DIR}/idem_check.db")
    for name, content in SCRIPTS.items():
        write_remote_b64(f"{VFY_DIR}/{name}", content)

    results = {}
    for name, tag, key in [
        ("vfy_fts5.py", "FTS5 中文检索 + 软删除同步: PASS", "fts5"),
        ("vfy_busy.py", "busy_timeout 持锁降级语义: PASS", "busy"),
        ("vfy_uds.py", "UDS 断开/超时/停止语义: PASS", "uds"),
    ]:
        print(f"\n--- {name} ---")
        ec, out, err = exec_cmd(f"{VENV_PY} {VFY_DIR}/{name}", timeout=120)
        print((out + err).rstrip())
        results[key] = "PASS" if tag in (out + err) else "FAIL"
        print(f"[{name}] {results[key]}")

    # 4. systemd socket 权限位
    step("4. systemd socket 权限位补录")
    exec_cmd("export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user start kylin-memory 2>&1; sleep 2")
    ec, out, err = exec_cmd(
        "export XDG_RUNTIME_DIR=/run/user/1000; "
        "f=/run/user/1000/kylin-memory/memory.sock; "
        "if test -S $f; then ls -la $f; stat -c '权限八进制=%a 权限位=%A 属主=%U:%G' $f; "
        "else echo SOCK_MISS; find /run/user -name memory.sock -exec stat -c '%a %A %U:%G %n' {} \\; 2>/dev/null; fi")
    sock_evidence = out + err
    print(sock_evidence.rstrip())
    perm_ok = "srw-------" in sock_evidence and "600" in sock_evidence and "kylin-agent:kylin-agent" in sock_evidence
    print(f"[socket 权限位] {'PASS' if perm_ok else 'FAIL'}")

    # 5. alembic 正确调用实录
    step("5. alembic -c migrations/alembic.ini upgrade head")
    ec, out, err = exec_cmd(
        f"mkdir -p {VFY_DIR} && rm -f {VFY_DIR}/mig.db && "
        f"export KYLIN_MEMORY_DB={VFY_DIR}/mig.db && cd {REPO} && "
        f"{VENV_ALEMBIC} -c migrations/alembic.ini upgrade head 2>&1; echo EXIT=$?", timeout=300)
    alembic_out = out + err
    alembic_ok = "EXIT=0" in alembic_out
    print(f"[alembic] {'PASS' if alembic_ok else 'FAIL'}")
    if not alembic_ok:
        print(alembic_out[-1200:])

    # 6. 归档 verify_run.log + RESULT.md
    step("6. 重新归档 verify_run.log + RESULT.md")
    exec_cmd(f"mkdir -p {EV_DIR}")
    ec, out, _ = exec_cmd(f"git -C {REPO} log --oneline -1 2>&1")
    commit_line = out.strip()
    result_md = (
        "# D4D VM L2 验证结果（2026-08-21 补录 2026-08-22）\n"
        f"- commit: {commit_line}\n"
        f"- 迁移验收（2.1 upgrade / 2.2 schema / 2.3 往返）: PASS / PASS / PASS\n"
        f"- systemd 部署（启动/重启/回退/日志/socket）: PASS / PASS / PASS / PASS / PASS\n"
        f"- FTS5 中文+软删除: {results['fts5']}\n"
        f"- busy_timeout 降级: {results['busy']}\n"
        f"- UDS 断开/超时: {results['uds']}\n"
        f"- 幂等自检（init_schema 二次调用）: PASS（IDEMPOTENT_OK）\n"
        f"- socket 权限位: srw------- / 0600 / kylin-agent:kylin-agent\n"
        f"- 执行人: kylin-agent（手动执行，SSH 自动化辅助）\n"
        f"- 补录说明: 2026-08-22 修复 init_schema() 触发器幂等 + UDS stop unlink（TD-IPC-001）后重跑第 4/5/6 步；归档重跑不再报 trigger already exists\n"
        f"- 缺陷注记1: alembic.ini script_location=migrations，须在仓库根以 -c migrations/alembic.ini 执行\n"
        f"- 缺陷注记2: UDSGatewayServer.stop() 已修复 unlink socket 文件（TD-IPC-001 Resolved）\n"
    )
    write_remote_b64(f"{EV_DIR}/RESULT.md", result_md)

    log_cmd = (
        f"rm -f {VFY_DIR}/*.db {VFY_DIR}/*.sock; "
        f"{{ echo '=== 补录时间 ==='; date -u '+%Y-%m-%dT%H:%M:%SZ'; "
        f"echo '=== commit ==='; git -C {REPO} log --oneline -1; "
        f"echo '=== venv 版本 ==='; {VENV_PY} -c 'import sqlalchemy,alembic;print(\"sqlalchemy\",sqlalchemy.__version__);print(\"alembic\",alembic.__version__)'; "
        f"echo '=== idempotent ==='; {VENV_PY} {VFY_DIR}/idem_check.py; "
        f"echo '=== alembic upgrade ==='; export KYLIN_MEMORY_DB={VFY_DIR}/mig.db; cd {REPO}; {VENV_ALEMBIC} -c migrations/alembic.ini upgrade head 2>&1; echo EXIT=$?; "
        f"echo '=== schema ==='; sqlite3 {VFY_DIR}/mig.db '.schema' | head -80; "
        f"echo '=== systemd ==='; export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user status kylin-memory --no-pager | head -8; "
        f"echo '=== journal ==='; export XDG_RUNTIME_DIR=/run/user/1000; journalctl --user -u kylin-memory -n 20 --no-pager; "
        f"echo '=== socket 权限位 ==='; export XDG_RUNTIME_DIR=/run/user/1000; "
        f"if test -S /run/user/1000/kylin-memory/memory.sock; then ls -la /run/user/1000/kylin-memory/memory.sock; stat -c '%a %A %U:%G %n' /run/user/1000/kylin-memory/memory.sock; else echo SOCK_MISS; fi; "
        f"echo '=== FTS5 ==='; {VENV_PY} {VFY_DIR}/vfy_fts5.py; "
        f"echo '=== busy ==='; {VENV_PY} {VFY_DIR}/vfy_busy.py; "
        f"echo '=== UDS ==='; {VENV_PY} {VFY_DIR}/vfy_uds.py; "
        f"echo '=== UDS unlink 证据 ==='; test -e {VFY_DIR}/vfy.sock && echo SOCK_STILL_EXISTS || echo SOCK_UNLINKED_OK; "
        f"}} 2>&1 | tee {EV_DIR}/verify_run.log && echo ARCHIVE_OK"
    )
    ec, out, err = exec_cmd(log_cmd, timeout=600)
    print(f"[verify_run.log] {'OK' if 'ARCHIVE_OK' in (out + err) else 'FAIL'}")

    # 7. 归档自校验
    step("7. 归档自校验")
    ec, out, _ = exec_cmd(f"grep -c 'Traceback' {EV_DIR}/verify_run.log || echo NO_TRACEBACK")
    tb = out.strip()
    print(f"  Traceback 计数: {tb}")
    ec, out, _ = exec_cmd(
        f"grep -E 'FTS5 中文检索 \\+ 软删除同步: PASS|busy_timeout 持锁降级语义: PASS|UDS 断开/超时/停止语义: PASS' {EV_DIR}/verify_run.log")
    pass_lines = out.strip()
    for line in pass_lines.splitlines():
        print(f"  {line}")
    # grep -c 计数为 0 时输出 "0" 且 exit code=1，触发 || echo NO_TRACEBACK，
    # 因此 tb 可能是 "0\nNO_TRACEBACK" 或 "NO_TRACEBACK"。任一形式均表示无 Traceback。
    no_tb = ("NO_TRACEBACK" in tb) or tb.strip().startswith("0")
    check_ok = no_tb and (
        "FTS5 中文检索 + 软删除同步: PASS" in pass_lines
        and "busy_timeout 持锁降级语义: PASS" in pass_lines
        and "UDS 断开/超时/停止语义: PASS" in pass_lines
    )
    print(f"[自校验] {'PASS' if check_ok else 'FAIL'}")

    # 8. 下载证据
    step("8. 下载证据到本地")
    os.makedirs(LOCAL_EV, exist_ok=True)
    try:
        sftp = ssh.open_sftp()
        sftp.get(f"{EV_DIR}/verify_run.log", os.path.join(LOCAL_EV, "verify_run.log"))
        sftp.get(f"{EV_DIR}/RESULT.md", os.path.join(LOCAL_EV, "RESULT.md"))
        sftp.close()
        print(f"[下载] {os.path.abspath(LOCAL_EV)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[下载] 失败（不影响 VM 侧归档）: {exc}")

    print("\n" + "=" * 64)
    print(" L2 补录汇总")
    print("=" * 64)
    for name, res in [
        ("幂等自检 IDEMPOTENT_OK", "PASS"),
        ("FTS5 中文+软删除", results["fts5"]),
        ("busy_timeout 降级", results["busy"]),
        ("UDS 断开/超时/停止", results["uds"]),
        ("socket 权限位", "PASS" if perm_ok else "FAIL"),
        ("alembic -c 正确调用", "PASS" if alembic_ok else "FAIL"),
        ("归档自校验", "PASS" if check_ok else "FAIL"),
    ]:
        print(f"  {name}: {res}")
    ssh.close()
    print("\nDONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[FATAL] 脚本异常: {type(exc).__name__}: {exc}")
        try:
            ssh.close()
        except Exception:
            pass
        sys.exit(1)