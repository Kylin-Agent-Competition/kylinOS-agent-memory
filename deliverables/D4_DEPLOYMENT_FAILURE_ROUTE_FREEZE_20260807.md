# 部署路径与失败路由冻结声明

- **冻结日期**：2026-08-07
- **依据**：[02 §3.3] Gate 0 失败路由、`D4_GATE0_FORMAL_DECISION_20260807.md` Gate 0 审查结论、`D4_GATE0_MANUAL_REVIEW_CHECKLIST.md` §2.4 步骤3
- **前提**：D4-D 完成 memory-service/app、Migration、Outbox 基础后执行严格冻结
- **当前阶段**：**设计冻结**（目录结构、命名约定、systemd unit 骨架、失败路由策略已确定；具体实现和 L2 验证待 D4-D）

---

## 一、部署路径（设计冻结）

### 1.1 目录约定 [03 §5, §7.1]

| 路径 | 用途 | 所有者 | 权限 |
|------|------|--------|------|
| `~/.config/kylin-memory/` | 配置文件目录 | 当前用户 | 0700 |
| `~/.local/share/kylin-memory/` | 数据目录（SQLite DB） | 当前用户 | 0700 |
| `~/.local/state/kylin-memory/` | 运行时状态（日志） | 当前用户 | 0700 |
| `$XDG_RUNTIME_DIR/kylin-memory/` | UDS Socket 目录 | systemd RuntimeDirectory | 0700 |

**禁止**：
- ❌ 不写入 `/usr`、`/etc`、`/opt`
- ❌ 不覆盖官方 .so
- ❌ 不要求 root 权限运行

### 1.2 systemd Unit 骨架（设计冻结）

**Unit 文件**：`~/.config/systemd/user/kylin-memory.service`

```ini
[Unit]
Description=Kylin Memory Service
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/kylin-memory-server --socket %t/kylin-memory/memory.sock
RuntimeDirectory=kylin-memory
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
```

**关键约定**：
- 使用 `systemd --user`（用户级服务，不要求 root）
- `RuntimeDirectory=kylin-memory` 自动创建 `$XDG_RUNTIME_DIR/kylin-memory/`
- `%t` = `$XDG_RUNTIME_DIR`
- `%h` = `$HOME`
- Restart=on-failure（异常退出自动重启，与 UT-2 测试一致）
- RestartSec=5s（5秒后退避重试）

### 1.3 Socket 路径约定（设计冻结）

| 模式 | Socket 路径 | 适用场景 |
|------|-----------|---------|
| systemd 模式 | `$XDG_RUNTIME_DIR/kylin-memory/memory.sock` | 生产运行 |
| dev 模式 | `--socket <任意路径>` CLI 覆盖 | 开发调试 |

**证据**：ECHO-003 UDS Echo 全链路在麒麟 VM 上通过（`/run/kylin-memory-echo/echo.sock`），UT-2 验证了 `/home/kylin-agent/.echo_run/echo.sock` 用户自有路径也能正常工作。

### 1.4 构建与安装顺序（设计冻结）

```
1. CMake configure  → cmake -S . -B build
2. CMake build      → cmake --build build
3. Binary verify    → ls -la build/kylin-memory-server
4. Install          → install.sh (systemctl --user daemon-reload + enable)
5. Socket ready     → ls -la $XDG_RUNTIME_DIR/kylin-memory/memory.sock
```

**已知问题**：ECHO-009 FAIL — install.sh 先于 build 执行导致二进制缺失 → **TD-DEPLOY-001**

### 1.5 回退路径（设计冻结）

```
1. systemctl --user stop kylin-memory
2. systemctl --user disable kylin-memory
3. rm -f ~/.config/systemd/user/kylin-memory.service
4. systemctl --user daemon-reload
5. rm -rf $XDG_RUNTIME_DIR/kylin-memory/
```

**证据**：ECHO-006 rollback PASS（systemd stop 清理 socket，无残留进程）

### 1.6 二进制清单（设计冻结）

