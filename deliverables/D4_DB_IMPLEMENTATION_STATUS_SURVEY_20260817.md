# 数据库施工状态全面普查报告

- **普查日期**：2026-08-17
- **普查范围**：`E:\Kylin-memory-dev\Unified-Json-format` 全仓（`memory-service/`、`os-agent-integration/`、`scripts/`、`packaging/`、`config/`、`cpp-bridge/`、`memory-client/`、`migrations/`、`Kylin-runtime-knowledge/`、`tests/`、`evidence/`、`deliverables/`），排除 `.git`、`__pycache__`、`node_modules`、`dist-info`
- **方法**：grep 扫描 Python/C++/Shell/配置/文档中的数据库痕迹（`import sqlite3/sqlalchemy/alembic/aiosqlite`、`sqlite3.connect`、`CREATE TABLE / VIRTUAL TABLE / USING fts5 / executemany`、`sqlite3.h / sqlite3_open / sqlite3_exec`、`sqlite3 <db>`、`.db` 路径引用），并枚举实际存在的 `*.db / *.sqlite / *.sqlite3` 数据文件与 `migrations/` 内容
- **证据诚实原则**：只写代码中实际存在的内容并给 file:line；未找到即标「未实现/未找到」；严格区分「模块真实建表」与「脚本/文档仅引用路径」；不把设计/冻结文档描述当实现

---

## 一、核心结论

1. **自研数据库（`kylin_memory.db`）整体未实现，施工阶段 = 未启动**。全仓自研 `.py` 无任何 `import sqlite3`/`sqlalchemy`/`alembic`/`aiosqlite`（grep 零命中），无 `CREATE TABLE`/`CREATE VIRTUAL TABLE`/`CREATE INDEX`/`CREATE TRIGGER`/`USING fts5`/`executemany`，无 `alembic.ini`，无任何 `*.sql` 迁移文件。`migrations/` 仅一个 README，明确声明「仅建立目录和职责边界，尚无生产实现」（`migrations/README.md:19`）。冻结文档定义的 5 张核心表（conversations/turns/memory_entries/outbox/idempotency_cache）+ FTS5 `memory_fts` 均停留在设计层。

2. **官方库的读写只存在于「只读参考代码」与「只读探测脚本」两层，本仓库无任何对官方库的写入**：
   - 官方向量引擎 `kylin-ai-vector-engine`（vendor C++ 源码，Milvus Lite fork）用 SQLiteCpp 真实建表/读写其 `default.db` —— 属 vendor 代码，非本项目自研，且按 AGENTS.md 为 reference-only。
   - 官方聊天库 `kylin_aiassistant_database.db` 仅被本项目 `scripts/d2c_*` 三脚本以 `sqlite3` CLI **只读 SELECT**（`RECORD` 表），用于证据采集/验证，非生产读写。
   - 官方 `knowledgebase_database.db` 仅在 kaiming 打包 yaml 与文档中被引用路径，无任何读写代码。

3. **真实存在的 `.db` 数据文件共 3 个，全部位于 `Kylin-runtime-knowledge/kylin-ai-runtime/configs/`**，为 vendor 运行时配置数据（intent.db 5.5MB、knowledge_base.db 4KB、vector.db 33.6MB），非本项目产物，且被 `.gitignore`（`*.db`）排除。

4. **整体施工阶段判断**：数据库层处于「契约已冻结、实现零启动」状态。本项目（memory-service/cpp-bridge/memory-client）三层的 DB 实现均为空白；唯一"动过数据库"的代码是（a）vendor 向量引擎源码（非我们写的），（b）evidence/scripts 中的只读探测脚本。自研 `kylin_memory.db` 的建表/读写/迁移工作尚未开工（对应冻结文档 GAP-DB-001~004，标注「D4-D 实现」）。

---

## 二、逐模块状态表

> 状态：✅ 已实现 / 🟡 部分 / ❌ 未实现 / 🔍 仅引用（路径或设计文档引用，无实现代码）

