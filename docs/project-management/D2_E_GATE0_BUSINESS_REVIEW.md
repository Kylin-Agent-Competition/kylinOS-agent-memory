# Day2 E 轨道 Gate 0 业务预审报告（v0.1）

- **版本**：v0.1
- **状态**：DRAFT 预审报告，非冻结基线
- **阶段定位**：Day2 / E 轨道 / Gate 0 业务预审
- **用途**：基于当前仓库可核验的 C/D 交付物、证据路径和真实日志，对 `MemoryContext`、`ToolExecutionEvent`、`TurnFinalizedEvent` 及 D 轨道 UDS/Hook/KYSEC/安装/回退逐项给出基于当前证据的分项结论，形成进入 D3 冻结前必须补齐的材料清单
- **报告性质**：本报告是 D3 Gate 的**预审输入**，不是 D3 冻结决议；是否进入 D3 由 D/E Reviewer 评审决定

---

## 一、审查目标与边界

- **审查作者**：E 轨道（本报告作者为 E，最终 Reviewer 仍为 D 轨道，E 不批准 E 自己的变更）
- **审查范围**：C 轨道 Day2 三个派生业务对象（`MemoryContext`、`ToolExecutionEvent`、`TurnFinalizedEvent`）与 D 轨道 UDS/Hook/KYSEC/安装/回退证据
- **审查基准**：当前分支 `docs/e-d2-event-gate-review` 可见仓库内容、`evidence/index.yaml`、原始日志与代码现状，**不预设历史结论**
- **本批次不执行 L2**：`runtime_required=false`，本报告仅审查已有证据，不进入银河麒麟虚拟机补跑 C/D 测试，不以 WSL 静态检查代替宿主证据
- **明确不修改**：不修改任务 1 检查表（`docs/architecture/D2_EVENT_CONTRACT_PRE_FREEZE_CHECKLIST_V0.1.md`）、任务 2 案例集（`datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json`）、C/D 代码、日志、证据文件、部署脚本、Runtime 脚本与数据库；不冻结 D3 共享契约；不执行 push、不创建 PR、不合并

## 二、审查元数据

| 项目 | 值 |
|------|-----|
| 审查分支 | `docs/e-d2-event-gate-review` |
| 审查时 HEAD Commit | `343d76a04d68fe65e9905008ab63efcac175b160` |
| 审查日期 | 2026-08-08 |
| 作者（E 轨道） | E 轨道（业务预审） |
| Reviewer（D 轨道） | D 轨道（最终 Reviewer，未批准本报告前不视为通过） |
| 工作区状态 | 审查时 `git status` 无未提交修改 |

## 三、输入证据清单

证据按四态分类：**已核验（仓库内可核验）**、**未入库（人工已知但未入仓库）**、**缺失**、**计划**。

### 3.1 已核验（仓库内可核验）

