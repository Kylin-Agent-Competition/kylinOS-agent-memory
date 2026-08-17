# 10 轨道 C — OS Agent 宿主事件契约开工门禁

> **当前结论：`READY_FOR_CANDIDATE_WORK / BLOCKED_FOR_FINAL_FREEZE`**
> worktree 已 fast-forward 到最新 main，且用户已确认公共测试 seams；本文允许 D3-C 编制可审查的 C++/JSON 候选契约和 Qt 契约测试，
> 但不允许在 C/D/E 证据与审批缺口关闭前标记为最终 `FROZEN`、
> `ACCEPTED`、`HOST_VERIFIED` 或 Gate PASS。

- 日期：2026-08-14
- 任务：D3-C「路径选择与共享契约冻结」
- 临时负责人：高翌哲（仅临时接手 D3-C，不改变 B 轨长期责任）
- 目标基线：`origin/main` @ `d37fb95eca9083eb480491cda2464ebe8515477d`（含 PR #19 D2-C squash 合并）
- 开工时 worktree HEAD：`d37fb95eca9083eb480491cda2464ebe8515477d`（已与 `origin/main` 同步）
- 工作分支：`feat/C-d3-host-contract-v1`
- Reviewer：D 主审；用户交互与安全影响由 E 补审

## 1. 本任务的唯一范围

依据 15 天 75 项施工台账，D3-C 只交付：

1. `MemoryQuery`、`MemoryContext`、`TurnFinalizedEvent`、
   `ToolExecutionEvent` 的 C++/JSON v1 候选契约；
2. 示例 Payload；
3. 主 Hook 路径、批准的备用路径以及无法批准时的明确阻断结论；
4. 面向公共接口的 Qt 契约测试样例。

本文不实现生产 Hook，不补做 D2-C 宿主实验，不修改 B 轨 Vector、FTS5、RRF、
检索或索引内容，也不替 D/E 冻结 IPC、业务 Schema 或安全规则。

## 2. 证据状态词

| 状态 | 本文含义 |
|---|---|
| `HOST_VERIFIED / E4` | 已在目标银河麒麟宿主执行并有可复核证据 |
| `SOURCE_VERIFIED / E2` | 仅由已合并源码或文档静态确认 |
| `PARTIAL` | 仅部分路径或语义有证据，不能外推全部能力 |
| `UNVERIFIED` / `UNTESTED` | 尚无足够验证，或测试尚未执行 |
| `C_D2_EVIDENCE_MISSING` | D2 预审明确指出 C 侧真实宿主证据缺位 |
| `PENDING_C/D/E_CONFIRMATION` | 对应轨道仍需取证、决策或审批 |
| `BLOCKED` | 当前前置条件不足，不得宣称冻结或通过 |
| `FROZEN_CANDIDATE` | D3-C 给出唯一候选语义，等待证据与独立 Reviewer 接受 |

冻结候选是接口稳定性提案，不表示功能已经实现，也不表示 Runtime Test 通过。

## 3. 基线与分支审计

| 检查 | 结果 | 状态 | 对 D3-C 的影响 |
|---|---|---|---|
| GitHub `main` HEAD | `d37fb95`，PR #19 已 squash 合并 | `SOURCE_VERIFIED` | D3-C 已采用该共同基线 |
| 开工时 worktree HEAD | `d37fb95`，与 `origin/main` 一致 | `PASS_LOCAL` | 已经用户授权以 fast-forward 同步，无 merge commit |
| 原工作区 | `docs/C-d2-osagent-runtime`，含未跟踪 `.scratch/` | `SOURCE_VERIFIED` | 不在该分支修改；已用独立 worktree 隔离 |
| D2-C 合并状态 | PR #19 已以 `d37fb95` squash 合并；来源提交不成为 main 祖先是 squash 的正常结果 | `SOURCE_VERIFIED` | 只采用 `d37fb95` 中的合并内容，不采用来源分支作为基线 |
| D3-C 远端分支/提交 | 未找到 | `NOT_FOUND` | 本批次须建立独立分支和后续独立 PR |
| 四对象 C++ 定义 | main 的 `.h/.hpp/.cpp` 中未找到 | `NOT_FOUND` | D3-C 需要新增公共契约 |
| 四对象 Qt 契约测试 | main 的测试文件中未找到 | `NOT_FOUND` | D3-C 需要新增测试 seam 与构建入口 |
| Qt 构建现状 | Echo CMake 仅注释可选 Qt Network；无 QtTest 入口 | `SOURCE_VERIFIED` | 新测试须显式探测 Qt Core/Test，不得假装本地环境具备 Qt |

