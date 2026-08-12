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

## 当前阻塞与下一步

1. `kylin-bot` 需提供正式、受支持的脱敏审计输出；现有安装中未发现本地审计文件或本地 API 文档服务。
2. 取得审计 JSONL 后，使用 `import-audit` 导入并重跑 PreChat 三路采集。
3. 之后执行 Tool 的成功、失败、取消结构化事件验证。
4. 所有正式证据完成脱敏、校验和与 D/E 复核前，`evidence/index.yaml` 必须继续保持 `BLOCKED`。
