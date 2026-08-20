# Gate 0 补充审查：基于环境基线 v2（麒灵 5.0.3 智能体模式）的重新评估

- **审查日期**：2026-08-16
- **审查人**：周子腾（D）
- **关联文档**：
  - `D4_GATE0_FORMAL_DECISION_20260807.md`（原 Gate 0 正式结论，基于 3.0.67）
  - `D4_GATE0_AGENT_MODE_MANUAL_VERIFICATION_20260816.md`（5.0.3 智能体模式人工验证）
  - `docs/baseline/v2-20260816/05_capability_boundary_reevaluation_20260816.md`（能力边界重评 v1.2）
  - `docs/baseline/v2-20260816/02_kylin_vm_environment_baseline_20260816.md`（环境基线 v2）
- **审查范围**：环境基线从 3.0.67 → 5.0.3 升级后，对 Gate 0 结论的增量重评；不重复原审查已裁决且不受版本影响的项。

---

## 一、审查背景

原 Gate 0 审查（2026-08-07）基于测试环境基线**麒灵 AI 助手 3.0.67**，其**不具备调用工具 / Skill / Harness 的能力**，导致：

- **AGT-004（真实 Tool Result）** 裁决为 BLOCKED，批准替代架构路线 B（独立 Qt 演示壳 + 执行日志 Adapter，ADR-004）；
- 真实 Kaiming Hook 路径标记「源码已开源、待编译验证」。

环境基线已按实际情况升级至 **麒灵 AI 助手 5.0.3（智能体模式，可调用工具 / Skill / Harness）**，并在麒麟 VM 完成人工验证（自选模型 + 接入 deepseek 官方云端模型，V1/V2/V3/V5-2 通过；V4 Skill/Harness 因日志无调用记录暂无法验证，详见人工验证文档）。本补充审查据此对受影响项重新裁决。

---

## 二、环境基线变化摘要（对 Gate 0 有影响的部分）

| 项 | 旧基线（3.0.67） | 新基线（5.0.3） | 对 Gate 0 的影响 |
|----|------------------|------------------|------------------|
| 工具调用能力 | ❌ 无 | ✅ 智能体模式可调用 Tool/Skill/Harness | AGT-004 宿主基础具备 |
| 模型接入 | 单一本地/固定 | 多厂商引擎插件（deepseek/qwen/baidu/xunfei 等 + 本地 LLM） | 验证手段扩充 |
| 聊天核心 ABI | `OsAssistant::chatAsync` 等（旧命名） | `kyai::assistant::OsAssistant::chatAsync` 等（nm -D 确认导出） | AGT-001 需 5.0.3 重新取证 |
| 聊天 DB Schema | RECORD 无扩展字段 | RECORD +6 字段（chat_type/is_collect/request_data/mode_type/session_uuid/has_unread）、新增 DOCUMENT_REFERENCE、knowledgebase_database.db | AGT-005 方向有利（request_data 潜在注入点） |
| 安装路径 | `/opt/apps/` | `/opt/kaiming/layers/stable/.../binary/5.0.3/` | AGT-006 部署布局变化，需重验 |
| 新增记忆相关组件 | 无 | kylin-ai-memorymap 2.0.23、知识库/文档/Recollect/数据管理服务 | MEM-001/002 待重新调查 |

---

## 三、逐项补充裁决

### 3.1 AGT-004 真实 Tool Result — **从 BLOCKED 上调为「宿主能力具备，端到端验证待推进」**

| 字段 | 原裁决（08-07） | 补充裁决（08-16） |
|------|-----------------|-------------------|
| 状态 | BLOCKED（3.0.67 无工具能力） | **上调**：5.0.3 智能体模式 + 工具调用已在麒麟 VM 人工验证通过（V1/V2/V3/V5-2） |
| 依据 | 源码已开源，待编译验证 | 环境基线 v2 + `D4_GATE0_AGENT_MODE_MANUAL_VERIFICATION_20260816.md` |
| 说明 | 真实 Hook 路径 BLOCKED | 5.0.3 宿主具备工具调用能力，真实 Tool Result 的宿主侧前提已满足；**但本项目 Hook（事件捕获 → Memory Service 落库）端到端链路仍需在 5.0.3 上重新实现并验证**，不得将「宿主能调工具」等同「本项目 Hook 已验证」 |
| 状态标签 | BLOCKED | **PARTIAL / 宿主能力已证 + 本项目集成待验证** |