| 证据项 | 路径 | 适用 Commit | 证据状态 |
|--------|------|------------|----------|
| 任务 1 事件契约冻结前检查表 v0.1 DRAFT | `docs/architecture/D2_EVENT_CONTRACT_PRE_FREEZE_CHECKLIST_V0.1.md` | 当前 HEAD | SOURCE_VERIFIED（文档在库） |
| 任务 2 业务验收案例集 v0.1 DRAFT（14 案例） | `datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json` | 当前 HEAD | SOURCE_VERIFIED（文档在库） |
| 追踪矩阵 v0.1 DRAFT（REQ-01..07 均 PENDING） | `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md` | 当前 HEAD | SOURCE_VERIFIED（文档在库） |
| Day1 记忆业务 Schema v0.1 DRAFT | `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md` | 当前 HEAD | SOURCE_VERIFIED（文档在库） |
| 证据索引 v1.1 | `evidence/index.yaml` | 当前 HEAD | SOURCE_VERIFIED（索引在库） |
| UDS Echo Spike 宿主证据（ECHO-001..009） | `evidence/gate0_echo/final/evidence.jsonl` | tested_commit `830e694` | HOST_VERIFIED（模拟客户端 6/6、systemd 12/12；D2-1 独立调查为宿主调查） |
| Kaiming Hook 调查最终报告（真实 Hook） | `evidence/gate0_echo/d2_1_evidence/D2_1_Final_Evidence_Report.md` | 当前 HEAD | BLOCKED（闭源二进制，宿主调查如实记录失败） |
| D2-3 部署启动日志 | `evidence/gate0_echo/day2_results/D2_3_deploy_startup.log` | 当前 HEAD | HOST_VERIFIED（CMake/dev 模式） |
| D2-4 Socket 路径审计 | `evidence/gate0_echo/day2_results/E9_socket_path_audit.log` | 当前 HEAD | HOST_VERIFIED（带限制） |
| D2-6 KYSEC 授权口径 | `evidence/gate0_echo/day2_results/D2_6_kysec_scope.log` | 当前 HEAD | UNVERIFIED（仅 ACL 模拟） |
| D2-7 回退对照基线 | `evidence/gate0_echo/day2_results/E8_rollback_baseline_compare.log` | 当前 HEAD | HOST_VERIFIED（带限制，等价 PARTIAL） |
| 回退逐项补证（P1-6..P1-10） | `evidence/gate0_echo/day2_results/P1_6_to_P1_10_rollback_detail.log` | 当前 HEAD | PARTIAL（rollback 脚本当时 NOT_FOUND，AFTER 数据等于 BEFORE） |
| KYSEC 记录一致性（P2-3） | `evidence/gate0_echo/day2_results/P2_3_kysec_consistency.log` | 当前 HEAD | SOURCE_VERIFIED（sysfs 不可用，CLI 可用） |
| Echo 服务端代码（协议实现） | `os-agent-integration/echo/memory_echo_server.py` | 当前 HEAD | SOURCE_VERIFIED |
| 模拟客户端代码（协议实现） | `os-agent-integration/echo/kaiming_memory_client.cpp` | 当前 HEAD | SOURCE_VERIFIED |
| KYSEC 授权脚本（当前仓库版本已自标 UNVERIFIED） | `os-agent-integration/echo/kysec_authorize.sh` | 当前 HEAD | SOURCE_VERIFIED（仅 ACL；头部已加 UNVERIFIED 标注、已支持 --socket，但无修正后宿主复验） |
| 回退脚本（当前仓库已存在） | `os-agent-integration/echo/test_rollback.sh` | 当前 HEAD | SOURCE_VERIFIED（未在麒麟补跑标准 rollback） |
| OS Agent 集成模块 README | `os-agent-integration/README.md` | 当前 HEAD | SOURCE_VERIFIED（仅目录和职责边界） |
| OS Agent Hook 任务卡（设计稿，非证据） | `os-agent-integration/D1_OS_Agent_调用链与Hook_Spike_任务卡.md` | 当前 HEAD | SOURCE_VERIFIED（任务卡，非宿主取证） |
| D3 Provider 契约草稿（TurnFinalizedEvent dataclass） | `docs/day3/06_provider_contract_v1.md` | 当前 HEAD | SOURCE_VERIFIED（前向草稿，非冻结契约，非宿主证据） |

### 3.2 未入库（人工已知，未在仓库内形成证据）

- 基线 DOCX（01 官方 SDK 能力边界 v1.1、02 总体架构 SOP v1.1、03 环境配置手册、04 Agent/LLM 使用指南）：`docs/baseline/README.md` 均标注「待人工导入」，实体文件未被 Git 跟踪
- 麒麟 VM 测试时 VM 内无 git 客户端，evidence.jsonl 中 `tested_commit` 由开发机 HEAD 提供（`830e694`），并非 VM 内检出 commit

### 3.3 缺失

