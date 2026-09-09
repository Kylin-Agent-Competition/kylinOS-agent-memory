# D14B L3 Formal Harness 与证据契约（2026-09-07）

## 1. 状态与边界

| 字段 | 值 |
| --- | --- |
| D14B 分支 | `test/D14B-l3-vm-release-regression` |
| 历史准备基线 | `8cc4a89e34ca7ec73563c798a46339721f291139`（仅历史） |
| 历史开发基线 | `3430a1f`（合并 `origin/main@ba3b50e` 后的历史 D14B 开发基线） |
| 当前开发基线 | `c1443aaecc82a79b9b9f835664ba5e4fee5edfc2`（合并 `origin/main@632b24b` 后的本地 D14B HEAD） |
| 上游 SSOT（尚未合并至本分支） | `origin/main@77826122a8aa1eaeed60ec9295a4bb8f979b3fe7` 的 `docs/D_TRACK_STATUS.md` |
| formal tested_commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（已核验；待在精确干净 checkout 消费） |
| D13D_FROZEN | `YES`（D13D freeze record，2026-09-08） |
| D14D_L3_READY | `YES`（D14D final review / `docs/D_TRACK_STATUS.md`） |
| final package/hash | `FROZEN`（`kylin-memory-a-d14a 0.1.0-d14a`；tar `2222c904…b401`；manifest `76a839…fc0`） |
| D14B_FORMAL_L3 / RESULT | `PENDING_LOCAL_INTAKE / UNVERIFIED` |

本批只提供 B 轨的只读 harness、比较口径及证据布局；不创建正式 evidence root，
不运行 VM、不操作 D14D/D13D 环境，也不把本地 L0/L1 结论描述为 L3 PASS。

2026-09-08 远端主线 SSOT 已登记 D13D Phase 3 formal closure、D14D final review 和
D14A package/hash freeze。D14B 已只读核验以下上游记录：

- `docs/D_TRACK_STATUS.md`（状态与共同 `tested_commit`）；
- `evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/D13D_FREEZE_RECORD_20260908.md`；
- `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/{snapshot_identity.json,package_build_identity.json}`；
- `evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md`。

这些记录证明上游身份一致，但当前分支尚未合并该主线，且没有可直接交给本工具的
标准化 `d13d-handoff.json` / `d14d-handoff.json`；更不能由 D14B 自行编造它们。正式
操作者仍须交接结构化输入，以及四类 production capture command 和 runner identity。

## 2. Formal preflight

入口：`scripts/run_d14b_preflight.py`。

```text
python scripts/run_d14b_preflight.py \
  --expected-tested-commit <tested-commit> \
  --d13d-handoff <d13d-handoff.json> \
  --d14d-handoff <d14d-handoff.json> \
  --package-manifest <package-manifest.json> \
  --repo-root <exact-clean-checkout> \
  --evidence-root <absolute-new-root> \
  --capture-handoff <d14b-capture-handoff.json> \
  --package-tar <actual-frozen-tar> \
  --actual-package-manifest <actual-frozen-manifest.json>
```

它要求的最小交接字段如下。所有 SHA 均为小写十六进制。

```json
{
  "d13d": {
    "freeze_status": "FROZEN",
    "tested_commit": "<40-hex>",
    "freeze_reference": "<可定位的 Seal/summary 引用>"
  },
  "d14d": {
    "release_status": "L3_READY",
    "tested_commit": "<同一 40-hex>",
    "evidence_reference": "<可定位的 D14D G9 引用>",
    "package": {
      "package_version": "<version>",
      "package_tar_sha256": "<64-hex>",
      "package_manifest_sha256": "<64-hex>"
    },
    "vm": {
      "vm_name": "<name>",
      "vm_uuid": "<uuid>",
      "snapshot_name": "<name>",
      "snapshot_uuid": "<uuid>",
      "environment_id": "<id>"
    }
  },
  "manifest": {
    "source_commit": "<同一 40-hex>",
    "package_version": "<同一 version>",
    "package_tar_sha256": "<同一 64-hex>",
    "package_manifest_sha256": "<同一 64-hex>"
  }
}
```

preflight fail-closed：任一 commit/package 不一致、D13D 非 `FROZEN`、D14D 非
`L3_READY`、Seal/G9 引用不是既有仓库路径或 HTTPS URL、evidence root 已存在、工作树
非干净或 HEAD 不同、已声明 runner 的路径/哈希不可验证，都会返回非零状态。它成功时也**不**创建 evidence root；正式
操作者在成功后才能创建一次性 root。

