# D14D_ENV_PREPARED — evidence package r2（2026-09-06 · Route A）

## 状态

```text
D14D_ENV_PREPARED = READY（本包 r2，clean-state Gate fail-closed PASS）
D14D_PHASE0       = r1 SUPERSEDED；r2 ACTIVE
D14D_FORMAL_L3    = NOT_STARTED（未执行 install/restart/reboot/rollback/release gate）
D14A_FORMAL_L3_GO = NO
```

r1（`d14d-env-prepared-20260906/`）因 clean-state residue 与 checksum 未闭环被
Review 降级并 SUPERSEDED（不改写）；本 r2 root 为 Route A 重建的干净起点
（B 轨基础 VM：清除 7 个 build 残留 + 安装冻结版 SDK/runtime/model 后冻结）。

## 关键测量（真实 r2，非 Mock）

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
| installed pkgs | 2030（完整清单在 raw 依赖日志） |
| clean-state | PASS（fail-closed：checkout/prefix/launcher/unit/sock/venv/build/d14a 全 0） |

## 采集与恢复

1. 从 r2 poweroff 冷启一次（headless/前台，127.0.0.1:2222）；
2. 只读 fail-closed clean probe + environment + dependency 采集（无敏感写操作）；
3. VM 已恢复：优雅关机，最终 `VMState=poweroff @ d14d-clean-base-20260906-r2`。

## 边界

- 本包只表示“可供 D13D I3d / A package 对齐使用”，不表示 D14D PASS，
  不表示依赖 vendor freeze 完成，不表示 Trust Root 已重验，不授予 L3。
- runtime/model/subsystem 在本包按 r2 实测记录为 host baseline；
  契约侧 vendor-lock / D Reviewer 会签仍为 `HANDOFF_REQUIRED`（正式 G0）。
- kernel 为 `6.6.0-63`（Route A 新基础；superseded r1 记录为不同 VM 的 `6.6.0-76`）。

## 文件

```text
.gitattributes
snapshot_identity.json
environment.json
dependency_identity.json
evidence_root_policy.md
trust_root_candidate.md
raw/            # probe/env/deps 原始日志 + 摘要 JSON
checksums.txt   # 本 evidence root 除 checksums.txt 自身外全部 regular files 的 SHA-256
```