# PR #65 第二轮 Review 待办追踪（REWORK）

- **编制日期**：2026-08-27
- **编制人**：opencode（D 轨开发 Agent）｜Reviewer：lovezy0730-create
- **基线**：PR #65 Base `main @ 11afb36c` → HEAD `5e9e1f43`（分支 `feat/d5d-ipc-pr2`，第 2 轮复审结论 **REWORK**，当前禁止合并）
- **输入**：PR #65 第二轮 Review（2026-08-27 15:15，`state=CHANGES_REQUESTED`，附独立探针实证）
- **目的**：合并前逐项闭合 2 HIGH 阻断 + 4 MEDIUM，补齐缺失测试路径，并产出复审回复所需证据。

> 红线提示：B1（跨用户污染）、B2（软删除数据可检索）为 Reviewer 实证复现问题，**禁止转为合并后技术债**，必须在本 PR 合并前修复。

---

## 一、Blockers（HIGH，必须合并前闭合）

### B1｜High｜跨用户会话与 Turn 写入污染（已实证复现）

- **位置**：`memory-service/gateway/handlers.py`（`turn_finalized_handler`）、`memory-service/db/uow.py`（`save_turn_with_outbox`）
- **现象**：用户 B 以 `uB / s1 / H-1` 提交可更新用户 A 的原 Turn，并向 B 泄漏 A 的 `conversation_id / db_turn_id`。
- **待办**：
  - [x] 1.1 对已存在 `session_id` 强制核验所属 `user_id`，不匹配即拒绝
  - [x] 1.2 Turn 查询与更新链路实现用户隔离（按 `(user_id, session_id, host_turn_id)` 定位）
  - [x] 1.3 用户不匹配时返回冻结契约内安全错误（不得泄漏已有 Conversation/Turn 标识）
  - [x] 1.4 失败请求不得修改 Turn / Outbox / 幂等缓存
  - [x] 1.5 补充可复现的跨用户隔离回归测试（A 写 B 抢占场景 → 拒绝）
  - 修复位置：`memory-service/db/repositories.py`（`upsert_conversation` 所有权校验 + 新增 `ConversationOwnershipError` / `get_conversation_with_user`；`find_turn_by_host` 增加 user join）、`memory-service/db/uow.py:156`（传 user_id）、`memory-service/gateway/handlers.py`（`_business` 前置所有权校验 + 双层防御）
  - 测试：`memory-service/tests/test_turn_finalized_pr2.py`（`test_t1_cross_user_session_pollution_blocked` / `test_t1_find_turn_by_host_user_scoped` / `test_t1_conversation_ownership_dao_layer`）

### B2｜High｜downgrade 使软删除记忆重新进入 FTS（已实证复现）

- **位置**：`migrations/versions/20260826_add_trace_id.py`
- **现象**：downgrade 重建 `memory_fts` 无条件回填全部记录，`is_deleted=1` 正文经 `MATCH` 可重新命中。
- **待办**：
  - [x] 2.1 回填 SQL 增加 `WHERE is_deleted = 0`
  - [x] 2.2 迁移测试：正常记录 + 软删除记录 → 正常可命中、软删不可命中
  - [x] 2.3 验证 upgrade → downgrade → upgrade 往返成功
  - [x] 2.4 验证触发器、外键及 `PRAGMA foreign_key_check` 正常
  - 修复位置：`migrations/versions/20260826_add_trace_id.py:163-166`
  - 测试：`memory-service/tests/test_migrations_trace_id_pr2.py`（`test_downgrade_excludes_soft_deleted_from_fts` / `test_downgrade_upgrade_roundtrip_fts_matchers`）+ 既有 `test_downgrade_returns_001_schema` / `test_downgrade_preserves_data_and_fts` 保留

---

## 二、MEDIUM（需修复并随回复附证据）

### M3｜TurnFinalizedValidator 契约校验不完整

- **位置**：`memory-service/gateway/handlers.py`（validator 部分）
- **待办**：
  - [x] 3.1 必填 ID/引用拒绝空字符串 / 纯空白字符串
  - [x] 3.2 `schema_version` 严格校验 `major.minor`
  - [x] 3.3 时间字段要求带时区，拒绝无时区时间 / 纯日期字符串
  - [x] 3.4 写入 Outbox 的时间统一规范化为 UTC 毫秒
  - [x] 3.5 等价时间表达不改变幂等 fingerprint 一致性
  - [x] 3.6 错误响应不泄漏原始输入（脱敏/拒绝回显）
  - [x] 3.7 补对应边界测试
  - 修复位置：`memory-service/gateway/handlers.py`（validator 空串校验 / `re.fullmatch(r"1\.\d+")` / `_require_iso_ts` 时区校验 / `extra_payload` 走 `_canonical_ts`）
  - 测试：`memory-service/tests/test_turn_finalized_pr2.py`（`test_t9_*` 系列 + 既有 invalid_payload 参数化 + insert_ok outbox 断言更新为 UTC 毫秒）

