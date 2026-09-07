# TD-017 关闭候选审计报告（KnowledgeCandidate 六类结构化字段无损映射）

- **任务**：day12-e-07-knowledge-mapping-debt-closure-audit-v6（D12E TD-017 KnowledgeCandidate 无损映射关闭审计）
- **日期**：2026-09-03
- **分支**：`fix/e-d12-business-schema-drift-remediation`
- **当前 HEAD**：`d653392eaf3190ba3009e4d959ae6a857f2e2a5a`（工作区干净）
- **审计对象**：TD-017「KnowledgeCandidate 六类结构化字段未获 E Domain 无损承载」（`memory-service/domain/knowledge.py`、`memory-service/service/candidate_governance.py`、`memory-service/providers/extraction_provider.py`）
- **审计性质**：关闭候选审计（Closure Candidate），**非 Resolved 宣告**。本报告只陈述仓库中已落地并已提交的代码事实与测试定义，不预写本 Task 尚未执行的 L0/L1 结果，不虚构 Reviewer 签署。D 主审确认关闭四条件前，登记表状态保持 `In Progress`。

---

## 0、四层状态分离说明

本报告按以下四层分别陈述，各层互不替代：

| 层 | 状态标记 | 含义 |
|----|----------|------|
| 代码事实层 | `CODE_VERIFIED` | 实现已落地并已提交（HEAD `d653392e`），引用文件与行号可核对 |
| 测试定义层 | `TEST_DEFINED` | 测试用例已定义并已提交（同 HEAD），覆盖六类映射/逐字段无损/值不被改写/extra fail-closed 等断言；**只陈述定义存在，不写运行数值** |
| Controller Gate 层 | `GATE_PENDING` | 本 Task 的 L0/L1 验收命令由 Controller 在 Implementer 返回后独立执行，结果另行记录 |
| Reviewer 关闭层 | `REVIEW_PENDING` | D 主审（周子腾）尚未签署，状态为 In Progress（Closure Candidate pending D Reviewer），**不得标记 Resolved** |

---

## 1、代码事实层（CODE_VERIFIED）

涉及实现文件（均只读核验，本次不修改）：

| 文件 | 证据范围 |
|------|----------|
| `memory-service/providers/extraction_provider.py` | KnowledgeCandidate v0.2 六类结构化字段定义（第 168–201 行）、13 字段可选性常量（第 257–261 行） |
| `memory-service/service/candidate_governance.py` | `_build_knowledge` 1:1 同名直传（第 370–397 行）、事件门禁 `_validate_event_admission`（第 259–309 行） |
| `memory-service/domain/knowledge.py` | 13 个结构化承载字段声明（第 82–106 行）、`extra="forbid"`（第 52 行） |

### 1.1 六类 13 字段逐字段四要素核对

字段四要素：字段名 / 可选性 / 直传实现 / 测试定义。逐字段核对如下（候选定义列 = `extraction_provider.py`，Domain 定义列 = `knowledge.py`，直传实现列 = `candidate_governance.py`，测试定义列 = `test_knowledge_domain_mapping_d8e.py`）：

