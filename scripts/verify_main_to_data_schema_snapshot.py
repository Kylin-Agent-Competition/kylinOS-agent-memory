#!/usr/bin/env python3
"""verify_main_to_data_schema_snapshot.py — E-M1 SchemaSnapshot 确定性校验器

对冻结的 ``interfaces/main_to_data/schema_snapshot.json`` 与仓库当前代码 SSOT
（``memory-service/domain/enums.py``、``memory-service/pipeline/schemas.py``）以及
Canonical 文档（``KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md``）做确定性、离线、
fail-closed 的一致性校验。

设计要点：
- 纯离线、确定性、无网络与 Runtime 依赖；以仓库根目录为稳定定位基准
  （默认由本文件位置推导 ``parents[1]``）。
- 判定数据主要来自真实输入（Snapshot 文件 + 动态导入的当前代码 SSOT +
  Canonical 文档文本 + 源码级 AST 核验）。除下述显式冻结基线常量外，
  取值判定一律来自真实输入：
  - ``EXPECTED_SCHEMA_NAME``、``SSOT_ENUM_LOCATORS``/``PROCESSING_STATUS_LOCATOR``
    （仅用于定位 SSOT 枚举类，取值仍来自动态导入的当前代码）；
  - ``EXPECTED_SOURCE_MAIN_COMMIT``（冻结允许的 main 基线 SHA，见 BLOCKER-01）；
  - ``EXPECTED_FROZEN_MAPPINGS``（冻结稳定映射语义基线，见 BLOCKER-02）；
  - ``EXPECTED_AUTHORITY_PROVENANCE``（``authority.provenance`` 声明字段精确冻结
    门禁：legacy pr/approved_review/evidence_review 字符串与两个 review_status、
    两个 head SHA、pr_number、merge_commit、controller_evidence_repository_tracked
    必须与冻结常量全等；含 ``.agent-runs`` 的 legacy 字符串只做文本精确比较，
    不要求 clean clone 中存在对应文件，也不做任何文件系统访问）。
- fail-closed：Snapshot JSON 不可解析、漂移、缺字段、非法 provenance、
  无法导入或解析代码 SSOT、Canonical 文档缺失/非 FROZEN、冻结基线与代码侧
  fail-closed 声明漂移，均返回 exit 1。任何内部异常都会以 ``[FAIL]`` 形式
  输出并返回 1，绝不吞掉或静默降级。

仅服务 E-M1 Snapshot closure，不构成全仓 Schema Drift Framework。

用法：
    python3 scripts/verify_main_to_data_schema_snapshot.py [--snapshot PATH] [--root PATH]

- ``--snapshot``：Snapshot JSON 路径，默认 ``interfaces/main_to_data/schema_snapshot.json``
  （相对 ``--root`` 解析）。
- ``--root``：仓库根目录，默认由本文件位置推导。
- 退出码：全部检查通过 → 0；任一检查失败 → 1。
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_SNAPSHOT_REL = Path("interfaces/main_to_data/schema_snapshot.json")
EXPECTED_SCHEMA_NAME = "main_to_data_canonical_business_schema_snapshot"

# Snapshot 组 + 值集键 → (相对 memory-service 的模块文件, 枚举类名)。
# 该表只用于定位 SSOT 枚举类；判定取值一律来自动态导入的当前代码 SSOT。
SSOT_ENUM_LOCATORS = {
    ("core_value_sets", "memory_status"): ("domain/enums.py", "MemoryStatus"),
    ("core_value_sets", "preference_scope"): ("domain/enums.py", "PreferenceScope"),
    ("core_value_sets", "expression_type"): ("domain/enums.py", "ExpressionType"),
    ("core_value_sets", "sensitivity"): ("pipeline/schemas.py", "SensitivityLevel"),
    ("additional_stable_value_sets", "knowledge_type"): ("domain/enums.py", "KnowledgeType"),
    ("additional_stable_value_sets", "forget_mode"): ("domain/enums.py", "ForgetMode"),
    ("additional_stable_value_sets", "source_type"): ("pipeline/schemas.py", "SourceType"),
    ("additional_stable_value_sets", "source_business_status"): (
        "pipeline/schemas.py",
        "SourceBusinessStatus",
    ),
}
# 显式非 Canonical 的 processing_status（不得进入 core/additional 值集）
PROCESSING_STATUS_LOCATOR = ("pipeline/schemas.py", "ProcessingStatus")

CANONICAL_GROUPS = ("core_value_sets", "additional_stable_value_sets")
FROZEN_STABLE_FIELDS = ("canonical_field", "kind", "mapping_status", "document")
FROZEN_STABLE_ALIAS_FIELDS = ("source_alias", "source_fields")
AUTHORITY_REQUIRED_KEYS = (
    "canonical_document",
    "supporting_documents",
    "source_identity",
    "provenance",
)
PROVENANCE_REQUIRED_KEYS = ("pr", "merge_commit", "approved_review", "evidence_review")
TOP_LEVEL_REQUIRED_KEYS = (
    "schema",
    "schema_version",
    "status",
    "source_main_commit",
    "authority",
    "canonical",
    "aliases_and_mappings",
    "unknown_policy",
)
ALIAS_SECTIONS = ("frozen_stable", "deprecated_or_compatibility", "pending_mapping")

# 冻结允许的 main 基线 SHA（BLOCKER-01）。
# 权威性由治理冻结流程背书；更新须经书面治理流程，且必须与真实 origin/main
# 冻结提交一致。禁止为通用化做 Git 网络/ancestry 查询——本校验保持离线 deterministic。
EXPECTED_SOURCE_MAIN_COMMIT = "ba3b50e1bdeea185bca9daee9d1d45958f62a636"

# authority.provenance 声明字段精确冻结基线（E-M1 final review-fix Task 2）。
# 冻结常量写死在源码中，禁止运行时从 Snapshot 反推（否则会与篡改值同漂移）。
# 仅冻结下列声明字段：pr / pr_number / pr_head_commit / merge_commit /
# approved_review / approved_review_status / approved_reviewed_head /
# evidence_review / evidence_review_status / controller_evidence_repository_tracked。
# 说明字段（merge_commit_verified / governance_freeze_commit / reviewer_identity /
# note 等）不参与本精确门禁。含 ``.agent-runs`` 的 legacy 字符串（pr /
# approved_review / evidence_review）是 external/controller evidence reference，
# 只做与冻结常量的文本精确比较，不要求对应文件存在于 clean clone，不做任何
# 文件系统访问（纯离线 deterministic）。
EXPECTED_AUTHORITY_PROVENANCE = {
    "pr": "#137 (Fix/e d12 business schema drift remediation)",
    "pr_number": 137,
    "pr_head_commit": "468c591192769b8e5a4e69190db3bc279ed52e8a",
    "merge_commit": "f263d5b7beefa4d380fd94d34ef0fa83ffc622c3",
    "approved_review": ".agent-runs/batches/day12-e-business-schema-drift-remediation-v3/tasks/day12-e-01-canonical-schema-governance-v3/review.md (FINAL_STATUS: APPROVE)",
    "approved_review_status": "APPROVED",
    "approved_reviewed_head": "468c591192769b8e5a4e69190db3bc279ed52e8a",
    "evidence_review": ".agent-runs/batches/day12-e-business-schema-drift-remediation-v3/tasks/day12-e-01-canonical-schema-governance-v3/evidence-review.md (FINAL_STATUS: EVIDENCE_APPROVED)",
    "evidence_review_status": "EVIDENCE_APPROVED",
    "controller_evidence_repository_tracked": False,
}
# 必须与冻结常量全等的 legacy 字符串字段（garbage 替换即 FAIL，禁止只查非空）。
PROVENANCE_LEGACY_EXACT_STRINGS = ("pr", "approved_review", "evidence_review")

# 冻结稳定映射语义基线（BLOCKER-02）：frozen_stable 每条须与下列期望条目
# 做精确语义投影比较（canonical_field / alias 身份 / kind / mapping_status /
# target_value）。target_value 仅对声明 frozen_stable 的 Host failure→failed
# 条目构成结构化约束（其期望为 "failed"）；captured_at/sensitivity 条目不含
# target_value，投影第 5 元素为 None；Host success/partial/cancelled/timeout
# 不做结构化冻结（TD-060/TD-016 保持 Open）。
# 任一漂移、删除、重复或新增未冻结映射均须 FAIL，直到治理流程显式升版本常量。
EXPECTED_FROZEN_MAPPINGS = (
    {
        "canonical_field": "captured_at",
        "source_alias": "collected_at",
        "kind": "legacy_transport_alias",
        "mapping_status": "frozen_stable",
    },
    {
        "canonical_field": "sensitivity",
        "source_alias": "sensitivity_level",
        "kind": "annotation_layer_1to1_alias",
        "mapping_status": "frozen_stable",
    },
    {
        "canonical_field": "source_business_status",
        "source_alias": "Host DTO execution_status=failure",
        "target_value": "failed",
        "kind": "host_dto_alias_normalization",
        "mapping_status": "frozen_stable",
    },
)

# 需要 AST 核验 `ConfigDict(extra="forbid")` 的代码侧 fail-closed 类（REVIEW-03）。
EXTRA_FORBID_CLASS_NAMES = ("MemorySourceEvent", "NormalizedEvent")
EXTRA_FORBID_SCHEMAS_REL = Path("memory-service/pipeline/schemas.py")

# Canonical 文档首部 FROZEN 状态声明（REVIEW-04）：仅解析文档首部状态 metadata。
_FROZEN_DECL_RE = re.compile(r"状态\s*[：:]\s*FROZEN(?![A-Za-z0-9_])")
# FROZEN 判定域：首个 `##`/`###` 标题行之前的首部前置区；无标题时取前 N 行。
_FROZEN_PREAMBLE_HEADING_RE = re.compile(r"^#{2,}\s+.+$", re.MULTILINE)
_FROZEN_PREAMBLE_FALLBACK_LINES = 30


def _resolve_root(root: Optional[Path]) -> Path:
    """仓库根目录：显式传入则解析之，否则由本文件位置推导 parents[1]。"""
    if root is None:
        return Path(__file__).resolve().parents[1]
    return Path(root).resolve()


def _resolve_snapshot(snapshot_path: Optional[Path], root: Path) -> Path:
    """Snapshot 路径：显式传入则解析之，否则取 root 下默认相对路径。"""
    if snapshot_path is None:
        return (root / DEFAULT_SNAPSHOT_REL).resolve()
    p = Path(snapshot_path)
    return p if p.is_absolute() else (root / p).resolve()


# ── 结果收集 ──────────────────────────────────────────────────────────────

def _add(results: List[Tuple[bool, str, str]], ok: bool, name: str, detail: str = "") -> None:
    results.append((bool(ok), name, detail))


def _fail(results: List[Tuple[bool, str, str]], name: str, detail: str = "") -> None:
    results.append((False, name, detail))


def _set_diff_detail(snapshot_values: Sequence[str], ssot_values: Sequence[str]) -> str:
    """集合比较差异描述（missing = SSOT 有而 Snapshot 缺，extra = 反之）。"""
    missing = sorted(set(ssot_values) - set(snapshot_values))
    extra = sorted(set(snapshot_values) - set(ssot_values))
    parts = []
    if missing:
        parts.append("missing_vs_ssot=" + ",".join(missing))
    if extra:
        parts.append("extra_vs_ssot=" + ",".join(extra))
    return ";".join(parts)


# ── SSOT 动态导入 ─────────────────────────────────────────────────────────

def _load_ssot_value_set(memory_service_dir: Path, rel_module_file: str, class_name: str) -> List[str]:
    """动态导入当前代码 SSOT 枚举并返回其 value 列表。

    导入失败（模块缺失 / 语法错误 / 依赖缺失等）将向上抛出，由调用方
    按 fail-closed 记录为校验失败，绝不吞掉。
    """
    module_name = rel_module_file[:-3].replace("/", ".")
    if str(memory_service_dir) not in sys.path:
        sys.path.insert(0, str(memory_service_dir))
    module = importlib.import_module(module_name)
    enum_class = getattr(module, class_name)
    return [member.value for member in enum_class]


def _doc_text_declares_frozen(text: str) -> bool:
    """按文档首部状态 metadata 判断 FROZEN（REVIEW-04）。

    仅解析标题（^## 或 ^###）之前的首部前置区（无标题时取前
    ``_FROZEN_PREAMBLE_FALLBACK_LINES`` 行）；对首部做既有标记归一
    （去 `` ` ``、``*``、``_``）后，命中 ``状态：FROZEN`` 才为 True。
    历史段落/正文残留 ``状态：FROZEN`` 不参与判定，避免假阳性。
    """
    normalized = re.sub(r"[`*_]", "", text)
    heading = _FROZEN_PREAMBLE_HEADING_RE.search(normalized)
    if heading is not None:
        preamble = normalized[: heading.start()]
    else:
        lines = normalized.splitlines(keepends=True)
        preamble = "".join(lines[:_FROZEN_PREAMBLE_FALLBACK_LINES])
    return bool(_FROZEN_DECL_RE.search(preamble))


