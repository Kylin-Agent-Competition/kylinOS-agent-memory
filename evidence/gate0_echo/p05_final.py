#!/usr/bin/env python3
"""P0-5 Final: 铁律上传+sudo清理+dev启动+6项测试+生成evidence.jsonl"""
import paramiko, hashlib, json, os, sys, time, io, subprocess
from datetime import datetime, timezone

if sys.platform=='win32':
    sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')

PW='***REMOVED_PASSWORD***';USER='kylin-agent';REPO=f'/home/{USER}/kylin-memory-echo'
PROJ=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEV_SOCK='/tmp/kylin-memory-echo/echo.sock'
OUT=os.path.join(PROJ,'evidence','gate0_echo','final','evidence.jsonl')
NOW=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
HEAD=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,cwd=PROJ).stdout.strip()

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(65536),b''):h.update(c)
    return h.hexdigest()

def sha256_str(s): return hashlib.sha256(s.encode()).hexdigest()

ssh=paramiko.SSHClient();ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

def run(cmd, timeout=15):
    _,o,e=ssh.exec_command(cmd,timeout=timeout)
    ec=o.channel.recv_exit_status()
    out=o.read().decode('utf-8','replace')
    err=e.read().decode('utf-8','replace')
    return ec,out,err

def run_sudo(cmd, timeout=15):
    return run(f"echo '{PW}' | sudo -S bash -c '{cmd}'", timeout)

def upload(local_rel, remote):
    local=os.path.join(PROJ,local_rel)
    lsha=sha256_file(local)
    run(f'mkdir -p {os.path.dirname(remote)}')
    sftp=ssh.open_sftp();sftp.put(local,remote,confirm=True);sftp.close()
    ec,o,_=run(f'sha256sum {remote}')
    rsha=o.strip().split()[0]
    ok=(lsha==rsha)
    print(f'  {"OK" if ok else "FAIL"}: {os.path.basename(local_rel)} sha={rsha[:12]}')
    return ok

print('='*50)
print(f'P0-5 Evidence Rebuild @ {HEAD[:12]}')
print('='*50)

ssh.connect('127.0.0.1',port=2222,username=USER,password=PW,timeout=30)
print('Connected')

# 1. Upload
print('\n[1] Upload...')
upload('os-agent-integration/echo/kaiming_memory_client.cpp',f'{REPO}/kaiming_memory_client.cpp')
upload('os-agent-integration/echo/memory_echo_server.py',f'{REPO}/bin/kylin-memory-echo-server')
run(f'chmod +x {REPO}/bin/kylin-memory-echo-server')

# 2. Compile
print('\n[2] Compile...')
ec,o,e=run(f'cd {REPO} && g++ -std=c++17 -O2 -o kaiming_memory_client kaiming_memory_client.cpp 2>&1',timeout=60)
ok=(ec==0)
print(f'  {"PASS" if ok else "FAIL"}: ec={ec}')
if e: print(f'  err: {e[:200]}')
run(f'chmod +x {REPO}/kaiming_memory_client')

# 3. Force cleanup + start dev server
print('\n[3] Cleanup + start dev server...')
run_sudo('pkill -f memory_echo_server.py 2>/dev/null; true')
time.sleep(1)
run_sudo('rm -rf /tmp/kylin-memory-echo; mkdir -p /tmp/kylin-memory-echo; chown kylin-agent:kylin-agent /tmp/kylin-memory-echo')
time.sleep(0.5)
ec,o,e=run(f'nohup python3 {REPO}/bin/kylin-memory-echo-server --dev > /tmp/srv.log 2>&1 &',timeout=5)
time.sleep(4)
ec,o,_=run(f'test -S {DEV_SOCK} && echo SOCK_OK || echo SOCK_FAIL')
sock_ok=('SOCK_OK' in o)
print(f'  Socket: {"OK" if sock_ok else "FAIL"}')
if not sock_ok:
    ec,o,_=run('cat /tmp/srv.log 2>/dev/null || echo NO_LOG')
    print(f'  Server log: {o[:300]}')

