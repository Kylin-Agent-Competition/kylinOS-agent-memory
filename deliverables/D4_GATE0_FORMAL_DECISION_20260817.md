# Gate 0 人工审查正式结论（2026-08-17 版 · 环境基线 v2）

- **审查日期**：2026-08-17
- **审查性质**：Gate 0 四项认证（仓库基线 / VM 环境 / 架构审查 / 基线文档 + ADR）的正式裁决与冻结签署
- **审查基线**：环境基线 v2（麒灵 AI 助手 5.0.3，智能体模式）
- **审查依据**：
  - `D4_GATE0_FORMAL_DECISION_20260807.md`（原结论，基线 3.0.67）
  - `D4_GATE0_SUPPLEMENTARY_REVIEW_20260816.md`（补充审查，基线 5.0.3）
  - `D4_GATE0_AGENT_MODE_MANUAL_VERIFICATION_20260816.md`（5.0.3 人工验证 V1-V5）
  - `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（IPC 正式冻结声明）
  - `D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md`（冻结 vs 代码偏离核对）
  - `D4_DB_SCHEMA_V53_COMPARISON_20260817.md`（数据库初版冻结对照）
  - `docs/baseline/v2-20260816/01_sdk_model_abi_baseline_v2_20260816.md`（SDK/模型/ABI 基线 v2）
  - `docs/baseline/v2-20260816/02_kylin_vm_environment_baseline_20260816.md`（环境基线 v2）
  - `docs/baseline/v2-20260816/03_defensive_checklist_v2_20260816.md`（防御检查清单 v2）
  - `docs/baseline/v2-20260816/05_capability_boundary_reevaluation_20260816.md`（能力边界重评 v1.3）
  - `docs/baseline/v2-20260816/06_memorymap_capability_boundary_20260817.md`（memorymap 能力边界调查）
  - `evidence/index.yaml`（证据索引 Schema 1.1）
- **审查人**：周子腾（E，主持人）；Reviewer 1（D）；Reviewer 2（E）

> 本文档同时回答三个问题：① 每项裁决关联的证据索引；② 该结论是否需在新环境基线（5.0.3）复测；③ 复测应关注哪些项。

---

## 一、总体结论

- **Gate 0 结论**：☐ **PASS**　☑ **PASS_WITH_DEBT**　☐ REWORK　☐ BLOCKED
- **说明**：四项 Gate 0 均达 PASS 或 PASS_WITH_DEBT，D4 BLOCKED 状态解除。环境基线升级至 5.0.3 后，AGT-004 由「PARTIAL(模拟)+BLOCKED(真实)」上调为「PARTIAL（宿主能力已证 E4，本项目 Hook 集成待验证）」，其余与助手版本无关的裁决维持。官方记忆地图（memorymap）能力边界已定案：纯 UI 前端 + recollect 屏幕视觉记忆内核，MEM-001/002 维持 NOT_FOUND，新增 MEM-003 条件数据源，自研范围不收缩（§5.2）。所有 HOST_VERIFIED 结论中涉及宿主组件版本变化的项，均须在新基线复测后方可在能力矩阵固化（见 §五复测矩阵）。

---

## 二、逐项裁决结果（含证据索引 + 复测需求）

### 2.1 原 5 项裁决复审

| # | 裁决项 | 08-07 结论 | 本次复审结论 | 关联证据索引 | 需在新基线复测？ |
|---|--------|-----------|-------------|-------------|----------------|
| 1 | 部署 ECHO-009（构建顺序） | PASS_WITH_DEBT (TD-DEPLOY-001) | **维持** PASS_WITH_DEBT | `D2-3-DEPLOY-STARTUP`（HOST_VERIFIED/E4）；`D2-7-ROLLBACK-BASELINE`（回退对照） | **是**（部署布局 /opt/apps→/opt/kaiming/layers，见 AGT-006） |
| 2 | KYSEC | PASS_WITH_DEBT (TD-KYSEC-001) | **维持** PASS_WITH_DEBT（镜像无 kysec 内核） | `D2-6-KYSEC-SCOPE`（UNVERIFIED/E4，仅 ACL 模拟）；`ECHO-005`（ACL_SPIKE=VERIFIED, KYSEC_REAL_RULE=UNVERIFIED） | 否（内核能力与助手版本无关），但新部署路径下 ACL 有效性需确认 |
| 3 | 原文隔离 | PASS（UT-1 11/11） | **维持** PASS（UDS Echo 层） | `evidence/gate0_echo/ut_results/ut1_results.txt`（⚠️ 未登记 index.yaml，见 §七）；`ECHO-005` | **是**（5.0.3 聊天 DB Schema 变化，request_data 字段） |
| 4 | 真实 Tool Result (AGT-004) | 批准替代路线 B (ADR-004) | **上调为 PARTIAL**（见 §2.2） | `AGT-004-5.0.3-001`（HOST_VERIFIED/E4）；`D2-1-KAIMING-HOOK`（UNBLOCKED）；`D4-OPENKYLIN-HOOK`（PARTIAL/E3） | **是**（本项目 Hook 端到端三场景） |
| 5 | UDS IPC | PASS_WITH_DEBT (TD-IPC-002~004) | **维持** PASS_WITH_DEBT | `ECHO-005`；`D4-R3-VERIFY`（HOST_VERIFIED/E4）；`D2-4-SOCKET-AUDIT` | 否（自研协议与宿主版本无关），但 deadline 超时行为待补齐 |

### 2.2 AGT-004 上调裁决（本次核心）

| 字段 | 内容 |
|------|------|
| 提议 | AGT-004 由「PARTIAL(模拟)+BLOCKED(真实)」上调为「**PARTIAL（宿主能力已证 E4 + 本项目集成待验证）**」 |
| 关联证据 | `AGT-004-5.0.3-001`（evidence/index.yaml，HOST_VERIFIED/E4，reviewer=周子腾 E）；证据文件 `evidence/l2-kylin-vm/d4_agent_mode_5_0_3_20260816/`（7 文件 + MANIFEST.sha256）；报告 `deliverables/D4_GATE0_AGENT_MODE_MANUAL_VERIFICATION_20260816.md` |
| 依据 | ① 5.0.3 智能体模式 + 工具调用人工验证通过（V1/V2/V3/V5-2 ✅，shell tool_call → tool_result 音量 67% → 回复闭环）；② 失败场景已观测（V5-1/V5-3：`ls -la /root` → 权限不够，宿主如实报告失败，日志无沉淀） |
| 待验证边界 | 本项目 Hook（事件捕获 → Memory Service 落库）端到端**未**在 5.0.3 验证；不得将「宿主能调工具」等同「本项目 Hook 已验证」 |
| **人工裁决结果** | ☑ 接受上调（与 08-16 补充审查一致）　☐ 否决维持 BLOCKED　☐ 有条件接受（条件：______） |
| 对 ADR-004 的处理 | ☑ **保留为备份路线**（真实 Hook 端到端未通前不撤销）　☐ 降级为演示用途　☐ 撤销 |

### 2.3 新增风险项确认（08-16 补充审查 §五）

| 编号 | 风险 | 级别 | 本次确认 | 责任轨道 | 关联证据/文档 |
|------|------|------|---------|---------|--------------|
| R-NEW-1 | 官方知识库/文档/数据管理能力边界未知（memorymap 已定案，见 §5.2） | 高 | ☐ 接受 ☐ 驳回 ☐ 降级 | E（P0 调查） | `06_memorymap_capability_boundary`；`05_capability_boundary_reevaluation` §2.4、§4 |
| R-NEW-2 | request_data 字段语义未验证 | 中高 | ☐ 接受 ☐ 驳回 ☐ 降级 | C（P0 实验） | `D4_DB_SCHEMA_V53_COMPARISON` §2.2、P0-V1 |
| R-NEW-3 | /opt/kaiming/layers 下 KYSEC/回退未验证 | 中 | ☐ 接受 ☐ 驳回 ☐ 降级 | D | `D4_DB_SCHEMA_V53_COMPARISON` §二；AGT-006 |

---

## 三、证据索引关联总表

每项裁决对应的 `evidence/index.yaml` 条目（含状态与证据等级），供审查追溯：

| 证据条目 ID | 描述 | status | evidence_level | 关联裁决 |
|-------------|------|--------|----------------|---------|
| `GATE0-ENV-001` | 麒麟 VM 环境基线冻结（**旧基线 3.0.67 时代**） | HOST_VERIFIED | E4 | 环境基线（已被 v2 取代，见 §五） |
| `ECHO-005` | UDS Echo Spike 复测（8 条记录，ECHO-001~005 + systemd） | HOST_VERIFIED | E4 | 裁决 2/3/5 |
| `D4-R3-VERIFY` | PR21 R3 P0 修复全链路协议 6/6 PASS | HOST_VERIFIED | E4 | 裁决 5 |
| `D2-3-DEPLOY-STARTUP` | CMake 构建 + dev 模式启动 + --dev 使能 | HOST_VERIFIED | E4 | 裁决 1 |
| `D2-4-SOCKET-AUDIT` | 统一 Socket 路径全链路一致性审计 | HOST_VERIFIED | E4 | 裁决 5 |
| `D2-6-KYSEC-SCOPE` | KYSEC 授权口径（ACL 模拟替代） | UNVERIFIED | E4 | 裁决 2 |
| `D2-7-ROLLBACK-BASELINE` | 回退对照 Day1 基线（P1-6~P1-10 缺口） | HOST_VERIFIED | E4 | 裁决 1 |
| `D2-1-KAIMING-HOOK` | Kaiming→UDS 真实 Hook 调查（路线 B 失败→D4 解封） | UNBLOCKED | E4 | 裁决 4 |
| `D4-OPENKYLIN-HOOK` | D4 openkylin 阶段4-5 Tool Result Hook 审计 + patch | PARTIAL | E3 | 裁决 4 |
| `AGT-004-5.0.3-001` | 5.0.3 智能体模式 + 工具调用人工验证（deepseek） | HOST_VERIFIED | E4 | 裁决 4（上调核心依据） |
| `EMBED-CALL-001~005` | Embedding 调用验证（D1-A→D6-A） | HOST_VERIFIED | E4 | 能力边界 EMB-001（需复测） |
| `VECTOR-CALL-001~003`、`D1-B-01`、`D1-B-02` | Vector Engine CRUD/隔离/持久化 | 混合 | E3/E4 | 能力边界 VEC-001~004（需复测） |
| `RUNTIME-001` | kylin-ai-runtime 二进制完整性（旧基线） | HOST_VERIFIED | E4 | 环境基线（runtime 二进制未变） |
| `MEM-BOUNDARY-001` | 官方记忆地图 memorymap 能力边界调查（纯 UI + recollect 记忆内核，phase1~10） | HOST_VERIFIED | E3 | MEM-001/002 定案（§5.2） |
| `GATE0-ENV-002` | 环境基线 v2 调查（01 SDK/ABI 基线、02 环境采集、03 防御清单、05 能力边界 v1.3） | HOST_VERIFIED | E3 | Gate 0「VM 环境」认证支撑（§5.0） |

> 注：UT-1/UT-2 结果尚未登记 index.yaml，见 §七「登记缺口」。

---

## 四、冻结确认

| 冻结对象 | 结论 | 说明 |
|---------|------|------|
| IPC 协议 FRZ-IPC-001~007 | ☑ 正式冻结　☐ 暂缓 | 依据 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`；自研协议不受 5.0.3 影响 |
| IPC 一致性对齐（ALIGN-001~005） | ☑ 冻结优先、冻结后对齐　☐ 反向修改冻结 | 核对报告发现 5 处偏离（消息上限 4MiB≠64KB、错误码枚举、envelope、方法路由、UDS 路径），先冻结、后按 ADR 对齐 |
| 数据库初版 FRZ-DB-001 | ☑ 可冻结　☐ 有条件　☐ 暂缓 | 自研库独立，不受 5.0.3 官方 Schema 影响（`D4_DB_SCHEMA_V53_COMPARISON` §三） |
| 部署路径 / 失败路由 | ☐ 可冻结　☑ **有条件冻结**　☐ 暂缓 | 前置：5.0.3 新部署布局（/opt/kaiming/layers）下的构建基线、备份、回退复验（AGT-006） |

