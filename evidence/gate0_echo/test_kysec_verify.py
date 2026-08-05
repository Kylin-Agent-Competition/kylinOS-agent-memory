#!/usr/bin/env python3
"""KYSEC 验证脚本 — 在麒麟VM上验证 kysec_authorize.sh 写入真实规则"""
import sys
import os
import paramiko

# SSH config (from kylin-ssh-connect skill)
VM_HOST = "127.0.0.1"
VM_PORT = 2222
VM_USER = "ZhouYifan"
VM_PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")

def exec_sh(ssh, cmd, timeout=30):
    """Execute command and return (exit_code, stdout, stderr)"""
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

def main():
    if not VM_PASSWORD:
        print("ERROR: KYLIN_VM_PASSWORD environment variable not set")
        return 1
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASSWORD, timeout=15)
    
    results = []
    
    try:
        # === Step 1: Pre-flight check ===
        print("=" * 60)
        print("Step 1: Pre-flight — KYSEC CLI availability")
        print("=" * 60)
        
        for tool in ['kysec_set', 'kysec_get', 'getfattr']:
            ec, out, _ = exec_sh(ssh, f'which {tool} 2>&1 || echo NOT_FOUND')
            found = 'NOT_FOUND' not in out
            print(f"  {tool}: {out.strip()}")
            results.append((f'CLI_{tool}', 'PASS' if found else 'SKIP'))
        
        # === Step 2: Check deployment ===
        print()
        print("=" * 60)
        print("Step 2: Check echo deployment")
        print("=" * 60)
        
        ec, out, _ = exec_sh(ssh, 'ls /home/ZhouYifan/kylin-memory-echo/build/echo_client 2>&1 || echo NOT_FOUND')
        deployed = 'NOT_FOUND' not in out
        print(f"  echo_client: {'EXISTS' if deployed else 'NOT FOUND'}")
        
        ec, out, _ = exec_sh(ssh, 'ls /home/ZhouYifan/kylin-memory-echo/build/kaiming_memory_client 2>&1 || echo NOT_FOUND')
        kaiming_deployed = 'NOT_FOUND' not in out
        print(f"  kaiming_memory_client: {'EXISTS' if kaiming_deployed else 'NOT FOUND'}")
        
        if not deployed:
            print("  ERROR: echo_client not deployed. Skipping KYSEC test.")
            print()
            print("SUMMARY: DEPLOY_NOT_READY — need to install echo service first")
            return 1
        
        # === Step 3: Run status before ===
        print()
        print("=" * 60)
        print("Step 3: Run kysec_authorize.sh status (before)")
        print("=" * 60)
        
        ec, out, _ = exec_sh(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh status 2>&1',
            timeout=30
        )
        print(out)
        
        # === Step 4: Run authorize ===
        print()
        print("=" * 60)
        print("Step 4: Run kysec_authorize.sh authorize")
        print("=" * 60)
        
        ec, out, _ = exec_sh(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh authorize 2>&1',
            timeout=30
        )
        print(out)
        results.append(('authorize', 'PASS' if ec == 0 else 'FAIL'))
        
        # === Step 5: Verify security.exectl attribute ===
        print()
        print("=" * 60)
        print("Step 5: Verify security.exectl extended attribute")
        print("=" * 60)
        
        for label, path in [
            ('echo_client', '/home/ZhouYifan/kylin-memory-echo/build/echo_client'),
            ('kaiming_client', '/home/ZhouYifan/kylin-memory-echo/build/kaiming_memory_client'),
        ]:
            ec, out, _ = exec_sh(ssh, f'sudo getfattr -n security.exectl "{path}" 2>&1 || echo NO_ATTR')
            has_attr = 'security.exectl=' in out
            print(f"  {label}: {'VERIFIED' if has_attr else 'NO ATTR'}")
            print(f"    {out.strip()}")
            results.append((f'attr_{label}', 'PASS' if has_attr else 'FAIL'))
        
        # === Step 6: Run status after ===
        print()
        print("=" * 60)
        print("Step 6: Run kysec_authorize.sh status (after)")
        print("=" * 60)
        
        ec, out, _ = exec_sh(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh status 2>&1',
            timeout=30
        )
        print(out)
        
        # === Step 7: Rollback ===
        print()
        print("=" * 60)
        print("Step 7: Run kysec_authorize.sh rollback")
        print("=" * 60)
        
        ec, out, _ = exec_sh(ssh,
            'KYLIN_ECHO_DEPLOY_BASE=/home/ZhouYifan/kylin-memory-echo '
            'sudo -E bash /home/ZhouYifan/kysec_authorize.sh rollback 2>&1',
            timeout=30
        )
        print(out)
        results.append(('rollback', 'PASS' if ec == 0 else 'FAIL'))
        
        # === Step 8: Verify revocation ===
        print()
        print("=" * 60)
        print("Step 8: Verify KYSEC revocation (security.exectl cleared)")
        print("=" * 60)
        
        for label, path in [
            ('echo_client', '/home/ZhouYifan/kylin-memory-echo/build/echo_client'),
            ('kaiming_client', '/home/ZhouYifan/kylin-memory-echo/build/kaiming_memory_client'),
        ]:
            ec, out, _ = exec_sh(ssh, f'sudo getfattr -n security.exectl "{path}" 2>&1 || echo NO_ATTR')
            has_attr = 'security.exectl=' in out
            print(f"  {label}: {'HAS ATTR (revocation FAILED)' if has_attr else 'CLEARED (revocation OK)'}")
            print(f"    {out.strip()}")
            results.append((f'revoke_{label}', 'PASS' if not has_attr else 'FAIL'))
        
        # === Summary ===
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        passed = sum(1 for _, r in results if r == 'PASS')
        skipped = sum(1 for _, r in results if r == 'SKIP')
        failed = sum(1 for _, r in results if r == 'FAIL')
        for name, result in results:
            marker = chr(0x2705) if result == 'PASS' else (chr(0x26A0) + chr(0xFE0F) if result == 'SKIP' else chr(0x274C))
            print(f"  {marker} {name}: {result}")
        print(f"  TOTAL: {passed}P / {failed}F / {skipped}S")
        
        return 0 if failed == 0 else 1
        
    finally:
        ssh.close()

if __name__ == '__main__':
    sys.exit(main())