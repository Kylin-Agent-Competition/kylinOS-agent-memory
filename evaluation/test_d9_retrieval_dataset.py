"""
test_d9_retrieval_dataset.py — Day9E 检索 Corpus 与 Query 候选集 v2 验证测试

对齐任务卡：day9-e-rw-02-dataset-retrieval-ref-v2-manual-cleanup-v2

目标：只校验 `D9_RETRIEVAL_CORPUS_V2.jsonl` 与
`D9_RETRIEVAL_QUERYSET_CANDIDATE_V2.jsonl` 的 V2 正式 Dataset 契约（消费
Gold Policy/Spec v2，不重新定义任何 Gold 规则）：

- JSONL 逐行合法 JSON；必填字段完整；corpus 行主键 (memory_id, version_id)
  全局唯一、query_id 全局唯一且格式合法；
- 引用键为版本级 retrieval_ref：每个 ref 为对象且恰好 `{memory_id, version_id}`
  两键；`relevant_ids` / `near_miss_refs` 为禁现 legacy 字段；
- Corpus 枚举合法；每 memory_id 恰一条 is_current=true；同 memory 各版本
  user_id / knowledge_type / knowledge_id 一致；knowledge_id 为独立合成标识
  `d9k-{NNN}` 且必须 != memory_id（不声明与 memory_id 的生产等价映射）；
- distractor_tag 与行属性一致性（含新增 deprecated 取值）；
- Corpus 覆盖：总数 >= 62；positive-answerable 六类 knowledge_type 各 >= 4；
  七类危险干扰（removed_or_forgotten / expired / superseded / candidate /
  unresolved_conflict / cross_user / stale_version）各 >= 2 + deprecated >= 1；
  user_id >= 2；
- Query 枚举合法；角色约束：positive_retrieval 的 relevant_refs 非空且每个 ref
  精确命中同用户 positive-answerable 的确切版本行；negative_guardrail 的
  relevant_refs 为空、guardrail_category ∈ 八类（含 deprecated）、每条 >= 1 个
  forbidden_refs；boundary 无配额（仅当出现时校验字段约束）；
- 引用完整性：relevant_refs / forbidden_refs / semantic_near_miss_refs 均精确
  解析到 (memory_id, version_id) 的确切版本行；forbidden 覆盖九态版本级禁止
  形态（deprecated / removed / expired / superseded / candidate / unresolved /
  cross-user / sensitive / stale version）；cross-user forbidden ref 必须解析到
  另一个 user 的 corpus 行并被判禁止；同 query 内三桶两两不相交；
- B 轨 2026-08-31 PR #88 裁决锚定：d9q-001/007/010 的 stale v1 与 current v2
  版本级拆分；d9q-003/016 问法改写并指向 d9c-005-v1 / d9c-029-v1；
  d9q-007 的 d9c-038-v2 不属 forbidden_refs；d9q-033/034/035/036 从 V2 消失；
  存在全新 query_id 的真实 deprecated guardrail 查询；
- 覆盖配额由真实样本决定（无 boundary>=4 / query>=36 要求）；README 必须
  明确不得用治理问题填充检索 Gold、knowledge_id↔memory_id 生产映射
  PENDING_D_CONFIRMATION；
- 全文无真实凭据模式；JSONL 数据中不出现 reviewed / sealed 状态令牌；
- 非法 JSON / 重复 ID / 缺字段 / 未知枚举 / 覆盖不足 / 引用悬空 /
  禁现字段 / 状态令牌出现时本测试必须真实失败。

测试纪律（沿用 test_d6_multisource_devset.py / test_d9_retrieval_gold_spec.py）：
- 不使用 pytest.skip / xfail / 无条件 pass；不吞异常；不自动修正非法 JSON；
  不跳过坏行；所有断言为硬断言（assert）。
- 测试自包含：仅使用标准库（json / re / pathlib）+ pytest，
  **不导入 memory-service 任何模块**。
- 本测试只验证 V2 三件；不读取 V1 文件、不含「V1 文件必须不存在」断言
  （V1 三件由人工清理步骤移除，删除不属本测试职责）。
"""

import json
import re
from pathlib import Path

import pytest

# ── 文件定位（仅 V2） ──

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_PATH = EVAL_DIR / "D9_RETRIEVAL_CORPUS_V2.jsonl"
QUERY_PATH = EVAL_DIR / "D9_RETRIEVAL_QUERYSET_CANDIDATE_V2.jsonl"
README_PATH = EVAL_DIR / "D9_RETRIEVAL_DATASET_README_V2.md"

# ── 合法枚举（对齐 README v2 / D9 gold policy v2） ──

