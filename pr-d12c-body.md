# C-D12 缺陷清理 v3：Stop / Retry / 断线重连 / 空状态\&UI / 生产路径审计 / TD同步 / Review 全部修复

**Roll (轨道)**：C 轨（memory-client + Demo/QML + 技术债注册表）
**分支**：`codex/C-D12-fixes`（rebased on `origin/main@0820036`，ahead 5 / behind 0）

## Head commits（5 个，分组清晰）

| # | SHA       | 类型   | 说明                                                                                                                                                        |
| - | --------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `e6fea47` | fix  | 核心实现：3-attempt reconnect backoff, client deadline timeout + late-drop, strict parser payload/error msg, Stop/Retry UI, prod mock audit（9 files，+761/−167） |
| 2 | `b8d86f3` | docs | TD Register 同步 + reconnectFinished toast 转发（审查 HIGH-01/MEDIUM-02 followup）                                                                                |
| 3 | `7c36c50` | test | 4 FAIL L0 测试修复：reconnectFinished 误发、Mock close() 残留、Stop abort() 同步兜底（3 files，+47/−3）                                                                     |
| 4 | `f8c49d7` | fix  | Review R2 修复：MEDIUM-01 protocol-fatal no-reconnect + MEDIUM-02 deadline+100ms boundary test + rebase main\@0820036（5 files，+142/−14）                      |
| 5 | `db96a35` | docs | Review R2 治理回写：TD-022 关闭证据补充 `deadlineGraceBoundaryShortDeadlineTest` + commit `f8c49d7`；PR Body 刷新为最新 HEAD                                               |

## Review 处置全项对照

### Round 1 Review (REQUEST\_CHANGES → 全部修复)

| 项              | 审查发现                  | 处置                                         | 状态       |
| -------------- | --------------------- | ------------------------------------------ | -------- |
| HIGH-01        | TD 注册表未同步             | TD-022/023 Resolved、TD-IPC-004 In Progress | ✅ Closed |
| MEDIUM-01 (R1) | TD-IPC-004 关闭条件含 L2   | In Progress（L2 Close-block 登记）             | ✅ Closed |
| MEDIUM-02 (R1) | reconnectFinished 未转发 | ViewModel 信号转发 + QML toast                 | ✅ Closed |
| MEDIUM-03 (R1) | 分支未 rebase            | Rebased on `0820036`                       | ✅ Closed |

### Round 2 Review (REQUEST\_CHANGES → 全部修复)

| 项               | 审查发现                           | 处置                                                                                                                        | 状态       |
| --------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | -------- |
| MERGE GATE (R2) | 落后 main 2 commits              | Rebased on `0820036`，ahead 5 / behind 0                                                                                   | ✅ Closed |
| MEDIUM-01 (R2)  | Protocol error 后 reconnect 未禁止 | `protocolFatalDisconnect_` flag 在 `abort()` 前设置 + 回归测试 `protocolErrorDoesNotTriggerAutoReconnect`                         | ✅ Closed |
| MEDIUM-02 (R2)  | TD-022 timing boundary 未验证     | `setDeadlineMs(int)` API + `deadlineGraceBoundaryShortDeadlineTest`（deadline=100ms → 150ms 无 TIMEOUT → 200ms+ TIMEOUT 触发） | ✅ Closed |

### Round 2 Remaining — PR Body / TD 关闭证据同步（本轮修复）

| 项           | 审查发现                                           | 处置                                                      | 状态            |
| ----------- | ---------------------------------------------- | ------------------------------------------------------- | ------------- |
| PR Body 同步  | Body 仍写 base=7ad9945 / 2 commits               | 刷新为 base=0820036 / HEAD=db96a35 / 5 commits             | ✅ This commit |
| TD-022 关闭证据 | 仅引用 `clientSideDeadlineTimeout...` + `7bf51b9` | 补充 `deadlineGraceBoundaryShortDeadlineTest` + `f8c49d7` | ✅ This commit |

## 测试结果（WSL Ubuntu 22.04 + Qt 5.15.3）

```
100% tests passed, 0 tests failed out of 10
Total Test time = 20.29 sec
```

| #    | 套件                   | 结果     | 时长           | 用例数                            |
| ---- | -------------------- | ------ | ------------ | ------------------------------ |
| 1    | protocol\_adapter    | ✅ PASS | 0.01s        | 55+                            |
| 2    | memory\_client\_mock | ✅ PASS | 14.14s       | 15（含 MEDIUM-01 + MEDIUM-02 新增） |
| 3-10 | d5\~d11 demo 套件      | ✅ PASS | 0.05s\~3.37s | —                              |

## 技术债状态

| TD         | 状态              | 关闭证据                                                                                                                                        |
| ---------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| TD-022     | **Resolved**    | `clientSideDeadlineTimeoutEmitsRequestFailedAndLateResponseDropped` + `deadlineGraceBoundaryShortDeadlineTest`；commit `7bf51b9` + `f8c49d7` |
| TD-023     | **Resolved**    | 7 条 L0 用例；commit `7bf51b9`                                                                                                                  |
| TD-IPC-004 | **In Progress** | L0：3 次退避 + 4 条测试 + MEDIUM-01 protocol-fatal 抑制；L2：麒麟 VM 证据归档后 Resolved                                                                      |

## 硬约束核对

| 约束                                   | 状态                                             |
| ------------------------------------ | ---------------------------------------------- |
| commit 半角冒号 + `type(scope): desc` 格式 | ✅                                              |
| PRs must be rebased on latest main   | ✅ base = `0820036`                             |
| TD 注册表与 PR 一致                        | ✅ TD-022/023 Resolved + TD-IPC-004 In Progress |
| Demo/Prototype 声明保留                  | ✅                                              |
| memory.store 仍 UNSUPPORTED\_METHOD   | ✅                                              |
| 生产路径无假实现                             | ✅                                              |
| L0 测试注册到 ctest 10/10 green           | ✅                                              |

