# D12E 合并后剩余关闭项独立审计（2026-09-04）

> 任务卡：`day12-e-postmerge-residual-closure-audit-v1`（docs-only）
> 本文档为**单一新增交付物**，只承载事实陈述，不修改任何运行时代码、测试、冻结契约、技术债状态或跨轨文件。

## 1. 审计基线（当前仓库事实）

| 事实 | 证据 |
|---|---|
| 当前 HEAD 与 origin/main 对齐，工作区干净 | `git rev-parse HEAD` == `cc4acf6ec67de50ca6fbb60bb7044cff46f7d4a5`；`git status` 显示 `On branch fix/e-d12-remaining-closure`、`nothing to commit, working tree clean`（审计与测试执行前后两次核验一致） |
| PR #137 已合并且早于后续 D12 主线修改 | PR #137（`f263d5b Fix/e d12 business schema drift remediation (#137)`）已合并；其后 #138/#135/#141/#140/#136 为主线后续修改（Plan 事实核验，不重复执行 `git log`） |
| 本报告不重写 D12E v5/v6 历史 Batch 结论 | D12E v5/v6 Batch 已合并；历史单项关闭候选审计（`docs/day12/10/11/12/13`，TD-013/014/015/017）与生命周期跨轨 handoff（`docs/day12/14`，TD-016）保留原结论，本报告仅在其上做当前 HEAD 收敛核验 |

本报告区分两类事项：

1. **随 PR #137 及主线合并已落地的交付**（代码、测试、治理实现已在当前 HEAD 生效并核验）；
2. **仍为跨轨待决事项**（D Reviewer 关闭门禁、TD-016/060、Host mapping），本报告仅登记事实与 handoff，不代行关闭。

## 2. 安全审查

逐项核对安全边界，确认**无生产激活误报**。

| # | 审查项 | 当前 HEAD 事实 | 证据 | 状态 |
|---|---|---|---|---|
| SEC-1 | `InMemorySourceResolver` 仅为测试/验证 seam | 类注释明确「PR-2 交付的测试/纯内存 resolver（production 不注册）」，仅 L1 契约测试与 L2 test profile 显式注入；`resolve` 未命中返回 None（调用方按 INTERNAL_ERROR，禁止编造正文）；生产状态常量为 `BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED` | `service/source_resolver.py:11-13,48-68,105-109` | PASS（无 production 误报） |
| SEC-2 | `turn.finalized` / `event.ingest` production 默认不注册 | handlers 头部声明 `CANDIDATE/BLOCKED_BY_HOST_MAPPING`，production 默认不注册 → `UNSUPPORTED_METHOD`；仅 `register_*_handler` 显式注册（test/validation profile）；app.py 中注册参数标注「production 禁止使用此参数（BLOCKED_BY_HOST_MAPPING）」 | `gateway/handlers.py:5,110-113,124,395`；`app.py:147-150,167-170` | PASS |
| SEC-3 | `forget.preview` / `forget.execute` production 默认不注册 | forget_handlers 头部声明 activation 状态 `CANDIDATE / BLOCKED_BY_HOST_MAPPING`，production 默认不注册 → `UNSUPPORTED_METHOD`；trusted_identity precheck 先行（cache-bypass 防护）；错误统一转 `INVALID_REQUEST`，不回显正文/凭据/敏感 | `gateway/forget_handlers.py:4-6,8-17`；`app.py:176-180` | PASS |
| SEC-4 | 未注册方法一律 `UNSUPPORTED_METHOD` | Registry 路由未注册 → 抛 `UnsupportedMethodError`（`ERROR_CODE_UNSUPPORTED_METHOD`），不落入任何隐式生产实现 | `gateway/registry.py:56,67-72`；`gateway/protocol.py:26` | PASS |
| SEC-5 | payload 身份仅属声明，数据归属由 ctx 控制 | `user_id` 仅来自 ctx（`ctx.user_id`），不采信 payload 自称身份；`source_event_id` 直接相等（R3），事件门禁 `source_event_id_mismatch` 防护 | `service/candidate_governance.py:372,376`；`domain/knowledge.py:56`；TD-017 审计引用 `candidate_governance.py:259-263` | PASS |

