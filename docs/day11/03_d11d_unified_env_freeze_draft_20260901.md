# D11D 统一环境冻结草案（2026-09-01）

> 对应 D11D 开工工作清单第 2 项。本文为**草案**：VM 依赖值在 D11D 专用 VM 实测前一律 `UNVERIFIED`；定案后回填 VERSION_MAP / 环境基线证据，并更新本文状态。

## 待冻结项与建议值

| # | 冻结项 | 建议值（草案） | 状态 |
|---|---|---|---|
| 1 | 代码提交 | `origin/main@47af2fa` | 已定（本批次基线） |
| 2 | D11D 专用 VM | 建议基于长期快照 `20-btrack-test-deps-20260821` 派生链接克隆（复用 D11B 克隆 `Kylin-V11-2603-D11B-ffd20b9-Test` 或新建同 Commit 环境） | 待 D 轨负责人/用户确认 |
| 3 | vector-engine 版本 | 存在不一致：D11B 实测 `1.2.0.1-0k0.11` vs VERSION_MAP `1.2.0.1-0k1.0` | 待 D11D 专用 VM 实测定案 |
| 4 | vector-engine-client | `1.2.0.0-0k0.7`（D11B） vs `1.2.0.0-0k1.1`（VERSION_MAP） | 待 D11D 专用 VM 实测定案 |
| 5 | Embedding SDK / 模型 | `libkylin-coreai-embedding 1.2.0.0-0k0.4`；runtime `1.3.0`；model `ensemble-embd_gte-base_uint8-text`（dim 768） | 引用 D11A evidence；D11D 环境复测 |
| 6 | Python / pytest / pydantic | `3.12.3` / `9.1.1` / `2.13.5` | 引用 D11A/D11B；D11D 环境复测 |
| 7 | UDS 路径 | Vector `/tmp/kylin-ai-vector-engine-1000.sock`；Runtime `/tmp/.kylin-ai-runtime-unix/1000/core-textembedding.sock`；memory `%t/kylin-memory/memory.sock`（systemd） | D11D 环境实测 |
| 8 | 数据目录 | memory-service DB 目录、`source_events`/outbox 数据库（Alembic 迁移至 head） | 待实现阶段冻结 |
| 9 | 配置 | `config/environment.example` 对应项；`--no-migrate` 由 Alembic 统一升级 | 待实现阶段冻结 |
| 10 | VERSION_MAP 回填 | D11D 实测后更新 `Kylin-runtime-knowledge/VERSION_MAP.md` | 待实测 |

## 开放决策（需确认）

- D-决策 1：D11D 专用 VM 采用哪种（复用 D11B 克隆 / 从 `20-btrack-test-deps-20260821` 新建 / 其他）。
- D-决策 2：vector-engine 版本以 D11D 专用 VM 实测为准并回写 VERSION_MAP。
- D-决策 3：最晚停止时间（进入实现前须指定）。

## 红线

- 不以 D11A / D11B / D2 历史证据替代 D11D 同一提交实测。
- 不修改冻结契约（FRZ-IPC / FRZ-DB / ADR）。
- 版本不一致未定案前，不把任一版本写为「已冻结」。