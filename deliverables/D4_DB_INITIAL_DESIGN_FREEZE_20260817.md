# 数据库初版设计冻结声明

> ⚠️ **本声明尚未正式生效，待 E（谢嘉然）签署**：R-5/R-6/R-7 已由 D 决策采纳（ADR-005/006/007，2026-08-17，方案 A；Reviewer 指派 E），冻结文档 §2.2.5/§4.1 已回写；冻结人（周子腾，D）签署 + Reviewer E（谢嘉然）签署后转为正式冻结。文档基线 Commit `b29c6b8`（仅指本声明关联的文档基线，**非代码基线**——自研库实现零启动，见 §二.3）。

- **版本**：v1.3（2026-08-17，按 v1.2 审查报告整改 + ADR-005/006/007 采纳）
- **冻结日期**：2026-08-17
- **冻结人**：周子腾（D）
- **冻结性质**：数据库初版**设计层**冻结（草案）；实现未启动，D4-D 实施
- **依据文档**：
  - `deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`（设计冻结：FRZ-DB-001~005、Migration 策略、FRZ-CFG-001、GAP-DB-001~004）
  - `deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md`（**v1.3**，需求文档：FR/FR-FB/附录 A-D）
  - `docs/adr/005-db-error-code-envelope.md`、`006-db-idempotency-primary-key.md`、`007-db-migration-baseline-naming.md`（R-5/6/7 已采纳）
  - `deliverables/D4_DB_REQUIREMENTS_COMPLIANCE_AUDIT_20260817.md`（opencode 符合性审查）
  - 人工审查报告 ×2（需求 v1.1→v1.2 整改 15 项；本声明 v1.2→v1.3 整改 11 项）
  - `deliverables/D4_DB_SCHEMA_V53_COMPARISON_20260817.md`（5.0.3 官方库对照）
  - `docs/baseline/v2-20260816/02_kylin_vm_environment_baseline_20260816.md`（聊天优先、原文隔离原则）

---

## 一、冻结对象清单

> 状态说明：✅ = 正式冻结（含已采纳 ADR 支撑项）；⏳ = **条件冻结**（依赖项未批准，不得据此写 DDL）。

| 编号 | 冻结对象 | 定义位置 | 状态 | 依赖 |
|------|---------|---------|:---:|------|
| FRZ-DB-001 | 核心表 5 张 + 4 项索引 + FTS5 `memory_fts` | 冻结文档 §2.2-2.4；需求 v1.3 §二 FR-DB-001 | ✅ | R-6 已采纳（ADR-006，复合 PK） |
| FRZ-DB-002 | 失败路由 5 条路径 | 冻结文档 §3.1；需求 v1.3 §三 FR-FB-001（映射表） | ✅ | R-5 已采纳（ADR-005，冻结枚举/envelope） |
| FRZ-DB-003 | 降级层级 L0-L3+Fatal | 冻结文档 §3.2；需求 v1.3 §三 FR-FB-001 | ✅ | 无 |
| FRZ-DB-004 | Dead Letter 策略 | 冻结文档 §3.4；需求 v1.3 §三 FR-FB-003 + §二 FR-DB-004 | ✅ | 无 |
| FRZ-DB-005 | 幂等写入策略 | 冻结文档 §3.5；需求 v1.3 附录 A | ✅ | R-6 已采纳（ADR-006） |
| FRZ-CFG-001 | 配置 8 键 + 默认值/校验 + `KYLIN_MEMORY_*` 覆盖 | 冻结文档 §5；需求 v1.3 §二 FR-DB-006 | ✅ | R-3 已定案 |
| Migration 策略 | Alembic + SQLAlchemy 2.0 Core + downgrade + 禁止项 | 冻结文档 §4；需求 v1.3 §二 FR-DB-002 | ✅ | R-7 已采纳（ADR-007，基线命名） |

**冻结效力**：自签署之日起全部冻结对象生效；任何变更须走 ADR + Gate 流程。

---

## 二、审查结论摘要

### 2.1 符合性确认（摘要；明细见各审查报告）

- opencode 符合性审查：9 类符合项确认，6 处缺陷在需求 v1.1 修正；
- 人工审查（需求）：15 项问题（5 矛盾 + 4 重复 + 6 难维护）在需求 v1.2 整改——幂等/Outbox/降级合并为附录 A/B + 单一映射表，配置校验/告警接口/验收断言/聊天主链路边界补齐；
- 人工审查（本声明）：11 项问题（5 矛盾 + 2 重复 + 4 难维护）在本版整改（见 §三 变更记录）。

### 2.2 实现尚未启动（属预期，非冻结阻塞）

