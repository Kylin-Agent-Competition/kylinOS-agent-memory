# D4D 任务卡：IPC Gateway / 数据库层 / Outbox+部署骨架（Day10-D）

| 字段 | 内容 |
|------|------|
| 任务编号 | D4D（Day10-D） |
| 任务标题 | ① IPC Gateway + Handler Registry + health；② SQLite/SQLAlchemy Core/Alembic/UoW；③ Outbox + 配置 + 日志 + systemd --user 骨架 |
| 责任轨道 | D（周子腾）；Reviewer：E（谢嘉然） |
| 基线分支 | `feat/d4d-ipc-db-outbox`（基于 main @ `2b8bed7`，PR #47） |
| 基线 Commit | `2b8bed7b2cae33bb5a00e1291fb6ac00ec304358` |
| 对照文档版本 | IPC 冻结 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-001~007，已签署）；DB 需求 v1.3 `D4_DB_INITIAL_REQUIREMENTS_20260817.md`（FRZ-DB-001~005/FRZ-CFG-001/ADR-005/006/007，已签署）；部署冻结 `D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`；技术栈基线 [02 §2.1]；VERSION_MAP 真源 |
| 目标 | 建立 Memory Service 对外服务主骨架：冻结 IPC 协议上的 Gateway 层（含 Handler Registry 与 health）；冻结 DB 契约上的 SQLite 数据层（Alembic 迁移 + SQLAlchemy 2.0 Core + UoW + DAO）；Outbox Worker 骨架 + 配置加载器 + 日志 + systemd --user 正式 unit |

---

## 一、范围

### 1.1 范围内（本任务必须）

| # | 模块 | 内容 | 依据 |
|---|------|------|------|
| 1 | `memory-service/gateway/` | 长度前缀 JSON 协议（**按冻结**：4B BE uint32 + UTF-8 JSON、64KB、protocol_version `"1.0"`）、Handler Registry、UDS 服务器、health/echo/memory.retrieve handler、memory.store → UNSUPPORTED_METHOD | FRZ-IPC-001~007 |
| 2 | `migrations/` | Alembic 工具链（alembic.ini + env.py）+ 基线迁移 `001_initial_schema.py`（5 表 + 4 冻结索引 + 1 辅助索引 + FTS5 + 触发器），每个迁移含 downgrade | FRZ-DB-001/002、ADR-007、R-2 |
| 3 | `memory-service/db/` | SQLite 连接管理（WAL/busy_timeout/单写锁）、SQLAlchemy 2.0 Core 表定义、DAO（5 表基础 CRUD + 幂等缓存）、UoW（业务写 + Outbox 入队同事务） | FRZ-DB-001/003/005、FR-DB-003、附录 A |
| 4 | `memory-service/outbox/` | Outbox Worker 骨架（独立线程、轮询、指数退避、attempts>3 进 Dead Letter、幂等缓存过期清理 LIMIT 100） | FR-DB-004、附录 B |
| 5 | `memory-service/config.py` | `config.toml` 8 键 + 默认值 + 校验 + `KYLIN_MEMORY_*` 环境变量覆盖（CLI > env > file）；文件缺失用默认值 + WARN；值非法 fail-fast | FRZ-CFG-001、FR-DB-006 |
| 6 | `memory-service/logging_setup.py` | 日志配置（`~/.local/state/kylin-memory/`、log.level 可配、禁止记录正文/PII） | 部署冻结 §1.1、NFR-4 |
| 7 | `packaging/systemd/kylin-memory.service` | 正式 systemd --user unit（按冻结 §1.2：Type=simple、RuntimeDirectory=kylin-memory、Restart=on-failure、RestartSec=5s） | 部署冻结 §1.2 |
| 8 | `memory-service/app.py` | 组装入口（配置 → 日志 → DB/UoW → Outbox Worker → Gateway 启动） | 部署冻结 §1.2 ExecStart |
| 9 | `memory-service/tests/` | 对应 L0/L1 测试（协议/配置/DAO/UoW/Outbox/Gateway/幂等） | NFR-6 |

### 1.2 范围外（本任务不做，DEFERRED）

