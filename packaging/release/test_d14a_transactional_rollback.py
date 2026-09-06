"""D14A 事务化升级回退隔离测试（纯 stdlib，pytest）。

性质：L1（WSL 组件测试）。不依赖真实 SDK、真实 systemd、真实网络、银河麒麟 L2/L3。
方式：把仓库内真实 `packaging/release/systemd_install.sh` 与
`packaging/release/systemd_uninstall.sh` 复制进临时构造的最小发布包（与生产布局一致：
SELF_DIR=包内 systemd/，PKG_DIR=包根），包内提供 venv python/alembic 桩与
`systemd/kylin-memory.service` 模板，用 mock PATH（有状态 systemctl / journalctl /
dpkg-query 桩）+ 临时 HOME/XDG + 预绑定 XDG_RUNTIME_DIR socket + fake SDK 文件
（经 `D14A_SYSTEM_SDK_*` 测试缝接入 install 系统前置校验）驱动真实脚本完整走通
install →（事务化）rollback 全流程。

覆盖（任务验收判据，含历史 Reviewer H-1/M-1/M-2/M-3 收口）：
1. 旧 launcher 为普通文件：install 后事务就位、新 prefix/unit/symlink 就位；
   rollback 后旧 prefix 标记文件字节/hash 一致、旧 unit 字节一致、launcher 恢复为
   普通文件且字节一致，无新 prefix 内容、无事务目录残留。
2. 旧 launcher 为 symlink：rollback 后 readlink 与旧 target 完全一致；prefix/unit
   逐字节一致同上。
3. clean-state 回退语义：无旧状态 → install → rollback → prefix/unit/symlink/事务
   目录全部不存在（等价既有 clean-state smoke 断言）。
4. 恢复失败 fail-closed：install 后将 $UNIT_DST 占位为目录使旧 unit 回写确定性失败
   → rollback 非零退出、stderr 含可诊断错误、旧 unit 备份仍在、事务目录未被删除。
5. 中段失败可恢复性：mock 在 enable 时失败导致 install 非零退出（事务保留）→
   rollback 仍能完整恢复预置旧状态。
6. L0 静态证据：以 subprocess 对四脚本（build_release_package.sh /
   systemd_install.sh / systemd_uninstall.sh / package_smoke.sh）分别执行 `bash -n`
   并断言 exit 0（controller L0 白名单不接受裸 bash -n，故以 pytest 形式提供；
   这仍是 L0 shell 静态证据，不是 L1/Runtime）。
7. H-1：package_smoke.sh 的 upgrade-rollback 场景必须在调用 install/uninstall
   子脚本前 `export INSTALL_PREFIX`（静态顺序断言于真实脚本文本）+ 缺 --prefix 时
   提供清晰诊断（`${INSTALL_PREFIX:-}`，避免 set -u 掩盖 die）；
   `--scenario`/`--old-launcher` 非法值真实退出码 2（行为断言）。
8. M-1：事务最终切换 `mv "$stage" "$TXN_DIR"` 失败（确定性注入）→ install 非零退出、
   可诊断错误，且旧 prefix 已被安全回迁（不丢不毁），无事务/stage 残留。
9. M-2：切换成功但 finalization `chmod 0700 "$TXN_DIR"` 失败（确定性注入）→
   install 非零退出，唯一 backup 保留于事务目录，随后 rollback 仍精确恢复旧状态。
10. M-3：自定义 install prefix 的 clean-state 安装后，rollback 环境不带
    INSTALL_PREFIX → 依 txn.meta 记录路径清理，自定义新 prefix/unit/symlink 无残留。
11. HIGH-1（本恢复任务新增）：双失败注入——“切换 mv 失败（旧 prefix 已被捕获进
    stage）+ 回迁 mv 失败（目标为 INSTALL_PREFIX）”→ install fail-closed 非零退出、
    stage/old-prefix 唯一备份保留且 marker/内容与捕获前字节一致、stderr 报告真实
    retained backup 路径并透传 mv 根因（证明无 2>/dev/null 吞错）、stage 未被 rm -rf。

全部案例使用临时 HOME/XDG/prefix，不接触真实用户 prefix、服务、SDK 或 evidence。

失败注入说明（M-1/M-2/HIGH-1）：与既有 mock systemctl FAIL_ENABLE 故障点同一套隔离缝——
PATH 内 `mv`/`chmod` 转发桩仅在显式 opt-in 环境变量（D14A_FAIL_MV_SWITCH /
D14A_FAIL_MV_RESTORE / D14A_FAIL_CHMOD_TXN）触发时对“精确单操作”失败，其余一律
委托真实工具；断言的是脚本自身的 fail-closed 分支行为，非自证 mock 结果。
"""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
INSTALL_SCRIPT_SRC = TEST_DIR / "systemd_install.sh"
UNINSTALL_SCRIPT_SRC = TEST_DIR / "systemd_uninstall.sh"
SMOKE_SCRIPT_SRC = TEST_DIR / "package_smoke.sh"

PACKAGE_NAME = "kylin-memory-a-d14a"
PACKAGE_VERSION = "0.1.0-d14a"
SOURCE_COMMIT = "a" * 40
SDK_VERSION = "1.2.0.0-0k0.4"
# 包内 manifest 冻结的 SDK identity（完整性 Gate 始终校验冻结常量，不受测试缝影响）
SDK_IDENTITY = {
    "so_path": "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0",
    "version": SDK_VERSION,
    "sha256": "028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48",
}