**结论**：当前 HEAD 上无任何将测试 seam、`BLOCKED_BY_HOST_MAPPING` 或未注册状态误报为 production 激活路径的安全问题。安全红线（原文隔离、身份由 ctx 控制、未注册即 UNSUPPORTED_METHOD）保持成立。

## 3. 假实现审查（seam vs production activation）

| # | 审查项 | 结论 | 证据 |
|---|---|---|---|
| FAKE-1 | 有无以 Mock/内存实现冒充 production 能力 | 无。`InMemorySourceResolver`、`register_turn_finalized_handler`、`register_event_ingest_handler`、`register_forget_handlers` 全部路径均显式声明为 test/validation seam，production 默认不装配 | `source_resolver.py:48-53,83-84,105-109`；`handlers.py:285-293,478-485`；`app.py:147-180` |
| FAKE-2 | 有无测试降级（删除失败测试、放宽断言、无条件 skip） | 无。本任务不触碰任何测试；L1 指定 8 个测试文件全部真实执行（见 §5） | 本任务不改 `tests/`；L1 执行证据见 §5 |
| FAKE-3 | 有无以静态检查/Mock 冒充 Runtime 证据 | 无。本报告全部 Runtime 相关状态标记 `RUNTIME_NOT_REQUIRED`（docs-only 任务，`runtime_required=false`，无 runtime_commands）；不出现 `HOST_VERIFIED` | 任务卡；§5、§8 |

**结论**：test/validation seam 与 production activation 边界在代码注释、app.py 注册门控与文档三处一致，无假实现冒充。

## 4. 业务规则审查

| # | 规则 | 当前 HEAD 事实 | 证据 | 状态 |
|---|---|---|---|---|
| BIZ-1 | NonEmptyStr 真值语义（TD-013） | `NonEmptyStr = Annotated[str, Field(min_length=1), AfterValidator(_ensure_non_blank)]`，拒绝空串与纯空白，原值不 strip；TD-013 登记为 In Progress（Closure Candidate pending D Reviewer） | `domain/common.py:38-45,51` | PASS（关闭候选，门禁待 D Reviewer，见 §6） |
| BIZ-2 | Optional ID/Reference 非空约束统一（TD-014） | Optional ID/Reference/Selector 统一为 `Optional[NonEmptyStr]` 或等价元素级约束（previous_version_id、content_ref、superseded_by_id、involved_knowledge_ids、resolved_by、resolved_target_ids、target_id、target_session_id、target_topic、target_time_range、rollback_plan_id）；三处范围决策点（extracted_entities、13 个结构化内容字段、resolution_strategy）登记为 GAP 待 D 主审 | TD-014 寄存器条目（register.md:90）；`domain/preference.py:64`、`domain/knowledge.py:69,72,75,82-106`、`domain/conflict.py:57-61`、`domain/forgetting.py:65-72` | PASS（实现语义）；GAP 记入 §6 handoff |
| BIZ-3 | ForgetPlan mode-selector 互斥（TD-015） | `_MODE_SELECTOR_FIELDS` 各模式只允许其对应 selector；`model_validator` 拒绝模式外 selector（full_reset 禁止任何具体 selector）；Preview 复用 Domain 校验、Execute fail-closed | `domain/forgetting.py:35-41,100-125`；`gateway/forget_handlers.py:8-14,41-60`；`db/uow.py:225-245`（TD-015 审计引用）；L1 用例群见 §5 | PASS（关闭候选，门禁待 D Reviewer）；真实遗忘执行链路未接线 → §6 handoff |
| BIZ-4 | KnowledgeCandidate 13 字段无损映射（TD-017） | 13 个结构化字段（conditions/evidence/steps/expected_result/problem/outcome/reproducible/template_body/parameters/priority/failure_reason/avoid_condition/alternative）在 Knowledge Domain 声明（`Optional[str]`、extra="forbid"），candidate_governance 1:1 同名直传（384-396 行）；content_summary=candidate.fact 仅承载 fact，不拼接伪装；source_event_id 直接相等；user_id 仅来自 ctx | `domain/knowledge.py:52,82-106`；`service/candidate_governance.py:370-397`；`providers/extraction_provider.py:168-201,257-261`（TD-017 审计引用） | PASS（关闭候选，门禁待 D Reviewer，四条件见 §6） |
| BIZ-5 | LifecyclePolicy 以 memory_status 为真值（TD-016 边界） | `memory_status` 为唯一优先生命周期真源（六值冻结）；lifecycle policy 消费之，不依赖 is_active/is_outdated/should_decay 做最终决策；`is_temporary/should_persist` 与 memory_status 冲突校验（D3 §7.9） | `service/lifecycle_policy.py:8,103`；`domain/enums.py:64`；`domain/preference.py:51,84-88`；`domain/knowledge.py:59,64`；`gateway/preference_handlers.py:97-118` | PASS（真值口径核验）；TD-016 迁移本身仍 Open（条件 ②③④⑤），见 §6 |

