# TD-014 关闭候选审计报告（Domain Optional ID/Reference/Selector 非空约束统一）

- **任务**：day12-e-05-td014-closure-audit-v6（D12E TD-014 关闭候选事实审计回写）
- **日期**：2026-09-03
- **分支**：`fix/e-d12-business-schema-drift-remediation`
- **当前 HEAD**：`5d1c4cacbda629f97934e52f7cd0d5cbcd81ba9f`（工作区干净）
- **审计对象**：TD-014「Domain Optional ID/字符串字段非空约束未统一」（`memory-service/domain/preference.py`、`knowledge.py`、`conflict.py`、`forgetting.py`）
- **审计性质**：关闭候选审计（Closure Candidate），**非 Resolved 宣告**。本报告陈述仓库中已落地并已提交的代码事实、测试定义，以及 2026-09-03 在 WSL2 project `.venv` 中实际取得的 L1 验证结果；不虚构银河麒麟 Runtime 证据或 Reviewer 签署。

---

## 0、四层状态分离说明

本报告按以下四层分别陈述，各层互不替代；另设 `GAP` 分类承载盘点中判定为「尚未统一」或「明确判定为本债范围外」的字段：

| 层 | 状态标记 | 含义 |
|----|----------|------|
| 代码事实层 | `CODE_VERIFIED` | Optional ID/Reference/Selector 字段已在当前分支统一约束，引用文件与行号可核对 |
| 测试定义层 | `TEST_DEFINED` | 对应负向/兼容测试用例已定义并已提交；**只陈述定义存在与断言意图，不写运行数值** |
| L1 验证层 | `WSL_L1_VERIFIED` | 2026-09-03 已在当前 PR 分支的 WSL2 project `.venv` 中执行 TD-013/TD-014 定向回归，结果 `132 passed in 0.42s`、exit code 0；该结果不构成 `HOST_VERIFIED` 或 L2/L3 Runtime 证据 |
| Reviewer 关闭层 | `REVIEW_PENDING` | D 主审（周子腾）尚未签署，状态为 Closure Candidate / In Progress pending D Reviewer，**不得标记 Resolved** |
| 范围决策层 | `GAP` | 盘点中发现的 Optional 字符串字段，标注为「未纳入 TD-014 统一约束」的范围决策点，交由 D 主审确认 |

---

## 1、代码事实层（CODE_VERIFIED）

实现文件（当前分支 HEAD）：

- `memory-service/domain/common.py`：统一约束类型 `NonEmptyStr`（第 51 行）、`NonEmptyIdList`（第 57 行）、`_ensure_non_blank`（第 38–45 行，strip 后为空即拒绝、否则原样返回不 strip）；
- `memory-service/domain/preference.py` / `knowledge.py` / `conflict.py` / `forgetting.py`：四模型 Optional ID/Reference/Selector 字段逐项落地。

### 1.1 Preference 盘点

| 字段 | 类型（当前实现） | 引用行号 | TD-014 关闭条件对应 | 状态 |
|------|------------------|----------|----------------------|------|
| `previous_version_id` | `Optional[NonEmptyStr] = None` | `preference.py` 第 64 行 | 存在时须非空非纯空白（version=1 仍须 None，D3 §7.2 版本链不变量保持） | `CODE_VERIFIED` |
| `extracted_entities` | `Optional[List[str]] = None` | `preference.py` 第 65 行 | 裸 `str` 列表，未使用元素级统一约束 | `GAP`（范围决策点，见 §1.5） |

### 1.2 Knowledge 盘点

| 字段 | 类型（当前实现） | 引用行号 | TD-014 关闭条件对应 | 状态 |
|------|------------------|----------|----------------------|------|
| `content_ref` | `Optional[NonEmptyStr] = None` | `knowledge.py` 第 69 行 | 存在时须非空非纯空白（DEFERRED：存储形态待 D） | `CODE_VERIFIED` |
| `superseded_by_id` | `Optional[NonEmptyStr] = None` | `knowledge.py` 第 72 行 | 存在时须非空非纯空白（D3 §7.2 替代回溯） | `CODE_VERIFIED` |
| `extracted_entities` | `Optional[List[str]] = None` | `knowledge.py` 第 75 行 | 裸 `str` 列表，未使用元素级统一约束 | `GAP`（范围决策点，见 §1.5） |
| 13 个结构化字段（`conditions`/`evidence`/`steps`/`expected_result`/`problem`/`outcome`/`reproducible`/`template_body`/`parameters`/`priority`/`failure_reason`/`avoid_condition`/`alternative`） | `Optional[str] = None` | `knowledge.py` 第 82–106 行 | 内容承载字段，非 ID/Reference/Selector | `GAP`（范围声明：非本债对象，见 §1.5） |

