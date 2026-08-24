# 建立Day6多源安全对抗门禁

| 字段 | 内容 |
|---|---|
| Task ID | `day6-e-02-multisource-security-adversarial-gate-v1` |
| Day / Track | Day6 / E |
| 责任人 | E 轨 |
| Reviewer | D（非作者 Reviewer） |
| Module | `memory-service` |
| Runtime Required | `false` |
| 状态 | 作者侧实现与 L0/L1 已完成，待 PR 文档/证据闭环复核 |

## 目标

围绕Day6E多源准入策略、A轨EventPipeline与Day5E Candidate Governance建立数据驱动的安全对抗测试，验证敏感信息、Prompt Injection、provenance伪造、跨用户、Tool状态伪造、ignored绕过、未安全检查Raw Payload和临时偏好持久化攻击不能越过结构化信任边界；只在真实测试暴露source admission缺陷时对该策略做最小修复。

## 允许修改范围

- memory-service/security/source_admission.py
- memory-service/tests/test_multisource_security_adversarial_d6e.py

## 明确禁止范围

- 不修改memory-service/pipeline/**
- 不修改memory-service/providers/**
- 不修改memory-service/service/candidate_governance.py
- 不修改memory-service/domain/**
- 不修改SQLite、Repository、Outbox、Vector、FTS5、RRF、IPC或Runtime代码
- 不实现通用Prompt Injection分类器或依赖外部LLM进行安全终判
- 不修改.local-agent-workflow/
- 不执行分支创建、切换、Push、PR或合并
- 不执行银河麒麟Runtime Test

## 约束

- 开始前必须读取Task1最终实现及其测试，并读取memory-service/pipeline/pipeline.py、memory-service/service/candidate_governance.py和现有Day5E admission测试
- 测试必须是数据驱动或参数化的，至少覆盖Sensitive、Prompt Injection、Provenance Injection、Identity Injection、Tool Status Injection、Memory Status Injection、Cross-user、Ignored Bypass、Raw Payload Bypass、Temporary-to-persistent十类攻击族
- Prompt Injection验证重点是恶意自然语言不能覆盖结构化可信字段，不要求构建新的自然语言攻击分类模型
- 攻击文本可以声称修改user_id、source_event_id、Tool状态、memory_status或安全策略，但系统判定必须继续来自可信Context/Event/Pipeline
- 敏感测试只能使用明确虚构的测试凭据或占位模式，禁止真实API Key、Token、密码、私钥或真实用户数据
- 必须验证普通错误日志/reason code不回显完整敏感正文
- 至少包含user-A事件配user-B上下文的跨用户负向测试以及同用户正向对照
- 必须验证failed/cancelled/timeout/partial Tool正文即使声称success也不能形成成功稳定知识
- 必须验证should_ignore/ignored事件正文即使要求强制保存也不能放行
- 必须验证Tool Result的payload_security_checked=false不能被正文中的安全声明绕过
- 必须验证临时偏好或should_persist=false不会因攻击文本获得稳定跨会话资格，复用Day5E现有治理语义
- 若现有source_admission.py已正确通过全部测试，不得为了本Task进行无关重构
- 不得修改既有测试以掩盖失败，不得skip/xfail攻击用例
- 本任务只支持L0/L1安全契约结论，不得声明真实宿主攻击防护已HOST_VERIFIED

## 验收标准

- 新增安全对抗测试文件且覆盖至少十类攻击族
- 敏感信息攻击无法进入ALLOW_EXTRACTION且reason/audit不包含完整测试秘密
- Prompt Injection无法改变可信user_id、source_event_id、Tool状态、安全等级或memory_status语义
- 跨用户读取/准入攻击fail-closed，同用户对照正常
- failed/cancelled/timeout/partial Tool状态不能因正文声称success而形成成功稳定Knowledge
- ignored/should_ignore攻击无法绕过安全Gate
- payload_security_checked=false的Tool Result无法因正文声明已检查而放行
- 临时偏好无法因恶意文本被升级为稳定跨会话偏好
- Day5E Candidate Governance与Admission Gate关键回归继续通过
- 仅在测试证明必要时最小修改source_admission.py，未触碰A/C/D轨生产实现
- 未修改allowed_change_files以外文件
- L0和L1命令退出码均为0
- Reviewer返回APPROVE
- Evidence Reviewer返回EVIDENCE_APPROVED
- 控制器生成且仅生成一个原子Commit

## L0

```bash
python3 -m compileall memory-service/security memory-service/tests/test_multisource_security_adversarial_d6e.py
```

## L1

```bash
python3 -m pytest memory-service/tests/test_multisource_security_adversarial_d6e.py memory-service/tests/test_source_admission_d6e.py memory-service/tests/test_pipeline_integration.py memory-service/tests/test_candidate_admission_gate_d5e.py memory-service/tests/test_cross_session_business_case_d5e.py -q
```

## Runtime

本 Task `runtime_required=false`。

本任务仅形成 WSL L0/L1 证据，不声明 `HOST_VERIFIED`，也不单独证明 Day6 全轨 Gate 已完成。

## Commit 约定

- type: `test`
- subject: `建立Day6多源安全对抗门禁`

## 边界说明

本任务卡用于固化本轮实际开发 Task 的范围、禁止范围和验收依据，不新增或修改冻结 IPC、Persistence、Extraction、Pipeline、Vector、Hook 或 QML 契约。