## 4. 输入来源审计

| 输入 | 当前事实 | 状态 | 可采用范围 |
|---|---|---|---|
| 15 天 75 项施工台账 | 外部正式 XLSX 已读取，D3-C 定义与本文 §1 一致；实体未导入仓库 | `SOURCE_VERIFIED / OUT_OF_REPO` | 采用任务范围和交付定义；保留基线未导入阻断 |
| SOP v1.1 | 外部正式 DOCX 已读取；仓库 `docs/baseline/README.md` 仍标 01–06 待人工导入 | `SOURCE_VERIFIED / OUT_OF_REPO` | 可对照字段示例，不能声称仓库内权威基线已闭合 |
| D1 OS Agent Hook 任务卡 | 普通聊天、唯一 `is_end=true` 与 RECORD 落库已有 E4；Context 注入未测，Tool 仅 PARTIAL | 混合，见 §6 | 采用已明确的调用边界和红线，不外推未验证事件结构 |
| D2 事件契约冻结前检查表 | 明确是 D3 输入而非冻结协议，三派生对象字段为候选 | `SOURCE_VERIFIED / UNTESTED` | 用作字段候选和未决项索引 |
| D2 E Gate 0 预审 | 最终结论 `BLOCKED`；该文档早于 PR #19，仍写 `C_D2_EVIDENCE_MISSING` | `SOURCE_VERIFIED / STALE_C_STATUS` | 保留 Gate 阻断，不再用旧表述覆盖已合并的部分证据 |
| PR #19 D2-C 合并交付 | `evidence/index.yaml` 正式条目为 `BLOCKED`、`review_status: BLOCKED`、`merge_qualified: false`、`E2` | `SOURCE_VERIFIED` | 证明 D2-C 已合并，但不证明 D2-C Gate 或三对象通过 |
| D2-C PostTurn | 有 `is_end=true` 诊断观察；正式索引/README 仍因完整证据与复核缺口标 `BLOCKED` | `PARTIAL / DIAGNOSTIC` | 可加强最终回调候选位置；不能标事件契约 `HOST_VERIFIED` |
| D2-C PreChat | UI/RECORD 有部分验证；H2C-PreChat-3 书面豁免不是技术 PASS，真实请求前注入仍不能证明 | `PARTIAL / WAIVED_NON_PASS` | Hook A 注入状态保持 `NOT_OBSERVED`，关联 TD-008 |
| D2-C Tool | 真实前台入口有诊断覆盖，但未捕获结构化 success/failure/cancelled Tool 事件 | `NOT_VERIFIED` | 关联 TD-007/TD-009，Tool Hook 不能冻结 |
| D3 业务契约 v1 | 只冻结 E 可单方面冻结的业务语义；C 宿主结构仍 `PENDING_C_CONFIRMATION` | `CANDIDATE_FOR_FREEZE` | 采用业务红线，不把它当 C++ 结构唯一依据 |
| D3 安全验收契约 v1 | 38 条安全规则为候选；真实 C/D 宿主能力仍未验证 | `CANDIDATE_FOR_FREEZE` | 采用原文隔离、敏感引用、LLM/Tool 信任红线 |
| D UDS Echo Spike | 长度前缀、`protocol_version`、request/trace 回显有受限 E4 | `HOST_VERIFIED / SPIKE_ONLY` | 只能引用 Spike 事实；C 不冻结生产 IPC |

## 5. 四对象冻结门禁矩阵

