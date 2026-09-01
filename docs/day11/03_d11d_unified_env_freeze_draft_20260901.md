# D11D 统一环境冻结（2026-09-02 实测定案）

> 对应 D11D 开工工作清单第 2 项。VM 依赖值已由 D11D 专用麒麟 VM 实测（2026-09-02）；未定案项保持 `UNVERIFIED` 并注明归属。

## 已实测定案项

| # | 冻结项 | 定案值 | 证据 |
|---|---|---|---|
| 1 | 代码提交 | `origin/main@47af2fa` | D11D 分支基线 |
| 2 | D11D 专用 VM | `Kylin-V11-2603-D11D-47af2fa-Test`（链接克隆，基础快照 `20-btrack-test-deps-20260821`，GUI 前台） | VM 创建与运行记录 |
| 3 | vector-engine | `kylin-ai-vector-engine 1.2.0.1-0k0.11` | D11D VM 实测；与 D11B 一致；VERSION_MAP 的 `0k1.0` 为 `Kylin-desktop-neo` 另一环境 |
| 4 | vector-engine-client | `libkysdk-vector-engine-client 1.2.0.0-0k0.7` | 同上 |
| 5 | Python / pytest / pydantic | `3.12.3` / `9.1.1` / `2.13.5`（另 sqlalchemy 2.0.52、alembic 1.19.1） | D11D VM 实测 |
| 6 | UDS 路径 | Vector `/tmp/kylin-ai-vector-engine-1000.sock`；memory `/run/user/1000/kylin-memory/memory.sock`（0600） | D11D VM 实测 |
| 7 | 数据目录 / 迁移 | `~/.local/share/kylin-memory/kylin_memory.db`；Alembic head=`20260901_d10b_vector_ledger` | D11D VM 实测 + `alembic current` |
| 8 | 服务入口 | `kylin-memory.service`（user 级，`--no-migrate`）+ wrapper `~/.local/bin/kylin-memory-server` | 第 3 项 L2 通过 |

## 未定案 / 归属

| 项 | 状态 | 归属 |
|---|---|---|
| 配置 `config.toml` | 不存在时用全部默认值启动（已实测，预期行为）；正式配置冻结 | 实现阶段 |
| Kaiming 包安装 | `packaging/kaiming` 仍为目录边界，未实现 | 后续批次/跨轨 |
| VERSION_MAP 回填 | 不回填：VERSION_MAP 记录 `Kylin-desktop-neo` 环境；D11D 环境版本以本草案与 evidence 为准 | 保持现状 |
| 最晚停止时间 | 仍待 D 轨负责人/用户指定 | 用户 |

## 开放决策（已定）

- D-决策 1：D11D 专用 VM = 新建链接克隆（已定案并落地）。
- D-决策 2：vector-engine/client 版本以 D11D 专用 VM 实测为准（0k0.11 / 0k0.7）。
- D-决策 3：最晚停止时间——待用户确认。