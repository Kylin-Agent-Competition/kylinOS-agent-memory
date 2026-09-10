# D14C：主线同步与 D15C 输入消费审计（2026-09-10）

> 性质：D14C preparation 的静态 intake audit。本文只消费已合入的主线材料和
> 当前工作树的确定性测试；不访问麒麟 VM、不创建 formal evidence root、不改变
> production route、也不产生 `HOST_VERIFIED`、`L3 PASS` 或 `D14C complete` 结论。

## 审计身份

| 项 | 值 |
| --- | --- |
| D14C development HEAD | `e5268ad1911a6fe87625475f2b2e3c0c0505f2d5` |
| D14C 同步前 HEAD | `77319aa4ce75d7f7fe4d7ed64f7332cffdb88441` |
| 已合入的本地主线 ref | `origin/main@a7abb1e71c03c4f1558e5c6a9eff2b9f36437993` |
| 正式 runtime tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| 合并方式 | `merge(main): 同步 D14C 主线基线`；无冲突，D14C harness 保留 |
| 远端刷新 | 未完成：本机 GitHub 凭据不可用；本文只对上述本地 `origin/main` ref 作出结论 |

`e5268ad` 是运行 D14C preparation 工具的 development HEAD，不是 formal runtime
tested commit。formal handoff 仍必须把 D13D、D14A 和 D14D 的运行时身份绑定到
`ba3b50e`，并以各自的 SHA-256 和环境身份完成逐项校验。

## 本次消费的主线输入

`a7abb1e` 已包含 D15C #167 的 handoff、证据目录和 D14E Phase 1 baseline。D15C
handoff 的可消费事实严格限于：

| 输入 | 可消费结论 | 不能推出的结论 |
| --- | --- | --- |
| TD-007 | outbound Hook 已实测并有结构化 `tool_invocation` 证据 | 不等价于 Tool 的完整回程或三态完成 |
| TD-008 | `chatAsync` 输入未观察到 `memory_context` 等字段；因聊天 LLM 缺失，结论仍为 `AMBIGUOUS` | 不得写成 Host 注入已验证或未实现已定论 |
| TD-009 | outbound 已验证；回程因 `model is empty` 仍 `BLOCKED` | 不得写成 SUCCESS/FAILED/CANCELLED 完整闭环 |
| Production identity | `tool_id` 仅是 outbound tool selector；`rowid` / `sessionID` / `msgIndex` 尚未在真实时序中取得 | 不得把 `tool_id` 当作 Chat DB record identity |
| 回退演练 | 原二进制 SHA 已还原一致且助手可启动 | 不替代 D14C formal run 的完整回退验收 |

D14E Phase 1 baseline 的快照还登记：#167 的 D review 为
`REQUEST_CHANGES / REWORK`，且 `HIGH-01`、`HIGH-02`、`MEDIUM-01` 未闭合。这是
已合入快照中的状态；因为本机无法刷新远端，不能将它表述为当前 GitHub 的实时
review 状态。

## D14C Gate 判定

| Gate | 状态 | 依据 |
| --- | --- | --- |
| G1 frozen runtime baseline | `READY_TO_CONSUME` | D13D/D14A/D14D 的 formal runtime identity 仍绑定 `ba3b50e` |
| G2 clean VM + final package lineage | `READY_TO_CONSUME` | 仅可消费 D14D/D14A 已冻结 lineage；D14C 自身 runtime identity 仍未采集 |
| G3 D14C development assets | `DEVELOPMENT_READY_FORMAL_PENDING` | harness 与其测试保留于 `e5268ad` |
| G4 Host DB / resolver binding | `BLOCKED` | Production identity 未解析，D15C handoff 未提供可批准的 SourceReference |
| G5 trusted host identity | `BLOCKED` | 尚无 D 主审批准的 final identity manifest |
| G6 production routes | `BLOCKED` | `turn.finalized`、`event.ingest`、`forget.preview`、`forget.execute` 尚无 ACTIVE formal handoff |
| G7 MemoryContext mapping | `BLOCKED` | hit / no-match / failure 的正式 frozen mapping 未提供 |
| G8 unique formal evidence root | `NOT_CREATED_BY_DESIGN` | G4--G7 任一未关闭即禁止创建 |

因此：

```text
D14C_PREPARATION = ADVANCED / IN_PROGRESS
D14C_FORMAL_L3 = BLOCKED
D14C_FORMAL_RESULT = UNVERIFIED
```

## 验证结果

在既有隔离 Python 环境中，以下 D14C 契约测试均通过：

```text
memory-service/tests/test_d14c_l3_harness.py
memory-service/tests/test_d14c_runtime_precheck.py
memory-service/tests/test_d14c_runtime_precheck_cli.py
memory-service/tests/test_d14c_evidence_package.py

26 passed
```

未运行 formal preflight：它需要 G4--G7 均关闭后的真实 formal handoff；在当前
输入下运行只能产生预期拒绝，不能提供新的 D14C 证据。

合并引入的 D14E baseline test 在本 D14C 分支上有一项失败：它要求快照输入提交
`87fe5ad` 必须是当前 HEAD 的祖先，但该提交不在此分支的历史中。这是 D14E
测试的跨分支祖先假设，不是 D14C harness 的失败；本审计不修改该跨轨测试。

## 下一步（依赖顺序）

1. 获取并消费 #167 rework 关闭后的 D 主审批准及 ProductionSourceReference / trusted identity 输入（G4、G5）。
2. 获取 D 轨四条 production route 的 `ACTIVE` formal handoff（G6）。
3. 获取 C/D/E 批准的 MemoryContext freeze（G7）。
4. 仅在 G4--G7 全部为 PASS 后组装唯一 formal handoff，运行 preflight，并创建一次新的 formal evidence root。
