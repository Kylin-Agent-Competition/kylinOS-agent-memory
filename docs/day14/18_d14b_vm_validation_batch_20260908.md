# D14B VM Validation Batch（2026-09-08）

> 性质：本批为 D14B **PREPARATION / VALIDATION**（test/validation profile，B 轨负责人
> 2026-09-08 授权 B2）。非正式 L3 evidence；`D14B_FORMAL_L3` 仍 = `UNVERIFIED`；未创建
> formal evidence root；报告中明示 deviation。

## 1. 身份

- 分支 / PR：`test/D14B-l3-vm-release-regression`（PR #124）
- VM：`Kylin-V11-2603-BTrack-Base`（UUID `103fb8a8-…`，快照 D14B `ae9a3fcb-…`），guest `yanmouren778-pc`
- 精确 checkout：`~/d14b-ba3b50e-full-preparation` @ `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（git 干净）
- harness：`~/d14b-harness-4b78957-preparation`（@ `4b78957`）

## 2. 实测结果（全部在 VM 真实执行）

| # | 项 | 结果 | VM 证据位置 |
| --- | --- | --- | --- |
| 1 | D14A `systemd/verify.sh`（service/socket holder/cmdline/真实 SDK embed dim=768/SDK maps SHA=`028e7099…`==冻结值） | ALL PASS | 会话记录 |
| 2 | D14B harness L0/L1（`tests/retrieval/test_d14b_harness.py`） | 20 passed | `~/d14b-harness-4b78957-preparation` |
| 3 | D10B 删除 L2（`run_d10b_vector_delete_l2.sh`，`ba3b50e`，真实 engine） | 15/15 PASS | 会话记录 |
| 4 | D13D stage1 同款真实链路驱动（隔离库） | PASS | `~/d14b-validation-20260908/persist` |
| 5 | 服务 DB SQLite/FTS5 服务重启持久化（#2/#5 部分） | PASS | `~/d14b-validation-20260908/svc_persist` |
| 6 | 服务层删除残留（#4 部分，`repo.soft_delete_memory_entry`，6/6） | PASS | `~/d14b-validation-20260908/svc_delete` |
| 7 | retrieval L0/L1 回归（#8 部分：harness + formal_eval + 完整 `memory-service/tests/retrieval/`） | 365 passed | VM 会话 |
| 8 | FTS 通道性能采样（#6 部分：500 语料，P50/P95/mean/max；无冻结阈值 → 仅记录 delta） | 记录 | `~/d14b-validation-20260908/svc_perf` |
| 9 | OS 整机重启一致性（#5 部分：真实 guest reboot，boot_id 变化，kylin-memory/vector-engine 自启 active，SQLite/FTS 数据与重启前一致） | PASS | `~/d14b-validation-20260908/os_reboot/result.json` |
| 10 | 重建一致性（#3 部分·FTS 侧：soft-delete 后 FTS5 `rebuild`，target 未复活、其余可检索） | PASS(5/5) | `~/d14b-validation-20260908/svc_rebuild/result.json` |
| 11 | **Vector 持久化（#2 部分，自配置 durable binding）**：真实 embed(768)×5 → `SqliteVectorProvider` upsert → engine 重启 → loader 重绑定 → ledger=5、top_hits 与重启前一致 | PASS | `~/d14b-validation-20260908/vector_persist/{baseline,after,meta}.json` |

## 3. Deviation（明示）

1. 本 VM 非 D14D formal clean VM（D14D clean VM `Kylin-D14D-clean-vdi-20260906` 未注册于本机）。
2. 受控数据写入采用 validation-profile / 真实 provider 驱动；`main` 上 production IPC 写路径被
   ADR-010/014 门禁（`memory.store`/`memory.retrieve` 未实现；`turn.finalized`/`event.ingest`
   默认未注册）。
3. D14D clean VM 不可得 → B 自配置 vector 持久化：app `vector-bridge` 绑定持久 db-file
   （`~/…/kylin-ai-vector-engine/vector-bridge.db`），loader `vector_db_load` 于开机/engine 重启后重注册，
   数据跨 engine/OS 重启保留（deviation 记录）。

## 4. 阻塞（如实）

- Vector 持久化已由自配置 durable binding 解除（本 VM，见 Deviation 3 与行 11）；
  服务级全通道与 RRF 相关正式切片、#7 正式 evidence、#8 独立 Review 仍待 D 轨流程/正式输入。

## 5. 环境持久化（2026-09-08，重启自愈）
- vector engine 后端目录改至 `~/kytensor-backends`（home 持久；drop-in `--backend-directory` 已更新）。
- kylin-ai-runtime 依赖库改至 `~/kytensor-libs`（home 持久）；autostart Exec 已更新。
- 实测 guest OS 重启后：kytensor/kylin-memory/vector-engine 自启，真实 SDK `memory.embed` dim=768
  可用（D14A verify ALL PASS）。
- vector 持久 db-file 绑定：`~/d14b-tools/vector_db_load` + autostart `d14b-vector-load.desktop`
  （ensure_vector_db.sh 带重试），engine/OS 重启后自动重注册，collection 落于 vector-bridge.db。
## 6. 合并资格

本批不改生产代码、不创建 formal evidence root；`D14B_FORMAL_L3=UNVERIFIED`；PR #124 不具
formal merge 资格。Draft/Ready 与合并由负责人手动操作。