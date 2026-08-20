# 初版数据库需求文档目标符合性审查报告

- **审查日期**：2026-08-17
- **审查对象**：`deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md`（v1.0 DRAFT）
- **审查方式**：逐项比对冻结契约、代码现状、施工普查，只给 file:line 证据，不臆测；严格区分「需求文档自身缺陷」与「实现尚未启动（预期）」
- **对照依据**：
  - `deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`（FRZ-DB-001~005 / Migration / FRZ-CFG-001）
  - `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`、`D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md`
  - `docs/baseline/v2-20260816/02_kylin_vm_environment_baseline_20260816.md`
  - `deliverables/D4_DB_IMPLEMENTATION_STATUS_SURVEY_20260817.md`、`D4_DB_INITIAL_IMPLEMENTATION_AUDIT_20260817.md`
  - `deliverables/D4_DB_SCHEMA_V53_COMPARISON_20260817.md`
  - `memory-service/` 实际代码

---

## 一、核心结论

需求文档对冻结契约的**复述整体忠实**：五张表逐列、4 项索引、FTS5 定义、迁移工具链、配置 8 键 + `KYLIN_MEMORY_*` 环境变量、失败路由 5 条路径 + L0-L3+Fatal + Dead Letter + 幂等策略、红线（不写官方库 / 原文隔离 / 假数据零容忍）、范围外 DEFERRED 项，均与冻结文档一致。R-2/R-3/R-4/R-5 四项待裁定也基本准确反映了已知冲突。

**但不完全符合目标**：存在 **4 处实质缺陷 + 2 处次要缺陷**，其中 3 处是需求文档自身的缺陷（未识别冻结契约内部矛盾、未纳入已知代码偏离、新增未冻结项），须在 D4-D 开工前修正，否则会导致幂等表结构错误、失败路由错误码域无法落地、触碰冻结纪律。

| 类别 | 数量 | 是否阻断开工 |
|------|------|-------------|
| 实质缺陷（需求文档自身） | 4 | 其中 2 项阻断（幂等主键、错误码域） |
| 次要缺陷 | 2 | 不阻断，需登记 |
| 符合项 | 9 类 | — |

---

## 二、逐项不符清单

