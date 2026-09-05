"""D14A 发布包 Python runtime 可重定位恢复专项测试（纯 stdlib，pytest）。

性质：L1（WSL 组件测试）。仅使用临时目录/mock 真实工具，不依赖真实 SDK、真实
systemd、真实网络、银河麒麟 L2/L3。

目的（PR152 D14A R3）：
- 生产迁移统一使用 <runtime python> -m alembic 模块入口，发布包内不再调用
  `runtime/python/bin/alembic` console-script（其 shebang 携带构建期绝对路径
  /tmp/kylin-d14a-build-venv/bin/python，不可重定位）。
- 构建 venv 在包内 migration smoke 前删除，由 smoke 证明模块入口不依赖构建路径。
- runtime/python/bin 常规文件必须 fail-closed 扫描构建 venv 绝对路径。
- 本文件独立证明以上语义（不复用 transactional fake fixture），并承担
  bash -n / git diff --check 等价 L0 静态检查。

覆盖：
1. 静态：两个生产脚本（build_release_package.sh / systemd_install.sh）无
   console-script 调用；迁移调用为模块入口；构建 venv 删除命令先于 smoke 行；
   残留扫描存在且残留分支 fail-closed（die）。
2. 行为（临时树，镜像 build 脚本 tar 复制 + venv 删除）：
   - 构建 venv 删除后 `python -m alembic -c migrations/alembic.ini upgrade head`
     迁移成功并写入 alembic_version（fake alembic 模块，仅证明调用路径）。
   - “已安装 prefix”副本上 install 模块入口（-m alembic）与 launcher 模块入口
     （-m app 输出 marker）均可用。
   - 复刻残留扫描命令：有残留 → 检出非空；清理后 → 空（且 python symlink 不误报）。
3. L0：bash -n 两脚本；git diff --check 等价检查（4 个目标文件：无行尾空白、
   无冲突标记、以换行结尾）。
"""

import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
BUILD_SCRIPT = TEST_DIR / "build_release_package.sh"
INSTALL_SCRIPT = TEST_DIR / "systemd_install.sh"

TARGET_FILES = (
    "build_release_package.sh",
    "systemd_install.sh",
    "test_d14a_transactional_rollback.py",
    "test_d14a_relocatable_runtime.py",
)

# 与 build_release_package.sh Phase 2.5 heredoc 一致的可重定位 launcher（行为验证用）
LAUNCHER = (
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    'SELF="$(cd "$(dirname "$0")/.." && pwd)"\n'
    'export PYTHONPATH="$SELF/runtime/app:$SELF/runtime/bridge"\n'
    'exec "$SELF/runtime/python/bin/python" -m app "$@"\n'
)

APP_MARKER = "kylin-memory-d14a-relocatable"

# fake alembic 模块（-m alembic 的模块入口；仅证明调用路径与 DB 写语义，
# 不等价真实 Alembic 行为，与 transactional fixture 的 DB 写语义一致）
FAKE_ALEMBIC_MAIN = (
    "import os, sqlite3\n"
    'db = os.environ["KYLIN_MEMORY_DB"]\n'
    "conn = sqlite3.connect(db)\n"
    'conn.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")\n'
    'conn.execute("DELETE FROM alembic_version")\n'
    "conn.execute(\"INSERT INTO alembic_version (version_num) VALUES ('d14a_head')\")\n"
    "conn.commit()\n"
    "print('relocatable fake alembic upgrade head: d14a_head')\n"
)


def tar_copy_tree(src: Path, dst: Path) -> None:
    """镜像 build 脚本 `tar -C "$BUILD_VENV" -cf - . | tar -C ... -xf -`。"""
    dst.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        tar.add(str(src), arcname=".")
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        tar.extractall(str(dst))


def build_mock_build_venv(root: Path, py) -> Path:
    """模拟构建期 venv：python/python3 symlink → 真实 python；alembic/pip 常规文件
    携带构建 venv 绝对路径（模拟构建期 console-script shebang 残留）。"""
    venv = root / "kylin-d14a-build-venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").symlink_to(py)
    (bin_dir / "python3").symlink_to(py)
    (bin_dir / "alembic").write_text(
        "#!/%s/bin/python\nimport sys\nprint('mock console-script')\n" % venv,
        encoding="utf-8",
    )
    (bin_dir / "pip").write_text(
        "#!/%s/bin/python\n# mock pip console-script\n" % venv, encoding="utf-8"
    )
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    return venv


def build_mock_app(dist: Path) -> Path:
    """镜像发布包 runtime/app 布局 + fake alembic 模块（-m alembic 可导入）。"""
    app_dir = dist / "runtime" / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "app.py").write_text("print('%s')\n" % APP_MARKER, encoding="utf-8")
    mig = app_dir / "migrations"
    mig.mkdir(parents=True)
    (mig / "alembic.ini").write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    alembic_pkg = app_dir / "alembic"
    alembic_pkg.mkdir()
    (alembic_pkg / "__init__.py").write_text("", encoding="utf-8")
    (alembic_pkg / "__main__.py").write_text(FAKE_ALEMBIC_MAIN, encoding="utf-8")
    return app_dir


