# PR60 第二轮 Review 修复方案（收口 5 HIGH + 2 MEDIUM + 4 LOW）

- **编制日期**：2026-08-26
- **编制人**：opencode（D 轨开发 Agent）｜Reviewer：E（谢嘉然）
- **基线**：PR #60 HEAD `4e39ad1`（分支 `feat/d5d-pr0-contract-adr`，基 main @ `d12df5a`）
- **输入**：PR #60 第二轮 Review（`lovezy0730-create`，2026-08-26 13:28，结论 **REWORK**：BLOCKER 0 / HIGH 5 / MEDIUM 2 / LOW 4）
- **对照文档**：`01_sdk_capability_boundary.md` v1.1 / `02_architecture_sop.md` v1.1 / ADR-005~011 / `docs/day3/11_os_agent_event_contract_v1.md`
- **目的**：把 ADR-010、ADR-011、05 Task List、04 Survey、PR Body 收敛成**唯一契约**，使 Implementer 仅阅读 ADR-010/011/05 Task List 即可直接实现 PR-2，无需自行做架构决策

---

## 一、结论概览

第二轮 Review 阻断已从「核心架构未形成」转为「架构方向基本正确，但 ADR / Task List / PR Body 与幂等 / UPDATE 具体语义尚未收口成唯一契约」。上一轮 8 项中 6 项 FIXED、2 项 PARTIALLY_FIXED（Issue 2、Issue 6）。本轮需收口：

```
HIGH:   5（Task List 同步 / fingerprint 语义 / cache wrapper / Upsert 矩阵 / PR Body）
MEDIUM: 2（production resolver activation / fingerprint canonicalization）
LOW:    4（typo / survey 表述 / 迁移命名残留 / 迁移往返测试）
```

---

## 二、人工裁决结论（2026-08-26 已裁决）

D（周子腾）对三项待裁决项**全部选择推荐项**，ADR-010/011 与 PR Body 按以下结论改写：

| # | 裁决项 | 裁决结果 |
|---|---|---|
| 1 | UPDATE 时 `trace_id` 更新 or 保持首次 | ✅ **更新为最新请求 trace_id**（指向最终写入链路） |
| 2 | refinalize 是否再次 enqueue outbox | ✅ **是**，每次 `turn.finalized` 均 enqueue，payload 携带 `host_turn_id` + `refinalize:true` 标志 |
| 3 | production resolver 未就绪时 activation 策略 | ✅ **方案 A + B**：默认生产路由不注册 → `UNSUPPORTED_METHOD`；FRZ-IPC-007 标 `CANDIDATE / BLOCKED_BY_HOST_MAPPING` |

---

## 三、HIGH 项修复方案

### HIGH-1 — `05_d5d_task_list` 与 ADR-010/011 同步

**文件**：`docs/day10/05_d5d_task_list_20260826.md`

| 位置 | 现状（旧契约） | 改为（对齐 ADR） |
|---|---|---|
| §1.1 metadata 清单 | 缺 `schema_version` | 补 `schema_version`(必填)，注明「接受 `1.x`，≠ `protocol_version`」 |
| §1.2 / T2.2 | 只有 `turns.trace_id` / `memory_entries.trace_id` | 补 `turns.host_turn_id` + 部分唯一索引 `UNIQUE(session_id, host_turn_id) WHERE host_turn_id IS NOT NULL` |
| T2.3 / T2.4 | 只写 trace_id 透传 | 补 `host_turn_id` 透传 + **Upsert 匹配**（`(session_id, host_turn_id)` 不存在 INSERT / 存在 UPDATE） |
| §六红线 | 「不修改 `service/` 代码」 | 「不修改 `service/` 既有文件（`contracts.py`/`candidate_governance.py`），允许**新增** `service/source_resolver.py`」 |
| §八执行顺序 | 「迁移 002」 | 「迁移 `20260826_add_trace_id.py`」 |

### HIGH-2 — fingerprint 移除 `trace_id`、修正 user/session 来源

**文件**：`docs/adr/010-turn-finalized-method.md` §幂等

- **fingerprint 不包含**：`trace_id` / `request_id` / `deadline_ms`（纯传输/追踪字段，重投天然变化）。
- **字段来源三元组**（替换当前「envelope 权威值(user_id/session_id/trace_id)」的错误表述）：
  - `trace_id` → **IPC envelope 顶级字段**（FRZ-IPC-006）
  - `idempotency_key` → **唯一权威合并规则**（envelope 优先 → 无则 metadata → 同提供不一致 `INVALID_REQUEST`）
  - `user_id` / `session_id` → **validated `payload.metadata`**（不是 envelope 顶级字段）
