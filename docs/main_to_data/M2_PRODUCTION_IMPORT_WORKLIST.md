# M2 Main → Data Production Import 工作清单

> 状态：IN PROGRESS / NOT YET PASS  
> 目标：在已合并 M1-KB contract v2 的基础上，完成 RC10 的真实 Main 绑定、生产导入、授权读回与幂等重放，形成可供 Data-R 一次性裁定的 M2 evidence package。

## 0. 已冻结基线

- Main #180 merge commit: `d743f27c722fe24e38943f46fd9904cbb71c324d`
- M1-KB: `PASS`
- Contract: `interfaces/main_to_data/kb_import_contract.json`
- Contract schema: `v2`
- Data #68 merge commit: `3ca28a7c7b8742d81c3a14aa1ea7fc343ef2a711`
- Data-R RC10 admission: `os_kb_0001..os_kb_0010`
- M2: `IN PROGRESS`
- M3: 独立并行，不属于本 PR 完成条件
- Runtime lane: `RUNTIME_LANE_ALLOWED=false`

## 1. 本 PR Scope

本 PR 只关闭 **M2**：

1. 接收 Data 侧 RC10 binding request；
2. 为 RC10 建立真实、可解释、同用户、已准入的 Main source-event binding；
3. 实现/接通符合 M1-KB v2 的 production import path；
4. 实现 durable import identity / idempotency registry；
5. 执行真实 RC10 import；
6. 执行 authorized current-state readback；
7. 执行 same-request replay 与 conflict negative test；
8. 输出完整 M2 evidence / receipt。

本 PR **不**：

- 宣称 M3 PASS；
- 宣称 Runtime Gate 全绿；
- 重做 D13D/D14D；
- 重审 Data Final625 / seal-v3；
- 生成或修改 Data 侧冻结 KB400 source；
- 替代 Data-R 最终 M2 裁定。

## 2. Main-B / Main-C：RC10 Source Binding

对 `os_kb_0001..os_kb_0010` 逐条返回：

- `user_id`
- `source_event_id`
- `source_type`
- `source_business_status`
- `source_reference`
- `idempotency_key`
- `admission_decision=allow_extraction`

硬条件：

- [ ] same-user
- [ ] source event 在 Main 中真实存在
- [ ] `admission_decision=allow_extraction`
- [ ] descriptor 与 Main registry 一致
- [ ] source event 与对应 RC content 在 provenance 上相容/可解释
- [ ] 禁止为了字段完整度绑定无关 source event
- [ ] 禁止人工伪造 source event / source_reference

如当前没有可匹配来源：

- 必须走 Main 正常 source-event ingestion/admission 路径生成可审计来源；
- 不得手填生产真值。

建议输出：

`interfaces/main_to_data/m2_rc_binding_response.json`

DoD：

```text
RC10_BINDING = 10/10
CROSS_USER = 0
SOURCE_NOT_ADMITTED = 0
PROVENANCE_MISMATCH = 0
FABRICATED_EVENT = 0
```

## 3. Main-B / Main-C / Main-D：Production Import Path

必须满足 M1-KB v2：

### 请求层

- [ ] authenticated principal
- [ ] request_id
- [ ] source_manifest
- [ ] source_manifest_sha256
- [ ] exact JSONL SHA-256 校验
- [ ] record_count 校验
- [ ] envelope unknown-field fail-closed

### Record 层

- [ ] same-user scope
- [ ] source event lookup
- [ ] allow_extraction
- [ ] descriptor match
- [ ] knowledge_type enum fail-closed
- [ ] memory_status=`candidate`
- [ ] scope=`user`
- [ ] forbidden production identity fields rejected

### Production identity

由 Main 唯一分配：

- `knowledge_id`
- `memory_id`
- `accepted_version`
- `accepted_version_id`
- `accepted_memory_status`

首次接受应机械断言：

```text
accepted_version = 1
accepted_version_id = v1
accepted_memory_status = candidate
```

## 4. Main-D：Durable Import Idempotency

不得复用现有 24h request cache 作为生产 import identity registry。

必须实现/验证：

```text
registry_kind = durable_import_identity_registry
ttl = none
key = (user_id, idempotency_key)
```

首次成功保存：