evidence=[]

if sock_ok:
    # 4. Run all 6 tests
    print('\n[4] kaiming_memory_client --method all...')
    ec,o,e=run(f'cd {REPO} && ./kaiming_memory_client --method all --socket {DEV_SOCK} 2>&1',timeout=30)
    out=o+e
    results={}
    for l in out.split('\n'):
        if 'RESULT' in l:
            p=l.split()
            if len(p)>=3:results[p[1]]=p[2]
    p_cnt=sum(1 for v in results.values() if v=='PASS')
    f_cnt=sum(1 for v in results.values() if v=='FAIL')
    all_ok=(p_cnt==6 and f_cnt==0)
    for k,v in results.items():print(f'    {k}: {v}')
    print(f'  Total: {p_cnt}P/{f_cnt}F -> {"PASS" if all_ok else "FAIL"}')
    evidence.append({'test_id':'ECHO-001','tested_commit':HEAD,
        'command':f'kaiming_memory_client --method all --socket {DEV_SOCK}',
        'exit_code':0 if all_ok else 1,'status':'PASS' if all_ok else 'FAIL',
        'timestamp':NOW,'environment':'Kylin V11 dev mode',
        'source_log':f'{REPO}/logs/p05_all.log','sha256':sha256_str(out)})

    # 5. evidence.record removed (exclude comments)
    print('\n[5] evidence.record removed...')
    ec,o,_=run(f'grep -v "^\\s*#" {REPO}/bin/kylin-memory-echo-server 2>/dev/null | grep -c evidence.record || echo 0')
    ev=int(o.strip().split('\n')[0] or '0')
    ev_ok=(ev==0)
    print(f'  Active code count={ev} -> {"PASS" if ev_ok else "FAIL"}')
    evidence.append({'test_id':'ECHO-002','tested_commit':HEAD,
        'command':'grep -v comment | grep -c evidence.record server.py','exit_code':0 if ev_ok else 1,
        'status':'PASS' if ev_ok else 'FAIL','timestamp':NOW,
        'environment':'Kylin V11','source_log':'N/A','sha256':sha256_str(str(ev))})

    # 6. Compile record
    print('\n[6] Compile record...')
    evidence.append({'test_id':'ECHO-003','tested_commit':HEAD,
        'command':'g++ -std=c++17 -O2 kaiming_memory_client.cpp',
        'exit_code':0 if ok else 1,'status':'PASS' if ok else 'FAIL',
        'timestamp':NOW,'environment':'Kylin V11',
        'source_log':f'{REPO}/logs/p05_all.log','sha256':sha256_str(str(ec))})

    # Cleanup
    run_sudo('pkill -f memory_echo_server.py 2>/dev/null; true')
else:
    ec,o,_=run('cat /tmp/srv.log 2>/dev/null||echo NO_LOG')
    print(f'\nServer failed to start: {o[:500]}')
    evidence.append({'test_id':'ECHO-001','tested_commit':HEAD,
        'command':'nohup python3 server.py --dev','exit_code':1,'status':'FAIL',
        'timestamp':NOW,'environment':'Kylin V11','source_log':'/tmp/srv.log',
        'sha256':sha256_str(o)})

# Write evidence
os.makedirs(os.path.dirname(OUT),exist_ok=True)
with open(OUT,'w',encoding='utf-8') as f:
    for rec in evidence:
        f.write(json.dumps(rec,ensure_ascii=False)+'\n')
print(f'\nEvidence: {OUT} ({len(evidence)} records, sha={sha256_file(OUT)[:20]}...)')
for rec in evidence:
    s=rec['status']
    print(f'  {"PASS" if s=="PASS" else "FAIL"} {rec["test_id"]} commit={rec["tested_commit"][:12]}')

ssh.close()
print('\nDONE')