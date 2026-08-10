# Day3 记忆安全验收契约 v1 候选

- **版本**：v1
- **状态**：`CANDIDATE_FOR_FREEZE`
- **阶段定位**：Day3 / Gate 0 / E 轨道安全验收契约候选
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（IPC、SQLite、Outbox、虚拟机成品化与发布）
- **冻结为团队基线条件**：**只有非作者 D Reviewer 批准且 PR 合并后，本文档方可视为团队冻结基线**。本文件的 `CANDIDATE_FOR_FREEZE` 状态仅表示 E 轨道单方面提出的 v1 候选安全验收语义集合，**不代表已被 D 批准、不代表 D3 Gate 通过、不代表任何宿主行为、KYSEC 规则、Kaiming Hook、断线重连或实现能力已被验证**。
- **用途**：在已冻结的 `D3_MEMORY_BUSINESS_CONTRACT_V1.md`（业务契约 v1 候选）安全侧面之上，把 E 轨道负责的安全红线（用户隔离、敏感信息与原始载荷、LLM 权限、Tool 证据可信度、精准遗忘、幂等/重试、上下文隔离、授权边界）写成**可验收契约**——每条规则至少包含：规则 ID、前置条件/输入、必须行为、禁止行为、所需证据、当前证据状态、阻断级别；并把 Day2 Gate 0 业务验收案例集 `GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json`（G0-E-01..14）映射为可审查验收规则。
- **本文件不是**：SQLite 物理 Schema、Migration、Vector Collection Schema、过滤表达式、删除逻辑、ACL、KYSEC 规则文件、SQLite 约束、Vector 过滤实现、IPC 鉴权实现、C++ 结构体或 Provider 接口。上述技术实现层事项见「八、不可冻结项声明（本文件不是实现方案）」，全部 `DEFERRED` 或 `待对应轨道确认`。
- **本任务性质声明**：本任务为纯 Markdown 契约任务（`runtime_required=false`、`runtime_commands=[]`）。L0/L1 的 `python3 -m pytest --version` 仅作为控制器允许的**本地工具可用性探测**，**不是安全能力验证**；本文件全部规则所需证据目标均为 `HOST_VERIFIED`，真正 L2/L3 麒麟证据由后续对应实现任务在银河麒麟 V11 x86_64 真实环境执行后回填，本文件不虚标任何验证通过。

---

## 一、依据来源与局限声明

### 1.1 依据来源（仓库内已核验文件）

| 编号 | 来源 | 路径 | 仓库状态 |
|------|------|------|----------|
| SEC-S-01 | Day3 业务契约 v1 候选（安全侧面：§7.1/§7.5/§7.6/§7.7/§7.8/§7.10/§1.2 证据口径） | `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md` | SOURCE_VERIFIED（在库，`CANDIDATE_FOR_FREEZE`） |
| SEC-S-02 | Day1 标注规范 v0.1 DRAFT（修订2）：§5.1 敏感类型 S-01..S-09、§5.2 敏感过滤字段、§5.3 跨用户隔离正/负向测试 | `datasets/ANNOTATION_GUIDELINE_V0.1.md` | SOURCE_VERIFIED（在库） |
| SEC-S-03 | Day2 业务验收案例集 v0.1 DRAFT（G0-E-01..14，含 `forbidden_outcomes`/`required_evidence_level`/`current_status`） | `datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json` | SOURCE_VERIFIED（在库，DRAFT） |
| SEC-S-04 | Day2 事件契约冻结前检查表 v0.1 DRAFT（§8 失败语义、§9 安全/隔离/遗忘/幂等映射、§13 阻塞项 HD-D2E-01..07） | `docs/architecture/D2_EVENT_CONTRACT_PRE_FREEZE_CHECKLIST_V0.1.md` | SOURCE_VERIFIED（在库） |
| SEC-S-05 | Day2 E Gate0 业务预审报告 v0.1（Gate 结论 `BLOCKED`，HD-D2E-B01..B07，C 三对象 `C_D2_EVIDENCE_MISSING`） | `docs/project-management/D2_E_GATE0_BUSINESS_REVIEW.md` | SOURCE_VERIFIED（在库） |
| SEC-S-06 | 证据索引 v1.1（UDS Echo Spike `HOST_VERIFIED`、Embedding 调用 `HOST_VERIFIED`、真实 Kaiming Hook `BLOCKED`、KYSEC `UNVERIFIED`、C 三派生对象缺证） | `evidence/index.yaml` | SOURCE_VERIFIED（在库） |
| SEC-S-07 | 安全设计文档框架（占位，无实质内容，非本任务修改范围） | `docs/security/README.md` | SOURCE_VERIFIED（框架占位） |
| SEC-S-08 | 项目 README（业务代码未开始、Memory Service/C++ Bridge/Memory Client/Hook/Kaiming 通道/性能指标均未完成） | `README.md` | SOURCE_VERIFIED（在库） |

### 1.2 局限声明

