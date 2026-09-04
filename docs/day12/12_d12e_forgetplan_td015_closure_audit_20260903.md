# TD-015 关闭候选审计报告（ForgetPlan forget_mode 与模式外 target 字段互斥）

- **任务**：day12-e-06-forgetplan-debt-closure-audit-v6（D12E TD-015 关闭候选事实审计回写）
- **日期**：2026-09-03
- **分支**：`fix/e-d12-business-schema-drift-remediation`
- **当前 HEAD**：`20fd30917c4c692c768f0442623d4c5545ef95b8`（工作区干净）
- **审计对象**：TD-015「ForgetPlan 未强制 forget_mode 与模式外 target 字段互斥」（`memory-service/domain/forgetting.py`）
- **审计性质**：关闭候选审计（Closure Candidate），**非 Resolved 宣告**。本报告只陈述仓库中已落地并已提交的代码事实与测试定义，不预写本 Task 尚未执行的 L0/L1 结果，不虚构 Runtime 证据或 Reviewer 签署。

---

## 0、四层状态分离说明

本报告按以下四层分别陈述，各层互不替代；另设 `GAP` 分类承载审计中判定为「尚未闭合」或「明确判定为本债范围外」的事项：

| 层 | 状态标记 | 含义 |
|----|----------|------|
| 代码事实层 | `CODE_VERIFIED` | forget_mode 与 selector 互斥逻辑已在当前分支落地，引用文件与行号可核对 |
| 测试定义层 | `TEST_DEFINED` | 对应正向/负向测试用例已定义并已提交；**只陈述定义存在与断言意图，不写运行数值** |
| Controller Gate 层 | `GATE_PENDING` | 本 Task 的 L0/L1 验收命令由 Controller 在 Implementer 返回后独立执行，结果另行记录 |
| Reviewer 关闭层 | `REVIEW_PENDING` | D 主审（周子腾）尚未签署，状态为 Closure Candidate / In Progress pending D Reviewer，**不得标记 Resolved** |
| 未闭合层 | `GAP` | 审计中确认尚未闭合的事项（真实遗忘执行未接线），登记 HANDOFF，由 D 轨后续处理 |

---

## 1、代码事实层（CODE_VERIFIED）

实现文件（当前分支 HEAD，审计时点锁定）：

- `memory-service/domain/forgetting.py`：
  - 第 35–41 行：`_MODE_SELECTOR_FIELDS` 定义四种模式的专属 selector 字段映射——`SINGLE_ITEM→target_id`、`SESSION→target_session_id`、`TOPIC→target_topic`、`TIME_WINDOW→target_time_range`；第 41 行 `_SELECTOR_FIELDS` 冻结全部 selector 字段集合。
  - 第 100–125 行：`_mode_conditional` 模式互斥校验器（`model_validator(mode="after")`）：
    - 第 103 行：`required_field = _MODE_SELECTOR_FIELDS.get(self.forget_mode)`（full_reset 无映射 → `None`）；
    - 第 104–108 行：`supplied_fields` 收集当前实例中所有非 None 的 selector 字段；
    - 第 109–116 行：`required_field is None`（即 full_reset）时，任何已提供 selector 均触发 `ValueError("forget_mode=full_reset forbids concrete target selectors (TD-015)")`；
    - 第 117–120 行：有专属 selector 的模式缺失其 `required_field` 时触发缺失错误（D3 §5.5 / SEC-FORGET-03）；
    - 第 121–124 行：`supplied_fields != {required_field}`（携带任一模式外 selector）时触发 `ValueError("forget_mode only permits its matching target selector (TD-015)")`。
  - 第 74–88 行 `_selectors_must_not_be_whitespace_only` 与第 90–98 行 `_resolved_ids_must_not_be_whitespace_only`：selector 与解析 ID 不得以空串/纯空白绕过校验（TD-014 结合部，非 TD-015 主体）。

### 1.1 四模式专属 selector 互斥核验

| forget_mode | 专属 selector（required_field） | 实现事实（forgetting.py） | 状态 |
|-------------|--------------------------------|---------------------------|------|
| `single_item` | `target_id` | 第 36 行映射 + 第 117–124 行（必填且仅允许） | `CODE_VERIFIED` |
| `session` | `target_session_id` | 第 37 行映射 + 第 117–124 行（必填且仅允许） | `CODE_VERIFIED` |
| `topic` | `target_topic` | 第 38 行映射 + 第 117–124 行（必填且仅允许） | `CODE_VERIFIED` |
| `time_window` | `target_time_range` | 第 39 行映射 + 第 117–124 行（必填且仅允许） | `CODE_VERIFIED` |

### 1.2 full_reset 禁止具体 selector 核验

| 校验事实 | 实现位置（forgetting.py） | 状态 |
|----------|---------------------------|------|
| full_reset（`required_field is None`）时任何已提供 selector 一律拒绝（TD-015 消息） | 第 109–116 行 | `CODE_VERIFIED` |
| 全部四种 selector 字段（`target_id`/`target_session_id`/`target_topic`/`target_time_range`）均被 `_SELECTOR_FIELDS` 覆盖，无遗漏字段可绕行 | 第 41 行 + 第 104–108 行 | `CODE_VERIFIED` |
| 空串/纯空白 selector 不得绕过校验 | 第 74–88 行 | `CODE_VERIFIED` |