# ── 分组检查 ──────────────────────────────────────────────────────────────

def _check_basics(results, data: Dict[str, Any]) -> None:
    for key in TOP_LEVEL_REQUIRED_KEYS:
        if key not in data:
            _fail(results, "top_level_key_present", f"missing key: {key}")
    if "status" in data:
        _add(
            results,
            data["status"] == "FROZEN",
            "snapshot_status_frozen",
            f"status={data.get('status')!r}",
        )
    if "schema" in data:
        _add(
            results,
            data["schema"] == EXPECTED_SCHEMA_NAME,
            "snapshot_schema_name",
            f"schema={data.get('schema')!r}",
        )
    _check_source_main_commit(results, data)


def _check_source_main_commit(results, data: Dict[str, Any]) -> None:
    """BLOCKER-01：顶层 provenance 基线的 presence/类型/SHA 格式/精确相等门禁。"""
    commit = data.get("source_main_commit")
    if not isinstance(commit, str):
        _fail(
            results,
            "source_main_commit_type",
            f"type={type(commit).__name__} value={commit!r}",
        )
        return
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        _fail(
            results,
            "source_main_commit_sha_format",
            f"invalid git SHA (expect 40 lowercase hex): {commit!r}",
        )
        return
    _add(
        results,
        commit == EXPECTED_SOURCE_MAIN_COMMIT,
        "source_main_commit_matches_frozen_baseline",
        f"commit={commit!r} expected={EXPECTED_SOURCE_MAIN_COMMIT!r}",
    )


