# D11D 基线与环境盘点（2026-09-01）

> 对应 D11D 开工工作清单第 1 项。本文仅记录仓库与既有证据可确认的基线；未实测项一律标注来源与 `UNVERIFIED`，不以既有证据替代 D11D 专用环境实测。

## 1. 代码基线

- `origin/main@47af2fa`（2026-09-01 复核；含已合并 D11 集成基础 PR #84、D10B PR #82、A-REQ-01 PR #110 等）。
- 本批次分支：`feat/D11D-vm-integration`（自 `origin/main@47af2fa` 创建）。
- D11D 专用麒麟 VM：尚未创建/确认（见 §3）。

## 2. 既有 D 轨产物（仓库内，origin/main 基线）

| 路径 | 内容 | 状态 |
|---|---|---|
| `packaging/systemd/kylin-memory.service` | Memory Service systemd 单元（user 级、`--no-migrate` fail-fast、`RuntimeDirectory`、最小加固） | 设计冻结骨架；unit 注释明确：正式发行环境 systemd 测试未执行前不得写“成品通过”，需在麒麟 VM 完成 L2（安装/重启/回退） |
| `packaging/systemd/kylin-memory-echo.service` | Echo UDS 最小验证服务单元（`__USERNAME__` 占位符） | `UNVERIFIED`：直实验证通过，正式发行环境未验证 |
| `packaging/systemd/README.md` | 目录与职责边界 | 无生产实现 |
| `packaging/kaiming/README.md` | Kaiming 打包目录与职责边界 | 无生产实现 |
| `os-agent-integration/echo/` | `memory_echo_server.py`、`kaiming_memory_client.cpp`、`echo_client.cpp`、`deploy_echo.sh`、`install_systemd.sh`、`kysec_authorize.sh`、`test_systemd_lifecycle.sh`、`test_rollback.sh`、`CMakeLists.txt` | D2 起的最小 UDS/Hook/回退/生命周期验证资产 |
| `docs/deployment/README.md` | 部署指南框架 | 详细内容待填写 |
| `Kylin-runtime-knowledge/VERSION_MAP.md` | Runtime 版本对照索引（v2，2026-09-01 更新，VM 已安装版本实测复核） | 已维护 |

## 3. VM 快照与环境

| 项 | 值 | 来源 / 状态 |
|---|---|---|
| D11B 专用克隆 | `Kylin-V11-2603-D11B-ffd20b9-Test`（基于长期 B 轨基线快照 `20-btrack-test-deps-20260821`） | D11B 准备清单；D11D 需确认复用或新建 |
| 目标环境（VERSION_MAP） | 银河麒麟 V11 2603 x86_64（VirtualBox，VM `Kylin-desktop-neo`） | VERSION_MAP |
| OS / kernel | Kylin V11；`6.6.0-63-generic` | D11B 实测 |
| Python / pytest / pydantic | `3.12.3` / `9.1.1` / `2.13.5` | D11A / D11B 实测 |
| 根分区余量 | 约 24 GiB | D11B 实测 |
| SSH | NAT `127.0.0.1:2222`（D11B 密码认证；公钥未获接受，未擅改来宾 SSH 授权配置） | D11B 准备清单 |
| `kylin-memory.service` 部署 | 干净 VM 中不存在 | D11B 记录；属 D 轨部署职责 |

## 4. Vector / UDS / KYSEC 状态

| 项 | 值 | 来源 / 状态 |
|---|---|---|
| vector-engine | `1.2.0.1-0k0.11`（D11B）/ `1.2.0.1-0k1.0`（VERSION_MAP） | D11B 实测 / VERSION_MAP；两值不一致，工作项 2 统一环境冻结时须定案 |
| vector-engine-client | `libkysdk-vector-engine-client 1.2.0.0-0k0.7`（D11B）/ `1.2.0.0-0k1.1`（VERSION_MAP） | D11B / VERSION_MAP；同上 |
| Vector UDS | `/tmp/kylin-ai-vector-engine-1000.sock` 存在 | D11B 实测 |
| Runtime / Embedding UDS | `/tmp/.kylin-ai-runtime-unix/1000/core-textembedding.sock` | D11A evidence |
| Embedding SDK / 模型 | `libkylin-coreai-embedding 1.2.0.0-0k0.4`；runtime `1.3.0`；model `ensemble-embd_gte-base_uint8-text`（dim 768）；bridge loaded、lifecycle `READY` | D11A evidence（commit `b16b00f`，2026-08-31） |
| KYSEC | D2 已实测 Vector Engine 信任/撤销（`evidence/l2-kylin-vm/d2-vector-kysec-*`）；`kysec_authorize.sh` 为非真实 KYSEC 规则写入，状态 `UNVERIFIED` | 既有 evidence |

## 5. 盘点结论与影响

- 仓库侧基线清晰：D 轨部署/服务产物处于“骨架 / UNVERIFIED”状态；`kylin-memory.service` 未在任何 VM 完成 L2（安装/重启/回退）。
- 进入工作项 3（服务与安装）前，需先确认/创建 D11D 专用 VM（建议基于 `20-btrack-test-deps-20260821` 或 D11B 克隆派生，部署 `origin/main@47af2fa`）。
- 服务重启、OS 重启、正式 health/index state、KYSEC 生产规则均保持 `UNVERIFIED`；不把 D11A/D11B/D2 历史证据表述为 D11D 同一提交的证明。
- Vector Engine 版本在 D11B 与 VERSION_MAP 间不一致（`0k0.11` vs `0k1.0`），须在工作项 2 统一环境冻结时以 D11D 专用 VM 实测定案。