| 对象 | 已确认输入 | 主要未决项 | 当前可做 | 最终冻结状态 |
|---|---|---|---|---|
| `MemoryQuery` | SOP 示例给出 `user_id`、`session_id`、`query_text`、`scene`、`max_context_tokens`、deadline 语义；D1 给出 Pre-Chat 构造位置 | deadline 属 C++ 调用预算还是 D IPC envelope；真实宿主用户/会话映射；版本字段所有权 | 定义不泄漏 D 私有 IPC 的 C++ 值对象和 JSON 候选，冲突项显式 `PENDING_D_CONFIRMATION` | `BLOCKED` |
| `MemoryContext` | D2 候选九字段、E 业务红线及 PR #19 的 PreChat 部分观察已合并 | 真实请求前注入仍未技术证明；载荷形状、正文/安全摘要承载、跨 Turn 复用和 `injection_status` 枚举 | 定义候选元数据、验证规则与安全引用；不虚构官方 `memory_context` 字段 | `BLOCKED / PARTIAL / TD-008` |
| `ToolExecutionEvent` | D2/E 候选规则和 PR #19 的真实前台诊断覆盖已合并 | 未捕获结构化 success/failure/cancelled 事件；实际 intentionrecognition 路径与字段映射待 instrument | 定义候选对象与 fail-safe 解析；模型自述或界面结果不得成为结构化 Tool 证据 | `BLOCKED / NOT_VERIFIED / TD-007/009` |
| `TurnFinalizedEvent` | 普通文本最终回调边界已有历史 E4；PR #19 合并了诊断性 `is_end=true` 观察 | 正式索引仍 `BLOCKED/E2`；完整 Gate 证据、Stop/Retry/续轮和实际事件字段未闭合 | 定义候选对象与关联约束；不声称宿主已发布该事件 | `BLOCKED / PARTIAL` |

### 5.1 公共字段边界

- `user_id`、`session_id`、`turn_id`、`occurred_at`、`tool_call_id` 等归属、时间和
  证据字段必须来自宿主或可信外部输入，禁止模型生成。
- `event_id` 不能替代 `idempotency_key`；ID 生成和 IPC 幂等属于 D 轨待确认项。
- `arguments_ref`、`result_ref`、`error_message_safe` 只允许脱敏引用；不得在示例、
  日志或普通错误中放入真实敏感正文。
- 未知主版本必须拒绝；同一主版本新增未知可选响应字段可忽略。具体规则待 C/D
  Reviewer 对齐后进入 v1 候选。

## 6. Hook 路径证据门禁

| 路径 | D1 证据 | D3-C 当前结论 |
|---|---|---|
| 普通聊天主链 | 发送、流式回调、唯一 `is_end=true`、RECORD 落库为 `HOST_VERIFIED / E4` | 可作为 Pre/Post Hook 语义位置依据，但不证明 Memory 事件已实现 |
| Pre-Chat | D1 候选位置为 `SystemChat::sendMessageImpl` 中最终 `chatAsync` 前；PR #19 发现真实智能体请求经 `~/.kylinbot/gateway.sock`，注入状态 `NOT_OBSERVED` | 保留语义主路径候选；真实接入点和注入字段必须通过受支持审计或源码 instrument，关联 TD-008 |
| Post-Turn | 最终 `is_end=true` 边界的普通聊天行为已有历史 E4；PR #19 又合并诊断观察，但正式 D2-C 条目仍 `BLOCKED/E2` | 语义主路径可形成 `FROZEN_CANDIDATE`；实际事件、Stop/Retry 和完整 Gate 证据仍阻塞 |
| Tool Result | PR #19 发现非 OpenAI `tool_call` 的 intentionrecognition 线索，但没有结构化事件证据 | `sendToolMessage` 旧候选不能直接冻结；实际路径需 instrument，关联 TD-007/009 |
| 备用路径 | main 中没有 D/E 已批准的 C 轨替代 Hook 决议 | 标记 `PENDING_APPROVAL`，不得自行把 LD_PRELOAD、旁路日志或 Prompt Skill 写成批准方案 |

### 6.1 禁止路径

- 原地改写随后进入 UI 或 `RECORD.message` 的用户原文。
- 在 QML/UI 线程执行检索、向量化、冲突计算或其他阻塞工作。
- 用 Prompt/文本 Skill、模型回复、自制日志或关键词命中冒充真实 Tool 结果。
- 依赖 `RECORD.ID` 作为可靠递增标识。
- 由 C 轨单方面冻结 D 的长度前缀、错误码、KYSEC、部署或幂等实现。