def _check_authority(results, root: Path, data: Dict[str, Any]) -> None:
    authority = data.get("authority")
    if not isinstance(authority, dict):
        _fail(results, "authority_object", f"type={type(authority).__name__}")
        return
    for key in AUTHORITY_REQUIRED_KEYS:
        if key not in authority:
            _fail(results, "authority_key_present", f"missing key: authority.{key}")

    # canonical_document：path/version/status 完整且 status=FROZEN
    canonical_doc = authority.get("canonical_document")
    if not isinstance(canonical_doc, dict):
        _fail(results, "canonical_document_object", f"type={type(canonical_doc).__name__}")
    else:
        for key in ("path", "version", "status"):
            value = canonical_doc.get(key)
            if not isinstance(value, str) or not value:
                _fail(results, "canonical_document_field", f"missing/empty field: {key}")
        status = canonical_doc.get("status")
        _add(
            results,
            status == "FROZEN",
            "canonical_document_status_frozen",
            f"status={status!r}",
        )
        doc_rel = canonical_doc.get("path")
        if isinstance(doc_rel, str) and doc_rel:
            doc_path = (root / doc_rel).resolve()
            if not doc_path.is_file():
                _fail(results, "canonical_document_file_exists", f"missing: {doc_path}")
            else:
                try:
                    text = doc_path.read_text(encoding="utf-8")
                except OSError as exc:
                    _fail(results, "canonical_document_readable", f"{exc!r}")
                else:
                    _add(
                        results,
                        _doc_text_declares_frozen(text),
                        "canonical_document_text_frozen",
                        f"doc={doc_path}",
                    )

    # source_identity：非空且每个文件存在（相对 root）
    source_identity = authority.get("source_identity")
    if not isinstance(source_identity, list) or not source_identity:
        _fail(results, "authority_source_identity_nonempty", f"value={source_identity!r}")
    else:
        for rel in source_identity:
            if not isinstance(rel, str) or not rel:
                _fail(results, "source_identity_entry", f"invalid entry: {rel!r}")
                continue
            _add(
                results,
                (root / rel).is_file(),
                "source_identity_file_exists",
                f"file={rel}",
            )

    # supporting_documents：每个条目 path/status 完整
    supporting = authority.get("supporting_documents")
    if not isinstance(supporting, list):
        _fail(results, "supporting_documents_list", f"type={type(supporting).__name__}")
    else:
        for idx, entry in enumerate(supporting):
            if not isinstance(entry, dict):
                _fail(results, "supporting_document_entry", f"index={idx} not a dict")
                continue
            for key in ("path", "status"):
                value = entry.get(key)
                if not isinstance(value, str) or not value:
                    _fail(
                        results,
                        "supporting_document_field",
                        f"index={idx} missing/empty field: {key}",
                    )

    # provenance：结构完整（必需键为非空字符串）+ 声明字段精确冻结门禁
    provenance = authority.get("provenance")
    if not isinstance(provenance, dict):
        _fail(results, "provenance_object", f"type={type(provenance).__name__}")
    else:
        for key in PROVENANCE_REQUIRED_KEYS:
            value = provenance.get(key)
            if not isinstance(value, str) or not value:
                _fail(results, "provenance_field", f"missing/empty field: {key}")
        _check_provenance_frozen_exact(results, provenance)


