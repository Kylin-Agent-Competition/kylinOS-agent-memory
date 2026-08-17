# ADR-004：Gate 0 真实 Tool Result 路线 B 替代架构批准

- **状态**：已采纳（2026-08-17 起保留为备份路线，真实 Hook 端到端未通前不撤销）
- **日期**：2026-08-07（2026-08-17 增补环境基线 v2 复审）
- **责任轨道**：C（OS Agent Hook、MemoryClient）、D（IPC、部署）
- **适用范围**：Gate 0 前置门禁「真实 Tool Result」（能力矩阵 AGT-004）的验证路径选择

## 背景

Gate 0 前置门禁要求「真实 Tool Result（成功 / 失败 / 取消）」取得宿主证据后，方可冻结对应接口 [02 §3.3、§16.0]。原环境基线为麒灵 AI 助手 3.0.67，其**不具备调用工具（Tool）/ Skill / Harness 的能力**，导致真实 Tool Result 路径无法在宿主验证：

1. D2-1 原始调查以「闭源二进制，6 条阻断原因」标记真实 Kaiming Hook 为 BLOCKED；
2. `reviewDocuments/openkylin_blocker_survey.md` 后续调查确认 kylin-aiassistant 及其上下游组件在 openkylin **完全开源**，原始阻断原因大部分不成立，源码可获取但尚未在 VM 内完成编译与 Socket 路径修改验证；
3. 独立模拟客户端（`kaiming_memory_client`）已完成 6/6 PASS [ECHO-003]，覆盖 UDS 协议全链路；
4. Gate 0 阶段不具备生产级 Hook 部署条件（构建环境、KYSEC 授权、GUI-only 触发等限制）。

因此需在「真实 Hook 尚未跑通」的前提下，决定 Gate 0 阶段采用何种 Tool Result 验证路径以解除 D4 BLOCKED 状态，同时不把「模拟」表述为「真实」。

## 候选方案

### 方案 A：真实 Kaiming Hook（源码编译 + Socket 路径修改）

在 VM 内 `git clone kylin-aiassistant` → 编译 → 源码层审计 Socket 路径 → 修改指向自研 Memory Service → 集成测试输出结构化 `ToolExecutionEvent`。

优点：

- 证据链最完整，直接验证生产路径；
- 一旦跑通即可关闭 R-ARCH-05 与 TD-007。

缺点：

- 依赖完整构建工具链（dev 包、qmake、cmake 等）；
- GUI-only 触发无法自动化（Wayland 无 xdotool、D-Bus 无消息注入）；
- 构建环境与 KYSEC 授权在 Gate 0 阶段不齐备，短期不可达。

### 方案 B：独立 Qt 演示壳 + 执行日志 Adapter

用独立 Qt 演示壳模拟 AI 助手的 Tool 调用入口，配合执行日志 Adapter 输出结构化 Tool Result，验证 Tool Result → Memory Service 契约。

优点：

- 无需依赖官方源码编译，可立即推进；
- 可独立、可重复地验证 Tool Result 契约（成功 / 失败 / 取消三类）；
- 与已完成的独立模拟客户端（6/6 PASS）共用 UDS 协议验证成果。

缺点：

- 不验证真实宿主 Hook 路径，存在「演示通过 ≠ 生产可用」的表述风险；
- 需在所有文档与证据中如实标注「真实 Hook BLOCKED / 待验证」。

### 方案 C：Gate 0 不选择，推迟到实现阶段

优点是避免提前承诺；缺点是 D4 BLOCKED 无法解除，IPC 协议冻结、数据库初版冻结等下游动作全部被阻塞。

## 决策

选择**方案 B（独立 Qt 演示壳 + 执行日志 Adapter）作为 Gate 0 阶段 Tool Result 验证路径**，并作出以下三点约束：

1. **Gate 0 阶段接受**独立 Qt 演示壳 + 执行日志 Adapter 作为 Tool Result 契约验证路径，满足成功 / 失败 / 取消三类覆盖 [02 §3.3]；
2. **真实 Kaiming Hook 编译验证与 Socket 路径修改在 D4 阶段推进**（源码已可获取，无需等待 Gate 1）；
3. **所有文档与证据必须如实标注**「真实 Hook BLOCKED，已批准替代架构」，不得将模拟验证表述为真实宿主 Hook 已验证。

## 原因

- 解除 D4 BLOCKED 是继续冻结 IPC 协议、数据库初版、部署路径的前置条件 [02 §3.3]；
- 独立模拟客户端已覆盖 UDS 协议全链路，方案 B 与既有验证成果复用度最高；
- 真实 Hook 虽源码开源，但 Gate 0 阶段构建 / 授权 / 触发条件均不齐备，强行方案 A 会引入不可控进度风险（R-ARCH-05）；
- 方案 B 不阻塞真实 Hook 在 D4 阶段并行推进，两者互不替代。

## 影响

### 架构影响

- Tool Result 契约与 Memory Service 接入通过演示壳先行定形，真实 Hook 接入时以同一契约为准；
- 必须区分「模拟路径证据」与「真实路径证据」两条状态线，能力矩阵分别标注。

### 开发影响

- C 轨需实现独立 Qt 演示壳与执行日志 Adapter，输出结构化 Tool Result（成功 / 失败 / 取消）；
- D 轨在 D4 推进真实 Hook 源码编译与 Socket 路径修改（关联 R-ARCH-05、TD-007）。

### 安全与表述影响

- 任何文档、能力矩阵、代码注释、证据索引不得将模拟验证写成「真实宿主 Hook 已验证」；
- 证据等级标注须如实：模拟路径 PARTIAL/E4，真实路径 BLOCKED。

## 回滚方式

- 真实 Kaiming Hook 在 5.0.3（或后续版本）完成「成功 / 失败 / 取消」端到端验证后，本 ADR 的替代路径由 D/E 主审决定降级为「仅演示用途」或撤销；
- 若替代路径（演示壳 + Adapter）被证明无法满足 Tool Result 契约要求，回退为方案 C（Gate 0 维持 BLOCKED，重新评估），不得以删除测试或虚标证据方式换取通过。

## 证据与限制

- `evidence/index.yaml`：`D2-1-KAIMING-HOOK`（UNBLOCKED/E4）、`D4-OPENKYLIN-HOOK`（PARTIAL/E3）、`AGT-004-5.0.3-001`（HOST_VERIFIED/E4，宿主能力已证）；
- `reviewDocuments/openkylin_blocker_survey.md`：kylin-aiassistant 完全开源调查结论；
- `deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md`：阶段 0-5 修复计划；
- `D4_GATE0_FORMAL_DECISION_20260807.md` §二：本 ADR 原始批准记录。

## 修订记录

| 版本 | 日期 | 修订内容 |
| --- | --- | --- |
| v1 | 2026-08-07 | 初版：批准替代架构路线 B（独立 Qt 演示壳 + 执行日志 Adapter） |
| v2 | 2026-08-17 | 增补：环境基线升级至 5.0.3（智能体模式 + 工具调用已宿主验证），AGT-004 由 BLOCKED 上调为 PARTIAL（宿主能力已证 E4）；本 ADR 保留为**备份路线**，真实 Hook 端到端未通前不撤销、不降级 |
