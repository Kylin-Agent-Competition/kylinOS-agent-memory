# D12E 生命周期字段漂移消费者矩阵与跨轨迁移 Handoff

- **任务引用**：`day12-e-08-lifecycle-drift-handoff-v6`（D12E TD-016 生命周期字段漂移消费者矩阵）
- **日期**：2026-09-03
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（IPC、SQLite、Outbox、虚拟机成品化与发布）
- **状态**：盘点完成，结论待 D/E 决策；TD-016 保持 Open
- **类型**：纯文档任务（`runtime_required: false`），无运行时代码行为变化

---

## 1、盘点范围与排除声明

### 1.1 盘点对象

以 `memory_status`（六值：`active`/`superseded`/`deprecated`/`expired`/`removed`/`candidate`）为**唯一业务生命周期真值**（KMA 冻结 R-3，`docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` L78），对以下三个过渡布尔字段的全仓消费者做事实盘点：

- `is_active`
- `is_outdated`
- `should_decay`

### 1.2 盘点范围

全仓代码与迁移文件（`memory-service/`、`migrations/`），含领域层、服务层、持久化层、检索层与全部测试。

### 1.3 分类定义（四值集合）

| 分类 | 定义 |
|------|------|
| `derived` | 由 `memory_status` 派生/与 `memory_status` 同向一致，或仅用于一致性回归守护（测试断言），不独立承载业务决策 |
| `legacy_read` | 仅读取/注释过渡字段，不反向覆写 `memory_status` |
| `write_path` | 代码中存在写入过渡字段的路径（构造承载或派生共写） |
| `unused` | 全仓零消费（无标识符引用） |

### 1.4 排除声明

- **`vector_index_entries.is_active` 不在本盘点对象内**：属 Vector ledger 世代可见性/软删的**同名异义（orthogonal）**字段，与 preferences 生命周期布尔语义无关，冻结保留，不被 TD-016 布尔移除决策波及（详见 §3）。
- **本任务不删除任何 legacy Boolean 字段/列**：盘点只产出事实与迁移建议，字段移除/派生化/冻结为 orthogonal 属 TD-016 关闭条件 ②，由 D 主审裁定。
- **本书面盘点不构成「已完成迁移」声明**：所有「已完成」表述仅指盘点动作本身。

### 1.5 事实证据

- 全仓 `.py` 检索 `is_active|is_outdated|should_decay` 共 83 处匹配，**全部位于 `memory-service/` 与 `migrations/`**。
- `memory-client/`、`os-agent-integration/`、`cpp-bridge/` **零匹配**（C 轨零消费，A 轨无直接消费者）。

---

## 2、消费者矩阵（全仓）

### 2.1 E 轨 — 领域层（domain）

| 文件 | 行号 | 字段 | 读写方向 | 当前语义 | 分类 | 风险 | 责任轨 | 迁移方式 |
|------|------|------|----------|----------|------|------|--------|----------|
| `memory-service/domain/preference.py` | L8（docstring） | `is_active` / `should_decay` | 仅注释 | D3 REVISED 过渡字段标注：「待 D/E 统一为 memory_status 后移除」 | `legacy_read` | 无（注释） | E | 随 TD-016 条件 ② 决策更新注释 |
| `memory-service/domain/preference.py` | L52 | `is_active: bool` | 写（模型字段承载） | 过渡字段承载，`MemoryPreference` 构造时取值 | `write_path` + `legacy_read` | Medium（双写漂移） | E 决策 / D 持久化保留 | 条件 ② 裁定后由 E/D 移除或冻结并同步序列化映射 |
| `memory-service/domain/preference.py` | L55 | `should_decay: bool` | 写（模型字段承载） | 过渡字段承载 | `write_path` + `legacy_read` | Medium（双写漂移） | E 决策 / D 持久化保留 | 同上 |
| `memory-service/domain/knowledge.py` | L14（docstring） | `is_outdated` | 仅注释 | REVISED 过渡字段标注：「待 D/E 统一为 memory_status 后移除」 | `legacy_read` | 无（注释） | E | 随条件 ② 更新注释 |
| `memory-service/domain/knowledge.py` | L64 | `is_outdated: bool` | 写（模型字段承载） | 过渡字段承载，`KnowledgeEntry` 构造时取值 | `write_path` + `legacy_read` | Medium（双写漂移） | E 决策 / D 持久化保留 | 同上 |
| `memory-service/domain/enums.py` | L66（仅注释） | 三布尔（注释提及） | 仅注释 | 过渡字段说明：「待 D/E 统一后移除」 | `legacy_read` | 无（注释） | E | 随条件 ② 更新注释 |

### 2.2 E 轨 — 服务层（service）

