# D2-C L2 证据目录

> task_id: D2-C-OSAGENT-SPIKE
> 责任轨道: C · 刘承恩
> Reviewer: D(周子腾) 主审；E(谢嘉然) 补审
> 状态: READY_FOR_L2（脚本与手册就绪，等待人在麒麟虚拟机执行）

## 本目录用途

存放 **银河麒麟虚拟机 L2 层** 的真实宿主实验证据。所有证据必须来自当前 Commit 的麒麟虚拟机，不得用 WSL/Reasonix 沙箱替代。

## 证据清单

执行完三项实验后，将 `d2c_evidence_<timestamp>.tar.gz` 解压到此目录，预期结构：

```
evidence/l2-kylin-vm/d2c/
├── README.md                          # 本说明文件
├── environment.json                   # 环境信息（OS、宿主版本、Commit SHA）
├── postturn/
│   ├── postturn_<ts>.log              # H2C-PostTurn 原始日志
│   ├── postturn_<ts>.summary.json     # is_end 计数报告
│   └── postturn_<ts>.db_snapshots.json # RECORD 表快照
├── prechat/
│   ├── prechat_<ts>.baseline.json     # H2C-PreChat 基线
│   ├── prechat_<ts>.ui_screenshot.png  # UI 截图（含用户气泡）
│   ├── prechat_<ts>.db_message.txt     # 数据库 message 导出
│   └── prechat_<ts>.model_request.jsonl # 模型请求 JSONL
├── tool/
│   ├── tool_<ts>.log                  # H2C-Tool 原始日志
│   └── tool_<ts>.summary.json         # Tool 事件报告
└── checksums.sha256                   # 所有文件 SHA-256 校验和
```

## 关联能力项

| 能力 ID | 能力名称 | D2 前状态 | 本实验目标 |
|---------|---------|-----------|-----------|
| AGT-002 | 普通聊天流式完成 | HOST_VERIFIED/E4 | 确认 is_end=true 唯一，可作为 TurnFinalizedEvent Hook 点 |
| AGT-005 | Memory Context 注入 | UNTESTED/E0·E2 | 验证 UI/聊天库/模型请求三路隔离 |
| AGT-004 | 真实 Tool Result | PARTIAL/E2·E4 | 捕获成功/失败/取消三类事件，关闭 TD-007 |

## 上传后操作

证据上传到本目录后，需：

1. 更新 `evidence/index.yaml` 中 D2-C 条目的 `status` → `L2_VERIFIED` 或 `L2_FAILED`
2. 回填 `commit` 字段（实际执行的 Commit SHA）
3. 回填 `checksum` 字段（checksums.sha256 文件内容哈希）
4. 更新 os-agent-integration/D2_C_宿主实验执行手册.md 的完成定义
5. 关闭/更新 TD-007（如 Tool Hook 路径已确认）

## 脱敏要求

- API Key、用户聊天敏感原文必须脱敏或删除
- 截图如含敏感信息需打码（同时保留原始未打码版本在受控存储）
- 大体积原始日志（>10MB）放外部受控存储，此处仅保留摘要与链接
