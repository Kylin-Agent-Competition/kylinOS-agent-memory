# D13C L2 麒麟 VM 实测 — D 轨交付归档

> **来源**：D 轨（Ducknesses）PR #149 `test(D13C): add D-track L2 evidence collector`，
> 2026-09-05 合并至 main（squash commit `2cba0115942fb39ea8130279543a1b2f07ed456e`）。
> **对应需求**：`docs/day13/08_d13c_l2_requirements_d_track.md`（C 轨 2026-09-03 提出，20 项 D-L2-01~20）。
> **归档路径**：`docs/day13/10_d13c_l2_d_track_delivery_20260905.md`

## 交付物

| 文件 | 内容 |
|---|---|
| `scripts/d13c_l2_collect.py` | 只读 UDS L2 证据采集器（大端 u32 帧前缀，SQLite `mode=ro`，凭据字段递归 redact） |
| `memory-service/tests/test_d13c_l2_collect.py` | 4 个 L1 单测（redaction / 百分位计算 / 输出目录 fail-closed / 错误响应不计入延迟） |
| `docs/day13/08_d13c_d_l2_rework_execution.md` | VM 执行程序 + 验收映射矩阵 |

采集器边界：仅使用生产方法 `echo` / `memory.retrieve`；不启用任何验证 seam；
`turn.finalized` / `forget.*` 生产默认不注册 → 机械上报 `BLOCKED`。

## L2 关键结论（VM baseline @ `053754d`，非 PR head）

### VERIFIED（4 项）

| # | 需求项 | 结论 | 关键证据 |
|---|---|---|---|
| D-L2-01 | UDS socket 可监听 | **VERIFIED** | socket 权限 0600，路径符合 FRZ-IPC-001 |
| D-L2-02 | 客户端可连接 Gateway | **VERIFIED** | UDS echo 连接成功 |
| D-L2-03 | 长度前缀协议正确编解码 | **VERIFIED** | echo envelope 校验通过 |
| D-L2-06 | SQLite 查询延迟可接受 | **VERIFIED** | 30 样本，p50=1.703ms / p95=3.656ms（门槛 p50<300ms / p95<1000ms） |

### FAILED → 对发布 BLOCKED（2 项，需 C/D/E 联合 ADR）

| # | 需求项 | 结论 | 根因 |
|---|---|---|---|
| D-L2-04 | memory.retrieve 返回合法 MemoryContext | **FAILED（对发布 BLOCKED）** | 生产服务返回 `data.context=[]`，缺 `selected_memory_ids`/`context_version`/`injection_status` |
| D-L2-05 | 空查询不产生伪 Context | **FAILED（对发布 BLOCKED）** | 同上；受控 no-match 探针（非字面空串查询） |

D 轨明确要求：**不得只替换为 3 个 D13C 命名字段**。C/D/E 必须先冻结完整空
`MemoryContext` 响应映射（含 payload 身份校验、`context_version`、时间戳、
token budget、安全 `skipped` 状态），ADR 批准并实现前 D-L2-04/05 保持 BLOCKED。

### BLOCKED（14 项，依赖 C 轨侧工作）

| 需求组 | 阻塞原因（C 轨依赖） |
|---|---|
| D-L2-07~10 | 需生产 `turn.finalized` host mapping（Chat DB 写入与事件字段持久化） |
| D-L2-11~12 | D-L2-11 需 **C++ MemoryClient 在麒麟 VM 的超时状态断言**；D-L2-12 需批准的 slow-handler 场景 |
| D-L2-13~17 | 需 forget host mapping + **C ViewModel 集成** |
| D-L2-18~20 | 需 **C 轨五步编排 + resetAllPipelines 部署到客户端** |

## 环境信息

| 项 | 值 |
|---|---|
| 被测提交（部署） | `053754d611801548fdac59b2894c6862bf85cf56` |
| 采集器 PR head | `267f1e469de87446c871eb338703feff9e83fb88` / squash `2cba0115` |
| Gateway UDS 回归 | `test_gateway_server_d4d.py`：**12 passed**（UDS framing / 默认路由 / 服务端 deadline→TIMEOUT / stop cleanup） |

**证据绑定声明**：VM baseline 绑定部署 commit `053754d`，非 PR head；
基线日志在仓库外（`E:\Kylin-memory-dev\evidence\l2-kylin-vm\runs\`，
SHA-256 `80d04feeae50eb9eabfcecb3b5b47e71830ddb5c13766c2ce5a7173759129b84`），
明确不作为 PR head Runtime 证据。

## 对 C 轨 D13C 的直接影响

1. `runtime_status` 升级依据：仅 D-L2-01/02/03/06 四项可支撑对应通道
   `VERIFIED`；其余 16 项维持 `UNVERIFIED`/`BLOCKED`。
2. C 轨会话评测报告（`d13c-session-eval-report/v1`）的 `provenance.note`
   保持 fail-closed 口径，不因部分 VERIFIED 而整体升级。
3. C 轨后续待办见 `docs/day13/11_d13c_l2_status_summary_20260905.md`。