**裁决**：AGT-004 由 BLOCKED 上调为 **PARTIAL（宿主能力已证 E4，本项目 Hook 集成待 5.0.3 重新验证）**。通过标准仍须覆盖成功 / 失败 / 取消三场景 [02 §3.3]。

**对 ADR-004（替代架构路线 B）的处理**：
- 保留为**备份路线**，不撤销（真实 Hook 端到端尚未在 5.0.3 验证通过，Route B 仍是风险兜底）；
- 待真实 Hook 在 5.0.3 上完成成功/失败/取消验证后，再由 D/E 主审决定是否降级为仅演示用途。

### 3.2 AGT-001 chatAsync ABI — 确认需在 5.0.3 重新取证

| 字段 | 值 |
|------|-----|
| 原状态 | ABI_VERIFIED / E3（3.0.67） |
| 新状态 | **ABI_VERIFIED（5.0.3 符号已确认，Build ID 需重取）** |
| 依据 | 05 文档 §2.3：`kyai::assistant::OsAssistant::chatAsync`、`initWithChatHistory`、`setChatAsyncCallback`、`stopChat`、`clearContext` 已由 nm -D 确认导出 |
| 待办 | 记录 5.0.3 的 libkyai-assistant.so Build ID（`0ffedd8f74c6cec8d0096c9a924d67104ca9b222`，02 文档 §2.1）并更新能力矩阵 |

### 3.3 AGT-005 Memory Context 注入 — 方向有利，待 request_data 实验

| 字段 | 值 |
|------|-----|
| 原状态 | UNTESTED / E0-E2 |
| 新状态 | **UNTESTED（方向有利）** |
| 依据 | 05 文档 §2.3：RECORD 表新增 `request_data` 字段，可能是官方预留的模型请求侧数据通道；若验证属实，Memory Context 可写 `request_data` 而非污染 `message` |
| 待办 | P0：在麒麟 VM 做 `request_data` 读写语义实验；原「不得原地修改 RECORD.message」原则不变 |

### 3.4 AGT-006 构建/部署/回退 — 部署布局已变，需重新验证

| 字段 | 值 |
|------|-----|
| 原状态 | UNTESTED / E1-E3（/opt/apps 布局） |
| 新状态 | **UNTESTED（部署布局已变）** |
| 依据 | 应用迁移至 `/opt/kaiming/layers/stable/x86_64/app/<id>/binary/5.0.3/`，Kaiming run 封装；旧 /opt/apps 路径结论不可直接沿用 |
| 待办 | 5.0.3 路径下的构建基线记录、备份、最小 KYSEC 授权、部署前快照、异常回退复验 [02 §4.5] |

### 3.5 MEM-001 / MEM-002 官方记忆能力 — 维持「待重新调查」（P0）

| 字段 | 值 |
|------|-----|
| 原状态 | NOT_FOUND（3.0.67 时代） |
| 新状态 | **待重新调查（不能维持 NOT_FOUND）** |
| 依据 | 05 文档 §2.4：memorymap 2.0.23、知识库服务、数据管理服务、Recollect 独立服务已安装 |
| 影响 | 自研 Memory Service 边界可能与官方组件重叠，需先调查官方记忆能力边界再定自研范围 |

### 3.6 不受环境升级影响的项（维持原裁决）

| Gate 0 项 | 原裁决 | 补充说明 |
|-----------|--------|---------|
| 部署 ECHO-009（顺序修复） | PASS_WITH_DEBT（TD-DEPLOY-001） | 与助手版本无关，维持 |
| KYSEC | PASS_WITH_DEBT（TD-KYSEC-001） | 与助手版本无关，维持 |
| 原文隔离 | PASS（UT-1 11/11） | 本项目 UDS Echo 层结论不变；5.0.3 聊天 DB 的原文隔离链路另需按新 Schema 复测 |
| UDS IPC | PASS_WITH_DEBT（TD-IPC-002~004） | 自研协议，与助手版本无关，维持 |
| 长度前缀 JSON / 错误码 / deadline / protocol_version | 已冻结 | 自研协议，不受环境升级影响，冻结结论继续有效 |

