# PR #65 Rework 修复证据（R1-R6 复审回复）

- **编制日期**：2026-08-28
- **编制人**：opencode（D 轨开发 Agent）
- **基线**：PR #65 Base `main @ 11afb36c` → HEAD `fac5411`（分支 `feat/d5d-ipc-pr2`，2026-08-28 VM L1 回归后回填）
- **对照**：`docs/day10/10_pr65_review_rework_tracking.md`、`docs/day10/11_pr65_rework_fix_plan.md`
- **修复范围**：B1（High）×5 待办 / B2（High）×4 / M3~M6（Medium）×24 / 测试缺口 T1-T9

> 红线确认：B1（跨用户污染）、B2（软删除可检索）在本 PR 合并前已修复，未转技术债。修复不触碰 FRZ-IPC-001~006 / FRZ-DB-001 既有列 / ADR-010 指纹字段清单。

---

## R1｜新 HEAD SHA

- **状态**：已回填（2026-08-28）。
- 修复合入：`a94ae55` `fix(d5d): PR-65 rework 修复 - B1/B2/M3~M6/T1-T9 验收合入 + VM L1 测试清单与证据`
- 测试基础设施（UDS 就绪等待竞态）固定：`fac5411` `test(d5d): 修复 UDS 就绪等待竞态 - _wait_socket 改为 connect 探测（bind↔listen 窗口误判）`
- 最新远端 HEAD：**`dc4080a`**（`git rev-parse HEAD`；仅证据文档 + 测试 import 清理，无生产代码变更）。
- 运行口径：L1/L2 全部在麒麟 VM 于 `fac5411` 上执行；`dc4080a` 与 `fac5411` 的 `memory-service/` 生产代码一致（差异仅为 docs + 测试文件一处未使用 import 清理）。

---

## R2｜逐项修复文件清单（本文件末尾「修改文件清单」为准）

