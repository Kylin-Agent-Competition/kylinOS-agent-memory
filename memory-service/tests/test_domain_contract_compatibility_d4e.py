"""
test_domain_contract_compatibility_d4e.py — Day4 E 跨轨契约兼容门禁测试

对齐任务卡：day4-e-03-contract-compatibility-gate-v1（建立Day4 E业务层契约兼容门禁）。

测试目标：这是**跨轨契约防漂移门禁**，不是生产功能实现。它把 Day4 E 新增业务层骨架
（domain/service/security）与当前 A 轨已存在实现（memory-service/pipeline/schemas.py、
memory-service/providers/extraction_provider.py）之间的一致性状态编码为自动化断言，
防止未来任何一侧修改引入字段值域漂移或第二套真源。

以当前 main 中的 A 轨实现为"已存在事实"引用，不做任何 A 轨修改：

- pipeline/schemas.py 事实：MemorySourceEvent / NormalizedEvent / MemoryType（四值）
- providers/extraction_provider.py 事实：PreferenceCandidate / KnowledgeCandidate /
  PreferenceScope / Explicitness / KnowledgeCategory / PreferenceCategory

覆盖的防漂移契约（对齐 D3_MEMORY_BUSINESS_CONTRACT_V1.md §5.6 与 C-01/C-05 登记）：

1. Domain 不重新定义 A 轨共享类型：MemorySourceEvent / NormalizedEvent /
   PreferenceCandidate / KnowledgeCandidate（含 domain.__all__ 排除）。
2. Provider↔Domain 枚举值域一致（含 D3 §5.6 明确命名映射）：
   - PreferenceScope（同名，§5.6 preference_scope 五值）
   - Explicitness ↔ ExpressionType（C-01 归一，§5.6 expression_type 二值）
   - KnowledgeCategory ↔ KnowledgeType（§5.6 knowledge_type 六值）
   - PreferenceCategory（A 轨 TABLE 19 分类，不在 D3 §5.6 冻结业务枚举中，
     Domain 不得定义同名平行枚举）。
3. candidate 生命周期兼容：Provider 候选模型 memory_status="candidate"
   被 Domain MemoryStatus 值集接受（§5.6 memory_status，candidate 六值之一）。
4. MemoryType 复用而非重定义：domain/knowledge.py 引用的 MemoryType 与
   pipeline.schemas.MemoryType 为同一对象（identity 检查），Knowledge.memory_type
   字段 annotation 亦为 pipeline.schemas.MemoryType。
5. 无同名同值域平行定义：pipeline.schemas 与 domain.enums 之间若出现同名枚举，
   值域必须一致（当前无同名，此为防未来漂移门禁）。

测试纪律：
- 不使用 Mock、skip、xfail、monkeypatch 长期替换模块或固定 PASS 输出。
- 仅使用合成数据（user_demo_*、evt_d4e_*、脱敏内容），不引入任何真实用户数据。
- 测试失败 = 跨轨契约漂移，属于 CODE_FAILURE 或 TEST_FAILURE，不得通过删除
  断言或扩容允许范围使其变绿；若揭示 A 轨实现与 D3 契约真实冲突，由独立
  跨轨任务处理，本测试不修改 A 轨。
"""

import sys
import typing
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── A 轨已存在实现事实（只读引用，不修改） ──
import pipeline.schemas as pipeline_schemas_module  # noqa: E402
from pipeline.schemas import MemorySourceEvent, MemoryType, NormalizedEvent  # noqa: E402
from providers.extraction_provider import (  # noqa: E402
    Explicitness as ProviderExplicitness,
    KnowledgeCandidate as ProviderKnowledgeCandidate,
    KnowledgeCategory as ProviderKnowledgeCategory,
    PreferenceCandidate as ProviderPreferenceCandidate,
    PreferenceCategory as ProviderPreferenceCategory,
    PreferenceScope as ProviderPreferenceScope,
)

# ── Day4 E 业务层骨架（本批次新增） ──
import domain  # noqa: E402
from domain import knowledge as domain_knowledge  # noqa: E402
from domain.enums import (  # noqa: E402
    ExpressionType as DomainExpressionType,
    KnowledgeType as DomainKnowledgeType,
    MemoryStatus as DomainMemoryStatus,
    PreferenceScope as DomainPreferenceScope,
)

# A 轨共享类型候选集（防漂移契约 1：Domain 不得重新定义）
_A_TRACK_SHARED_TYPE_NAMES = (
    "MemorySourceEvent",
    "NormalizedEvent",
    "PreferenceCandidate",
    "KnowledgeCandidate",
)


def _enum_value_set(enum_cls) -> frozenset:
    """提取 str-Enum 值域（确定性：同一枚举 → 同一值集）。"""
    return frozenset(m.value for m in enum_cls)


def _iter_enum_classes(module):
    """遍历模块中定义的 Enum 子类（排除 enum.Enum 基类本身）。"""
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, Enum) and obj is not Enum:
            yield name, obj