- **基线 DOCX 未导入**：赛题原文、总体架构 SOP v1.1、官方 SDK 与 OS Agent 能力边界等基线文档当前均未被 Git 仓库跟踪（`docs/baseline/README.md` 标注「待人工导入」），本文件不得声称已从实体 DOCX 独立核验任何字段语义或安全边界。
- **C 轨真实宿主取证缺位**：`MemoryContext`/`ToolExecutionEvent`/`TurnFinalizedEvent` 真实宿主事件结构在当前仓库不可见，全部 `C_D2_EVIDENCE_MISSING`（HD-D2E-B04）。本文件涉及上述对象的内容均为**业务候选语义**，不是官方 SDK 原生字段，也不是已批准协议。
- **D 轨关键证据未闭合**：真实 Kaiming Hook `BLOCKED`（HD-D2E-B01）、KYSEC 最小授权 `UNVERIFIED`（HD-D2E-B02）、幂等/取消/断线重连 `UNTESTED`/`NOT_FOUND`（D-06/07/08）、deadline 超时语义 `PARTIAL`（D-05）、回退原版完整恢复 `PARTIAL`（HD-D2E-B03）。
- **`evidence/gate0` 硬编码凭据风险**：仓库中被跟踪文件含疑似真实凭据（High/Critical 级，**本文件不输出任何明文**），处置按 `SECURITY.md` 密钥泄露流程，属安全渠道，不在本契约闭合范围（HD-D2E-B07）。
- **证据状态口径**：本文件遵循业务契约 §1.2 与追踪矩阵双轴口径——业务侧 `PENDING`/`UNVERIFIED`/`PARTIAL`/`CANDIDATE_FOR_FREEZE`；SDK/实现侧 `UNTESTED`/`SOURCE_VERIFIED`/`ABI_VERIFIED`/`HOST_VERIFIED`/`PARTIAL`/`NOT_FOUND`/`BLOCKED`/`DEFERRED`/`PENDING_C_CONFIRMATION`/`PENDING_D_CONFIRMATION`/`PENDING_B_CONFIRMATION`/`PENDING_E_CONFIRMATION`/`UNVERIFIED`。**无真实银河麒麟宿主证据的事项一律不得标 `HOST_VERIFIED`/`PASS`**。
- **本文件引用既有宿主证据（UDS Echo Spike、Embedding 调用）仅为来源引用**，不是本文件新取得的 Runtime 证据；本任务 `runtime_required=false`，不新增 Runtime 验证。

### 1.3 本文件与业务契约的关系

- 业务契约（`D3_MEMORY_BUSINESS_CONTRACT_V1.md`）冻结 E 轨道可单方面冻结的**业务语义**（七类业务概念、字段语义、枚举、业务规则）；本文件在其安全侧面之上，把**安全红线**抽离为「规则 ID + 前置/必须/禁止/证据/状态/阻断级别」的可验收结构，并与 G0-E-01..14 案例建立双向可追踪映射。
- 本文件**不修改、不覆盖**业务契约任何内容；两文件冲突时以业务契约为业务语义基准，安全红线以本文件为验收基准，差异由 E/D Reviewer 裁定。
- 本文件全部规则若未在麒麟真实环境执行对应验证，一律保持 `UNVERIFIED`/`BLOCKED`/`PENDING_*`/`C_D2_EVIDENCE_MISSING`/`PARTIAL`/`UNTESTED`/`NOT_FOUND`，**不得写成 `HOST_VERIFIED`/`PASS`**。

---

## 二、安全规则结构与证据状态口径

### 2.1 规则结构（每条至少七列）

| 列名 | 含义 |
|------|------|
| 规则 ID | 形如 `SEC-UI-01`、`SEC-SENS-01`、`SEC-LLM-01`、`SEC-TOOL-01`、`SEC-FORGET-01`、`SEC-IDEMP-01`、`SEC-CTX-01`、`SEC-AUTH-01` |
| 前置条件 / 输入 | 该规则适用前提与触发输入（如「事件含 S-01..S-04 类型」「`forget_mode=session` 且 `target_selector` 用户输入」） |
| 必须行为 | 业务层强制动作（如「跨用户读取必须以请求 `user_id` 为过滤键」「`resolved_target_ids` 由遗忘规则引擎产出」） |
| 禁止行为 | 显式禁令（逐条对齐 G0-E-01..14 案例 `forbidden_outcomes`，**不得减少**） |
| 所需证据 | 验证该规则需要的 Runtime 证据（对应案例 `required_evidence_level`，目标 `HOST_VERIFIED`） |
| 当前证据状态 | 沿用业务契约 §1.2 双轴口径：`UNVERIFIED`/`PENDING_C_CONFIRMATION`/`PENDING_D_CONFIRMATION`/`PENDING_B_CONFIRMATION`/`PENDING_E_CONFIRMATION`/`PARTIAL`/`DEFERRED`/`BLOCKED`/`UNTESTED`/`NOT_FOUND`/`C_D2_EVIDENCE_MISSING` |
| 阻断级别 | `CRITICAL` / `HIGH` / `MEDIUM` 三档 |

### 2.2 证据状态口径

- 每条规则「所需证据」均为目标 `HOST_VERIFIED`（对应案例 `required_evidence_level`），**不等于当前已达成**。
- 案例集全部案例（G0-E-01..14）当前状态为 `BLOCKED`/`UNTESTED`，本契约如实沿用，**不提升为 `HOST_VERIFIED`/`PASS`**。
- 真实 KYSEC 规则、真实 Kaiming Hook、真实断线重连等未有证据时，本契约保持 `UNVERIFIED`/`BLOCKED`/`DEFERRED`/`UNTESTED`/`NOT_FOUND`，不得写成通过。

---

## 三、敏感信息类别（S-01..S-09，沿用标注规范 §5.1）

> 以下编号与语义**严格沿用** `datasets/ANNOTATION_GUIDELINE_V0.1.md` §5.1，**不得静默改号或改义**。标注处理含义：命中该类载荷不得写入任何字段的文本值，仅可写入脱敏占位或仅用 ID 引用。

| 编号 | 敏感类型 | 识别要点（标注规范原文） | 标注处理（标注规范原文） |
|------|---------|--------------------------|--------------------------|
| S-01 | API Key | 特征前缀（`sk-`、`api-` 等）、高熵字符串、常见服务商 Key 模式 | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_API_KEY]`；强制不形成记忆 |
| S-02 | Token | JWT 特征（三段 Base64，`eyJ` 开头）、Bearer Token、OAuth Token | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_TOKEN]`；强制不形成记忆 |
| S-03 | 密码 | 明文密码字符串、含「密码」「password」上下文的赋值操作 | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_PASSWORD]`；强制不形成记忆 |
| S-04 | 私钥 | PEM 头尾标记（`-----BEGIN` / `-----END`）、`.pem` `.key` 文件内容 | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_PRIVATE_KEY]`；强制不形成记忆 |
| S-05 | 身份证号 | 18 位数字组合（含末位 X）、地址/生日等关联上下文 | 标记 `sensitivity=high`；标注字段填 `[REDACTED_ID_NUMBER]`；不写入记忆 |
| S-06 | 手机号 | 11 位手机号码模式、国家代码前缀、通讯录关联上下文 | 标记 `sensitivity=high`；标注字段填 `[REDACTED_PHONE]`；不写入记忆 |
| S-07 | 敏感路径 | 绝对路径含 `/etc/shadow`、`~/.ssh/`、系统关键目录、用户私密目录 | 标记 `sensitivity=high`；标注字段填 `[REDACTED_PATH]`；路径原文不写入记忆 |
| S-08 | 跨用户数据 | 数据内容不属于当前 `user_id`（如包含另一用户的聊天记录、偏好、操作日志） | 标记 `sensitivity=critical`；标注字段仅记录 `sensitivity=critical` 与 `isolation_violation=true`；正文不写入、不进入可检索索引 |
| S-09 | 硬删除正文 | 经 `ForgetPlan` 执行硬删除的条目内容 | 已完成硬删除的正文不得在 SQLite、Vector、FTS5、日志、导出文件和备份中留存明文可检索残留。标注记录仅保留 `forget_plan_id` 和遗忘执行时间戳，不保留正文 |