| 待办 | 文件 | 变更摘要 |
|---|---|---|
| 1.1/1.2/1.3/1.4 | `memory-service/db/repositories.py` | `upsert_conversation` 命中校验 `existing.user_id == user_id`，不一致抛新异常 `ConversationOwnershipError`；新增 `get_conversation_with_user`（handler 前置校验用）；`find_turn_by_host` 签名增加 `user_id` 并 `JOIN conversations` 强制过滤（按 `(user_id, session_id, host_turn_id)` 定位） |
| 1.1/1.2 | `memory-service/db/uow.py:156` | `find_turn_by_host(..., user_id=user_id)` 调用方同步 |
| 1.1/1.3 | `memory-service/gateway/handlers.py` | `_business` 入口 `get_conversation_with_user` + `conv.user_id != user_id` → `RequestValidationError("session ownership conflict")`（固定英文，不回显标识）；`execute_idempotent` 外包 `except ConversationOwnershipError → RequestValidationError` 双层防御 |
| 1.5 | `memory-service/tests/test_turn_finalized_pr2.py` | `test_t1_cross_user_session_pollution_blocked` / `test_t1_find_turn_by_host_user_scoped` / `test_t1_conversation_ownership_dao_layer` |
| 2.1 | `migrations/versions/20260826_add_trace_id.py:163-166` | 回填 SQL 增加 `WHERE is_deleted = 0` |
| 2.2/2.3 | `memory-service/tests/test_migrations_trace_id_pr2.py` | `test_downgrade_excludes_soft_deleted_from_fts` / `test_downgrade_upgrade_roundtrip_fts_matchers` |
| 3.1 | `memory-service/gateway/handlers.py` | MUST 字段 `strip()` 后非空校验（`invalid_blank`） |
| 3.2 | 同上 | `re.fullmatch(r"1\.\d+", schema_version.strip())`（拒绝 `1.0.0`/`1.`/`1.abc`/`2.0`） |
| 3.3 | 同上 | `_require_iso_ts` 解析后校验 `dt.tzinfo is not None`（拒绝无时区/纯日期） |
| 3.4 | 同上 | `extra_payload` 时间戳改走 `_canonical_ts()`（UTC 毫秒规范化） |
| 3.5 | 同上 + 测试 | 既有指纹用 `_canonical_ts`，逻辑正确；补 `test_t9_equivalent_time_fingerprint_idempotent` |
| 3.6 | 同上 + 测试 | validator message 固定英文；补 `test_t9_error_safe_message_no_leak` |
| 3.7 | 同上 | `test_t9_schema_version_strict_major_minor` / `test_t9_reject_blank_ids` / `test_t9_reject_timezone_missing` |
| 4.1 | `memory-service/observability/request_context.py` | `set_request_context` 增 `event_id`（默认 `""` 向后兼容），`clear`/`get` 同步 |
| 4.1 | `memory-service/observability/json_logging.py` | JsonFormatter 增 `"event_id"` 字段；`formatException` 结果过 `sanitize_message()` |
| 4.2/4.3/4.4/4.5 | `memory-service/outbox/worker.py` | `_process_event` 解析 payload 取 `trace_id/event_id` 并 `set_request_context`；`try/finally` 清上下文；`_fail` 的 `last_error` 经 `sanitize_message()` 后存/写日志 |
| 4.2/4.6 | `memory-service/gateway/handlers.py` | turn handler 校验通过后 `set_request_context(..., event_id=...)` |
| 4.5 | `memory-service/service/source_resolver.py` | 未命中日志 `source_reference` 经 `sanitize_message()` |
| 4.6 | `memory-service/tests/test_observability_pr2.py` | `test_worker_restores_trace_event_and_clears` / `test_request_context_event_id_backward_compat` |
| 5.1/5.2/5.3 | `memory-service/gateway/handlers.py` | `health_handler`：metrics 抛错/哨兵 `backlog=-1`/Worker 未注入 → `data.status=degraded`；envelope status 维持 `ok` |
| 5.3 | `memory-service/tests/test_observability_pr2.py` | `test_health_status_*` 5 条（全绿/抛错/哨兵/无 Worker/DB 不可达） |
| 6.1/6.2 | `memory-service/service/source_resolver.py` | 新增 `load_resolver_from_json(path)`（JSON `{ref: {original_user_text, model_request, model_response}}`） |
| 6.2/6.3 | `memory-service/app.py` | 新增 `--validation-sources <path.json>`，**仅** `--register-turn-finalized` 分支解析；无 path → 空 resolver + warning；production 默认行为不变（`test_turn_finalized_unsupported_in_default_profile` 保留） |
| 6.4 | 同上 + 测试 | `test_t8_load_resolver_from_json_and_write`（JSON resolver → UoW → SQLite+Outbox 正向） |
| 6.5/6.6 | 既有测试扩展 | `test_turn_finalized_resolver_miss_internal_error` 扩展：断言 outbox 与幂等缓存也为空 |
| 6.7 | `docs/day10/05_d5d_task_list_20260826.md` L2-2、`docs/day10/09_development_report_pr2.md` L2-2 | 写明 `--validation-sources <file>` 操作方式 |

---

## R3｜跨用户污染复现用例修复后结果

- **复现（修复前语义）**：B 以 `uB / s1 / H-1` 命中 A 的 conversation/turn → 篡改 + 泄漏标识。
- **修复后语义**：
  1. DAO 层 `upsert_conversation` 命中既有会话校验 `user_id`，不匹配抛 `ConversationOwnershipError`；
  2. `find_turn_by_host` JOIN `conversations.user_id`，B 查询 A 的 turn 返回 `None`；
  3. handler `_business` 前置 `RequestValidationError("session ownership conflict")` → INVALID_REQUEST，固定英文不泄漏 `conversation_id/db_turn_id`；
  4. 异常在 `execute_idempotent` 写缓存前抛出 → UoW 回滚，无 Turn/Outbox/缓存残留。
- **L1 测试**：`test_t1_cross_user_session_pollution_blocked`（A 成功 → B 抢占 → INVALID_REQUEST + A turn 未变 + 无新增 Turn/Outbox/缓存行）——已 PASS（本机 L1 logic）。
- **麒麟 VM L1（真实 UDS，RUN 2026-08-28）**：A1 阶段 `memory-service/tests/test_turn_finalized_pr2.py`（`-v`，52 passed）内 `test_t1_cross_user_session_pollution_blocked` / `test_t1_find_turn_by_host_user_scoped` / `test_t1_conversation_ownership_dao_layer` **全部 PASSED**（VM HEAD `fac5411`）。

---

## R4｜downgrade/FTS 探针修复后结果