正式 preflight 另强制两道机器门禁：
- **P1-3 capture provenance**：`--capture-handoff` 必须声明 SQLite/FTS5/Vector/RRF
  四类 runner（path 不越 repo、实际 SHA-256 == 声明、command_id 非空、tested_commit
  一致），任一缺失/不一致即 `D14B_PREFLIGHT_FAIL`；每个 source artifact 还必须带
  `.receipt.json`（channel/commit/command_id/runner SHA/artifact SHA），capture 逐项
  校验后才汇编 checkpoint，手工 JSON 无 provenance 一律拒绝。
- **P2-1 package bytes**：`--package-tar`/`--actual-package-manifest` 现场计算 SHA-256
  并校验 == 冻结值，且 manifest `source_commit`/`package_version` 与 tested_commit/冻结
  version 一致；改字节/改语义均 FAIL CLOSED。
- **comparator（P1-1/P1-2）**：SQLite truth `stable_ids`/`active_version_ids` 在
  before/after 两侧机械比较（非 Top-K 增删同样 FAIL）；before/after 各做
  duplicate/cross-user/stale/ghost 合法性检查；comparison output 采用 exclusive-create，
  已存在即拒绝覆盖。comparator 仅用于 service restart / rebuild / OS reboot 的
  invariant 比较，不用于 delete。

## 2bis. Provenance retention（R3）

正式 evidence root 固定保留 provenance 原始 bytes，纳入 SHA256SUMS 闭包：

```text
evidence/l3-kylin-vm/d14b_<UTC_RUN_ID>_<sha7>/
  provenance/d14b-capture-handoff.json      # 每个 root 只保存一次，不可覆盖
  <phase>/<checkpoint>.json
  <phase>/provenance/<checkpoint>/          # 每次 capture 实际消费的 4 份 receipt
    sqlite-truth.receipt.json
    fts5-results.receipt.json
    vector-results.receipt.json
    rrf-results.receipt.json
  SHA256SUMS
```

### Required lifecycle checkpoints

Formal evidence verifier 不采用 JSON heuristic discovery。下列路径是唯一接受的
lifecycle checkpoint 集合；每一个都必须是进入 `SHA256SUMS` 的 regular file，含完整
checkpoint schema，且内部 `checkpoint` 值必须与路径中的 ID 相同。缺失、schema
不完整或路径/ID 不一致一律 fail-closed。

```text
baseline/baseline.json                         # baseline
service_restart/service_restart_after.json     # service_restart_after
rebuild/rebuild_after.json                     # rebuild_after
delete/delete_before.json                      # delete_before
delete/delete_after.json                       # delete_after
os_reboot/reboot_before.json                   # reboot_before
os_reboot/reboot_after.json                    # reboot_after
```

`baseline.tested_commit` 是本次 formal run 的 commit；其余六个 checkpoint 及全局
capture handoff 的 `tested_commit` 必须完全一致。evidence root、`SHA256SUMS` 与 root
内任意路径均不得为 symlink。

checkpoint 的 `capture_sources` 扩展为可独立复核的 provenance 摘要：

```json
{
  "sqlite_truth": {"artifact_sha256": "...", "receipt_sha256": "...", "command_id": "...", "runner_sha256": "...", "runner_path": "..."},
  "fts5": {...}, "vector": {...}, "rrf": {...},
  "capture_handoff_sha256": "..."
}
```

receiver/reviewer 离线复算规则：root 内 handoff/receipt bytes 必须与 checkpoint 登记的
SHA 一致，且全部文件（含 provenance）都经 `verify_d14b_evidence_manifest.py` 的
SHA256SUMS 闭合；缺失或篡改任何 retained provenance bytes 即 FAIL。

## 3. 快照和比较口径

入口：`scripts/compare_d14b_retrieval_snapshots.py`。

```text
python scripts/compare_d14b_retrieval_snapshots.py \
  --before baseline.json --after after.json --output comparison.json
```

每个 checkpoint 记录 `tested_commit`、`checkpoint`、受控 `user_id`、SQLite 的
`stable_ids` 与 `active_version_ids`，以及 `fts5`、`vector`、`rrf` 每个
`query_id` 的有序 `stable_id/user_id/version_id/rank` 结果。比较器只读，输出：

```text
missing_ids / unexpected_ids / duplicate_ids / rank_changes
cross_user_hits / stale_version_hits / ghost_hits
```

没有上述差异才返回 `PASS`。浮点 score 可作为原始采集信息保留，但并不以字节级
score 相等代替 stable identity、用户/版本范围及 Top-K 顺序比较。

### 3.1 Checkpoint capture