### M4｜event_id 与 Worker 跨线程日志关联未闭合

- **位置**：`memory-service/observability/`（request_context + JsonFormatter + PiiSanitizeFilter）、Worker
- **待办**：
  - [x] 4.1 Request Context 与 JSON Formatter 完整包含 `event_id`
  - [x] 4.2 Worker 能从 Outbox payload 恢复 `trace_id / event_id`
  - [x] 4.3 成功 / 重试 / Dead Letter 日志可跨线程关联
  - [x] 4.4 每次事件处理结束后正确清理上下文
  - [x] 4.5 `traceback`、`exc`、外部 `source_reference` 均经过脱敏
  - [x] 4.6 补 Gateway → DAO → Worker 关联（任务卡 L2 验收要求）测试
  - 修复位置：`memory-service/observability/request_context.py`（event_id / 向后兼容默认空串）、`json_logging.py`（event_id 字段 + exc 脱敏）、`outbox/worker.py`（`_process_event` 恢复上下文 + finally 清理 + `_fail` last_error 脱敏）、`gateway/handlers.py`（turn handler set event_id）、`service/source_resolver.py`（source_reference 脱敏日志）
  - 测试：`memory-service/tests/test_observability_pr2.py`（`test_worker_restores_trace_event_and_clears` / `test_request_context_event_id_backward_compat` + 既有上下文测试更新）

### M5｜health 业务状态仍可能错误报告为 `ok`

- **位置**：health handler、`worker.metrics()`
- **待办**：
  - [x] 5.1 区分响应 envelope `status` 与业务数据 `data.status`
  - [x] 5.2 Outbox metrics 异常 / 返回哨兵值（如 `backlog=-1`）时，`data.status` 置为 `degraded`
  - [x] 5.3 补 DB/metrics 异常、busy、Worker 未启动及哨兵值路径测试，断言真实业务状态
  - 修复位置：`memory-service/gateway/handlers.py`（`health_handler` 业务状态判定）
  - 测试：`memory-service/tests/test_observability_pr2.py`（`test_health_status_*` 5 条 + 既有 `test_health_degraded_when_worker_metrics_fails` 兼容：信封 ok、data.status=degraded、backlog=-1）
  - 待裁决项见 `docs/day10/11_pr65_rework_fix_plan.md` §九.1（无 Worker 判 degraded 语义）

### M6｜validation profile 与证据入口未闭合

- **位置**：CLI 注册入口、`memory-service/service/source_resolver.py`
- **待办**：
  - [x] 6.1 为 `--register-turn-finalized` 注入可加载映射（当前空 `InMemorySourceResolver()` 无法真实正向验证）
  - [x] 6.2 验证入口受控，production 不会误启用
  - [x] 6.3 证明默认 production 保持 `UNSUPPORTED_METHOD`
  - [x] 6.4 validation profile 可完成 Gateway → UoW → SQLite + Outbox 正向写入
  - [x] 6.5 resolver 未命中时安全失败
  - [x] 6.6 失败后不留下 Turn / Outbox / 幂等缓存半成品
  - [x] 6.7 文档 L2 操作方式与真实代码入口一致
  - 修复位置：`memory-service/service/source_resolver.py`（`load_resolver_from_json`）、`memory-service/app.py`（`--validation-sources` 仅在 `--register-turn-finalized` 分支解析）
  - 文档：`docs/day10/05_d5d_task_list_20260826.md` L2-2、`docs/day10/09_development_report_pr2.md` L2-2 更新
  - 测试：`memory-service/tests/test_turn_finalized_pr2.py`（`test_t8_load_resolver_from_json_and_write`）+ 既有 `test_turn_finalized_resolver_miss_internal_error` / `test_turn_finalized_unsupported_in_default_profile`

---

## 三、测试缺口补齐（B1/M3 之外必补用例）

- [x] T1 跨用户 session/turn 隔离（A/B 竞争复现用例）
- [x] T2 downgrade 后软删除记录不进入 FTS
- [x] T3 并发 `IntegrityError` 幂等回查（fingerprint compare + unwrap）
- [x] T4 fingerprint 一致时 unwrap 首次响应
- [x] T5 fingerprint 不一致时返回 `INVALID_REQUEST`
- [x] T6 Worker 跨线程恢复 `trace_id / event_id`
- [x] T7 health `data.status=degraded`（含哨兵值路径）
- [x] T8 validation profile 正向写链路
- [x] T9 严格 `major.minor`、非空 ID、带时区时间边界

落点：
- T1/T3/T4/T8/T9 → `memory-service/tests/test_turn_finalized_pr2.py`（新增；handler 直接调用，Windows/VM 均可跑；UDS 全链路仍由 `gw_turn_finalized` fixture 覆盖）
- T2 → `memory-service/tests/test_migrations_trace_id_pr2.py`（新增 `test_downgrade_excludes_soft_deleted_from_fts` + `test_downgrade_upgrade_roundtrip_fts_matchers`）
- T6/T7 → `memory-service/tests/test_observability_pr2.py`（新增）
- T5 → 既有 `test_turn_finalized_idempotent_conflict` 已覆盖

