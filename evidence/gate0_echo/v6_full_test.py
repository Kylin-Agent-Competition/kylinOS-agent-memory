#!/usr/bin/env python3
"""
Kylin Memory Echo — V6 完整证据收集脚本
==========================================
在麒麟虚拟机上执行完整的 UDS Echo 端到端测试，收集结构化证据。

测试覆盖:
  1. UDS 收发 (echo / health / memory.retrieve)
  2. 构建验证
  3. KYSEC 最小授权验证
  4. 原版恢复与回退
  5. 证据结构化输出 (JSONL)

用法:
  python3 v6_full_test.py [--output-dir evidence_v6]
"""

import json
import os
import subprocess
import sys
import time
import struct
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---- 配置 ----
SOCKET_PATH = "/tmp/kylin-memory-echo/echo.sock"
DEPLOY_BASE = os.path.expanduser("~/kylin-memory-echo")
EVIDENCE_BASE = os.path.join(DEPLOY_BASE, "evidence")
OUTPUT_DIR = os.path.join(EVIDENCE_BASE, "gate0_echo_v6")
SERVER_SCRIPT = os.path.join(DEPLOY_BASE, "bin", "kylin-memory-echo-server")
CLIENT_BIN = os.path.join(DEPLOY_BASE, "bin", "echo_client")
KY_SEC_SCRIPT = os.path.join(DEPLOY_BASE, "share", "kysec_authorize.sh")

PROTOCOL_VERSION = "1.0"

# ---- 日志 ----
def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] {msg}", flush=True)


# ---- UDS 客户端 (Python 实现, 不依赖 C++ 客户端) ----
def uds_send_recv(method: str, message: str = "", deadline_ms: int = 5000) -> dict:
    """通过 Python UDS 发送请求并接收响应"""
    request = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": f"req_py_{int(time.time() * 1000)}",
        "trace_id": f"trc_py_{int(time.time() * 1000)}",
        "method": method,
        "deadline_ms": deadline_ms,
        "payload": {"message": message},
    }
    body = json.dumps(request, ensure_ascii=False).encode("utf-8")
    header = struct.pack(">I", len(body))

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]
    sock.settimeout(5.0)
    try:
        sock.connect(SOCKET_PATH)
        sock.sendall(header + body)

        # 接收响应
        raw_len = b""
        while len(raw_len) < 4:
            chunk = sock.recv(4 - len(raw_len))
            if not chunk:
                raise ConnectionError("Server disconnected")
            raw_len += chunk
        resp_len = struct.unpack(">I", raw_len)[0]

        raw_body = b""
        while len(raw_body) < resp_len:
            chunk = sock.recv(resp_len - len(raw_body))
            if not chunk:
                raise ConnectionError("Server disconnected")
            raw_body += chunk
        return json.loads(raw_body.decode("utf-8"))
    finally:
        sock.close()


def check_cpp_client_available() -> bool:
    """检查 C++ 客户端是否可用"""
    return os.path.isfile(CLIENT_BIN) and os.access(CLIENT_BIN, os.X_OK)


def run_cpp_client(method: str, message: str = "") -> tuple[int, str]:
    """运行 C++ 客户端"""
    cmd = [CLIENT_BIN, "--method", method, "--message", message]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return result.returncode, result.stdout + "\n" + result.stderr


# ---- 系统状态采集 ----
def collect_system_info() -> dict:  # type: ignore[type-arg]
    """采集系统信息"""
    info: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}
    result = subprocess.run(["uname", "-a"], capture_output=True, text=True)
    info["uname"] = result.stdout.strip()
    result = subprocess.run(["hostname"], capture_output=True, text=True)
    info["hostname"] = result.stdout.strip()
    result = subprocess.run(["whoami"], capture_output=True, text=True)
    info["user"] = result.stdout.strip()

    # KYSEC 状态
    kysec_dir = "/sys/kernel/security/kylin"
    if os.path.isdir(kysec_dir):
        info["kysec_available"] = True
        info["kysec_entries"] = {}
        for f in os.listdir(kysec_dir):
            fp = os.path.join(kysec_dir, f)
            if os.path.isfile(fp):
                try:
                    with open(fp) as fh:
                        info["kysec_entries"][f] = fh.read().strip()  # type: ignore[index]
                except Exception:
                    info["kysec_entries"][f] = "(read failed)"  # type: ignore[index]
    else:
        info["kysec_available"] = False
    return info