**敏感过滤标注字段（§5.2）**：`sensitivity_level`（none/low/medium/high/critical）、`sensitive_type`（如 S-01、S-03）、`should_ignore`（含 S-01 至 S-04 或 S-08 的 Turn 必须为 `true`）、`redacted_summary`（不含任何敏感原文的简要描述）。

**跨用户隔离（§5.3）**：`user_id` 是用户级数据隔离硬约束；`user_id` 取值禁止由模型/LLM 生成，必须来自宿主侧业务事件或外部输入；一个会话内不得出现两个不同的 `user_id`（构造错误需标记 `isolation_violation=true` 且 `sensitivity=critical`）；负向隔离要求不同 `user_id` 必须无法读取、更新或删除其他用户的条目，任何跨用户操作尝试必须被标记 `isolation_violation=true`、`sensitivity=critical`。

---

## 四、安全规则分组

> 每组规则的「禁止行为」逐条对齐 G0-E-01..14 对应案例 `forbidden_outcomes`，**不减少任何一项**；禁止行为末尾标注来源案例 ID。

### A. 用户隔离组（SEC-UI-01..07）

> `user_id` 是写入、检索、上下文注入、冲突处理、遗忘与审计六类操作共用的业务隔离键（对齐业务契约 §7.1、标注规范 §5.3）。**不得把某一层过滤（如仅检索过滤）描述为对其他层复核的替代**——每一层都必须独立受 `user_id` 边界约束。

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-UI-01 | 写入 `MemorySourceEvent`/`Preference`/`Knowledge`/`Conflict`/`ForgetPlan` | 以请求 `user_id` 为归属键写入，数据归属始终以 `user_id` 为准 | 跨 `user_id` 写入；`user_id` 由 LLM 生成或伪造导致隔离键失控（G0-E-04 禁止项 3） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` + `PENDING_D_CONFIRMATION` | CRITICAL |
| SEC-UI-02 | 检索请求含 `user_id` | 以 `user_id` 硬过滤；跨用户命中在融合前丢弃并审计 | user_a 记忆进入 user_b 的 `model_request` 或返回结果（G0-E-04 禁止项 1）；跨用户命中未在融合前被丢弃（G0-E-04 禁止项 2）；跨用户操作未被标记 `isolation_violation=true`（G0-E-04 禁止项 4） | `HOST_VERIFIED` | `C_D2_EVIDENCE_MISSING` | CRITICAL |
| SEC-UI-03 | `MemoryContext.selected_memory_ids` 生成阶段 | 注入前回源 SQLite 当前版本并复核 `user_id`、状态、有效期、敏感等级与冲突状态 | 跨用户 `selected_memory_ids` 注入 `model_request` | `HOST_VERIFIED` | `C_D2_EVIDENCE_MISSING` | CRITICAL |
| SEC-UI-04 | `Conflict` 涉及条目派生 `user_id` | 冲突双方必须属同一 `user_id`；跨用户不产生冲突 | 模型生成 `user_id`/`resolution_status` 最终值/`resolved_by`（对齐业务契约 §7.5 第 6 档约束） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` | HIGH |
| SEC-UI-05 | `ForgetPlan.target_selector` 解析阶段 | `resolved_target_ids` 仅含当前 `user_id` 条目 | `resolved_target_ids` 含 `user_id != 请求 user_id` 条目；跨用户遗忘执行（G0-E-04 禁止项 3；标注规范 §5.3 负向隔离反例 6 尝试 3） | `HOST_VERIFIED` | `UNVERIFIED` | CRITICAL |
| SEC-UI-06 | 任何写入/检索/注入/遗忘审计记录 | 审计记录绑定 `user_id`；跨用户隔离违规标记 `isolation_violation=true` 且 `sensitivity=critical` | 审计无 `user_id`；隔离违规操作未留审计（G0-E-04 禁止项 4） | `HOST_VERIFIED` | `UNVERIFIED` | HIGH |
| SEC-UI-07 | 所有核心业务对象 + 端到端会话 | `user_id` 来自宿主侧业务事件或外部输入；`actor_id` 同源（同一 `user_id` 下可有多个 `actor_id`） | LLM 生成 `user_id`/`actor_id`（G0-E-04 禁止项 3；对齐业务契约 §7.1/§7.10） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` | CRITICAL |

### B. 敏感信息与原始载荷红线组（SEC-SENS-01..07）

> 原始敏感载荷（命中 S-01..S-09）**不得进入普通日志、Vector 元数据或可回显 MemoryContext**；需要追踪时使用安全引用或脱敏摘要。`sensitivity` 终判由敏感过滤规则引擎产出，模型不得覆写或降级。

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-SENS-01 | 载荷命中 S-01..S-09 且进入日志路径 | 以脱敏占位（如 `[REDACTED_API_KEY]`）/仅 ID 引用记录 | 完整敏感 Context 原文进入普通日志（G0-E-01 禁止项 2；G0-E-02 禁止项 2） | `HOST_VERIFIED` | `UNVERIFIED`（`PENDING_D_CONFIRMATION` 日志边界） | CRITICAL |
| SEC-SENS-02 | 载荷命中 S-01..S-09 且进入向量索引路径 | Vector 仅保存脱敏摘要或仅 ID 引用（对齐业务契约 §7.7、S-09） | 敏感明文写入 Vector metadata | `HOST_VERIFIED` | `PENDING_B_CONFIRMATION` + `UNVERIFIED` | CRITICAL |
| SEC-SENS-03 | `MemoryContext` 组装阶段 | 注入前过滤；`sensitive_excluded_count` 正确计数并留审计 | 敏感原文进入 `model_request`（G0-E-02 禁止项 1）；敏感原文以明文出现在案例、标注或导出文件（G0-E-02 禁止项 3）；敏感原文进入可回显 MemoryContext（G0-E-01/G0-E-02 关联） | `HOST_VERIFIED` | `C_D2_EVIDENCE_MISSING` | CRITICAL |
| SEC-SENS-04 | 须追踪原始载荷（证据链/溯源） | 使用安全引用/脱敏摘要；`raw_payload_ref`/`content_ref`/`source_reference` 不承载明文（对齐业务契约 §3.4/§7.7） | 用原始载荷回显代替脱敏摘要；失败项敏感文件名/内容进入知识（G0-E-09 禁止项 1） | `HOST_VERIFIED` | `PENDING_D_CONFIRMATION` | HIGH |
| SEC-SENS-05 | 载荷敏感度定级路径 | `sensitivity` 由敏感过滤规则引擎产出；分级标准待 E 终审（HD-ANNO-05） | 模型覆写/降级 `sensitivity` 终判（G0-E-02 禁止项 4；G0-E-13 关联禁止项） | `HOST_VERIFIED` | `PARTIAL`（分级标准未终审） | CRITICAL |
| SEC-SENS-06 | 事件入库阶段 | 命中 S-01..S-04/S-08 的 Turn 标 `should_ignore=true`、`source_business_status=ignored`，不进入后续抽取与存储；错误消息按 S-01..S-09 处理，不得泄漏敏感原文（对齐业务契约 §7.7；G0-E-06 禁止项 3） | `ignored` 事件进入抽取流水线；错误消息明文泄漏敏感原文（G0-E-06 禁止项 3） | `HOST_VERIFIED` | `UNVERIFIED`（`PENDING_E_CONFIRMATION` 终审分级 + D 实现侧） | HIGH |
| SEC-SENS-07 | `hard_delete=true` 遗忘执行后 | SQLite/Vector/FTS5/日志/导出/备份均无可检索明文残留（S-09） | 硬删除正文在任一存储层留下可检索明文残留（G0-E-03 禁止项 2） | `HOST_VERIFIED` | `PENDING_D_CONFIRMATION` + `PENDING_B_CONFIRMATION` | CRITICAL |

### C. LLM 权限组（SEC-LLM-01..08）

> 对齐业务契约 §7.10「禁止模型生成字段清单」。LLM 只能参与候选抽取/辅助判断，**不得生成或覆写** `user_id`、`actor_id`、`occurred_at`、最终 `sensitivity`、授权范围、删除目标最终集合等安全终判字段。

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-LLM-01 | 所有核心业务对象 + 端到端会话 | `user_id` 来自宿主侧业务事件/外部输入 | LLM 生成 `user_id`（对齐业务契约 §7.1/§7.10；G0-E-04 禁止项 3） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION`（宿主字段取证） | CRITICAL |
| SEC-LLM-02 | `MemorySourceEvent` | `actor_id` 来自宿主侧业务事件/外部输入 | LLM 生成 `actor_id`（对齐业务契约 §7.1/§7.10） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION`（宿主字段取证） | CRITICAL |
| SEC-LLM-03 | `MemorySourceEvent` | `occurred_at` 必须来自宿主侧业务事件 | LLM 生成 `occurred_at`（对齐业务契约 §7.10） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION`（宿主时间字段取证） | HIGH |
| SEC-LLM-04 | `Conflict` 消解路径 | 冲突最终结果由消解规则引擎/系统计算产出（对齐业务契约 §7.5 第 6 档） | 模型直接产出 `resolution_status` 已决值/`resolution_strategy`/`resolution_confidence`/`resolved_by` 最终结果 | `HOST_VERIFIED` | `PENDING_B_CONFIRMATION` + `PENDING_E_CONFIRMATION`（消解规则待 B/E，HD-SCHEMA-04） | HIGH |
| SEC-LLM-05 | `sensitivity` 最终定级 | 由敏感过滤规则引擎产出 | 模型覆写/降级（已由 SEC-SENS-05 冻结，此处仅交叉引用，不复述） | `HOST_VERIFIED` | 交叉引用 SEC-SENS-05（`PARTIAL`） | CRITICAL |
| SEC-LLM-06 | `ForgetPlan` 执行路径 | `resolved_target_ids`/`requires_confirmation` 最终判定/`affected_count` 最终值/整体删除执行决策由遗忘规则引擎/系统计算产出（对齐业务契约 §7.6；G0-E-03） | LLM 生成上述遗忘最终决策 | `HOST_VERIFIED` | `UNVERIFIED`（遗忘规则引擎未实现未验证） | CRITICAL |
| SEC-LLM-07 | `MemorySourceEvent` 接入层 | `idempotency_key` 由业务事件/系统生成（接入层）；不可由 `event_id` 替代其业务语义（对齐业务契约 §5.1；G0-E-11 禁止项 2） | LLM 生成 `idempotency_key`；以 `event_id` 替代 `idempotency_key` 作为去重键 | `HOST_VERIFIED` | `UNVERIFIED`（D 幂等机制 `UNTESTED`，D-07） | HIGH |
| SEC-LLM-08 | 候选抽取/辅助判断路径 | LLM 候选输出标记 `memory_status=candidate`；六档冲突优先级中第 6 档不得覆盖第 1–5 档（对齐业务契约 §7.5） | 第 6 档（模型推测）覆盖第 1–5 档高可信来源（G0-E-14 禁止项 3）；候选自述未标记 `memory_status=candidate`（G0-E-14 禁止项 4）；模型自述作为事实真源/已验证结论 | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` + `PENDING_E_CONFIRMATION`（六档优先级待 SOP v1.1 导入复核，HD-SCHEMA-15） | CRITICAL |

### D. Tool 证据可信度组（SEC-TOOL-01..07）

> 对齐业务契约 §7.8 与 D2 检查表 §8。**只有真实 Tool 执行证据允许形成成功知识；禁止把模型文本声称的成功当作真实执行证据。** `execution_status != success`（含 failure/cancelled/timeout）不得形成成功知识；失败、取消、超时、部分执行、副作用、回滚在业务上必须分别处理，不得混为一类。

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-TOOL-01 | `ToolExecutionEvent.execution_status=success` | 仅真实 Tool 成功证据允许形成成功知识；成功但属瞬态上下文（一次性查询）不得形成长期记忆（标注规范正例 7）；副作用信息不得由模型自述 | 无真实 Tool 结果即形成成功知识（G0-E-05 禁止项 1）；未记录副作用即沉淀记忆（G0-E-05 禁止项 2）；把瞬态上下文（一次性查询）沉淀为长期记忆（G0-E-05 禁止项 3）；以模型自述替代真实 Tool 成功证据（G0-E-05 禁止项 4） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` | CRITICAL |
| SEC-TOOL-02 | `ToolExecutionEvent.execution_status=failure` | `should_form_memory=false`；仅可沉淀带条件失败经验（`knowledge_type=failure_experience`，G0-E-06）；错误消息脱敏后写入 `error_message_safe` | 从失败信息推断并沉淀成功知识（G0-E-06 禁止项 1）；把失败信息当作成功结果记录（G0-E-06 禁止项 2）；错误消息明文泄漏敏感原文（G0-E-06 禁止项 3）；`should_form_memory` 被置为 `true`（G0-E-06 禁止项 4） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` | CRITICAL |
| SEC-TOOL-03 | `ToolExecutionEvent.execution_status=cancelled`（用户或系统取消） | 按取消处理，不形成完成事实/成功知识；取消前已产生副作用须记录 `side_effect=true` 并评估 `rollback_required`；审计取消原因与时间（G0-E-07）；`cancelled` 是否入 D3 正式候选待 E/B/D 复核（HD-D2E-05） | 取消后形成完成事实或成功知识（G0-E-07 禁止项 1）；已有副作用未记录即忽略（G0-E-07 禁止项 2）；已产生副作用但未判断是否需回滚（G0-E-07 禁止项 3）；把 cancelled 混为 success 处理（G0-E-07 禁止项 4） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` + `PENDING_E_CONFIRMATION`（HD-D2E-05） | HIGH |
| SEC-TOOL-04 | `ToolExecutionEvent.execution_status=timeout` | 结果保持未知，`should_form_memory=false`；超时事件与重试/取消关联留审计（G0-E-08） | 超时后被推断为成功并沉淀（G0-E-08 禁止项 1）；超时后被推断为失败并沉淀（G0-E-08 禁止项 2）；以超时结果冒充真实 Tool 成功证据（G0-E-08 禁止项 3）；超时未记录结构化错误或审计（G0-E-08 禁止项 4） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` + `PARTIAL`（deadline 超时语义 D-05） | CRITICAL |
| SEC-TOOL-05 | `ToolExecutionEvent.execution_status=partial`（批量部分成功） | 仅成功部分可形成知识；失败项敏感内容脱敏（`[REDACTED_FILENAME]`）；记录 `side_effect` 与适用条件；评估 `rollback_required` 并留审计（G0-E-09）；`partial` 是否入 D3 正式候选待 E/B/D 复核（HD-D2E-05） | 失败项敏感文件名/内容进入知识（G0-E-09 禁止项 1）；未记录副作用即沉淀（G0-E-09 禁止项 2）；未标注回滚需求（G0-E-09 禁止项 3）；把 partial 整体视为完全成功或完全失败（G0-E-09 禁止项 4） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` + `PENDING_E_CONFIRMATION`（HD-D2E-05） | HIGH |
| SEC-TOOL-06 | 有副作用的执行需要回滚（`rollback_required=true`） | 记录 `rollback_required`/`rollback_status`（done/failed/N/A）；回滚成功与失败分别记录残留风险；回滚不视为成功、不得形成成功知识；审计回滚时间与结果（G0-E-10）；SQLite 事务回滚可行性待 D | 把回滚视为成功并沉淀成功知识（G0-E-10 禁止项 1）；未记录 `rollback_status`（G0-E-10 禁止项 2）；忽略回滚残留风险（G0-E-10 禁止项 3）；回滚失败未标记且无审计（G0-E-10 禁止项 4） | `HOST_VERIFIED` | `PENDING_D_CONFIRMATION`（SQLite 事务可行性） | HIGH |
| SEC-TOOL-07 | 模型文本声称 Tool 成功但无 `ToolExecutionEvent` | 无真实 Tool 证据时不得形成已验证事实或成功知识；自述仅可作为 `memory_status=candidate` 候选且不得升级（G0-E-14；已与 SEC-LLM-08 交叉） | 无 Tool 证据即形成已验证事实（G0-E-14 禁止项 1）；无 Tool 证据即形成成功知识（G0-E-14 禁止项 2） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` | CRITICAL |

### E. 精准遗忘组（SEC-FORGET-01..05）

> 对齐业务契约 §7.6、标注规范 §2.5/§5.3。遗忘以业务对象级别的 `resolved_target_ids` 为精准范围；必须先预览再确认再执行；跨用户拒绝；已遗忘内容不得再次召回或注入上下文。

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-FORGET-01 | `target_selector` 用户输入 → 目标解析 | 系统解析 `target_selector` 生成 `resolved_target_ids`；按 `resolved_target_ids` 精准范围执行 | `resolved_target_ids` 由 LLM 生成；模糊关键词/时间窗口粗略删除后声称已精准遗忘；未按 `resolved_target_ids` 精准范围执行导致误删或漏删（G0-E-03 禁止项 3） | `HOST_VERIFIED` | `UNVERIFIED` | CRITICAL |
| SEC-FORGET-02 | 遗忘计划创建与执行 | 先预览 → 用户确认 → 执行；状态机 `pending→previewing→awaiting_confirmation→executing→completed/failed/rolled_back`（对齐业务契约 §5.5 `status` 七值） | 跳过预览/确认直接执行；`requires_confirmation` 最终判定由 LLM 产出 | `HOST_VERIFIED` | `UNVERIFIED` | CRITICAL |
| SEC-FORGET-03 | `forget_mode` 与 `target_*` 字段 | 五种模式（`single_item`/`session`/`topic`/`time_window`/`full_reset`）按 `target_type`/`target_id`/`target_session_id`/`target_topic`/`target_time_range` 校验；`full_reset` 安全边界待 E/D（HD-SCHEMA-06） | 跨 `forget_mode` 边界扩展删除范围 | `HOST_VERIFIED` | `PENDING_E_CONFIRMATION` + `PENDING_D_CONFIRMATION` | CRITICAL |
| SEC-FORGET-04 | 跨用户遗忘请求 | 仅当前 `user_id` 条目可被解析并删除 | 跨用户遗忘执行（已由 SEC-UI-05 冻结，此处仅交叉引用，不复述） | `HOST_VERIFIED` | 交叉引用 SEC-UI-05（`UNVERIFIED`） | CRITICAL |
| SEC-FORGET-05 | 遗忘执行后重新检索 / MemoryContext 组装 | `forgotten_excluded_count` 正确计数；遗忘后重新检索与 MemoryContext 组装时已遗忘目标被排除 | 已遗忘记忆重新注入 `model_request` 或检索返回（G0-E-03 禁止项 1）；硬删除后留可检索明文（G0-E-03 禁止项 2，已与 SEC-SENS-07 交叉） | `HOST_VERIFIED` | `UNVERIFIED` + `PENDING_D_CONFIRMATION` | CRITICAL |

### F. 幂等 / 重试组（SEC-IDEMP-01..02）

> 对齐业务契约 §5.1、D2 检查表 §9。`idempotency_key` 用于接入侧幂等与去重，不可由 `event_id` 替代；同一逻辑回合仅一个有效终结事件。

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-IDEMP-01 | 相同 `idempotency_key` 重复投递 | 仅首次沉淀记忆；后续重复请求去重命中并留审计（G0-E-11） | 相同 `idempotency_key` 重复沉淀记忆（G0-E-11 禁止项 1）；以 `event_id` 替代 `idempotency_key` 作为去重键（G0-E-11 禁止项 2）；重复事件产生重复偏好/知识条目（G0-E-11 禁止项 3）；幂等命中无审计记录（G0-E-11 禁止项 4） | `HOST_VERIFIED` | `UNVERIFIED`（D 无幂等机制 `UNTESTED`，D-07） | CRITICAL |
| SEC-IDEMP-02 | Stop 后 Retry 生成 ≥2 个终结候选 | 同一逻辑回合仅一个有效 `TurnFinalizedEvent`；重试终结通过 `retry_of_turn_id` 关联；`is_final` 语义与重试语境一致；终结唯一性留审计（G0-E-12） | 同一逻辑回合产生多个有效 `TurnFinalizedEvent`（G0-E-12 禁止项 1）；Retry 生成重复的终结沉淀（G0-E-12 禁止项 2）；重试终结事件未关联 `retry_of_turn_id`（G0-E-12 禁止项 3）；以模型自述或推理替代真实 Turn 边界证据（G0-E-12 禁止项 4） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION`（C 取证 Turn 边界/重试机制） | HIGH |

