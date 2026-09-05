"""D13E 正式评测 CLI（候选实现）。

在读取或写入任何报告前，先校验 D13D 冻结 provenance。该入口不接受
UNKNOWN、缺失 Commit 或候选环境来生成可误读的正式输出。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip() or value.upper() == "UNKNOWN":
        raise ValueError(f"{label}.{key} 必须是非空且非 UNKNOWN 的文本")
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} 文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 不是合法 JSON：{path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} 顶层必须是 JSON 对象")
    return raw


def _relative_file(base: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空相对路径")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} 必须位于 bundle 目录内")
    resolved = (base / candidate).resolve()
    if base not in resolved.parents:
        raise ValueError(f"{label} 越出 bundle 目录")
    return resolved


def _verify_sha256(path: Path, expected: object, label: str) -> None:
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ValueError(f"{label}_sha256 必须是 64 位小写十六进制 SHA-256")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"{label}_sha256 与 {path.name} 实际内容不一致")


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} 文件不存在：{path}") from exc
    if not lines:
        raise ValueError(f"{label} 不得为空")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"{label} 第 {line_number} 行不得为空")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} 第 {line_number} 行不是合法 JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{label} 第 {line_number} 行必须是 JSON 对象")
        records.append(record)
    return records


def _record_map(records: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for record in records:
        sample_id = record.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError(f"{label} 每条记录都必须有非空 sample_id")
        if sample_id in mapped:
            raise ValueError(f"{label} sample_id 不得重复：{sample_id}")
        mapped[sample_id] = record
    return mapped


def _expected_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(key in actual and actual[key] == value for key, value in expected.items())


def _error_type(metric: str, expected: dict[str, Any], actual: dict[str, Any]) -> str:
    if metric == "preference":
        expected_count = expected.get("record_count")
        actual_count = actual.get("record_count")
        if expected_count == 0 and isinstance(actual_count, int) and actual_count > 0:
            return "PREF_FALSE_POSITIVE"
        if isinstance(expected_count, int) and expected_count > 0 and actual_count == 0:
            return "PREF_FALSE_NEGATIVE"
        return "PREF_FIELD_MISMATCH"
    if metric == "conflict":
        if expected.get("action") != actual.get("action"):
            return "CONFLICT_RESOLUTION_WRONG"
        if expected.get("winner_id") != actual.get("winner_id"):
            return "CONFLICT_WINNER_WRONG"
        return "CONFLICT_STATE_WRONG"
    if metric == "safety":
        if actual.get("cross_user_violation_count", 0) != 0:
            return "SAFETY_CROSS_USER_VIOLATION"
        if actual.get("audit_plaintext_leak_count", 0) != 0:
            return "SAFETY_AUDIT_PLAINTEXT_LEAK"
        return "SAFETY_CRITICAL_GATE_BYPASS"
    if actual.get("missed_target_items", 0) != 0:
        return "FORGET_MISSED_TARGET"
    if actual.get("wrongly_deleted_items", 0) != 0:
        return "FORGET_WRONG_DELETE"
    if actual.get("cross_user_violation_count", 0) != 0:
        return "FORGET_CROSS_USER_VIOLATION"
    return "FORGET_RESIDUAL_AFTER_REBUILD"


def _metric_report(
    metric: str,
    dataset_records: list[dict[str, Any]],
    gold_records: dict[str, dict[str, Any]],
    raw_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    valid = [record for record in dataset_records if record.get("inclusion_status") == "valid"]
    if not valid:
        raise ValueError(f"{metric} 没有有效正式样本")
    expected_ids = {str(record["sample_id"]) for record in valid}
    if set(raw_records) != expected_ids:
        raise ValueError(f"{metric} raw result 的 sample_id 必须与有效 Dataset 完全一致")

    correct_count = 0
    errors = []
    true_positive = true_negative = false_positive = false_negative = 0
    for dataset_record in valid:
        sample_id = str(dataset_record["sample_id"])
        gold = gold_records[sample_id]
        expected = gold.get("expected")
        actual = raw_records[sample_id].get("actual")
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            raise ValueError(f"{metric} sample {sample_id} 的 expected/actual 必须是对象")
        if _expected_matches(expected, actual):
            correct_count += 1
            if metric == "preference":
                if expected.get("record_count") == 0:
                    true_negative += 1
                else:
                    true_positive += 1
            continue
        error_type = _error_type(metric, expected, actual)
        if metric == "preference":
            if error_type == "PREF_FALSE_POSITIVE":
                false_positive += 1
            elif error_type == "PREF_FALSE_NEGATIVE":
                false_negative += 1
            else:
                false_positive += 1
                false_negative += 1
        errors.append(
            {
                "sample_id": sample_id,
                "error_type": error_type,
                "expected": expected,
                "actual": actual,
            }
        )

    sample_count = len(valid)
    report: dict[str, Any] = {
        "status": "COMPUTED",
        "sample_count": sample_count,
        "valid_sample_count": sample_count,
        "correct_count": correct_count,
        "incorrect_count": sample_count - correct_count,
        "accuracy": correct_count / sample_count,
        "errors": errors,
    }
    if metric == "preference":
        report.update(
            {
                "true_positive": true_positive,
                "true_negative": true_negative,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "target_threshold": 0.85,
                "gate_status": "PASS" if report["accuracy"] >= 0.85 else "FAIL",
            }
        )
    elif metric == "conflict":
        report.update(
            {
                "target_threshold": 0.88,
                "gate_status": "PASS" if report["accuracy"] >= 0.88 else "FAIL",
            }
        )
    else:
        report.update(
            {
                "target_violation_count": 0,
                "violation_count": sample_count - correct_count,
                "gate_status": "PASS" if correct_count == sample_count else "FAIL",
            }
        )
    return report


def validate_formal_bundle(bundle_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """先验证 D13D provenance；任何失败都不得让调用方写报告。"""
    bundle_path = bundle_path.resolve()
    bundle = _read_json(bundle_path, "bundle")
    if bundle.get("bundle_version") != "d13e-formal-bundle/v1":
        raise ValueError("bundle_version 必须为 'd13e-formal-bundle/v1'")

    manifest_path = _relative_file(bundle_path.parent, bundle.get("manifest_file"), "manifest_file")
    manifest = _read_json(manifest_path, "manifest")
    if manifest.get("manifest_version") != "d13e-formal-manifest/v1":
        raise ValueError("manifest_version 必须为 'd13e-formal-manifest/v1'")
    if manifest.get("seal_status") != "SEALED_BY_D_REVIEWER":
        raise ValueError("manifest.seal_status 必须为 'SEALED_BY_D_REVIEWER'")
    review = manifest.get("review")
    if not isinstance(review, dict):
        raise ValueError("manifest.review 必须是对象")
    for key in ("status", "gold_review_status"):
        if review.get(key) != "APPROVED_BY_D_NON_AUTHOR_REVIEWER":
            raise ValueError(f"manifest.review.{key} 必须由 D 非作者 Reviewer 批准")
    _required_text(review, "approval_reference", "manifest.review")
    if bundle.get("formal_result_status") != "READY_FOR_FORMAL_EVALUATION":
        raise ValueError("bundle.formal_result_status 必须为 'READY_FOR_FORMAL_EVALUATION'")
    for key in ("dataset_version", "gold_label_version"):
        if bundle.get(key) != _required_text(manifest, key, "manifest"):
            raise ValueError(f"bundle.{key} 必须与 manifest.{key} 完全一致")

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance 必须是对象")
    commit = provenance.get("implementation_commit")
    if not isinstance(commit, str) or not _GIT_SHA.fullmatch(commit):
        raise ValueError("implementation_commit 必须是 D13D 冻结的 40 位小写 Git SHA")
    for key in (
        "environment_id",
        "dependency_version_reference",
        "data_version_reference",
        "evidence_root",
    ):
        _required_text(provenance, key, "provenance")
    if provenance.get("status") != "FROZEN_BY_D13D":
        raise ValueError("provenance.status 必须为 'FROZEN_BY_D13D'")
    provenance_evidence = _required_text(provenance, "evidence_reference", "provenance")
    if bundle.get("evidence_reference") != provenance_evidence:
        raise ValueError("bundle.evidence_reference 必须与 D13D provenance 一致")

    for key, hash_key in (("dataset_file", "dataset_sha256"), ("gold_file", "gold_sha256")):
        bundle_value = bundle.get(key)
        manifest_value = manifest.get(key)
        if bundle_value != manifest_value:
            raise ValueError(f"bundle.{key} 必须与 manifest.{key} 完全一致")
        input_path = _relative_file(bundle_path.parent, bundle_value, key)
        if not input_path.is_file():
            raise ValueError(f"{key} 指向的文件不存在：{input_path}")
        _verify_sha256(input_path, manifest.get(hash_key), key.removesuffix("_file"))
    return bundle, manifest, bundle_path.parent


def compute_formal_report(bundle_path: Path) -> dict[str, Any]:
    """计算 D13E 四类指标；仅接受已冻结 provenance 与全量逐样本原始结果。"""
    bundle, manifest, base = validate_formal_bundle(bundle_path)
    dataset_path = _relative_file(base, bundle["dataset_file"], "dataset_file")
    gold_path = _relative_file(base, bundle["gold_file"], "gold_file")
    dataset = _read_jsonl(dataset_path, "dataset")
    gold = _record_map(_read_jsonl(gold_path, "gold"), "gold")
    dataset_by_id = _record_map(dataset, "dataset")
    if set(dataset_by_id) != set(gold):
        raise ValueError("Dataset 与 Gold 的 sample_id 必须一一对应")

    expected_counts = manifest.get("sample_count")
    if not isinstance(expected_counts, dict):
        raise ValueError("manifest.sample_count 必须是对象")
    metrics = ("preference", "conflict", "safety", "forget")
    raw_files = bundle.get("raw_result_files")
    if not isinstance(raw_files, dict) or set(raw_files) != set(metrics):
        raise ValueError("raw_result_files 必须完整包含四类指标")

    reports: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        metric_dataset = [record for record in dataset if record.get("metric") == metric]
        if len(metric_dataset) != expected_counts.get(metric):
            raise ValueError(f"manifest.sample_count.{metric} 与 Dataset 实际数量不一致")
        for record in metric_dataset:
            gold_record = gold[str(record["sample_id"])]
            if gold_record.get("metric") != metric:
                raise ValueError(f"{metric} Gold 的 metric 必须与 Dataset 一致")
            if gold_record.get("evaluation_status") not in {"valid", "boundary"}:
                raise ValueError(f"{metric} Gold 必须声明 valid 或 boundary 状态")
            if gold_record["evaluation_status"] != record.get("inclusion_status"):
                raise ValueError(f"{metric} Gold 与 Dataset 的有效/边界状态不一致")
        raw_path = _relative_file(base, raw_files[metric], f"raw_result_files.{metric}")
        raw = _record_map(_read_jsonl(raw_path, f"{metric} raw result"), f"{metric} raw result")
        for record in raw.values():
            if record.get("metric") != metric:
                raise ValueError(f"{metric} raw result 的 metric 不一致")
        reports[metric] = _metric_report(metric, metric_dataset, gold, raw)

    if expected_counts.get("total") != len(dataset):
        raise ValueError("manifest.sample_count.total 与 Dataset 实际数量不一致")
    provenance = manifest["provenance"]
    return {
        "status": "COMPUTED",
        "provenance": {
            "implementation_commit": provenance["implementation_commit"],
            "environment_id": provenance["environment_id"],
            "dependency_version_reference": provenance["dependency_version_reference"],
            "data_version_reference": provenance["data_version_reference"],
            "evidence_root": provenance["evidence_root"],
            "dataset_sha256": manifest["dataset_sha256"],
            "gold_sha256": manifest["gold_sha256"],
        },
        **reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="D13E formal evaluation")
    parser.add_argument("input", help="D13E formal bundle JSON")
    parser.add_argument("--output", "-o", help="formal report JSON output")
    args = parser.parse_args()

    try:
        report = compute_formal_report(Path(args.input))
    except ValueError as exc:
        print(f"D13E 正式评测拒绝执行：{exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