| 二进制 | 路径 | 用途 |
|--------|------|------|
| `kylin-memory-server` | `~/.local/bin/kylin-memory-server` | Memory Service 主进程 |
| `kylin-memory-cli` | `~/.local/bin/kylin-memory-cli` | 管理 CLI 工具（可选） |
| `echo_client` | `build/echo_client` | Gate 0 测试客户端 |
| `kaiming_memory_client` | `build/kaiming_memory_client` | Gate 0 模拟 Kaiming 客户端 |

---

## 二、数据库初版 Schema（设计冻结）

### 2.1 SQLite 路径

```
~/.local/share/kylin-memory/kylin_memory.db
```

### 2.2 核心表（设计冻结）

#### 2.2.1 conversations

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 会话 ID |
| `user_id` | TEXT | NOT NULL | 用户标识 |
| `session_id` | TEXT | NOT NULL UNIQUE | 会话 UUID |
| `started_at` | TEXT | NOT NULL | ISO 8601 开始时间 |
| `ended_at` | TEXT | | ISO 8601 结束时间（NULL = 活跃） |

#### 2.2.2 turns

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 回合 ID |
| `session_id` | TEXT | NOT NULL REFERENCES conversations(session_id) | 所属会话 |
| `turn_index` | INTEGER | NOT NULL | 回合序号 |
| `original_user_text` | TEXT | NOT NULL | 用户原始输入（**不入 model_request**） |
| `model_request` | TEXT | | 注入 memory context 后的模型请求 |
| `model_response` | TEXT | | 模型原始响应 |
| `is_end` | INTEGER | NOT NULL DEFAULT 0 | TurnFinalizedEvent 标志 |
| `created_at` | TEXT | NOT NULL | ISO 8601 |

**原文隔离约束** [02 §4.1]：
- `original_user_text` 保存用户原始输入
- `model_request` 保存注入 memory context 后的请求
- 禁止在 `model_request` 中原地修改 `original_user_text`
- 检索上下文只允许从 `model_request` 拉取，不得从 `original_user_text` 直接注入

#### 2.2.3 memory_entries

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 记忆条目 ID |
| `user_id` | TEXT | NOT NULL | 所属用户 |
| `entry_type` | TEXT | NOT NULL | `preference` / `knowledge` / `tool_result` / `behavior` |
| `content` | TEXT | NOT NULL | 结构化 JSON 内容 |
| `source_turn_id` | INTEGER | REFERENCES turns(id) | 来源回合 |
| `confidence` | REAL | NOT NULL DEFAULT 0.0 | 可信度 [0.0, 1.0] |
| `version` | INTEGER | NOT NULL DEFAULT 1 | 乐观锁版本号 |
| `is_deleted` | INTEGER | NOT NULL DEFAULT 0 | 软删除标记 |
| `created_at` | TEXT | NOT NULL | ISO 8601 |
| `updated_at` | TEXT | NOT NULL | ISO 8601 |

#### 2.2.4 outbox

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 事件 ID |
| `aggregate_type` | TEXT | NOT NULL | 聚合类型（`turn` / `memory`） |
| `aggregate_id` | TEXT | NOT NULL | 聚合 ID |
| `event_type` | TEXT | NOT NULL | 事件类型 |
| `payload` | TEXT | NOT NULL | JSON 事件负载 |
| `attempts` | INTEGER | NOT NULL DEFAULT 0 | 重试次数 |
| `next_retry_at` | TEXT | | ISO 8601 下次重试时间 |
| `last_error` | TEXT | | 最后一次错误信息 |
| `created_at` | TEXT | NOT NULL | ISO 8601 |

**并发约束** [02 §11.3]：
- 在线检索优先于后台索引写入
- Embedding Worker 默认串行或低并发
- attempts > 3 进 Dead Letter

