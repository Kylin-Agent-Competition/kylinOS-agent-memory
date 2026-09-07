#!/usr/bin/env python3
"""verify_main_to_data_schema_snapshot.py — E-M1 SchemaSnapshot 确定性校验器

对冻结的 ``interfaces/main_to_data/schema_snapshot.json`` 与仓库当前代码 SSOT
（``memory-service/domain/enums.py``、``memory-service/pipeline/schemas.py``）以及
Canonical 文档（``KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md``）做确定性、离线、
fail-closed 的一致性校验。

设计要点：
- 纯离线、确定性、无网络与 Runtime 依赖；以仓库根目录为稳定定位基准
  （默认由本文件位置推导 ``parents[1]``）。
- 判定数据全部来自真实输入（Snapshot 文件 + 动态导入的当前代码 SSOT +
  Canonical 文档文本），不硬编码任何成功取值。
- fail-closed：Snapshot JSON 不可解析、漂移、缺字段、非法 provenance、
  无法导入或解析代码 SSOT、Canonical 文档缺失/非 FROZEN 均返回 exit 1。
  任何内部异常都会以 ``[FAIL]`` 形式输出并返回 1，绝不吞掉或静默降级。

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
    "authority",
    "canonical",
    "aliases_and_mappings",
    "unknown_policy",
)
ALIAS_SECTIONS = ("frozen_stable", "deprecated_or_compatibility", "pending_mapping")

_FROZEN_DECL_RE = re.compile(r"状态\s*[：:]\s*FROZEN")


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
    """按文档首部状态声明判断 FROZEN（容忍 **加粗** 与 `反引号` 标记）。"""
    normalized = re.sub(r"[`*_]", "", text)
    return bool(_FROZEN_DECL_RE.search(normalized))


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

    # provenance：结构完整（必需键为非空字符串）
    provenance = authority.get("provenance")
    if not isinstance(provenance, dict):
        _fail(results, "provenance_object", f"type={type(provenance).__name__}")
    else:
        for key in PROVENANCE_REQUIRED_KEYS:
            value = provenance.get(key)
            if not isinstance(value, str) or not value:
                _fail(results, "provenance_field", f"missing/empty field: {key}")


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


def _check_unknown_policy(results, data: Dict[str, Any]) -> None:
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
    _check_unknown_policy(results, data)
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