| 字段 | 所属类别 | Candidate 定义 | 可选性（两端一致） | Domain 定义 | 直传实现（1:1 同名无转换） | 测试定义 |
|------|----------|----------------|--------------------|-------------|---------------------------|----------|
| `conditions` | 通用 | extraction_provider.py:183 | `Optional[str] = None` | knowledge.py:82 | candidate_governance.py:384 | d8e:272–288（跨三类回归）、313–335（13 字段合体）、338–355（值不改写） |
| `evidence` | 通用（R3 可信来源） | extraction_provider.py:184 | `Optional[str] = None` | knowledge.py:84 | candidate_governance.py:385 | d8e:291–307（跨三类回归）、313–335、338–355 |
| `steps` | workflow | extraction_provider.py:191 | `Optional[str] = None` | knowledge.py:86 | candidate_governance.py:386 | d8e:191–203（workflow 正向）、313–335、338–355、443–471（核心字段不变量） |
| `expected_result` | workflow | extraction_provider.py:192 | `Optional[str] = None` | knowledge.py:88 | candidate_governance.py:387 | d8e:191–203 |
| `problem` | case | extraction_provider.py:193 | `Optional[str] = None` | knowledge.py:90 | candidate_governance.py:388 | d8e:206–220（case 正向） |
| `outcome` | case | extraction_provider.py:194 | `Optional[str] = None` | knowledge.py:92 | candidate_governance.py:389 | d8e:206–220 |
| `reproducible` | case | extraction_provider.py:195 | `Optional[str] = None` | knowledge.py:94 | candidate_governance.py:390 | d8e:206–220 |
| `template_body` | template | extraction_provider.py:196 | `Optional[str] = None` | knowledge.py:96 | candidate_governance.py:391 | d8e:223–235（template 正向）、338–355（含换行/特殊字符逐字节相等） |
| `parameters` | template | extraction_provider.py:197 | `Optional[str] = None` | knowledge.py:98 | candidate_governance.py:392 | d8e:223–235、338–355 |
| `priority` | constraint | extraction_provider.py:198 | `Optional[str] = None` | knowledge.py:100 | candidate_governance.py:393 | d8e:238–248（constraint 正向）、443–471 |
| `failure_reason` | failure_experience | extraction_provider.py:199 | `Optional[str] = None` | knowledge.py:102 | candidate_governance.py:394 | d8e:251–266（failure 正向）、418–437（FAILED 事件端到端） |
| `avoid_condition` | failure_experience | extraction_provider.py:200 | `Optional[str] = None` | knowledge.py:104 | candidate_governance.py:395 | d8e:251–266、418–437 |
| `alternative` | failure_experience | extraction_provider.py:201 | `Optional[str] = None` | knowledge.py:106 | candidate_governance.py:396 | d8e:251–266、418–437 |

逐字段核对结论：

- **字段名**：13 字段在 Candidate、Governance 直传、Domain 三处完全同名（无重命名、无驼峰/下划线改写）。
- **可选性**：Candidate 侧全部 `Optional[str] = None`（extraction_provider.py:183/184、191–201），Domain 侧全部 `Optional[str] = None`（knowledge.py:82–106），两端可选性一致。
- **直传实现**：`_build_knowledge` 第 384–396 行以 `字段名=candidate.字段名` 形式 1:1 同名直传，无转换、无拼接、无改写（对照 candidate_governance.py:362–368 docstring 契约声明）。
- **测试定义**：`test_knowledge_domain_mapping_d8e.py` 提供逐类正向（第 191/206/223/238/251 行）、通用字段独立回归（第 272/291 行）、13 字段合体无损（第 313 行）、值不被改写含空格/换行/特殊字符逐字节相等（第 338 行）、向后兼容 None（第 361/371 行）、FAILED 事件 + failure_experience 端到端（第 418 行）全覆盖。

结论：13 个结构化字段的字段名、可选性、直传实现、测试定义四要素均已定位到行级证据，标记 `CODE_VERIFIED`（实现侧）与 `TEST_DEFINED`（测试侧）。

### 1.2 结构不变量审计（不重复实现已正确功能）