#### 2.2.5 idempotency_cache

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `idempotency_key` | TEXT | PRIMARY KEY | 幂等键 |
| `user_id` | TEXT | NOT NULL | 所属用户 |
| `session_id` | TEXT | NOT NULL | 所属会话 |
| `response` | TEXT | NOT NULL | 缓存响应 JSON |
| `created_at` | TEXT | NOT NULL | ISO 8601 |
| `expires_at` | TEXT | NOT NULL | ISO 8601（TTL = 24h） |

### 2.3 索引（设计冻结）

| 索引名 | 表 | 列 | 说明 |
|--------|-----|-----|------|
| `idx_turns_session` | turns | (session_id, turn_index) | 按会话查询回合 |
| `idx_memory_user_type` | memory_entries | (user_id, entry_type) | 按用户和类型检索 |
| `idx_memory_deleted` | memory_entries | (is_deleted) | 过滤软删除 |
| `idx_outbox_pending` | outbox | (next_retry_at) WHERE attempts <= 3 | 待处理事件扫描 |

### 2.4 FTS5 全文搜索（设计冻结）

```sql
CREATE VIRTUAL TABLE memory_fts USING fts5(
    content,
    entry_type,
    user_id UNINDEXED,
    tokenize='unicode61'
);
```

使用触发器保持 FTS 与 memory_entries 同步。

---

## 三、失败路由（设计冻结）

### 3.1 总体失败路由策略 [02 §5.3]

```
聊天请求 → Memory Service
  ├─ UDS 连接失败 → 降级：空上下文，聊天继续
  ├─ 150ms deadline 超时 → 降级：空上下文，聊天继续
  ├─ SQLite 读取失败 → 降级：空上下文 + 错误日志
  ├─ Embedding 失败 → 降级：纯关键词检索或空上下文
  ├─ Vector 索引写入失败 → Outbox 重试 × 3 → Dead Letter
  └─ 遗忘/撤回失败 → Outbox 重试 × 3 → Dead Letter + 审计告警
```

### 3.2 降级层级

| 层级 | 场景 | 行为 | 聊天继续？ |
|------|------|------|-----------|
| L0 | 正常 | 返回完整 memory context | ✅ |
| L1 | UDS 超时（≤150ms） | 返回空 context + 日志 | ✅ |
| L2 | Memory Service 不可用 | 返回空 context + 日志 | ✅ |
| L3 | SQLite 损坏 | 返回空 context + 告警 | ✅ |
| Fatal | 任何降级都失败 | 聊天继续（零上下文） | ✅ |

**核心原则**：Memory Service 超时/故障时聊天继续 [02 §2.2]

### 3.3 写入失败路由

```
TurnFinalizedEvent → SQLite INSERT (同步)
  └─ Outbox INSERT (同事务)
      └─ Worker 轮询 (1s)
          ├─ Embedding 成功 → Vector INSERT → Outbox DELETE
          ├─ Embedding 失败 → attempts++ → next_retry_at = now + 2^attempts * 30s
          └─ attempts > 3 → Dead Letter + 告警
```

### 3.4 Dead Letter 策略（设计冻结）

- 事件 `attempts > 3` 后移入 Dead Letter 状态
- 不丢失事件（保留在 outbox 表中，`next_retry_at = NULL`）
- 诊断页暴露 backlog、oldest_pending_age、index_sync_lag [02 §11.3]

### 3.5 幂等写入策略

```
请求到达 → 查 idempotency_cache(user_id, session_id, idempotency_key)
  ├─ 命中 & 未过期 → 返回缓存响应（不执行副作用）
  ├─ 命中 & 已过期 → 删除缓存记录，继续执行
  └─ 未命中 → 执行业务逻辑 → 写入 idempotency_cache（TTL=24h）
```

### 3.6 遗忘/撤回路由

```
forget 请求 → preview（预览影响范围）
  └─ 用户确认 → execute
      ├─ SQLite 软删除（is_deleted=1）
      ├─ Vector 标记删除
      ├─ FTS 重建索引
      ├─ 审计日志写入（不保留正文）
      └─ Outbox INSERT（确保最终一致性）
```

---

## 四、Migration 策略（设计冻结）

### 4.1 Alembic 约定