KNOWLEDGE_TYPES = {
    "workflow", "case", "template", "fact", "constraint", "failure_experience",
}
MEMORY_STATUSES = {"active", "superseded", "deprecated", "expired", "removed", "candidate"}
MEMORY_TYPES = {"short_term", "medium_term", "long_term", "ephemeral"}
SENSITIVITIES = {"none", "low", "medium", "high", "critical"}
CONFLICT_STATES = {"none", "resolved", "unresolved"}
DISTRACTOR_TAGS = {
    "removed_or_forgotten", "expired", "superseded", "deprecated", "candidate",
    "unresolved_conflict", "cross_user", "sensitive_recall_prohibited",
    "stale_version",
}
EVALUATION_ROLES = {"positive_retrieval", "negative_guardrail", "boundary"}
ANNOTATION_STATUSES = {"candidate", "pending_review"}
GUARDRAIL_CATEGORIES = {
    "removed_or_forgotten", "expired", "superseded", "deprecated", "candidate",
    "unresolved_conflict", "cross_user", "sensitive_recall_prohibited",
}
FORBIDDEN_VERSION_FORMS = {
    "deprecated", "removed", "expired", "superseded", "candidate", "unresolved",
    "cross_user", "sensitive", "stale_version",
}
SYNTHETIC_USERS = {"user_demo_d9e_a", "user_demo_d9e_b"}

# ── 必填字段 ──

CORPUS_REQUIRED_FIELDS = (
    "memory_id",
    "version_id",
    "knowledge_id",
    "user_id",
    "object_type",
    "memory_type",
    "knowledge_type",
    "primary_category",
    "content_summary",
    "source_event_id",
    "memory_status",
    "sensitivity",
    "conflict_state",
    "is_current",
    "relation_ids",
    "distractor_tag",
    "notes",
)

QUERY_REQUIRED_FIELDS = (
    "query_id",
    "query",
    "user_id",
    "evaluation_role",
    "relevant_refs",
    "forbidden_refs",
    "semantic_near_miss_refs",
    "guardrail_category",
    "guardrail_reason",
    "boundary_reason",
    "rationale",
    "annotation_status",
    "notes",
)

# V1 legacy 引用字段：正式 V2 契约中禁止出现（任何记录出现即失败）
LEGACY_QUERY_FIELDS = ("relevant_ids", "near_miss_refs")

# ── ID 与引用格式 ──

MEMORY_ID_RE = re.compile(r"^d9c-\d{3}$")
VERSION_ID_RE = re.compile(r"^d9c-\d{3}-v[1-9]\d*$")
QUERY_ID_RE = re.compile(r"^d9q-\d{3}$")
KNOWLEDGE_ID_RE = re.compile(r"^d9k-\d{3}$")

# ── 伪状态令牌（对 JSONL 数据正文扫描；annotation_status 值仅
#    candidate/pending_review，data 中不得出现 reviewed/sealed 词） ──

FORBIDDEN_TOKENS = [
    re.compile(r"\breviewed\b", re.IGNORECASE),
    re.compile(r"\bsealed\b", re.IGNORECASE),
]

# ── 禁止的真实凭据模式（沿用 D6 / D9 gold 纪律） ──

