# D11D 麒麟 VM L2 证据：服务与安装（systemd --user 生命周期）

> 对应 D11D 开工工作清单第 2、3 项。本证据在 D11D 专用链接克隆上执行，被测生产代码为 `origin/main@47af2fa`（产品代码零差异，本分支仅新增 docs/day11 与 `packaging/systemd/install_kylin_memory.sh`）。

## 环境（实测，2026-09-02）

| 项 | 值 |
|---|---|
| VM | `Kylin-V11-2603-D11D-47af2fa-Test`（链接克隆，基础快照 `20-btrack-test-deps-20260821`，VirtualBox GUI 前台） |
| OS / kernel | 银河麒麟桌面操作系统 V11 / `6.6.0-63-generic` |
| 被测提交 | `47af2fa42edf45ab4dc227453c47ed784bf46e16` |
| Python / 依赖 | 3.12.3 / sqlalchemy 2.0.52 / alembic 1.19.1 / pydantic 2.13.5 / pytest 9.1.1 |
| Vector Engine | `kylin-ai-vector-engine 1.2.0.1-0k0.11` + `libkysdk-vector-engine-client 1.2.0.0-0k0.7`（D11D 专用 VM 实测定案；此前 D11B 与 VERSION_MAP 分歧以本实测为准） |
| UDS | Vector `/tmp/kylin-ai-vector-engine-1000.sock`（存在）；memory `/run/user/1000/kylin-memory/memory.sock`（`srw-------` 0600） |
| DB | `~/.local/share/kylin-memory/kylin_memory.db`，Alembic head=`20260901_d10b_vector_ledger` |

## L2 执行与结果

| 步骤 | 命令 | 结果 |
|---|---|---|
| 迁移 | `alembic -c migrations/alembic.ini upgrade head`（KYLIN_MEMORY_DB=默认路径） | exit 0；`current = 20260901_d10b_vector_ledger (head)`；表齐（memory_entries/memory_versions/outbox/source_events/vector_index_* 等 20 表） |
| 安装 | `install_kylin_memory.sh install --python /usr/bin/python3 --repo …` | exit 0；`enabled` + `active (running)`；socket OK；journal「Memory Service 就绪」已出现 |
| 重启 | 脚本内置 `systemctl --user restart` 复验 | `active (running)`；socket OK；journal OK |
| 回退 | `install_kylin_memory.sh rollback` | exit 0；服务 `inactive`；wrapper 与 unit 均被删除 |
| 重装 | `install_kylin_memory.sh install …` | exit 0；`active (running)`（可重复、可回退） |

## 关键运行事实

- `kylin-memory.service`：`active (running)`，Main PID 41568（`/usr/bin/python3 …/memory-service/app.py --socket /run/user/1000/kylin-memory/memory.sock --no-migrate`），Memory 34.2M。
- journal 关键行：`生产模式：alembic_version 校验通过，schema 由 Alembic 管理`；`Outbox Worker 启动（poll=1s, max_retries=3）`；`Memory Service 就绪`；`IPC Gateway 启动`。
- `config.toml` 不存在时按全部默认值启动（预期行为，不视为缺陷）。

> 被测脚本 commit：`install_kylin_memory.sh` 由 `df5df7f` 引入；`df5df7f..HEAD` 间仅状态注释变更（+4/-2，`UNVERIFIED → HOST_VERIFIED`），无行为变化。
>
## 限制 / UNVERIFIED

- 正式发行环境（生产 Kylin）systemd 行为未验证（仅本链接克隆）。
- OS 整机重启后服务自启复测归入工作项 7（启动/重启/部署问题）。
- Kaiming 包安装路径未实现（`packaging/kaiming` 仍为目录边界）。
- 本证据仅覆盖服务生命周期；检索/删除/性能等由 A/B 轨既有证据覆盖，不以本证据替代。

## 证据文件

- 原始日志：`evidence/l2-kylin-vm/d11d_vm_service_l2_20260902.log`（SHA-256 `cd0bb83f1f99cdc55d05055ac37f003ebf49083d20d85164579d7fe1408fb298`，LF 归一化）