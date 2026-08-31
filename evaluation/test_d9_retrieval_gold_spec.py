"""
test_d9_retrieval_gold_spec.py — Day9E 检索 Gold/指标语义 v2 验证测试

对齐任务卡：day9-e-rw-01-gold-policy-v2-b-adjudication-v1

目标：校验 `D9_RETRIEVAL_GOLD_POLICY_V2.json` 与
`D9_RETRIEVAL_GOLD_SPEC_V2.md` 的语义冻结契约（吸收 B 轨 2026-08-31
对 PR #88 的正式裁决，v2 升级自 v1 候选）：

- 策略 JSON 可解析；顶层/嵌套字段白名单 fail-fast（未知字段即失败）；
- V1 候选两文件不得在最终 PR 树残留（no residual），测试只针对 V2；
- 身份：policy_version=="v2"、status=="CANDIDATE_FOR_FREEZE"、
  spec_ref / supersedes / adjudication_ref（B 轨 PR #88 裁决，经任务卡传入）；
- retrieval_ref 版本级判定键：序列化键 (memory_id, version_id)、
  完整校验键 (user_id, memory_id, version_id)，memory_id-only 不再是正式契约；
- 三类评测角色枚举稳定（positive_retrieval / negative_guardrail / boundary）
  且各自 in_m2_formal_denominator 取值锁定（true / false / false）；
- 空 Gold（empty relevant_refs）不进入 Recall/MRR/nDCG 正式分母，
  与 D3 第四章 M2 无效样本处理原文子句一致（empty Gold 规则沿用 v1）；
- negative_guardrail 覆盖八类业务边界（含 deprecated）：
  removed_or_forgotten / expired / superseded / deprecated / candidate /
  unresolved_conflict / cross_user / sensitive_recall_prohibited；
  deprecated 条目必须声明 history/audit-only 访问且不进入标准 M2；
- guardrail violation 统计口径：query/item count 与 rate 字段、
  按类别拆分、cross_user/sensitive_recall_prohibited critical=0；
- 评测配置冻结 d9-retrieval-eval-config/v1：k=10、top_k=10、rrf_k=60、
  top_k==k、origin=TEAM_DEFINED、official_requirement=false；
- conflict_state={none,resolved,unresolved} 仅属 evaluation normalization，
  NOT production shared enum，不新增生产 Enum；
- team_defined_params 仅保留未冻结参数（statistics_method / dataset_split，
  PENDING、frozen=false）；k/top_k/rrf_k 不得留在该容器；
- 版本化评测元数据字段与 D3 第十二章对齐（含 policy_version，全 PENDING）；
- 两 V2 文件全文字符串不得出现伪状态/伪结果令牌：
  HOST_VERIFIED / PASS（含 PASS_ 前缀）/ reviewed / sealed / 已达标 / 已达成；
- 规格文档声明三类角色、TD-036 / PR #76 / Issue #79 / PR #88 依赖、
  「不修改 B 轨实现」边界、retrieval_ref、deprecated guardrail、
  冻结配置值、conflict_state 评测归一化与 V1 已替换；
- 全文无真实凭据模式。

测试纪律（沿用 test_d6_multisource_devset.py）：
- 不使用 pytest.skip / xfail / 无条件 pass；不吞异常；不自动修正非法 JSON；
  所有断言为硬断言（assert）。
- 测试自包含：仅使用标准库（json / re / pathlib）+ pytest，
  **不导入 memory-service 任何模块**。
- 未知字段 / 非法角色 / 锚点缺失 / 伪状态令牌出现时本测试必须真实失败。
"""

import json
import re
from pathlib import Path

import pytest

# ── 文件定位 ──

EVAL_DIR = Path(__file__).resolve().parent
POLICY_PATH = EVAL_DIR / "D9_RETRIEVAL_GOLD_POLICY_V2.json"
SPEC_PATH = EVAL_DIR / "D9_RETRIEVAL_GOLD_SPEC_V2.md"
D3_PATH = EVAL_DIR / "D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md"
V1_POLICY_PATH = EVAL_DIR / "D9_RETRIEVAL_GOLD_POLICY_V1.json"
V1_SPEC_PATH = EVAL_DIR / "D9_RETRIEVAL_GOLD_SPEC_V1.md"

