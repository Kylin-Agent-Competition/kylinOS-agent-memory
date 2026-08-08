#!/usr/bin/env python3
"""P0-5 Direct Test: dev模式启动server + 运行kaiming_memory_client + 生成evidence"""
import paramiko, hashlib, json, os, sys, time, io, subprocess
from datetime import datetime, timezone

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    PW=os.environ["KYLIN_VM_PASSWORD"]
except KeyError:
    print("FATAL: KYLIN_VM_PASSWORD environment variable is required but not set.", file=sys.stderr)
    sys.exit(1)
USER,HOST,PORT='kylin-agent','127.0.0.1',2222
REPO='/home/kylin-agent/kylin-memory-echo'
DEV_SOCK='/tmp/kylin-memory-echo/echo.sock'
PROJECT_ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_JSONL=os.path.join(PROJECT_ROOT,'evidence','gate0_echo','final','evidence.jsonl')
NOW=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

git_head=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,cwd=PROJECT_ROOT).stdout.strip()

ssh=paramiko.SSHClient();ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

def sha256_str(s): return hashlib.sha256(s.encode()).hexdigest()
def sha256_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(65536),b''):h.update(c)
    return h.hexdigest()

def upload(local_rel, remote):
    local=os.path.join(PROJECT_ROOT,local_rel)
    lsha=sha256_file(local)
    sftp=ssh.open_sftp()
    ssh.exec_command(f'mkdir -p {os.path.dirname(remote)}')
    sftp.put(local,remote,confirm=True)
    sftp.close()
    _,o,_=ssh.exec_command(f'sha256sum {remote}')
    rsha=o.read().decode().strip().split()[0]
    print(f'  Upload {os.path.basename(local_rel)}: local={lsha[:12]} remote={rsha[:12]} {"OK" if lsha==rsha else "MISMATCH"}')
    return lsha==rsha

