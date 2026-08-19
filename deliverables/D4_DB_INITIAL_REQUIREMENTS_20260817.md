# 初版数据库需求文档（D4-D 实施输入）

- **文档版本**：v1.3（2026-08-17，按 AI Reviewer 可维护性审查整改：补 Vector 存储/并发模型/乐观锁/FTS5 软删除语义等 17 项）
- **编制人**：周子腾（D），配合 D4-D 实施
- **审查人**：周子腾（D）人工核对（15 项，v1.1→v1.2 整改）+ AI Reviewer 可维护性审查（17 项，本版整改）
- **依据**：
  - `deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`（设计冻结：FRZ-DB-001~005、Migration 策略、FRZ-CFG-001、GAP-DB-001~004）
  - `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（IPC 正式冻结：错误码 5 项、幂等三元组、deadline）
  - `deliverables/D4_DB_REQUIREMENTS_COMPLIANCE_AUDIT_20260817.md`（opencode 符合性审查）
  - 人工审查报告 ×2 + AI Reviewer 可维护性审查报告（本版整改依据）
  - `docs/baseline/v2-20260816/02_kylin_vm_environment_baseline_20260816.md`（聊天优先、原文隔离原则）
  - `Kylin-runtime-knowledge/VERSION_MAP.md`（Vector Engine 接入真源）
- **用途**：作为 D4-D 制定「最初版本数据库」的 DDL / Alembic 迁移 / DAO / 失败路由实现的需求输入；本文件只定义"需求"，不替代 DDL 本身
- **单一真相源约定**：幂等流程见**附录 A**、Outbox 流程见**附录 B**、Vector 存储方案见**附录 C**、错误码映射见**附录 D**；正文其他位置只引用不重复定义
- **裁定项状态一致性约定（审查 1.1 整改）**：R-5/R-6/R-7 的**定案建议已写入正文**（DDL/实现可据此直接落地）；§六 为状态表，ADR/Gate 批准作为正式手续与冻结声明同步推进。**正文即实现依据，不因批准流程阻塞开工**；若 ADR 否决，按 §六 fallback 调整。

---

## 一、初版范围定义

### 1.1 目标

实现自研 `kylin_memory.db`（SQLite）的最小可用垂直：**建表 → 迁移 → 基础读写 DAO → 幂等 → Outbox → 失败路由/降级**，满足冻结契约 FRZ-DB-001~005 与 FRZ-CFG-001；Vector 数据接入官方 Vector Engine（附录 C）。

### 1.2 范围内（初版必须）

| # | 需求域 | 内容 |
|---|--------|------|
| 1 | 数据模型 | 5 张核心表 + 4 项索引 + FTS5 `memory_fts`（见 §二） |
| 2 | 迁移 | Alembic（SQLAlchemy 2.0 Core）工具链 + `001_initial_schema.py` 基线迁移 |
| 3 | 连接管理 | SQLite 连接、WAL 模式、单写多读约束、事务边界（R-8 定案见 §二 FR-DB-003） |
| 4 | 读写 DAO | conversations / turns / memory_entries / outbox / idempotency_cache 的基础 CRUD |
| 5 | 幂等写入 | 复合主键三元组命中返回缓存 / 未命中执行后写缓存（TTL=24h），流程见附录 A |
| 6 | Outbox | 写入事务化入队、Worker 轮询重试、指数退避、Dead Letter，流程见附录 B |
| 7 | 失败路由 | 5 条路径 + L0-L3+Fatal 降级层级（见 §三 FR-FB-001，映射关系单一来源） |
| 8 | 遗忘/撤回 | preview → confirm → execute（软删除 + FTS 同步 + 审计 + Outbox） |
| 9 | 配置 | `config.toml` 8 键 + 环境变量覆盖（默认值/校验规则见 §二 FR-DB-006） |
| 10 | **Vector 存储（审查 1.2 新增）** | 接入官方 Vector Engine，方案见附录 C |

### 1.3 范围外（初版不做，DEFERRED）

| # | 项 | 理由 |
|---|-----|------|
| 1 | 压缩/多路复用/心跳/连接池/流式 | IPC DEFERRED（08-07 文档 §七） |
| 2 | 官方库写入（kylin_aiassistant_database.db / knowledgebase_database.db） | 红线：自研库与官方库隔离，不写入官方库 |
| 3 | 生产 Schema 之外的并发/性能优化 | 非验收范围 |
| 4 | 多用户在线并发写（跨进程） | 单用户本地优先；并发写策略待 D4+ |

---

## 二、功能需求（FR）

### FR-DB-001 数据模型（DDL 依据）

实现以下表结构（逐字段对齐冻结文档 §2.2，**列名/类型/约束不得偏离**；已裁定项见 §六）：

**conversations**（id PK AUTOINCREMENT / user_id NOT NULL / session_id NOT NULL UNIQUE / started_at NOT NULL / ended_at NULL）

**turns**（id PK / session_id NOT NULL REFERENCES conversations(session_id) / turn_index NOT NULL / original_user_text NOT NULL / model_request NULL / model_response NULL / is_end NOT NULL DEFAULT 0 / created_at NOT NULL）
- 原文隔离约束：`original_user_text` 保存用户原文，`model_request` 保存注入后请求；禁止在 model_request 中原地修改 original_user_text；检索上下文只允许从 model_request 拉取

**memory_entries**（id PK / user_id NOT NULL / entry_type NOT NULL ∈ {preference,knowledge,tool_result,behavior} / content NOT NULL JSON / source_turn_id NULL REFERENCES turns(id) / confidence NOT NULL DEFAULT 0.0 ∈ [0,1] / version NOT NULL DEFAULT 1 乐观锁 / is_deleted NOT NULL DEFAULT 0 / created_at NOT NULL / updated_at NOT NULL）
- **乐观锁使用规范（审查 1.4 整改）**：
  - 所有 UPDATE memory_entries 必须带 `WHERE id = ? AND version = :current_version`
  - 冲突（0 行受影响）→ 抛 `ConcurrentUpdateError`，由调用方重试（最多 3 次）或放弃并记日志
  - `version` 由应用层自增（`SET version = version + 1`），不使用触发器

**outbox**（id PK / aggregate_type NOT NULL ∈ {turn,memory} / aggregate_id NOT NULL / event_type NOT NULL / payload NOT NULL JSON / attempts NOT NULL DEFAULT 0 / next_retry_at NULL / last_error NULL / created_at NOT NULL）
- 并发约束：在线检索优先于后台索引写入；Embedding Worker 默认串行或低并发；attempts > 3 进 Dead Letter

**idempotency_cache**（**复合主键 (user_id, session_id, idempotency_key)** / response NOT NULL JSON / created_at NOT NULL / expires_at NOT NULL，TTL=24h）
- 主键裁定（R-6，见 §六）：复合 PK；DDL 按此实现
- **辅助索引（审查 2.3 整改）**：`idx_idempotency_expires` (expires_at)——用于过期清理任务，属允许扩展（不破坏冻结 4 索引）

**索引**（4 项冻结 + 1 项辅助，与冻结文档 §2.3 一致）：
- `idx_turns_session` (turns.session_id, turn_index)
- `idx_memory_user_type` (memory_entries.user_id, entry_type)
- `idx_memory_deleted` (memory_entries.is_deleted)
- `idx_outbox_pending` (outbox.next_retry_at) WHERE attempts <= 3
- （辅助）`idx_idempotency_expires` (idempotency_cache.expires_at)

> **索引与配置配套约束（审查 2.2 整改）**：`idx_outbox_pending` 的 WHERE `attempts <= 3` 与 `outbox.max_retries` 默认 3 配套。若 D4-D 调整 `max_retries` 偏离 3，须同步走 ADR 更新该部分索引（或去掉 WHERE），避免 Worker 轮询全表扫描；需求默认**保持 max_retries=3**。

**FTS5**（冻结文档 §2.4）：
```sql
CREATE VIRTUAL TABLE memory_fts USING fts5(
    content, entry_type, user_id UNINDEXED, tokenize='unicode61'
);
```
- **软删除同步语义（审查 2.1 整改）**：
  - `is_deleted` 0→1 时，UPDATE 触发器自动从 FTS5 **删除**对应记录（MATCH 不再命中）；
  - 遗忘操作**不需要额外重建 FTS**（触发器已同步删除）；恢复/审计数据源为 `memory_entries`（含 is_deleted=1 记录）；
  - 仅在 FTS5 损坏修复时执行全表重建（数据源 memory_entries 全量）。
- INSERT/UPDATE/DELETE 触发器各一，保持 FTS 与 memory_entries 同步

**entry_type 映射（审查 2.5 整改）**：**DAO 仅接受已归类的 DB `entry_type` 值（透传），归类逻辑由上层 pipeline 负责**；下表为文档参考与验收口径，不纳入 DAO 实现逻辑。

| DB `entry_type` | 业务层来源 | 归类规则（pipeline 负责） |
|----------------|-----------|--------------------------|
| `preference` | 偏好规则输出 | 偏好规则命中 → preference |
| `knowledge` | 知识抽取输出（D8 六类知识） | 知识抽取 → knowledge |
| `tool_result` | `SourceType.tool_result` | 仅真实工具成功结果；失败/取消不形成成功知识（V5-3 口径） |
| `behavior` | 行为特征提取 | 行为特征 → behavior |

**验收**：麒麟 VM 上执行迁移后 `.schema` 与冻结文档逐列一致（含 R-6 复合主键）；FTS5 中文检索可用（unicode61）。

### FR-DB-002 迁移（Alembic）

- 工具：Alembic + SQLAlchemy 2.0 Core；迁移目录 `migrations/`
- 命名裁定（R-7）：基线迁移固定为 `001_initial_schema.py`；后续迁移使用 `YYYYMMDD_<description>.py`。二者不混用。
- 每个迁移必须有 `downgrade()`
- 禁止：手动改 SQLite、`render_as_batch=False` 的 autogenerate、删除列（用重命名迁移）
- R-2 定案：`migrations/README.md` 目录示意改为 Alembic `.py`（`001_initial_schema.py`），删除 `.sql` 示意

### FR-DB-003 连接与事务

- SQLite 文件 `~/.local/share/kylin-memory/kylin_memory.db`（默认，可配置覆盖）
- R-8 定案：WAL 模式 / `busy_timeout` / 单写多读为实现细节，数值由 D4-D 定；**语义边界冻结**：busy_timeout 到期必须触发降级（不得无限阻塞）
- **busy_timeout 捕获转换（审查 3.1 整改）**：SQLite `busy_timeout` 到期返回 `SQLITE_BUSY`（SQLAlchemy `OperationalError: database is locked`），**DAO 层必须捕获该异常并转换为 L1/L2 降级（空上下文 + 日志），不得上抛阻塞聊天**；禁止仅设置 busy_timeout 而不处理异常
- 写事务边界：业务写 + Outbox 入队**同一事务**提交（冻结文档 §3.3）
- 幂等检查与响应缓存写入：见**附录 A**（含并发冲突处理）
- **写串行化（审查 1.3 整改，详见 FR-DB-004）**：业务线程与 Worker 的所有 SQLite 写操作经统一写队列/锁串行化

### FR-DB-004 Outbox Worker

- **并发模型（审查 1.3 整改，P0）**：
  - Worker 为**独立线程**（同进程内，asyncio 任务或 threading.Thread），非独立进程；
  - SQLite 连接：业务与 Worker 各自持有连接（WAL 一写多读），但**所有写操作经进程内单一写锁/写队列串行化**（单写者模型），避免多线程写触发 BUSY；
  - 读操作可并行（WAL 快照读）。
- 轮询间隔 `outbox.poll_interval_s`（默认 1s）
- 重试：`next_retry_at = now + 2^attempts * 30s`（指数退避）
- 成功：Embedding 成功 → Vector INSERT（附录 C）→ Outbox DELETE
- 失败：attempts++ → 更新 next_retry_at；attempts > 3 → Dead Letter（保留记录，next_retry_at = NULL，不丢事件）
- 完整流程：见**附录 B**（单一真相源，本条目仅列参数）
- **Dead Letter 告警（审查 2.4 整改，简化）**：初版**每次 Dead Letter 记一条 ERROR 日志**（含 aggregate_id/event_type/attempts/last_error），不做去噪；消噪作为后续优化项
- **幂等缓存过期清理（审查 2.3 整改）**：Worker 每次轮询顺带执行 `DELETE FROM idempotency_cache WHERE expires_at < now LIMIT 100`（借 `idx_idempotency_expires`），避免查询时被动清理导致延迟

### FR-DB-005 遗忘/撤回

- `forget` 请求：preview（预览影响范围）→ 用户确认 → execute
- execute：SQLite 软删除（is_deleted=1，FTS 由触发器同步删除，**不额外重建**）→ Vector 标记删除 → 审计日志 → Outbox INSERT（最终一致性）
- **审计日志（审查 3.4 整改）**：记录操作元数据（user_id / entry_id / action / timestamp），**不记录 content 正文**；FTS5 重建数据源为 memory_entries（含 is_deleted=1）
- 失败：Outbox 重试 ×3 → Dead Letter + ERROR 日志告警

### FR-DB-006 配置（FRZ-CFG-001）

- 配置文件 `~/.config/kylin-memory/config.toml`；环境变量覆盖（CLI > env > file）
- **配置项表（含默认值/校验规则/环境变量映射，审查 2.6 整改——8 键全量映射）**：

| 键 | 类型 | 默认值 | 校验规则 | 环境变量 |
|----|------|--------|---------|---------|
| `socket.path` | string | `$XDG_RUNTIME_DIR/kylin-memory/memory.sock` | 非空；目录可创建 | `KYLIN_MEMORY_SOCKET` |
| `database.path` | string | `~/.local/share/kylin-memory/kylin_memory.db` | 非空；父目录可创建 | `KYLIN_MEMORY_DB` |
| `deadline.default_ms` | int | 5000 | 正整数 1..60000 | `KYLIN_MEMORY_DEADLINE_MS` |
| `retrieve.deadline_ms` | int | 150 | 正整数 1..5000 | `KYLIN_MEMORY_RETRIEVE_DEADLINE_MS` |
| `outbox.poll_interval_s` | int | 1 | 正整数 1..60 | `KYLIN_MEMORY_OUTBOX_POLL_INTERVAL_S` |
| `outbox.max_retries` | int | 3 | 正整数 1..10（**默认保持 3**，偏离须同步评估索引并走 ADR） | `KYLIN_MEMORY_OUTBOX_MAX_RETRIES` |
| `embedding.model` | string | `default` | 非空 | `KYLIN_MEMORY_EMBEDDING_MODEL` |
| `log.level` | enum | `INFO` | ∈ {DEBUG,INFO,WARNING,ERROR,CRITICAL} | `KYLIN_MEMORY_LOG_LEVEL` |

> 冻结契约仅冻结 3 个环境变量（socket/db/log.level）；**其余 5 个映射为扩展项**（审查 2.6 建议），不改变冻结契约，如需纳入冻结走 ADR。

- **加载与校验边界（审查 3.2 整改）**：
  - `config.toml` 不存在 → 用全部默认值启动 + WARN 日志（不 fail-fast）；
  - 文件存在但值非法 → fail-fast 拒绝启动；
  - 环境变量值非法 → **fail-fast**（不回退文件值）。
- R-3 定案：以冻结 `config.toml` + `KYLIN_MEMORY_*` 为准；`config/environment.example` 的 `KMA_*` 模板同步改为 `KYLIN_MEMORY_*` 并接线到代码

---

## 三、回退策略需求（FR-FB，期望实现的回退）

> 核心原则 [02 §2.2]：**Memory Service 超时/故障时聊天继续**。降级只返回真实结果或空上下文，不允许假数据蒙混（假实现零容忍）。
> **分层说明**：L0-L3+Fatal 为**读取侧**降级层级；写入侧失败（Vector 索引写入 / 遗忘执行）走 Outbox 重试（附录 B），**不映射到 L 层级**，同样遵循「不阻塞聊天」。

### FR-FB-001 读取侧失败路径 ↔ 降级层级映射（单一真相源）

| # | 路径 | 触发 | L 层级 | 降级行为 | 聊天继续 |
|---|------|------|:---:|---------|:---:|
| 1 | UDS 连接失败 | 无法连到 memory.sock | L2 | 空 context + 日志 | ✅ |
| 2 | UDS 超时 | 检索超过 `retrieve.deadline_ms`(150) | L1 | 空 context + 日志 | ✅ |
| 3 | SQLite 读取失败 | 查询异常/损坏（含 SQLITE_BUSY） | L3 | 空 context + 告警 | ✅ |
| 4 | Embedding 失败 | Provider 失败 | L2（读取侧） | 纯关键词检索（FTS5）或空 context | ✅ |
| 5 | Vector 检索失败 | 检索异常 | L2 | 空 context + 日志 | ✅ |
| — | Fatal | 任何降级都失败 | Fatal | 聊天继续（零上下文） | ✅ |

> L0 = 正常；L1 = UDS 超时；L2 = 服务不可用（连接失败/Embedding/Vector 检索）；L3 = SQLite 损坏。**Vector 索引写入失败**属写入侧（附录 B），不入本表。

### FR-FB-002 写入侧失败路由（单一真相源：附录 B）

```
TurnFinalizedEvent → SQLite INSERT（同步）
  └→ Outbox INSERT（同事务）                  [附录 B 步骤 1-2]
      └→ Worker 轮询 (1s)                    [附录 B 步骤 3]
          ├→ Embedding 成功 → Vector INSERT → Outbox DELETE   [步骤 4a]
          ├→ Embedding 失败 → attempts++ → next_retry_at      [步骤 4b]
          └→ attempts > 3 → Dead Letter + ERROR 日志          [步骤 4c]