| 模块/组件 | 数据库实现类型 | 状态 | 证据 file:line | 说明 |
|---|---|---|---|---|
| `memory-service/`（自研核心） | 无 | ❌ 未实现 | 全仓 `.py` 无 `import sqlite3`/`sqlalchemy`/`alembic`（grep 零命中）；`memory-service/README.md:44-52` 仅实现 Embedding 最小链路，`memory-service/README.md:61-73` 标注 memory/retrieval 为「未来主要目录」；`memory-service/requirements.txt:5-9` 仅 pydantic/pytest/pybind11，无 DB 依赖 | 无建表、无读写、无迁移；Pydantic 模型仅做事件校验（`pipeline/schemas.py`），不落库 |
| `migrations/` | 无 | ❌ 未实现 | `migrations/README.md:19`（「仅建立目录和职责边界，尚无生产实现」）；目录下仅 `README.md`，无 `.py`/`.sql`；全仓无 `alembic.ini`、无 `*.sql` | 迁移目录已建、无任何迁移脚本 |
| `cpp-bridge/` | 无 | ❌ 未实现 | 全仓 C++ 无 `sqlite3.h`/`sqlite3_open`/`sqlite3_exec`（grep 零命中）；`cpp-bridge/src/` 仅 `embedding_bridge.cpp`/`py_module.cpp`（embedding ABI 桥） | 桥接层不触碰 SQLite |
| `memory-client/` | 无 | ❌ 未实现 | `memory-client/` 下仅 `README.md`（无源码） | 模块空壳 |
| `os-agent-integration/` | 仅路径引用 | 🔍 仅引用 | `os-agent-integration/D1_OS_Agent_调用链与Hook_Spike_任务卡.md:38`、`os-agent-integration/D2_C_宿主实验执行手册.md:54,137`（引用 `~/.config/kylin-aiassistant/kylin_aiassistant_database.db` 与 RECORD 表） | echo 组件走 UDS，不读写 DB；仅实验手册/任务卡引用官方库路径 |
| `scripts/d2c_evidence_collector.sh` | 官方库只读 | 🟡 部分（只读 SELECT） | `scripts/d2c_evidence_collector.sh:80`（`DB_PATH=.../kylin_aiassistant_database.db`） | 只读官方聊天库，采集证据；非生产建表/读写 |
| `scripts/d2c_prechat_context_probe.sh` | 官方库只读 | 🟡 部分（只读 SELECT） | `scripts/d2c_prechat_context_probe.sh:84`（DB_PATH）、`:466-467`（`sqlite3 "${DB_PATH}" "SELECT rowid,sessionID,... FROM RECORD WHERE rowid>... AND message LIKE ..."`） | 只读 RECORD 表验证 Hook 上下文污染 |
| `scripts/d2c_postturn_isend_counter.sh` | 官方库只读 | 🟡 部分（只读 SELECT） | `scripts/d2c_postturn_isend_counter.sh:74`（DB_PATH）、`:407-409`（`sqlite3 ... "SELECT MIN/MAX(rowid), COUNT(*) FROM RECORD"`） | 只读 RECORD 表计数 |
| `scripts/check_kylin_environment.sh` | 仅 CLI 存在性检查 | 🔍 仅引用 | `scripts/check_kylin_environment.sh:91`（`check_cmd sqlite3`） | 检查 VM 是否装有 `sqlite3` 命令，不读写库 |
| `scripts/run_d2_vector_smoke.sh` | 仅路径引用 | 🔍 仅引用 | `scripts/run_d2_vector_smoke.sh:18`（`DEFAULT_DATABASE_RELATIVE=".local/share/kylin-ai-vector-engine/default.db"`） | 引用官方向量引擎 default.db 路径做路径校验 |
| `scripts/verify_repository_baseline.sh` | 无（安全扫描） | 🔍 仅引用 | `scripts/verify_repository_baseline.sh:139`（`DANGEROUS_EXTS="... db sqlite sqlite3"`） | 把 `.db/.sqlite` 列为禁止提交的敏感扩展名 |
| `config/environment.example` | 仅配置占位 | 🔍 仅引用 | `config/environment.example:11`（`KMA_DATABASE_PATH=` 空值） | 声明自研 SQLite 路径变量，值为空、未被任何代码消费 |
| `packaging/` | 无 | ❌ 未实现 | 未发现 `.db`/sqlite 相关代码 | 未扫描到 DB 实现 |
| `Kylin-runtime-knowledge/kylin-ai-vector-engine/src/`（vendor C++，Milvus Lite fork） | 自研 vendor SQLiteCpp 读写 | ✅ 已实现（vendor） | `src/milvus_proxy.cpp:52-63`（`CREATE TABLE IF NOT EXISTS t_app_db_path(app_id,db_file,encrypt)` + `PRAGMA key`）、`src/collection_meta.cpp:80-82`（`CREATE TABLE IF NOT EXISTS {collection_meta}`）、`src/collection_data.cpp:40`（每 collection `CREATE TABLE IF NOT EXISTS "{name}"`）、`src/storage.cpp:65-73`（`SQLite::Database` OPEN_CREATE + `PRAGMA key`） | vendor 官方向量引擎用 SQLiteCpp（`#include "SQLiteCpp/Database.h"` `collection_meta.h:50`）真实建表读写其向量库 `default.db`；reference-only，不可改 |
| `Kylin-runtime-knowledge/kylin-ai-runtime/configs/` | vendor 数据文件 | 🔍 仅引用（含真实 .db） | `.../intent-recognition/intent.db`（5,591,040 字节）、`.../knowledge-base/knowledge_base.db`（4,096 字节）、`.../knowledge-base/vector.db`（33,640,448 字节） | 3 个真实 SQLite 数据文件，为 vendor 运行时配置数据；被 `.gitignore:34`（`*.db`）排除 |
| `Kylin-runtime-knowledge/kylin-aiassistant/` | 仅路径引用 | 🔍 仅引用 | `kylin-aiassistant/kaiming/cn.kylin.kylin-aiassistant.km.yaml:59`（`$HOME/.config/kylin-aiassistant/knowledgebase_database.db`）、`kylin-aiassistant/web/src/pages/config/sections/MemorySection.tsx:13,32`（`{ value: 'sqlite', label: 'SQLite' }` 配置项） | 仅打包声明与前端配置枚举引用官方知识库路径；无本仓库读写代码 |

