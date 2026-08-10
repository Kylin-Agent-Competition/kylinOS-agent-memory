# PR 审查报告 — PR #25

- **对照文档**：项目仓库 `docs/baseline/01_sdk_model_abi_baseline.md`（v1.0，2026-07-26）、`docs/baseline/03_defensive_checklist.md`（v1.0，2026-07-26）。完整基线文档 `02_architecture_sop.md`、`04_agent_llm_guide.md` 未在仓库中找到；PR 引用的「总体架构文档 v1」TABLE 12/48/54/55/15/17 亦无法交叉验证（`docs/architecture/` 中该文档尚为计划项）。
- **PR 范围**：Day5 首个真实垂直链路——EmbeddingService(UDS+envelope+真实降级) + 线程池
- **Head**: `feat/day5-minimal-vertical-chain` → **Base**: `main`
- **作者**：lyf-1213 | **审查者**：D 主审
- **变更规模**：+1147 / -1（11 文件：7 新增，4 修改）
- **结论**：**PASS_WITH_DEBT**（需记录技术债 TD-A-005-09，已登记）

---

## 问题清单

| # | 位置(文件:行) | 严重度(Critical/High/Medium/Low) | 类型(Bug/Blocker/Risk/Debt/建议) | 问题描述 | 对照依据 | 修复建议 |
|---|---|---|---|---|---|---|
| 1 | `embedding_service.py:50-53` + `server.py:108` | Medium | Debt | 启动期 SDK 缺失无降级：`EmbeddingProvider.__init__` 在 `kylin_embedding` 缺失时直接 `raise RuntimeError`，`server.py` 硬编码 `EmbeddingService()` 无 provider 注入点——导致无 SDK 时 UDS server 构造即崩溃 | `[01 §5.3]` SDK 缺失应走降级而非崩溃；架构 13.1 要求聊天继续 | **已登记 TD-A-005-09**（Medium，计划 2026-08-14），接受为 Debt。计划修复：Provider 可注入/延迟构造 + 无 SDK 时返回结构化降级 |
| 2 | PR body / `memory-service/README.md` | Low | 建议 | 引用「总体架构文档 v1」TABLE 12/48/54/55/15/17 等，但仓库 `docs/architecture/` 中不存在该文档（README 中"总体架构图与模块划分"仍为计划内容）。审查无法交叉验证引用的一致性 | `[02 §18.1]` PR 应含架构依据可追溯 | 在 PR 中补充架构文档的仓库路径，或在 README 注明文档仍在外部/待同步；若为外部文档，应标注版本和获取方式 |
| 3 | `embedding_service.py:153-154` | Low | 建议 | 超时后 `fut.cancel()` 无法中断已在执行的线程（Python ThreadPoolExecutor 已知限制）。代码注释已说明此行为，但未关联 TD 编号 | `[02 §17.5]` TODO/FIXME 应引用 TD 编号 | 无需阻塞合并；若后续需精确中断能力，可登记为 TD 条目 |
| 4 | `test_embedding_service_real.py:121-149` | Low | 建议 | `test_degraded_when_so_missing` 使用 `FailProvider` 注入模拟降级，未在麒麟 VM 复现真实 `dlopen` 失败路径。当前 L2 证据无法证明「真实 so 缺失」端到端降级 | `[01 §1.3]` 接口返回成功≠业务正确，需核对实际结果 | 已在 TD-A-005-09 验收标准③中列入；无需独立登记 |

---

## 范围与契约核对

| 检查项 | 结果 |
|--------|------|
| 是否超出 Day5 任务卡批准范围 | ✅ 否——仅为 Embedding 最小垂直链路，未涉及记忆读写/检索/偏好 |
| 是否改动冻结契约（IPC 协议/Schema/数据库字段/错误码） | ✅ 否——新增 `memory.embed`/`memory.embed_batch` 标记为 P2-1（不在冻结方法集），`memory.ping`/`memory.health` 在冻结集内 |
| 是否改动 Day4 已合并代码 | ✅ 否——`cpp-bridge/`、`memory-service/providers/` 未修改 |
| 是否改动架构 4.4 冻结方法语义（retrieve/observe_turn 等） | ✅ 否 |
| 信封协议 `protocol_version=1.0` 是否与已有系统兼容 | ✅ 新增模块，无历史兼容负担 |