| 文件 | 行号 | 字段 | 读写方向 | 当前语义 | 分类 | 风险 | 责任轨 | 迁移方式 |
|------|------|------|----------|----------|------|------|--------|----------|
| `memory-service/service/candidate_governance.py` | L323（docstring）、L336–337（`is_active=False`）、L340（`should_decay=False`）、L375（docstring）、L380（`is_outdated=False`） | 三布尔 | 写（创建候选时**派生共写**） | 与 `memory_status=CANDIDATE` 同向一致：候选未激活、未配置衰减、未过期 | `write_path`（派生共写） | 低（当前同向一致，**未覆写 memory_status 语义**） | E | 保持派生共写现状；**预防约束**：任何后续以 legacy Boolean 覆写 `memory_status` 的写路径一律标 High 并冻结 |

### 2.3 D 轨 — 持久化层（db）

| 文件 | 行号 | 字段 | 读写方向 | 当前语义 | 分类 | 风险 | 责任轨 | 迁移方式 |
|------|------|------|----------|----------|------|------|--------|----------|
| `memory-service/db/schema.py` | L202 | `preferences.is_active`（Integer, `nullable=False, server_default="1"`） | 写（DDL 列定义）/ 读（ORM 映射） | preferences 表生命周期过渡列，`server_default="1"` 默认激活语义 | `write_path` + `legacy_read` | Medium（双写漂移；默认值与 `memory_status` 初始化路径无一致性约束） | D（持久化保留至 E 决定） | 列保留；E 决定条件 ② 后由 D 出迁移，移除前不得改变 `server_default` |

### 2.4 B 轨 — 检索层（vector ledger `is_active`，orthogonal，见 §3）

| 文件 | 行号 | 字段 | 读写方向 | 当前语义 | 分类 | 风险 | 责任轨 | 迁移方式 |
|------|------|------|----------|----------|------|------|--------|----------|
| `memory-service/db/schema.py` | L526 | `vector_index_entries.c.is_active` | 读（JOIN 过滤） | Vector ledger 世代可见性 | **orthogonal（非生命周期布尔）** | 无（排除对象） | B/D | 冻结保留，不受 TD-016 波及 |
| `memory-service/retrieval/sqlite_vector_provider.py` | L234 | `vector_index_entries.c.is_active == 1` | 读（检索过滤） | 仅检索可见世代 | orthogonal | 无 | B | 冻结保留 |
| `memory-service/retrieval/sqlite_vector_provider.py` | L266 | `.values(is_active=0)` | 写（停用世代） | 世代软删/停用 | orthogonal | 无 | B | 冻结保留 |
| `memory-service/retrieval/sqlite_vector_provider.py` | L501 | `is_active=1` | 写（激活世代） | 世代激活 | orthogonal | 无 | B | 冻结保留 |
| `migrations/versions/20260901_d10b_vector_ledger.py` | L51 | `Column("is_active", ..., server_default="1")` | 写（建表列定义） | 建表 | orthogonal | 无 | B/D | 冻结保留 |
| `migrations/versions/20260901_d10b_vector_ledger.py` | L56 | 唯一索引 `["scope_id","generation","user_id","is_active"]` | 读（约束） | 世代可见性参与唯一键 | orthogonal | 无 | B/D | 冻结保留 |

### 2.5 测试层（derived — 一致性回归守护）

| 文件 | 行号（示例断言） | 字段 | 当前语义 | 分类 | 迁移方式 |
|------|------------------|------|----------|------|----------|
| `memory-service/tests/test_lifecycle_policy_d8e.py` | L13（docstring）、L199–201、L1063 | 三布尔 | 断言过渡字段传入 LifecycleSnapshot → `ValidationError`（`extra="forbid"` 守护） | `derived` | 迁移时同步更新断言，**不降低断言强度** |
| `memory-service/tests/test_knowledge_conflict_lifecycle_flow_d8e.py` | L434 | `is_outdated` | 断言冲突流 `is_outdated is False`（与 `memory_status` 一致） | `derived` | 同上 |
| `memory-service/tests/test_candidate_governance_d5e.py` | L147、L150、L231、L235、L337、L365、L376 | 三布尔 | 守护候选治理输出的派生共写不变量 | `derived` | 同上 |
| `memory-service/tests/test_domain_models_d4e.py` | L72、L75、L97 | 三布尔 | Domain 模型构造一致性 | `derived` | 同上 |
| `memory-service/tests/test_knowledge_domain_mapping_d8e.py` | L383、L408 | `is_outdated` | Knowledge 领域映射一致性 | `derived` | 同上 |
| `memory-service/tests/test_cross_session_business_case_d5e.py` | L196、L257 | `is_active` | 跨会话业务流一致性 | `derived` | 同上 |
| `memory-service/tests/test_multisource_security_adversarial_d6e.py` | L572 | `is_active` | 多源安全对抗流一致性 | `derived` | 同上 |
| `memory-service/tests/test_preference_business_flow_d7e.py` | L15（docstring）、L265、L268、L490、L504、L516、L625、L686、L722、L819 | 三布尔 | 偏好业务流一致性守护 | `derived` | 同上 |
| `memory-service/tests/test_preference_version_policy_d7e.py` | L124、L127、L424+（`SUPERSEDED, is_active=False` 系列） | `is_active` / `should_decay` | 版本策略状态一致性守护 | `derived` | 同上 |
| `memory-service/tests/test_preference_business_policy_d7e.py` | L132、L135 | `is_active` / `should_decay` | 偏好业务策略一致性 | `derived` | 同上 |
| `memory-service/tests/retrieval/test_sqlite_vector_provider.py` | L245、L264、L307、L644 | `vector_index_entries.is_active` | Vector ledger 世代可见性守护 | `derived` + **orthogonal** | 与 B 轨冻结一致，不受生命周期布尔移除波及 |

