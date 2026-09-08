# D14B Formal L3 执行 Runbook（准备模板，未授权正式运行）

## 0. 状态与用途

本文件固定 D14B 正式 handoff 后的命令顺序、输入文件和停止条件。它不是正式证据，
不创建 evidence root，也不授予 VM、重启、删除、重建或 OS reboot 权限。

当前状态：`D14B_PREPARATION = IN_PROGRESS`，`D14B_FORMAL_L3 = BLOCKED`，
`D14B_FORMAL_RESULT = UNVERIFIED`。

## 1. 固定 preparation 输入

- Controlled dataset contract：`tests/retrieval/fixtures/d14b_controlled_dataset_v1.json`。
  它只保存稳定 ID、版本 ID、受控用户和删除控制关系；**不含用户正文**。写入/删除只可经现有 production Repository/API/service path，不得复制业务 schema 或直接篡改索引。
- Checkpoint assembler：`scripts/capture_d14b_retrieval_snapshot.py`。
- Comparator：`scripts/compare_d14b_retrieval_snapshots.py`。
- Handoff gate：`scripts/run_d14b_preflight.py`。
- Evidence closure：`scripts/verify_d14b_evidence_manifest.py`。
- 删除 contract：`tests/vector-engine/run_d10b_vector_delete_l2.sh`。
- 指标：`scripts/run_d13b_formal_eval.py`。

## 2. Formal intake：未全部满足即停止

执行者先核对下列输入，任意缺失或不一致均不得创建 evidence root：

```text
D13D freeze_status = FROZEN
D14D release_status = L3_READY
D14A final package version/tar SHA/manifest SHA 已冻结
三方 tested_commit 与 manifest source_commit 相同
VM UUID / snapshot UUID / environment_id 与 D14D handoff 相同
checkout 的 HEAD == tested_commit，且 git status --porcelain 为空
```

在未存在的新路径上运行：

```text
python scripts/run_d14b_preflight.py \
  --expected-tested-commit <tested-commit> \
  --d13d-handoff <d13d-handoff.json> \
  --d14d-handoff <d14d-handoff.json> \
  --package-manifest <package-manifest.json> \
  --repo-root <exact-clean-checkout> \
  --evidence-root <absolute-new-root>
```

只有 exit 0 后，操作者才创建一次性 root：

```text
evidence/l3-kylin-vm/d14b_<UTC_RUN_ID>_<sha7>/
```

失败保留已有失败 root；重试使用新的 run ID。不得覆盖、补删或复用 root。

## 3. 每个 checkpoint 的生产 source artifacts

每次 capture 前，formal handoff/部署契约必须已给出且审批下列四个**实际命令**和其 runner identity：

```text
SQLite truth command  -> sqlite-truth.json
FTS5 query command    -> fts5-results.json
Vector query command  -> vector-results.json
RRF query command     -> rrf-results.json
```

每个 channel artifact 的格式为：

```json
{
  "queries": [{
    "query_id": "d14b-q-user-a",
    "results": [{"stable_id": "...", "user_id": "...", "version_id": "...", "rank": 1}]
  }]
}
```

SQLite truth 必须含 `stable_ids` 与 `active_version_ids`。source command 未交接、输出缺失、
JSON 非法或 output 已存在时，capture CLI fail-closed。D14B 不以手工 JSON 代替 production source。

标准 capture 命令：

```text
python scripts/capture_d14b_retrieval_snapshot.py \
  --tested-commit <tested-commit> --checkpoint <checkpoint> \
  --user-id <controlled-user> --captured-at-utc <UTC-Z> \
  --sqlite-truth <source-dir>/sqlite-truth.json \
  --fts5-results <source-dir>/fts5-results.json \
  --vector-results <source-dir>/vector-results.json \
  --rrf-results <source-dir>/rrf-results.json \
  --output <evidence-root>/<phase>/<checkpoint>.json
```

## 4. 机械生命周期顺序

1. 用 production path 初始化 controlled dataset；记录命令与 dataset contract SHA256。
2. Capture `baseline`；运行 D13B formal evaluation，保存 raw 与 report。
3. `systemctl --user restart kylin-memory`；确认 `systemctl --user is-active --quiet kylin-memory`，按 D14D handoff 的 socket/health/index-state command 核验；capture `service_restart_after`；运行 compare。
4. 仅调用交接中批准的 production rebuild entrypoint；capture `rebuild_after`；运行 compare。`missing_ids`、`unexpected_ids`、`duplicate_ids`、`ghost_hits`、`cross_user_hits`、`stale_version_hits` 均必须为 0。
5. 重跑 D10B delete contract；用 production 精确删除 delete target；capture delete 前后 SQLite/FTS5/Vector/RRF。删除 target residual 必须为 0，same-user、foreign-user、wrong-version control 必须保持。
6. Capture `reboot_before` 与 `/proc/sys/kernel/random/boot_id`；执行真实 OS reboot；确认 boot ID 已变、service active、socket/health/index state；capture `reboot_after`；运行 compare。
7. 通过 D13B formal evaluation 采集 FTS5/Vector/RRF 的 P50/P95；额外记录 mean/max/throughput、CPU、RAM、kernel、runtime、SDK/model。无已冻结阈值时只记录 delta，不写性能 PASS。
8. 重跑 B-track L0/L1 与 `git diff --check`；写正式报告；生成 SHA256SUMS；运行 evidence manifest closure；追加 `evidence/index.yaml`；再交独立 Reviewer。

## 5. Stop-the-line

任一情况立即停止当前 run，保留原始 bytes，且不通过手工改索引、补删或复跑同一 root 修复：

```text
identity / package / VM / snapshot mismatch
dirty checkout 或 HEAD mismatch
capture source 缺失或无 production runner identity
evidence root 已存在
cross_user / stale / ghost / duplicate 非零
删除对象在 SQLite、FTS5、Vector 或 RRF 任一通道残留
rebuild 复活已删对象
service/OS reboot 后状态不可验证
SHA256SUMS 不闭合
```

## 6. Preparation Review 目标

Reviewer 在正式 handoff 前仅审：preflight、controlled dataset、capture、compare、runbook、
manifest closure 和 fail-closed 行为。不得将此模板或 L0/L1 写成 L3 PASS、VERIFIED 或性能达标。