| # | 项 | 理由 |
|---|-----|------|
| 1 | Vector 接入（附录 C） | R-9 待 D4-D 技术确认（C++ 桥 / Kytensor HTTP-gRPC），不阻塞 SQLite 部分；Outbox 处理步骤 4a 的 Vector 写入以注入点 + FTS5 兜底表达 |
| 2 | 真实 Embedding 桥接入 Outbox 处理链 | Embedding 属轨道 A 已交付能力；本任务 Outbox Worker 只建骨架与失败路由，真实 Vector/Embedding 消费待 Vector 接入确认后接线 |
| 3 | 遗忘/撤回 execute 全流程 | FR-DB-005 属 D4+ 业务，本任务仅保留 outbox/memory_entries 所需表结构与审计列 |
| 4 | 压缩/多路复用/心跳/连接池/流式/双向流 | IPC DEFERRED（08-07 §七） |
| 5 | 修改现有 `embedding/`、`pipeline/`、`domain/`、`providers/`、`security/`、`service/` 代码 | 范围克制；现有 embedding 协议偏离（ALIGN-001~005）登记不动，不阻塞新 Gateway（新 Gateway 按冻结实现） |
| 6 | 官方库写入、多用户跨进程并发写 | 红线 + DEFERRED |

## 二、禁止修改范围（红线）

- 不修改已冻结契约：FRZ-IPC-001~007 线协议/错误码/字段/路由；FRZ-DB-001~005 列名/类型/约束/索引；FRZ-CFG-001 配置键；ADR-005/006/007 裁定（复合 PK、envelope、迁移命名）。
- 不修改官方 SDK 头文件、不写 `/usr`、不覆盖官方 .so、不要求 root。
- 代码/配置/日志/测试中不得出现 API Key/密码/Token/私钥；只提交 `.env.example`。
- 不把 Mock/固定返回/空实现当生产功能；降级只返回真实结果或空上下文。
- 不把 WSL/沙箱结果当宿主证据；L2 验证项如实标注"未执行/待验证"。

## 三、契约分析（第 3 步，实现依据）

### 3.1 IPC 线协议（FRZ-IPC-001/002/003/004/006）

- 帧 = 4 字节 Big-Endian uint32 长度 + UTF-8 JSON，最大 **65536 字节（64KB）**。
- `protocol_version` 固定 `"1.0"`；请求/响应均携带；请求版本不匹配 → `PROTOCOL_ERROR`。
- 错误码枚举（5 项）：`UNSUPPORTED_METHOD / INVALID_REQUEST / PROTOCOL_ERROR / INTERNAL_ERROR / TIMEOUT`；内部异常一律经映射表转稳定枚举，禁止泄漏 traceback。
- 请求顶级字段（7）：`protocol_version` / `request_id` / `trace_id` / `method` / `deadline_ms`（必填，无默认）/ `idempotency_key`（可选，写操作建议）/ `payload`（object）。
- 响应顶级字段（6）：`protocol_version` / `request_id` / `trace_id` / `status`（"ok"/"error"）/ `data` / `server_ts`（ISO8601 UTC）；错误响应追加 `error_code` / `message`（不可含 PII/堆栈）。
- 超时语义：服务端 `server_processing_time > deadline_ms` → `status:"error"` + `error_code:"TIMEOUT"`；客户端 `deadline_ms+100ms` 未收到响应视为超时。

### 3.2 方法路由（FRZ-IPC-007）

| method | 本任务行为 |
|--------|-----------|
| `echo` | 回显 payload（调试） |
| `health` | 返回服务状态（含 db 可达性探测结果） |
| `memory.retrieve` | 返回空上下文（检索主链后续接入；`data.context=[]` 真实空结果，非假数据） |
| `memory.store` | 返回 `UNSUPPORTED_METHOD`（符合 Gate 0 预期） |
| 其余未知 | `UNSUPPORTED_METHOD` |

### 3.3 数据库 Schema（FRZ-DB-001，DDL 逐字段对齐，不得偏离）

