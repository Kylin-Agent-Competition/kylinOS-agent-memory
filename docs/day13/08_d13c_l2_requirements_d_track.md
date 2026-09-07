# D13C L2 麒麟 VM 实测需求 — D 轨（IPC/数据轨）

## 背景

C 轨 D13C 已完成 L0 Mock 契约测试（S1-S6）与 L1 Python 评测账本（32 passed）。
L0/L1 均基于 Mock Gateway，**Runtime 结论标为 `UNVERIFIED`**。
L2 麒麟 VM 实测需 D 轨在真实部署环境中提供以下结论，以便 C 轨将会话评测
结论从 `UNVERIFIED` 升级为 `VERIFIED`。

> **交付状态（2026-09-05 更新）**：D 轨已通过 PR #149 交付只读 L2 采集器并
> 记录 VM baseline（部署 commit `053754d`）。详见
> `docs/day13/10_d13c_l2_d_track_delivery_20260905.md` 与 D 轨执行文档
> `docs/day13/08_d13c_d_l2_rework_execution.md`。下表已附交付状态列。

---

## D 轨需提供的 L2 结论清单

### 1. IPC 通道可用性结论

| # | 结论项 | 验证方法 | 预期结果 | 交付状态 |
|---|---|---|---|---|
| D-L2-01 | UDS socket 在麒麟 VM 可监听 | 部署 memory-service 后确认 socket 文件存在 | socket 文件权限 0600，路径符合 FRZ-IPC-001 | **VERIFIED**（PR #149 baseline） |
| D-L2-02 | 客户端可连接 Gateway | memory-client `connectToService()` 返回 `connected` | connectionState=connected，无 error | **VERIFIED**（PR #149 baseline，echo 探针） |
| D-L2-03 | 长度前缀协议在麒麟 VM 正确编解码 | 发送 echo 请求，校验响应 envelope | status=ok，data.echo 回显 method | **VERIFIED**（PR #149 baseline） |

### 2. memory.retrieve 端到端结论

| # | 结论项 | 验证方法 | 预期结果 | 交付状态 |
|---|---|---|---|---|
| D-L2-04 | memory.retrieve 返回合法 MemoryContext | 执行 PreChat pipeline，校验 `data.context` | context 含 selected_memory_ids / context_version / injection_status | **FAILED→BLOCKED**：生产返回 `context=[]`；需 C/D/E 联合 ADR 冻结完整空 MemoryContext 映射 |
| D-L2-05 | 空查询不产生伪 Context | 查询无命中条件，观察 `injection_status` | injection_status=skipped，context 为空对象 | **FAILED→BLOCKED**：同 D-L2-04（受控 no-match 探针） |
| D-L2-06 | SQLite 查询延迟在麒麟 VM 可接受 | 记录 `memory.retrieve` 请求-响应延迟 | p50 < 300ms，p95 < 1000ms | **VERIFIED**：30 样本，p50=1.703ms / p95=3.656ms |

### 3. turn.finalized 端到端结论（ADR-010）

| # | 结论项 | 验证方法 | 预期结果 | 交付状态 |
|---|---|---|---|---|
| D-L2-07 | turn.finalized 在麒麟 VM 可写入 Chat DB | 执行 PostTurn pipeline，查询 Chat DB | TurnFinalizedEvent 持久化成功，字段完整 | **BLOCKED**：需生产 turn.finalized host mapping |
| D-L2-08 | stop_reason 透传到 ChatRecord | 对比请求 payload 与 Chat DB 记录 | stop_reason 原样持久化 | **BLOCKED**：同 D-L2-07 |
| D-L2-09 | retry_of_turn_id 透传到 ChatRecord | 构造 retry 场景，查询 Chat DB | retry_of_turn_id 正确持久化 | **BLOCKED**：同 D-L2-07 |
| D-L2-10 | finalization_reason 在事件顶层（非 metadata） | 查询 Chat DB 记录结构 | finalization_reason 在事件顶层，不在 metadata 嵌套内 | **BLOCKED**：同 D-L2-07 |