def _check_provenance_frozen_exact(results, provenance: Dict[str, Any]) -> None:
    """authority.provenance 声明字段的类型严格 + 精确相等的结构化门禁。

    纯离线、fail-closed、无任何文件系统访问（``.agent-runs`` legacy 字符串只做
    文本全等比较，不要求对应文件存在于 clean clone，也不校验文件存在性）。
    任一字段 FAIL 即记入 results（由 verify_snapshot 汇总返回 1）。

    字段级语义：
    - pr / approved_review / evidence_review：必须为 str 且与冻结常量全等
      （禁止只做非空检查，任意 garbage 替换均 FAIL）。
    - pr_number：``type(x) is int`` 且等于冻结值 137（bool/str 视为失败）。
    - pr_head_commit / approved_reviewed_head：必须为 str 且与冻结 SHA 全等。
    - merge_commit：三层独立判定——str → 40 位 lowercase hex → 等于冻结值。
    - approved_review_status / evidence_review_status：必须为 str 且等于冻结值。
    - controller_evidence_repository_tracked：``type(x) is bool`` 且为 False。
    未冻结字段（merge_commit_verified / governance_freeze_commit /
    reviewer_identity / note 等）不参与本精确门禁。
    """
    for key in PROVENANCE_LEGACY_EXACT_STRINGS:
        expected = EXPECTED_AUTHORITY_PROVENANCE[key]
        value = provenance.get(key)
        if not isinstance(value, str):
            _fail(
                results,
                f"provenance_legacy_exact.{key}",
                f"type={type(value).__name__} value={value!r}",
            )
            continue
        _add(
            results,
            value == expected,
            f"provenance_legacy_exact.{key}",
            f"value={value!r} expected={expected!r}",
        )

    pr_number = provenance.get("pr_number")
    if type(pr_number) is not int:
        _fail(
            results,
            "provenance_pr_number_exact",
            f"type={type(pr_number).__name__} value={pr_number!r} (expect int 137)",
        )
    else:
        _add(
            results,
            pr_number == EXPECTED_AUTHORITY_PROVENANCE["pr_number"],
            "provenance_pr_number_exact",
            f"value={pr_number!r} expected={EXPECTED_AUTHORITY_PROVENANCE['pr_number']!r}",
        )

    merge_commit = provenance.get("merge_commit")
    if not isinstance(merge_commit, str):
        _fail(
            results,
            "provenance_merge_commit_type",
            f"type={type(merge_commit).__name__} value={merge_commit!r}",
        )
    elif not re.fullmatch(r"[0-9a-f]{40}", merge_commit):
        _fail(
            results,
            "provenance_merge_commit_sha_format",
            f"invalid git SHA (expect 40 lowercase hex): {merge_commit!r}",
        )
    else:
        _add(
            results,
            merge_commit == EXPECTED_AUTHORITY_PROVENANCE["merge_commit"],
            "provenance_merge_commit_matches_frozen",
            f"value={merge_commit!r} expected={EXPECTED_AUTHORITY_PROVENANCE['merge_commit']!r}",
        )

    for key in ("pr_head_commit", "approved_reviewed_head"):
        expected = EXPECTED_AUTHORITY_PROVENANCE[key]
        value = provenance.get(key)
        if not isinstance(value, str):
            _fail(
                results,
                f"provenance_head_sha_exact.{key}",
                f"type={type(value).__name__} value={value!r}",
            )
            continue
        _add(
            results,
            value == expected,
            f"provenance_head_sha_exact.{key}",
            f"value={value!r} expected={expected!r}",
        )

    for key in ("approved_review_status", "evidence_review_status"):
        expected = EXPECTED_AUTHORITY_PROVENANCE[key]
        value = provenance.get(key)
        if not isinstance(value, str):
            _fail(
                results,
                f"provenance_status_exact.{key}",
                f"type={type(value).__name__} value={value!r}",
            )
            continue
        _add(
            results,
            value == expected,
            f"provenance_status_exact.{key}",
            f"value={value!r} expected={expected!r}",
        )

    tracked = provenance.get("controller_evidence_repository_tracked")
    if type(tracked) is not bool:
        _fail(
            results,
            "provenance_controller_evidence_tracked_exact",
            f"type={type(tracked).__name__} value={tracked!r} (expect False)",
        )
    else:
        _add(
            results,
            tracked is False,
            "provenance_controller_evidence_tracked_exact",
            f"value={tracked!r} expected=False",
        )


