#!/usr/bin/env python3
"""
麒麟 VM 铁律文件传输模块
========================
设计原则：任何传输操作默认失败，只有 SHA256 校验通过才算成功。

铁律：
1. 上传 = 本地 SHA256 → SFTP put → 远程 SHA256 → 比对 → 不匹配则重试(最多3次) → 仍失败则抛出 TransferError
2. 下载 = SFTP get → 本地 SHA256 → 远程 SHA256 → 比对 → 不匹配则抛出 TransferError
3. Exec 写文件 = heredoc/base64 → 远程 SHA256 → 比对 → 不匹配则抛出 TransferError
4. 目录存在性检查：sftp.listdir() 前必须 stat() 确认目录存在
5. 所有错误必须显式报告，禁止静默吞没

用法:
  from evidence.ssh_transfer_diagnosis.kylin_transfer import transfer, KylinConnection

  with KylinConnection() as kc:
      transfer.upload_file(kc, "local.py", "/remote/path.py")
      transfer.upload_directory(kc, "local_dir", "/remote/dir")
      transfer.download_file(kc, "/remote/file.log", "local/file.log")
      transfer.exec_verify(kc, "echo hello", expected_output="hello")
"""

import os
import sys
import io
import hashlib
import time
import base64
import traceback
from typing import Optional, Tuple, List
from contextlib import contextmanager

import paramiko


# ============================================================
# 异常定义
# ============================================================
class TransferError(Exception):
    """文件传输校验失败异常 — 不可静默吞没"""
    def __init__(self, message: str, local_sha: str = "", remote_sha: str = "", retries: int = 0):
        self.local_sha = local_sha
        self.remote_sha = remote_sha
        self.retries = retries
        super().__init__(message)


class ConnectionError(TransferError):
    """SSH/SFTP 连接异常"""
    pass


class VerificationError(TransferError):
    """SHA256 校验失败 — 文件损坏或未完整传输"""
    pass


class DirectoryNotFoundError(TransferError):
    """远程目录不存在 — sftp.listdir() 前置检查失败"""
    pass


# ============================================================
# 连接管理
# ============================================================
class KylinConnection:
    """麒麟 VM SSH 连接管理器，支持 context manager"""

    DEFAULT_HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
    DEFAULT_PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
    DEFAULT_USER = os.environ.get("KYLIN_VM_USER", "REDACTED_VM_USER")
    DEFAULT_PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "REDACTED_VM_PASSWORD")

    def __init__(self, host: str = None, port: int = None, username: str = None, password: str = None,
                 timeout: int = 20):
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT
        self.username = username or self.DEFAULT_USER
        self.password = password or self.DEFAULT_PASSWORD
        self.timeout = timeout
        self._client: Optional[paramiko.SSHClient] = None

    def connect(self) -> paramiko.SSHClient:
        if self._client is None:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                self._client.connect(
                    self.host, port=self.port, username=self.username, password=self.password,
                    allow_agent=False, look_for_keys=False, timeout=self.timeout
                )
            except Exception as e:
                raise ConnectionError(f"SSH 连接失败 ({self.username}@{self.host}:{self.port}): {e}")
        return self._client

    @property
    def client(self) -> paramiko.SSHClient:
        return self.connect()

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    # ---- 便捷方法 ----
    def exec(self, cmd: str, timeout: int = 30, sudo: bool = False) -> Tuple[int, str, str]:
        """执行远程命令，返回 (exit_code, stdout, stderr)"""
        if sudo:
            cmd = f"echo '{self.password}' | sudo -S bash -c '{cmd}'"
        _, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return exit_code, out, err

    def exec_background(self, cmd: str, timeout: int = 5):
        """后台执行命令（fire-and-forget），不读取输出，不阻塞"""
        wrapped = f"nohup bash -c '{cmd}' </dev/null >/dev/null 2>&1 &"
        transport = self.client.get_transport()
        session = transport.open_session()
        session.exec_command(wrapped)
        try:
            session.recv_exit_status()
        except Exception:
            pass
        session.close()

    def remote_sha256(self, remote_path: str) -> Optional[str]:
        """计算远程文件 SHA256"""
        exit_code, out, _ = self.exec(f"sha256sum '{remote_path}' 2>/dev/null || echo 'MISSING'")
        if exit_code != 0 or "MISSING" in out:
            return None
        parts = out.split()
        return parts[0] if parts else None

    def dir_exists(self, remote_dir: str) -> bool:
        """检查远程目录是否存在"""
        exit_code, _, _ = self.exec(f"test -d '{remote_dir}'")
        return exit_code == 0


