# D14C-02 静态状态记录：Host Mapping / Production Route 核查（tested commit 6a121844）

> 任务：D14C-02（阶段 A）——核对 Host Mapping 是否可进入 production。
> 执行身份：B＝高翌哲（已获用户明确授权代 C 轨执行）。
> 审计日期：2026-09-06。
> 审计性质：**纯静态只读核查**（grep + 读源码注释），不修改任何 production 代码、状态常量或注册逻辑。
> 审计对象：分支 `test/D14C-l3-clean-vm-release-regression` @ `c4a0409`，其代码基线 = `origin/main@6a1218441feeb7b1d96411e60f993061767f3aba`（本批仅新增 docs/day14 文档，memory-service / memory-client 文件树未改动）。
> 审计文件：`memory-service/app.py`、`memory-service/gateway/handlers.py`、`memory-service/service/source_resolver.py`、`memory-client/src/adapters/*`（#151 交付物清单核验）。

---

## 1. 核查方法

```text
grep 定位：PRODUCTION_RESOLVER_STATUS / BLOCKED_BY_HOST_MAPPING / UNSUPPORTED_METHOD
           / turn.finalized / event.ingest / forget.preview / forget.execute / ACTIVE / CANDIDATE
读源码：  memory-service/app.py build_parser() 与 main() 注册分支
          memory-service/gateway/handlers.py register_default_handlers() 与模块 docstring
          memory-service/service/source_resolver.py（PRODUCTION_RESOLVER_STATUS 常量）
```

不改任何状态常量（D 轨决定权）；本记录仅作为 D14C blocker matrix 的静态证据输入。

---

## 2. 核查结论（tested commit 6a121844）

### 2.1 默认注册路由（FRZ-IPC-007，register_default_handlers）

| method | production 默认 | 说明 |
|---|---|---|
| `echo` | 注册 | 连通性/调试 |
| `health` | 注册 | 服务 + DB 探针 + outbox backlog |
| `memory.retrieve` | 注册 | 返回真实空上下文（`context: []`，主检索链未接入；非假数据） |
| `memory.store` | 注册 | 未实现 → `UNSUPPORTED_METHOD`（Gate 0 预期） |

### 2.2 Host Mapping 相关写路由（默认**不注册** → production-effective 未激活）

| method | production 默认 | 显式激活开关 | trusted_identity | 代码内声明状态 | production-effective 状态 |
|---|---|---|---|---|---|
| `turn.finalized` | 不注册 | `--register-turn-finalized`（test/validation + in-memory resolver） | 未提供 | `CANDIDATE / BLOCKED_BY_HOST_MAPPING`（handlers.py docstring；ADR-010 activation 方案 A+B） | `UNSUPPORTED_METHOD`（默认未注册） |
| `event.ingest` | 不注册 | `--register-event-ingest` | `trusted_identity=None` | `BLOCKED_BY_HOST_MAPPING`（app.py 注释；ADR-014 activation 方案 A+B） | `UNSUPPORTED_METHOD`（默认未注册） |
| `forget.preview` / `forget.execute` | 不注册 | `--register-forget-handlers` | `trusted_identity=None` | `CANDIDATE / BLOCKED_BY_HOST_MAPPING`（app.py 注释；ADR-019 activation 方案 A+B） | `UNSUPPORTED_METHOD`（默认未注册） |
| `preference.*` | 不注册 | `--register-preference-handlers` | 未提供 | `CANDIDATE_SYNC`（ADR-016 待立项） | `UNSUPPORTED_METHOD`（默认未注册） |

### 2.3 生产 Resolver 状态

```text
memory-service/service/source_resolver.py
PRODUCTION_RESOLVER_STATUS = "BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED"
```

即服务端 production resolver 仍未注册：turn.finalized production 注册被门禁（`app.py`：production 禁止使用 `--register-turn-finalized`），杜绝「协议 SUPPORTED 但生产必然 INTERNAL_ERROR」矛盾。

### 2.4 #151 已合并交付物（client 侧，复用不重做）

