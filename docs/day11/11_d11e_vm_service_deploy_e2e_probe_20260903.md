# D11E 麒麟 VM 服务部署与 E2E IPC 冒烟证据（2026-09-03）

## 概览

- VM：`Kylin-V11-2603-D11E-0820036-Test`（链接克隆自 `20-btrack-test-deps-20260821`，GUI 前台）；来宾 yanmouren778，Kylin V11 2603 / kernel 6.6.0-63-generic / Python 3.12.3。
- 被测提交：`f4d9a00`（= `main@b70827c` + D11E 文档；E 业务运行时代码与 `main@b70827c` 一致）。
- 复用 D11D 统一 VM 部署产物：`packaging/systemd/install_kylin_memory.sh`、`kylin-memory.service`（PR #115）。

## 部署步骤与结果（来宾实测）

| 步骤 | 命令 | 结果 |
|---|---|---|
| DB 迁移 | `python3 -m alembic -c migrations/alembic.ini upgrade head`（PYTHONPATH=~/d11e-pylibs） | exit 0；head=`20260902_add_memory_relation_conflict`（含 ADR-017 关系/冲突/生命周期表） |
| 服务安装 | `bash packaging/systemd/install_kylin_memory.sh install --python /usr/bin/python3 --repo $HOME/kylinOS-agent-memory` | exit 0；`enabled` + `active (running)`；socket OK；journal「Memory Service 就绪」；内置 restart 复验通过 |
| 依赖 | `~/d11e-pylibs`（pydantic 2.13.5 / sqlalchemy 2.0.52 / pytest 9.1.1）；PYTHONPATH 注入 systemd user 管理器 | import 校验通过 |

journal 关键行：`生产模式：alembic_version 校验通过，schema 由 Alembic 管理`、`Outbox Worker 启动（poll=1s, max_retries=3）`、`IPC Gateway 启动`、`Memory Service 就绪`。
socket：`/run/user/1000/kylin-memory/memory.sock`（`srw-------` 0600）。

## IPC 冒烟结果

### production profile（默认注册）
- 方法集：`echo / health / memory.retrieve / memory.store`。
- `echo` → ok；`health` → ok（db=ok，outbox backlog=0）。
- `memory.retrieve` → ok，`context: []`，reason=`retrieval main chain pending`（检索主链未接入，符合 D11 现状）。

### test/validation profile（systemd drop-in `--register-turn-finalized --register-preference-handlers --register-event-ingest --register-forget-handlers`）
- 方法集新增：`turn.finalized / event.ingest / preference.list|create|update|rollback|history / forget.preview|forget.execute`。
- `preference.list`（user 空库）→ ok，`items: []`。
- `forget.preview`（缺 `forget_plan_id`）→ `INVALID_REQUEST: missing required field: forget_plan_id`（schema 校验 fail-closed 生效）。

> 注：validation profile 属代码预留测试 seam，production 禁止使用（日志 `BLOCKED_BY_HOST_MAPPING`）；本证据仅用于 E2E 冒烟，不作为生产配置结论。

## 边界与结论口径

- 已达成：`kylin-memory` 服务在 D11E VM 上按 D11D 产物部署成功、DB 迁移到 head、生产 health 正常、validation profile 可 E2E 调用 E 业务方法且空库/非法输入行为正确。
- **不构成** D11E 完成证据：含真实种子数据与 A/B/C 输入的**同 VM 端到端业务验收（RC-01..07）仍未执行**，保持 `UNVERIFIED`；validation resolver 空映射（未提供 `--validation-sources`）仅负路径可验证；C 轨 QML 主演示与 B 轨真实检索/删除输出仍需同 Commit 输入。
- 复现路径：部署命令见上表；冒烟脚本为 UDS 长度前缀 JSON 信封客户端（`health`/`echo`/`memory.retrieve`/`preference.list`/`forget.preview`）。
- 本批未修改任何生产代码、冻结契约或其他轨道交付物；服务以 validation profile 运行仅用于测试。