- fingerprint = `sha256(规范化 method + 业务语义字段)`，业务语义字段清单见 MEDIUM-2。

### HIGH-3 — 幂等 cache wrapper / unwrap 冻结

**文件**：`docs/adr/010-turn-finalized-method.md` §幂等

- 冻结内部缓存结构（`idempotency_cache.response` 仍为 JSON Text，不改 DDL）：

  ```json
  { "_request_fingerprint": "<sha256>", "response": { "db_turn_id": 123, "host_turn_id": "T-1", "conversation_id": 10 } }
  ```

- 流程固化：
  1. **write** → 计算 fingerprint → 包 wrapper → 写缓存；
  2. **hit** → 比对当前请求 fingerprint 与缓存 `_request_fingerprint`：一致 → **unwrap 返回 `response`**；不一致 → `INVALID_REQUEST`（幂等冲突）；
  3. **返回 IPC 的 data 永远不含 `_request_fingerprint`**；
  4. 旧/legacy 缓存行（response 无 `_request_fingerprint` 键）→ 按幂等命中直接返回 `response`，不触发指纹校验（向后兼容）。

### HIGH-4 — Upsert 字段矩阵 + refinalize 失败语义

**文件**：`docs/adr/010-turn-finalized-method.md` §落库语义

| 字段 | INSERT | UPDATE / refinalize |
|---|---|---|
| `db_turn_id`(id) | DB 自增生成 | 保持原值（更新同一条） |
| `host_turn_id` | 请求值 | 保持（匹配键，不改变） |
| `turn_index` | 服务端 `1+MAX(turn_index)` | **保持首次值**（重投不重算，防序号漂移） |
| `original_user_text` | resolver 解析 | **保持首次值**（refinalize 不重 resolve，保证原文隔离与稳定） |
| `trace_id` | 请求 envelope.trace_id | **更新为最新请求 trace_id**（裁决 #1） |
| `created_at` | 服务端时间 | 保持首次 |
| `is_end` | `=1`（`is_final` 必为 true） | 保持 `=1` |
| `model_request` / `model_response` | NULL | 保持 NULL |
| Outbox | enqueue `turn.finalized` | **再次 enqueue**（payload 携带 `host_turn_id` + `refinalize:true`，裁决 #2） |

**关键失败语义（本轮冻结，不留实现者自行判断）**：

- 已有 turn（UPDATE/refinalize）+ resolver 失败 → **继续使用既有 `original_user_text`，不报错**；
- 仅 **INSERT 场景**（无既有 turn）+ resolver 失败 → `INTERNAL_ERROR`（safe，禁止编造正文/空串）。

### HIGH-5 — 同步 PR Body

**载体**：PR #60 description（`github_update_pull_request` / issue body）

- `002_add_trace_id.py` → `20260826_add_trace_id.py`；
- `upgrade ADD / downgrade DROP` → `upgrade ADD COLUMN / downgrade 表重建`；
- `{turn_id, conversation_id}` → `{db_turn_id, host_turn_id, conversation_id}`；
- 补 `turns.host_turn_id` 部分唯一索引与 resolver seam（`service/source_resolver.py`）描述。

---

## 四、MEDIUM 项修复方案

### MEDIUM-1 — production resolver 未就绪时 activation 状态

**文件**：`docs/adr/010-turn-finalized-method.md` §落库语义 + `05_d5d_task_list` §PR-2

采纳裁决 #3（方案 A + B）：

- **默认生产路由不注册 `turn.finalized`**（`register_default_handlers` 不含它）→ 未注册即 `UNSUPPORTED_METHOD`，杜绝「协议 SUPPORTED 但生产必然 INTERNAL_ERROR」的矛盾；
- FRZ-IPC-007 路由表将 `turn.finalized` 标为 **`CANDIDATE / BLOCKED_BY_HOST_MAPPING`**，待 C 轨 `TurnExtractionAdapter`（production resolver）就绪后升级 ACTIVE；
- PR-2 用测试客户端 + **显式注入内存 resolver** 验证服务端写链路（测试态可注册）。

### MEDIUM-2 — fingerprint canonicalization

**文件**：`docs/adr/010-turn-finalized-method.md` §幂等（新增小节）

