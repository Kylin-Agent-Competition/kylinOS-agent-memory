# D14C 请求：production route activation 正式交接

**请求对象：D 轨。状态：`BLOCKED_PENDING_D_ACTIVATION`。**

请针对同一 frozen tested commit 与同一正式 service profile，逐项提供：

| method | 必需回执 |
|---|---|
| `turn.finalized` | `ACTIVE`、production resolver reference、trusted identity reference、启动 profile、approval |
| `event.ingest` | `ACTIVE`、trusted identity precheck reference、启动 profile、approval |
| `forget.preview` | `ACTIVE`、trusted identity reference、启动 profile、approval |
| `forget.execute` | `ACTIVE`、trusted identity reference、启动 profile、approval |

回执必须同时列出 route activation reference、tested commit、service package identity 与可复核证据路径。`--register-*`、in-memory resolver、validation profile 或 `UNSUPPORTED_METHOD` 都不能作为 ACTIVE 回执。收到前 G6 保持 `BLOCKED`。