**结论**：五项业务规则在当前 HEAD 的实现语义全部核验通过（对应 TD 关闭候选成立的前提）；TD-013/014/015/017 的**正式关闭门禁**与 TD-016 的**跨轨迁移验收**均保持由 D Reviewer 确认，本报告不代行。

## 5. 测试覆盖审查（真实执行证据）

执行环境：WSL2 当前工作区（`/home/carlton/projects/kylinOS-agent-memory`），HEAD `cc4acf6`，工作区在测试前干净。L0/L1 均在**报告成稿前真实执行**，以下为真实命令、真实输出与真实退出码；非为预写值。

### L0 静态检查

| 命令 | 退出码 | 输出摘要 |
|---|---|---|
| `python3 -m compileall memory-service/domain memory-service/service memory-service/gateway` | 0 | 三个目录逐一 Listing，无语法错误输出 |
| `python3 -m pytest --version` | 0 | `pytest 9.1.0` |

> 静态检查仅证明语法可编译，不构成任何 Runtime 或真实系统行为证据。

### L1 WSL 单元/组件测试

命令（按任务卡原样执行）：

```
python3 -m pytest -o pythonpath=memory-service memory-service/tests/test_domain_models_d4e.py memory-service/tests/test_knowledge_domain_mapping_d8e.py memory-service/tests/test_candidate_governance_d5e.py memory-service/tests/test_lifecycle_policy_d8e.py memory-service/tests/test_knowledge_conflict_lifecycle_flow_d8e.py memory-service/tests/test_source_admission_d6e.py memory-service/tests/test_multisource_security_adversarial_d6e.py memory-service/tests/test_forget_persistence_d10d.py -q
```

结果：**355 passed in 10.15s**；passed=355、failed=0、skipped=0；退出码 0。

用例群 ↔ TD 对应：

| 测试文件 | 覆盖语义点 | 对应 TD |
|---|---|---|
| `test_domain_models_d4e.py` | TD-013 NonEmptyStr 正反向（含纯空白拒绝）；TD-014 Optional ID/Reference 用例群（751-841 行）；TD-015 ForgetPlan 各模式正向 + 跨模式负向 | TD-013 / TD-014 / TD-015 |
| `test_knowledge_domain_mapping_d8e.py` | 六类 KnowledgeCandidate→Domain 映射与 13 字段无损断言 | TD-017 |
| `test_candidate_governance_d5e.py` | 候选治理入口回归、user_id 仅来自 ctx、source_event_id 一致性 | TD-017 / 安全边界 |
| `test_lifecycle_policy_d8e.py` | LifecyclePolicy 决策、memory_status 真值语义 | TD-016 相关 |
| `test_knowledge_conflict_lifecycle_flow_d8e.py` | 冲突与生命周期流一致性 | TD-016 相关 |
| `test_source_admission_d6e.py` | 多源准入策略 | 安全/准入 |
| `test_multisource_security_adversarial_d6e.py` | 多源对抗安全用例 | 安全边界 |
| `test_forget_persistence_d10d.py` | forget.preview/execute 持久化与 Preview selector 互斥（621 行） | TD-015 / D10D |

> 测试结果与代码版本对应（HEAD `cc4acf6`、工作区干净）已核验。本次 L1 覆盖的是**已落地测试定义的执行态**；D Reviewer 正式关闭候选时是否复跑由门禁流程决定。

## 6. Bug / Blocker / Risk / Debt 表

