# Day6E 多源开发集统一错误分类表 v1

- **版本**：v1
- **状态**：`DEVSET_V1`
- **阶段定位**：Day6 / E 轨道 / 多源开发集错误归因分类表
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **用途**：为本仓库多源融合开发集 `D6_MULTISOURCE_DEVSET_V1.jsonl` 提供统一的错误归因代码（error code registry）。开发集样本的 `expected_error_codes` 字段**只能引用本表已定义代码**；本表为评测归因层使用，**不是生产契约**，不新增或冻结 `MemorySourceEvent`、`SourceType`、`EventType` 等共享生产枚举。
- **非 Gold 声明**：本分类表服务于 `DEVSET_V1` 开发集的错误归因与测试，**不是**最终 Gold Label 判定规则、不是回归集或封存测试集的错误基准；后续仍需人工双人复核、切分与封存后另行冻结正式错误基准。
- **任务性质声明**：本任务为纯 Markdown + 数据集 + 测试任务（`runtime_required=false`、`runtime_commands=[]`），不产生 Runtime 结论，不更新 `evidence/index.yaml`。

---

## 一、编号规则

1. 全表共十个错误域，域代码分别为：`Q`、`SRC`、`SEC-SENS`、`SEC-PII`、`SEC-UI`、`PROV`、`TOOL`、`LIFE`、`DUP`、`CONTRACT`。
2. 每个域内从 `001` 开始递增编号，三位数字补零；代码格式为 `{DOMAIN}-{NNN}`，其中域代码可包含连字符（如 `SEC-SENS-001`）。
3. 一个样本可引用多个错误代码（数组）；无错误时使用空数组 `[]`。
4. 阻断级别仅使用 `CRITICAL` / `HIGH` / `MEDIUM` 三档（对齐 Day3 安全验收契约 §2.1 阻断级别口径），**不新增其他档位**。
5. 代码全局唯一；已发布的代码不得改名或改义，只允许新增（追加新代码或在既有域内递增编号）。
6. 测试解析规则：`evaluation/test_d6_multisource_devset.py` 使用正则

   ```
   \b((?:SEC-SENS|SEC-PII|SEC-UI|Q|SRC|PROV|TOOL|LIFE|DUP|CONTRACT)-\d{3})\b
   ```

   从本文件提取全部已定义代码，并校验开发集 `expected_error_codes` 中每个元素均存在定义。

| 域代码 | 域名称 | 编号格式 | 阻断级别范围 | 覆盖语义 |
|--------|--------|----------|-------------|----------|
| Q | Quality | Q-NNN | MEDIUM / HIGH | 质量门禁不达标（completeness / extractability / overall / freshness-validity） |
| SRC | Source | SRC-NNN | MEDIUM / HIGH | 数据源类型 / 分类验证异常 |
| SEC-SENS | Sensitive Information | SEC-SENS-NNN | CRITICAL / HIGH | 敏感信息命中（S-01/S-02/S-03/S-04/S-07/S-09）及 payload 未检查 |
| SEC-PII | PII | SEC-PII-NNN | HIGH / MEDIUM | 个人身份信息（S-05/S-06） |
| SEC-UI | User Isolation | SEC-UI-NNN | CRITICAL | 跨用户隔离违规（S-08）、user_id 不一致、模型生成 user_id |
| PROV | Provenance | PROV-NNN | HIGH / MEDIUM | 来源溯源异常（event_id 伪造、身份注入、溯源证据缺失） |
| TOOL | Tool Execution | TOOL-NNN | CRITICAL / HIGH | Tool 执行状态异常（failed/cancelled/timeout/partial/无证据自述/payload 未检查） |
| LIFE | Lifecycle | LIFE-NNN | MEDIUM / HIGH | 记忆生命周期状态异常（candidate/expired/临时不可升级） |
| DUP | Duplication | DUP-NNN | HIGH / MEDIUM | 幂等 / 重复事件异常 |
| CONTRACT | Contract/Schema | CONTRACT-NNN | HIGH / MEDIUM | 契约 / Schema 校验异常（缺字段 / 枚举非法 / 类型错误 / 多余字段 / 配置冲突） |

---

## 二、错误域定义

### 2.1 Q（Quality）

