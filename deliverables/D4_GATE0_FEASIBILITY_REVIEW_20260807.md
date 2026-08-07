# Gate 0 状态与 D4 三项工作可行性审查报告

- 对照文档：`02_architecture_sop.md` v1.1 / 2026-07-29；`01_sdk_capability_boundary.md` v1.1 / 2026-07-28
- 审查日期：2026-08-07
- 依据：`D4_开工前置条件清单_20260806.md` + 基线文档 §3.3 Gate 0、§16.0 前置门禁、§16.8-16.9 冻结契约流程
- 审查范围：判断以下三项工作当前是否具备启动条件
  1. 主持 Gate 0 人工审查
  2. 冻结长度前缀 JSON、错误码、幂等、deadline 和 protocol_version
  3. 冻结数据库初版、部署路径与失败路由

---

## 1. Gate 0 四项当前状态

D4 开工前置条件清单明确要求"4 项 Gate 0 全部有结论"。以下逐项汇总当前证据与状态。

### 1.1 Hook 构建 / 部署 / KYSEC / 回退 — PARTIAL

| 子项 | 状态 | 证据 |
|---|---|---|
| 构建 | PASS | ECHO-008 PASS；DAY2_GAP 确认 S1.2 全部通过 |
| 部署 | **FAIL** | ECHO-009 FAIL（二进制缺失，root_cause: install.sh 先于 build 执行） |
| KYSEC | UNVERIFIED | ECHO-005 INFO（`/sys/kernel/security/kysec/` 不可用）；ACL 两面模式通过；脚本缺 `--socket` 实现 |
| 回退 | PASS（5 项缺口） | ECHO-006 PASS；D2-7.2/7.5/7.7/7.8/7.9 对比缺失；PID 64432 残留 |

### 1.2 Memory Context 注入与原文隔离 — PARTIAL

| 子项 | 状态 | 证据 |
|---|---|---|
| JSON 合法性 (R1) | PASS | `}}"` 闭合修复，服务端无 PROTOCOL_ERROR |
| 断言正确性 (R2) | PARTIAL（冲突） | PR21: 6/6 PASS；DAY2_GAP: 5/6 PASS（KAIMING-STORE 因 INTERNAL_ERROR 被判 FAIL） |
| 原文隔离 | **UNTESTED** | 无独立测试用例 |

### 1.3 真实 Tool Result — PARTIAL / BLOCKED

| 子项 | 状态 | 证据 |
|---|---|---|
| 独立模拟客户端 | PASS | 6/6 PASS exit=0 |
| 真实 Kaiming Hook | **BLOCKED** | 闭源二进制，6 条阻断原因，路线 B 调查报告完成 |
| 综合 | PARTIAL/BLOCKED | 通过标准要求"覆盖成功、失败和取消" [02 §3.3]，真实路径未通 |

### 1.4 Kaiming → UDS IPC — PARTIAL

| 子项 | 状态 | 证据 |
|---|---|---|
| Socket 路径一致性 | PASS（带冲突） | PR21: 7 组件已修复；DAY2_GAP: `--socket` 参数整体缺失 |
| UDS Echo 全链路 | PASS | ECHO-003 UDS PASS |
| 权限 | PARTIAL | systemd RuntimeDirectory 不可确认 |
| 超时 | PARTIAL | deadline_ms 已定义但行为复测不完整 |
| 重连 | PARTIAL | 单连接阻塞式，未验证重连 |
| 重启复测 | 未覆盖 | 无 OS 重启复测证据 |

**四项 Gate 0 均未达到 PASS。**

---

## 2. 逐项工作可行性判断

### 工作 1：主持 Gate 0 人工审查 — ✅ 可立即进行

**结论：这是解除当前 D4 BLOCKED 状态的关键步骤。**

依据 [02 §3.3] Gate 0 失败路由：

> Gate 0 未通过时，不得冻结对应接口，也不得继续按"完整 OS Agent 集成已可行"的假设开发。失败路由包括：
> - 启用批准的独立 Qt 演示壳（须如实标注差异）
> - 人工 Gate 评估 D-Bus 或带鉴权本地 TCP（保持上层契约不变）

当前需要人工审查裁决的事项：

| 待裁决项 | 问题 |
|---|---|
| 部署 ECHO-009 FAIL | 是否接受 PARTIAL 标记 PASS_WITH_DEBT？修复计划与责任轨道？ |
| KYSEC UNVERIFIED | 是否登记技术债继续推进？最低可接受证据是什么？ |
| 原文隔离 UNTESTED | 是否可从 R1/R2 间接推定为 PASS_WITH_DEBT？ |
| 真实 Tool Result BLOCKED | 是否走批准的替代架构（独立 Qt 演示壳 / 执行日志 Adapter）？ |
| UDS IPC PARTIAL | 权限/超时/重连/重启是否登记为技术债并在 D4 补齐？ |

**前置依赖：** 权威基线资料入库与版本复核（D4 清单该项同样未满足），建议与人工审查并行完成。

### 工作 2：冻结 IPC 协议子集 — ⚠️ 部分可冻结

**核心约束** [02 §3.3]：Gate 0 未通过前，不得冻结对应接口。需逐项区分冻结对象与 Gate 0 项的关联度。

