"""
test_d6_multisource_devset.py — Day6E 多源开发集 v1 验证测试

对齐任务卡：day6-e-03-multisource-devset-error-taxonomy-v1

目标：校验 `D6_MULTISOURCE_DEVSET_V1.jsonl` 的完整性与一致性：
- JSONL 逐行合法 JSON；必填字段完整；sample_id 全局唯一且格式合法；
- 总样本 >= 90，三类 source_family 各 >= 30；每类覆盖
  normal / boundary / error / security_attack 四种类别；
- 全部枚举合法（source_family / sample_category / expected_gate /
  expected_memory_kind / expected_security_decision / annotation_status /
  tool_execution_status / mapping_status / attack_tags）；
- expected_error_codes 中每个元素都必须在
  `D6_MULTISOURCE_ERROR_TAXONOMY_V1.md` 中有定义（taxonomy 解析失败即失败，
  不允许默认空集合通过）；
- behavior_candidate 映射状态必须为 PENDING_C_CONFIRMATION，且不得被冻结为
  共享 SourceType（不新增 SourceType=behavior）；
- tool_result 覆盖 success / failed / cancelled / timeout / partial /
  unchecked_payload 六种状态各 >= 1；
- 非攻击样本 attack_tags 必须为空数组；
- 敏感样本使用占位标记；全文无真实凭据模式。

测试纪律：
- 不使用 pytest.skip / xfail / 无条件 pass；不吞异常；不自动修正非法 JSON；
  不跳过坏行；所有断言为硬断言（assert）。
- 测试自包含：仅使用标准库（json / re / pathlib）+ pytest，
  **不导入 memory-service 任何模块**。
- 非法 JSON 行 / 重复 sample_id / 缺字段 / 未知 error code / 数量不足时
  本测试必须真实失败。
"""

import json
import re
from pathlib import Path

import pytest

# ── 文件定位 ──

EVAL_DIR = Path(__file__).resolve().parent
DEVSET_PATH = EVAL_DIR / "D6_MULTISOURCE_DEVSET_V1.jsonl"
TAXONOMY_PATH = EVAL_DIR / "D6_MULTISOURCE_ERROR_TAXONOMY_V1.md"
README_PATH = EVAL_DIR / "D6_MULTISOURCE_DEVSET_README_V1.md"

# ── 合法枚举（与 D6_MULTISOURCE_DEVSET_README_V1.md 对齐） ──

SOURCE_FAMILIES = {"tool_result", "behavior_candidate", "manual_config"}
SAMPLE_CATEGORIES = {"normal", "boundary", "error", "security_attack"}
EXPECTED_GATES = {"allow_extraction", "audit_only", "reject"}
EXPECTED_MEMORY_KINDS = {
    "none", "preference", "success_knowledge", "failure_experience", "all",
}
EXPECTED_SECURITY_DECISIONS = {"allow", "deny", "audit_only", "conditional"}
ANNOTATION_STATUSES = {"candidate", "pending_review"}
MAPPING_STATUSES = {"PENDING_C_CONFIRMATION"}
TOOL_EXECUTION_STATUSES = {
    "success", "failed", "cancelled", "timeout", "partial", "unchecked_payload",
}
ATTACK_TAGS = {
    "prompt_injection", "sensitive_leak", "cross_user", "tool_status_injection",
    "identity_injection", "provenance_injection", "memory_status_injection",
    "ignored_bypass", "payload_bypass", "temporary_to_persistent",
    "schema_violation", "config_conflict",
}
# 与敏感/凭据/隔离相关的攻击族（此类 security_attack 样本的 input_case
# 必须包含占位标记词）
SENSITIVE_TAGS = {
    "sensitive_leak", "payload_bypass", "cross_user",
    "identity_injection", "provenance_injection",
}

REQUIRED_FIELDS = (
    "sample_id",
    "source_family",
    "sample_category",
    "input_case",
    "expected_gate",
    "expected_should_extract",
    "expected_memory_kind",
    "expected_security_decision",
    "expected_error_codes",
    "attack_tags",
    "annotation_status",
    "notes",
)

SAMPLE_ID_RE = re.compile(r"^d6-(tr|bc|mc)-\d{3}$")

# 错误分类表代码提取正则（与 taxonomy README 约定一致）
TAXONOMY_CODE_RE = re.compile(
    r"\b((?:SEC-SENS|SEC-PII|SEC-UI|Q|SRC|PROV|TOOL|LIFE|DUP|CONTRACT)-\d{3})\b"
)