---

## 逐项检查结果

### 1. 假实现与降级正确性 ✅

- **生产路径无 Mock/固定返回值**：`embed()` 调用真实 `EmbeddingProvider`（进程级单例，Day4），无硬编码向量
- **降级返回真实语义**：Provider 不可用 → `ok=true` + `degraded=true` + 明确空向量 `{"vector": [], "dimension": 0}`，**非固定样例**，符合架构 TABLE 54 红线
- **超时返回结构化错误**：`ERR_TIMEOUT`（`ProviderErrorCode.ERR_TIMEOUT`），不返回假数据
- **无 TODO/FIXME/HACK 未关联 TD**：全量扫描 `embedding_service.py` 和 `server.py` 确认 0 处违规
- **启动期降级缺口**：已登记为 TD-A-005-09（见问题 #1）

### 2. 架构红线 ✅

- **原文隔离**：本次 PR 不涉及聊天数据库/用户原文，无污染风险
- **SQLite 真源**：不涉及（D6+）
- **Post-Turn 异步写入**：Bridge 调用在 `ThreadPoolExecutor(max_workers=2)` 执行，`embed_thread != caller_thread` 断言通过，不阻塞聊天线程
- **不重写官方 UI**：✅
- **数据源层级**：D5 为 Embedding 链路，不声称多源接入完成
- **检索融合**：不涉及（D6+）
- **Outbox 并发模型**：不涉及
- **版本链**：不涉及

### 3. SDK / ABI / 环境边界 ✅

- **只调用已验证符号**：`text_embedding_create_session`、`text_embedding_init_session`、`text_embedding_embed` 等均为 `[01 §5]` 已验证接口
- **未硬依赖未验证接口**：`text_embedding_init_model`（SOURCE_VERIFIED 但未 HOST_VERIFIED）仅 SDK 内部日志 warn 建议调用，代码未强制依赖
- **未修改 SDK 头文件**：✅
- **构建产物放项目目录**：CMake 构建在 `cpp-bridge/build/`，不写入 `/usr`
- **KYSEC**：不涉及（本次为上层 Service，不直接触碰内核安全模块）
- **SDK Bridge 防御性设计**：查询向量维度由 Provider 校验（Day4 已有），空输入异常由 `[01 §5.5]` 覆盖
- **每次重试新建 ClientContext**：Provider 由 Day4 管理生命周期，不涉及本次变更

### 4. 安全 ✅

- **无密钥/密码/Token**：全量代码扫描 0 发现
- **4 MiB 消息上限**：`protocol.py:32` 定义 `MAX_MSG_LEN`，`encode()`（L45-46）和 `decode_packet()`（L64-65）双侧校验
- **method 白名单**：`parse_envelope()` 的 `expected_methods` 参数强制校验，未知方法返回 `ERR_PROTOCOL`
- **输入类型校验**：`embed()` 拒绝非 str 输入 → `ERR_INVALID_TEXT`；envelope payload 必须为 dict
- **日志不记录敏感原文**：✅
- **Tool 失败不沉淀为成功知识**：不涉及（D6+）

### 5. 测试与证据

| 层级 | 状态 | 详情 |
|------|------|------|
| L0 静态检查 | ✅ | 全量 pytest 36 passed + 47 skipped（WSL），反向顺序同样 36 passed |
| L1 组件集成 | ✅ | 协议 12 + Service 11 = 23 项全绿（encode/decode 往返、半包/粘包、非法版本/方法/payload、降级、超时、线程池断言） |
| L2 麒麟 VM | ✅ | 真实 SDK 8/8 无 Skip（768 维/中文/空串/batch/envelope 分发/health/降级）+ 端到端 UDS（bridge_loaded=true, embed dim=768, request_id/trace_id 回显）；证据文件 `evidence/l2-kylin-vm/day5_verify_latest.log`，checksum `2f506a89`，evidence/index.yaml 条目 EMBED-CALL-004 |
| L3 全链路 | N/A | D5 为 Embedding 垂直链路，记忆读写/检索全链路属 D6+ |
| Gate 0 前置门禁 | N/A | 不涉及 Hook 构建/部署/KYSEC/回退 |
| 证据等级 | E4 | `HOST_VERIFIED`，来自真实麒麟 V11 x86_64 虚拟机，Python 3.12.3，Runtime 1.3.0 |