---

## 五、新环境基线（5.0.3）复测矩阵

> 本表回答「哪些结论需在新基线复测 + 复测关注项」。判定原则：**宿主组件版本变化的项必须复测；自研/内核无关项不复测；官方新增组件走 P0 重新调查。**

### 5.0 环境基线 v2 调查成果总览（2026-08-16/17 完成）

环境基线 v2 调查由 5 份文档构成（`docs/baseline/v2-20260816/01~06`），已完成；证据等级均为 ABI/包/Schema 级（E3），运行时功能验证待复测：

| 文档 | 内容 | 状态 |
|------|------|------|
| `01_sdk_model_abi_baseline_v2` | SDK/模型/ABI 基线（Embedding 0k0.4 新增图像符号、助手 5.0.3 chatAsync ABI、Vector 0k1.0、30 模型目录） | ✅ 已完成 |
| `02_kylin_vm_environment_baseline` | 环境采集（系统层/应用层/Runtime/模型仓库/服务状态） | ✅ 已完成 |
| `03_defensive_checklist_v2` | 防御检查清单（构建工具链/Embedding/模型/Kytensor/最小调用） | ✅ 已完成（含 cmake 缺失阻塞） |
| `05_capability_boundary_reevaluation` v1.3 | 能力边界重评（EMB/VEC/AGT/MEM/REC 五轨） | ✅ 已完成 |
| `06_memorymap_capability_boundary` | memorymap 能力边界调查（phase1~10） | ✅ 已完成 |

