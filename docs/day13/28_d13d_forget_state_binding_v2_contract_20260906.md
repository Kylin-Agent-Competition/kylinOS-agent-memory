# D13D Forget State Binding V2 Contract（runtime-bound，CURRENT NORMATIVE）

| 字段 | 内容 |
|------|------|
| 契约名 | `D13D_FORGET_STATE_BINDING_V2` |
| binding_version | `d13d-forget-state-binding/v2` |
| 状态 | `CURRENT NORMATIVE`（V1 = `HISTORICAL / SUPERSEDED`，仅 state-preparation evidence，见 `27_d13d_forget_state_binding_contract_20260906.md`） |
| 目的 | 关闭最新 Review（PR #160 R4）：artifact 描述的 VM 预置 source DB 与实际 dispatch runtime DB 之间建立**真实、可复核、隔离**的关系；不再把单一 `applicable_source_commit` 同时承担 state-prep 与 dispatch 两种语义 |
| 编制日期 | 2026-09-06 |

> 关联：`docs/day13/26_…`（§9 P2-B）、`memory-service/evaluation/d13d_forget_state_binding.py`（v1/v2 静态校验）、PR #160 R5–R10（runtime restore / dispatch / observation / receipt）。

---

## 1. 顶层结构（v2）

```jsonc
{
  "binding_version": "d13d-forget-state-binding/v2",
  "artifact_sha256": "<canonical SHA-256，口径同 v1 §7>",
  "owner": "…", "approved_by": "…", "approval_reference": "…",
  "state_preparation_commit": "<准备 sealed source DB 的 commit>",
  "execution_compatibility": {
    "minimum_commit": "<可消费该 state 的最低 commit>",
    "policy": "descendant-and-contract-compatible"
  },
  "environment_id": "…",
  "vm_snapshot": { "vm": "…", "vm_uuid": "…", "snapshot": "…", "snapshot_uuid": "…" },
  "source_state": {
    "state_root": "<绝对路径>",
    "sealed_db_path": "<sealed source DB 绝对路径>",
    "sealed_db_sha256": "<SHA-256>",
    "db_size_bytes": 0,
    "sqlite_schema_fingerprint": "<sqlite_master canonical SHA-256>",
    "prepared_on_vm_snapshot": "<VM snapshot>",
    "prepared_at_utc": "<UTC>"
  },
  "retrieval_profile": "d13d-validation-profile-v2",
  "created_at_utc": "…", "created_by": "…",
  "samples": [ "…五条，结构见 §3…" ]
}
```

## 2. 语义拆分（取代 v1 的 `applicable_source_commit`）

- `state_preparation_commit`：只描述“source state 由哪个 commit 预置”；
- `execution_compatibility.minimum_commit`：声明可消费该 state 的最低 commit；
  当前 tested HEAD 必须满足 `minimum_commit` 是 HEAD 祖先（`git merge-base --is-ancestor`）+ schema fingerprint 兼容；
- **禁止**继续使用单一 `applicable_source_commit` equality 作为 dispatch 门禁（v2 校验器直接拒绝该字段）；
- Phase 3：final tested_commit 选定后重新生成 exact V2 binding，不提前绑定未来 final commit。

## 3. source_state（sealed source DB）身份

- `sealed_db_path / sealed_db_sha256 / db_size_bytes`：现场复算 SHA-256 与字节数；
- `sqlite_schema_fingerprint`：对 `sqlite_master` canonical 序列化求 SHA-256（schema 兼容性现场校验用）；
- source DB 是**封存快照**，adapter 不得直接修改；runtime 只操作它的隔离副本。

## 4. R5｜sealed source → isolated runtime restore

- 校验 sealed source：artifact SHA、路径存在、拒绝 symlink、DB SHA 复算、SQLite integrity/schema、`state_preparation_commit` ancestry；
- 对每个 sample 在 `state_root/runtime/<sample_id>/` 复制 sealed DB 作为 fresh runtime clone（初始 SHA == source SHA）；
- runtime 执行后 DB bytes 会变化；只绑定“初始 restore hash”，不在 execute 后要求等于 source hash。

## 5. 每 sample 结构与 retrieval（v2）

- sample 必填与 v1 相同（target/controls/prerequisite/realtime/rebuild）；
- realtime/rebuild 的 `entrypoint` 必须来自 **closed allowlist** `retrieval_profile`（禁止 artifact 提供任意 Python import path）；
- 准备阶段只保存受控 profile/entrypoint 与显式命名锚点 `prepared_state_snapshot` / `prepared_state_watermark`；
- 运行后 snapshot/watermark/trace 由 runtime evidence 实际产生，禁止把 realtime observation 复制成 rebuild observation。

## 6. 禁止与边界

- 不改 Dataset / Gold / Threshold / Runner bytes；
- 不写死 target_identity、不伪造 observation、不补零；confirmation token 不入 artifact；
- 不产生 formal raw / Seal / attestation / Runner / `D13D_FROZEN`（Phase 3 范围）。

## 7. 验收要点（对应 PR #160 复审矩阵）

- [ ] source DB 与 runtime DB 关系可证明（source SHA 现场复算、source 不被修改、runtime 为 verified restore/copy）
- [ ] 每 sample fresh isolated state
- [ ] state_preparation_commit / execution_compatibility 语义正确，无单一 applicable_source_commit
- [ ] sealed source 现场 schema fingerprint 兼容验证
- [ ] 5/5 real preview/execute/realtime/rebuild E2E + receipt provenance（R8–R10）