已存在于 tested commit：

```text
memory-client/src/adapters/memory_source_resolver.h
memory-client/src/adapters/production_source_resolver.{h,cpp}
memory-client/src/adapters/turn_extraction_adapter.{h,cpp}
memory-client/tests/test_production_source_resolver.cpp
memory-client/tests/test_turn_extraction_adapter.cpp
```

结论：#151 把 Host Adapter/Resolver 主体（client 侧 + L0/L2 证据）合入 main；但**服务端 production 注册 seam 与 trusted host identity 仍未 ACTIVE**，服务侧 `source_resolver.py` 生产状态保持 `BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED`。

---

## 3. 对 D14C-02 判定的回答

D14C 施工清单 §5 询问四方法当前处于：

```text
ACTIVE / CANDIDATE / BLOCKED_BY_HOST_MAPPING / UNSUPPORTED_METHOD
```

在 tested commit `6a121844` 的**默认 production 启动**下：

- `turn.finalized`：production-effective = `UNSUPPORTED_METHOD`（默认未注册）；声明状态 = `CANDIDATE / BLOCKED_BY_HOST_MAPPING`。
- `event.ingest`：production-effective = `UNSUPPORTED_METHOD`（默认未注册）；声明状态 = `BLOCKED_BY_HOST_MAPPING`（trusted_identity=None）。
- `forget.preview`：production-effective = `UNSUPPORTED_METHOD`（默认未注册）；声明状态 = `CANDIDATE / BLOCKED_BY_HOST_MAPPING`。
- `forget.execute`：production-effective = `UNSUPPORTED_METHOD`（默认未注册）；声明状态 = `CANDIDATE / BLOCKED_BY_HOST_MAPPING`。

**均非 ACTIVE**。`trusted host identity` 未冻结、production resolver registration 未 ACTIVE，对应 D14C Gate：

```text
G5 trusted host identity 已批准      → NOT CLOSED
G6 所需 production routes 已 ACTIVE  → NOT CLOSED
```

---

## 4. 责任边界（本记录不越权）

- C 轨（本批，B 代执行）：只提供/记录静态核查与 blocker 证据；**不修改** `source_resolver.py` 的 `PRODUCTION_RESOLVER_STATUS`、`app.py` 注册门禁或任何状态常量。
- D 轨：审核 trusted host identity；审核 production resolver registration；决定 `turn.finalized / event.ingest / forget.*` 是否升级 `ACTIVE`。
- 正式 L3 结论：保持 NO-GO / PRE-RUN / DIAGNOSTIC only，直至 G5/G6 关闭。

---

## 5. 证据与可复核命令

| 证据 | 位置 |
|---|---|
| 分支/HEAD/基线 | `test/D14C-l3-clean-vm-release-regression` @ `c4a0409`；代码基线 `6a121844…` |
| 默认路由注册 | `memory-service/gateway/handlers.py`：`register_default_handlers()` |
| 显式激活开关与门禁注释 | `memory-service/app.py`：`build_parser()`、`main()` 注册分支 |
| 生产 resolver 状态 | `memory-service/service/source_resolver.py`：`PRODUCTION_RESOLVER_STATUS` |
| #151 交付物清单 | `memory-client/src/adapters/`、`memory-client/tests/test_production_source_resolver.cpp`、`test_turn_extraction_adapter.cpp` |

复核命令（只读）：

```bash
git rev-parse HEAD
git log -1 --oneline
grep -n "PRODUCTION_RESOLVER_STATUS" memory-service/service/source_resolver.py
grep -n "register_turn_finalized\|register_event_ingest\|register_forget_handlers" memory-service/app.py
```

---

## 6. 状态

```text
D14C-02（静态部分）：COMPLETED（记录如上；代码零改动）
D14C formal L3：NO-GO（G5/G6 未关闭，等 D 轨 ACTIVE + trusted host identity）
下一解除阻塞者：D 轨（route ACTIVE / trusted host identity 审批）
```