def _literal_string_values(annotation) -> frozenset:
    """从 Literal annotation 提取字符串值集合。

    兼容 Pydantic v2 已解析的 typing.Literal：get_args 返回字面量元组。
    防御性处理字符串形式（from __future__ import annotations 场景）：
    若 get_args 为空且 annotation 为 str，则回退用模型类 get_type_hints
    解析，避免测试依赖具体环境。
    """
    if annotation is None:
        return frozenset()
    args = typing.get_args(annotation)
    if args:
        return frozenset(str(a) for a in args)
    if isinstance(annotation, str):
        # 字符串形式的前向引用：交由 Pydantic 模型解析后取字段 annotation
        return frozenset()
    return frozenset()


def _provider_memory_status_values(model_cls) -> frozenset:
    """从 Provider 候选模型 memory_status 字段提取允许值。

    首选 model_fields 中已解析的 annotation（Pydantic v2 行为）；
    若为未解析字符串（forward ref），回退 get_type_hints 解析。
    """
    annotation = model_cls.model_fields["memory_status"].annotation
    values = _literal_string_values(annotation)
    if not values and isinstance(annotation, str):
        hints = typing.get_type_hints(model_cls)
        values = _literal_string_values(hints["memory_status"])
    return values


# ── 契约 1：Domain 不重新定义 A 轨共享类型 ──


def test_domain_does_not_redefine_memory_source_event():
    """Domain 不得重新定义 pipeline.schemas.MemorySourceEvent（第二套真源禁止）。"""
    assert pipeline_schemas_module.MemorySourceEvent is MemorySourceEvent  # A 轨事实存在
    assert not hasattr(domain, "MemorySourceEvent"), (
        "domain 不得重新定义 A 轨 MemorySourceEvent")


def test_domain_does_not_redefine_normalized_event():
    """Domain 不得重新定义 pipeline.schemas.NormalizedEvent。"""
    assert pipeline_schemas_module.NormalizedEvent is NormalizedEvent  # A 轨事实存在
    assert not hasattr(domain, "NormalizedEvent"), (
        "domain 不得重新定义 A 轨 NormalizedEvent")


def test_domain_does_not_redefine_preference_candidate():
    """Domain 不得重新定义 providers PreferenceCandidate。"""
    assert ProviderPreferenceCandidate is not None  # A 轨事实可导入
    assert not hasattr(domain, "PreferenceCandidate"), (
        "domain 不得重新定义 A 轨 PreferenceCandidate")


def test_domain_does_not_redefine_knowledge_candidate():
    """Domain 不得重新定义 providers KnowledgeCandidate。"""
    assert ProviderKnowledgeCandidate is not None
    assert not hasattr(domain, "KnowledgeCandidate"), (
        "domain 不得重新定义 A 轨 KnowledgeCandidate")


def test_domain_all_excludes_shared_types():
    """domain.__all__ 不得导出 A 轨共享类型（4 类）与 MemoryType。"""
    shared = set(_A_TRACK_SHARED_TYPE_NAMES) | {"MemoryType"}
    assert shared & set(domain.__all__) == set(), (
        f"domain.__all__ 不得包含：{shared & set(domain.__all__)}")


# ── 契约 2：Provider↔Domain 枚举值域一致（含 D3 §5.6 命名映射） ──


def test_preference_scope_literal_matches_domain_enum():
    """PreferenceScope 同名映射：Provider 五值与 Domain PreferenceScope 值域一致
    （D3 §5.6 preference_scope 五值；C-05 已对齐，见 extraction_provider.py）。"""
    provider_values = frozenset(typing.get_args(ProviderPreferenceScope))
    domain_values = _enum_value_set(DomainPreferenceScope)
    assert provider_values == domain_values, (
        f"PreferenceScope 漂移: provider={sorted(provider_values)} "
        f"domain={sorted(domain_values)}")


def test_explicitness_literal_matches_expression_type_enum():
    """Explicitness ↔ ExpressionType 命名映射（D3 §5.6 expression_type、
    C-01 修订2 归一）：explicit/implicit 二值一致。"""
    provider_values = frozenset(typing.get_args(ProviderExplicitness))
    domain_values = _enum_value_set(DomainExpressionType)
    assert provider_values == domain_values, (
        f"Explicitness/ExpressionType 漂移: provider={sorted(provider_values)} "
        f"domain={sorted(domain_values)}")


def test_knowledge_category_literal_matches_knowledge_type_enum():
    """KnowledgeCategory ↔ KnowledgeType 命名映射（D3 §5.6 knowledge_type
    六值；E 轨 §2.6）：fact/workflow/case/template/constraint/failure_experience。"""
    provider_values = frozenset(typing.get_args(ProviderKnowledgeCategory))
    domain_values = _enum_value_set(DomainKnowledgeType)
    assert provider_values == domain_values, (
        f"KnowledgeCategory/KnowledgeType 漂移: provider={sorted(provider_values)} "
        f"domain={sorted(domain_values)}")


