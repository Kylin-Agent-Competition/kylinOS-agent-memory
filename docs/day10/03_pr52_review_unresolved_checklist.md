# PR#52 审查未完成修复清单

> 基线：当前分支 `feat/d4d-ipc-db-outbox` @ `d2b7205`（`fix(D4D): PR#52 审查收尾——11项修复+登记TD-D4D-001~003`）
> 依据：PR#52 最新一轮 review（lovezy0730-create，"第二轮复审结论"，`CHANGES_REQUESTED` / REWORK）
> 生成日期：2026-08-24

---

## 闭环进展（2026-08-24 推进后）

本轮已闭环 3 项（U-1/U-2/U-3），U-4/U-5 维持延期（已登记 TD，Day5+ 接线慢 handler/真实 consumer 前处理）：

| 序号 | 处理结果 |
|---|---|
| U-1 | ✅ 已修复：`app.py` 生产模式（`--no-migrate`）启动校验 `alembic_version` 表，缺失即 fail-fast（exit=2）；`systemd` ExecStart 显式加 `--no-migrate`；`db/engine.py` 新增 `has_alembic_version()`；补 `test_db_d4d.py` / `test_migrations_d4d.py` 回归 |
| U-2 | ✅ 已修复：`RESULT.md` / `verify_run.log` / `index.yaml` 补全 commit 绑定（原始 ed9949c / 补录 35e8c54 / 最终 HEAD）+ 上传文件 SHA256，并重算 `checksum_sha256` |
| U-3 | ✅ 已同步：`git rebase origin/main` 完成，`behind 2 / ahead 4` → `behind 0 / ahead 6`（旧 4 commit rebase 后新 SHA：ed9949c→b2a3d04、272c7b5→268a887、35e8c54→2770e26、d2b7205→9fe84c7）。**L1 仍需麒麟 VM / 装依赖环境重跑**（本机无 sqlalchemy/pydantic/alembic） |
| U-4 | 🟡 维持延期（TD-D4D-002）：deadline 抢占式需 Day5+ 接线慢 handler 前处理，当前 Gate 0 内置 handler 均快速，不阻断 |
| U-5 | 🟡 维持延期（TD-D4D-003）：Outbox 经典 claim→commit→process→mark 重构需 Day5+ 接线真实 consumer 前处理，当前无 consumer 整批快速失败，不阻断 |

---

## 结论速览

review 共提 13 项，`d2b7205` 已修复 9 项（Issue 1/2/5/7/8/9/10/11/12）、Issue 13 已确认通过、Issue 3/4 已登记 TD 延期。
**仍存在 5 项未完全闭环**，其中 3 项为"代码/证据/流程层面完全未处理"，2 项为"仅登记 TD、行为未改"。

| 序号 | 分类 | 问题 | 严重度 | 当前状态 |
|---|---|---|---|---|
| U-1 | 代码 | Issue 6：create_all / Alembic 双迁移路径未收敛 | Moderate | ❌ 未修复（仅 WARN，无校验） |
| U-2 | 证据 | L2 证据 commit 绑定不一致（RESULT.md/verify_run.log 仍标 ed9949c） | Evidence | ❌ 未修复 |
| U-3 | 流程 | 分支落后 main 2 个 commit 未同步 | 流程 | ❌ 未处理 |
| U-4 | 代码 | Issue 3：deadline 仍为事后判定（非抢占式） | Moderate | 🟡 仅登记 TD-D4D-002，行为未改 |
| U-5 | 代码 | Issue 4：Outbox 单事务持锁消费 | Moderate | 🟡 仅登记 TD-D4D-003，行为未改 |

---

## U-1 [Moderate] Issue 6 — create_all / Alembic 双迁移路径未收敛

- **问题**：应用默认仍走 `init_schema/create_all`，systemd 启动路径未强制唯一 migration 模式，`create_all` 与 Alembic 长期是两个 schema truth source。
- **当前代码现状**：
  - `memory-service/app.py:47-55`：默认 `init_schema(engine)`（即 `create_all`），仅打印一条 WARN 提示"生产先 `alembic upgrade head` 再 `--no-migrate` 启动"。
  - `packaging/systemd/kylin-memory.service:9`：`ExecStart=... kylin-memory-server --socket ...` **未加 `--no-migrate`**，生产默认仍是 `create_all`。
- **review 要求**：明确生产环境唯一数据库初始化/升级路径；建议"启动校验 `alembic_version` 表"。
- **待办动作**：
  1. 启动时校验 `alembic_version` 表存在（不存在则拒绝以"生产模式"启动，或强制要求先跑 migration）。
  2. systemd unit 的 ExecStart 显式加 `--no-migrate`（或改用唯一 migration 入口），消除 `create_all` 默认路径。
- **涉及文件**：`memory-service/app.py`、`packaging/systemd/kylin-memory.service`。

---

## U-2 [Evidence] L2 证据 commit 绑定不一致