- C 轨道 `MemoryContext`/`ToolExecutionEvent`/`TurnFinalizedEvent` 真实宿主取证：全仓库 `evidence/` 与 index.yaml 无对应条目 → `C_D2_EVIDENCE_MISSING`
- D 真实 Kaiming Hook 证据：`D2-1-KAIMING-HOOK` → `BLOCKED`
- KYSEC 真实规则写入证据：`D2-6-KYSEC-SCOPE` → `UNVERIFIED`
- 幂等去重、取消、断线重连能力与证据 → `UNTESTED` / `NOT_FOUND`
- deadline 超时语义独立验证 → `PARTIAL`

### 3.4 计划（未来计划，尚未执行）

| 计划项 | 责任轨道 | 计划状态 |
|--------|----------|----------|
| C 麒麟 VM 官方 Tool/Turn/Context 真实取证 | C | 计划/未执行 |
| D Gate 1 SDK 源码申请与签名权限、KYSEC 测试授权、最小规则集验证 | D | 计划/未执行（Gate 1） |
| 标准 rollback 在麒麟补跑（test_rollback.sh 已入库） | D | 计划/未执行 |
| 基线 DOCX 人工导入 `docs/baseline/` 与版本核验 | 团队/E | 计划/未执行 |
| D3 共享契约冻结 | C/D/E | 计划/未执行（本报告为预审输入） |

## 四、HOST_VERIFIED 红线说明

- 依据 `runtime-validation.md` 与追踪矩阵第五节：`HOST_VERIFIED` 仅能由真实银河麒麟 V11 x86_64 虚拟机中实际执行的 L2/L3 Runtime Test 证据支持。
- 本报告中 `HOST_VERIFIED` **仅**用于以下既有宿主证据：UDS Echo Spike（ECHO-003 模拟客户端 6/6、ECHO-004 systemd 12/12）、D2-3 部署启动 Spike、D2-4 Socket 审计、D2-7 回退基线（带限制）。
- 以下无真实麒麟宿主证据的条目**均未使用** `HOST_VERIFIED`：C 三个派生对象（`C_D2_EVIDENCE_MISSING`）、真实 Kaiming Hook（`BLOCKED`）、KYSEC 真实规则（`UNVERIFIED`）、幂等/取消/断线重连（`UNTESTED`/`NOT_FOUND`）、deadline 超时语义（`PARTIAL`）。

## 五、C 轨审查

C 轨全部条目当前均为**业务候选设计**（任务 1 检查表、任务 2 案例集、OS Agent 任务卡），真实宿主取证在当前仓库不可见。以下每项均给出检查结论与缺证原因；结论一律标 `C_D2_EVIDENCE_MISSING`，不推断通过。

| 检查项 | 检查内容 | 路径或缺失原因 | 适用 Commit | 证据状态 | 结论 |
|--------|----------|----------------|------------|----------|------|
| C-01 UI/聊天库原文隔离 | UI 与聊天数据库保留原始用户文本，不被 Memory Context 覆盖或改写 | 无真实宿主取证；仅设计稿（任务卡 §原文隔离、案例 G0-E-01） | 当前 HEAD | 缺失 | C_D2_EVIDENCE_MISSING |
| C-02 MemoryContext 仅进入 model_request | 注入对象只进入模型请求，普通日志不保存完整敏感 Context | 无真实宿主取证；仅设计稿（任务卡、案例 G0-E-01） | 当前 HEAD | 缺失 | C_D2_EVIDENCE_MISSING |
| C-03 敏感与遗忘过滤 | `sensitive_excluded_count`、`forgotten_excluded_count`、S-01..S-09 敏感类型、已遗忘排除 | 无真实宿主取证；E 敏感分级标准亦未终审（案例 G0-E-02/03） | 当前 HEAD | 缺失 | C_D2_EVIDENCE_MISSING |
| C-04 跨用户隔离 | `user_id` 硬过滤、跨用户命中融合前丢弃、`user_id` 禁止模型生成 | 无真实宿主取证（案例 G0-E-04）；D UDS 用户身份绑定亦未冻结 | 当前 HEAD | 缺失 | C_D2_EVIDENCE_MISSING |
| C-05 Tool 成功/失败/取消/超时 | `execution_status` 四态真实语义、`result_ref`、`error_message_safe` | 无真实宿主取证（案例 G0-E-05..08）；echo Spike 的 `memory.retrieve` 返回空 contexts 为模拟，非真实 Tool 结果 | 当前 HEAD | 缺失 | C_D2_EVIDENCE_MISSING |
| C-06 部分执行与副作用 | `partial` 语义、`side_effect` 记录、失败项脱敏 | 无真实宿主取证（案例 G0-E-09）；`partial` 是否入 D3 候选待 E/B/D 复核 | 当前 HEAD | 缺失 | C_D2_EVIDENCE_MISSING |
| C-07 最终回合唯一性 | 同一逻辑回合仅一个有效 `TurnFinalizedEvent`、`is_final`、`stop_reason`、`retry_of_turn_id`、Stop/Retry | 无真实宿主取证（案例 G0-E-12）；D3 Provider 契约草稿仅有 dataclass 定义，非宿主行为证据 | 当前 HEAD | 缺失 | C_D2_EVIDENCE_MISSING |

