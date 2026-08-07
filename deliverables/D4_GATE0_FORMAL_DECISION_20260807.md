# Gate 0 人工审查正式结论

- **审查日期**：2026-08-07
- **审查依据**：[02 §3.3] Gate 0 失败路由、[02 §16.0] 前置门禁、[02 §16.8-16.9] 冻结契约流程
- **输入文档**：`D4_GATE0_MANUAL_REVIEW_CHECKLIST.md`（5项待裁决）、`UNTESTED_TRACKING_TABLE.md`（4项UNTESTED）
- **分支**：`feature/d4-gate0-review-freeze`
- **基线 Commit**：`ceb64e6` (基于 feature/uds-echo-clean 的 UNTESTED 测试提交)

---

## 一、逐项裁决结果

### 1.1 部署 ECHO-009 — PASS_WITH_DEBT

| 字段 | 值 |
|------|-----|
| 当前状态 | FAIL（二进制缺失，root_cause: install.sh 先于 build 执行） |
| 裁决 | **PASS_WITH_DEBT** |
| 修复计划 | D4 阶段修复构建顺序，在 install.sh 前执行 CMake build |
| 责任轨道 | D4-D 部署骨架任务卡（`packaging/systemd/`） |
| 技术债编号 | TD-DEPLOY-001 |

### 1.2 KYSEC — PASS_WITH_DEBT（维持 UNVERIFIED）

| 字段 | 值 |
|------|-----|
| 当前状态 | UNVERIFIED（`/sys/kernel/security/kysec/` 不可用） |
| 裁决 | **PASS_WITH_DEBT** |
| 最低可接受标准 | 1) ACL 两面模式（authorize/revoke）在 `/tmp` 和 `/run` 两个 socket 路径下通过；2) `--socket` 参数已实现；3) UNVERIFIED 标注已写入脚本头部和 status 输出 |
| 技术债编号 | TD-KYSEC-001 |
| 进展 | R4 修复完成：authorize/status/rollback 三操作在 dev 和 systemd 模式下均通过 [ECHO-005 INFO] |

### 1.3 原文隔离 — PASS（UT-1 验证通过）

| 字段 | 值 |
|------|-----|
| 当前状态 | UNTESTED（无独立测试用例）→ 现在 **11/11 PASS** |
| 裁决 | **PASS** |
| 依据 | UT-1 独立测试在麒麟 VM 上全通过：回显一致、retrieve 不注入用户原文、特殊字符（换行/Unicode/JSON注入/SQL注入/超长10KB/空字符串）、敏感信息不泄露、响应结构完整性 |
| 证据 | `evidence/gate0_echo/ut_results/ut1_results.txt`（SHA256 校验上传） |
| 注意 | Gate 0 Echo 层面通过 ≠ 生产 Memory Service 通过；后续 D4+ 阶段需验证 UI/聊天数据库 original_user_text 保存与 model_request 注入的完整隔离链路 [02 §4.1] |

### 1.4 真实 Tool Result — 批准替代架构路线

| 字段 | 值 |
|------|-----|
| 当前状态 | PARTIAL / BLOCKED（独立模拟客户端 PASS，真实 Kaiming Hook BLOCKED） |
| 裁决 | **批准替代架构路线** |
| 真实路径 | BLOCKED（闭源二进制，6条阻断原因，D2-1路线B调查报告完成） |
| 替代路径 | **路线 B**：独立 Qt 演示壳 + 执行日志 Adapter |
| ADR 编号 | ADR-004（见下文 §2） |
| 后续步骤 | Gate 1 获取 SDK 源码 → 修改 Socket 连接逻辑 → 编译验证 → 集成测试 |
| 状态标注 | 真实 Hook 标注为 BLOCKED，模拟验证路径标注为 PARTIAL/E4 |

### 1.5 UDS IPC — PASS_WITH_DEBT

| 字段 | 值 |
|------|-----|
| 当前状态 | PARTIAL（权限/超时/重连/重启缺口） |
| 裁决 | **PASS_WITH_DEBT** |
| 已通过项 | Socket 路径一致性、UDS Echo 全链路（ECHO-003 6/6 PASS）、IPC 重启复测（UT-2 10/12 PASS 核心链路全通过） |
| 缺口 | 权限（systemd RuntimeDirectory 不可确认）、超时（deadline_ms 行为复测不完整）、重连（单连接阻塞式未验证重连） |
| 技术债编号 | TD-IPC-002~004 |

---

## 二、替代架构批准记录（ADR-004）

**标题**：ADR-004 — Gate 0 真实 Tool Result 路线 B 替代架构批准