UNIT_TEMPLATE = (
    b"[Unit]\nDescription=Kylin Memory Service\n"
    b"[Service]\nExecStart=%h/.local/bin/kylin-memory-server\n"
    b"[Install]\nWantedBy=default.target\n"
)

OLD_MARKER = b"KYLIN_D14A_OLD_VERSION marker v1\n"
OLD_UNIT = (
    b"[Unit]\nDescription=Kylin Memory Service (OLD D14A)\n"
    b"[Service]\nExecStart=/bin/true\n[Install]\nWantedBy=default.target\n"
)
OLD_LAUNCHER_FILE = b"#!/usr/bin/env bash\n# D14A old launcher (plain file)\n"

# 最小合格包受管理文件（镜像 build_release_package.sh 布局；venv 桩可执行）
MANAGED_FILES = {
    "runtime/app/app.py": b"print('kylin-memory-d14a')\n",
    "runtime/app/migrations/alembic.ini": b"[alembic]\nscript_location = migrations\n",
    "runtime/bridge/kylin_embedding_cpython312.so": b"\x7fELF-mock-bridge",
    "bin/kylin-memory-server": b"#!/usr/bin/env bash\nexit 0\n",
    "config/config.toml.example": b"[socket]\npath = \"$XDG_RUNTIME_DIR/kylin-memory/memory.sock\"\n",
}

# 包内 venv 桩：python 转发到 PYTHON3；argv 含 `-m alembic` 时执行与 ALEMBIC_STUB
# 等价的 SQLite 写 alembic_version 行为（KYLIN_MEMORY_DB 守卫保留），其余参数转发。
PYTHON_STUB = (
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    'prev=""\n'
    'for a in "$@"; do\n'
    '  if [ "$prev" = "-m" ] && [ "$a" = "alembic" ]; then\n'
    "    db=\"${KYLIN_MEMORY_DB:?KYLIN_MEMORY_DB required}\"\n"
    '    mkdir -p "$(dirname "$db")"\n'
    '    exec "${PYTHON3:?PYTHON3 required}" - "$db" <<'"'"'PYEOF'"'"'\n'
    "import sqlite3, sys\n"
    "db = sys.argv[1]\n"
    "conn = sqlite3.connect(db)\n"
    'conn.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")\n'
    'conn.execute("DELETE FROM alembic_version")\n'
    "conn.execute(\"INSERT INTO alembic_version (version_num) VALUES ('d14a_head')\")\n"
    "conn.commit()\n"
    "print('mock alembic upgrade head: d14a_head')\n"
    "PYEOF\n"
    "  fi\n"
    '  prev="$a"\n'
    "done\n"
    'exec "${PYTHON3:?PYTHON3 required}" "$@"\n'
)
ALEMBIC_STUB = (
    "#!/usr/bin/env bash\n"
    "db=\"${KYLIN_MEMORY_DB:?KYLIN_MEMORY_DB required}\"\n"
    "mkdir -p \"$(dirname \"$db\")\"\n"
    "exec \"${PYTHON3:?}\" - \"$db\" <<'PYEOF'\n"
    "import sqlite3, sys\n"
    "db = sys.argv[1]\n"
    "conn = sqlite3.connect(db)\n"
    "conn.execute(\"CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)\")\n"
    "conn.execute(\"DELETE FROM alembic_version\")\n"
    "conn.execute(\"INSERT INTO alembic_version (version_num) VALUES ('d14a_head')\")\n"
    "conn.commit()\n"
    "print('mock alembic upgrade head: d14a_head')\n"
    "PYEOF\n"
)