| # | 需求条目 | 问题类型 | 依据（file:line） | 建议修改 |
|---|---------|---------|------------------|---------|
| 1 | FR-DB-001 §二 idempotency_cache（:62）+ FR-FB-005（:161-166） | **矛盾 / 不可落地（高）** | 需求 `idempotency_key` 为**单列主键**（`D4_DB_INITIAL_REQUIREMENTS_20260817.md:62`），但 FR-FB-005 写「查 idempotency_cache(user_id, session_id, idempotency_key)」且「幂等键作用域为三元组」（:161、:166）；冻结契约同样自相矛盾——`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md:175` 单列 PK，但 `:252`、`:254` 三元组查询、FRZ-IPC-005 声明「三元组作用域」（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:23`）。代码侧 `fingerprint.py:65-66` 的去重键为 `user_id:{key}`，证明 `idempotency_key` **并非全局唯一**，单列 PK 会导致跨用户撞键 | 需求文档必须新增待裁定项：主键改为复合 `(user_id, session_id, idempotency_key)`，或明确 `idempotency_key` 全局唯一（丢弃三元组作用域语义）。二者择一并回写冻结（走 ADR/Gate） |
| 2 | FR-DB-006 / R-5「失败路由使用统一错误码枚举」（:113、:205） | **缺失 / 不可落地（高）** | R-5 只处理了 TIMEOUT 纳入枚举，**未纳入 ALIGN-002/003 已知偏离**：代码实际错误码域为 `ERR_PROTOCOL/ERR_INVALID_REQUEST/ERR_TIMEOUT/ERR_UNKNOWN/ERR_EMBED_FAILED/ERR_SERVICE_STOPPED`（`embedding_service.py:181`、`server.py:117`），与冻结 FRZ-IPC-002 五项 `UNSUPPORTED_METHOD/INVALID_REQUEST/PROTOCOL_ERROR/INTERNAL_ERROR/TIMEOUT` 不一致（`D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md:23`）；尤其代码发的是 `ERR_TIMEOUT` 而非冻结 `TIMEOUT`（`embedding_service.py:181`），envelope 也是 `ok/result/error` 而非 `status/data/server_ts`（`embedding_service.py:225-246`、一致性审计 :27） | 需求须明确：DB 失败路由对外错误码与 envelope 采用哪个域，并登记 ALIGN-002/003 对齐动作（映射到冻结枚举 or 走 ADR 承认子服务独立域），不得在 R-5 中以「统一错误码枚举」一语带过 |
| 3 | FR-DB-003 连接与事务（:90-91） | **新增未冻结项（中）** | 需求新增「开启 WAL 模式 / busy_timeout 合理设置 / 单写多读约束」，但 FRZ-DB-001~005 冻结契约**未冻结**这三项（`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md:206-350` 无 WAL/busy_timeout/单写多读条目；仅 outbox 有「在线检索优先于后台写入/Embedding Worker 串行」并发约束，见 `:166-169`） | 属「新增未冻结项」，按项目红线纪律须登记（ADR 或任务卡批准），或在需求中标注「实现细节、不纳入冻结审查」 |
| 4 | FR-DB-002 迁移命名（:83） | **矛盾（沿袭冻结矛盾，中）** | 需求写「基线 `001_initial_schema`（或按日期命名）」，用「或」掩盖冻结自身矛盾：冻结 §4.1 同时要求「命名 `YYYYMMDD_<description>.py`」与「基线 `001_initial_schema.py`」，二者格式不兼容（`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md:280、:282`） | 需求新增待裁定项（建议 R-6）：基线迁移命名确定为 `001_initial_schema.py`（与冻结「基线」一致）还是 `YYYYMMDD_initial_schema.py`（与命名约定一致），并同步回写冻结 |
| 5 | FR-DB-001 memory_entries.entry_type 枚举（:57） | **缺失（低）** | 需求定义 DB 枚举 `{preference,knowledge,tool_result,behavior}`，但未定义其与 E 轨业务 Schema 枚举的映射：`pipeline/schemas.py:74-80` `MemoryType{short_term,medium_term,long_term,ephemeral}`、`:31-40` `SourceType{chat,tool_result,...}` 是另一套体系，`tool_result` 两处同名不同层级，DAO 落库时无映射依据 | 需求补一条：entry_type 与业务枚举的映射关系（谁映射到谁），或明确 DB 层独立枚举、由业务层负责归类 |
| 6 | §五 验收建议（:185-194） | **缺失（低）** | 验收表仅 L0/L2，缺 L1（组件集成）；且无「聊天不阻塞」的直接断言项（核心原则 [02 §2.2] 仅隐含在「降级→空上下文」项内） | 建议补 L1（WSL2 本地 IPC 集成）验收项 + 一条「故障注入下聊天主链路不阻塞」显式断言 |

---

## 三、符合项确认

| # | 检查点 | 结论 | 依据 |
|---|--------|------|------|
| 1 | 五张表逐列与 FRZ-DB-001 一致（conversations 5 列 / turns 8 列 / memory_entries 10 列 / outbox 9 列 / idempotency_cache 6 列） | ✅ 一致 | 需求 :52-62 vs 冻结 `D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md:110-181` |
| 2 | 4 项索引一致（idx_turns_session / idx_memory_user_type / idx_memory_deleted / idx_outbox_pending 含 `WHERE attempts<=3`） | ✅ 一致 | 需求 :64-68 vs 冻结 :184-189 |
| 3 | FTS5 `memory_fts` 定义一致（content/entry_type/user_id UNINDEXED/tokenize='unicode61' + 触发器同步） | ✅ 一致 | 需求 :71-76 vs 冻结 :193-202 |
| 4 | 迁移工具/目录/禁止项一致（Alembic + SQLAlchemy 2.0 Core + downgrade + 禁止手动改库 / 禁止 `render_as_batch=False` autogenerate / 禁止删列） | ✅ 一致 | 需求 :82-86 vs 冻结 :274-288 |
| 5 | 配置 8 键 + `KYLIN_MEMORY_*` 3 环境变量 + 优先级 CLI>env>file 与 FRZ-CFG-001 一致 | ✅ 一致 | 需求 :111-112 vs 冻结 :302-319 |
| 6 | 失败路由 5 条路径 + L0-L3+Fatal + 写入路由 + Dead Letter + 幂等策略全覆盖冻结 §3.1~3.5（含遗忘/撤回路径由 FR-DB-005 承接） | ✅ 一致 | 需求 :121-166 vs 冻结 :210-256、:258-268 |
| 7 | 红线守住：范围外「不写官方库」、NFR-2 原文隔离、FR-FB-001 假数据零容忍 | ✅ 一致 | 需求 :40、:55、:119、:174-176 |
| 8 | 范围外 DEFERRED（压缩/多路复用/心跳/连接池/流式）与 IPC 冻结 DEFERRED 一致 | ✅ 一致 | 需求 :39 vs `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:49` |
| 9 | R-2（`.sql` vs `.py`）、R-3（`KMA_*` vs `KYLIN_MEMORY_*`）、R-4（degraded 同名异义）待裁定项与施工普查结论一致 | ✅ 一致 | 需求 :202-204 vs `D4_DB_IMPLEMENTATION_STATUS_SURVEY_20260817.md:83-87` |

---

## 四、区分「需求文档缺陷」 vs 「实现尚未启动（预期）」

- **需求文档自身缺陷（须修需求，共 6 项）**：§二清单 #1（幂等主键矛盾）、#2（错误码域缺失）、#3（新增未冻结项）、#4（迁移命名矛盾）、#5（entry_type 映射缺失）、#6（验收表缺 L1/聊天不阻塞断言）。
- **实现尚未启动（预期，非需求缺陷）**：`kylin_memory.db` 建表 / Alembic / DAO / Outbox / 幂等缓存表 / FTS5 当前零实现，与冻结文档 GAP-DB-001~004「设计冻结，D4-D 实现」一致（`D4_DB_IMPLEMENTATION_STATUS_SURVEY_20260817.md:12、21`）。需求文档未把它们描述为「已实现」，不构成虚假表述。
- **代码偏离（已冻结登记、非本需求引入）**：ALIGN-001~005（4MiB vs 64KB、错误码域、envelope、方法路由、UDS 路径）在 IPC 正式冻结中已登记为「冻结后代码对齐」（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:58-66`），但需求文档 R-5 只覆盖其中 TIMEOUT 一项，未将 ALIGN-002/003 纳入 DB 失败路由的错误码/envelope 决策（见 §二 #2）。

