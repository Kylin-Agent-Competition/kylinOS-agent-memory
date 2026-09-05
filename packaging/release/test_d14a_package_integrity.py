"""D14A 发布包完整性 Gate 隔离测试（纯 stdlib，pytest）。

性质：L1（WSL 组件测试）。不依赖真实 SDK、真实 systemd、真实网络、银河麒麟 L2/L3。
方式：在临时目录构造最小合格发布包（含 VERSION / manifest.json / SHA256SUMS 与少量
受管理常规文件），把仓库内真实 `packaging/release/systemd_install.sh` 复制为包内
`systemd/install.sh`（与生产布局一致：SELF_DIR=包内 systemd/，PKG_DIR=包根），
用 mock PATH（前置 stub `systemctl`/`alembic`/`journalctl`，调用即写 marker 并失败）
与临时 HOME/INSTALL_PREFIX 驱动安装脚本。

覆盖（任务验收判据）：
1. 未篡改包 `_integrity-gate` 返回 0（PASS）；
2. 未篡改包 `install` 先 PASS 完整性 Gate，随后在 SDK 前置检查处停止（无副作用）；
3. 任一受管理文件被修改（SHA256SUMS 未同步）→ FAIL，且发生在复制/迁移/systemd 之前
   （INSTALL_PREFIX 未创建、mock systemctl/alembic 从未被调用、HOME 无污染）;
4. 任一受管理文件被删除 → FAIL；
5. systemd unit 篡改 → FAIL；包内 install 脚本篡改 → FAIL；
6. SHA256SUMS 语法异常：空清单 / 重复路径 / 绝对路径 / 路径穿越 → 全部 FAIL；
7. 双向不一致：SHA256SUMS 多余条目 / manifest 多余条目 / manifest 缺失条目 → FAIL；
8. 文件内容修改但 SHA256SUMS 已同步（manifest 未同步）→ FAIL；
9. manifest identity 不一致：package_name / source_commit / sdk 冻结值 / VERSION 内容 → FAIL。

所有 FAIL 案例均断言返回码非 0 且「无副作用顺序」成立。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
INSTALL_SCRIPT_SRC = TEST_DIR / "systemd_install.sh"

PACKAGE_NAME = "kylin-memory-a-d14a"
PACKAGE_VERSION = "0.1.0-d14a"
SOURCE_COMMIT = "a" * 40
SDK_IDENTITY = {
    "so_path": "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0",
    "version": "1.2.0.0-0k0.4",
    "sha256": "028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48",
}

# 最小合格包的受管理常规文件（全部进入 manifest.files 与 SHA256SUMS，镜像构建侧
# 生成逻辑：先 walk 磁盘，manifest.json / SHA256SUMS 在建时尚未存在、天然不进入清单）。
MANAGED_FILES = {
    "runtime/python/bin/python": b"#!/bin/sh\nexit 0\n",
    "runtime/app/app.py": b"print('kylin-memory-d14a')\n",
    "runtime/app/migrations/alembic.ini": b"[alembic]\nscript_location = migrations\n",
    "runtime/bridge/kylin_embedding_cpython312.so": b"\x7fELF-mock-bridge",
    "bin/kylin-memory-server": b"#!/usr/bin/env bash\nexit 0\n",
    "systemd/kylin-memory.service": b"[Unit]\nDescription=Kylin Memory Service\n",
    "config/config.toml.example": b"[socket]\npath = \"$XDG_RUNTIME_DIR/kylin-memory/memory.sock\"\n",
}

EXECUTABLE = {
    "runtime/python/bin/python",
    "bin/kylin-memory-server",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_package(root: Path, *, tamper=None) -> Path:
    """构造最小合格包；tamper 为可选的回调 (pkg_dir) -> None 用于事后篡改。

    布局镜像生产构建（Phase 2.7 先复制 systemd 脚本，Phase 3 再 walk 生成清单）：
    systemd/install.sh 是受管理常规文件，位于 manifest.files / SHA256SUMS 内。
    """
    pkg = Path(root) / "kylin-memory-a-d14a-0.1.0-d14a"
    pkg.mkdir(parents=True)

    # 受管理文件：真实 install 脚本先进入包内 systemd/（生产 Phase 2.7 同序）
    (pkg / "systemd").mkdir(parents=True)
    shutil.copyfile(INSTALL_SCRIPT_SRC, pkg / "systemd" / "install.sh")

    for rel, data in MANAGED_FILES.items():
        f = pkg / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    for rel in EXECUTABLE:
        (pkg / rel).chmod(0o755)
    (pkg / "systemd" / "install.sh").chmod(0o755)

    # 镜像构建侧：先 walk 磁盘计算 files（manifest.json/SHA256SUMS 尚不存在）
    files = {}
    for dirpath, _dirs, fnames in os.walk(pkg):
        for fn in fnames:
            p = Path(dirpath) / fn
            rel = str(p.relative_to(pkg))
            files[rel] = {
                "size": p.stat().st_size,
                "sha256": sha256_bytes(p.read_bytes()),
            }

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
    (pkg / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (pkg / "VERSION").write_text(PACKAGE_VERSION + "\n", encoding="utf-8")
    sums = "".join("%s  %s\n" % (files[rel]["sha256"], rel) for rel in sorted(files))
    (pkg / "SHA256SUMS").write_text(sums, encoding="utf-8")

    if tamper is not None:
        tamper(pkg)
    return pkg


def rewrite(root: Path, rel: str, data: bytes) -> None:
    """覆盖受管理文件内容但不更新 SHA256SUMS/manifest（模拟非同步篡改）。"""
    (root / rel).write_bytes(data)


def rmfile(root: Path, rel: str) -> None:
    (root / rel).unlink()


def parse_sum_lines(text: str):
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        yield parts[0], parts[1]


def install_script_rel(root: Path) -> Path:
    return root / "systemd" / "install.sh"


def run_install(pkg: Path, home: Path, mode: str = "install"):
    """以 mock PATH + 临时 HOME/INSTALL_PREFIX 驱动完整性 Gate。

    执行仓库内的真实 install 脚本，并通过 PKG_DIR 环境变量把完整性 Gate 指向
    临时构造的发布包（生产布局下 PKG_DIR 由 systemd/install.sh 的 SELF_DIR 推导，
    此处用测试缝显式覆盖，使篡改包内 install 脚本副本也能被真实 Gate 检出）。

    返回 (returncode, stdout, stderr, marker_path, prefix_path)。
    """
    mock_bin = pkg.parent / "mock-bin"
    mock_bin.mkdir(exist_ok=True)
    marker = pkg.parent / "mock-called.marker"
    if marker.exists():
        marker.unlink()

    stub = (
        "#!/usr/bin/env bash\n"
        'echo "$(basename "$0")" >> "{}"\n'
        "exit 99\n"
    ).format(marker)
    for name in ("systemctl", "alembic", "journalctl"):
        (mock_bin / name).write_text(stub)
        (mock_bin / name).chmod(0o755)

    prefix = home / "install-prefix"
    env = {
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_RUNTIME_DIR": str(home / ".runtime"),
        "INSTALL_PREFIX": str(prefix),
        "PKG_DIR": str(pkg),
        "PYTHON3": sys.executable,
        "PATH": str(mock_bin) + os.pathsep + os.environ.get("PATH", ""),
        "MOCK_MARKER": str(marker),
    }
    proc = subprocess.run(
        ["bash", str(INSTALL_SCRIPT_SRC), mode],
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr, marker, prefix


def assert_no_side_effects(marker: Path, prefix: Path, home: Path) -> None:
    """断言失败发生在复制/迁移/systemd 之前：无前缀目录、mock 从未被调用、HOME 无安装产物。"""
    assert not prefix.exists(), "INSTALL_PREFIX 已被创建（完整性失败不应产生安装副作用）"
    if marker.exists():
        called = marker.read_text().strip().splitlines()
        assert not called, "mock systemctl/alembic/journalctl 被调用: %s" % called
    assert not (home / ".local" / "bin").exists(), "launcher symlink 被创建"
    assert not (home / ".config" / "systemd").exists(), "unit 被写入"
    assert not (home / ".local" / "share" / "kylin-memory").exists(), "数据库目录被创建"


# ─────────────────────────── PASS 案例 ───────────────────────────

def test_untampered_package_passes_integrity_gate(tmp_path):
    pkg = build_package(tmp_path)
    home = tmp_path / "home"

    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc == 0, "未篡改包 _integrity-gate 应返回 0\nstdout=%s\nstderr=%s" % (out, err)
    assert "PASS" in out, "未篡改包应输出 PASS:\n%s" % out


def test_untampered_install_passes_gate_then_stops_before_side_effects(tmp_path):
    """未篡改包 install：完整性 Gate PASS 后，在 SDK 前置检查（WSL 无真实 SDK）停止，
    无任何复制/迁移/systemd 副作用。"""
    pkg = build_package(tmp_path)
    home = tmp_path / "home"

    rc, out, err, marker, prefix = run_install(pkg, home, mode="install")
    assert rc != 0, "WSL 无真实 SDK，install 应在 SDK 检查处停止"
    assert "PASS" in out, "完整性 Gate 应先 PASS:\n%s" % out
    assert "前置依赖缺失" in err, "应在 SDK 前置检查处失败:\n%s" % err
    assert_no_side_effects(marker, prefix, home)


# ─────────────────────── 篡改 / 删除 受管理文件 ───────────────────────

def test_tamper_managed_app_py_fails_before_side_effects(tmp_path):
    def tamper(pkg):
        rewrite(pkg, "runtime/app/app.py", b"print('TAMPERED')\n")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, marker, prefix = run_install(pkg, home, mode="install")
    assert rc != 0, "篡改 app.py 应 FAIL"
    assert "完整性Gate" in err and "哈希不符" in err, "应报哈希不符: %s" % err
    assert_no_side_effects(marker, prefix, home)


def test_delete_managed_file_fails_before_side_effects(tmp_path):
    def tamper(pkg):
        rmfile(pkg, "runtime/app/app.py")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, marker, prefix = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0, "删除受管理文件应 FAIL"
    assert "受管理文件缺失" in err and "app.py" in err, "应报受管理文件缺失: %s" % err
    assert_no_side_effects(marker, prefix, home)


def test_delete_venv_python_fails(tmp_path):
    def tamper(pkg):
        rmfile(pkg, "runtime/python/bin/python")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "受管理文件缺失" in err, "删除 venv python 应 FAIL: %s" % err


# ─────────────────────── unit / 脚本 篡改 ───────────────────────

def test_tamper_systemd_unit_fails_before_side_effects(tmp_path):
    def tamper(pkg):
        rewrite(pkg, "systemd/kylin-memory.service", b"[Unit]\nDescription=EVIL\n")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, marker, prefix = run_install(pkg, home, mode="install")
    assert rc != 0, "篡改 systemd unit 应 FAIL"
    assert "完整性Gate" in err and "哈希不符" in err, "应报哈希不符: %s" % err
    assert_no_side_effects(marker, prefix, home)


def test_tamper_packaged_install_script_fails_before_side_effects(tmp_path):
    def tamper(pkg):
        rewrite(pkg, "systemd/install.sh", b"#!/usr/bin/env bash\n# EVIL\n")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, marker, prefix = run_install(pkg, home, mode="install")
    assert rc != 0, "篡改包内 install 脚本应 FAIL"
    assert "完整性Gate" in err, "应报完整性错误: %s" % err
    assert_no_side_effects(marker, prefix, home)


def test_tamper_launcher_script_fails(tmp_path):
    def tamper(pkg):
        rewrite(pkg, "bin/kylin-memory-server", b"#!/usr/bin/env bash\nexit 42\n")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "哈希不符" in err, "篡改 launcher 应 FAIL: %s" % err


# ─────────────────────── SHA256SUMS 语法异常（fail-closed） ───────────────────────

def test_empty_sha256sums_fails(tmp_path):
    def tamper(pkg):
        (pkg / "SHA256SUMS").write_text("", encoding="utf-8")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, marker, prefix = run_install(pkg, home, mode="install")
    assert rc != 0, "空 SHA256SUMS 应 FAIL"
    assert "为空清单" in err, "应报空清单: %s" % err
    assert_no_side_effects(marker, prefix, home)


def test_duplicate_path_in_sha256sums_fails(tmp_path):
    def tamper(pkg):
        text = (pkg / "SHA256SUMS").read_text(encoding="utf-8")
        lines = text.splitlines()
        first = lines[0]
        (pkg / "SHA256SUMS").write_text(text + first + "\n", encoding="utf-8")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "重复路径" in err, "重复路径应 FAIL: %s" % err


def test_absolute_path_in_sha256sums_fails(tmp_path):
    def tamper(pkg):
        (pkg / "SHA256SUMS").write_text(
            "%s  /etc/passwd\n" % ("0" * 64),
            encoding="utf-8",
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "绝对路径禁止" in err, "绝对路径应 FAIL: %s" % err


def test_path_traversal_in_sha256sums_fails(tmp_path):
    def tamper(pkg):
        (pkg / "SHA256SUMS").write_text(
            "%s  ../outside\n" % ("0" * 64),
            encoding="utf-8",
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "路径穿越" in err, "路径穿越应 FAIL: %s" % err


# ─────────────────────── 双向一致（manifest <-> SHA256SUMS） ───────────────────────

def test_sha256sums_extra_unmanaged_entry_fails(tmp_path):
    """SHA256SUMS 含 manifest 未登记文件（磁盘存在但未登记）→ FAIL。"""

    def tamper(pkg):
        (pkg / "runtime/app/extra.py").write_bytes(b"x = 1\n")
        (pkg / "SHA256SUMS").write_text(
            (pkg / "SHA256SUMS").read_text(encoding="utf-8")
            + "%s  runtime/app/extra.py\n" % sha256_bytes(b"x = 1\n"),
            encoding="utf-8",
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "未登记文件" in err, "多余 SHA256SUMS 条目应 FAIL: %s" % err


def test_manifest_extra_file_not_in_sha256sums_fails(tmp_path):
    """manifest.files 含 SHA256SUMS 不存在的条目（磁盘真实存在）→ FAIL。"""

    def tamper(pkg):
        (pkg / "runtime/bridge/kylin_embedding_extra.so").write_bytes(b"ELF-mock")
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"]["runtime/bridge/kylin_embedding_extra.so"] = {
            "size": 9,
            "sha256": sha256_bytes(b"ELF-mock"),
        }
        (pkg / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "未覆盖" in err, "manifest 多余条目应 FAIL: %s" % err


def test_manifest_missing_entry_fails(tmp_path):
    """从 manifest.files 删除条目（磁盘与 SHA256SUMS 仍在）→ FAIL。"""

    def tamper(pkg):
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        del manifest["files"]["runtime/app/app.py"]
        (pkg / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "未登记文件" in err, "manifest 缺失条目应 FAIL: %s" % err


def test_synchronized_tamper_still_fails(tmp_path):
    """文件内容被修改且 SHA256SUMS 已同步（manifest 未同步）→ 仍须 FAIL。
    使用等长替换（d14a → T4MP）保持 size 不变，专门命中
    manifest.sha256 与 SHA256SUMS 双向 hash 不一致路径。"""

    def tamper(pkg):
        p = pkg / "runtime/app/app.py"
        new_data = p.read_bytes().replace(b"d14a", b"T4MP")
        assert len(new_data) == p.stat().st_size, "等长替换前提失效"
        p.write_bytes(new_data)
        lines = (pkg / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            _s, rel = line.split()
            if rel == "runtime/app/app.py":
                out.append("%s  %s" % (sha256_bytes(new_data), rel))
            else:
                out.append(line)
        (pkg / "SHA256SUMS").write_text("\n".join(out) + "\n", encoding="utf-8")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "与 SHA256SUMS 不一致" in err, "同步篡改仍应 FAIL: %s" % err


# ─────────────────────── manifest identity ───────────────────────

def test_identity_package_name_mismatch_fails(tmp_path):
    def tamper(pkg):
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        manifest["package_name"] = "kylin-memory-a-d99"
        (pkg / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "package_name 不符" in err, "package_name 不符应 FAIL: %s" % err


def test_identity_source_commit_invalid_fails(tmp_path):
    def tamper(pkg):
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        manifest["source_commit"] = "deadbeef"
        (pkg / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "source_commit" in err, "source_commit 非法应 FAIL: %s" % err


def test_identity_sdk_frozen_mismatch_fails(tmp_path):
    def tamper(pkg):
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        manifest["sdk"]["sha256"] = "0" * 64
        (pkg / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "sdk.sha256 不符" in err, "SDK identity 不符应 FAIL: %s" % err


def test_version_file_mismatch_fails(tmp_path):
    def tamper(pkg):
        (pkg / "VERSION").write_text("9.9.9-evil\n", encoding="utf-8")

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, marker, prefix = run_install(pkg, home, mode="install")
    assert rc != 0, "VERSION 与 package_version 不一致应 FAIL"
    assert "package_version" in err, "应报 VERSION 不一致: %s" % err
    assert_no_side_effects(marker, prefix, home)


def test_identity_package_version_empty_fails(tmp_path):
    def tamper(pkg):
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        manifest["package_version"] = ""
        (pkg / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    pkg = build_package(tmp_path, tamper=tamper)
    home = tmp_path / "home"
    rc, out, err, _m, _p = run_install(pkg, home, mode="_integrity-gate")
    assert rc != 0 and "package_version" in err, "空 package_version 应 FAIL: %s" % err