- **修复**：`migrations/versions/20260826_add_trace_id.py` 回填 `INSERT ... SELECT ... FROM memory_entries WHERE is_deleted = 0`。
- **L1 数据级验证（本机 SQLite 3.49 sqlite3 **未跑 Alembic**，用等价 SQL 探针）**：
  - 正常记录 `MATCH` 命中 = 1；软删记录 `MATCH` 命中 = 0；`memory_fts` 行数 = 非软删行数（探针输出 `normal_hits= 1 deleted_hits= 0 fts_total= 1 normal_total= 1`）。
  - 迁移级测试 `test_downgrade_excludes_soft_deleted_from_fts` / `test_downgrade_upgrade_roundtrip_fts_matchers` 完成编写，待 VM 跑（本机 Alembic 因 Windows 读取 alembic.ini 编码问题无法执行，见测试结果节）。
- **麒麟 VM L1（真实 Alembic，RUN 2026-08-28）**：A3 阶段 `memory-service/tests/test_migrations_trace_id_pr2.py`（`-v`，10 passed）真实 Alembic 迁移下 `test_downgrade_excludes_soft_deleted_from_fts` / `test_downgrade_upgrade_roundtrip_fts_matchers` / `test_downgrade_preserves_data_and_fts` / `test_downgrade_returns_001_schema` / `test_upgrade_downgrade_upgrade_roundtrip_pr2` **全部 PASSED**；既有 `test_migrations_d4d.py`（C3，5 passed）覆盖基线迁移/往返/FK/触发器。亦含 `SELECT count(*) FROM memory_entries WHERE is_deleted=1 → 保留` 与 `MATCH` 不命中软删（downgrade/FTS 数据级探针在 A3 断言内）。
- **L2（麒麟 VM，NOT_RUN）**：手工 `alembic upgrade head` + `.schema` 逐列对照 / `PRAGMA foreign_key_check` 交互探针仍列为 L2 项（不在本 L1 清单，见 R6）。

---

## R5｜测试真实命令、退出码与数量

> 本机为 Windows（Python 3.13.3），`AF_UNIX` 不可用、Alembic 读取 alembic.ini 发生 GBK 解码失败、
> 捆绑 SQLite 未启用 `SQLITE_ENABLE_UPDATE_DELETE_LIMIT` → **UDS 全链路 / Alembic 迁移 / Worker `_poll_once` 类用例在本机无法执行**。
> 下列为本机可执行范围（逻辑/DAO/Validator/Handler 级），迁移与 UDS 用例在麒麟 VM L1/L2 跑。

### L0 静态

- `python -m py_compile`（memory-service 全量 + migrations/versions/20260826_add_trace_id.py）→ **退出码 0，全部通过**。
- `python -m ruff check --select F,E9 <修改文件>` → **All checks passed!**（首次报告 1 处 `time` 未使用，属既有 worker.py 遗留，已顺手移除且仅限已修改文件）。

### L1 逻辑实测（本机）

```bash
PYTHONPATH=memory-service python -m pytest memory-service/tests/test_turn_finalized_pr2.py \
  -k "t1_ or t3_ or t4_ or t8_ or t9_ or handler_env" -q
→ 11 passed
```

```bash
PYTHONPATH=memory-service python -m pytest memory-service/tests/test_observability_pr2.py \
  -k "health_status or request_context or json_ or pii_" -q
→ 13 passed（含新增 health data.status 5 条 + event_id 兼容）
```

- 新增用例汇总（本机可跑范围）：**24 passed**（T1×3 / T3×1 / T4×1 / T8×1 / T9×5 / T6×1(需 VM) / T7×5 / 既有上下文适配×3）。
- 全量扫描 `memory-service/tests`（排除迁移）：**941 passed / 49 skipped / 26 failed / 29 errors**——失败与 error 全部可归因于本机平台限制（`AF_UNIX` 缺失 → Gateway/server/turn UDS 用例；GBK → migrations_d4d；DELETE-LIMIT → worker/db 清理用例）；**基线（git stash 后）同类用例同样失败**，确认非本次修复引入。
- **T6**：`test_worker_restores_trace_event_and_clears` 本机失败仅因 `_poll_once` 触发 `cleanup_expired_idempotency` 的 `DELETE ... LIMIT`（本机 SQLite 编译未含该选项）；VM 的 SQLite 支持（基线 `test_outbox_worker_d4d.py *_poll_once` 通过即证明），待 VM 跑。

