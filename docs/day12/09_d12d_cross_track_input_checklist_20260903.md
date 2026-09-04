# D12D 跨轨输入核对表（2026-09-03，Path C）

> 分支 fix/D12D-stability-gate（PR #131）；仓库基线已 merge 同步 origin/main@44d9474。
> 口径：真实 Embedding/SDK 调用采信 A 轨 D12A L2；本 VM 非 embed 同 Commit（tested_commit=0820036）完成部署/重启/权限/IPC。

## 核对表

| 输入 | 责任轨 | 内容 | D12D 处理 / 状态 | tested_commit / 基线 |
|---|---|---|---|---|
| A-1 Embedding/SDK 健康与性能 | A | bridge_loaded=true、dim=768、异常输入、性能 avg77.7ms/p99 97.6ms ≤180ms | **采信 A 轨 D12A L2**（PR #100 `D12A-L2-VERIFY`）；D VM 降级路径（bridge 编译 + 服务降级）已验证 | A：#100 分支（D12A-L2 实测）；D VM：0820036 |
| A-2 cpp-bridge 接线 | A | 假实现/吞异常审计、health executor 分项 | 采信 A（#100 合入 main@22cb497 及后续 44d9474） | 22cb497→44d9474 |
| B-1 检索/删除/重建一致性 | B | D11B/D13B 检索账本、删除运行器 | 采信 B 轨既有 L2 账本；本 VM 无 KySec 信任 vector_bridge_cli 未复跑（如实标注） | D11B/D13B 账本（B 侧） |
| B-2 重启后索引一致性（TD-055/Issue #118） | B/D | 服务/OS 重启后 health/index/检索可用 | D 侧重启自启 PASS（本 VM）；检索一致性以 B 轨复测为准（跨轨 pending） | D VM：0820036 |
| C-1 端到端演示调用路径 | C | D11C #116（5 Demo 路径）、C-D12 #127 修复 | 采信 C 轨输入；D VM 无 C 客户端，真实 VM 交互复测跨轨 pending | #116 合入 7ad9945；#127 合入 44d9474 |
| E-1 安全/假实现/业务验收 | E | 独立 Review、假实现审计 | 交 E 非作者 Reviewer（本 PR 待审查） | — |
| D-1 本 VM 实测（服务/重启/权限/IPC/日志） | D（代行） | install/start、服务重启、OS 整机重启自启、UDS IPC fail-closed、权限 0700/0600、日志脱敏 | **已完成**（证据 docs/day12/08 + evidence/l2-kylin-vm/d12d_pathc_* + index D12D-PATHC-01~07；install readiness 已修复并重跑 RC=0） | 0820036 |

## 结论
- A/C 输入采信并标注来源；B 检索一致性、C 真实 VM 交互为跨轨 pending，不代实现、不冒充本 VM 实测。
- 本表不改变 D12D 完成定义边界：完整故障注入、稳定性 Gate 达标仍待后续/另行授权。