REAL_CREDENTIAL_PATTERNS = [
    re.compile(r"(?i)sk-(?:live|prod|real|actual)-"),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)password=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
    re.compile(r"(?i)token=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
    re.compile(r"(?i)api[_-]?key=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
]


# ── 读取辅助（读取/解析异常直接冒泡为测试失败，不吞异常、不跳过坏行） ──


def _read_raw_lines(path: Path) -> list:
    with path.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


@pytest.fixture(scope="module")
def corpus_raw_lines():
    assert CORPUS_PATH.exists(), "Corpus V2 JSONL 文件不存在"
    return _read_raw_lines(CORPUS_PATH)


@pytest.fixture(scope="module")
def query_raw_lines():
    assert QUERY_PATH.exists(), "Query V2 JSONL 文件不存在"
    return _read_raw_lines(QUERY_PATH)


@pytest.fixture(scope="module")
def corpus_records(corpus_raw_lines):
    # 非法 JSON 行 -> json.JSONDecodeError 直接冒泡 -> 测试失败
    return [json.loads(ln) for ln in corpus_raw_lines]


@pytest.fixture(scope="module")
def query_records(query_raw_lines):
    return [json.loads(ln) for ln in query_raw_lines]


@pytest.fixture(scope="module")
def readme_text():
    assert README_PATH.exists(), "数据集 V2 README 文件不存在"
    return README_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def corpus_by_version(corpus_records):
    mapping = {}
    for rec in corpus_records:
        key = (rec["memory_id"], rec["version_id"])
        assert key not in mapping, f"重复 (memory_id, version_id): {key}"
        mapping[key] = rec
    return mapping


@pytest.fixture(scope="module")
def corpus_by_memory_id(corpus_records):
    groups = {}
    for rec in corpus_records:
        groups.setdefault(rec["memory_id"], []).append(rec)
    return groups


def _ref(memory_id: str, version_id: str) -> dict:
    return {"memory_id": memory_id, "version_id": version_id}


def _positive_answerable(row):
    return (
        row["memory_status"] == "active"
        and row["is_current"] is True
        and row["conflict_state"] != "unresolved"
        and row["sensitivity"] in ("none", "low", "medium")
        and row["distractor_tag"] is None
    )


def _business_not_recallable_for(row, query_user):
    # V1 _business_not_recallable_for 的 v2 扩展：memory_status 集合加入 deprecated
    return (
        row["user_id"] != query_user
        or row["memory_status"]
        in ("expired", "superseded", "removed", "candidate", "deprecated")
        or row["conflict_state"] == "unresolved"
        or row["is_current"] is False
        or row["sensitivity"] in ("high", "critical")
        or row["distractor_tag"] is not None
    )


def _all_refs(rec):
    return rec["relevant_refs"] + rec["forbidden_refs"] + rec["semantic_near_miss_refs"]


def _find_query(query_records, query_id):
    for rec in query_records:
        if rec["query_id"] == query_id:
            return rec
    raise AssertionError(f"Query 集合中不存在 {query_id}")


# ── 文件存在性 ──


def test_corpus_file_exists():
    assert CORPUS_PATH.exists()


def test_query_file_exists():
    assert QUERY_PATH.exists()


def test_readme_file_exists():
    assert README_PATH.exists()


# ── JSONL 结构与必填字段 ──


def test_jsonl_all_lines_valid_json(corpus_raw_lines, query_raw_lines):
    for ln in corpus_raw_lines + query_raw_lines:
        obj = json.loads(ln)  # 非法 JSON 行必须真实抛错
        assert isinstance(obj, dict), "JSONL 行不是 JSON 对象"


def test_corpus_required_fields_present(corpus_records):
    for rec in corpus_records:
        for field in CORPUS_REQUIRED_FIELDS:
            assert field in rec, f"{rec.get('memory_id', '?')} 缺少必填字段 {field}"


def test_query_required_fields_present(query_records):
    for rec in query_records:
        for field in QUERY_REQUIRED_FIELDS:
            assert field in rec, f"{rec.get('query_id', '?')} 缺少必填字段 {field}"


def test_query_legacy_ref_fields_absent(query_records):
    for rec in query_records:
        for legacy in LEGACY_QUERY_FIELDS:
            assert legacy not in rec, (
                f"{rec['query_id']} 出现 V1 legacy 字段 {legacy}（V2 契约禁止）"
            )


# ── ID 唯一性与格式 ──


def test_memory_id_format(corpus_records):
    for rec in corpus_records:
        assert isinstance(rec["memory_id"], str) and MEMORY_ID_RE.match(
            rec["memory_id"]
        ), f"memory_id 格式非法: {rec['memory_id']}"  # noqa: E501


def test_version_id_format(corpus_records):
    for rec in corpus_records:
        assert isinstance(rec["version_id"], str) and VERSION_ID_RE.match(
            rec["version_id"]
        ), f"version_id 格式非法: {rec['version_id']}"  # noqa: E501
        assert rec["version_id"].startswith(rec["memory_id"] + "-v"), (
            f"version_id 必须基于 memory_id: {rec['version_id']}"
        )


def test_memory_version_key_unique(corpus_records):
    keys = [(rec["memory_id"], rec["version_id"]) for rec in corpus_records]
    assert len(keys) == len(set(keys)), "存在重复 (memory_id, version_id) 行"


def test_knowledge_id_independent_format(corpus_records):
    # V2：knowledge_id 为相互独立的合成标识，必须 != memory_id（替代 v1 同值断言）
    for rec in corpus_records:
        assert isinstance(rec["knowledge_id"], str) and KNOWLEDGE_ID_RE.match(
            rec["knowledge_id"]
        ), f"knowledge_id 格式非法: {rec['knowledge_id']}"  # noqa: E501
        assert rec["knowledge_id"] != rec["memory_id"], (
            f"{rec['memory_id']} knowledge_id 必须与 memory_id 相互独立"
        )


def test_query_id_unique_and_format(query_records):
    ids = [rec["query_id"] for rec in query_records]
    assert len(ids) == len(set(ids)), "存在重复 query_id"
    for rec in query_records:
        assert isinstance(rec["query_id"], str) and QUERY_ID_RE.match(
            rec["query_id"]
        ), f"query_id 格式非法: {rec['query_id']}"  # noqa: E501


def test_query_non_empty(query_records):
    for rec in query_records:
        assert isinstance(rec["query"], str) and rec["query"], (
            f"{rec['query_id']} 的 query 必须为非空字符串"
        )


# ── retrieval_ref 对象契约 ──


def test_ref_objects_strict_two_keys(query_records):
    for rec in query_records:
        for ref in _all_refs(rec):
            assert isinstance(ref, dict), (
                f"{rec['query_id']} ref 必须是对象（禁止 memory_id-only 字符串）"
            )
            assert set(ref.keys()) == {"memory_id", "version_id"}, (
                f"{rec['query_id']} ref 必须恰好含 memory_id/version_id 两键: {ref}"
            )
            assert isinstance(ref["memory_id"], str) and MEMORY_ID_RE.match(
                ref["memory_id"]
            ), f"{rec['query_id']} ref.memory_id 格式非法: {ref}"
            assert isinstance(ref["version_id"], str) and VERSION_ID_RE.match(
                ref["version_id"]
            ), f"{rec['query_id']} ref.version_id 格式非法: {ref}"
            assert ref["version_id"].startswith(ref["memory_id"] + "-v"), (
                f"{rec['query_id']} ref.version_id 必须基于 ref.memory_id: {ref}"
            )


# ── Corpus 枚举合法性 ──


def test_object_type_knowledge(corpus_records):
    for rec in corpus_records:
        assert rec["object_type"] == "knowledge", (
            f"{rec['memory_id']} object_type 必须为 knowledge"
        )


def test_knowledge_type_valid_enum(corpus_records):
    for rec in corpus_records:
        assert rec["knowledge_type"] in KNOWLEDGE_TYPES, (
            f"{rec['memory_id']} 未知 knowledge_type: {rec['knowledge_type']}"
        )


def test_memory_status_valid_enum(corpus_records):
    for rec in corpus_records:
        assert rec["memory_status"] in MEMORY_STATUSES, (
            f"{rec['memory_id']} 未知 memory_status: {rec['memory_status']}"
        )


def test_memory_type_valid_enum(corpus_records):
    for rec in corpus_records:
        assert rec["memory_type"] in MEMORY_TYPES, (
            f"{rec['memory_id']} 未知 memory_type: {rec['memory_type']}"
        )


def test_sensitivity_valid_enum(corpus_records):
    for rec in corpus_records:
        assert rec["sensitivity"] in SENSITIVITIES, (
            f"{rec['memory_id']} 未知 sensitivity: {rec['sensitivity']}"
        )


def test_conflict_state_valid_enum(corpus_records):
    for rec in corpus_records:
        assert rec["conflict_state"] in CONFLICT_STATES, (
            f"{rec['memory_id']} 未知 conflict_state: {rec['conflict_state']}"
        )


def test_distractor_tag_valid(corpus_records):
    for rec in corpus_records:
        tag = rec["distractor_tag"]
        assert tag is None or tag in DISTRACTOR_TAGS, (
            f"{rec['memory_id']} 未知 distractor_tag: {tag}"
        )


def test_is_current_boolean(corpus_records):
    for rec in corpus_records:
        assert isinstance(rec["is_current"], bool), (
            f"{rec['memory_id']} is_current 必须为布尔值"
        )


def test_relation_ids_array(corpus_records):
    for rec in corpus_records:
        assert isinstance(rec["relation_ids"], list), (
            f"{rec['memory_id']} relation_ids 必须为数组"
        )
        for rid in rec["relation_ids"]:
            assert isinstance(rid, str) and rid, (
                f"{rec['memory_id']} relation_ids 元素必须为非空字符串"
            )


# ── Corpus 版本约束 ──


def test_each_memory_id_exactly_one_current(corpus_records):
    groups = {}
    for rec in corpus_records:
        groups.setdefault(rec["memory_id"], []).append(rec)
    for mid, rows in groups.items():
        current_count = sum(1 for r in rows if r["is_current"] is True)
        assert current_count == 1, (
            f"memory_id={mid} 的 is_current=true 行数为 {current_count}，必须恰为 1"
        )


def test_versions_share_user_type_and_knowledge_id(corpus_records):
    groups = {}
    for rec in corpus_records:
        groups.setdefault(rec["memory_id"], []).append(rec)
    for mid, rows in groups.items():
        users = {r["user_id"] for r in rows}
        kts = {r["knowledge_type"] for r in rows}
        kids = {r["knowledge_id"] for r in rows}
        assert len(users) == 1, f"memory_id={mid} 各版本 user_id 必须一致"
        assert len(kts) == 1, f"memory_id={mid} 各版本 knowledge_type 必须一致"
        assert len(kids) == 1, f"memory_id={mid} 各版本 knowledge_id 必须一致"


# ── distractor_tag 与行属性一致性 ──


def test_distractor_tag_consistency(corpus_records):
    for rec in corpus_records:
        tag = rec["distractor_tag"]
        if tag == "expired":
            assert rec["memory_status"] == "expired", (
                f"{rec['memory_id']} expired 干扰行 memory_status 必须为 expired"
            )
        elif tag in ("superseded", "stale_version"):
            assert rec["memory_status"] == "superseded", (
                f"{rec['memory_id']} {tag} 干扰行 memory_status 必须为 superseded"
            )
            assert rec["is_current"] is False, (
                f"{rec['memory_id']} {tag} 干扰行 is_current 必须为 false"
            )
        elif tag == "deprecated":
            assert rec["memory_status"] == "deprecated", (
                f"{rec['memory_id']} deprecated 干扰行 memory_status 必须为 deprecated"
            )
        elif tag == "candidate":
            assert rec["memory_status"] == "candidate", (
                f"{rec['memory_id']} candidate 干扰行 memory_status 必须为 candidate"
            )
        elif tag == "removed_or_forgotten":
            assert rec["memory_status"] == "removed", (
                f"{rec['memory_id']} removed 干扰行 memory_status 必须为 removed"
            )
        elif tag == "unresolved_conflict":
            assert rec["conflict_state"] == "unresolved", (
                f"{rec['memory_id']} unresolved_conflict 干扰行 conflict_state 必须为 unresolved"
            )
        elif tag == "sensitive_recall_prohibited":
            assert rec["sensitivity"] in ("high", "critical"), (
                f"{rec['memory_id']} sensitive 干扰行 sensitivity 必须为 high/critical"
            )
            assert "[REDACTED_" in rec["content_summary"], (
                f"{rec['memory_id']} sensitive 干扰行正文必须使用 [REDACTED_*] 占位"
            )
        elif tag == "cross_user":
            assert rec["user_id"] in SYNTHETIC_USERS, (
                f"{rec['memory_id']} cross_user 行 user_id 非法"
            )


# ── Corpus 覆盖度 ──


def test_corpus_total_count(corpus_records):
    assert len(corpus_records) >= 62, f"Corpus V2 行数 {len(corpus_records)} 不足 62"


def test_positive_answerable_coverage_by_type(corpus_records):
    pa = [rec for rec in corpus_records if _positive_answerable(rec)]
    from collections import Counter

    counts = Counter(rec["knowledge_type"] for rec in pa)
    missing = [kt for kt in KNOWLEDGE_TYPES if counts[kt] < 4]
    assert not missing, (
        f"positive-answerable 行六类 knowledge_type 各需 >=4，不足: "
        f"{[(kt, counts[kt]) for kt in KNOWLEDGE_TYPES]}"
    )


def test_corpus_distractor_coverage(corpus_records):
    tags = [rec["distractor_tag"] for rec in corpus_records if rec["distractor_tag"]]
    from collections import Counter

    counts = Counter(tags)
    missing = [
        tag for tag in ("removed_or_forgotten", "expired", "superseded", "candidate",
                        "unresolved_conflict", "cross_user", "stale_version")
        if counts[tag] < 2
    ]
    assert not missing, f"Corpus 危险干扰行各需 >=2，不足: {dict(counts)}"
    assert counts["deprecated"] >= 1, "Corpus 必须含 >= 1 条 deprecated 干扰行"


def test_corpus_user_coverage(corpus_records):
    users = {rec["user_id"] for rec in corpus_records}
    assert len(users) >= 2, f"Corpus user_id 数 {len(users)} 不足 2"
    assert users <= SYNTHETIC_USERS, f"存在非合成用户: {users - SYNTHETIC_USERS}"


# ── Query 枚举与角色约束 ──


def test_query_user_valid(query_records):
    for rec in query_records:
        assert rec["user_id"] in SYNTHETIC_USERS, (
            f"{rec['query_id']} 未知 user_id: {rec['user_id']}"
        )


def test_evaluation_role_valid_enum(query_records):
    for rec in query_records:
        assert rec["evaluation_role"] in EVALUATION_ROLES, (
            f"{rec['query_id']} 未知 evaluation_role: {rec['evaluation_role']}"
        )


def test_annotation_status_valid_enum(query_records):
    for rec in query_records:
        assert rec["annotation_status"] in ANNOTATION_STATUSES, (
            f"{rec['query_id']} 未知 annotation_status: {rec['annotation_status']}"
        )


def test_ref_arrays_typed(query_records):
    for rec in query_records:
        for field in ("relevant_refs", "forbidden_refs", "semantic_near_miss_refs"):
            assert isinstance(rec[field], list), (
                f"{rec['query_id']} {field} 必须为数组"
            )


def test_rationale_required(query_records):
    for rec in query_records:
        assert isinstance(rec["rationale"], str) and rec["rationale"], (
            f"{rec['query_id']} rationale 必须为非空依据说明"
        )


def test_positive_role_relevant_nonempty(query_records):
    for rec in query_records:
        if rec["evaluation_role"] == "positive_retrieval":
            assert rec["relevant_refs"], (
                f"{rec['query_id']} positive_retrieval 的 relevant_refs 必须非空"
            )


def test_negative_role_guardrail_required(query_records):
    for rec in query_records:
        if rec["evaluation_role"] == "negative_guardrail":
            assert rec["relevant_refs"] == [], (
                f"{rec['query_id']} negative_guardrail 的 relevant_refs 必须为空数组"
            )
            assert rec["guardrail_category"] in GUARDRAIL_CATEGORIES, (
                f"{rec['query_id']} 缺少/非法 guardrail_category: "
                f"{rec['guardrail_category']}"
            )
            assert isinstance(rec["guardrail_reason"], str) and rec["guardrail_reason"], (
                f"{rec['query_id']} negative_guardrail 必须带非空 guardrail_reason"
            )
            assert rec["forbidden_refs"], (
                f"{rec['query_id']} negative_guardrail 必须挂接 >= 1 个 forbidden_refs"
            )


def test_boundary_role_when_present(query_records):
    # boundary 无配额：仅当真实存在 PENDING retrieval semantics 样本时校验字段约束
    for rec in query_records:
        if rec["evaluation_role"] == "boundary":
            assert rec["relevant_refs"] == [], (
                f"{rec['query_id']} boundary 的 relevant_refs 必须为空数组"
            )
            reason = rec["boundary_reason"] or ""
            assert any(
                anchor in reason for anchor in ("PENDING", "§4.1", "TEAM_DEFINED")
            ), (
                f"{rec['query_id']} boundary 必须带引用 PENDING 事项"
                f"/§4.1 争议/TEAM_DEFINED 参数的 boundary_reason"
            )


def test_non_negative_guardrail_category_null(query_records):
    for rec in query_records:
        if rec["evaluation_role"] != "negative_guardrail":
            assert rec["guardrail_category"] is None, (
                f"{rec['query_id']} 非 negative_guardrail 不得携带 guardrail_category"
            )


# ── 引用完整性（三桶 retrieval_ref 精确解析到确切版本行） ──


def test_all_refs_resolve_to_exact_rows(query_records, corpus_by_version):
    for rec in query_records:
        for ref in _all_refs(rec):
            key = (ref["memory_id"], ref["version_id"])
            assert key in corpus_by_version, (
                f"{rec['query_id']} 引用了不存在的 (memory_id, version_id): {key}"
            )


def test_relevant_refs_meet_gold_rules(query_records, corpus_by_version):
    for rec in query_records:
        for ref in rec["relevant_refs"]:
            row = corpus_by_version[(ref["memory_id"], ref["version_id"])]
            assert row["user_id"] == rec["user_id"], (
                f"{rec['query_id']} relevant_ref 必须属同 user: {ref}"
            )
            assert _positive_answerable(row), (
                f"{rec['query_id']} relevant_ref 未精确命中 positive-answerable "
                f"版本行: {ref}（行: {row['memory_status']}/{row['is_current']}/"
                f"{row['conflict_state']}/{row['sensitivity']}/{row['distractor_tag']}）"
            )


def test_forbidden_refs_business_not_recallable(query_records, corpus_by_version):
    for rec in query_records:
        for ref in rec["forbidden_refs"]:
            row = corpus_by_version[(ref["memory_id"], ref["version_id"])]
            assert _business_not_recallable_for(row, rec["user_id"]), (
                f"{rec['query_id']} forbidden_ref 命中业务可召回版本行: "
                f"{ref}（对该查询用户不得作为正解）"
            )


def test_semantic_near_miss_refs_business_legal(query_records, corpus_by_version):
    for rec in query_records:
        for ref in rec["semantic_near_miss_refs"]:
            row = corpus_by_version[(ref["memory_id"], ref["version_id"])]
            assert row["user_id"] == rec["user_id"], (
                f"{rec['query_id']} semantic_near_miss_ref 必须属同 user: {ref}"
            )
            assert _positive_answerable(row), (
                f"{rec['query_id']} semantic_near_miss_ref 必须命中业务合法"
                f"（positive-answerable）current 版本行: {ref}"
            )


def test_three_buckets_pairwise_disjoint(query_records):
    for rec in query_records:
        buckets = [
            ("relevant_refs", rec["relevant_refs"]),
            ("forbidden_refs", rec["forbidden_refs"]),
            ("semantic_near_miss_refs", rec["semantic_near_miss_refs"]),
        ]
        for i in range(len(buckets)):
            for j in range(i + 1, len(buckets)):
                name_i, refs_i = buckets[i]
                name_j, refs_j = buckets[j]
                overlap = set(frozenset(r.items()) for r in refs_i) & set(
                    frozenset(r.items()) for r in refs_j
                )
                assert not overlap, (
                    f"{rec['query_id']} 三桶之间存在重复引用 {name_i}×{name_j}: "
                    f"{sorted(overlap)}"
                )


def test_cross_user_forbidden_resolves_to_other_user(
    query_records, corpus_by_version
):
    # 约束：cross-user forbidden ref 必须能解析到另一个 user 的 corpus 行并被判禁止
    cross_user_qs = [
        rec for rec in query_records if rec["guardrail_category"] == "cross_user"
    ]
    assert cross_user_qs, "必须存在 guardrail_category=cross_user 的查询"
    for rec in cross_user_qs:
        assert rec["forbidden_refs"], (
            f"{rec['query_id']} cross_user 查询必须挂接 forbidden_refs"
        )
        for ref in rec["forbidden_refs"]:
            row = corpus_by_version[(ref["memory_id"], ref["version_id"])]
            assert row["user_id"] != rec["user_id"], (
                f"{rec['query_id']} cross_user 的 forbidden_ref {ref} 必须解析到"
                f"另一个 user 的 corpus 行（当前行属 {row['user_id']}）"
            )
            assert _business_not_recallable_for(row, rec["user_id"]), (
                f"{rec['query_id']} 跨用户 forbidden_ref {ref} 必须被判定为禁止"
            )


# ── 版本级禁止引用形态覆盖（九态） ──


def test_forbidden_refs_version_forms_coverage(query_records, corpus_by_version):
    covered = set()
    for rec in query_records:
        for ref in rec["forbidden_refs"]:
            row = corpus_by_version[(ref["memory_id"], ref["version_id"])]
            if row["memory_status"] == "deprecated":
                covered.add("deprecated")
            if row["memory_status"] == "removed":
                covered.add("removed")
            if row["memory_status"] == "expired":
                covered.add("expired")
            if row["memory_status"] == "superseded":
                covered.add("superseded")
            if row["memory_status"] == "candidate":
                covered.add("candidate")
            if row["conflict_state"] == "unresolved":
                covered.add("unresolved")
            if row["user_id"] != rec["user_id"]:
                covered.add("cross_user")
            if row["sensitivity"] in ("high", "critical"):
                covered.add("sensitive")
            if row["is_current"] is False:
                covered.add("stale_version")
    missing = FORBIDDEN_VERSION_FORMS - covered
    assert not missing, (
        f"forbidden_refs 版本级禁止形态缺少: {sorted(missing)}"
        f"（当前 {sorted(covered)}）"
    )


# ── Query 覆盖度（真实样本决定最低覆盖，无治理问题配额填充） ──


def test_query_total_count(query_records):
    assert len(query_records) >= 33, f"Query V2 总数 {len(query_records)} 不足 33"


def test_positive_query_count_and_type_coverage(query_records, corpus_by_version):
    pos = [rec for rec in query_records if rec["evaluation_role"] == "positive_retrieval"]
    assert len(pos) >= 20, f"positive_retrieval 查询数 {len(pos)} 不足 20"
    from collections import Counter

    type_counts = Counter()
    for rec in pos:
        matched_type = None
        for ref in rec["relevant_refs"]:
            row = corpus_by_version[(ref["memory_id"], ref["version_id"])]
            if _positive_answerable(row) and row["user_id"] == rec["user_id"]:
                matched_type = row["knowledge_type"]
                break
        assert matched_type is not None, (
            f"{rec['query_id']} 无法解析正解 knowledge_type"
        )
        type_counts[matched_type] += 1
    missing = [kt for kt in KNOWLEDGE_TYPES if type_counts[kt] < 3]
    assert not missing, (
        f"positive_retrieval 六类 knowledge_type 各需 >=3，不足: {dict(type_counts)}"
    )
    b_users = [rec for rec in pos if rec["user_id"] == "user_demo_d9e_b"]
    assert b_users, "positive_retrieval 至少需要 1 条第二合成用户（用户隔离正例）"


def test_negative_query_count_and_category_coverage(query_records):
    neg = [rec for rec in query_records if rec["evaluation_role"] == "negative_guardrail"]
    assert len(neg) >= 13, f"negative_guardrail 查询数 {len(neg)} 不足 13"
    categories = {rec["guardrail_category"] for rec in neg}
    missing = GUARDRAIL_CATEGORIES - categories
    assert not missing, f"negative_guardrail 缺少 D9 八类 guardrail_category: {missing}"


def test_boundary_no_quota(query_records):
    # boundary 无配额：不得以治理问题填充检索 Gold；当前 v2 由真实样本决定
    boundary = [rec for rec in query_records if rec["evaluation_role"] == "boundary"]
    for rec in boundary:
        assert rec["guardrail_category"] is None, (
            f"{rec['query_id']} boundary 不得携带 guardrail_category"
        )


# ── B 轨 2026-08-31 PR #88 裁决锚定 ──


def test_anchor_d9q001_version_split(query_records):
    q = _find_query(query_records, "d9q-001")
    assert q["relevant_refs"] == [_ref("d9c-001", "d9c-001-v1")]
    assert _ref("d9c-037", "d9c-037-v1") in q["forbidden_refs"]
    assert _ref("d9c-037", "d9c-037-v2") in q["semantic_near_miss_refs"]
    assert _ref("d9c-037", "d9c-037-v2") not in q["forbidden_refs"]
    assert q["annotation_status"] == "pending_review", (
        "d9q-001 的 d9c-037-v2 晋升待人工确认，必须保持 pending_review"
    )


def test_anchor_d9q007_current_not_forbidden(query_records):
    q = _find_query(query_records, "d9q-007")
    assert q["relevant_refs"] == [_ref("d9c-013", "d9c-013-v1")]
    assert _ref("d9c-038", "d9c-038-v1") in q["forbidden_refs"]
    assert _ref("d9c-038", "d9c-038-v2") in q["semantic_near_miss_refs"]
    assert _ref("d9c-038", "d9c-038-v2") not in q["forbidden_refs"], (
        "B 轨裁决：d9c-038-v2 为 active/current，绝不能放入 forbidden_refs"
    )


def test_anchor_d9q010_version_split(query_records):
    q = _find_query(query_records, "d9q-010")
    assert q["relevant_refs"] == [_ref("d9c-019", "d9c-019-v1")]
    assert _ref("d9c-039", "d9c-039-v1") in q["forbidden_refs"]
    assert _ref("d9c-039", "d9c-039-v2") in q["semantic_near_miss_refs"]
    assert q["annotation_status"] == "pending_review", (
        "d9q-010 的 d9c-039-v2 等价 Gold 待人工确认，必须保持 pending_review"
    )


def test_anchor_d9q003_rewritten_workflow_step(query_records):
    q = _find_query(query_records, "d9q-003")
    assert "上一步" in q["query"], (
        "d9q-003 问法必须按 B 裁决明确为 workflow 上一步"
    )
    assert q["relevant_refs"] == [_ref("d9c-005", "d9c-005-v1")]
    for ref in _all_refs(q):
        assert ref["memory_id"] != "d9c-029", (
            "d9q-003 不得引用合并准入约束 d9c-029（workflow 上一步 vs constraint）"
        )


def test_anchor_d9q016_rewritten_constraint(query_records):
    q = _find_query(query_records, "d9q-016")
    assert "准入" in q["query"], (
        "d9q-016 问法必须按 B 裁决明确为 constraint 强制准入条件"
    )
    assert q["relevant_refs"] == [_ref("d9c-029", "d9c-029-v1")]
    for ref in _all_refs(q):
        assert ref["memory_id"] != "d9c-005", (
            "d9q-016 不得引用部署冒烟测试 d9c-005（constraint vs workflow 上一步）"
        )


def test_anchor_governance_queries_removed(query_records):
    ids = {rec["query_id"] for rec in query_records}
    for removed in ("d9q-033", "d9q-034", "d9q-035", "d9q-036"):
        assert removed not in ids, (
            f"{removed} 属参数/治理问题或语料不足，必须从 V2 QuerySet 删除"
        )


def test_anchor_deprecated_guardrail_query(query_records, corpus_by_version):
    deprecated_qs = [
        rec for rec in query_records if rec["guardrail_category"] == "deprecated"
    ]
    assert deprecated_qs, "V2 必须存在 guardrail_category=deprecated 的查询"
    for q in deprecated_qs:
        assert q["evaluation_role"] == "negative_guardrail"
        assert q["relevant_refs"] == []
        assert q["query_id"] != "d9q-033", (
            "deprecated guardrail 查询必须使用全新 query_id，不得复用被拒绝的 d9q-033"
        )
        assert q["forbidden_refs"], "deprecated guardrail 查询必须挂接 forbidden_refs"
        for ref in q["forbidden_refs"]:
            row = corpus_by_version[(ref["memory_id"], ref["version_id"])]
            assert row["memory_status"] == "deprecated", (
                f"{q['query_id']} deprecated guards 的 forbidden_ref 必须解析到 "
                f"memory_status=deprecated 行: {ref}"
            )


# ── 凭据与伪状态令牌扫描（仅 V2 两个 JSONL，范围与测试纪律一致） ──


def _assert_no_forbidden_tokens(text, label):
    for pat in FORBIDDEN_TOKENS:
        m = pat.search(text)
        assert not m, f"{label} 中出现伪状态令牌: {m.group(0)!r}（模式 {pat.pattern}）"


def _assert_no_real_credentials(text, label):
    for pat in REAL_CREDENTIAL_PATTERNS:
        assert not pat.search(text), (
            f"{label} 中出现疑似真实凭据模式: {pat.pattern}"
        )


def test_corpus_no_forbidden_tokens(corpus_raw_lines):
    _assert_no_forbidden_tokens("\n".join(corpus_raw_lines), "D9_RETRIEVAL_CORPUS_V2.jsonl")


def test_query_no_forbidden_tokens(query_raw_lines):
    _assert_no_forbidden_tokens(
        "\n".join(query_raw_lines), "D9_RETRIEVAL_QUERYSET_CANDIDATE_V2.jsonl"
    )


def test_corpus_no_real_credentials(corpus_raw_lines):
    _assert_no_real_credentials("\n".join(corpus_raw_lines), "D9_RETRIEVAL_CORPUS_V2.jsonl")


def test_query_no_real_credentials(query_raw_lines):
    _assert_no_real_credentials(
        "\n".join(query_raw_lines), "D9_RETRIEVAL_QUERYSET_CANDIDATE_V2.jsonl"
    )


# ── README V2 契约锚点 ──


def test_readme_declares_candidate_status(readme_text):
    assert "非 Gold" in readme_text
    assert "annotation_status" in readme_text
    assert "candidate" in readme_text and "pending_review" in readme_text


def test_readme_declares_v2_ref_schema(readme_text):
    for field in ("relevant_refs", "forbidden_refs", "semantic_near_miss_refs"):
        assert field in readme_text, f"README 必须声明 ref 字段 {field}"
    assert "retrieval_ref" in readme_text
    assert "version_id" in readme_text


def test_readme_declares_eight_guardrail_categories(readme_text):
    for cat in GUARDRAIL_CATEGORIES:
        assert cat in readme_text, f"README 必须声明八类 guardrail_category: {cat}"


def test_readme_declares_b_adjudication(readme_text):
    assert "PR #88" in readme_text, "README 必须声明 B 轨 PR #88 裁决"


def test_readme_declares_mapping_pending(readme_text):
    assert "formal_mapping_status" in readme_text
    assert "PENDING_D_CONFIRMATION" in readme_text, (
        "README 必须声明 knowledge_id↔memory_id 生产映射 PENDING_D_CONFIRMATION"
    )
    assert "knowledge_id" in readme_text
    assert "不宣称 equality" in readme_text, (
        "README 必须声明不宣称 knowledge_id↔memory_id 生产等价"
    )


def test_readme_declares_v1_retention_and_manual_cleanup(readme_text):
    assert "V1" in readme_text, "README 必须说明与 V1 的关系"
    assert "git rm" in readme_text, "README 必须说明 V1 由人工 git rm 清理"


def test_readme_declares_no_governance_filler(readme_text):
    assert "不得用治理问题填充" in readme_text, (
        "README 必须明确不得用治理问题填充检索 Gold"
    )
    assert "治理问题" in readme_text


def test_readme_declares_no_retrieval_gold_quota(readme_text):
    # 覆盖配额由真实样本决定：明确丢弃 v1 的 boundary>=4 / query>=36 形式配额
    assert "真实样本决定" in readme_text or "真实样本" in readme_text, (
        "README 必须声明覆盖由真实样本决定"
    )
    assert "boundary" in readme_text
    assert "无配额" in readme_text


def test_readme_declares_d6_relationship(readme_text):
    assert "D6" in readme_text
    assert "复用" in readme_text
    assert "非 Gold" in readme_text