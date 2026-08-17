# 05 能力边界重新评估（v1.3 · 基于 2026-08-16 环境基线 v2，2026-08-17 memorymap 定案增补）

> **性质**：对 `reviewDocuments/01_sdk_capability_boundary.md`（v1.1）的能力边界结论，依据新环境基线
> `docs/baseline/02_kylin_vm_environment_baseline_20260816.md`（v2）重新评估的结果。
> **评估方法**：本次为 **ABI/包/Schema 级** 评估（nm -D、dpkg、sqlite schema、路径探查），未做运行时功能测试；
> 凡旧基线标 HOST_VERIFIED 的结论，因组件版本变化一律降级为「旧版本已证、新版本待复测」，不自动继承。
> **状态标签**沿用 01 文档：HOST_VERIFIED / SOURCE_VERIFIED / ABI_VERIFIED / PARTIAL / UNTESTED / NOT_FOUND / BLOCKED。

---

## 0 评估依据

| 项目 | 旧基线（01 v1.1） | 新环境（基线 v2 · 实测） | 影响 |
| --- | --- | --- | --- |
| 麒灵 AI 助手 | 3.0.67 | **5.0.3** | 主链 Hook/ABI/DB 全部需重评 |
| Embedding SDK | 1.2.0.0-0k0.3 | **1.2.0.0-0k0.4** | 新增图像嵌入符号 |
| Vector Engine 服务端 | 1.2.0.1-0k0.11 | **1.2.0.1-0k1.0** | CRUD 结论需复测 |
| kylin-ai-subsystem | 1.2.0.0-0k0.3 | **1.3.0.1-0k0.1** | 元包升级 |
| 官方知识库/文档/Recollect | 部分不存在 | **独立服务已安装** | 新增官方组件 |
| 记忆地图 memorymap | 不存在 | **2.0.23** | 新增应用，与记忆直接相关 |

---

## 1 核心结论摘要

1. **助手 5.0.3 的聊天核心 ABI 保持不变**：`OsAssistant::chatAsync`、`initWithChatHistory`、`setChatAsyncCallback`、`stopChat`、`clearContext` 仍由 `libkyai-assistant.so.1.0.0` 导出（本次 nm -D 确认），但函数已挂到 `kyai::assistant::OsAssistant` 命名空间下。旧基线 AGT-001「chatAsync ABI」的**结论方向延续**，但 Build ID、精确源码行、Hook 语义必须在 5.0.3 ELF 上重新取证，不能直接复用 3.0.67 的结论。

2. **聊天数据库 Schema 发生重大变化**，直接影响「原文隔离 / Memory Context 注入」的评估：
   - `RECORD` 表新增 `chat_type`、`is_collect`、`request_data`、`mode_type`、`session_uuid`、`has_unread` 六个字段；
   - 新增 `DOCUMENT_REFERENCE` 表（文档问答引用）；
   - 新增独立数据库 `knowledgebase_database.db`，含 `KNOWLEDGEBASE` 表（官方知识库）。
   - 旧基线「聊天 Schema 无原始用户文本与模型增强文本分离字段」的结论 **已被部分推翻**：`request_data` 字段可能承载模型请求侧数据，需进一步验证其是否可用于 Memory Context 注入且不污染 `message` 原文。

3. **官方出现了与「记忆」直接相关的组件**。经 2026-08-17 memorymap 能力边界调查（`06_memorymap_capability_boundary_20260817.md`）**定案**：
   - `cn.kylin.kylin-ai-memorymap 2.0.23`（记忆地图）= 纯 UI 前端，记忆内核为 `kylin-ai-recollect-service`，二者构成「屏幕视觉记忆」（截图→OCR→CLIP→SQLite+Milvus-Lite→检索→删除），**非**偏好/知识/工具结果通用记忆；
   - MEM-001 / MEM-002 **维持 NOT_FOUND**（官方无通用偏好/知识 MemoryClient / Memory Service）；
   - 新增 **MEM-003 官方视觉记忆组件**（ABI_VERIFIED/E3），定位条件数据源（只读复用）；
   - `kylin-ai-knowledge-base-service`、`kylin-ai-document-qa-service`、`kyai-data-management-service` 功能边界仍未知，**继续列为 P0 重新调查项**（R-NEW-1）。

4. **Recollect 从「条件数据源」升级为官方独立服务**：`kylin-ai-recollect-service` + `libkylin-ai-recollect-client` 已作为独立包安装。旧基线「普通聊天未启动 Recollect」的结论需在 5.0.3 上重新验证。

