# PR #65 Rework 修复计划（问题定位 + 修复方案）

- **编制日期**：2026-08-27
- **编制人**：opencode（D 轨开发 Agent）
- **基线**：PR #65 Base `main @ 11afb36c` → HEAD `5e9e1f43`（分支 `feat/d5d-ipc-pr2`，第 2 轮复审结论 **REWORK**，当前禁止合并）
- **输入**：`docs/day10/10_pr65_review_rework_tracking.md`（2 HIGH 阻断 + 4 MEDIUM + 测试缺口）
- **对照基线**：ADR-010 `010-turn-finalized-method.md`、ADR-011 `011-trace-id-columns.md`、FRZ-IPC-001~007 / FRZ-DB-001、kylin-memory-review skill（02 §16.6 跨用户隔离 / 02 §17.4 严重度门禁）

> 红线：B1（跨用户污染）、B2（软删除数据可检索）为 Reviewer 实证复现问题，**禁止转为合并后技术债**，必须在本 PR 合并前修复。

---

## 一、B1｜跨用户会话与 Turn 写入污染（High）

### 定位（复现链路）

| 文件:行 | 问题 |
|---|---|
| `memory-service/db/repositories.py:69-86` | `upsert_conversation` 仅按 `session_id` 查（`:74-78`），命中即返回既有 conversation 的 id，**不校验 `user_id`** → 用户 B 用 A 的 `s1`，`save_turn_with_outbox` 首行就拿到 A 的 `conversation_id` |
| `memory-service/db/repositories.py:139-159` | `find_turn_by_host` 只过滤 `(session_id, host_turn_id)`，**无 user join** → B 以 `uB/s1/H-1` 命中 A 的既有 turn，走 UPDATE/refinalize 分支，篡改 A 的 turn |
| `memory-service/gateway/handlers.py:275-317` | `_business` 复用上述两个未隔离查询；成功响应 `{:313-316}` 回显 A 的 `db_turn_id / conversation_id` |
| `memory-service/db/schema.py:37` | `conversations.session_id` 全局唯一 → **所有权边界就是 conversation 的 `user_id`**，校验点清晰 |

### 修复方案

1. **DAO 层新增所有权校验**（防御第一道，[02 §16.6]）：
   - `upsert_conversation`（`repositories.py:69`）命中既有 conversation 时校验 `existing.user_id == user_id`，不匹配抛新异常 `ConversationOwnershipError`（加入 `repositories.py`）。不修改冻结表结构。
2. **`find_turn_by_host` 增加 `user_id` 强制过滤**：签名变更为 `(conn, *, session_id, host_turn_id, user_id)`，`JOIN conversations` 后 `AND conversations.user_id == user_id` 定位（对应待办 1.2「按 (user_id, session_id, host_turn_id) 定位」）。同步更新调用方 `handlers.py:278`、`uow.py:156`（两处均有 `user_id` 在手）。
3. **Handler 前置所有权校验**（对应 1.1/1.3）：`_business` 入口先查 `get_conversation_by_session(conn, session_id=...)`，`conv.user_id != user_id` 时 `raise RequestValidationError("session ownership conflict")` → `INVALID_REQUEST`，**固定英文 safe_message，不回显 conversation_id/db_turn_id 等任何标识**。同时在调用 `save_turn_with_outbox` 外包一层 `except ConversationOwnershipError → RequestValidationError` 兜底（双层防御）。
4. **失败零副作用**（对应 1.4）：所有权异常在 `execute_idempotent` 写缓存前抛出 → UoW 回滚，`idempotency_cache` 未写入；无 Turn/Outbox 残留（复用 UoW 原子性，仅需测试断言）。
5. **回归测试 T1**：A `(uA, s1, H-1)` 成功 → B `(uB, s1, H-1)`（新 idem key）断言 `INVALID_REQUEST`、错误 message 不含 A 的 `conversation_id/db_turn_id`、A 的 turn 未变、无新增 Turn/Outbox/缓存行（对应待办 1.5）。

> 契约合规：`(session_id, host_turn_id)` 部分唯一索引（ADR-011）不换；仅查询层收紧 user 作用域，属于新增安全约束，不改冻结 DDL/错误码枚举。

---

## 二、B2｜downgrade 使软删除记忆重新进入 FTS（High）

### 定位