EXECUTABLE = {
    "runtime/python/bin/python",
    "runtime/python/bin/alembic",
    "bin/kylin-memory-server",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_package(root: Path) -> Path:
    """构造最小合格发布包：复制真实 install/uninstall 脚本进 systemd/ 并生成清单。"""
    pkg = root / "kylin-memory-a-d14a-0.1.0-d14a"
    pkg.mkdir(parents=True)

    (pkg / "systemd").mkdir(parents=True)
    shutil.copyfile(INSTALL_SCRIPT_SRC, pkg / "systemd" / "install.sh")
    shutil.copyfile(UNINSTALL_SCRIPT_SRC, pkg / "systemd" / "uninstall.sh")
    (pkg / "systemd" / "kylin-memory.service").write_bytes(UNIT_TEMPLATE)

    for rel, data in MANAGED_FILES.items():
        f = pkg / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    # 包内 venv 桩：python 转发到 PYTHON3 并识别 -m alembic；alembic 在临时 DB 上
    # 写入 alembic_version（与 ALEMBIC_STUB 同语义；install 迁移现走模块入口）
    venv_bin = pkg / "runtime" / "python" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text(PYTHON_STUB, encoding="utf-8")
    (venv_bin / "alembic").write_text(ALEMBIC_STUB, encoding="utf-8")
    for rel in EXECUTABLE:
        (pkg / rel).chmod(0o755)
    (pkg / "systemd" / "install.sh").chmod(0o755)
    (pkg / "systemd" / "uninstall.sh").chmod(0o755)

    # 镜像生产构建顺序（build_release_package.sh Phase 2.8 → Phase 3）：VERSION 先于
    # walk 写入成为受管理文件并进入 manifest.files 与 SHA256SUMS；manifest.json/
    # SHA256SUMS 在 walk 后生成且自身不进清单。
    (pkg / "VERSION").write_text(PACKAGE_VERSION + "\n", encoding="utf-8")
    files = {}
    for dirpath, _dirs, fnames in os.walk(pkg):
        for fn in fnames:
            p = Path(dirpath) / fn
            rel = str(p.relative_to(pkg))
            files[rel] = {"size": p.stat().st_size, "sha256": sha256_bytes(p.read_bytes())}

    manifest = {
        "package_name": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "source_commit": SOURCE_COMMIT,
        "built_at": "2026-09-06T00:00:00+00:00",
        "target_os": "银河麒麟桌面 V11 2603 x86_64",
        "target_arch": "amd64",
        "sdk": dict(SDK_IDENTITY),
        "runtime": {"version": "kylin-ai-runtime 1.2.0.4-0k0.1"},
        "model": {"identity": "ensemble-embd_gte-base_uint8-text", "dimension": 768},
        "files": files,
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    sums = "".join("%s  %s\n" % (files[rel]["sha256"], rel) for rel in sorted(files))
    (pkg / "SHA256SUMS").write_text(sums, encoding="utf-8")
    return pkg


class TxnHarness:
    """驱动真实 install/uninstall 脚本的隔离执行环境。

    - 包内脚本：pkg/systemd/install.sh、pkg/systemd/uninstall.sh（生产布局）
    - mock PATH：有状态 systemctl / journalctl / dpkg-query 桩，以及仅 opt-in 触发
      的 mv / chmod 失败注入桩（M-1/M-2/HIGH-1 确定性故障点，默认全部委托真实工具）
    - 预绑定 XDG_RUNTIME_DIR socket；fake SDK 经 D14A_SYSTEM_SDK_* 测试缝接入
    """

    def __init__(self, tmp_path, launcher_kind="file", fail_enable=False):
        self.tmp = Path(tmp_path)
        self.pkg = build_package(self.tmp)
        self.home = self.tmp / "home"
        self.home.mkdir(parents=True)
        self.prefix = self.home / "install-prefix"
        self.mock_bin = self.tmp / "mock-bin"
        self.mock_bin.mkdir(parents=True)
        self.state_file = self.tmp / "systemctl-state"
        if self.state_file.exists():
            self.state_file.unlink()

        self.real_mv = shutil.which("mv")
        self.real_chmod = shutil.which("chmod")
        assert self.real_mv and self.real_chmod, "需要系统 mv/chmod 用于转发桩"

        self._write_stubs()

        # fake SDK 文件（测试缝仅作用于 install 系统前置校验）
        self.sdk_file = self.tmp / "fake-sdk" / "libkysdk-coreai-embedding.so.1.0.0"
        self.sdk_file.parent.mkdir(parents=True)
        self.sdk_file.write_bytes(b"\x7fELF fake kylin embedding SDK\n")
        self.sdk_sha = sha256_bytes(self.sdk_file.read_bytes())

        # 预绑定 XDG_RUNTIME_DIR socket（满足 install 的 socket 检查）
        self.sock_path = self.home / ".runtime" / "kylin-memory" / "memory.sock"
        self.sock_path.parent.mkdir(parents=True)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.sock_path))
        self._sock.listen(1)

        self.launcher_kind = launcher_kind
        self.fail_enable = fail_enable
        self.old_marker_path = self.prefix / "KYLIN_D14A_OLD_VERSION.marker"
        self.unit_path = self.home / ".config" / "systemd" / "user" / "kylin-memory.service"
        self.launcher_path = self.home / ".local" / "bin" / "kylin-memory-server"
        self.old_launcher_target = str(self.tmp / "old-launcher-target-root" / "bin" / "kylin-memory-server")
        self.txn_dir = self.home / ".local" / "state" / "kylin-memory" / "d14a-install-txn"

        self._preset_old_state()
        self.base_env = self._build_env()

    # ── 环境 ──
    def _write_stubs(self) -> None:
        systemctl = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'state_file="${SYSTEMCTL_STATE_FILE:?SYSTEMCTL_STATE_FILE required}"\n'
            # 跳过全局选项（如 --user），取首个非选项参数作为子命令
            'cmd=""; for a in "$@"; do case "$a" in --*) : ;; *) cmd="$a"; break ;; esac; done\n'
            'cur="inactive"\n'
            '[ -f "$state_file" ] && cur="$(cat "$state_file")"\n'
            'case "$cmd" in\n'
            "  stop) echo inactive > \"$state_file\" ;;\n"
            "  disable) echo inactive > \"$state_file\" ;;\n"
            "  daemon-reload) : ;;\n"
            "  enable) [ -z \"${FAIL_ENABLE:-}\" ] || exit 99; echo active > \"$state_file\" ;;\n"
            "  restart) echo active > \"$state_file\" ;;\n"
            "  is-active) [ \"$cur\" = active ] || exit 3 ;;\n"
            '  *) echo "systemctl: unhandled: $cmd" >&2; exit 99 ;;\n'
            "esac\n"
        )
        (self.mock_bin / "systemctl").write_text(systemctl, encoding="utf-8")
        (self.mock_bin / "systemctl").chmod(0o755)
        (self.mock_bin / "journalctl").write_text(
            "#!/usr/bin/env bash\necho \"Memory Service 就绪\"\n", encoding="utf-8"
        )
        (self.mock_bin / "journalctl").chmod(0o755)
        (self.mock_bin / "dpkg-query").write_text(
            "#!/usr/bin/env bash\necho \"${D14A_SYSTEM_SDK_VERSION:-unknown}\"\n", encoding="utf-8"
        )
        (self.mock_bin / "dpkg-query").chmod(0o755)
        # M-1 注入桩：仅当 D14A_FAIL_MV_SWITCH=1 且目标 == D14A_TXN_DIR 且源为
        # 事务暂存目录（d14a-install-txn.stage.*，取倒数第二个参数，规避 -f 等选项）
        # 时失败，其余委托真实 mv。
        # HIGH-1 注入桩：仅当 D14A_FAIL_MV_RESTORE=1 且目标 == D14A_INSTALL_PREFIX
        # 且源为事务暂存目录内 old-prefix（回迁 mv：$stage/old-prefix → $INSTALL_PREFIX）
        # 时失败——与切换失败叠加即为“双失败”（切换 mv 失败 + 回迁 mv 失败）。
        mv_stub = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'args=("$@")\n'
            'last=""; srcprev=""\n'
            'if [ "${#args[@]}" -ge 1 ]; then last="${args[${#args[@]}-1]}"; fi\n'
            'if [ "${#args[@]}" -ge 2 ]; then srcprev="${args[${#args[@]}-2]}"; fi\n'
            'if [ "${D14A_FAIL_MV_SWITCH:-0}" = "1" ] && [ -n "${D14A_TXN_DIR:-}" ] \\\n'
            '   && [ "$last" = "$D14A_TXN_DIR" ] && [ -n "$srcprev" ]; then\n'
            '  case "$srcprev" in\n'
            '    *"/d14a-install-txn.stage."*)\n'
            '      echo "mv: injected failure for transaction switch (dest=$last)" >&2\n'
            "      exit 1\n"
            "      ;;\n"
            "  esac\n"
            "fi\n"
            'if [ "${D14A_FAIL_MV_RESTORE:-0}" = "1" ] && [ -n "${D14A_INSTALL_PREFIX:-}" ] \\\n'
            '   && [ "$last" = "$D14A_INSTALL_PREFIX" ] && [ -n "$srcprev" ]; then\n'
            '  case "$srcprev" in\n'
            '    *"/d14a-install-txn.stage."*"/old-prefix")\n'
            '      echo "mv: injected failure for old-prefix restore (dest=$last)" >&2\n'
            "      exit 1\n"
            "      ;;\n"
            "  esac\n"
            "fi\n"
            'exec "${D14A_REAL_MV:?D14A_REAL_MV required}" "$@"\n'
        )
        (self.mock_bin / "mv").write_text(mv_stub, encoding="utf-8")
        (self.mock_bin / "mv").chmod(0o755)
        # M-2 注入桩：仅当 D14A_FAIL_CHMOD_TXN=1 且目标 == D14A_TXN_DIR 时失败。
        chmod_stub = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'last=""; for a in "$@"; do last="$a"; done\n'
            'if [ "${D14A_FAIL_CHMOD_TXN:-0}" = "1" ] && [ -n "${D14A_TXN_DIR:-}" ] \\\n'
            '   && [ "$last" = "$D14A_TXN_DIR" ]; then\n'
            '  echo "chmod: injected failure for txn dir permission (dest=$last)" >&2\n'
            "  exit 1\n"
            "fi\n"
            'exec "${D14A_REAL_CHMOD:?D14A_REAL_CHMOD required}" "$@"\n'
        )
        (self.mock_bin / "chmod").write_text(chmod_stub, encoding="utf-8")
        (self.mock_bin / "chmod").chmod(0o755)

    def _build_env(self) -> dict:
        return {
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_RUNTIME_DIR": str(self.home / ".runtime"),
            "INSTALL_PREFIX": str(self.prefix),
            "PKG_DIR": str(self.pkg),
            "PYTHON3": sys.executable,
            "PATH": str(self.mock_bin) + os.pathsep + os.environ.get("PATH", ""),
            "SYSTEMCTL_STATE_FILE": str(self.state_file),
            "D14A_SYSTEM_SDK_SO_PATH": str(self.sdk_file),
            "D14A_SYSTEM_SDK_VERSION": SDK_VERSION,
            "D14A_SYSTEM_SDK_SHA256": self.sdk_sha,
            "D14A_REAL_MV": self.real_mv,
            "D14A_REAL_CHMOD": self.real_chmod,
        }

    # ── 预置“旧版本”现场 ──
    def _preset_old_state(self) -> None:
        # 旧 prefix：唯一旧版本标记文件
        self.prefix.mkdir(parents=True, exist_ok=True)
        (self.old_marker_path).write_bytes(OLD_MARKER)
        # 旧 unit
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_bytes(OLD_UNIT)
        # 旧 launcher
        self.launcher_path.parent.mkdir(parents=True, exist_ok=True)
        if self.launcher_kind == "symlink":
            self.launcher_path.symlink_to(self.old_launcher_target)
        else:
            self.launcher_path.write_bytes(OLD_LAUNCHER_FILE)
            self.launcher_path.chmod(0o755)

    # ── 运行 ──
    def run(self, script: Path, args, extra_env=None, drop_env=None) -> subprocess.CompletedProcess:
        env = dict(self.base_env)
        if drop_env:
            for key in drop_env:
                env.pop(key, None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(script)] + list(args),
            env=env,
            capture_output=True,
            text=True,
        )

    def install(self, fail_enable=False, extra_env=None):
        # 预适配 Task2 正式必填语义（EXPECT_SOURCE_COMMIT 缺失 fail-closed）：经既有
        # extra_env 通道显式注入固定合法测试值 SOURCE_COMMIT（非仓库 checkout SHA）；
        # 调用方显式传入的同名键可覆盖 base。
        extra = {"EXPECT_SOURCE_COMMIT": SOURCE_COMMIT}
        if self.fail_enable or fail_enable:
            extra["FAIL_ENABLE"] = "1"
        if extra_env:
            extra.update(extra_env)
        return self.run(self.pkg / "systemd" / "install.sh", ["install"], extra_env=extra)

    def uninstall(self, drop_env=None):
        return self.run(self.pkg / "systemd" / "uninstall.sh", ["rollback"], drop_env=drop_env)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            self.sock_path.unlink()
        except OSError:
            pass

    # ── 断言 ──
    def assert_installed_state(self) -> None:
        assert (self.txn_dir / "txn.meta").is_file(), "install 后应存在 txn.meta"
        assert (self.prefix / "runtime" / "app" / "app.py").is_file(), "新 prefix 应已安装"
        expected_unit = UNIT_TEMPLATE.replace(
            b"%h/.local/bin/kylin-memory-server",
            (str(self.prefix) + "/bin/kylin-memory-server").encode(),
        )
        assert self.unit_path.read_bytes() == expected_unit, "新 unit 应渲染为指向新 prefix"
        assert self.launcher_path.is_symlink(), "install 后 launcher 应为 symlink"
        assert os.readlink(self.launcher_path) == str(self.prefix) + "/bin/kylin-memory-server"

    def assert_restored(self) -> None:
        # 旧 prefix 标记文件字节/hash 一致
        assert self.old_marker_path.read_bytes() == OLD_MARKER, "旧 prefix 标记文件应逐字节恢复"
        assert sha256_bytes(self.old_marker_path.read_bytes()) == sha256_bytes(OLD_MARKER)
        # 旧 unit 字节一致
        assert self.unit_path.read_bytes() == OLD_UNIT, "旧 unit 应逐字节恢复"
        # 旧 launcher 恢复
        if self.launcher_kind == "symlink":
            assert self.launcher_path.is_symlink(), "旧 launcher 应恢复为 symlink"
            assert os.readlink(self.launcher_path) == self.old_launcher_target, \
                "旧 symlink target 应一致"
        else:
            assert not self.launcher_path.is_symlink(), "旧 launcher 应恢复为普通文件"
            assert self.launcher_path.read_bytes() == OLD_LAUNCHER_FILE, \
                "旧 launcher 应逐字节恢复"
        # 无新 prefix 内容残留、无事务目录残留
        assert not (self.prefix / "runtime" / "app" / "app.py").exists(), \
            "回退后不得残留新 prefix 内容"
        assert not self.txn_dir.exists(), "回退后不得残留事务目录"
        assert not (self.home / ".local" / "state" / "kylin-memory" / "d14a-install-txn").exists()


