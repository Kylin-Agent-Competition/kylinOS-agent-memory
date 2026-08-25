# ADR-009：UDS socket ownership 归属裁决（ALIGN-005）

- **状态**：🟡 提议 / 待审（D 已决策；Reviewer E（谢嘉然）待签）
- **日期**：2026-08-25
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（IPC）为主，E 审查
- **决策版本**：`socket-ownership-v1`
- **适用范围**：Memory Service / Embedding 子服务 / echo（Gate 0）三者的 UDS socket 路径归属；关联 ALIGN-005、FRZ-IPC-007

## 背景

1. **FRZ-IPC-007 冻结**（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:35-36`）：Memory Service 标准 socket 路径为 `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`；Gate 0/验证期的 echo 与 embedding 等独立 socket 属实现细节。
2. **ALIGN-005 登记偏离**（同上 `:66`）：当前实现存在 `echo /run/kylin-memory-echo/echo.sock`、`/tmp/kylin-memory-echo/echo.sock`；embedding `/tmp/kylin-memory-embed.sock`；`KMA_SOCKET_PATH=/tmp/kylin-memory-service.sock` 多套路径。
3. **实现现状**（`memory-service/embedding/server.py::_default_socket_path`）：embedding 子服务默认私有 socket `$XDG_RUNTIME_DIR/kylin-memory/embedding.sock`，**不默认占用**正式 `memory.sock`（该 socket 归 Memory Service / Phase 2 Gateway 所有）。
4. **口径冲突**：`deliverables/D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md` Phase 0.5 曾写「裁定唯一 socket 路径 `memory.sock`，3 套路径收敛」，与实现（独立 `embedding.sock`）及 ADR-008 范围限定（「不得被解释为批准 ALIGN-005 当前 socket 方案」）三者不一致。

## 候选方案

### 方案 A：承认分属 ownership（本 ADR 决策）

不同服务/子服务拥有各自的 UDS 入口 socket，不要求所有进程绑定同一个 UDS：

- **Memory Service / Phase 2 Gateway** owns `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`（对外统一入口）；
- **Embedding 子服务** owns 私有 `$XDG_RUNTIME_DIR/kylin-memory/embedding.sock`（子服务实现细节）；
- **echo** 属 Gate 0 验证服务，使用自身验证路径（`/run/kylin-memory-echo/echo.sock`、`/tmp/kylin-memory-echo/echo.sock`），为验证期实现细节。

优点：

- 与冻结声明「独立 socket 属实现细节」口径一致，不制造虚假的「唯一 socket」；
- 尊重进程/服务边界，embedding 不抢占正式 `memory.sock`（ALIGN-005 返工核心，`_remove_stale_socket` 拒绝 unlink active socket）；
- Phase 2 统一 Gateway 建起后，对外统一入口仍是 `memory.sock`，embedding 私有 socket 对调用方透明。

缺点：

- Phase 2 之前存在多个 socket 路径，需在统一 Gateway 落地时收敛对外入口（checklist Phase 2.2）。

### 方案 B：强制所有进程绑定唯一 `memory.sock`

要求 echo/embedding/Gateway 全部绑定 `memory.sock`。

缺点：

- echo（Gate 0 独立验证进程）与 embedding 子服务进程不同，强行共用同一 socket 会引入 socket ownership 抢占问题，正是本次 ALIGN-005 返工要消除的风险；
- 违背冻结声明「独立 socket 属实现细节」的口径。

## 决策

选择方案 A：`socket-ownership-v1`。**Memory Service / Phase 2 Gateway owns `memory.sock`；Embedding 子服务 owns 私有 `embedding.sock`；echo 属 Gate 0 验证细节；不要求所有进程绑定同一 UDS。**

- embedding 子服务 `_default_socket_path` 默认 `$XDG_RUNTIME_DIR/kylin-memory/embedding.sock`，不默认占用正式 `memory.sock`；
- ALIGN-005 的「冻结目标路径」`memory.sock` 解释为 Memory Service / Gateway 的对外统一入口，而非全部进程共享的单一 socket。

### 变更控制

- 新增子服务私有 socket 属子服务内部实现细节，不触碰冻结的对外 `memory.sock` 入口；
- 对外 `memory.sock` 入口变更仍走 IPC 冻结 ADR 流程。

## 影响

### 架构影响

- socket ownership 分层清晰：统一入口（`memory.sock`）与子服务私有 socket（`embedding.sock`）分离，符合「IPC Gateway → Application Service → 子服务」分层。

### 开发影响

- Phase 2 建统一 Gateway 时，对外入口统一为 `memory.sock`，embedding 私有 `embedding.sock` 作为子服务内部调用细节（承接 checklist Phase 2.2）。

### 安全影响

- 子服务私有 socket 位于 `$XDG_RUNTIME_DIR/kylin-memory/`（per-user，父目录 `_ensure_socket_dir` 收敛 0700），沿用既有 per-user 隔离。

## 回滚与替代条件

若未来决定统一所有服务绑定单一 socket，可经新 ADR 撤销本 ADR，但须在 Phase 2 统一 Gateway 落地后进行，并经独立 Reviewer 批准。

## 证据与限制

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:35-36`（memory.sock 标准路径 + 独立 socket 属实现细节）、`:66`（ALIGN-005）
- `memory-service/embedding/server.py::_default_socket_path`（embedding 私有 `embedding.sock`）
- `docs/adr/008-embedding-subservice-method-domain.md` 范围限定（socket 方案另行裁决）
- `deliverables/D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md` Phase 0.5（本 ADR 修订其口径）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：D 决策选方案 A（2026-08-25）；Reviewer E（谢嘉然）待签署。
