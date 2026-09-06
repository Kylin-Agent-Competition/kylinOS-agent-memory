# EVIDENCE INDEX — Carlton Kylin V11 Independent Host Validation

> EVIDENCE_CLASS=INDEPENDENT_KYLIN_HOST_VALIDATION · NON_AUTHORITATIVE_FOR_D14D
> Source environment（全部 raw）: Carlton 银河麒麟 V11 x86_64 独立宿主
> （VM `Kylin-Desktop-V11-2603-SDK`，VirtualBox 7.2.8r173730，Windows host SSH 抓取，只读源目录
> `/mnt/c/Users/Carlton Benzol/Desktop/d14d-env-prepared-20260906-r2/`）

## Raw 证据登记（失败证据必须登记）

| Evidence ID | File | Type | Source Environment | Observed Fact | Result | SHA256（前 12 位，全文见 source_inventory.json / checksums.txt） | Limitation |
|---|---|---|---|---|---|---|---|
| EVID-CARLTON-R2-01 | raw/r2_clean_gate.log | Clean gate probe | Carlton Kylin V11 host | UTC=2026-09-06T07:51:42Z；hostname=Carlton-pc；user=Carlton；D14D_R2_CLEAN_STATE=PASS | PASS_RESULT_CAPTURED | ee9e83e4dc9b | exit code 未在 archived raw 记录 → NOT_CAPTURED_IN_ARCHIVED_RAW |
| EVID-CARLTON-R2-02 | raw/r2_clean_gate_strict.log | Fail-closed strict clean probe | Carlton Kylin V11 host | UTC=2026-09-06T08:20:17Z；D14D_R2_CLEAN_FIND=ERROR；`find: '/home/Carlton/.box': Operation not permitted` | FAIL_CLOSED_ERROR_CAPTURED | 7fded644f2e1 | 不可验证区域 fail-closed 历史事件，不是工程通过证据；exit code 未记录 |
| EVID-CARLTON-R2-03 | raw/r2_dependencies.log | Dependency identity inventory | Carlton Kylin V11 host | SDK/runtime/model/subsystem/parser 目标包身份 + full package inventory；SDK SHA 028e7099… 与 D14A FROZEN §6 一致 | CAPTURED（identity 记录于 dependency_identity.json） | 0f1cfd1db598 | 仅 dpkg 可读状态；exit code 未记录；系统包计数不在本文件 |
| EVID-CARLTON-R2-04 | raw/r2_environment.log | Environment identity | Carlton Kylin V11 host | UTC=2026-09-06T07:54:20Z；OS/kernel/python/systemd/root disk/包计数；ASCII identity 字段 | CAPTURED（identity 记录于 environment.json） | 8e5e898428c3 | 本地化 VERSION 行在 raw 中为 Windows SSH 抓取 mojibake，按字节保留，不作为身份门禁；系统包计数仅记录于 environment.json |
| EVID-CARLTON-R2-05 | raw/r2_final_clean_gate.log | Allowlist-aware final clean probe | Carlton Kylin V11 host | UTC=2026-09-06T08:30:11Z；PATH=/home/Carlton/.box MODE=700 OWNER=Carlton GROUP=Carlton；EXACT_PATH_ONLY；7 个 ABSENT 的 D14A runtime path；D14D_R2_RUNTIME_PATH_STATE=PASS；HOME_FIND=PASS；ALLOWLIST_VALIDATED=PASS；CLEAN_STATE=PASS | ALLOWLIST_AWARE_PASS_RESULT_CAPTURED | dbbd708d7d24 | 覆盖 opaque home 子目录的 allowlist-aware 探针；exit code 未记录 |
| EVID-CARLTON-R2-06 | raw/r2_host_final_state.log | Host state diagnostic | VBox host（VM Kylin-Desktop-V11-2603-SDK） | COLLECTED_AT_UTC=2026-09-06T08:17:09Z；VMState=poweroff；CurrentSnapshot=d14d-clean-base-20260906-r2 | DIAGNOSTIC_ONLY | a9a43892c03f | 诊断性 capture，非 gate；exit code 未记录 |
| EVID-CARLTON-R2-07 | raw/r2_host_final_state_after_gate.log | Post-gate host state diagnostic | VBox host（VM Kylin-Desktop-V11-2603-SDK） | COLLECTED_AT_UTC=2026-09-06T09:47:30Z；VMState=poweroff；CurrentSnapshot=d14d-clean-base-20260906-r2 | DIAGNOSTIC_ONLY | 45d5ccb00a70 | 诊断性 capture，非 gate；exit code 未记录 |
| EVID-CARLTON-R2-08 | raw/r2_host_snapshot_identity.log | VM/snapshot identity diagnostic | VBox host（VM Kylin-Desktop-V11-2603-SDK） | COLLECTED_AT=2026-09-06T07:54:07Z；VBox 7.2.8r173730；VMState=running；CurrentSnapshot=d14d-clean-base-20260906-r2 | DIAGNOSTIC_ONLY | 27ab15d91834 | 快照链中本地化 snapshot 名含 mojibake，按字节保留；exit code 未记录 |
| EVID-CARLTON-R2-09 | raw/r2_os-release.raw | /etc/os-release 原始输出 | Carlton Kylin V11 host | NAME="Kylin"；PRETTY_NAME="Kylin V11"；VERSION_ID="v11"；KYLIN_RELEASE_ID="2603"；ID_LIKE=openKylin | CAPTURED（ASCII fields 记录于 environment.json） | e5952e5be208 | 本地化 VERSION 行为声明文本（VERSION_US 提供 ASCII 等价），不作为身份门禁 |
| EVID-CARLTON-R2-10 | raw/r2_runtime_residue_gate.log | Runtime residue probe | Carlton Kylin V11 host | UTC=2026-09-06T07:59:36Z；D14D_R2_RUNTIME_RESIDUE=PASS | PASS_RESULT_CAPTURED | fbaaaf8e67a2 | exit code 未在 archived raw 记录 |

## Derived 文件来源

| Derived 文件 | 来源 |
|---|---|
| .gitattributes | `* binary` 全 root 纪律（仿 evidence/phase0/d14d-env-prepared-20260906-r3/.gitattributes） |
| README.md | 包级摘要：状态、可证明事实表、authoritative r3 引用、limitations、自校验执行目录说明 |
| EVIDENCE_INDEX.md | 本文件：raw + derived 登记 |
| evidence_scope.md | 可证明/不可证明清单 + authoritative r3 引用 + 混用禁令 |
| source_inventory.json | 10 个 raw 的 relative_path/size_bytes/sha256（与实测一致） |
| environment.json | raw/r2_environment.log + raw/r2_os-release.raw（ASCII identity 字段；系统包计数唯一位置） |
| dependency_identity.json | raw/r2_dependencies.log（SDK-only MATCHES_D14A_FROZEN_SDK_IDENTITY；不含计数） |
| snapshot_identity.json | raw/r2_host_snapshot_identity.log、raw/r2_host_final_state.log、raw/r2_host_final_state_after_gate.log |
| clean_state_summary.json | 上表 EVID-CARLTON-R2-01/02/05 + 3 个 diagnostic + runtime residue（7 事件时间序） |
| provenance.json | 封存元数据（packaging HEAD/branch、计数、source/authoritative root、scope、limitations；created_at fail-closed） |
| checksums.txt | 由 test_package_closure.py 基于当前文件集确定性生成（稳定排序，`<sha256>  <path>`） |
| test_package_closure.py | 自校验闭环测试（证据包组成部分，纳入 checksums 闭环） |