**C 轨结论**：`MemoryContext`、`ToolExecutionEvent`、`TurnFinalizedEvent` 三个派生业务对象的真实宿主证据在当前仓库不可见，全部标记 `C_D2_EVIDENCE_MISSING`。不得将 echo Spike 的模拟 `memory.retrieve`（空 contexts）或 `docs/day3/` 契约草稿视为 C 轨真实取证。

## 六、D 轨审查

**声明**：本报告**不再沿用**历史 `BLOCKED_BY_D_DAY1` 预设结论（任务 1/任务 2 产物中曾以该标记 D 轨项）。以下逐项以当前 `evidence/index.yaml`、原始日志与代码现状判定；证据缺失时如实标记 `BLOCKED`、`UNVERIFIED`、`UNTESTED` 或 `NOT_FOUND`。

| 检查项 | 当前仓库证据 | 适用 Commit | 证据状态 | 结论 |
|--------|--------------|------------|----------|------|
| D-01 Kaiming→UDS 可达性 | 独立模拟客户端 `kaiming_memory_client` 6/6 PASS（ECHO-003、D2-1 调查报告）；真实 kylin-aiassistant Hook 闭源二进制、strings 未发现 QLocalSocket 引用、无 SDK 构建环境与签名权限（D2-1-KAIMING-HOOK） | tested_commit `830e694` / 当前 HEAD | 模拟客户端 HOST_VERIFIED；真实 Hook BLOCKED | 可达性仅限模拟客户端；真实 Hook 阻断 |
| D-02 长度前缀 JSON（4 字节 BE + JSON） | 服务端 `recv_message`/`send_message`（`>I` 长度 + JSON）与客户端 `htonl`/`ntohl` 实现；ECHO-003 宿主验证 | tested_commit `830e694` | Spike HOST_VERIFIED | Spike 协议通过；非 D3 冻结生产协议 |
| D-03 `protocol_version` | `PROTOCOL_VERSION="1.0"` 服务端常量，客户端请求携带 `"protocol_version":"1.0"`，响应回显 | tested_commit `830e694` | Spike HOST_VERIFIED | 字段存在并回显；无版本协商/不兼容拒绝，非冻结版本契约 |
| D-04 trace/request 关联 | 请求携带 `request_id`/`trace_id`，服务端 `build_response` 原样回显 | tested_commit `830e694` | Spike HOST_VERIFIED | 回显链路通过；无跨服务分布式追踪链 |
| D-05 超时/deadline | 客户端发 `deadline_ms:5000`，服务端实际用固定 `CLIENT_TIMEOUT=30.0`，二者未联动 | 当前 HEAD 代码 | PARTIAL | deadline 超时语义未独立验证 |
| D-06 取消 | 代码无取消请求机制、无取消后状态处理；ECHO 测试集无取消用例 | 当前 HEAD 代码 | NOT_FOUND | 取消语义不存在 |
| D-07 幂等去重 | 代码无 `idempotency_key` 去重逻辑、无重放保护；rapid 5/5 为并发压测，非幂等验证 | 当前 HEAD 代码 | UNTESTED | 幂等能力未实现未验证 |
| D-08 断线重连 | 客户端无重连策略；服务端仅读超时断连 | 当前 HEAD 代码 | NOT_FOUND | 断线重连未实现 |
| D-09 Socket 权限 | 服务端 socket 文件 chmod 0700、目录 0700；`kysec_authorize.sh` chmod 0700/0600 + setfacl ACL；D2-4 审计确认 dev 模式目录 0700，`/run` 非根审计权限不够 | tested_commit `830e694` | Spike HOST_VERIFIED（带限制） | 文件权限最小化通过；RuntimeDirectory 在 unit 卸载后不可确认 |
| D-10 KYSEC 最小授权 | `kysec_authorize.sh` 仅实施 chmod+ACL 纵深防御，**不写入真实 KYSEC 规则**；`/sys/kernel/security/kylin` sysfs 不存在；当前仓库版本脚本头部已自标 UNVERIFIED（D2-6 审计时缺失，P1-4/P0-3 修正后无宿主复验） | 当前 HEAD 代码 | UNVERIFIED | KYSEC 真实规则未验证 |
| D-11 Hook 构建/安装/启动 | 自建 echo 服务 CMake 构建 PASS、dev 模式 socket 创建 PASS、`--dev` 参数使能 PASS（D2-3-DEPLOY-STARTUP） | tested_commit `830e694` | 自建服务 HOST_VERIFIED；真实 Hook BLOCKED | 自建服务部署启动通过；真实 kylin-aiassistant Hook 安装/启动未实现 |
| D-12 原版恢复与回退后残留 | D2-7 回退对照：unit/service 移除确认、socket 清理确认、进程清理不干净（PID 残留）；审计时标准 `test_rollback.sh` NOT_FOUND（E8 exit 127），P1-6..P1-10 中「回退后一致」实为无回退执行时前后相同（AFTER 等于 BEFORE）；当前仓库已有 `test_rollback.sh` 但未在麒麟补跑标准 rollback | 当前 HEAD 代码 + 日志 | HOST_VERIFIED（带限制，等价 PARTIAL） | 原版完整恢复未获真实标准回退证明 |

