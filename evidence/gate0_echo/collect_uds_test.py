#!/usr/bin/env python3
"""Direct UDS test via SSH - writes results to local client.log"""
import paramiko, os, time, json

PW = os.environ.get("KYLIN_VM_PASSWORD", "")
OUT = os.path.join(os.path.dirname(__file__), 'final')
os.makedirs(OUT, exist_ok=True)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('127.0.0.1', port=2222, username='kylin-agent', password=PW, timeout=15)

def run(cmd, timeout=30):
    _, so, se = ssh.exec_command(cmd, timeout=timeout)
    ec = so.channel.recv_exit_status()
    out = so.read().decode('utf-8', errors='replace')
    err = se.read().decode('utf-8', errors='replace')
    return ec, out, err

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
lines = [f"# UDS Client Test Log", f"# {ts}", ""]

# Step 1: Simple socket existence check
ec, o, _ = run('ls -la /run/kylin-memory-echo/echo.sock 2>&1')
lines.append(f"## Socket Check (ec={ec})")
lines.append(o)
lines.append("")

# Step 2: Use bin/echo_client (owned by kylin-agent)
ec, o, _ = run('timeout 5 /home/kylin-agent/kylin-memory-echo/bin/echo_client --socket /run/kylin-memory-echo/echo.sock --method echo --message "Day1_TEST" 2>&1; echo "EXIT=$?"')
lines.append(f"## D4 echo_client (ec={ec})")
lines.append(o)
lines.append("")

# Step 3: bin/kaiming_memory_client
ec, o, _ = run('timeout 5 /home/kylin-agent/kylin-memory-echo/bin/kaiming_memory_client --method health --socket /run/kylin-memory-echo/echo.sock 2>&1; echo "EXIT=$?"')
lines.append(f"## D5 kaiming_memory_client health (ec={ec})")
lines.append(o)
lines.append("")

ec, o, _ = run('timeout 5 /home/kylin-agent/kylin-memory-echo/bin/kaiming_memory_client --method all --socket /run/kylin-memory-echo/echo.sock 2>&1; echo "EXIT=$?"')
lines.append(f"## D5 kaiming_memory_client all (ec={ec})")
lines.append(o)
lines.append("")

# Step 4: Python UDS direct test (via inline script)
py_test = """
import socket, struct, json
sock = '/run/kylin-memory-echo/echo.sock'
def uds(path, req, to=5):
    s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(to); s.connect(path)
    b=json.dumps(req).encode(); s.sendall(struct.pack('>I',len(b))+b)
    h=s.recv(4)
    if len(h)<4: s.close(); print('BAD_HDR'); return
    rl=struct.unpack('>I',h)[0]
    chunks=[]; rem=rl
    while rem>0:
        c=s.recv(min(rem,4096))
        if not c: break
        chunks.append(c); rem-=len(c)
    s.close()
    print(json.dumps(json.loads(b''.join(chunks)), indent=2, ensure_ascii=False))

print('--- HEALTH ---')
uds(sock, {'protocol_version':'1.0','request_id':'r1','method':'health','deadline_ms':5000,'payload':{}})
print('--- ECHO ---')
uds(sock, {'protocol_version':'1.0','request_id':'r2','method':'echo','deadline_ms':5000,'payload':{'message':'Day1-UDS-Test-20260806'}})
print('--- RETRIEVE ---')
uds(sock, {'protocol_version':'1.0','request_id':'r3','method':'memory.retrieve','deadline_ms':5000,'payload':{'query':'test'}})
print('--- STORE ---')
uds(sock, {'protocol_version':'1.0','request_id':'r4','method':'memory.store','deadline_ms':5000,'payload':{'key':'k','value':'v'}})
print('--- DONE ---')
"""

# Write py_test to remote
sftp = ssh.open_sftp()
from io import BytesIO
sftp.putfo(BytesIO(py_test.encode()), '/tmp/uds_test.py')
sftp.close()

ec, o, _ = run('python3 /tmp/uds_test.py 2>&1', timeout=15)
lines.append(f"## Python UDS direct test (ec={ec})")
lines.append(o)
lines.append("")

# Write all to local client.log
content = '\n'.join(lines)
client_path = os.path.join(OUT, 'client.log')
with open(client_path, 'w', encoding='utf-8') as f:
    f.write(content)

ssh.close()
print(f'Written {len(content)} bytes to {client_path}')
print(f'File size: {os.path.getsize(client_path)}')