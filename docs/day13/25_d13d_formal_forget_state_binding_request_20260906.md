# D13D 正式 Forget 执行：状态绑定与检索观测输入请求

## 状态

`BLOCKED_PENDING_EXTERNAL_BINDING`。本文件记录 D13D adapter 的外部输入缺口，
不定义新的 Dataset 字段、生产 selector 语义或检索算法，也不授权 D13D 自行创建测试目标。

## 已核验事实

- D13E 封存 Dataset 的五个 Forget sample 使用 `d13e-memory-001`、
  `d13e-session-001`、`d13e-topic`、时间窗口和 full reset 选择器。
- `service.forgetting.resolve_forget_targets()` 的 `single_item` 生产路径只解析真实
  数字数据库 ID；session/topic/time_window/full_reset 都从已持久化的同用户事实解析。
- `service.d13d_forget_observability.observe_forget_execution()` 要求由真实检索调用提供
  realtime 与 rebuild 的 `ForgetRetrievalObservation`，其中包括 source snapshot 与 watermark。
- 仓库、`evaluation/d13e/` 和现有 D13D evidence 中均未找到可验证的 sample-to-state
  binding 或上述两类检索观测来源。

因此，adapter 若自行根据 selector 插入 memory、构造 ID 映射、伪造 retrieval 结果或补零，
将违反 D13D-B07 的真实 dispatch 和 fail-closed 约束。

## 请求的外部输入

请由获授权的业务/VM 执行责任方提供一个版本化、可审查的正式环境绑定工件，并给出完整
SHA-256、具名 Owner、批准引用及适用 `tested_commit`。该工件至少应让执行人以不含用户正文的
方式核验以下事实：

1. 每个 Forget `sample_id` 在专用 VM snapshot、工作树和隔离数据库中的预置目标/控制组身份；
2. 单条样本的 Dataset 外部标识与真实、同用户、活动数据库 ID 的受控对应；
3. session、topic、time_window 和 full_reset 的实际持久化前置事实，以及 foreign-user control；
4. 每个 sample 的真实 realtime 与 full-rebuild 检索调用入口、脱敏 trace/reference、
   snapshot ID 与 watermark 来源；
5. 预置状态的创建责任、清理/回退边界，以及 adapter 对这些状态只读验证、preview 和 execute
   的权限范围。

该工件不得包含 Gold、Threshold、expected、formal PASS/FAIL、私钥、凭据或用户正文。

## D13D adapter 的固定边界

收到并核验该工件后，adapter 只能：

- 验证 binding 的版本、SHA-256、`tested_commit`、VM/environment ID 和所有引用的实际存在性；
- 对已经存在的状态走真实 `forget.preview -> confirmation -> forget.execute`；
- 从真实事务和真实检索 observation 调用现有 observer，写入 raw 事实；
- 任一 binding、目标、控制组、trace、snapshot 或 watermark 缺失时非零退出且不写 canonical raw。

adapter 不得创建或修补目标、替换生产 selector、从 Dataset 推导数据库 ID、读取评测判定物，
或将缺失 observation 解释为零残留。

## 对 D13D 状态的影响

在该输入、P0-I3 正式基线选择、独立审查和 VM snapshot 到位前，D13D 只能完成 L0/L1 适配器
合同工作；不得开始五条 Forget formal raw、attestation、Seal、Runner 或 `FROZEN` 流程。
