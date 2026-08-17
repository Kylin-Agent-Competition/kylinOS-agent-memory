"""可复用 SSH 调查助手：连接麒麟 VM，批量执行命令并落盘证据。

用法:
    python _kylin_ssh.py "<任务名>" "<cmd1>|||<cmd2>|||..."
输出: 每条命令 stdout 追加写入 <任务名>.log，含命令与退出码分隔线。
"""
import os
import sys
import datetime

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


def run(c, cmd, timeout=120):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    ec = o.channel.recv_exit_status()
    return ec, out, err


def main():
    task = sys.argv[1]
    cmds = sys.argv[2].split("|||")
    logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), task + ".log")
    c = connect()
    try:
        with open(logpath, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n# 任务: {task}  @ {datetime.datetime.now().isoformat()}\n{'='*80}\n")
            for cmd in cmds:
                f.write(f"\n----- CMD: {cmd} -----\n")
                try:
                    ec, out, err = run(c, cmd)
                    f.write(f"# exit={ec}\n")
                    if out:
                        f.write(out)
                        if not out.endswith("\n"):
                            f.write("\n")
                    if err:
                        f.write(f"# STDERR:\n{err}")
                except Exception as ex:
                    f.write(f"# EXCEPTION: {ex!r}\n")
                f.flush()
    finally:
        c.close()
    print(f"[OK] {task} -> {logpath}")


if __name__ == "__main__":
    main()