| 不变量 | 实现事实 | 引用 |
|--------|----------|------|
| 六类均有映射覆盖 | `knowledge_type=KnowledgeType(candidate.category)` 六值同源；测试 `test_d8e_six_knowledge_types_mapping`（d8e:155、185 行 `len(cases) == 6`）逐类断言 knowledge_type 映射且 user_id 只来自 ctx | candidate_governance.py:373；d8e:155–185 |
| `content_summary` 仍只承载 fact | `content_summary=candidate.fact`（直接赋值，非拼接、非拼接结构化字段伪装）；测试第 464 行 `result.content_summary == fact_text` 精确等于 fact | candidate_governance.py:377；d8e:464 |
| `source_event_id` 直接相等（真值来源不破坏） | `source_event_id=candidate.source_event_id` 直接相等；事件门禁 `_validate_event_admission` 第 259–263 行校验 `candidate.source_event_id == event.event_id`，不匹配拒绝 `source_event_id_mismatch`；测试第 465 行直接相等断言 | candidate_governance.py:376、259–263；d8e:465 |
| `user_id` 只来自 ctx | `user_id=ctx.user_id`（可信归属）；门禁第 264–268 行校验 `ctx.user_id == event.user_id`，不匹配拒绝 `user_id_mismatch`；测试第 466 行与第 183 行断言 | candidate_governance.py:372、264–268；d8e:466、183 |
| `memory_status` 恒 candidate | `memory_status=MemoryStatus.CANDIDATE`；测试第 468 行断言 | candidate_governance.py:375；d8e:468 |
| `confidence_score` 数值不变 | `confidence_score=candidate.confidence`（数值含义不变）；测试第 467 行 `confidence_score == 0.42` 断言 | candidate_governance.py:378；d8e:467 |
| `extra="forbid"` fail-closed 保持 | knowledge.py:52 `model_config = ConfigDict(extra="forbid")`（注：其一在 KnowledgeCandidate，其一在 Domain）；13 字段为已声明字段而非静默放行；测试第 391–412 行 `unexpected_field` 仍触发 `ValidationError` | knowledge.py:52、extraction_provider.py:179；d8e:391–412 |
| failed 事件语义 | 门禁第 294–309 行：failed 事件仅放行 failure_experience 类别（`failed_event_success_knowledge_forbidden`），其余 Knowledge 与 Preference 一律拒绝；测试第 418–437 行 FAILED 事件 + failure_experience 端到端 | candidate_governance.py:294–309；d8e:418–437 |

**结论**：未发现字段重命名、值拼接、静默丢失或 provenance 边界破坏的实现证据；`content_summary` 仍只承载 fact，`source_event_id`/`user_id` 门禁与真值来源未被绕过。候选与 Domain 的 `extra="forbid"` 均保持，13 字段为已声明字段。

### 1.3 额外代码事实

- `_KNOWLEDGE_OPTIONAL_STR_FIELDS`（extraction_provider.py:257–261，tuple 在 258–260 行）以 13 字段全表常量为知识可选字符串字段降级路径服务，与 Domain 承载字段同名，不引入第三套命名。
- 13 字段契约声明：KnowledgeCandidate v0.2 docstring（extraction_provider.py:168–177）与 Knowledge `_structured_payload` 注释（knowledge.py:77–81）明确「全可选、向后兼容、1:1 直接映射、无转换、无改写」。

---

## 2、测试定义层（TEST_DEFINED）

测试文件：`memory-service/tests/test_knowledge_domain_mapping_d8e.py`（471 行，只陈述定义，不包含运行结果数值）。

