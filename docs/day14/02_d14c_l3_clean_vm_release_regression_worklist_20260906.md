# D14C 任务卡：L3 干净虚拟机发布回归（C 轨，B 代执行）

| 字段 | 内容 |
|------|------|
| 施工项 | D14 C 轨「L3 干净虚拟机发布回归」（台账 D14-C，original_owner：C＝刘承恩） |
| 执行身份 | current_executor：B＝高翌哲（已获用户明确授权，代 C 轨执行；本卡不改变台账责任归属） |
| 任务编号 | D14C（承接 D13C #134 合并后主仓状态；正式结论依赖 D 轨 ACTIVE 与冻结环境） |
| 工作类型 | `test`（真实发布环境集成 + L3 Runtime Evidence Upgrade） |
| 工作分支 | `test/D14C-l3-clean-vm-release-regression`（按提交分支要求命名：`<类型>/<用途>`，不含 `codex`） |
| 唯一被测基线 | `origin/main@6a1218441feeb7b1d96411e60f993061767f3aba`（= PR #134 D13C 合并提交；已含 PR #151 Host Mapping） |
| 关键上游 | PR #151 Host Mapping（TurnExtractionAdapter / ProductionSourceResolver 已入 main）；PR #134 D13C 会话评测与稳定性（已入 main） |
| 初始状态 | `PREPARED` |
| 禁止提前表述 | `L3 PASS` / `HOST_VERIFIED` / `production ready` / `D14C complete` |
| 审查责任 | D 主审；涉及安全/评测影响时 E 补审（人工 Review，不在本批范围内） |
| 编制日期 | 2026-09-06 |

---

## 1. 一页判定（冻结）

依据 `可直接查看/D14C_工作内容与详细施工清单.md` 的当前判断：

```text
D14C preparation: GO
D14C implementation / harness preparation: GO
D14C formal clean-VM L3 execution: CONDITIONAL GO
D14C formal PASS: NO-GO
until runtime activation / frozen environment / evidence gates close
```

D14C 不是：

- 再做一轮 L0 Mock；
- 再实现一套假的主演示；
- 重写 #151 已交付的 Adapter/Resolver；
- 用 Windows/WSL 结果标 `HOST_VERIFIED`；
- 用 `context=[]` 或纯 IPC 延迟冒充完整知识检索。

D14C 是：把 D13C/C-HM 已实现功能与测试，在干净麒麟 VM 真实发布环境上集成，产出 L3 Runtime Evidence。

---

## 2. 冻结范围（Scope Freeze）

正式运行前冻结以下字段，形成可证明的单一身份链：

| 冻结字段 | 要求 | 当前值 |
|---|---|---|
| tested_commit | 正式运行前重跑 `git rev-parse HEAD` / `git status --porcelain` / `git log -1 --oneline` 并记录 | 候选 `main@6a121844…`（运行时以实际冻结为准） |
| release artifact | 发布包（SHA-256、版本） | 待 D14D/D14A 交付 |
| AI Assistant artifact | binary 路径、SHA-256、版本 | 待定 |
| MemoryClient artifact | build hash、版本 | 待定 |
| Memory Service artifact | commit、PID、cmdline、cwd、systemd 状态 | 待定 |
| VM snapshot | 干净快照标识 | 待 D14D |
| evidence root | 全新目录，不复用历史目录 | 待定 |

冻结顺序（DoD）：

```text
Git SHA → 构建物 → 安装物 → 正在运行进程
```

---

## 3. Formal Prerequisites（开跑前置）

正式 L3 开跑前 8 条硬门（Gate）建议冻结为：

```text
G1 tested_commit 已冻结
G2 clean VM / release artifact 已确定
G3 #151 Adapter/Resolver 已在 tested commit
G4 AI Assistant artifact 与 Host DB schema 已绑定
G5 trusted host identity 已批准
G6 所需 production routes 已 ACTIVE
G7 MemoryContext 正式 mapping 已冻结
G8 evidence root 为全新目录
```

判定：