### 1.3 Conflict 盘点

| 字段 | 类型（当前实现） | 引用行号 | TD-014 关闭条件对应 | 状态 |
|------|------------------|----------|----------------------|------|
| `involved_knowledge_ids` | `Optional[List[NonEmptyStr]] = None` | `conflict.py` 第 57 行 | 元素级复用 `NonEmptyStr`：空串/纯空白元素拒绝 | `CODE_VERIFIED` |
| `resolved_by` | `Optional[NonEmptyStr] = None` | `conflict.py` 第 61 行 | 存在时须非空非纯空白（D3 §5.4 消解执行方，禁止模型生成） | `CODE_VERIFIED` |
| `resolution_strategy` | `Optional[str] = None` | `conflict.py` 第 58 行 | 非 Reference/Selector（DEFERRED 未冻结枚举） | `GAP`（范围声明：非本债对象，见 §1.5） |

### 1.4 ForgetPlan 盘点

| 字段 | 类型（当前实现） | 引用行号 | TD-014 关闭条件对应 | 状态 |
|------|------------------|----------|----------------------|------|
| `resolved_target_ids` | `Optional[List[NonEmptyStr]] = None` | `forgetting.py` 第 65 行 | 元素级非空非纯空白（另由 `_resolved_target_consistency` 保证去重与计数一致，SEC-FORGET-01） | `CODE_VERIFIED` |
| `target_id` | `Optional[NonEmptyStr] = None` | `forgetting.py` 第 66 行 | 条件必填（single_item）；存在时非空非纯空白 | `CODE_VERIFIED` |
| `target_session_id` | `Optional[NonEmptyStr] = None` | `forgetting.py` 第 67 行 | 条件必填（session）；存在时非空非纯空白 | `CODE_VERIFIED` |
| `target_topic` | `Optional[NonEmptyStr] = None` | `forgetting.py` 第 68 行 | 条件必填（topic）；存在时非空非纯空白 | `CODE_VERIFIED` |
| `target_time_range` | `Optional[NonEmptyStr] = None` | `forgetting.py` 第 69 行 | 条件必填（time_window）；存在时非空非纯空白 | `CODE_VERIFIED` |
| `rollback_plan_id` | `Optional[NonEmptyStr] = None` | `forgetting.py` 第 72 行 | 存在时须非空非纯空白 | `CODE_VERIFIED` |

ForgetPlan 另有条件 selector 校验器：`_selectors_must_not_be_whitespace_only`（`forgetting.py` 第 74–88 行，覆盖 `target_selector`/`target_id`/`target_session_id`/`target_topic`/`target_time_range`，纯空白拒绝、原文本保留不 strip）与 `_resolved_ids_must_not_be_whitespace_only`（第 90–98 行，`resolved_target_ids` 元素级纯空白拒绝）。

### 1.5 盘点范围声明（GAP / 范围决策点，交 D 主审确认）

| 字段 | 位置 | 范围决策 | 说明 |
|------|------|----------|------|
| `extracted_entities`（Preference） | `preference.py` 第 65 行 | 尚未统一；判定为实体标签（内容性质，非 ID 列表）而未使用 `NonEmptyIdList` 元素约束 | 候选 GAP：若 D 主审认可其为内容字段则保持现状并记录；否则列入 TD-014 未完成项 |
| `extracted_entities`（Knowledge） | `knowledge.py` 第 75 行 | 同上 | 同上 |
| Knowledge 13 个结构化内容字段 | `knowledge.py` 第 82–106 行 | 判定为本债范围外：内容承载字段而非 ID/Reference/Selector，不受「存在时必须有效」引用语义约束 | 与 TD-017（结构化字段无损承载）正交，非本债对象 |
| `resolution_strategy`（Conflict） | `conflict.py` 第 58 行 | 判定为本债范围外：DEFERRED 未冻结枚举（策略集合与优先级待 B/E），非 Reference/Selector | 不纳入 TD-014 统一约束 |

**结论**：TD-014 关闭条件中的 ID/Reference/Selector 字段（`previous_version_id`/`content_ref`/`superseded_by_id`/`involved_knowledge_ids`/`resolved_by`/`resolved_target_ids`/`target_id`/`target_session_id`/`target_topic`/`target_time_range`/`rollback_plan_id`）已在当前分支统一为 `Optional[NonEmptyStr]` 或等价元素级约束并落地，标记 `CODE_VERIFIED`；范围决策点如实列为 `GAP`，不以「看起来合理」写入已统一。

---

## 2、测试定义层（TEST_DEFINED）

以下只陈述测试**定义**及其参数化输入与断言意图，**不包含任何运行结果数值、不虚构日志**。

### 2.1 TD-014 直接负向 / None 语义用例（`memory-service/tests/test_domain_models_d4e.py`）

