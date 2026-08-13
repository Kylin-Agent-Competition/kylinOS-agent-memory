# D2-C L2 证据目录

> **当前审计结论（2026-08-08）：BLOCKED。** 本目录只含部分观察日志；缺少
> PostTurn 数据库前后快照、15 秒稳定性证据与 PreChat UI 截图。strace 关键词
> 命中不是已解码模型请求的证明，Tool 的成功/失败/取消结构化事件也尚未捕获。
> 因此，下面的历史 `PASS_CANDIDATE` / `REVIEW_PENDING` 表述不得用于 Gate 或
> 合并准入判断，待人在麒麟 VM 补采完整证据并经 D/E 审核后再更新。

> task_id: D2-C-OSAGENT-SPIKE
> 责任轨道: C · 刘承恩
> Reviewer: D(周子腾) 主审；E(谢嘉然) 补审
> 状态: BLOCKED（2026-08-08 审计）。以下仅为旧提交的部分观察记录，不能证明三项
> 实验完成，也不能作为 D2-C Gate 或合并准入证据。
> 历史执行 Commit: 20adffc7449ad97f837108b02ce0dcc0d1d79f24
> 执行环境: Kylin-Desktop V11 / Linux 6.6.0-63-generic / VirtualBox (由 systemd-detect-virt 自检测, 禁止硬编码)

## 本目录用途

存放 **银河麒麟虚拟机 L2 层** 的真实宿主实验证据。所有证据必须来自当前 Commit 的麒麟虚拟机，不得用 WSL/Reasonix 沙箱替代。

## 实验执行结果

| 实验 | 当前审计状态 | 阻塞原因 |
|---|---|---|
| H2C-PostTurn | BLOCKED | 缺数据库快照、15 秒稳定性及 UI/RECORD 一致性证据 |
| H2C-PreChat | PARTIAL（H2C-PreChat-3 WAIVED） | 本轮 UI 原文与 RECORD 精确原文已验证；正式 Gateway Audit 未开放，D/E 已书面豁免 H2C-PreChat-3。该豁免不是技术 PASS，仍保留“无法证明请求前注入 Memory Context”的风险。 |
| H2C-Tool | BLOCKED | 未捕获成功、失败、取消的真实结构化 Tool 事件 |

下表为历史观察记录，不改变上述当前审计状态。

| 实验 | 状态 | 关键结论 |
|---|---|---|
| H2C-PostTurn | PASS_CANDIDATE | is_end=true 唯一 (计数=1, sendmsg 到 assistant.sock); 待补数据库前后快照和15秒稳定性验证 |
| H2C-PreChat | PARTIAL_FAIL_CANDIDATE | H2C-PreChat-2 通过 (DB 无污染); H2C-PreChat-3 memory_context 未观察到 (AGT-005=NOT_OBSERVED) |
| H2C-Tool | ARCHITECTURE_FINDING_UNVERIFIED | 发现 stop_chat/intentionrecognition 线索; OpenAI风格关键词=0; 成功/失败/取消Tool结构化事件未捕获 |

## 三大架构发现

1. **AF-1**: Hook 点 A (Pre-Chat Memory Context 注入) strace 未观察到 memory_context 字段 — AGT-005 状态为 NOT_OBSERVED (需源码 instrument 确认, 不得直接判定 NOT_IMPLEMENTED)
2. **AF-2**: 麒麟 AI 助手不使用 OpenAI 风格 tool_call/function_call — Tool 动作由 kylin-ai-runtime 内部 intentionrecognition.cpp 直接执行 (AGT-004=PARTIAL, TD-007=OPEN)
3. **AF-3**: 真实 IPC 通道为 /tmp/.kylin-ai-runtime-unix/1000/assistant.sock (DBus), 方法 chat/stop_chat, 信号 ChatResult

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
│   ├── prechat_<ts>.strace_filtered.log  # 仅诊断用途的 strace 过滤文本
│   └── prechat_<ts>.gateway_audit.jsonl  # 正式脱敏 Gateway Audit JSONL
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

## 完整证据补采后操作

人在麒麟 VM 使用当前被测 Commit 补采完整、脱敏的证据并经 D/E 复核后，方可：

1. 更新 `evidence/index.yaml` 中 D2-C 条目的 `status` → `REVIEW_PENDING`（完整证据上传并经 D Reviewer 复核后，方可升级为 `L2_VERIFIED`）
2. 回填 `commit` 字段（实际执行的 Commit SHA）
3. 回填 `checksum_sha256` 字段（checksums.sha256 文件内容哈希）
4. 更新 os-agent-integration/D2_C_宿主实验执行手册.md 的完成定义
5. 保持 TD-007 为 OPEN（Tool Hook 路径已确认为 intentionrecognition.cpp, 但需源码 instrument 补做成功/失败/取消 Tool 结构化事件）

## 脱敏要求

- API Key、用户聊天敏感原文必须脱敏或删除
- 截图如含敏感信息需打码（同时保留原始未打码版本在受控存储）
- 大体积原始日志（>10MB）放外部受控存储，此处仅保留摘要与链接
