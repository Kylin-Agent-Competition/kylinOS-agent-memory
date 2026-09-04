# D11E 麒麟 VM f263d5b 基线复跑证据（2026-09-04）

## 概览

- VM：`Kylin-V11-2603-D11E-0820036-Test`（GUI 前台）；来宾 yanmouren778，Kylin V11 2603 / Python 3.12.3。
- 被测提交：**`a12ca33`**（D11E PR #132 head = `main@f263d5b` + D11E 文档；运行时与 `f263d5b` 一致，含 E 轨 schema-drift 修复 #137）。
- 环境：`~/d11e-pylibs` 依赖；`kylin-memory.service`（validation profile）active；Vector Engine `1.2.0.1-0k0.11` + SDK client `0k0.7`，UDS socket 正常。

## 结果

| 项 | 命令 | 结果 |
|---|---|---|
| E 轨 L0/L1 | `PYTHONPATH=~/d11e-pylibs python3 -m pytest -q -p no:cacheprovider <16 E 轨文件>` | **571 passed in 3.70s**（日志 `docs/day11/19_d11e_vm_e_l0l1_f263d5b_20260904.log`） |
| 广回归 | `PYTHONPATH=~/d11e-pylibs:memory-service python3 -m pytest -q -p no:cacheprovider memory-service/tests evaluation --ignore=test_embedding_service_real.py` | **1780 passed / 39 skipped / 0 error**（172.42s；日志 `docs/day11/20_d11e_vm_broad_regression_f263d5b_20260904.log`） |
| health（IPC） | `health` 信封 | ok：db=ok，outbox backlog=0，方法集含 E 业务 validation 方法 |

## 说明与口径

- 相对 b70827c 基线：E 轨 L0/L1 535→571、广回归 1744→1780（#137 为 `test_domain_models_d4e.py` 等新增用例）；D3 lifecycle 竞态 error 本次未复现。
- 39 skipped 仍为 A 轨真实 SDK Embedding 用例（D11E 克隆只读模式无法构建 `cpp-bridge`，见 `15_*`）。
- 本复跑刷新 VM 侧证据至 `f263d5b`；检索主链（`memory.retrieve`）与 C 主演示/真实 SDK 的完整 E2E 仍 `UNVERIFIED`，待 A/C/D 合入后复核。
- 未修改生产代码/冻结契约。