# ── 顶层键白名单（出现未知顶层键即失败） ──

TOP_KEYS = {
    "policy",
    "policy_version",
    "status",
    "baseline_ref",
    "spec_ref",
    "supersedes",
    "adjudication_ref",
    "tech_debt_refs",
    "pr_refs",
    "retrieval_ref_schema",
    "roles",
    "empty_gold_rule",
    "negative_guardrail_scope",
    "guardrail_violation_accounting",
    "evaluation_config",
    "conflict_state_semantics",
    "team_defined_params",
    "evaluation_metadata",
}

# ── 嵌套字段白名单 ──

RETRIEVAL_REF_FIELDS = {
    "serialization_key",
    "full_validation_key",
    "applies_to",
    "forbidden_semantics",
}
ROLE_FIELDS = {"description", "in_m2_formal_denominator", "reporting"}
EMPTY_GOLD_FIELDS = {
    "rule_id",
    "definition",
    "recall_denominator",
    "mrr_denominator",
    "ndcg_denominator",
    "forbidden_interpretations",
    "required_report_fields",
    "d3_alignment",
}
GUARDRAIL_FIELDS = {"category_id", "basis", "guardrail_expectation"}
GUARDRAIL_ACCOUNTING_FIELDS = {
    "trigger_definition",
    "query_count_field",
    "item_count_field",
    "query_rate_field",
    "item_rate_field",
    "per_category_breakdown_required",
    "critical_zero_categories",
    "zero_target_rule",
    "denominator_note",
}
EVAL_CONFIG_FIELDS = {
    "config_version",
    "k",
    "top_k",
    "rrf_k",
    "top_k_equals_recall_k",
    "origin",
    "official_requirement",
    "note",
}
CONFLICT_STATE_FIELDS = {
    "values",
    "scope",
    "production_shared_enum",
    "production_retrieval_note",
    "normalization_note",
}
TEAM_PARAM_FIELDS = {"origin", "current_value", "d3_ref", "frozen"}
METADATA_FIELDS = {
    "case_id",
    "dataset_version",
    "gold_label_version",
    "implementation_commit",
    "environment",
    "metric_result",
    "evidence_reference",
    "policy_version",
}

# ── 角色 / 分母 / 边界 / 参数契约 ──

REQUIRED_ROLES = {"positive_retrieval", "negative_guardrail", "boundary"}
EXPECTED_DENOMINATOR = {
    "positive_retrieval": True,
    "negative_guardrail": False,
    "boundary": False,
}
REQUIRED_GUARDRAIL_CATEGORIES = {
    "removed_or_forgotten",
    "expired",
    "superseded",
    "deprecated",
    "candidate",
    "unresolved_conflict",
    "cross_user",
    "sensitive_recall_prohibited",
}
REQUIRED_TEAM_PARAMS = {"statistics_method", "dataset_split"}
FROZEN_PARAMS_NOT_IN_TEAM_DEFINED = {"k", "top_k", "rrf_k"}
REQUIRED_APPLIES_TO = {
    "relevant_refs",
    "forbidden_refs",
    "semantic_near_miss_refs",
    "retrieval_returned_results",
}

# ── D3 M2 锚点（已核验 D3 原文逐字子串；TEAM_DEFINED 锚点取自
#    D3 第五章第 135 行正文，含反引号） ──

EMPTY_GOLD_ANCHOR = "无正解（Gold Label 判定为「不应形成记忆」）的查询不进入分母"
S01_S09_ANCHOR = "命中 S-01..S-09 的查询样本剔除并单列"
TEAM_DEFINED_ANCHOR = "`TEAM_DEFINED`（非 OFFICIAL_REQUIREMENT）"

# ── 伪状态 / 伪结果令牌（对 JSON 与 MD 全文扫描；
#    PASS 大小写敏感且含 PASS_ 前缀；reviewed/sealed 词边界匹配） ──

FORBIDDEN_TOKENS = [
    re.compile(r"HOST_VERIFIED"),
    re.compile(r"\bPASS"),  # 匹配 PASS 及 PASS_* 前缀
    re.compile(r"\breviewed\b", re.IGNORECASE),
    re.compile(r"\bsealed\b", re.IGNORECASE),
]
FORBIDDEN_CLAIMS = ["已达标", "已达成"]