def run_module_migrate(python_bin: Path, app_dir: Path, db: Path, extra_env=None):
    """复刻迁移调用：`<runtime python> -m alembic -c migrations/alembic.ini upgrade head`。"""
    env = dict(os.environ)
    env.update({"KYLIN_MEMORY_DB": str(db), "PYTHONPATH": str(app_dir)})
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(python_bin), "-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        cwd=str(app_dir),
        env=env,
        capture_output=True,
        text=True,
    )


def read_db_version(db: Path):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        conn.close()


# ─────────────────────── 1. 静态：模块入口 + 可重定位守卫 ───────────────────────

def test_production_scripts_use_module_entry_only(tmp_path):
    """两个生产脚本不得再调用 runtime/python/bin/alembic console-script；
    迁移一律使用 <runtime python> -m alembic 模块入口。"""
    build = BUILD_SCRIPT.read_text(encoding="utf-8")
    install = INSTALL_SCRIPT.read_text(encoding="utf-8")

    # 1) 无 console-script 调用（模块入口恢复的核心）
    assert '"$DIST/runtime/python/bin/alembic"' not in build, \
        "build_release_package.sh 不得调用 bin/alembic console-script"
    assert '"$INSTALL_PREFIX/runtime/python/bin/alembic"' not in install, \
        "systemd_install.sh 不得调用 bin/alembic console-script"
    assert 'bin/alembic"' not in build, "build 脚本不得出现任何 bin/alembic 调用"
    assert 'bin/alembic"' not in install, "install 脚本不得出现任何 bin/alembic 调用"

    # 2) 迁移调用为模块入口
    assert '"$DIST/runtime/python/bin/python" -m alembic -c migrations/alembic.ini upgrade head' in build, \
        "build smoke 应为 <runtime python> -m alembic 模块入口"
    assert '"$INSTALL_PREFIX/runtime/python/bin/python"' in install, \
        "install 迁移应使用 runtime/python/bin/python"
    assert "-m alembic -c migrations/alembic.ini upgrade head" in install, \
        "install 迁移应为 -m alembic 模块入口"


def test_build_venv_deleted_before_smoke_and_residue_scan_fail_closed(tmp_path):
    """构建 venv 必须在包内 smoke 前删除；runtime/python/bin 常规文件的构建路径
    残留扫描必须存在且残留时 fail-closed（die）。"""
    build = BUILD_SCRIPT.read_text(encoding="utf-8")

    # 1) 删除/重命名构建 venv 的命令先于 smoke 行
    del_idx = build.index('rm -rf "$BUILD_VENV"')
    smoke_idx = build.index('"$DIST/runtime/python/bin/python" -m alembic -c migrations/alembic.ini upgrade head')
    assert del_idx < smoke_idx, "构建 venv 删除必须发生在包内 smoke 之前"

    # 2) 残留扫描（常规文件）存在
    assert 'grep -rlF "$BUILD_VENV" "$DIST/runtime/python/bin"' in build, \
        "必须对 runtime/python/bin 常规文件执行构建路径残留扫描"

    # 3) 残留分支 fail-closed（die 并列出残留）
    assert 'die "runtime/python/bin 仍残留构建 venv 路径' in build, \
        "残留扫描必须 fail-closed（die 并列出残留文件）"


# ─────────────────────── 2. 行为：venv 删除后模块迁移独立 ───────────────────────

def test_migration_works_after_build_venv_removal(tmp_path):
    """构建 venv 删除后，`python -m alembic` 模块入口迁移仍成功写入 DB——
    证明运行入口不依赖构建期路径（可重定位的核心语义）。"""
    py = sys.executable
    venv = build_mock_build_venv(tmp_path, py)
    dist = tmp_path / "dist"
    app_dir = build_mock_app(dist)

    # 镜像 build 脚本 2.4：tar 复制 venv → runtime/python
    tar_copy_tree(venv, dist / "runtime" / "python")
    assert (dist / "runtime" / "python" / "bin" / "python").is_symlink(), \
        "venv bin/python 应为 symlink（tar 保留符号链接）"

    # 镜像 Phase 2.9 前置：删除构建 venv
    shutil.rmtree(venv)
    assert not venv.exists(), "构建 venv 必须已被删除"

    # smoke 语义：模块入口迁移写入 DB
    db = tmp_path / "migrate.db"
    proc = run_module_migrate(dist / "runtime" / "python" / "bin" / "python", app_dir, db)
    assert proc.returncode == 0, "venv 删除后 -m alembic 迁移应成功\nstdout=%s\nstderr=%s" % (
        proc.stdout, proc.stderr)
    assert read_db_version(db) == [("d14a_head",)], "迁移应写入 alembic_version=d14a_head"
    assert "relocatable fake alembic upgrade head" in proc.stdout, \
        "模块入口应执行 fake alembic 模块\nstdout=%s" % proc.stdout