**D 轨结论**：UDS 协议承载（长度前缀、protocol_version、request_id/trace_id 回显）、Socket 文件权限与自建服务部署启动在 Spike 层面有真实麒麟宿主证据（HOST_VERIFIED）；但真实 Kaiming Hook 仍 `BLOCKED`、KYSEC 最小授权 `UNVERIFIED`、幂等/取消/断线重连 `UNTESTED`/`NOT_FOUND`、deadline 超时语义 `PARTIAL`、原版恢复仅有受限证据。D 轨关键阻断**尚未全部关闭**。

## 七、字段覆盖摘要

复用任务 1 检查表（v0.1 DRAFT）覆盖范围，标注每个派生对象当前证据状态（均为候选字段，非冻结协议）：

| 候选分组 | 字段数 | 当前证据状态 | 说明 |
|----------|--------|--------------|------|
| 公共事件字段 | 14 | UNTESTED / PARTIAL | `sensitivity` PARTIAL（E 分级未终审），其余 UNTESTED |
| `MemoryContext` | 9 | C_D2_EVIDENCE_MISSING | 全部候选，未取证 |
| `ToolExecutionEvent` | 12 | C_D2_EVIDENCE_MISSING | 全部候选，未取证；`cancelled`/`partial` 入候选待复核 |
| `TurnFinalizedEvent` | 7 | C_D2_EVIDENCE_MISSING | 全部候选，未取证 |
| UDS/IPC 承载 | 9 | 逐项按第六节 | protocol_version/request_id/trace_id Spike HOST_VERIFIED；deadline PARTIAL；幂等/取消/断线重连 UNTESTED/NOT_FOUND；用户身份边界待 D/C |