---

## 四、复审回复必备证据（提交修复后回复 Reviewer）

- [x] R1 新 HEAD SHA ← 已回填 `fac5411`（证据文档 §R1）
- [x] R2 逐项修复所在文件 + 测试文件清単 ← 已汇编（证据文档 §R2 + 修改文件清单）
- [x] R3 跨用户污染复现用例的修复后结果 ← L1 已过；**麒麟 VM L1 真实 UDS 复跑 RUN 全绿**（A1：`test_t1_cross_user_session_pollution_blocked` 等 52 passed，见证据文档 §R3）
- [x] R4 downgrade/FTS 探针的修复后结果 ← L1 逻辑已过；**麒麟 VM L1 真实 Alembic 复跑 RUN 全绿**（A3：`test_downgrade_excludes_soft_deleted_from_fts` / roundtrip，见证据文档 §R4；L2 手工探针仍 NOT_RUN，见 R6）
- [x] R5 针对性测试及全量测试的真实命令、退出码与数量 ← L0 已过 + 本机逻辑 L1 实测 + **麒麟 VM L1 全量 1003 passed / 49 skipped / exit 0**（证据文档 §R5，日志 `evidence/l1/pr65_l1_vm_checklist_20260828.log`）
- [x] R6 L2 尚未执行的项目继续明确标记为 `NOT_RUN` ← 已列（证据文档 §R6）

> 状态：R1（`fac5411` 已回填）、R2（见修改文件清单）、R3/R4（本地 L1 + 麒麟 VM L1 真实 UDS/Alembic 复跑全绿）、R5（L0 已过 + 麒麟 VM 全量 1003 passed / 49 skipped / exit 0）、R6（下述 L2 项均标 NOT_RUN）。

### 修改文件清单草稿（R2）

| 文件 | 变更 |
|---|---|
| `memory-service/db/repositories.py` | B1：`upsert_conversation` 所有权校验 + `ConversationOwnershipError` / `get_conversation_with_user`；`find_turn_by_host` 增加 user join（`user_id` 参数） |
| `memory-service/db/uow.py` | B1：`save_turn_with_outbox` 传 `user_id` 给 `find_turn_by_host` |
| `memory-service/gateway/handlers.py` | B1（前置所有权校验+双层防御）＋ M3（validator 严格校验/规范时间）＋ M4（turn handler set event_id）＋ M5（health data.status） |
| `memory-service/observability/request_context.py` | M4：event_id 进 context（向后兼容默认空串） |
| `memory-service/observability/json_logging.py` | M4：event_id 字段 + exc 脱敏 |
| `memory-service/outbox/worker.py` | M4：`_process_event` 恢复 trace_id/event_id + finally 清理 + `_fail` 脱敏 |
| `memory-service/service/source_resolver.py` | M4（source_reference 脱敏）＋ M6（`load_resolver_from_json`） |
| `memory-service/app.py` | M6：`--validation-sources`（仅 `--register-turn-finalized` 分支解析） |
| `migrations/versions/20260826_add_trace_id.py` | B2：回填 `WHERE is_deleted = 0` |
| `memory-service/tests/test_turn_finalized_pr2.py` | T1/T3/T4/T8/T9 新增 + 既有 outbox 断言更新（UTC 毫秒） |
| `memory-service/tests/test_observability_pr2.py` | T6/T7 新增 + 既有 request_context 测试适配 event_id |
| `memory-service/tests/test_migrations_trace_id_pr2.py` | T2 新增 |
| `docs/day10/05_d5d_task_list_20260826.md`、`docs/day10/09_development_report_pr2.md` | M6.7 操作方式同步 |

### L2 未执行项（R6，全部 NOT_RUN，待麒麟 VM）

- [ ] L2-1 `alembic upgrade head` + schema 对照
- [ ] L2-2 turn.finalized 端到端（`--register-turn-finalized --validation-sources <file>` 真实 UDS）
- [ ] L2-3 health degraded 真实探针
- [ ] L2-4 JSON 日志 event_id 真实输出
- [ ] L2-5 systemd 启动/重启/回退

---

## 五、其它约束

- 仅修改 Review 意见涉及范围，不顺手重构、不扩大改动、不触碰冻结契约（FRZ-IPC-001~006、FRZ-DB-001）
- 修复不得引入新红线（假实现 / 原文隔离 / 真源 / 安全 / ABI 自审）
- 涉及宿主能力（Embedding / Vector / UDS）的修复标注「待麒麟 VM L2 验证」，不得声称已通过
- 远端 HEAD 更新前不重复请求复审；更新后凭第 四 节证据提交复审