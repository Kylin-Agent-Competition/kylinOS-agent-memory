#!/usr/bin/env python3
"""直接修复麒麟 VM 上的 systemd unit 文件并重启服务"""
import paramiko, time

HOST = '127.0.0.1'
PORT = 2222
USER = 'REDACTED_VM_USER'
PASS = 'REDACTED_VM_PASSWORD'

NEW_UNIT = """[Unit]
Description=Kylin Memory Echo Server - UDS min verification
After=network.target

[Service]
Type=simple
User=REDACTED_VM_USER
ExecStart=/usr/bin/python3 /home/REDACTED_VM_USER/kylin-memory-echo/bin/kylin-memory-echo-server
ExecStopPost=/bin/rm -f /tmp/kylin-memory-echo/echo.sock
Restart=on-failure
RestartSec=2
StandardOutput=append:/home/REDACTED_VM_USER/kylin-memory-echo/logs/server_stdout.log
StandardError=append:/home/REDACTED_VM_USER/kylin-memory-echo/logs/server_stderr.log
NoNewPrivileges=yes
RestrictAddressFamilies=AF_UNIX

[Install]
WantedBy=default.target"""

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
print('[OK] Connected')

# Step 1: Write unit file via sudo tee with password pipe
print('[1/4] Writing unit file...')
cmd1 = 'echo ' + PASS + ' | sudo -S tee /etc/systemd/system/kylin-memory-echo.service <<\'UNITEOF\'\n' + NEW_UNIT + '\nUNITEOF'
chan = c.get_transport().open_session(timeout=15)
chan.exec_command(cmd1)
chan.recv_exit_status()
out = chan.recv(65536).decode('utf-8', errors='replace')
err = chan.recv_stderr(65536).decode('utf-8', errors='replace')
chan.close()
print('  stdout:', out.strip()[:200])
print('  stderr:', err.strip()[:200])

# Step 2: Verify unit file
print('[2/4] Verifying unit file...')
_, o, e = c.exec_command('head -12 /etc/systemd/system/kylin-memory-echo.service', timeout=10)
print(o.read().decode('utf-8', errors='replace')[:800])

# Step 3: daemon-reload + reset + start
print('[3/4] Reload and start...')
cmd3 = 'echo ' + PASS + ' | sudo -S systemctl daemon-reload && echo ' + PASS + ' | sudo -S systemctl reset-failed kylin-memory-echo 2>/dev/null; echo ' + PASS + ' | sudo -S systemctl stop kylin-memory-echo 2>/dev/null; sleep 1; rm -rf /tmp/kylin-memory-echo; echo ' + PASS + ' | sudo -S systemctl start kylin-memory-echo; sleep 3; echo DONE'
chan3 = c.get_transport().open_session(timeout=30)
chan3.exec_command(cmd3)
chan3.recv_exit_status()
out3 = chan3.recv(131072).decode('utf-8', errors='replace')
err3 = chan3.recv_stderr(131072).decode('utf-8', errors='replace')
chan3.close()
print('  stdout:', out3.strip()[:500])
print('  stderr:', err3.strip()[:500])

# Step 4: Check status
print('[4/4] Checking status...')
_, o4, e4 = c.exec_command('systemctl status kylin-memory-echo --no-pager --lines=8; echo ---; ls -la /tmp/kylin-memory-echo/ 2>&1; echo ---; pgrep -a -f kylin-memory-echo-server 2>&1', timeout=15)
print(o4.read().decode('utf-8', errors='replace'))
e4_out = e4.read().decode('utf-8', errors='replace')
if e4_out.strip():
    print('STDERR:', e4_out[:500])

c.close()
print('\n[DONE]')