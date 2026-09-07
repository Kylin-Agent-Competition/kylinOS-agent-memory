# KMA 统一业务数据格式冻结候选 v1（Canonical Business Schema v1）

- **版本**：v1
- **日期**：2026-09-03
- **状态**：`CANDIDATE_FOR_FREEZE`
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（IPC、SQLite、Outbox、虚拟机成品化与发布）
- **团队冻结条件**：只有非作者 D Reviewer 批准且承载本候选的 PR 合并后，本文件方可通过后续治理提交升级为团队级 `FROZEN` 业务语义基线；当前状态不代表团队冻结已经完成。
- **定位**：本文件是 KMA 记忆系统 Canonical Business Schema v1 的统一业务语义**冻结候选**，用于收口 E 轨历史业务 Schema 文档中的字段语义漂移与权威层级冲突。当前 PR 阶段仅提出统一业务语义裁定候选，不代表团队级冻结已经完成；本文件也不冻结任何宿主字段、IPC 线格式、SQLite 物理结构或 C++ 结构体。
- **KMA 前缀说明**：`KMA` 沿用仓库既有前缀用法（如 ADR-009 `KMA_SOCKET_PATH`、baseline v2 `KMA-CAPABILITY-*`），本文件不新造缩写全称定义。

---

## 0、定位与权威层级

### 0.1 拟议三层业务语义权威层级

以下层级是本轮 E 轨提出的团队业务语义权威层级候选，**只有本文件经非作者 D Reviewer 批准并完成对应 PR 合并后方可生效**。在此之前，本文件不得以尚未冻结的候选身份覆盖现有团队级契约：

| 层级 | 文档 | 状态 | 权威范围 |
|------|------|------|----------|
| **拟议 L1** | 本文件 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` | `CANDIDATE_FOR_FREEZE` | 承载统一业务字段语义裁定候选（R-1..R-6）、字段别名与映射边界、物理结构边界；D Reviewer 批准且 PR 合并后方可升级为团队级最高业务语义权威 |
| **拟议 L2** | `D3_MEMORY_BUSINESS_CONTRACT_V1.md` | `CANDIDATE_FOR_FREEZE` | 承载 Canonical 未覆盖的详细业务语义；当前两者均为候选，不建立“未审核 Canonical 自动覆盖 D3”的团队级关系 |
| **拟议 L3** | `MEMORY_BUSINESS_SCHEMA_V0.1.md` | `DRAFT` | 历史初稿，作为 compatibility/来源参照；待 Canonical 完成团队冻结后，再按冻结后的权威关系处理冲突 |

### 0.2 superseded / compatibility 矩阵

| 文档 | 与 Canonical v1 的关系 | 说明 |
|------|------------------------|------|
| `D3_MEMORY_BUSINESS_CONTRACT_V1.md` | **compatibility 候选关系** | 保持 `CANDIDATE_FOR_FREEZE`，继续承载详细业务语义；不改变其 §12.2 冻结条件。Canonical v1 完成团队冻结前，不以候选文档身份覆盖 D3；完成冻结后按最终批准的权威层级处理冲突 |
| `MEMORY_BUSINESS_SCHEMA_V0.1.md` | **proposed superseded + compatibility** | 作为历史初稿保留；“业务语义权威由 Canonical v1 承接”是本轮拟议关系，待 Canonical 完成团队冻结后生效；当前继续作为来源参照 |

**约束**：三份文档不得同时声称业务语义最高权威。当前本文件仅为 `CANDIDATE_FOR_FREEZE`，不改变 D3 的 `CANDIDATE_FOR_FREEZE` 状态，也不改变 Schema 的 `DRAFT` 状态；只有 D Reviewer 批准且对应 PR 合并后，方可通过后续治理提交升级本文件状态并正式建立团队级权威关系。

---

## 1、依据与局限声明

### 1.1 在库依据（SOURCE_VERIFIED）

| 编号 | 来源 | 路径 | 仓库状态 |
|------|------|------|----------|
| S-01 | Day1 记忆业务 Schema v0.1 DRAFT（修订2，2026-07-30） | `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md` | SOURCE_VERIFIED（在库） |
| S-02 | Day1 标注规范 v0.1 DRAFT（修订2，2026-07-31） | `datasets/ANNOTATION_GUIDELINE_V0.1.md` | SOURCE_VERIFIED（在库） |
| S-03 | Day2 事件契约冻结前检查表 v0.1 DRAFT（2026-08-07） | `docs/architecture/D2_EVENT_CONTRACT_PRE_FREEZE_CHECKLIST_V0.1.md` | SOURCE_VERIFIED（在库） |
| S-04 | Day3 记忆业务契约 v1 候选 | `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md` | SOURCE_VERIFIED（在库，`CANDIDATE_FOR_FREEZE`） |
| S-05 | ADR-010（IPC Mapping metadata 含 `collected_at`） | `docs/adr/` | SOURCE_VERIFIED（在库） |
| S-06 | 技术债务登记表（TD-039 记录 ADR-010 IPC Mapping metadata 含 `collected_at`） | `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | SOURCE_VERIFIED（在库） |

