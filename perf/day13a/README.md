# D13A 性能基线与高压负载测试

本目录保存说明、已审阅后导入的证据和历史失效声明；正式 runner **绝不**写入 Git worktree。它默认将三轮产物写到 `/tmp/kylin-day13a/<commit>/<run-id>/`，避免 benchmark 自身污染 Git clean 校验。

## 范围与指标

| 路径 | 实际测量边界 | 默认矩阵 |
| --- | --- | --- |
| Embedding | `EmbeddingService` → 真实 `EmbeddingProvider` → SDK | 1000 请求，并发 1/4/8 |
| Bridge | Python → pybind11 → C++ `EmbeddingBridge` → SDK | 1000 请求，并发 1/4/8 |
| IPC | 客户端 UDS round-trip → Gateway → Registry → handler → response | 2000 请求，并发 1/4/8/16 |
| Outbox queue | SQLite `outbox` 表 → 真实 `OutboxWorker` → 可控消费回调 | 5000 events，记录队列积压与 drain |

每组正式请求前 warm-up 50 次。P50/P95/P99 基于成功请求的单请求延迟。每档同时输出 `attempt_rate_req_s`、`success_throughput_req_s`、`success_rate`、`error_rate` 和 `errors`；`throughput_req_s` 明确等同于成功请求吞吐，不能把失败连接尝试当作业务吞吐。CPU/RSS 每 100ms 采样当前进程。每条请求和每条资源/积压样本都写入 JSONL，便于复算。

`memory.retrieve` 当前返回 empty context，因此它的 `measurement_scope` 是 `gateway_empty_context_ipc_baseline`：仅代表 UDS → Gateway → Registry → handler → response 的 IPC 基线，不能用作知识检索主链延迟或比赛“知识检索响应 ≤500ms”的达标证据。

当前 `benchmark_outbox.py` 测的是 `outbox_queue_backlog_drain`，不是索引积压：它写入 `turn.finalized` 并使用可控 consumer。结果会写入 `index_backlog_measurement.status=not_measured`，并使 collection 的 `formal_baseline_complete=false`。只有补齐 `memory.upserted → OutboxWorker → index consumer → Vector/Embedding backend` 的真实链路后，才可将索引积压列为已测量。

项目内部 Embedding 查询预算是 **≤180ms**；比赛官方知识检索响应指标是 **≤500ms**。二者属于不同层级，不能互相替代。D13A 只记录基线，不设置回归 Gate，也不承担 D13B/D13C 的热点定位或优化。

## 麒麟 VM 正式运行

先在固定的银河麒麟 VM 中，从真实、干净的 Git worktree checkout 固定 commit，安装仓库依赖、构建 `kylin_embedding`，并启动真实 Memory Service。runner 启动时冻结 `DAY13A_EXPECTED_COMMIT` 和 `DAY13A_EXPECTED_BRANCH`（未设置时取当前 HEAD/branch）；每轮都验证实际值与冻结身份一致、`git status --porcelain` 为 clean，且 Git 命令返回成功。任一条件不满足都会 fail-closed。

```bash
cd /path/to/kylinOS-agent-memory
export DAY13A_IPC_SOCKET=/run/user/$(id -u)/kylin-memory.sock
export DAY13A_SDK_SO=/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0
export DAY13A_MODEL_VERSION=ensemble-embd_gte-base_uint8-text
export DAY13A_EXPECTED_COMMIT=$(git rev-parse HEAD)
export DAY13A_EXPECTED_BRANCH=perf/D13A-baseline-load
export DAY13A_RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
export DAY13A_OUTPUT_DIR=/tmp/kylin-day13a/${DAY13A_EXPECTED_COMMIT}/${DAY13A_RUN_ID}
export DAY13A_BASELINE_MODE=partial
PYTHONPATH=memory-service:scripts ./scripts/run_day13a_benchmarks.sh
```