### 2.6 C 轨 / A 轨 / 其他（unused）

| 模块 | 匹配情况 | 分类 | 动作 |
|------|----------|------|------|
| `memory-client/` | 零匹配（无 `is_active`/`is_outdated`/`should_decay` 标识符引用） | `unused` | 无动作；若未来接入生命周期展示，直接读 `memory_status` |
| `os-agent-integration/` | 零匹配 | `unused` | 无动作 |
| `cpp-bridge/` | 零匹配 | `unused` | 无动作 |
| A 轨 Provider/Embedding | 无直接消费者 | `unused` | 无新增动作；`should_decay` 涉及的衰减函数语义为既有 A/E 决策点（`confidence_score` 量化方法/衰减函数 `DEFERRED`，freeze 文档 §5 HD-SCHEMA-03），未来实现衰减函数时必须以 `memory_status` 为真值依据，不得以 `should_decay` 为决策源 |

---

## 3、同名异义排除对象：`vector_index_entries.is_active`

`vector_index_entries.is_active`（`db/schema.py` L526、`sqlite_vector_provider.py` L234/266/501、`d10b_vector_ledger.py` L51/56）与 preferences 生命周期布尔 `is_active` **同名异义**：前者是 Vector ledger 世代可见性/软删标记，参与世代唯一索引（`d10b_vector_ledger.py` L56），不表达任何业务生命周期语义。

- **分类**：orthogonal（非生命周期布尔）
- **处置**：冻结保留；**不得被 TD-016 的过渡布尔移除决策波及**
- **责任轨**：B（检索行为）/ D（建表与迁移）维持现状，无改动

---

## 4、A/B/C/D 最小 Handoff 清单

### 4.1 A 轨（Embedding、提取 Provider、数据质量与性能可靠性）

- **无直接消费者**：全仓检索 A 轨实现无三布尔引用。
- **动作**：无新增。
- **既有决策点**：`should_decay` 的衰减语义属 `confidence_score` 量化方法/衰减函数（HD-SCHEMA-03，`DEFERRED`，A/E）。未来实现衰减函数时以 `memory_status` 为真值（如 `expired` 触发依据），不得以 `should_decay` 为决策源。

### 4.2 B 轨（Vector、FTS5、应用层 RRF、索引一致性与检索评测）

- **动作**：无改动。
- **冻结**：`vector_index_entries.is_active`（世代可见性/软删，orthogonal）冻结保留，不被 TD-016 波及；`tests/retrieval/test_sqlite_vector_provider.py` 相关守护维持现状。
- **边界**：B 轨不得因生命周期布尔语义变化而改变 vector ledger 世代过滤/停用/激活逻辑。

### 4.3 C 轨（OS Agent Hook、MemoryClient、Tool/Turn Adapter 与 QML）

- **零消费**：`memory-client/`、`os-agent-integration/`、`cpp-bridge/` 均无三布尔引用（unused）。
- **动作**：无。
- **边界**：C 轨 Host/Client 若消费生命周期信息，直接读 `memory_status`；不得新建三布尔副本。

### 4.4 D 轨（IPC、SQLite、Outbox、虚拟机成品化与发布）

- **持久化保留**：`preferences.is_active` 列（`schema.py` L202）保留至 E 决定 TD-016 条件 ②；`migrations/` 不修改（既有迁移文件不动）。
- **验收**：TD-016 关闭条件 ⑤「D Reviewer 确认迁移完成」由 D 主审在条件 ②③④ 完成后验收；本文档为条件 ① 的事实依据，供 D 主审复核。
- **约束**：D 轨新增/修改迁移时不得改变 `server_default` 或隐式引入新的生命周期布尔一致性路径，须先登记 TD-016 相关决策。

