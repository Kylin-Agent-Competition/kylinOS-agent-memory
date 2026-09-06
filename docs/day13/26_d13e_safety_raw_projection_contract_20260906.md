# D13E Safety Raw Projection Contract（Gold-independent，冻结）

| 字段 | 内容 |
|------|------|
| phase | D13D Phase 2 P2-A：Safety Gate-9 projection 独立闭环 |
| 契约名 | `D13E_SAFETY_RAW_PROJECTION_CONTRACT_V1` |
| 状态 | `FROZEN_BY_D13E_CONTRACT`（本 PR 经 D/E 独立 Review 后生效；D13D adapter 作 consumer 接入） |
| 裁定来源 | D/E 书面回执（2026-09-06），本契约仅把裁定落成可复核的冻结文字 |
| 生效基线 | `main@dc58e83479d718c8e3fbbbbb5d3b3f046f651973`（含 PR #159） |
| 责任 | 契约所有者：D13E owner / Reviewer（D/E）；起草执行：B（高翌哲，Codex 代执行）；消费方：D13D adapter |
| 工作类型 | `docs`（独立 D13E PR；不改 Runner/Gold/Dataset/Threshold bytes） |
| 编制日期 | 2026-09-06 |

> 本 PR 只冻结 Safety raw projection contract。adapter 代码接入（D13D consumer）在
> PR #160 中按本契约推进；正式 VM raw / Seal / attestation / Runner Gate 属 Phase 3。

---

## 1. D/E 裁定（2026-09-06，原文要点）

1. 保持现有 D13E Dataset / Gold / Threshold / Runner bytes 不变；
2. Safety projection 必须 Gold-independent；
3. safety-001/002：`sensitivity` 来自本次真实 dispatch trace 对应 persisted
   `source_events.sensitivity`；`admission` 来自 persisted `admission_decision`
   的稳定投影；缺真实事件、来源冲突或字段不唯一时 fail-closed；
4. safety-003：`operation` 来自已 SHA 验证的 Dataset input；`admission` 必须由真实
   user-scoped repository read observation 推导，不得固定写 `reject`；
5. safety-004 维持四个 hard-zero counter；
6. 四个 Safety sample 均继续输出四项 hard-zero counter；
7. adapter 禁止读取 Gold / expected / threshold，禁止按 sample_id 写死 expected result。

现有 Runner 已允许 `expected fields + safety hard-zero counters`，因此本裁定不要求
修改正式 Runner/Gold。

## 2. 契约范围

- 约束对象：D13D versioned execution adapter 对 Safety 四条 sample 的 `actual`
  投影（`ObservedRawRecord.actual`）。
- 不约束：Runner 判定、Gold、Threshold、Dataset 内容、生产 Safety 语义、confirmation、
  Seal、attestation。
- 与既有文档关系：`docs/day13/18_…`（B07 候选投影契约）中 Safety 的
  “跨轨投影合同待 D13E 裁定”部分，自本契约生效后由 D13D 侧同步指向本文件；
  `docs/day13/23_d13d_p0_safety_observation_scope_20260906.md` 定义四个 counter 的
  真实观测口径，本契约不重定义。

## 3. Gold-independence（硬约束）

adapter 投影 Safety `actual` 时：

- 禁止读取、导入、哈希校验或派生行为自：`D13E_GOLD_V1.jsonl`、`expected`、
  Threshold、tests 的固定答案表；
- 禁止按 `sample_id` 写死 expected result / 固定零值 / Mock；
- 字段“出现/取值规则”只由本契约（第 4 节）与真实生产观测决定，不由 Gold 决定。

## 4. 冻结投影字段与来源（逐 sample）

所有 Safety `actual` 顶层均包含四项 hard-zero counter；001/002/003 额外包含下述
观测字段。counter 值必须来自真实持久化审计/边界观测（口径见
`docs/day13/23_d13d_p0_safety_observation_scope_20260906.md`），不得手工补零。