### 1.3 Preview/Execute 一致 selector 语义核验

| 复用/关停点 | 实现位置 | 状态 |
|-------------|----------|------|
| `forget.preview` 复用 ForgetPlan Domain 互斥校验（构造 `ForgetPlan` 前收集 conditional selector，构造失败抛 `RequestValidationError`） | `memory-service/gateway/forget_handlers.py` 第 76–99 行 | `CODE_VERIFIED` |
| Execute 侧运行时 fail-closed：`topic`/`time_window`/`full_reset` 未闭环前一律拒绝（`UnsupportedForgetScopeError`），不自动降级软删后报成功 | `memory-service/db/uow.py` 第 225–245 行（第 238–241 行三个模式） | `CODE_VERIFIED` |

---

## 2、测试定义层（TEST_DEFINED）

以下只陈述测试**定义**及其参数化输入与断言意图，**不包含任何运行结果数值、不虚构日志**。目标文件 `memory-service/tests/test_domain_models_d4e.py`（第 24–26 行测试纪律：不使用 Mock、skip、xfail 或弱化断言）；`memory-service/tests/test_forget_persistence_d10d.py`。

### 2.1 四模式专属 selector 正向 / 缺失 / 空值（`test_domain_models_d4e.py`）

| 测试函数 | 定义行号 | 参数化输入 / 覆盖 | 断言意图 |
|----------|----------|-------------------|----------|
| `test_forget_plan_valid_construction` | 192–195 | 默认 base（single_item + target_id） | 合法构造成功 |
| `test_forget_plan_accepts_only_its_matching_selector` | 490–509（参数化 481–489） | 四模式分别携带各自专属 selector（single_item/session/topic/time_window） | 每模式只接受自己模式的 selector，构造成功 |
| `test_forget_plan_single_item_missing_target_rejected` | 434–436 | single_item 缺 `target_id` | 缺专属 selector → `ValidationError` |
| `test_forget_plan_session_missing_target_rejected` | 609–615 | session 缺 `target_session_id` | 缺专属 selector → `ValidationError` |
| `test_forget_plan_topic_missing_target_rejected` | 618–624 | topic 缺 `target_topic` | 缺专属 selector → `ValidationError` |
| `test_forget_plan_time_window_missing_target_rejected` | 627–635 | time_window 缺 `target_time_range` | 缺专属 selector → `ValidationError` |
| `test_forget_plan_rejects_empty_matching_selector` | 448–458（参数化 439–447） | 四模式匹配 selector 传空串 `""` | 空串不得绕过模式条件必填检查 |

### 2.2 跨模式负向（`test_domain_models_d4e.py`）

| 测试函数 | 定义行号 | 参数化输入 / 覆盖 | 断言意图 |
|----------|----------|-------------------|----------|
| `test_forget_plan_single_item_cross_mode_selector_rejected` | 475–478 | single_item 携带 `target_session_id`（单例） | 模式外 selector → `ValidationError`（TD-015） |
| `test_forget_plan_rejects_every_cross_mode_selector` | 521–534（参数化 512–520） | 四模式各自在专属 selector 之外再携带一个模式外 selector（single_item+session、session+topic、topic+time_range、time_window+target_id） | 任意额外 selector 一律拒绝，不得悄然扩大精准删除范围（TD-015） |
| `test_forget_plan_rejects_whitespace_only_selectors_and_resolved_ids` | 469–472（参数化 461–468） | `target_selector=" \t "`、`target_id=" \n "`、`resolved_target_ids=["  "]`（affected_count=1） | selector 与解析 ID 不得以纯空白伪装为有效值 |

### 2.3 full_reset 负向 / 正向（`test_domain_models_d4e.py`）

| 测试函数 | 定义行号 | 参数化输入 / 覆盖 | 断言意图 |
|----------|----------|-------------------|----------|
| `test_forget_plan_full_reset_rejects_every_concrete_selector` | 560–575（参数化 556–559） | full_reset 逐字段携带 `target_id`/`target_session_id`/`target_topic`/`target_time_range`（4 字段参数化） | full_reset 禁止任意具体 selector（TD-015） |
| `test_forget_plan_full_reset_valid` | 198–207 | full_reset 无 selector（target_id=None） | 无 selector 的 full_reset 合法构造 |
| `test_forget_plan_preserves_unresolved_full_reset_type_boundary` | 544–553（参数化 537–543） | full_reset + `target_type`（all/preference） | HD-SCHEMA-06：未书面确认前不由 Domain 冻结 full_reset 类型细节（与 TD-015 正交，不夹带 selector） |

### 2.4 Preview/Execute 一致 selector 语义（`memory-service/tests/test_forget_persistence_d10d.py`）