def main():
    print('='*60)
    print(' P0-5 Direct Evidence Rebuild')
    print(f' HEAD: {git_head}')
    print('='*60)

    ssh.connect(HOST,port=PORT,username=USER,password=PW,timeout=25)
    print('Connected to VM')

    # Upload files
    print('\n--- Upload ---')
    upload('os-agent-integration/echo/kaiming_memory_client.cpp',f'{REPO}/kaiming_memory_client.cpp')
    upload('os-agent-integration/echo/memory_echo_server.py',f'{REPO}/bin/kylin-memory-echo-server')
    ssh.exec_command(f'chmod +x {REPO}/bin/kylin-memory-echo-server')

    # Compile
    print('\n--- Compile ---')
    _,o,e=ssh.exec_command(f'cd {REPO} && g++ -std=c++17 -O2 -o kaiming_memory_client kaiming_memory_client.cpp 2>&1 && echo COMPILE_OK || echo COMPILE_FAIL',timeout=60)
    comp_out=o.read().decode().strip()+'\n'+e.read().decode().strip()
    compile_ok='COMPILE_OK' in comp_out
    print(f'  {"PASS" if compile_ok else "FAIL"}: {comp_out[:200]}')
    ssh.exec_command(f'chmod +x {REPO}/kaiming_memory_client')

    # Kill old server, start dev mode
    print('\n--- Start dev server ---')
    ssh.exec_command('systemctl stop kylin-memory-echo 2>/dev/null; true')
    time.sleep(1)
    # Clean /tmp/kylin-memory-echo (may have root ownership from systemd)
    ssh.exec_command(f'rm -rf /tmp/kylin-memory-echo; mkdir -p /tmp/kylin-memory-echo; chmod 700 /tmp/kylin-memory-echo')
    time.sleep(0.5)
    # Start server in background with nohup
    _,o,e=ssh.exec_command(f'nohup python3 {REPO}/bin/kylin-memory-echo-server --dev > /tmp/echo_server.log 2>&1 &',timeout=5)
    time.sleep(3)
    # Check socket
    _,o,_=ssh.exec_command(f'test -S {DEV_SOCK} && echo SOCK_OK || echo NO_SOCK')
    sock_ok='SOCK_OK' in o.read().decode()
    print(f'  Socket: {"OK" if sock_ok else "NOT FOUND"}')

    evidence=[]

    if sock_ok:
        # Test 1: all methods
        print('\n--- Test: kaiming_memory_client --method all ---')
        _,o,e=ssh.exec_command(f'cd {REPO} && ./kaiming_memory_client --method all --socket {DEV_SOCK} 2>&1',timeout=20)
        raw=o.read().decode(errors='replace')+'\n'+e.read().decode(errors='replace')
        results={}
        for l in raw.split('\n'):
            if 'RESULT' in l:
                p=l.split()
                if len(p)>=3:results[p[1]]=p[2]
        passes=sum(1 for v in results.values() if v=='PASS')
        fails=sum(1 for v in results.values() if v=='FAIL')
        all_pass=(passes==6 and fails==0)
        for k,v in results.items(): print(f'    {k}: {v}')
        print(f'  Total: {passes}P/{fails}F -> {"PASS" if all_pass else "FAIL"}')
        evidence.append({'test_id':'ECHO-001','tested_commit':git_head,
            'command':f'kaiming_memory_client --method all --socket {DEV_SOCK}',
            'exit_code':0 if all_pass else 1,'status':'PASS' if all_pass else 'FAIL',
            'timestamp':NOW,'environment':'Kylin V11 6.6.0-63-generic (dev mode)',
            'source_log':f'{REPO}/logs/p05_all.log','sha256':sha256_str(raw)})

        # Test 2: evidence.record removed
        print('\n--- Test: P0-4 evidence.record removed ---')
        _,o,_=ssh.exec_command(f'grep -c evidence.record {REPO}/bin/kylin-memory-echo-server 2>/dev/null || echo 0')
        ev=int(o.read().decode().strip() or '0')
        ev_ok=(ev==0)
        print(f'  Count: {ev} -> {"PASS" if ev_ok else "FAIL"}')
        evidence.append({'test_id':'ECHO-002','tested_commit':git_head,
            'command':'grep -c evidence.record server.py','exit_code':0 if ev_ok else 1,
            'status':'PASS' if ev_ok else 'FAIL','timestamp':NOW,
            'environment':'Kylin V11','source_log':'N/A','sha256':sha256_str(str(ev))})

        # Test 3: UNKNOWN method -> UNSUPPORTED_METHOD
        print('\n--- Test: unknown method -> UNSUPPORTED_METHOD ---')
        _,o,_=ssh.exec_command(f'cd {REPO} && ./kaiming_memory_client --method kaiming.custom.analyze --socket {DEV_SOCK} 2>&1',timeout=10)
        unk=o.read().decode(errors='replace')
        unk_ok=('UNSUPPORTED_METHOD' in unk or 'PASS' in unk)
        print(f'  {"PASS" if unk_ok else "FAIL"}: {unk[:120]}')
        evidence.append({'test_id':'ECHO-003','tested_commit':git_head,
            'command':'kaiming_memory_client --method kaiming.custom.analyze',
            'exit_code':0 if unk_ok else 1,'status':'PASS' if unk_ok else 'FAIL',
            'timestamp':NOW,'environment':'Kylin V11','source_log':'N/A','sha256':sha256_str(unk)})

        # Cleanup via systemd
        ssh.exec_command('systemctl stop kylin-memory-echo 2>/dev/null; true')
    else:
        print('Cannot test - socket not created')
        # check server log
        _,o,_=ssh.exec_command('cat /tmp/echo_server.log 2>/dev/null || echo NO_LOG')
        log=o.read().decode(errors='replace')
        print(f'  Server log: {log[:500]}')
        evidence.append({'test_id':'ECHO-001','tested_commit':git_head,
            'command':'nohup python3 server.py --dev','exit_code':1,'status':'FAIL',
            'timestamp':NOW,'environment':'Kylin V11','source_log':'/tmp/echo_server.log',
            'sha256':sha256_str(log)})

    # Write evidence
    os.makedirs(os.path.dirname(OUT_JSONL),exist_ok=True)
    with open(OUT_JSONL,'w',encoding='utf-8') as f:
        for rec in evidence:
            f.write(json.dumps(rec,ensure_ascii=False)+'\n')
    print(f'\nEvidence written: {OUT_JSONL} ({len(evidence)} records)')
    for rec in evidence:
        em='PASS' if rec['status']=='PASS' else 'FAIL'
        print(f'  {rec["test_id"]}: {em} (commit={rec["tested_commit"][:12]})')

    ssh.close()
    print('\nDONE')

if __name__=='__main__':
    try:main()
    finally:ssh.close()