`kylin_memory.db` 零实现（无建表/迁移/DAO/Outbox/幂等缓存/FTS5），与冻结文档 GAP-DB-001~004「设计冻结，D4-D 实现」一致。本声明**不是**实现证据；实现证据须由 D4-D 以 L0（WSL2 单测）+ L1（集成）+ L2（麒麟 VM）闭环。

### 2.3 文档基线 Commit

`b29c6b8`（feature/d4-gate0-review-freeze）仅为本声明所关联**文档提交**；代码基线待 D4-D 首个实现提交建立。

---

## 三、v1.2 → v1.3 整改记录（本版）

| 审查项 | 整改 |
|--------|------|
| 1.1 冻结状态与阻断项冲突 | FRZ-DB-001/002/005/Migration 改为 ⏳ 条件冻结，与 R-5/R-6/R-7 关联（见 §一） |
| 1.2 冻结人「待确认」vs 标题 | 文档顶部标注 DRAFT；签署区冻结人结论改为「待签署确认」（见 §六） |
| 1.3 FRZ-DB-004 编号混淆 | 精确引用：需求 v1.2 §二 FR-DB-004（Outbox Worker，含告警接口定义） |
| 1.4 R-8 矛盾 | 冻结**语义边界**：busy_timeout 必须设置、到期必须触发降级（纳入 L2 验收）；数值本身不冻结（见 §四 R-8） |
| 1.5 基线 Commit 歧义 | 顶部 + §二.3 明确「文档基线 Commit，非代码基线」 |
| 2.1 §二/§四 重复 | §二 只留摘要，明细仅在 §四 裁定表 |
| 2.2 附录不可见 | 本声明附关键附录（映射表 + 幂等流程 + Outbox 流程，来源需求 v1.2，见附录 A/B/C） |
| 3.1 ADR 责任/时间缺失 | §五 补充 ADR 责任人、目标日期、阻塞范围、fallback |
| 3.2 Reviewer 未签即发布 | 顶部标注 DRAFT，Reviewer 签署后生效 |
| 3.3 证据登记指引模糊 | §七 给出 index.yaml 登记模板与示例 |
| 3.4 错误码变更路径不清 | §四 R-5 + 变更控制明确：错误码变更一律走 IPC 冻结 ADR（FRZ-IPC-002），本声明引用其结论 |

---

## 四、裁定项状态（R-2~R-8）

| 编号 | 项 | 结论 | 状态 |
|------|-----|------|------|
| R-2 | migrations/README `.sql` vs `.py` | 以冻结为准：README 改 `.py` 示意 | ✅ 已定案（D4-D 开工时校正） |
| R-3 | 配置命名 `KMA_*` vs `KYLIN_MEMORY_*` | 以冻结为准：模板改 `KYLIN_MEMORY_*` 并接线代码 | ✅ 已定案 |
| R-4 | embedding 局部 `degraded` vs 系统级降级 | 分层命名：provider 局部 vs 系统读取侧 L0-L3；写入侧走 Outbox | ✅ 已定案 |
| R-5 | **DB 对外错误码与 envelope 域** | 以 IPC 冻结契约为准（5 枚举 + `status/data/server_ts`）；`ERR_*`/`ok/result/error` 按 ALIGN-002/003 冻结后对齐；错误码变更走 IPC 冻结 ADR（FRZ-IPC-002） | ✅ 已采纳（ADR-005，D 决策方案 A；Reviewer E 待签） |
| R-6 | **idempotency_cache 主键** | 复合 PK `(user_id, session_id, idempotency_key)`；DDL 按此实现 | ✅ 已采纳（ADR-006，D 决策方案 A；Reviewer E 待签；冻结 §2.2.5 已回写） |
| R-7 | **迁移基线命名** | 基线 `001_initial_schema.py`，后续 `YYYYMMDD_<desc>.py` | ✅ 已采纳（ADR-007，D 决策方案 A；Reviewer E 待签；冻结 §4.1 已回写） |
| R-8 | WAL/busy_timeout/单写多读 | 数值由 D4-D 定（不冻结）；**语义边界冻结**：busy_timeout 必须设置、到期必须触发降级（不无限阻塞）→ 纳入 L2 验收（需求 v1.2 §五） | ✅ 已定案（语义边界冻结） |

---

## 五、阻断项 ADR 安排（审查 3.1 整改）