**字段差异记录区（复用任务 1 第十一章）**：`collected_at` 与 Day1 `captured_at` 语义差异待 D/E 确认；`MemoryContext`、`TurnFinalizedEvent` 为 Day1 无对应对象的新增候选；`ToolExecutionEvent.cancelled` 为标注规范未定义的新增候选；`side_effect`/`rollback_*` 为新增。全部处于「待确认」，**关键字段差异尚未闭合**。

## 八、安全与用户隔离

| 业务用途 | 关键机制 | 当前证据状态 | 结论 |
|----------|----------|--------------|------|
| 原文隔离 | UI/聊天库保留原文；Memory Context 仅进入 `model_request`；普通日志不保存完整敏感 Context | C_D2_EVIDENCE_MISSING | 未取证 |
| 跨用户隔离 | `user_id` 硬过滤；跨用户命中融合前丢弃；`user_id` 禁止模型生成 | C_D2_EVIDENCE_MISSING | 未取证；D UDS 身份绑定未冻结 |
| 授权/consent_scope | `consent_scope` 承载与同意模型；超出范围不沉淀 | C_D2_EVIDENCE_MISSING | 未取证；E 终审同意模型未定 |
| 敏感过滤脱敏 | S-01..S-09、`sensitive_excluded_count`、`error_message_safe`、`arguments_ref` 脱敏 | C_D2_EVIDENCE_MISSING | 未取证 |
| 已遗忘/冲突排除 | `forgotten_excluded_count`、`conflict_excluded_count` | C_D2_EVIDENCE_MISSING | 未取证 |
| 幂等键 | `idempotency_key` 不可由 `event_id` 替代其业务语义 | D 无幂等机制 | UNTESTED |

**已识别安全风险（登记为技术债，不在本任务修改范围）**：仓库中被跟踪的文件 `evidence/gate0`（Python 脚本）包含**硬编码 SSH 与 sudo 密码（疑似真实凭据）**，违反 `SECURITY.md`「禁止提交密钥/密码」红线。本报告仅登记文件位置与风险类型（High/Critical 级），**不输出凭据明文**；处置须按 `SECURITY.md` 密钥泄露处理流程（立即轮换、清理 Git 历史、通知相关方、记录事件），并指向安全渠道。

## 九、失败语义

以下 8 类业务处理规则均来自任务 1 检查表第八节候选规则，当前均依赖 C 轨真实取证，故全部 `UNTESTED`（不得以设计稿或 echo 模拟代替）：

| 场景 | 业务处理规则 | 是否形成记忆 | 当前证据状态 |
|------|--------------|--------------|--------------|
| success | 仅真实 Tool 成功证据允许形成成功知识；瞬态上下文不形成长期记忆 | 视复用价值 | UNTESTED |
| failure | 不得从失败推断知识；`should_form_memory=false` | 否 | UNTESTED |
| cancelled | 按取消处理，不形成成功知识 | 否 | UNTESTED |
| timeout | 等同失败处理，不得以超时冒充成功 | 否 | UNTESTED |
| partial | 仅成功部分可形成知识；失败项脱敏（`[REDACTED_FILENAME]`） | 视成功部分 | UNTESTED |
| side_effect | 有副作用须记录；副作用不得由模型自述 | 视情况 | UNTESTED |
| rollback | 记录 `rollback_required`/`rollback_status`；回滚不视为成功 | 否 | UNTESTED（D 待确认 SQLite 事务可行性） |
| 模型自述 | 第 6 档不得覆盖第 1–5 档高可信来源；自述仅候选 | 仅候选 | UNTESTED |

## 十、阻塞项

