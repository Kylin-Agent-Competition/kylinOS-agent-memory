# PR#57 L2 麒麟宿主验证清单

- **来源**：PR#57 第二轮复审（Reviewer `lovezy0730-create`，结论 REWORK / DO NOT MERGE）修复后的遗留 L2 验证项
- **整理日期**：2026-08-24
- **修复 Commit**：`740bb62`（`fix(ipc): PR#57 复审 REWORK 修复……`，分支 `feat/d4-phase0-ipc-alignment`）
- **依据文档**：
  - `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-001~007 + ALIGN-001~005）
  - `deliverables/D4_IPC_PROTOCOL_FREEZE_20260807.md`（§6.1/6.2 字段契约、§2 错误码）
  - `docs/adr/005-db-error-code-envelope.md`（错误码映射 + envelope）
  - 基线 `01_sdk_capability_boundary.md` §12.1（P0/P1/P2 能力认证）、`02_architecture_sop.md` §16.7（L1/L2/L3 分层）
- **分层口径**：本清单全部为 **L2（麒麟 VirtualBox V11 虚拟机宿主）** 验证项，**WSL 结果不构成宿主证据**，不得以 L0/L1 通过替代。

---

## 一、汇总登记表

| 编号 | 验证项 | 关联能力/契约 | 认证级别 | 当前状态 | 责任人 | 完成日期 | 结果 |
|------|--------|--------------|:---:|:---:|:---:|:---:|:---:|
| L2-A1 | ALIGN-005：active socket 拒绝 unlink | ALIGN-005 / FRZ-IPC-006 | P0 | UNTESTED | | | |
| L2-A2 | ALIGN-005：stale socket 清理后正常 bind | ALIGN-005 | P0 | UNTESTED | | | |
| L2-A3 | ALIGN-005：socket 父目录 per-user 隔离（0700） | ALIGN-005 | P0 | UNTESTED | | | |
| L2-B1 | 真实 SDK 下新 envelope 断言（`data` 恒 object / 错误 `data:{}` / `degraded_reason` 并入） | FRZ-IPC-006 / ADR-005 | P0 | UNTESTED | | | |
| L2-B2 | 错误码语义分类端到端（unknown method / 缺字段 / 帧错误） | FRZ-IPC-002 | P0 | UNTESTED | | | |
| L2-B3 | 真实客户端字段兼容性（新必填校验不误拒） | FRZ-IPC-006 | P0 | UNTESTED | | | |
| L2-C1 | Embedding 异常输入降级 `degraded_reason` 保留 | EMB-T03 | P0 | UNTESTED | | | |
| L2-C2 | Embedding 空输入 / 非法输入行为 | EMB-T03 | P0 | UNTESTED | | | |
| L2-D1 | 证据收集器脱敏（servicekey 等无明文）+ HEAD 绑定 | 证据治理 [02 §16.12-16.15] | — | UNTESTED | | | |

> **P0 认证纪律**：`IPC-001`（UDS）、`EMB-T03`（Embedding 异常输入）为 P0 能力 [01 §12.1]，**在 L2-B2/B3、L2-C 通过前，不得冻结对应接口或将端到端闭环标记完成**。

---

## 二、详细验证项

### L2-A1：ALIGN-005 active socket 拒绝 unlink

- **背景**：本轮 BLOCKER 修复——`embedding/server.py::start()` 改为 `_remove_stale_socket()`，active socket（能 connect 成功）时抛错拒绝 unlink，防止独立 Embedding Server 抢占正式 `memory.sock` ownership。
- **前置条件**：麒麟 VM，`$XDG_RUNTIME_DIR=/run/user/1000`，正式服务监听 `memory.sock`。
- **操作步骤**：
  1. 确认旧进程占用：`ss -lnpx | grep memory.sock`（现状证据显示 `python pid=3107` 已监听）。
  2. 以默认路径启动 embedding：`cd memory-service && PYTHONPATH=. python3 -m embedding.server`（默认 `$XDG_RUNTIME_DIR/kylin-memory/embedding.sock`）。
  3. 断言启动失败，观察 stderr。
- **通过标准**：抛 `RuntimeError: active socket already listening: ...memory.sock...; refusing to unlink`；**不**删除 `memory.sock`；旧进程 `pid=3107` 仍存活、原 socket 仍可连接。
- **证据要求**：命令、exit code、stderr、`ls -la` 前后对比 raw log 回收，绑定当前 HEAD。

### L2-A2：ALIGN-005 stale socket 清理后正常 bind

- **操作步骤**：
  1. 手工制造 stale socket：`python3 -c "import socket; s=socket.socket(socket.AF_UNIX); s.bind('$XDG_RUNTIME_DIR/kylin-memory/embedding.sock'); s.close()"`。
  2. 确认残留：`ls -la $XDG_RUNTIME_DIR/kylin-memory/embedding.sock`。
  3. 启动 embedding server（默认路径）。
  4. 用真实/模拟客户端发 `memory.embed` 请求。
- **通过标准**：残留被清理、bind+listen 成功、请求返回 `status:"ok"` + `data.dimension==768`（或 degraded 空向量，取决于 SDK 是否可用）。
- **证据要求**：同 L2-A1。

### L2-A3：ALIGN-005 socket 父目录 per-user 隔离

- **操作步骤**：`ls -ld $XDG_RUNTIME_DIR/kylin-memory`。
- **通过标准**：目录 `0700`、owner=kylin-agent，无 group/other 写权限。
- **证据要求**：`ls -ld` 输出 raw log。

### L2-B1：真实 SDK 下新 envelope 断言

- **前置条件**：`kylin_embedding` 已编译（`KYLIN_L2=1`）。
- **命令**：
  ```bash
  cd memory-service
  KYLIN_L2=1 python3 -m pytest tests/test_embedding_service_real.py -v
  ```
- **通过标准**：全绿；逐项核对：
  - `memory.ping` → `data == {"pong": true}`（`data` 恒 object）
  - `memory.embed` → `data.dimension == 768`、`data.vector` 长度 768
  - `memory.embed_batch` → `data.vectors` 长度 == 文本数
  - `memory.health` → `data.service/provider/bridge_loaded` 字段
  - 错误响应含 `data == {}` + `error_code`（冻结枚举）
  - 降级路径 `data.degraded == true` 且 `data.degraded_reason.code/message` 保留
- **证据要求**：pytest 输出 + `KYLIN_L2=1` exit code，绑定 HEAD。

### L2-B2：错误码语义分类端到端

- **操作步骤**：用真实 C++ 客户端（`echo_client` / `kaiming_memory_client`）或 Python 客户端分别发送：
  1. unknown method（如 `memory.unknown`）
  2. 缺 `request_id` / `trace_id` / `deadline_ms` 的请求
  3. 声明长度 > 65536 或非法 UTF-8 的帧
- **通过标准**（三类语义正确分离，非全部 `PROTOCOL_ERROR`）：

  | 输入 | 期望 `error_code` |
  |---|---|
  | unknown method | `UNSUPPORTED_METHOD` |
  | 缺必填字段 / 错误类型 | `INVALID_REQUEST` |
  | protocol_version 不匹配 / 帧错误 | `PROTOCOL_ERROR` |

- **证据要求**：三类用例 raw 响应 JSON 回收，绑定 HEAD。

### L2-B3：真实客户端字段兼容性

- **背景**：`parse_envelope` 新增必填校验，需确认真实客户端不被误拒。
- **前置核对**（已静态确认）：`echo_client.cpp::build_request`（`request_id/trace_id/deadline_ms/payload` 齐全）、`kaiming_memory_client.cpp`（同上）已含全部必填字段。
- **操作步骤**：真实客户端对 embedding server 发正常业务请求。
- **通过标准**：正常请求不被 `INVALID_REQUEST` 拒绝，返回 `status:"ok"`。
- **证据要求**：真实客户端联调 raw log + 响应 JSON。

### L2-C1：Embedding 异常输入降级 `degraded_reason` 保留

- **操作步骤**：
  1. SDK 缺失场景：移走 `.so` 后启动 server，发 `memory.embed`。
  2. Runtime 重启恢复场景：重启 `kylin-ai-runtime` 后重发。
- **通过标准**：返回 `status:"ok"` + `data.vector == []` + `data.dimension == 0` + `data.degraded == true` + `data.degraded_reason.code`（如 `ERR_SDK_NOT_LOADED`）**完整保留在 envelope data 中**，不被静默丢失。
- **证据要求**：响应 JSON raw 回收。

### L2-C2：Embedding 空输入 / 非法输入

- **操作步骤**：发 `text=""`（空串）、`text=<非字符串>`。
- **通过标准**：
  - 空串 → 768 维（Day2 已证，复测确认）
  - 非 str → 错误（映射后 `INVALID_REQUEST`，不崩溃、不穿透异常）
- **证据要求**：响应 JSON raw 回收。

### L2-D1：证据收集器脱敏 + HEAD 绑定

- **操作步骤**：在真实 VM 配置 `KYLIN_VM_PASSWORD` 后重跑 `evidence/phase0/collect_phase0_evidence.py`。
- **通过标准**：
  - 输出 `/etc/.kyinfo` 的 `[servicekey] key=...` 已脱敏为 `REDACTED`（无明文数字）
  - markdown 头部含 `project/task/branch/commit_sha/result/limitations` 正式字段
  - `commit_sha` 正确绑定当前 HEAD
- **证据要求**：重跑后的 `phase0_vm_evidence.md/.jsonl` + 脱敏 diff 对比。

---

## 三、完成后的产出要求

全部 L2 项通过后：

- [ ] 逐项回填上表「结果」列（PASS / PASS_WITH_DEBT / FAIL）并附证据路径
- [ ] 更新 `evidence/index.yaml`（新增/回写 IPC-001、EMB-T03 状态为 HOST_VERIFIED，注明 tested_commit）
- [ ] 回写能力矩阵：`IPC-001`（UDS）→ HOST_VERIFIED / E4；`EMB-T03`（异常输入）→ 按实际结果
- [ ] ADR-008 由「提议 / 待审」→ 提交 Reviewer E 签署，签署后更新 ADR 状态与 ADR README
- [ ] 提交完整测试与证据后，请求 Reviewer 发起 PR#57 下一轮复审

---

## 四、诚实声明与限制

- 本清单所有项当前 **UNTESTED**，WSL 已通过的 `599 passed, 49 skipped` 为 L0/L1，**不构成麒麟宿主 L2 证据**。
- 现有 `evidence/phase0/phase0_vm_evidence.md` 为 **INVESTIGATION_ONLY（E1）**，仅记录旧进程占用 `memory.sock` 的现状，仅用于印证 ALIGN-005 风险真实性，**不得作为 L2 PASS 依据**。
- 能力表述纪律：未完成 L2 前，文档/代码注释不得写「已支持」「成品通过」；冻结接口需 P0 认证通过后方可标记完成 [01 §1.3, §12.1]。