- 文件头第 18–20 行声明 TD-014 覆盖范围：`previous_version_id`/`content_ref`/`superseded_by_id`/`rollback_plan_id`/`resolved_by` 存在时拒绝空串与纯空白；`involved_knowledge_ids` 元素级同规则；字段缺失（None）Optional 语义不变。

| 测试函数 | 定义行号 | 参数化输入 / 覆盖 | 断言意图 |
|----------|----------|-------------------|----------|
| `test_preference_optional_previous_version_id_rejects_blank` | 761–764（参数化 754–760） | `""`、`" \t "`（version=2 场景） | `previous_version_id` 存在时为空串/纯空白 → `ValidationError` |
| `test_knowledge_optional_reference_rejects_blank` | 774–777（参数化 767–773） | `content_ref=""`、`superseded_by_id=" "` | 存在时为空串/纯空白 → `ValidationError` |
| `test_conflict_involved_knowledge_ids_reject_blank_element` | 789–792（参数化 780–788） | `["", "kn_d4e_03"]`、`["  "]`、`["\t"]`、`[" \u3000"]` | `involved_knowledge_ids` 元素级空串/纯空白（含全角空格） → `ValidationError` |
| `test_conflict_resolved_by_rejects_whitespace_only` | 795–804 | `resolved_by=" "`（resolved_manual + resolved_at） | `resolved_by` 纯空白 → `ValidationError` |
| `test_forget_plan_rollback_plan_id_rejects_blank` | 814–817（参数化 807–813） | `""`、`"\n"` | `rollback_plan_id` 存在时为空串/纯空白 → `ValidationError` |
| `test_optional_id_reference_fields_missing_still_default_to_none` | 820–835 | 四模型全部 Optional ID/Reference 缺省构造（`previous_version_id`/`extracted_entities`/`content_ref`/`superseded_by_id`/`involved_knowledge_ids`/`resolved_by`/`rollback_plan_id`） | 缺省（None）Optional 语义保持不变 |
| `test_conflict_involved_knowledge_ids_accepts_non_blank_elements` | 838–841 | `["kn_d4e_03"]` | 合法非空元素构造成功且值保留 |

### 2.2 ForgetPlan selector 空白 / 跨模式用例（`test_domain_models_d4e.py`，TD-014/TD-015 结合部）

| 测试函数 | 定义行号 | 参数化输入 / 覆盖 | 断言意图 |
|----------|----------|-------------------|----------|
| `test_forget_plan_rejects_empty_matching_selector` | 448–458（参数化 439–447） | 四模式匹配 selector 传 `""`（`target_id`/`target_session_id`/`target_topic`/`target_time_range` 逐模式） | 空串不得绕过模式条件必填检查 |
| `test_forget_plan_rejects_whitespace_only_selectors_and_resolved_ids` | 469–472（参数化 461–468） | `target_selector=" \t "`、`target_id=" \n "`、`resolved_target_ids=["  "]`（affected_count=1） | selector 与解析 ID 不得以纯空白伪装为有效值 |
| `test_forget_plan_rejects_every_cross_mode_selector` | 521–534（参数化 512–520） | 每模式在匹配 selector 之外再携带一个模式外 selector | 任意额外 selector 一律拒绝（TD-015，selector 范围不可悄然扩展） |

### 2.3 跨轨兼容测试目标（`memory-service/tests/test_knowledge_domain_mapping_d8e.py`）

TD-014 关闭条件要求「Domain 与跨轨兼容测试定义/目标存在」。本文件为 Day8 E Candidate→Governance→Knowledge 映射链路（TD-017），覆盖 TD-014 收紧 `content_ref`/`superseded_by_id` 后既有构造与映射路径不回归的兼容性断言意图：

| 测试函数 | 定义行号 | 覆盖 | 断言意图 |
|----------|----------|------|----------|
| `test_d8e_six_knowledge_types_mapping` | 155–185 | 六类 KnowledgeType 经 `admit_with_event` 门禁映射 | 六类均有有值映射，`user_id` 只来自 ctx |
| `test_d8e_all_13_fields_preserved_together` | 313–335 | 13 个结构化字段同时非空 | 逐字段精确 `==` 保留、无改写 |
| `test_d8e_backward_compatible_no_structured_fields` | 361–368 | 不带结构化字段的既有 Candidate | 既有构造路径仍然可用，13 字段为 None |
| `test_d8e_structured_fields_default_none_in_domain` | 371–388 | Domain 层直接构造 Knowledge 不提供结构化字段 | 默认 None，向后兼容 |
| `test_d8e_knowledge_domain_extra_field_still_rejected` | 391–412 | 未声明字段 `unexpected_field` | `extra="forbid"` fail-closed 保持 |
| `test_d8e_core_fields_unchanged_with_structured` | 443–471 | 携带结构化字段时核心字段映射 | `content_summary` 非拼接、`source_event_id` 直接相等、`confidence_score` 数值不变、`memory_status` 恒 candidate |