5. **Embedding 多模态能力从「符号存在但无模型」升级为「符号 + 模型均已就位」**：`text_embedding_by_image_model(_async)`、`ai_runtime_core_image_embedding_*` 系列已导出，且 CN-CLIP / SAM / 语音 ASR / TTS / OCR 模型目录齐全。旧基线 EMB-004（图像/多模态 BLOCKED/条件）应上调为「ABI 已就绪，待运行时验证」。

6. **本地 LLM 推理能力出现**：`kytensor-llm 2.0.0` + `llm-backend 1.0.1`，配合多厂商引擎插件（deepseek/qwen/baidu/xunfei/custom/freetrial/ondevice），官方模型调用链从「本地或云端」扩展为「多厂商 + 本地 LLM」。旧基线「本地或云端模型」的调用关系描述需更新。

---

## 2 分组件重新评估

### 2.1 Embedding SDK（轨道 A）

| 编号 | 能力 | 旧状态（v1.1） | 新评估（v1.2） | 依据 |
| --- | --- | --- | --- | --- |
| EMB-001 | 同步文本向量化 | HOST_VERIFIED / E4 | **待复测**（0k0.3→0k0.4） | 版本变化，768 维/范数/确定性需重新验证 |
| EMB-002 | 模型列表/选择 | PARTIAL / E1/E3 | **ABI_VERIFIED（上调）** | `text_embedding_get_model_list`、`text_embedding_init_model` 现已在 .so 导出 |
| EMB-003 | 异步文本向量化 | UNTESTED | UNTESTED（维持） | 符号存在，仍无运行时验证 |
| EMB-004 | 图像/多模态 | PARTIAL（无模型） | **ABI_VERIFIED（上调，模型已就位）** | 图像嵌入符号已导出 + CN-CLIP/SAM 模型目录齐全 |
| EMB-T03 | 空输入异常 | UNTESTED / P0 | UNTESTED / P0（维持） | 仍需运行时补测 |
| EMB-T06 | Runtime 重启恢复 | UNTESTED / P0 | UNTESTED / P0（维持） | — |

**开发影响**：`cpp-bridge/embedding_abi_compat.h` 中「init_model / get_model_list 缺失」的兼容声明需修正为「已导出但待运行时验证」；可考虑将图像嵌入纳入 Provider 扩展边界（仍不阻塞主链）。

### 2.2 Vector Engine（轨道 B）

| 编号 | 能力 | 旧状态（v1.1） | 新评估（v1.2） | 依据 |
| --- | --- | --- | --- | --- |
| VEC-001 | CRUD | HOST_VERIFIED / E4 | **待复测** | 服务端 0k0.11→0k1.0 |
| VEC-002 | 标量过滤 | HOST_VERIFIED / E4 | **待复测** | 同上 |
| VEC-003/004 | 重启持久化/重建 | HOST_VERIFIED / E5 | **待复测** | 同上 |
| VEC-005 | Hybrid/RRF | SOURCE_VERIFIED / E2 | SOURCE_VERIFIED（维持） | 仍无宿主实测 |
| VEC-T07 | 客户端缺陷防御 | SOURCE_VERIFIED / P0 | SOURCE_VERIFIED / P0（维持） | 客户端 0k1.1 未变 |

**开发影响**：客户端版本未变，Bridge 防御设计基本沿用；但服务端版本变化必须重新跑一遍 CRUD/持久化/精准遗忘回归后再固化结论。

### 2.3 OS Agent 与聊天数据库（轨道 C，变化最大）

| 编号 | 能力 | 旧状态（v1.1） | 新评估（v1.2） | 依据 |
| --- | --- | --- | --- | --- |
| AGT-001 | chatAsync ABI | ABI_VERIFIED / E3 | **ABI_VERIFIED（需 5.0.3 重新取证 Build ID）** | `kyai::assistant::OsAssistant::chatAsync` 已确认导出 |
| AGT-002 | 普通聊天流式完成 | HOST_VERIFIED / E4 | **待复测** | 3.0.67→5.0.3 |
| AGT-003 | 聊天 DB 落库 | HOST_VERIFIED / E4 | **待复测（Schema 已变）** | RECORD 表新增 6 字段 |
| AGT-004 | 真实 Tool Result | PARTIAL / E2/E4 | **PARTIAL（上调，宿主能力已证 E4）** | 5.0.3 智能体模式 + 工具调用人工验证通过（V1/V2/V3/V5-2 ✅）；本项目 Hook 端到端（事件捕获→落库，成功/失败/取消三场景）待验证 |
| AGT-005 | Memory Context 注入 | UNTESTED / E0/E2 | **方向有利但需重验** | `request_data` 字段提供潜在注入点，语义未验证 |
| AGT-006 | 修改版构建/部署/KYSEC/回退 | UNTESTED / E1/E3 | **UNTESTED（部署布局已变）** | 应用从 `/opt/apps` 迁移到 `/opt/kaiming/layers/...` |
| IPC-001 | Kaiming→UDS | UNTESTED / E0 | UNTESTED（维持） | 无变化证据 |

