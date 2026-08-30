# PR-3 麒麟 VM L2 验证清单与证据归档（D5-D）

- **编制日期**：2026-08-29
- **编制人**：opencode（D 轨开发 Agent）
- **分支**：`feat/d5d-ipc-pr3-l2-archive`（基于 main @ `4926345`，即 PR #65 合并后）
- **关联**：PR-1（PR #60 ADR-010/011 契约）→ PR-2（PR #65 代码主体）→ **PR-3（本文档）**
- **对照**：`docs/day10/05_d5d_task_list_20260826.md` §三（PR-3 定义）、`docs/day10/09_development_report_pr2.md`（L2-1~L2-5 操作清单）、`docs/day10/12_pr65_rework_evidence.md` §R6

> **说明**：原计划 PR-3 =「麒麟 VM L2 验证（人工操作清单交付，不声称已执行）」。实际 L2-1~L2-5 已在 PR-2 的 rework 阶段于麒麟 VM 真实执行（2026-08-28）并回填证据日志。本 PR 补正式验证清单 + `evidence/index.yaml` 登记，完成 D5-D 收尾归档。

---

## 一、验证环境

| 项 | 值 |
|---|---|
| 宿主机 | 银河麒麟桌面 V11 x86_64（VirtualBox VM，SSH `127.0.0.1:2222`，用户 `kylin-agent`） |
| 仓库 | `/home/kylin-agent/kylinOS-agent-memory` |
| venv | `/home/kylin-agent/d4d-venv/bin/python`（sqlalchemy 2.0.52 / alembic 1.19.1 / pydantic 2.13.4） |
| 执行 HEAD | `fac5411`（完整麒麟 VM L1/L2 执行 commit；PR #65 rework） |
| 后续代码修复 | `946eb3d`（Outbox event_id 传递 + resolver miss 日志；定向测试 30+23 passed，其中两项新增定向用例包含在 30 项中） |
| 合并 main | `4926345`（PR #65 merge commit，2026-08-28 14:23） |

---

## 二、L2 验证清单与结果（L2-1 ~ L2-5）

### L2-1 迁移升级 + schema 对照

| 子项 | 命令/方法 | 通过标准 | 结果 |
|---|---|---|---|
| upgrade head | `alembic -c migrations/alembic.ini upgrade head` | exit=0，`001_initial_schema → 20260826_add_trace_id` | **PASS** |
| schema 对照 | `.schema` 逐列对照 FRZ-DB-001 + ADR-011 | `turns.trace_id/host_turn_id`、`memory_entries.trace_id`、`idx_turns_host_turn_id`（唯一 + `WHERE host_turn_id IS NOT NULL`）、`memory_fts` + 4 触发器、`alembic_version` 全部落位 | **PASS** |
| 外键 | `PRAGMA foreign_key_check` | 空 | **PASS** |
| 往返 | downgrade → upgrade | exit=0（表重建回滚 + FTS 触发器重建回填） | **PASS** |
| FTS 软删过滤 | 数据级探针（MATCH `麒麟`） | insert=1 / 软删后=0（`WHERE is_deleted=0` 回填生效） | **PASS** |

### L2-2 turn.finalized 真实 CLI 端到端

| 子项 | 命令/方法 | 通过标准 | 结果 |
|---|---|---|---|
| 正向写 | `app.py --register-turn-finalized --validation-sources sources.json` + `uds_client` 发事件 | `status ok`，落库 `db_turn_id=1/host_turn_id=H-1`，`original_user_text` = resolver 正文 | **PASS** |
| Outbox 入队 | 同事务 | payload 含 `trace_id=L2A-1`、`host_turn_id=H-1`、UTC 时间、`refinalize:false` | **PASS** |
| 幂等回放 | 同 envelope 重发 | 相同响应（同 `db_turn_id/host_turn_id/conversation_id`），不重复落库 | **PASS** |
| 跨用户毒素 | 用户 B 复用用户 A 的 `(s1, H-1)` | `INVALID_REQUEST`，message 固定英文无标识泄漏；B 零副作用（turns/outbox 不变） | **PASS** |
| 空映射 | 未提供 `--validation-sources` | 空 resolver + warning；resolver miss → `INTERNAL_ERROR`；turns/idempotency/outbox 零副作用 | **PASS** |
| production profile | 默认注册（不传 `--register-turn-finalized`） | `turn.finalized → UNSUPPORTED_METHOD` | **PASS** |

### L2-3 health degraded 真实探针