# ─────────────────────────── 0. L0 shell 静态证据（bash -n） ───────────────────────────

def test_shell_syntax_bash_n_release_scripts(tmp_path):
    for name in ("build_release_package.sh", "package_smoke.sh",
                 "systemd_install.sh", "systemd_uninstall.sh"):
        script = TEST_DIR / name
        proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, "bash -n 失败: %s\nstderr=%s" % (name, proc.stderr)


# ─────────────────── 0a. 夹具构建顺序：VERSION 为受管理文件 ───────────────────

def test_rollback_fixture_manifest_includes_version(tmp_path):
    """夹具契约断言（纯 stdlib）：镜像生产构建顺序（Phase 2.8 → Phase 3）后，
    VERSION 先于 walk 写入，必须同时进入 manifest.files 与 SHA256SUMS；
    manifest.json/SHA256SUMS 自身不入清单；VERSION 内容 == PACKAGE_VERSION；
    manifest.files 键集与 SHA256SUMS 文件集双向一致（两侧同步含 VERSION）。"""
    pkg = build_package(tmp_path)
    manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    assert "VERSION" in manifest["files"], "VERSION 应作为受管理文件进入 manifest.files"
    sums = (pkg / "SHA256SUMS").read_text(encoding="utf-8")
    assert any(line.endswith("  VERSION") for line in sums.splitlines()), \
        "SHA256SUMS 应包含 VERSION 行"
    assert "manifest.json" not in manifest["files"], "manifest.json 自身不得入清单"
    assert "SHA256SUMS" not in manifest["files"], "SHA256SUMS 自身不得入清单"
    assert (pkg / "VERSION").read_text(encoding="utf-8").strip() == PACKAGE_VERSION
    sums_files = {line.rsplit("  ", 1)[1] for line in sums.splitlines() if line.strip()}
    assert set(manifest["files"]) == sums_files, "manifest.files 与 SHA256SUMS 应双向一致"


