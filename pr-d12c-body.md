# fix(C): align C-track fields with KMA canonical v1 CANDIDATE (Adapter Window)

**轨道 (Track)**：C 轨（memory-client ViewModel + os-agent-integration 契约层 + 双端 L0/L1 测试）
**Head**：`60aa788`（on branch `fix/c-d12-schema-drift-canonical-adapter`，rebased on latest main `d5e3b0f`）
**Base**：`main@d5e3b0f`

> **治理口径**：本 PR 是对 `docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md`（当前状态 **CANDIDATE\_FOR\_FREEZE**，§0 / §R-1 handoff / §结尾明确）的 Candidate **Adapter Window** 对齐。本文任何地方不宣称 Canonical v1 已进入 `FROZEN` 团队级权威基线；transport 层不单方面停止 ADR-010/TD-039 的 `collected_at` 名称（按 R-1 handoff 登记 **TD-060 由 C/D 书面冻结后才允许删除 legacy alias**）。

***

## 背景（Why — Candidate Adapter Window 动机）

E 轨在 D12E 审计与 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` 中提出了 6 条统一业务字段命名**候选**（R-1..R-6）。该文档当前为 **CANDIDATE\_FOR\_FREEZE**，需经非作者 D Reviewer 批准 + PR 合并 + 后续治理升级后才是团队级冻结基线（§0 / §end 声明）。其 R-1 handoff + §责任分工表明确：

- Transport 层 legacy `collected_at` 现状保留；

- Adapter/Mapping 或更名方案必须经 **C/D 书面冻结 TD-060** 后才允许改 transport；

- 未完成前，不得以 Candidate 文档身份覆盖 D3 / IPC 已有团队级契约。

因此本 PR 不把 transport 出站直接从 collected\_at 改到 captured\_at，而是走 **Candidate Adapter Window 双写**：payload 同时携带 **Canonical 候选名**（对齐 R-1/R-3/R-5/R-6 提案语义）+ **transport/host DTO 既有短名**，如此：

- ADR-010 IPC consumer、Host DTO handlers、D3 contract reader 继续读 legacy 字段，零改动；

- 下游 E 轨 Canonical Adapter 可在 production fail-closed 模式下消费 Canonical 候选名；

- 等 D Reviewer 对 Candidate → FROZEN 升级 + C/D 书面冻结 TD-060 冻结完毕后，在独立 follow-on PR 删除 legacy alias 即可。

本 PR 在 4 个行为域做了 Candidate Adapter Window 对齐（R-1 时间、KMA R-5 + DRIFT-007/008/009 ManualConfig、DRIFT-002/003 Tool 业务结果、DRIFT-004/011 Behavior 拆分）：

| Drift ID         | Legacy（Host / IPC 既有）                     | Canonical Candidate（E KMA v1 候选）                                                  | Adapter Window 做法                                                                            |
| ---------------- | ----------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| KMA R-1 / TD-060 | `metadata.collected_at`（ADR-010 / TD-039） | `metadata.captured_at`（业务入库事件捕获时间）                                                | **双名出站**（不切换 transport）                                                                      |
| KMA R-5          | `sensitivity_level`                       | `sensitivity`                                                                     | **双写**，归一 lowercase                                                                          |
| DRIFT-007        | `scope`（混用"配置种类+偏好作用域"）                   | `config_kind` + `preference_scope`（R-3 五值 global/topic/tool/session/time\_window） | **双写**：scope+config\_kind；当 config\_kind==preference 加 preference\_scope                     |
| DRIFT-008 / 009  | `key` / `value` / `confidence`            | `preference_key` / `preference_value` / `confidence_score`                        | **双写**                                                                                       |
| DRIFT-002 / 003  | Host DTO `execution_status=failure`       | Canonical `source_business_status=failed`                                         | Tool event 同时携带 execution\_status + 归一后的 source\_business\_status                            |
| DRIFT-011        | 单字段 `actor`（角色标签）                         | `actor_role` + `actor_id`（可信实体 ID，Demo 缺则显式 PENDING\_HOST\_IDENTITY）              | behavior 同时携带 actor（legacy）+ actor\_role / actor\_id                                         |
| DRIFT-004        | 隐式 source\_type 推断                        | `source_type_projected` + `mapping_status=PENDING_C_CONFIRMATION`                 | 已知 chat 类写 "chat"；user\_action 写 PENDING\_E\_DECISION\_D021\_user\_action；都附 mapping\_status |

***

## 改动（What）

### 契约层 `os-agent-integration/contracts/`（2 files）

- **`memory_event_contract_v1.{h,cpp}`** **— INPUT 接受双名；Canonical wins**

  - `readCanonicalCapturedAt()`：INPUT 同时接受 `captured_at`（Canonical，优先级高）与 `collected_at`（legacy transport alias）；当两者都提供且 Canonical 存在时，忽略 legacy 值。

  - `firstMissingRequiredEventMetadataField()`：required 检查接受 `captured_at ∨ collected_at` 任一；错误字段名统一报 Canonical 的 `captured_at`（让下游 error handler 不依赖 transport alias 名）。

  - **（MEDIUM-01 修复）** `firstInvalidEventMetadataJsonType()`：改到与 "canonical wins" 完全对称：

    - both present → **只 type-check Canonical captured\_at**（malformed legacy alias 不再能反向污染 Canonical ingest 结果）；

    - legacy only present → type-check collected\_at，但错误**仍报 Canonical captured\_at 字段名**；

    - neither → 跳过，交给 required check 单独报错。

  - `toolExecutionStatusFromString()`：Host DTO `failure` + Canonical `failed` 都映射到同一个 Failure 枚举。

### Candidate packaged examples（2 files — MEDIUM-02 修复）

本 PR 的目标就是消除这些字段漂移，因此 candidate schema 示例必须同步。**legacy + canonical 双写**如下（core 3 个 packaged 在 HIGH-02 前次已同步）：

- `contracts/examples/manual_config_event.v1.json`：

  - `metadata.collected_at` → 保留；新增 `metadata.captured_at`；

  - `config`：保留 `scope/key/value/confidence/sensitivity_level`；
    新增 `config_kind/preference_scope/preference_key/preference_value/confidence_score/sensitivity`；
    双名并存，与 HIGH-01 修复后的 ViewModel 输出 + D6c mock both-side 断言严格一致。

- `contracts/examples/behavior_event.v1.json`：

  - `metadata.captured_at` + legacy `collected_at`；

  - `behavior`：保留 `actor`；新增 `actor_role=user / actor_id=PENDING_HOST_IDENTITY / source_type_projected=chat`（对应当 behavior\_kind==user\_message）。

### ViewModel 层 `memory-client/src/view_models/memory_view_model.cpp`（1 file）

- **（GOVERNANCE-01 策略 A 修复）R-1 OUTPUT 回退到 Adapter Window 双名**：

  - `buildTurnFinalizedEventJson()` / `buildEventMetadata()`：**同时写** **`collected_at`** **+** **`captured_at`**，并在注释里注明："仅 Candidate Adapter Window；等 TD-060 C/D 书面冻结 + KMA 文档升 FROZEN 才删 legacy"。

  - 原错误：只写 `captured_at` 并宣称 transport 已切换 → 违反 §R-1 handoff。

- **R-1**：其余 metadata 字段照旧；Canonical `captured_at` 保持输出（Candidate 消费）。

- **DRIFT-002 / 003**：Tool execution event 继续输出 Canonical `source_business_status`（failure→failed 归一）+ Host DTO `execution_status` 双名。

- **R-5 / DRIFT-007/008/009**：Manual config 继续 scope/config\_kind+preference\_scope / key/preference\_key / value/preference\_value / confidence/confidence\_score / sensitivity\_level/sensitivity 双写。

- **（MEDIUM-03 修复）DRIFT-011 / DRIFT-004**：Behavior 保留 legacy `actor` + 新增 `actor_role` + `actor_id`(PENDING\_HOST\_IDENTITY) + `source_type_projected` + `mapping_status` 三写（legacy 兼容 + canonical 候选 + pending marker）。`runBehaviorPipeline()` 中 `behavior.insert("actor", actor)` 已恢复，与 `behavior_event.v1.json` candidate example 严格一致。

### 测试更新（3 files）

1. **`os-agent-integration/tests/test_memory_event_contract_v1.cpp`**

   - **（HIGH-03 编译错误修复）** `capturedAtCanonicalWinsOverBadLegacyAliasType()`：

     - `ctxParsed.ok` → `ctxParsed.ok()`（×3，ParseResult<T>::ok 是 const 成员函数，非静态成员）；

     - 原 `toJson(ctxParsed.value->metadata)`（无该公开重载）改为：对完整 `MemoryContext` 调 `toJson(*ctxParsed.value)`。

   - **（HIGH-04 round-trip flat JSON 修复）** 同一个测试中：

     - `toJson(MemoryContext)` 返回的是 **flat JSON**（`captured_at` 在顶层，不在 `metadata` 嵌套对象内）；

     - 修正：直接从 `ctxRoundTrip.value("captured_at")` 读取，而非 `ctxRoundTrip["metadata"]["captured_at"]`；

     - Tool/Turn 正路径只断言 `.ok()`，避免堆叠新 API。

   - `eventMetadataWrongJsonTypesAreRejected_data()`：新增行 "legacy\_collected\_at\_only\_invalid\_type"，错误字段要求为 canonical `captured_at`。

   - HIGH-02 行：`TurnFinalizedEvent.captured_at` 仍然验证 Canonical wrong-type 为 invalid\_type。

2. **`memory-client/tests/test_d5_vertical_link_demo.cpp`**

   - turn.finalized ingress 必填：继续 `captured_at ∨ collected_at`（Adapter Window 双通道接受）；

   - `previewAndSendReuseSameEventIdTimestamp()` 比较 `captured_at`（Canonical）即可（因为 Demo 客户端对象构造函数实际是同一个 now 值写入两个字段）。

3. **`memory-client/tests/test_d6c_multi_source_adapters.cpp`（HIGH-01 D6c mock 从 either/or 收紧为 both-side contract）**

   - 之前 either/or 会漏 "ViewModel 只写 Canonical 没写 legacy" 的回归（正是 HIGH-01 的 bug）。

   - 现在要求：

     - `cfg.scope && cfg.config_kind`（scope 无论是否 preference，都必须有 config\_kind）；

     - 当 `config_kind == preference` 时必须有 `cfg.preference_scope`；

     - `cfg.key && cfg.preference_key`、`cfg.value && cfg.preference_value`、
       `cfg.sensitivity_level && cfg.sensitivity`。

***

## 用户与开发者影响（Impact）

- **Host / IPC Transport（C→B/A，既有 DTO）零破坏**：scope/key/value/sensitivity\_level/confidence/actor/collected\_at/execution\_status 全部保留为 legacy 短名出槽；ADR-010/handlers.py 不用改。

- **Canonical 通道（C→E 业务，Candidate Adapter Window）**：captured\_at / source\_business\_status / config\_kind / preference\_scope / preference\_key / preference\_value / confidence\_score / sensitivity / actor\_role / actor\_id / source\_type\_projected / mapping\_status 全部携带；下游 E Canonical Adapter 可以 Candidate 身份消费（生产 fail-closed；若检测到仍为 Candidate 但字段有冲突就 block）。

- **Fail-closed / Pending Marker（仍保持）**：

  - `actor_id = PENDING_HOST_IDENTITY`：仍要求可信宿主注入；

  - `source_type_projected = PENDING_E_DECISION_D021_user_action`：user\_action 的 MemorySourceEvent.source\_type 仍等 E 裁决；

  - `mapping_status = PENDING_C_CONFIRMATION`：C 轨 SourceType 未冻结；

  - **新增 Blocker 条目 TD-060**：CANDIDATE Adapter Window 保留 `collected_at`；只有在 **C/D 书面冻结 TD-060（transport adapter/mapping 或更名方案）+ KMA 文档升级到 FROZEN** 之后，**在独立 follow-on PR 删除** **`metadata.collected_at`** **legacy alias**，不得在本 PR 删除。

***

## 验证（Validation）

| 检查项                                                     | 结果                        | 证据/备注                                                                                                                                                                            |
| ------------------------------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `git diff --check origin/main...HEAD`                   | ✅ Clean                   | 只剩 workflow EOF 末尾空行 warning（合法 YAML newline at EOF 需求）                                                                                                                          |
| Diff stat                                               | ✅ 真实                      | 累计 14 files changed, 527 insertions(+), 39 deletions(-)（含 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` TD-060 关联 PR 回写）                                                      |
| Rebased on latest main                                  | ✅ Behind 0                | main `d5e3b0f`（fetch + rebase 完）                                                                                                                                                 |
| **CI — Repository Baseline Check**                      | ✅ PASS                    | `.github/workflows/baseline-check.yml`                                                                                                                                           |
| **CI — Memory Client L0 ctest**                         | ✅ PASS                    | memory-client build + ctest + QML smoke build 全 PASS                                                                                                                             |
| **CI — os-agent-integration standalone contract ctest** | ✅ PASS                    | Job `contract-ctest` 3 steps 全 PASS：configure + build `test_memory_event_contract_v1` + ctest `--output-on-failure`。HIGH-04 flat JSON round-trip 修复后 ctest PASS。                 |
| **standalone os-agent-integration ctest（Linux 复现命令）**   | ⚠️ Windows 宿主机无 cmake/Qt5 | `cmake -S os-agent-integration -B build-ct -DBUILD_TESTING=ON && cmake --build build-ct --target test_memory_event_contract_v1 && ctest --test-dir build-ct --output-on-failure` |