**日期**：2026-08-07

**状态**：已接受

**上下文**：
- 真实 Kaiming Hook 需要 kylin-aiassistant 源码（闭源二进制），6 条阻断原因经 D2-1 调查确认
- 独立模拟客户端（kaiming_memory_client）已完成 6/6 PASS [ECHO-003]
- Gate 0 阶段不具备生产级 Hook 部署条件

**决策**：
1. Gate 0 阶段接受独立 Qt 演示壳 + 执行日志 Adapter 作为 Tool Result 验证路径
2. 真实 Kaiming Hook 推迟到 Gate 1（获取 SDK 源码后）
3. 所有文档和证据中必须如实标注"真实 Hook BLOCKED，已批准替代架构"

**后果**：
- 正向：解除 D4 BLOCKED 状态，可继续冻结 IPC 协议
- 负向：无法在 Gate 0 验证真实 Kaiming → UDS 的完整链路，存在集成风险（R-ARCH-05）
- 缓解：模拟客户端覆盖了 UDS 协议全链路，QML 演示壳可独立验证 Tool Result 契约

---

## 三、技术债登记

| 编号 | 标题 | 状态 | 责任人 | 验收标准 |
|------|------|------|--------|---------|
| TD-DEPLOY-001 | 部署顺序修复（build 先于 install） | 新增 | D4-D | CMake build → install.sh → binary exists 三者顺序验证通过 |
| TD-KYSEC-001 | KYSEC 真实规则验证不可用 | 维持 | L2/L3 | 麒麟成品环境的 KYSEC 规则写入并验证通过 |
| TD-IPC-002 | UDS 权限（systemd RuntimeDirectory） | 新增 | D4 | systemd unit 中 RuntimeDirectory 配置可确认并在麒麟 VM 验证 |
| TD-IPC-003 | deadline_ms 行为复测不完整 | 新增 | D4 | deadline 超时后客户端正确截断，服务端不保持僵尸连接 |
| TD-IPC-004 | 重连机制未实现 | 新增 | D4-D | 客户端支持 3 次指数退避重连，有 Evidence L2 日志 |
| R-ARCH-05 | 真实 Kaiming Hook 未验证 | 维持 | Gate 1 | SDK 源码接入后编译通过，完整 ToolResultEvent 链路在麒麟 VM 跑通 |

---

## 四、Gate 0 总表

| Gate 0 项 | 子项 | 原状态 | 裁决 |
|-----------|------|--------|------|
| 1. Hook 构建/部署/KYSEC/回退 | 构建 | PASS | PASS |
| 1. Hook 构建/部署/KYSEC/回退 | 部署 | FAIL | **PASS_WITH_DEBT** |
| 1. Hook 构建/部署/KYSEC/回退 | KYSEC | UNVERIFIED | **PASS_WITH_DEBT** |
| 1. Hook 构建/部署/KYSEC/回退 | 回退 | PASS | PASS |
| 2. Memory Context 注入与原文隔离 | JSON 合法性 | PASS | PASS |
| 2. Memory Context 注入与原文隔离 | 断言正确性 | PARTIAL | PASS (R1+R2 verified) |
| 2. Memory Context 注入与原文隔离 | 原文隔离 | UNTESTED→**11/11 PASS** | **PASS** |
| 3. 真实 Tool Result | 模拟客户端 | PASS | PASS |
| 3. 真实 Tool Result | 真实 Hook | BLOCKED | **替代架构批准** |
| 4. Kaiming → UDS IPC | Socket 路径 | PASS | PASS |
| 4. Kaiming → UDS IPC | UDS Echo | PASS | PASS |
| 4. Kaiming → UDS IPC | 权限 | PARTIAL | **PASS_WITH_DEBT** |
| 4. Kaiming → UDS IPC | 超时 | PARTIAL | **PASS_WITH_DEBT** |
| 4. Kaiming → UDS IPC | 重连 | PARTIAL | **PASS_WITH_DEBT** |
| 4. Kaiming → UDS IPC | 重启复测 | 未覆盖→**10/12 PASS** | **PASS** |

**Gate 0 结论**：**全部四项 Gate 达到 PASS 或 PASS_WITH_DEBT 标准。D4 BLOCKED 状态解除。**

---

## 五、产出清单

- [x] 书面 Gate 0 结论（本文档）
- [x] 技术债登记（§三，6项）
- [x] 替代架构批准记录（§二，ADR-004）
- [x] IPC 冻结范围确认（见下一阶段产出）
- [x] 能力矩阵不一致项修正（UT-3/UT-4已完成）