**关键版本变化（旧基线 → v2）**：

| 组件 | 旧基线 | v2 | 影响 |
|------|--------|-----|------|
| 麒灵 AI 助手 | 3.0.67 | **5.0.3** | 智能体模式 + 工具调用（AGT-004 上调） |
| Embedding SDK | 0k0.3 | **0k0.4** | 新增图像嵌入符号（EMB-002/004 上调） |
| Vector Engine 服务端 | 0k0.11 | **0k1.0** | CRUD/持久化待复测 |
| cmake | 3.28.3 | **未安装** | C++ Bridge 编译阻塞（§5.4） |
| 模型仓库 | 15 目录 | **30 目录** | 新增 CN-CLIP/SAM/ASR/TTS |

**能力边界结论（05 v1.3）**：
- **上调**：EMB-002/004（ABI_VERIFIED）、REC-002（ABI_VERIFIED）、AGT-001（ABI_VERIFIED，需重取 Build ID）
- **定案**：MEM-001/002（NOT_FOUND 维持）、新增 MEM-003（ABI_VERIFIED，见 §5.2）
- **待复测**：EMB-001、VEC-001~004、AGT-002/003/004/005/006、REC-001（见 §5.1）

**新增官方组件（影响自研范围边界）**：memorymap 2.0.23（已定案 §5.2）、知识库/文档/数据管理服务（待调查 R-NEW-1）、Recollect 独立服务、kytensor-llm/llm-backend（本地 LLM）、9 厂商引擎插件。

