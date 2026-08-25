# ADR-008：embedding 子服务方法域独立承认（ALIGN-004）

- **状态**：🟡 提议 / 待审（D 已选方案 A；独立 Review 通过前不标记"已采纳"，Reviewer：E（谢嘉然）待签）
- **日期**：2026-08-24
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（IPC）为主，E 审查
- **决策版本**：`subsvc-method-v1`
- **适用范围**：`memory-service/embedding` 子服务对外方法路由；关联 FRZ-IPC-007、ALIGN-004

## 背景

1. **FRZ-IPC-007 冻结顶层方法路由**（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25`）：
   活跃 3 项 `echo / health / memory.retrieve`；`memory.store` 未实现返回 `UNSUPPORTED_METHOD`；`evidence.record` 已按 P0-4 移除。
2. **embedding 子服务使用另一套方法**（`memory-service/embedding/embedding_service.py` `_METHODS`）：
   `memory.embed / memory.embed_batch / memory.ping / memory.health`，不在 FRZ-IPC-007 顶层路由内。
3. **ALIGN-004 登记该偏离**（冻结声明 §3.2）：`embedding 另用 memory.embed/embed_batch/ping/health`，对齐动作「子服务方法纳入统一路由，或 ADR」。
4. **架构事实**：embedding 是 Memory Service 的一个**子服务模块**（向量化），与 echo（Gate 0 验证服务）分属不同服务边界与进程；二者方法命名空间不重叠、不冲突。

## 候选方案

### 方案 A：承认子服务方法域（本 ADR 决策）

embedding 作为 Memory Service 子服务，保留独立方法域 `memory.embed / memory.embed_batch / memory.ping / memory.health`；Phase 2 建统一 Gateway（`app/api/gateway.py`）时，由 Gateway 统一路由，子服务方法域并入统一 `METHOD_ROUTER`。

优点：

- 不混淆服务边界：embedding 不处理 `echo/memory.retrieve`，echo 不处理 `memory.embed`；
- 与 ADR-005 方案 A 一致（「各子服务对外统一冻结枚举 + envelope」，方法域属子服务内部路由）；
- 改动最小、无兼容破坏，Phase 2 统一 Gateway 是既定的收敛点（checklist Phase 2.2）。

缺点：

- 在 Phase 2 之前，embedding 与 echo 的 method 白名单并存（两套 `_METHODS` / `METHOD_ROUTER`），需在统一 Gateway 时显式合并，避免遗漏。

### 方案 B：立即并入 FRZ-IPC-007 顶层路由

把 `memory.embed/embed_batch/ping/health` 并入顶层路由表。

缺点：

- embedding 服务若识别 `echo/memory.retrieve` 会越界；echo 服务若识别 `memory.embed` 亦越界；
- 在统一 Gateway 尚未建立时强制合并，语义错位、易产生跨服务误路由；
- 违背「子服务方法域」分层意图（`session-handoff-20260809.md:39` 分层 `IPC Gateway → Application Service → ...`）。

### 方案 C：维持现状不裁决

不写 ADR、不改代码。

缺点：ALIGN-004 偏离持续登记却无处置结论，违反冻结「冻结后对齐」义务。

## 决策

选择方案 A：`subsvc-method-v1`。**承认 `memory-service/embedding` 为子服务方法域（`memory.embed/embed_batch/ping/health`），与 FRZ-IPC-007 顶层路由（`echo/health/memory.retrieve`）分属不同服务边界；Phase 2 统一 Gateway 时合并路由。**

- `_METHODS`（embedding 子服务白名单）保持不变，代码注释标注 ALIGN-004 + 本 ADR 依据；
- Phase 2（`app/api/gateway.py`）统一 `METHOD_ROUTER` 时，将子服务方法域并入统一路由表（承接 checklist Phase 2.2）。

### 变更控制

- 子服务方法域新增方法（如 `memory.embed` 变体）属子服务内部扩展，不触碰 FRZ-IPC-007 顶层路由；
- 顶层路由（`echo/health/memory.retrieve` 等）变更仍走 IPC 冻结 ADR 流程（FRZ-IPC-007）。

## 影响

### 架构影响

- 子服务方法域与顶层路由分层清晰，符合 `IPC Gateway → Application Service → 子服务` 分层；
- Phase 2 统一 Gateway 是唯一收敛点，本 ADR 不引入新的运行时组件。

### 开发影响

- Phase 0 无需修改 `_METHODS`；Phase 2 建 Gateway 时合并路由（`echo/health/memory.retrieve` + `memory.embed/embed_batch/ping/health`）。

### 评测影响

- 失败路由验收仍按冻结 5 枚举断言（ADR-005）；方法路由按各自服务白名单断言。

### 安全影响

- 无新增；子服务 method 白名单继续由 `parse_envelope(expected_methods=...)` 强制校验。

## 回滚与替代条件

若未来决定子服务方法并入顶层单一方法域，可经新 ADR 撤销本 ADR，但须在统一 Gateway 落地后进行（避免回退到「两套白名单并存」的偏离状态），并经独立 Reviewer 批准。

## 证据与限制

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25`（FRZ-IPC-007）、`:65`（ALIGN-004）
- `deliverables/D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md:93`（embedding 方法集 `memory.embed/embed_batch/ping/health`）
- `memory-service/embedding/embedding_service.py` `_METHODS`
- `deliverables/D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md` Phase 0.4 / Phase 2.2

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：D 决策选方案 A（2026-08-24）；Reviewer E（谢嘉然）待签署。

> **范围限定（治理澄清）**：本 ADR 仅处理 **method routing**（embedding 子服务方法域与 FRZ-IPC-007 顶层路由的边界），**不得被解释为批准 ALIGN-005 的当前 socket 方案**。socket ownership 归属已由 **ADR-009** 另行裁决（Memory Service/Gateway owns `memory.sock`；Embedding 子服务 owns 私有 `embedding.sock`；echo 属 Gate 0 验证细节）。
