# [PR #58 / Day7E] 偏好长期化业务策略 + 版本变更规划 + 跨链路回归 + C/D 验收规范候选

> 本文件是 **PR #58（Day7E）** 的独立 PR 描述。Day7E 为 E 轨业务策略层交付，建立在 D7-A 偏好抽取（PR #36，见 `docs/day7/02_pr_description.md`）之上，**不覆盖** PR #36 旧描述。
>
> 本文档由 Reviewer 按本任务 `acceptance_criteria` 逐条人工核对。

## 元信息

- **PR**：#58
- **标识**：Day7E
- **责任轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer**：D（周子腾）主审
- **runtime_required**：false

## 背景与目标

Day7E 在 Day7A 偏好抽取（PR #36）之上，交付 **E 轨业务策略层**：明确哪些偏好候选可以长期化（D7E-01）、进入长期记忆后如何规划版本变更（/ 共存 / 更新 / 防膨胀 / 回滚）（D7E-02），并用跨链路回归证明 E 轨策略不绕过上游 Day5 Candidate Governance 与 Day6 Source Admission 安全门禁（D7E-03）；同时形成对 C 轨偏好 UI 与 D 轨版本持久化的业务验收规范候选。

本 PR 交付的是**长期化业务策略、版本业务规划、回归测试与验收规范候选**，不实现 C 轨 QML、不实现 D 轨版本持久化、不产生 L3 发布候选。

## E 轨交付范围（已完成，不越界）

E 轨业务核心为以下交付物，其共同边界是：**一律不写数据库、不修改 `current_version` 指针、不实现 Repository / UoW / Migration / Outbox / 真实事务，不实现 C 轨 UI**。

1. **D7E-01 长期化业务决策策略**（`memory-service/service/preference_business_policy.py`）
   - 基于结构化字段判定偏好候选是否可作为长期偏好候选（memory_status=candidate，非 active）保留；
   - 输出 `should_store` / `requires_confirmation` / `reason_code`；
   - 临时边界（`temporary_not_persistent` / `should_persist_false`）、implicit 不跳过确认、confidence 无硬编码晋升阈值（0.7/0.8/0.9 等），不把高 confidence 候选自动升级为 active。

2. **D7E-02 版本变更规划策略**（`memory-service/service/preference_version_policy.py`）
   - 规划 CREATE / COEXIST / UPDATE / NO_OP / ROLLBACK 五种**纯业务**版本动作 + REJECTED 防御态；
   - 模块头明确「一律不写数据库、不修改 current_version 指针」，输出仅为业务计划。

3. **D7E-03 跨链路回归测试**（`memory-service/tests/test_preference_business_flow_d7e.py`）
   - 跨 Day5 / Day6 / Day7A / Day7E 链路回归，证明 E 轨策略不绕过 Day5 CandidateGovernance 与 Day6 SourceAdmission 门禁。

4. **验收规范候选**（`docs/day7/day7-e-ui-version-acceptance-v1.md`，状态 `PENDING_INTEGRATION`）
   - E 轨单方面提出的、关于 C 轨偏好 UI 与 D 轨版本持久化的**用户可观察行为验收标准**候选；
   - 不代表 C/D 已实现或已通过验收。

## 本轮 PR #58 审查问题修复收敛

PR #58 正式审查提出 #1、#2、#3 三个问题；#1 与 #2 已通过代码 + 测试收敛（见下），#3（缺少独立 PR 描述）即本文档。

### 问题 #1：scope fail-closed

- **修复**：`PreferenceVersionIntent.scope` 直接复用 `PreferenceScope` 枚举（`preference_version_policy.py:136`），**非第二套 scope 字符串常量**；非法 / 空 scope 在构造阶段即被 Pydantic 拒绝（fail-closed），不进入业务规划。
- **测试**：`test_invalid_scope_rejected_at_construction`、`test_empty_scope_rejected_at_construction`、`test_intent_scope_reuses_preference_scope_enum`（`test_preference_version_policy_d7e.py`）。

### 问题 #2：default_factory

- **修复**：`PreferenceVersionPlan.coexist_with_scopes` 使用 `Field(default_factory=list)`（`preference_version_policy.py:169`），两个默认实例的列表互相独立，无共享可变默认值。
- **测试**：`test_coexist_with_scopes_default_independent_instances`（`test_preference_version_policy_d7e.py`）。

### 复审追加收敛（TD-022 / TD-023）

PR #58 复审进一步识别并收敛两项 **Medium** 问题，分别登记为 TD-022 与 TD-023（均 In Progress，等待非作者 Reviewer 最终确认后关闭）：