### G. 上下文隔离组（SEC-CTX-01）

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-CTX-01 | `MemoryContext` 注入 `model_request` | UI 与聊天数据库保留原始用户文本；MemoryContext 只进 `model_request`；普通日志不保存完整敏感 Context；注入失败须记录 `injection_status=failed` 并留审计（G0-E-01） | 聊天数据库或 UI 中的原始用户文本被 Memory Context 覆盖或改写（G0-E-01 禁止项 1）；注入失败但未记录 `injection_status=failed` 且无审计（G0-E-01 禁止项 3） | `HOST_VERIFIED` | `C_D2_EVIDENCE_MISSING` | CRITICAL |

### H. 授权组（SEC-AUTH-01）

| 规则 ID | 前置条件 / 输入 | 必须行为 | 禁止行为 | 所需证据 | 当前证据状态 | 阻断级别 |
|---------|----------------|----------|----------|----------|--------------|----------|
| SEC-AUTH-01 | 事件含 `consent_scope`（如 `memory_only`）且内容超范围 | 超 `consent_scope` 的记忆不沉淀；缺少授权访问被拒绝并审计；`sensitivity` 终判不被模型覆写（G0-E-13） | 沉淀超出 `consent_scope` 的记忆（G0-E-13 禁止项 1）；敏感记忆未经授权即沉淀（G0-E-13 禁止项 2）；授权检查缺失导致跨 consent 边界写入（G0-E-13 禁止项 3）；拒绝操作无审计记录（G0-E-13 禁止项 4） | `HOST_VERIFIED` | `PENDING_C_CONFIRMATION` + `PENDING_E_CONFIRMATION`（同意模型未定） | CRITICAL |