```

### FR-FB-003 Dead Letter 策略

- 不丢事件：Dead Letter 记录保留在 outbox 表（next_retry_at = NULL）
- 诊断页暴露：backlog / oldest_pending_age / index_sync_lag（指标接口）
- 告警：ERROR 级别日志（简化实现，见 FR-DB-004）

### FR-FB-004 幂等写入（防重）

- 完整流程见**附录 A**（单一真相源）
- 与 IPC 冻结一致：幂等键作用域为三元组（user_id, session_id, idempotency_key），写操作建议提供

---

## 四、非功能需求

| 编号 | 需求 | 说明 |
|------|------|------|
| NFR-1 | 聊天优先 | 任何 DB 故障不得阻塞聊天；降级路径必须真实（空上下文），禁止假数据 |
| NFR-2 | 原文隔离 | original_user_text 与 model_request 分离；检索注入只走 model_request |
| NFR-3 | 数据隔离 | 自研库独立 SQLite 文件，不写官方库；用户数据按 user_id 隔离 |
| NFR-4 | 安全红线 | 不落明文密钥；审计日志不保留正文；敏感字段按 E 轨道规则处理 |
| NFR-5 | 可迁移性 | 所有 Schema 变更必须走 Alembic，禁止手工改库 |
| NFR-6 | 证据可追溯 | 每个 DAO/路由实现需可挂接 L0（单测）/ L1（集成）/ L2（麒麟 VM）验证证据 |

---

## 五、验收建议（L0/L1/L2）

> **「聊天主链路」边界定义**：限定为 **Memory Service 对外 UDS 请求路径**——故障注入下 UDS 请求必须按时返回（正常响应或降级空上下文），**不得挂起超过 `deadline.default_ms`**；不包含 LLM 推理线程与 UI 渲染（宿主侧）。

| 验收项 | 层级 | 验证方式 |
|--------|------|---------|
| 迁移可执行、downgrade 可用、`.schema` 与冻结一致 | L2 | 麒麟 VM 执行 `alembic upgrade head` + `.schema` 对照 |
| 5 表 CRUD 单测 | L0 | pytest（WSL2） |
| 组件集成（服务启动→客户端读写→幂等/Outbox 联动） | L1 | WSL2 本地 UDS IPC 集成测试 |
| FTS5 中文检索 + 软删除同步（is_deleted=1 后 MATCH 不再命中） | L0/L2 | 插入中文条目 → MATCH 命中 → 软删 → MATCH 不再命中 |
| 幂等：同 key 重复请求仅执行一次副作用 | L0/L2 | 重复写测试（附录 A 流程断言） |
| 幂等并发：双请求同时未命中不双写副作用 | L0 | 并发测试（附录 A 原子性断言） |
| Outbox：Embedding 失败重试退避、attempts>3 进 DL | L0/L2 | 注入失败模拟（附录 B 流程断言） |
| 降级：UDS 断开/超时/SQLite 损坏 → 空上下文 | L2 | VM 故障注入 |
| **聊天不阻塞** | L1/L2 | 故障注入下断言 UDS 请求在 `deadline.default_ms` 内返回 |
| **原文隔离（审查 2.7 整改）** | L0 | 断言方法：注入内容必须经显式标记包裹（如 `<injected_context>...</injected_context>`），断言 **model_request 中无裸 original_user_text**；用户合法引用场景（"我刚才说了什么"）因有包裹标记不误报 |
| 配置：8 键默认值 + env 覆盖 + 非法值 fail-fast + 文件缺失用默认值 | L0 | 加载测试（含非法值拒绝启动、文件缺失 WARN 启动用例） |
| busy_timeout 到期 → SQLITE_BUSY 捕获转降级（R-8 行为验证） | L2 | 注入持锁场景 → 断言超时降级而非异常上抛/无限阻塞 |
| Vector 写入失败 → Outbox 重试（附录 C 方案） | L0/L2 | 注入 Vector 故障 → 断言走 Outbox |

---

## 六、裁定结论与待批项

> **正文即实现依据**：R-5/R-6/R-7 已由 D 决策采纳方案 A（ADR-005/006/007，2026-08-17），冻结文档 §2.2.5/§4.1 已回写；Reviewer E（谢嘉然）签署后完成全部生效手续，D4-D 可按正文实现。

| 编号 | 项 | 结论 | 状态 | fallback（若 ADR 否决） |
|------|-----|------|------|------------------------|
| R-2 | migrations/README `.sql` vs `.py` | 以冻结为准：README 改 `.py` 示意 | ✅ 已定案 | — |
| R-3 | 配置命名 `KMA_*` vs `KYLIN_MEMORY_*` | 以冻结为准：模板改 `KYLIN_MEMORY_*` 并接线 | ✅ 已定案 | — |
| R-4 | embedding 局部 `degraded` vs 系统级降级 | 分层命名：provider 局部 vs 系统读取侧 L0-L3；写入侧走 Outbox | ✅ 已定案 | — |
| R-5 | **DB 对外错误码与 envelope 域** | 以 IPC 冻结契约为准（5 枚举 + `status/data/server_ts`）；映射见附录 D；`ERR_*` 按 ALIGN-002/003 冻结后对齐 | ✅ 已采纳（ADR-005，D 决策方案 A；Reviewer E 待签） | 按现代码域实现并登记技术债 ALIGN-002/003 |
| R-6 | **idempotency_cache 主键** | 复合 PK `(user_id, session_id, idempotency_key)` | ✅ 已采纳（ADR-006，D 决策方案 A；Reviewer E 待签；冻结 §2.2.5 已回写） | 临时单列 PK，批准后 Alembic 迁移为复合 PK |
| R-7 | **迁移基线命名** | 基线 `001_initial_schema.py`，后续 `YYYYMMDD_<desc>.py` | ✅ 已采纳（ADR-007，D 决策方案 A；Reviewer E 待签；冻结 §4.1 已回写） | 按 `YYYYMMDD_initial_schema.py` 命名（加别名） |
| R-8 | WAL/busy_timeout/单写多读 | 数值不冻结；**语义边界冻结**（busy_timeout 到期必须降级） | ✅ 已定案 | — |
| R-9 | **Vector 接入方式（审查 1.2 新增）** | 附录 C 方案：官方 Vector Engine，collection 命名 + 关联键；具体接入接口（C++ 桥/HTTP）由 D4-D 在现有 ABI 证据上确认 | ⏳ 待 D4-D 技术确认（不阻塞 SQLite 部分开工） | 初版 Vector 降级为 FTS5-only（纯关键词检索） |

**可先行开工（不受阻断项影响）**：migrations 目录与 alembic.ini 骨架（不含基线文件）、配置加载器（FR-DB-006）、连接管理（FR-DB-003）、Outbox Worker 骨架（FR-DB-004）。

---

## 附录 A：幂等写入流程（单一真相源）

```
请求到达
  → 查 idempotency_cache WHERE user_id=? AND session_id=? AND idempotency_key=?
    ├→ 命中 & expires_at > now → 返回缓存 response（不执行副作用）
    ├→ 命中 & expires_at <= now → DELETE 该行，继续执行
    └→ 未命中 → 执行业务逻辑（含 SQLite + Outbox 同事务）
                → INSERT idempotency_cache(user_id, session_id, idempotency_key,
                                           response, created_at=now, expires_at=now+24h)
                → 返回真实响应
