# D15D 资产盘点与差距分析（main@3138e94）

> 日期：2026-09-06
> 盘点口径：以 `git show 3138e942770ec1f9863e86c03da4df9dd1ad8703:<path>` 的实际树内容为准；
> 不使用本地旧 D14D worktree 工作区文件代替 main 树（`E:\Kylin-memory-dev\main` 当前 checkout 不是 main@3138e94）。
> 结论：除下列 `PENDING_D/E_SIGN` 项外，D15D“待锁定清单”在 main@3138e94 上已具备可锁定对象；
> 正式 Release Commit / 版本清单 / 提交包 / 签署 Gate 尚缺最终输入。

## 1. 资产映射表

| 锁定项 | main@3138e94 路径 | 现状 | D15D 处置 | 差距/备注 |
| --- | --- | --- | --- | --- |
| 发布目录正式入口 | `packaging/README.md` | 已声明 `release/` 为 D14A 正式入口；`systemd/` 为历史；`kaiming/` deferred | 以本 README 为目录语义基线 | `packaging/systemd/README.md` 与 `packaging/kaiming/README.md` 仍写“尚无生产实现”，需文档同步（GAP-03） |
| 构建器 | `packaging/release/build_release_package.sh` | 存在，source_commit/dirty-tree/迁移 smoke/manifest/SHA256SUMS Gate | 锁定脚本 SHA | 无内容缺口 |
| 自动 smoke | `packaging/release/package_smoke.sh` | 存在，clean 与 upgrade-rollback 两场景 | 作为 upgrade 语义验收入口 | 无独立 `upgrade.sh`（GAP-01，推荐以事务化 install+rollback 为官方口径） |
| systemd 安装 | `packaging/release/systemd_install.sh` | 存在，事务化安装 + SDK fail-closed | 锁定脚本 SHA；包内映射 `systemd/install.sh` | 无内容缺口 |
| systemd 卸载/回退 | `packaging/release/systemd_uninstall.sh` | 存在，事务恢复 + clean-state removal | 锁定脚本 SHA；包内映射 `systemd/uninstall.sh` | 无内容缺口 |
| systemd 验证 | `packaging/release/systemd_verify.sh` | 存在，真实 embedding PID/SDK SHA/dim | 锁定脚本 SHA；包内映射 `systemd/verify.sh` | 无内容缺口 |
| systemd unit | `packaging/systemd/kylin-memory.service` | 存在，build 复制入包；install 将 ExecStart 渲染为 prefix launcher | 锁定 source blob + 渲染后 unit 的验收口径 | 无内容缺口 |
| 历史 systemd | `packaging/systemd/install_kylin_memory.sh`、`kylin-memory-echo.service`、`README.md` | 历史/只读；echo 非生产 | 不锁定为正式部署入口 | README 过时（GAP-03） |
| Kaiming | `packaging/kaiming/README.md` | 占位，无生产实现 | 终口径 = `OUT_OF_SCOPE / DEFERRED`（`PENDING_D/E_SIGN`） | GAP-02 |
| 发布契约 | `docs/day14/00_d14a_release_package_contract.md` | FROZEN v4 | D15D 引用不修改 | §6bis runtime/model = `HANDOFF_REQUIRED`（GAP-04） |
| D14D 状态与证据 | `docs/day14/13_d14d_l3_current_status_20260906.md`、`evidence/phase0/d14d-env-prepared-20260906[-r2][-r3]/` | 已入库；r1/r2 历史、r3 ACTIVE | 消费 ENV_PREPARED；等待 FORMAL L3 | GAP-05 |
| 运行时版本真源 | `Kylin-runtime-knowledge/VERSION_MAP.md` | 存在 | D15D 版本清单引用不修改 | runtime/model 锁待正式 G0 |
| 测试 | `packaging/release/test_d14a_*.py`（4 个）、`docs/day14/test_d14a_release_provenance.py` | 存在，接入 CI `d14a-packaging-provenance` | 锁定测试集与 CI job | 无内容缺口 |
| Release Commit | 无 | 缺 | 待 D13D #160 merge + D14D 正式 run 后定 | GAP-05 |
| 版本清单 | 无 | 缺 | 新增 `D15D_VERSION_MANIFEST.json`（`docs/day15/`） | 见 runbook |
| 提交包 | 无 | 缺 | 固定内容清单，与 main 文件集一一对应 | 见 runbook |
| 签署记录 | 无 | 缺 | Reviewer E APPROVE + 台账“已审查→已合并” | GAP-06 |

## 2. 缺口清单与推荐处置（均标 `PENDING_D/E_SIGN`）

| ID | 缺口 | 事实 | 推荐处置 | 责任人 |
| --- | --- | --- | --- | --- |
| GAP-01 | 独立 upgrade 脚本口径 | 仓库无 `upgrade.sh`；`package_smoke.sh` 以 `upgrade-rollback` 场景验证事务化升级回退 | 不新增独立脚本；官方升级 = 事务化 `install.sh install` + `uninstall.sh rollback`；runbook 固化；D15D 卡书面记录 | D15D 起草 / D 主审确认 / E 签署 |
| GAP-02 | Kaiming 终口径 | `packaging/kaiming/` 仅占位；顶层 README 标 deferred pending D 主审确认 | 最终提交不包含 Kaiming 包：`OUT_OF_SCOPE / DEFERRED`；不实现、不改占位 | D 主审 / E 会签 |
| GAP-03 | 旧 systemd 与 release 双源文档口径 | 顶层 README 已说 systemd 为历史；`packaging/systemd/README.md` 仍写“尚无生产实现” | 随 D15D PR 仅改 `packaging/systemd/README.md` 为“历史/只读，正式入口 = `packaging/release/`”；不改脚本 | D15D（入 PR 阶段）/ E |
| GAP-04 | runtime/model 身份 | D14A §6bis `HANDOFF_REQUIRED`；r1/r2/r3 有 host baseline 但未正式冻结 | 保持 `HANDOFF_REQUIRED`；正式 D14D G0 采集回填后才能进入版本清单 | D14D 执行 / D Reviewer |
| GAP-05 | Release Commit / D14D 正式 L3 未闭合 | #160 OPEN（CI FAILURE）；D14D FORMAL L3 NOT_RUN；`tested_commit` 未定 | D15D 先起草；#160 merge → 最终 tested_commit → D14D G0–G9 → 回填 release_commit | D13D owner / D14D / E |
| GAP-06 | 版本清单/提交包/签署记录缺失 | 当前无 D15D 版本清单、提交包清单与签署 Gate 记录 | 按任务卡 §2.1 与 runbook 建立 | D15D / E |

## 3. 禁止在本盘点阶段“补平”的项

- 不创建最终 `release_commit` 或包 hash；
- 不修改 `docs/day14/00`、VERSION_MAP、`packaging/release/*`、`packaging/systemd/*` 脚本内容；
- 不实现 Kaiming；
- 不把 `packaging/systemd/README.md` 修改提前到 D15D PR 之外；
- 不因 main 前进而追改本表资产路径（main 前进时先重建盘点快照再更新）。