### 5.1 需在 5.0.3 复测的项（Gate 0 后 D1+ 执行）

| 能力 ID | 能力 | 版本变化 | 复测关注项 | 责任轨道 |
|---------|------|---------|-----------|---------|
| EMB-001 | 同步文本向量化 | 0k0.3→0k0.4 | 768 维、L2 范数=1、确定性、中文/空串/batch；图像嵌入符号新增需重做 ABI 兼容声明 | A |
| VEC-001~004 | Vector CRUD/过滤/持久化/重建 | 0k0.11→0k1.0 | CRUD、标量过滤、重启持久化、精准遗忘回归全链路重跑 | B |
| AGT-001 | chatAsync ABI | 3.0.67→5.0.3 | `kyai::assistant::OsAssistant::chatAsync` 符号已确认，重取 `libkyai-assistant.so` Build ID（`0ffedd8f…`）与导入表，5.0.3 ELF 上重新定位 Hook 点 | C/D |
| AGT-002 | 普通聊天流式完成 | 3.0.67→5.0.3 | 流式完成在 5.0.3 上重新验证 | C |
| AGT-003 | 聊天 DB 落库 | Schema 已变 | RECORD 表新增 6 字段（chat_type/is_collect/request_data/mode_type/session_uuid/has_unread）、新增 DOCUMENT_REFERENCE、knowledgebase_database.db | C |
| AGT-004 | 真实 Tool Result | 宿主能力已证 | 本项目 Hook 端到端（事件捕获→Memory Service 落库），**覆盖成功/失败/取消三场景** [02 §3.3] | C/D |
| AGT-005 | Memory Context 注入 | 方向有利 | request_data 字段读写语义实验：能否承载模型请求侧数据、能否作注入通道且不污染 message 原文 | C |
| AGT-006 | 构建/部署/回退 | /opt/apps→/opt/kaiming/layers | 新路径下构建基线记录、备份、最小 KYSEC 授权、部署前快照、异常回退复验 | D |
| REC-001 | Recollect 普通聊天参与 | 升级为独立服务 | 5.0.3 上重新验证普通聊天是否启动 Recollect | E |