- `migrations/versions/20260826_add_trace_id.py:160-166`：downgrade 重建触发器后 `DELETE FROM memory_fts` 清空，然后 `INSERT ... SELECT id, content, entry_type, user_id FROM memory_entries` **无条件回填** → `is_deleted=1` 的行重新进入 FTS，`MATCH` 可命中（复现根因）。
- 基线 `001_initial_schema.py` 与 `engine.py::init_schema` 不涉及回填，修复仅限该迁移 downgrade 一处。

### 修复方案

1. 回填 SQL 增加过滤（对应 2.1）：

   ```sql
   INSERT INTO memory_fts(rowid, content, entry_type, user_id)
   SELECT id, content, entry_type, user_id FROM memory_entries WHERE is_deleted = 0
   ```

2. 迁移测试 T2 / 2.2：升级到 head → 插入「正常」+「`is_deleted=1`」两条 → `downgrade 001` → 断言正常记录 `MATCH` 命中 1、软删记录 `MATCH` 命中 0；同时断言 `memory_fts` 行数 = 非软删行数。
3. 2.3 往返：复用/扩展 `test_upgrade_downgrade_upgrade_roundtrip_pr2`（已存在，downgrade 后加一条 `MATCH` 断言）。
4. 2.4：现有 `test_downgrade_returns_001_schema` 已断言 `PRAGMA foreign_key_check == []` 与 4 个触发器存在，保留即可，补充数据级断言。

---

## 三、M3｜TurnFinalizedValidator 契约校验不完整（Medium）

### 定位（`memory-service/gateway/handlers.py:107-201`）

| 待办 | 现状定位 | 修复 |
|---|---|---|
| 3.1 必填 ID/引用拒空/纯空白 | `:133-138` 仅查存在与 str 类型，`" "`/`""` 通过 | 对 `schema_version/event_id/user_id/session_id/turn_id/idempotency_key/source_reference` 增加 `strip()` 后非空校验 |
| 3.2 `schema_version` 严格 `major.minor` | `:141-143` `startswith("1.")` 放行 `"1.0.0"`/`"1."`/`"1.abc"` | 用 `re.fullmatch(r"1\.\d+", v)`（或解析后 major==1 且 minor 为整数） |
| 3.3 时间要求带时区 | `:196-201` `_require_iso_ts` 对无时区 `"2026-08-27T10:00:00"` 解析成功即放行 | 解析后校验 `dt.tzinfo is not None`，否则 `invalid_timestamp`；纯日期字符串需显式拒绝 |
| 3.4 Outbox 时间规范化 UTC 毫秒 | `handlers.py:304-310` `extra_payload` 写入原始 `occurred_at/collected_at/finalized_at` | 改用现成 `_canonical_ts()`（`:204-214`）规范化后再入 `extra_payload` |
| 3.5 等价时间表达不改变幂等指纹 | 指纹已用 `_canonical_ts`（`:233-234`），逻辑正确 | 补测试：同一时刻 `+00:00` 与 `Z` 与 `+08:00` 表达 → 指纹一致 → 幂等命中返回首次响应 |
| 3.6 错误响应不泄漏原始输入 | validator message 为固定英文不回显（`:111-112` 已声明） | turn.finalized 层补脱敏回归测试：恶意 payload 值不得出现在 error `message` 中 |
| 3.7 边界测试 | — | 新增参数化用例（见测试缺口 T9） |

---

## 四、M4｜event_id 与 Worker 跨线程日志关联未闭合（Medium）

### 定位

| 文件:行 | 问题 |
|---|---|
| `memory-service/observability/request_context.py:19-39` | `set/clear/get` 无 `event_id` |
| `memory-service/observability/json_logging.py:57-69` | JsonFormatter 输出无 `event_id`；`:69` `formatException` 结果未脱敏 |
| `memory-service/outbox/worker.py:121-185` | `_process_event` 未设置线程请求上下文 → 成功/重试/DL 日志无 `trace_id/event_id`；`:151` `last_error` 为原始 `exc` 摘要（未脱敏即入库/入日志） |
| `memory-service/gateway/server.py:182-186` | 仅设置 `request_id/trace_id/method` |
| `memory-service/service/source_resolver.py:65-68` | 日志含原始 `source_reference` |

### 修复方案