### 1.2 局限声明

- **本文件不新增任何 Runtime 证据**：本任务 `runtime_required=false`，不产生 `HOST_VERIFIED`、Runtime PASS 或性能达标声明。
- **宿主映射保持待确认**：所有依赖 C 真实宿主取证的事项保持 `PENDING_C_CONFIRMATION`；所有依赖 D IPC/持久化证据的事项保持 `PENDING_D_CONFIRMATION`。本文件不把「业务语义冻结候选」写成「团队冻结已完成」或「宿主字段已确认」。
- **不修改协议版本**：`protocol_version`（IPC）与业务事件 `schema_version`（"0.1"）均不由本文件改动。
- **基线 DOCX 未导入**：赛题原文、总体架构 SOP v1.1、官方 SDK 与 OS Agent 能力边界基线文档仍未导入仓库，本文件不声称已从实体 DOCX 独立核验任何字段语义。

---

## 2、Canonical 裁定（R-1..R-6）

以下六项为 E 轨提出的 Canonical 业务语义统一裁定候选。每条含：候选裁定内容、在库依据、兼容性影响、责任轨道 handoff。其具体语义在本 PR 中接受 D Reviewer 审查；本文件只有在 D Reviewer 批准并完成 PR 合并后的后续治理中，才可升级为团队级 `FROZEN` 权威基线。

### R-1：`captured_at` 为 Canonical 事件捕获时间字段；`collected_at` 仅为 legacy transport alias

- **裁定内容**：`captured_at` 是 Canonical 事件捕获时间字段（事件捕获入库时间，系统生成）。`collected_at` 仅为 legacy transport alias，业务语义与 `captured_at` 一一对应；transport 层（IPC/事件承载）若使用 `collected_at`，必须经 Adapter/Mapping 映射到业务层 `captured_at`，不得在业务层引入第三种时间字段语义。
- **在库依据**：Schema §3.1 `captured_at`（事件捕获入库时间）；D2 检查表第 60/206 行 `collected_at`（候选公共字段，语义差异待确认）；TD-039 记录 ADR-010 IPC Mapping metadata 含 `collected_at`；A Provider 前向草稿（D3 C-05）亦用 `collected_at`。
- **兼容性影响**：不修改任何 ADR、D2 检查表或 A Provider 草稿；transport 层 `collected_at` 现状保留，采纳/更名属 C/D 实现 handoff（登记 TD-060）。
- **责任轨道 handoff**：C/D（transport 层 Adapter/Mapping 或更名方案书面冻结，不修改 `protocol_version`）；E（业务语义候选已提出，待 D Reviewer 确认并完成团队冻结）。

### R-2：`expression_type` 仅允许 `explicit`/`implicit`；`candidate` 由 `memory_status=candidate` 表达

- **裁定内容**：`expression_type` 取值仅 `explicit`/`implicit` 二值。`inferred` 为旧称，已归一为 `implicit`；`candidate` 不是表达类型值，候选生命周期由 `memory_status=candidate` 表达。
- **在库依据**：标注规范修订2（2026-07-31）第 18/19/66/69/817 行已归一为二值；Schema §2.5 说明；D3 §5.2/§5.6/§六。
- **兼容性影响**：Schema §2.5 与 HD-SCHEMA-14 的过时三值描述已由 day12-e-01 修正（见变更记录）；HD-SCHEMA-14 的 SOP v1.1 导入后终审仍保留。
- **责任轨道 handoff**：E（SOP v1.1 导入后终审，HD-SCHEMA-14）。

