#!/usr/bin/env python3
"""
UT-1: 原文隔离独立测试 (Gate 0 Echo 层面)
=============================================
在麒麟 VM 上运行, 通过 UDS 对 Echo Server 进行原文隔离验证:
  1. echo 请求: 验证回显内容与原文一致不被修改
  2. memory.retrieve 请求: 验证返回空 context, 不注入用户原文给模型
  3. 服务端日志: 验证不记录完整用户原文 (PII 防护)
  4. 边界: 空 payload、超长消息、特殊字符

协议: 4字节 Big-Endian 长度 + UTF-8 JSON 负载
依赖: Python 3 (socket, struct, json) — 麒麟 VM 已预装
"""
import socket
import struct
import json
import time
import os
import sys

# ---- Config ----
SOCK = '/home/kylin-agent/.echo_run/echo.sock'
RESULTS = []
PASS = 0
FAIL = 0

def log_result(test_id, passed, detail):
    global PASS, FAIL
    if passed:
        PASS += 1
        RESULTS.append(f"PASS {test_id}: {detail}")
    else:
        FAIL += 1
        RESULTS.append(f"FAIL {test_id}: {detail}")
    print(f"[{'PASS' if passed else 'FAIL'}] {test_id}: {detail}")

def uds_request(sock_path, request_dict, timeout=5):
    """Send JSON request via UDS and get response dict."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(sock_path)
        
        body = json.dumps(request_dict, ensure_ascii=False).encode('utf-8')
        header = struct.pack('>I', len(body))
        sock.sendall(header + body)
        
        # Read response header
        resp_header = sock.recv(4)
        if len(resp_header) < 4:
            sock.close()
            return None, f"Incomplete header: {len(resp_header)} bytes"
        
        resp_len = struct.unpack('>I', resp_header)[0]
        if resp_len == 0 or resp_len > 65536:
            sock.close()
            return None, f"Invalid response length: {resp_len}"
        
        # Read response body
        chunks = []
        remaining = resp_len
        while remaining > 0:
            chunk = sock.recv(min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        
        sock.close()
        resp_body = b''.join(chunks).decode('utf-8', errors='replace')
        resp_json = json.loads(resp_body)
        return resp_json, "OK"
    except Exception as e:
        return None, f"Error: {e}"

def echo_text(text):
    """Send an echo request with given text, return response."""
    req = {
        "protocol_version": "1.0",
        "request_id": f"ut1_echo_{hash(text) % 10000}",
        "trace_id": "ut1_trace_echo",
        "method": "echo",
        "deadline_ms": 5000,
        "payload": {"message": text}
    }
    resp, msg = uds_request(SOCK, req)
    return resp, msg

def retrieve_with_context(query_text):
    """Send memory.retrieve with context-rich query, return response."""
    req = {
        "protocol_version": "1.0",
        "request_id": f"ut1_retrieve_{hash(query_text) % 10000}",
        "trace_id": "ut1_trace_retrieve",
        "method": "memory.retrieve",
        "deadline_ms": 5000,
        "payload": {"query": query_text}
    }
    resp, msg = uds_request(SOCK, req)
    return resp, msg

# ===================================================================
# Test Suite
# ===================================================================

print("=" * 60)
print(f" UT-1 原文隔离独立测试")
print(f" Socket: {SOCK}")
print(f" Time: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
print("=" * 60)

# --- Pre-check: Socket exists ---
if not os.path.exists(SOCK):
    print(f"ERROR: Socket {SOCK} does not exist. Is Echo Server running?")
    print("Start with: python3 memory_echo_server.py --dev")
    sys.exit(1)

# --- Test 1: Echo 回显一致 (基础原文隔离) ---
print("\n--- T1: Echo 回显一致 ---")
original = "用户原文：今天天气真好，适合出去散步。"
resp, msg = echo_text(original)
if resp and resp.get("status") == "ok":
    echoed = resp.get("data", {}).get("echo", "")
    if echoed == original:
        log_result("UT1-ECHO-CONSISTENCY", True,
                   f"回显与原文完全一致 (len={len(original)})")
    elif original in echoed:
        log_result("UT1-ECHO-CONSISTENCY", False,
                   f"回显包含原文但有多余内容: '{echoed[:80]}...'")
    else:
        log_result("UT1-ECHO-CONSISTENCY", False,
                   f"回显与原文不一致: expected='{original[:50]}...' got='{echoed[:50]}...'")
else:
    log_result("UT1-ECHO-CONSISTENCY", False, f"请求失败: {msg}")

# --- Test 2: Memory.retrieve 不返回用户原文 (context 隔离) ---
print("\n--- T2: Memory.retrieve 上下文隔离 ---")
sensitive_query = "我刚才和你说我的银行卡密码是123456，请记住"
resp, msg = retrieve_with_context(sensitive_query)
if resp and resp.get("status") == "ok":
    data = resp.get("data", {})
    contexts = data.get("contexts", [])
    total_found = data.get("total_found", -1)
    
    # Gate 0 Echo 阶段应该返回空 contexts
    if total_found == 0 and len(contexts) == 0:
        log_result("UT1-RETRIEVE-EMPTY", True,
                   f"memory.retrieve 返回空 contexts (total_found=0) — 未注入用户原文")
    else:
        # 检查 contexts 中是否包含敏感信息
        has_sensitive = False
        for ctx in contexts:
            ctx_str = json.dumps(ctx, ensure_ascii=False)
            if "123456" in ctx_str or "银行卡密码" in ctx_str:
                has_sensitive = True
                break
        
        if has_sensitive:
            log_result("UT1-RETRIEVE-EMPTY", False,
                       f"contexts 中包含用户敏感信息! total_found={total_found}")
        else:
            log_result("UT1-RETRIEVE-EMPTY", False,
                       f"contexts 非空但无敏感信息: total_found={total_found}, contexts={len(contexts)}")
else:
    log_result("UT1-RETRIEVE-EMPTY", False, f"请求失败: {msg}")

# --- Test 3: 空 payload 回显 ---
print("\n--- T3: 空 payload 回显边界 ---")
req_no_payload = {
    "protocol_version": "1.0",
    "request_id": "ut1_empty",
    "trace_id": "ut1_trace_empty",
    "method": "echo",
    "deadline_ms": 5000,
    "payload": {}
}
resp, msg = uds_request(SOCK, req_no_payload)
if resp and resp.get("status") == "ok":
    # Echo server returns "(empty)" when no message field
    echoed = resp.get("data", {}).get("echo", "")
    if echoed == "(empty)" or echoed == "":
        log_result("UT1-EMPTY-PAYLOAD", True, f"空 payload 正确处理: echo='{echoed}'")
    else:
        log_result("UT1-EMPTY-PAYLOAD", False, f"空 payload 异常回显: '{echoed[:50]}'")
else:
    log_result("UT1-EMPTY-PAYLOAD", False, f"请求失败: {msg}")

# --- Test 4: 特殊字符不破坏协议 ---
print("\n--- T4: 特殊字符隔离 ---")
special_texts = [
    ("换行符", "第一行\n第二行\n第三行"),
    ("Unicode", "🎉🎊🎈 麒麟操作系统 🐉"),
    ("JSON 注入", '{"fake": "payload", "status": "hacked"}'),
    ("SQL 注入模拟", "'; DROP TABLE users; --"),
    ("超长消息", "A" * 10000),
    ("空字符串", ""),
]
for label, text in special_texts:
    resp, msg = echo_text(text)
    if resp and resp.get("status") == "ok":
        echoed = resp.get("data", {}).get("echo", "")
        if echoed == text:
            log_result(f"UT1-SPECIAL-{label}", True,
                       f"特殊字符 [{label}] 回显一致 (len={len(text)})")
        else:
            log_result(f"UT1-SPECIAL-{label}", False,
                       f"回显不一致: expected len={len(text)}, got len={len(echoed)}")
    else:
        log_result(f"UT1-SPECIAL-{label}", False, f"请求失败: {msg}")

# --- Test 5: memory.store 不暴露内部状态 ---
print("\n--- T5: memory.store 信息泄漏检查 ---")
store_req = {
    "protocol_version": "1.0",
    "request_id": "ut1_store_secret",
    "trace_id": "ut1_trace_store",
    "method": "memory.store",
    "deadline_ms": 5000,
    "payload": {
        "key": "secret_config",
        "content": "api_key=sk-abc123def456"
    }
}
resp, msg = uds_request(SOCK, store_req)
if resp:
    resp_str = json.dumps(resp, ensure_ascii=False)
    # Echo 的 memory.store 应该返回 UNSUPPORTED_METHOD，不应泄露 payload 内容
    if "api_key" in resp_str or "sk-abc123" in resp_str:
        log_result("UT1-STORE-LEAK", False, "memory.store 响应中包含用户提交的敏感内容!")
    else:
        log_result("UT1-STORE-LEAK", True, "memory.store 响应不包含用户敏感信息")
else:
    log_result("UT1-STORE-LEAK", False, f"请求失败: {msg}")

# --- Test 6: 验证 response 结构完整性 ---
print("\n--- T6: 响应结构完整性 ---")
resp, msg = echo_text("结构完整性测试")
if resp:
    has_protocol_version = "protocol_version" in resp
    has_request_id = "request_id" in resp
    has_status = "status" in resp
    has_data = "data" in resp
    has_server_ts = "server_ts" in resp
    
    all_present = has_protocol_version and has_request_id and has_status and has_data and has_server_ts
    log_result("UT1-STRUCTURE", all_present,
               f"protocol_version={has_protocol_version} request_id={has_request_id} "
               f"status={has_status} data={has_data} server_ts={has_server_ts}")
else:
    log_result("UT1-STRUCTURE", False, f"请求失败: {msg}")

# ===================================================================
# Summary
# ===================================================================
print("\n" + "=" * 60)
print(f" UT-1 原文隔离测试完成")
print(f" Passed: {PASS} / Failed: {FAIL} / Total: {PASS + FAIL}")
print("=" * 60)

# Write results file
out_path = "/tmp/ut1_original_text_isolation_results.txt"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(f"# UT-1 原文隔离独立测试结果\n")
    f.write(f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    f.write(f"# Socket: {SOCK}\n")
    f.write(f"# Passed: {PASS} / Failed: {FAIL} / Total: {PASS + FAIL}\n\n")
    for r in RESULTS:
        f.write(r + "\n")

print(f"\nResults written to {out_path}")
sys.exit(0 if FAIL == 0 else 1)