1. `request_context.py`：`set_request_context` 增 `event_id` 参数（默认 `""`），`clear` 清空，`get` 返回 `event_id` 键（保持向后兼容）。
2. `json_logging.py`：Formatter 增加 `"event_id"` 字段；对 `exc = self.formatException(...)` 结果套 `sanitize_message()`（对应 4.5 traceback/exc 脱敏）。
3. `worker.py::_process_event`：入口解析 payload（字符串先 `json.loads`）取 `trace_id/event_id`，`set_request_context(request_id="", trace_id=..., method=f"outbox:{event_type}", event_id=...)`；`try/finally` 中 `clear_request_context()`（对应 4.2/4.3/4.4）。`_fail` 的 `last_error` 用 `sanitize_message()` 后再存/写日志（对应 4.5）。
4. `handlers.py` turn handler 校验通过后 `set_request_context(..., event_id=metadata["event_id"])`（同一线程，DAO 层日志自动携带；`server.py` 的 finally 已负责清理）。
5. `source_resolver.py:66` 日志中的 `source_reference` 经 `sanitize_message()` 输出（对应 4.5 外部引用脱敏）。
6. **T6 测试**：挂自定义 logging handler，在 emit 时读 `get_request_context()`；构造带 `trace_id/event_id` 的 outbox 行 → 跑 `worker._poll_once()` → 断言 Worker 日志携带二者且事件结束后 context 清空；另补 Gateway→DAO 单测（`set_event_id` 后 DAO 日志携带）。

---

## 五、M5｜health 业务状态仍可能错误报告为 ok（Medium）

### 定位

- `handlers.py:32-50`：`data["status"]` 在 metrics 之前按 `db_ok` 定值；metrics 抛错已降级 `backlog=-1`（`:46-49`）但**不回写 `status`**。
- `worker.py:82-92`：busy 时内部返回哨兵 `backlog=-1`（`:91`），handler 拿到后同样不改 `status`。
- envelope 侧 `server.py:272-278` 恒为 `"ok"`（请求已被处理），与业务 `data.status` 是两个概念（对应 5.1）。

### 修复方案（`handlers.py`）

```
status = "ok"
if not db_ok: status = "degraded"
if worker_metrics is not None:
    try: outbox = worker_metrics()
    except Exception: outbox = {backlog:-1, dead_letter:-1, oldest_pending_created_at:None}; status = "degraded"
    if outbox.get("backlog") == -1: status = "degraded"   # 哨兵/busy
else:
    if status == "ok": status = "degraded"                # Worker 未注入（未启动）→ 写管道不可用
data["status"] = status
```

- envelope `status` 维持 `"ok"`（请求已 ack），`data.status` 为真实业务探针状态——与现有 `test_health_degraded_when_worker_metrics_fails`（断言信封 ok、backlog=-1）一致，不破坏现有断言。
- **T7 测试**：DB 不可达 / metrics 抛错 / metrics 返回 `backlog=-1`（busy）/ 无 worker_metrics / 全绿正常 → 各断言 `data.status` 真实值。

> 说明：无 worker 判 degraded 是语义选择，符合「无 Outbox Worker 则写入管道不可用」；如 Reviewer 倾向保守（worker 缺省不判 degraded）可改，风险已标注待裁决（见「待人工裁决」）。

---

## 六、M6｜validation profile 与证据入口未闭合（Medium）

### 定位

- `app.py:95-102`：`--register-turn-finalized` 注入 `InMemorySourceResolver()` **空映射** → 任何 `source_reference` 均未命中（`source_resolver.py:62-70`），CLI 只能验证 INTERNAL_ERROR 负路径，无法完成 6.4 正向写。
- `docs/day10/05_d5d_task_list_20260826.md:94`（L2-2）与 `docs/day10/09_development_report_pr2.md:66` 描述与真实入口不一致（对应 6.7）。

### 修复方案

1. `source_resolver.py` 新增加载器：`load_resolver_from_json(path) -> InMemorySourceResolver`，JSON 结构 `{"ref://turn/H-1": {"original_user_text": "...", "model_request": ..., "model_response": ...}}`（对应 6.1 可加载映射）。
2. `app.py` 增加 `--validation-sources <path.json>`，**仅在 `--register-turn-finalized` 分支内解析**（6.2 受控）：有 path → `load_resolver_from_json`；无 path → 保持空 resolver，并 `logger.warning` 注明「仅负路径可验证」。production 默认（不加 flag）行为不变（6.3，已有测试 `test_turn_finalized_unsupported_in_default_profile`）。
3. 6.5/6.6：resolver 未命中 → `INTERNAL_ERROR` 且无 Turn/Outbox/幂等缓存残留（扩展现有 `test_turn_finalized_resolver_miss_internal_error` 断言 outbox 与 cache 也为空）。
4. **T8 测试**：写临时 sources JSON → 以 `UoW`+handler 或 CLI 子进程发 `turn.finalized` → 断言真实落库 `original_user_text` + Outbox 入队（Gateway→UoW→SQLite+Outbox 正向）。
5. 6.7：同步更新 `docs/day10/05_d5d_task_list_20260826.md` L2-2 与 `docs/day10/09_development_report_pr2.md` L2-2，写明 `--validation-sources <file>` 操作方式。