| 项 | 约定 |
|----|------|
| 工具 | Alembic（SQLAlchemy 2.0 Core） |
| 迁移目录 | `migrations/` |
| 命名 | `YYYYMMDD_<description>.py` |
| 回滚 | 每个迁移必须有 `downgrade()` |
| 基线 | 初版 Schema 为 `001_initial_schema.py` |

### 4.2 禁止操作

- ❌ 不得手动修改 SQLite 文件（必须通过 Alembic）
- ❌ 不得在迁移中使用 `autogenerate` 的 `render_as_batch=False`（SQLite 限制）
- ❌ 不得删除列（SQLite 不支持，使用重命名+迁移）

---

## 五、配置管理（设计冻结）

### 5.1 配置文件路径

```
~/.config/kylin-memory/config.toml
```

### 5.2 核心配置项（设计冻结）

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `socket.path` | string | `$XDG_RUNTIME_DIR/kylin-memory/memory.sock` | UDS 监听路径 |
| `database.path` | string | `~/.local/share/kylin-memory/kylin_memory.db` | SQLite 文件路径 |
| `deadline.default_ms` | int | 5000 | 默认请求超时 |
| `retrieve.deadline_ms` | int | 150 | 检索超时 |
| `outbox.poll_interval_s` | int | 1 | Outbox Worker 轮询间隔 |
| `outbox.max_retries` | int | 3 | Outbox 最大重试 |
| `embedding.model` | string | `default` | Embedding 模型名称 |
| `log.level` | string | `INFO` | 日志级别 |

### 5.3 环境变量覆盖（优先级：CLI > env > config 文件）

| 环境变量 | 覆盖配置项 |
|---------|-----------|
| `KYLIN_MEMORY_SOCKET` | `socket.path` |
| `KYLIN_MEMORY_DB` | `database.path` |
| `KYLIN_MEMORY_LOG_LEVEL` | `log.level` |

---

## 六、已知缺口与待验证项

| 编号 | 项 | 状态 | 计划 |
|------|-----|------|------|
| TD-DEPLOY-001 | 部署顺序修复 | 新增 | D4-D |
| GAP-DB-001 | 初版 Schema 未迁移到 SQLite | 设计冻结 | D4-D 实现 Alembic 迁移 |
| GAP-DB-002 | Outbox 表结构与 Dead Letter 逻辑未实现 | 设计冻结 | D4-D |
| GAP-DB-003 | FTS5 全文搜索未建立 | 设计冻结 | D4-D |
| GAP-DB-004 | 幂等缓存表未创建 | 设计冻结 | D4-D |
| GAP-DEP-001 | systemd unit 未在麒麟 VM 验证 | 设计冻结 | D4-D L2 验证 |
| GAP-DEP-002 | 回退脚本未在干净快照测试 | 设计冻结 | D4 L2 验证 |

---

## 七、冻结对象清单

| 编号 | 对象 | 冻结层级 | 冻结日期 |
|------|------|---------|---------|
| FRZ-DEP-001 | 目录约定（4个标准路径） | 设计冻结 | 2026-08-07 |
| FRZ-DEP-002 | systemd unit 骨架 | 设计冻结 | 2026-08-07 |
| FRZ-DEP-003 | 构建与安装顺序 | 设计冻结 | 2026-08-07 |
| FRZ-DEP-004 | 回退路径 | 设计冻结 | 2026-08-07 |
| FRZ-DB-001 | 核心表结构（5表） | 设计冻结 | 2026-08-07 |
| FRZ-DB-002 | 失败路由策略（5条路径） | 设计冻结 | 2026-08-07 |
| FRZ-DB-003 | 降级层级（L0-L3+Fatal） | 设计冻结 | 2026-08-07 |
| FRZ-DB-004 | Dead Letter 策略 | 设计冻结 | 2026-08-07 |
| FRZ-DB-005 | 幂等写入策略 | 设计冻结 | 2026-08-07 |
| FRZ-CFG-001 | 核心配置项（8项） | 设计冻结 | 2026-08-07 |