- **conversations**：id PK AUTOINCREMENT / user_id NOT NULL / session_id NOT NULL UNIQUE / started_at NOT NULL / ended_at NULL
- **turns**：id PK / session_id NOT NULL REFERENCES conversations(session_id) / turn_index NOT NULL / original_user_text NOT NULL / model_request NULL / model_response NULL / is_end NOT NULL DEFAULT 0 / created_at NOT NULL
- **memory_entries**：id PK / user_id NOT NULL / entry_type NOT NULL ∈ {preference,knowledge,tool_result,behavior} / content NOT NULL JSON / source_turn_id NULL REFERENCES turns(id) / confidence NOT NULL DEFAULT 0.0 ∈ [0,1] / version NOT NULL DEFAULT 1（乐观锁）/ is_deleted NOT NULL DEFAULT 0 / created_at NOT NULL / updated_at NOT NULL
- **outbox**：id PK / aggregate_type NOT NULL ∈ {turn,memory} / aggregate_id NOT NULL / event_type NOT NULL / payload NOT NULL JSON / attempts NOT NULL DEFAULT 0 / next_retry_at NULL / last_error NULL / created_at NOT NULL
- **idempotency_cache**：**复合 PK (user_id, session_id, idempotency_key)**（ADR-006）/ response NOT NULL JSON / created_at NOT NULL / expires_at NOT NULL（TTL=24h）
- **索引**（4 冻结 + 1 辅助）：`idx_turns_session`(turns.session_id, turn_index) / `idx_memory_user_type`(memory_entries.user_id, entry_type) / `idx_memory_deleted`(memory_entries.is_deleted) / `idx_outbox_pending`(outbox.next_retry_at) WHERE attempts <= 3 / （辅助）`idx_idempotency_expires`(idempotency_cache.expires_at)
- **FTS5**：`memory_fts(content, entry_type, user_id UNINDEXED, tokenize='unicode61')`；INSERT/UPDATE/DELETE 触发器同步；软删除（is_deleted 0→1）时触发器自动删除 FTS 记录，遗忘不额外重建。

### 3.4 配置（FRZ-CFG-001 / FR-DB-006，8 键）

| 键 | 类型 | 默认值 | 校验 | 环境变量 |
|----|------|--------|------|---------|
| socket.path | string | `$XDG_RUNTIME_DIR/kylin-memory/memory.sock` | 非空；目录可创建 | `KYLIN_MEMORY_SOCKET` |
| database.path | string | `~/.local/share/kylin-memory/kylin_memory.db` | 非空；父目录可创建 | `KYLIN_MEMORY_DB` |
| deadline.default_ms | int | 5000 | 正整数 1..60000 | `KYLIN_MEMORY_DEADLINE_MS` |
| retrieve.deadline_ms | int | 150 | 正整数 1..5000 | `KYLIN_MEMORY_RETRIEVE_DEADLINE_MS` |
| outbox.poll_interval_s | int | 1 | 正整数 1..60 | `KYLIN_MEMORY_OUTBOX_POLL_INTERVAL_S` |
| outbox.max_retries | int | 3 | 正整数 1..10（保持 3） | `KYLIN_MEMORY_OUTBOX_MAX_RETRIES` |
| embedding.model | string | `default` | 非空 | `KYLIN_MEMORY_EMBEDDING_MODEL` |
| log.level | enum | INFO | ∈ {DEBUG,INFO,WARNING,ERROR,CRITICAL} | `KYLIN_MEMORY_LOG_LEVEL` |

加载边界：文件缺失 → 默认值 + WARN；文件存在但值非法 → fail-fast；环境变量非法 → fail-fast。优先级 CLI > env > file。

### 3.5 Outbox（FR-DB-004 / 附录 B）

- Worker 独立线程；轮询 `poll_interval_s`（默认 1s）；查询 `next_retry_at <= now AND attempts <= max_retries ORDER BY next_retry_at`。
- 成功 → DELETE；失败 → attempts+1、`next_retry_at = now + 2^attempts * 30s`、last_error（不含 PII）；attempts > max_retries → Dead Letter（保留记录，next_retry_at=NULL，ERROR 日志）。
- 幂等缓存过期清理：每轮轮询 `DELETE FROM idempotency_cache WHERE expires_at < now LIMIT 100`。
- 写串行化：业务线程与 Worker 共用进程内单写锁（避免 SQLITE_BUSY）；busy_timeout 到期捕获 `OperationalError: database is locked` → 转降级（空上下文 + 日志），不得上抛阻塞聊天。

### 3.6 UoW（FR-DB-003）

- 业务写 + Outbox 入队**同一事务**提交。
- 幂等：查缓存 → 命中返回缓存；未命中 → 同事务执行业务 + 写缓存；并发未命中双写由单写锁 + 复合 PK 唯一约束兜底，第二次 INSERT 冲突 → 回查返回首次缓存（不得视为错误）。