入口：`scripts/capture_d14b_retrieval_snapshot.py`。它只读取四个由既有 production
Repository/API/service path 产生的 JSON artifact，校验输入结构、记录每个 artifact 的
SHA256，并写出一次性 checkpoint；它不连接服务、不写 SQLite、不建/删索引，也不允许
覆盖已有 evidence 文件。

```text
python scripts/capture_d14b_retrieval_snapshot.py \
  --tested-commit <tested-commit> \
  --checkpoint <checkpoint> \
  --user-id <controlled-user> \
  --captured-at-utc <UTC-Z> \
  --capture-handoff <evidence-root>/provenance/d14b-capture-handoff.json \
  --sqlite-truth <source-dir>/sqlite-truth.json \
  --sqlite-receipt <source-dir>/sqlite-truth.receipt.json \
  --fts5-results <source-dir>/fts5-results.json \
  --fts5-receipt <source-dir>/fts5-results.receipt.json \
  --vector-results <source-dir>/vector-results.json \
  --vector-receipt <source-dir>/vector-results.receipt.json \
  --rrf-results <source-dir>/rrf-results.json \
  --rrf-receipt <source-dir>/rrf-results.receipt.json \
  --output <evidence-root>/<phase>/<checkpoint>.json
```

生产 capture source command 不是 D14B 自造的业务实现：正式 handoff 必须为每个
artifact 提供已批准的 command/path 与 runner identity。缺任意 source artifact 或其
来源未获交接时，D14B 停止，不生成“手工补录”的 checkpoint。

## 4. 证据布局与闭合

正式 root 仅在 intake 完成后创建：

```text
evidence/l3-kylin-vm/d14b_<UTC_RUN_ID>_<sha7>/
  README.md
  environment.json
  handoff_identity.json
  commands.log
  baseline/baseline.json
  service_restart/service_restart_after.json
  rebuild/rebuild_after.json
  delete/delete_before.json
  delete/delete_after.json
  os_reboot/reboot_before.json
  os_reboot/reboot_after.json
  comparisons/{service_restart,rebuild,reboot,delete_residual}.json
  performance/{raw,summary,comparison}.json
  l0_l1/pytest.log
  SHA256SUMS
```

失败也保留原始 root，重试另建新 root；不得覆盖历史 raw。最终使用
`scripts/verify_d14b_evidence_manifest.py --evidence-root <root>` 复核：
`SHA256SUMS` 必须逐字节匹配 root 内的全部 regular files（排除自身），且拒绝
遗漏、多余、重复、绝对路径和路径穿越条目。

## 5. 复用的既有 B 轨入口

- 删除 L2：`tests/vector-engine/run_d10b_vector_delete_l2.sh --binary <绝对路径/vector_bridge_cli>`；正式 run 必须在 final VM/final commit 重跑，历史 15/15 仅作参考。
- 正式评测：`PYTHONPATH=memory-service python scripts/run_d13b_formal_eval.py <bundle.json> --output <report.json>`；沿用 Recall@K、MRR、nDCG@K、P50/P95，不建立第二套指标实现。
- D14B formal VM 后仍须重跑现有 retrieval 与 delete contracts；本次 harness 的 L0/L1 只证明 gate/compare/evidence 工具本身。

## 6. 当前可交付与剩余项

| 项 | 状态 | 验证 |
| --- | --- | --- |
| 分支同步与旧 baseline 降级 | 完成 | D14B merge `c1443aa`（含 main `632b24b` / #166）；`3430a1f` 仅保留为历史开发基线 |
| preflight | 完成 | commit/FROZEN/L3_READY/root fail-closed tests |
| snapshot compare | 完成 | missing/duplicate/cross-user/stale/exact tests |
| checkpoint capture | 完成（只读汇编） | input SHA256 + schema + no-overwrite tests；production source command 待 formal handoff |
| evidence closure | 完成 | SHA256SUMS valid/extra-file tests |
| D13D/D14D formal identity | 已核验（上游） | 同一 `ba3b50e…`、D13D `FROZEN`、D14D `L3_READY`、冻结包 hash |
| 标准化 D14B intake | 待交接 | `d13d-handoff.json`、`d14d-handoff.json`、production capture command 与 runner identity |
| 正式 VM 生命周期、性能和报告 | 未开始 | 唯一 formal root 上机械执行 |

本文件更新原因：原 D14B 任务卡的开发基线仍指向 2026-09-02 的历史 SHA，且缺少
可执行的交接验证与机器比较口径。本次将准备阶段的基线、工具与证据规则显式化；
不改变任何既有正式结论或 runtime 能力状态。
