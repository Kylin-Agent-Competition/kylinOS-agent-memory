# D14D 人工仲裁记录（2026-09-06，回填到 PR #152 收敛分支）

> 依据：工作区 `docs/D14D_人工裁决明细清单_20260906.md`。本文件记录已回填裁决中与本
> PR/契约/CI 直接相关的项，供 Ducknesses 第四轮复审与 D14D 后续执行引用。

## 已回填裁决摘要

| 编号 | 裁决 | 影响 |
| --- | --- | --- |
| D-01 | 以 PR #152 head `02ca7a0` 为唯一权威 packaging 代码线 | 本地 `5700d52`/`fix/d14a-release-lifecycle` 并行线按被替代归档 |
| D-02 | 第四轮复审对象=`02ca7a0`（或契约修正后收敛 head）；范围接受；放行级别 `PACKAGE_IMPLEMENTATION_CANDIDATE` | Ducknesses 实际 review 仍未发生，本裁决不替代 |
| D-03 | BLOCKER C=`HANDOFF_REQUIRED`；正式 D14D G0 采集冻结 runtime/model 身份 | 契约 §3/§6bis 已统一，install 只对 SDK 全量 fail-closed |
| D-04 | 四身份模型接受；§3/§6bis 统一后契约升 FROZEN v4 | 本分支契约已升 FROZEN v4 |
| D-05 | 正式 package version 固定 `0.1.0-d14a` | manifest/VERSION/EXPECT_PACKAGE_VERSION 对齐该值 |
| D-07 | `tested_commit`=`02ca7a0`（契约修正后以最终收敛 head 为准）；G5=30s→90s→停止另开 root | D14D Phase 0 task card 待最终 head 固化后签署 |
| D-09 | G7 本轮 `NOT_RUN / N/A` | 不阻塞 packaging 代码线与正式 G0–G6 |
| D-10 | G8 本轮 `NOT_RUN` | 需要 D13A owner 提供 package-only runner/阈值 |
| D-11 | 正式 Phase 4 纪律：预建不可复用 root、失败即停；VM 起点=r1 | D14D 正式 run 执行规则 |
| D-13 | 方向：推送收敛分支并把复审材料同步至 PR #152 | 执行须用户授权，本记录不擅自 push |
| D-14 | packaging 4 测试 + provenance 测试加入 CI | 本分支已新增 `d14a-packaging-provenance` job |

## 状态

- 契约：`FROZEN v4`（[00_d14a_release_package_contract.md](00_d14a_release_package_contract.md)）。
- 实施报告：已同步仲裁收口（[01_d14a_implementation_report_20260905.md](01_d14a_implementation_report_20260905.md)）。
- CI：新增 packaging/provenance L1 job（`.github/workflows/baseline-check.yml`）。
- L0/L1：本地 WSL 对 head `02ca7a0` 与契约修正后分支均实测 `77 passed`。
- 未闭合（外部）：D-02 Ducknesses 实际 review、D-08 D13D SEAL/raw/Runner、TD-061；
  因此在正式 run 前，D14D 结论仍为 `PARTIAL / BLOCKED`，不得标 `L3_READY`。