| 测试函数 | 行号 | 覆盖 | 断言意图 |
|----------|------|------|----------|
| `test_d8e_six_knowledge_types_mapping` | 155–185 | 六类（fact/workflow/case/template/constraint/failure_experience）逐类映射 | `knowledge_type is KnowledgeType(category)`、`user_id == ctx_user`、`len(cases) == 6`；failure_experience 走 FAILED 事件真实语义路径 |
| `test_d8e_workflow_steps_expected_result_preserved` | 191–203 | workflow | `steps` / `expected_result` 正向无损保留 |
| `test_d8e_case_problem_outcome_reproducible_preserved` | 206–220 | case | `problem` / `outcome` / `reproducible` 正向无损保留 |
| `test_d8e_template_body_parameters_preserved` | 223–235 | template | `template_body` / `parameters` 正向无损保留 |
| `test_d8e_constraint_priority_preserved` | 238–248 | constraint | `priority` 正向无损保留 |
| `test_d8e_failure_experience_fields_preserved` | 251–266 | failure_experience（FAILED 事件） | `failure_reason` / `avoid_condition` / `alternative` 正向无损保留 |
| `test_d8e_common_conditions_preserved` | 272–288 | conditions 跨三类 | 通用字段独立回归，跨类别无损 |
| `test_d8e_common_evidence_preserved` | 291–307 | evidence 跨三类 | 通用字段独立回归（R3 系统可信来源承载） |
| `test_d8e_all_13_fields_preserved_together` | 313–335 | 13 字段合体 | 全部非空时逐字段 `getattr(result, field) == structured[field]` |
| `test_d8e_fields_not_rewritten` | 338–355 | 值不被改写 | 前导/尾随空格、特殊符号（`$ @ #`、`{{T}}`、`<-`/`->`）、换行、中文逐字节完全相等，非截断/非修剪/非拼接 |
| `test_d8e_backward_compatible_no_structured_fields` | 361–368 | 兼容旧候选 | 不携带结构化字段时 13 字段均为 None |
| `test_d8e_structured_fields_default_none_in_domain` | 371–388 | Domain 构造兼容 | 直接构造 Knowledge 不提供结构化字段时均为 None |
| `test_d8e_knowledge_domain_extra_field_still_rejected` | 391–412 | extra="forbid" 保持 | 未声明 `unexpected_field` 仍触发 `ValidationError`（13 字段为已声明字段，非静默放行） |
| `test_d8e_failure_experience_with_failed_event_admission` | 418–437 | FAILED 事件端到端 | 门禁通过且 failure 三字段无损保留 |
| `test_d8e_core_fields_unchanged_with_structured` | 443–471 | 核心字段不变量 | `content_summary == fact`（非拼接，464 行）、`source_event_id == event_id`（直接相等，465 行）、`user_id == USER`（466 行）、`confidence_score == 0.42`（467 行）、`memory_status is MemoryStatus.CANDIDATE`（468 行）、结构化字段仍无损（470–471 行） |

治理入口回归：`memory-service/tests/test_candidate_governance_d5e.py`（540 行）为候选→Domain 业务治理单元测试，全部经公开 `admit_with_event()` 入口（PR #47 High 旁路关闭），文件头第 16–21 行声明覆盖正向 Knowledge 的 `source_event_id` 直接相等、`user_id` 来自 ctx、confidence 数值不变、六值 category 映射。

测试纪律（d8e 文件头第 21–24 行、d5e 文件头第 28–32 行）：不使用 Mock、skip、xfail 或弱化断言；测试数据仅使用合成用户 ID、合成事件 ID 与脱敏内容；`model_construct` 只用于防御守卫验证。

**结论**：六类映射、13 字段逐字段无损、值不被改写、向后兼容、extra fail-closed、FAILED 事件语义与核心字段不变量的测试定义均已提交，标记 `TEST_DEFINED`。本 Task 不新增、不修改任何测试。

---

## 3、Controller Gate 层（GATE_PENDING）

本 Task 的验收命令由 Controller 在 Implementer 返回后**独立执行**，结果按 `.local-agent-workflow/rules/runtime-validation.md` 证据规则另行记录并归档。本报告**不声称执行结果、不预写 PASS 数值**。

| Gate | 命令 | 说明 |
|------|------|------|
| L0 | `python3 -m pytest --version` | pytest 可达性冒烟 |
| L1 | `python3 -m pytest -o pythonpath=memory-service memory-service/tests/test_knowledge_domain_mapping_d8e.py -q` | TD-017 六类 13 字段无损承载主测试 |
| L1 | `python3 -m pytest -o pythonpath=memory-service memory-service/tests/test_candidate_governance_d5e.py -q` | 治理入口回归（admit_with_event 语义不变） |
| L2/L3 | 无（`runtime_required=false`，`runtime_commands=[]`） | 不适用；本 Task 为 docs 审计 + L0/L1 静态与组件验证，无银河麒麟系统能力依赖，不产生也不虚构任何 Runtime 证据（`RUNTIME_NOT_REQUIRED`） |

---

## 4、Reviewer 关闭层（REVIEW_PENDING）