def test_installed_prefix_module_entry_and_launcher(tmp_path):
    """“已安装 prefix”副本：install 模块入口（-m alembic）与 launcher 模块入口
    （-m app 输出 marker）均可用，进一步证明整包可重定位。"""
    py = sys.executable
    venv = build_mock_build_venv(tmp_path, py)
    dist = tmp_path / "dist"
    app_dir = build_mock_app(dist)
    tar_copy_tree(venv, dist / "runtime" / "python")
    shutil.rmtree(venv)

    # 镜像 systemd_install.sh 第 3 步：整包 tar 复制到 install_prefix（tar 保留符号链接）
    prefix = tmp_path / "install-prefix"
    tar_copy_tree(dist, prefix)

    # install 模块入口
    db2 = tmp_path / "installed.db"
    proc = run_module_migrate(
        prefix / "runtime" / "python" / "bin" / "python",
        prefix / "runtime" / "app",
        db2,
    )
    assert proc.returncode == 0, "install 模块入口迁移应成功\nstdout=%s\nstderr=%s" % (
        proc.stdout, proc.stderr)
    assert read_db_version(db2) == [("d14a_head",)], "install 迁移应写入 alembic_version"

    # launcher 模块入口（bin/kylin-memory-server → runtime/python/bin/python -m app）
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "kylin-memory-server"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    launcher.chmod(0o755)
    proc = subprocess.run([str(launcher)], capture_output=True, text=True)
    assert proc.returncode == 0, "launcher 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)
    assert APP_MARKER in proc.stdout, "launcher 应通过 -m app 输出 app marker\nstdout=%s" % proc.stdout


# ─────────────────────── 3. 行为：残留扫描检出与清理（复刻脚本命令） ───────────────────────

def test_residue_scan_detects_and_cleans(tmp_path):
    """复刻 build 脚本 2.4.1/2.4.2 残留扫描命令：有残留 → 检出非空（常规文件）；
    清理后 → 空；python/python3 symlink 不误报。"""
    py = sys.executable
    venv = build_mock_build_venv(tmp_path, py)
    dist = tmp_path / "dist"
    build_mock_app(dist)
    tar_copy_tree(venv, dist / "runtime" / "python")
    bin_dir = dist / "runtime" / "python" / "bin"
    needle = str(venv)

    # 2.4.2 语义：grep -rlF（常规文件；grep -r 不跟随 symlink）
    proc = subprocess.run(["grep", "-rlF", needle, str(bin_dir)], capture_output=True, text=True)
    assert proc.returncode == 0, "有残留时 grep 应命中（exit 0）"
    assert proc.stdout, "有残留时扫描应检出非空"
    assert "bin/alembic" in proc.stdout and "bin/pip" in proc.stdout, \
        "应检出携带构建路径的常规文件\nstdout=%s" % proc.stdout
    assert "bin/python" not in proc.stdout, "python symlink 不得被误报为残留"

    # 2.4.1 语义：NUL 分隔删除匹配的常规文件
    proc_z = subprocess.run(["grep", "-rlZF", needle, str(bin_dir)], capture_output=True, text=True)
    assert proc_z.returncode == 0
    for f in [x for x in proc_z.stdout.split("\0") if x]:
        (bin_dir / f).unlink()

    # 2.4.2 二次扫描：清理后为空（grep 无匹配 exit 1，脚本侧以 || true 守卫）
    proc2 = subprocess.run(["grep", "-rlF", needle, str(bin_dir)], capture_output=True, text=True)
    assert proc2.returncode == 1 and not proc2.stdout.strip(), \
        "清理后二次扫描应为空（fail-closed 通过）"

    # symlink 仍完好（仅清理常规文件）
    assert (bin_dir / "python").is_symlink(), "python symlink 应保留"
    assert (bin_dir / "python3").is_symlink(), "python3 symlink 应保留"


# ─────────────────────────────── 4. L0 静态检查 ───────────────────────────────

def test_bash_n_release_scripts(tmp_path):
    for name in ("build_release_package.sh", "systemd_install.sh"):
        script = TEST_DIR / name
        proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, "bash -n 失败: %s\nstderr=%s" % (name, proc.stderr)


def test_git_diff_check_equivalent(tmp_path):
    """git diff --check 等价检查（controller L0 不执行直接 git 白名单外的命令）：
    4 个目标文件无行尾空白、无冲突标记、以换行结尾。"""
    for name in TARGET_FILES:
        text = (TEST_DIR / name).read_text(encoding="utf-8")
        assert text.endswith("\n"), "%s 应以换行结尾" % name
        for lineno, line in enumerate(text.splitlines(), 1):
            assert not line.endswith((" ", "\t")), \
                "%s:%d 存在行尾空白" % (name, lineno)
            assert not line.startswith(("<<<<<<<", ">>>>>>>", "=======")), \
                "%s:%d 存在冲突标记" % (name, lineno)
