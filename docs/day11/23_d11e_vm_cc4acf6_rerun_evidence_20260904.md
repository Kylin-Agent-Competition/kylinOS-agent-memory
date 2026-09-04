# D11E 麒麟 VM cc4acf6 基线复跑证据（2026-09-04，Host-Only 网络）

## 概览

- VM：`Kylin-V11-2603-D11E-0820036-Test`（2026-09-04 重建的干净克隆，VirtualBox GUI 前台，Host-Only 接入）。
- 来宾：yanmouren778，Kylin V11 2603 / Python 3.12.3；Host-Only IP `192.168.56.101`（SSH 直连，不再依赖 NAT）。
- 被测提交：**`2698f7c`**（D11E PR #132 head = `main@cc4acf6` + D11E 文档；含 A#135/B#138/C#140/D#141/D12D#136 drift 合并）。
- 环境：`~/d11e-pylibs` 依赖（pydantic 2.13.5 / sqlalchemy 2.0.52 / pytest 9.1.1）；`kylin-memory.service`（validation profile）active；DB 迁移到 head；Vector Engine UDS 正常。

## 结果

| 项 | 结果 |
|---|---|
| E 轨 L0/L1 | **571 passed in 5.48s**（日志 `docs/day11/24_d11e_vm_e_l0l1_cc4acf6_20260904.log`） |
| 广回归 | **1799 passed / 39 skipped / 0 error**（340.39s；日志 `docs/day11/25_d11e_vm_broad_regression_cc4acf6_20260904.log`） |
| health（IPC） | ok：db=ok，outbox backlog=0，方法集含 E 业务 validation 方法 |

## 说明与口径

- 相对 f263d5b：E 571 不变；广回归 1780→1799（#135/#138/#140/#141/#136 新增用例），0 error。
- 39 skipped 仍为 A 轨真实 SDK Embedding 用例（本 VM 只读模式无法构建 `cpp-bridge`；A 轨需在可写 VM 复跑，见 15/22）。
- 本复跑为 D11E 项 5/6 在 `cc4acf6` 的 VM 侧证据刷新；检索主链（`memory.retrieve`）与 C 主演示完整 E2E 仍 `UNVERIFIED`，待 D2 接线与 C/A 可写 VM 输入。
- 网络说明：NAT 宿主侧端口转发异常（VBox 宿主服务问题），改 Host-Only（192.168.56.101）直连后正常；此为本机环境调整，不影响被测代码与证据口径。
- 未修改生产代码/冻结契约。