## 四、安全边界

- 日志/审计不记录 content 正文与 PII；last_error 仅错误摘要。
- UDS socket 目录权限 0700（部署冻结 §1.1）；拒绝已停止连接的新请求。
- 原文隔离列语义保留（original_user_text 与 model_request 分离），本任务仅建表不实现注入逻辑。
- 跨用户隔离由 user_id 列 + DAO 层强制 user_id 过滤（Repository 层约束，[02 §16.6]）。

## 五、WSL 可测项（L0/L1，本任务执行）

- L0：py_compile 全量、Ruff、pytest 收集。
- L1（pytest，WSL2 Python 3.10）：
  - 协议：编码/解码往返、64KB 上限、非法 JSON/长度 → PROTOCOL_ERROR、protocol_version 不匹配。
  - 配置：8 键默认值、env 覆盖、非法值 fail-fast、文件缺失 WARN 默认启动。
  - 迁移：`alembic upgrade head` 成功 + `.schema` 断言（表/列/索引/FTS5 存在）+ `downgrade base` 成功。
  - DAO/UoW：5 表 CRUD、业务写 + Outbox 同事务（回滚原子性）、幂等命中/未命中/并发冲突回查。
  - Outbox：成功删除、失败退避（next_retry_at 计算）、attempts>3 进 DL、幂等缓存清理 LIMIT 100。
  - Gateway：UDS 端到端 echo/health/retrieve（空上下文）/store（UNSUPPORTED_METHOD）/未知方法、TIMEOUT 行为、停止后拒绝新请求。

## 六、麒麟 L2 必测项（本任务不声称已执行，交付人工操作清单）

- VM 上 `alembic upgrade head` + `.schema` 与冻结文档逐列对照（FRZ-DB-001 验收）。
- VM 上 systemd --user 安装 `kylin-memory.service` → 启动/重启/日志/回退（部署冻结 §1.2 验收；正式发行环境 systemd 测试未执行前不得写"成品通过"）。
- FTS5 中文检索 + 软删除同步（MATCH 不再命中）。
- busy_timeout 注入持锁场景 → 断言超时降级而非无限阻塞（R-8 语义边界）。
- UDS 断开/超时 → 空上下文（FR-FB-001 路径 1/2）。

## 七、交付物

- 新增：`memory-service/gateway/`（protocol/registry/server/handlers）、`memory-service/db/`（schema/engine/repositories/uow）、`memory-service/outbox/worker.py`、`memory-service/config.py`、`memory-service/logging_setup.py`、`memory-service/app.py`、`migrations/`（alembic.ini/env.py/versions/001_initial_schema.py）、`packaging/systemd/kylin-memory.service`、`memory-service/tests/test_*_d4d*.py`、本任务卡 `docs/day10/01_task_card.md`。
- 修改：`config/environment.example`（KMA_* → KYLIN_MEMORY_* 接线，R-3）、`migrations/README.md`（.sql 示意 → Alembic .py 示意，R-2）。

## 八、验收标准

- L0：py_compile + Ruff 全绿；pytest 全量通过（含失败路径/幂等/并发/边界用例，禁止删测试换取通过）。
- 契约零偏离：新 Gateway 按 FRZ-IPC-001~007；DDL 按 FRZ-DB-001；配置按 FRZ-CFG-001。
- 无假实现：memory.retrieve 返回真实空上下文；降级为真实结果或空上下文；TODO/FIXME 引用 TD 编号。
- 开发报告按输出格式：修改清单、契约变化、测试结果、待 L2 验证项、技术债变化、风险与回滚。

## 九、技术债关联

- 涉及既有登记：TD-IPC-002（权限）、TD-IPC-003（deadline 复测）、TD-IPC-004（重连单连接）；ALIGN-001~005（现有 embedding 协议偏离，本任务不处理，保持登记）。
- 本任务新增候选：Vector 接入确认（R-9）未完成前 Outbox 消费端为注入点 + FTS5 兜底 —— 实现时登记 TD 编号并在代码注释引用。

---
*任务卡编制：opencode（2026-08-21）｜依据冻结文档均已在 main 签署生效（Reviewer E 2026-08-20）*
