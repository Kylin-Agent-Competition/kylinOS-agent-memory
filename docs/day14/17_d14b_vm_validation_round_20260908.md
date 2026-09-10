# D14B VM Validation Round（2026-09-08）

> 性质：本批为 D14B **PREPARATION / VALIDATION**（test/validation profile），非正式 L3 evidence。
> `D14B_FORMAL_L3` 仍 = `UNVERIFIED`；未创建 formal evidence root；不得把本批结果写成
> L3 PASS / VERIFIED / 性能达标。

## 1. 范围与身份

- 分支 / PR：`test/D14B-l3-vm-release-regression`（PR #124）
- VM：`Kylin-V11-2603-BTrack-Base`（UUID `103fb8a8-…`，快照 D14B `ae9a3fcb-…`），guest `yanmouren778-pc`
- 精确 checkout：`~/d14b-ba3b50e-full-preparation` @ `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（git status 干净）
- harness：`~/d14b-harness-4b78957-preparation`（D14B harness @ `4b78957`）

## 2. 环境修复（真实根因；OS reboot 后 kylin-ai-runtime 依赖需持久化，见 §5）

1. kylin-ai-runtime 启动即崩：缺 triton client 符号
   （`triton::client::InferenceServerHttpClient::Create`）→ 以 kytensor-client 解包库
   + `LD_LIBRARY_PATH` 运行并保持存活。
2. kytensor 无法加载 onnxruntime 模型：onnxruntime 后端位于 `/usr/lib/kytensor/backends`，
   而默认 backend 目录是 `/opt/tritonserver/backends` → 建 `/var/tmp/kytensor-backends`
   合并符号链接 + systemd drop-in `--backend-directory`（跨重启有效）。
3. 修复后模型 `ensemble-embd_gte-base_uint8-text` 可加载，真实 SDK `memory.embed` 可用。

## 3. 实测结果（全部真实执行并 PASS）

| 项 | 结果 |
| --- | --- |
| D14A `systemd/verify.sh` | ALL PASS（service / socket holder / cmdline / 真实 SDK embed dim=768 degraded=false / SDK maps SHA=`028e7099…`==冻结值） |
| D14B harness L0/L1（`tests/retrieval/test_d14b_harness.py`） | 20 passed |
| `vector_bridge_cli` 编译 | PASS：0k1.1 headers（`Database.h` SHA `12c6f819…` 与 D13D G6 一致），binary SHA `3c0ab221…` |
| D10B 删除 L2（`run_d10b_vector_delete_l2.sh`） | 15/15 PASS（`ba3b50e`，真实 engine；无残留） |
| D13D stage1 同款真实链路驱动（隔离 runtime.db） | PASS：真实 embed(768)→`SqliteVectorProvider.upsert`（真实 bridge CLI）→vector search hit rank1→delete→0 hit→collection drop，ledger active 1→0 |

## 4. Deviation（B 轨负责人 2026-09-08 授权，报告中明示）

1. 本 VM 非 D14D formal clean VM（D14D clean VM `Kylin-D14D-clean-vdi-20260906` 未注册于本机）。
2. 受控数据写入采用 validation-profile / 真实 provider 驱动；production IPC 写路径在
   `main` 上被 ADR-010/014 门禁（`memory.store`/`memory.retrieve` 未实现；
   `turn.finalized`/`event.ingest` 默认未注册）。

## 5. 遗留与风险

- D14B 多通道生命周期驱动（FTS5/RRF/受控语料/服务重启持久化/重建/性能）尚未构建，为下批次任务。
- OS reboot 后：kytensor drop-in 与 `/var/tmp/kytensor-backends` 有效；kylin-ai-runtime 依赖库在
  `/tmp`（会被清空），需复制到持久路径或重启后以 `LD_LIBRARY_PATH` 重新拉起。

## 6. 合并资格

本批不改生产代码、不创建 formal evidence root；`D14B_FORMAL_L3=UNVERIFIED`，PR #124 保持
Draft，不具 formal merge 资格。