# D13C L2 状态汇总 — B 轨 + D 轨交付合并视图（C 轨视角）

> **编制**：C 轨（李田皓），2026-09-05。
> **输入**：
> - B 轨交付：`docs/day13/09_d13c_l2_b_track_delivery_20260903.md`（main@`b70827c`，2026-09-03）
> - D 轨交付：PR #149（main squash `2cba0115`，2026-09-05），VM baseline @ `053754d`
> **用途**：确定 D13C 会话评测报告 `provenance.runtime_status` 的逐项升级依据，
> 并固化 C 轨专属 L2 待办。

---

## 1. L2 结论总览（32 项）

| 轨 | 总项数 | VERIFIED | FAILED→BLOCKED | PARTIAL/BLOCKED |
|---|---|---|---|---|
| B 轨 | 12 | 6 | 0 | 6 |
| D 轨 | 20 | 4 | 2 | 14 |
| **合计** | **32** | **10** | **2** | **20** |

### VERIFIED 明细（10 项）

| # | 轨 | 结论项 | 关键指标 | 绑定 commit |
|---|---|---|---|---|
| B-L2-01 | B | FTS5 通道可用 | P50=0.10ms / P95=0.34ms | `b70827c` |
| B-L2-02 | B | Vector 通道可用 | 搜索/过滤/隔离 PASS | `b70827c` |
| B-L2-04 | B | 检索延迟可接受 | P50=0.10ms / P95=0.34ms | `b70827c` |
| B-L2-08 | B | 跨会话检索结果可区分 | 双通道隔离验证 | `b70827c` |
| B-L2-10 | B | Vector 精确删除 | 15/15，残留 0 | `b70827c` |
| B-L2-11 | B | FTS5 精确删除 | 残留 0 | `b70827c` |
| D-L2-01 | D | UDS socket 可监听 | 权限 0600 | `053754d` |
| D-L2-02 | D | 客户端可连接 Gateway | echo 连接成功 | `053754d` |
| D-L2-03 | D | 长度前缀协议编解码 | envelope 校验通过 | `053754d` |
| D-L2-06 | D | retrieve 延迟可接受 | 30 样本，p50=1.703ms / p95=3.656ms | `053754d` |

### BLOCKED 根因聚类（22 项）

| 根因 | 涉及项 | 责任轨 |
|---|---|---|
| gateway 检索主链未接线（context.assemble seam 缺失） | B-L2-03/05/06/07 | B+D |
| `memory.retrieve` 返回 `context=[]`，需完整空 MemoryContext ADR | D-L2-04/05 | **C/D/E 联合** |
| turn.finalized host mapping 未生产化 | D-L2-07~10 | C host mapping + D |
| C++ client VM 超时断言 / slow-handler 场景 | D-L2-11/12 | **C** + D |
| forget host mapping + C ViewModel | D-L2-13~17 | C + D |
| C 轨五步编排未部署到 VM | D-L2-18~20，B-L2-09 | **C** |

---

## 2. C 轨会话评测指标 ↔ L2 升级矩阵

D13C 会话评测报告（`d13c-session-eval-report/v1`）各指标的 Runtime 升级条件：

| 指标 | 依赖 L2 项 | 当前 Runtime 状态 | 升级条件 |
|---|---|---|---|
| `latency_p50/p95`（retrieve） | B-L2-04 + D-L2-06 | **可标注 VERIFIED**（双轨均过阈值） | 已满足：B P50=0.10ms / D P50=1.703ms |
| `latency_p50/p95`（forget/turn） | D-L2-13/07 | UNVERIFIED | forget/turn host mapping 生产化 |
| `ipc_method_coverage`（echo/connect） | D-L2-01/02/03 | **可标注 VERIFIED**（IPC 通道部分） | 已满足 |
| `ipc_method_coverage`（turn/forget 全集） | D-L2-07~17 | UNVERIFIED | host mapping 生产化 |
| `isolation_pass_rate` | B-L2-08 + D-L2-04 | **PARTIAL**（检索层 VERIFIED，context 层 BLOCKED） | D-L2-04 ADR 落地 |
| `cross_session_isolation` | B-L2-08/09 | **PARTIAL**（单次区分 VERIFIED，5 轮串台复测 BLOCKED） | C 编排部署 VM |
| `step_completion_rate` | D-L2-18~20 | UNVERIFIED | C 编排部署 VM |
| `stop_retry_violation`（Runtime 部分） | D-L2-08/09 | UNVERIFIED | turn.finalized host mapping |
| `guardrail_critical_count` | B 轨隔离 + D 轨跨用户 | **PARTIAL**（引擎层 VERIFIED，事务层 BLOCKED） | D-L2-13~16 |

