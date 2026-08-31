"""
test_d9_retrieval_dataset.py — Day9E 检索 Corpus 与 Query 候选集 v1 验证测试

对齐任务卡：day9-e-02-retrieval-dataset-candidate-v1

目标：校验 `D9_RETRIEVAL_CORPUS_V1.jsonl` 与
`D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl` 的完整性与一致性：

- JSONL 逐行合法 JSON；必填字段完整；corpus 行主键 (memory_id, version_id)
  全局唯一、query_id 全局唯一且格式合法；
- Corpus 枚举合法（object_type / memory_type / knowledge_type / memory_status /
  sensitivity / conflict_state / distractor_tag）；每 memory_id 恰一条
  is_current=true；同一 memory_id 各版本 user_id 与 knowledge_type 一致；
- distractor_tag 与行属性一致性（expired->memory_status=expired 等）；
- Corpus 覆盖：总数 >= 60；positive-answerable 行六类 knowledge_type 各 >= 4；
  七类危险干扰（expired / superseded / candidate / removed_or_forgotten /
  unresolved_conflict / cross_user / stale_version）各 >= 2；user_id >= 2；
- Query 枚举合法（evaluation_role / annotation_status / guardrail_category）；
  角色约束：positive_retrieval 的 relevant_ids 非空且每个引用满足 Gold 规则
  （存在同用户 active+is_current+非 unresolved+低敏感+无 distractor 行）；
  negative_guardrail 的 relevant_ids 为空且带 guardrail_reason、每条 >= 1 个
  near_miss_refs；boundary 带 boundary_reason；
- Query 覆盖：总数 >= 36；positive >= 20（六类 each >= 3，且 >= 1 条用户B）；
  negative >= 12（D9 七类 category 各 >= 1）；boundary >= 4；
  全部查询的 near_miss_refs 形态集合覆盖七种危险形态；
- 引用完整性：relevant_ids / near_miss_refs 引用的 memory_id 均存在于 Corpus
  且业务状态符合规则；relevant_ids 不引用带非空 distractor_tag 的行；
- 全文无真实凭据模式；JSONL 数据中不出现 reviewed / sealed 状态令牌；
- 非法 JSON / 重复 ID / 缺字段 / 未知枚举 / 覆盖不足 / 引用悬空 /
  状态令牌出现时本测试必须真实失败。

测试纪律（沿用 test_d6_multisource_devset.py / test_d9_retrieval_gold_spec.py）：
- 不使用 pytest.skip / xfail / 无条件 pass；不吞异常；不自动修正非法 JSON；
  不跳过坏行；所有断言为硬断言（assert）。
- 测试自包含：仅使用标准库（json / re / pathlib）+ pytest，
  **不导入 memory-service 任何模块**。
"""

import json
import re
from pathlib import Path

import pytest

# ── 文件定位 ──

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_PATH = EVAL_DIR / "D9_RETRIEVAL_CORPUS_V1.jsonl"
QUERY_PATH = EVAL_DIR / "D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl"
README_PATH = EVAL_DIR / "D9_RETRIEVAL_DATASET_README_V1.md"

# ── 合法枚举（对齐 README v1 / D9 gold policy v1 / domain.enums 六值） ──

KNOWLEDGE_TYPES = {
    "workflow", "case", "template", "fact", "constraint", "failure_experience",
}
MEMORY_STATUSES = {"active", "superseded", "deprecated", "expired", "removed", "candidate"}
MEMORY_TYPES = {"short_term", "medium_term", "long_term", "ephemeral"}
SENSITIVITIES = {"none", "low", "medium", "high", "critical"}
CONFLICT_STATES = {"none", "resolved", "unresolved"}
DISTRACTOR_TAGS = {
    "removed_or_forgotten", "expired", "superseded", "candidate",
    "unresolved_conflict", "cross_user", "sensitive_recall_prohibited",
    "stale_version",
}
EVALUATION_ROLES = {"positive_retrieval", "negative_guardrail", "boundary"}
ANNOTATION_STATUSES = {"candidate", "pending_review"}
GUARDRAIL_CATEGORIES = {
    "removed_or_forgotten", "expired", "superseded", "candidate",
    "unresolved_conflict", "cross_user", "sensitive_recall_prohibited",
}
NEAR_MISS_DANGEROUS_FORMS = {
    "expired", "superseded", "candidate", "removed", "unresolved_conflict",
    "cross_user", "stale_version",
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
    "relevant_ids",
    "near_miss_refs",
    "guardrail_category",
    "guardrail_reason",
    "boundary_reason",
    "rationale",
    "annotation_status",
    "notes",
)

# ── ID 格式 ──

