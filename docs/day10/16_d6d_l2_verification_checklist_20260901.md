# PR #98（D6-D）麒麟 VM L2 验证清单与证据归档

- **编制日期**：2026-09-01
- **编制人**：opencode（D 轨开发 Agent，PR #98 L2 委托）
- **分支**：`feat/d6d-event-persistence-impl`（PR #98，head `d721bad`，behind=0）
- **关联**：PR #83（ADR-013/014 v5 契约签署）→ **PR #98（D6-D 实现，本文档）**
- **对照**：`docs/day6/day6-d-01-event-persistence-contract-plan-v0.5.md` §八（L2 清单）、`docs/day10/15_pr3_l2_verification_checklist.md`（PR-3 先例格式）、ADR-013/014 v5

> **执行说明**：本 L2 在真实麒麟 VM 上执行（2026-09-01），tested_commit = `d721bad`（PR #98 当前 head，执行前已把该 commit 同步到 VM 并核对 `git rev-parse HEAD`）。所有证据来自麒麟 VM 真实运行，无 WSL/Mock 冒充。执行驱动见 `evidence/l2-kylin-vm/d6d_l2_vm_20260901.log`。

---

## 一、验证环境

| 项 | 值 |
|---|---|
| 宿主机 | 银河麒麟桌面 V11 x86_64（VirtualBox VM，SSH `127.0.0.1:2222`，用户 `kylin-agent`） |
| 仓库 | `/home/kylin-agent/kylinOS-agent-memory` |
| venv | `/home/kylin-agent/d4d-venv/bin/python`（sqlalchemy 2.0.52 / alembic 1.19.1 / pydantic 2.13.4） |
| 执行 HEAD | `d721badf3be1afeb7ce5daead51d5344ca546acb`（VM `git rev-parse HEAD` 核对一致） |
| 同步方式 | git bundle `d6d_d721bad.bundle`（VM 无法直连 GitHub，bundle fetch + checkout 后核对 HEAD） |

---

## 二、L2 验证清单与结果（L2-1 ~ L2-5）

### L2-1 迁移升级 + schema 对照（source_events）

| 子项 | 命令/方法 | 通过标准 | 结果 |
|---|---|---|---|
| upgrade head | `alembic -c migrations/alembic.ini upgrade head` | exit=0，版本链 `001_initial_schema → 20260826_add_trace_id → 20260831_preference_versions → 20260831_add_source_events`，无多 head | **PASS** |
| schema 对照 | `.schema` / PRAGMA 逐列对照 ADR-013 v5 + `db/schema.py` | `source_events` 35 列 + 5 索引（`uq_source_events_event` 全局 UNIQUE、`idx_source_events_user_created`、`idx_source_events_fingerprint`、`idx_source_events_dedup_group`、`idx_source_events_status`）+ 5 CHECK（consent_scope/source_business_status/sensitivity/admission_decision/processing_status）与 `db/schema.py` 单一真源一致 | **PASS** |
| 全局 UNIQUE | `CREATE UNIQUE INDEX uq_source_events_event` + `PRAGMA index_list` unique=1 | `UNIQUE(event_id)` 全局唯一 | **PASS** |
| 外键 | `PRAGMA foreign_key_check` | 空 | **PASS** |
| 往返 | downgrade → upgrade | exit=0（`DROP TABLE source_events` 回滚后重建，`alembic_version=20260831_add_source_events`） | **PASS** |

### L2-2 event.ingest 真实 CLI 端到端（uds_client）

activation：ADR-014 v5 activation seam —— 按 handlers.py 实际 seam（`register_event_ingest_handler`）在 test/validation profile 显式注册后启动 UDSGatewayServer（真实 handler + 真实 Repository + 真实 SQLite + alembic 迁移库），uds_client 走真实 UDS。production profile 用 `app.py` 默认启动验证不注册。

