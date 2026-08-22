# TD-004 关闭路径提请：冻结 routing-switch 等价方案（请 D 轨确认）

> 提请方：B 轨（D5B）
> 提请对象：D 轨主审（Provider/SQLite/Outbox/IPC 关注方）
> 提请性质：按 `TECHNICAL_DEBT_REGISTER.md` TD-004 关闭条件「由 D/B 冻结并验证 maintenance-window/routing-switch 等价方案」，正式提请 D 轨对 **routing-switch 等价方案**作冻结确认，作为 TD-004 的关闭路径。
> 关联 PR：#51（`feature/d5-b-retrieval-vertical-slice`）；本提请基于证据归档 commit `146c359`，提请文档自身提交于 commit `5cefde0`

---

## 1. 提请冻结的具体内容

D 轨确认冻结以下等价方案，作为未取得"原子 Collection swap"宿主能力时，Vector 索引代次切换的**唯一允许激活方式**：

1. **激活方式 = `routing_switch`**：新代次构建 + 校验通过后，通过 **drop-old + keep-new**（丢弃旧 serving generation、保留新 generation 作为 serving）完成切换；不使用也不宣称 `atomic_switch`。
2. **失败不替换旧代次**：新代次构建/验证失败时，旧 serving generation 保持可用，不因失败而替换或标记异常。
3. **旧代次清理由独立、可审计、幂等的生命周期步骤执行**，与激活解耦。
4. **能力声明**：`supports_atomic_generation_switch` 保持 `false / UNTESTED`（08 §6.6 契约字段），不猜测为真；`activation_mode` 显式返回 `routing_switch`（或经授权的 `maintenance_window`），绝不选 `atomic_switch`。

## 2. 提请依据

### 2.1 契约层面已冻结，本方案不越界
- `docs/day3/08_vector_retrieval_contract_v1.md` §6.6已冻结 `activation_mode ∈ {atomic_switch, maintenance_window, routing_switch}`，并明确：
  - 当前无原子 Collection swap 宿主证据时，Provider 必须显式返回 activation_mode；
  - `atomic_switch` 仅当 capabilities 明确支持且取得目标宿主证据时允许；
  - 失败重建不得替换旧 serving generation，恢复路径须可审计。
- `B-D3-019 / B-D3-T023`：未验证原子切换前 capability=false，强制选 maintenance/routing，禁止假定 Collection rename 原子。
- 该约束已在 `memory-service/retrieval/validation.py:resolve_activation_mode()` 落地：`supports_atomic=False` 时请求 `atomic_switch` 直接报错。

### 2.2 宿主实证（V005，能力否定）已归档
- SDK 源码：`2213447ef765e709e93f94d4177f4417478fe8ea`；运行库：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`；基线 `origin/main@8bf4c9b`。
- 麒麟 VM（Kylin V11 x86_64）运行 `tests/vector-engine/d5_vector_atomic_switch.cpp`（候选 SHA `dd137146…`），日志 `evidence/l2-kylin-vm/v005_atomic_switch_20260823.log`（SHA `a12243c1…`）。
- 结果：**SDK API 面无 rename/swap/replace 原子切换操作**；唯一切换原语为 drop-old + keep-new（routing switch）。探针输出 `atomic_switch_capability="absent; only drop-old + keep-new routing switch available"`。
- 报告：`docs/day3/16_d5b_retrieval_vertical_slice_host_report_20260823.md`；登记：`evidence/index.yaml` `B-D3-V005`；矩阵：`09_retrieval_contract_review_matrix.md` → `PASS_VM / TD-004 Open`。

### 2.3 多代次模式可行性（V004）已归档
- `tests/vector-engine/d4_vector_generation_rebuild.cpp`（候选 SHA `f77d9cf3…`），日志 `evidence/l2-kylin-vm/v004_generation_rebuild_20260823.log`（SHA `99707a68…`）。
- 结果：新代次构建不干扰 serving（gen_A 保持 100 行可查）；失败不替换旧代次（`code=1002` 错误注入后 gen_A 仍完整）；drop-old 后新代次成为 serving（50 行可查）。与 §6.6 冻结约束逐条一致。

## 3. 请求 D 轨确认/批准的事项

请 D 轨主审确认以下一项或多项，并回复批准记录：

- [ ] **冻结 routing-switch 等价方案**为 TD-004 的关闭路径（认可 V005 能力否定实证 + V004 多代次模式验证）。
- [ ] 确认关闭后不放松能力矩阵：`supports_atomic_generation_switch=false/UNTESTED`，激活仅走 `routing_switch`/`maintenance_window`，禁止 `atomic_switch`。
- [ ] 确认 TD-004 由 `Open` → `Resolved`（或登记为「已接受等价方案」），并同意 B 轨同步回写 `TECHNICAL_DEBT_REGISTER.md` 与能力矩阵。

## 4. 批准后 B 轨将执行

1. 将 `TECHNICAL_DEBT_REGISTER.md` TD-004 状态改为 `Resolved`（附 D 轨批准人/日期/条件），引用 16 号报告与 V005 日志 SHA。
2. 保持 `supports_atomic_generation_switch=false`、激活走 `routing_switch`，同步 01 能力矩阵状态。
3. 明确边界：本冻结仅约束"索引代次切换"激活方式；不替代 PR#51 自身独立 Reviewer 的 `APPROVED`；V007 正式量化评测仍待 E 轨 Gold Label/封存集。

## 5. 边界与不虚标声明

- 本提请不将 TD-004 标记为关闭；仅在 D 轨冻结批准后由 B 轨据批准记录执行状态变更。
- 未伪造"原子切换已取得宿主证据"；能力矩阵保持 `UNTESTED`。
- 若 D 轨要求补充故障注入/恢复路径证据，B 轨按 D 轨意见补充后再行关闭。

---
**提请人**：B 轨（gaoyizhe934）
**日期**：2026-08-23
**请 D 轨主审在本文件/对应 PR 评论中回复：`APPROVED`（附批准人、日期、接受的边界条件）或所需补充项。**