def _check_enum_entry(results, memory_service_dir, group: str, key: str, entry: Any) -> None:
    """单个值集条目：结构完整 + 与当前代码 SSOT 完全一致。"""
    if not isinstance(entry, dict):
        _fail(results, f"value_set_entry_object.{group}.{key}", f"type={type(entry).__name__}")
        return
    values = entry.get("values")
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        _fail(results, f"value_set_values_valid.{group}.{key}", f"values={values!r}")
        return
    rel_module_file, class_name = SSOT_ENUM_LOCATORS[(group, key)]
    if not (memory_service_dir / rel_module_file).is_file():
        _fail(
            results,
            f"ssot_source_file_exists.{key}",
            f"missing ssot file: memory-service/{rel_module_file}",
        )
        return
    try:
        ssot_values = _load_ssot_value_set(memory_service_dir, rel_module_file, class_name)
    except Exception as exc:  # 导入/解析失败 → fail-closed，不吞异常
        _fail(
            results,
            f"ssot_import.{key}",
            f"cannot import memory-service/{rel_module_file}::{class_name}: "
            f"{type(exc).__name__}: {exc}",
        )
        return
    diff = _set_diff_detail(values, ssot_values)
    _add(
        results,
        set(values) == set(ssot_values),
        f"value_set_matches_ssot.{group}.{key}",
        diff,
    )