| 冻结对象 | 关联 Gate 0 项 | 当前证据 | 可冻结？ | 说明 |
|---|---|---|---|---|
| 长度前缀 JSON（IPC 协议格式） | 第 4 项 | UDS Echo 全链路 E4 PASS，Python + C++ 双端一致 | **✅ 可冻结** | 格式本身已验证通过，不直接依赖其他三项 |
| protocol_version ("1.0") | 第 4 项 | 双端实现一致 | **✅ 可冻结** | 同上 |
| deadline (deadline_ms) | 第 4 项 | 协议中已定义，结构明确 | **⚠️ 可冻结定义** | 超时行为复测不完整，冻结时须标注 DEFERRED：行为验证待 D4 L2 补齐 |
| 错误码 | 跨项 | IPC 层 `memory_echo_server.py` 有枚举；Bridge 层 `bridge_error_contract.h` 有定义 | **⚠️ 可冻结现有枚举** | 两套定义尚未统一成一份契约；冻结时标注 DEFERRED：统一错误码契约待 D4 对齐 |
| 幂等 | 跨项 | **未见定义** | **❌ 不可冻结** | 尚未设计，无对象可冻结。需在 D4 完成幂等方案设计后再进入冻结流程 |

**前置动作：** 冻结前须更新能力矩阵中 IPC-001 的状态（当前标记 UNTESTED/E0，与 E4 证据不符）。

### 工作 3：冻结数据库初版、部署路径与失败路由 — ❌ 当前不可进行

依据 [02 §16.8-16.9]：冻结契约需要"已接受契约 + ADR + 未决项标记为 DEFERRED"。当前三项均不满足最低验证标准。

| 冻结对象 | 当前状态 | 阻断原因 |
|---|---|---|
| 数据库初版 | `migrations/` 仅有 README.md | 无实际 schema 文件；SQLite 真源设计尚未落地；D4-D 服务骨架 `memory-service/app` 不存在 [D4 清单] |
| 部署路径 | ECHO-009 **FAIL** | install.sh 先于 build 执行导致二进制缺失；部署流程未通过麒麟 VM 验证；systemd unit 文件 RuntimeDirectory 不可确认 |
| 失败路由 | 无设计文档 | Outbox/Dead Letter 模式仅在架构文档 [02 §11.3] 中有概念描述；无实现、无契约、无 ADR |

---

## 3. 建议执行顺序

```
1. 【可立即执行】工作 1：主持 Gate 0 人工审查
   ├── 并行：完成权威基线资料入库与版本复核
   ├── 逐项裁决四项 Gate 0 的 PARTIAL/BLOCKED 状态
   ├── 对真实 Tool Result 决定是否走批准的替代架构
   └── 产出：书面 Gate 0 结论（PASS / PASS_WITH_DEBT / 替代方案批准）

2. 【Gate 0 审查后】工作 2：冻结 IPC 协议子集
   ├── 冻结长度前缀 JSON + protocol_version（已具备 E4 证据）
   ├── 冻结 deadline 定义（标注超时行为验证待 L2 补齐）
   ├── 冻结现有错误码枚举（标注统一契约待 D4 对齐）
   ├── 更新能力矩阵 IPC-001 状态为 HOST_VERIFIED / E4
   └── 设计并冻结幂等方案（D4 新任务）

3. 【D4-D 服务骨架就绪后】工作 3：冻结数据库与部署
   ├── 前提：D4-D 完成 memory-service/app、Migration、Outbox 基础
   ├── 前提：部署路径通过麒麟 VM 验证（修复 ECHO-009 FAIL）
   └── 届时冻结：数据库初版 Schema、部署路径、失败路由
```

---

## 4. 附加发现：能力矩阵不一致

审查过程中发现 `01_sdk_capability_boundary.md` 中以下条目与当前证据不一致，建议在 Gate 0 审查前或同时修正：

| 能力 ID | 当前标记 | 建议修正 | 依据 |
|---|---|---|---|
| IPC-001 (UDS 可访问性) | UNTESTED / E0 | HOST_VERIFIED / E4 | UDS Echo 全链路在麒麟 VM 通过 |
| AGT-005 (Memory Context 注入) | UNTESTED / E0/E2 | PARTIAL / E4（R1+R2 部分通过） | R1 PASS + R2 6/6 模拟通过，原文隔离仍 UNTESTED |
| AGT-004 (真实 Tool Result) | PARTIAL / E2/E4 | PARTIAL / E4（模拟） + BLOCKED（真实 Hook） | 需区分模拟与真实路径状态 |

---

## 5. 参考资料

- `D4_开工前置条件清单_20260806.md`
- `02_architecture_sop.md` v1.1 / 2026-07-29 — §3.3 Gate 0、§16.0 前置门禁、§16.8-16.9 冻结契约
- `01_sdk_capability_boundary.md` v1.1 / 2026-07-28 — §12.1 P0 能力认证、能力矩阵
- `evidence/gate0_echo/final/evidence.jsonl`
- `deliverables/DAY1_KYLIN_RUNTIME_PENDING.md`
- `deliverables/DAY2_KYLIN_RUNTIME_PENDING.md`
- `deliverables/DAY2_EVIDENCE_GAP_ANALYSIS.md`
- `deliverables/PR21_REVIEW_ACTION_ITEMS.md`
- `os-agent-integration/echo/memory_echo_server.py`
- `cpp-bridge/bridge_error_contract.h`