# ── 禁止的真实凭据模式（沿用 D6 纪律） ──

REAL_CREDENTIAL_PATTERNS = [
    re.compile(r"(?i)sk-(?:live|prod|real|actual)-"),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)password=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
    re.compile(r"(?i)token=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
    re.compile(r"(?i)api[_-]?key=(?!PLACEHOLDER|fake|demo|REDACTED|DUMMY)\S+"),
]


# ── 读取辅助（读取/解析异常直接冒泡为测试失败，不吞异常） ──


@pytest.fixture(scope="module")
def policy():
    assert POLICY_PATH.exists(), "策略 JSON 文件不存在"
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def policy_text():
    assert POLICY_PATH.exists(), "策略 JSON 文件不存在"
    return POLICY_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec_text():
    assert SPEC_PATH.exists(), "规格 MD 文件不存在"
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def d3_text():
    assert D3_PATH.exists(), "D3 基线规范文件不存在"
    return D3_PATH.read_text(encoding="utf-8")


# ── 文件存在性（V2 到位、V1 无残留） ──


def test_policy_file_exists():
    assert POLICY_PATH.exists(), "D9_RETRIEVAL_GOLD_POLICY_V2.json 不存在"


def test_spec_file_exists():
    assert SPEC_PATH.exists(), "D9_RETRIEVAL_GOLD_SPEC_V2.md 不存在"


def test_d3_baseline_exists():
    assert D3_PATH.exists(), "D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md 不存在"


def test_v1_policy_absent():
    assert not V1_POLICY_PATH.exists(), (
        "V1 策略候选文件不得在最终 PR 树残留（应已由 v2 替换移除）"
    )


def test_v1_spec_absent():
    assert not V1_SPEC_PATH.exists(), (
        "V1 规范候选文件不得在最终 PR 树残留（应已由 v2 替换移除）"
    )


# ── 策略 JSON：解析与顶层结构 ──


def test_policy_valid_json(policy):
    # fixture 已解析；此处显式断言对象类型（解析失败在 fixture 冒泡）
    assert isinstance(policy, dict), "策略 JSON 顶层必须是对象"


def test_top_level_keys_exact(policy):
    assert set(policy.keys()) == TOP_KEYS, (
        f"顶层键白名单不符: {sorted(set(policy.keys()) ^ TOP_KEYS)}"
    )


def test_policy_identity(policy):
    assert policy["policy"] == "d9_retrieval_gold", "policy 标识必须为 d9_retrieval_gold"
    assert policy["policy_version"] == "v2", "policy_version 必须为 v2"


def test_policy_status_candidate_for_freeze(policy):
    assert policy["status"] == "CANDIDATE_FOR_FREEZE", (
        "status 必须为 CANDIDATE_FOR_FREEZE（不得出现已复核/已封存类状态）"
    )


def test_policy_refs(policy):
    assert policy["baseline_ref"] == "evaluation/D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md"
    assert policy["spec_ref"] == "evaluation/D9_RETRIEVAL_GOLD_SPEC_V2.md"
    assert policy["supersedes"] == "evaluation/D9_RETRIEVAL_GOLD_POLICY_V1.json"
    assert "TD-036" in policy["tech_debt_refs"], "tech_debt_refs 必须引用 TD-036"
    assert "PR #76" in policy["pr_refs"], "pr_refs 必须引用 PR #76"
    assert "Issue #79" in policy["pr_refs"], "pr_refs 必须引用 Issue #79"
    assert "PR #88" in policy["pr_refs"], "pr_refs 必须引用 PR #88（B 轨裁决对象）"


def test_policy_adjudication_ref(policy):
    ref = policy["adjudication_ref"]
    assert isinstance(ref, str) and ref, "adjudication_ref 必须为非空字符串"
    assert "PR #88" in ref, "adjudication_ref 必须关联 PR #88"
    assert "2026-08-31" in ref, "adjudication_ref 必须标注 B 轨裁决日期 2026-08-31"
    assert (
        "day9-e-rw-01-gold-policy-v2-b-adjudication-v1" in ref
    ), "adjudication_ref 必须注明裁决经本任务卡传入"


# ── spec 与 policy 互相引用 ──