---

## 五、Day2 Gate 0 案例到安全规则映射表

> 下表覆盖 G0-E-01..14 全部 14 例；每例 `forbidden_outcomes` 已完整迁移到对应规则「禁止行为」列（见第四章），**不减少任何一项**。案例 `required_evidence_level` 全部为 `HOST_VERIFIED`、`current_status` 全部为 `BLOCKED`/`UNTESTED`，本契约如实沿用，**不提升为 `HOST_VERIFIED`/`PASS`**。

| 案例 ID | 案例标题 | `forbidden_outcomes` 数量 | 映射规则 ID | 阻断级别 |
|---------|----------|---------------------------|-------------|----------|
| G0-E-01 | 正常 Memory Context 注入与原文隔离 | 3 | SEC-CTX-01、SEC-SENS-01、SEC-SENS-03 | CRITICAL |
| G0-E-02 | 敏感记忆过滤 | 4 | SEC-SENS-01、SEC-SENS-03、SEC-SENS-05、SEC-SENS-06 | CRITICAL |
| G0-E-03 | 已遗忘/硬删除记忆排除 | 3 | SEC-FORGET-05、SEC-SENS-07、SEC-FORGET-01 | CRITICAL |
| G0-E-04 | 跨用户隔离 | 4 | SEC-UI-01、SEC-UI-02、SEC-UI-05、SEC-UI-06、SEC-UI-07 | CRITICAL |
| G0-E-05 | 真实 Tool 成功 | 4 | SEC-TOOL-01、SEC-LLM-08 | CRITICAL |
| G0-E-06 | Tool 失败 | 4 | SEC-TOOL-02、SEC-SENS-06 | CRITICAL |
| G0-E-07 | Tool 取消 | 4 | SEC-TOOL-03 | HIGH |
| G0-E-08 | Tool 超时 | 4 | SEC-TOOL-04 | CRITICAL |
| G0-E-09 | 部分执行后失败 | 4 | SEC-TOOL-05、SEC-SENS-04、SEC-TOOL-06 | HIGH |
| G0-E-10 | 回滚成功或失败 | 4 | SEC-TOOL-06 | HIGH |
| G0-E-11 | 重复事件幂等去重 | 4 | SEC-IDEMP-01、SEC-LLM-07 | CRITICAL |
| G0-E-12 | Stop/Retry 唯一终结事件 | 4 | SEC-IDEMP-02、SEC-LLM-08 | HIGH |
| G0-E-13 | 缺少授权 | 4 | SEC-AUTH-01、SEC-SENS-05 | CRITICAL |
| G0-E-14 | 模型自述不得冒充真实 Tool 结果 | 4 | SEC-TOOL-07、SEC-LLM-08 | CRITICAL |