---

## 5、E 自身核验：LifecyclePolicy 仅依赖 memory_status

E 侧商业生命周期策略已实现为「仅以 `memory_status` 为真值」的结构性约束，证据如下：

1. **策略声明**：`memory-service/service/lifecycle_policy.py` L26 ——「不依赖 is_active / is_outdated / should_decay 过渡字段做最终决策」。
2. **快照契约**：`lifecycle_policy.py` L103–104 —— `memory_status` 为唯一优先生命周期真源（domain.enums 六值冻结）；`LifecycleSnapshot` 明确不含三过渡字段（`extra="forbid"` 结构性拒绝）。
3. **决策分派**：`lifecycle_policy.py` L213–223 —— 决策仅按 `memory_status` 六值分派（REMOVED/EXPIRED/CANDIDATE/SUPERSEDED/DEPRECATED/ACTIVE），无布尔分支。
4. **测试守护**：
   - `memory-service/tests/test_lifecycle_policy_d8e.py` L199–201：三布尔传入 LifecycleSnapshot → `ValidationError`；L1063：快照字段白名单（循环断言三布尔拒绝）。
   - `memory-service/tests/test_knowledge_conflict_lifecycle_flow_d8e.py` L434：知识冲突生命周期流 `is_outdated is False`（过渡字段与 `memory_status` 语义一致性守卫）。

**结论**：E 商业策略仅依赖 `memory_status`；E 侧**无**以 legacy Boolean 覆写 `memory_status` 的写路径；`candidate_governance.py` L323–380 的派生共写与 `memory_status=CANDIDATE` 同向一致，不构成冲突写路径。

---

## 6、TD-016 状态回写

| 关闭条件 | 内容 | 2026-09-03 状态 |
|----------|------|------------------|
| ① | 全系统盘点过渡字段消费者 | ✅ **本任务完成**（本文档 §2 全仓消费者矩阵，83 处匹配逐项归类） |
| ② | 删除、派生化或冻结为正交属性 | 保持开放（待 D 主审裁定；`vector_index_entries.is_active` 已明确排除为 orthogonal 冻结对象） |
| ③ | Domain/Service/Repository 统一语义 | 保持开放 |
| ④ | 补充 Candidate→Active、Superseded、Deprecated、Expired 等一致性测试 | 保持开放 |
| ⑤ | D Reviewer 确认迁移完成 | 保持开放（D 主审验收） |

**状态结论**：TD-016 保持 **Open**（跨轨迁移与 D 主审完成前不关闭）。本文档不回写 Resolved，仅完成关闭条件 ① 的事实依据。状态与 `docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` R-3 保持一致（不改变裁定内容、不提前关闭）。

---

## 7、无运行时代码行为变化声明

- 本任务为纯文档任务（`runtime_required: false`）：仅新建/编辑 3 个文档文件（本文档、`TECHNICAL_DEBT_REGISTER.md` TD-016 行、`KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` R-3 引用）。
- **不修改** `memory-service/`、`memory-client/`、`os-agent-integration/`、`cpp-bridge/`、`migrations/` 任何代码。
- **不删除** 任何 legacy Boolean 字段/列。
- **不改变** IPC 协议、DB schema、迁移文件或运行时行为。
- L1 回归守护（`test_lifecycle_policy_d8e.py`、`test_knowledge_conflict_lifecycle_flow_d8e.py`）用于确认 E 侧「LifecycleSnapshot 拒绝过渡字段」与「knowledge 冲突生命周期流」不变量在 docs-only 改动后仍成立。

---

## 8、风险与技术债

| 风险 | 影响 | 缓解 |
|------|------|------|
| 将 `vector_index_entries.is_active` 误判为生命周期布尔 | B/D 轨误导性动作 | §3 显式「同名异义」排除小节，附行号证据，声明冻结保留 |
| 未来的写路径以 legacy Boolean 覆写 `memory_status` | 双写漂移，违反唯一真值原则 | §2.2 预防约束：出现即标 High 并冻结，回写 TD-016 |
| 「盘点完成」被误读为「迁移完成」 | 违反 acceptance，规避测试降级红线 | 全文禁止词：不写「已迁移/已移除/已关闭」；仅陈述盘点事实与条件 ① 完成 |
| 测试迁移时降低断言强度 | 回归守护失效 | §2.5 迁移方式统一约定：同步更新断言、不降低断言强度 |

## 9、后续决策点（留给 D/E Reviewer，非本任务阻断）

- TD-016 条件 ② 最终裁定（删除 vs 派生化 vs 冻结为 orthogonal）——D 主审。
- TD-016 条件 ④ 一致性测试补充——后续任务。
- 本文档矩阵的复核——D 主审。