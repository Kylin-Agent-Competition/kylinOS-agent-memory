# D4D 开发报告：IPC Gateway / 数据库层 / Outbox+部署骨架

- 任务卡：`docs/day10/01_task_card.md`（D4D，Day10-D）｜分支：`feat/d4d-ipc-db-outbox`｜基线 Commit：`2b8bed7`（main，PR #47）
- 对照文档版本：IPC 冻结 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-001~007，已签署）；DB 需求 v1.3 `D4_DB_INITIAL_REQUIREMENTS_20260817.md`（FRZ-DB-001~005/FRZ-CFG-001/ADR-005/006/007，已签署）；部署冻结 `D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`；[02 §2.1] 技术栈基线

## 修改文件清单（新增 / 修改）

**新增**
- `docs/day10/01_task_card.md` — 任务卡（范围/契约/验收）
- `memory-service/config.py` — 配置加载器（FRZ-CFG-001 8 键 + KYLIN_MEMORY_* 覆盖 + fail-fast + CLI>env>file）
- `memory-service/logging_setup.py` — 日志（~/.local/state/kylin-memory/，禁止正文/PII）
- `memory-service/db/__init__.py` / `schema.py` / `engine.py` / `repositories.py` / `uow.py` — 数据层
- `memory-service/outbox/__init__.py` / `worker.py` — Outbox Worker
- `memory-service/gateway/__init__.py` / `protocol.py` / `registry.py` / `handlers.py` / `server.py` — IPC Gateway
- `memory-service/app.py` — 组装入口
- `migrations/alembic.ini` / `env.py` / `versions/001_initial_schema.py` — Alembic 工具链 + 基线迁移
- `packaging/systemd/kylin-memory.service` — 正式 systemd --user unit（冻结 §1.2 骨架）
- `memory-service/tests/test_{config,db,gateway_protocol,gateway_server,migrations,outbox_worker}_d4d.py` — 65 个测试

**修改**
- `config/environment.example` — KMA_* → KYLIN_MEMORY_*（R-3 定案）
- `migrations/README.md` — .sql 示意 → Alembic .py 示意（R-2 定案）
- `memory-service/requirements.txt` — 补 sqlalchemy/alembic/tomli

## 契约变化（Schema / IPC / DB / 错误码）

- IPC：**零偏离**。新 Gateway 按 FRZ-IPC-001~007 实现：64KB 上限、5 错误码（含 TIMEOUT）、protocol_version "1.0"、请求 7 字段/响应 6 字段、路由 echo/health/memory.retrieve/store(UNSUPPORTED)。
- DB：按 FRZ-DB-001 逐列实现：5 表 + 4 冻结索引 + 1 辅助索引 + FTS5 memory_fts + 4 触发器；idempotency_cache 复合 PK（ADR-006）；迁移命名 001_initial_schema.py（ADR-007）。
- 配置：FRZ-CFG-001 8 键全量映射。
- **实现偏差登记（非契约变更）**：FTS5 同步触发器统一用 `DELETE FROM memory_fts WHERE rowid = old.id` 替代官方 'delete' 命令——实测 SQLite 3.37 触发器内 'delete' 命令对 JSON 中文内容抛 SQL logic error（`scripts/_repro_fts*.sh` 验证，方式 B/C 全通过）；语义与冻结文档 §2.4 一致（软删除后 MATCH 不再命中）。

## 设计说明（关键决策与依据）

- **Gateway 独立实现**：新建 `gateway/protocol.py` 按冻结实现，不复用 `embedding/protocol.py`（其 4MiB/独立错误码域偏离 ALIGN-001~005 保持登记，不阻塞新代码）。
- **UoW + 单写锁**：业务写 + Outbox 入队同一事务（FR-DB-003）；进程级 RLock 串行化所有写（FR-DB-004 单写者模型）；busy_timeout 到期捕获 → DatabaseLockedError → 调用方降级（FR-DB-003）。
- **幂等**：execute_idempotent 同事务执行 + 写缓存；并发冲突由复合 PK 兜底回查（附录 A）。
- **Outbox Worker**：独立线程 + 单写锁；consumer 注入点（Vector 接入 R-9 未确认前为 None → 真实失败路径退避/DL，不假装成功）；每轮顺带清理过期幂等缓存（LIMIT 100 原生 SQL）。
- **迁移 env.py**：URL 从 KYLIN_MEMORY_DB/默认路径动态读取，alembic.ini 不写死路径。

## 测试结果（L0/L1）

- L0：`python3 -m py_compile` 全部模块 OK（含 migrations/env.py、versions/001_initial_schema.py）。
- L1：`pytest memory-service/tests/test_*_d4d.py` → **65 passed in 12.9s**（WSL2 Python 3.10.12；pydantic 2.13.4 / sqlalchemy 2.0.51 / alembic 1.19.1）。
- 覆盖：协议编解码/64KB/错误码/版本校验、配置 8 键/env 覆盖/fail-fast、迁移 upgrade/downgrade/往返、5 表 CRUD、UoW 原子回滚、幂等命中/过期/并发冲突、Outbox 成功/退避/DL/清理、Gateway 端到端（echo/health/retrieve/store/未知方法/协议错误/TIMEOUT/停止拒绝）、FTS5 中文命中与软删除同步、乐观锁冲突、用户隔离。
- 端到端冒烟：`python -m app --socket /tmp/kylin-memory-smoke.sock --db /tmp/kylin-memory-smoke.db --no-outbox` → health/echo/retrieve/store/unknown 全通过；`--db` 接线已生效。
- 修复过程（Bug）：FTS5 'delete' 命令兼容性、SQLAlchemy 2.0 `Select.count()` 移除、`Delete.limit()` 不存在、`sqlite_where` 需 text()、`--db` 未接线、测试 PRAGMA 键序——均已修复并补测试。

## 待麒麟宿主 L2 验证项（人工操作清单，未执行）

1. VM 上 `alembic upgrade head` + `.schema` 与冻结文档逐列对照（FRZ-DB-001 验收）。
2. VM 上安装 `packaging/systemd/kylin-memory.service`：`systemctl --user daemon-reload && enable --now` → 启动/重启/日志/回退（部署冻结 §1.2；正式发行环境 systemd 测试未执行前不得写"成品通过"）。
3. FTS5 中文检索（unicode61 完整 token）+ 软删除 MATCH 不再命中（VM SQLite 版本差异复核）。
4. busy_timeout 注入持锁 → 断言超时降级而非无限阻塞（R-8 语义边界）。
5. UDS 断开/超时 → 空上下文（FR-FB-001 路径 1/2）。
6. Vector 接入确认（R-9，附录 C）后接线 Outbox consumer，再验 Embedding→Vector→DELETE 闭环。

## 技术债变化

- 新增登记建议：**TD-D4D-001**：Outbox consumer 未接线（Vector 接入 R-9 待确认），Worker 对无 consumer 事件按真实失败退避/DL；代码注释已引用（`outbox/worker.py`）。接线后关闭。
- 既有保持：TD-IPC-002/003/004、ALIGN-001~005（本任务不处理，保持登记）。

## 风险与回滚方式

- **风险**：FTS5 触发器用 rowid DELETE 而非官方 'delete' 命令，与冻结文档 SQL 示意有实现差异——已在报告中登记，语义等价且经测试验证；如需完全对齐官方命令，麒麟 VM（更新版 SQLite）可复核后走 ADR 调整。
- **回滚**：迁移 `alembic downgrade base` 完整可逆（测试覆盖往返）；代码回滚 = `git revert`（分支独立，未触碰 main 与其他轨道代码）。