| 编号 | 阻塞项 | 影响范围 | 当前状态 | 解除条件 | 责任轨道 |
|------|--------|----------|----------|----------|----------|
| HD-D2E-B01 | 真实 Kaiming Hook 阻断（闭源二进制、无源码、无签名权限、Socket 路径硬编码） | D 真实 UDS 可达性、真实 Hook 构建/安装/启动 | BLOCKED | Gate 1 获取 SDK 源码/签名权限，或降级方案（LD_PRELOAD/socat/SDK 合作） | D（需人工决策路线） |
| HD-D2E-B02 | KYSEC 最小授权仅 ACL 模拟，未写真实规则 | D 授权边界 | UNVERIFIED | KYSEC 开发者文档 + 测试环境授权 + 最小规则集验证 | D（需环境/权限协调） |
| HD-D2E-B03 | 回退基线未闭合（标准 rollback 未在麒麟执行、进程残留、原版完整恢复未证实） | D 安装与回退 | PARTIAL | 上传 `test_rollback.sh` 后补跑标准 rollback，补齐前后 SHA/owner/mode/ACL/包版本对比与进程清理 | D |
| HD-D2E-B04 | C 真实 Context/Tool/Turn 取证缺位 | 三个派生对象字段与失败语义 | C_D2_EVIDENCE_MISSING | C 在麒麟 VM 完成真实宿主取证回填 | C |
| HD-D2E-B05 | 基线 DOCX（01–06）未导入 | 字段语义待权威基线终审 | 待人工导入 | 人工导入 `docs/baseline/` 并版本核验 | 团队/E |
| HD-D2E-B06 | 本批次未执行 L2，案例集 G0-E-01..14 全部为设计稿未执行 | C/D Day2 验收 | UNTESTED | C/D 在真实环境执行对应案例 | C/D/E |
| HD-D2E-B07 | `evidence/gate0` 硬编码凭据风险 | 安全红线 | 已识别（不输出明文） | 按 SECURITY.md 密钥泄露流程处理 | 安全渠道 |

## 十一、必须补证清单（D3 冻结前）

| 证据项 | 责任轨道 | 解除条件 | 关联阻塞 |
|--------|----------|----------|----------|
| C 麒麟 VM 真实 `MemoryContext` 宿主取证（注入链路、原文隔离、敏感/遗忘排除、跨用户隔离） | C | 麒麟 VM 执行并保存环境探针、命令、exit code、stdout/stderr 与日志 | HD-D2E-B04 |
| C 麒麟 VM 真实 `ToolExecutionEvent` 取证（success/failure/cancelled/timeout、side_effect、result_ref、error_message_safe） | C | 同上；`cancelled`/`partial` 入候选经 E/B/D 复核 | HD-D2E-B04 |
| C 麒麟 VM 真实 `TurnFinalizedEvent` 取证（is_final、stop_reason、retry_of_turn_id、最终回合唯一性） | C | 同上 | HD-D2E-B04 |
| D 真实 Kaiming Hook 证据（真实 kylin-aiassistant → UDS 可达） | D | Gate 1 SDK 源码/签名权限或降级方案 | HD-D2E-B01 |
| D KYSEC 最小授权真实规则证据 | D | KYSEC 文档 + 测试授权 + 最小规则集验证 | HD-D2E-B02 |
| D 标准 rollback 麒麟复验（`test_rollback.sh` 已入库，补跑） | D | 执行标准回退 + 前后 SHA/owner/mode/ACL/包版本对比 + 进程清理 | HD-D2E-B03 |
| D 幂等/取消/断线重连能力与证据 | D | D3 协议草案 + 麒麟验证 | D-07/D-06/D-08 |
| D deadline 与 `CLIENT_TIMEOUT` 联动确认与验证 | D | 协议草案确认 + 麒麟验证 | D-05 |
| 基线 DOCX 导入与版本核验 | 团队/E | 人工导入 `docs/baseline/` | HD-D2E-B05 |
| `evidence/gate0` 凭据处置与历史清理 | 安全渠道 | 轮换 + 清理 + 通知 + 记录 | HD-D2E-B07 |

## 十二、D3 冻结建议

进入 D3 冻结最低条件逐项检查：

