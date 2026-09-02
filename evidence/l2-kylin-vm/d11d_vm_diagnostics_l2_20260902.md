# D11D 麒麟 VM L2 证据：日志与诊断 / 权限与安全 / 证据汇总（第 4–6 项）

> 被测生产代码 `origin/main@47af2fa`；VM `Kylin-V11-2603-D11D-47af2fa-Test`（2026-09-02）。

## 第 4 项 日志与诊断（PASS）

- UDS 诊断（production socket `/run/user/1000/kylin-memory/memory.sock`）：
  - `health` → `{"status":"ok","db":"ok","methods":[echo,health,memory.retrieve,memory.store],"outbox":{"backlog":0,...}}`
  - `echo` → ok；`memory.retrieve` → `{"context":[],"degraded":false,"reason":"retrieval main chain pending"}`（真实空上下文，无假数据）
- JSON 日志（`--json-logs` 实例）每行含 `ts/level/logger/trace_id/request_id/method/event_id/message`；请求级日志携带调用方 `trace_id`/`request_id`（memory.retrieve 行 `trace_id=diag-988a8644e0` 与客户端一致）→ trace 关联成立。
- 脱敏：日志只记 `method/request_id`，不落正文/查询内容；PII 扫描（sk-demo/password/secret/api_key/token）命中 0。
- 注：diag 实例 `--no-outbox` 时 health 返回 `status=degraded`（outbox 指标降级），为测试实例预期行为，非缺陷。

## 第 5 项 权限与安全（本 VM 能力范围内 PASS，KYSEC 保持 UNVERIFIED）

- memory socket：`srw-------`（0600），owner `yanmouren778`；memory 目录 0755。
- DB：`~/.local/share/kylin-memory/kylin_memory.db` `-rw-------`（0600，含 -shm/-wal）。
- wrapper：`~/.local/bin/kylin-memory-server` 0755（本用户）。
- 用户隔离：服务以 `yanmouren778`（uid 1000）运行，unit `RestrictAddressFamilies=AF_UNIX` + `NoNewPrivileges=yes`。
- KYSEC：`/sys/kernel/security/kylin/` 在本 VM 不存在 → 生产 KYSEC 规则**保持 `UNVERIFIED`**；`kysec_authorize.sh` 仍为“非真实 KYSEC 规则写入”状态。vector/runtime socket 权限由 SDK 自身管理，不属 D11D 修改范围。

## 第 6 项 trace / 数据库 / 性能证据（已汇总）

- 数据库：Alembic head=`20260901_d10b_vector_ledger`；`outbox/source_events/memory_entries/vector_index_entries/turns` 均 0 行（干净基线，无测试数据残留）。
- 失败披露（E-4）：采集脚本中 `select status, count(*) from outbox group by status` 因 outbox 表无 `status` 列（`sqlite3.OperationalError: no such column: status`）失败；`outbox: 0 rows` 的总行数统计有效，按状态分组统计不可用，raw log 保留失败现场，未伪装 PASS。
- trace：JSON 日志中 `trace_id` 与请求关联成立（见第 4 项）。
- 性能：A 轨 D11A 填写（2026-09-02，基线 `47af2fa`）真实 SDK 20 次 embed 实测：`min=2.86ms p50=3.92ms p95=5.93ms p99=5.93ms avg=4.14ms max=6.48ms`，p95=5.93ms 远低于 180ms 预算（约 3.3%）；D11D 未重复 embedding 压测（属 A 轨范围），本项为汇总引用并标注来源（A+C 输入归档见 `evidence/l2-kylin-vm/d11d_ac_track_input_20260902.md`）。

## 限制 / UNVERIFIED

- KYSEC 生产规则（本 VM 不可见）；OS 整机重启自启（归第 7 项）；检索/删除端到端（B/C 轨输入 pending）；embedding 性能为 A 轨证据引用。
- 原始日志：`evidence/l2-kylin-vm/d11d_vm_diagnostics_l2_20260902.log`（SHA-256 `569afe12e5003f7b18eaccb2df46ab8f8ade5162f633981d4971de390307023a`，LF 归一化）。