测试纪律（`test_domain_models_d4e.py` 第 24–26 行、`test_knowledge_domain_mapping_d8e.py` 第 28–32 行）：不使用 Mock、skip、xfail 或弱化断言；测试数据仅使用合成用户 ID、合成事件 ID 与脱敏内容。

**结论**：TD-014 的负向用例定义（空串/纯空白/元素级/全角空格）、None 语义用例定义与跨轨兼容测试目标（`test_knowledge_domain_mapping_d8e.py`）均已存在并已提交，标记 `TEST_DEFINED`。本 Task 不新增、不修改任何测试，不产生任何运行数值。

---

## 3、L1 验证层（WSL_L1_VERIFIED）

本报告已取得当前 PR 分支上的真实 WSL L1 验证结果。验证在 WSL2 project `.venv` 中执行，不等同于银河麒麟宿主 Runtime 验证；因此仅标记 `WSL_L1_VERIFIED`，不标记 `HOST_VERIFIED`。

| Gate | 命令 / 状态 | 结果 |
|------|-------------|------|
| L1 | `python3 -m pytest -o pythonpath=memory-service memory-service/tests/test_domain_models_d4e.py memory-service/tests/test_knowledge_domain_mapping_d8e.py -q` | `132 passed in 0.42s`，exit code 0，`WSL_L1_VERIFIED` |
| L2/L3 | 无（`runtime_required=false`） | `RUNTIME_NOT_REQUIRED`；本报告不产生 `HOST_VERIFIED` |

---

## 4、Reviewer 关闭层（REVIEW_PENDING）

- **当前状态**：Closure Candidate / In Progress **pending D Reviewer**（周子腾，D 主审）。
- **未完成事项**：
  1. §1.5 三处范围决策点（`extracted_entities` 实体标签性质、Knowledge 13 个结构化内容字段、`resolution_strategy` DEFERRED 字段）需 D 主审对「不在 TD-014 统一约束范围内」的认定；
  2. D 主审尚未对关闭候选进行正式确认；
  3. 登记表状态推进到 `Resolved` 需要 D Reviewer 确认验收标准达成（`代码合并 ≠ 技术债关闭`，见登记表管理规则第 3 条）。
- **明确声明**：本报告**不标记 Resolved**，不虚构 Reviewer 签署，不把 WSL 测试描述为麒麟 Runtime 证据或 `HOST_VERIFIED`。

---

## 5、明确未完成 / 未验证事项

1. D Reviewer（周子腾）对 TD-014 关闭候选与 §1.5 范围决策点的正式确认尚未取得。
2. 本报告已取得 WSL L1 实际执行证据：`132 passed in 0.42s`、exit code 0。
3. 本报告不包含银河麒麟 Host Runtime 证据；`HOST_VERIFIED`、L2/L3 Runtime PASS 均未声明。

---

## 6、结论

TD-014 的代码能力、测试定义及定向 WSL L1 验证均已完成：Optional ID/Reference/Selector 字段已统一为 `Optional[NonEmptyStr]` 或等价元素级约束；相关回归于 2026-09-03 实际执行并取得 `132 passed in 0.42s`、exit code 0，状态为 `WSL_L1_VERIFIED`。当前业务流程上仅剩 §1.5 三处范围决策点确认与 D Reviewer 正式确认；登记表继续保持 `In Progress`（Closure Candidate pending D Reviewer），**不得直接标记 Resolved**。该验证不构成银河麒麟 `HOST_VERIFIED` 或 L2/L3 Runtime 证据。
## 最终 L1 验证结果（2026-09-03）

验证环境：

- 环境：WSL2 / project `.venv`
- 验证层级：`WSL_L1_VERIFIED`
- Runtime / Host：`NOT_HOST_VERIFIED`
- 本结果不构成银河麒麟 L2/L3 Runtime 证据

执行命令：

    python3 -m pytest \
      -o pythonpath=memory-service \
      memory-service/tests/test_domain_models_d4e.py \
      memory-service/tests/test_knowledge_domain_mapping_d8e.py \
      -q

实际结果：

    132 passed in 0.42s

结论：

- exit code：0
- TD-013 / TD-014 直接相关 Domain 与 Knowledge 映射回归全部通过；
- 无 failed；
- 无新增 skip；
- 该结果支持本技术债进入 `Closure Candidate / In Progress pending D Reviewer`；
- 是否最终标记 `Resolved` 仍需非作者 D Reviewer 正式确认。