def _check_canonical(results, root: Path, data: Dict[str, Any]) -> None:
    canonical = data.get("canonical")
    if not isinstance(canonical, dict):
        _fail(results, "canonical_object", f"type={type(canonical).__name__}")
        return
    memory_service_dir = (root / "memory-service").resolve()

    for key in CANONICAL_GROUPS:
        if key not in canonical:
            _fail(results, "canonical_section_present", f"missing key: canonical.{key}")

    # 1) core / additional 键集合必须与 SSOT 定位表完全一致（不允许多值集或缺失值集）
    for group in CANONICAL_GROUPS:
        section = canonical.get(group)
        if not isinstance(section, dict):
            _fail(results, f"canonical_section_object.{group}", f"type={type(section).__name__}")
            continue
        expected_keys = {key for (g, key) in SSOT_ENUM_LOCATORS if g == group}
        actual_keys = set(section.keys())
        diff = _set_diff_detail(actual_keys, expected_keys)
        _add(
            results,
            actual_keys == expected_keys,
            f"canonical_section_keys_exact.{group}",
            diff,
        )
        for key, entry in section.items():
            _check_enum_entry(results, memory_service_dir, group, key, entry)

    # 2) PENDING_* 不得写入任何 Canonical 值集
    pending_hits = []
    for group in CANONICAL_GROUPS:
        section = canonical.get(group)
        if not isinstance(section, dict):
            continue
        for key, entry in section.items():
            values = entry.get("values") if isinstance(entry, dict) else None
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and value.startswith("PENDING_"):
                        pending_hits.append(f"{group}.{key}={value}")
    _add(
        results,
        not pending_hits,
        "no_pending_members_in_canonical",
        ";".join(pending_hits),
    )

    # 3) processing_status 仅在 explicit_non_canonical；不得被当作统一业务结果状态
    explicit = canonical.get("explicit_non_canonical")
    if not isinstance(explicit, dict):
        _fail(results, "explicit_non_canonical_object", f"type={type(explicit).__name__}")
        return
    if "processing_status" not in explicit:
        _fail(results, "processing_status_in_explicit_non_canonical", "missing entry")
    for group in CANONICAL_GROUPS:
        section = canonical.get(group)
        if isinstance(section, dict) and "processing_status" in section:
            _fail(
                results,
                "processing_status_not_in_canonical",
                f"processing_status wrongly placed under canonical.{group}",
            )
    processing_entry = explicit.get("processing_status")
    if not isinstance(processing_entry, dict):
        _fail(
            results,
            "processing_status_entry_object",
            f"type={type(processing_entry).__name__}",
        )
        return
    processing_values = processing_entry.get("values")
    if not isinstance(processing_values, list) or not all(
        isinstance(v, str) for v in processing_values
    ):
        _fail(results, "processing_status_values_valid", f"values={processing_values!r}")
        return
    rel_module_file, class_name = PROCESSING_STATUS_LOCATOR
    if (memory_service_dir / rel_module_file).is_file():
        try:
            ssot_processing = _load_ssot_value_set(
                memory_service_dir, rel_module_file, class_name
            )
        except Exception as exc:  # fail-closed
            _fail(
                results,
                "ssot_import.processing_status",
                f"cannot import memory-service/{rel_module_file}::{class_name}: "
                f"{type(exc).__name__}: {exc}",
            )
        else:
            diff = _set_diff_detail(processing_values, ssot_processing)
            _add(
                results,
                set(processing_values) == set(ssot_processing),
                "processing_status_matches_ssot",
                diff,
            )
    else:
        _fail(
            results,
            "ssot_source_file_exists.processing_status",
            f"missing ssot file: memory-service/{rel_module_file}",
        )


def _check_aliases(results, data: Dict[str, Any]) -> None:
    aliases = data.get("aliases_and_mappings")
    if not isinstance(aliases, dict):
        _fail(results, "aliases_and_mappings_object", f"type={type(aliases).__name__}")
        return
    for section_name in ALIAS_SECTIONS:
        section = aliases.get(section_name)
        if not isinstance(section, list):
            _fail(
                results,
                f"aliases_section_list.{section_name}",
                f"type={type(section).__name__}",
            )
            continue
        for idx, entry in enumerate(section):
            if not isinstance(entry, dict):
                _fail(
                    results,
                    f"aliases_entry_object.{section_name}",
                    f"index={idx} not a dict",
                )
                continue
            # mapping_status 必须为非空字符串（缺失/空即为 fail-closed）
            mapping_status = entry.get("mapping_status")
            _add(
                results,
                isinstance(mapping_status, str) and bool(mapping_status),
                f"aliases_mapping_status_present.{section_name}",
                f"index={idx} mapping_status={mapping_status!r}",
            )
    # frozen_stable：字段完整（含 alias 或 fields 至少一种），稳定 alias 不漂移
    frozen_stable = aliases.get("frozen_stable")
    if isinstance(frozen_stable, list):
        for idx, entry in enumerate(frozen_stable):
            if not isinstance(entry, dict):
                _fail(results, "frozen_stable_entry_object", f"index={idx} not a dict")
                continue
            # 稳定 alias 必须声明 frozen_stable；mapping_status 缺失/漂移即失败
            mapping_status = entry.get("mapping_status")
            _add(
                results,
                mapping_status == "frozen_stable",
                "frozen_stable_mapping_status_fixed",
                f"index={idx} mapping_status={mapping_status!r}",
            )
            for key in FROZEN_STABLE_FIELDS:
                value = entry.get(key)
                if not isinstance(value, str) or not value:
                    _fail(
                        results,
                        "frozen_stable_field_complete",
                        f"index={idx} missing/empty field: {key}",
                    )
            has_alias = any(
                entry.get(field) for field in FROZEN_STABLE_ALIAS_FIELDS
            )
            _add(
                results,
                has_alias,
                "frozen_stable_alias_present",
                f"index={idx} canonical_field={entry.get('canonical_field')!r}",
            )
    # BLOCKER-02：frozen_stable 与冻结期望映射做精确语义比较（绝不只查存在性）
    if isinstance(frozen_stable, list):
        _check_frozen_mappings_semantics(results, frozen_stable)