MEMORY_ID_RE = re.compile(r"^d9c-\d{3}$")
VERSION_ID_RE = re.compile(r"^d9c-\d{3}-v[1-9]\d*$")
QUERY_ID_RE = re.compile(r"^d9q-\d{3}$")

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
    assert CORPUS_PATH.exists(), "Corpus JSONL 文件不存在"
    return _read_raw_lines(CORPUS_PATH)


@pytest.fixture(scope="module")
def query_raw_lines():
    assert QUERY_PATH.exists(), "Query JSONL 文件不存在"
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
    assert README_PATH.exists(), "数据集 README 文件不存在"
    return README_PATH.read_text(encoding="utf-8")


def _positive_answerable(row):
    return (
        row["memory_status"] == "active"
        and row["is_current"] is True
        and row["conflict_state"] != "unresolved"
        and row["sensitivity"] in ("none", "low", "medium")
        and row["distractor_tag"] is None
    )


def _business_not_recallable_for(row, query_user):
    return (
        row["user_id"] != query_user
        or row["memory_status"] in ("expired", "superseded", "removed", "candidate")
        or row["conflict_state"] == "unresolved"
        or row["is_current"] is False
        or row["sensitivity"] in ("high", "critical")
        or row["distractor_tag"] is not None
    )


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


