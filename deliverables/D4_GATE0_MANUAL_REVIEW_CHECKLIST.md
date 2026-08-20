# Gate 0 人工审查工作清单

- **来源文档**：`deliverables/D4_GATE0_FEASIBILITY_REVIEW_20260807.md`
- **审查日期**：2026-08-07
- **依据**：`D4_开工前置条件清单_20260806.md` + 基线文档 §3.3 Gate 0、§16.0 前置门禁、§16.8-16.9 冻结契约流程
- **背景**：四项 Gate 0 均未达到 PASS，人工审查是解除 D4 BLOCKED 状态的关键步骤

---

## 一、待裁决事项（5 项）

依据 [02 §3.3] Gate 0 失败路由，以下 5 项需人工逐项裁决：

| # | 待裁决项 | 当前状态 | 问题 | 裁决结果 |
|---|---------|---------|------|---------|
| 1 | **部署 ECHO-009** | FAIL | 是否接受 PARTIAL 标记为 PASS_WITH_DEBT？修复计划与责任轨道如何安排？ | 
| 2 | **KYSEC** | UNVERIFIED | 是否登记为技术债继续推进？最低可接受证据标准是什么？ | 已知原版kylin-desktop镜像并不包含kysec内核，暂时登记为技术债，最低接受标准为kysec登记表中能够正确显示相应的权限|
| 3 | **原文隔离** | UNTESTED | 是否可从 R1/R2 间接推定为 PASS_WITH_DEBT？ ||
| 4 | **真实 Tool Result** | BLOCKED | 是否批准替代架构路线（独立 Qt 演示壳 / 执行日志 Adapter）？ ||
| 5 | **UDS IPC** | PARTIAL | 权限/超时/重连/重启等缺口是否登记为技术债并在 D4 补齐？ ||

---

## 二、Gate 0 四项逐项状态回溯

### 2.1 Hook 构建 / 部署 / KYSEC / 回退 — PARTIAL

| 子项 | 状态 | 证据 |
|------|------|------|
| 构建 | PASS | ECHO-008 PASS；DAY2_GAP 确认 S1.2 全部通过 |
| 部署 | **FAIL** | ECHO-009 FAIL（二进制缺失，root_cause: install.sh 先于 build 执行） |
| KYSEC | UNVERIFIED | ECHO-005 INFO（`/sys/kernel/security/kysec/` 不可用）；ACL 两面模式通过；脚本缺 `--socket` 实现 |
| 回退 | PASS（5 项缺口） | ECHO-006 PASS；D2-7.2/7.5/7.7/7.8/7.9 对比缺失；PID 64432 残留 |

### 2.2 Memory Context 注入与原文隔离 — PARTIAL

| 子项 | 状态 | 证据 |
|------|------|------|
| JSON 合法性 (R1) | PASS | `}}"` 闭合修复，服务端无 PROTOCOL_ERROR |
| 断言正确性 (R2) | PARTIAL（冲突） | PR21: 6/6 PASS；DAY2_GAP: 5/6 PASS（KAIMING-STORE 因 INTERNAL_ERROR 被判 FAIL） |
| 原文隔离 | **UNTESTED** | 无独立测试用例 |

### 2.3 真实 Tool Result — PARTIAL / BLOCKED

| 子项 | 状态 | 证据 |
|------|------|------|
| 独立模拟客户端 | PASS | 6/6 PASS exit=0 |
| 真实 Kaiming Hook | **BLOCKED** | D2-1 原始调查标记为"闭源二进制，6 条阻断原因"；`reviewDocuments/openkylin_blocker_survey.md` 调查发现 kylin-aiassistant 已在 openkylin 完全开源，源码可获取但尚未在 VM 内编译验证 |
| 综合 | PARTIAL/BLOCKED | 通过标准要求"覆盖成功、失败和取消" [02 §3.3]，真实路径未通 |

### 2.4 Kaiming → UDS IPC — PARTIAL