def test_spec_and_policy_cross_reference(spec_text):
    assert "D9_RETRIEVAL_GOLD_POLICY_V2.json" in spec_text, (
        "V2 规格文档必须引用配套机器策略契约文件"
    )
    assert "policy_version=v2" in spec_text or "`policy_version=v2`" in spec_text, (
        "V2 规格文档必须声明配套策略 policy_version=v2"
    )


# ── retrieval_ref 版本级判定键 ──


def test_retrieval_ref_schema_whitelist(policy):
    schema = policy["retrieval_ref_schema"]
    assert set(schema.keys()) == RETRIEVAL_REF_FIELDS, (
        f"retrieval_ref_schema 字段白名单不符: "
        f"{sorted(set(schema.keys()) ^ RETRIEVAL_REF_FIELDS)}"
    )


def test_retrieval_ref_serialization_key(policy):
    assert policy["retrieval_ref_schema"]["serialization_key"] == [
        "memory_id",
        "version_id",
    ], "序列化判定键 retrieval_ref 必须为 (memory_id, version_id)"


def test_retrieval_ref_full_validation_key(policy):
    assert policy["retrieval_ref_schema"]["full_validation_key"] == [
        "user_id",
        "memory_id",
        "version_id",
    ], "完整校验键必须为 (user_id, memory_id, version_id)"


def test_retrieval_ref_applies_to(policy):
    applies = set(policy["retrieval_ref_schema"]["applies_to"])
    missing = REQUIRED_APPLIES_TO - applies
    assert not missing, (
        f"retrieval_ref 适用范围缺少必需对象: {sorted(missing)}"
    )


def test_retrieval_ref_forbidden_semantics(policy):
    text = policy["retrieval_ref_schema"]["forbidden_semantics"]
    assert isinstance(text, str) and text, "forbidden_semantics 必须为非空字符串"
    assert "memory_id-only" in text, (
        "forbidden_semantics 必须明确 memory_id-only 不再是正式 Gold v2 契约"
    )
    assert "retrieval_ref" in text, "forbidden_semantics 必须给出 retrieval_ref 键"
    assert "version_id" in text, "forbidden_semantics 必须涉及 version_id"


# ── 角色枚举与分母语义 ──


def test_roles_enum_stable(policy):
    roles = policy["roles"]
    assert set(roles.keys()) == REQUIRED_ROLES, (
        f"角色键集合必须恰为 {sorted(REQUIRED_ROLES)}: {sorted(roles.keys())}"
    )


def test_role_fields_whitelist(policy):
    for role, body in policy["roles"].items():
        assert set(body.keys()) == ROLE_FIELDS, (
            f"角色 {role} 字段白名单不符: {sorted(set(body.keys()) ^ ROLE_FIELDS)}"
        )
        assert isinstance(body["in_m2_formal_denominator"], bool), (
            f"角色 {role} 的 in_m2_formal_denominator 必须为布尔值"
        )
        assert isinstance(body["description"], str) and body["description"], (
            f"角色 {role} 缺少非空 description"
        )
        assert isinstance(body["reporting"], str) and body["reporting"], (
            f"角色 {role} 缺少非空 reporting"
        )


def test_role_denominator_locked(policy):
    for role, expected in EXPECTED_DENOMINATOR.items():
        assert policy["roles"][role]["in_m2_formal_denominator"] is expected, (
            f"角色 {role} 的 in_m2_formal_denominator 必须为 {expected}"
        )


# ── 空 Gold 规则（沿用 v1，逐字契约） ──


def test_empty_gold_fields_whitelist(policy):
    rule = policy["empty_gold_rule"]
    assert set(rule.keys()) == EMPTY_GOLD_FIELDS, (
        f"empty_gold_rule 字段白名单不符: {sorted(set(rule.keys()) ^ EMPTY_GOLD_FIELDS)}"
    )


def test_empty_gold_denominators_excluded(policy):
    rule = policy["empty_gold_rule"]
    assert rule["recall_denominator"] == "excluded"
    assert rule["mrr_denominator"] == "excluded"
    assert rule["ndcg_denominator"] == "excluded"


def test_empty_gold_definition_covers_relevant_refs(policy):
    definition = policy["empty_gold_rule"]["definition"]
    assert "relevant_refs" in definition, "空 Gold 定义必须涉及 relevant_refs"
    assert "正式分母" in definition, "空 Gold 定义必须明确不进入正式分母"


