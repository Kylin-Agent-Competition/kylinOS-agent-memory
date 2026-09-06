# D14D 当前状态与 Phase 0 准备（2026-09-06 · Draft）

> 状态：`DRAFT`。本文件是 D14D 作为独立载体重新发布的入口说明；正文记录
> 2026-09-06 仲裁与收敛后的任务现状。D14D 交付物此前随 PR #150 进入过审，评审返工时
> 已从 #150 迁出并按“独立 PR 发布”处理；本 PR 即该独立载体。

## 0. 任务

| 字段 | 值 |
| --- | --- |
| 任务 | D14D：L3 干净快照发布 Gate、安装生命周期、回退与证据闭环 |
| 责任轨道 | D |
| 工作类型 | `release/test-infrastructure`；不修改业务、IPC、Schema、数据库或 SDK ABI |
| 关联任务 | D13D 环境冻结、D13E 正式封存、D14A 发布包（PR #152）、D14B/C L3 发布回归 |
| 输出边界 | D14B 只消费 `L3_READY` 的干净快照与发布包输入；本 PR 不代表 D14D PASS |

## 1. 当前结论（两阶段状态模型）

按 2026-09-06 协调裁决（D-15），D14D 状态拆为两阶段，避免“环境准备”与
“正式 L3 / Release Gate”互相锁死：

```text
D14D_ENV_PREPARED = READY（候选已具备；正式身份工件按需冷启 r1 产出）
D14D_FORMAL_L3    = BLOCKED / PARTIAL（不是 L3_READY）
L3                = NOT_STARTED
D14A_FORMAL_L3_GO = NO
```

- `D14D_ENV_PREPARED` 不依赖 A final package、D13D_FROZEN 或 Ducknesses 第四轮 review；
  仅表示可供 D13D I3d 与 A package 对齐消费。
- `D14D_FORMAL_L3` 依赖 `D13D_FROZEN + A_FINAL_PACKAGE_READY + final tested commit/package hash`；
  正式 G0–G9 与 Release Gate 只在此阶段执行。

本 PR 禁止提前写入：`L3_READY`、`HOST_VERIFIED`、`production ready`、
`release ready`、`D14D complete`。

## 2. 当前已完成内容（2026-09-06）

### 2.1 仲裁、代码线与 CI 收敛

- D-01：以 PR #152 head 为唯一权威 packaging 代码线；本地 `5700d52`/
  `fix/d14a-release-lifecycle` 并行线按被替代归档为历史。
- D-03/D-04/D-05：contract §3/§6bis 统一为 `HANDOFF_REQUIRED`（SDK 全量 fail-closed；
  runtime/model 由正式 D14D G0 采集冻结）；契约升 `FROZEN v4`；正式 package version
  固定 `0.1.0-d14a`。
- D-14：packaging 4 个 Python 测试与 provenance 测试已加入 CI
  （`.github/workflows/baseline-check.yml` 新增 `d14a-packaging-provenance` job）。
- 当前收敛 head：`f24c29b685e4263f439e440d776455daaf56ba65`（PR #152 head；
  与 `02ca7a0a6370034f0918ea45809c7fcd2c1cd0f2` runtime/packaging 文件一致，
  后随提交仅 docs/CI）。
- GitHub CI：`Repository Baseline Check` PASS、`D14A packaging + provenance L1` PASS。
- L0/L1：PR head packaging + provenance 独立实测 `77 passed`（WSL；不替代麒麟 L3）。

仲裁明细与契约收敛记录已在 D14A 载体可见：
- [00_d14a_release_package_contract.md](00_d14a_release_package_contract.md)（#152 分支，FROZEN v4）
- [14_d14a_arbitration_record_20260906.md](14_d14a_arbitration_record_20260906.md)（#152 分支）

### 2.2 Phase A/B 收口（历史，不升级为正式 Gate）

- 5700d52 clean-VM run 已补齐 G9 归档（gate_matrix/checksums/summary/README），
  结论维持历史 `PARTIAL`。
- G1/G5 首跑失败与同 root 重试偏离已按原始日志分类：
  G1＝调用方漏传 `install` 子命令；G5＝reboot 后独立 embedding server 30s 未就绪、
  90s 重试通过（启动时序风险）；重试偏离“失败即停、另开 root”纪律已记录。
- packaging 双代码源对照完成；结论按 D-01 以 PR #152 head 收敛。
- 上述内容保留在本地工作分支（`chore/d14d-*`）与本地工作区 `docs/`，本次未随
  docs-only draft 推送；正式 run 与独立审查完成前不宣称 L3。

### 2.3 ENV_PREPARED 冻结值（候选）