---

## 四、能力矩阵增量更新（相对 08-07 结论）

| 能力 ID | 08-07 状态 | 08-16 补充状态 | 责任轨道 |
|---------|-----------|----------------|---------|
| AGT-004 真实 Tool Result | PARTIAL(模拟) + BLOCKED(真实) | **PARTIAL（宿主能力已证 E4 + 本项目集成待验证）** | C/D |
| AGT-001 chatAsync ABI | ABI_VERIFIED(3.0.67) | ABI_VERIFIED(5.0.3，Build ID 已记录，语义待重取) | C/D |
| AGT-005 Context 注入 | UNTESTED | UNTESTED（request_data 提供有利方向，P0 实验） | C |
| AGT-006 Hook 部署回退 | UNTESTED | UNTESTED（部署布局迁移至 /opt/kaiming/layers） | D |
| MEM-001/002 官方记忆能力 | NOT_FOUND | 待重新调查（memorymap 2.0.23 等已安装） | E |

---

## 五、技术债与风险更新

| 编号 | 标题 | 状态变化 | 说明 |
|------|------|---------|------|
| R-ARCH-05 | 真实 Kaiming Hook 未验证 | In Progress → **维持 In Progress（载体变化）** | 验证载体从「3.0.67 源码编译」切换为「5.0.3 智能体模式 + 工具调用」，宿主能力已证，端到端 Hook 集成仍待做 |
| TD-007 | Tool Result Hook 源码级设计 | Open → 维持 Open | 5.0.3 上重新实现后关闭 |
| 新增风险 | 5.0.3 智能体模式与官方 memorymap/知识库能力边界未知 | **高** | P0 调查官方记忆组件，避免自研范围与官方重叠 |
| 新增风险 | request_data 字段语义未验证 | 中高 | P0 读写语义实验后再定注入契约 |
| 新增风险 | /opt/kaiming/layers 部署布局下的 KYSEC/回退未验证 | 中 | 5.0.3 完整工程链路重验 |

---

## 六、对三项冻结任务的结论

1. **Gate 0 人工审查**：原 5 项裁决中，与助手版本无关的项（部署/KYSEC/原文隔离/UDS IPC）维持不变；AGT-004 由 BLOCKED 上调为 PARTIAL（宿主能力已证）。**Gate 0 总体结论维持「PASS / PASS_WITH_DEBT」，不因环境升级而回退。**
2. **IPC 协议冻结**（长度前缀 JSON / 错误码 / 幂等 / deadline / protocol_version）：**不受影响，冻结结论继续有效**，可推进正式冻结。
3. **数据库初版 / 部署路径 / 失败路由冻结**：自研 SQLite schema 与部署路径不受助手版本影响，可继续；需在冻结审查中补充 5.0.3 聊天 DB Schema 变化（RECORD +6 字段、knowledgebase_database.db）作为对照项。

---

## 七、需人工裁决 / 下一步

1. **确认本补充审查裁决**：AGT-004 上调为 PARTIAL（宿主能力已证）是否接受；ADR-004 备份路线处理方式。
2. **证据状态**：V1/V2/V3/V5-2 证据已落库 `evidence/l2-kylin-vm/d4_agent_mode_5_0_3_20260816/` 并登记 `evidence/index.yaml`（AGT-004-5.0.3-001）；V4 Skill/Harness 无日志记录无法验证。
3. **P0 调查**：request_data 读写语义实验；官方 memorymap/知识库/数据管理能力边界调查。
4. **5.0.3 真实 Hook 端到端**：在 5.0.3 上重新实现 Tool 事件捕获 → Memory Service 落库，覆盖成功/失败/取消三场景。
5. **更新 01 能力矩阵与 VERSION_MAP**：按 §四 增量更新。

---

## 签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 审查人 | 周子腾（D） | 2026-08-16 | 待确认 |
| Reviewer 1 | 待填写 | | |
| Reviewer 2 | 待填写 | | |