| 子项 | 通过标准 | 结果 |
|---|---|---|
| 正向写入 | `status ok`，`source_events` 落库：`processing_status='pending'`、`admission_decision=allow_extraction`、非敏感事件保留 `content_fingerprint` | **PASS**（L2A-E1，source_event_id=1，allow_extraction/ok，content_fingerprint=5a878986…） |
| 幂等回放 | 同 envelope 重发 → 相同响应（cache replay）；换 idempotency_key 重投同 event_id → `duplicate_reason='idempotent_replay'`，不重复落库（行数不变） | **PASS**（L2A-E2 首投 id=2；同 envelope 重发相同响应；idem-2b 重投 → `duplicate:true / idempotent_replay`；uA 仅 1 行 L2A-E2） |
| identity collision | 同 `event_id` + 不同 immutable identity → `EventIdentityConflict` → `INVALID_REQUEST` | **PASS**（L2A-E2 换 actor_id → `INVALID_REQUEST` / "event_id reused with different immutable identity"） |
| consent 前置 | `consent_scope=none` → `REJECT`（`consent_not_granted`），落库 `processing_status='pending'`、content_fingerprint NULL | **PASS**（L2A-E3：reject/consent_not_granted/pending，content_summary/content_fingerprint NULL） |
| 高敏四路不落 | sensitive 事件：`content_summary`/`raw_payload_ref`/`content_fingerprint` 落库 NULL；`idempotency_cache` 不含敏感派生 hash（request_fingerprint 为 `<SENSITIVE-OMITTED>` 占位） | **PASS**（L2A-E4：sensitivity=critical/is_sensitive_matched=1，三字段 NULL；补充核对 STORED_FP == 安全占位指纹、≠ 敏感正文 SHA-256、canonical JSON 含 `<SENSITIVE-OMITTED>` 且不含原文） |
| 跨用户 fail-close | 用户 B 复用用户 A 的 `event_id` → `INVALID_REQUEST`（`UNIQUE(event_id)` IntegrityError fail-close），B 零副作用 | **PASS**（uB→L2A-E1 → `INVALID_REQUEST` / "event_id already owned by another identity"；uB 落库 0 行） |
| 指纹去重 | 同 user+fingerprint+source_type 24h 窗口 → 仍插入新行 + `duplicate_of`/`dedup_group` 标记（保留真实事件） | **PASS**（L2A-E5 head id=5；L2A-E6 `duplicate:true / content_duplicate / duplicate_of=5`，dedup_group 同值，两行均 pending） |
| schema_version | 缺失/`!= "0.1"` → `INVALID_REQUEST`（显式预检） | **PASS**（缺失 → "missing required field: schema_version"；`0.2` → "unsupported_schema_version"） |
| production profile | 默认不注册 → `UNSUPPORTED_METHOD` | **PASS**（app.py 默认启动，event.ingest → `UNSUPPORTED_METHOD` / "unsupported method: event.ingest"） |

### L2-3 服务日志（event_id + PII 零泄漏）

| 子项 | 通过标准 | 结果 |
|---|---|---|
| JSON 单行格式 | `--json-logs` 启动：每行 JSON 含 `ts/level/logger/trace_id/request_id/method/event_id/message` | **PASS**（boot/请求日志行 8 字段齐全，JSON_FORMAT=PASS） |
| 请求关联（正对照） | 请求 → 日志含对应 `trace_id` + `request_id` | **PASS**（memory.retrieve 控制：日志含 `L2J-tr-4` + `req-l2j-4` + method；证明 request_context→JSON Formatter 链路可用） |
| **event.ingest 请求关联** | event.ingest 请求 → 日志含对应 `trace_id` + `event_id` | **FAIL（发现）**：`event.ingest` handler 成功路径**未发出任何应用日志行**（对照 memory.retrieve 有 INFO 日志点；event.ingest 在 `set_request_context(event_id=…)` 后无 INFO/DEBUG 日志），故 event.ingest 请求期间日志中观察不到 `trace_id`+`event_id` 关联。JSON 基础设施本身可用（正对照 PASS），缺口在 handler 日志点。 |
| PII 零泄漏 | 扫描全部日志（含事件正文/`source_reference`/敏感载荷） | **PASS**（敏感标记 `L2A_SENSITIVE_MARKER`/`sk-demo-…`/高敏载荷文本零命中，PII_ZERO_LEAK=PASS） |

### L2-4 systemd 部署（如 VM 环境支持）

