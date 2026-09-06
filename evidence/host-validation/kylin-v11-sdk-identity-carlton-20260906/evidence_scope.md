# Evidence Scope — Carlton Kylin V11 Independent Host Validation

> EVIDENCE_CLASS=INDEPENDENT_KYLIN_HOST_VALIDATION · NON_AUTHORITATIVE_FOR_D14D
> AUTHORITATIVE_D14D_PHASE0=NO · FORMAL_D14D_L3=NO · L3_READY=NO
> HOST_VERIFIED_SCOPE=LIMITED_TO_RECORDED_FACTS · RELEASE_READY=NO · D13D_FROZEN=NO

## 可证明（raw 实际支持）

1. 存在第二套真实 Kylin V11 x86_64 宿主身份：hostname=Carlton-pc、user=Carlton、uid/gid=1000、Kernel 6.6.0-63-generic、arch=x86_64、Python 3.12.3、systemd 255、KYLIN_RELEASE_ID=2603、VERSION_ID=v11。
2. 已记录系统与依赖身份：SDK（libkylin-coreai-embedding 1.2.0.0-0k0.4 amd64，`.so` 路径/SONAME/SHA-256/size）、runtime（kylin-ai-runtime 1.2.0.4-0k0.1，binary SHA-256/size）、model（kylin-gte-base-model 1.0.0.1-0k0.9 all，ONNX 等 artifacts）、subsystem（1.2.0.0-0k0.3）、parser（NOT_INSTALLED）。
3. SDK 冻结身份匹配：SDK SHA/版本/路径/SONAME 与 D14A FROZEN contract §6 精确一致（`MATCHES_D14A_FROZEN_SDK_IDENTITY`，仅 SDK）。
4. 已记录 clean-state / snapshot observations：7 个 clean gate / diagnostic 事件时间序（含 strict fail-closed EPERM 历史事件与 allowlist-aware final PASS）；VBox 7.2.8r173730、VM `Kylin-Desktop-V11-2603-SDK`、snapshot `d14d-clean-base-20260906-r2` 及三个 capture 的 VMState/当前快照。
5. 真实宿主适配旁证：Windows Desktop 作为采集渠道产生的真实抓取记录（含 mojibake 本地化文本，按字节保留）。

## 不可证明（超出本包范围）

- authoritative D14D Phase0（无 G0-G9 正式结论）；
- D14D FORMAL G0-G9 门禁结论；
- L3_READY / 正式 L3 验收；
- final tested_commit、FINAL_P；
- formal package hash、release/production ready；
- D13D_FROZEN；
- D14A final package runtime validation（本包仅封存既有身份与 clean-state 观测，不证明任何运行时行为）。

## Authoritative root 与混用禁令

- authoritative D14D Phase0 root：`evidence/phase0/d14d-env-prepared-20260906-r3/`
- 本包（`evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906/`）与 authoritative root **不得混用**：本包不得被引用为 D14D Phase0 输入、不得作为正式 L2/L3 的替代证据，也不得自称替代 authoritative root。
- 本包内全部 exit code 语义遵循 fail-closed：raw 未记录 → `NOT_CAPTURED_IN_ARCHIVED_RAW`（时间 `NOT_CAPTURED`），绝不写 0。