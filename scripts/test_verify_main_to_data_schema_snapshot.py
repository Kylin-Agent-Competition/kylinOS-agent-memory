"""test_verify_main_to_data_schema_snapshot.py — E-M1 SchemaSnapshot 校验器最小 L1 测试

覆盖：
- 正例：对真实冻结 Snapshot 运行校验器，ExitCode 应为 0。
- 构造性负例（在临时 JSON 副本上扰动后注入字段语义影响，再校验 fail-closed）：
  - Snapshot 文件缺失 → non-zero
  - Snapshot JSON 非法 → non-zero
  - status 改为 DRAFT → non-zero
  - unknown_policy 改为 permissive → non-zero
  - core 值集加入 PENDING_* 值 → non-zero
  - 移除 frozen_stable alias 字段 → non-zero

纪律：
- 负例全部在真实的临时副本上构造（不改动原 Snapshot 的字典，避免对被导入
  SSOT 的副作用）。
- 不 Mock、不 skip；校验结果以 verify_snapshot() 返回的退出码为准。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 使 scripts 目录可被 import（脚本级测试惯例）
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from verify_main_to_data_schema_snapshot import verify_snapshot  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent
SNAPSHOT_REL = Path("interfaces/main_to_data/schema_snapshot.json")
SNAPSHOT_PATH = REPO_ROOT / SNAPSHOT_REL


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _write_variant(data: dict, tmp_path: Path) -> Path:
    """把扰动后的 dict 写入临时 JSON 副本（不改动原文件）。"""
    variant = tmp_path / "snapshot_variant.json"
    variant.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return variant


# ── 正例 ──────────────────────────────────────────────────────────────────

def test_real_frozen_snapshot_passes():
    """对当前冻结 Snapshot 自检必须通过（exit 0）。"""
    assert SNAPSHOT_PATH.is_file(), f"missing {SNAPSHOT_PATH}"
    assert verify_snapshot(snapshot_path=SNAPSHOT_PATH, root=REPO_ROOT) == 0


# ── 输入不可用 ────────────────────────────────────────────────────────────

def test_missing_snapshot_file_fails(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert verify_snapshot(snapshot_path=missing, root=REPO_ROOT) == 1


def test_invalid_json_fails(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json ", encoding="utf-8")
    assert verify_snapshot(snapshot_path=bad, root=REPO_ROOT) == 1


# ── 构造性负例 ────────────────────────────────────────────────────────────

def test_status_changed_to_draft_fails(tmp_path):
    data = _load_snapshot()
    data["status"] = "DRAFT"
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


def test_unknown_policy_permissive_fails(tmp_path):
    data = _load_snapshot()
    data["unknown_policy"]["policy"] = "permissive"
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


def test_pending_member_in_canonical_fails(tmp_path):
    data = _load_snapshot()
    data["canonical"]["core_value_sets"]["memory_status"]["values"].append("PENDING_X")
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


def test_frozen_stable_alias_field_removed_fails(tmp_path):
    data = _load_snapshot()
    entry = data["aliases_and_mappings"]["frozen_stable"][0]
    entry.pop("source_alias", None)
    entry.pop("source_fields", None)
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


@pytest.mark.skipif(
    not SNAPSHOT_PATH.is_file(),
    reason="真实 Snapshot 缺失时跳过正例（保护性，非无条件 skip）",
)
def test_missing_canonical_document_fails(tmp_path):
    """Canonical 文档路径被改写为空时，authority 结构校验应 fail-closed。"""
    data = _load_snapshot()
    data["authority"]["canonical_document"]["path"] = ""
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1
