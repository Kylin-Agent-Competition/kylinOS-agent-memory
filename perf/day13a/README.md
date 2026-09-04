# D13A 性能基线与高压负载测试

本目录只保存可复现的测试工具说明；正式结果默认放在 `run_01`、`run_02`、`run_03` 运行目录中，避免不同硬件、SDK 或 Git commit 的数据混在一起。

## 范围与指标

| 路径 | 实际测量边界 | 默认矩阵 |
| --- | --- | --- |
| Embedding | `EmbeddingService` → 真实 `EmbeddingProvider` → SDK | 1000 请求，并发 1/4/8 |
| Bridge | Python → pybind11 → C++ `EmbeddingBridge` → SDK | 1000 请求，并发 1/4/8 |
| IPC | 客户端 UDS round-trip → Gateway → Registry → handler → response | 2000 请求，并发 1/4/8/16 |
| Outbox | SQLite `outbox` 表 → 真实 `OutboxWorker` → 可控消费回调 | 5000 events，记录积压与 drain |

每组正式请求前 warm-up 50 次。P50/P95/P99 基于成功请求的单请求延迟；吞吐是该组请求数除以墙钟时间；错误数单独报告。CPU/RSS 每 100ms 采样当前进程。每条请求和每条资源/积压样本都写入 JSONL，便于复算。

项目内部 Embedding 查询预算是 **≤180ms**；比赛官方知识检索响应指标是 **≤500ms**。二者属于不同层级，不能互相替代。D13A 只记录基线，不设置回归 Gate，也不承担 D13B/D13C 的热点定位或优化。

## 麒麟 VM 正式运行

先在固定的银河麒麟 VM 中安装仓库依赖、构建 `kylin_embedding`，并启动真实 Memory Service。再从同一 Git commit 执行：

```bash
cd /path/to/kylinOS-agent-memory
export DAY13A_IPC_SOCKET=/run/user/$(id -u)/kylin-memory.sock
PYTHONPATH=memory-service:scripts ./scripts/run_day13a_benchmarks.sh
```

可选参数：`DAY13A_PYTHON`、`DAY13A_SDK_SO`、`DAY13A_OUTPUT_DIR`、`DAY13A_RUN_ID`、`DAY13A_RUN_COUNT`、`DAY13A_TEXTS`、`DAY13A_IPC_REQUESTS`、`DAY13A_IPC_PID`、`DAY13A_OUTBOX_EVENTS`。默认连续跑 3 轮；本地只验证一轮可设置 `DAY13A_RUN_COUNT=1`。每轮 IPC 都会分别运行 `echo` 和 `memory.retrieve`。`DAY13A_IPC_PID` 可指向 Gateway 服务 PID，使 CPU/RSS 采样服务进程；未设置时采样 benchmark 客户端。脚本不会自动启动/停止服务，不会安装软件，也不会删除已有 DB。

运行目录结构如下（`DAY13A_RUN_COUNT=1` 时也可以使用 UTC 时间戳目录）：

```text
perf/day13a/run_01/
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

三轮完成后，`perf/day13a/summary.json` 还会索引全部运行目录、Git commit 和每轮汇总；单轮调试时统一汇总位于该轮目录内。

`environment.json` 绑定 Git commit、branch、dirty 状态、OS/kernel、CPU/RAM、Python 和 SDK 线索，并保留 `git rev-parse HEAD`、`git status --porcelain`、`uname -a`、`lscpu`、`free -m`、`python --version` 原始输出。正式基线必须在干净 commit 上运行；Windows/Ubuntu/银河麒麟结果不能合并为同一条基线。

## 本地冒烟与限制

无麒麟 SDK 的机器只能执行 Embedding 的 `--fake` 冒烟；该结果会标注 `formal_run=false`，严禁写入正式基线。IPC benchmark 必须连接真实 UDS Gateway；一键流程会分别保留 `echo` 轻量请求和 `memory.retrieve` 业务请求。Outbox benchmark 使用新建的专用 SQLite 路径，若初始 backlog 非零会直接拒绝运行。

本仓库当前工作环境为 Windows，且未提供 `kylin_embedding`、固定银河麒麟 VM 或已启动的 UDS Gateway。因此本地可验证脚本语法/协议和 fake/SQLite 冒烟，但 A1 的固定宿主信息、Bridge 真 SDK、IPC 正式矩阵和同机三轮结果必须在麒麟 VM 上补跑；未补跑前不能把 D13A 标记为“正式基线完成”。
