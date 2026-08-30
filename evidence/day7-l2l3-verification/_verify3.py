"""Day7E L2/L3 独立验证 —— 第三阶段：D4d 数据库层与 DB 实际 schema 核对。

已确认 VM 部署 repo HEAD=ed9949c（D4D 提交），service/ 无 Day7E
preference_*_policy.py。本阶段核对 D4d db 层是否真的实现了 Day7E 所需
current_version 指针语义，以及落盘 kylin_memory.db 的实际 schema。
"""
import os
import datetime
import json
import paramiko


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        os.environ.get("KYLIN_VM_HOST", "127.0.0.1"),
        int(os.environ.get("KYLIN_VM_PORT", "2222")),
        os.environ.get("KYLIN_VM_USER", "kylin-agent"),
        os.environ["KYLIN_VM_PASSWORD"],
        timeout=20,
    )
    return c


def run(c, cmd, timeout=60):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    ec = o.channel.recv_exit_status()
    return ec, out, err


R = "/home/kylin-agent/kylinOS-agent-memory"
DB = "/data/home/kylin-agent/.local/share/kylin-memory/kylin_memory.db"

CMDS = [
    ("db_schema_py", f"sed -n '1,200p' {R}/memory-service/db/schema.py 2>/dev/null"),
    ("db_repositories_py", f"grep -n 'current_version\\|version\\|previous_version\\|memory_entries\\|class ' {R}/memory-service/db/repositories.py 2>/dev/null | head -80"),
    ("migration_001", f"sed -n '1,120p' {R}/migrations/versions/001_initial_schema.py 2>/dev/null"),
    ("kylin_memory_db_tables", f"sqlite3 {DB} '.tables' 2>&1; echo '--- schema ---'; sqlite3 {DB} '.schema' 2>&1 | head -120"),
    ("kylin_memory_db_current_version", f"sqlite3 {DB} '.schema' 2>&1 | grep -i -E 'current_version|previous_version|version' || echo 'NO_VERSION_COLUMN_IN_DB'"),
    ("d4d_service_dir", f"ls -la {R}/memory-service/service {R}/memory-service/db {R}/memory-service/gateway {R}/memory-service/outbox 2>/dev/null"),
    ("git_branches", f"cd {R} && git branch -a 2>/dev/null | head -40; echo '--- describe ---'; git describe --always 2>/dev/null"),
]


def main():
    logdir = os.path.dirname(os.path.abspath(__file__))
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    logpath = os.path.join(logdir, "day7-l2l3-vm-db-schema.log")
    c = connect()
    results = []
    try:
        with open(logpath, "w", encoding="utf-8") as f:
            f.write(f"{'='*80}\n# Day7E L2/L3 D4d DB 层核对  @ {ts}\n{'='*80}\n")
            for name, cmd in CMDS:
                f.write(f"\n----- {name} :: {cmd} -----\n")
                try:
                    ec, out, err = run(c, cmd)
                    f.write(f"# exit={ec}\n")
                    if out:
                        f.write(out)
                        if not out.endswith("\n"):
                            f.write("\n")
                    if err:
                        f.write(f"# STDERR:\n{err}")
                    results.append({"name": name, "exit": ec})
                except Exception as ex:
                    f.write(f"# EXCEPTION: {ex!r}\n")
                    results.append({"name": name, "exit": "EXCEPTION", "error": repr(ex)})
                f.flush()
    finally:
        c.close()
    print(f"[OK] log -> {logpath}")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
