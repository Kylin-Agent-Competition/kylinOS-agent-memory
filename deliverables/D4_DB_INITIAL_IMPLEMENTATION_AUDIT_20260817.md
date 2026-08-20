# 数据库初版实现一致性核对报告（设计冻结 vs 实际代码）

- **核对日期**：2026-08-17
- **冻结依据**：`deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md` 第二~五章（FRZ-DB-001~005、Migration 策略、FRZ-CFG-001）
- **对照对象**：`memory-service/`、`migrations/`、`config/` 及全仓实际代码
- **核对方式**：只依据代码中实际存在的内容给出 file:line；未找到即标「未实现/未找到」，不把冻结文档当实现，不臆测

---

## 一、核心结论

1. **数据库初版（FRZ-DB-001）整体未实现**。`memory-service/` 当前处于 D5 阶段（仅 Embedding 最小垂直链路 + Pipeline 规则提取），**不存在任何 SQLite 建表、SQLAlchemy/Alembic 迁移、FTS5 虚拟表、索引创建代码**。`migrations/` 目录仅有一个 README，明确声明「仅建立目录和职责边界，尚无生产实现」。

2. **失败路由（FRZ-DB-002）、降级层级（FRZ-DB-003）、Dead Letter（FRZ-DB-004）未实现**。唯一相关联的「降级」是 embedding 层 Provider 失败时返回空向量（`embedding_service.py`），属轨道 A 的局部降级，**不是**冻结定义的 UDS 超时/SQLite 损坏/Outbox 失败路由与 L0-L3 分层，不应混淆。

3. **幂等写入（FRZ-DB-005）仅部分实现（字段级）**。`pipeline/schemas.py` 存在 `idempotency_key` 字段、`fingerprint.py` 存在内存级业务去重键推导，但**无 `idempotency_cache` SQLite 表、无 TTL=24h 缓存读写、无请求级「命中返回缓存响应」逻辑**。

4. **配置管理（FRZ-CFG-001）偏离**。冻结为 `~/.config/kylin-memory/config.toml` + 8 个 toml 键 + `KYLIN_MEMORY_*` 环境变量覆盖；实际仅有 `config/environment.example` 环境变量模板（键名 `KMA_*`），且**该模板未被 memory-service 代码消费**（代码仅通过 argparse `--socket` CLI 参数取 socket 路径）。

5. **本次「未实现」与冻结文档自身声明一致，属预期状态**：冻结文档第六、七章已把 GAP-DB-001~004 标注为「设计冻结，D4-D 实现」。本报告结论为「设计冻结已完成、实际实现尚未启动」，而非「实现偏离冻结契约」。

---

## 二、逐项对照表

> 结论取值：✅ 已实现 / 🟡 部分实现 / ❌ 未实现 / ⚠️ 偏离

### 2.1 数据库 Schema（FRZ-DB-001）

| 冻结项 | 结论 | 证据 file:line | 说明 |
|---|---|---|---|
| SQLite 建表（CREATE TABLE / sqlite3 / SQLAlchemy / Alembic / migration 文件） | ❌ 未实现 | `migrations/README.md:19`（「仅建立目录和职责边界，尚无生产实现」）；全仓 `.py` 无 `import sqlite3`/`sqlalchemy`/`alembic`（grep 无匹配）；`memory-service/requirements.txt:5-9` 仅含 pydantic/pytest/pybind11，无 SQLAlchemy/Alembic 依赖 | 无任何建表代码；`migrations/` 下仅 README.md，无 `001_initial_schema.py`/`.sql` |
| `conversations` 表（5 列，session_id UNIQUE） | ❌ 未实现 | 全仓无 `CREATE TABLE conversations`（.sql/.py grep 均无匹配） | 冻结文档 §2.2.1 仅停留在设计层 |
| `turns` 表（7 列，original_user_text 与 model_request 分离） | ❌ 未实现 | 无 `CREATE TABLE turns`；原文隔离约束仅存在于冻结文档 §2.2.2，代码无落地 | 同上 |
| `memory_entries` 表（9 列：entry_type/content/confidence/version/is_deleted 等） | ❌ 未实现 | 无 `CREATE TABLE memory_entries`；`memory-service/` 目录下无 memory 持久化模块（`memory-service/README.md:61-73` 标注 memory/retrieval 为「未来主要目录」） | 同上 |
| `outbox` 表（9 列：attempts/next_retry_at/last_error 等） | ❌ 未实现 | 无 `CREATE TABLE outbox`；全仓 `.py` 无 `outbox` 相关实现（grep 仅命中冻结文档/README 描述文字） | 同上 |
| `idempotency_cache` 表（6 列，idempotency_key 主键） | ❌ 未实现 | 无 `CREATE TABLE idempotency_cache`；`migrations/README.md` 无任何 .py/.sql 文件 | 与既有 `D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md:26` 结论一致（`migrations/` 仅 README） |
| 4 项索引（idx_turns_session / idx_memory_user_type / idx_memory_deleted / idx_outbox_pending） | ❌ 未实现 | 全仓无 `CREATE INDEX`（.sql grep 无匹配） | 冻结文档 §2.3 停留在设计层 |
| FTS5 虚拟表 `memory_fts` + 同步触发器 | ❌ 未实现 | 全仓无 `CREATE VIRTUAL TABLE` / `USING fts5` / `CREATE TRIGGER`（.sql grep 无匹配） | 冻结文档 §2.4 停留在设计层 |

