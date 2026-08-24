# D4D 麒麟 VM L2 手动验证执行手册

- **被测分支/Commit**：`feat/d4d-ipc-db-outbox` @ `ed9949c`（IPC Gateway + 数据库层 + Outbox 骨架）
- **执行环境**：银河麒麟桌面 V11（x86_64）虚拟机，用户 `kylin-agent`
- **日期**：2026-08-21
- **对照文档**：FRZ-IPC-001~007（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`）、FRZ-DB-001~005（`D4_DB_INITIAL_REQUIREMENTS_20260817.md`）、部署冻结 `D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`
- **说明**：全部命令在 VM 终端执行，**无需 sudo**。每步含"执行命令 + 预期输出 + 判定标准"。执行时建议全程 `tee` 记录：执行前先 `exec 2>&1 | tee ~/d4d_l2_verify_20260821.log`（或每步手动追加）。

---

## 第 0 步：同步代码（干净 clone）

```bash
git clone --branch feat/d4d-ipc-db-outbox https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory.git ~/kylinOS-agent-memory
cd ~/kylinOS-agent-memory && git log --oneline -1
```

**预期输出**：
```
ed9949c feat(D4D): IPC Gateway + 数据库层（SQLAlchemy/Alembic/UoW）+ Outbox/配置/日志/systemd 骨架
```

**判定**：commit 为 `ed9949c` 即 ✅；否则 STOP，先与宿主确认分支。

---

## 第 1 步：重建 venv + 装依赖

```bash
python3 -m venv ~/d4d-venv
~/d4d-venv/bin/pip install --upgrade pip
~/d4d-venv/bin/pip install -r ~/kylinOS-agent-memory/memory-service/requirements.txt
~/d4d-venv/bin/python -c "import sqlalchemy, alembic, pydantic; print('sqlalchemy', sqlalchemy.__version__); print('alembic', alembic.__version__); print('pydantic', pydantic.__version__)"
```

**预期输出**：三个版本号正常打印（sqlalchemy 2.0.x / alembic 1.13+ / pydantic 2.x）。

**判定**：无报错即 ✅。

---

## 第 2 步：Alembic 迁移验收（L2 必测项 1）

```bash
mkdir -p /tmp/kylin-memory-vfy
export KYLIN_MEMORY_DB=/tmp/kylin-memory-vfy/kylin_memory.db
cd ~/kylinOS-agent-memory/migrations

# 2.1 升级到 head
~/d4d-venv/bin/alembic upgrade head

# 2.2 导出 schema 供逐列对照
sqlite3 "$KYLIN_MEMORY_DB" ".schema" > /tmp/kylin-memory-vfy/schema_after_upgrade.sql
cat /tmp/kylin-memory-vfy/schema_after_upgrade.sql

# 2.3 往返可逆验证
~/d4d-venv/bin/alembic downgrade base
~/d4d-venv/bin/alembic upgrade head
```

**预期输出（2.2）**：
- 5 张表：`conversations` / `turns` / `memory_entries` / `outbox` / `idempotency_cache`
- 4 冻结索引 + 1 辅助索引：`idx_turns_session` / `idx_memory_user_type` / `idx_memory_deleted` / `idx_outbox_pending`(partial WHERE attempts <= 3) / `idx_idempotency_expires`
- FTS5 虚拟表 `memory_fts(content, entry_type, user_id UNINDEXED, tokenize='unicode61')`
- 4 个触发器：`memory_fts_ai` / `memory_fts_au_content` / `memory_fts_au_deleted` / `memory_fts_ad`
- `idempotency_cache` 复合主键 `(user_id, session_id, idempotency_key)`
- 约束：`entry_type IN ('preference','knowledge','tool_result','behavior')`、`confidence 0..1`、`aggregate_type IN ('turn','memory')`

**判定**：与冻结文档 FRZ-DB-001 逐列一致 ✅；2.3 无报错 ✅。若 2.3 downgrade 报错 → STOP 记录，勿继续。

---

## 第 3 步：systemd --user 部署验收（L2 必测项 2）

```bash
mkdir -p ~/.local/bin ~/.config/systemd/user

