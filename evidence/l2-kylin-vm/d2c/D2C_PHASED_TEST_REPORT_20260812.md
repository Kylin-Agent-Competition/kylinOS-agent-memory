# D2-C 阶段性测试报告（2026-08-12）

> 状态：`BLOCKED`。本报告记录临时 VM 上的诊断与脚本验证，不构成 D2-C Gate PASS，也不替代正式 L2 证据包。

## 范围与环境

- 被测分支：`docs/C-d2-osagent-runtime`
- 脚本修复提交：`ae85be3`（正式脱敏网关审计导入）
- 环境：隔离的 Kylin Desktop V11 VirtualBox 临时 VM
- 限制：不导出 API Key、`kylin-bot` 密钥、原始模型请求、原始 Memory Context 或临时 trace。

## 阶段性结果

| 项目 | 结果 | 证据状态 |
|---|---|---|
| H2C-PostTurn | `DIAGNOSTIC_PASS` | 已观察到 `is_end=true`；已完成 DB 快照与 15 秒稳定性检查。正式证据包仍待脱敏整理及复核。 |
| H2C-PreChat UI | `DIAGNOSTIC_PASS` | AI 智能体模式可接受标记请求并返回响应。 |
| H2C-PreChat-3 | `BLOCKED` | 未获得正式、脱敏的网关模型请求审计记录，不能证明 Memory Context 已进入模型请求。 |
| H2C-Tool | `NOT_VERIFIED` | 未捕获真实成功、失败、取消的结构化 Tool 事件。 |
| D2-C Gate | `BLOCKED` | 三项实验的正式完整 L2 证据尚未齐全。 |

## 已定位的 PreChat 链路

本次诊断确认 AI 助手主进程会连接：

```text
kylin-aiassistant -> ~/.kylinbot/gateway.sock -> /usr/bin/kylin-bot daemon
```

因此，旧脚本假设的 `kylin-ai-runtime` `genai-nlp.sock` 不是该智能体请求的实际承载通道。对 Runtime socket 的 `strace` 或关键词匹配不能证明 Hook A 注入成功。

## 已完成的修复与验证

`ae85be3` 新增：

- `import-audit FILE.jsonl`，仅接受来源为 `kylin-bot-gateway` 的正式脱敏 JSONL；
- 必需字段：`timestamp`、`source`、`request_id`、`user_marker`、`memory_context_present`、`context_sha256`、`field_names`；
- 字段白名单：拒绝 `api_key` 或任何未声明字段，避免原始请求和密钥进入证据；
- PreChat-3 只有导入正式审计且 `memory_context_present: true` 时才可通过。

临时 VM 验证结果：Bash 语法通过；合规审计记录可导入；含 `api_key` 的记录被拒绝。

## 2026-08-13 重测：可复用运行骨架

本轮仅验证未偏离主线的真实会话、真实智能体触发与脚本安全清理；不采集、打包或提升任何 Gate 证据状态。

- 环境恢复：将此前由 `root` 遗留创建的临时测试状态目录和输出目录恢复给测试用户；未修改 AI 配置、会话数据库内容或正式证据目录。
- PreChat：前台 AI 智能体完成带标记请求并返回响应；标记消息已写入本地 `RECORD`（本轮最新行号为 `80`）。脚本仅附加到真实助手进程，启动/停止成功且采集 PID 状态文件已删除。
- PreChat 限制：原始采集日志仅含 `strace` attach/detach 两行，未获得模型请求内容；因此 H2C-PreChat-3 继续为 `BLOCKED`。
- Tool：前台智能体完成一次北京天气查询并返回完整结果；观察脚本启动/停止成功，采集 PID 状态文件已删除且摘要 JSON 格式有效。
- Tool 限制：原始采集日志同样仅含 attach/detach 两行，未捕获结构化成功、失败或取消 Tool 事件；因此 H2C-Tool-1/2/3/4 继续为 `NOT_VERIFIED`。
- 文案回归：Tool 零计数输出已调整为 `NOT_OBSERVED` / `DIAGNOSTIC`，避免将诊断计数误表述为验收通过；隔离零计数回归已通过并清理临时产物。

## 当前阻塞与下一步

1. `kylin-bot` 需提供正式、受支持的脱敏审计输出；现有安装中未发现本地审计文件或本地 API 文档服务。
2. 取得审计 JSONL 后，使用 `import-audit` 导入并重跑 PreChat 三路采集。
3. 之后执行 Tool 的成功、失败、取消结构化事件验证。
4. 所有正式证据完成脱敏、校验和与 D/E 复核前，`evidence/index.yaml` 必须继续保持 `BLOCKED`。