| 子项 | 命令/方法 | 通过标准 | 结果 |
|---|---|---|---|
| 正常态 | `uds_client --method health` | `data.status=ok, db=ok, backlog=0` | **PASS** |
| worker 未注入 | `--no-outbox` 启动 | `data.status=degraded`（真实 UDS） | **PASS** |
| DB 不可达/metrics 哨兵 | VM L1 同 handler 单测 | `test_health_status_degraded_*` 3 passed；实机口径注明：health `SELECT 1` 对存活池化连接无页 I/O，无法外部伪造该状态 | **PASS** |

### L2-4 JSON 结构化日志（event_id + PII）

| 子项 | 命令/方法 | 通过标准 | 结果 |
|---|---|---|---|
| 单行 JSON | `--json-logs` 启动 | 每行 JSON 含 `ts/level/logger/trace_id/request_id/method/event_id/message` | **PASS** |
| 请求关联 | `memory.retrieve` 请求 | 日志含 `trace_id=L2R-1` + `request_id=req-r-1` | **PASS** |
| Worker 跨线程 | 注入 Outbox 事件 | Worker 日志含 `trace_id=L2W-1` + `event_id=evt-W1`（M4 跨线程关联） | **PASS** |
| PII 零泄漏 | 扫描全部日志 | resolver 注入正文 / `source_reference` 不出现在任何日志 | **PASS** |

### L2-5 systemd --user 部署

| 子项 | 命令/方法 | 通过标准 | 结果 |
|---|---|---|---|
| 默认库迁移 | `systemctl --user` 安装后自动 alembic | `ALEMBIC_EXIT=0` | **PASS** |
| enable/start | `systemctl --user enable --now kylin-memory` | RC=0 | **PASS** |
| socket 可达 | `/run/user/1000/kylin-memory/memory.sock` | `SOCK_READY` | **PASS** |
| health | systemd 运行态 `uds_client --method health` | `status ok, db ok, backlog 0` | **PASS** |
| restart | `systemctl --user restart` | active | **PASS** |
| stop + socket 清理 | `systemctl --user stop` | inactive + socket 清理（`SOCK_GONE`） | **PASS** |
| 回退恢复 | `enable --now` | active 恢复 | **PASS** |

---

## 三、整体判定

- L2-1 ~ L2-5 全部子项 **RUN/PASS**（2026-08-28 麒麟 VM 实测），整体判定 **PASS**。
- 完整麒麟 VM L1/L2 执行于 `fac5411`；`946eb3d` 修改 Outbox event_id 传递与 resolver miss 日志，在该精确提交上通过 `test_turn_finalized_pr2.py` 30 项 + observability/migrations 23 项；其后治理提交仅修改文档，未重跑完整 L2。
- 证据均来自麒麟 VM 真实运行，无 WSL/Mock 冒充。

---

## 四、证据文件

| 文件 | 说明 | SHA-256 |
|---|---|---|
| `evidence/l2-kylin-vm/pr65_l2_vm_20260828.log` | L2-1~L2-5 完整探针日志（本次归档主证据） | `FF78527139A2B52CE784A5CB3D88B1D053B7E10F4F50EE82EBBE1BEA144B3416` |
| `evidence/l1/pr65_l1_vm_checklist_20260828.log` | 麒麟 VM L1 全量（1003 passed, 49 skipped） | `9EE65EF82D17B336EF96B8E44B56157B6A7E6710005330299D641795DA51F1CA` |
| `docs/day10/12_pr65_rework_evidence.md` §R6 | L2 验证结果文字归档 | — |
| `docs/day10/14_pr65_outstanding_tasks.md` | 待办勾销（L2-1~L2-5 DONE） | — |

---

## 五、技术债与限制

- TD-D4D-001/002/003：保持 Open（consumer 未接线 / deadline 非抢占 / Outbox 单事务持锁）——本轮纯文档收尾不触发。
- TD-028（真实 IntegrityError 竞态回查分支缺测试）：保持 Open（PR #65 已登记，本文档不代做）。
- 限制：L2 完整执行于 `fac5411`；`946eb3d` 后的运行时代码差异已由定向测试覆盖，未重跑完整 VM L2（与 PR #65 最终复审口径一致）。

---

## 六、修改文件清单

| 类别 | 文件 | 变更 |
|---|---|---|
| 新增 | `docs/day10/15_pr3_l2_verification_checklist.md` | 本文档（正式验证清单） |
| 修改 | `evidence/index.yaml` | 登记 D5D-L2-VM-20260828 证据条目 |

**红线**：未修改任何生产代码、测试、迁移、配置；未触碰冻结契约（FRZ-IPC-001~007 / FRZ-DB-001 / ADR-010/011）。