# 3.1 创建 ExecStart 入口 wrapper（unit 骨架 ExecStart=%h/.local/bin/kylin-memory-server，不改 unit 冻结文件）
printf '#!/bin/bash\nexec %s %s "$@"\n' "$HOME/d4d-venv/bin/python" "$HOME/kylinOS-agent-memory/memory-service/app.py" > ~/.local/bin/kylin-memory-server
chmod +x ~/.local/bin/kylin-memory-server

# 3.2 安装 unit 并启动
cp ~/kylinOS-agent-memory/packaging/systemd/kylin-memory.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kylin-memory

# 3.3 状态 / socket / 日志
systemctl --user status kylin-memory --no-pager
ls -la $XDG_RUNTIME_DIR/kylin-memory/memory.sock
journalctl --user -u kylin-memory -n 20 --no-pager

# 3.4 重启验证
systemctl --user restart kylin-memory
systemctl --user status kylin-memory --no-pager | head -5
journalctl --user -u kylin-memory -n 5 --no-pager

# 3.5 回退验证
systemctl --user stop kylin-memory
systemctl --user status kylin-memory --no-pager | head -3
```

**预期输出**：
- 3.3：`Active: active (running)`；socket 文件存在（`srw-------`，0600 权限）；日志含 `IPC Gateway 启动: /run/user/1000/kylin-memory/memory.sock` 与 `Memory Service 就绪`
- 3.4：重启后仍 `active (running)`
- 3.5：stop 后 `Inactive (dead)`

**判定**：启动/重启/回退/日志/socket 五项全过 ✅。注意 unit 内注释：正式发行环境 systemd 测试未执行前不得写"成品通过"——本步通过即为该 unit 的首次宿主级验证证据。

---

## 第 4 步：FTS5 中文检索 + 软删除同步（L2 必测项 3）

```bash
mkdir -p /tmp/kylin-memory-vfy
cat > /tmp/kylin-memory-vfy/vfy_fts5.py <<'PYEOF'
# -*- coding: utf-8 -*-
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
PYEOF
~/d4d-venv/bin/python /tmp/kylin-memory-vfy/vfy_fts5.py
```

**预期输出**：
```
MATCH '咖啡' -> 1（期望 >=1）
MATCH '我喜欢喝咖啡' -> 1（期望 >=1）
软删除后 MATCH '咖啡' -> 0（期望 0）
软删除后 MATCH '我喜欢喝咖啡' -> 0（期望 0）
主表软删除记录保留 -> 2（期望 2）
FTS5 中文检索 + 软删除同步: PASS
```

**判定**：末尾 `PASS` 且四行断言无 `AssertionError` ✅。VM SQLite 3.42 与 WSL 3.37 的行为差异也由此步覆盖。

---

## 第 5 步：busy_timeout 持锁注入 → 超时降级（L2 必测项 4，R-8 语义）

```bash
cat > /tmp/kylin-memory-vfy/vfy_busy.py <<'PYEOF'
# -*- coding: utf-8 -*-
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
PYEOF
~/d4d-venv/bin/python /tmp/kylin-memory-vfy/vfy_busy.py
```

**预期输出**：
```
异常类型: OperationalError
识别为锁定降级: True
耗时: 2.x s（busy_timeout=2s，期望约 2~4s 返回，非无限阻塞）
busy_timeout 持锁降级语义: PASS
```

**判定**：末尾 `PASS`、异常被识别为锁定降级、耗时落在 1.5~6s（未无限阻塞）✅。此即 R-8"到期降级而非无限阻塞"的宿主级证据。

---

## 第 6 步：UDS 断开 / 超时 / 停止语义（L2 必测项 5，FR-FB-001）

```bash
cat > /tmp/kylin-memory-vfy/vfy_uds.py <<'PYEOF'
# -*- coding: utf-8 -*-
"""L2: UDS 端到端 — health / memory.retrieve 空上下文 / store UNSUPPORTED /
未知方法 / 客户端提前断开 / TIMEOUT / 停止后拒绝新连接"""
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
server.stop()
time.sleep(0.3)
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    s.connect(SOCK)
    print("FAIL: 停止后仍可连接")
    sys.exit(1)
except OSError:
    print("6.7 停止后拒绝新连接: PASS")

