# PR-2 开发报告：turn.finalized 写链路 + trace_id 落库 + health/JSON 日志（D5-D）

- **任务卡**：`docs/day10/05_d5d_task_list_20260826.md`（PR-2 代码主体）｜
  **分支**：`feat/d5d-ipc-pr2`（基线 tree == main @ `11afb36c`，即 PR#60 ADR-010/011 合并后）
- **对照文档版本**：ADR-010（turn.finalized 方法，D/E 签署 2026-08-27）、ADR-011（trace_id 列）、
  FRZ-IPC-001~007 / FRZ-DB-001（冻结）、`docs/day3/11_os_agent_event_contract_v1.md` §7（事件契约 v1 候选）
- **日期**：2026-08-27

## 修改文件清单

### 新增
| 文件 | 说明 |
|---|---|
| `migrations/versions/20260826_add_trace_id.py` | ADR-011 迁移：3 列 ADD + 部分唯一索引；downgrade 表重建回滚（禁 DROP COLUMN）+ FTS 触发器重建回填 |
| `memory-service/service/source_resolver.py` | ADR-010 resolver seam（接口 + InMemory 实现；production 标注 BLOCKED_BY_HOST_MAPPING） |
| `memory-service/observability/__init__.py` | 可观测性包 |
| `memory-service/observability/request_context.py` | 请求上下文线程局部（T3.3） |
| `memory-service/observability/json_logging.py` | JSON Formatter + PII 脱敏 filter（T3.2） |
| `memory-service/tests/test_migrations_trace_id_pr2.py` | ADR-011 迁移测试（列/部分唯一索引/往返/数据保留/FTS 回填） |
| `memory-service/tests/test_turn_finalized_pr2.py` | ADR-010 端到端（写链路/幂等指纹/错误路径/Upsert/resolver） |
| `memory-service/tests/test_observability_pr2.py` | health backlog / JSON 日志 / 请求上下文线程隔离 |

### 修改
| 文件 | 变更 |
|---|---|
| `memory-service/db/schema.py` | turns +trace_id/host_turn_id、memory_entries +trace_id、部分唯一索引 idx_turns_host_turn_id（单一真相） |
| `memory-service/db/repositories.py` | insert_turn/insert_memory_entry 透传 trace_id/host_turn_id；find_turn_by_host/next_turn_index/update_turn_refinalize；幂等指纹 wrapper/unwrap + IdempotencyConflictError |
| `memory-service/db/uow.py` | save_turn_with_outbox Upsert（INSERT/UPDATE 字段矩阵）；execute_idempotent 透传 request_fingerprint；并发回查走指纹比对 |
| `memory-service/gateway/handlers.py` | turn_finalized_handler + _TurnFinalizedValidator + request_fingerprint + register_turn_finalized_handler（显式注册 seam）；health 增补 outbox backlog |
| `memory-service/gateway/server.py` | worker_metrics 注入；请求上下文线程局部设置/清理；RequestValidationError/IdempotencyConflictError → INVALID_REQUEST |
| `memory-service/app.py` | UnitOfWork 工厂注入；`--register-turn-finalized`（test profile，production 默认不注册）；`--json-logs` |
| `memory-service/logging_setup.py` | json_logs 开关（T3.4 兼容文本日志） |

## 契约变化

- **IPC**：FRZ-IPC-007 路由表新增 `turn.finalized`（ADR-010 已回写冻结文档；production 默认 UNSUPPORTED_METHOD，测试态显式注册）
- **DB**：turns/memory_entries 新增 nullable trace_id、turns 新增 host_turn_id + 部分唯一索引（ADR-011 已回写 FRZ-DB-001）；outbox 不改表
- **错误码**：无新枚举（沿用 5 项冻结）；幂等冲突复用 INVALID_REQUEST
- 未修改 FRZ-IPC-001~006、FRZ-DB-001 既有列定义

## 设计说明

- **幂等指纹（ADR-010）**：`_request_fingerprint = sha256(规范化 method+业务语义字段)`；
  缓存 wrapper `{"_request_fingerprint": ..., "response": ...}`，命中比对指纹，不一致 → INVALID_REQUEST；
  legacy 缓存行（无指纹键）直接返回（向后兼容）；`collected_at`/`trace_id`/`request_id`/`deadline_ms` 不入指纹
- **Upsert 字段矩阵（ADR-010）**：INSERT 服务端计算 turn_index（1+MAX）、resolver 解析 original_user_text；
  UPDATE/refinalize 保持首次值（turn_index/original_user_text/created_at），仅更新 trace_id/is_end，Outbox 再次入队 refinalize:true
- **activation 方案 A+B**：production `register_default_handlers` 不含 turn.finalized → UNSUPPORTED_METHOD；
  `--register-turn-finalized` 仅供 test/validation profile（in-memory resolver）
- **trace_id 唯一真源**：IPC envelope 顶级；payload.metadata.trace_id 不一致 → INVALID_REQUEST
- **原文隔离**：resolver 结果只落 original_user_text，不进入日志/异常/响应；INSERT resolver 失败 → INTERNAL_ERROR（safe）

## 测试结果

- **L0**：`py_compile` 全量通过；`ruff check --select F,E9`（修改文件）All checks passed
- **L1**：全量 pytest **983 passed, 49 skipped**（原 951 + 新增 32；WSL2 Python 3.10，sqlalchemy 2.0.51）
  - 新增覆盖：迁移往返/部分唯一索引/数据保留/FTS 回填；写链路落库+outbox 同事务；
    幂等重投/冲突（同三元组不同指纹 → INVALID_REQUEST）；envelope/metadata key 合并；
    11 类 payload 校验错误；resolver 未命中 → INTERNAL_ERROR 且不落库；
    refinalize Upsert 保持首次值；health backlog；JSON 日志格式/PII/线程隔离
- 失败分类：无（先期 1 个测试断言笔误已修）

## 待麒麟宿主 L2 验证项（人工操作清单，本 PR 不声称已执行）

1. **L2-1 迁移升级**：`alembic -c migrations/alembic.ini upgrade head` + `.schema` → turns/memory_entries 含 trace_id 列
2. **L2-2 turn.finalized 端到端**：`--register-turn-finalized`（test profile + in-memory resolver）模拟客户端发事件 → 落库+outbox 入队+worker 退避/DL；production profile 下 `turn.finalized → UNSUPPORTED_METHOD`
3. **L2-3 health**：`uds_client --method health` 返回 outbox_backlog；停 DB 时 degraded
4. **L2-4 JSON 日志**：`--json-logs` 运行日志每行 JSON 含 trace_id/request_id；无 PII
5. **L2-5 systemd**：`systemctl --user` 安装 kylin-memory.service 启动/重启/回退

## 技术债变化

- TD-D4D-001/002/003：保持 Open（consumer 注入点、deadline 非抢占、Outbox 单事务持锁——本轮不触发）
- 新增：无

## 风险与回滚方式

- **风险**：production resolver 未就绪（BLOCKED_BY_HOST_MAPPING）——已用 activation A+B 消除「协议 SUPPORTED 但生产 INTERNAL_ERROR」矛盾；
  C 轨 protocol_adapter 需同步 turn.finalized 方法（不阻塞本 PR 服务端）
- **回滚**：迁移 `downgrade 001_initial_schema`（表重建，数据保留）；代码回退分支基线