**追踪说明**：G0-E-01/G0-E-02 的敏感原文相关禁止项由 SEC-SENS-01/03 承载；G0-E-03 的硬删除明文残留由 SEC-SENS-07、已遗忘召回由 SEC-FORGET-05、精准范围由 SEC-FORGET-01 承载；G0-E-04 的隔离键失控禁止项由 SEC-UI-01/05/07 共同承载；G0-E-13 的敏感终判不被覆写由 SEC-SENS-05 承载。

---

## 六、真实能力证据保留规则

以下无真实银河麒麟宿主证据或实现未完成的项，**一律如实保留 `UNVERIFIED`/`BLOCKED`/`DEFERRED`/`PARTIAL`/`UNTESTED`/`NOT_FOUND`/`C_D2_EVIDENCE_MISSING`，不得写成 `HOST_VERIFIED`/`PASS`**：

| 证据项 | 当前状态 | 依据 |
|--------|----------|------|
| 真实 Kaiming Hook（真实 kylin-aiassistant → UDS） | `BLOCKED`（闭源二进制、无源码、无签名权限、Socket 路径硬编码） | HD-D2E-B01；evidence D2-1-KAIMING-HOOK |
| KYSEC 最小授权真实规则 | `UNVERIFIED`（仅 ACL 模拟，未写真实规则） | HD-D2E-B02；evidence D2-6-KYSEC-SCOPE |
| 幂等/取消/断线重连机制 | `UNTESTED`/`NOT_FOUND`（D-07/D-06/D-08 代码无实现） | HD-D2E-B02 关联；D2 预审报告第六节 |
| deadline 超时语义（`deadline_ms` 与 `CLIENT_TIMEOUT` 联动） | `PARTIAL`（D-05 未独立验证） | D2 预审报告第六节 |
| 回退基线（标准 rollback 未在麒麟执行、进程残留） | `PARTIAL`（等价受限证据） | HD-D2E-B03；evidence D2-7-ROLLBACK-BASELINE |
| C 三个派生对象（MemoryContext/ToolExecutionEvent/TurnFinalizedEvent）真实宿主取证 | `C_D2_EVIDENCE_MISSING` | HD-D2E-B04；D2 预审报告第五节 |
| 基线 DOCX（01–06） | 未导入（`docs/baseline/` 无实体文件） | HD-D2E-B05 |
| 案例集 G0-E-01..14 在麒麟执行 | `UNTESTED`（全部为设计稿未执行） | HD-D2E-B06 |
| `evidence/gate0` 硬编码凭据风险（已识别 High/Critical，**不输出明文**） | `HD-D2E-B07`，处置属安全渠道，不在本契约闭合范围 | D2 预审报告第八节 |
| UDS Echo Spike / Embedding 调用既有宿主证据 | `HOST_VERIFIED`（**仅来源引用**，非本文件新取证；UDS Spike 为模拟客户端，非真实 Kaiming Hook） | evidence/index.yaml |

