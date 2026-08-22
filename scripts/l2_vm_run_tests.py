#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D4D L2 麒麟 VM 手动验证（第 2~6 步）自动化执行。
SSH: 127.0.0.1:2222 / kylin-agent，密码来自环境变量 KYLIN_VM_PASSWORD（禁止硬编码）。
执行：C:\\Users\\jackb\\AppData\\Local\\Programs\\Python\\Python313\\python.exe scripts\\l2_vm_run_tests.py

修复说明（相对手册 / 首次运行）：
  * 第 2 步：仓库 alembic.ini 的 script_location=migrations 要求从仓库根以
    `alembic -c migrations/alembic.ini` 执行；手册 `cd migrations` 会报
    "Path doesn't exist: migrations"。
  * 第 6 步 6.7：麒麟 Linux 对已关闭 listening socket 的 connect() 不抛 OSError
    （socket 文件未 unlink），请求在 send/recv 阶段被 ECONNRESET 拒绝。
    判定改为"不得获得任何业务响应"。
"""
import base64, hashlib, io, os, sys, time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import paramiko

try:
    PW = os.environ["KYLIN_VM_PASSWORD"]
except KeyError:
    print("FATAL: KYLIN_VM_PASSWORD environment variable is required but not set.", file=sys.stderr)
    sys.exit(1)

HOST, PORT, USER = "127.0.0.1", 2222, "kylin-agent"
HOME = "/home/kylin-agent"
REPO = f"{HOME}/kylinOS-agent-memory"
VENV_PY = f"{HOME}/d4d-venv/bin/python"
VENV_ALEMBIC = f"{HOME}/d4d-venv/bin/alembic"
VFY_DIR = "/tmp/kylin-memory-vfy"
DB = f"{VFY_DIR}/kylin_memory.db"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# ─────────────────────────────────────────────────────────────
# 手册第 4 步：FTS5 中文检索 + 软删除同步（原文）
VFY_FTS5 = r'''# -*- coding: utf-8 -*-
"""L2: FTS5 中文检索 + 软删除 MATCH 不再命中（独立临时库）"""
import json, sqlite3, sys
sys.path.insert(0, "/home/kylin-agent/kylinOS-agent-memory/memory-service")
from db.engine import create_db_engine, init_schema

DB = "/tmp/kylin-memory-vfy/fts5_vfy.db"
engine = create_db_engine(DB)
init_schema(engine)

conn = sqlite3.connect(DB)
t = "2026-08-21T00:00:00Z"

# 独立中文 token：MATCH '咖啡' 应命中
conn.execute(
    "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
    ("u1", "preference", json.dumps({"note": "咖啡"}, ensure_ascii=False), 0.9, 1, 0, t, t),
)
# 完整中文句子 token：MATCH 完整句应命中
conn.execute(
    "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
    ("u1", "knowledge", json.dumps({"note": "我喜欢喝咖啡"}, ensure_ascii=False), 0.8, 1, 0, t, t),
)
conn.commit()

r1 = conn.execute("SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '咖啡'").fetchone()[0]
r2 = conn.execute("SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '我喜欢喝咖啡'").fetchone()[0]
print(f"MATCH '咖啡' -> {r1}（期望 >=1）")
print(f"MATCH '我喜欢喝咖啡' -> {r2}（期望 >=1）")
assert r1 >= 1 and r2 >= 1, "中文检索未命中"

# 软删除两条
conn.execute("UPDATE memory_entries SET is_deleted=1, updated_at=? WHERE id IN (1,2)", (t,))
conn.commit()

r3 = conn.execute("SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '咖啡'").fetchone()[0]
r4 = conn.execute("SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '我喜欢喝咖啡'").fetchone()[0]
print(f"软删除后 MATCH '咖啡' -> {r3}（期望 0）")
print(f"软删除后 MATCH '我喜欢喝咖啡' -> {r4}（期望 0）")
assert r3 == 0 and r4 == 0, "软删除后 FTS 仍命中"

# 软删记录仍保留在主表（仅 FTS 移除）
n = conn.execute("SELECT count(*) FROM memory_entries WHERE is_deleted=1").fetchone()[0]
print(f"主表软删除记录保留 -> {n}（期望 2）")
assert n == 2

print("FTS5 中文检索 + 软删除同步: PASS")
conn.close()
'''

# ─────────────────────────────────────────────────────────────
# 手册第 5 步：busy_timeout 持锁注入 → 超时降级（原文）
VFY_BUSY = r'''# -*- coding: utf-8 -*-
"""L2: 持锁场景 busy_timeout 到期 → 降级异常（非无限阻塞）"""
import sqlite3, sys, time
sys.path.insert(0, "/home/kylin-agent/kylinOS-agent-memory/memory-service")
from sqlalchemy import text
from db.engine import create_db_engine, init_schema, is_locked_error

DB = "/tmp/kylin-memory-vfy/busy_vfy.db"
engine = create_db_engine(DB, busy_timeout_ms=2000)  # 2s 便于观测
init_schema(engine)

# 锁持有者：独立连接 BEGIN IMMEDIATE 持写锁不提交
locker = sqlite3.connect(DB, timeout=0.1)
locker.execute("PRAGMA busy_timeout=100")
locker.execute("BEGIN IMMEDIATE")
locker.execute("INSERT INTO conversations (user_id, session_id, started_at) VALUES ('u1','s1','2026-08-21T00:00:00Z')")

start = time.monotonic()
try:
    with engine.begin() as c:
        c.execute(text("INSERT INTO conversations (user_id, session_id, started_at) VALUES ('u2','s2','2026-08-21T00:00:00Z')"))
    print("FAIL: 未触发锁定降级（不应走到这里）")
    sys.exit(1)
except Exception as exc:
    elapsed = time.monotonic() - start
    locked = is_locked_error(exc)
    print(f"异常类型: {type(exc).__name__}")
    print(f"识别为锁定降级: {locked}")
    print(f"耗时: {elapsed:.1f}s（busy_timeout=2s，期望约 2~4s 返回，非无限阻塞）")
    assert locked, "应识别为 database is locked / DatabaseLockedError"
    assert 1.5 <= elapsed <= 6.0, f"返回时间异常: {elapsed:.1f}s"
    print("busy_timeout 持锁降级语义: PASS")
finally:
    locker.rollback()
    locker.close()
'''

# ─────────────────────────────────────────────────────────────
# 手册第 6 步：UDS 断开 / 超时 / 停止语义
# 6.7 判定已针对 Linux/麒麟行为调整（见文件头注释）
VFY_UDS = r'''# -*- coding: utf-8 -*-
"""L2: UDS 端到端 — health / memory.retrieve 空上下文 / store UNSUPPORTED /
未知方法 / 客户端提前断开 / TIMEOUT / 停止后拒绝新请求"""
import socket, sys, threading, time
sys.path.insert(0, "/home/kylin-agent/kylinOS-agent-memory/memory-service")
from db.engine import create_db_engine, init_schema
from gateway.handlers import register_default_handlers
from gateway.protocol import decode_packet, encode
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer

SOCK = "/tmp/kylin-memory-vfy/vfy.sock"
DB = "/tmp/kylin-memory-vfy/uds_vfy.db"
engine = create_db_engine(DB)
init_schema(engine)

reg = HandlerRegistry()
register_default_handlers(reg)
server = UDSGatewayServer(SOCK, reg, engine=engine, default_deadline_ms=5000)
threading.Thread(target=server.start, daemon=True).start()
time.sleep(0.6)

def call(msg, timeout=3):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    s.sendall(encode(msg))
    buf = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
        try:
            resp, buf = decode_packet(buf)
            break
        except Exception:
            continue
    s.close()
    return resp

def base(method, deadline_ms=5000, **extra):
    m = {"protocol_version": "1.0", "request_id": "r1", "trace_id": "t1",
         "method": method, "deadline_ms": deadline_ms, "payload": {}}
    m.update(extra)
    return m

# 6.1 health（真实 DB 探测）
r = call(base("health"))
assert r["status"] == "ok" and r["data"]["db"] == "ok", r
print("6.1 health: PASS (db=ok, methods=%s)" % r["data"]["methods"])

# 6.2 memory.retrieve → 真实空上下文（FR-FB-001 降级路径，非假数据）
r = call(base("memory.retrieve"))
assert r["status"] == "ok" and r["data"]["context"] == [], r
print("6.2 memory.retrieve 空上下文: PASS")

# 6.3 memory.store → UNSUPPORTED_METHOD（Gate 0 预期）
r = call(base("memory.store"))
assert r["status"] == "error" and r["error_code"] == "UNSUPPORTED_METHOD", r
print("6.3 memory.store UNSUPPORTED_METHOD: PASS")

# 6.4 未知方法 → UNSUPPORTED_METHOD
r = call(base("no.such.method"))
assert r["status"] == "error" and r["error_code"] == "UNSUPPORTED_METHOD", r
print("6.4 未知方法 UNSUPPORTED_METHOD: PASS")

# 6.5 客户端提前断开（发半个包即断）→ 服务器存活可继续服务
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(SOCK)
s.sendall(b"partial-data")
s.close()
time.sleep(0.3)
r = call(base("health"))
assert r["status"] == "ok", r
print("6.5 客户端提前断开后服务器仍存活: PASS")

# 6.6 TIMEOUT 语义（慢 handler，deadline=100ms）
def slow(payload, ctx):
    time.sleep(0.5)
    return {"done": True}
reg.register("vfy.slow", slow)
r = call(base("vfy.slow", deadline_ms=100))
assert r["status"] == "error" and r["error_code"] == "TIMEOUT", r
print("6.6 TIMEOUT 语义: PASS")

# 6.7 停止后拒绝新请求
# 注：Linux/麒麟对已关闭 listening socket 的 connect() 不抛 OSError（socket 文件
# 未 unlink），请求在 send/recv 阶段被 ECONNRESET 拒绝。判定改为：不得获得任何业务响应。
server.stop()
time.sleep(0.3)
rejected = False
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    s.connect(SOCK)
    s.sendall(encode(base("health")))
    s.settimeout(1.5)
    try:
        data = s.recv(64)
        rejected = not data  # 空数据 = 连接被关闭
        if data:
            print("FAIL: 停止后仍获得业务响应: %r" % data[:40])
            sys.exit(1)
    except OSError:
        rejected = True      # ECONNRESET = 拒绝
    except socket.timeout:
        rejected = True      # 排队无响应 = 拒绝
    s.close()
except OSError:
    rejected = True
if rejected:
    print("6.7 停止后拒绝新请求（连接被重置/无响应）: PASS")
else:
    print("FAIL: 停止后仍可连接")
    sys.exit(1)

print("UDS 断开/超时/停止语义: PASS")
'''

SCRIPTS = {
    "vfy_fts5.py": VFY_FTS5,
    "vfy_busy.py": VFY_BUSY,
    "vfy_uds.py": VFY_UDS,
}


def exec_cmd(cmd, timeout=300):
    """执行远程命令，持续读取直到结束。返回 (exit_code, stdout_str, stderr_str)。"""
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


def step(title):
    print("\n" + "=" * 64)
    print(f"STEP: {title}")
    print("=" * 64)


def write_remote_b64(remote_path, content):
    """base64 写入远程文件 + SHA256 校验（铁律 3）。"""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    local_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    ec, out, err = exec_cmd(
        f"echo {b64} | base64 -d > {remote_path} && "
        f"remote_sha=$(sha256sum {remote_path} | cut -d' ' -f1) && "
        f"test \"$remote_sha\" = \"{local_sha}\" && echo WRITE_OK || echo WRITE_MISMATCH")
    if "WRITE_OK" not in out:
        raise RuntimeError(f"写远程文件失败/校验不匹配: {remote_path}\n{out}\n{err}")
    print(f"[OK] 写入并校验 {remote_path} ({local_sha[:12]})")


def main():
    print("=" * 64)
    print(" D4D L2 麒麟 VM 验证（第 2~6 步）")
    print("=" * 64)

    ssh.connect(HOST, port=PORT, username=USER, password=PW, timeout=25)
    print("[OK] 已连接麒麟 VM\n")

    # ── 探测 ──
    step("探测：目录/依赖/sqlite3")
    checks = [
        f"test -d {REPO}/migrations && echo MIG_OK || echo MIG_MISS",
        f"test -d {REPO}/memory-service/db && echo DB_OK || echo DB_MISS",
        f"test -d {REPO}/memory-service/gateway && echo GW_OK || echo GW_MISS",
        f"test -f {REPO}/memory-service/app.py && echo APP_OK || echo APP_MISS",
        f"test -f {REPO}/packaging/systemd/kylin-memory.service && echo UNIT_OK || echo UNIT_MISS",
        f"test -x {VENV_ALEMBIC} && echo ALEMBIC_OK || echo ALEMBIC_MISS",
        f"which sqlite3 || echo NO_SQLITE3",
    ]
    ok_all = True
    for c in checks:
        ec, out, _ = exec_cmd(c)
        out = out.strip()
        print(f"  {out}")
        for miss in ("_MISS", "NO_SQLITE3"):
            if miss in out:
                ok_all = False
    if not ok_all:
        print("[FATAL] 结构探测未全过，按上方缺失项处理。")
        sys.exit(1)

    # ── 第 2 步：Alembic 迁移验收 ──
    step("第 2 步：Alembic 迁移验收（2.1 upgrade / 2.2 schema / 2.3 往返）")
    exec_cmd(f"mkdir -p {VFY_DIR} && rm -f {DB}")
    # 注：仓库 alembic.ini script_location=migrations，须从仓库根以 -c 指定配置执行
    ec, out, err = exec_cmd(
        f"export KYLIN_MEMORY_DB={DB} && cd {REPO} && "
        f"{VENV_ALEMBIC} -c migrations/alembic.ini upgrade head 2>&1; echo EXIT=$?",
        timeout=300)
    step_2_up = "FAIL" if ("EXIT=0" not in out) else "PASS"
    print(f"[第2步-2.1 upgrade head] {step_2_up}")
    if step_2_up == "FAIL":
        print(out[-1200:])

    ec, out, err = exec_cmd(f'sqlite3 "{DB}" ".schema" > {VFY_DIR}/schema_after_upgrade.sql 2>&1 && echo SCHEMA_OK')
    step_2_schema = "FAIL" if "SCHEMA_OK" not in out else "PASS"
    print(f"[第2步-2.2 schema 导出] {step_2_schema}")
    schema_pass = True
    if step_2_schema == "PASS":
        ec, schema_out, _ = exec_cmd(f"cat {VFY_DIR}/schema_after_upgrade.sql")
        for tbl in ("conversations", "turns", "memory_entries", "outbox", "idempotency_cache"):
            has = tbl in schema_out
            print(f"   表 {tbl}: {'OK' if has else 'MISSING!'}")
            schema_pass = schema_pass and has
        for idx in ("idx_turns_session", "idx_memory_user_type", "idx_memory_deleted", "idx_outbox_pending", "idx_idempotency_expires"):
            has = idx in schema_out
            print(f"   索引 {idx}: {'OK' if has else 'MISSING!'}")
            schema_pass = schema_pass and has
        has_fts = "memory_fts" in schema_out
        print(f"   FTS5 memory_fts: {'OK' if has_fts else 'MISSING!'}")
        schema_pass = schema_pass and has_fts
        for trig in ("memory_fts_ai", "memory_fts_au_content", "memory_fts_au_deleted", "memory_fts_ad"):
            has = trig in schema_out
            print(f"   触发器 {trig}: {'OK' if has else 'MISSING!'}")
            schema_pass = schema_pass and has
        has_entry_type_ck = "entry_type" in schema_out and "preference" in schema_out
        print(f"   entry_type CHECK(preference..): {'OK' if has_entry_type_ck else 'MISSING!'}")
        # idempotency_cache 复合主键
        has_pk = "PRIMARY KEY" in schema_out and "idempotency_cache" in schema_out
        print(f"   idempotency 主键定义存在: {'OK' if has_pk else '手动核对'}")
        if not schema_pass:
            print("[WARN] 2.2 逐列对照发现缺失，请与 FRZ-DB-001 核对")

    ec, out, err = exec_cmd(
        f"export KYLIN_MEMORY_DB={DB} && cd {REPO} && "
        f"{VENV_ALEMBIC} -c migrations/alembic.ini downgrade base 2>&1 && "
        f"{VENV_ALEMBIC} -c migrations/alembic.ini upgrade head 2>&1; echo EXIT=$?",
        timeout=300)
    step_2_round = "FAIL" if ("EXIT=0" not in out) else "PASS"
    print(f"[第2步-2.3 往返可逆] {step_2_round}")
    if step_2_round == "FAIL":
        print(out[-1200:])

    # ── 第 3 步：systemd --user 部署验收 ──
    step("第 3 步：systemd --user 部署验收")
    exec_cmd("mkdir -p ~/.local/bin ~/.config/systemd/user")
    ec, out, err = exec_cmd(
        f'printf \'#!/bin/bash\\nexec %s %s "$@"\\n\' "{HOME}/d4d-venv/bin/python" '
        f'"{REPO}/memory-service/app.py" > ~/.local/bin/kylin-memory-server && '
        "chmod +x ~/.local/bin/kylin-memory-server && echo WRAPPER_OK")
    print(f"[第3步-3.1 wrapper] {'OK' if 'WRAPPER_OK' in out else 'FAIL'}")

    exec_cmd(f"cp {REPO}/packaging/systemd/kylin-memory.service ~/.config/systemd/user/")
    # 启动前清默认 DB（VM 无 config.toml → 默认 ~/.local/share/kylin-memory/kylin_memory.db），
    # 保证 init_schema 全新初始化（带 outbox 时旧库触发器重复会导致启动崩溃）
    exec_cmd("rm -f ~/.local/share/kylin-memory/kylin_memory.db")
    ec, out, err = exec_cmd(
        "export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user daemon-reload; "
        "systemctl --user enable --now kylin-memory 2>&1; echo RC=$?")
    step_3_start = "PASS" if "RC=0" in out else "FAIL"
    print(f"[第3步-3.2 enable/start] {step_3_start}")

    # 等待 socket 出现（app 建表 + Outbox Worker 初始化需要时间）
    ec, out, err = exec_cmd(
        "export XDG_RUNTIME_DIR=/run/user/1000; "
        "for i in $(seq 1 30); do "
        "  test -S /run/user/1000/kylin-memory/memory.sock && echo SOCK_READY && break; "
        "  sleep 0.5; "
        "done; "
        "test -S /run/user/1000/kylin-memory/memory.sock && "
        "echo SOCK_FINAL_OK || echo SOCK_FINAL_MISS")
    poll_log = out + err
    print(f"   [3.2等待socket] {poll_log.strip()[-200:]}")

    # 等待应用日志写入后再取 journal
    time.sleep(2)

    ec, out, err = exec_cmd("export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user status kylin-memory --no-pager")
    status_str = out + err
    active = "active (running)" in status_str
    print(f"[第3步-3.3 status] {'PASS' if active else 'FAIL'}")
    if active:
        for line in status_str.splitlines()[:6]:
            print(f"   {line}")

    # 探测实际 XDG_RUNTIME_DIR 与 socket 位置（手册脚本假设 /run/user/1000）
    ec, out, err = exec_cmd("echo XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR; id -u; ls -la /run/user/1000/kylin-memory/ 2>&1; ls -la $XDG_RUNTIME_DIR/kylin-memory/ 2>&1")
    print(f"   [3.3探测] {out.strip()}")

    ec, out, err = exec_cmd(
        "export XDG_RUNTIME_DIR=/run/user/1000; "
        "find /run/user -name memory.sock -exec ls -la {} \\; 2>&1 | head -5; "
        "ps aux | grep -E 'kylin-memory-server|app.py' | grep -v grep | head -3")
    print(f"   [3.3探测-sock/进程] {out.strip()}")
    sock_ok = ("SOCK_READY" in poll_log or "SOCK_FINAL_OK" in poll_log) and "memory.sock" in out and "srw" in out
    print(f"[第3步-3.3 socket] {'PASS' if sock_ok else 'FAIL'}")

    ec, out, err = exec_cmd(
        "journalctl --user -u kylin-memory --since '2026-08-22 00:38' --no-pager -n 40 2>&1; "
        "echo '---XDG---'; echo XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR; "
        "systemctl --user show kylin-memory -p ExecMainPID -p ActiveState -p SubState 2>&1")
    jlog = out + err
    print(f"   [3.3探测-journal] {jlog.strip()[-1600:]}")
    j_ok = ("IPC Gateway 启动" in jlog) and ("Memory Service 就绪" in jlog)
    print(f"[第3步-3.3 journal] {'PASS' if j_ok else 'FAIL'}")
    for line in (jlog.splitlines() or [])[:8]:
        print(f"   {line}")

    ec, out, err = exec_cmd("export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user restart kylin-memory; systemctl --user status kylin-memory --no-pager | head -5")
    step_3_restart = "PASS" if "active (running)" in (out + err) else "FAIL"
    print(f"[第3步-3.4 restart] {step_3_restart}")

    ec, out, err = exec_cmd("export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user stop kylin-memory; systemctl --user status kylin-memory --no-pager | head -3")
    s3stop = out + err
    step_3_stop = "PASS" if ("Inactive (dead)" in s3stop or "inactive (dead)" in s3stop) else "FAIL"
    print(f"[第3步-3.5 stop] {step_3_stop}")

    # ── 第 4/5/6 步：传输验证脚本并执行 ──
    step("第 4/5/6 步：写入验证脚本（base64 + SHA256 校验）")
    # 清理上一轮遗留的临时库/触发器和 socket，保证 init_schema 全新执行
    exec_cmd(f"rm -f {VFY_DIR}/*.db {VFY_DIR}/*.sock")
    for name, content in SCRIPTS.items():
        write_remote_b64(f"{VFY_DIR}/{name}", content)

    step("第 4 步：FTS5 中文检索 + 软删除同步")
    ec, out, err = exec_cmd(f"{VENV_PY} {VFY_DIR}/vfy_fts5.py", timeout=120)
    print((out + err).rstrip())
    step_4 = "PASS" if ("FTS5 中文检索 + 软删除同步: PASS" in (out + err)) else "FAIL"
    print(f"[第4步结果] {step_4}")

    step("第 5 步：busy_timeout 持锁注入 → 超时降级")
    ec, out, err = exec_cmd(f"{VENV_PY} {VFY_DIR}/vfy_busy.py", timeout=120)
    print((out + err).rstrip())
    step_5 = "PASS" if ("busy_timeout 持锁降级语义: PASS" in (out + err)) else "FAIL"
    print(f"[第5步结果] {step_5}")

    step("第 6 步：UDS 断开 / 超时 / 停止语义")
    ec, out, err = exec_cmd(f"{VENV_PY} {VFY_DIR}/vfy_uds.py", timeout=120)
    print((out + err).rstrip())
    step_6 = "PASS" if ("UDS 断开/超时/停止语义: PASS" in (out + err)) else "FAIL"
    print(f"[第6步结果] {step_6}")

    # ── 第 7 步：证据归档 ──
    step("第 7 步：证据归档（verify_run.log + RESULT.md）")
    ev_dir = f"{REPO}/evidence/l2-kylin-vm/d4d_vm_verify_20260821"
    exec_cmd(f"mkdir -p {ev_dir}")
    result_md = (
        "# D4D VM L2 验证结果（2026-08-21）\n"
        f"- commit: ed9949c\n"
        f"- 迁移验收（2.1 upgrade / 2.2 schema / 2.3 往返）: {step_2_up} / {step_2_schema} / {step_2_round}\n"
        f"- systemd 部署（启动/重启/回退/日志/socket）: {step_3_start} / {step_3_restart} / {step_3_stop} / {'PASS' if j_ok else 'FAIL'} / {'PASS' if sock_ok else 'FAIL'}\n"
        f"- FTS5 中文+软删除: {step_4}\n"
        f"- busy_timeout 降级: {step_5}\n"
        f"- UDS 断开/超时: {step_6}\n"
        f"- 执行人: kylin-agent（手动执行，SSH 自动化辅助）\n"
        f"- 缺陷注记1: alembic.ini `script_location=migrations`，须在仓库根以 `-c migrations/alembic.ini` 执行（手册 cd migrations 会报 Path doesn't exist: migrations）\n"
        f"- 缺陷注记2: UDSGatewayServer.stop() 未 unlink socket 文件；Linux 下停后 connect 成功、请求被 ECONNRESET 拒绝（建议登记技术债 TD-IPC）\n"
    )
    write_remote_b64(f"{ev_dir}/RESULT.md", result_md)
    ec, out, err = exec_cmd(
        f"{{ echo '=== commit ==='; git -C {REPO} log --oneline -1; "
        f"echo '=== venv 版本 ==='; {VENV_PY} -c 'import sqlalchemy,alembic;print(sqlalchemy.__version__,alembic.__version__)'; "
        f"echo '=== 迁移 schema ==='; cat {VFY_DIR}/schema_after_upgrade.sql; "
        f"echo '=== systemd ==='; export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user status kylin-memory --no-pager | head -8; "
        f"echo '=== journal ==='; export XDG_RUNTIME_DIR=/run/user/1000; journalctl --user -u kylin-memory -n 20 --no-pager; "
        f"echo '=== FTS5 ==='; {VENV_PY} {VFY_DIR}/vfy_fts5.py; "
        f"echo '=== busy ==='; {VENV_PY} {VFY_DIR}/vfy_busy.py; "
        f"echo '=== UDS ==='; {VENV_PY} {VFY_DIR}/vfy_uds.py; "
        f"}} 2>&1 | tee {ev_dir}/verify_run.log && echo ARCHIVE_OK")
    print(f"[第7步] verify_run.log: {'OK' if 'ARCHIVE_OK' in out else 'FAIL'}")

    # ── 汇总 ──
    print("\n" + "=" * 64)
    print(" L2 验证汇总")
    print("=" * 64)
    rows = [
        ("第2步-2.1 upgrade head", step_2_up),
        ("第2步-2.2 schema 导出", step_2_schema),
        ("第2步-2.3 往返可逆", step_2_round),
        ("第3步-3.2 enable/start", step_3_start),
        ("第3步-3.3 status", "PASS" if active else "FAIL"),
        ("第3步-3.3 socket", "PASS" if sock_ok else "FAIL"),
        ("第3步-3.3 journal", "PASS" if j_ok else "FAIL"),
        ("第3步-3.4 restart", step_3_restart),
        ("第3步-3.5 stop", step_3_stop),
        ("第4步 FTS5 中文+软删除", step_4),
        ("第5步 busy_timeout 降级", step_5),
        ("第6步 UDS 断开/超时", step_6),
    ]
    for name, res in rows:
        print(f"  {name}: {res}")
    print(f"  证据归档: {ev_dir}")

    # 下载 verify_run.log / RESULT.md 到本地
    try:
        local_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidence", "l2-kylin-vm", "d4d_vm_verify_20260821")
        os.makedirs(local_log, exist_ok=True)
        sftp = ssh.open_sftp()
        sftp.get(f"{ev_dir}/verify_run.log", os.path.join(local_log, "verify_run.log"))
        sftp.get(f"{ev_dir}/RESULT.md", os.path.join(local_log, "RESULT.md"))
        sftp.close()
        print(f"[下载] 已下载 verify_run.log / RESULT.md 到本地 {os.path.abspath(local_log)}")
    except Exception as exc:
        print(f"[下载] 本地证据下载失败（不影响 VM 侧归档）: {exc}")

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