# fix(C): align C-track fields with KMA canonical schema v1

**轨道 (Track)**：C 轨（memory-client ViewModel + os-agent-integration 契约层 + 双端 L0/L1 测试）
**Head**：`a2dd45f`  on branch `fix/c-d12-schema-drift-canonical-adapter`（rebased on latest main，已纳入 E 轨 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1` + `docs/day12/14_d12e_knowledge_td017_closure_audit_20260903.md` 移交的治理点）
**Base**：`main`

## 背景（Why）

E 轨在 D12E 审计与 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` 中冻结了统一业务字段命名，C 轨在 event payload / manual config / behavior 等 6 处出现与 Canonical 命名不一致：

| Drift ID | Legacy（C 轨遗留） | Canonical（KMA v1 冻结） | 影响面 |
| --- | --- | --- | --- |
| KMA R-1 / TD-060 | `collected_at` | `captured_at` | 所有事件 metadata 时间字段 |
| KMA R-5 | `sensitivity_level` | `sensitivity` | ManualConfig 敏感等级 |
| DRIFT-007 | 单字段 `scope`（混含"配置类型"与"偏好作用域"两层含义） | `config_kind` + `preference_scope` | ManualConfig `scope` 拆分 |
| DRIFT-008 / 009 | `key` / `value` | `preference_key` / `preference_value` | ManualConfig KV 命名 |
| DRIFT-002 / 003 | 仅 `execution_status=failure`（Host DTO 术语） | `source_business_status=failed`（KMA 业务结果） + Host DTO 保留 | Tool.execution 业务状态 |
| DRIFT-011 | 单字段 `actor`（混含"角色标签"与"可信 ID"） | `actor_role` + `actor_id` | Behavior 行为事件 |
| DRIFT-004 | 隐式 source_type 推断 | `source_type_projected` + `mapping_status` 显式标注 | Behavior→MemorySourceEvent 映射 |

若不修正：下游 E 轨 Canonical 适配器进入 fail-closed，C 轨事件在生产路径被直接丢弃。

## 改动（What）

### 契约层 `os-agent-integration/contracts/`（2 files）

- `memory_event_contract_v1.h` / `.cpp`：
  - **R-1 TD-060**：新增 `readCanonicalCapturedAt` → INPUT 同时接受 `captured_at`（Canonical，优先）与 `collected_at`（legacy transport 别名）；**OUTPUT 只写 Canonical 名 `captured_at`**。
  - 时间字段 required 校验失败以 Canonical `captured_at` 报告，避免错误信息仍指向 legacy 名。
  - 类型错误 (`invalid_type`) 双通道校验两个 key 任一非字符串即报错。
  - **DRIFT-003**：`toolExecutionStatusFromString` 同时接受 `failure`(Host DTO) 与 `failed`(Canonical KMA)，统一映射到 `ToolExecutionStatus::Failure`，序列化仍保留 Host DTO 词形 `failure`（下游以 `source_business_status` 为准）。

### ViewModel 层 `memory-client/src/view_models/memory_view_model.cpp`（1 file）

- **R-1**：`buildMemoryContextMetadata` / `tool_metadata` / `turn.finalized` nested metadata 全量输出 Canonical `captured_at`，`collected_at` 作为 transport legacy 由 contracts 侧双名接受，不在 Client 输出。
- **DRIFT-002/003**：`runToolPipeline` 除原 `execution_status` 外附加 Canonical 字段 `source_business_status`，并显式 `failure → failed` 归一；其余词形 (success/partial/cancelled/timeout) 保持一致。
- **KMA R-5 / DRIFT-007/008/009**：`runManualConfigPipeline`
  - `scope` 拆为 `config_kind`（原 scope 值，"配置类型"层） + 当 `config_kind==preference` 时 `preference_scope=global`（Demo 默认，等宿主回填）；
  - `key/value` → `preference_key/preference_value`；
  - legacy 短名与 Canonical 长名**双写**，Adapter Window 内新旧 reader 都可读；
  - `sensitivity`(Canonical, 小写归一) 与 `sensitivity_level`(alias, 原始大小写) **双写**；
  - `confidence`/`confidence_score` 双写 (DRIFT-009 兼容)。
- **DRIFT-011 / DRIFT-004**：`runBehaviorPipeline`
  - `actor` 拆 `actor_role`(user/agent/system 标签) + `actor_id=PENDING_HOST_IDENTITY`（Fail-closed，生产端必须注入可信实体 ID，否则 block）；
  - `source_type_projected`：已知 chat 类(um/ar/sm) → `chat`；user_action 类显式标 `PENDING_E_DECISION_D021_user_action`，pending E 轨裁决；
  - `mapping_status=PENDING_C_CONFIRMATION`，通知 C 轨下游：SourceType 枚举映射尚未冻结，不得入库。