**RECORD 表 Schema 变化明细**（本次 sqlite .schema 实测）：

| 字段 | 旧基线 | 新实测 | 评估意义 |
| --- | --- | --- | --- |
| `chat_type` | 无 | INT DEFAULT 0 | 区分聊天类型（普通/会议/文档等） |
| `is_collect` | 无 | INT DEFAULT 0 | 疑似「收藏/记忆」标记，与记忆相关 |
| `request_data` | 无 | TEXT DEFAULT NULL | **潜在模型请求侧数据字段**，可能是原文隔离突破口 |
| `mode_type` | 无 | INT DEFAULT 0 | 模式类型 |
| `session_uuid` | 无 | VARCHAR(64) | 会话 UUID（区别于 sessionID） |
| `has_unread` | 无 | INTEGER | 未读标记 |

**开发影响（关键）**：
- 旧基线「不得原地修改 `RECORD.message`」的原则仍成立，但新增的 `request_data` 字段可能正是官方预留的「模型增强文本」通道，若验证属实，Memory Context 注入可写入 `request_data` 而非污染 `message`——这将显著降低 AGT-005 的实现风险。**必须优先做一次 request_data 字段的读写语义实验。**
- 聊天 DB 路径仍为 `~/.config/kylin-aiassistant/kylin_aiassistant_database.db`（不变），新增 `knowledgebase_database.db`。

### 2.4 Memory（轨道 E，结论可能反转）

| 编号 | 能力 | 旧状态（v1.1） | 新评估（v1.2） | 依据 |
| --- | --- | --- | --- | --- |
| MEM-001 | 官方 MemoryClient | NOT_FOUND / E3 | **NOT_FOUND（维持）** | `libkylin-ai-recollect-client` 为「视觉记忆 client」，非通用偏好/知识 MemoryClient（06 报告 §3.2） |
| MEM-002 | 完整 Memory Service | NOT_FOUND / E1-E4 | **NOT_FOUND（维持）** | `kylin-ai-recollect-service` 为「屏幕视觉记忆 service」，不含偏好/知识/冲突/遗忘/流转（06 报告 §3.2） |
| MEM-003 | 官方视觉记忆组件 | —（新增） | **ABI_VERIFIED / E3** | memorymap（纯 UI）+ recollect-service（记忆内核）= 屏幕视觉记忆；D-Bus `com.kylin.Recollect` + client C API 实证；定位条件数据源（只读复用） |

**新发现组件清单（ABI/包级确认，功能未知）**：

| 组件 | 版本 | 与「记忆」的潜在关系 |
| --- | --- | --- |
| kylin-ai-memorymap（记忆地图） | 2.0.23 | **已定案**：纯 UI 前端（06 报告 §2.4） |
| kylin-ai-knowledge-base-service | 1.2.0.0-0k1.0 | 官方知识库服务，`KNOWLEDGEBASE` 表已落地 |
| kylin-ai-document-qa-service | 1.2.0.0-0k1.0 | 文档问答（DOCUMENT_REFERENCE 表） |
| kylin-ai-document-service | 1.2.0.0-0k0.6 | 文档解析服务 |
| kylin-ai-parser-extension | 1.2.0.0-0k0.4 | 解析扩展 |
| kyai-data-management-service | 1.2.0.0-0k1.10 | 数据管理业务服务（含 client 0k0.3） |
| kylin-ai-recollect-service | 1.0.0.0-0k1.0 | **已定案**：memorymap 记忆内核（截图+OCR+CLIP+Milvus+SQLite）（06 报告 §2.4） |

**开发影响（已定案 + 部分仍待调查）**：memorymap 能力边界已定案（06 报告，2026-08-17）——官方「记忆」= 屏幕视觉记忆，非通用偏好/知识记忆，**自研 Memory Service 主范围不收缩**；recollect-service 可作「屏幕行为」条件数据源（只读复用），与自研仅共享基础设施（embedding/vision/vector-engine-client SDK）、功能互补。但知识库 / 文档 / 数据管理服务的功能边界仍未调查，**继续作为 P0 项**（R-NEW-1），不得按「官方无记忆能力，全部自研」或「官方已有完整记忆」任一侧偏废。

### 2.5 Recollect（条件数据源）

| 编号 | 能力 | 旧状态（v1.1） | 新评估（v1.2） |
| --- | --- | --- | --- |
| REC-001 | 普通聊天参与 | NOT_FOUND / E4 | **待复测**（Recollect 已成独立服务） |
| REC-002 | D-Bus 数据读取 | SOURCE_VERIFIED / E2/E3 | **ABI_VERIFIED（上调）**：`com.kylin.Recollect` D-Bus 接口 + `libkylin-ai-recollect-client` 完整 C API 已实证（06 报告 §3） |