## 7. 未关闭阻断项

| ID | 阻断 | 责任 | 本任务处置 |
|---|---|---|---|
| D2-C 合并后 Gate | 已有部分/诊断证据，但正式索引仍 `BLOCKED/E2`，三对象均未完整闭合 | C/D/E | 采用合并后的分项状态；本轮不扩张去补做 D2-C |
| `TD-007` | 真实 Tool Result Hook 未经源码 instrument 验证 | C | 保持 Open；D3-C 只登记候选 seam |
| `TD-008` | Hook A Memory Context 注入实现状态未确认 | C | 保持 Open；不得把 `NOT_OBSERVED` 写成 `NOT_IMPLEMENTED` |
| `TD-009` | 非 OpenAI Tool 路径无结构化事件证据 | C | 保持 Open；备用 Hook 必须待批准与验证 |
| `HD-D2E-B05` | 基线 01–06 实体仍未导入 `docs/baseline/` | 团队/E | 外部原件只作 SOURCE 对照，不能关闭仓库基线门禁 |
| `HD-D2E-B06` | G0-E-01..14 真实宿主案例未执行 | C/D/E | 转为 L2 待验证清单，不虚标 PASS |
| `HD-D2E-B01/B02/B03` | 真实 Kaiming Hook、KYSEC、完整回退未闭合 | D/环境 | 仅登记依赖，不在 C 轨实现 |
| `HD-D2E-05` | `cancelled`/`partial` 是否进入正式 Tool 枚举 | E/B/D | C 候选解析可 fail-safe 接受，冻结状态保持待审 |
| `HD-D2E-06` | `MemoryContext` 跨 Turn 复用与版本升级 | C/D | v1 候选默认不承诺跨 Turn 复用，待决议 |
| 安全凭据风险 | 历史 `evidence/gate0` 疑似硬编码凭据 | 安全渠道 | 不读取、不复制、不输出；不在普通 PR 中处置 |

## 8. 允许继续的工作与停止条件

### 8.1 当前允许

- 编写四对象 `FROZEN_CANDIDATE` 文档；
- 经用户确认公共 seam 后，以 TDD 编写 Qt/C++ 值对象和 JSON 转换测试；
- 使用脱敏、人工审定的固定 JSON 示例；
- 编写 Hook 决策文档，将未批准路径标记为 `PENDING_APPROVAL`；
- 运行本地 L0/L1 构建测试，并如实登记 Qt/麒麟环境限制。

### 8.2 必须停止并报告

- 需要补做 D2-C 宿主取证、读取未合并分支作为实现依据或修改真实 AI 助手源码；
- 需要替 D/E/B 决定其专属字段、协议、安全或检索语义；
- 需要将任何 `UNVERIFIED`/`PARTIAL`/`BLOCKED` 状态升级为 PASS；
- 需要 commit、push、创建 PR 或 merge，但尚未取得对应独立授权。

## 9. Gate 结论

| Gate | 条件 | 当前状态 |
|---|---|---|
| G0 范围与基线 | D3-C 单一范围；隔离分支；worktree fast-forward 到 `d37fb95` | `PASS_LOCAL` |
| G1 输入可追溯 | D1/D2/D3、PR #19 合并证据与外部正式基线已建立来源矩阵 | `PASS_LOCAL_WITH_STATE_DRIFT` |
| G2 公共测试 seam | 用户确认 C++ 值对象、JSON、枚举/错误三个 seam | `PASS_LOCAL` |
| G3 候选实现 | 四对象、示例和 Qt 契约测试通过 | `PASS_LOCAL / REVIEW_REMEDIATION` |
| G4 C 宿主取证 | PR #19 已合并部分/诊断证据；正式 D2-C 条目仍 `BLOCKED/E2` | `BLOCKED / OUT_OF_SCOPE` |
| G5 跨轨与人工审查 | D 主审，E 覆盖用户交互/安全；未决枚举/IPC 仍待责任轨决议 | `PENDING_REVIEW` |

**当前总体结论：工作树基线与公共测试 seams 均已确认，可以继续候选契约的
本地 TDD 工作；最终冻结仍被 G4/G5 及跨轨依赖阻断。**
