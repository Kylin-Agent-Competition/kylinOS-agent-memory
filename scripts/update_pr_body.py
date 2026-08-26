#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新 PR#52 body：65 passed -> 72 passed（麒麟 VM 实测 L1 计数）。

读取当前 body，做精确字符串替换，落盘 UTF-8 文件供 gh pr edit --body-file 使用。
执行：C:\\Users\\jackb\\AppData\\Local\\Programs\\Python\\Python313\\python.exe scripts\\update_pr_body.py
"""
import io, json, subprocess, sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO = "Kylin-Agent-Competition/kylinOS-agent-memory"
OUT = r"e:\Kylin-memory-dev\UDS-Kylin-D4-memory-service\scripts\pr52_body_new.txt"


def gh(*args):
    r = subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"[FATAL] gh {' '.join(args)} 失败: {r.stderr}")
        sys.exit(1)
    return r.stdout


def main():
    body = json.loads(gh("pr", "view", "52", "--json", "body"))["body"]

    replacements = [
        # 1. 新增文件清单里的测试数
        ("（65 个测试）", "（72 个测试）"),
        # 2. L1 证据表的计数 + 环境（麒麟 VM 实测）
        (
            "**65 passed in 12.9s**（WSL2 Python 3.10.12；sqlalchemy 2.0.51 / alembic 1.19.1）",
            "**72 passed in 14.74s**（麒麟 VM Python 3.12.3；sqlalchemy 2.0.52 / alembic 1.19.1 / pydantic 2.13.4）",
        ),
    ]

    for old, new in replacements:
        if old not in body:
            print(f"[WARN] 未找到待替换字符串: {old!r}")
        else:
            body = body.replace(old, new)
            print(f"[OK] 已替换: {old[:30]!r} -> {new[:30]!r}")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"[OK] 新 body 已写入 {OUT} ({len(body)} chars)")
    print("\n===== 校验：关键行 =====")
    for line in body.splitlines():
        if "passed" in line or "个测试" in line:
            print(line)


if __name__ == "__main__":
    main()