### 4. deadline timeout 行为结论

| # | 结论项 | 验证方法 | 预期结果 | 交付状态 |
|---|---|---|---|---|
| D-L2-11 | 客户端 5000ms deadline timeout 在麒麟 VM 生效 | Gateway 延迟响应（>5000ms），观察客户端行为 | stage=timeout，busy=false，可恢复 | **BLOCKED**：需 C++ MemoryClient 在 VM 的超时状态断言（C 轨待办，L0 S4 已有 Mock 版） |
| D-L2-12 | Gateway 侧 deadline_ms 超时处理 | 请求携带 deadline_ms=2000，Gateway 延迟 3000ms | Gateway 返回 TIMEOUT 错误码 | **BLOCKED**：需批准的 slow-handler 场景（服务端 deadline→TIMEOUT 语义已由 `test_gateway_server_d4d.py` 12 passed 佐证，非完整 D-L2-12） |

### 5. 精准遗忘结论（D 轨 SQLite 事务）

| # | 结论项 | 验证方法 | 预期结果 | 交付状态 |
|---|---|---|---|---|
| D-L2-13 | forget.preview 在麒麟 VM 返回 selection_hash | 执行 forget.preview，校验响应 | 含 selection_hash / affected_count / confirmation_credential | **BLOCKED**：需 forget host mapping |
| D-L2-14 | forget.execute 在麒麟 VM 执行软删事务 | 执行 forget.execute 后查询 SQLite | 条目 memory_status=deleted，审计日志完整 | **BLOCKED**：同 D-L2-13 |
| D-L2-15 | 确认凭据一次性消费 | 同一 confirmation_token 重复执行 | 第二次返回 INVALID_REQUEST | **BLOCKED**：同 D-L2-13 |
| D-L2-16 | 跨用户操作拦截 | 请求 user_id 与响应 user_id 不匹配 | forgetCrossUserBlocked=true，stage=failed | **BLOCKED**：需 C ViewModel 集成 |
| D-L2-17 | 明文 target_selector 清除 | forget.preview 后检查 ViewModel 状态 | forgetSelectorCleared=true | **BLOCKED**：需 C ViewModel 集成 |

### 6. 主演示编排稳定性结论

| # | 结论项 | 验证方法 | 预期结果 | 交付状态 |
|---|---|---|---|---|
| D-L2-18 | 5 步 7 IPC 方法全流程在麒麟 VM 可完成 | 执行 D11-C 主演示编排一轮 | 7 步全部 stage=ready/sent/completed | **BLOCKED**：需 C 轨五步编排部署 |
| D-L2-19 | 复跑 5 轮无 hang / 无 stage 错乱 | 连续 5 轮主演示编排 | 5 轮全部成功，无 hang、无 stage 残留 | **BLOCKED**：同 D-L2-18 |
| D-L2-20 | resetAllPipelines 后可重新发起 | 复跑后执行 reset，再发起请求 | stage 回 idle，新请求正常完成 | **BLOCKED**：同 D-L2-18 |

---

## 输出要求

D 轨需将以上结论归档为 evidence 条目（`evidence/index.yaml`），包含：

- **环境信息**：麒麟 OS 版本、memory-service commit SHA、SQLite 版本、部署配置
- **测试命令**：可复现的完整命令序列
- **原始日志**：请求/响应 envelope 全文 + Chat DB 查询结果（脱敏后）
- **结论标注**：每项标注 `VERIFIED` / `FAILED` / `BLOCKED`
- **SHA-256 校验**：所有日志/数据文件含递归校验和

C 轨在收到 D 轨 L2 结论后，将更新 D13C 会话评测报告的 `provenance.runtime_status`
从 `UNVERIFIED` 升级为对应结论。