| 项 | 决策 | 状态 |
|----|------|------|
| R-5 | ADR-005 方案 A：DB 层对外按 IPC 冻结契约（5 枚举 + status/data/server_ts） | ✅ 已采纳（D 决策 2026-08-17；Reviewer E 待签） |
| R-6 | ADR-006 方案 A：复合 PK (user_id, session_id, idempotency_key) | ✅ 已采纳（D 决策 2026-08-17；Reviewer E 待签；冻结 §2.2.5 已回写） |
| R-7 | ADR-007 方案 A：基线 001_initial_schema.py + 后续 YYYYMMDD_<desc>.py | ✅ 已采纳（D 决策 2026-08-17；Reviewer E 待签；冻结 §4.1 已回写） |

> 三项阻断项已解除：D4-D 可据需求 v1.3 与 ADR-005/006/007 直接实现（migrations 基线、复合主键 DDL、错误码/envelope 映射）；Reviewer E（谢嘉然）签署为正式手续。
> 不受影响、**可先行开工**：migrations 目录与 alembic.ini 骨架、配置加载器（FR-DB-006）、连接管理（FR-DB-003）、Outbox Worker 骨架（FR-DB-004）。

---

## 六、签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 冻结人 | 周子腾（D） | 2026-08-17 | 确认冻结（ADR-005/006/007 已采纳） |
| Reviewer 1 | E（谢嘉然，待签） | | 待签署 |
| Reviewer 2 | 待填写 | | 待签署 |

> 本声明自冻结人确认 + Reviewer E（谢嘉然）签署后转为正式冻结（R-5/6/7 已采纳，阻断已解除）。

---

## 七、证据登记指引（审查 3.3 整改）

签署生效后登记 `evidence/index.yaml`，模板：

```yaml
- id: "DB-FREEZE-001"
  task_id: "D4-DB-FREEZE"
  description: "数据库初版设计冻结（FRZ-DB-001~005 + FRZ-CFG-001 + Migration 策略）"
  status: "DESIGN_FROZEN"            # 或 PARTIAL_FROZEN（R 项未批时）
  evidence_level: "E3"               # 设计冻结；实现证据待 D4-D L0/L2
  source: "deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md"
  date: "2026-08-17"
  reviewer: "谢嘉然（E）"
  limitations: "实现零启动；R-5/R-6/R-7 待 ADR/Gate 批准；冻结 ≠ 实现证据"
  checksum_sha256: "<文件 SHA-256>"
```

---

## 附录 A：读取侧失败路径 ↔ 降级层级映射表（来源：需求 v1.2 §三 FR-FB-001）

| # | 路径 | 触发 | L 层级 | 降级行为 | 聊天继续 |
|---|------|------|:---:|---------|:---:|
| 1 | UDS 连接失败 | 无法连到 memory.sock | L2 | 空 context + 日志 | ✅ |
| 2 | UDS 超时 | 检索超过 `retrieve.deadline_ms`(150) | L1 | 空 context + 日志 | ✅ |
| 3 | SQLite 读取失败 | 查询异常/损坏 | L3 | 空 context + 告警 | ✅ |
| 4 | Embedding 失败 | Provider 失败 | L2（读取侧） | 纯关键词检索（FTS5）或空 context | ✅ |
| 5 | Vector 检索失败 | 检索异常 | L2 | 空 context + 日志 | ✅ |
| — | Fatal | 任何降级都失败 | Fatal | 聊天继续（零上下文） | ✅ |

> L0 = 正常；L1 = UDS 超时；L2 = 服务不可用（连接失败/Embedding/Vector 检索）；L3 = SQLite 损坏。**Vector 索引写入失败属写入侧（附录 C），不映射 L 层级。**

## 附录 B：幂等写入流程（来源：需求 v1.2 附录 A）

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

## 附录 C：Outbox 失败路由流程（来源：需求 v1.2 附录 B）

```
1. 业务写入（TurnFinalizedEvent / memory / forget 审计）→ SQLite INSERT
2. 同事务 Outbox INSERT（aggregate_type, aggregate_id, event_type, payload,
                          attempts=0, next_retry_at=now, last_error=NULL）
3. Worker 轮询（每 outbox.poll_interval_s 秒）：
     SELECT * FROM outbox WHERE next_retry_at <= now AND attempts <= outbox.max_retries
     ORDER BY next_retry_at
4. 逐条处理：
   4a. Embedding 成功 → Vector INSERT 成功 → Outbox DELETE（事件完成）
   4b. Embedding/Vector 失败 → attempts += 1
         → next_retry_at = now + 2^attempts * 30s（指数退避）
         → last_error = 错误摘要（不含 PII）
   4c. attempts > outbox.max_retries → Dead Letter：
         → 保留记录（不 DELETE），next_retry_at = NULL
         → ERROR 日志告警（按需求 v1.2 FR-DB-004 接口：last_error + ERROR 日志 + attempts 去重消噪）
```