| ID | 事项 | 责任轨 | 状态（本报告口径） | 后续 handoff（不越权修复） |
|---|---|---|---|---|
| B-1 | TD-013 关闭门禁（实现与测试已落地） | D 主审 | 关闭候选成立；`pending D Reviewer` | 建议后续原子 Task：D Reviewer 依 `docs/day12/10` 结论与 L0/L1 证据确认后关闭 TD-013 |
| B-2 | TD-014 关闭门禁 + 三处范围决策 GAP（extracted_entities、13 个结构化内容字段、resolution_strategy） | D 主审 | 关闭候选成立；GAP 未裁；`pending D Reviewer` | 建议后续原子 Task：D Reviewer 裁定三处 GAP 的约束形态后关闭 TD-014 |
| B-3 | TD-015 关闭门禁 + 真实遗忘执行链路未接线 | D 主审；安全边界由 E 负责 | 关闭候选成立；`pending D Reviewer`；真实执行属 D 轨范围外 | 建议后续原子 Task：D Reviewer 确认 Preview/Execute 语义一致后关闭 TD-015；真实执行链路接线另立 D 轨任务 |
| B-4 | TD-017 关闭门禁（D Reviewer 四条件：①正式承载契约 ②逐项无损 ③content_summary 未伪装 ④provenance 边界） | D 主审 | 关闭候选成立；`pending D Reviewer` | 建议后续原子 Task：D Reviewer 依 `docs/day12/13` 与 L1 证据逐条确认四条件后关闭 TD-017 |
| B-5 | TD-016 生命周期跨轨迁移（条件 ②③④⑤ 未闭合） | D/E 协同，D 主审 | `Open`（本任务不关闭） | 建议后续原子 Task：过渡布尔字段删除/派生化/冻结方案由 D/E 协同产出并经 D Reviewer 验收 |
| B-6 | TD-060 Canonical/transport 治理（四条件，含 `collected_at` alias 书面冻结、Canonical 索引） | E 轨（语义）+ C/D 轨（transport） | `Open`（本任务不关闭） | 建议后续原子 Task：D Reviewer 确认权威关系；C/D transport alias 冻结方案书面化 |
| B-7 | Host mapping 阻塞（`TurnExtractionAdapter` / production resolver / trusted host identity） | C/D 轨 | `BLOCKED_BY_HOST_MAPPING`；`turn.finalized`、`event.ingest`、`forget.*` 均不升级 ACTIVE | 建议后续原子 Task：C 轨 TurnExtractionAdapter 与 trusted host identity 就绪后再评估写方法 ACTIVE 化 |
| B-8 | KMA Canonical 仍为 `CANDIDATE_FOR_FREEZE` | E 轨（语义）+ D Reviewer 批准 | `CANDIDATE_FOR_FREEZE`（非团队级 FROZEN） | 建议后续原子 Task：D Reviewer 批准且 PR 合并后，由治理提交升级状态 |

**风险 R1（误表述）**：本报告严格使用 `CANDIDATE_FOR_FREEZE`、`BLOCKED_BY_HOST_MAPPING`、`UNSUPPORTED_METHOD`、seam 口径，未声称任何候选/阻塞状态已激活或已冻结。
**风险 R2（越权关闭）**：TD-013/014/015/017 全部保持 `pending D Reviewer`，TD-016/060 与 Host mapping 不因本任务关闭。

## 7. 已知发现但不修改

审计过程未发现超出既有登记范围的新代码缺陷。既有 GAP（TD-014 三处范围决策点、TD-016 过渡字段消费者、TD-060 transport alias）已在 §6 按责任轨与后续原子 Task 登记。按规定**发现即记录、不修改**；本次审计未触发任何范围外修复。

## 8. 运行验证状态

- **Runtime**：`RUNTIME_NOT_REQUIRED`。本任务为 docs-only 审计，`runtime_required=false`、`runtime_commands=[]`；L0/L1（WSL2）即满足本任务验证要求。
- **未声称**：无 L2/L3 执行，不出现 `HOST_VERIFIED` 或针对 Runtime 的 `PASS`。
- 本报告所有 PASS 均指 `L0/L1（WSL2 单测/静态）` 语义下的通过，与银河麒麟宿主能力无关。

## 9. 改动范围核验

- 本任务实际变更：**仅新增本文件**（`docs/day12/15_d12e_postmerge_residual_closure_audit_20260904.md`）。
- 未修改：`memory-service/`、`memory-client/`、`os-agent-integration/`、`migrations/`、`tests/`、KMA Canonical、ADR、`TECHNICAL_DEBT_REGISTER.md` 及其余全部文件。
- 回滚方式：删除本文件即可完全回滚，对仓库其余部分零影响。