- **问题**：证据头部标记 `commit: ed9949c`（原始提交），而补录步骤实际使用 `35e8c54`（及之后 `d2b7205`）修复后的 schema/migration，产生只有修复版才能通过的 `IDEMPOTENT_OK`，证据不能严格归属于当前 PR HEAD。
- **当前代码现状**：
  - `evidence/l2-kylin-vm/d4d_vm_verify_20260821/RESULT.md` 头部仍写 `commit: ed9949c ...`。
  - `evidence/l2-kylin-vm/d4d_vm_verify_20260821/verify_run.log` 头部 `=== commit === ed9949c ...`。
- **review 要求**：修正 RESULT.md/verify_run.log 中的 commit 说明，明确记录：① 原始验证 commit；② 补录验证 commit；③ 实际上传并验证的文件 SHA256；④ 当前最终证据对应的 HEAD。
- **待办动作**：
  1. 在 RESULT.md/verify_run.log 补充"原始 commit = ed9949c、补录 commit = 35e8c54（及 d2b7205）、最终 HEAD = d2b7205、上传文件 SHA256"。
  2. 证据绑定修正前，不建议将当前 HEAD 标记为 `HOST_VERIFIED`。
- **涉及文件**：`evidence/l2-kylin-vm/d4d_vm_verify_20260821/RESULT.md`、`verify_run.log`。

---

## U-3 [流程] 分支落后 main 2 个 commit 未同步

- **问题**：review 指出当前分支落后 `main` 2 个 commit，修复完成后需先同步最新 `main`，再重跑受影响测试与证据一致性检查。
- **当前状态**：`git rev-list --left-right --count origin/main...HEAD` = `2 4`（仍 behind 2 / ahead 4）。
- **review 要求（合并前最低要求 #8/#9）**：同步最新 main；同步后重新执行 L1，确认 evidence/index 无回归。
- **待办动作**：
  1. `git fetch origin && git rebase origin/main`（或 merge），解决可能的冲突。
  2. 在麒麟 VM / 装依赖环境重跑 D4D L1（当前 HEAD 为 67 passed，非 PR body 的 65）并更新 PR body。
- **说明**：本机未安装 sqlalchemy/pydantic/alembic，L1 无法本地执行，需在麒麟 VM 或补齐依赖后运行。

---

## U-4 [Moderate] Issue 3 — deadline 仍为事后判定（非抢占式）

- **问题**：`_dispatch` 中 `handler` 跑完才检查 `elapsed_ms > deadline_ms`，属于执行完成后判超时，非真正的抢占/取消语义；不打断执行中的 handler。
- **当前代码现状**：`memory-service/gateway/server.py:213-237` 逻辑未改，仍为事后判定；docstring 已如实标注"非抢占"，并登记 **TD-D4D-002**。
- **review 判定**：部分修复（docstring 对齐 + 登记 TD 即可）。
- **待办动作**：Day5+ 接线慢 handler（embedding/检索）前，将 deadline 改为抢占式（带超时的独立执行线程或等效中断）；当前 Gate 0 内置 handler 均快速，暂不阻断。
- **关联 TD**：`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` → TD-D4D-002。

---

## U-5 [Moderate] Issue 4 — Outbox 单事务持锁消费

- **问题**：`_poll_once` 在一个事务（`with self._lock: with self._engine.begin()`）中处理整批 consumer 调用，consumer 网络 I/O 期间持写锁不释放，会阻塞业务写。
- **当前代码现状**：`memory-service/outbox/worker.py:108-119` 逻辑未改，仍单事务批量处理；已登记 **TD-D4D-003**。
- **review 判定**：未修复（仅注释/登记 TD），建议 MUST-FIX-BEFORE-DAY5 TD。
- **待办动作**：Day5+ 接线真实 consumer 前，重构为经典 Outbox 模式：`claim → commit → 事务外 process → 新事务 mark`，consumer I/O 期间不持写锁；当前无 consumer 时整批快速失败，暂不阻断。
- **关联 TD**：`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` → TD-D4D-003。

---

## 已闭环项（供对照，无需再处理）

| Issue | 问题 | 修复位置 |
|---|---|---|
| 1 | PII 日志 | `gateway/handlers.py:41-45` 不再记录 query 正文 |
| 2 | get_turn/get_conversation 缺 user_id | `db/repositories.py:79` / `:121` 强制 user_id 过滤 |
| 5 | attempts≤3 与 config 脱钩 | `config.py:74` `outbox_max_retries: le=3` |
| 7 | conn_threads 不 prune | `gateway/server.py:102` 清理已结束线程 |
| 8 | uow `__import__("datetime")` hack | `db/uow.py:15` 顶部导入 + `datetime.now(timezone.utc)` |
| 9 | DAO OperationalError 包装不一致 | `db/repositories.py` 全部写操作补 `_wrap_locked` |
| 10 | toml 未知键静默忽略 | `config.py:150-151` 未知键 WARN |
| 11 | FTS 触发器漏 entry_type/user_id | `db/schema.py:140-144` WHEN 子句扩展 |
| 12 | 仓库根游离 L2 MD | 已移至 `evidence/l2-kylin-vm/d4d_vm_verify_20260821/` |
| 13 | 虚拟化检测硬编码 | review 已确认通过（无 VBoxManage 硬编码） |