### L1 麒麟 VM 全量（R5 达标命令，已执行）

```bash
cd /home/kylin-agent/kylinOS-agent-memory
export PYTHONPATH=memory-service
/home/kylin-agent/d4d-venv/bin/python -m pytest memory-service/tests -q
```

- 结果（VM HEAD `fac5411`，2026-08-28）：**1003 passed / 49 skipped in 43.44s，退出码 0**。与清单预期（基线 983 + 新增约 20 ≈ 1003）**一致**。
- 分阶段计数（全部 exit 0）：
  - A1 PR2 针对性（`test_turn_finalized_pr2.py test_observability_pr2.py test_migrations_trace_id_pr2.py`, -v）：52 passed
  - B DAO/Worker（`test_db_d4d.py test_outbox_worker_d4d.py test_gateway_server_d4d.py`, -v）：40 passed
  - C 契约/CLI（`test_gateway_protocol_d4d.py test_server_lifecycle.py test_migrations_d4d.py`）：33 passed
  - D 全量（`memory-service/tests` -q）：1003 passed / 49 skipped
- 完整日志：`evidence/l1/pr65_l1_vm_checklist_20260828.log`。

### L1 待麒麟 VM 全量（R5 达标命令，执行前参考）

```bash
alias ms="PYTHONPATH=memory-service"
python -m pytest memory-service/tests -q            # 基线 983 passed / 49 skipped + 新增用例
```

---

## R6｜L2 麒麟 VM 验证（L2-1~L2-5，2026-08-28 已执行）

> 执行入口：`kylin-vm-test` SSH（127.0.0.1:2222），仓库 `/home/kylin-agent/kylinOS-agent-memory`（HEAD `fac5411`，
> 与本地 `dc4080a` 生产代码一致），venv `/home/kylin-agent/d4d-venv/bin/python`。完整日志：`evidence/l2-kylin-vm/pr65_l2_vm_20260828.log`。

| # | 验证项 | 命令/要点 | 结果 |
|---|---|---|---|
| L2-1 | 迁移手工探针 | `alembic -c migrations/alembic.ini upgrade head` + `.schema` 对照 + `PRAGMA foreign_key_check`；downgrade→upgrade 往返；FTS 软删过滤数据级探针 | **RUN/PASS**：upgrade exit=0；`turns.trace_id/host_turn_id`、`memory_entries.trace_id`、`idx_turns_host_turn_id`(唯一+`WHERE host_turn_id IS NOT NULL`)、`memory_fts`+4 触发器、`alembic_version` 全员 OK；FK 检查空；往返 exit=0；MATCH `麒麟` insert=1 / 软删后=0 |
| L2-2 | turn.finalized 真实 CLI 端到端 | `app.py --register-turn-finalized --validation-sources sources.json` + `uds_client` | **RUN/PASS**：正向写 `status ok` + 落库（turn.host_turn_id=H-1, trace_id=L2A-1, original_user_text=resolver 正文）+ Outbox 入队（payload 含 trace_id/host_turn_id，UTC 毫秒）；幂等回放同响应；跨用户毒素（u2 复用 u1 的 s1）→ `INVALID_REQUEST`（message 固定英文、无 db_turn_id 泄漏）+ B 零副作用；无 `--validation-sources` → 空映射 warning + resolver miss → `INTERNAL_ERROR`（turns/idempotency/outbox 全 0）；production 默认 → `UNSUPPORTED_METHOD` |
| L2-3 | health degraded 真实探针 | `uds_client --method health` | **RUN/PASS**：全绿 `data.status=ok, db=ok, backlog=0`；`--no-outbox`（worker 未注入）→ `data.status=degraded`；DB 不可达 / metrics 异常 / 哨兵 `backlog=-1` 分支由 VM L1 handler 单测（`test_health_status_degraded_*`）覆盖 3 passed。实机受限说明：health db 探针 `SELECT 1` 不做页 I/O，对存活池化连接无法从外部伪造 DB 不可达 |
| L2-4 | JSON 日志 event_id | `--json-logs` 运行日志 | **RUN/PASS**：单行 JSON 格式；`memory.retrieve` 请求日志含 `trace_id=L2R-1 / request_id=req-r-1`；Worker 处理注入 outbox 事件日志含 `trace_id=L2W-1 / event_id=evt-W1`（M4 跨线程）；resolver 注入正文未出现在任何日志（PII 零泄漏） |
| L2-5 | systemd 部署 | `systemctl --user` kylin-memory.service | **RUN/PASS**：默认库 alembic 迁移后 enable/start RC=0；socket `/run/user/1000/kylin-memory/memory.sock` 可达；health ok；restart 后 active；stop 后 inactive + socket 清理；`enable --now` 回退恢复 active。注：冻结 ExecStart 不带 `--json-logs`（文本日志），JSON 由 L2-4 独立覆盖 |