---

## 三、自研库 vs 官方库区分

| 数据库 | 归属 | 路径 | 本仓库读写情况 | 证据 |
|---|---|---|---|---|
| **自研库 `kylin_memory.db`** | 本项目（我们写） | 冻结文档设计为 `~/.local/share/kylin-memory/kylin_memory.db`（`deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md:103,305`）；`config/environment.example:11` 为 `KMA_DATABASE_PATH=` 空占位 | **零实现**：无建表、无读写、无迁移 | 全仓无 `CREATE TABLE conversations/turns/memory_entries/outbox/idempotency_cache`；无 `memory_fts`/fts5 |
| **官方聊天库 `kylin_aiassistant_database.db`** | 官方 AI 助手（C++ Qt，`msgpane.cpp` 生产读写） | `~/.config/kylin-aiassistant/kylin_aiassistant_database.db` | 本项目**只读 SELECT**（`RECORD` 表），用于 d2c 证据采集/验证；**无写入** | `scripts/d2c_prechat_context_probe.sh:466-467`、`scripts/d2c_postturn_isend_counter.sh:407-409`、`scripts/d2c_evidence_collector.sh:80` |
| **官方知识库 `knowledgebase_database.db`** | 官方（5.0.3 新增，`KNOWLEDGEBASE` 表） | `~/.config/kylin-aiassistant/knowledgebase_database.db` | **仅路径引用**，无读写代码 | `Kylin-runtime-knowledge/kylin-aiassistant/kaiming/...km.yaml:59`；`deliverables/D4_DB_SCHEMA_V53_COMPARISON_20260817.md:26` |
| **官方向量引擎库 `default.db`** | 官方 `kylin-ai-vector-engine`（vendor） | `~/.local/share/kylin-ai-vector-engine/default.db` | vendor 源码用 SQLiteCpp **建表读写**（`t_app_db_path`/`collection_meta`/collection 表，`PRAGMA key` 加密） | `Kylin-runtime-knowledge/kylin-ai-vector-engine/src/milvus_proxy.cpp:52-63`、`collection_meta.cpp:80-82`、`collection_data.cpp:40`、`storage.cpp:65-73` |

