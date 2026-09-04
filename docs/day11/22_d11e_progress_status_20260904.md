# D11E 进度总览与证据索引（2026-09-04）

## 工作清单状态（台账 D11-E：同一虚拟机全功能联调）

| # | 工作项 | 状态 | 证据/说明 |
|---|---|---|---|
| 1 | 基线与环境盘点 | ✅ | `docs/day11/04/09/11/16`；VM `Kylin-V11-2603-D11E-0820036-Test`；基线 `main@cc4acf6`（已同步 #135/138/140/141/136） |
| 2 | 业务验收矩阵 | ✅ | `06_d11e_acceptance_matrix_20260903.md` |
| 3 | 真实案例/评委路径 | ✅（文档） | `07_d11e_real_case_judge_path_20260903.md`；可执行 VM 脚本待 L2 |
| 4 | UI 文案/证据/安全确认 | ✅（静态） | `08_*`；运行态待同 VM |
| 5 | 同 VM 端到端验收 | 🟡 部分 | 服务部署+偏好/遗忘软删闭环+广回归（b70827c/f263d5b 采集，见 11/12/13/18/19/20）；**cc4acf6 VM 复跑与 C 主演示/A 真实 SDK 完整 E2E 待执行** |
| 6 | L0/L1 回归 | ✅ | 主机 571（17/21 log）；VM 535/571（10/19 log）、广回归 1744/1780（14/20 log） |
| 7 | 收口与 D Review | ⏳ | PR #132（Draft）待 D 非作者 Reviewer；Draft→Ready 由用户手动 |

## 跨轨交付记录

- D：PR #139/#141（embedding 线程竞态）已合入 main（#141）；D1 VM 正式部署口径由 D 轨确认；D2 检索主链接线仍待 D（`memory.retrieve` main chain pending）。
- C：C 轨回填（入口/输入/构建配方/汇总灯规格）；C canonical adapter（#140）已合入 main；C3 `preference.list` removed 过滤语义待 E/D 决策（建议服务端默认过滤或 `include_removed`）。
- A：A 轨报告（A1/A3 需可写 VM 复跑；A2 文档可交付）；A DRIFT-001（#135）已合入 main；真实 SDK E2E 仍待 A 可写 VM（D11E 克隆只读无法装 python3-dev）。

## 仍需完成（外部/跨轨）

1. D2：`memory.retrieve`/MemoryContext 主链接线（D 轨）→ 遗忘后排除 SEC-FORGET-05 可验证。
2. A1/A3：A 轨可写 VM 构建 `cpp-bridge` 复跑真实 SDK Embedding（10 用例）并归档 `cc4acf6` 证据。
3. C2/C4：memory-client 在可写环境构建 + 运行态截图（或 B/D 在可写 VM 按 C 配方构建）。
4. D Review（PR #132）→ 合并。

## 说明

- 本文件为 D11E 交付状态总览；证据文档见 `docs/day11/04~21_*`。
- VM 当前 poweroff；`cc4acf6` 同 VM 复跑与完整 RC-01..07 端到端在 VM 重启后执行。