| 子项 | 状态 | 证据 |
|------|------|------|
| Socket 路径一致性 | PASS（带冲突） | PR21: 7 组件已修复；DAY2_GAP: `--socket` 参数整体缺失 |
| UDS Echo 全链路 | PASS | ECHO-003 UDS PASS |
| 权限 | PARTIAL | systemd RuntimeDirectory 不可确认 |
| 超时 | PARTIAL | deadline_ms 已定义但行为复测不完整 |
| 重连 | PARTIAL | 单连接阻塞式，未验证重连 |
| 重启复测 | 未覆盖 | 无 OS 重启复测证据 |

---

## 三、前置依赖

以下前置条件需与人工审查并行完成：

| # | 前置依赖 | 当前状态 |
|---|---------|---------|
| P1 | 权威基线资料入库与版本复核 | D4 清单该项未满足 |
| P2 | 修正能力矩阵不一致项（见附录 A） | 3 项不一致待修正 |

---

## 四、审查产出要求

审查完成后须产出：

- [ ] **书面 Gate 0 结论**：逐项判定 PASS / PASS_WITH_DEBT / 替代方案批准
- [ ] **技术债登记**：对 PARTIAL 项明确技术债编号与责任人
- [ ] **替代架构批准记录**：如真实 Tool Result 走替代路线，须有正式 ADR
- [ ] **IPC 冻结范围确认**：明确可冻结对象清单（长度前缀 JSON、protocol_version）及 DEFERRED 标注项

---

## 五、建议执行步骤

```
步骤 1【可立即执行】
  主持 Gate 0 人工审查
  ├── 并行：完成权威基线资料入库与版本复核
  ├── 逐项裁决四项 Gate 0 的 PARTIAL/BLOCKED 状态（见"一、待裁决事项"）
  ├── 对真实 Tool Result 决定是否走批准的替代架构
  └── 产出：书面 Gate 0 结论

步骤 2【Gate 0 审查后】
  冻结 IPC 协议子集
  ├── 冻结长度前缀 JSON + protocol_version（已具备 E4 证据）
  ├── 冻结 deadline 定义（标注超时行为验证待 L2 补齐）
  ├── 冻结现有错误码枚举（标注统一契约待 D4 对齐）
  ├── 更新能力矩阵 IPC-001 状态为 HOST_VERIFIED / E4
  └── 设计并冻结幂等方案（D4 新任务）

步骤 3【D4-D 服务骨架就绪后】
  冻结数据库与部署
  ├── 前提：D4-D 完成 memory-service/app、Migration、Outbox 基础
  ├── 前提：部署路径通过麒麟 VM 验证（修复 ECHO-009 FAIL）
  └── 届时冻结：数据库初版 Schema、部署路径、失败路由
```

---

## 附录 A：能力矩阵不一致项（审查前修正）

| 能力 ID | 当前标记 | 建议修正 | 依据 |
|---------|---------|---------|------|
| IPC-001 (UDS 可访问性) | UNTESTED / E0 | HOST_VERIFIED / E4 | UDS Echo 全链路在麒麟 VM 通过 |
| AGT-005 (Memory Context 注入) | UNTESTED / E0/E2 | PARTIAL / E4（R1+R2 部分通过） | R1 PASS + R2 6/6 模拟通过，原文隔离仍 UNTESTED |
| AGT-004 (真实 Tool Result) | PARTIAL / E2/E4 | PARTIAL / E4（模拟） + BLOCKED（真实 Hook） | 需区分模拟与真实路径状态 |

---

## 参考资料

- `D4_开工前置条件清单_20260806.md`
- `02_architecture_sop.md` v1.1 / 2026-07-29 — §3.3 Gate 0、§16.0 前置门禁、§16.8-16.9 冻结契约
- `01_sdk_capability_boundary.md` v1.1 / 2026-07-28 — §12.1 P0 能力认证、能力矩阵
- `evidence/gate0_echo/final/evidence.jsonl`
- `deliverables/DAY1_KYLIN_RUNTIME_PENDING.md`
- `deliverables/DAY2_KYLIN_RUNTIME_PENDING.md`
- `deliverables/DAY2_EVIDENCE_GAP_ANALYSIS.md`
- `deliverables/PR21_REVIEW_ACTION_ITEMS.md`