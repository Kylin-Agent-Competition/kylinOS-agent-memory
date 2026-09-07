"""D14A verify/smoke fail-closed 语义隔离测试（纯 stdlib，pytest）。

性质：L1（WSL 组件测试，确定性、可重复）。不依赖真实 SDK、真实 systemd、真实网络、
银河麒麟 L2/L3。方式：以 subprocess 真实执行仓库内 `packaging/release/`
systemd_verify.sh 与 package_smoke.sh，用 mock PATH（systemctl / ss 桩）与临时
HOME/XDG + 真实 bound Unix socket 构造隔离执行环境，驱动脚本的 fail-closed 负向
分支：
  - verify：holder PID 无法解析、holder PID != MainPID、缺 --embed-pid；
  - smoke：clean/upgrade-rollback 缺 --prefix、EXPECT_SOURCE_COMMIT 缺失/非法格式。
全部断言非零退出与可诊断 stderr，并证明无 UID-fallback 式"替代成功"路径。

mock 结果仅用于证明脚本自身的 fail-closed 分支行为（非自证 mock 结果），绝不作为
runtime evidence；L2/L3（systemd/D-Bus/真实 SDK 在银河麒麟环境的验证）保持
RUNTIME_UNVERIFIED。
"""

import os
import socket
import subprocess
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
VERIFY_SCRIPT = TEST_DIR / "systemd_verify.sh"
SMOKE_SCRIPT = TEST_DIR / "package_smoke.sh"

# 隔离 fixture（明确非当前 checkout / 非正式包 hash）
VERIFY_MAIN_PID = "4242"
HOLDER_PID_MISMATCH = "9999"

# 环境继承键：测试前一律剔除，避免宿主机环境变量污染导致"缺失即失败"用例失真
INHERITED_KEYS = (
    "INSTALL_PREFIX",
    "EXPECT_SOURCE_COMMIT",
    "PKG_DIR",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "XDG_STATE_HOME",
)


def _clean_env(tmp_path, mock_bin=None, extra=None):
    env = dict(os.environ)
    for key in INHERITED_KEYS:
        env.pop(key, None)
    env["HOME"] = str(tmp_path / "home")
    env["XDG_RUNTIME_DIR"] = str(tmp_path / ".runtime")
    if mock_bin is not None:
        env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    if extra:
        env.update(extra)
    return env


def _write_verify_stubs(mock_bin):
    # systemctl 桩：is-active → 0；show -p MainPID --value → $VERIFY_MAIN_PID
    systemctl = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'for a in "$@"; do\n'
        "  case \"$a\" in\n"
        "    is-active) exit 0 ;;\n"
        "    show) printf '%s\\n' \"${VERIFY_MAIN_PID:?VERIFY_MAIN_PID required}\"; exit 0 ;;\n"
        "  esac\n"
        "done\n"
        "exit 0\n"
    )
    (mock_bin / "systemctl").write_text(systemctl, encoding="utf-8")
    (mock_bin / "systemctl").chmod(0o755)

    # ss 桩：输出 $VERIFY_SS_OUTPUT 原样内容（可注入空输出或含 pid=9999 的行）
    ss = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s" "${VERIFY_SS_OUTPUT:-}"\n'
    )
    (mock_bin / "ss").write_text(ss, encoding="utf-8")
    (mock_bin / "ss").chmod(0o755)


def _bind_memory_socket(runtime_dir):
    """在临时 XDG_RUNTIME_DIR 下绑定真实 Unix socket（满足 verify 的 socket 存在性检查）。"""
    sock_path = Path(runtime_dir) / "kylin-memory" / "memory.sock"
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(sock_path))
    s.listen(1)
    return s, sock_path


def _close_socket(s, sock_path):
    try:
        s.close()
    except OSError:
        pass
    try:
        sock_path.unlink()
    except OSError:
        pass


# ─────────────────────────── 0. L0 shell 静态证据（bash -n） ───────────────────────────

def test_shell_syntax_bash_n_verify_and_smoke():
    for script in (VERIFY_SCRIPT, SMOKE_SCRIPT):
        proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, "bash -n 失败: %s\nstderr=%s" % (script.name, proc.stderr)


# ─────────────────────────── 1. 静态契约断言（真实脚本文本） ───────────────────────────

