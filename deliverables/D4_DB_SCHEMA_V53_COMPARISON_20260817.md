# 5.0.3 聊天 DB Schema 对照清单（数据库初版冻结前置）

- **编制日期**：2026-08-17
- **编制人**：周子腾（D）
- **用途**：任务 3「冻结数据库初版、部署路径与失败路由」的冻结审查前置对照项；依据 `D4_GATE0_SUPPLEMENTARY_REVIEW_20260816.md` §六.3「需补充 5.0.3 聊天 DB Schema 变化作为对照项」
- **数据来源**：`docs/baseline/v2-20260816/05_capability_boundary_reevaluation_20260816.md` §2.3（麒麟 VM sqlite `.schema` 实测）
- **证据等级**：E4（麒麟 VM 宿主实测）；**request_data 语义为未验证项（待 P0 实验）**

---

## 一、对照目的

1. 确认环境基线升级（3.0.67 → 5.0.3）后，**自研 Memory Service 数据库初版冻结是否受影响**；
2. 将官方聊天 DB 的新 Schema 变化纳入冻结审查对照，明确「自研库」与「官方库」的边界，防止冻结对象与官方组件混淆；
3. 为 Memory Context 注入契约（AGT-005）提供 `request_data` 通道的待验证对照。

---

## 二、官方聊天 DB（5.0.3）变化对照

### 2.1 数据库文件与路径

| 项 | 旧基线（3.0.67） | 新实测（5.0.3） | 变化 |
|----|-----------------|----------------|------|
| 聊天 DB 路径 | `~/.config/kylin-aiassistant/kylin_aiassistant_database.db` | 同左（**不变**） | 无 |
| 新增独立库 | 无 | `knowledgebase_database.db`（官方知识库，`KNOWLEDGEBASE` 表） | **新增** |
| 新增表 | 无 | `DOCUMENT_REFERENCE`（文档问答引用） | **新增** |

### 2.2 RECORD 表新增 6 字段（sqlite .schema 实测）

| 字段 | 类型/默认 | 旧基线 | 评估意义 | 冻结影响 |
|------|----------|--------|---------|---------|
| `chat_type` | INT DEFAULT 0 | 无 | 区分聊天类型（普通/会议/文档等） | 自研库不受影响；记忆提取若按聊天类型过滤需后续对齐 |
| `is_collect` | INT DEFAULT 0 | 无 | 疑似「收藏/记忆」标记，与记忆相关 | **需关注**：与自研「记忆候选」边界可能重叠，P0 调查 |
| `request_data` | TEXT DEFAULT NULL | 无 | **潜在模型请求侧数据字段**，可能是原文隔离突破口 | **需 P0 实验**：若可作 Memory Context 注入通道，AGT-005 契约将引用它 |
| `mode_type` | INT DEFAULT 0 | 无 | 模式类型 | 无直接冲突 |
| `session_uuid` | VARCHAR(64) | 无 | 会话 UUID（区别于 sessionID） | 自研 `session_id` 语义需与官方 `session_uuid` 对照确认 |
| `has_unread` | INTEGER | 无 | 未读标记 | 无直接冲突 |

### 2.3 新组件/服务（ABI/包级确认，功能未知）

| 组件 | 版本 | 与「记忆」潜在关系 | 冻结影响 |
|------|------|------------------|---------|
| kylin-ai-memorymap（记忆地图） | 2.0.23 | 名字直指「记忆」，需确认是 UI 还是含记忆内核 | 自研范围边界待定（MEM-001/002 待重新调查） |
| kylin-ai-knowledge-base-service | 1.2.0.0-0k1.0 | 官方知识库，`KNOWLEDGEBASE` 表已落地 | 自研知识库/检索范围需重新界定 |
| kylin-ai-document-qa-service | 1.2.0.0-0k1.0 | 文档问答（DOCUMENT_REFERENCE 表） | 同上 |
| kyai-data-management-service | 1.2.0.0-0k1.10 | 数据管理业务服务 | 同上 |

---

## 三、自研 Memory Service 数据库初版（冻结对象）与官方库对照

### 3.1 冻结对象（自研库，FRZ-DB-001 设计冻结）

| 表 | 用途 | 与官方库关系 |
|----|------|-------------|
| `conversations` | 会话元数据 | 独立自建；与官方 RECORD/session_uuid 无耦合 |
| `turns` | 对话轮次（original_user_text 与 model_request 分离） | 独立自建；**原文隔离约束** [02 §4.1] |
| `memory_entries` | 记忆条目（entry_type/content JSON/confidence/version/is_deleted） | 独立自建；与官方 `is_collect` 边界待 P0 确认 |
| `outbox` | 事件重试（attempts/next_retry_at/last_error） | 独立自建 |
| `idempotency_cache` | 幂等三元组缓存 | 独立自建（FRZ-IPC-005） |
| `memory_fts`（FTS5） | 全文检索 | 独立自建 |

### 3.2 对照结论

| 对照项 | 结论 |
|--------|------|
| 自研库是否受 5.0.3 官方 Schema 变化影响？ | **不受影响**：自研库为独立 SQLite 文件，不写入官方 `kylin_aiassistant_database.db`；冻结结论继续有效 |
| 是否存在表名/字段名冲突？ | 未发现冲突；`session_id` vs `session_uuid` 语义需在注入契约定案时对照 |
| 是否需要变更冻结对象？ | 不需要变更 FRZ-DB-001；但冻结审查时需附上本对照清单 |

---

## 四、待验证项（P0，不阻塞冻结但需登记）

| 编号 | 待验证项 | 说明 | 责任轨道 |
|------|---------|------|---------|
| P0-V1 | `request_data` 读写语义实验 | 验证是否承载模型请求侧数据、能否作 Memory Context 注入通道且不污染 `message` | C |
| P0-V2 | `is_collect` 与自研记忆候选边界 | 官方「收藏/记忆」标记与自研 memory_entries 是否重叠 | E |
| P0-V3 | 官方 memorymap/知识库/数据管理能力边界 | 避免自研范围与官方组件重叠（MEM-001/002） | E |
| P0-V4 | `session_uuid` 与自研 `session_id` 映射 | 注入契约与证据追溯对齐 | C/D |

---

## 五、冻结审查使用说明

1. 本清单作为「数据库初版 / 部署路径 / 失败路由冻结」审查的**对照附件**，随冻结审查文档一并提交；
2. 冻结结论：自研库（FRZ-DB-001~005）不受 5.0.3 影响，可继续冻结；本清单仅作边界澄清与待验证登记；
3. P0 四项不阻塞冻结，但须在技术债登记中体现（关联 R-NEW-1 / R-NEW-2）；
4. 若 P0-V1 验证确认 `request_data` 可作注入通道，Memory Context 注入契约（AGT-005）将在后续 ADR 中引用本对照，**不触碰**已冻结的自研库 Schema。

---

## 六、签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 编制人 | 周子腾（D） | 2026-08-17 | 待确认 |
| Reviewer 1 | 待填写 | | |
| Reviewer 2 | 待填写 | | |
