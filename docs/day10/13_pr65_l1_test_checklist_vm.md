# PR #65 Rework — 麒麟 VM L1 测试清单

- **编制日期**：2026-08-28
- **编制人**：opencode（D 轨开发 Agent）
- **适用**：PR #65 Rework 修复（B1/B2/M3~M6/T1-T9）合并前 L1 回归验证
- **分支**：`feat/d5d-ipc-pr2`（修复完成后同步 VM）
- **覆盖说明**：本机 Windows 无法执行的用例（UDS `AF_UNIX`、Alembic 迁移、SQLite `DELETE...LIMIT`）全部在麒麟 VM 补齐

---

## 一、前置准备（每次必做）

```bash
# 1) 将 rework 改动 push 到远端分支
git push origin feat/d5d-ipc-pr2

# 2) SSH 进入麒麟 VM 并同步仓库
ssh -p 2222 kylin-agent@127.0.0.1
cd /home/kylin-agent/kylinOS-agent-memory
git fetch origin && git reset --hard origin/feat/d5d-ipc-pr2

# 3) 环境自检
/home/kylin-agent/d4d-venv/bin/python -c \
  "import sqlalchemy,alembic,pytest;print(sqlalchemy.__version__,alembic.__version__,pytest.__version__)"
```

环境变量/常量约定（沿用 `scripts/run_l1_regression.py` / `scripts/l2_vm_run_tests.py`）：

| 项 | 值 |
|---|---|
| SSH | `-p 2222 kylin-agent@127.0.0.1` |
| 仓库路径 | `/home/kylin-agent/kylinOS-agent-memory` |
| venv 解释器 | `/home/kylin-agent/d4d-venv/bin/python` |
| venv alembic | `/home/kylin-agent/d4d-venv/bin/alembic` |
| PYTHONPATH | `memory-service` |

---

## 二、A. Rework 针对性回归（本机跑不了的关键项）

| 阶段 | 测试文件 | 覆盖范围 | 失败即排查项 |
|---|---|---|---|
| A1 | `memory-service/tests/test_turn_finalized_pr2.py`（`-v`） | turn.finalized UDS 全链路；**B1(T1×3)** 跨用户 A/B 竞争 + `find_turn_by_host` user 作用域 + DAO 层所有权；T3 并发 `IntegrityError` 幂等回查；T4 unwrap 首次响应；T5 指纹不一致 → INVALID_REQUEST；T8 validation profile 正向写；T9 严格 major.minor / 非空 ID / 带时区时间 / 等价时间指纹 / 错误不回显 | B1 隔离逻辑、validator 边界、`--validation-sources` 加载 |
| A2 | `memory-service/tests/test_observability_pr2.py`（`-v`） | **T6** Worker 跨线程恢复 trace_id/event_id（需 VM SQLite `DELETE...LIMIT`）；**T7** health `data.status=degraded`×5（全绿/抛错/哨兵/无 Worker/DB 不可达）；UDS health backlog / 降级；request_context 线程隔离 | worker 上下文设置/清理、health 哨兵判定 |
| A3 | `memory-service/tests/test_migrations_trace_id_pr2.py`（`-v`） | **B2(T2)** downgrade 软删不入 FTS；往返 upgrade→downgrade→upgrade；部分唯一索引；数据保留 | 迁移回填 `WHERE is_deleted=0` |

## 三、B. 受影响 DAO / Worker 回归（改动点直接回归）

| 阶段 | 测试文件 | 覆盖范围 | 失败即排查项 |
|---|---|---|---|
| B1 | `memory-service/tests/test_db_d4d.py`（`-v`） | `upsert_conversation` 所有权校验（B1）；`find_turn_by_host` 签名变更调用方；`get_turn`/`get_conversation` 用户隔离；幂等/Outbox 同事务；软删除 FTS 同步 | DAO 层跨用户防御 |
| B2 | `memory-service/tests/test_outbox_worker_d4d.py`（`-v`） | `_process_event` 重构后成功/重试/Dead Letter 路由仍正确（需 `DELETE...LIMIT`） | worker 消费与日志关联改造 |
| B3 | `memory-service/tests/test_gateway_server_d4d.py`（`-v`） | UDS/Gateway 端到端：health/echo/retrieve/store/TIMEOUT/停止拒绝 | envelope 与 `data.status` 语义分离 |