> 语义对齐：A 轨六维质量评分（completeness / validity / reliability / freshness / consistency / extractability）与 `QualityScore.eligible_for_extraction` 门禁；质量不达标但无安全拒绝时按 `audit_only` 处理（`quality_not_eligible`）。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| Q-001 | completeness 完整性不达标：必填 / 条件字段缺失导致完整性分低于门禁 | MEDIUM | 事件缺 `source_reference`，溯源信息不完整 |
| Q-002 | extractability 可提取性不达标：无可抽取的结构化载荷 | MEDIUM | 事件载荷为纯自由文本，无结构化内容可抽取 |
| Q-003 | overall 总质量门禁不达标：`eligible_for_extraction=false` | MEDIUM | 六维总分低于门禁，事件只能 `audit_only` 不得进入抽取 |
| Q-004 | freshness / validity 时效或值性校验不达标 | MEDIUM | `occurred_at` 早于 `captured_at`，时间秩序异常 |

### 2.2 SRC（Source）

> 语义对齐：`SourceType` 七值（chat / tool_result / manual_config / recollect / file / meeting / voice）为**生产契约**；开发集 `source_family`（tool_result / behavior_candidate / manual_config）为**评测分类字段，不是生产契约**。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| SRC-001 | 数据源分类非法：`source_family` 不在合法集合 | MEDIUM | 出现未注册的 `source_family` |
| SRC-002 | 来源与内容不符：载荷语义与声明来源分类矛盾 | MEDIUM | `manual_config` 载荷实为行为日志内容 |
| SRC-003 | behavior 候选被当作已冻结 `SourceType`（禁止；C 轨尚未冻结 `behavior`→`source_type` 映射） | HIGH | 把 `behavior_candidate` 直列 `MemorySourceEvent.source_type=behavior` |

### 2.3 SEC-SENS（Sensitive Information）

> 语义对齐：标注规范 §5.1 S-01/S-02/S-03/S-04/S-07/S-09 与安全契约 SEC-SENS 组；命中强制不形成记忆、不写入明文。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| SEC-SENS-001 | S-01 API Key 敏感命中 | CRITICAL | 载荷含 `sk-*` 形式 Key |
| SEC-SENS-002 | S-02 Token / JWT 敏感命中 | CRITICAL | 载荷含 `eyJ` 开头三段 JWT |
| SEC-SENS-003 | S-03 密码敏感命中 | CRITICAL | `password=` 赋值操作 |
| SEC-SENS-004 | S-04 私钥 / PEM 敏感命中 | CRITICAL | 载荷含 `-----BEGIN PRIVATE KEY-----` |
| SEC-SENS-005 | S-07 敏感路径命中 | HIGH | 载荷含 `/etc/shadow`、`~/.ssh/` |
| SEC-SENS-006 | S-09 硬删除正文泄漏 | CRITICAL | 遗忘条目正文在存储层残留可检索明文 |
| SEC-SENS-007 | Tool Result 原始载荷未做安全检查（`payload_security_checked=false`） | HIGH | `tool_result` 事件 payload 未检查仍试图进入抽取 |

### 2.4 SEC-PII（PII）

> 语义对齐：标注规范 §5.1 S-05/S-06；命中不写入记忆。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| SEC-PII-001 | S-05 身份证号敏感命中 | HIGH | 18 位数字（含末位 X）组合 |
| SEC-PII-002 | S-06 手机号敏感命中 | MEDIUM | 11 位手机号码模式 |

### 2.5 SEC-UI（User Isolation）

> 语义对齐：安全契约 SEC-UI-01..07、标注规范 §5.3；`user_id` 为隔离硬键，禁止模型生成。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| SEC-UI-001 | S-08 跨用户数据：载荷包含非当前 `user_id` 内容 | CRITICAL | 事件载荷含另一用户偏好 / 操作日志 |
| SEC-UI-002 | 请求上下文 `user_id` 与事件 `user_id` 不一致 | CRITICAL | `ctx.user_id != event.user_id` |
| SEC-UI-003 | `user_id` 由模型 / 正文生成或伪造（含 admin 提权） | CRITICAL | 正文声称 `user_id=admin` 请求提权 |

### 2.6 PROV（Provenance）

> 语义对齐：安全契约 SEC-TOOL-07、G0-E-14；只有真实事件证据允许溯源。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| PROV-001 | 来源事件伪造：`event_id` / `source_event_id` 指向不存在的真实事件 | HIGH | 引用 `evt_attacker_id` 无真实对应事件 |
| PROV-002 | 溯源证据缺失：无法定位到真实会话 / 事件 | HIGH | 模型自述结果无真实事件支撑 |
| PROV-003 | 身份 / 溯源注入：正文自称管理员或伪造来源身份 | HIGH | 正文自称 admin 要求按管理员溯源 |

