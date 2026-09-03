# D12D Path C：非 embed 同 Commit 实测证据 + 采信 A 轨 D12A L2（2026-09-03）

> 分支：fix/D12D-stability-gate（PR #131，Draft）。基线：origin/main@0820036（2026-09-03 已 merge 同步 origin/main@44d9474）。
> 执行 VM：Kylin-V11-2603-Env-V2-Main（8 vCPU / 8GB / 256MB 显存）。
> 定位：**D12D 阶段性 Path C evidence batch（非最终 Stability Gate 收口）**；完整故障注入与 Gate 未宣告完成。
> 口径（Path C，经负责人确认）：真实 Embedding/SDK 调用采信 A 轨 D12A L2（D12A-L2-VERIFY）；本 VM 完成非 embed 的同 Commit 项。

## 一、采信项（不重复实测，如实标注）
| 项 | 采信来源 |
|---|---|
| 真实 SDK embed（bridge_loaded=true、dim=768、异常输入回归、性能 avg77.7ms/p99 97.6ms ≤180ms） | A 轨 PR #100：evidence/l2-kylin-vm/day12a_verify_20260902_232744.log（D12A-L2-VERIFY，HOST_VERIFIED/E4） |
| C 轨 QML/MemoryClient 真实交互 | C 轨（跨轨 pending，采信其输入；D VM 无 C 客户端） |
| B 轨 vector 删除/重建一致性 L2 | B 轨既有 L2 账本（D11B/D13B）；本 VM 无 KySec 信任 vector_bridge_cli，不冒充本 VM 实测 |

## 二、本 VM 实测证据（麒麟 VM）
| 项 | 结果 | 证据文件（evidence/l2-kylin-vm/） |
|---|---|---|
| 环境 | 单 VM 运行；空闲内存 7.4GB；8 vCPU；停用 kylin-aiassistant/文档/知识库/回忆/OptiDaemon/软件中心/天气/便签并禁自启 | d12d_pathc_perms_20260903.txt |
| DB 迁移 | alembic upgrade head → D10D `add_forget_plan`（RC=0） | d12d_pathc_service_journal_20260903.txt |
| 服务安装（初测） | **暴露缺陷**：install 脚本 readiness 等待 ~12s < 冷启动 ~18s → socket 未就绪 ERROR（install 真实退出码≠0） | d12d_pathc_service_install_20260903.txt（DEFECT_RECORDED） |
| 服务启动 | journal：alembic 校验通过 / Outbox Worker / IPC Gateway / “Memory Service 就绪” | d12d_pathc_service_journal_20260903.txt |
| 服务重启 | `systemctl --user restart` → active、socket、再“就绪”（重启命令 RC=0） | d12d_pathc_service_restart_20260903.txt |
| OS 整机重启自启 | `systemctl reboot` 后 kylin-memory 自动 active（46s 后自启）、vector active、IPC 回环正常 | d12d_pathc_os_reboot_20260903.txt |
| UDS IPC | memory.health / memory.ping → UNSUPPORTED_METHOD（未注册方法 fail-closed）；memory.retrieve → ok（main chain pending 桩）；memory.store → UNSUPPORTED_METHOD（Gate 0 契约） | d12d_pathc_uds_ipc_20260903.txt（health/ping）+ d12d_pathc_service_restart_20260903.txt / d12d_pathc_os_reboot_20260903.txt（retrieve/store） |
| 权限 | config/share/state/RuntimeDir 0700；socket/DB 0600 | d12d_pathc_perms_20260903.txt |
| 日志脱敏 | journal 文本日志含 trace_id（未启用 --json-logs）；无用户正文（中文为启动提示语） | d12d_pathc_service_restart_20260903.txt |
| **install readiness 修复 + 重跑** | 修复 packaging/systemd/install_kylin_memory.sh（wait_socket 20→120×0.5s、journal 10→60×0.5s）后，麒麟 VM 重跑 **install/restart/rollback/reinstall 均 RC=0**，最终 active、socket ok | d12d_pathc_rerun_rc_20260903.txt |

## 三、明确边界（不越轨声明）
- `memory.store` 在 main@0820036 网关按冻结契约返回 UNSUPPORTED_METHOD（Gate 0 预期），主链业务写入/检索未接线；D 轨不以本 VM 冒充业务闭环。
- embed 真实调用不写“本 VM 已测”；仅采信 A 轨并标注。
- B/C 端到端结论保持跨轨 pending / 采信，不代实现。
- tested_commit=0820036 为历史 Runtime evidence；本 PR 已 merge main@44d9474，宣告为阶段性 batch，非最终 Gate（MEDIUM-03 口径）。

## 四、Review 返工与状态
- [x] HIGH-01：install readiness timeout 已修复并重跑（install/restart/rollback/reinstall RC=0；install 不再登记为失败→HOST_VERIFIED 基于重跑证据）
- [x] MEDIUM-01：index 描述与原始证据严格一致（PATHC-06 改“未注册方法 fail-closed”；install 初测标 DEFECT_RECORDED；日志=文本非 JSON）
- [x] MEDIUM-02：定位统一为“阶段性 Path C evidence batch”；07/08/09 与证据一致；原始 PR Body 未改（按仓库规则以修改报告 comment 同步）
- [x] MEDIUM-03：保持 PARTIAL，未宣告最终 Gate；历史 0820036 证据标注
- [ ] 待 E 非作者 Reviewer 复审