# 禁止的真实凭据模式（敏感占位约束；sk-demo-PLACEHOLDER-* 等占位不受限）
REAL_CREDENTIAL_PATTERNS = [
    re.compile(r"(?i)sk-(?:live|prod|real|actual)-"),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)password=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
    re.compile(r"(?i)token=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
    re.compile(r"(?i)api[_-]?key=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
]

# 敏感占位标记词（README 声明；input_case 命中任一即可）
PLACEHOLDER_MARKERS = ("PLACEHOLDER", "fake", "demo", "REDACTED", "DUMMY", "虚构", "测试用")


# ── 读取辅助（读取失败/解析异常直接冒泡为测试失败，不吞异常） ──


def _read_raw_lines() -> list:
    with DEVSET_PATH.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


@pytest.fixture(scope="module")
def raw_lines():
    assert DEVSET_PATH.exists(), "开发集 JSONL 文件不存在"
    return _read_raw_lines()


@pytest.fixture(scope="module")
def records(raw_lines):
    # 非法 JSON 行 → json.JSONDecodeError 直接冒泡 → 测试失败（不跳过坏行）
    return [json.loads(ln) for ln in raw_lines]


@pytest.fixture(scope="module")
def taxonomy_codes():
    assert TAXONOMY_PATH.exists(), "错误分类表文件不存在"
    text = TAXONOMY_PATH.read_text(encoding="utf-8")
    codes = set(TAXONOMY_CODE_RE.findall(text))
    assert codes, "错误分类表未解析出任何错误代码（不允许默认空集合通过）"
    return codes


def _family_records(records, family):
    return [rec for rec in records if rec["source_family"] == family]


# ── 文件存在性 ──


def test_devset_file_exists():
    assert DEVSET_PATH.exists(), "D6_MULTISOURCE_DEVSET_V1.jsonl 不存在"


def test_taxonomy_file_exists():
    assert TAXONOMY_PATH.exists(), "D6_MULTISOURCE_ERROR_TAXONOMY_V1.md 不存在"


def test_readme_file_exists():
    assert README_PATH.exists(), "D6_MULTISOURCE_DEVSET_README_V1.md 不存在"


# ── 结构与必填字段 ──


def test_jsonl_all_lines_valid_json(raw_lines):
    for ln in raw_lines:
        obj = json.loads(ln)  # 非法 JSON 行必须真实抛错（不吞异常）
        assert isinstance(obj, dict), "JSONL 行不是 JSON 对象"


def test_required_fields_present(records):
    for rec in records:
        for field in REQUIRED_FIELDS:
            assert field in rec, f"{rec.get('sample_id', '?')} 缺少必填字段 {field}"


def test_sample_id_unique(records):
    ids = [rec["sample_id"] for rec in records]
    assert len(ids) == len(set(ids)), "存在重复 sample_id"


def test_sample_id_non_empty(records):
    for rec in records:
        assert isinstance(rec["sample_id"], str) and rec["sample_id"], (
            f"sample_id 必须为非空字符串: {rec['sample_id']!r}"
        )


def test_sample_id_format(records):
    expected_hint = "d6-tr-001 / d6-bc-001 / d6-mc-001（tr/bc/mc 对应三类 source_family）"
    for rec in records:
        assert SAMPLE_ID_RE.match(rec["sample_id"]), (
            f"sample_id 格式非法: {rec['sample_id']}，应为 {expected_hint}"
        )


def test_input_case_non_empty(records):
    for rec in records:
        assert isinstance(rec["input_case"], str) and rec["input_case"], (
            f"{rec['sample_id']} 的 input_case 必须为非空字符串"
        )


def test_expected_should_extract_is_boolean(records):
    for rec in records:
        assert isinstance(rec["expected_should_extract"], bool), (
            f"{rec['sample_id']} 的 expected_should_extract 必须为布尔值"
        )


def test_error_codes_array_type(records):
    for rec in records:
        assert isinstance(rec["expected_error_codes"], list), (
            f"{rec['sample_id']} 的 expected_error_codes 必须为数组"
        )


def test_attack_tags_array_type(records):
    for rec in records:
        assert isinstance(rec["attack_tags"], list), (
            f"{rec['sample_id']} 的 attack_tags 必须为数组"
        )


# ── 数量与分布 ──


def test_total_sample_count(records):
    assert len(records) >= 90, f"总样本数 {len(records)} 不足 90"


def test_source_family_counts(records):
    for family in SOURCE_FAMILIES:
        count = len(_family_records(records, family))
        assert count >= 30, f"source_family={family} 样本数 {count} 不足 30"


def test_each_family_has_all_four_categories(records):
    for family in SOURCE_FAMILIES:
        categories = {rec["sample_category"] for rec in _family_records(records, family)}
        assert categories == SAMPLE_CATEGORIES, (
            f"source_family={family} 类别覆盖不完整: {sorted(categories)}"
        )


def test_tool_result_status_coverage(records):
    statuses = {
        rec["tool_execution_status"]
        for rec in _family_records(records, "tool_result")
    }
    assert statuses == TOOL_EXECUTION_STATUSES, (
        f"tool_result 状态覆盖不完整（需 success/failed/cancelled/timeout/"
        f"partial/unchecked_payload 各 >=1）: {sorted(statuses)}"
    )


# ── 枚举合法性 ──


def test_source_family_valid_enum(records):
    for rec in records:
        assert rec["source_family"] in SOURCE_FAMILIES, (
            f"{rec['sample_id']} 未知 source_family: {rec['source_family']}"
        )


def test_sample_category_valid_enum(records):
    for rec in records:
        assert rec["sample_category"] in SAMPLE_CATEGORIES, (
            f"{rec['sample_id']} 未知 sample_category: {rec['sample_category']}"
        )


def test_expected_gate_valid_enum(records):
    for rec in records:
        assert rec["expected_gate"] in EXPECTED_GATES, (
            f"{rec['sample_id']} 未知 expected_gate: {rec['expected_gate']}"
        )


def test_expected_memory_kind_valid_enum(records):
    for rec in records:
        assert rec["expected_memory_kind"] in EXPECTED_MEMORY_KINDS, (
            f"{rec['sample_id']} 未知 expected_memory_kind: {rec['expected_memory_kind']}"
        )


def test_expected_security_decision_valid_enum(records):
    for rec in records:
        assert rec["expected_security_decision"] in EXPECTED_SECURITY_DECISIONS, (
            f"{rec['sample_id']} 未知 expected_security_decision: "
            f"{rec['expected_security_decision']}"
        )


def test_annotation_status_valid_enum(records):
    for rec in records:
        assert rec["annotation_status"] in ANNOTATION_STATUSES, (
            f"{rec['sample_id']} 未知 annotation_status: {rec['annotation_status']}"
        )


def test_attack_tags_valid_enum(records):
    for rec in records:
        for tag in rec["attack_tags"]:
            assert tag in ATTACK_TAGS, (
                f"{rec['sample_id']} 未知 attack_tag: {tag}"
            )


# ── 错误码与 taxonomy 一致性 ──


def test_error_codes_exist_in_taxonomy(records, taxonomy_codes):
    for rec in records:
        for code in rec["expected_error_codes"]:
            assert code in taxonomy_codes, (
                f"{rec['sample_id']} 引用了未在错误分类表中定义的错误码 {code}"
            )


def test_expected_error_codes_empty_when_no_error(records):
    for rec in records:
        if (
            rec["expected_gate"] == "allow_extraction"
            and rec["sample_category"] == "normal"
        ):
            assert rec["expected_error_codes"] == [], (
                f"{rec['sample_id']} 正常样本不应携带错误码"
            )


# ── 攻击样本约束 ──


def test_non_attack_samples_empty_attack_tags(records):
    for rec in records:
        if rec["sample_category"] != "security_attack":
            assert rec["attack_tags"] == [], (
                f"{rec['sample_id']} 非攻击样本 attack_tags 必须为空数组"
            )


def test_sensitive_samples_use_placeholders(records):
    for rec in records:
        if rec["sample_category"] == "security_attack" and any(
            tag in SENSITIVE_TAGS for tag in rec["attack_tags"]
        ):
            assert any(
                marker in rec["input_case"] for marker in PLACEHOLDER_MARKERS
            ), f"{rec['sample_id']} 敏感攻击样本 input_case 缺少占位标记词"


def test_no_real_credentials(raw_lines):
    full_text = "\n".join(raw_lines)
    for pat in REAL_CREDENTIAL_PATTERNS:
        assert not pat.search(full_text), (
            f"开发集 JSONL 中出现疑似真实凭据模式: {pat.pattern}"
        )


# ── behavior_candidate 映射约束 ──


def test_behavior_mapping_status(records):
    for rec in _family_records(records, "behavior_candidate"):
        assert rec.get("mapping_status") in MAPPING_STATUSES, (
            f"{rec['sample_id']} behavior_candidate 必须标记 "
            f"mapping_status=PENDING_C_CONFIRMATION"
        )


def test_behavior_not_frozen_as_source_type(records):
    for rec in records:
        # 任何样本都不得把 behavior 直列成已冻结的 source_type 字段
        assert "source_type" not in rec, (
            f"{rec['sample_id']} 不得携带生产契约 source_type 字段"
        )
        text = f"{rec['input_case']} {rec['notes']}".lower()
        assert "frozen_source_type" not in text, (
            f"{rec['sample_id']} 不得声称已冻结 SourceType 映射"
        )
        assert "source_type=behavior" not in text, (
            f"{rec['sample_id']} 不得伪造 SourceType=behavior"
        )


# ── tool_result 条件字段 ──


def test_tool_result_has_execution_status(records):
    for rec in _family_records(records, "tool_result"):
        assert "tool_execution_status" in rec, (
            f"{rec['sample_id']} tool_result 必须携带 tool_execution_status"
        )


def test_tool_execution_status_valid_enum(records):
    for rec in _family_records(records, "tool_result"):
        assert rec["tool_execution_status"] in TOOL_EXECUTION_STATUSES, (
            f"{rec['sample_id']} 未知 tool_execution_status: "
            f"{rec['tool_execution_status']}"
        )