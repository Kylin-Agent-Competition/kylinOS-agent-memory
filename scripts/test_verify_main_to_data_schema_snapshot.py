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
  - source_main_commit 缺失 / 非法 SHA / valid-but-wrong SHA（BLOCKER-01）→ non-zero
  - frozen_stable alias/kind/canonical_field 语义漂移（BLOCKER-02）→ non-zero
  - 代码侧 MemorySourceEvent/NormalizedEvent 失去 extra="forbid"（REVIEW-03）→ non-zero
  - Canonical 文档首部改回 CANDIDATE_FOR_FREEZE 而历史段落残留 FROZEN（REVIEW-04）→ non-zero

纪律：
- 负例全部在真实的临时副本上构造（不改动原 Snapshot 的字典，避免对被导入
  SSOT 的副作用）。
- 不 Mock、不 skip；校验结果以 verify_snapshot() 返回的退出码为准。
"""

from __future__ import annotations

import json
import shutil
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

SCHEMAS_REL = Path("memory-service/pipeline/schemas.py")
KMA_DOC_REL = Path("docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md")
_FORBID_LINE = 'model_config = ConfigDict(extra="forbid")'


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _write_variant(data: dict, tmp_path: Path) -> Path:
    """把扰动后的 dict 写入临时 JSON 副本（不改动原文件）。"""
    variant = tmp_path / "snapshot_variant.json"
    variant.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return variant


def _copy_repo_subtrees(tmp_path: Path) -> Path:
    """构造 fake root：复制 memory-service（略过 __pycache__/tests）、真实
    Snapshot 与 KMA Canonical 文档，供 REVIEW-03 / REVIEW-04 源码级与
    文档级负例使用。SSOT 值集比较读取的枚举成员与真实副本一致，AST/文档
    检查读取磁盘文件，结果与 sys.modules 缓存顺序无关、确定可控。
    """

    def _ignore(_dir: str, names: list[str]) -> list[str]:
        return [n for n in names if n in ("__pycache__", "tests")]

    target = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "memory-service", target / "memory-service", ignore=_ignore)
    (target / "interfaces" / "main_to_data").mkdir(parents=True, exist_ok=True)
    shutil.copy(SNAPSHOT_PATH, target / SNAPSHOT_REL)
    (target / "docs" / "architecture").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / KMA_DOC_REL, target / KMA_DOC_REL)
    return target


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


# ── BLOCKER-01：source_main_commit 溯源门禁 ───────────────────────────────

def test_source_main_commit_missing_fails(tmp_path):
    """删除顶层 source_main_commit 必须 FAIL。"""
    data = _load_snapshot()
    data.pop("source_main_commit", None)
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


def test_source_main_commit_invalid_sha_fails(tmp_path):
    """非法 SHA（非 40 位 lowercase hex）必须 FAIL。"""
    data = _load_snapshot()
    data["source_main_commit"] = "ba3b50e1bdeea185bca9daee9d1d45958f62a63Z"
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


def test_source_main_commit_valid_but_wrong_fails(tmp_path):
    """篡改为另一合法 40 位 SHA（≠ 冻结基线常量）必须 FAIL。"""
    data = _load_snapshot()
    data["source_main_commit"] = "a" * 40
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


# ── BLOCKER-02：frozen_stable 语义级精确比较 ──────────────────────────────

def _frozen_entry(data: dict, canonical_field: str) -> dict:
    for entry in data["aliases_and_mappings"]["frozen_stable"]:
        if entry["canonical_field"] == canonical_field:
            return entry
    raise AssertionError(f"frozen_stable 缺少 canonical_field={canonical_field!r}")


def test_frozen_collected_at_alias_drift_fails(tmp_path):
    """captured_at←collected_at 的 source_alias 漂移必须 FAIL。"""
    data = _load_snapshot()
    entry = _frozen_entry(data, "captured_at")
    entry["source_alias"] = "collected_ts"  # mapping_status 保持不变
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


def test_frozen_sensitivity_alias_drift_fails(tmp_path):
    """sensitivity←sensitivity_level 的 source_alias 漂移必须 FAIL。"""
    data = _load_snapshot()
    entry = _frozen_entry(data, "sensitivity")
    entry["source_alias"] = "sensitivity_lvl"
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


def test_frozen_host_dto_failure_mapping_drift_fails(tmp_path):
    """Host DTO execution_status=failure 映射条目 kind 漂移必须 FAIL。"""
    data = _load_snapshot()
    entry = _frozen_entry(data, "source_business_status")
    entry["kind"] = "renamed_kind"  # mapping_status 保持不变，漂移来自 kind
    variant = _write_variant(data, tmp_path)
    assert verify_snapshot(snapshot_path=variant, root=REPO_ROOT) == 1


# ── REVIEW-03：unknown_policy=fail_closed 的代码侧核验 ────────────────────

def test_code_side_extra_forbid_drift_fails(tmp_path):
    """代码侧 MemorySourceEvent/NormalizedEvent 失去 extra="forbid" 必须 FAIL。"""
    target = _copy_repo_subtrees(tmp_path)
    schemas_path = target / SCHEMAS_REL
    source = schemas_path.read_text(encoding="utf-8")
    assert _FORBID_LINE in source, "测试前提：源码应含 extra=forbid 声明"
    schemas_path.write_text(
        source.replace(_FORBID_LINE, 'model_config = ConfigDict(extra="ignore")'),
        encoding="utf-8",
    )
    assert verify_snapshot(root=target) == 1


# ── REVIEW-04：Canonical 文档首部 FROZEN 判定（防假阳性） ─────────────────

def test_doc_header_reverted_candidate_still_fails(tmp_path):
    """首部改回 CANDIDATE_FOR_FREEZE、历史段落残留 FROZEN 必须 FAIL。"""
    target = _copy_repo_subtrees(tmp_path)
    doc_path = target / KMA_DOC_REL
    doc_path.write_text(
        "# Test\n"
        "- **状态**：CANDIDATE_FOR_FREEZE（header-only）\n"
        "\n"
        "## 变更记录\n"
        "历史段落残留 状态：FROZEN\n",
        encoding="utf-8",
    )
    assert verify_snapshot(root=target) == 1