| 项 | 值 | 状态 |
| --- | --- | --- |
| VM | `Kylin-D14D-clean-vdi-20260906`（UUID `70ca1ea3-c27e-483d-aaba-0cac7dc5c77c`） | 候选冻结 |
| 正式起点 snapshot | `d14d-clean-base-20260906-r1`（UUID `4eeade26-5cd3-4467-a31b-c7440c5b04e0`），poweroff 待命 | D-11 |
| OS | 银河麒麟桌面 V11（`KYLIN_RELEASE_ID=2603`；`dist_id=Kylin-Desktop-V11-2603-Release-20260228-X86_64`） | 正式 G0 现场重采 |
| kernel / arch | Linux `6.6.0-63-generic` / x86_64 | 正式 G0 现场重采 |
| SDK | `libkylin-coreai-embedding 1.2.0.0-0k0.4`；`.so` SHA `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` | FROZEN（D14D r1 raw / d14a evidence） |
| runtime / model | runtime `kylin-ai-runtime 1.2.0.4-0k0.1`；model `kylin-gte-base-model 1.0.0.1-0k0.9`（默认 `ensemble-embd_gte-base_uint8-text`） | 参考值；vendor/hash freeze = `HANDOFF_REQUIRED`，正式 G0 采集后升版 |
| Trust Root | candidate `D13E_TRUST_ROOTS_V1.json` + public PEM；`--trust-roots` 重验入口已定义 | 重验/Seal 属阶段二（D13D I3d / W6） |
| evidence root | `d14d_<UTC-RUN-ID>_<前7位SHA>`；预创建、空、不可复用、单次执行 | D-11 / Phase0 TaskCard |

## 3. 正式 Gate 状态（阶段二）

| Gate | 状态 | 说明 |
| --- | --- | --- |
| G0 基线 | BLOCKED | 需正式 tested_commit（f24c29b）工作树干净、runtime/model 身份 G0 采集、D13D FROZEN |
| G1 快照 | READY（起点） / NOT_RUN | r1 已 poweroff 待命；正式运行前从 r1 恢复 |
| G2 包审计 | NOT_RUN（工具 READY） | 正式包须从 tested_commit 重建并冻结 tar/manifest/SHA256SUMS |
| G3 安装 | NOT_RUN | 正式 run 未执行 |
| G4 真 SDK | NOT_RUN | 正式 run 未执行 |
| G5 服务重启 | NOT_RUN | 正式 run 未执行；等待语义=30s→90s→停止另开 root（D-07） |
| G6 OS 重启 | NOT_RUN | 正式 run 未执行 |
| G7 升级 | NOT_RUN / N/A | D-09 书面不适用；不得标 PASS |
| G8 性能 | NOT_RUN | D-10：package-only runner/阈值未批准 |
| G9 Evidence | NOT_RUN | 历史归档仅为 PARTIAL；正式 run 未产生 |

## 4. 阻塞项与外部动作

| 编号 | 阻塞 | 责任人 / 动作 |
| --- | --- | --- |
| B1 | Ducknesses 第四轮 review 未执行；PR #152 `reviewDecision=CHANGES_REQUESTED`（head f24c29b） | D 主审 / Ducknesses 复审 |
| B2 | D13D FROZEN 未闭合；TD-061 Open（High）；无 Seal / 17 raw / Runner Gate 0–10 | D13D 实施方 / D Reviewer |
| B3 | runtime/model 依赖为 `HANDOFF_REQUIRED`，未在正式 G0 采集冻结 | D14D 执行（正式 run） |
| B4 | 正式 package 未从 tested_commit 重建 / hash 未冻结 | A/D14D（G2/G3 解锁后） |
| B5 | G8 package-only runner/阈值未批准 | D 主审 + D13A owner |
| B6 | 正式 evidence root 上 G0–G9 未执行、非作者独立审查未完成 | D14D 执行 + D/E Reviewer |

## 5. 下一步（不在本 draft 内代执行）

1. PR #152 完成第四轮 review 会签（或依最新 review 状态同步）；
2. D13D 在收敛 `tested_commit` 上闭合 FROZEN（TD-061、Seal、17 raw、Runner Gate 0–10）；
3. 从 `tested_commit` 重建唯一正式发布包并冻结身份/hash；
4. 从 r1 恢复并在预建、不可复用的 evidence root 上执行正式 G0–G9；
5. 非作者独立审查与 D 主审唯一结论（`L3_READY / PARTIAL / REWORK / BLOCKED`）发布。

## 6. Reviewer 检查重点

- 是否守住“ENV_PREPARED ≠ PASS；FORMAL_L3 未闭合前不得 L3_READY”边界；
- 本 draft 是否未虚报正式 VM G0–G9、D13D FROZEN、D14A 最终包或 D14D 完成；
- 状态值（`f24c29b` / `02ca7a0` / `0.1.0-d14a` / r1 snapshot / SDK identity）是否与
  PR #152、契约 v4 与本地仲裁记录一致；
- 历史 PARTIAL run 是否仅作历史证据、未升级为正式 PASS。