### 5.2 官方记忆能力边界 — memorymap 已定案（2026-08-17）

> 依据 `docs/baseline/v2-20260816/06_memorymap_capability_boundary_20260817.md`（编号 KMA-CAPABILITY-MEMORYMAP-20260817）+ `evidence/l2-kylin-vm/memorymap-boundary-20260817/`（phase1~10 原始日志 + MANIFEST.sha256）。

**定案结论**：
- memorymap（`cn.kylin.kylin-ai-memorymap 2.0.23`）= **纯 UI 前端**（Qt5 + recollect-client + 本地 OCR 辅助，`nm -D` 无导出 API），记忆内核在 `kylin-ai-recollect-service` 后台。
- 官方「记忆」= **屏幕视觉记忆**（截图→合成 MP4→OCR→CLIP 512 图文 Embedding→SQLite + Milvus-Lite 向量→检索→按时间区间删除），**非**偏好/知识/工具结果通用记忆。
- **MEM-001（官方 MemoryClient）维持 NOT_FOUND**：`libkylin-ai-recollect-client` 是「视觉记忆 client」，非通用偏好/知识 MemoryClient。
- **MEM-002（完整 Memory Service）维持 NOT_FOUND**：recollect-service 是「屏幕视觉记忆 service」，不含偏好提取/知识结构化/Tool Result/自然语言遗忘/短中长期流转。
- 新增 **MEM-003（官方视觉记忆组件）**：状态 `ABI_VERIFIED`/E3，定位「条件数据源（只读复用）」，同步修订 01 §9 旧「官方无记忆能力」表述。

**可复用 / 重叠 / 互补判定**：
- memorymap UI → **不可复用**（纯前端应用，无库级导出）；
- recollect-service → **只读可复用**（D-Bus `com.kylin.Recollect` + `libkylin-ai-recollect-client` 读取屏幕活动数据，不可改内核）；
- 与自研 → 仅**共享基础设施**（同一套 embedding/vision/vector-engine-client SDK + SQLite），**功能互补**（recollect=「屏幕上发生过什么」原始数据源；自研=偏好/知识理解、冲突消解、精准遗忘、上下文注入）；
- **自研范围不收缩**。

**仍需 P0 调查（未定案）**：

| 项 | 关注点 | 责任轨道 |
|----|--------|---------|
| 知识库/文档/数据管理能力边界 | `kylin-ai-knowledge-base-service`、`kylin-ai-document-qa-service`、`kyai-data-management-service` 功能边界（memorymap 之外仍未知） | E |
| P0-V2 | 官方 `is_collect` 与自研 memory_entries「记忆候选」边界是否重叠 | E |
| P0-V4 | 官方 `session_uuid` 与自研 `session_id` 映射关系 | C/D |
| 待运行时补测 | recording-memory 开启后端到端闭环、CLIP 视觉检索命中率、deleteUserData 无残留、exclude-apps 隐私边界（06 报告 §4，当前 UNTESTED/E0） | E |

### 5.3 无需因 5.0.3 复测（维持原结论）

| 项 | 理由 |
|----|------|
| UDS IPC（TD-IPC-002~004） | 自研协议，与宿主助手版本、聊天 DB Schema 无关；仅 deadline 超时行为待补齐（TD-IPC-003） |
| 部署顺序修复（TD-DEPLOY-001） | 构建顺序逻辑与助手版本无关；但部署路径相关部分纳入 AGT-006 复验 |
| KYSEC（TD-KYSEC-001） | 镜像无 kysec 内核，属内核能力缺口，与助手版本无关；新路径下 ACL 有效性纳入 AGT-006 |