---

## 七、测试缺口补齐（T1-T9）映射

| 用例 | 归属 | 落点 |
|---|---|---|
| T1 跨用户 A/B 竞争 | B1 | 新增于 `memory-service/tests/test_turn_finalized_pr2.py` |
| T2 downgrade 软删不入 FTS | B2 | 新增于 `memory-service/tests/test_migrations_trace_id_pr2.py` |
| T3 并发 `IntegrityError` 幂等回查（fingerprint compare + unwrap） | B1 相关 / PR60 LOW-3 | 现有 `uow.py:101-112` 逻辑已含 unwrap，缺测试 → 新增（预占三元组写缓存后再次执行，断言回查走指纹比对） |
| T4 指纹一致 unwrap 首次响应 | —— | `test_turn_finalized_idempotent_replay` 已覆盖；补一个直接 `_unwrap_response` 层单测 |
| T5 指纹不一致 → INVALID_REQUEST | —— | `test_turn_finalized_idempotent_conflict` 已覆盖 |
| T6 Worker 跨线程恢复 trace_id/event_id | M4 | 新增于 `memory-service/tests/test_observability_pr2.py` |
| T7 health `data.status=degraded`（含哨兵） | M5 | 新增于 `memory-service/tests/test_observability_pr2.py` |
| T8 validation profile 正向写 | M6 | 新增于 `memory-service/tests/test_turn_finalized_pr2.py` 或独立文件 |
| T9 严格 major.minor / 非空 ID / 带时区时间 | M3 | 新增参数化用例于 `memory-service/tests/test_turn_finalized_pr2.py` |

---

## 八、复审回复必备证据（R1-R6）与回归验证

- **L0**：`py_compile` 全量 + `ruff check --select F,E9`（修改文件）
- **L1**：`pytest memory-service/tests -q`（基线 983 passed / 49 skipped + 新增用例），记录真实退出码与数量（R5）
- **L2（待麒麟 VM，标 NOT_RUN，不得声称已过）**：
  - T1 跨用户毒素用例在真实 UDS 下复跑（R3）
  - `alembic upgrade head` + downgrade + FTS `MATCH` 探针复跑（R4）
  - L2-2 validation profile 正向写（`--register-turn-finalized --validation-sources`）、L2-3 health degraded、L2-4 JSON 日志 `event_id`
- **文档同步**：更新 `docs/day10/10_pr65_review_rework_tracking.md` 勾选项 + `docs/day10/05_d5d_task_list_20260826.md`、`docs/day10/09_development_report_pr2.md`（M6.7）

---

## 九、待人工裁决 / 风险提示

1. **M5 Worker 未注入是否判 degraded**：本方案判 degraded（写入管道不可用）；若 Reviewer 倾向「worker_metrics=None 时仅 DB 决定 status」，仅需删除 `else` 分支。倾向前者，若非则改回——不影响其它项。
2. **B1 错误码**：用冻结枚举 `INVALID_REQUEST`（未新增枚举，合规）；跨用户探测本质属客户端错误而非服务故障，故不用 INTERNAL_ERROR。
3. B1/B2 为已实证 High，**不登记技术债**（红线）；M3~M6 为 Medium，本 PR 内直接修复。
4. 修复期间不触碰 FRZ-IPC-001~006 / FRZ-DB-001 既有列 / ADR-010 指纹字段清单；不顺手重构（如 `_business` 与 `save_turn_with_outbox` 重复查 turn 的问题仅登记，不扩大改动）。
5. 修复纪律：仅修改 Review 意见涉及范围；修复不得引入新红线（假实现 / 原文隔离 / 真源 / 安全 / ABI 自审）；涉及宿主能力（Embedding / Vector / UDS）的修复标注「待麒麟 VM L2 验证」。

---

## 十、实施顺序

1. B1 → 2. B2 → 3. M3 → 4. M4 → 5. M5 → 6. M6 → 7. 测试缺口（T1-T9）→ 8. L1 回归 + L0 静态 → 9. 更新追踪文档勾选状态 → 10. 产出 R1-R6 复审回复证据