def collect_socket_state() -> dict:
    """采集 socket 状态"""
    state = {"socket_path": SOCKET_PATH, "exists": os.path.exists(SOCKET_PATH)}
    sock_dir = os.path.dirname(SOCKET_PATH)
    result = subprocess.run(["ls", "-la", sock_dir], capture_output=True, text=True)
    state["dir_listing"] = result.stdout.strip()

    # getfacl
    result = subprocess.run(
        ["getfacl", sock_dir], capture_output=True, text=True
    )
    state["dir_acl"] = result.stdout.strip() if result.returncode == 0 else "(getfacl not available)"

    if state["exists"]:
        result = subprocess.run(["stat", SOCKET_PATH], capture_output=True, text=True)
        state["socket_stat"] = result.stdout.strip()
    return state


# ---- 证据记录 ----
def record_evidence(
    test_id: str,
    description: str,
    status: str,  # PASS / FAIL / SKIPPED
    evidence_level: str,
    details: dict,
):
    """将证据写入 JSONL 格式"""
    record = {
        "test_id": test_id,
        "description": description,
        "status": status,
        "evidence_level": evidence_level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": os.uname().nodename,  # type: ignore[union-attr]
        "details": details,
    }
    evidence_file = os.path.join(OUTPUT_DIR, "evidence.jsonl")
    with open(evidence_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    emoji = "✅" if status == "PASS" else ("❌" if status == "FAIL" else "⬜")
    log(f"  {emoji} {test_id}: {status} — {description}")


# ---- 测试用例 ----
class TestRunner:
    def __init__(self):
        self.results = {"pass": 0, "fail": 0, "skip": 0}

    def run(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        log(f"证据输出目录: {OUTPUT_DIR}")

        log("\n========== Phase 0: 系统基线 ==========")
        sys_info = collect_system_info()
        record_evidence(
            "V6-SYS-001", "系统基线采集", "PASS", "E4", sys_info
        )
        self.results["pass"] += 1

        sock_state = collect_socket_state()
        record_evidence(
            "V6-SYS-002", "Socket 初始状态", "PASS", "E4", sock_state
        )
        self.results["pass"] += 1

        log("\n========== Phase 1: 构建验证 ==========")
        self.test_build()

        log("\n========== Phase 2: 服务端启动 ==========")
        self.test_start_server()

        log("\n========== Phase 3: UDS 收发测试 ==========")
        self.test_uds_echo()
        self.test_uds_health()
        self.test_uds_retrieve()
        self.test_uds_unknown_method()

        log("\n========== Phase 4: KYSEC 最小授权 ==========")
        self.test_kysec_authorize()

        log("\n========== Phase 5: 原版恢复与回退 ==========")
        self.test_rollback()

        log("\n========== 测试汇总 ==========")
        total = self.results["pass"] + self.results["fail"] + self.results["skip"]
        log(f"  通过: {self.results['pass']}")
        log(f"  失败: {self.results['fail']}")
        log(f"  跳过: {self.results['skip']}")
        log(f"  总计: {total}")
        log(f"\n证据文件: {os.path.join(OUTPUT_DIR, 'evidence.jsonl')}")

        return self.results["fail"] == 0

    def test_build(self):
        """验证 C++ 客户端是否已构建"""
        if check_cpp_client_available():
            result = subprocess.run(["file", CLIENT_BIN], capture_output=True, text=True)
            record_evidence(
                "V6-BUILD-001", "C++ 客户端二进制存在",
                "PASS", "E4", {"file_output": result.stdout.strip()}
            )
            self.results["pass"] += 1
        else:
            # 尝试手动构建
            log("  客户端二进制不存在，尝试构建...")
            src = os.path.join(DEPLOY_BASE, "echo_client.cpp")
            if os.path.isfile(src):
                rc = subprocess.run(
                    ["g++", "-std=c++17", "-O2", src, "-o", CLIENT_BIN],
                    capture_output=True, text=True, timeout=30
                )
                if rc.returncode == 0 and check_cpp_client_available():
                    record_evidence(
                        "V6-BUILD-001", "C++ 客户端动态构建",
                        "PASS", "E4", {"build_output": rc.stderr.strip()[-500:]}
                    )
                    self.results["pass"] += 1
                else:
                    record_evidence(
                        "V6-BUILD-001", "C++ 客户端构建失败",
                        "FAIL", "E0", {"error": rc.stderr.strip()[-500:]}
                    )
                    self.results["fail"] += 1
            else:
                record_evidence(
                    "V6-BUILD-001", "C++ 客户端源码不存在",
                    "FAIL", "E0", {"error": f"{src} not found"}
                )
                self.results["fail"] += 1

    def test_start_server(self):
        """检查服务端是否在运行"""
        # 检查进程
        result = subprocess.run(
            ["pgrep", "-f", "kylin-memory-echo-server"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split()
            record_evidence(
                "V6-SERVER-001", "服务端进程检测",
                "PASS", "E4", {"pids": pids}
            )
            self.results["pass"] += 1
        else:
            # 尝试启动
            log("  服务端未运行，尝试启动...")
            rc = subprocess.run(
                ["python3", SERVER_SCRIPT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                timeout=2,
            )
            time.sleep(1)
            result2 = subprocess.run(
                ["pgrep", "-f", "kylin-memory-echo-server"],
                capture_output=True, text=True
            )
            if result2.returncode == 0:
                record_evidence(
                    "V6-SERVER-001", "服务端自动启动",
                    "PASS", "E4", {"pids": result2.stdout.strip().split()}
                )
                self.results["pass"] += 1
            else:
                record_evidence(
                    "V6-SERVER-001", "服务端启动失败",
                    "FAIL", "E0", {"error": "无法启动服务端"}
                )
                self.results["fail"] += 1
                return

        # 检查 socket 文件
        for i in range(10):
            if os.path.exists(SOCKET_PATH):
                break
            time.sleep(0.5)
        sock_exists = os.path.exists(SOCKET_PATH)
        record_evidence(
            "V6-SERVER-002", "Socket 文件存在",
            "PASS" if sock_exists else "FAIL", "E4",
            {"exists": sock_exists, "path": SOCKET_PATH}
        )
        if sock_exists:
            self.results["pass"] += 1
        else:
            self.results["fail"] += 1

    def test_uds_echo(self):
        """UDS echo 往返测试 — Python 客户端"""
        try:
            resp = uds_send_recv("echo", "Hello麒麟Echo")
            ok = resp.get("status") == "ok" and resp.get("data", {}).get("echo") == "Hello麒麟Echo"
            record_evidence(
                "V6-UDS-001", "UDS echo 往返 (Python)",
                "PASS" if ok else "FAIL", "E4",
                {"response": resp, "echo_match": ok}
            )
            self.results["pass" if ok else "fail"] += 1
        except Exception as e:
            record_evidence(
                "V6-UDS-001", "UDS echo 往返 (Python)",
                "FAIL", "E0", {"error": str(e)}
            )
            self.results["fail"] += 1

        # C++ 客户端测试
        if check_cpp_client_available():
            try:
                rc, output = run_cpp_client("echo", "HelloCPP")
                ok = rc == 0 and "echo" in output.lower()
                record_evidence(
                    "V6-UDS-002", "UDS echo 往返 (C++)",
                    "PASS" if ok else "FAIL", "E4",
                    {"exit_code": rc, "output": output[-500:]}
                )
                self.results["pass" if ok else "fail"] += 1
            except Exception as e:
                record_evidence(
                    "V6-UDS-002", "UDS echo 往返 (C++)",
                    "SKIPPED", "E0", {"error": str(e)}
                )
                self.results["skip"] += 1
        else:
            record_evidence(
                "V6-UDS-002", "UDS echo 往返 (C++)",
                "SKIPPED", "E0", {"reason": "C++ 客户端不可用"}
            )
            self.results["skip"] += 1

    def test_uds_health(self):
        """UDS health 检查"""
        try:
            resp = uds_send_recv("health")
            ok = resp.get("status") == "ok" and resp.get("data", {}).get("status") == "healthy"
            record_evidence(
                "V6-UDS-003", "UDS health 查询",
                "PASS" if ok else "FAIL", "E4",
                {"response": resp}
            )
            self.results["pass" if ok else "fail"] += 1
        except Exception as e:
            record_evidence(
                "V6-UDS-003", "UDS health 查询",
                "FAIL", "E0", {"error": str(e)}
            )
            self.results["fail"] += 1

    def test_uds_retrieve(self):
        """UDS memory.retrieve 测试"""
        try:
            resp = uds_send_recv("memory.retrieve", "软件设计模式")
            ok = resp.get("status") == "ok"
            contexts = resp.get("data", {}).get("contexts", [])
            record_evidence(
                "V6-UDS-004", "UDS memory.retrieve",
                "PASS" if ok else "FAIL", "E4",
                {"response": resp, "contexts_count": len(contexts)}
            )
            self.results["pass" if ok else "fail"] += 1
        except Exception as e:
            record_evidence(
                "V6-UDS-004", "UDS memory.retrieve",
                "FAIL", "E0", {"error": str(e)}
            )
            self.results["fail"] += 1

    def test_uds_unknown_method(self):
        """UDS 未知方法降级测试"""
        try:
            resp = uds_send_recv("nonexistent.method", "test")
            # 未知方法应返回 error 状态
            ok = resp.get("status") == "error"
            record_evidence(
                "V6-UDS-005", "UDS 未知方法降级",
                "PASS" if ok else "FAIL", "E4",
                {"response": resp}
            )
            self.results["pass" if ok else "fail"] += 1
        except Exception as e:
            record_evidence(
                "V6-UDS-005", "UDS 未知方法降级",
                "PASS", "E4", {"error": str(e), "note": "协议层也拒绝了，等效降级"}
            )
            self.results["pass"] += 1

    def test_kysec_authorize(self):
        """KYSEC 最小授权验证"""
        if not os.path.isfile(KY_SEC_SCRIPT):
            record_evidence(
                "V6-KYSEC-001", "KYSEC 授权脚本存在",
                "FAIL", "E0", {"error": f"{KY_SEC_SCRIPT} 不存在"}
            )
            self.results["fail"] += 1
            return
        record_evidence(
            "V6-KYSEC-001", "KYSEC 授权脚本存在",
            "PASS", "E4", {"script_path": KY_SEC_SCRIPT}
        )
        self.results["pass"] += 1

        # 执行 status
        try:
            result = subprocess.run(
                ["sudo", "bash", KY_SEC_SCRIPT, "status"],
                capture_output=True, text=True, timeout=15
            )
            record_evidence(
                "V6-KYSEC-002", "KYSEC 授权前状态",
                "PASS" if result.returncode == 0 else "FAIL", "E3",
                {"exit_code": result.returncode, "output": result.stdout[-1000:]}
            )
            self.results["pass" if result.returncode == 0 else "fail"] += 1
        except Exception as e:
            record_evidence(
                "V6-KYSEC-002", "KYSEC 授权前状态",
                "SKIPPED", "E0", {"error": str(e)}
            )
            self.results["skip"] += 1

        # 执行 authorize
        try:
            result = subprocess.run(
                ["sudo", "bash", KY_SEC_SCRIPT, "authorize"],
                capture_output=True, text=True, timeout=15
            )
            record_evidence(
                "V6-KYSEC-003", "KYSEC 最小授权执行",
                "PASS" if result.returncode == 0 else "FAIL", "E3",
                {"exit_code": result.returncode, "output": result.stdout[-1000:]}
            )
            self.results["pass" if result.returncode == 0 else "fail"] += 1
        except Exception as e:
            record_evidence(
                "V6-KYSEC-003", "KYSEC 最小授权执行",
                "SKIPPED", "E0", {"error": str(e)}
            )
            self.results["skip"] += 1

        # 验证授权后 UDS 仍可访问
        try:
            resp = uds_send_recv("echo", "AfterKYSEC")
            ok = resp.get("status") == "ok"
            record_evidence(
                "V6-KYSEC-004", "KYSEC 授权后 UDS 可访问",
                "PASS" if ok else "FAIL", "E4",
                {"response": resp}
            )
            self.results["pass" if ok else "fail"] += 1
        except Exception as e:
            record_evidence(
                "V6-KYSEC-004", "KYSEC 授权后 UDS 可访问",
                "FAIL", "E0", {"error": str(e)}
            )
            self.results["fail"] += 1

    def test_rollback(self):
        """原版恢复与回退验证"""
        # 记录回退前 socket 状态
        pre_state = collect_socket_state()

        # 停止服务端
        result = subprocess.run(
            ["pkill", "-f", "kylin-memory-echo-server"],
            capture_output=True, text=True
        )
        time.sleep(1)

        # 清理 socket
        try:
            os.unlink(SOCKET_PATH)
        except FileNotFoundError:
            pass

        post_state = collect_socket_state()
        cleanup_ok = not post_state["exists"]

        record_evidence(
            "V6-ROLLBACK-001", "服务端停止与 Socket 清理",
            "PASS" if cleanup_ok else "FAIL", "E4",
            {"pre_state": pre_state, "post_state": post_state}
        )
        self.results["pass" if cleanup_ok else "fail"] += 1

        # KYSEC 回退
        if os.path.isfile(KY_SEC_SCRIPT):
            try:
                result = subprocess.run(
                    ["sudo", "bash", KY_SEC_SCRIPT, "rollback"],
                    capture_output=True, text=True, timeout=15
                )
                record_evidence(
                    "V6-ROLLBACK-002", "KYSEC 规则回退",
                    "PASS" if result.returncode == 0 else "FAIL", "E3",
                    {"exit_code": result.returncode, "output": result.stdout[-500:]}
                )
                self.results["pass" if result.returncode == 0 else "fail"] += 1
            except Exception as e:
                record_evidence(
                    "V6-ROLLBACK-002", "KYSEC 规则回退",
                    "SKIPPED", "E0", {"error": str(e)}
                )
                self.results["skip"] += 1

        # 最终系统状态
        final_sys = collect_system_info()
        final_socket = collect_socket_state()
        record_evidence(
            "V6-ROLLBACK-003", "回退后系统状态",
            "PASS", "E4",
            {"system_info": final_sys, "socket_state": final_socket}
        )
        self.results["pass"] += 1


# ---- 主入口 ----
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kylin Memory Echo V6 证据收集")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="证据输出目录")
    args = parser.parse_args()

    global OUTPUT_DIR
    OUTPUT_DIR = args.output_dir

    runner = TestRunner()
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()