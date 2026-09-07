# D14D_ENV_PREPARED — evidence package r3（2026-09-06 · ACTIVE）

## 状态

```text
D14D_ENV_PREPARED = READY（r3 ACTIVE；fail-closed Gate 脚本 + 正/负向证据）
D14D_PHASE0       = r1/r2 SUPERSEDED（历史）；r3 ACTIVE
D14D_FORMAL_L3    = NOT_STARTED（未执行 install/restart/reboot/rollback/release gate）
D14A_FORMAL_L3_GO = NO
```

r3 为第三轮 Review（Review ID 5124446136 后续）要求的修正版 ACTIVE root：
- r2 已提交且不可改写；其 raw 未保存可复核的 fail-closed probe 脚本/命令，
  且 r2 内 `evidence_root_policy.md` §5 交接仍指向 SUPERSEDED r1 root。
- 本 r3 root 在同一 r2 snapshot（`d14d-clean-base-20260906-r2`，UUID
  `c5e3c3de…`）上补采：提交固定 `clean_state_gate.sh`（SHA
  `f90939d1…`）+ 正向运行（`CLEAN_STATE_PASS` exit 0）与受控负向运行
  （注入 build → `CLEAN_STATE_FAIL` exit 1）证据；修正 policy §5 交接指向
  本 ACTIVE root。r1/r2 均保持 SUPERSEDED 历史，不改写。

## 关键测量（真实 r2 snapshot，非 Mock）

| 项 | 值 |
|---|---|
| VM / snapshot | `Kylin-V11-2603-BTrack-Base` / `d14d-clean-base-20260906-r2` |
| OS | 银河麒麟桌面 V11（`KYLIN_RELEASE_ID=2603`） |
| kernel / arch | `6.6.0-63-generic` / x86_64 |
| Python / systemd | 3.12.3 / systemd 255 |
| SDK | `libkylin-coreai-embedding 1.2.0.0-0k0.4` · `.so` SHA `028e7099…`（FROZEN） |
| runtime | `kylin-ai-runtime 1.2.0.4-0k0.1` · `/usr/bin/kylin-ai-runtime` SHA `b3f83fc9…` |
| model | `kylin-gte-base-model 1.0.0.1-0k0.9` · ONNX SHA `cef0fc76…` |
| subsystem / parser | `kylin-ai-subsystem 1.3.0.1-0k0.1` / `kylin-ai-parser-extension 1.2.0.0-0k0.4` |
| installed pkgs | 2030（重采，无 grep 错误） |
| clean-state Gate | `clean_state_gate.sh`（fail-closed）：正向 PASS/exit 0；负向（受控 build 残留）FAIL/exit 1 |

## 采集与恢复

1. 从 r2 poweroff 冷启一次（127.0.0.1:2222）；
2. 运行提交的 `clean_state_gate.sh` 正向（ROOT=/home/yanmouren778）与负向
   （ROOT=临时目录注入 build，测后删除）→ 记录脚本 SHA、命令、exit code、stdout/stderr；
3. 只读采集 environment 与 dependency（2030 包完整清单）；
4. VM 关机并恢复到 r2 snapshot（丢弃临时采集层），最终
   `VMState=poweroff @ d14d-clean-base-20260906-r2`（快照未变，保持纯净）。

## 边界

- 本包只表示“可供 D13D I3d / A package 对齐使用”，不表示 D14D PASS，
  不表示依赖 vendor freeze 完成，不表示 Trust Root 已重验，不授予 L3。
- runtime/model/subsystem 在本包按 r2 实测记录为 host baseline；
  契约侧 vendor-lock / D Reviewer 会签仍为 `HANDOFF_REQUIRED`（正式 G0）。
- kernel 为 `6.6.0-63`（Route A 新基础；superseded r1 记录为不同 VM 的 `6.6.0-76`）。

## 文件

```text
.gitattributes
clean_state_gate.sh     # 固定 fail-closed clean-state Gate（提交于本 root）
snapshot_identity.json
environment.json
dependency_identity.json
evidence_root_policy.md # §5 交接指向本 ACTIVE root
trust_root_candidate.md
raw/                    # probe(正向)/neg(负向)/env/deps 原始日志 + 摘要 JSON
checksums.txt           # 本 evidence root 除 checksums.txt 自身外全部 regular files 的 SHA-256
```