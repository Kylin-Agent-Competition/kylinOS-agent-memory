# Carlton Kylin V11 Independent Host Validation Evidence

- **EVIDENCE_CLASS**: `INDEPENDENT_KYLIN_HOST_VALIDATION`
- **状态**: `NON_AUTHORITATIVE_FOR_D14D`
- AUTHORITATIVE_D14D_PHASE0=NO
- FORMAL_D14D_L3=NO
- L3_READY=NO
- HOST_VERIFIED_SCOPE=LIMITED_TO_RECORDED_FACTS
- RELEASE_READY=NO
- D13D_FROZEN=NO

## 本包是什么

本包封存 Carlton 在 Windows Desktop 上已真实产生的银河麒麟 V11 x86_64 独立宿主（第二套 Kylin 宿主身份）r2 Runtime evidence。10 个 raw 文件从只读源目录
`/mnt/c/Users/Carlton Benzol/Desktop/d14d-env-prepared-20260906-r2/` 以 byte-for-byte 方式复制（不改换行、不修乱码、不删失败记录），并生成 12 个派生文件与自校验闭环。

本任务只封存既有 Runtime evidence：

- 不执行、不重跑 L2/L3；
- 不操作 VirtualBox（不启动/关闭/恢复/删除/修改 VM 或 snapshot）；
- 不对官方 SDK 做新的运行时验证，不产生任何新 Runtime 结论；
- 不修改任何 D14D authoritative evidence。

## 实际可证明的事实（全部来自 raw）

| 类别 | 事实 |
|---|---|
| OS identity | Kylin，KYLIN_RELEASE_ID=2603，VERSION_ID=v11，PRETTY_NAME="Kylin V11"（ASCII identity；raw 中本地化 VERSION 含 Windows SSH 抓取乱码，按字节保留，不作为身份门禁） |
| Kernel | 6.6.0-63-generic（`Linux Carlton-pc ... x86_64 x86_64 x86_64 GNU/Linux`） |
| Arch | x86_64 |
| 主机身份 | hostname=Carlton-pc，user=Carlton，uid/gid=1000 |
| Python / systemd | Python 3.12.3；systemd 255 (255.2-ok1.9k1.39) |
| SDK | libkylin-coreai-embedding 1.2.0.0-0k0.4 amd64；`.so` `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0`；SONAME `libkysdk-coreai-embedding.so.1`；SHA-256 `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48`；size=366624 —— 与 D14A FROZEN contract §6 精确一致 → `MATCHES_D14A_FROZEN_SDK_IDENTITY`（仅 SDK） |
| Runtime | kylin-ai-runtime 1.2.0.4-0k0.1 amd64；`/usr/bin/kylin-ai-runtime` SHA-256 `b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225`、size=3174000 |
| Model | kylin-gte-base-model 1.0.0.1-0k0.9 all；ONNX `/usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text/1/gte-base-multilingual-model_QUInt8.onnx` SHA-256 `cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1` 等 artifacts（完整列表见 raw） |
| Subsystem / parser | kylin-ai-subsystem 1.2.0.0-0k0.3 amd64；kylin-ai-parser-extension NOT_INSTALLED（与 authoritative r3 的 1.3.0.1 / 1.2.0.0-0k0.4 差异如实保留） |
| Snapshot / VM identity | VBox 7.2.8r173730；VM `Kylin-Desktop-V11-2603-SDK` UUID `23a31c42-63bb-482f-8856-e8a9f04176c8`；snapshot `d14d-clean-base-20260906-r2` UUID `b2af169e-8bfc-46a8-9120-6348095eccf3` |
| Clean-state observation | raw 中按真实时间顺序记录 7 个 clean gate / diagnostic 事件（初始 clean PASS、runtime residue PASS、strict fail-closed EPERM 历史事件、allowlist-aware final PASS、3 个 diagnostic）；strict EPERM 是不可验证区域的 fail-closed 历史事件，不是工程通过证据；所有 raw 未记录的 exit code 一律 `NOT_CAPTURED_IN_ARCHIVED_RAW`，未记录时间写 `NOT_CAPTURED` |
| 环境包计数 | 系统包计数记录于 environment.json（唯一位置），来源 raw/r2_environment.log |

