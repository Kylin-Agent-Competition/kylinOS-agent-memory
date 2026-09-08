# D14B L3 Formal Harness 与证据契约（2026-09-07）

## 1. 状态与边界

| 字段 | 值 |
| --- | --- |
| D14B 分支 | `test/D14B-l3-vm-release-regression` |
| 历史准备基线 | `8cc4a89e34ca7ec73563c798a46339721f291139`（仅历史） |
| 历史开发基线 | `3430a1f`（合并 `origin/main@ba3b50e` 后的历史 D14B 开发基线） |
| 当前开发基线 | `c1443aaecc82a79b9b9f835664ba5e4fee5edfc2`（合并 `origin/main@632b24b` 后的本地 D14B HEAD） |
| formal tested_commit | `PENDING_D13D_D14D_HANDOFF` |
| D13D_FROZEN | `NO` |
| D14D_ENV_PREPARED | `READY`（Phase0 r3，不能等同于 L3） |
| D14D_L3_READY | `NO` |
| final package/hash | `NOT_FROZEN` |
| D14B_FORMAL_L3 / RESULT | `BLOCKED / UNVERIFIED` |

本批只提供 B 轨的只读 harness、比较口径及证据布局；不创建正式 evidence root，
不运行 VM、不操作 D14D/D13D 环境，也不把本地 L0/L1 结论描述为 L3 PASS。

2026-09-07 主线已合入 D13D I3b-completion（#160），包括双通道 Forget 观测及
SQLite→Vector 重建输入快照；其状态仍为 Phase 3 `PREPARATION / NON-FORMAL`，不产生
`D13D_FROZEN`。D14B 只消费正式 handoff，不把该准备证据提升为 formal input。

2026-09-08 主线已合入 E 轨 M1 schema snapshot 闭合（#166）。本分支将
`origin/main@632b24b` 合并为当前开发基线，仅用于接口与依赖对齐；它不提供
`D13D_FROZEN`、`D14D_L3_READY` 或 final package/hash，故不改变 formal 状态。

## 2. Formal preflight

入口：`scripts/run_d14b_preflight.py`。

```text
python scripts/run_d14b_preflight.py \
  --expected-tested-commit <40-hex> \
  --d13d-handoff <d13d-handoff.json> \
  --d14d-handoff <d14d-handoff.json> \
  --package-manifest <manifest.json> \
  --repo-root <clean-worktree> \
  --evidence-root <new-absolute-root>
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
  --tested-commit <40-hex> --checkpoint <name> --user-id <controlled-user> \
  --captured-at-utc <ISO-8601-Z> \
  --sqlite-truth <sqlite-truth.json> \
  --fts5-results <fts5-results.json> \
  --vector-results <vector-results.json> \
  --rrf-results <rrf-results.json> \
  --output <new-checkpoint.json>
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
  baseline/{sqlite_counts,retrieval_fts5,retrieval_vector,retrieval_rrf,retrieval_formal_eval}.json
  service_restart/{before,after}.json
  rebuild/{before,after,comparison}.json
  delete/{before,after,residual}.json
  os_reboot/{before,after,boot_identity}.json
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
| D13D/D14D formal handoff | 阻塞 | 等 `FROZEN` + `L3_READY` + final identity |
| 正式 VM 生命周期、性能和报告 | 未开始 | 唯一 formal root 上机械执行 |

本文件更新原因：原 D14B 任务卡的开发基线仍指向 2026-09-02 的历史 SHA，且缺少
可执行的交接验证与机器比较口径。本次将准备阶段的基线、工具与证据规则显式化；
不改变任何既有正式结论或 runtime 能力状态。