### R-3：`memory_status` 是生命周期唯一业务真值；`is_active`/`is_outdated`/`should_decay` 仅 compatibility/deprecated

- **裁定内容**：`memory_status` 六值（`active`/`superseded`/`deprecated`/`expired`/`removed`/`candidate`）是生命周期唯一业务真值。`is_active`/`is_outdated`/`should_decay` 仅 compatibility/deprecated 过渡字段，冲突时以 `memory_status` 为准；过渡字段移除按 TD-016 既有条件由 D Reviewer 验收。
- **在库依据**：Schema §2.8/§3.2/§3.3；D3 §3.6/§7.4；TD-016（Open，关闭条件含「⑤ D Reviewer 确认迁移完成」）。
- **兼容性影响**：不改变 TD-016 状态；本裁定不替代或提前关闭 TD-016。
- **责任轨道 handoff**：D/E（过渡字段移除验收，TD-016）。全仓消费者矩阵见 `docs/day12/14_d12e_lifecycle_schema_drift_handoff_20260903.md`（2026-09-03 盘点，TD-016 关闭条件 ① 完成，条件 ②③④⑤ 开放，状态保持 Open；`vector_index_entries.is_active` 为同名异义 orthogonal 对象，冻结排除）。

### R-4：`processing_status` 仅属于 Runtime technical state，与 `source_business_status` 正交

- **裁定内容**：`processing_status` 五值（`pending`/`extracting`/`extracted`/`embedded`/`stored`）仅为 Memory Service 内部处理流水线的 Runtime technical state，**不得升格为业务枚举**。`processing_status` 与 `source_business_status`（八值业务结果状态）语义正交：一个事件可能业务上 `success` 但处理流水线中仍处于 `extracting`。
- **在库依据**：Schema §2.4；D3 §5.1/§5.6/§8.2。
- **兼容性影响**：三份文档均保持 `processing_status` 技术枚举定位，无升格。
- **责任轨道 handoff**：A/B/D（状态机条件，D3 §8.2 已登记 REVISED）。

### R-5：Canonical 字段名使用 `sensitivity`；`sensitivity_level` 仅注解层明确 1:1 alias

- **裁定内容**：Canonical 业务字段名为 `sensitivity`（五级：`none`/`low`/`medium`/`high`/`critical`）。`sensitivity_level` 仅允许作为注解层（标注规范）的明确 1:1 alias，不得出现第三种命名或语义分叉。
- **在库依据**：Schema §2.10/§3.1；D3 §5.1/§7.7；`sensitivity_level` 仅出现在注解层（`datasets/ANNOTATION_GUIDELINE_V0.1.md` 第 277/646 行）、C 轨示例（`os-agent-integration/contracts/examples/manual_config_event.v1.json`）与 `D3_MEMORY_SECURITY_ACCEPTANCE_V1.md` 第 85 行。
- **兼容性影响**：注解层 `sensitivity_level` 保留为 1:1 alias；业务 Canonical 层统一使用 `sensitivity`。
- **责任轨道 handoff**：E（分级标准终审，HD-ANNO-05）；C（宿主字段取证，`PENDING_C_CONFIRMATION`）。

### R-6：业务 Canonical Schema 不要求与 C++/IPC/SQLite 物理结构 1:1 同形，差异必须经 Adapter/Mapping

- **裁定内容**：业务 Canonical Schema 是业务语义层定义，**不要求**与 C++ 结构体、IPC JSON Schema、SQLite 物理表结构 1:1 同形。任何物理结构与业务语义的差异必须经 Adapter/Mapping 显式转换，不得以物理结构差异反向改写业务语义。
- **在库依据**：README.md 技术路线（SQLite 真源、Vector 可重建、UDS + 长度前缀 JSON）；D3 §八 不可冻结项清单（SQLite/Vector/IPC/C++ 结构体全部 DEFERRED）。
- **兼容性影响**：不修改 `protocol_version`、不触碰 FRZ-IPC/FRZ-DB 物理层契约；物理层契约仍由 D 轨负责。
- **责任轨道 handoff**：D（IPC/SQLite 物理契约）；C/D（C++ 结构体与 QML 客户端）。

---

## 3、字段别名与映射边界表

