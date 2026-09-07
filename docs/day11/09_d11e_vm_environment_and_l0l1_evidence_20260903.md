# D11E 麒麟 VM 运行环境与 L0/L1 实测证据（2026-09-03）

## 概览

- VM：`Kylin-V11-2603-D11E-0820036-Test`（VirtualBox 链接克隆，源=长期 B 轨基线快照 `20-btrack-test-deps-20260821`，GUI 前台运行，NAT SSH `127.0.0.1:2222`）。
- 来宾：银河麒麟桌面 V11 2603（x86_64），kernel `6.6.0-63-generic`，Python `3.12.3`，根分区可用约 24 GiB。
- 被测提交：`f4d9a00`（D11E PR #132 合并头 = `main@b70827c` + D11E 文档 04–08；E 业务运行时代码与 `main@b70827c` 一致）。
- 部署方式：宿主 git bundle → 回环 HTTP 传输 → 来宾 `git clone` 至 `~/kylinOS-agent-memory`；依赖安装至 `~/d11e-pylibs`（隔离系统 pydantic 1.10）。

## 运行环境事实（来宾实测）

| 项 | 值 |
|---|---|
| Vector Engine | `kylin-ai-vector-engine 1.2.0.1-0k0.11`（systemd user 服务 active） |
| Vector SDK Client | `libkysdk-vector-engine-client 1.2.0.0-0k0.7` |
| Vector UDS | `/tmp/kylin-ai-vector-engine-1000.sock` 存在 |
| Python | 3.12.3（系统） |
| E 测试依赖 | `~/d11e-pylibs`：pydantic 2.13.5 / sqlalchemy 2.0.52 / pytest 9.1.1 / alembic |
| 项目工作树 | `~/kylinOS-agent-memory` @ `f4d9a00`（干净检出） |

## L0/L1 实测结果

- 命令：`PYTHONPATH=~/d11e-pylibs python3 -m pytest -q -p no:cacheprovider <16 个 E 轨测试文件>`
- 结果：**535 passed in 4.89s**（退出码 0）。
- 原始输出：`docs/day11/10_d11e_vm_l0l1_regression_20260903.log`。
- 覆盖：domain 模型（D4E）、业务边界/契约兼容（D4E）、候选治理与准入（D5E）、多源安全对抗（D6E）、偏好业务与版本（D7E）、知识/冲突/生命周期（D8E）、检索业务治理（D9E）、遗忘策略（D10E）。

## 边界与结论口径

- 本证据证明：E 业务语义与隔离/安全护栏在**麒麟宿主 Python 3.12** 上通过 L0/L1（单测/流程层）。
- **不构成** D11E 完成证据：`kylin-memory` 服务已在 D11E VM 按 D11D 产物部署并通过 health/IPC 冒烟（validation profile，见 `docs/day11/11_d11e_vm_service_deploy_e2e_probe_20260903.md`），但含真实数据与 A/B/C 输入的**同 VM 端到端业务验收（工作清单项 5，RC-01..07）仍未执行，保持 `UNVERIFIED`**；完整验收依赖 C 轨 QML 主演示、B 轨真实检索/删除输出与 A 轨真实 SDK 同 Commit 输入。
- 复现路径见上文「部署方式」与「L0/L1 实测结果」；本批未修改任何生产代码、冻结契约或其他轨道交付物。

## 建议下一步（跨轨确认项）

1. **已确认复用 D11D 统一 VM 环境**：由 D 轨以 D11D 部署产物（`packaging/systemd/install_kylin_memory.sh`、`kylin-memory.service`、DB 迁移）在 D11E 验收 VM/快照上提供 `kylin-memory` 服务，使同 Commit 端到端验收可行；
2. C 轨主演示（D11 5 步编排）在真实 VM 运行输入与 B 轨真实检索/删除输出就绪；
3. 以上就绪后按 `docs/day11/07_d11e_real_case_judge_path_20260903.md` 案例卡 D11E-RC-01..07 执行并归档证据。