### 2.7 TOOL（Tool Execution）

> 语义对齐：安全契约 SEC-TOOL-01..07、业务契约 §7.8；`execution_status != success` 不得形成成功知识。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| TOOL-001 | failed Tool 被用于形成成功知识（或未按 `failure_experience` 处理） | CRITICAL | failed 事件产出成功知识条目 |
| TOOL-002 | cancelled 被当作完成事实 | CRITICAL | 用户取消后仍沉淀完成结论 |
| TOOL-003 | timeout 被推断为成功 / 失败结论 | CRITICAL | 超时事件被冒充为结论 |
| TOOL-004 | partial 被整体视为完全成功或完全失败 | HIGH | 批量部分成功整体沉淀为成功 |
| TOOL-005 | 无真实执行的模型自述成功 / 不可信正文声称 | CRITICAL | 无 `ToolExecutionEvent` 却自称 tool success |
| TOOL-006 | Tool Result 原始载荷绕过安全检查而进入抽取 | CRITICAL | payload 未检查仍需抽取放行 |

### 2.8 LIFE（Lifecycle）

> 语义对齐：业务契约 §7.4/§7.9、标注规范 §2.1；临时偏好不升级、`candidate` 不自动晋升、过期不当作活跃。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| LIFE-001 | 临时偏好 / 一次性指令被升级为持久记忆 | HIGH | `is_temporary=true` 却获得跨会话持久资格 |
| LIFE-002 | 过期 / 失效条目被当作活跃条目 | MEDIUM | `expired` 条目仍可被检索召回 |
| LIFE-003 | `memory_status=candidate` 被声称 `verified` 并跳过复核升级 | HIGH | 候选未复核即被当作已确认 |
| LIFE-004 | 未复核候选被当作正式知识使用 | MEDIUM | `candidate` 未复核进入正式结论 |

### 2.9 DUP（Duplication）

> 语义对齐：安全契约 SEC-IDEMP-01/02、业务契约 §5.1；`idempotency_key` 用于去重，`event_id` 不可替代。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| DUP-001 | 相同 `idempotency_key` 重复投递导致重复沉淀 | HIGH | 重试事件重复入库产生重复条目 |
| DUP-002 | 重复事件产生重复偏好 / 知识条目 | MEDIUM | 同一语义内容多次沉淀 |
| DUP-003 | 以 `event_id` 替代 `idempotency_key` 作去重键 | MEDIUM | 去重键业务语义错用 |

### 2.10 CONTRACT（Contract / Schema）

> 语义对齐：pipeline.schemas `MemorySourceEvent` 校验策略（必填字段缺失 → 拒绝、类型错误 → 拒绝、未知高风字段 → `extra="forbid"` 拒绝）。

| 代码 | 含义 | 阻断级别 | 示例 |
|------|------|----------|------|
| CONTRACT-001 | 必填字段缺失 / 配置冲突 | HIGH | 事件缺 `user_id`；同一 `preference_key` 冲突值并存 |
| CONTRACT-002 | 枚举值非法 | HIGH | `source_family` 拼写错误、未知状态值 |
| CONTRACT-003 | 字段类型错误 | MEDIUM | `preference_value` 应为字符串实为对象 |
| CONTRACT-004 | 多余未知字段（`extra="forbid"` 违规） | MEDIUM | 事件含未声明的额外字段 |

---

## 三、Error Code Registry（测试解析用汇总表）

> 下表为本表全部已定义错误代码，供测试正则解析与开发集引用。**开发集 `expected_error_codes` 中任何元素必须能在下表中找到**。

| 域 | 已定义代码 |
|----|-----------|
| Q | Q-001、Q-002、Q-003、Q-004 |
| SRC | SRC-001、SRC-002、SRC-003 |
| SEC-SENS | SEC-SENS-001、SEC-SENS-002、SEC-SENS-003、SEC-SENS-004、SEC-SENS-005、SEC-SENS-006、SEC-SENS-007 |
| SEC-PII | SEC-PII-001、SEC-PII-002 |
| SEC-UI | SEC-UI-001、SEC-UI-002、SEC-UI-003 |
| PROV | PROV-001、PROV-002、PROV-003 |
| TOOL | TOOL-001、TOOL-002、TOOL-003、TOOL-004、TOOL-005、TOOL-006 |
| LIFE | LIFE-001、LIFE-002、LIFE-003、LIFE-004 |
| DUP | DUP-001、DUP-002、DUP-003 |
| CONTRACT | CONTRACT-001、CONTRACT-002、CONTRACT-003、CONTRACT-004 |

