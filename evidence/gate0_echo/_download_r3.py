#!/usr/bin/env python3
"""Download R3 test results and print summary"""
import paramiko, os

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('127.0.0.1', port=2222, username='kylin-agent', password='***REMOVED_PASSWORD***', timeout=10)
s = c.open_sftp()

local_dir = os.path.join(os.path.dirname(__file__), 'day2_results')
remote_files = ['/tmp/r3_result.txt', '/tmp/r3_done.flag']

for rf in remote_files:
    try:
        st = s.stat(rf)
        lf = os.path.join(local_dir, os.path.basename(rf))
        s.get(rf, lf)
        print(f'OK: {rf} ({st.st_size} bytes) -> {lf}')
    except Exception as e:
        print(f'FAIL: {rf} -> {e}')

# Also download latest lifecycle log
logs_dir = '/home/kylin-agent/kylin-memory-echo/logs'
try:
    entries = s.listdir(logs_dir)
    matched = [e for e in entries if e.startswith('systemd_test_')]
    if matched:
        matched.sort(reverse=True)
        latest = f'{logs_dir}/{matched[0]}'
        st = s.stat(latest)
        lf = os.path.join(local_dir, '_R3_LIFECYCLE.log')
        s.get(latest, lf)
        print(f'OK: {latest} ({st.st_size} bytes) -> {lf}')
except Exception as e:
    print(f'FAIL lifecycle log: {e}')

s.close()
c.close()

# Now analyze downloaded file
result_file = os.path.join(local_dir, 'r3_result.txt')
if os.path.exists(result_file):
    with open(result_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract pass/fail
    import re
    pass_m = re.search(r'\u901a\u8fc7:\s*(\d+)', content)
    fail_m = re.search(r'\u5931\u8d25:\s*(\d+)', content)
    
    summary_lines = []
    summary_lines.append('=== R3 Result Summary ===')
    if pass_m and fail_m:
        summary_lines.append(f'Pass: {pass_m.group(1)}, Fail: {fail_m.group(1)}')
    
    # Check Step 8
    if '\u5df2\u786e\u8ba4\u6ce8\u9500\u670d\u52a1' in content:
        summary_lines.append('Step 11: PASS (systemd confirmed unregistered)')
    else:
        summary_lines.append('Step 11: CHECK NEEDED')
    
    # Check Step 8 patterns
    if 'UDS echo \u901a\u8fc7' in content or 'UDS echo PASS' in content:
        summary_lines.append('Step 8 echo: PASS')
    else:
        summary_lines.append('Step 8 echo: CHECK (may have used fallback)')
    
    if 'UDS health \u901a\u8fc7' in content or 'UDS health PASS' in content:
        summary_lines.append('Step 8 health: PASS')
    else:
        summary_lines.append('Step 8 health: CHECK')
    
    # Last 10 lines
    lines = content.strip().split('\n')
    summary_lines.append(f'')
    summary_lines.append('=== Last 15 lines ===')
    for l in lines[-15:]:
        summary_lines.append(l[:150])
    
    summary_path = os.path.join(local_dir, '_R3_SUMMARY.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary_lines))
    print(f'Summary: {summary_path}')
    for sl in summary_lines:
        print(sl)
else:
    print('No result file found - test may still be running or failed')