### 2.2 Migration 策略

| 冻结项 | 结论 | 证据 file:line | 说明 |
|---|---|---|---|
| Alembic（SQLAlchemy 2.0 Core）工具落地 | ❌ 未实现 | 全仓无 `alembic`/`sqlalchemy`（grep 无匹配）；无 `alembic.ini`；`memory-service/requirements.txt:5-9` 无相关依赖 | 无 alembic 环境 |
| 迁移目录 + 命名 `YYYYMMDD_<description>.py` + 每个迁移含 `downgrade()` | ❌ 未实现 | `migrations/README.md` 无 .py 文件；未来目录示意为 `.sql`（`migrations/README.md:24-27`）而非 `.py` | 注意：README 的未来目录示意用 `001_initial_schema.sql`，与冻结的「Alembic + .py」命名约定**不一致**（见风险点 R-2） |
| 基线 `001_initial_schema.py` | ❌ 未实现 | 无此文件（`migrations/` 仅 README.md） | — |
| 禁止手动改 SQLite / 禁止 `render_as_batch=False` | 无法核验（N/A） | 无迁移实现，无从违规 | 暂无代码，不构成违规 |

### 2.3 失败路由（FRZ-DB-002，5 条路径）

| 冻结项 | 结论 | 证据 file:line | 说明 |
|---|---|---|---|
| UDS 连接失败 → 降级空上下文 | ❌ 未实现 | 无 memory context 组装代码（memory/retrieval 为「未来目录」`memory-service/README.md:61-73`） | D5 仅 embedding 链路，无上下文组装 |
| 150ms deadline 超时 → 降级空上下文 | ❌ 未实现 | 代码无 150ms deadline 读取/实现；`KMA_RETRIEVE_DEADLINE_MS=150` 仅存在于模板 `config/environment.example:17`，未被消费 | embedding 侧有独立超时（ERR_TIMEOUT，`memory-service/tests/test_embedding_service.py:115`），但非 150ms 检索 deadline |
| SQLite 读取失败 → 降级空上下文 + 错误日志 | ❌ 未实现 | 无 SQLite 读取代码 | — |
| Embedding 失败 → 降级纯关键词检索或空上下文 | 🟡 部分实现（局部） | `memory-service/embedding/embedding_service.py:184-187`、`:254-271`（Provider 失败返回明确空向量 + `degraded` 标记） | 仅覆盖「Embedding Provider 失败返回空向量」，属轨道 A 局部降级；「纯关键词检索」无实现（FTS5 未建） |
| Vector 索引写入失败 → Outbox 重试×3 → Dead Letter | ❌ 未实现 | 无 outbox/vector 写入代码 | — |
| 遗忘/撤回失败 → Outbox 重试×3 → Dead Letter + 审计告警 | ❌ 未实现 | 无 forget 执行/审计代码 | — |

### 2.4 降级层级（FRZ-DB-003）

