#!/usr/bin/env python3
"""KYSEC 验证 — 独立执行版本（输出到文件避免终端截断）"""
import sys, os, time, paramiko

LOG_FILE = os.path.join(os.path.dirname(__file__), 'kysec_verify_output.txt')

def log(msg):
    print(msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def exec_cmd(ssh, cmd, timeout=60):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    ec = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return ec, out, err

def main():
    # Clear log
    with open(LOG_FILE, 'w') as f:
        f.write(f'KYSEC Verify started at {time.strftime("%Y-%m-%dT%H:%M:%S")}\n')
    
    results = []
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        log("Connecting to 127.0.0.1:2222 as ZhouYifan...")
        ssh.connect('127.0.0.1', port=2222, username='ZhouYifan', timeout=15,
                     allow_agent=True, look_for_keys=True)
        log("CONNECTED")
        
        # Step 1: CLI check
        log("=== Step 1: CLI check ===")
        for tool in ['kysec_set', 'kysec_get', 'getfattr']:
            ec, out, _ = exec_cmd(ssh, f'which {tool} 2>&1 || echo NOT_FOUND')
            found = 'NOT_FOUND' not in out
            log(f"  {tool}: {'FOUND' if found else 'NOT_FOUND'} -> {out.strip()}")
            results.append((f'CLI_{tool}', 'PASS' if found else 'SKIP'))
        
        # Step 2: Deployment check
        log("=== Step 2: Deployment check ===")
        ec, out, _ = exec_cmd(ssh, 'ls /home/ZhouYifan/kylin-memory-echo/build/echo_client 2>&1 || echo NOT_FOUND')
        deployed = 'NOT_FOUND' not in out
        log(f"  echo_client: {'EXISTS' if deployed else 'NOT_FOUND'}")
        
        if not deployed:
            log("ABORT: echo service not deployed")
            results.append(('DEPLOY', 'FAIL'))
            return 1
        
        results.append(('DEPLOY', 'PASS'))
        
        # Step 3: Status before
        log("=== Step 3: status before ===")
        ec, out, _ = exec_cmd(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh status 2>&1')
        log(out)
        
        # Step 4: Authorize
        log("=== Step 4: authorize ===")
        ec, out, _ = exec_cmd(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh authorize 2>&1')
        log(out)
        results.append(('authorize', 'PASS' if ec == 0 else 'FAIL'))
        
        # Step 5: Verify security.exectl
        log("=== Step 5: Verify security.exectl ===")
        for label, path in [
            ('echo_client', '/home/ZhouYifan/kylin-memory-echo/build/echo_client'),
            ('kaiming_client', '/home/ZhouYifan/kylin-memory-echo/build/kaiming_memory_client'),
        ]:
            ec, out, _ = exec_cmd(ssh, f'sudo getfattr -n security.exectl "{path}" 2>&1 || echo NO_ATTR')
            has_attr = 'security.exectl=' in out
            log(f"  {label}: {'VERIFIED' if has_attr else 'NO ATTR'} -> {out.strip()}")
            results.append((f'attr_{label}', 'PASS' if has_attr else 'FAIL'))
        
        # Step 6: Status after
        log("=== Step 6: status after ===")
        ec, out, _ = exec_cmd(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh status 2>&1')
        log(out)
        
        # Step 7: Rollback
        log("=== Step 7: rollback ===")
        ec, out, _ = exec_cmd(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh rollback 2>&1')
        log(out)
        results.append(('rollback', 'PASS' if ec == 0 else 'FAIL'))
        
        # Step 8: Verify revocation
        log("=== Step 8: Verify revocation ===")
        for label, path in [
            ('echo_client', '/home/ZhouYifan/kylin-memory-echo/build/echo_client'),
            ('kaiming_client', '/home/ZhouYifan/kylin-memory-echo/build/kaiming_memory_client'),
        ]:
            ec, out, _ = exec_cmd(ssh, f'sudo getfattr -n security.exectl "{path}" 2>&1 || echo NO_ATTR')
            has_attr = 'security.exectl=' in out
            log(f"  {label}: {'ATTR_STILL_PRESENT' if has_attr else 'CLEARED_OK'} -> {out.strip()}")
            results.append((f'revoke_{label}', 'PASS' if not has_attr else 'FAIL'))
        
        # Summary
        log("=== SUMMARY ===")
        passed = sum(1 for _, r in results if r == 'PASS')
        skipped = sum(1 for _, r in results if r == 'SKIP')
        failed = sum(1 for _, r in results if r == 'FAIL')
        for name, result in results:
            log(f"  {name}: {result}")
        log(f"  TOTAL: {passed}P / {failed}F / {skipped}S")
        
        return 0 if failed == 0 else 1
        
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        import traceback
        log(traceback.format_exc())
        return 1
    finally:
        ssh.close()
        log(f'Finished at {time.strftime("%Y-%m-%dT%H:%M:%S")}')

if __name__ == '__main__':
    sys.exit(main())