def test_smoke_exports_expect_source_commit_before_install_calls():
    """EXPECT_SOURCE_COMMIT 必须显式传递/导出且在 install 子进程调用之前
    （原样传递语义；clean 与 upgrade 两条路径均被该前置校验覆盖）。"""
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    first_install = text.index('bash "$PKG_DIR/systemd/install.sh" install')
    export_pos = text.index("export EXPECT_SOURCE_COMMIT")
    assert export_pos < first_install, "调用 install 前必须 export EXPECT_SOURCE_COMMIT（原样传递）"
    assert "EXPECT_SOURCE_COMMIT" in text
    assert "[0-9a-f]{40}" in text, "应包含 40 位十六进制格式校验"


def test_verify_no_uid_fallback_success_path_and_embed_pid_required():
    """verify 不得存在 UID 一致替代 holder PID 比对的成功路径；--embed-pid 必填。"""
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert 'if [ -n "$HOLDER_PID" ]' not in text, "不得存在 holder PID 空值短路"
    assert "无法解析 socket holder PID" in text, "缺失 holder PID 解析失败诊断"
    assert "!= systemd MainPID" in text, "缺失 holder PID 精确比对诊断"
    assert "--embed-pid 必填" in text, "缺失 --embed-pid 必填校验"
    assert 'if [ -n "$EMBED_PID" ]; then' not in text, "maps/hash Gate 不得被条件包裹跳过"


# ─────────────────────────── 2. verify 负向 fail-closed（mock PATH + 临时目录） ───────────────────────────

def test_verify_missing_embed_pid_fails_closed(tmp_path):
    """缺 --embed-pid：早期必填校验，非零退出；不得跳过 SDK maps/hash Gate。"""
    env = _clean_env(tmp_path, extra={"INSTALL_PREFIX": str(TEST_DIR.parent.resolve())})
    proc = subprocess.run(
        ["bash", str(VERIFY_SCRIPT), "--embed-socket", "/tmp/unused.sock"],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode != 0, "缺 --embed-pid 必须 fail-closed: rc=%s" % proc.returncode
    assert "--embed-pid 必填" in proc.stderr, "stderr 应含必填诊断:\n%s" % proc.stderr
    assert "PASS" not in proc.stdout, "不得出现 PASS（maps/hash Gate 不得被跳过）"


def test_verify_holder_pid_unparseable_fails_closed(tmp_path):
    """ss 输出无法解析出 socket holder PID（ss 桩注入空输出）→ 非零 fail-closed，
    不得以 socket/proc UID 一致作为解析失败的成功替代。"""
    mock_bin = tmp_path / "mock-bin"
    mock_bin.mkdir(exist_ok=True)
    _write_verify_stubs(mock_bin)
    runtime_dir = tmp_path / ".runtime"
    runtime_dir.mkdir(parents=True)
    s, sock_path = _bind_memory_socket(runtime_dir)
    try:
        env = _clean_env(tmp_path, mock_bin=mock_bin, extra={
            "INSTALL_PREFIX": str(TEST_DIR.parent.resolve()),
            "VERIFY_MAIN_PID": VERIFY_MAIN_PID,
            "VERIFY_SS_OUTPUT": "",
        })
        proc = subprocess.run(
            ["bash", str(VERIFY_SCRIPT),
             "--embed-socket", "/tmp/unused.sock", "--embed-pid", VERIFY_MAIN_PID],
            env=env, capture_output=True, text=True,
        )
    finally:
        _close_socket(s, sock_path)
    assert proc.returncode != 0, "holder PID 无法解析必须 fail-closed"
    assert "无法解析 socket holder PID" in proc.stderr, \
        "stderr 应含 holder PID 解析失败诊断:\n%s" % proc.stderr
    # 不得以 socket/proc UID 一致替代 holder PID 比对成功：holder 比对 PASS 与 ALL PASS 均不得出现
    assert "socket holder = MainPID" not in proc.stdout, "不得以 UID 一致替代 holder PID 比对成功"
    assert "ALL PASS" not in proc.stdout, "不得以 UID 一致替代 holder PID 比对成功"


def test_verify_holder_pid_mismatch_mainpid_fails_closed(tmp_path):
    """ss 输出解析出 holder PID=9999 != systemctl MainPID=4242 → 非零 fail-closed，
    精确相等比对生效。"""
    mock_bin = tmp_path / "mock-bin"
    mock_bin.mkdir(exist_ok=True)
    _write_verify_stubs(mock_bin)
    runtime_dir = tmp_path / ".runtime"
    runtime_dir.mkdir(parents=True)
    s, sock_path = _bind_memory_socket(runtime_dir)
    sock_full = str(sock_path)
    ss_output = (
        'u_str LISTEN 0 4096 %s 4242 users:(("kylin-memory-server",pid=%s,fd=15))\n'
        % (sock_full, HOLDER_PID_MISMATCH)
    )
    try:
        env = _clean_env(tmp_path, mock_bin=mock_bin, extra={
            "INSTALL_PREFIX": str(TEST_DIR.parent.resolve()),
            "VERIFY_MAIN_PID": VERIFY_MAIN_PID,
            "VERIFY_SS_OUTPUT": ss_output,
        })
        proc = subprocess.run(
            ["bash", str(VERIFY_SCRIPT),
             "--embed-socket", "/tmp/unused.sock", "--embed-pid", VERIFY_MAIN_PID],
            env=env, capture_output=True, text=True,
        )
    finally:
        _close_socket(s, sock_path)
    assert proc.returncode != 0, "holder PID != MainPID 必须 fail-closed"
    assert "!= systemd MainPID" in proc.stderr, \
        "stderr 应含 MainPID 精确比对诊断:\n%s" % proc.stderr
    # holder 比对 PASS 与 ALL PASS 均不得出现（精确比对生效，无替代成功路径）
    assert "socket holder = MainPID" not in proc.stdout, "holder PID 比对不得 PASS"
    assert "ALL PASS" not in proc.stdout, "verify 不得 ALL PASS"


# ─────────────────────────── 3. smoke 负向 fail-closed（干净 env + 临时目录） ───────────────────────────

def _run_smoke(tmp_path, args, extra_env=None):
    env = _clean_env(tmp_path)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SMOKE_SCRIPT)] + args,
        env=env, capture_output=True, text=True,
    )