| 冻结项 | 结论 | 证据 file:line | 说明 |
|---|---|---|---|
| L0-L3 + Fatal 五级降级分层 | ❌ 未实现 | 无分级降级实现；仅有 embedding 单点 `degraded`（`embedding_service.py:254-271`）与抽取 Provider 空候选降级（`memory-service/providers/extraction_provider.py:880` 区域） | 均属 provider 级局部降级，非冻结的 L0-L3 系统级分层 |
| 核心原则「超时/故障聊天继续（零上下文）」 | ❌ 未实现 | 无聊天主链路/上下文组装代码 | — |

### 2.5 Dead Letter 策略（FRZ-DB-004）

| 冻结项 | 结论 | 证据 file:line | 说明 |
|---|---|---|---|
| `attempts > 3` 进 Dead Letter | ❌ 未实现 | 无 outbox 表、无 attempts 字段逻辑 | — |
| 不丢事件（保留 outbox，`next_retry_at = NULL`） | ❌ 未实现 | 无 outbox 表 | — |
| 诊断页暴露 backlog / oldest_pending_age / index_sync_lag | ❌ 未实现 | 无诊断页/指标代码 | — |

### 2.6 幂等写入策略（FRZ-DB-005）

| 冻结项 | 结论 | 证据 file:line | 说明 |
|---|---|---|---|
| `idempotency_key` 字段存在 | ✅ 已实现（字段级） | `memory-service/pipeline/schemas.py:146`（`idempotency_key: str = Field(min_length=1)`） | 仅 Pydantic 事件模型字段 |
| 内存级业务去重键推导 | 🟡 部分实现 | `memory-service/pipeline/fingerprint.py:58-66`（`event_duplicate_key`：idempotency_key 优先、退化 event_id） | 属接入侧内存判重键，非持久化 |
| 请求到达 → 查 `idempotency_cache` 三元组 | ❌ 未实现 | 无 `idempotency_cache` 表、无查询逻辑 | — |
| 命中未过期 → 返回缓存响应（不执行副作用） | ❌ 未实现 | 无缓存响应读写 | — |
| 未命中 → 执行后写 `idempotency_cache`（TTL=24h） | ❌ 未实现 | 无写入/TTL 逻辑 | — |

### 2.7 配置管理（FRZ-CFG-001）

| 冻结项 | 结论 | 证据 file:line | 说明 |
|---|---|---|---|
| 配置文件 `~/.config/kylin-memory/config.toml` | ⚠️ 偏离 | 全仓无 `config.toml`（grep 无匹配）；仅 `config/environment.example`（环境变量模板） | 冻结为 toml，实际为 env 模板 |
| 8 项核心配置键（socket.path / database.path / deadline.default_ms / retrieve.deadline_ms / outbox.poll_interval_s / outbox.max_retries / embedding.model / log.level） | ⚠️ 偏离 | `config/environment.example:8,11,14,17`（KMA_SOCKET_PATH / KMA_DATABASE_PATH / KMA_LOG_LEVEL / KMA_RETRIEVE_DEADLINE_MS）；`outbox.*`、`deadline.default_ms`、`embedding.model` 无对应项 | 命名体系不同（KMA_* vs 冻结 toml 点分键），且仅 4 项有近似等价，其余 4 项缺失 |
| 环境变量覆盖（KYLIN_MEMORY_SOCKET / _DB / _LOG_LEVEL） | ⚠️ 偏离 | 冻结为 `KYLIN_MEMORY_*`，实际模板为 `KMA_*`（`config/environment.example:8,11,14`） | 环境变量命名不一致 |
| 配置是否被代码消费 | ⚠️ 偏离 | `memory-service/embedding/server.py:18,145-146`（socket 路径经 argparse `--socket`，默认 `/tmp/kylin-memory-embed.sock`）；memory-service 代码仅 `os.environ.get("KYLIN_L2")` 用于测试开关（`tests/test_embedding_service_real.py:30`） | 模板与代码未接线；代码走 CLI 参数而非 config 文件/环境变量 |

---

## 三、未覆盖项汇总