**仍需麒麟宿主验证项**：
- 真实 `dlopen` 失败端到端降级（当前仅 mock 覆盖，TD-A-005-09 验收标准③）
- 异步/并发/大 batch 压测
- envelope `deadline_ms` 强制执行

### 6. 技术债与门禁

| 检查项 | 结果 |
|--------|------|
| Critical=0 | ✅ 当前无 Critical 项 |
| High | ✅ 当前无 High 项（TD-A-005-09 为 Medium） |
| 新增 TD-A-005-09 | ✅ 完整登记：编号、标题、模块、类别(Technical Debt)、严重度(Medium)、责任人(A 轨成员)、Reviewer(D 主审+E 补审)、计划日期(2026-08-14)、验收标准(3 条)、延期说明 |
| 核心指标/安全/一致性类问题登记为技术债 | ✅ 否——TD-A-005-09 属健壮性增强，不涉及核心指标/安全/一致性 |
| 失败分类正确 | ✅ 无删除/削弱测试换取通过的情况 |

### 7. 文档与 PR 完整性

| 检查项 | 结果 |
|--------|------|
| PR 含背景/修改范围/不修改范围 | ✅ |
| PR 含架构与能力边界依据 | ⚠️ 引用 TABLE 12/48/54/55 无法在仓库中验证（见问题 #2） |
| PR 含 L0-L3 证据路径 | ✅ |
| PR 含技术债变化 | ✅ TD-A-005-09 新增 |
| PR 含回滚方式 | ✅ 分支级回退，纯新增目录无残留 |
| 能力状态已回写 | ✅ evidence/index.yaml EMBED-CALL-004 status=HOST_VERIFIED |
| Reviewer 非作者 | ✅ 本次审查由 D 主审执行 |

---

## 技术债变化

| 变化 | TD 编号 | 严重度 | 状态 |
|------|---------|--------|------|
| 新增 | TD-A-005-09 | Medium | Open（验收标准：①Provider 可注入/延迟构造；②无 SDK 时 server 返回结构化降级；③麒麟 VM 补充 so 缺失端到端证据） |
| 仍存在 | TD-A-005-01~08 | — | Open（均为 Day4 遗留，不在本次修改范围） |

---

## 待人工裁决项

1. **架构文档引用可验证性**：PR body 和 README 多处引用「总体架构文档 v1」的 TABLE 12/48/54/55/15/17，但仓库 `docs/architecture/` 仅有检索候选草案和事件契约，不包含该总体架构文档。需裁决：
   - 该文档是否存在于外部（如共享网盘/内部 Wiki）？若存在，应在 PR 中标注获取路径和版本。
   - 若文档尚未完成，PR 中的 TABLE 引用应改为 `[计划中]` 或引用对应的 ADR/基线条目。

---

## 最终结论

**PASS_WITH_DEBT**

本 PR 实现了 Day5 首个真实垂直链路的核心目标：
- ✅ UDS + 长度前缀 JSON + 架构 4.4 envelope 协议完整且防御完备
- ✅ EmbeddingService 接真实 Provider → 768 维向量，降级返回明确空向量（非假数据）
- ✅ Bridge 调用在线程池执行，不阻塞聊天线程
- ✅ 麒麟 VM L2 证据真实有效（8/8 无 Skip + 端到端 UDS 全绿）
- ✅ 安全边界齐备（4 MiB 上限、method 白名单、无密钥泄露）
- ✅ 启动期降级缺口已登记为 TD-A-005-09，有明确验收标准和计划日期

阻塞项为零。建议合入后跟踪 TD-A-005-09 在 Day6+ 的修复进展，并补充架构文档引用路径。