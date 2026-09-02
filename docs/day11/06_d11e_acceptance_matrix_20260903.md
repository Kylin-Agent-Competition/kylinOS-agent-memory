# D11E 业务验收矩阵：同一虚拟机全功能联调（五类业务 + 隔离/安全护栏）

## 文档定位

- 本文件是 D11E 开工工作清单（`docs/day11/04_d11e_business_acceptance_worklist_20260903.md`）工作项 2 的交付物：把偏好、知识、冲突、生命周期、遗忘五类业务及跨用户/敏感护栏映射到「冻结契约 → 安全规则 → 既有 L0/L1 测试 → 主演示/联调路径 → 验收证据级别」的验收矩阵。
- 证据级别口径：L0（pytest 单测/流程）、L1（同机服务/DB 流程）、L2（麒麟 VM、同一 Commit 实测）。**任何 L2 结论未取得前一律 `UNVERIFIED`**，本矩阵不把 L0/L1 通过写成宿主验收通过。
- 本批不修改任何生产代码与冻结契约；矩阵只作验收范围与判定口径的收口。
- 基线：`origin/main@0820036`（2026-09-03）；E 轨既有 L0/L1 回归基线见 `docs/day11/05_d11e_l0l1_regression_20260903.log`（535 passed，2026-09-03）。

## 一、偏好（Preference）

| # | 验收子场景 | 冻结契约锚点 | 安全/隔离规则 | L0/L1 锚点（既有测试） | 主演示/联调路径 | 当前状态 |
|---|---|---|---|---|---|---|
| P-01 | 显式长期偏好创建（全链路 CREATE：来源安全门禁 → 候选治理 → 业务长期化 → 版本规划） | D3 §3.2/§7.9/§5.6；MemoryType=LONG_TERM | SEC-UI-01/02、SEC-SENS-* | `test_preference_business_flow_d7e.py`、`test_candidate_governance_d5e.py`、`test_domain_models_d4e.py` | 聊天沉淀（Step1/Step2）→ 偏好编辑器（D7C）确认 | L0/L1 已覆盖；L2 同 VM 待执行（UNVERIFIED） |
| P-02 | 临时指令不进入稳定长期偏好；隐式偏好不跳过确认 | D3 §7.9（临时 vs 长期） | SEC-LLM-*（终判禁模型生成） | `test_preference_business_policy_d7e.py`、`test_preference_business_flow_d7e.py` | 聊天临时指令对照 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| P-03 | 偏好共存/更新/回滚：同 key+scope 的 CREATE/NO_OP/UPDATE/COEXIST/ROLLBACK | D3 §3.2/§7.2（版本与回溯） | SEC-UI-*（同用户隔离） | `test_preference_version_policy_d7e.py`、`test_preference_business_flow_d7e.py` | 偏好编辑器：编辑/历史/回滚（D7C） | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| P-04 | 跨用户/越权偏好不可写、不可检索 | D3 §7.1/§7.10 | SEC-UI-01/02/07 | `test_multisource_security_adversarial_d6e.py`、`test_cross_session_business_case_d5e.py` | 负向注入样例 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |

## 二、知识（Knowledge）

| # | 验收子场景 | 冻结契约锚点 | 安全/隔离规则 | L0/L1 锚点（既有测试） | 主演示/联调路径 | 当前状态 |
|---|---|---|---|---|---|---|
| K-01 | 六类知识（workflow/case/template/fact/constraint/failure_experience）域映射与证据引用（source_event_id、superseded_by_id） | D3 §3.3/§5.6/§7.3 | SEC-TOOL-*、SEC-SENS-* | `test_knowledge_domain_mapping_d8e.py`、`test_domain_models_d4e.py` | Step3 Tool 事实型知识 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| K-02 | Tool 结果高于模型自述；失败/取消/超时不得沉淀为稳定知识 | D3 §7.8（Tool 可信度） | SEC-TOOL-01..07、SEC-LLM-08 | `test_candidate_admission_gate_d5e.py`、`test_multisource_security_adversarial_d6e.py` | Step3 Tool 成功/失败/取消 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| K-03 | 内容摘要经敏感过滤（S-01..S-09 不进正文/日志） | D3 §7.7 | SEC-SENS-01..07 | `test_multisource_security_adversarial_d6e.py`、`test_source_admission_d6e.py` | 负向敏感样例 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |

## 三、冲突（Conflict）

| # | 验收子场景 | 冻结契约锚点 | 安全/隔离规则 | L0/L1 锚点（既有测试） | 主演示/联调路径 | 当前状态 |
|---|---|---|---|---|---|---|
| C-01 | 冲突检测后对比展示：candidates.size>=2、可解释裁决（KEEP_LEFT/KEEP_RIGHT/COEXIST/DEFER/REJECT） | D3 §3.5/§7.5（六档优先级）；`service/conflict_resolution_policy.py` | SEC-UI-04（同用户冲突） | `test_conflict_resolution_policy_d8e.py`、`test_knowledge_conflict_lifecycle_flow_d8e.py` | Step4 conflict.compare | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| C-02 | 冲突最终裁决值（resolved_auto/resolved_manual/unresolvable）由规则引擎产出，非模型生成 | D3 §7.10 | SEC-LLM-04 | `test_knowledge_conflict_lifecycle_flow_d8e.py`、`test_domain_contract_compatibility_d4e.py` | Step4 对比结果展示 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |

## 四、生命周期（Lifecycle）

| # | 验收子场景 | 冻结契约锚点 | 安全/隔离规则 | L0/L1 锚点（既有测试） | 主演示/联调路径 | 当前状态 |
|---|---|---|---|---|---|---|
| L-01 | 提升/降级/过期/归档请求决策（PROMOTE/DEMOTE/EXPIRE/ARCHIVE_REQUEST）与 memory_status 计划一致 | D3 §3.6/§7.4/§5.6 | SEC-UI-*、SEC-SENS-* | `test_lifecycle_policy_d8e.py`、`test_knowledge_conflict_lifecycle_flow_d8e.py` | Step4 lifecycle.status | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| L-02 | expired/deprecated/removed/candidate 不进入标准 MemoryContext/检索；deprecated 仅显式 history/audit 模式 | D9 评测口径；`service/retrieval_business_policy.py` | SEC-CTX-01、B 轨 guardrail 口径 | `test_retrieval_business_policy_d9e.py` | 标准上下文组装对照 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |

## 五、遗忘（ForgetPlan）

| # | 验收子场景 | 冻结契约锚点 | 安全/隔离规则 | L0/L1 锚点（既有测试） | 主演示/联调路径 | 当前状态 |
|---|---|---|---|---|---|---|
| F-01 | 请求→Plan 输入边界：五种 forget_mode 各自唯一 selector；full_reset 默认拒绝/受限 | D3 §3.7/§7.6；`domain/forgetting.py` | SEC-FORGET-03 | `test_forgetting_policy_d10e.py` | Step5 forget 输入 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| F-02 | 目标解析精准：resolved_target_ids/affected_count 由规则引擎产出，误删=0、漏删=0，禁模型生成 | D3 §7.6/§7.10 | SEC-FORGET-01/04、SEC-UI-05 | `test_forgetting_policy_d10e.py` | Step5 预览快照 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| F-03 | 预览→确认→执行状态机：pending→previewing→awaiting_confirmation→executing→completed/failed/rolled_back；不可跳步/复用过期确认 | D3 §5.5；SEC-FORGET-02 状态机 | SEC-FORGET-02 | `test_forgetting_policy_d10e.py` | Step5 Preview→Execute（credential TTL） | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| F-04 | 软删除立即排除标准检索/上下文；硬删除后无正文/明文可检索残留（跨 D/B 通道） | D3 §7.6；D10D 持久化 | SEC-FORGET-05、SEC-SENS-07 | `test_forgetting_policy_d10e.py`、`test_forget_persistence_d10d.py` | Step5 执行后复检（真源/Vector/FTS5） | L0/L1 已覆盖；L2 同 VM 待执行（UNVERIFIED，D10B 删除 L2 证据为 B 轨输入） |
| F-05 | 高敏感遗忘须已鉴权预览后确认；跨用户遗忘零影响 | D3 §7.7 | SEC-FORGET-04、SEC-UI-05/06、SEC-AUTH-01 | `test_forgetting_policy_d10e.py`、`test_multisource_security_adversarial_d6e.py` | 负向跨用户/敏感遗忘 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |

## 六、检索业务治理与隔离护栏（D9E/D10E 业务约束在联调中的表现）

| # | 验收子场景 | 冻结契约锚点 | 安全/隔离规则 | L0/L1 锚点（既有测试） | 主演示/联调路径 | 当前状态 |
|---|---|---|---|---|---|---|
| R-01 | 标准 MemoryContext 排除 removed/expired/跨用户/敏感/unresolved；deprecated 不进标准上下文 | D9 Gold Policy v2；`service/retrieval_business_policy.py` | SEC-CTX-01、SEC-UI-02/03 | `test_retrieval_business_policy_d9e.py` | Step2 跨会话上下文对照 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |
| R-02 | 跨用户/敏感条目进入最终 Top-K = Critical（目标 0）；guardrail 计数口径一致 | D9 检索评测口径（PR88 裁决） | SEC-UI-02、SEC-SENS-* | `test_retrieval_business_policy_d9e.py`、`evaluation/test_d9_retrieval_gold_spec.py` | B 轨检索输出核验 | L0/L1 已覆盖；正式检索 L2 以 D13B/D13E 封存口径为准 |
| R-03 | 遗忘后重新检索/上下文组装排除目标（forgotten_excluded_count 正确） | SEC-FORGET-05 | SEC-FORGET-05 | `test_forgetting_policy_d10e.py`、`test_retrieval_business_policy_d9e.py` | Step5 执行后复检 | L0/L1 已覆盖；L2 待执行（UNVERIFIED） |

## 七、验收结论口径

- 上表「L0/L1 已覆盖」= 2026-09-03 在 `origin/main@0820036` 复跑 E 轨既有测试 535 passed（`docs/day11/05_d11e_l0l1_regression_20260903.log`），证明业务语义与护栏在单测/流程层成立。
- 「L2 待执行（UNVERIFIED）」= 尚未在同一麒麟 VM、同一 Commit 上以真实服务/UI/检索链路验收；**不构成 D11E 完成证据**。
- 完成 D11E 的宿主侧证据仍依赖：D11D 统一 VM/快照、C-D11 5 步主演示在真实 VM 运行、B 轨真实检索/删除输出与 A 轨 SDK 健康（见工作清单工作项 5）。未齐备前不得把本矩阵写成验收通过。