**结论**：
- 本项目自研代码 **不写官方库、也不读官方库的生产数据**（仅脚本只读 RECORD 表做证据核对）。
- 自研库 `kylin_memory.db` 与官方库完全隔离（独立 SQLite 文件），设计上「不写入官方 `kylin_aiassistant_database.db`」（`deliverables/D4_DB_SCHEMA_V53_COMPARISON_20260817.md:68`），但自研库本身尚未实现。
- 唯一"会建表"的代码是 vendor 向量引擎（SQLiteCpp），属 reference-only，**不能作为本项目数据库施工证据**。

---

## 四、migrations/ 施工状态

| 项目 | 状态 | 证据 |
|---|---|---|
| 迁移目录是否建立 | ✅ 已建 | `migrations/` 目录存在，含 `README.md` |
| 迁移脚本（`.py`/`.sql`） | ❌ 无 | `migrations/` 下仅 `README.md`；全仓无 `*.sql`、无 `001_initial_schema.*` |
| Alembic 环境 | ❌ 无 | 全仓无 `alembic.ini`、无 `alembic`/`sqlalchemy` 依赖（`memory-service/requirements.txt:5-9` 无相关声明） |
| 命名约定 | ⚠️ 未定/冲突 | `migrations/README.md:24-27` 未来目录示意用 `001_initial_schema.sql`；而冻结文档 §4.1 约定 Alembic + `YYYYMMDD_<description>.py`。两者不一致（沿用 `D4_DB_INITIAL_IMPLEMENTATION_AUDIT_20260817.md:46` 结论） |
| 迁移策略（正向/回滚、禁止手动改库） | ❌ 无实现 | 无任何迁移代码，无从核验 |
| 官方说明 | — | `migrations/README.md:19` 明确「仅建立目录和职责边界，尚无生产实现」 |

---

## 五、关键风险 / 待办

1. **R-1（进度风险）**：自研 DB 层完全空白，D4-D 需从零启动（5 张核心表 + 4 索引 + FTS5 `memory_fts` + Outbox + idempotency_cache + Alembic 环境），工作量集中且未列依赖。落地前需先补 `sqlalchemy`/`alembic` 依赖声明（`memory-service/requirements.txt:5-9` 现无）。

2. **R-2（命名冲突）**：`migrations/README.md:24-27` 的目录示意用 `.sql`，冻结文档约定 Alembic `.py`（`YYYYMMDD_<description>.py`），需校正 README 或裁定约定，避免误导后续实现。

3. **R-3（配置命名漂移）**：自研库路径三方不一致 —— 冻结 `config.toml` 点分键 / 环境变量 `KYLIN_MEMORY_*` / 现有模板 `KMA_*`（`config/environment.example:8,11,14,17`），且模板未被代码消费（`memory-service/embedding/server.py` 走 argparse `--socket`）。实现配置加载器前需先裁定命名体系。

4. **R-4（证据诚实红线）**：vendor 向量引擎的 SQLiteCpp 建表代码（`Kylin-runtime-knowledge/kylin-ai-vector-engine/src/`）与 `scripts/d2c_*` 的只读 SELECT **均不可**当作「自研 kylin_memory.db 已实现」的 L0/L2 证据；自研建表/读写/迁移证据目前为零。

5. **R-5（数据文件安全）**：`Kylin-runtime-knowledge/kylin-ai-runtime/configs/` 下 3 个 `.db`（vector.db 33.6MB）虽被 `.gitignore:34` 排除，但属 vendor 运行时数据，需确保不被误提交（`scripts/verify_repository_baseline.sh:139` 已把 `db/sqlite` 列为禁止扩展名，机制在位）。

6. **待办清单**（由冻结文档 GAP-DB-001~004 推导，非本次普查新增结论）：
   - 补 SQLAlchemy/Alembic 依赖与 `alembic.ini`
   - 落 `001_initial_schema` 迁移（5 表 + 索引 + FTS5 触发器）
   - 实现 `kylin_memory.db` 的连接管理与读写 DAO
   - 实现失败路由/降级/Dead Letter/幂等缓存（对应 FRZ-DB-002~005）
   - 接线 `KMA_DATABASE_PATH`（或裁定后命名）到 memory-service 代码