| Canonical 字段 | 别名 / 过渡字段 | 别名层级 | 映射边界 |
|----------------|-----------------|----------|----------|
| `captured_at` | `collected_at` | legacy transport alias | transport→business 必经 Adapter/Mapping；业务层统一 `captured_at` |
| `expression_type` | `inferred`（旧称） | 已废弃 | `inferred` 归一为 `implicit`，不作为独立枚举值 |
| `memory_status` | `is_active`/`is_outdated`/`should_decay` | compatibility/deprecated 过渡字段 | 冲突时以 `memory_status` 为准；移除按 TD-016 由 D Reviewer 验收 |
| `sensitivity` | `sensitivity_level` | 注解层 1:1 alias | 仅注解层允许；业务 Canonical 层统一 `sensitivity` |
| `source_business_status` | `processing_status` | 正交字段（非别名） | `processing_status` 仅 Runtime technical state，不得升格为业务枚举 |

---

## 4、物理结构边界

- 业务 Canonical Schema 与 C++/IPC/SQLite 物理结构**非 1:1 同形**（R-6）。
- 以下物理层契约不由本文件冻结，保持 `DEFERRED`/`PENDING_*`：
  - SQLite 数据库表结构、schema 迁移、唯一约束、外键（`PENDING_D_CONFIRMATION`）
  - IPC JSON Schema（UDS 消息结构）、`protocol_version`、`request_id`、错误码（`PENDING_D_CONFIRMATION`）
  - Vector Collection Schema / 索引布局（`PENDING_B_CONFIRMATION`）
  - C++ 侧结构体定义（cpp-bridge/、memory-client/）（`PENDING_C_CONFIRMATION`/`PENDING_D_CONFIRMATION`）
- 本文件不修改 `protocol_version` 与业务事件 `schema_version`（"0.1"）。

---

## 5、明确不裁定 / 不冻结清单

以下事项**不在本文件裁定范围**，保持既有状态，不得因本文件当前的冻结候选状态而改变：

| 事项 | 保持状态 | 责任轨道 |
|------|----------|----------|
| 宿主字段是否真实存在及语义（`user_id`/`actor_id`/`turn_id`/`tool_call_id`/`occurred_at` 等） | `PENDING_C_CONFIRMATION` | C |
| IPC 线格式、`protocol_version`、UDS 消息结构 | `PENDING_D_CONFIRMATION`，不修改 | D |
| SQLite 物理 Schema、迁移、存储形态 | `PENDING_D_CONFIRMATION` | D |
| `confidence_score` 量化方法、衰减函数 | `DEFERRED`（HD-SCHEMA-03） | A/E |
| 冲突判定阈值算法 | `DEFERRED`（HD-SCHEMA-04） | B |
| 短/中/长期分层边界与存储布局 | `DEFERRED`（HD-SCHEMA-07） | D |
| `*_id` 生成策略 | `DEFERRED`（HD-SCHEMA-09） | D |
| 过渡布尔字段移除 | 按 TD-016 既有条件，由 D Reviewer 验收 | D/E |
| transport 层 `collected_at` alias 的 Adapter/Mapping 或更名方案 | 书面冻结待 C/D（登记 TD-060） | C/D |
| Canonical 文档索引至 `docs/architecture/README.md` | 独立维护任务（HD-SCHEMA-10） | 团队 |
| 基线 DOCX（01–06）导入与 SOP v1.1 终审 | 待人工导入 | 团队/E |

---

## 6、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-09-03 | 建立 KMA Canonical Business Schema v1 冻结候选：提出拟议三层权威层级、superseded/compatibility 候选关系与六项 Canonical 业务语义裁定候选（R-1..R-6）；附字段别名与映射边界表、物理结构边界、证据纪律与不裁定清单。状态 `CANDIDATE_FOR_FREEZE`；待非作者 D Reviewer 批准且对应 PR 合并后，再通过后续治理提交升级为团队级 `FROZEN`。 | E 轨道 |

---

> **本文档到此结束。** 当前状态为 `CANDIDATE_FOR_FREEZE`。只有非作者 D Reviewer 批准且承载本候选的 PR 合并后，方可通过后续治理提交升级为团队级 `FROZEN`；任何宿主/物理层证据变化仍须先经对应轨道取证并更新证据状态。