原始 raw 均为不可修改的事实来源：执行退出码在 raw 中未记录时不得推断为 0。

## Authoritative D14D Phase0 引用

本包**不替代** authoritative D14D Phase0 root：

- authoritative root：`evidence/phase0/d14d-env-prepared-20260906-r3/`
- 本包为独立宿主第二套身份证据（`INDEPENDENT_KYLIN_HOST_VALIDATION`、`NON_AUTHORITATIVE_FOR_D14D`），与 authoritative root 不得混用、不得作为 D14D Phase0 / 正式 L2/L3 的输入替代。

## 包结构

```
evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906/
├── .gitattributes                # 全 root binary 纪律（字节稳定，禁止 EOL/文本规范化）
├── README.md                     # 本文件
├── EVIDENCE_INDEX.md             # raw + derived 登记
├── evidence_scope.md             # 可证明/不可证明清单
├── source_inventory.json         # 10 raw 的 relative_path/size_bytes/sha256
├── environment.json              # 仅依据 raw/r2_environment.log + raw/r2_os-release.raw
├── dependency_identity.json      # 仅依据 raw/r2_dependencies.log
├── snapshot_identity.json        # 仅依据 3 个 host capture raw
├── clean_state_summary.json      # 7 个 clean gate/diagnostic 事件时间序整理
├── provenance.json               # 封存元数据（fail-closed 时间戳等）
├── checksums.txt                 # 除自身外全部 regular files 的 SHA-256（稳定排序）
├── test_package_closure.py       # 自校验闭环测试（证据包组成部分）
└── raw/                          # 10 个 byte-for-byte 源文件
```

## 封存完整性自校验

在**证据包根目录**（`evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906/`）执行：

```bash
sha256sum -c checksums.txt
```

必须全部 PASS。若不在包根目录执行，请显式指定目录以避免歧义：

```bash
sha256sum --directory evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906 -c checksums.txt
```

自校验测试（L0 与 L1 使用同一命令，退出码必须为 0，无 skip）：

```bash
python3 -m pytest evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906/test_package_closure.py -q
```

- 首封存：checksums.txt 缺失时由一次 pytest 运行确定性生成；
- 只读验证：checksums.txt 存在时后续 pytest 运行只验证，任何内容漂移一律 FAIL（不静默改写）；
- raw 缺失或哈希不符时，测试从只读源目录以 bytes 模式复制并断言 源 SHA == SOURCE_SHA256_EXPECTED == 目标 SHA，源不可达或哈希不符则 FAIL（fail-closed，不自动采用新哈希）。

## Limitations

1. 本包只封存既有 raw evidence，**不构成** L2/L3 执行结果；HOST_VERIFIED_SCOPE 仅限 `LIMITED_TO_RECORDED_FACTS`（raw 记录范围内的事实），任何超出现有记录范围的主机验证声明都不成立。
2. 本包不是 authoritative D14D Phase0，不替代 `evidence/phase0/d14d-env-prepared-20260906-r3/`。
3. raw 中部分本地化文本为 Windows SSH 抓取产生的 mojibake，已按字节保留在 raw/；派生 JSON 只使用 ASCII identity 字段，不把乱码当身份门禁。
4. 所有 raw 未记录的 exit code 一律 `NOT_CAPTURED_IN_ARCHIVED_RAW`（时间 `NOT_CAPTURED`），禁止推断为 0。
5. strict EPERM 事件（`find: '/home/Carlton/.box': Operation not permitted`）是 fail-closed 历史事件，不是工程通过证据。
6. runtime/model/subsystem/parser 按 raw+contract 状态写 host baseline，不声明 FROZEN；SDK-only 的 `MATCHES_D14A_FROZEN_SDK_IDENTITY` 见 dependency_identity.json。
7. 本任务不存在受控注入的证据化 packaging 时间戳，provenance.json `created_at_utc` 按 fail-closed 标记为 `NOT_CAPTURED_IN_PACKAGING_LOG`。
8. 无 final tested_commit / FINAL_P / formal package hash / release-ready 声明。
9. 系统包计数仅记录于 environment.json（来源 raw/r2_environment.log），不属于依赖身份文件。