def _frozen_semantic_projection(entry: Dict[str, Any]) -> Optional[Tuple[Any, ...]]:
    """把 frozen_stable 条目投影为
    (canonical_field, alias_identity, kind, mapping_status, target_value)。

    alias_identity：
    - ``source_alias`` 为 str → 直接用该字符串；
    - 否则 ``source_fields`` 为 list → ``tuple(sorted(source_fields))``；
    - 否则 ``source_value`` → 该字符串。
    投影无法确定（缺少任何别名身份）返回 None，由调用方判 FAIL。

    target_value：取 ``entry.get("target_value")``——期望映射无该键时投影为 None，
    与真实 Snapshot 两条非 Host 条目（captured_at/sensitivity 键缺失→None）一致；
    Host failure→failed 期望条目的第 5 元素为 "failed"。删除或篡改 target_value
    均造成投影失配，由 ``_check_frozen_mappings_semantics`` 的精确匹配判 FAIL。
    target_value 仅对声明 frozen_stable 的 failure→failed 条目构成结构化冻结；
    Host success/partial/cancelled/timeout 不做结构化冻结（TD-060/TD-016 保持 Open）。
    不从 note/document 文本解析 target value。
    """
    canonical_field = entry.get("canonical_field")
    kind = entry.get("kind")
    mapping_status = entry.get("mapping_status")
    source_alias = entry.get("source_alias")
    source_fields = entry.get("source_fields")
    source_value = entry.get("source_value")
    if isinstance(source_alias, str):
        alias_identity = source_alias
    elif isinstance(source_fields, list):
        alias_identity = tuple(sorted(source_fields))
    elif isinstance(source_value, str):
        alias_identity = source_value
    else:
        return None
    return (canonical_field, alias_identity, kind, mapping_status, entry.get("target_value"))


def _check_frozen_mappings_semantics(results, frozen_stable: List[Any]) -> None:
    """BLOCKER-02：frozen_stable 与冻结期望映射做精确语义比较。

    要求：真实条目数 == 期望条数，且每个期望条目被“恰好一个”真实条目精确
    匹配（canonical_field / alias 身份 / kind / mapping_status / target_value
    全等）。删除、多余重复、alias/kind/canonical_field/status 漂移与
    target_value 被删除或篡改均被覆盖。target_value 仅对声明 frozen_stable 的
    failure→failed 条目构成结构化约束；``failed`` 作为 Canonical 值成员资格
    继续由 ``value_set_matches_ssot`` 门禁守护。不从 note/document 文本解析
    target value。
    """
    expected_projs = [_frozen_semantic_projection(e) for e in EXPECTED_FROZEN_MAPPINGS]
    if any(p is None for p in expected_projs):
        _fail(results, "frozen_mappings_expected_projection", "expected baseline malformed")
        return
    actual_projs = []
    for idx, entry in enumerate(frozen_stable):
        proj = _frozen_semantic_projection(entry) if isinstance(entry, dict) else None
        actual_projs.append((idx, proj))

    # 数量精确相等
    _add(
        results,
        len(frozen_stable) == len(EXPECTED_FROZEN_MAPPINGS),
        "frozen_mappings_count_exact",
        f"actual={len(frozen_stable)} expected={len(EXPECTED_FROZEN_MAPPINGS)}",
    )

    # 每个期望条目必须被恰好一个实际条目精确匹配，且无重复匹配
    matched_actual = set()
    mismatches = []
    for exp in expected_projs:
        hit_indices = [
            idx
            for (idx, proj) in actual_projs
            if proj is not None and proj == exp and idx not in matched_actual
        ]
        if len(hit_indices) == 1:
            matched_actual.add(hit_indices[0])
        else:
            mismatches.append(f"expected={exp!r} matches={len(hit_indices)}")
    for idx, proj in actual_projs:
        if proj is not None and idx not in matched_actual:
            mismatches.append(f"unmatched_actual_idx={idx} proj={proj!r}")
    _add(
        results,
        not mismatches,
        "frozen_mappings_semantics_exact",
        ";".join(mismatches),
    )


