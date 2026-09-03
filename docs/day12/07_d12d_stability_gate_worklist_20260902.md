# D12D 开工工作清单：功能冻结——故障注入、缺陷清理与稳定性 Gate（D 轨代行 · 准备阶段）

## 任务信息

- 施工项：D12 D 轨「功能冻结、联调缓冲与缺陷清理」（台账 D12-D 行，负责人：D＝周子腾）。
- 授权：已取得 D 轨负责人授权，由 B 轨（高翌哲）代行 D12D 限定范围（准备阶段，2026-09-02）。
- 工作类型：`fix`（故障注入定位后的安装脚本/systemd/诊断页缺陷清理；稳定性 Gate 的组织与证据汇总）。
- 工作分支：`fix/D12D-stability-gate`（基线 `origin/main@0820036`；按提交分支要求命名：`<类型>/<用途>`，不含 `codex`）。
- 本次范围（准备阶段）：建立 D12D 工作清单、基线口径与验收边界；不包含麒麟 VM 故障注入实测、缺陷修复代码或稳定性 Gate 达标结论。
- 开始时间：2026-09-02（准备阶段）。最晚停止时间：进入实测/实现前须由 D 轨负责人指定并确认。
- 当前进度：0/8（0%，准备阶段）。

## 完成定义

对照台账 D12-D 行完成定义「Critical=0，未安排 High=0，部署和故障恢复可重复」：

1. 在同一基线麒麟 VM、同一 Commit（`main` 最新）上执行服务/OS 重启、权限、磁盘与 SDK 故障注入，全部恢复路径可重复、可复核；
2. 故障注入暴露的安装脚本、systemd 单元与诊断页/诊断脚本缺陷完成修复，并跑通 L0/L1 回归；
3. 主持稳定性 Gate：汇总故障注入矩阵、修复清单与恢复可重复证据，支撑 Critical=0、未安排 High=0 结论（最终以 E 非作者 Reviewer 审查为准）；
4. 日志与诊断输出不泄露记忆正文、候选标识、用户标识或敏感配置；任一泄露均为 Critical。

没有麒麟 VM 实测证据的结论一律标 `UNVERIFIED`；不以本地/L1 或历史 L2 证据冒充当前 Commit 的稳定性结论。

## 工作清单

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| 1 | 基线与环境盘点（准备阶段）：记录 `origin/main@0820036`、D11D 已合并交付（PR #115：`packaging/systemd/install_kylin_memory.sh`、`kylin-memory.service`、JSON 日志/trace_id/脱敏诊断与 L2 证据）、D11D 专用 VM（`Kylin-V11-2603-D11D-47af2fa-Test`）与冻结环境、VERSION_MAP、UDS/权限基线与磁盘余量；确认 D12D 专用 VM/快照复用或新建 | `origin/main`；D11D 合并基线 | `git status`、仓库审阅、快照/版本/哈希核对 | 待开始（基线口径已记录于本清单；VM 实测待 D12D 专用环境复核） |
| 2 | 服务/OS 重启故障注入与恢复：`systemctl --user stop/start/restart kylin-memory`、服务自启、OS 整机重启后自启与状态确认（active、UDS/socket、health、index/DB 状态、检索可调用）；定位并修复启动/重启问题 | 工作项 1；D11D systemd 部署产物 | 真实 VM 日志、重启前后状态对比、恢复路径复跑 | 待开始（无 VM 证据前为 `UNVERIFIED`） |
| 3 | 权限/安全故障注入：UDS socket 与 DB 文件权限（0700/0600）、`RuntimeDirectoryMode`、用户/组隔离、socket 固定跨用户路径风险（呼应 TD-049）、KYSEC 授权；越权访问与失败关闭路径 | 工作项 1；D11D 权限加固 | 越权/失败路径实测、权限核对、KYSEC 实测或如实标 `UNVERIFIED` | 待开始 |
| 4 | 磁盘故障注入：磁盘满/只读/数据目录缺失与写入失败场景下服务 fail-closed、日志不泄露、恢复后行为可重复 | 工作项 1 | 真实 VM 故障注入、日志断言、恢复复跑 | 待开始 |
| 5 | SDK 故障注入（跨轨消费，只消费不实现）：Embedding/SDK 超时、挂死、异常返回、模型/Bridge 缺失时 memory-service 降级与恢复（A 轨 D12A PR #100 已合并：health executor 分项/挂死恢复与麒麟 VM L2 就绪） | A 轨 D12A（PR #100）合入并构建 | health 分项、降级/恢复真实日志、脱敏断言 | 待开始（前置已就绪；VM 实测待 D12D 专用环境） |
| 6 | 安装脚本/systemd/诊断页缺陷修复：`install_kylin_memory.sh`、`kylin-memory.service`、health/诊断端点与诊断命令/脚本在故障注入暴露问题上的修复；L0/L1 回归（`py_compile`、相关 pytest、`git diff --check`） | 工作项 2–5 暴露的缺陷清单 | 复跑安装/回退/重启恢复、pytest 全绿、diff --check | 待开始 |
| 7 | 稳定性 Gate 主持与证据收口：汇总故障注入矩阵（场景×结果×恢复）、修复清单与证据至 `evidence/l2-kylin-vm/`，`evidence/index.yaml` 登记 SHA-256 与 `tested_commit`；输出 Critical/High 清零核对表；交由 E 非作者 Reviewer 审查 | 工作项 1–6；证据目录与 `evidence/index.yaml` | 证据可复跑、checksum 一致、Gate 材料完整 | 待开始 |
| 8 | 收口与跨轨核对：同 Commit 同 VM 复测；按固定口径核对 B（重启后检索一致性，TD-055 中 B 侧跟踪项）、C（D→C 端到端真实输入）与 E（安全/假实现）输入；Review 意见回填 | 工作项 1–7；B/C/E 输入 | 核对表 ☑、trace/DB 关联、Review 结论 | 待开始（跨轨 pending 部分如实标注） |

