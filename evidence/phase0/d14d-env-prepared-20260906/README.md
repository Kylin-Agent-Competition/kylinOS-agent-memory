# D14D_ENV_PREPARED — evidence package（2026-09-06）

## 状态

```text
D14D_ENV_PREPARED = READY（本包）
D14D_FORMAL_L3     = NOT_STARTED（未执行 install/restart/reboot/rollback/release gate）
D14A_FORMAL_L3_GO  = NO（阶段二前置未闭合，本包不改变该结论）
```

本包按两阶段状态模型（D-15）交付：

- W5a snapshot identity → `snapshot_identity.json`
- W5b environment identity → `environment.json`
- dependency baseline → `dependency_identity.json`
- W5c evidence root 规则 → `evidence_root_policy.md`
- Trust Root candidate / 重验证入口 → `trust_root_candidate.md`

## 关键测量（真实 r1，非 Mock）

| 项 | 值 |
|---|---|
| VM / snapshot | `Kylin-D14D-clean-vdi-20260906` / `d14d-clean-base-20260906-r1` |
| OS | 银河麒麟桌面 V11（`KYLIN_RELEASE_ID=2603`） |
| kernel / arch | `6.6.0-76-generic` / x86_64 |
| Python / systemd | 3.12.3 / systemd 255 |
| SDK | `libkylin-coreai-embedding 1.2.0.0-0k0.4` · `.so` SHA `028e7099…`（FROZEN） |
| runtime | `kylin-ai-runtime 1.2.0.4-0k0.1` · `/usr/bin/kylin-ai-runtime` SHA `b3f83fc9…` |
| model | `kylin-gte-base-model 1.0.0.1-0k0.9` · ONNX SHA `cef0fc76…` |
| installed pkgs | 2036（完整清单在 raw 依赖日志） |
| 项目残留 | 无 checkout / venv / prefix / launcher / unit / socket |

## 采集与恢复

1. 从 r1 poweroff 冷启一次（headless，127.0.0.1:2223）；
2. 只读 probe + environment + dependency 采集（无 sudo）；
3. 首个 probe 因 sshd 尚在初始化返回 BLOCKED（`envprep_probe_20260906_1`），
   就绪后以新 run-id 重试 PASS（`envprep_probe_20260906_2`），不覆盖；
4. VM 已恢复：r1 snapshot restore + saved state discard，最终
   `VMState=poweroff @ d14d-clean-base-20260906-r1`。

## 边界

- 本包只表示“可供 D13D I3d / A package 对齐使用”，不表示 D14D PASS，
  不表示依赖 vendor freeze 完成，不表示 Trust Root 已重验，不授予 L3。
- runtime/model 在本包按 r1 实测冻结为 ENV_PREPARED host baseline；
  契约侧 vendor-lock / D Reviewer 会签仍为 `HANDOFF_REQUIRED`（正式 G0）。
- A 侧 SDK 裁决：`0k0.4 / 028e7099…`（方案 A，A 契约不改）。

## 文件

```text
snapshot_identity.json
environment.json
dependency_identity.json
evidence_root_policy.md
trust_root_candidate.md
raw/            # kylin_vm_test.py 原始日志 + 摘要 JSON
checksums.txt   # 本 root 全部文件 SHA-256
```