# ─────────────────────────── 1. 旧 launcher 普通文件 ───────────────────────────

def test_old_plain_launcher_full_upgrade_rollback(tmp_path):
    h = TxnHarness(tmp_path, launcher_kind="file")
    try:
        proc = h.install()
        assert proc.returncode == 0, "install 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)
        h.assert_installed_state()

        proc = h.uninstall()
        assert proc.returncode == 0, "rollback 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)
        h.assert_restored()
    finally:
        h.close()


# ─────────────────────────── 2. 旧 launcher symlink ───────────────────────────

def test_old_symlink_launcher_upgrade_rollback(tmp_path):
    h = TxnHarness(tmp_path, launcher_kind="symlink")
    try:
        proc = h.install()
        assert proc.returncode == 0, "install 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)

        proc = h.uninstall()
        assert proc.returncode == 0, "rollback 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)
        assert h.launcher_path.is_symlink(), "旧 launcher 应恢复为 symlink"
        assert os.readlink(h.launcher_path) == h.old_launcher_target, "symlink target 应一致"
        h.assert_restored()
    finally:
        h.close()


# ──────────────────── 3. clean-state 回退语义（无旧状态） ────────────────────

def test_clean_state_rollback_removes_everything(tmp_path):
    h = TxnHarness(tmp_path, launcher_kind="file")
    try:
        # 强制视为“无旧状态”：移除预置旧现场
        shutil.rmtree(h.prefix)
        h.unit_path.unlink()
        h.launcher_path.unlink()

        proc = h.install()
        assert proc.returncode == 0, "install 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)
        assert (h.txn_dir / "txn.meta").is_file(), "clean 安装也应建事务（记录无旧状态）"

        proc = h.uninstall()
        assert proc.returncode == 0, "rollback 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)
        assert not h.prefix.exists(), "回退后 prefix 应不存在"
        assert not h.unit_path.exists(), "回退后 unit 应不存在"
        assert not h.launcher_path.exists(), "回退后 symlink 应不存在"
        assert not h.txn_dir.exists(), "回退后事务目录应不存在"
    finally:
        h.close()