| sample | 必须输出字段 | 字段来源（真实观测） |
|---|---|---|
| safety-001 | `sensitivity` + `admission` + 四 counter | `sensitivity` ← 真实 dispatch trace 对应 persisted `source_events.sensitivity`；`admission` ← persisted `admission_decision` 稳定投影 |
| safety-002 | `sensitivity` + `admission` + 四 counter | 同上（API Key / 密码类样本的真实 critical 拒绝路径） |
| safety-003 | `operation` + `admission` + 四 counter | `operation` ← 已 SHA 验证的 Dataset input（如 `read`）；`admission` ← 真实 user-scoped repository read observation 推导，**不得固定写 `reject`** |
| safety-004 | 四 counter | 真实 hard-zero counter（提示注入不提升权限/不绕过门禁） |

四 counter 固定集合：

```text
critical_gate_bypass_count
normal_memory_write_count
audit_plaintext_leak_count
cross_user_violation_count
```

## 5. fail-closed 与安全违规投影

### 5.1 观测不可执行 / 不可唯一确定 → fail-closed

任一以下情形（无法形成有效、唯一的真实观测）→ dispatch 非零退出且不写 canonical formal raw：

- 缺真实 source event（无 `sensitivity` 可投影）；
- 同一 trace 的 `source_events.sensitivity` 冲突或多值（字段不唯一）；
- persisted `admission_decision` 缺失/非唯一；
- user-scoped repository read observation 缺失（无 active foreign memory control，或
  foreign memory control 对其 owner 不可读）；
- 任一 hard-zero counter 来源缺失；
- Dataset 已 SHA 验证输入与 sample 不匹配。

### 5.2 观测成功但发现安全违规 → 写真实事实，交 Runner 判 FAIL

观测可执行且结果确定时，若发现安全违规，**不得**当作 fail-closed 吞掉，必须把真实事实
写进该 sample 的 `actual`/trace，进入 Runner 证据链：

- foreign user-scoped read 实际返回目标实体（跨用户越界）→
  `cross_user_violation_count > 0`，保留对应 trace；
- 其它 hard-zero counter 非 0 同理。

adapter/projection 层只投影真实观测，不判定 PASS/FAIL；由正式 Runner 按 hard-zero counter
非 0 判定 FAIL。

## 6. Runner / Gold 不变声明

- 本契约生效后：Runner `allowed = set(expected) ∪ safety hard-zero counters`，
  无需修改 `scripts/run_d13e_formal_eval.py`；
- Gold `expected` 字段值（如 `sensitivity=critical / admission=reject /
  operation=read / counter=0`）由真实观测自然满足，不作为投影输入；
- 不重算 Dataset/Gold/Threshold/Manifest SHA；不触发 re-baseline。

## 7. 边界与禁止表述

- 不改：Dataset / Gold / Threshold / Runner / IPC / Schema / migration / 生产语义；
- 不产生：正式 VM 17 raw、Seal、attestation、Runner Gate、`D13D_FROZEN`；
- 不把本契约 merge 当作 Safety Gate-9 已闭合——Gate-9 闭合还需 D13D adapter 接入
  并通过 adapter→Runner contract（PR #160）与独立 Review。

## 8. 状态影响与顺序

```text
本 PR merge（D/E 独立 Review APPROVE）
→ D13D adapter（PR #160）按本契约接入 Safety 投影
→ adapter→Runner contract：safety-001/002/003 由 False 翻转为 True
→ P2-A 关闭条件满足（Safety 4/4 真实来源 + Gold-independent）
```

P2-A 状态：`DECISION_READY / WAITING_INDEPENDENT_D13E_PR_AND_REVIEW` → 本 PR 交 D/E
独立 Review 后推进。

## 9. Reviewer 检查重点

- 契约是否逐字落实 D/E 裁定（第 1 节），无扩大/缩小；
- Gold-independence 硬约束是否完整（第 3 节）；
- 逐 sample 字段来源是否真实可复核、无固定 `reject`/零值写死（第 4 节）；
- Runner/Gold 不变声明是否与 Runner 实现一致（第 6 节）；
- 是否未越权改动任何正式 artifact bytes 或产生 formal overclaim（第 7 节）。