```

**并发冲突处理（审查 3.5 整改）**：
- 幂等检查 + 业务执行 + 缓存写入必须在**同一事务**内完成（或使用 `INSERT OR IGNORE`）；
- 并发双请求同时未命中时，业务副作用只允许执行一次：写串行化（FR-DB-004 单写者模型）+ 复合 PK 唯一约束兜底；
- 第二次 INSERT 触发唯一键冲突 → 捕获后返回第一次写入的缓存 response（回查），**不得视为错误**。

**过期清理**：Worker 轮询顺带清理（FR-DB-004），非查询时被动清理。

## 附录 B：Outbox 失败路由流程（单一真相源）

```
1. 业务写入（TurnFinalizedEvent / memory / forget 审计）→ SQLite INSERT
2. 同事务 Outbox INSERT（aggregate_type, aggregate_id, event_type, payload,
                          attempts=0, next_retry_at=now, last_error=NULL）
3. Worker 独立线程，每 outbox.poll_interval_s 秒轮询：
     SELECT * FROM outbox WHERE next_retry_at <= now AND attempts <= outbox.max_retries
     ORDER BY next_retry_at
4. 逐条处理：
   4a. Embedding 成功 → Vector INSERT（附录 C）成功 → Outbox DELETE（事件完成）
   4b. Embedding/Vector 失败 → attempts += 1
         → next_retry_at = now + 2^attempts * 30s（指数退避）
         → last_error = 错误摘要（不含 PII）
   4c. attempts > outbox.max_retries → Dead Letter：
         → 保留记录（不 DELETE），next_retry_at = NULL
         → ERROR 日志一条（aggregate_id/event_type/attempts/last_error）