- **跨用户 Rollback 拒绝载荷（TD-022，commit `0344955`）**：跨用户 Rollback 拒绝时载荷不回显他人 `key`/`scope`。`0344955` 将跨用户拒绝的 `preference_key`/`scope` 置空（`_reject(REASON_REJECTED_CROSS_USER, intent.user_id, "", "")`），5 个负向泄露测试覆盖：`test_rollback_cross_user_rejected_key_scope_empty`、`test_rollback_cross_user_rejected_no_target_leak_in_dump`、`test_rollback_cross_user_via_collection_key_scope_empty`、`test_rollback_non_cross_user_rejections_still_echo_key_scope`、`test_rollback_valid_history_unchanged_after_cross_user_fix`。
- **monotonic version（TD-023，commit `ccc8664`）**：rollback 后 UPDATE 版本号按同 `user_id + preference_key + scope` 链内全部现存记录（含历史 SUPERSEDED）的 `max(version)+1` 分配，不复用历史版本号（`_find_max_version_in_chain` + `_update`）；7 个 monotonic version 测试覆盖：`test_update_after_rollback_uses_chain_max_version`、`test_update_version_isolated_across_keys`、`test_update_version_isolated_across_scopes`、`test_update_version_isolated_across_users`、`test_update_chain_max_includes_all_memory_statuses`、`test_update_after_rollback_no_side_effects`、`test_update_after_rollback_deterministic`，含 v1 active + v2/v3 历史后 UPDATE=4。
- **identity 门禁（`18818a8`）**：版本意图与 decision identity 一致性门禁收敛，非 Medium 修复，不对应独立 TD，归入 TD-024 治理同步范围。

### 技术债登记

- **TD-024**（PR #58 审查状态与 TD 登记同步治理）= `Technical Debt` / `Low` / **`In Progress`**，详见 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`。
- **责任人**：E 轨成员；**Reviewer**：D 主审；**关联 PR**：#58。
- **验收标准摘要**：保留原 Reviewer 正式审查正文与时点事实（首次 100 passed），仅追加收敛补记，不篡改历史正文；补记明确 `b883516` 已收敛原审查问题 #1（scope fail-closed）/ #2（default_factory / identity Low）；正确 TD 编号归因（PR #58 正式登记为 TD-022/023/024，纠正 Day7 文档误占的 TD-018/019/020）；正确 commit 归因（`18818a8`=版本意图与 decision identity 一致性门禁，`0344955`=TD-022，`ccc8664`=TD-023）；区分首次 100 passed、收敛 104 passed、独立复测 109/305 passed 与 Reviewer 在 HEAD `b9d5abe` 复核的 51/121/317 passed（不同时点，互不覆盖）；本轮 identity Low 已修但待非作者 Reviewer 复核；C/D/L2/L3 状态保持 `PENDING_INTEGRATION` / `RUNTIME_UNVERIFIED`，不虚报；Acceptance Spec 不冻结；最终由非作者 Reviewer 确认后标记 `Resolved`。
- **当前状态**：`In Progress`，等待非作者 Reviewer 最终确认后关闭。
- **TD-022**（跨用户 Rollback 拒绝载荷回显他人 key/scope，commit `0344955`）= `Technical Debt` / `Medium` / **`In Progress`**，详见 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`。**责任人**：E 轨成员；**Reviewer**：D 主审；**关联 PR**：#58。**摘要**：跨用户 REJECTED 时 key/scope 清空（不回显 target 用户数据）+ 5 个负向泄露测试全部通过 + 非作者 Reviewer 确认后关闭。
- **TD-023**（rollback 后 UPDATE 版本号可能与历史冲突，commit `ccc8664`）= `Technical Debt` / `Medium` / **`In Progress`**，详见 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`。**责任人**：E 轨成员；**Reviewer**：D 主审；**关联 PR**：#58。**摘要**：同 user_id + preference_key + scope 链 max(existing version)+1 + v1 active/v2v3 历史后 UPDATE=4 隔离测试通过 + 非作者 Reviewer 确认后关闭。

## 明确不修改范围

- **不覆盖** `docs/day7/02_pr_description.md`（PR #36 D7-A 描述，保持原样）。
- 不修改任何生产代码与测试代码。
- 不修改 `.local-agent-workflow/`。
- 不执行 Push、创建 PR 或合并。

## C 轨 QML 状态：PENDING_INTEGRATION / RUNTIME_UNVERIFIED

C 轨 QML 偏好 UI **尚未实现**：

- `memory-client/README.md`：「**仅建立目录和职责边界，尚无生产实现。**」
- 仓库无 `.qml` 生产文件。
- 偏好 UI（历史列表展示、修改交互、回滚交互）由 C 轨实现并证明。

本 PR **未虚报** C 轨 QML 状态，保持 `PENDING_INTEGRATION` / `RUNTIME_UNVERIFIED`。

## D 轨版本持久化状态：PENDING_INTEGRATION / RUNTIME_UNVERIFIED