def _source_declares_extra_forbid(schemas_path: Path) -> Optional[str]:
    """源码级核验两个模型类仍声明 ``model_config = ConfigDict(extra="forbid")``。

    返回违规描述字符串，或 None（核验通过）。使用确定性 AST 解析，不导入、
    无副作用；不做全仓扫描、不解析 Pydantic 元类。
    """
    if not schemas_path.is_file():
        return f"missing file: {schemas_path}"
    try:
        source = schemas_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"unreadable file: {exc!r}"
    try:
        tree = ast.parse(source, filename=str(schemas_path))
    except SyntaxError as exc:
        return f"SyntaxError: {exc!r}"
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in EXTRA_FORBID_CLASS_NAMES:
            continue
        forbid = False
        for stmt in node.body:
            if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                continue
            target = getattr(stmt, "targets", None)
            if target is not None and len(target) == 1 and isinstance(target[0], ast.Name):
                name = target[0].id
            else:
                ann_target = getattr(stmt, "target", None)
                name = ann_target.id if isinstance(ann_target, ast.Name) else None
            if name != "model_config":
                continue
            value = getattr(stmt, "value", None)
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "ConfigDict":
                for kw in value.keywords:
                    if kw.arg == "extra" and isinstance(kw.value, ast.Constant) and kw.value.value == "forbid":
                        forbid = True
        found[node.name] = forbid
    missing_violations = []
    for name in EXTRA_FORBID_CLASS_NAMES:
        if name not in found:
            missing_violations.append(f"{name}: class missing")
        elif not found[name]:
            missing_violations.append(f"{name}: extra != 'forbid'")
    return ";".join(missing_violations) if missing_violations else None


def _check_unknown_policy(results, root: Path, data: Dict[str, Any]) -> None:
    unknown_policy = data.get("unknown_policy")
    if not isinstance(unknown_policy, dict):
        _fail(results, "unknown_policy_object", f"type={type(unknown_policy).__name__}")
        return
    policy = unknown_policy.get("policy")
    _add(
        results,
        policy == "fail_closed",
        "unknown_policy_fail_closed",
        f"policy={policy!r}",
    )
    # REVIEW-03：fail_closed 声明必须与代码侧 MemorySourceEvent/NormalizedEvent
    # 仍声明 ConfigDict(extra="forbid") 绑定（fail-closed：读/解析失败即 FAIL）。
    if policy == "fail_closed":
        schemas_path = (root / EXTRA_FORBID_SCHEMAS_REL).resolve()
        violation = _source_declares_extra_forbid(schemas_path)
        _add(
            results,
            violation is None,
            "unknown_policy_code_side_extra_forbid",
            f"violation={violation!r}" if violation else f"schemas={schemas_path}",
        )


# ── 校验入口 ──────────────────────────────────────────────────────────────

def _verify_all(root: Path, snapshot_path: Path) -> List[Tuple[bool, str, str]]:
    results: List[Tuple[bool, str, str]] = []

    if not snapshot_path.is_file():
        _fail(results, "snapshot_file_exists", f"missing: {snapshot_path}")
        return results
    try:
        text = snapshot_path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(results, "snapshot_readable", f"{exc!r}")
        return results
    try:
        data = json.loads(text)
    except ValueError as exc:
        _fail(results, "snapshot_json_parses", f"invalid JSON: {exc}")
        return results
    if not isinstance(data, dict):
        _fail(results, "snapshot_top_level_object", f"type={type(data).__name__}")
        return results

    _check_basics(results, data)
    _check_authority(results, root, data)
    _check_canonical(results, root, data)
    _check_aliases(results, data)
    _check_unknown_policy(results, root, data)
    return results


def _report(results: List[Tuple[bool, str, str]]) -> int:
    failures = [r for r in results if not r[0]]
    for ok, name, detail in results:
        if ok:
            print(f"[PASS] {name}")
        else:
            print(f"[FAIL] {name} {detail}".rstrip(), file=sys.stderr)
    total = len(results)
    if failures:
        print(
            f"SchemaSnapshot verification FAILED "
            f"({total} checks, {len(failures)} failure(s))",
            file=sys.stderr,
        )
        return 1
    print(f"SchemaSnapshot verification PASSED ({total} checks)")
    return 0


def verify_snapshot(snapshot_path: Optional[Path] = None, root: Optional[Path] = None) -> int:
    """校验入口（可导入复用）：全部通过返回 0，任一失败或异常返回 1。

    - ``snapshot_path``：Snapshot JSON 路径（默认仓库根下相对路径）。
    - ``root``：仓库根目录（默认由本文件位置推导）。
    """
    try:
        resolved_root = _resolve_root(root)
        resolved_snapshot = _resolve_snapshot(snapshot_path, resolved_root)
        results = _verify_all(resolved_root, resolved_snapshot)
        return _report(results)
    except Exception as exc:  # fail-closed：表面化异常，绝不静默通过
        print(
            f"[FAIL] verify_unexpected_exception {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="E-M1 SchemaSnapshot 确定性校验器（离线 fail-closed）"
    )
    parser.add_argument(
        "--snapshot",
        default=None,
        help="Snapshot JSON 路径（默认 interfaces/main_to_data/schema_snapshot.json）",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="仓库根目录（默认由本文件位置推导）",
    )
    args = parser.parse_args(argv)
    return verify_snapshot(
        snapshot_path=Path(args.snapshot) if args.snapshot else None,
        root=Path(args.root) if args.root else None,
    )


if __name__ == "__main__":
    sys.exit(main())