def test_empty_gold_d3_alignment(policy):
    assert policy["empty_gold_rule"]["d3_alignment"] == EMPTY_GOLD_ANCHOR, (
        "d3_alignment 必须与 D3 M2 无效样本处理原文子句一致"
    )


def test_empty_gold_forbidden_interpretations(policy):
    items = policy["empty_gold_rule"]["forbidden_interpretations"]
    assert isinstance(items, list) and items, "forbidden_interpretations 必须为非空数组"
    assert any("满分" in it for it in items), (
        "禁止解释必须包含「空 Gold 计为满分」类解释"
    )
    assert any(("计入" in it and "分母" in it) for it in items), (
        "禁止解释必须包含「计入任一正式分母」类解释"
    )
    assert any("1.0" in it for it in items), (
        "禁止解释必须明确不得计为 Recall=1.0/nDCG=1.0"
    )


def test_empty_gold_required_report_fields(policy):
    fields = policy["empty_gold_rule"]["required_report_fields"]
    assert isinstance(fields, list) and fields, "required_report_fields 必须为非空数组"
    joined = " | ".join(fields)
    assert "valid_query_count" in joined, "必报字段缺少有效查询数 valid_query_count"
    assert "excluded_query_count" in joined, "必报字段缺少剔除数量 excluded_query_count"
    assert "exclusion_reason" in joined, "必报字段缺少剔除原因 exclusion_reason"


# ── D3 M2 锚点存在性（跨文件锚点，缺失即真实失败） ──


def test_d3_empty_gold_anchor_present(d3_text):
    assert EMPTY_GOLD_ANCHOR in d3_text, (
        f"D3 中必须存在锚点原文: {EMPTY_GOLD_ANCHOR}"
    )


def test_d3_s01_s09_anchor_present(d3_text):
    assert S01_S09_ANCHOR in d3_text, (
        f"D3 中必须存在锚点原文: {S01_S09_ANCHOR}"
    )


def test_d3_team_defined_anchor_present(d3_text):
    assert TEAM_DEFINED_ANCHOR in d3_text, (
        f"D3 中必须存在锚点原文: {TEAM_DEFINED_ANCHOR}"
    )


# ── negative_guardrail 边界（八类，含 deprecated） ──


def test_guardrail_scope_structure(policy):
    scope = policy["negative_guardrail_scope"]
    assert isinstance(scope, list) and scope, "negative_guardrail_scope 必须为非空数组"
    for item in scope:
        assert set(item.keys()) == GUARDRAIL_FIELDS, (
            f"guardrail 条目字段白名单不符: {sorted(set(item.keys()) ^ GUARDRAIL_FIELDS)}"
        )
        assert isinstance(item["category_id"], str) and item["category_id"]
        assert isinstance(item["basis"], str) and item["basis"]
        assert isinstance(item["guardrail_expectation"], str) and item[
            "guardrail_expectation"
        ]


def test_guardrail_categories_coverage(policy):
    actual = {item["category_id"] for item in policy["negative_guardrail_scope"]}
    missing = REQUIRED_GUARDRAIL_CATEGORIES - actual
    assert not missing, (
        f"negative_guardrail 缺少必需业务边界: {sorted(missing)}"
    )


def test_guardrail_categories_unique(policy):
    ids = [item["category_id"] for item in policy["negative_guardrail_scope"]]
    assert len(ids) == len(set(ids)), "guardrail category_id 不得重复"


def test_guardrail_deprecated_semantics(policy):
    deprecated = next(
        (
            item
            for item in policy["negative_guardrail_scope"]
            if item["category_id"] == "deprecated"
        ),
        None,
    )
    assert deprecated is not None, "negative_guardrail 必须包含 deprecated 类别"
    expectation = deprecated["guardrail_expectation"]
    assert "history/audit" in expectation, (
        "deprecated 条目必须声明仅显式 history/audit 模式可访问"
    )
    assert "标准 M2" in expectation, (
        "deprecated 条目必须声明不进入标准 M2 正式分母"
    )
    assert "standard Memory Context" in deprecated["basis"], (
        "deprecated 条目依据必须声明 standard Memory Context 归入 negative_guardrail"
    )


# ── guardrail violation 统计口径 ──