---

## 七、FREEZE_BLOCKERS（冻结阻断项登记，不闭合）

> 完整沿用业务契约 §10 行表：HD-D2E-B01..B07 + HD-SCHEMA 关键待办 + HD-ANNO-05/08/09（敏感分级终审、架构审查报告导入、`expression_type` 终审）。**本契约只登记，不替其他轨道闭合**；不得为了完成 Day3 而删除或弱化任何一项。

| 编号 | 阻断项 | 影响范围 | 责任轨道 | 所需证据 / 解除条件 |
|------|--------|----------|----------|---------------------|
| HD-D2E-B01 | 真实 Kaiming Hook 阻断（闭源二进制、无源码、无签名权限、Socket 路径硬编码） | D 真实 UDS 可达性、真实 Hook 构建/安装/启动 | D（需人工决策路线） | Gate 1 获取 SDK 源码/签名权限，或降级方案（LD_PRELOAD/socat/SDK 合作） |
| HD-D2E-B02 | KYSEC 最小授权仅 ACL 模拟，未写真实规则 | D 授权边界 | D（需环境/权限协调） | KYSEC 开发者文档 + 测试环境授权 + 最小规则集验证 |
| HD-D2E-B03 | 回退基线未闭合（标准 rollback 未在麒麟执行、进程残留、原版完整恢复未证实） | D 安装与回退 | D | 补跑标准 rollback（`test_rollback.sh` 已入库），补齐前后 SHA/owner/mode/ACL/包版本对比与进程清理 |
| HD-D2E-B04 | C 真实 Context/Tool/Turn 取证缺位 | 三个派生对象字段与失败语义 | C | C 在麒麟 VM 完成真实宿主取证回填 |
| HD-D2E-B05 | 基线 DOCX（01–06）未导入 | 字段语义待权威基线终审 | 团队/E | 人工导入 `docs/baseline/` 并版本核验 |
| HD-D2E-B06 | 案例集 G0-E-01..14 全部为设计稿未执行 | C/D Day2 验收 | C/D/E | C/D 在真实环境执行对应案例（`required_evidence_level` 均为 `HOST_VERIFIED`） |
| HD-D2E-B07 | `evidence/gate0` 硬编码凭据风险（已识别 High/Critical，不输出明文） | 安全红线 | 安全渠道 | 按 SECURITY.md 密钥泄露流程处理（轮换 + 清理历史 + 通知 + 记录） |
| HD-ANNO-05 | 敏感分级标准与识别规则 E 终审（影响 SEC-SENS-05/06） | 敏感过滤规则 | E | E 终审分级标准 |
| HD-SCHEMA-06 | 遗忘级联范围与 `full_reset` 安全边界（影响 SEC-FORGET-03） | ForgetPlan | E/D | E/D 确认 |
| HD-SCHEMA-04 | 冲突判定阈值与消解规则（影响 SEC-LLM-04） | Conflict | B | B 确认 |
| HD-SCHEMA-05 | Vector 与 SQLite 真源一致性策略（影响 SEC-SENS-02/07） | Vector | B | B 确认 |
| HD-SCHEMA-12/15/16 | C 麒麟取证宿主事件结构、SOP v1.1 导入复核（影响 SEC-UI-*、SEC-LLM-*） | 宿主字段/枚举 | C/团队/E | C 取证 + SOP 导入 |