`DAY13A_SDK_SO`、`DAY13A_MODEL_VERSION`（或 `DAY13A_MODEL_SHA256`）与 `DAY13A_IPC_PID` 是正式运行的必填身份资料；环境快照会记录实际 `.so` 路径、文件存在性、SHA-256、SONAME、SDK/runtime 版本线索和模型身份。`DAY13A_OUTPUT_DIR` 是所有轮次共用的**外部**根目录，必须不存在或为空；若位于 Git worktree 内或已含旧产物，runner 会拒绝运行。可选参数：`DAY13A_PYTHON`、`DAY13A_RUN_ID`、`DAY13A_RUN_COUNT`、`DAY13A_BASELINE_MODE`、`DAY13A_EXPECTED_COMMIT`、`DAY13A_EXPECTED_BRANCH`、`DAY13A_TEXTS`、`DAY13A_IPC_REQUESTS`、`DAY13A_IPC_PAYLOAD`、`DAY13A_OUTBOX_EVENTS`。默认连续跑 3 轮；本地只验证一轮可设置 `DAY13A_RUN_COUNT=1`。每轮 IPC 都会分别运行 `echo` 和 `memory.retrieve`；业务请求默认 payload 为 `schema_version=1.0,user_id=day13a-benchmark`，Gateway validation profile 的可信身份应匹配该用户，或通过 `DAY13A_IPC_PAYLOAD` 覆盖。`DAY13A_IPC_PID` 必须是当前可见的实际 Gateway/Memory Service PID；IPC summary 会记录 resource_sample_target=gateway_service 和 resource_sample_pid，避免将 benchmark 客户端的 CPU/RSS 误作服务端资源。脚本不会自动启动/停止服务，不会安装软件，也不会删除已有 DB。

目前仓库尚未包含真实 index backlog benchmark，因此应显式设置 `DAY13A_BASELINE_MODE=partial` 执行 VM 采集。`full` 模式必须显式提供 `DAY13A_EXPECTED_COMMIT` 与 `DAY13A_EXPECTED_BRANCH`，且会在性能负载前检查真实 index benchmark 是否存在；不具备该能力时立即退出，不会先浪费三轮 VM 测试时间。

运行目录结构如下（所有目录均在 `DAY13A_OUTPUT_DIR` 或默认的 `/tmp` 路径下）：

```text
/tmp/kylin-day13a/<commit>/<run-id>/run_01/
├── environment.json
├── summary.json
├── embedding.summary.json
├── bridge.summary.json
├── ipc_echo/
│   ├── ipc.summary.json
│   └── raw/ipc.jsonl
├── ipc_memory_retrieve/
│   ├── ipc.summary.json
│   └── raw/ipc.jsonl
├── outbox.summary.json
└── raw/
    ├── embedding.jsonl
    ├── bridge.jsonl
    ├── outbox.jsonl
    └── resources.jsonl
```

三轮完成后，外部运行根目录的 `summary.json` 会索引全部运行目录、expected/actual Git identity 和每轮汇总。`full`（默认）只有在三轮绑定唯一且符合冻结身份的 clean Git commit、SDK/模型身份完整、Embedding/Bridge/两类 IPC/Outbox queue 核心矩阵完整、且每轮存在真实索引积压测量时，才会写出 `formal_baseline_complete=true`；否则会输出 `formal_baseline_blockers` 并以非零状态退出。`partial` 模式允许尚未测量真实索引积压，但只会写出 `collection_status=partial` 和 `formal_baseline_complete=false`，不能用于 D13A 完成或合并判断。

正式运行结束后，先在 repo 外审阅 `summary.json`、原始 JSONL、Git/SDK identity 和完整性状态；只有经人工确认的完整证据才可通过独立 import 步骤加入仓库。不得直接覆盖本目录中的历史 run 目录。

`environment.json` 绑定 Git commit、branch、dirty 状态、冻结的 expected identity、OS/kernel、CPU/RAM、Python、SDK/runtime 版本、实际 SDK `.so` 路径/文件身份/SHA-256/SONAME 和模型版本或 hash，并保留 `git rev-parse HEAD`、`git status --porcelain`、`uname -a`、`LC_ALL=C lscpu`、`free -m`、`python --version` 原始输出。正式基线必须在干净 commit 上运行；Git 命令失败时 `git_dirty` 为 `null`（unknown），绝不解释为 clean；Windows/Ubuntu/银河麒麟结果不能合并为同一条基线。

## 本地冒烟与限制

无麒麟 SDK 的机器只能执行 Embedding 的 `--fake` 冒烟；该结果会标注 `formal_run=false`，严禁写入正式基线。IPC benchmark 必须连接真实 UDS Gateway；一键流程会分别保留 `echo` 轻量请求和 `memory.retrieve` 业务请求。Outbox benchmark 使用新建的专用 SQLite 路径，若初始 backlog 非零会直接拒绝运行。

本仓库当前工作环境为 Windows，且未提供 `kylin_embedding`、固定银河麒麟 VM 或已启动的 UDS Gateway。因此本地可验证脚本语法/协议和 fake/SQLite 冒烟，但 A1 的固定宿主信息、Bridge 真 SDK、IPC 正式矩阵和同机三轮结果必须在麒麟 VM 上补跑；未补跑前不能把 D13A 标记为“正式基线完成”。
