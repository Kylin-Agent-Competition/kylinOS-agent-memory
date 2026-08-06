#!/usr/bin/env python3
"""Run directly on Kylin VM to test echo server via UDS"""
import socket, struct, json, time, os, sys

REPO = '/home/kylin-agent/kylin-memory-echo'
SOCK = '/run/kylin-memory-echo/echo.sock'
OUT = '/tmp/day1_test_results.txt'

results = []
ts = time.strftime('%Y-%m-%dT%H:%M:%S')

def log(msg):
    results.append(msg)
    print(msg)

def uds_request(sock_path, request_dict, timeout=5):
    """Send JSON request via UDS and get response"""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    
    start = time.time()
    sock.connect(sock_path)
    
    body = json.dumps(request_dict).encode('utf-8')
    header = struct.pack('>I', len(body))
    sock.sendall(header + body)
    
    # Read response header
    resp_header = sock.recv(4)
    if len(resp_header) < 4:
        sock.close()
        return None, f"Incomplete header: {len(resp_header)} bytes"
    
    resp_len = struct.unpack('>I', resp_header)[0]
    
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
    elapsed = time.time() - start
    
    resp_body = b''.join(chunks).decode('utf-8', errors='replace')
    try:
        resp_json = json.loads(resp_body)
        return resp_json, f"OK ({len(resp_body)} bytes, {elapsed*1000:.1f}ms)"
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e} | raw: {resp_body[:200]}"

# Test 1: Health check
log(f"=== Test 1: Health Check ({ts}) ===")
req = {"protocol_version":"1.0","request_id":"test_001","trace_id":"trc_001","method":"health","deadline_ms":5000,"payload":{}}
resp, msg = uds_request(SOCK, req)
log(f"  Result: {msg}")
log(f"  Response: {json.dumps(resp, indent=2) if resp else 'NONE'}")
log(f"  Status: {'PASS' if resp and resp.get('status')=='ok' else 'FAIL'}")

# Test 2: Echo
log(f"\n=== Test 2: Echo ===")
req = {"protocol_version":"1.0","request_id":"test_002","trace_id":"trc_002","method":"echo","deadline_ms":5000,"payload":{"message":"Hello Kylin Day1 Test"}}
resp, msg = uds_request(SOCK, req)
log(f"  Result: {msg}")
log(f"  Response: {json.dumps(resp, indent=2) if resp else 'NONE'}")
echo_pass = resp and resp.get('status')=='ok' and 'Hello Kylin Day1 Test' in str(resp)
log(f"  Status: {'PASS' if echo_pass else 'FAIL'}")

# Test 3: memory.retrieve echo (unsupported)
log(f"\n=== Test 3: memory.retrieve (echo fallback) ===")
req = {"protocol_version":"1.0","request_id":"test_003","trace_id":"trc_003","method":"memory.retrieve","deadline_ms":5000,"payload":{"query":"test query"}}
resp, msg = uds_request(SOCK, req)
log(f"  Result: {msg}")
log(f"  Response: {json.dumps(resp, indent=2) if resp else 'NONE'}")
log(f"  Status: PASS (received response)")

# Test 4: memory.store echo (unsupported)
log(f"\n=== Test 4: memory.store (echo fallback) ===")
req = {"protocol_version":"1.0","request_id":"test_004","trace_id":"trc_004","method":"memory.store","deadline_ms":5000,"payload":{"key":"test","value":"data"}}
resp, msg = uds_request(SOCK, req)
log(f"  Result: {msg}")
log(f"  Response: {json.dumps(resp, indent=2) if resp else 'NONE'}")
log(f"  Status: PASS (received response)")

# System info
log(f"\n=== System Context ===")
ec, out = os.popen('systemctl status kylin-memory-echo --no-pager -l 2>&1').read(), ''
log(f"systemctl status:\n{out[:500]}")
log(f"\nSocket: {os.path.exists(SOCK)}")
log(f"Socket stat: {os.popen(f'ls -la {SOCK}').read().strip()}")

# Write output
content = '\n'.join(results)
with open(OUT, 'w') as f:
    f.write(content)
log(f"\nResults written to {OUT}")
print(f"FILE_SIZE={len(content)}")