---

## 四、与既有 reason_code 对齐说明（语义映射，非冻结追踪）

> 以下为 Day6E Task1 `SourceAdmissionPolicy` 15 个固定 `reason_code` 与本分类表代码的**语义对齐说明**（开发集归因参考，**不建立正式双向追踪表**，避免扩大范围）。`reason_code` 为生产实现层审计码，本分类表代码为开发集评测归因码，两者不互替。

| `reason_code`（既有实现） | 本表对齐代码 | 说明 |
|---------------------------|--------------|------|
| `invalid_pipeline_result` | CONTRACT-001 / CONTRACT-003 | 结果对象类型不可信，契约层异常 |
| `invalid_context` | CONTRACT-001 | 上下文对象不可信，契约层异常 |
| `user_id_mismatch` | SEC-UI-002 | 请求与事件 `user_id` 不一致 |
| `event_should_ignore` | SEC-SENS 组（S-01..S-04）/ SEC-UI-001（S-08） | 命中强制忽略的敏感 / 跨用户载荷 |
| `event_status_ignored` | SEC-SENS 组 | 已标记 `ignored` 的事件不得进入抽取 |
| `security_gate_triggered` | SEC-SENS-007 / TOOL-006 | 安全门禁触发（含 payload 未检查） |
| `event_sensitive_high` | SEC-PII-001 / SEC-PII-002 / SEC-SENS-005 | `sensitivity=high` 敏感命中 |
| `event_sensitive_critical` | SEC-SENS-001..004 / SEC-UI-001 | `sensitivity=critical` 敏感命中 |
| `tool_payload_unchecked` | SEC-SENS-007 / TOOL-006 | Tool payload 未做安全检查 |
| `event_status_cancelled` | TOOL-002 | cancelled 不得形成完成事实 |
| `event_status_timeout` | TOOL-003 | timeout 不得推断结论 |
| `quality_not_eligible` | Q-003 | 总质量门禁不达标 → `audit_only` |
| `ok_failed_tool_failure_experience_only` | TOOL-001（正确语义） | failed 仅允许失败经验路径 |
| `ok_partial_preference_only` | TOOL-004（正确语义） | partial 仅允许偏好路径 |
| `ok` | （无错误） | 正常放行，无错误归因 |

---

## 五、与敏感类型 S-01..S-09 对齐说明

> 严格沿用标注规范 §5.1 与安全契约 §三 的编号与语义，**不改号不改义**；开发集敏感样本一律使用虚构占位内容。

| 敏感类型 | 本表对齐代码 | 阻断级别 |
|----------|--------------|----------|
| S-01 API Key | SEC-SENS-001 | CRITICAL |
| S-02 Token | SEC-SENS-002 | CRITICAL |
| S-03 密码 | SEC-SENS-003 | CRITICAL |
| S-04 私钥 | SEC-SENS-004 | CRITICAL |
| S-05 身份证号 | SEC-PII-001 | HIGH |
| S-06 手机号 | SEC-PII-002 | MEDIUM |
| S-07 敏感路径 | SEC-SENS-005 | HIGH |
| S-08 跨用户数据 | SEC-UI-001 | CRITICAL |
| S-09 硬删除正文 | SEC-SENS-006 | CRITICAL |

---

## 六、使用约束

1. 开发集 `expected_error_codes` 只能引用本表已定义代码；无错误时使用空数组 `[]`。
2. 本表为 `DEVSET_V1` 归因层定义，**不新增 / 不冻结** `MemorySourceEvent`、`SourceType`、`EventType` 等共享生产契约。
3. 本表**不宣称**已冻结为最终 Gold 错误基准、回归集或封存测试基准；冻结需经人工双人复核、切分与封存流程后另行确认。
4. 本表不输出任何真实用户数据、密钥或凭据。

---

## 七、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-08-24 | 初稿：定义十个错误域（Q / SRC / SEC-SENS / SEC-PII / SEC-UI / PROV / TOOL / LIFE / DUP / CONTRACT）及编号规则、阻断级别、示例与 Error Code Registry；建立与既有 15 个 `reason_code` 及 S-01..S-09 的语义对齐说明。状态 `DEVSET_V1`，服务于 `D6_MULTISOURCE_DEVSET_V1.jsonl` 错误归因。 | E 轨道 |