def test_knowledge_id_equals_memory_id(corpus_records):
    for rec in corpus_records:
        assert rec["knowledge_id"] == rec["memory_id"], (
            f"{rec['memory_id']} knowledge_id 必须与 memory_id 同值（候选约定）"
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


def test_versions_share_user_and_type(corpus_records):
    groups = {}
    for rec in corpus_records:
        groups.setdefault(rec["memory_id"], []).append(rec)
    for mid, rows in groups.items():
        users = {r["user_id"] for r in rows}
        kts = {r["knowledge_type"] for r in rows}
        assert len(users) == 1, f"memory_id={mid} 各版本 user_id 必须一致"
        assert len(kts) == 1, f"memory_id={mid} 各版本 knowledge_type 必须一致"


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
    assert len(corpus_records) >= 60, f"Corpus 行数 {len(corpus_records)} 不足 60"


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


def test_relevant_ids_array(query_records):
    for rec in query_records:
        assert isinstance(rec["relevant_ids"], list), (
            f"{rec['query_id']} relevant_ids 必须为数组"
        )


def test_near_miss_refs_array(query_records):
    for rec in query_records:
        assert isinstance(rec["near_miss_refs"], list), (
            f"{rec['query_id']} near_miss_refs 必须为数组"
        )


def test_rationale_required(query_records):
    for rec in query_records:
        assert isinstance(rec["rationale"], str) and rec["rationale"], (
            f"{rec['query_id']} rationale 必须为非空依据说明"
        )


def test_positive_role_relevant_nonempty(query_records):
    for rec in query_records:
        if rec["evaluation_role"] == "positive_retrieval":
            assert rec["relevant_ids"], (
                f"{rec['query_id']} positive_retrieval 的 relevant_ids 必须非空"
            )


def test_negative_role_guardrail_required(query_records):
    for rec in query_records:
        if rec["evaluation_role"] == "negative_guardrail":
            assert rec["relevant_ids"] == [], (
                f"{rec['query_id']} negative_guardrail 的 relevant_ids 必须为空数组"
            )
            assert rec["guardrail_category"] in GUARDRAIL_CATEGORIES, (
                f"{rec['query_id']} 缺少/非法 guardrail_category: "
                f"{rec['guardrail_category']}"
            )
            assert isinstance(rec["guardrail_reason"], str) and rec["guardrail_reason"], (
                f"{rec['query_id']} negative_guardrail 必须带非空 guardrail_reason"
            )
            assert rec["near_miss_refs"], (
                f"{rec['query_id']} negative_guardrail 必须挂接 >= 1 个 near_miss_refs"
            )


def test_boundary_role_required(query_records):
    for rec in query_records:
        if rec["evaluation_role"] == "boundary":
            assert rec["relevant_ids"] == [], (
                f"{rec['query_id']} boundary 的 relevant_ids 必须为空数组"
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


# ── 引用一致性（relevant_ids 与 near_miss_refs 解析到 Corpus） ──


@pytest.fixture(scope="module")
def corpus_by_memory_id(corpus_records):
    groups = {}
    for rec in corpus_records:
        groups.setdefault(rec["memory_id"], []).append(rec)
    return groups


def _exists_positive_answerable_for(rows, query_user):
    return any(
        _positive_answerable(r) and r["user_id"] == query_user for r in rows
    )


def test_relevant_ids_reference_exists(
    query_records, corpus_by_memory_id
):
    for rec in query_records:
        for ref in rec["relevant_ids"]:
            assert ref in corpus_by_memory_id, (
                f"{rec['query_id']} relevant_ids 引用了不存在的 memory_id: {ref}"
            )


def test_relevant_ids_meet_gold_rules(query_records, corpus_by_memory_id):
    for rec in query_records:
        for ref in rec["relevant_ids"]:
            rows = corpus_by_memory_id[ref]
            assert _exists_positive_answerable_for(rows, rec["user_id"]), (
                f"{rec['query_id']} relevant_ids {ref} 不存在满足 Gold 规则"
                f"（同用户 active+is_current+非 unresolved+低敏感）的行"
            )
            for r in rows:
                assert r["distractor_tag"] is None, (
                    f"{rec['query_id']} relevant_ids 不得引用带非空 distractor_tag "
                    f"的行: {ref}"
                )


def test_near_miss_refs_reference_exists_and_valid(
    query_records, corpus_by_memory_id
):
    for rec in query_records:
        for ref in rec["near_miss_refs"]:
            assert ref in corpus_by_memory_id, (
                f"{rec['query_id']} near_miss_refs 引用了不存在的 memory_id: {ref}"
            )
            assert ref not in rec["relevant_ids"], (
                f"{rec['query_id']} near_miss_refs {ref} 不得同时出现在 relevant_ids"
            )
            rows = corpus_by_memory_id[ref]
            assert any(
                _business_not_recallable_for(r, rec["user_id"]) for r in rows
            ), (
                f"{rec['query_id']} near_miss_refs {ref} 对该查询用户业务上可召回，"
                f"不能作为危险近似干扰"
            )


# ── Query 覆盖度 ──


def test_query_total_count(query_records):
    assert len(query_records) >= 36, f"Query 总数 {len(query_records)} 不足 36"


def test_positive_query_count_and_type_coverage(
    query_records, corpus_by_memory_id
):
    pos = [rec for rec in query_records if rec["evaluation_role"] == "positive_retrieval"]
    assert len(pos) >= 20, f"positive_retrieval 查询数 {len(pos)} 不足 20"
    from collections import Counter

    type_counts = Counter()
    for rec in pos:
        matched_type = None
        for ref in rec["relevant_ids"]:
            rows = corpus_by_memory_id[ref]
            for r in rows:
                if _positive_answerable(r) and r["user_id"] == rec["user_id"]:
                    matched_type = r["knowledge_type"]
                    break
            if matched_type is not None:
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
    assert len(neg) >= 12, f"negative_guardrail 查询数 {len(neg)} 不足 12"
    categories = {rec["guardrail_category"] for rec in neg}
    missing = GUARDRAIL_CATEGORIES - categories
    assert not missing, f"negative_guardrail 缺少 D9 七类 guardrail_category: {missing}"


def test_boundary_query_count(query_records):
    b = [rec for rec in query_records if rec["evaluation_role"] == "boundary"]
    assert len(b) >= 4, f"boundary 查询数 {len(b)} 不足 4"


def test_near_miss_dangerous_forms_coverage(
    query_records, corpus_by_memory_id
):
    covered = set()
    for rec in query_records:
        for ref in rec["near_miss_refs"]:
            rows = corpus_by_memory_id[ref]
            for r in rows:
                if r["memory_status"] == "expired":
                    covered.add("expired")
                if r["memory_status"] == "superseded":
                    covered.add("superseded")
                if r["memory_status"] == "candidate":
                    covered.add("candidate")
                if r["memory_status"] == "removed":
                    covered.add("removed")
                if r["conflict_state"] == "unresolved":
                    covered.add("unresolved_conflict")
                if r["user_id"] != rec["user_id"]:
                    covered.add("cross_user")
                if r["is_current"] is False:
                    covered.add("stale_version")
    missing = NEAR_MISS_DANGEROUS_FORMS - covered
    assert not missing, (
        f"near_miss_refs 形态集合缺少危险形态: {sorted(missing)}（当前 {sorted(covered)}）"
    )


# ── 凭据与伪状态令牌扫描 ──


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
    _assert_no_forbidden_tokens("\n".join(corpus_raw_lines), "D9_RETRIEVAL_CORPUS_V1.jsonl")


def test_query_no_forbidden_tokens(query_raw_lines):
    _assert_no_forbidden_tokens(
        "\n".join(query_raw_lines), "D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl"
    )


def test_corpus_no_real_credentials(corpus_raw_lines):
    _assert_no_real_credentials("\n".join(corpus_raw_lines), "D9_RETRIEVAL_CORPUS_V1.jsonl")


def test_query_no_real_credentials(query_raw_lines):
    _assert_no_real_credentials(
        "\n".join(query_raw_lines), "D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl"
    )


# ── README 候选定位声明 ──


def test_readme_declares_candidate_status(readme_text):
    assert "非 Gold" in readme_text or "非 `Gold`" in readme_text
    assert "annotation_status" in readme_text
    assert "candidate" in readme_text and "pending_review" in readme_text


def test_readme_declares_d6_relationship(readme_text):
    assert "D6" in readme_text
    assert "复用" in readme_text
    assert "非 Gold" in readme_text