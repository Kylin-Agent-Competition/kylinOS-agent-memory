# 建立Day6多源开发集与错误分类

| 字段 | 内容 |
|---|---|
| Task ID | `day6-e-03-multisource-devset-error-taxonomy-v1` |
| Day / Track | Day6 / E |
| 责任人 | E 轨 |
| Reviewer | D（非作者 Reviewer） |
| Module | `evaluation` |
| Runtime Required | `false` |
| 状态 | 作者侧实现与 L0/L1 已完成，待 PR 文档/证据闭环复核 |

## 目标

建立Day6E可持续扩充的多源开发集v1与统一错误分类表，为后续偏好、知识、检索与正式Gold Label评测提供可复用样本和错误归因基础；覆盖Tool Result、用户行为候选和手动配置三类硬数据源，同时对尚未由C轨正式冻结的行为事件映射保持PENDING_C_CONFIRMATION，不自行新增共享SourceType。

## 允许修改范围

- evaluation/D6_MULTISOURCE_DEVSET_V1.jsonl
- evaluation/D6_MULTISOURCE_ERROR_TAXONOMY_V1.md
- evaluation/D6_MULTISOURCE_DEVSET_README_V1.md
- evaluation/test_d6_multisource_devset.py

## 明确禁止范围

- 不修改memory-service/**
- 不修改datasets/**
- 不修改docs/**
- 不修改evidence/**
- 不修改现有D3 Gold Label与指标规范
- 不新增或冻结MemorySourceEvent、SourceType、EventType等共享生产契约
- 不下载外部大数据集，不写入真实用户数据或真实凭据
- 不宣称本开发集已经是最终Gold、回归集或封存测试集
- 不修改.local-agent-workflow/
- 不执行分支创建、切换、Push、PR或合并
- 不执行银河麒麟Runtime Test

## 约束

- 开始前必须阅读evaluation/D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md、Day3安全验收契约、Day6E Task1/Task2实现与测试以及当前pipeline.schemas的公开枚举
- 开发集定位必须明确为DEVSET_V1而非最终Gold或封存测试集，后续仍需人工双人复核、切分与封存
- 至少提供90条合成或脱敏样本，Tool Result、behavior candidate、manual config三类source_family各不少于30条
- 每类必须同时包含正常、边界、错误和安全攻击样本，不得只生成正例
- 每条记录至少包含sample_id、source_family、input_case或input_event、expected_gate、expected_should_extract、expected_memory_kind、expected_security_decision、expected_error_codes、attack_tags、annotation_status和notes
- sample_id必须全局唯一且稳定；枚举字段必须由README和测试明确约束
- Tool Result样本应覆盖success、failed、cancelled、timeout、partial以及未安全检查payload等状态
- manual config样本应覆盖长期偏好、临时设置、安全相关配置、敏感内容和冲突/非法值边界
- behavior candidate只作为数据集source_family分类；若当前C轨尚未冻结其到MemorySourceEvent.source_type的正式映射，记录mapping_status=PENDING_C_CONFIRMATION，不得擅自增加behavior SourceType或伪造已冻结字段
- 错误分类至少覆盖Q、SRC、SEC-SENS、SEC-PI、SEC-UI、PROV、TOOL、LIFE、DUP、CONTRACT十个错误域，并给出编号规则、含义、阻断级别和示例
- expected_error_codes只能引用错误分类表中已定义的代码；无错误时使用空数组
- 所有敏感样本必须是明显虚构/测试用途内容，不得使用真实账户、手机号、身份证、私钥或API凭据
- test_d6_multisource_devset.py必须校验JSONL逐行合法、必填字段、唯一sample_id、三类数量下限、枚举合法、error code存在性、behavior映射状态和敏感占位约束
- 不得通过在测试中硬编码无条件PASS、跳过坏行或自动修正非法JSON制造通过
- 本任务不产生Runtime结论，不更新evidence/index.yaml

## 验收标准

- D6_MULTISOURCE_DEVSET_V1.jsonl存在且逐行均为合法JSON
- 开发集样本总数不少于90，Tool Result、behavior candidate、manual config各不少于30条
- 三类数据源均包含正常、边界、错误和安全攻击样本
- Tool Result状态覆盖success、failed、cancelled、timeout和partial
- behavior candidate未被擅自冻结成新的共享SourceType；未确认映射明确标PENDING_C_CONFIRMATION
- 每条样本具备规定的最小字段且sample_id唯一
- 错误分类表至少覆盖Q、SRC、SEC-SENS、SEC-PI、SEC-UI、PROV、TOOL、LIFE、DUP、CONTRACT十个错误域
- 所有expected_error_codes均能在错误分类表中找到定义
- README明确开发集用途、非Gold定位、数据来源为合成/脱敏、后续人工双人复核与封存流程
- 数据集不包含真实密钥、Token、密码、私钥或未脱敏真实用户数据
- 验证测试能够在非法JSON、重复sample_id、缺字段、未知error code或样本数量不足时真实失败
- Day6E Task1/Task2及Day5E关键回归与本开发集验证一起通过
- 未修改allowed_change_files以外文件
- L0和L1命令退出码均为0
- Reviewer返回APPROVE
- Evidence Reviewer返回EVIDENCE_APPROVED
- 控制器生成且仅生成一个原子Commit

## L0

```bash
python3 -m compileall evaluation/test_d6_multisource_devset.py
```

## L1

```bash
python3 -m pytest evaluation/test_d6_multisource_devset.py -q
```

```bash
python3 -m pytest memory-service/tests/test_source_admission_d6e.py memory-service/tests/test_multisource_security_adversarial_d6e.py memory-service/tests/test_candidate_governance_d5e.py memory-service/tests/test_candidate_admission_gate_d5e.py memory-service/tests/test_cross_session_business_case_d5e.py memory-service/tests/test_pipeline_integration.py evaluation/test_d6_multisource_devset.py -q
```

## Runtime

本 Task `runtime_required=false`。

本任务仅形成 WSL L0/L1 证据，不声明 `HOST_VERIFIED`，也不单独证明 Day6 全轨 Gate 已完成。

## Commit 约定

- type: `test`
- subject: `建立Day6多源开发集与错误分类`

## 边界说明

本任务卡用于固化本轮实际开发 Task 的范围、禁止范围和验收依据，不新增或修改冻结 IPC、Persistence、Extraction、Pipeline、Vector、Hook 或 QML 契约。