# ──────────────────── 4. 恢复失败 fail-closed ────────────────────

def test_restore_failure_is_fail_closed(tmp_path):
    h = TxnHarness(tmp_path, launcher_kind="file")
    try:
        proc = h.install()
        assert proc.returncode == 0, "install 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)

        # 将新 unit 占位为目录 → 旧 unit 回写确定性失败
        h.unit_path.unlink()
        h.unit_path.mkdir()
        (h.unit_path / "junk").write_text("x", encoding="utf-8")

        proc = h.uninstall()
        assert proc.returncode != 0, "rollback 应 fail-closed 失败"
        assert "无法移除新 unit" in proc.stderr, "stderr 应含可诊断错误:\n%s" % proc.stderr
        # 事务与旧备份保留：旧 unit 备份仍在、事务目录未删除、不静默清理
        old_unit_backup = h.txn_dir / "old-unit"
        assert old_unit_backup.is_file(), "旧 unit 备份应保留"
        assert old_unit_backup.read_bytes() == OLD_UNIT, "旧 unit 备份内容应完好"
        assert h.txn_dir.exists(), "事务目录不得被删除"
        assert (h.txn_dir / "txn.meta").is_file(), "txn.meta 不得被删除"
    finally:
        h.close()


# ──────────────── 5. 安装中段失败，rollback 仍能完整恢复 ────────────────

def test_mid_install_failure_then_rollback_restores(tmp_path):
    h = TxnHarness(tmp_path, launcher_kind="file", fail_enable=True)
    try:
        proc = h.install()
        assert proc.returncode != 0, "mock enable 失败应使 install 非零退出"
        assert "enable --now 失败" in proc.stderr, "stderr 应含 enable 失败:\n%s" % proc.stderr
        # 事务保留：旧 prefix 已搬迁进事务目录，新 prefix 已构建
        assert (h.txn_dir / "old-prefix" / "KYLIN_D14A_OLD_VERSION.marker").is_file(), \
            "中段失败后旧 prefix 备份应保留在事务目录"
        assert (h.prefix / "runtime" / "app" / "app.py").exists(), "新 prefix 应已构建"

        # rollback 仍需完整恢复旧状态（不再注入失败）
        proc = h.uninstall()
        assert proc.returncode == 0, "中段失败后的 rollback 应成功\nstdout=%s\nstderr=%s" % (
            proc.stdout, proc.stderr)
        h.assert_restored()
    finally:
        h.close()


# ──────────────────── 6. H-1：smoke 必须先导出 INSTALL_PREFIX（静态顺序） ────────────────────

def test_smoke_upgrade_rollback_exports_install_prefix_before_child_calls(tmp_path):
    """H-1 闭合：upgrade-rollback 场景调用 install/uninstall 子脚本前必须导出
    INSTALL_PREFIX；缺 --prefix 时必须给出清晰诊断（不得依赖 set -u unbound 报错）。

    该场景本体需真实 SDK/systemd（VM-only），此处对仓库内真实脚本作静态顺序断言，
    属于 L0/L1 层面的真实脚本检查（不升级为 Runtime 证据）。
    """
    text = SMOKE_SCRIPT_SRC.read_text(encoding="utf-8")
    assert "run_upgrade_rollback() {" in text, "缺少 upgrade-rollback 场景函数"
    body_start = text.index("run_upgrade_rollback() {")
    body_end = text.index("\n}\n", body_start)
    body = text[body_start:body_end]

    # L-1：缺 --prefix 的清晰诊断（${INSTALL_PREFIX:-}，set -u 安全）
    assert "${INSTALL_PREFIX:-" in body, "缺 --prefix 时应使用 ${INSTALL_PREFIX:-} 提供清晰诊断"

    # H-1：export 必须在 install/uninstall 子进程调用之前
    install_call = body.index('bash "$PKG_DIR/systemd/install.sh" install')
    uninstall_call = body.index('bash "$PKG_DIR/systemd/uninstall.sh" rollback')
    export_pos = body.index("export INSTALL_PREFIX")
    assert export_pos < install_call, "H-1: 调用 install 子脚本前必须 export INSTALL_PREFIX"
    assert export_pos < uninstall_call, "H-1: 调用 rollback 子脚本前必须 export INSTALL_PREFIX"