def test_guardrail_violation_accounting_whitelist(policy):
    acc = policy["guardrail_violation_accounting"]
    assert set(acc.keys()) == GUARDRAIL_ACCOUNTING_FIELDS, (
        f"guardrail_violation_accounting 字段白名单不符: "
        f"{sorted(set(acc.keys()) ^ GUARDRAIL_ACCOUNTING_FIELDS)}"
    )


def test_guardrail_violation_count_fields(policy):
    acc = policy["guardrail_violation_accounting"]
    assert acc["query_count_field"] == "guardrail_violation_query_count"
    assert acc["item_count_field"] == "guardrail_violation_item_count"
    assert acc["query_rate_field"] == "guardrail_violation_query_rate"
    assert acc["item_rate_field"] == "guardrail_violation_item_rate"


def test_guardrail_violation_trigger_definition(policy):
    trigger = policy["guardrail_violation_accounting"]["trigger_definition"]
    assert isinstance(trigger, str) and trigger
    assert "Top-K" in trigger, "触发定义必须基于 Top-K 检索返回结果"
    assert "1 次" in trigger, "触发定义必须明确该 query 计 1 次"
    assert "forbidden ref" in trigger, "触发定义必须明确 forbidden ref"


def test_guardrail_violation_breakdown_and_critical_zero(policy):
    acc = policy["guardrail_violation_accounting"]
    assert acc["per_category_breakdown_required"] is True, (
        "必须要求按类别拆分 violation 统计"
    )
    assert acc["critical_zero_categories"] == [
        "cross_user",
        "sensitive_recall_prohibited",
    ], "critical 零值类别必须恰为 cross_user 与 sensitive_recall_prohibited"


def test_guardrail_violation_zero_target_rule(policy):
    rule = policy["guardrail_violation_accounting"]["zero_target_rule"]
    assert isinstance(rule, str) and rule
    assert "cross_user" in rule and "sensitive_recall_prohibited" in rule
    assert "critical" in rule, "zero_target_rule 必须声明任一非零标 critical"
    assert "0" in rule, "zero_target_rule 必须声明零值目标"


def test_guardrail_violation_denominator_note(policy):
    note = policy["guardrail_violation_accounting"]["denominator_note"]
    assert isinstance(note, str) and note
    assert "正式分母" in note, "denominator_note 必须声明独立于正式分母"
    assert "empty_gold_rule" in note, (
        "denominator_note 必须声明不改变空 Gold 规则"
    )


# ── 评测配置冻结（d9-retrieval-eval-config/v1） ──


def test_eval_config_whitelist(policy):
    cfg = policy["evaluation_config"]
    assert set(cfg.keys()) == EVAL_CONFIG_FIELDS, (
        f"evaluation_config 字段白名单不符: "
        f"{sorted(set(cfg.keys()) ^ EVAL_CONFIG_FIELDS)}"
    )


def test_eval_config_frozen_values(policy):
    cfg = policy["evaluation_config"]
    assert cfg["config_version"] == "d9-retrieval-eval-config/v1"
    assert cfg["k"] == 10, "Recall@K 的 K 必须冻结为 10"
    assert cfg["top_k"] == 10, "Top-K 窗口必须冻结为 10"
    assert cfg["rrf_k"] == 60, "RRF k 必须冻结为 60"
    assert cfg["top_k"] == cfg["k"], "top_k 必须等于 Recall@K 的 K"
    assert cfg["top_k_equals_recall_k"] is True


def test_eval_config_team_defined_origin(policy):
    cfg = policy["evaluation_config"]
    assert cfg["origin"] == "TEAM_DEFINED", (
        "评测配置 origin 必须为 TEAM_DEFINED（非比赛官方要求）"
    )
    assert cfg["official_requirement"] is False, (
        "official_requirement 必须为 false（不得写成比赛官方要求）"
    )
    assert isinstance(cfg["note"], str) and cfg["note"]


# ── conflict_state 评测归一化语义 ──


def test_conflict_state_semantics_whitelist(policy):
    cs = policy["conflict_state_semantics"]
    assert set(cs.keys()) == CONFLICT_STATE_FIELDS, (
        f"conflict_state_semantics 字段白名单不符: "
        f"{sorted(set(cs.keys()) ^ CONFLICT_STATE_FIELDS)}"
    )