print("UDS 断开/超时/停止语义: PASS")
PYEOF
~/d4d-venv/bin/python /tmp/kylin-memory-vfy/vfy_uds.py
```

**预期输出**：6.1~6.7 全部 PASS，末尾 `UDS 断开/超时/停止语义: PASS`。

**判定**：7 项断言全过 ✅。其中 6.2 验证"断开/超时 → 空上下文"的降级路径语义（主链未接入返回真实空结果），6.5/6.6/6.7 覆盖断开与超时行为。

---

## 第 7 步：证据归档

```bash
# 7.1 汇总日志（若未全程 tee，手动追加关键输出）
cd ~/kylinOS-agent-memory
mkdir -p evidence/l2-kylin-vm/d4d_vm_verify_20260821
{
  echo "=== commit ==="; git log --oneline -1
  echo "=== venv 版本 ==="; ~/d4d-venv/bin/python -c "import sqlalchemy,alembic;print(sqlalchemy.__version__,alembic.__version__)"
  echo "=== 迁移 schema ==="; cat /tmp/kylin-memory-vfy/schema_after_upgrade.sql
  echo "=== systemd ==="; systemctl --user status kylin-memory --no-pager | head -8
  echo "=== journal ==="; journalctl --user -u kylin-memory -n 20 --no-pager
  echo "=== FTS5 ==="; ~/d4d-venv/bin/python /tmp/kylin-memory-vfy/vfy_fts5.py
  echo "=== busy ==="; ~/d4d-venv/bin/python /tmp/kylin-memory-vfy/vfy_busy.py
  echo "=== UDS ==="; ~/d4d-venv/bin/python /tmp/kylin-memory-vfy/vfy_uds.py
} 2>&1 | tee evidence/l2-kylin-vm/d4d_vm_verify_20260821/verify_run.log

# 7.2 复制到共享文件夹（宿主可读取）
cp evidence/l2-kylin-vm/d4d_vm_verify_20260821/verify_run.log /run/media/sf_Kylin-Desktop-Sharedfolder/ 2>/dev/null && echo "已复制到共享文件夹" || echo "共享文件夹不可写，保留在仓库 evidence 目录"

# 7.3 登记摘要（可选）
cat > evidence/l2-kylin-vm/d4d_vm_verify_20260821/RESULT.md <<'MDEOF'
# D4D VM L2 验证结果（2026-08-21）
- commit: ed9949c
- 迁移验收：PASS/FAIL（对照 FRZ-DB-001）
- systemd 部署：PASS/FAIL（启动/重启/回退/日志/socket）
- FTS5 中文+软删除：PASS/FAIL
- busy_timeout 降级：PASS/FAIL
- UDS 断开/超时：PASS/FAIL
- 执行人：kylin-agent（手动执行）
MDEOF
echo "归档完成"
```

**判定**：`evidence/l2-kylin-vm/d4d_vm_verify_20260821/verify_run.log` 与 `RESULT.md` 生成 ✅，并把 RESULT.md 各栏按实际结果填 PASS/FAIL。

---

## 附录 A：验证清单速查

| # | 项 | 命令位置 | 通过标准 |
|---|----|---------|---------|
| 1 | DB 迁移验收 | 第 2 步 | alembic upgrade/downgrade 往返 + schema 逐列一致 |
| 2 | systemd --user 部署 | 第 3 步 | 启动/重启/回退/日志/socket 五过 |
| 3 | FTS5 中文 + 软删除 | 第 4 步 | MATCH 命中 → 软删后不再命中 |
| 4 | busy_timeout 降级 | 第 5 步 | ~2s 返回锁定异常，非无限阻塞 |
| 5 | UDS 断开/超时 | 第 6 步 | 7 项断言全过 |
| 6 | 证据归档 | 第 7 步 | verify_run.log + RESULT.md |

## 附录 B：异常处理

- 任一步报错：先把该步完整输出存到 `/tmp/kylin-memory-vfy/error_<步>.log`，然后继续后续步骤（互不依赖）；最后把 error log 一并复制到共享文件夹。
- `alembic` 命令找不到：确认第 1 步 venv 建成功，用 `~/d4d-venv/bin/alembic` 绝对路径。
- `systemctl --user` 报 `Failed to connect to bus`：先 `export XDG_RUNTIME_DIR=/run/user/1000` 再执行。
- FTS5 MATCH 断言失败：记录 VM SQLite 版本（`sqlite3 --version`，应为 3.42.0），与冻结文档 §2.4 语义对照后回报，勿自行改 schema。