**开发影响**：`libkylin-ai-recollect-client` 提供了正式访问入口，条件数据源的可接入性提升；但仍应维持「主链稳定后再接入」的原则。

---

## 3 统一能力矩阵更新（增量）

| 编号 | 能力 | v1.1 状态 | v1.2 状态 | 责任轨道 |
| --- | --- | --- | --- | --- |
| EMB-002 | 模型列表/选择 | PARTIAL | ABI_VERIFIED | A |
| EMB-004 | 图像/多模态 | PARTIAL | ABI_VERIFIED（模型已就位） | A |
| AGT-001 | chatAsync ABI | ABI_VERIFIED(3.0.67) | ABI_VERIFIED(5.0.3，需重取 Build ID) | C/D |
| AGT-004 | 真实 Tool Result | PARTIAL / E2/E4 | PARTIAL（宿主能力已证 E4，本项目 Hook 端到端待验证） | C/D |
| AGT-005 | Context 注入 | UNTESTED | UNTESTED（request_data 提供有利方向） | C |
| MEM-001 | 官方 MemoryClient | NOT_FOUND | NOT_FOUND（维持，视觉记忆 client 非通用） | E |
| MEM-002 | 完整 Memory Service | NOT_FOUND | NOT_FOUND（维持，屏幕视觉记忆 service） | E |
| MEM-003 | 官方视觉记忆组件 | —（新增） | ABI_VERIFIED（条件数据源，只读复用） | E |
| REC-002 | Recollect 读取 | SOURCE_VERIFIED | ABI_VERIFIED（D-Bus + client C API 实证） | E |

---

## 4 新增风险与开发影响

| 风险 | 等级 | 影响 | 建议控制 |
| --- | --- | --- | --- |
| 官方知识库/文档/数据管理能力边界未知（memorymap 已定案） | **高** | 自研范围可能与官方知识库/数据管理重叠 | P0：调查 `kylin-ai-knowledge-base-service`、`kylin-ai-document-qa-service`、`kyai-data-management-service` 功能边界（R-NEW-1） |
| 助手 5.0.3 源码与 Hook 点未对应 | 高 | 旧 Hook 语义（SystemChat 等类）可能失效 | D1-D3 重新做 5.0.3 ELF/源码定位 |
| `request_data` 字段语义未验证 | 中高 | 注入契约定案依赖它 | 优先做读写语义实验 |
| RECORD Schema 新增字段未在旧评估覆盖 | 中 | is_collect/chat_type 可能影响记忆提取 | 纳入聊天 DB 重评估 |
| cmake 缺失 | 中 | C++ Bridge 无法编译 | 重装 cmake 后重新采集基线 |

---

## 5 需人工裁决 / 下一步

1. **官方知识库/文档/数据管理能力边界调查**（最高优先，memorymap 已定案）：`kylin-ai-memorymap` 已定案为「屏幕视觉记忆 UI + recollect 内核」（06 报告），MEM-001/002 维持 NOT_FOUND、新增 MEM-003；仍需确认知识库、文档、数据管理服务是否为「可复用的官方记忆能力」。
2. **request_data 字段实验**：验证其是否承载模型请求侧数据、能否作为 Memory Context 注入通道且不污染 `message`。
3. **5.0.3 重新取证**：Build ID、`libkyai-assistant.so` 导入表、Hook 位置、Kaiming 重打包路径（/opt/kaiming/layers）。
4. **Embedding/Vector 回归**：版本变化后重新跑同步向量化（768 维）与 Vector CRUD/持久化。
5. **环境修复**：重装 cmake，并更新 v2 基线。

> 本评估结论均为 ABI/包/Schema 级，不得在代码或文档中写「5.0.3 已支持 X」。所有 HOST_VERIFIED 需待麒麟 VM 运行时复测。

## 修订记录

| 版本 | 日期 | 修订内容 |
| --- | --- | --- |
| v1.2 | 2026-08-16 | 初版：基于环境基线 v2 的 ABI/包/Schema 级重评 |
| v1.3 | 2026-08-17 | 增补：memorymap 能力边界定案（06 报告）——MEM-001/002 维持 NOT_FOUND、新增 MEM-003 ABI_VERIFIED、REC-002 上调 ABI_VERIFIED；知识库/文档/数据管理继续 P0 调查 |

## 签署

| 角色 | 姓名 | 日期 | 结论 |
| --- | --- | --- | --- |
| 评估人 | Agent | 2026-08-16 | 待 Review |
| Reviewer 1 | 待填写 | | |
| Reviewer 2 | 待填写 | | |