def test_conflict_state_values_and_scope(policy):
    cs = policy["conflict_state_semantics"]
    assert cs["values"] == ["none", "resolved", "unresolved"], (
        "conflict_state 取值必须恰为 {none, resolved, unresolved}"
    )
    assert "evaluation normalization" in cs["scope"], (
        "conflict_state 必须声明仅属 evaluation normalization 字段"
    )


def test_conflict_state_not_production_enum(policy):
    cs = policy["conflict_state_semantics"]
    assert cs["production_shared_enum"] is False, (
        "conflict_state 不得为 production shared enum"
    )
    assert "production shared enum" in cs["production_retrieval_note"].lower() or (
        "production shared enum" in cs["scope"].lower()
    ), "必须明确 NOT production shared enum"


def test_conflict_state_production_retrieval_note(policy):
    note = policy["conflict_state_semantics"]["production_retrieval_note"]
    assert isinstance(note, str) and note
    assert "unresolved" in note, "生产检索 note 必须提及 unresolved"
    assert "硬过滤" in note, "生产检索 note 必须声明既有 unresolved 硬过滤"
    assert "不修改 B 轨" in note, "生产检索 note 必须声明不修改 B 轨实现"


# ── TEAM_DEFINED 未冻结参数（仅 statistics_method / dataset_split） ──


def test_team_defined_params_keys_exact(policy):
    params = policy["team_defined_params"]
    assert set(params.keys()) == REQUIRED_TEAM_PARAMS, (
        f"team_defined_params 必须恰为 {sorted(REQUIRED_TEAM_PARAMS)}: "
        f"{sorted(set(params.keys()) ^ REQUIRED_TEAM_PARAMS)}"
    )


def test_frozen_params_not_in_team_defined(policy):
    params = policy["team_defined_params"]
    overlap = FROZEN_PARAMS_NOT_IN_TEAM_DEFINED & set(params.keys())
    assert not overlap, (
        f"已冻结参数 k/top_k/rrf_k 不得留在 team_defined_params: {sorted(overlap)}"
    )


def test_team_defined_param_fields_whitelist(policy):
    for name, body in policy["team_defined_params"].items():
        assert set(body.keys()) == TEAM_PARAM_FIELDS, (
            f"参数 {name} 字段白名单不符: {sorted(set(body.keys()) ^ TEAM_PARAM_FIELDS)}"
        )


def test_team_defined_origin_value_and_frozen(policy):
    for name, body in policy["team_defined_params"].items():
        assert body["origin"] == "TEAM_DEFINED", (
            f"参数 {name} 的 origin 必须为 TEAM_DEFINED，当前: {body['origin']}"
        )
        assert body["current_value"] == "PENDING", (
            f"参数 {name} 的 current_value 必须为 PENDING（不冻结取值）"
        )
        assert body["frozen"] is False, (
            f"参数 {name} 必须标记 frozen=false（裁决未冻结）"
        )
        assert isinstance(body["d3_ref"], str) and body["d3_ref"], (
            f"参数 {name} 必须引用 D3 登记行"
        )


def test_no_official_requirement_origin(policy):
    for name, body in policy["team_defined_params"].items():
        assert body["origin"] != "OFFICIAL_REQUIREMENT", (
            f"参数 {name} 不得把 TEAM_DEFINED 项声明为 OFFICIAL_REQUIREMENT"
        )


# ── 版本化评测元数据 ──


def test_evaluation_metadata_fields(policy):
    meta = policy["evaluation_metadata"]
    assert set(meta.keys()) == METADATA_FIELDS, (
        f"evaluation_metadata 字段白名单不符: {sorted(set(meta.keys()) ^ METADATA_FIELDS)}"
    )


def test_evaluation_metadata_placeholders(policy):
    for field, value in policy["evaluation_metadata"].items():
        assert value == "PENDING", (
            f"evaluation_metadata.{field} 必须为占位 PENDING（不得写入真实结果/数据）"
        )


def test_metadata_includes_policy_version(policy):
    assert "policy_version" in policy["evaluation_metadata"], (
        "evaluation_metadata 必须包含 policy_version 以支持版本化追溯"
    )


# ── 伪状态 / 伪结果令牌扫描（对 JSON 与 MD 全文） ──