- `tool_call_ids`：**排序去重后**参与 hash（事件契约已约束元素 Turn 内唯一）；
- 时间戳：**规范化 UTC 毫秒 ISO 8601 后**参与 hash；
- absent 与 null：**等价**（统一规范化为「缺失」，用同一占位）；
- **进入** fingerprint：`event_id`、`host_turn_id`、`source_reference`、`is_final`、`finalized_at`、`occurred_at`、`final_message_id`、`finalization_reason`、`stop_reason`、`retry_of_turn_id`、`tool_call_ids`（排序）；
- **不进入**（注明理由）：`trace_id` / `request_id` / `deadline_ms`（传输字段）、`collected_at`（采集时间，重投天然不同，若进入会误判正常重试）。

---

## 五、LOW 项清理

1. `docs/adr/010-turn-finalized-method.md` 第 66 行：`IPCe 契约定义` → `IPC 契约定义`。
2. `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §2.1：`已冻结 TurnFinalizedEvent` → `已形成 FROZEN_CANDIDATE / BLOCKED_FOR_FINAL_FREEZE 候选契约`。
3. `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §七风险表第 5 行：「迁移 002」→「迁移 `20260826_add_trace_id`」。
4. `docs/day10/05_d5d_task_list_20260826.md` PR-2 测试要求补：迁移 round-trip 增加 `PRAGMA foreign_key_check;`，并断言 downgrade 后 schema / FK / indexes / triggers / FTS 与 `001_initial_schema` 等价。

---

## 六、验证与回归

- **文档一致性自检**：ADR-010 / ADR-011 / 05 Task List / 04 Survey / PR Body / `README.md` 六处「`002`→`20260826`、`turn_id`→`host/db_turn_id`、downgrade 表重建、activation CANDIDATE」逐项 grep 一致。
- **L0**：`py_compile` + Ruff（本轮为纯文档 PR，无代码改动）。
- **L1（PR-2 时执行）**：迁移往返 + `foreign_key_check`、幂等命中/冲突（含相同三元组不同 fingerprint → INVALID_REQUEST）、wrapper/unwrap、Upsert INSERT/UPDATE 矩阵、refinalize resolver 失败沿用旧正文。
- **L2（麒麟 VM，PR-3）**：`alembic upgrade head` + `.schema` 对照、downgrade 回 001 等价、`turn.finalized` 端到端。

---

## 七、变更文件清单

| 文件 | 动作 |
|---|---|
| `docs/adr/010-turn-finalized-method.md` | 改写（HIGH-2/3/4、MEDIUM-1/2、LOW-1、裁决 #1/#2/#3） |
| `docs/day10/05_d5d_task_list_20260826.md` | 同步（HIGH-1、MEDIUM-1 activation、LOW-4） |
| `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` | 表述清理（LOW-2/3） |
| PR #60 Body | 同步（HIGH-5） |
| `docs/adr/README.md` | 无需变更（ADR-010/011 已登记，状态仍「提议/待 D 决策 + E 签署」） |

---

## 八、实施顺序

1. 改写 `010-turn-finalized-method.md`（HIGH-2/3/4、MEDIUM-1/2、LOW-1、裁决项）；
2. 同步 `05_d5d_task_list_20260826.md`（HIGH-1、MEDIUM-1、LOW-4）；
3. 清理 `04_d5d_prerequisite_design_survey_20260826.md`（LOW-2/3）；
4. 更新 PR #60 Body（HIGH-5）；
5. 六处一致性 grep 自检 → 推送 PR HEAD 更新 → 请求 E 复审；
6. E 签署 → 追加回写 commit（FRZ-IPC-007 / FRZ-DB-001）；
7. PR-2 按新契约实现：`turn_finalized_handler` + `20260826_add_trace_id.py`（重建式 downgrade）+ resolver seam + 幂等 fingerprint/wrapper + 对应 L0/L1 测试与 L2 清单。

---

## 九、红线自查（回归）

- 未修改冻结 FRZ-IPC-001~006 / FRZ-DB-001 既有定义；只新增 optional 字段/方法；
- 不内嵌正文，原文隔离，`source_reference` resolver 边界保持；
- 无 resolver 时 INSERT 拒绝（INTERNAL_ERROR）而非编造正文，符合 `[02 §16.14]` 假实现红线；
- production resolver 未就绪时不注册默认生产路由，符合「不假装成功」红线；
- 迁移 downgrade 采用表重建，遵守 `[ADR-007]`「禁止删除列」。

*本方案为第二轮 Review 修复计划，落盘备查；ADR 改写与 PR-2 实现严格按 `kylin-memory-dev` SOP 与冻结变更流程执行。*