**结论**：无任何指标可整体升级为 `VERIFIED`；`latency` 与 `ipc_method_coverage`
（通道子集）可标注 `PARTIAL_VERIFIED` 并引用 B/D 轨证据 commit。D13C 报告的
`provenance.runtime_status` **整体保持 `UNVERIFIED`**（fail-closed：部分通道
VERIFIED 不构成整体会话链路 VERIFIED）。

---

## 3. C 轨专属 L2 待办清单（从 B/D 轨交付中提取）

以下待办由 B/D 轨交付明确指向 C 轨，是解除 16+ 项 BLOCKED 的钥匙：

### C-1. 空 MemoryContext 完整映射 ADR（三轨联合，最高优先）

- **解除**：D-L2-04/05（直接）、B-L2-05/06/07（间接）
- **要求**（D 轨 PR #149 明确）：不得只替换为 3 个 D13C 命名字段；需冻结完整
  空 `MemoryContext` 响应映射——payload 身份校验、`context_version`、时间戳、
  token budget、安全 `skipped` 状态
- **C 轨动作**：C 侧候选解析器（memory-client MemoryContext 严格解析）参与
  ADR 联审；对应 host mapping 工作已在 `feat/C-host-mapping` 线程推进
  （TurnExtractionAdapter 等）
- **产出**：C/D/E 会签 ADR + 双侧实现

### C-2. C++ MemoryClient 麒麟 VM 超时状态断言

- **解除**：D-L2-11
- **现状**：L0 S4（`test_d13c_stability.cpp` deadline_timeout_client_block）
  已在 Mock Gateway 验证 5000ms fail-closed；需在 VM 对真实 Gateway 复测
- **C 轨动作**：VM 部署 memory-client + 慢响应场景，断言 stage=timeout /
  busy=false / 可恢复；原始客户端状态与 Chat DB 查询结果归入同一证据批次
  （对应 D 轨执行文档 §L2 Procedure 第 5 步）

### C-3. C ViewModel VM 集成（forget 链路）

- **解除**：D-L2-16/17
- **现状**：L0 已有 forget 测试（D10C 18 项 + Mock 凭据闭环）；需 VM 上对
  真实 forget host mapping 验证 forgetCrossUserBlocked / forgetSelectorCleared
- **依赖**：D 轨 forget host mapping 先生产化

### C-4. 五步编排 + resetAllPipelines VM 部署

- **解除**：D-L2-18/19/20 + B-L2-09
- **现状**：L0 S1/S5/S6（复跑 5 轮 / 跨会话隔离复跑 / reset 防回写）已 Mock
  验证；D11-C 编排页面已存在
- **C 轨动作**：memory-client QML 应用部署到麒麟 VM，对真实 Gateway 复跑
  5 轮编排，采集 UI/请求/日志/DB 四路证据
- **前置**：C-1（MemoryContext 映射）+ turn.finalized/forget host mapping

### C-5. 会话评测 L2 bundle 生成

- **最终交付**：D 轨执行文档 §L2 Procedure 第 4-5 步完成后，C 轨用
  `scripts/run_d13c_session_eval.py` 消费真实 VM 会话 bundle，产出
  Runtime VERIFIED 的会话评测报告，`runtime_status` 整体升级

---

## 4. 口径声明

- 本汇总为文档级状态归集，**不构成任何新的 Runtime 证据**。
- B/D 轨 VERIFIED 结论绑定各自声明的 commit（`b70827c` / `053754d`），
  非 D13C PR head；引用时需注明 commit 绑定关系。
- C 轨 D13C 报告整体 `runtime_status` 保持 `UNVERIFIED`，直至 C-1~C-4
  全部完成且真实会话 bundle 复算通过。