D 轨版本持久化 **尚未实现**：

- `preference_version_policy.py` 模块头：「一律不写数据库、不修改 current_version 指针、不实现 Repository / UoW / Migration / Outbox。」
- `day7-e-ui-version-acceptance-v1.md` S-05（D4 需求）：`memory_entries` 含 `version` 乐观锁字段但**无 `current_version` 指针**。
- `current_version` / `previous_version_id` / 版本链的持久化与事务正确性由 **D 轨**实现和证明。

本 PR **未虚报** D 轨版本持久化状态，**不声称 `current_version`、`previous_version_id` 或版本链已实现**。

## L2 / L3 状态

- 本任务 `runtime_required=false`，`runtime_commands` 为空，**不包含任何银河麒麟 Runtime Test**。
- L3 发布候选**不存在**（`day7-e-ui-version-acceptance-v1.md` 及 `04_final_checklist.md` 均标注「L3 不适用」）。
- C 轨 QML 与 D 轨版本持久化的真实 Runtime 验收须由 C/D 轨在银河麒麟 VM 中实际执行后另行验证，当前一律 `RUNTIME_UNVERIFIED`。

本 PR **未虚报** L3 状态，**不声称 L3 发布候选已存在**。

## Acceptance Spec 不可冻结

`docs/day7/day7-e-ui-version-acceptance-v1.md` 状态为 `PENDING_INTEGRATION`，其文件内全部 C/D 验收案例证据状态为 `RUNTIME_UNVERIFIED`。

**在 C 轨 QML 与 D 轨版本持久化分别在银河麒麟 VM 中完成 L2/L3 真实执行并提供真实证据之前，本验收规范候选不得冻结为团队基线。**

## L0 / L1 测试命令与通过判据

> 本任务为**纯文档修改**，不触碰任何生产/测试代码，以下 L0/L1 仅作为「文档任务不破坏既有 E 轨代码」的回归证据，不冒充 C 轨 UI 或 D 轨版本持久化的 Runtime 验收。
>
> **已记录的 L1 时点**：HEAD `85f7754` 独立复测 109 passed（三 D7E 文件）与跨阶段 305 passed，均为 **L1 非 Runtime 证据**（详见 `docs/day7/day7-e-l2l3-review-result.md` §6.2）。本任务 Reviewer 在 HEAD `b9d5abe` 复核确认：`test_preference_version_policy_d7e.py` **51 passed**、三 D7E 文件全量 **121 passed**、跨阶段 **317 passed**（退出码 0），为独立新时点，不覆盖前述 109/305 记录；全部为 **L1 非 Runtime 证据**。

### L0

```bash
python3 -m pytest memory-service/tests/test_preference_version_policy_d7e.py -q
# 通过判据：退出码 0（D7E-02 版本策略，含 PR #58 审查问题 #1/#2 测试）
```

### L1

```bash
python3 -m pytest memory-service/tests/test_preference_business_policy_d7e.py memory-service/tests/test_preference_version_policy_d7e.py memory-service/tests/test_preference_business_flow_d7e.py -q
# 通过判据：退出码 0（D7E 三测试文件全量回归）
```

## 安全与假实现审查声明

- 无密钥、VM 密码或真实用户数据。
- 无 Mock 冒充 Runtime Test：E 轨交付物为纯业务策略与回归测试，C 轨 UI 与 D 轨版本持久化保持 `PENDING_INTEGRATION` / `RUNTIME_UNVERIFIED`，未以静态代码或文档存在冒充真实交互 / 持久化 / Runtime 验收。

## 已知限制

- C 轨 QML 偏好 UI 未实现，D 轨版本持久化未实现，均需对应轨道在银河麒麟 VM 中提供真实证据。
- Acceptance Spec 为 E 轨单方面提出的验收规范候选，冻结前须经非作者 D Reviewer 批准且 PR 合并。
- 无 D7E 专属 L2 Runtime 执行日志。已记录 L1 passed 时点（HEAD `85f7754` 独立复测 109 passed、跨阶段 305 passed，以及本任务 Reviewer 在 HEAD `b9d5abe` 复核 51/121/317 passed），全部为 **L1 非 Runtime 证据**，不以静态检查 / L1 pytest 冒充真实宿主验收。

## 回滚方式

删除 `docs/day7/05_pr58_day7e_description.md` 即可恢复原状。纯新增文档，无代码 / 配置 / 数据库变更，回滚无副作用。

---

**Reviewer 结论**（由 Reviewer 按 acceptance_criteria 人工核对后填写）：

- [ ] APPROVE
- [ ] REQUEST_CHANGES

**Evidence Reviewer 结论**：

- [ ] EVIDENCE_APPROVED
- [ ] EVIDENCE_REQUIRES_CHANGES
