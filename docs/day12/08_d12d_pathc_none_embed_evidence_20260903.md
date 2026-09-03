# D12D Path C：非 embed 同 Commit 实测证据 + 采信 A 轨 D12A L2（2026-09-03）

> 分支：fix/D12D-stability-gate（PR #131，Draft）。基线：origin/main@0820036。
> 执行 VM：Kylin-V11-2603-Env-V2-Main（8 vCPU / 8GB / 256MB 显存）。
> 口径（Path C，经负责人确认）：**真实 Embedding/SDK 调用采信 A 轨 D12A L2（D12A-L2-VERIFY）**；
> 本 VM 完成非 embed 的同 Commit（0820036）项：服务/部署/IPC/重启/权限/日志/Vector。

## 一、采信项（不重复实测，如实标注）
| 项 | 采信来源 |
|---|---|
| 真实 SDK embed（bridge_loaded=true、dim=768、异常输入回归、性能 avg77.7ms/p99 97.6ms ≤180ms） | A 轨 PR #100：evidence/l2-kylin-vm/day12a_verify_20260902_232744.log（`D12A-L2-VERIFY`，HOST_VERIFIED/E4） |
| C 轨 QML/MemoryClient 真实交互 | C 轨（跨轨 pending，采信其输入；D VM 无 C 客户端） |
| B 轨 vector 删除/重建一致性 L2 | B 轨既有 L2 账本（D11B/D13B）；本 VM 无 KySec 信任 vector_bridge_cli，不冒充本 VM 实测 |

## 二、本 VM 实测证据（麒麟 VM，main@0820036）
| 项 | 结果 | 证据文件（evidence/l2-kylin-vm/） |
|---|---|---|
| 环境 | 单 VM 运行；空闲内存 7.4GB；8 vCPU；停用 kylin-aiassistant/文档/知识库/回忆/OptiDaemon/软件中心/天气/便签并禁自启 | d12d_pathc_perms_20260903.txt |
| DB 迁移 | alembic upgrade head → D10D `add_forget_plan`（RC=0） | d12d_pathc_service_journal_20260903.txt |
| 服务部署 | `install_kylin_memory.sh install` → kylin-memory.service active | d12d_pathc_service_install_20260903.txt |
| 服务启动 | journal：alembic 校验通过 / Outbox Worker / IPC Gateway / “Memory Service 就绪” | d12d_pathc_service_journal_20260903.txt |
| 服务重启 | `systemctl --user restart` → active、socket、再次“就绪” | d12d_pathc_service_restart_20260903.txt |
| **OS 整机重启自启** | `systemctl reboot` 后 kylin-memory 自动 active（46s 后自启）、vector active、IPC 回环正常、journal“就绪” | d12d_pathc_os_reboot_20260903.txt |
| UDS IPC | memory.retrieve → {ok, context:[], degraded:false, reason:“retrieval main chain pending”}；未实现方法 → 结构化 UNSUPPORTED_METHOD（fail-closed） | d12d_pathc_uds_ipc_20260903.txt |
| 权限 | config/share/state/RuntimeDir 0700；socket/DB 0600 | d12d_pathc_perms_20260903.txt |
| 日志脱敏 | JSON 日志含 trace_id；journal 无用户正文（中文为启动提示语） | d12d_pathc_service_restart_20260903.txt |

## 三、明确边界（不越轨声明）
- `memory.store` 在 main@0820036 网关按冻结契约返回 UNSUPPORTED_METHOD（Gate 0 预期），主链业务写入/检索未接线；
  D 轨不以本 VM 冒充业务闭环。
- embed 真实调用不写“本 VM 已测”；仅采信 A 轨并标注。
- B/C 端到端结论保持跨轨 pending / 采信，不代实现。

## 四、待办（进入 Review 前）
- [ ] evidence/index.yaml 回填（本批已附 checksum 条目，evidence_commit 待本提交后回填）
- [ ] Review 意见回填