> 遵循纪律：L2 证据均来自麒麟 VM 真实运行；「生产 DB 不可达 → degraded」在实机以存活池化连接自检 `SELECT 1` 不可外部注入，已如实标注并以同 handler 单测覆盖。
> R3/R4 的 L1-VM 复跑证据另见本文件 §R3/§R4 与 `evidence/l1/pr65_l1_vm_checklist_20260828.log`。

---

## 风险与待裁决

1. **M5 Worker 未注入是否判 degraded**：本方案判 degraded（写入管道不可用）。若 Reviewer 倾向保守（worker_metrics=None 仅由 DB 决定 status），删除 `health_handler` 的 `else` 分支回退即可，不影响其它项（引用 `11_pr65_rework_fix_plan.md` §九.1）。
2. **B1 错误码**：使用冻结枚举 `INVALID_REQUEST`（未新增枚举，合规）。
3. **M5 现有断言兼容**：`test_health_degraded_when_worker_metrics_fails` 断言信封 ok + backlog=-1 未破坏；新增 `data.status=degraded` 为附加业务语义。

---

## 修改文件清单

| 类别 | 文件 |
|---|---|
| 修改 | `memory-service/db/repositories.py`、`memory-service/db/uow.py`、`memory-service/gateway/handlers.py`、`memory-service/observability/request_context.py`、`memory-service/observability/json_logging.py`、`memory-service/outbox/worker.py`、`memory-service/service/source_resolver.py`、`memory-service/app.py`、`migrations/versions/20260826_add_trace_id.py` |
| 修改（测试） | `memory-service/tests/test_turn_finalized_pr2.py`、`memory-service/tests/test_observability_pr2.py`、`memory-service/tests/test_migrations_trace_id_pr2.py` |
| 修改（测试/竞态固定，fac5411） | `memory-service/tests/test_gateway_server_d4d.py`、`memory-service/tests/test_server_lifecycle.py`、`memory-service/tests/test_turn_finalized_pr2.py`、`memory-service/tests/test_observability_pr2.py`（`_wait_socket`/`_wait_listening` 改为 connect 探测） |
| 修改（文档） | `docs/day10/05_d5d_task_list_20260826.md`、`docs/day10/09_development_report_pr2.md`、`docs/day10/10_pr65_review_rework_tracking.md`、`docs/day10/13_pr65_l1_test_checklist_vm.md` |
| 新增 | `docs/day10/11_pr65_rework_fix_plan.md`、`docs/day10/12_pr65_rework_evidence.md`（本文件）、`evidence/l1/pr65_l1_vm_checklist_20260828.log` |

## 契约变化

Schema / IPC / DB 表结构 / 错误码枚举：**无变化**（B1 为查询层安全收紧，B2 为迁移回填过滤，均不触碰冻结 DDL）。

## 技术债变化

- 关闭/解决：B1、B2（红线，不转技术债）；M3~M6（本 PR 内修复）。
- 测试基础设施（VM L1 中发现并修复，分类 **Risk**）：UDS 就绪等待以 `os.path.exists` 判据在 `bind↔listen` 窗口误判就绪 → 负载叠加时偶发 `ECONNREFUSED`（B/D 阶段各 1 例，隔离复跑 3/3 PASS 佐证为竞态非逻辑缺陷）。fac5411 将 `_wait_socket`/`_wait_listening` 改为 connect 探测修复（未改生产 `gateway/server.py`、`embedding/server.py`）；VM 全量复跑 A/B/C/D 全绿。
- 新增：无。
- 仍存在（仅登记不扩大改动）：`_business` 与 `save_turn_with_outbox` 重复查 turn 的问题（引用 `11_pr65_rework_fix_plan.md` §九.4）。