| 最低条件 | 当前状态 | 是否满足 |
|----------|----------|----------|
| C 真实 Context/Tool/Turn 证据齐全 | 全部 `C_D2_EVIDENCE_MISSING` | 否 |
| D 当前相关关键阻断均已关闭 | 真实 Hook BLOCKED、KYSEC UNVERIFIED、回退限制未闭合 | 否 |
| D 真实 UDS/Hook/KYSEC/回退证据齐全 | UDS Spike HOST_VERIFIED，但 Hook BLOCKED、KYSEC UNVERIFIED、回退受限 | 否 |
| 关键字段差异闭合 | 字段差异记录区全部待确认 | 否 |
| Critical=0 且未安排 High=0 | 未安排项含 `evidence/gate0` 硬编码凭据（已识别 High/Critical 风险）待人工处置确认 | 待确认（倾向否） |

**建议**：当前不满足 D3 冻结最低条件，**不建议进入 D3 冻结**。任务 1 检查表与任务 2 案例集中对 D 轨项的历史 `D_DAY1_PR_BLOCKED`/`BLOCKED_BY_D_DAY1` 标记**已被本报告以当前证据复核**：部分 D 项（UDS Spike、构建启动、回退基线受限证据）已解除历史预设，但真实 Hook、KYSEC、幂等/取消/回退完整恢复仍未关闭；C 轨三项证据全部缺位。D3 冻结与否由 D/E Reviewer 在补证完成后评审决定。

## 十三、最终Gate结论

**最终Gate结论：`BLOCKED`**

判定依据（以当前证据为准）：

1. 存在未关闭的关键阻断：真实 Kaiming Hook `BLOCKED`（闭源二进制 + 无签名权限）、KYSEC 最小授权 `UNVERIFIED`（仅 ACL 模拟）、回退原版恢复未获真实标准回退证明（进程残留）。
2. 关键 D2 真实证据缺失：C 轨道 `MemoryContext`、`ToolExecutionEvent`、`TurnFinalizedEvent` 真实宿主取证在当前仓库不可见，全部 `C_D2_EVIDENCE_MISSING`；D 轨道幂等/取消/断线重连 `UNTESTED`/`NOT_FOUND`。
3. 进入 D3 冻结最低条件（C 证据齐全、D 关键阻断关闭、D 真实 UDS/Hook/KYSEC/回退齐全、关键字段差异闭合、Critical=0 且未安排 High=0）均未满足。

**说明**：`BLOCKED` 不是任务失败，而是当前 Gate 对依赖与证据缺口的真实工程结论。部分 D 项已有真实宿主证据（UDS Spike HOST_VERIFIED、构建启动 HOST_VERIFIED、回退受限证据），说明历史 `BLOCKED_BY_D_DAY1` 预设已被当前证据部分解除；但未关闭的关键阻断与缺失的关键 D2 证据仍指向 `BLOCKED`。分项状态可用 `PARTIAL`/`UNVERIFIED`/`UNTESTED`/`NOT_FOUND`，正式 Gate 结论仅取 `PASS`/`REWORK`/`BLOCKED` 三者之一（当前为 `BLOCKED`）。

## 十四、本批次未执行 L2 声明

- 本任务 `runtime_required=false`，本批次**未执行L2**，未进入银河麒麟虚拟机补跑任何 C/D 测试。
- 报告中出现的 `HOST_VERIFIED` 均为既有麒麟宿主证据的引用（echo Spike、部署启动 Spike、回退基线受限证据），**不是**本批次新取证。
- 本批次仅对已有证据进行业务预审，**未以 WSL 静态检查代替宿主证据**；全部 C/D Day2 验收案例（G0-E-01..14）在本批次未执行。
- 本报告为 D3 Gate 预审输入，Addendum（补证执行记录）将在 C/D 补证后由对应轨道追加，本批次不生成 Addendum。

---

**变更记录**

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-08-08 | DRAFT 初稿：基于当前分支可见仓库内容与 `evidence/index.yaml` 逐项审查 C/D 交付物，形成 Gate 0 业务预审结论 `BLOCKED`，列出 D3 冻结前必须补证清单；未沿用历史 `BLOCKED_BY_D_DAY1` 预设结论 | E 轨道 |