## 四、C. 契约 / CLI 回归

| 阶段 | 测试文件 | 覆盖范围 | 失败即排查项 |
|---|---|---|---|
| C1 | `memory-service/tests/test_gateway_protocol_d4d.py` | 冻结错误码/线协议/envelope 未回归 | 错误码枚举未变 |
| C2 | `memory-service/tests/test_server_lifecycle.py` | `app.py` CLI：`--register-turn-finalized` / 新增 `--validation-sources`；production 默认不注册 → UNSUPPORTED_METHOD | M6 受控入口 |
| C3 | `memory-service/tests/test_migrations_d4d.py` | 基线迁移/往返/FK/触发器（需 alembic） | B2 回填不影响基线 |

## 五、D. 全量 L1（R5 达标命令，最终计数）

```bash
cd /home/kylin-agent/kylinOS-agent-memory
export PYTHONPATH=memory-service
/home/kylin-agent/d4d-venv/bin/python -m pytest memory-service/tests -q
```

- 期望：**基线 983 passed / 49 skipped + 新增约 20**（B1/B2/M3~M6/T1-T9）≈ **1003 passed / 49 skipped**（宿主 skip 项视 VM 能力浮动）
- 记录：真实退出码、passed/skipped/failed/xpassed 数量，作为 R5 证据

---

## 六、证据回填（跑完后更新 `docs/day10/12_pr65_rework_evidence.md`）

| 证据 | 来源用例 | 说明 |
|---|---|---|
| R1 | 提交后 `git rev-parse HEAD` | 回填新 HEAD SHA（当前 5e9e1f43） |
| R3 | A1：`test_t1_cross_user_session_pollution_blocked` | 真实 UDS 下跨用户毒素用例通过结果 |
| R4 | A3：`test_downgrade_excludes_soft_deleted_from_fts` / `test_downgrade_upgrade_roundtrip_fts_matchers` | downgrade/FTS 探针 + `PRAGMA foreign_key_check` |
| R5 | D 阶段 | 全量命令、退出码、数量 |
| R6 | — | L2 项保持 `NOT_RUN`（迁移手工探针、systemd 属 L2，不并入本清单） |

---

## 七、判定标准

- A/B/C 各阶段 **0 failed / 0 error**，单项失败先按 Bug/Blocker/Risk/Debt 分类，**禁止删除或削弱测试换通过**（[02 §16.13/16.16]）；
- D 全量 exit code = 0；失败数 = 0；skipped 仅限宿主能力项（`kylin_embedding` 等）；
- 全部通过后方可更新 `docs/day10/10_pr65_review_rework_tracking.md` R3/R4 勾选状态，并请求 Reviewer 复核；
- 涉及宿主能力（Embedding/Vector）的用例由既有 L1 覆盖，本清单不新增宿主断言。

---

## 八、手动执行参照（SSH 批量脚本）

A/B/C 各阶段可合并为一次批量执行：

```bash
cd /home/kylin-agent/kylinOS-agent-memory
export PYTHONPATH=memory-service
PY=/home/kylin-agent/d4d-venv/bin/python

$PY -m pytest \
  memory-service/tests/test_turn_finalized_pr2.py \
  memory-service/tests/test_observability_pr2.py \
  memory-service/tests/test_migrations_trace_id_pr2.py \
  memory-service/tests/test_db_d4d.py \
  memory-service/tests/test_outbox_worker_d4d.py \
  memory-service/tests/test_gateway_server_d4d.py \
  memory-service/tests/test_gateway_protocol_d4d.py \
  memory-service/tests/test_server_lifecycle.py \
  memory-service/tests/test_migrations_d4d.py -q
```