| 子项 | 命令/方法 | 通过标准 | 结果 |
|---|---|---|---|
| unit 安装后迁移 | `packaging/systemd/kylin-memory.service` 安装 + `alembic upgrade head`（默认库） | exit=0，`alembic_version=20260831_add_source_events`、`source_events` 表存在 | **PASS** |
| 数据目录权限 | `stat` | 数据目录 0700 | **PASS**（`700 kylin-agent`） |
| DB 文件权限 | `stat` | DB 文件 0600 | **FAIL（发现）**：`kylin_memory.db` 实际为 `644`（目录 0700 已挡住越权访问，但未达 0600 要求；需部署加固 chmod 0600 或让 DB 创建带 0600） |
| enable/start | `systemctl --user enable --now kylin-memory` | RC=0，active (running) | **PASS** |
| socket 可达 | `/run/user/1000/kylin-memory/memory.sock` | srw------- 存在 | **PASS** |
| health | systemd 运行态 `uds_client --method health` | `status ok, db ok, backlog 0` | **PASS** |
| restart | `systemctl --user restart` | active | **PASS** |
| restart 数据存在 | 落库行 restart 后仍可查 | 插入 `L2A-SYSD-1` → restart → count=1 | **PASS**（补充核对：restart 后行仍存在、服务 active） |

### L2-5 证据归档

| 子项 | 通过标准 | 结果 |
|---|---|---|
| 执行日志归档 | `evidence/l2-kylin-vm/d6d_l2_vm_20260901.log`（含命令 + 输出 + tested_commit） | **PASS** |
| L2 验证清单文档 | 本文档 `docs/day10/16_d6d_l2_verification_checklist_20260901.md` | **PASS** |
| `evidence/index.yaml` 登记 | 新增条目 `D6D-L2-VM-20260901`（HOST_VERIFIED / E4 / tested_commit `d721bad` / checksum_sha256） | **PASS** |

---

## 三、整体判定

- L2-1 全部子项 **PASS**；L2-2 全部子项 **PASS**；L2-3 JSON 格式/PII 零泄漏 **PASS**，但 **event.ingest 请求关联 FAIL**（handler 成功路径无日志点）；L2-4 迁移/health/restart **PASS**，但 **DB 文件权限 644 未达 0600**。
- **整体判定：PARTIAL**（两个诚实发现的缺口，不影响 event.ingest 核心功能正确性；建议后续修复）。
- 证据均来自麒麟 VM 真实运行（tested_commit `d721bad`，VM `git rev-parse HEAD` 核对一致），无 WSL/Mock 冒充。

---

## 四、证据文件

| 文件 | 说明 | SHA-256 |
|---|---|---|
| `evidence/l2-kylin-vm/d6d_l2_vm_20260901.log` | L2-1~L2-4 完整探针日志（含命令 + 输出 + tested_commit；本次归档主证据） | `9110B72E55BCE732001BEF90F1DD3FB73FFE8E384D330C101B1873CFAC46B650`（git 仓库 LF 归一化 blob 校验） |
| `docs/day10/16_d6d_l2_verification_checklist_20260901.md` | 本文档（L2 验证清单） | — |

---

## 五、发现的问题与建议（如实）

1. **L2-3 event.ingest 请求关联 FAIL**：`event.ingest` handler（`memory-service/gateway/handlers.py` `register_event_ingest_handler`）成功路径在 `set_request_context(event_id=…)` 之后没有发出任何应用日志（对照 `memory_retrieve_handler` 有 INFO 日志点）。JSON Formatter / request_context 链路本身可用（正对照 memory.retrieve PASS）。**建议**：在 handler 校验后补一条 INFO 日志（如 `event.ingest method=%s event_id=%s trace_id=%s`），对齐 memory.retrieve 的观测性约定。
2. **L2-4 DB 文件权限 644 ≠ 0600**：默认库 `~/.local/share/kylin-memory/kylin_memory.db` 由 SQLite 以默认 umask 创建（644），未达 0600。数据目录 0700 已提供基本隔离，但未满足契约规划 §七.6 的 0600 要求。**建议**：部署侧对 DB 文件 chmod 0600，或由 engine/迁移创建后显式收紧。

## 六、修改文件清单

| 类别 | 文件 | 变更 |
|---|---|---|
| 新增 | `docs/day10/16_d6d_l2_verification_checklist_20260901.md` | 本文档（L2 验证清单） |
| 新增 | `evidence/l2-kylin-vm/d6d_l2_vm_20260901.log` | L2 执行证据日志 |
| 修改 | `evidence/index.yaml` | 登记 D6D-L2-VM-20260901 证据条目 |

**红线**：未修改任何生产代码、测试、迁移、配置；未触碰冻结契约（FRZ-IPC-001~007 / FRZ-DB-001 / ADR-013/014）。委托书 `PR98_L2_DELEGATION_20260901.md` 未加入 git 跟踪。