# D11D 开工工作清单：同一虚拟机全功能联调（D 轨代行）

## 任务信息

- 施工项：D11 D 轨「同一虚拟机全功能联调」（台账 D11 行，负责人周子腾）。
- 授权：已取得 D 轨负责人授权，由 B 轨（高翌哲）代行 D11D 限定范围。
- 工作类型：`feat`（主导服务、安装、日志、权限、诊断页与统一环境；含启动、重启、部署问题修复）。
- 工作分支：`feat/D11D-vm-integration`（基线 `origin/main@47af2fa`）。
- 本次范围：D 轨职责内的统一环境、服务生命周期、安装部署、日志诊断、权限与证据汇总；不代行 A/B/C/E 轨实现或审查。
- 开始时间：2026-09-01（准备阶段）。最晚停止时间：进入实现前须由 D 轨负责人指定并确认。
- 当前进度：6/9（67%）。

## 完成定义

所有模块（memory-service、embedding/UDS 子服务、vector-engine、outbox 消费方、诊断/检测脚本）在同一麒麟虚拟机、同一提交下**稳定启动并可追踪**：服务启动/停止/重启/OS 重启生命周期可验证；trace、数据库与性能证据可汇总；日志与诊断不泄露正文或敏感内容。没有麒麟 VM 实测证据的结论必须标为 `UNVERIFIED`。

## 工作清单

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| 1 | 基线与环境盘点：记录 `origin/main`、既有 D 轨产物（`packaging/systemd`、`os-agent-integration/echo`、`docs/deployment`）、VM 快照、Vector/UDS/KYSEC 状态与 VERSION_MAP | 可用的 `origin/main` 基线；D11 集成基础（已合并 PR #84） | `git status`、仓库审阅、VM 实测核对 | 已完成（仓库与既有证据侧；记录见 `docs/day11/02_d11d_baseline_environment_inventory_20260901.md`；VM 实测待 D11D 专用环境复核） |
| 2 | 冻结统一环境：统一 VM 内 Commit、依赖版本、配置与数据目录；更新环境基线/VERSION_MAP 证据 | 工作项 1 | 版本/哈希/配置核对、证据落盘 | 已完成（D11D 专用 VM 实测定案；见 `evidence/l2-kylin-vm/d11d_vm_service_l2_20260902.md`） |
| 3 | 服务与安装：部署并验证 `kylin-memory.service` 等 systemd 单元；安装流程（依赖、Kaiming 包、运行时）可重复、可回退 | 工作项 2 | `systemctl start/stop/restart`、安装/回退脚本复跑 | 已完成（麒麟 VM L2：安装/重启/回退/重装/socket/日志全部通过；`packaging/systemd/install_kylin_memory.sh`） |
| 4 | 日志与诊断页：JSON 日志、`trace_id` 贯穿、health/诊断端点（含 D11A 已增强分项）与诊断命令；禁止记录正文/敏感内容 | 工作项 3；A 轨 health 增强（已合并 PR #84） | 真实日志断言、脱敏断言、诊断输出核对 | 已完成（麒麟 VM L2：health/echo/retrieve + JSON 日志 + trace_id 关联 + PII 0；见 `evidence/l2-kylin-vm/d11d_vm_diagnostics_l2_20260902.md`） |
| 5 | 权限与安全：UDS socket 权限、KYSEC 授权（`kysec_authorize.sh`）、用户/组边界，失败关闭 | 工作项 3 | KYSEC 授权实测、越权/失败路径测试 | 已完成（本 VM 能力范围内：UDS 0600、DB 0600、用户隔离；KYSEC `/sys/kernel/security/kylin` 本 VM 不可见，保持 UNVERIFIED） |
| 6 | 汇总 trace、数据库与性能证据：trace 日志、`source_events`/outbox 数据库状态、延迟/吞吐性能基线 | 工作项 4、5 | 证据采集脚本、SHA-256、`evidence/index.yaml` 回填 | 已完成（DB head+0 行、trace 关联证据；性能引用 A 轨 D11A 实测 avg=41.3ms/p99=44.2ms） |
| 7 | 修复启动、重启与部署问题：启动失败、服务重启、OS 重启、部署/回退问题定位与修复 | 工作项 3–6 | 同 Commit 同 VM 复测、回归测试、真实日志 | 待开始 |
| 8 | 端到端联调：所有模块同 Commit 同 VM 启动并相互可追踪；与 A/B/C 轨输入联调 | 工作项 7；A/B/C 轨 D11 输入 | 全模块启动清单、trace 串联核对 | 待开始 |
| 9 | 证据归档与审查：整理 L2 证据入 `evidence/l2-kylin-vm/` 与 `evidence/index.yaml`；交由 E 轨非作者 Reviewer 审查 | 工作项 1–8 | 证据可复跑、`git diff --check`、审查材料 | 待开始 |

## 固定验收口径

- 所有模块在同一麒麟虚拟机、同一提交下稳定启动并可追踪；无实测证据的结论标为 `UNVERIFIED`。
- 日志与诊断输出不得包含记忆正文、候选标识、用户标识或敏感配置；任一泄露均为 Critical。
- 服务/OS 重启后模块状态可确认（systemd active、UDS 存在）；检索/索引一致性由 B 轨复测，D 轨提供部署与重启支持。
- 性能基线对照架构延迟预算（Embedding 查询 ≤180ms）。

## 跨轨依赖与不在范围

| 依赖 | 责任轨道 | D11D 处理方式 |
|---|---|---|
| Embedding/SDK 健康、Outbox consumer、VM 检测脚本 | A（PR #84 已合并） | 复用 health/诊断分项，不修改 A 轨实现 |
| 检索/索引/删除重建一致性、服务重启后索引状态 | B（D11B 进行中，PR #111） | 以稳定接口复测，问题反馈不代为实现 |
| MemoryClient、QML、OS Agent Hook 与演示输入 | C（D11C） | 消费其端到端输入验证环境，不改 QML/客户端 |
| 业务验收、安全确认、证据口径 | E（D11E） | 交付证据与诊断，交由 E 非作者审查 |
| D10D 精准遗忘持久化（ADR-015/017、outbox priority） | D（PR #112 进行中） | 本批次不实现遗忘持久化；如遇依赖，标注阻塞 |

## 当前状态与阻塞

- 准备阶段：已完成基线确认（`origin/main@47af2fa`）与本工作清单；分支 `feat/D11D-vm-integration` 已创建。
- 已完成第 1 项（基线与环境盘点）：记录见 `docs/day11/02_d11d_baseline_environment_inventory_20260901.md`；Vector Engine 版本（D11B `0k0.11` vs VERSION_MAP `0k1.0`）不一致已标记，待工作项 2 实测定案。
- 第 2 项（冻结统一环境）已完成：D11D 专用 VM 实测定案（vector 0k0.11/0k0.7、Python 3.12.3、DB head=`20260901_d10b_vector_ledger`、UDS），详见 `evidence/l2-kylin-vm/d11d_vm_service_l2_20260902.md`。
- 第 3 项（服务与安装）已完成：`install_kylin_memory.sh` 麒麟 VM L2 通过（安装/重启/回退/重装/socket/日志）。
- 尚未取得：D 轨负责人指定的最晚停止时间；D11D 专用麒麟 VM 联调环境（需确认复用 D11B 克隆 `Kylin-V11-2603-D11B-ffd20b9-Test` 或新建同 Commit 环境）；A/B/C 轨端到端输入。
- 上述事项未满足前，不将准备清单表述为已完成的联调能力。