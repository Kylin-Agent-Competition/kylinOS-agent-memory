"""
test_d9_retrieval_gold_spec.py — Day9E 检索 Gold/指标语义 v1 验证测试

对齐任务卡：day9-e-01-retrieval-gold-metric-semantics-v1

目标：校验 `D9_RETRIEVAL_GOLD_POLICY_V1.json` 与
`D9_RETRIEVAL_GOLD_SPEC_V1.md` 的语义冻结契约：

- 策略 JSON 可解析；顶层/嵌套字段白名单 fail-fast（未知字段即失败）；
- 三类评测角色枚举稳定（positive_retrieval / negative_guardrail / boundary）
  且各自 in_m2_formal_denominator 取值锁定（true / false / false）；
- 空 Gold（empty relevant_ids）不进入 Recall/MRR/nDCG 正式分母，
  与 D3 第四章 M2 无效样本处理原文子句一致；
- negative_guardrail 覆盖七类业务边界：
  removed_or_forgotten / expired / superseded / candidate /
  unresolved_conflict / cross_user / sensitive_recall_prohibited；
- TEAM_DEFINED 参数边界：origin 仅允许 "TEAM_DEFINED"、
  current_value="PENDING"，不得以 OFFICIAL_REQUIREMENT 为 origin；
- 版本化评测元数据字段与 D3 第十二章对齐（含 policy_version）；
- 两新文件全文不得出现伪状态/伪结果令牌：
  HOST_VERIFIED / PASS（含 PASS_ 前缀）/ reviewed / sealed / 已达标 / 已达成；
- 规格文档声明三类角色、TD-036 / PR #76 / Issue #79 依赖与
  「不修改 B 轨实现」边界；
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
POLICY_PATH = EVAL_DIR / "D9_RETRIEVAL_GOLD_POLICY_V1.json"
SPEC_PATH = EVAL_DIR / "D9_RETRIEVAL_GOLD_SPEC_V1.md"
D3_PATH = EVAL_DIR / "D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md"

# ── 顶层键白名单（出现未知顶层键即失败） ──

TOP_KEYS = {
    "policy",
    "policy_version",
    "status",
    "baseline_ref",
    "spec_ref",
    "tech_debt_refs",
    "pr_refs",
    "roles",
    "empty_gold_rule",
    "negative_guardrail_scope",
    "team_defined_params",
    "evaluation_metadata",
}

# ── 嵌套字段白名单 ──

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
TEAM_PARAM_FIELDS = {"origin", "current_value", "d3_ref"}
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
    "candidate",
    "unresolved_conflict",
    "cross_user",
    "sensitive_recall_prohibited",
}
REQUIRED_TEAM_PARAMS = {"k", "top_k", "rrf_k", "statistics_method", "dataset_split"}

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


# ── 文件存在性 ──


def test_policy_file_exists():
    assert POLICY_PATH.exists(), "D9_RETRIEVAL_GOLD_POLICY_V1.json 不存在"


def test_spec_file_exists():
    assert SPEC_PATH.exists(), "D9_RETRIEVAL_GOLD_SPEC_V1.md 不存在"


def test_d3_baseline_exists():
    assert D3_PATH.exists(), "D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md 不存在"


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
    assert policy["policy_version"] == "v1", "policy_version 必须为 v1"


def test_policy_status_candidate_for_freeze(policy):
    assert policy["status"] == "CANDIDATE_FOR_FREEZE", (
        "status 必须为 CANDIDATE_FOR_FREEZE（不得出现已复核/已封存类状态）"
    )


def test_policy_refs(policy):
    assert policy["baseline_ref"] == "evaluation/D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md"
    assert policy["spec_ref"] == "evaluation/D9_RETRIEVAL_GOLD_SPEC_V1.md"
    assert "TD-036" in policy["tech_debt_refs"], "tech_debt_refs 必须引用 TD-036"
    assert "PR #76" in policy["pr_refs"], "pr_refs 必须引用 PR #76"
    assert "Issue #79" in policy["pr_refs"], "pr_refs 必须引用 Issue #79"


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


# ── 空 Gold 规则 ──


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


def test_empty_gold_definition_covers_relevant_ids(policy):
    definition = policy["empty_gold_rule"]["definition"]
    assert "relevant_ids" in definition, "空 Gold 定义必须涉及 relevant_ids"
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


# ── negative_guardrail 边界 ──


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


# ── TEAM_DEFINED 参数边界 ──


def test_team_defined_params_required_keys(policy):
    params = policy["team_defined_params"]
    missing = REQUIRED_TEAM_PARAMS - set(params.keys())
    assert not missing, f"team_defined_params 缺少必需参数: {sorted(missing)}"


def test_team_defined_param_fields_whitelist(policy):
    for name, body in policy["team_defined_params"].items():
        assert set(body.keys()) == TEAM_PARAM_FIELDS, (
            f"参数 {name} 字段白名单不符: {sorted(set(body.keys()) ^ TEAM_PARAM_FIELDS)}"
        )


def test_team_defined_origin_and_value(policy):
    for name, body in policy["team_defined_params"].items():
        assert body["origin"] == "TEAM_DEFINED", (
            f"参数 {name} 的 origin 必须为 TEAM_DEFINED，当前: {body['origin']}"
        )
        assert body["current_value"] == "PENDING", (
            f"参数 {name} 的 current_value 必须为 PENDING（不冻结取值）"
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
    _assert_no_forbidden_tokens(policy_text, "D9_RETRIEVAL_GOLD_POLICY_V1.json")


def test_spec_no_forbidden_tokens(spec_text):
    _assert_no_forbidden_tokens(spec_text, "D9_RETRIEVAL_GOLD_SPEC_V1.md")


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


def test_spec_declares_no_b_modification(spec_text):
    assert "不修改 B 轨" in spec_text, "规格文档必须声明不修改 B 轨实现"


def test_spec_declares_empty_gold_rule(spec_text):
    assert "D9-EMPTY-GOLD-01" in spec_text, "规格文档必须定义 D9-EMPTY-GOLD-01"
    assert "不进入分母" in spec_text


def test_spec_declares_b_side_scenarios(spec_text):
    for scene in ("空集", "混合集", "全空集"):
        assert scene in spec_text, f"规格文档必须声明 B 轨验证场景「{scene}」"
    assert "valid_query_count" in spec_text


# ── 凭据扫描 ──


def test_no_real_credentials(policy_text, spec_text):
    for label, text in (
        ("D9_RETRIEVAL_GOLD_POLICY_V1.json", policy_text),
        ("D9_RETRIEVAL_GOLD_SPEC_V1.md", spec_text),
    ):
        for pat in REAL_CREDENTIAL_PATTERNS:
            assert not pat.search(text), (
                f"{label} 中出现疑似真实凭据模式: {pat.pattern}"
            )