```text
G1-G8 全 PASS → FORMAL RUN GO
任一 P0 BLOCKED → 只允许 PRE-RUN / DIAGNOSTIC，不产生 D14C Formal PASS
```

前置还包括阶段 B 需先清空的 Production Blocker（见第 6 节 Blocker 矩阵）。

---

## 4. Out-of-Scope（范围外 / 不代行）

- 不重写/不修改 #151 已交付的 Adapter/Resolver；不修改 `memory-service` production handler 注册与 `PRODUCTION_RESOLVER_STATUS` 常量（D 轨范围）。
- 不直接改状态常量越权解锁：`turn.finalized` / `event.ingest` / `forget.preview` / `forget.execute` 的 ACTIVE/CANDIDATE 决定权在 D 轨。
- 不实现 A 轨发布包/Bridge/SDK、不代替 D 轨 trusted host identity 审批与 Seal、不代替 E 轨 Gold/Threshold 与封存、不代替 D13D 环境冻结与 Execution Seal。
- 不以 MockGateway / test-only fake / fixture-only runtime 冒充真实运行。
- 禁止手工 SQL 删除替代 forget 真实事务；禁止脚本直接伪造 Tool event。
- 不把 WSL/L0/L1/历史 VM 证据写成当前 Commit 的 L3 结论；正式结论前一切 Runtime 相关标 `UNVERIFIED`。

---

## 5. Evidence Requirements（证据要求）

- 真实运行链：麒麟 AI Assistant → MemoryClient → Unix Domain Socket → Memory Service → Chat DB。
- 运行时身份记录：binary path、SHA-256、PID、cmdline、package/build version；服务侧 `systemctl --user show kylin-memory.service`（MainPID/ExecStart/FragmentPath/ActiveEnterTimestamp）。
- 日志正文安全：禁止复制正文到日志；正文只使用 `user_text_sha256` / `assistant_text_sha256` 等 hash/ID/长度做一致性证明。
- Evidence Package：`evidence/l3-kylin-vm/d14c_<UTC_RUN_ID>/`；最终登记 `evidence/index.yaml`，每项含 evidence path、SHA-256、tested commit、environment、status。
- 状态只使用：`VERIFIED` / `FAILED` / `BLOCKED` / `UNVERIFIED`。
- 原始证据可复核：命令、stdout/stderr、exit code、DB checkpoint、raw logs 一并留存。

---

## 6. 工作清单（按 D14C-00~19 展开，状态以任务卡登记为准）

### 阶段 A — 开工准备

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-00 | 建立正式任务卡（本文件），冻结 scope / tested_commit / formal prerequisites / out-of-scope / evidence requirements | 用户授权（B 代 C 轨执行） | 任务卡字段齐全、初始状态 `PREPARED`、无禁止表述 | 进行中（本批） |
| D14C-01 | 冻结唯一被测基线：Git SHA、release artifact、AI Assistant/MemoryClient/Memory Service artifact、VM snapshot、runtime 身份 | `origin/main` | 身份链可复核（SHA→构建物→安装物→进程） | 待开始 |
| D14C-02 | 核对 Host Mapping 是否可进入 production：确认 #151/#134 已入 tested commit；检查 `turn.finalized` / `event.ingest` / `forget.preview` / `forget.execute` 当前处于 ACTIVE/CANDIDATE/BLOCKED_BY_HOST_MAPPING/UNSUPPORTED_METHOD 的哪一种；只记录，不改状态 | #151 已入 main | 状态核查记录；无 C 轨改状态常量行为 | 待开始 |

### 阶段 B — 先清 Production Blocker

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-02b | trusted host identity 状态核对并形成 blocker matrix | D 轨审核结论 | 信任边界结论记录 | 待开始（D 轨） |
| D14C-06 | PreChat / MemoryContext 真链路：冻结完整 empty MemoryContext mapping（payload identity / context_version / timestamp / token budget / safe skipped-status）后，验证有记忆（retrieve→assemble→inject）与无记忆（返回冻结 empty MemoryContext，非裸 `[]`） | C/D/E 联合冻结 empty MemoryContext | AI Assistant 实际请求观察到正式 MemoryContext 注入 | 待开始（跨轨冻结） |