def test_smoke_clean_missing_prefix_fails_closed(tmp_path):
    """clean 场景缺 --prefix：非零 fail-closed，不得回退真实用户默认安装前缀。"""
    proc = _run_smoke(tmp_path, ["--scenario", "clean"])
    assert proc.returncode != 0, "clean 缺 --prefix 必须 fail-closed: rc=%s" % proc.returncode
    assert "需要显式 --prefix" in proc.stderr, "stderr 应含 --prefix 必填诊断:\n%s" % proc.stderr


def test_smoke_upgrade_rollback_missing_prefix_fails_closed(tmp_path):
    """upgrade-rollback 场景缺 --prefix：非零 fail-closed（显式 --old-launcher 合法值）。"""
    proc = _run_smoke(tmp_path, ["--scenario", "upgrade-rollback", "--old-launcher", "symlink"])
    assert proc.returncode != 0, "upgrade-rollback 缺 --prefix 必须 fail-closed: rc=%s" % proc.returncode
    assert "需要显式 --prefix" in proc.stderr, "stderr 应含 --prefix 必填诊断:\n%s" % proc.stderr


def test_smoke_missing_expect_source_commit_fails_closed(tmp_path):
    """显式 --prefix 但缺 EXPECT_SOURCE_COMMIT：非零 fail-closed（缺失即失败）。"""
    prefix = tmp_path / "iso-prefix"
    proc = _run_smoke(tmp_path, ["--prefix", str(prefix)])
    assert proc.returncode != 0, "缺 EXPECT_SOURCE_COMMIT 必须 fail-closed: rc=%s" % proc.returncode
    assert "EXPECT_SOURCE_COMMIT" in proc.stderr, "stderr 应含必填诊断:\n%s" % proc.stderr


def test_smoke_invalid_expect_source_commit_fails_closed(tmp_path):
    """EXPECT_SOURCE_COMMIT 传入错误值（非法格式 deadbeef，非 40 位十六进制）：
    非零 fail-closed（不得据此推断值或放行 install）。"""
    prefix = tmp_path / "iso-prefix"
    proc = _run_smoke(tmp_path, ["--prefix", str(prefix), "--expect-source-commit", "deadbeef"])
    assert proc.returncode != 0, "非法 EXPECT_SOURCE_COMMIT 必须 fail-closed: rc=%s" % proc.returncode
    assert "非法" in proc.stderr and "EXPECT_SOURCE_COMMIT" in proc.stderr, \
        "stderr 应含格式校验诊断:\n%s" % proc.stderr