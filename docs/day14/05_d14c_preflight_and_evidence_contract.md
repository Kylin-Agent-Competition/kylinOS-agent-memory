# D14C Formal Preflight 与证据转换契约

## 目的与边界

本契约只建立开跑前拒绝机制和数据转换入口：

- `scripts/run_d14c_formal_preflight.py <handoff.json>` 只读校验，不启动服务、不创建 evidence root、不产生 PASS。
- `scripts/build_d14c_d13c_bundle.py <capture.json> -o <bundle.json>` 只把真实 VM capture 的既有 D13C 字段交给 `scripts/run_d13c_session_eval.py`；不新增 evaluator 或评测阈值。

实现位于 `memory-service/evaluation/d14c_l3_harness.py`。L1 负向用例覆盖 dirty worktree、未冻结 D13D/D14D、未批准身份、非 ACTIVE 路由、未冻结 MemoryContext、非法/复用 evidence root，以及非 VM capture/provenance 漂移。

## Formal handoff

`d14c-formal-handoff/v1` 必须包含：

```text
formal_tested_commit (40 位 SHA，且等于干净工作树 HEAD)
d13d.status=FROZEN + evidence_reference
d14d.status=L3_READY + evidence_reference
release package: path/version/SHA-256/manifest SHA-256
AI Assistant、MemoryClient、Memory Service: path/version/SHA-256
VM: environment_id/name/uuid/snapshot/snapshot_uuid
trusted host identity: APPROVED + approval/process/DB reference + SHA-256
turn.finalized/event.ingest/forget.preview/forget.execute = ACTIVE
MemoryContext: FROZEN + schema/version/hash + no-match/failure semantics
evidence_root = evidence/l3-kylin-vm/d14c_<new-run-id>
```

目标 evidence root 必须尚不存在。通过 preflight 只意味着允许创建新 root 并开始**一次**正式运行；它不替代任何 Runtime 验收。失败时保留输入 handoff 作为诊断材料，修复后使用新 run ID。

## D13C evaluator 复用

真实 VM collector 写入 `d14c-runtime-capture/v1`，且只能在 `capture_status=VM_RAW_CAPTURED` 时转换。capture 的 `provenance.tested_commit/environment_id/evidence_root` 必须逐一等于 `d13c_config.implementation_commit/environment/evidence_reference`。转换结果仅为：

```json
{"config": "既有 D13C config", "sessions": "既有 D13C sessions"}
```

随后使用既有 `scripts/run_d13c_session_eval.py` 计算指标。任何 raw 缺失、状态非 VM capture 或 provenance 不一致均拒绝转换，不能用手写成功 bundle 代替。
