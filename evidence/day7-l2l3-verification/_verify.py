"""Day7E L2/L3 独立验证 —— 麒麟 VM 真实运行态勘察脚本。

目的：按 day7-e-l2-l3-verification-checklist.md 的 L2/L3 条目，独立核实
C 轨（QML 偏好 UI）与 D 轨（SQLite 版本持久化）在麒麟 VM 的真实实现/部署状态。

原则：零冒充。本脚本只采集真实命令 + 退出码 + stdout/stderr，不构造任何
"通过" 结论。C/D 轨若未实现，则如实记录 NOT_IMPLEMENTED，绝不伪造 HOST_VERIFIED。
"""
import os
import sys
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


def run(c, cmd, timeout=90):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    ec = o.channel.recv_exit_status()
    return ec, out, err


CMDS = [
    # ── 系统基线 ──
    ("sysinfo", "uname -m; cat /etc/.kyinfo 2>/dev/null | head -20; echo '---'; id"),
    # ── 是否有 memory-service 部署 / 运行 ──
    ("service_memory", "systemctl list-units --all --no-pager 2>/dev/null | grep -i -E 'memory|kylin-memory|echo' || echo 'NO_MEMORY_UNIT'"),
    ("process_memory", "ps aux | grep -i -E 'memory[-_]service|memory[-_]echo|preference' | grep -v grep || echo 'NO_MEMORY_PROCESS'"),
    # ── 是否有 SQLite 持久化 / current_version / memory_entries ──
    ("sqlite_bin", "which sqlite3 || echo 'NO_SQLITE3_BIN'"),
    ("sqlite_files", "find / -type f \\( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \\) 2>/dev/null | grep -i -E 'memory|preference|kylin' | head -50 || echo 'NO_MATCH_DB'"),
    ("db_memory_entries", "find / -type f \\( -name '*.db' -o -name '*.sqlite*' \\) 2>/dev/null -print0 | head -200"),
    # ── 是否有 QML 偏好 UI / memory-client ──
    ("qml_files", "find / -type f -name '*.qml' 2>/dev/null | grep -i -E 'preference|memory' | head -50 || echo 'NO_QML_MATCH'"),
    ("qml_all_pref", "find / -type f -iname '*preference*' 2>/dev/null | head -80 || echo 'NO_PREFERENCE_FILE'"),
    # ── 是否有 current_version 相关代码/表 ──
    ("current_version", "grep -rl 'current_version' /opt /usr/share/kylin-ai /home/kylin-agent 2>/dev/null | head -50 || echo 'NO_CURRENT_VERSION_REF'"),
    ("memory_entries_table", "grep -rl 'memory_entries' /opt /home/kylin-agent 2>/dev/null | head -50 || echo 'NO_MEMORY_ENTRIES_REF'"),
    # ── 是否有仓库代码被同步到 VM ──
    ("repo_sync", "ls -la /home/kylin-agent/ 2>/dev/null | head -50; echo '---'; find /home/kylin-agent -maxdepth 3 -type d 2>/dev/null | head -80"),
]


def main():
    logdir = os.path.dirname(os.path.abspath(__file__))
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    logpath = os.path.join(logdir, "day7-l2l3-vm-verification.log")
    c = connect()
    results = []
    try:
        with open(logpath, "w", encoding="utf-8") as f:
            f.write(f"{'='*80}\n# Day7E L2/L3 独立验证  @ {ts}\n{'='*80}\n")
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
