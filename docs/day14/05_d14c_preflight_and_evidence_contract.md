# D14C Formal Preflight 与证据转换契约

## 目的与边界

本契约只建立开跑前拒绝机制和数据转换入口：

- `scripts/run_d14c_formal_preflight.py <handoff.json>` 只读校验，不启动服务、不创建 evidence root、不产生 PASS。
- `scripts/build_d14c_d13c_bundle.py <capture.json> -o <bundle.json>` 只把真实 VM capture 的既有 D13C 字段交给 `scripts/run_d13c_session_eval.py`；不新增 evaluator 或评测阈值。

实现位于 `memory-service/evaluation/d14c_l3_harness.py`。L1 负向用例覆盖 dirty worktree、无法解析的 tested commit、缺失或越界的证据引用、实际构建物 SHA 不匹配、未冻结 D13D/D14D、未批准或跨运行身份的 host identity、无绑定 ACTIVE 路由、未冻结或跨运行身份的 MemoryContext、非法/复用 evidence root，以及非 VM capture/provenance 漂移。

## Formal handoff

`d14c-formal-handoff/v1` 必须包含：

```text
formal_tested_commit（冻结 runtime/package 的 40 位 SHA）
preflight_runner_commit（执行预检的干净工作树 HEAD）
d13d.status=FROZEN + d13d.frozen=true + d13d.tested_commit=formal_tested_commit + existing evidence_reference
d14d.status=L3_READY + d14d.l3_ready=true + d14d.tested_commit=formal_tested_commit + existing evidence_reference
release package: existing repository-local regular file + path/version/SHA-256/manifest SHA-256/source_commit（且 source_commit=formal_tested_commit）
AI Assistant、MemoryClient、Memory Service: existing repository-local regular file + path/version/SHA-256
VM: environment_id/name/uuid/snapshot/snapshot_uuid
trusted host identity: APPROVED + same tested_commit/environment_id/service_package_sha256 + existing approval reference + process/DB reference + SHA-256
turn.finalized/event.ingest/forget.preview/forget.execute: ACTIVE + same tested_commit/environment_id/service_package_sha256 + existing activation reference
MemoryContext: FROZEN + same tested_commit/environment_id/service_package_sha256 + existing freeze reference + existing schema_path/schema SHA-256 + no-match/failure semantics
evidence_root = evidence/l3-kylin-vm/d14c_<new-run-id>
```

`d14d.package_tar_sha256` 必须等于 `release_package.sha256`。这允许 D14C
preflight 工具在 clean development HEAD 运行，同时保持 D13D/D14A/D14D 已冻结的
runtime tested commit 不变；两种 SHA 均受校验，不能互相替代。

`formal_tested_commit` 必须由 Git `cat-file -e <commit>^{commit}` 解析为真实提交，
但不要求等于 `preflight_runner_commit`。所有 evidence/reference/artifact/schema path
必须是存在的 repository-relative 路径，解析后仍留在 repository root 内；绝对路径、
`..` 路径和 symlink escape 均拒绝。release package、三个 component artifact 与
MemoryContext schema 都以实际文件 bytes 重新计算 SHA-256，并要求等于 handoff 声明。

`RAW_READY_PENDING_SEALS`、仅有 D13D Execution Seal、D14D G0-G6 完成但
`l3_ready=false`，以及包来源提交与 formal tested commit 不一致，均必须 fail-closed。

目标 evidence root 必须尚不存在。通过 preflight 只意味着允许创建新 root 并开始**一次**正式运行；它不替代任何 Runtime 验收。失败时保留输入 handoff 作为诊断材料，修复后使用新 run ID。

## D13C evaluator 复用

真实 VM collector 写入 `d14c-runtime-capture/v1`，且只能在 `capture_status=VM_RAW_CAPTURED` 时转换。capture 的 `provenance.tested_commit/environment_id/evidence_root` 必须逐一等于 `d13c_config.implementation_commit/environment/evidence_reference`。转换结果仅为：

```json
{"config": "既有 D13C config", "sessions": "既有 D13C sessions"}
```

随后使用既有 `scripts/run_d13c_session_eval.py` 计算指标。任何 raw 缺失、状态非 VM capture 或 provenance 不一致均拒绝转换，不能用手写成功 bundle 代替。

## Runtime precheck observation

`scripts/collect_d14c_runtime_precheck.py <request.json> --output <observation.json>`
是 P1-B/P1-C 的只读采集入口。它输出固定
`d14c-runtime-precheck/v1` / `PRECHECK_OBSERVATION`，并固定
`formal_dispatch=NOT_STARTED`；它不是 Runtime capture、formal evidence 或
`HOST_VERIFIED` 结论。

请求需标明 run/tested commit/environment、VM name/UUID/snapshot/snapshot UUID，
以及 AI Assistant、MemoryClient、Memory Service 的路径、版本或 build ID、PID；
socket、DB、运行记录 ID 和预检命令结果。输出记录：

```text
VM kernel / Kylin release ID
三组件 binary/package SHA-256、PID、owner、cwd
Memory Service systemd FragmentPath / MainPID / ActiveEnterTimestamp
UDS 与 DB path 的 owner/mode，DB checkpoint reference 槽位
仅允许 session/trace/turn/event/execution_record ID
采集 started_at/finished_at/latency_ms 与 command exit code
```

collector 从不读取或写入 user/assistant plaintext。进程 command line 与
systemd `ExecStart` 只保留 SHA-256 和长度；组件缺失、unit inactive 或命令失败
仍只记录为 observation，不能提升任何 Gate。

`runtime_ids` 是严格 allowlist：只允许 `session_id`、`trace_id`、`turn_id`、
`event_id`、`execution_record_id`。任何额外字段（包括 user/assistant text、token 或
secret）均会在写入 observation 前被拒绝；拒绝信息不得回显字段值。

## Evidence package 闭环

正式运行结束后用 `scripts/verify_d14c_evidence_package.py <d14c_root>` 做离线完整性检查。根目录必须含 `manifest.json`、`SHA256SUMS`、run identity、commands 与 exit-codes；`VERIFIED` runtime package 还必须有 runtime capture 与 D13C evaluator report。`FAILED` / `BLOCKED` package 同样允许做完整性校验，但必须保留 `failure_summary`，输出只会是 `PACKAGE_INTEGRITY_VERIFIED`，绝不升级为 Runtime PASS。`SHA256SUMS` 必须恰好覆盖根目录中除自身外的每个 regular file。