### 阶段 C — 单链路 L3

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-03 | 真实启动 AI Assistant + MemoryClient + Memory Service（UDS 连通；记录版本/hash/PID/socket/DB） | 干净 VM、发布物 | `systemctl --user is-active`；socket stat；真实连通 | 待开始 |
| D14C-04 | 真实正文 Resolver 验证（source_reference→宿主 Chat DB→User/Bot final；流式中间行不误认；无终稿/JSON 损坏/session 错配 fail-closed；不跨上一 BotFinal、不串 turn） | D14C-03 | resolver=HOST_VERIFIED；plaintext_log_leak=0 | 待开始 |
| D14C-05 | `turn.finalized` 真实 L3 写链路（正常 finalize、Stop、Retry 真实验证；`retry_of_turn_id != turn_id`；不污染旧 turn） | D14C-03/04；路由可用 | DB 字段核验（session_id/turn_id/event_id/finalization_reason/stop_reason/retry_of_turn_id…） | 待开始 |
| D14C-07 | 真实 Tool 路径（SUCCESS/FAILED/CANCELLED 三态；trace_id/tool_name/arguments/status/result/error/started_at/finished_at/tool_call_id） | 干净 VM、GUI 可操作（Wayland 无 xdotool → 人工 GUI 真实触发） | GUI 真实操作→Hook→MemoryClient→Service→Evidence 三态闭环 | 待开始（人工 GUI） |
| D14C-08 | TD-008 MemoryContext 注入点实证：Hook A / chatAsync 请求前 instrument 捕获结构，敏感字段 hash/redact | 宿主可 instrument | TD-008 `NOT_OBSERVED`→`HOST_VERIFIED` | 待开始 |

### 阶段 D — 主演示与语义

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-09 | Conflict / Lifecycle 真链路（真实事件进 production pipeline；old/new/winner/decision/status/version/supersedes/后续检索一致；禁止直接改 DB 制造冲突） | D14C-03 | 冲突产生→决策→持久化→lifecycle 更新→检索一致 | 待开始 |
| D14C-10 | Forget Preview/Execute 真链路（preview→awaiting_confirmation→确认→execute→实时查询→重建后复验；target 删/must_keep 留/cross-user 不受影响/vector/FTS/cache 无残留/重启不复活） | D 轨 forget 路由 ACTIVE；否则标 `BLOCKED_BY_D_ROUTE_ACTIVATION` | 删除后残留 0；禁止手工 SQL 删除替代 | 待开始（D 轨路由） |
| D14C-11 | 完整五步主演示 5 rounds（Step1 PreChat/Step2 PostTurn/Step3 Tool/Step4 Conflict+Lifecycle/Step5 Forget） | 上述链路 | 5/5 rounds complete；逐轮记录 execution_record_id/stability_round/session_id/step_id/method/status/stage/latency/trace/DB checkpoint | 待开始 |
| D14C-12 | Stop / Retry / Deadline(5000ms) / Reset（复用 #134 已冻结语义） | #134 语义已入 main | L0 contract PASS → L3 Runtime PASS | 待开始 |
| D14C-13 | 跨会话隔离（Session A/B 同 scenario 可比较；A 记忆不进 B；B Tool/Forget 不影响 A；reset 无跨 session stale write） | D14C-11 | comparable_pair_count>0；cross_session_isolation=PASS；否则 fail-closed | 待开始 |

### 阶段 E — 稳定性

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-14 | 服务重启 + OS 重启（restart memory service→重跑关键路径→reboot Kylin OS→登录→确认 user service→启动 AI Assistant→重跑关键路径；service active/socket 重建/DB 保留/已有 memory 可检索/已删 memory 不复活/pending 不复活） | 干净 VM 自启能力 | service restart PASS；OS restart PASS | 待开始 |