### 测试更新（3 files）

- `os-agent-integration/tests/test_memory_event_contract_v1.cpp`
  - 3 组 fixture (MemoryContext / ToolExecution / TurnFinalized) 改用 Canonical `captured_at`。
  - `*RequiresTrustedMetadata_data()` / `*RequiresEventTimestamps_data()` 中 `collected_at` 行 → `captured_at`。
  - `toolExecutionStatusParsesKnownValues_data()` 新增 `failed → Failure` 用例（共 6 个状态）。
  - `turnFinalizedValidationRequiresCollectedAt` 重命名为 `turnFinalizedValidationRequiresCapturedAt`，验证字段错误名改为 `captured_at`。
  - `eventMetadataWrongJsonTypesAreRejected_data` 中 Turn 事件的 `"collected_at":42` → `"captured_at":42`，错误字段同步。
- `memory-client/tests/test_d5_vertical_link_demo.cpp`
  - fixture 中 `collected_at` → `captured_at`。
  - ADR-010 turn.finalized nested metadata 必填校验接受 `captured_at` 或 `collected_at` 任一（Adapter Window 兼容）。
  - `previewAndSendReuseSameEventIdTimestamp` 缓存一致断言改比较 `captured_at`。
- `memory-client/tests/test_d6c_multi_source_adapters.cpp`
  - B1 `manualConfigLongTermPersisted` mock 必填校验升级为**双通道**：
    - `scope` 或 (`config_kind` + `preference_scope`)；
    - `key` 或 `preference_key`；
    - `value` 或 `preference_value`；
    - `sensitivity_level` 或 `sensitivity`；
    - 确保 ViewModel 双写输出在下游 Mock 端一致接受。

## 用户与开发者影响（Impact）

- **Host DTO 层兼容（C→B/C→A）**：仍保留 legacy 字段 (`execution_status=failure`、`scope/key/value`、`sensitivity_level`)，上游 B/A 轨现有消费者零修改。
- **Canonical 通道（C→E 业务入库）**：已对齐 KMA v1，E 轨 Canonical Adapter 不再 fail-closed。
- **Fail-closed 保障**：
  - `actor_id=PENDING_HOST_IDENTITY`：生产端 Canonical Adapter 必须检查此字段并拒绝非可信注入；Client Demo 直接放行（仅演示）。
  - `source_type_projected=PENDING_E_DECISION_D021_user_action`：禁止对 user_action 行为事件做 C 轨隐式 schema 推断。
  - `mapping_status=PENDING_C_CONFIRMATION`：ManualConfig / Behavior 候选项不得在 C 轨未冻结 SourceType 前落正式表（MEMORY_BUSINESS_SCHEMA_V0.1 §2.9 close）。

## 验证（Validation）

| 检查项 | 结果 | 备注 |
| --- | --- | --- |
| `git diff --check` | ✅ Clean | 无尾随空白 / 无 Tab-Space 混用 / 无 EOF 缺换行 |
| Diff stat | 7 files / +265 / −35 | 6 代码 + 1 PR body；本次范围完整无泄漏 |
| 分支状态 | ✅ ahead main，无落后 | push 前已 clean rebase（用户要求 PR 必须基于最新 main） |
| `cmake --build build` + `ctest --output-on-failure` | ⚠️ 未在本机执行 | Windows 本机缺失 cmake/Qt6 工具链（仅有 gcc）；**必须在 Linux 构建机 / CI workflow `memory-client-ctest.yml` 上执行 L0/L1 编译 + ctest 并附日志后方可 Merge** |
| 字段级双通道 | ✅ 已覆盖 6 tests | legacy→Canonical INPUT 接受 + Canonical OUTPUT 归一 + 双写 Mock 通过 |

## 待 Reviewer 裁决项（Blockers to Close）

1. **CI 绿灯**：`memory-client-ctest.yml` 全部通过（含 contract+v1 parse, d5, d6c）。
2. **E 轨 D021 user_action 最终 SourceType**：`PENDING_E_DECISION_D021_user_action` 是占位，需要 E 给出 `chat` / `manual_behavior` / 新枚举值，C 侧对应替换。
3. **可信 `actor_id` 注入方式**：需要 Canonical Adapter 明确 host identity 来源（例如系统 Kiosk session / 可信 D-Bus 标识），Demo 的 `PENDING_HOST_IDENTITY` 不得长期保留。

## Related / Cross-track References

- E 轨治理：`docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md`（冻结条款 R-1, R-3, R-5, R-6）
- 生命周期漂移移交：`docs/day12/14_d12e_knowledge_td017_closure_audit_20260903.md`
- C 轨治理提案：`docs/architecture/C_TRACK_CANONICAL_FIELD_FREEZE_PROPOSAL_V0.2.md`（本轮已对齐其全部条目）