- canonical_request_sha256
- data_record_id
- knowledge_id
- memory_id
- accepted_version
- accepted_version_id
- accepted_memory_status
- source_event_id
- result_status

Replay：

- same key + same canonical request → 返回首次 acceptance snapshot，`replayed=true`
- 不创建新的 knowledge row / relation / outbox / identity

Conflict：

- same key + different canonical request → `idempotency_conflict`

Lifecycle：

- removed / expired / superseded 不释放 key
- 不允许 TTL-based GC

## 5. 真实 RC10 Import

等待 Data-B 依据 binding response 产出最终：

- `input_rc_10.jsonl`
- `source_manifest.json`
- exact-byte SHA256
- RFC8785 manifest SHA256

Main 再执行真实 production import。

建议 evidence root：

`evidence/main_to_data/runtime_gate/m2_rc_import/`

至少保存：

- input_rc_10.jsonl
- source_manifest.json
- import_request / command
- stdout.log
- stderr.log
- exit_code
- per_record_results.json
- M2_RC_IMPORT_RECEIPT.json

M2 不能由 mock / schema lint / manual SQLite INSERT / synthetic receipt 代替。

## 6. Authorized Current-State Readback

对 accepted records 执行独立授权读回，至少证明：

- knowledge_id
- memory_id
- current_version
- current_version_id
- current_memory_status
- user_id
- scope

要求：

- [ ] identity 与 import acceptance 对应
- [ ] user scope 正确
- [ ] 真实记录可读回
- [ ] import acceptance snapshot 与 current state 概念分离

## 7. Replay Tests

### Positive replay

重放同一 logical request：

- [ ] `replayed=true`
- [ ] knowledge_id unchanged
- [ ] memory_id unchanged
- [ ] accepted_version unchanged
- [ ] accepted_version_id unchanged
- [ ] accepted_memory_status unchanged
- [ ] no duplicate row
- [ ] no duplicate relation
- [ ] no duplicate outbox event

### Negative replay

same `idempotency_key` + different canonical request：

- [ ] 必须返回 `idempotency_conflict`
- [ ] 不产生额外 production state

## 8. 最终 Main Receipt

最终提交：

`interfaces/main_to_data/m2_import_receipt.json`

建议字段：

```text
gate = M2
status = PASS / FAIL
source_main_commit =
m1_contract_schema_version = 2
m1_contract_sha256 =
data_rc_sha256 =
record_count =
binding_count =
imported_count =
rejected_count =
readback_verified =
same_request_replay_verified =
conflict_replay_verified =
production_path_used =
mock_used = false
evidence_root =
```

注意：Main receipt 只能说明 Main 侧证据状态；最终 `M2=PASS` 仍由 Data-R 验收后裁定。

## 9. 分工

### Main-B

- source binding
- import schema / request path
- per-record acceptance/rejection
- readback

### Main-C

- production import integration
- command/API execution
- evidence capture
- replay execution

### Main-D

- durable import registry
- transaction/identity integrity
- duplicate/side-effect negative verification

### Main-E / Independent Reviewer

- 核验 source binding 真实性
- 核验 production path 非 mock
- 核验 durable replay 语义
- 核验 readback / conflict test

### Data-B（外部依赖）

- 消费 Main binding response
- join verifier
- final RC10 + exact SHA + RFC8785 manifest
- 汇集 Main evidence

### Data-R（外部最终验收）

- 不重审 KB400 全量语义
- 只审 M2 contract/binding/import/readback/replay evidence
- 最终裁 `M2=PASS/FAIL`

## 10. Definition of Done

```text
[ ] M1-KB v2 baseline bound
[ ] RC10 real source binding 10/10
[ ] no cross-user / no fake provenance
[ ] production import path implemented/available
[ ] durable import registry active
[ ] final RC10 real import executed
[ ] imported_count > 0
[ ] authorized readback PASS
[ ] same-request replay PASS
[ ] conflict replay PASS
[ ] complete evidence package
[ ] independent review
[ ] final Main M2 receipt

MAIN_M2_EVIDENCE_READY = true
```

> 本 PR 完成后仍不自动打开 Runtime lane；还需要 Data-R 确认 M2，以及独立 M3 handoff PASS。