---

## 八、不可冻结项声明（本文件不是实现方案）

本文件是**业务/安全验收契约**，不是技术实现方案。下列技术实现事项全部 `DEFERRED` 或 `待对应轨道确认`，本文件**不冻结任何实现细节**：

| 技术实现事项 | 责任轨道 | 本文件状态 |
|-------------|---------|------------|
| 敏感过滤规则引擎的具体实现（正则/规则集/去重策略） | E | DEFERRED（HD-ANNO-05） |
| 用户隔离的过滤表达式、SQLite 约束、索引或分表方案 | D | DEFERRED（`PENDING_D_CONFIRMATION`） |
| Vector 过滤/元数据脱敏的 Collection Schema 与索引布局 | B | DEFERRED（`PENDING_B_CONFIRMATION`） |
| 删除/遗忘的物理执行逻辑与 SQLite 事务回滚 | D | DEFERRED（`PENDING_D_CONFIRMATION`） |
| ACL/KYSEC 规则文件与最小授权规则集 | D | DEFERRED（HD-D2E-B02） |
| IPC 鉴权、UDS 用户身份绑定、`protocol_version`/`request_id`/幂等机制 | D | DEFERRED（`PENDING_D_CONFIRMATION`） |
| C++ 结构体、Provider 接口、QML 侧实现 | C/D | DEFERRED |
| 断线重连、取消、deadline 超时的传输层实现 | D | DEFERRED（D-05/06/07/08） |

**任何规则当前 `PENDING_*`/`UNVERIFIED`/`PARTIAL`/`BLOCKED`/`UNTESTED`/`NOT_FOUND`/`C_D2_EVIDENCE_MISSING` 状态不得因本契约冻结而被解读为实现已完成或宿主已验证。**

---

## 九、变更记录与冻结为团队基线条件

### 9.1 变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-08-09 | 候选初稿：在业务契约 v1 候选安全侧面之上，形成记忆模块安全验收契约 v1 候选。冻结 E 轨道负责的用户隔离（SEC-UI-01..07）、敏感信息与原始载荷红线（S-01..S-09 沿用 + SEC-SENS-01..07）、LLM 权限（SEC-LLM-01..08）、Tool 证据可信度（SEC-TOOL-01..07）、精准遗忘（SEC-FORGET-01..05）、幂等/重试（SEC-IDEMP-01..02）、上下文隔离（SEC-CTX-01）、授权边界（SEC-AUTH-01）共 38 条可验收规则；建立 G0-E-01..14 案例到安全规则的可追踪映射；登记 FREEZE_BLOCKERS 与真实能力证据保留状态；无真实宿主证据项一律保持 `UNVERIFIED`/`BLOCKED`/`DEFERRED`/`PARTIAL`/`UNTESTED`/`NOT_FOUND`/`C_D2_EVIDENCE_MISSING`。状态 `CANDIDATE_FOR_FREEZE`。 | E 轨道 |

### 9.2 升级为团队冻结基线（v1.0 冻结基线）的条件

以下条件**全部满足**后方可视为团队冻结基线：

1. **非作者 D Reviewer 批准**本文件（E 不批准 E 自己的变更）；
2. 本文件对应 PR 合并；
3. HD-D2E-B01..B07 阻断项均有明确处置（见第七章）；
4. HD-SCHEMA/HD-ANNO 关键待办经权威基线导入/对应轨道取证后闭合；
5. C 轨真实宿主取证回填（`PENDING_C_CONFIRMATION` 字段解除）；
6. D 轨 UDS/IPC 协议草案完成、KYSEC/回退/幂等/取消证据补齐（`PENDING_D_CONFIRMATION` 解除）；
7. B 轨 Vector 元数据脱敏与真源一致性策略确认（`PENDING_B_CONFIRMATION` 解除）；
8. G0-E-01..14 案例在银河麒麟 V11 x86_64 真实环境执行且 `required_evidence_level=HOST_VERIFIED` 证据回填；
9. Evidence Reviewer 确认本文件所有证据状态标注与当时实际证据等级一致（无 `HOST_VERIFIED` 虚标）。

在满足以上条件之前，本文件保持 `CANDIDATE_FOR_FREEZE`，**不得作为过滤/删除/ACL/KYSEC/SQLite 约束/Vector 过滤/IPC 鉴权实现的唯一依据**。

---

> **本文档到此结束。后续修订将在 D Reviewer 审查、C 麒麟取证、D 协议草案、B 检索契约冻结、SOP v1.1 导入与基线 DOCX 导入后按 A–E 轨道反馈进行。**