---

## 五、是否需要修改的明确判断

**需要修改。** 具体：

1. **必须修改（阻断开工）**：
   - #1 幂等表主键：新增待裁定项，PK 复合 `(user_id, session_id, idempotency_key)` 或声明 `idempotency_key` 全局唯一，二选一，回写冻结。
   - #2 错误码域：R-5 补全 ALIGN-002/003 对齐方案（映射到冻结枚举 或 ADR 承认独立域），明确 DB 失败路由对外错误码与 envelope 采用哪个契约。
2. **建议修改（不阻断，登记）**：
   - #3 WAL/单写多读/busy_timeout 登记为新增未冻结项或标注为不冻结的实现细节。
   - #4 迁移基线命名拆解冻结自身矛盾，新增 R-6。
   - #5 entry_type 与业务枚举映射补定义。
   - #6 验收表补 L1 + 聊天不阻塞断言。
3. **无需修改**：§三所列 9 类符合项。

> 附注：本报告 6 项缺陷中，#4 的根因在冻结文档自身（§4.1 命名约定 vs 基线命名自相矛盾），#1 的根因同样是冻结 §2.2.5 与 §3.5/FRZ-IPC-005 自相矛盾——需求文档作为下游输入，未能拆解上游矛盾并以待裁定项显式暴露，属需求编制缺陷。