def test_preference_category_no_domain_parallel_definition():
    """PreferenceCategory 为 A 轨 TABLE 19 六类分类，不在 D3 §5.6 冻结业务
    枚举中；Domain 不得定义同名平行枚举（防止第二套真源）。"""
    provider_values = frozenset(typing.get_args(ProviderPreferenceCategory))
    assert provider_values == frozenset({
        "presentation", "tool_selection", "workflow", "safety",
        "environment", "scene_specific",
    }), f"A 轨 PreferenceCategory 漂移: {sorted(provider_values)}"
    assert not hasattr(domain, "PreferenceCategory"), (
        "domain 不得定义平行 PreferenceCategory 枚举")
    assert not hasattr(domain.enums, "PreferenceCategory"), (
        "domain.enums 不得定义平行 PreferenceCategory 枚举")


# ── 契约 3：candidate 生命周期兼容 ──


def test_provider_preference_candidate_memory_status_accepted_by_domain():
    """Provider PreferenceCandidate.memory_status="candidate" 被 Domain
    MemoryStatus 值集接受（D3 §5.6 memory_status 六值、B2 恒 candidate）。"""
    provider_values = _provider_memory_status_values(ProviderPreferenceCandidate)
    domain_values = _enum_value_set(DomainMemoryStatus)
    assert provider_values <= domain_values, (
        f"PreferenceCandidate memory_status 漂移: provider={sorted(provider_values)} "
        f"domain={sorted(domain_values)}")
    # 实例级验证：Provider 候选确实以 candidate 落值（运行期事实，非仅类型层）
    cand = ProviderPreferenceCandidate(
        key="demo_key_d4e_03",
        value="demo_value_d4e_03",
        confidence=0.5,
        evidence="演示证据（脱敏）",
        source_event_id="evt_d4e_03",
    )
    assert cand.memory_status == "candidate"
    assert cand.memory_status in domain_values


def test_provider_knowledge_candidate_memory_status_accepted_by_domain():
    """Provider KnowledgeCandidate.memory_status="candidate" 被 Domain
    MemoryStatus 值集接受（B2 恒 candidate；D8 六类知识同样恒 candidate）。"""
    provider_values = _provider_memory_status_values(ProviderKnowledgeCandidate)
    domain_values = _enum_value_set(DomainMemoryStatus)
    assert provider_values <= domain_values, (
        f"KnowledgeCandidate memory_status 漂移: provider={sorted(provider_values)} "
        f"domain={sorted(domain_values)}")
    cand = ProviderKnowledgeCandidate(
        fact="演示知识：按修改日期降序排列文件（脱敏）",
        confidence=0.6,
        source_event_id="evt_d4e_03",
    )
    assert cand.memory_status == "candidate"
    assert cand.memory_status in domain_values


# ── 契约 4：MemoryType 复用而非重定义 ──


def test_domain_knowledge_memory_type_is_pipeline_memory_type():
    """domain/knowledge.py 引用的 MemoryType 与 pipeline.schemas.MemoryType
    是同一对象（identity 检查：复用共享类型，非值碰巧一致）。"""
    assert domain_knowledge.MemoryType is MemoryType, (
        "domain.knowledge.MemoryType 必须复用 pipeline.schemas.MemoryType")


def test_domain_all_excludes_memory_type():
    """domain.__all__ 不得导出 MemoryType（共享类型经由 pipeline.schemas 复用）。"""
    assert "MemoryType" not in domain.__all__, (
        "domain.__all__ 不得导出 MemoryType")


def test_knowledge_memory_type_field_annotation_is_pipeline_enum():
    """Knowledge.memory_type 字段 annotation 即为 pipeline.schemas.MemoryType
    （identity 检查：模型字段直接使用共享枚举对象）。"""
    from domain.knowledge import Knowledge

    annotation = Knowledge.model_fields["memory_type"].annotation
    assert annotation is MemoryType, (
        f"Knowledge.memory_type annotation 漂移: {annotation!r}")


# ── 契约 5：无同名异值平行定义（防未来漂移门禁） ──


def test_no_pipeline_domain_enum_name_collision_with_different_values():
    """pipeline.schemas 与 domain.enums 之间：同名枚举必须值域一致。

    当前无同名 Enum（共享类型 MemoryType 由 domain/knowledge.py 从
    pipeline.schemas 显式复用而非模块级同名定义）；本测试是防漂移门禁——
    若未来任一模块新增同名但值域不同的枚举，测试立即失败。
    """
    from domain import enums as domain_enums_module

    pipeline_enums = dict(_iter_enum_classes(pipeline_schemas_module))
    domain_enums = dict(_iter_enum_classes(domain_enums_module))
    common_names = set(pipeline_enums) & set(domain_enums)
    for name in sorted(common_names):
        assert _enum_value_set(pipeline_enums[name]) == _enum_value_set(
            domain_enums[name]), (
            f"同名枚举 {name} 值域不一致（第二套真源风险）："
            f"pipeline={sorted(_enum_value_set(pipeline_enums[name]))} "
            f"domain={sorted(_enum_value_set(domain_enums[name]))}")