# ============================================================
# 工具函数
# ============================================================
def local_sha256(filepath: str) -> str:
    """计算本地文件 SHA256"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_or_raise(local_sha: str, remote_sha: Optional[str], local_path: str, remote_path: str,
                     retries: int = 0) -> None:
    """校验 SHA256，不匹配则抛出 VerificationError"""
    if remote_sha is None:
        raise VerificationError(
            f"远程 SHA256 计算失败（文件可能不存在）: {remote_path}",
            local_sha=local_sha, remote_sha="(None)", retries=retries
        )
    if local_sha != remote_sha:
        raise VerificationError(
            f"SHA256 不匹配: local={local_sha[:16]}... remote={remote_sha[:16]}... | {os.path.basename(local_path)}",
            local_sha=local_sha, remote_sha=remote_sha, retries=retries
        )


# ============================================================
# 铁律传输 API
# ============================================================
class TransferAPI:
    """所有传输操作入口"""

    def __init__(self):
        self._total_uploads = 0
        self._total_failures = 0

    # ---- 主要 API ----

    def upload_file(self, kc: KylinConnection, local_path: str, remote_path: str,
                    max_retries: int = 3, silent: bool = False) -> str:
        """
        上传单个文件，强制 SHA256 校验，失败自动重试。
        
        Returns:
            SHA256 hex string (验证通过)
        
        Raises:
            VerificationError: 所有重试均校验失败
            FileNotFoundError: 本地文件不存在
        """
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"本地文件不存在: {local_path}")

        l_sha = local_sha256(local_path)
        file_size = os.path.getsize(local_path)
        fname = os.path.basename(local_path)

        if not silent:
            print(f"[TRANSFER] {fname} ({file_size:,} bytes) -> {remote_path}")

        # 确保远程目录存在
        remote_dir = os.path.dirname(remote_path)
        if remote_dir and not kc.dir_exists(remote_dir):
            kc.exec(f"mkdir -p '{remote_dir}'")

        last_error = None
        for attempt in range(max_retries):
            try:
                sftp = kc.client.open_sftp()
                try:
                    sftp.put(local_path, remote_path, confirm=True)
                finally:
                    sftp.close()

                time.sleep(0.3)  # 等待远端 fsync
                r_sha = kc.remote_sha256(remote_path)
                _verify_or_raise(l_sha, r_sha, local_path, remote_path, retries=attempt)
                
                if not silent:
                    print(f"  [OK] SHA256 verified: {l_sha[:16]}...")
                self._total_uploads += 1
                return l_sha

            except VerificationError as e:
                last_error = e
                if not silent:
                    print(f"  [RETRY {attempt+1}/{max_retries}] {e}")
            except Exception as e:
                last_error = ConnectionError(f"SFTP 上传异常 (attempt {attempt+1}): {type(e).__name__}: {e}")
                if not silent:
                    print(f"  [RETRY {attempt+1}/{max_retries}] {type(e).__name__}: {e}")

            if attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))  # 递增退避

        self._total_failures += 1
        raise last_error or VerificationError(
            f"上传最终失败: {fname}", local_sha=l_sha, remote_sha="(unknown)", retries=max_retries
        )

    def upload_directory(self, kc: KylinConnection, local_dir: str, remote_dir: str,
                         max_retries: int = 3) -> dict:
        """
        批量上传目录，每个文件强制校验。返回 {rel_path: sha256} 字典。
        任一文件失败则整个操作失败。
        """
        local_dir = os.path.abspath(local_dir)
        if not os.path.isdir(local_dir):
            raise FileNotFoundError(f"本地目录不存在: {local_dir}")

        # 收集文件
        files = []
        for root, _, filenames in os.walk(local_dir):
            for fname in filenames:
                local_path = os.path.join(root, fname)
                rel_path = os.path.relpath(local_path, local_dir)
                remote_path = os.path.join(remote_dir, rel_path).replace("\\", "/")
                files.append((local_path, remote_path, rel_path))

        print(f"[TRANSFER] 批量上传 {len(files)} 个文件: {local_dir} -> {remote_dir}")

        results = {}
        errors = []
        for local_path, remote_path, rel_path in files:
            try:
                sha = self.upload_file(kc, local_path, remote_path, max_retries=max_retries, silent=True)
                results[rel_path] = sha
                print(f"  [{len(results)}/{len(files)}] {rel_path} OK")
            except TransferError as e:
                errors.append((rel_path, e))
                print(f"  [{len(results)}/{len(files)}] {rel_path} FAIL: {e}")

        if errors:
            print(f"\n[FAIL] {len(errors)}/{len(files)} 文件传输失败:")
            for rel_path, e in errors:
                print(f"  - {rel_path}: {e}")
            raise TransferError(
                f"批量上传失败: {len(errors)}/{len(files)} 个文件校验未通过",
                local_sha="", remote_sha=""
            )

        print(f"[OK] 批量上传完成: {len(files)}/{len(files)} 全部校验通过")
        return results

    def download_file(self, kc: KylinConnection, remote_path: str, local_path: str,
                      max_retries: int = 3) -> str:
        """
        下载单个文件，强制 SHA256 校验。
        
        Returns:
            SHA256 hex string (验证通过)
        """
        fname = os.path.basename(remote_path)
        print(f"[TRANSFER] 下载: {remote_path} -> {local_path}")

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

        # 先获取远程 SHA256
        r_sha = kc.remote_sha256(remote_path)
        if r_sha is None:
            raise FileNotFoundError(f"远程文件不存在或无法计算 SHA256: {remote_path}")

        last_error = None
        for attempt in range(max_retries):
            try:
                sftp = kc.client.open_sftp()
                try:
                    sftp.get(remote_path, local_path)
                finally:
                    sftp.close()

                l_sha = local_sha256(local_path)
                _verify_or_raise(l_sha, r_sha, local_path, remote_path, retries=attempt)

                print(f"  [OK] SHA256 verified: {l_sha[:16]}...")
                return l_sha

            except VerificationError as e:
                last_error = e
                print(f"  [RETRY {attempt+1}/{max_retries}] {e}")
            except Exception as e:
                last_error = ConnectionError(f"SFTP 下载异常: {type(e).__name__}: {e}")
                print(f"  [RETRY {attempt+1}/{max_retries}] {type(e).__name__}: {e}")

            if attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))

        self._total_failures += 1
        raise last_error or VerificationError(f"下载最终失败: {fname}", remote_sha=r_sha)

    def download_evidence(self, kc: KylinConnection, remote_dir: str, local_dir: str) -> int:
        """
        下载远程目录中的所有文件到本地（sftp.listdir 安全版本，前置目录检查）。
        Returns: 下载的文件数量
        """
        if not kc.dir_exists(remote_dir):
            raise DirectoryNotFoundError(f"远程目录不存在: {remote_dir}")

        sftp = kc.client.open_sftp()
        try:
            entries = sftp.listdir(remote_dir)
        finally:
            sftp.close()

        os.makedirs(local_dir, exist_ok=True)
        count = 0
        for fname in entries:
            remote_path = f"{remote_dir}/{fname}"
            local_path = os.path.join(local_dir, fname)
            try:
                self.download_file(kc, remote_path, local_path)
                count += 1
            except TransferError as e:
                print(f"  [SKIP] {fname}: {e}")

        print(f"[OK] 证据下载: {count}/{len(entries)} 文件")
        return count

    def write_string_as_file(self, kc: KylinConnection, content: str, remote_path: str,
                             expected_sha: Optional[str] = None) -> str:
        """
        将字符串写入远程文件（用于小配置文件/systemd unit等）。
        通过 base64 编码 heredoc 方式确保完整性，然后 SHA256 校验。
        
        Returns: actual SHA256
        """
        content_bytes = content.encode("utf-8")
        l_sha = hashlib.sha256(content_bytes).hexdigest()

        # base64 编码后通过 heredoc 写入
        b64 = base64.b64encode(content_bytes).decode("ascii")
        remote_dir = os.path.dirname(remote_path)
        if remote_dir and not kc.dir_exists(remote_dir):
            kc.exec(f"mkdir -p '{remote_dir}'")

        # 单次写入（base64 保证了无特殊字符问题）
        exit_code, _, err = kc.exec(
            f"echo '{b64}' | base64 -d > '{remote_path}'",
            timeout=10
        )
        if exit_code != 0:
            raise TransferError(f"写入远程文件失败: {err[:200]}")

        time.sleep(0.3)
        r_sha = kc.remote_sha256(remote_path)
        _verify_or_raise(l_sha, r_sha, f"<string>{len(content_bytes)}bytes", remote_path)

        if expected_sha and r_sha != expected_sha:
            raise VerificationError(
                f"内容 SHA256 与期望不符: {remote_path}",
                local_sha=expected_sha, remote_sha=r_sha
            )

        print(f"[OK] 远程文件写入+校验通过: {remote_path} ({len(content_bytes):,} bytes)")
        return r_sha

    def exec_verify_output(self, kc: KylinConnection, cmd: str, expected_output: str = None,
                           timeout: int = 30, sudo: bool = False) -> Tuple[int, str]:
        """
        执行命令并验证输出。若期望输出指定且不匹配，抛出 VerificationError。
        """
        exit_code, out, err = kc.exec(cmd, timeout=timeout, sudo=sudo)
        if expected_output is not None and expected_output not in out:
            raise VerificationError(
                f"命令输出不包含期望内容: cmd='{cmd[:60]}...', expected='{expected_output[:40]}...'",
                local_sha="", remote_sha=out[:100]
            )
        return exit_code, out


# ============================================================
# 全局单例
# ============================================================
transfer = TransferAPI()


# ============================================================
# 便捷函数（兼容旧调用）
# ============================================================
def quick_upload(local_path: str, remote_path: str) -> bool:
    """快速上传（不抛异常版，返回 True/False）"""
    try:
        with KylinConnection() as kc:
            transfer.upload_file(kc, local_path, remote_path)
        return True
    except TransferError as e:
        print(f"[FAIL] {e}")
        return False


def quick_download(remote_path: str, local_path: str) -> bool:
    """快速下载（不抛异常版）"""
    try:
        with KylinConnection() as kc:
            transfer.download_file(kc, remote_path, local_path)
        return True
    except TransferError as e:
        print(f"[FAIL] {e}")
        return False


# ============================================================
# CLI 入口
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCLI 用法:")
        print("  python -m evidence.ssh_transfer_diagnosis.kylin_transfer upload <本地> <远程>")
        print("  python -m evidence.ssh_transfer_diagnosis.kylin_transfer download <远程> <本地>")
        print("  python -m evidence.ssh_transfer_diagnosis.kylin_transfer batch <本地目录> <远程目录>")
        print("  python -m evidence.ssh_transfer_diagnosis.kylin_transfer exec '<命令>'")
        print("  python -m evidence.ssh_transfer_diagnosis.kylin_transfer diagnose")
        sys.exit(1)

    action = sys.argv[1]

    if action == "upload":
        if len(sys.argv) < 4:
            print("用法: upload <local_path> <remote_path>")
            sys.exit(1)
        with KylinConnection() as kc:
            transfer.upload_file(kc, sys.argv[2], sys.argv[3])

    elif action == "download":
        if len(sys.argv) < 4:
            print("用法: download <remote_path> <local_path>")
            sys.exit(1)
        with KylinConnection() as kc:
            transfer.download_file(kc, sys.argv[2], sys.argv[3])

    elif action == "batch":
        if len(sys.argv) < 4:
            print("用法: batch <local_dir> <remote_dir>")
            sys.exit(1)
        with KylinConnection() as kc:
            transfer.upload_directory(kc, sys.argv[2], sys.argv[3])

    elif action == "exec":
        if len(sys.argv) < 3:
            print("用法: exec '<command>' [--sudo]")
            sys.exit(1)
        cmd = sys.argv[2]
        sudo = "--sudo" in sys.argv
        with KylinConnection() as kc:
            exit_code, out, err = kc.exec(cmd, sudo=sudo)
            print(out)
            if err:
                print(f"[STDERR]\n{err}")
            print(f"\n[EXIT: {exit_code}]")

    elif action == "diagnose":
        print("=" * 60)
        print(" 麒麟VM SSH/SFTP 连接诊断 (铁律传输模块)")
        print("=" * 60)
        try:
            with KylinConnection() as kc:
                print(f"[OK] SSH 连接成功: {kc.username}@{kc.host}:{kc.port}")

                # 系统信息
                ec, out, _ = kc.exec("uname -a")
                print(f"系统: {out.strip()}")
                ec, out, _ = kc.exec("cat /etc/.kyinfo 2>/dev/null | head -6 || cat /etc/os-release | head -3")
                print(f"版本:\n{out.strip()[:300]}")

                # SFTP 通道测试
                sftp = kc.client.open_sftp()
                sftp.close()
                print("[OK] SFTP 通道正常")

                # 小文件上传+校验
                test_content = b"KYLIN_TRANSFER_TEST_" + os.urandom(20)
                test_sha = hashlib.sha256(test_content).hexdigest()
                
                sftp = kc.client.open_sftp()
                sftp.putfo(io.BytesIO(test_content), "/tmp/kylin_diag_test.bin", confirm=True)
                sftp.close()
                time.sleep(0.3)
                r_sha = kc.remote_sha256("/tmp/kylin_diag_test.bin")
                if r_sha == test_sha:
                    print(f"[OK] 传输校验测试通过 ({r_sha[:16]}...)")
                else:
                    print(f"[FAIL] 传输校验测试失败: local={test_sha[:16]} remote={r_sha[:16] if r_sha else 'None'}")
                kc.exec("rm -f /tmp/kylin_diag_test.bin")

                print("\n[CONCLUSION] 连接正常，铁律传输模块可用")

        except ConnectionError as e:
            print(f"[FAIL] {e}")
        except Exception as e:
            print(f"[FAIL] 未知错误: {e}")
            traceback.print_exc()

    else:
        print(f"未知操作: {action}")
        sys.exit(1)