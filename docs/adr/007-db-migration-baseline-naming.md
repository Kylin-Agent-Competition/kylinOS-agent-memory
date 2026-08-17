# ADR-007：迁移基线命名 = `001_initial_schema.py`，后续迁移 `YYYYMMDD_<description>.py`（R-7）

- **状态**：✅ 已采纳（E 决策 2026-08-17，选方案 A；Reviewer：D）
- **日期**：2026-08-17
- **决策人**：周子腾（E）｜**Reviewer**：D（待签）
- **责任轨道**：D（DB/迁移）为主，E 审查
- **决策版本**：`migration-naming-v1`
- **适用范围**：Alembic 迁移目录命名约定与版本链；关联冻结文档 §4.1、需求 v1.3 §二 FR-DB-002

## 背景

冻结文档 §4.1（`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`）同时要求两个互斥的命名规范：

1. **所有迁移命名格式** `YYYYMMDD_<description>.py`；
2. **基线迁移命名** `001_initial_schema.py`。

两格式无法兼容：基线若叫 `001_initial_schema.py` 则违反 `YYYYMMDD_` 前缀规则；若改成 `YYYYMMDD_initial_schema.py` 则不再是「基线 001」。Alembic 按文件名排序确定版本链，命名不一致会导致版本链初始化混乱（如多版本号、排序歧义、`alembic history` 不可读）。

需求 v1.3 已按「基线 `001_initial_schema.py` + 后续 `YYYYMMDD_<desc>.py`」写 FR-DB-002，本 ADR 正式裁定并回写冻结。

## 候选方案

### 方案 A：基线 `001_initial_schema.py`，后续 `YYYYMMDD_<description>.py`（本 ADR 决策）

基线迁移使用固定名 `001_initial_schema.py`（Alembic 版本链起点），后续增量迁移全部使用 `YYYYMMDD_<description>.py`。

优点：

- 基线语义清晰（版本链第一个节点）；
- 后续迁移按日期排序，天然反映时间顺序与依赖；
- Alembic 文件名排序稳定，`upgrade head` / `downgrade` 行为可预期；
- 与冻结文档「基线 `001_initial_schema.py`」原文保留一致。

缺点：

- 基线文件名不符合 `YYYYMMDD_` 前缀（需在冻结 §4.1 注明「基线例外」）。

### 方案 B：全部使用 `YYYYMMDD_<description>.py`（含基线）

基线也命名为 `YYYYMMDD_initial_schema.py`（如 `20260817_initial_schema.py`）。

优点：

- 命名规范完全统一。

缺点：

- 与冻结「基线 001」表述冲突；
- 基线迁移与首日增量迁移同一天时排序不直观；
- 回写冻结需改「基线 001」原文。

### 方案 C：全部使用序号 `001/002/003...`

优点：简单。

缺点：无法表达时间顺序与依赖关系，长期维护混乱；与冻结 `YYYYMMDD_` 约定冲突最大。

## 决策

选择方案 A：`migration-naming-v1`。**基线迁移固定为 `001_initial_schema.py`；后续所有迁移使用 `YYYYMMDD_<description>.py`。二者不混用。**

### 约定细则

| 项 | 约定 |
|----|------|
| 基线迁移 | `001_initial_schema.py`（版本链起点，含 5 表 + 4 冻结索引 + 1 辅助索引 + FTS5 + 触发器） |
| 增量迁移 | `YYYYMMDD_<description>.py`（如 `20260818_add_memory_fts_trigger.py`） |
| 回滚 | 每个迁移必须有 `downgrade()` |
| 禁止 | 手动改 SQLite、`render_as_batch=False` 的 autogenerate、删除列 |
| 同一天多迁移 | 追加序号区分：`YYYYMMDD_<desc>_2.py`（可接受，按序排列） |
| README 同步 | `migrations/README.md` 目录示意由 `.sql` 改为 `.py`（R-2 联动） |

### 回写冻结

批准后回写 `D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md` §4.1：明确「基线 `001_initial_schema.py`（例外），后续 `YYYYMMDD_<description>.py`」，消除两规范互斥。

## 影响

### 架构影响

- Alembic 版本链初始化确定性：`alembic upgrade head` 从 `001_initial_schema` 起有序执行；
- 后续迁移文件命名可预测，review 时可核对排序与依赖。

### 开发影响

- D4-D 按此命名创建 `001_initial_schema.py` 与后续迁移；
- `migrations/README.md` 同步校正（R-2）。

### 评测影响

- L2 验收：麒麟 VM 执行 `alembic upgrade head` + `downgrade base` 可逆，`.schema` 与冻结一致。

### 安全影响

- 无直接安全影响；迁移文件不得含硬编码凭据/路径（沿用提交扫描红线）。

## 回滚与替代条件

若后续需要统一命名（方案 B），须经新 ADR 并一次性重命名版本链（含 `down_revision` 调整），不得静默改单文件。切换至少需：核对版本链、独立 Reviewer 批准、补迁移测试。

## 证据与限制

- `deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md` §4.1（两命名规范原文）
- `migrations/README.md:24-27`（当前 `.sql` 示意，待校正）
- `deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md` §二 FR-DB-002（v1.3 已按方案 A 写）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：E 决策选方案 A（2026-08-17）；Reviewer D 签署确认后正式生效并回写冻结 §4.1（基线例外 + 后续 YYYYMMDD）。