> ⚠️ Windows 本机无 cmake/Qt6/Qt5，无法本地编译 contract target；本 PR 把 os-agent-integration standalone ctest **纳入同一个 CI workflow** 直接提供绿灯证据链，若 runner 侧 Qt 依赖有问题请在 CI 失败后启动 `gh-fix-ci` 流程。

***

## Blocker Pending（待 Close / 待后续治理）

1. **CI 绿灯** ✅ — `memory-client-ctest.yml` 3 job 全 PASS：Baseline + memory-client L0 + standalone os-agent-integration contract ctest。GitHub Actions 四项检查均为 SUCCESS。
2. **TD-060（C/D 书面冻结 R-1 transport Adapter/Mapping 或更名方案）**——本 PR 仅做 Candidate Adapter Window 双写；在 KMA\_UNIFIED\_DATA\_FORMAT\_FREEZE\_V1 升级为 `FROZEN` + TD-060 被书面冻结**之前**，**不得**删除 `metadata.collected_at` legacy alias；相应 follow-on："删除 legacy alias"的 PR 必须引用本条目。

   - **正式登记位置**：`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` line 136（TD-060，状态 Open，D 主审，计划日期 2026-09-10）。**本 PR diff 已包含该文件回写**：在 TD-060 关联 PR 列追加 "PR #140（C 轨 Adapter Window 双写，依赖 TD-060 冻结后才可删除 legacy alias）"。
3. **E 轨 D021 user\_action 最终 SourceType**：`PENDING_E_DECISION_D021_user_action`（仍占位）。
4. **可信** **`actor_id`** **注入来源**：Canonical Adapter 生产环境必须显式注入可信 host identity（或 fail-closed）。Demo 长期不得保留 `PENDING_HOST_IDENTITY`。

***

## Related / Cross-track References

- E 轨治理（Candidate）：`docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md`

  - **状态：CANDIDATE\_FOR\_FREEZE**（R-1..R-6 候选裁定；§0 + §end 升级门槛；§R-1 handoff：transport collected\_at 现状保留 + TD-060 由 C/D 书面冻结）。

- D 轨 IPC / SQLite / Outbox / 成品化：`TD-060` 为 C/D 冻结 handoff，未在本 PR 提供书面冻结证据。

- E 轨生命周期漂移移交：`docs/day12/14_d12e_knowledge_td017_closure_audit_20260903.md`。