| 测试函数 | 定义行号 | 覆盖 | 断言意图 |
|----------|----------|------|----------|
| `test_preview_mode_selector_mutual_exclusion` | 621–625 | single_item 携带 `target_session_id` 走 `forget.preview` 链路 | 复用 Domain 互斥 → `RequestValidationError`（INVALID_REQUEST 语义） |

**结论**：TD-015 的正向（4 模式专属 selector）、跨模式负向（4 模式参数化 + single_item 单例）、full_reset 禁具体 selector（4 字段参数化）、缺失专属 selector 负向（4 模式）、空串/纯空白绕过负向、Preview 链路互斥负向的测试定义均已存在并已提交，标记 `TEST_DEFINED`。本 Task 不新增、不修改任何测试，不产生任何运行数值。

---

## 3、Controller Gate 层（GATE_PENDING）

本 Task 的验收命令由 Controller 在 Implementer 返回后**独立执行**，结果按 `.local-agent-workflow/rules/runtime-validation.md` 证据规则另行记录并归档。本报告**不声称执行结果、不预写任何通过数值**。

| Gate | 命令 | 说明 |
|------|------|------|
| L0 | `python3 -m pytest --version` | pytest 可达性冒烟 |
| L1 | `python3 -m pytest -o pythonpath=memory-service memory-service/tests/test_domain_models_d4e.py -q` | 覆盖 TD-015 专属 selector 正向/跨模式负向/full_reset 负向用例群（490/521/475/560/448/469/434/609/618/627/198 等） |
| L2/L3 | 无（`runtime_required=false`，`runtime_commands=[]`） | 不适用；TD-015 互斥语义为纯 Pydantic 域模型校验，本 Task 不产生也不虚构任何精准遗忘 Runtime 证据（`RUNTIME_NOT_REQUIRED`，不出现 `HOST_VERIFIED` 表述） |

---

## 4、Reviewer 关闭层（REVIEW_PENDING）

- **当前状态**：Closure Candidate / In Progress **pending D Reviewer**（周子腾，D 主审）。
- **未完成事项**：
  1. 本 Task 的 L0/L1 验收 Gate 尚未由 Controller 执行（结果未产生）；
  2. TD-015 关闭条件「真实遗忘执行接入前关闭」依赖真实遗忘执行链路（Execute 侧 runtime fail-closed 现状见 §1.3），属 D 轨范围事项，登记 `HANDOFF`，不由本 docs 任务越轨实现；
  3. D 主审尚未对关闭候选进行正式确认；
  4. 登记表状态推进到 `Resolved` 需要 D Reviewer 确认验收标准达成（`代码合并 ≠ 技术债关闭`，见登记表管理规则第 3 条）。
- **明确声明**：本报告**不标记 Resolved**，不虚构 Reviewer 签署，不把 WSL 测试描述为精准遗忘 Runtime 证据或 `HOST_VERIFIED`。

---

## 5、明确未完成 / 未验证事项

1. 本 Task 的 L0/L1 命令尚未执行（由 Controller 在 Implementer 返回后独立执行并记录结果）。
2. D Reviewer（周子腾）对 TD-015 关闭候选的正式确认尚未取得。
3. **真实遗忘执行缺口（GAP / HANDOFF）**：TD-015 关闭条件「真实遗忘执行接入前关闭」尚未闭合——`uow.py` 第 225–245 行对 `topic`/`time_window`/`full_reset` 及 hard delete/cascade 为运行时 fail-closed（拒绝而非降级），真实删除、Vector 清理、SQLite 持久化与 IPC 执行链路未接线。本任务显式排除实现（`explicitly_excluded`），仅在审计报告中登记 HANDOFF，登记到 D 轨后续任务，不越轨修改 `memory-service/`。
4. 本报告不包含任何 Runtime 证据（`RUNTIME_NOT_REQUIRED`），也不包含任何虚构的测试运行数值或日志。

---

## 6、结论

TD-015 的**代码能力与测试定义**已在当前分支落地并提交（审计时 HEAD `20fd30917c4c692c768f0442623d4c5545ef95b8`，工作区干净）：`forget_mode` 与 selector 互斥由 `forgetting.py:100-125`（`_mode_conditional`）实现，四种模式（single_item/session/topic/time_window）只允许各自专属 selector，full_reset 禁止任意具体 selector；`forget_handlers.py:76-99` 在 Preview 复用该校验，`uow.py:225-245` 在 Execute 侧对未闭环模式 fail-closed；测试定义覆盖四模式正向（490）、跨模式负向（521/475）、full_reset 禁具体 selector（560）、缺失专属 selector（434/609/618/627）、空串/纯空白绕过（448/469）与 Preview 互斥（test_forget_persistence_d10d.py:621）。

技术条件已具备关闭候选审计；业务流程上剩余 Controller Gate 执行、真实遗忘执行链路 HANDOFF 登记与 D Reviewer 正式确认。登记表状态由 `Open` 推进为 `In Progress（Closure Candidate pending D Reviewer）`，**不得直接标记 Resolved**。