| # | 冻结对象 | 状态 |
|---|---|---|
| 1 | 核心表 5 张 + 索引 4 项 + FTS5（FRZ-DB-001） | 全部未实现（GAP-DB-001/003/004） |
| 2 | Alembic 迁移工具链与命名约定 | 未实现；README 目录示意用 `.sql`，与冻结 `.py` 约定冲突 |
| 3 | 失败路由 5 条路径（FRZ-DB-002） | 除 embedding 局部降级外全部未实现 |
| 4 | 降级层级 L0-L3+Fatal（FRZ-DB-003） | 未实现 |
| 5 | Dead Letter 策略（FRZ-DB-004） | 未实现（GAP-DB-002） |
| 6 | 幂等缓存表与 TTL 写入（FRZ-DB-005） | 未实现（仅字段/内存键） |
| 7 | config.toml + 8 配置项 + KYLIN_MEMORY_* 覆盖（FRZ-CFG-001） | 偏离（env 模板 KMA_*，且未接线） |

---

## 四、风险点

1. **R-1（进度风险，非缺陷）**：DB 层完全空白，D4-D 需从零启动 Alembic + 5 表 + FTS5 + Outbox + 幂等缓存，工作量大。当前无 `sqlalchemy`/`alembic` 依赖声明（`memory-service/requirements.txt:5-9`），落地迁移前需先补齐依赖。

2. **R-2（命名不一致）**：`migrations/README.md:24-27` 的未来目录示意为 `001_initial_schema.sql`（SQL 文件），而冻结文档 §4.1 约定为 Alembic + `YYYYMMDD_<description>.py`（`001_initial_schema.py`）。README 与冻结约定冲突，D4-D 启动前应校正 README，避免误导后续实现。

3. **R-3（配置命名漂移）**：冻结环境变量覆盖为 `KYLIN_MEMORY_*`，实际模板为 `KMA_*`（且 `AGENTS.md` 用 `KMA_SOCKET_PATH`），冻结为 `config.toml` 点分键。三方命名体系不一致，D4-D 实现配置加载器前需先裁定「以冻结文档为准」还是「以现有模板为准」，否则会导致配置项对不上冻结审查。

4. **R-4（降级语义边界混淆）**：embedding 层 `degraded`（`embedding_service.py:254-271`）与冻结的 L0-L3 系统级降级同名但语义不同。后续做失败路由实现与审查时，须明确区分「provider 局部降级」与「FRZ-DB-003 系统级降级」，避免把 embedding 局部降级误当作 L1/L2 已实现。

5. **R-5（证据诚实）**：本报告所有「未实现」均与冻结文档 GAP-DB-001~004「设计冻结，D4-D 实现」一致，属预期缺口而非返工项。切勿在 D4-D 落地前把「设计冻结文档」当作「已实现证据」用于 L0/L2 举证。

---

## 五、证据索引

| 证据文件 | 关键行 | 用途 |
|---|---|---|
| `migrations/README.md` | 19、24-27 | 证明迁移目录无生产实现、且 README 目录示意与冻结命名冲突 |
| `memory-service/requirements.txt` | 5-9 | 证明无 SQLAlchemy/Alembic 依赖 |
| `memory-service/README.md` | 44-52、61-73 | 证明当前仅 D5 embedding 链路，memory/retrieval 为未来目录 |
| `memory-service/embedding/embedding_service.py` | 184-187、254-271 | 证明 embedding 局部降级（非 DB 失败路由） |
| `memory-service/pipeline/schemas.py` | 146 | 证明 idempotency_key 仅字段级 |
| `memory-service/pipeline/fingerprint.py` | 58-66 | 证明内存级业务去重键 |
| `config/environment.example` | 8、11、14、17 | 证明配置为 KMA_* 环境变量模板，非 config.toml |
| `config/README.md` | 9 | 证明「仅示例配置模板，未含生产配置」 |
| `memory-service/embedding/server.py` | 18、145-146 | 证明 socket 路径走 argparse --socket，未消费 config 模板 |
| `scripts/d2c_evidence_collector.sh` 等 | 74/80/84（DB_PATH 指向官方库） | 证明 scripts 中 `sqlite3` 仅读官方 `kylin_aiassistant_database.db` RECORD 表，非自研冻结 Schema |