- **当前状态**：In Progress（Closure Candidate pending D Reviewer）（周子腾，D 主审）。
- **D Reviewer 关闭四条件**（TD-017 登记表第 93 行既有关闭前提，本审计不代行确认）：
  1. 正式承载契约成立（六类结构化字段在 E Domain 有已声明承载字段）；
  2. workflow / case / template / failure_experience 等 13 字段逐项无损（本 §1.1 提供逐字段四要素证据供核对）；
  3. `content_summary` 未被用于伪装结构化承载（§1.2 提供 `content_summary=candidate.fact` 与测试 464 行证据）；
  4. provenance 边界未被破坏（section 1.2 提供 `source_event_id` 直接相等、`user_id` 仅来自 ctx、事件门禁 mismatch 拒绝证据）。
- **未完成事项**：
  1. 本 Task 的 L0/L1 验收 Gate 尚未由 Controller 执行（结果未产生）；
  2. D 主审尚未对关闭候选进行正式确认；
  3. 登记表状态推进到 `Resolved` 需要 D Reviewer 确认验收标准达成（`代码合并 ≠ 技术债关闭`，见登记表管理规则第 3 条）。
- **明确声明**：本报告**不标记 Resolved**，不虚构 Reviewer 签署，不把测试定义描述为已执行 PASS，不把 WSL 静态检查描述为 Runtime 证据。

---

## 5、交叉引用（TD-014 并行审计）

`docs/day12/11_d12e_td014_optional_reference_closure_audit_20260903.md` 第 47 行与第 76 行对同字段集（`knowledge.py` 第 82–106 行 13 个结构化内容字段）存在范围决策 `GAP` 标注：TD-014 判定这些字段为「内容承载字段而非 ID/Reference/Selector，不受『存在时必须有效』引用语义约束」，属 TD-014 债对象范围外，与 TD-017（结构化字段无损承载）正交。

两审计并行、由同一 D 主审确认，不互相覆盖、不互相替代：TD-014 的 GAP 确认不解除 TD-017 的关闭四条件，TD-017 的关闭也不豁免 TD-014 对其余 Optional 字段的约束统一要求。

---

## 6、缺口与后续 Task

本审计范围内未发现真实缺口：

- 13 字段字段名、可选性、直传实现、测试定义四要素均有行级证据；
- 未发现字段重命名、值拼接、静默丢失；
- `content_summary` 仍只承载 fact，未伪装结构化承载；
- `source_event_id` 与 provenance 边界未被破坏（门禁 mismatch 拒绝保留）。

若后续实施（Controller Gate 执行或 D Reviewer 核对）中发现真实缺口，将如实记录为后续 memory-service 原子 Task（由对应轨道实施修复），本次 docs 任务不越轨修改 `memory-service/`。

---

## 7、明确未完成 / 未验证事项

1. 本 Task 的 L0/L1 命令尚未执行（由 Controller 在 Implementer 返回后独立执行并记录结果）。
2. D Reviewer（周子腾）对 TD-017 关闭候选的正式确认尚未取得（四条件核对）。
3. 本审计行级证据对应当前 HEAD `d653392e`；后续提交若改动上述文件行号，证据需按审计时点核对。
4. 本报告不包含任何 Runtime 证据（`RUNTIME_NOT_REQUIRED`），也不包含任何虚构的测试运行数值或日志。

---

## 8、结论

TD-017 的**代码事实与测试定义**已在当前分支落地并提交（HEAD `d653392e`，工作区干净），六类 13 个结构化字段在 E Domain 的 1:1 同名无损承载具备逐行证据：无重命名、无拼接、无静默丢失，`content_summary` 仅承载 fact，`source_event_id`/`user_id` provenance 边界未被破坏，`extra="forbid"` fail-closed 保持。技术条件已具备**关闭候选**审计结论；业务流程上剩余 Controller Gate 执行与 D Reviewer 四条件正式确认。登记表状态更新为 `In Progress（Closure Candidate pending D Reviewer）`，**不得直接标记 Resolved**。