5. 写串行化：所有写操作经进程内单写锁（业务线程与 Worker 共用），避免 SQLITE_BUSY
```

## 附录 C：Vector 存储方案（审查 1.2 整改，P0）

**原则**：Vector 数据不存自研 SQLite（自研库仅存记忆元数据与检索结果关联），接入**官方 Vector Engine**（`libkysdk-vector-engine-client`，D2-B 已 E4 验证 CRUD/用户隔离/持久化；接口真源见 `Kylin-runtime-knowledge/VERSION_MAP.md`）。

| 项 | 方案 |
|----|------|
| 载体 | 官方 Vector Engine（独立于自研 SQLite；历史证据 VECTOR-CALL-001/002/003） |
| Collection 命名 | `memory_vectors`（按 user_id 隔离或单 collection + 过滤字段，以 D2-B 已验证的隔离方式为准） |
| 关联键 | `memory_entries.id` 作为 doc id / 关联字段（Vector ↔ 自研库双向可追溯） |
| 写入路径 | Outbox Worker 步骤 4a（附录 B）：Embedding 成功 → Vector INSERT |
| 删除路径 | 遗忘 execute：Vector 标记删除（按 doc id） |
| 失败降级 | Vector 写入失败 → Outbox 重试 ×3 → Dead Letter；Vector 检索失败 → L2 降级（空上下文）或 FTS5-only |
| 待 D4-D 确认 | Python 侧接入方式（C++ 桥 / Kytensor HTTP-gRPC 接口），基于现有 ABI/运行时证据；**未确认前不阻塞 SQLite 部分** |
| 兜底 | 若 Vector 接入不可行，初版降级为 FTS5-only（纯关键词检索，FR-FB-001 路径 4 已有此选项） |

## 附录 D：错误码映射表（审查 2.8 整改，建议对照；以 R-5 ADR 为准）

| 现有代码（`memory-service/embedding`） | IPC 冻结枚举（FRZ-IPC-002） | 说明 |
|---------------------------------------|---------------------------|------|
| `ERR_PROTOCOL` | `PROTOCOL_ERROR` | 协议层错误 |
| `ERR_INVALID_REQUEST` | `INVALID_REQUEST` | 请求格式无效 |
| `ERR_TIMEOUT` | `TIMEOUT` | 超时（冻结已含） |
| `ERR_UNKNOWN` | `INTERNAL_ERROR` | 未分类内部错误 |
| `ERR_EMBED_FAILED` | `INTERNAL_ERROR` | Provider 失败归内部错误（或经 ADR 增加专用码） |
| `ERR_SERVICE_STOPPED` | `INTERNAL_ERROR` | 服务停止归内部错误 |
| `UNSUPPORTED_METHOD` | `UNSUPPORTED_METHOD` | 同名（echo 层已正确） |

> 映射表为 D4-D 建议起点；IPC 冻结后续新增错误码时同步更新本表（错误码变更一律走 IPC 冻结 ADR，见冻结声明 §四 R-5）。

---

## 七、签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 需求编制 | 周子腾（D） | 2026-08-17 | 待确认 |
| D4-D 实施 | 待填写 | | |
| Reviewer | 待填写 | | |