### 阶段 F — 评测与性能

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-15 | 复用 #134 Evaluator（真实 raw→D13C session bundle→`scripts/run_d13c_session_eval.py`→report）；不写新评测器；只消费真实 VM evidence | #134 已入 main | 正式指标：step_completion_rate / isolation_pass_rate / guardrail_critical_count / ipc_method_coverage / stop_retry_violation_count / cross_session_isolation_pass_rate / latency p50/p95 | 待开始 |
| D14C-16 | 性能 sanity：PreChat retrieval / PostTurn / Tool event / Forget 延迟 | D14C-11 | 记录 P50/P95/mean/max（按通道）；`echo`/`context=[]`/纯 IPC 不冒充 ≤500ms 正式知识检索 | 待开始 |

### 阶段 G — 封存

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-17 | Evidence Package：`evidence/l3-kylin-vm/d14c_<UTC_RUN_ID>/`（environment/runtime identity/raw logs/DB checkpoints/SHA256SUMS） | 阶段 C-F | 包完整、可复核 | 待开始 |
| D14C-18 | Evidence Index：登记 `evidence/index.yaml`（path/SHA-256/tested commit/environment/status） | D14C-17 | 每项字段齐全；状态限 VERIFIED/FAILED/BLOCKED/UNVERIFIED | 待开始 |

### 阶段 H — 回退与收口

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| D14C-19 | 回退验证：还原原 AI Assistant 包/二进制、移除 hook/preload、还原 KySec 权限、重启、原助手可启动；不留永久 LD_PRELOAD/临时 .so/过宽 KySec 授权/测试 socket | 阶段 C-F 真实改动 | rollback = PASS | 待开始 |
| Review 收口 | 处理 D/E Review 意见并回填本清单与 PR | Review 可用性 | Review 结论 | 待开始（人工） |

---

## 7. 固定验收口径

- 完成定义（冻结建议）：在一台干净银河麒麟 VM 上，绑定唯一 tested commit 与唯一发布包，真实启动麒麟 AI 助手、MemoryClient、Memory Service，完整执行主演示链路，并证明写入、检索、Tool、Conflict/Lifecycle、Forget、Stop/Retry、Deadline、Reset、跨会话隔离在真实运行时成立；所有结论均可由原始证据复核。
- 正式 L3 达标结论只基于同一干净快照 VM 实测 + 冻结环境；否则一律标 `UNVERIFIED`。
- 任何结论不得提前写 `L3 PASS` / `HOST_VERIFIED` / `production ready` / `D14C complete`。

---

## 8. Blocker 矩阵（当前，跨轨责任）

| Blocker | 影响 | 责任 |
|---|---|---|
| trusted host identity 未冻结 | production route 无法安全 ACTIVE | C 供输入 + D 审信任边界 |
| `turn.finalized` 等 route 未 ACTIVE | L3 PostTurn/Forget 卡住 | D 轨激活 |
| empty MemoryContext mapping 未冻结 | PreChat 正式契约不成立 | C/D/E 联合冻结 |
| Forget route 未 ACTIVE | Demo Step 5 卡住 | D+C |
| Wayland 无 xdotool | 自动 Tool 触发困难 | 人工 GUI 真实触发 |
| VM 构建依赖缺失 | clean VM 不宜现场开发编译 | 发布轨提前准备构建物 |
| D13D 未正式冻结 | 不能形成最终发布冻结证据 | D 轨 |
| main 测试期间移动 | evidence 脱钩 | freeze tested_commit |

本批只记录，不代行其他轨道处置；需其他轨道处置的事项列为跨轨依赖。

---

## 9. PR 状态与提交

- 本批性质：D14C-00 开工准备（任务卡 + scope 冻结），纯文档，无生产代码改动。
- PR 状态：Draft（VM 实测结果将在后续批次回填；Draft→Ready 与合并由用户手动决定）。
- 标题（建议）：`test(D14C)：L3 干净虚拟机发布回归（开工任务卡 + 准备）`。
- 分支名不含 `codex`；PR 正文、评论、提交信息均使用中文。
- `commit` / `push` / 新建 PR / 合并 PR 分别需要用户明确指令；默认不执行 `git add`。
