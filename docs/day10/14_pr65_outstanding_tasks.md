# PR #65 Rework 待办清单（未完成项单独导出）

- **编制日期**：2026-08-28
- **编制人**：opencode（D 轨开发 Agent）
- **分支**：`feat/d5d-ipc-pr2`（当前 HEAD `946eb3d`，远端已同步；运行口径 `fac5411` 与 `946eb3d` 生产代码一致）
- **关联文档**：`docs/day10/10_pr65_review_rework_tracking.md`、`docs/day10/12_pr65_rework_evidence.md`、`docs/day10/13_pr65_l1_test_checklist_vm.md`
- **目的**：将已闭合项与剩余待办分离，剩余项全部以本节为准，逐一勾销（本清单已全部执行完毕）。

---

## 已完成（不在此清单，仅作对照）

- B1/B2（2 HIGH 红线）/ M3~M6（4 MEDIUM）/ 测试缺口 T1-T9 代码修复：合入 `a94ae55`
- L0 静态：ruff F/E9 All checks passed；py_compile 通过
- L1 麒麟 VM：A 52 / B 40 / C 33 / D 1003 passed, 49 skipped，exit 0
  - 证据日志：`evidence/l1/pr65_l1_vm_checklist_20260828.log`
- 证据文档 R1-R6：`docs/day10/12_pr65_rework_evidence.md`
- **L2-1~L2-5 麒麟 VM 验证全部 RUN/PASS（2026-08-28）**：证据日志 `evidence/l2-kylin-vm/pr65_l2_vm_20260828.log`

---

## 剩余待办

### L2-1｜迁移手工探针（DONE 2026-08-28）

- [x] 在麒麟 VM 执行 `alembic -c migrations/alembic.ini upgrade head`（exit=0）
- [x] `.schema` 导出逐列对照 FRZ-DB-001 + ADR-011（`turns.trace_id/host_turn_id`、`memory_entries.trace_id`、`idx_turns_host_turn_id` 部分唯一索引均落位）+ downgrade→upgrade 往返 + FTS 软删过滤数据级探针（MATCH `麒麟` insert=1，软删后=0）
- [x] `PRAGMA foreign_key_check` 交互验证（空，亲和 A3 自动化迁移测试全绿）

### L2-2｜turn.finalized 真实 CLI 端到端（DONE）

- [x] 以 `app.py --register-turn-finalized --validation-sources <sources.json>` 启动服务
- [x] 外部 `uds_client` 发触发事件 → 正向落库（turns + original_user_text）+ Outbox 入队（payload 含 trace_id/host_turn_id）
- [x] 未提供 `--validation-sources` 时验证空映射（warning）+ 负路径 `INTERNAL_ERROR`（turns/idempotency/outbox 零副作用）
- [x] **production profile** 下 `turn.finalized → UNSUPPORTED_METHOD`
- [x] 跨用户毒素用例（T1）在真实 UDS 复跑（`INVALID_REQUEST` + message 无泄漏 + B 零副作用）

### L2-3｜health degraded 真实探针（DONE）

- [x] `uds_client --method health` 正常态 → `data.status=ok, db=ok, backlog=0`
- [x] worker 未注入（`--no-outbox`）→ `data.status=degraded`（真实 UDS）
- [x] DB 不可达 / metrics 哨兵 `backlog=-1` 分支：VM L1 同 handler 单测覆盖（3 passed）；实机口径注明：health `SELECT 1` 对存活池化连接无页 I/O，无法外部伪造该状态（见证据文档 §R6）

### L2-4｜JSON 日志 event_id（DONE）

- [x] `--json-logs` 运行日志逐行 JSON 含 `trace_id` / `request_id` / `event_id`（`memory.retrieve` 请求 + Worker 处理事件均取到实据）
- [x] 确认无 PII（resolver 注入正文 / source_reference 不出现在任何日志）

### L2-5｜systemd 部署（DONE）

- [x] `systemctl --user` enable/start kylin-memory（默认库先 alembic 迁移，`--no-migrate` fail-fast 校验通过）
- [x] restart 正常（active + socket + health ok）
- [x] stop / 回退正常（inactive + socket 清理 + `enable --now` 恢复 active），日志与 socket 可访问

### R1｜新 HEAD SHA 回填一致性（DONE）

- [x] `docs/day10/12_pr65_rework_evidence.md` §R1 已回填：完整 L1/L2 执行 commit `fac5411`、后续证据/文档 commit `dc4080a`、当前远端 HEAD `946eb3d`；VM L1/L2 运行于 `fac5411`（与 `946eb3d` 生产代码一致，差异仅文档 + 测试 import 清理）

### 复审流程（流程待办）

- [ ] 远端 HEAD 更新后（已同步 `946eb3d`），凭 R1-R6 证据向 Reviewer（lovezy0730-create）提交第二/三轮复审回复
  - [x] L2-1~L2-5 已执行并附证据（见 §R6 / `evidence/l2-kylin-vm/pr65_l2_vm_20260828.log`），不再有 `NOT_RUN` 遗留
  - [x] 合并前治理回写完成（纯文档）：TD-027 登记（真实 IntegrityError 竞态回查分支缺少测试）+ T3 DEFERRED（关联 TD-027），HEAD 口径同步至 `946eb3d`
  - [ ] 复审回复 comment 提交（进行中）

---

## 判定合规约束

- B1/B2 属红线（已实证 High），**禁止转合并后技术债**，本 PR 合并前必须保持已修复状态
- L2 项未执行时不可声称「已通过」；文档与回复中一律标 `NOT_RUN`
- 涉及宿主能力（Embedding / Vector / UDS / Hook / QML）的验证项，证据必须来自麒麟 VM，WSL/Agent 沙箱结果不构成宿主证据
- 修复/验收不得删除或削弱测试换取通过（[02 §16.13/16.16]）

---

## 执行入口

- L2-1 ~ L2-5：通过 `kylin-vm-test` skill / SSH（`-p 2222 kylin-agent@127.0.0.1`，仓库 `/home/kylin-agent/kylinOS-agent-memory`，venv `/home/kylin-agent/d4d-venv/bin/python`）执行，证据回填至 `evidence/` 与 `12_pr65_rework_evidence.md` §R6
- 复审回复：`github` P/R #65 comment 提交，附 `docs/day10/12_pr65_rework_evidence.md`