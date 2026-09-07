# D14D Phase0 Formal Start Replacement Arbitration

> **Status: `DRAFT_PENDING_NON_AUTHOR_CONFIRMATION`**
> 本记录响应 PR #165 Review HIGH-02（2026-09-07T14:37Z）：Formal 起点从
> authoritative Phase0 r3/r2 lineage 切换为 r1→r4，缺少 replacement arbitration。
> 本记录由 D14D 执行方起草；在非作者（Reviewer E 或 D 主审）确认前不得视为
> authoritative Phase0 replacement 生效。确认后本记录状态改为
> `CONFIRMED`，`evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e` 消费的
> r4 起点随之成为正式 Formal start。

## 1. 原 authoritative Phase0 起点（PR #159 合并后）

| 项 | 值 |
| --- | --- |
| Evidence root | `evidence/phase0/d14d-env-prepared-20260906-r3/`（ACTIVE） |
| VM | `Kylin-V11-2603-BTrack-Base`，UUID `103fb8a8-cc85-4897-836a-70b68edb5745` |
| Formal start snapshot | `d14d-clean-base-20260906-r2`，UUID `c5e3c3de-1c70-4f58-b22a-ab07b2d2d56d` |
| Kernel | `6.6.0-63-generic` |
| Installed packages | 2030 |
| SSH | host `127.0.0.1:2222` |

## 2. 原起点不可消费的原因

PR #165 Formal run 准备时复核当前宿主 VirtualBox registry，r2 snapshot
`c5e3c3de-…` 不存在于可恢复条目中（VM `Kylin-V11-2603-BTrack-Base` 同样
不可用）。该结论记录于正式 evidence root 的
`snapshot_identity.json → deviation.status =
NOT_PRESENT_IN_CURRENT_VIRTUALBOX_REGISTRY`。

处置原则：不冒充 r2、不用其他 snapshot 改名顶替，而是按 fail-closed 纪律
在可用 D14D VM 上重建等价 clean 起点，并把血缘差异显式登记。

## 3. r4 起点重建过程（全部有 raw 证据）

1. 恢复 `Kylin-D14D-clean-vdi-20260906` 的 r1 snapshot
   `d14d-clean-base-20260906-r1`（UUID `4eeade26-5cd3-4467-a31b-c7440c5b04e0`）。
2. r1 已知存在唯一 build 残留（`13_d14d_l3_current_status_20260906.md` HIGH-1）；
   本次清除该残留后重跑 fail-closed clean-state Gate。
3. 正向 Gate：8 类 count 全 0 → `CLEAN_STATE_PASS` / exit 0
   （`raw/g0_baseline.log` 内 clean-state probe；结果固化于
   `environment_identity.json → clean_state_probe`）。
4. 负向 Gate：受控注入 build 目录 → `build_dir_count=1` →
   `CLEAN_STATE_FAIL`（`raw/g1_negative_gate.log`），证明 Gate 本身
   fail-closed 有效。
5. Gate 通过后创建 snapshot `d14d-clean-base-20260907-r4`
   （UUID `6dc9468e-36a8-41b3-b7c9-6115c7b8fc56`）作为 Formal start。

## 4. 新旧起点身份对照

| 项 | r3/r2（原 authoritative） | r4（本次 Formal start） | 等价性 |
| --- | --- | --- | --- |
| OS release | Kylin V11，`KYLIN_RELEASE_ID=2603` | 同 `2603` | 一致 |
| Kernel | `6.6.0-63-generic` | `6.6.0-76-generic` | 差异（如实登记） |
| Installed packages | 2030 | 2036 | 差异（如实登记） |
| SDK `.so` SHA-256 | `028e7099c8434ee2…` | `028e7099c8434ee2…` | 一致（FROZEN） |
| Runtime binary SHA-256 | `b3f83fc90966394e…` | `b3f83fc90966394e…` | 一致 |
| GTE model ONNX SHA-256 | `cef0fc76165ee5bb…` | `cef0fc76165ee5bb…` | 一致 |
| Clean-state Gate | fail-closed（r3 修正版脚本） | 同等 fail-closed + 负向对照 | 等价或更强 |
| VM / snapshot | `103fb8a8…` / `c5e3c3de…` | `70ca1ea3…` / `6dc9468e…` | 不同血缘 |
| SSH | 2222 | 2223 | 宿主端口差异，无语义影响 |

## 5. 等价性论证与边界

- 三个冻结依赖（SDK / runtime / model）SHA-256 与 r3/r2 记录逐位一致，
  OS release 一致，clean-state Gate 同为 fail-closed 且本次额外保留了
  负向对照证据；
- 本记录**不宣称**两套环境逐位等同：kernel 补丁级、包数量、VM/snapshot
  血缘均不同，全部如实登记；
- 原 r3/r2 evidence roots 不删除、不改写，标记为
  `SUPERSEDED_BY_START_REPLACEMENT` 历史保留；
- 若非作者不接受本仲裁，Formal L3 须回到原 r2 血缘（若恢复可得）或
  重新走 Phase0 准备流程。

## 6. 请求的裁定

请非作者确认以下两项之一：

1. **ACCEPT**：接纳 `d14d-clean-base-20260907-r4` 为 D14D Formal start
   replacement；本记录转 `CONFIRMED`；
2. **REJECT**：说明理由；Formal L3 按第 5 节边界回退。

## 7. 证据指针

- 新 Formal run evidence root：
  `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/`
  （`snapshot_identity.json` / `environment_identity.json` /
  `dependency_identity.json` / `raw/g0_baseline.log` / `raw/g1_negative_gate.log`）
- 原 authoritative Phase0：
  `evidence/phase0/d14d-env-prepared-20260906-r3/`（`snapshot_identity.json`）
- 触发本仲裁的 Review：PR #165 Review HIGH-02（2026-09-07T14:37Z）