def test_smoke_rejects_unknown_scenario_and_old_launcher(tmp_path):
    """package_smoke.sh 参数校验行为断言：非法场景/old-launcher 真实退出码 2。"""
    proc = subprocess.run(
        ["bash", str(SMOKE_SCRIPT_SRC), "--scenario", "bogus"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2, "未知场景应退出 2: rc=%s" % proc.returncode
    assert "未知场景" in proc.stderr, "stderr 应含未知场景诊断:\n%s" % proc.stderr

    proc = subprocess.run(
        ["bash", str(SMOKE_SCRIPT_SRC), "--scenario", "upgrade-rollback", "--old-launcher", "bogus"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2, "未知 old-launcher 应退出 2: rc=%s" % proc.returncode
    assert "未知 old-launcher" in proc.stderr, "stderr 应含未知 old-launcher 诊断:\n%s" % proc.stderr


# ──────────────────── 7. M-1：事务切换失败必须回迁旧 prefix（不销毁） ────────────────────

def test_txn_switch_mv_failure_migrates_back_old_prefix(tmp_path):
    """M-1 闭合：最终切换 `mv "$stage" "$TXN_DIR"` 失败时，install 非零退出且旧
    prefix 被 tx_fail 安全回迁（未 rm -rf 销毁已捕获备份），旧 unit/launcher 原样
    保留，无事务/stage 残留。"""
    h = TxnHarness(tmp_path, launcher_kind="file")
    try:
        proc = h.install(extra_env={"D14A_FAIL_MV_SWITCH": "1", "D14A_TXN_DIR": str(h.txn_dir)})
        assert proc.returncode != 0, "注入 switch mv 失败应使 install 非零退出"
        assert "事务捕获失败" in proc.stderr, "stderr 应含事务捕获失败诊断:\n%s" % proc.stderr

        # 旧 state 未丢失：旧 prefix 已完整回迁到原路径
        assert h.old_marker_path.read_bytes() == OLD_MARKER, "旧 prefix 标记文件应被回迁原样保留"
        assert (h.prefix / "KYLIN_D14A_OLD_VERSION.marker").exists(), "旧 prefix 应回迁到原路径"
        assert h.unit_path.read_bytes() == OLD_UNIT, "旧 unit 应原样保留"
        assert h.launcher_path.read_bytes() == OLD_LAUNCHER_FILE, "旧 launcher 应原样保留"

        # 无残留：事务未创建、stage 已清理、prefix 回迁后为旧状态（无新包内容）
        assert not h.txn_dir.exists(), "切换失败后不得创建事务目录"
        assert not list(h.tmp.glob("**/d14a-install-txn.stage.*")), \
            "stage 暂存目录应被清理"
        assert not (h.prefix / "runtime" / "app" / "app.py").exists(), \
            "回迁后 prefix 不得包含新包内容"
    finally:
        h.close()


# ──────────────────── 8. M-2：finalization 失败必须保留可恢复备份 ────────────────────

def test_txn_finalize_chmod_failure_keeps_backup_and_rollback_recovers(tmp_path):
    """M-2 闭合：切换成功但 finalization `chmod 0700 "$TXN_DIR"` 失败时，install 非零
    退出、唯一 backup（旧 prefix）保留于事务目录（未静默删除），随后 rollback 仍能
    依据 txn.meta 精确恢复旧状态（回迁旧 prefix，无空 prefix 遗留）。"""
    h = TxnHarness(tmp_path, launcher_kind="file")
    try:
        proc = h.install(extra_env={"D14A_FAIL_CHMOD_TXN": "1", "D14A_TXN_DIR": str(h.txn_dir)})
        assert proc.returncode != 0, "注入 TXN_DIR chmod 失败应使 install 非零退出"
        assert "事务捕获失败" in proc.stderr, "stderr 应含事务捕获失败诊断:\n%s" % proc.stderr

        # 唯一 backup 保留（fail-closed，不静默删除）：旧 prefix 备份仍在事务目录
        assert (h.txn_dir / "old-prefix" / "KYLIN_D14A_OLD_VERSION.marker").is_file(), \
            "M-2: 旧 prefix 唯一备份必须保留在事务目录"
        meta = (h.txn_dir / "txn.meta").read_text(encoding="utf-8")
        assert "OLD_PREFIX_BACKUP=present" in meta, "txn.meta 应记录旧 prefix 已捕获"

        # 事务可由 rollback 完整恢复（不再注入失败）
        proc = h.uninstall()
        assert proc.returncode == 0, "M-2: 失败后的 rollback 应成功\nstdout=%s\nstderr=%s" % (
            proc.stdout, proc.stderr)
        h.assert_restored()
    finally:
        h.close()


# ──────────────────── 9. M-3：无旧状态清理必须使用 TXN 记录路径 ────────────────────

def test_custom_prefix_no_old_state_rollback_without_env_removes_new_prefix(tmp_path):
    """M-3 闭合：clean-state（事务记录无旧状态）rollback 必须使用 txn.meta 记录的
    TXN_INSTALL_PREFIX/TXN_UNIT_PATH/TXN_BIN_SYMLINK_PATH 路径清理；自定义 install
    prefix 后 rollback 环境不带 INSTALL_PREFIX 时也不得遗留新 prefix。"""
    h = TxnHarness(tmp_path, launcher_kind="file")
    try:
        # 视为“无旧状态”（clean-state），但 prefix 为自定义路径（非默认）
        shutil.rmtree(h.prefix)
        h.unit_path.unlink()
        h.launcher_path.unlink()

        proc = h.install()
        assert proc.returncode == 0, "install 应成功\nstdout=%s\nstderr=%s" % (proc.stdout, proc.stderr)
        assert (h.txn_dir / "txn.meta").is_file(), "应建事务（记录无旧状态）"
        assert (h.prefix / "runtime" / "app" / "app.py").exists(), "自定义 prefix 应已安装新包"

        # M-3：rollback 环境不携带 INSTALL_PREFIX（自定义 prefix 仅记录于 txn.meta）
        proc = h.uninstall(drop_env=["INSTALL_PREFIX"])
        assert proc.returncode == 0, "M-3: rollback 应成功\nstdout=%s\nstderr=%s" % (
            proc.stdout, proc.stderr)
        assert not h.prefix.exists(), "M-3: 自定义新 prefix 必须依 TXN 记录路径清理"
        assert not h.unit_path.exists(), "M-3: unit 应被清理"
        assert not h.launcher_path.exists(), "M-3: symlink 应被清理"
        assert not h.txn_dir.exists(), "M-3: 事务目录应被清理"
    finally:
        h.close()


# ────────────── 10. HIGH-1：切换 mv 失败 + 回迁 mv 失败（双失败）fail-closed ──────────────

def test_dual_failure_switch_and_restore_keeps_unique_backup(tmp_path):
    """HIGH-1 闭合：新 prefix 切换失败且旧 prefix 回迁 mv 亦失败时，systemd_install.sh
    必须 fail-closed——非零退出、保留 stage/old-prefix 唯一备份（marker/内容与捕获前
    字节/hash 一致）、诊断报告真实 retained backup 路径、mv 根因错误透传至 stderr
    （证明无 2>/dev/null 吞错）、stage 未被 rm -rf。

    注入语义（真实脚本 + PATH 替身）：捕获 mv（$INSTALL_PREFIX → $stage/old-prefix）
    成功；一切目标为 $INSTALL_PREFIX 的 mv（含切换后回迁 old-prefix）确定性失败并输出
    真实 mv 风格错误、退出 1；切换 mv（$stage → $TXN_DIR）同样失败。两处注入均为
    精确单操作匹配，其余操作委托真实 mv。"""
    h = TxnHarness(tmp_path, launcher_kind="file")
    try:
        proc = h.install(extra_env={
            "D14A_FAIL_MV_SWITCH": "1",
            "D14A_TXN_DIR": str(h.txn_dir),
            "D14A_FAIL_MV_RESTORE": "1",
            "D14A_INSTALL_PREFIX": str(h.prefix),
        })
        # 1) 非零退出（fail-closed）
        assert proc.returncode != 0, "双失败注入应使 install 非零退出"
        assert "事务捕获失败" in proc.stderr, "stderr 应含事务捕获失败诊断:\n%s" % proc.stderr

        # 2) 回迁 mv 失败根因透传（无 2>/dev/null 吞错）
        assert "old-prefix restore" in proc.stderr, \
            "stderr 应透传回迁 mv 根因错误（2>/dev/null 已移除）:\n%s" % proc.stderr
        # 3) CRITICAL 诊断指向真实 retained backup 路径
        assert "CRITICAL" in proc.stderr, "stderr 应含 CRITICAL 诊断:\n%s" % proc.stderr
        assert "唯一备份保留于" in proc.stderr, \
            "CRITICAL 应报告真实保留的 backup 路径:\n%s" % proc.stderr

        # 4) stage/old-prefix 唯一备份保留（stage 未被 rm -rf 销毁）
        stages = list(h.tmp.glob("**/d14a-install-txn.stage.*"))
        assert stages, "双失败后 stage 暂存目录必须保留（不得 rm -rf）"
        stage = stages[0]
        backup_dir = stage / "old-prefix"
        assert backup_dir.is_dir(), "stage/old-prefix 备份目录应存在"
        # 5) backup marker/content 与捕获前字节一致（cmp/hash）
        marker_backup = backup_dir / "KYLIN_D14A_OLD_VERSION.marker"
        assert marker_backup.is_file(), "旧 prefix 标记文件应保留在备份目录"
        assert marker_backup.read_bytes() == OLD_MARKER, "marker 应逐字节一致"
        assert sha256_bytes(marker_backup.read_bytes()) == sha256_bytes(OLD_MARKER), \
            "marker hash 应一致"
        # 6) 唯一 backup 未被删除：旧 prefix 原路径仍不存在（未部分回迁），
        #    原现场只能保留于 stage/old-prefix
        assert not h.prefix.exists(), "双失败后旧 prefix 不得出现在原路径（回迁失败）"

        # 7) 回迁失败时不得删除唯一 backup：stage 目录本身仍完整存在
        assert stage.is_dir(), "stage 目录应完整保留"
        assert list(stage.iterdir()), "stage 内不应为空（txn.meta/old-prefix 等应保留）"
    finally:
        h.close()
