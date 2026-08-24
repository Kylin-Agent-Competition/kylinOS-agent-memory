"""Day7E L2/L3 独立验证 —— 第二阶段：聚焦已部署 repo 与持久化/QML 勘察。

上一阶段发现 VM 上运行着 /home/kylin-agent/kylinOS-agent-memory/memory-service/app.py。
本阶段聚焦核查：该部署是否含 D 轨 SQLite 版本持久化（memory_entries/current_version）
与 C 轨 QML 偏好 UI，以及 VM 上是否存在任何偏好持久化 DB。
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

CMDS = [
    ("deployed_tree", f"ls -la {R} 2>/dev/null; echo '--- memory-service ---'; ls -la {R}/memory-service 2>/dev/null; echo '--- git ---'; cd {R} 2>/dev/null && git rev-parse HEAD 2>/dev/null && git log --oneline -5 2>/dev/null"),
    ("deployed_pref_files", f"find {R} -type f \\( -name '*.py' -o -name '*.sql' -o -name '*.qml' -o -name '*.db' -o -name '*.sqlite*' \\) 2>/dev/null | grep -i -E 'preference|version|memory|sqlite|migration|repository|storage|qml' | head -100"),
    ("deployed_qml", f"find {R} /home/kylin-agent -maxdepth 6 -type f -name '*.qml' 2>/dev/null | head -60; echo '--- memclient ---'; ls -laR {R}/memory-client 2>/dev/null | head -60"),
    ("deployed_sql", f"find {R} /home/kylin-agent -maxdepth 8 -type f -name '*.sql' 2>/dev/null | head -60; echo '--- migrations ---'; ls -laR {R}/migrations 2>/dev/null | head -60"),
    ("deployed_db", f"find /home/kylin-agent /data/home/kylin-agent -maxdepth 6 -type f \\( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \\) 2>/dev/null | head -80"),
    ("current_version_ref", f"grep -rln 'current_version' {R} 2>/dev/null | head -60 || echo 'NO_CURRENT_VERSION_IN_DEPLOYED'"),
    ("memory_entries_ref", f"grep -rln 'memory_entries' {R} 2>/dev/null | head -60 || echo 'NO_MEMORY_ENTRIES_IN_DEPLOYED'"),
    ("sqlite_py_usage", f"grep -rln 'sqlite3' {R} 2>/dev/null | head -60 || echo 'NO_SQLITE3_USAGE_IN_DEPLOYED'"),
    ("service_d7e_policy", f"ls -la {R}/memory-service/service 2>/dev/null; echo '---'; ls -la {R}/memory-service/domain 2>/dev/null"),
]


def main():
    logdir = os.path.dirname(os.path.abspath(__file__))
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    logpath = os.path.join(logdir, "day7-l2l3-vm-deployed.log")
    c = connect()
    results = []
    try:
        with open(logpath, "w", encoding="utf-8") as f:
            f.write(f"{'='*80}\n# Day7E L2/L3 已部署 repo 勘察  @ {ts}\n{'='*80}\n")
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
