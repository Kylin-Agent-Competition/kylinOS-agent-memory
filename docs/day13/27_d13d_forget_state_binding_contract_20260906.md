# D13D Forget State Binding V1 Contract（artifact 规范，冻结）

| 字段 | 内容 |
|------|------|
| 契约名 | `D13D_FORGET_STATE_BINDING_V1` |
| 用途 | D13D Phase 2 P2-B：为五条正式 Forget sample 提供可复核的真实状态绑定与检索观测入口 |
| 状态 | `FROZEN_BY_B（获授权业务/VM Owner）`：契约冻结；artifact 生成待 VM 状态预置 |
| 裁定/授权 | D/E 书面回执 B-2（2026-09-06，ACCEPTED）+ B 完整明确授权（2026-09-06） |
| binding tested_commit | 候选 `main@dc58e83479d718c8e3fbbbbb5d3b3f046f651973`（用户确认；Phase 3 最终 tested_commit 变化须重生成） |
| 建议文件路径 | `evaluation/d13e/D13D_FORGET_STATE_BINDING_V1.json`（或仓库外 artifact + SHA-256） |
| 编制日期 | 2026-09-06 |

> 本文件是 artifact 的**结构规范**（generator/verifier 的单一真源）。VM 预置、真实 DB/state
> 身份采集、realtime/rebuild 观测入口与生成流程见 `docs/day13/26_…` §9 执行清单 4–7。

---

## 1. 顶层结构

```jsonc
{
  "binding_version": "d13d-forget-state-binding/v1",
  "artifact_sha256": "<对 canonical payload 的 SHA-256，见 §7>",
  "owner": "B（高翌哲）",
  "approved_by": "D/E（书面回执 B-2）",
  "approval_reference": "D/E 2026-09-06 B-2 ACCEPTED / BLOCKED_PENDING_VM_BINDING_ARTIFACT",
  "applicable_source_commit": "dc58e83479d718c8e3fbbbbb5d3b3f046f651973",
  "environment_id": "<env id>",
  "vm_snapshot": {
    "vm": "<VM 名>",
    "snapshot": "d14d-clean-base-20260906-r2",
    "snapshot_uuid": "<UUID>"
  },
  "state_root": "<绝对路径>",
  "db_identity": {
    "path": "<绝对路径>",
    "sha256": "<DB 文件 SHA-256>"
  },
  "retrieval_profile": "<validation profile 名，显式注册真实 forget.preview/execute>",
  "created_at_utc": "2026-09-06T…Z",
  "created_by": "B（高翌哲）",
  "samples": [ "…见 §3–§6…" ]
}
```

## 2. 顶层必填与禁填

必填：`binding_version`、`artifact_sha256`、`owner`、`approved_by`、`approval_reference`、
`applicable_source_commit`、`environment_id`、`vm_snapshot{vm,snapshot,snapshot_uuid}`、
`state_root`、`db_identity{path,sha256}`、`retrieval_profile`、`created_at_utc`、
`created_by`、`samples`（恰好 5 条，sample_id 集合 = D13E Forget 五条）。

禁止字段/内容：`gold` / `expected` / `threshold` / `PASS` / `FAIL` / `confirmation_token` /
`private key` / 凭据 / API Key / 用户正文 / 敏感载荷。

## 3. 每条 sample 必填结构

```jsonc
{
  "sample_id": "d13e-forget-001",
  "user_id": "user_d13e_alpha",
  "forget_mode": "single_item",
  "target_selector": { "…": "来自 D13E Dataset 的 selector 原样" },
  "target_identity": { "…": "真实、同用户、活动 DB/state 身份（含真实数字 DB ID）" },
  "same_user_controls": [ "≥1 个同用户、同 kind 的控制身份（full_reset 除外：整用户为作用域，可为空）" ],
  "foreign_user_controls": [ "≥1 个 foreign-user 同 kind 控制身份" ],
  "prerequisite_facts": { "…": "该 mode 的真实持久化前置事实引用（不含正文）" },
  "realtime_retrieval": { "entrypoint": "…", "trace_reference": "…", "snapshot": "…", "watermark": "…" },
  "rebuild_retrieval": { "entrypoint": "…", "trace_reference": "…", "snapshot": "…", "watermark": "…" }
}
```

## 4. 按 mode 的前置事实要求

| mode | sample | 前置事实（必须真实存在） |
|---|---|---|
| single_item | d13e-forget-001 | 该 user 的真实 active memory 条目（`memory_entries` 数字 DB ID = Dataset 外标识 `d13e-memory-001` 的受控对应） |
| session | d13e-forget-002 | 同一真实 session（Dataset 外标识 `d13e-session-001`）下多个目标/控制项 |
| topic | d13e-forget-003 | 真实 `topic_key = d13e-topic` 与绑定事实；不得从 content 反推 |
| time_window | d13e-forget-004 | 真实 `source_events.occurred_at` 落在冻结 UTC `[from,to)` 窗口内的事件与窗口外 control |
| full_reset | d13e-forget-005 | 该 user 的 knowledge + preference + foreign-user controls 全集 |

每个 mode 均需：same-user control（保留项）与 foreign-user same-kind control（不得误删）。

## 5. target_identity 约束

- `single_item`：必须含真实数字 DB ID（int）与稳定 identity（如 `memory_entries.id`）；
- 禁止：adapter/生成器临时插入 memory、按 selector 猜 DB ID、从 Dataset 推导数据库记录；
- 禁止把 confirmation token 写入 artifact——confirmation 由真实 `forget.preview` 动态产生。

## 6. retrieval 观测入口约束

- `realtime_retrieval` / `rebuild_retrieval` 必须是真实检索调用入口（脱敏 trace/reference、
  source snapshot、watermark）；
- realtime = `forget.execute` 后的实时查询；rebuild = index rebuild 后再查询；
- 禁止仅手工 DB 查询宣称 residual=0；观测值由真实检索调用提供。

## 7. SHA-256 口径

`artifact_sha256` = 对「去除自身字段后的 canonical payload」的 SHA-256：

```text
canonical = json.dumps(payload_without_artifact_sha256,
                       ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")
sha256 = hashlib.sha256(canonical).hexdigest()
```

verifier 重算并比对；任何 bytes 变化须重算 SHA 并重新独立复核。

## 8. 验收（对应 D/E B-2 + 25_ 请求 §验收）

- [ ] binding_version / artifact_sha256 / owner / approval_reference 齐全且 SHA 复核 PASS
- [ ] applicable_source_commit / environment_id / vm_snapshot / state_root / db_identity 齐全
- [ ] 5 sample 均有真实 DB/state 目标身份与前置事实
- [ ] 每 sample 有 foreign-user same-kind control；same-user control 除 full_reset（全量作用域允许空）外必填
- [ ] realtime/rebuild retrieval entrypoint + snapshot + watermark + trace 齐全
- [ ] 无 Gold/expected/confirmation/凭据/用户正文
- [ ] adapter 只读验证 + preview/execute 权限范围已声明（`retrieval_profile`）
- [ ] 独立复核通过

## 9. 边界

- 不定义新 Dataset 字段、生产 selector 语义或检索算法；
- 不授权 adapter 创建测试目标或替换生产 selector；
- 不产生 formal raw / Seal / attestation / Runner / `D13D_FROZEN`；
- 不宣称解除 production default registration 的 `BLOCKED_BY_HOST_MAPPING`。