## 固定验收口径

- 同一 Commit、同一麒麟 VM 实测为准；无实测证据一律标 `UNVERIFIED`，不冒充既有证据。
- 完成定义：Critical=0，未安排 High=0（按技术债总账责任与 Gate 口径核对）；部署与故障恢复可重复（安装/回退/重启恢复脚本可复跑）。
- 日志与诊断输出不得包含记忆正文、候选标识、用户标识或敏感配置；任一泄露均为 Critical。
- 服务/OS 重启后模块状态可确认（systemd active、UDS 存在、health/index state、检索可用）。
- 不越轨实现：SDK 故障注入只消费 A 轨能力；A（Bridge/SDK）、B（检索/索引）、C（QML/客户端）、E（业务/安全语义）一律不代为实现或审查。

## 跨轨依赖与不在范围

| 依赖 | 责任轨道 | D12D 处理方式 |
|---|---|---|
| SDK 稳定性修复与 health executor 分项、Bridge 假实现/吞异常检查 | A（D12A PR #100 已合并至 `main@0820036`，含麒麟 VM L2） | 工作项 5 前置已就绪；只消费不实现 |
| 服务/OS 重启后检索/索引一致性、删除残留、重建一致 | B（D12B 已合并 PR #119/#121；TD-054/055 按 Issue #117/#118 跟踪） | 以 B 轨接口与账本口径复测；TD-055 中 D 轨侧重启/部署验证由本批承担，B 侧跟踪项反馈不代实现 |
| MemoryClient、QML、OS Agent Hook 与 D→C 端到端真实输入 | C（D11C PR #116 已合并；C-D12 PR #127 进行中） | 消费 C 轨输入验证 D→C 路径；不改 QML/客户端 |
| 业务验收、安全与假实现独立审查、稳定性 Gate 结论 | E（D12E） | 交付故障注入/修复/Gate 证据，由 E 非作者 Reviewer 审查 |
| D10D 精准遗忘持久化（ADR-015/017、outbox priority）、D11D 剩余收口 | D（D10D PR #112/#120 已合并；D11D PR #115 已合并、续批 PR #125 已关闭未合并） | 本批以稳定性缺陷清理与 Gate 为主；D11D 剩余收口是否并入本批待 D 轨确认；如遇依赖标注阻塞，不扩张为遗忘持久化实现 |

## 当前状态与阻塞（准备阶段）

- D11D（PR #115）已合并至 `main`；`main` 现为 `0820036`（新增：A 轨 D12A #100、C 轨 D11 #116、D10D #120、D8D 契约 #122/#126）。A 轨 D12A（#100）已合并并完成麒麟 VM 真实 SDK L2（7/7），D12D 工作项 5 前置已就绪。D11D 续批 PR #125 已关闭（未合并）；其工作项 8 剩余收口（同 Commit 全模块复测、D→C 端到端）是否并入本批待 D 轨确认。
- D8D 相关 PR #126（ADR 冻结）、#128（持久化实现）与 C-D12 PR #127 进行中，均不在本批范围，不代行。
- 本批为纯文档准备：UTF-8 无 BOM、LF 行尾、无尾随空白，`git diff --check` 通过；未改动既有生产链路（Vector/FTS5/RRF）、SQLite 真源、部署脚本、冻结文档或其他轨道交付物。
- 尚未执行任何麒麟 VM 实测；凡涉及故障注入、缺陷修复、稳定性 Gate 达标与 TD-055 关闭结论，均保持 `UNVERIFIED` / 跨轨 pending，直到对应环境与跨轨输入就绪并在同 Commit 同 VM 复测通过。
- 最晚停止时间待 D 轨负责人指定；未满足上述边界前，不将本清单表述为已具备稳定性 Gate 达标能力。

## PR 状态与提交

- PR 状态：Draft（本批为 D12D 开工准备：工作清单 + 基线口径；VM 实测与修复结果将在后续批次回填）。
- 建议标题：`fix(D12D)：功能冻结——故障注入、缺陷清理与稳定性 Gate（开工工作清单 + 准备）`。
- 分支名不含 `codex`；PR 正文、评论、提交信息均使用中文。
- 后续代码/证据批次在取得单独 `commit`/`push` 授权后提交；Draft→Ready 与合并由用户手动决定。

---

## 2026-09-03 Path C 进展（负责人确认口径）

- 口径：真实 Embedding/SDK 调用**采信 A 轨 D12A L2**（D12A-L2-VERIFY，HOST_VERIFIED/E4）；D 轨 VM 完成非 embed 的同 Commit（0820036）项。
- 已完成（麒麟 VM Kylin-V11-2603-Env-V2-Main）：kylin-memory 安装/启动、服务重启、**OS 整机重启自启**、UDS IPC fail-closed、Vector active、权限 0700/0600、日志含 trace 无正文。
- 证据：docs/day12/08_d12d_pathc_none_embed_evidence_20260903.md + evidence/l2-kylin-vm/d12d_pathc_*.txt + evidence/index.yaml（D12D-PATHC-01~06）。
- 尚未进入 D12D 工作项 2–8 的完整故障注入实测；相关结论以 08 文档边界为准（不冒充业务闭环/真实 embed 本 VM 实测）。