### 5.4 环境修复前置项

| 项 | 说明 | 责任轨道 |
|----|------|---------|
| cmake 重装 | 环境基线 v2 实测 `which cmake` 退出码 127（未安装），C++ Bridge 无法编译；重装后重新采集基线 | D |

---

## 六、技术债更新与登记缺口

### 6.1 技术债状态变更

| 编号 | 标题 | 状态变更 | 说明 |
|------|------|---------|------|
| R-ARCH-05 | 真实 Kaiming Hook 未验证 | 维持 In Progress（载体切换为 5.0.3） | 端到端待做 |
| TD-007 | Tool Result Hook 源码级设计 | 维持 Open | 5.0.3 上重新实现后关闭 |
| TD-008 | Hook 点 A Memory Context 注入未确认 | 维持 Open | 关联 request_data 实验（P0-V1） |
| TD-009 | 非 OpenAI 风格 Tool 执行路径 | 维持 Open | 关联 AGT-004 |
| TD-DEPLOY-001 | 部署顺序修复 | 维持 | 关联 AGT-006 |
| TD-KYSEC-001 | KYSEC 真实规则不可用 | 维持 | 关联 AGT-006 新路径 ACL |
| TD-IPC-002~004 | UDS 权限/超时/重连缺口 | 维持 | D4 补齐 |

### 6.2 登记缺口（审查后须补齐，不影响本次结论）

| 缺口 | 说明 | 处置 |
|------|------|------|
| UT-1/UT-2 证据未登记 index.yaml | `evidence/gate0_echo/ut_results/ut1_results.txt`（原文隔离 11/11）、`ut2_results.txt`（IPC 重启 10/12）存在但无索引条目 | 审查后补登记 |
| 环境基线 v2 调查本体未登记 index.yaml | ~~`docs/baseline/v2-20260816/01~06` 五份文档~~ | ✅ 已补 `GATE0-ENV-002`（HOST_VERIFIED/E3，覆盖 01/02/03/05） |
| TD-DEPLOY-001/TD-KYSEC-001/TD-IPC-002~004 未入 TECHNICAL_DEBT_REGISTER.md | 08-07 结论引用这些编号，但登记表中仅有 TD-007/008/009、R-ARCH-05 | 补登记至技术债登记表 |
| ADR-004 无正式 ADR 文件 | 08-07 结论以正文形式记录 ADR-004，docs/adr/ 目录仅有 ADR-001 | 补写 `docs/adr/004-*` 正式文件 |
| AGT-004 能力矩阵未更新 | `05_capability_boundary_reevaluation` §2.3 仍标「待重新调查」 | 上调确认后更新为 PARTIAL |
| memorymap 边界调查证据未登记 index.yaml | ~~报告 `06_memorymap_capability_boundary` + `evidence/l2-kylin-vm/memorymap-boundary-20260817/`（10 日志）~~ | ✅ 已补登记 `MEM-BOUNDARY-001`（HOST_VERIFIED/E3） |

---

## 七、审查产出核对

- [x] 书面 Gate 0 结论（本文档）
- [x] 逐项裁决 + 证据索引关联（§二、§三）
- [x] 新基线复测矩阵（§五）
- [x] 冻结确认（§四：IPC 正式冻结 + 数据库初版可冻结 + 部署/失败路由有条件冻结）
- [x] 技术债状态变更（§六.1）
- [ ] 技术债登记缺口补齐（§六.2，审查后执行）
- [x] 能力矩阵同步（05 文档 v1.2→v1.3，含 MEM-001/002 定案 + 新增 MEM-003）
- [x] 01 SDK/ABI 基线 MEM 部分同步（memorymap/recollect 定案）
- [x] index.yaml 环境基线条目补登记（GATE0-ENV-002）
- [x] VERSION_MAP 更新（memorymap 纯 UI 定案 + recollect 记忆内核 + 时间戳 08-17）

---

## 八、签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 审查主持人 | 周子腾（E） | 2026-08-17 | PASS_WITH_DEBT（待确认） |
| Reviewer 1 | 待填写（D） | | |
| Reviewer 2 | 待填写（E） | | |

> 依据 AGENTS.md：D 与 E 为指定 Reviewer，自审无效。
