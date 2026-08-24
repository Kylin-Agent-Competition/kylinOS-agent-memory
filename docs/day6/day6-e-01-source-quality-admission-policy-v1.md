# 建立Day6多源质量与业务准入策略

| 字段 | 内容 |
|---|---|
| Task ID | `day6-e-01-source-quality-admission-policy-v1` |
| Day / Track | Day6 / E |
| 责任人 | E 轨 |
| Reviewer | D（非作者 Reviewer） |
| Module | `memory-service` |
| Runtime Required | `false` |
| 状态 | 作者侧实现与 L0/L1 已完成，待 PR 文档/证据闭环复核 |

## 目标

在不重复实现A轨EventPipeline、QualityScorer、敏感识别或Candidate抽取的前提下，新增E轨多源业务准入策略：只消费现有PipelineResult、MemorySourceEvent语义和可信ServiceRequestContext，将安全红线、用户隔离、质量Gate与Tool真实状态转换为可测试的ALLOW_EXTRACTION、AUDIT_ONLY或REJECT业务决策，并为failed Tool保留仅failure_experience可继续的业务限制。

## 允许修改范围

- memory-service/security/source_admission.py
- memory-service/security/__init__.py
- memory-service/tests/test_source_admission_d6e.py

## 明确禁止范围

- 不修改memory-service/pipeline/**
- 不修改memory-service/providers/**
- 不修改memory-service/service/candidate_governance.py
- 不修改memory-service/domain/**
- 不修改SQLite、Alembic、Repository、UoW或Outbox
- 不修改Vector、FTS5、RRF或retrieval实现
- 不修改IPC、C++ Bridge、MemoryClient、OS Agent Hook、QML、systemd或KYSEC
- 不新增第二套MemorySourceEvent、NormalizedEvent、QualityScore、PreferenceCandidate或KnowledgeCandidate真源
- 不修改.local-agent-workflow/
- 不执行分支创建、切换、Push、PR或合并
- 不执行银河麒麟Runtime Test

## 约束

- 开始前必须阅读memory-service/pipeline/pipeline.py、memory-service/pipeline/quality.py、memory-service/pipeline/schemas.py、memory-service/security/contracts.py、memory-service/service/contracts.py、memory-service/service/candidate_governance.py以及Day4E/Day5E现有测试
- 必须复用现有PipelineResult、NormalizedEvent、QualityScore、SourceBusinessStatus、SensitivityLevel和ServiceRequestContext；不得复制这些模型
- E轨策略不得重新计算A轨六维质量分、来源可靠性权重、敏感识别结果或内容指纹，只消费现有结构化结果
- 安全与用户隔离判定优先于质量Gate；高/严重敏感、should_ignore、ignored、安全Gate已触发、Tool raw payload未安全检查或ctx.user_id与event.user_id不一致时必须fail-closed
- 正文、content_summary、LLM输出或Candidate文本不得覆盖user_id、source_business_status、sensitivity、payload_security_checked等可信结构字段
- 当PipelineResult.eligible_for_extraction=false且不存在安全拒绝时，应保留AUDIT_ONLY语义而非伪装成安全违规
- failed Tool若允许继续抽取，只能明确限制为failure_experience路径；不得允许Preference或成功Knowledge语义
- cancelled、timeout和partial必须保持保守语义，不得产生成功稳定知识；具体决策需与现有A轨和Day5E契约一致
- 允许新增仅属于E轨source admission的最小结果类型或枚举，但不得形成与现有SecurityDecision、Event或Candidate平行的公共真源
- reason code必须稳定、可测试、不得包含用户原文、密钥、Token或完整敏感载荷
- 测试必须使用合成用户ID、事件ID和脱敏/虚构敏感样本，不得写入真实凭据
- 不得通过删除、skip、xfail、弱化断言或修改既有测试制造通过
- 本任务仅支持L0/L1结论，不得声明HOST_VERIFIED或Day6整体PASS

## 验收标准

- source_admission.py存在且可导入，公开入口能够消费现有PipelineResult与可信ServiceRequestContext并返回结构化业务准入结果
- 准入结果至少能区分ALLOW_EXTRACTION、AUDIT_ONLY和REJECT，且包含稳定reason code
- ctx.user_id与event.user_id不一致时REJECT
- event.should_ignore=true、source_business_status=ignored、security_gate_triggered=true或high/critical敏感事件均REJECT
- Tool Result在payload_security_checked=false时REJECT
- 非安全原因导致eligible_for_extraction=false时返回AUDIT_ONLY而非安全REJECT
- 正常质量合格且安全干净的事件可进入ALLOW_EXTRACTION
- failed Tool不会获得Preference准入，不会获得成功Knowledge准入；如保留抽取，仅明确允许failure_experience
- cancelled/timeout/partial不会被准入为成功稳定知识
- 策略不读取恶意正文来决定user_id、真实Tool状态、安全等级或可信生命周期
- 未修改allowed_change_files以外文件
- Day4E/Day5E既有业务治理与A轨Pipeline关键回归通过
- L0和L1命令退出码均为0
- Reviewer返回APPROVE
- Evidence Reviewer返回EVIDENCE_APPROVED
- 控制器生成且仅生成一个原子Commit

## L0

```bash
python3 -m compileall memory-service/security memory-service/tests/test_source_admission_d6e.py
```

## L1

```bash
python3 -m pytest memory-service/tests/test_source_admission_d6e.py memory-service/tests/test_pipeline_integration.py memory-service/tests/test_candidate_admission_gate_d5e.py memory-service/tests/test_candidate_governance_d5e.py -q
```

## Runtime

本 Task `runtime_required=false`。

本任务仅形成 WSL L0/L1 证据，不声明 `HOST_VERIFIED`，也不单独证明 Day6 全轨 Gate 已完成。

## Commit 约定

- type: `feat`
- subject: `建立Day6多源质量与业务准入策略`

## 边界说明

本任务卡用于固化本轮实际开发 Task 的范围、禁止范围和验收依据，不新增或修改冻结 IPC、Persistence、Extraction、Pipeline、Vector、Hook 或 QML 契约。
