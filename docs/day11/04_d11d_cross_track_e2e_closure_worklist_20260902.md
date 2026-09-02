# D11D 续批开工工作清单：跨轨端到端闭环与收口（D 轨代行 · 准备阶段）

## 任务信息

- 施工项：D11 D 轨「同一虚拟机全功能联调」（台账 D11 行，负责人周子腾）。
- 授权：已取得 D 轨负责人授权，由 B 轨（高翌哲）代行 D11D 限定范围。
- 上一批：PR #115（分支 `feat/D11D-vm-integration`）已合并至 `main`（2026-09-02），进度 7/9；工作项 8 为 `PARTIAL / BLOCKED_BY_A_RUNTIME`（A 轨 cpp-bridge 未构建），工作项 9 证据归档已随合并关闭。
- 本批范围：D11D 剩余事项的跨轨闭环与收口——工作项 8 端到端联调（A 轨 bridge 就绪后的真实 Embedding/SDK 调用验证；B/C 输入到位后的同 Commit 全模块复测）与收口（跨轨输入核对、trace/DB/性能证据汇总、`evidence/index.yaml` 回填、Review 意见闭环）。不代行 A/B/C/E 轨实现或审查。
- 工作类型：`feat`（联调/集成闭环）。
- 工作分支：`feat/D11D-cross-track-e2e-closure`（基线 `origin/main@8cc4a89`；按提交分支要求命名，不含 `codex`）。
- 开始时间：2026-09-02（准备阶段）。最晚停止时间：进入实测前须由 D 轨负责人指定并确认。
- 当前进度：0/6（准备阶段；第 2 项 BLOCKED_BY_A_RUNTIME，未计完成）。

## 完成定义

在 D11D 指定的同基线麒麟虚拟机上，以同一 Commit 完成：真实 Embedding/SDK 调用非降级；memory-service、embedding/UDS 子服务、vector-engine、outbox 消费方与诊断脚本全模块稳定启动并可追踪；trace、数据库与性能证据可汇总；日志与诊断不泄露正文或敏感内容。本批联调基线为 `origin/main@8cc4a89`；若 A 轨 bridge 合入后 main 前进，则同步 main 并以最新 HEAD 为准。没有麒麟 VM 实测证据的结论必须标为 `UNVERIFIED`。

## 工作清单

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| 1 | 跨轨输入核对清单回填：按《D11D 跨轨输入核对清单》逐项核对 A/B/C 输入（A：Embedding/SDK 健康与性能；B：D11B 检索诊断/删除重建/重启后索引；C：端到端演示输入与调用路径），标注 `tested_commit` 与基线 | A/B/C 轨确认或补充（D11B 侧 B 轨自持） | 核对表 ☑；命令/退出码/日志/路径/哈希可复现 | 待开始（跨轨 pending 部分如实标注） |
| 2 | A 轨 cpp-bridge 构建/接线就绪确认（D11D 只消费、不实现 A 轨交付物） | A 轨（PR #100 等）合入并构建 | health `bridge_loaded=true`、`sdk_missing=false`、embed 非降级 | BLOCKED_BY_A_RUNTIME（待 A 轨闭环） |
| 3 | 真实 Embedding/SDK 调用验证：同 Commit 同 VM 执行 start→health→embed，采集真实向量维度与延迟/吞吐，对照架构预算（Embedding 查询 ≤180ms） | 工作项 2 | 真实日志 + `tested_commit` + 脱敏断言 | 待开始（依赖工作项 2） |
| 4 | main 最新 HEAD 同 Commit 全模块启动与追踪复测：memory-service/vector/systemd/诊断统一环境，服务重启/OS 重启后自启与状态可确认 | 工作项 1；D11D 主批次部署产物已在 main | `systemctl` active、UDS 存在、health/index state、trace 串联 | 待开始 |
| 5 | B/C 端到端输入联调：B 轨检索/删除/索引一致性接口复测，C 轨演示调用路径（普通聊天、跨会话、Tool、冲突、遗忘主演示）在同一 VM 可追踪 | B 轨 D11B/D13B 账本与 C 轨输入（C 轨真实 VM 交互复测以 main 最新为准） | 调用路径证据、trace/DB 关联、无敏感泄露 | 待开始（跨轨 pending） |
| 6 | 证据汇总与收口：trace/DB/性能证据归档 `evidence/l2-kylin-vm/`，`evidence/index.yaml` 回填 SHA-256 与 `tested_commit`/`evidence_commit`；L0/L1 回归、`git diff --check`、Review 意见回填 | 工作项 1–5 | 证据可复跑、checksum 一致、diff --check 通过、Review 结论回填 | 待开始 |

## 固定验收口径

- 所有结论以同一 Commit、同一麒麟 VM 实测为准；无实测证据一律标 `UNVERIFIED`，不冒充既有证据。
- 日志与诊断输出不得包含记忆正文、候选标识、用户标识或敏感配置；任一泄露均为 Critical。
- 服务/OS 重启后模块状态可确认（systemd active、UDS 存在）；检索/索引一致性按 B 轨口径复测，D 轨提供部署与重启支持。
- 性能基线对照架构延迟预算（Embedding 查询 ≤180ms）。
- 不越轨实现：A 轨 bridge/SDK、C 轨 QML/客户端、E 轨业务语义一律不代为实现或审查。

## 跨轨依赖与不在范围

| 依赖 | 责任轨道 | D11D 续批处理方式 |
|---|---|---|
| cpp-bridge 构建与真实 Embedding/SDK 接线 | A（PR #100 进行中） | 工作项 2 阻塞点；就绪前保持 BLOCKED_BY_A_RUNTIME，不代为实现 |
| 检索/索引/删除重建一致性、重启后索引状态 | B（D11B/D13B 已合并） | 复用 B 轨接口与账本复测，问题反馈不代为实现 |
| MemoryClient、QML、OS Agent Hook 与演示输入 | C（D11C） | 消费 C 轨输入验证统一环境，不改 QML/客户端 |
| 业务验收、安全确认、证据口径 | E（D11E） | 交付证据与诊断，交由 E 非作者审查 |
| 精准遗忘持久化（ADR-015/017、outbox priority） | D（PR #112 进行中） | 本批不实现遗忘持久化；如遇依赖，标注阻塞 |

## 当前状态与阻塞（准备阶段）

- 上一批 PR #115 已合并（2026-09-02）：docs/day11 工作清单（7/9）、`packaging/systemd/install_kylin_memory.sh`、`kylin-memory.service`（`RuntimeDirectoryMode=0700`）、7 组麒麟 VM L2 证据 + `evidence/index.yaml` 6 条 `D11D-L2-*`；D/E Reviewer 最终 APPROVE。
- 本批为纯文档准备：UTF-8 无 BOM、LF 行尾、无尾随空白，`git diff --check` 通过；未改动既有生产链路（Vector/FTS5/RRF）、SQLite 真源、部署脚本、冻结文档或其他轨道交付物。
- 尚未执行任何实测；凡涉及麒麟 VM 实测、真实 Embedding/SDK 调用、跨轨端到端结论，均保持 `UNVERIFIED` / `BLOCKED_BY_A_RUNTIME` / 跨轨 pending，直到 A 轨 bridge 与 B/C 输入就绪并在同 Commit 同 VM 复测通过。
- 最晚停止时间待 D 轨负责人指定；未满足上述前提前，不将本清单表述为已具备完整联调能力。