def _assert_no_forbidden_tokens(text, label):
    for pat in FORBIDDEN_TOKENS:
        m = pat.search(text)
        assert not m, f"{label} 中出现伪状态令牌: {m.group(0)!r}（模式 {pat.pattern}）"
    for claim in FORBIDDEN_CLAIMS:
        assert claim not in text, f"{label} 中出现伪结果虚标短语: {claim}"


def test_policy_no_forbidden_tokens(policy_text):
    _assert_no_forbidden_tokens(policy_text, "D9_RETRIEVAL_GOLD_POLICY_V2.json")


def test_spec_no_forbidden_tokens(spec_text):
    _assert_no_forbidden_tokens(spec_text, "D9_RETRIEVAL_GOLD_SPEC_V2.md")


# ── 规格文档内容声明检查 ──


def test_spec_declares_three_roles(spec_text):
    for role in ("positive_retrieval", "negative_guardrail", "boundary"):
        assert role in spec_text, f"规格文档必须声明角色 {role}"


def test_spec_declares_candidate_status(spec_text):
    assert "CANDIDATE_FOR_FREEZE" in spec_text


def test_spec_declares_dependencies(spec_text):
    assert "TD-036" in spec_text, "规格文档必须引用 TD-036"
    assert "PR #76" in spec_text, "规格文档必须引用 PR #76"
    assert "Issue #79" in spec_text, "规格文档必须引用 Issue #79"
    assert "PR #88" in spec_text, "规格文档必须引用 PR #88（B 轨裁决对象）"


def test_spec_declares_no_b_modification(spec_text):
    assert "不修改 B 轨" in spec_text, "规格文档必须声明不修改 B 轨实现"


def test_spec_declares_empty_gold_rule(spec_text):
    assert "D9-EMPTY-GOLD-01" in spec_text, "规格文档必须定义 D9-EMPTY-GOLD-01"
    assert "不进入分母" in spec_text


def test_spec_declares_b_side_scenarios(spec_text):
    for scene in ("空集", "混合集", "全空集"):
        assert scene in spec_text, f"规格文档必须声明 B 轨验证场景「{scene}」"
    assert "valid_query_count" in spec_text


def test_spec_declares_retrieval_ref(spec_text):
    assert "retrieval_ref" in spec_text, "规格文档必须声明版本级判定键 retrieval_ref"
    assert "memory_id" in spec_text and "version_id" in spec_text
    assert "memory_id-only" in spec_text, (
        "规格文档必须声明 memory_id-only 不再是正式契约"
    )


def test_spec_declares_deprecated_guardrail(spec_text):
    assert "deprecated" in spec_text, "规格文档必须声明 deprecated 归入 guardrail"
    assert "history/audit" in spec_text, (
        "规格文档必须声明 deprecated 仅显式 history/audit 模式可访问"
    )


def test_spec_declares_frozen_eval_config(spec_text):
    assert "d9-retrieval-eval-config/v1" in spec_text, (
        "规格文档必须声明冻结配置 d9-retrieval-eval-config/v1"
    )
    assert "rrf_k" in spec_text and "top_k" in spec_text
    assert "TEAM_DEFINED" in spec_text


def test_spec_declares_conflict_state_normalization(spec_text):
    assert "评测归一化" in spec_text, (
        "规格文档必须声明 conflict_state 属评测归一化"
    )
    assert "production shared enum" in spec_text.lower(), (
        "规格文档必须声明 conflict_state NOT production shared enum"
    )


def test_spec_declares_v1_replaced(spec_text):
    assert "替换移除" in spec_text, "规格文档必须声明 V1 候选已由 v2 替换移除"
    assert "D9_RETRIEVAL_GOLD_SPEC_V1.md" in spec_text, (
        "规格文档必须登记 V1 spec 的历史演进对应文件"
    )


# ── 凭据扫描 ──


def test_no_real_credentials(policy_text, spec_text):
    for label, text in (
        ("D9_RETRIEVAL_GOLD_POLICY_V2.json", policy_text),
        ("D9_RETRIEVAL_GOLD_SPEC_V2.md", spec_text),
    ):
        for pat in REAL_CREDENTIAL_PATTERNS:
            assert not pat.search(text), (
                f"{label} 中出现疑似真实凭据模式: {pat.pattern}"
            )