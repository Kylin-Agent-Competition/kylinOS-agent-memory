# 技术债务登记表

> **重要**：本文件记录所有已识别的技术债务、临时实现和架构妥协。
> 技术债不是无限期的——每条记录必须有计划日期和明确的验收标准。

## 表格字段说明

| 字段 | 说明 |
|------|------|
| TD编号 | 格式 `TD-XXX`，按发现顺序递增 |
| 标题 | 简要描述技术债 |
| 模块 | 涉及的代码模块 |
| 类别 | Bug / Blocker / Risk / Technical Debt |
| 严重程度 | Critical / High / Medium / Low |
| 状态 | Open / In Progress / Resolved / Wontfix |
| 责任人 | 负责此条目的轨道成员 |
| Reviewer | 专业审查关注角色（不表示需要累计多份批准） |
| 计划日期 | 计划解决的日期 |
| 验收标准 | 如何判定此条目已解决 |
| 关联PR | 解决此条目的 PR 链接 |

## 技术债务登记表

| TD编号 | 标题 | 模块 | 类别 | 严重程度 | 状态 | 责任人 | Reviewer | 计划日期 | 验收标准 | 关联PR |
|--------|------|------|------|----------|------|--------|----------|----------|----------|--------|
| TD-001 | D1-B PR 修改了 D1-A 证据条目 reviewer 字段 | evidence/index.yaml | Technical Debt | Medium | Open | gaoyizhe934 (B) | jackb | 2026-08-07 | D1-A 条目 ABI-001、EMBED-CALL-001 的 reviewer 字段恢复为原始值，或获得 D 主审书面批准保留变更 | PR #12 |
| TD-002 | evidence/index.yaml Schema 1.0→1.1 迁移缺少独立变更记录 | evidence/index.yaml | Technical Debt | Medium | Open | gaoyizhe934 (B) | jackb | 2026-08-07 | evidence/README.md 中补充：① Schema 差异清单；② 已有条目迁移验证结果；③ 对下游消费者影响评估 | PR #12 |
| TD-003 | 当前 Vector SDK 原始 score 的距离/相似度语义未独立验证 | Vector Provider / evaluation | Risk | Medium | Open | gaoyizhe934 (B) | D；评测影响由 E 关注 | 2026-08-09 | 在固定客户端/服务端/模型组合上，用 identical、orthogonal、opposite 与重复向量完成受控宿主实验；证据绑定被测提交和版本，明确方向、范围、稳定性及允许用途；验证前保持 `sdk_score_unverified` 且不得跨通道比较 | PR #20 |
| TD-004 | Vector Engine 原子索引代次/Collection 切换能力未验证 | Vector Provider / index rebuild | Risk | High | Open | gaoyizhe934 (B) | D | 2026-08-06 | 取得目标麒麟宿主原子切换及故障恢复 E4 证据，或由 D/B 冻结并验证 maintenance-window/routing-switch 等价方案；失败重建不得替换旧 serving generation，恢复路径须可审计 | PR #20 |
| TD-A-005-01 | EmbeddingProvider 主动超时中断未实现（timeout_ms 无实际效果） | memory-service/providers/embedding_provider.py, cpp-bridge | Technical Debt | Medium | Open（部分缓解，审查报告 #4） | A 轨成员 | D 主审 | 2026-08-10 | Day5 已部分缓解：EmbeddingService 层 fut.result(timeout) 提供调用方超时保护（ERR_TIMEOUT 结构化返回，不阻塞聊天线程）；Bridge 内部无真正中断。剩余：实现 Bridge 内部定时器，主动中断 SDK 调用 | PR #17 / PR #25 |
| TD-A-005-02 | embed_batch 并行策略未定（当前顺序调用） | memory-service/providers/embedding_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-10 | Day5 确定并行策略（线程池/进程池），实测并记录延迟对比 | PR #17 |
| TD-A-005-03 | get_dimension() 首次调用用空串触发（有 IPC 副作用） | memory-service/providers/embedding_provider.py | Technical Debt | Low | Resolved | A 轨成员 | D 主审 | 2026-08-10 | ✅ start() 已完成初始化 embed 并写入 _shared_dimension（第 219 行），get_dimension() 正常路径直接返回，不再触发空串 embed（消除 IPC 副作用）；仅"未 start 前防御调用"保留空串 fallback；回归测试 test_td_a_005_03_05.py | PR #38 分支 fix/td-a-005-03-05-dimension-loaded |
| TD-A-005-04 | model_info.name 硬编码默认模型名 | memory-service/providers/embedding_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-10 | 接入 get_model_list 获取真实模型名 | PR #17 |
| TD-A-005-05 | model_info.loaded 临时语义（get_dimension 成功即代表可用） | memory-service/providers/embedding_provider.py | Technical Debt | Low | Resolved | A 轨成员 | D 主审 | 2026-08-10 | ✅ loaded 基于生命周期状态精确化：仅 _lifecycle==READY 时 loaded=True；INITIALIZING/CLOSED 时 loaded=False；回归测试 test_td_a_005_03_05.py | PR #38 分支 fix/td-a-005-03-05-dimension-loaded |
| TD-A-005-06 | EmbeddingProvider 进程级 Singleton 并发初始化缺少类级锁 | memory-service/providers/embedding_provider.py | Technical Debt | Low | Resolved | A 轨成员 | D 主审 | 2026-08-10 | ✅ 已加类级锁 _singleton_lock（threading.Lock），保护 __init__ 单例创建/配置锁定与 start 失败重置为临界区；回归测试 test_td_a_local_batch.py::test_td_005_06_concurrent_init_no_duplicate_bridge | PR #38 分支 fix/td-a-local-batch |
| TD-A-005-07 | Day4 Bridge/Provider 非权威文档与元数据收口（轮次标注、错误模型注释同步） | docs/day3/06_provider_contract_v1.md, docs/day4/08_bridge_provider_skeleton.md, evidence/index.yaml, cpp-bridge/src/py_module.cpp, memory-service/providers/embedding_provider.py, cpp-bridge/tests/test_bridge_failure_recovery.cpp | Technical Debt | Low | Resolved | A 轨成员 | D 主审 | 2026-08-12 | ✅ 轮次标注改为指向最新证据（去除"第七轮"硬编码）；embed() docstring 异常列表补 ERR_FATAL_FAILURE；py_module.cpp / test_bridge_failure_recovery.cpp 错误模型注释核实已为当前正式语义（BridgeFatalError/ERR_FATAL_FAILURE），无需改动 | PR #38 分支 fix/td-a-local-batch |
| TD-A-005-08 | Day4 验证脚本证据文件生命周期优化（.prev 备份不自动清理） | scripts/verify_day4_vm.sh, evidence/l2-kylin-vm | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-12 | 验证脚本可连续执行，无需人工删除上一次运行生成的 .prev 临时备份，同时保持 Step 1 严格工作区门禁（历史备份入 /tmp 或执行前自动清理，或建立统一 evidence archive 机制） | PR #17 |
| TD-A-005-09 | EmbeddingService 启动期 SDK 缺失无降级（server 构造直接抛 RuntimeError） | memory-service/embedding/embedding_service.py, memory-service/embedding/server.py, memory-service/providers/embedding_provider.py | Technical Debt | Medium | Open | A 轨成员 | D 主审；安全/降级影响 E 补审 | 2026-08-14 | ① EmbeddingProvider.__init__ 在 kylin_embedding 缺失时不再直接 raise，改为可注入/可延迟构造（或 EmbeddingUDSServer 增加 provider 注入点）；② 无 SDK 时 UDS server 可启动并返回结构化降级响应（memory.embed → ok+degraded 空向量；memory.health → bridge_loaded=false）；③ 麒麟 VM 补充"so 缺失"端到端证据 | PR #17 / Day5 PR |
| TD-A-D6-EXEC-RACE | server.stop() 与极端 in-flight executor race（stop 后已进入 handler 的并发窗口可能触发 executor 惰性重建） | memory-service/embedding/server.py, memory-service/embedding/embedding_service.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-13 | 当前保障：stop 后拒绝新连接/旧连接不能开始新业务请求/active connection join/常规 lifecycle test 通过（不影响正常 Embedding 与比赛演示主链路）；后续关闭条件：service accepting-work gate + executor lifecycle lock + 真正 concurrent race test | PR #27（Reviewer 第三轮收敛，非阻断） |
| TD-A-D6-TOOL-PARTIAL | Tool partial 高级语义未实现（成功子项提取/失败子项脱敏/side_effect/rollback） | memory-service/providers/extraction_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-13 | 当前保守策略：partial 不形成成功知识（漏记而非错记，fail-safe）；后续关闭条件：支持成功/失败子项结构化拆分 + side-effect/rollback 语义 | PR #27（Reviewer 第三轮收敛，非阻断） |
| TD-A-D6-LLM-TOOL-INPUT | Knowledge LLM 路径输入未绑定具体 success ToolResult.result（当前通过 Gate 后输入仍主要来自 user_text/assistant_text） | memory-service/providers/extraction_provider.py | Technical Debt | Low | Resolved | A 轨成员 | D 主审 | 2026-08-13 | ✅ _run_llm 增加 tool_context 参数：knowledge 路径 LLM 输入 = 具体 success ToolResult.result 拼接（含 [tool:xxx success] 前缀，建立 candidate→ToolResult provenance 基础）；preference 路径不受影响；B1 门控保持（无 success Tool 仍整体拒绝）；回归测试 test_td_a_local_batch.py::test_td_d6_llm_tool_input_*（正向绑定 + 无 Tool 拒绝） | PR #38 分支 fix/td-a-local-batch |
| TD-A-D7-CACHE-USER-DIMENSION | 抽取缓存键缺少 user 维度（当前 key=kind+source_event_id+内容指纹） | memory-service/providers/extraction_provider.py（PreferenceExtractionCache） | Technical Debt | Medium | Open | A 轨成员 | D 主审；安全/用户隔离影响 E 补审 | 2026-08-14 | 当前 Day7 按单用户端侧场景运行；TurnFinalizedEvent（Day3 冻结契约）尚无可信 user_id，缓存键暂时无法安全加入 user dimension；一旦事件契约加入可信 user_id，缓存键必须同步升级为包含 user_id（+ 测试）；多用户场景启用前必须关闭本 TD | PR #36（Reviewer 第四轮 REWORK，MEDIUM-02） |
| TD-A-D7-LLM-HANG-DEGRADE | LLM 永久挂死可能导致整个进程生命周期内 LLM 路径永久 busy-skip（ThreadPoolExecutor max_workers=1，超时后 in-flight 未完成会跳过后续调用） | memory-service/providers/extraction_provider.py | Technical Debt | Medium | Resolved | A 轨成员 | D 主审；安全/降级影响 E 补审 | 2026-08-14 | ✅ 挂死恢复机制：_llm_hang_threshold_ms（默认 60s，远大于单次超时）检测 in-flight 持续超阈值 → _rebuild_executor() 重建线程池释放挂死 worker，恢复 LLM 路径（llm-hang-recovered，_hang_recovered 统计）；未超阈值保持 busy-skip 不误重建；回归测试 test_td_a_local_batch.py::test_td_d7_llm_hang_*（恢复 + 阈值保护） | PR #38 分支 fix/td-a-local-batch |

### TD-A-005-07 / TD-A-005-08 延期说明（第四轮 Review，2026-08-08）

- **TD-A-005-07 产生原因**：Day4 多轮 REWORK 迭代中，文档/注释/元数据未随每轮同步更新，遗留描述性信息（如 Day4 文档顶部“第七轮 L2”、Day3 状态表“麒麟 VM 第七轮 L2”、EMBED-CALL-003 `date: 2026-08-07` 与第八轮运行时间 2026-08-08 不一致、py_module.cpp 注释仍写 `ERR_SESSION_* → BridgeSessionError`、embed() docstring 异常列表缺 ERR_FATAL_FAILURE、test_bridge_failure_recovery.cpp 注释把 init_session 首次失败写为 ERR_FATAL_FAILURE）。
  **当前影响**：仅影响描述性信息，不改变 Bridge 实际返回码、Provider 实际映射、生命周期控制、Runtime 执行结果、tested_commit、evidence_commit、checksum 或权威证据文件。
  **允许延期理由**：不影响运行安全、错误契约或测试可信度；待合并后统一清理，避免为纯文档改动反复触发 L2 重验。
- **TD-A-005-08 产生原因**：verify_day4_vm.sh 每次运行把上一版证据日志备份为 `day4_verify_latest.log.prev`，而 Step 1 严格工作区排除规则未覆盖 `.prev`，重复运行前可能需要人工清理。
  **当前影响**：仅影响连续运行的便利性；第八轮 L2 证据（HEAD 匹配 / status 空 / worktree clean / index clean / CTest 6/6 / pytest 52 / Smoke 11 / 生命周期 4 路径 / FAILURES=0）已生成且真实有效。
  **允许延期理由**：属测试基础设施维护，不影响已生成证据真实性。
- **TD-A-005-09 产生原因**：Day5 垂直链路审查（2026-08-09）实测复现——无 SDK 环境（WSL 模拟）下 `EmbeddingUDSServer()` 构造即抛 `RuntimeError`：`EmbeddingProvider.__init__` 在 `kylin_embedding` 模块缺失时直接 `raise RuntimeError(_IMPORT_ERROR)`，且 `server.py` 硬编码 `EmbeddingService()`（无 provider 注入点）。因此降级语义（`memory.embed` → 空向量+degraded）只覆盖"Provider 已构造成功、运行期调用失败"场景，不覆盖"启动期 SDK 缺失"场景——后者 UDS server 直接崩溃，客户端只能走连接失败降级（架构 13.1"聊天继续"仍成立，但服务端无结构化降级响应）。`test_embedding_service_real.py::test_degraded_when_so_missing` 自述用 FailProvider 注入、未模拟真实 so 缺失。
  **当前影响**：仅影响 SDK 缺失/损坏时的服务端降级能力；Day5 麒麟 VM 正常路径验证全绿（真实 SDK 8/8 无 Skip + 端到端 UDS bridge_loaded=true / embed dim=768），无假实现、无固定样例。
  **允许延期理由**：属健壮性增强而非核心链路缺陷；麒麟宿主正常安装路径 SDK 存在，未阻断 Day5 垂直链路验证与合并；修复涉及 Provider 构造/注入点重构，计划在 Day6+ 统一处理。
| TD-007 | 真实 Tool Result Hook 路径未通过源码 instrument 验证 | os-agent-integration / kylin-ai-runtime | Technical Debt | High | Open | C | D 主审；E 安全关注 | D3 阶段 | 源码 instrument 输出结构化 ToolExecutionEvent（trace_id、tool_name、arguments、status、result、error、started_at、finished_at），覆盖成功、失败、取消三类 | PR #19 |
| TD-008 | Hook 点 A 的 Memory Context 注入实现状态未确认 | os-agent-integration / PreChat | Risk | High | Open | C | D 主审；E 安全关注 | D3 阶段 | 通过源码 instrument、D-Bus 解码或真实 chatAsync 入参捕获确认 Hook 点 A 是否实现 memory_context 注入；strace 外部观察只能得出 NOT_OBSERVED | PR #19 |
| TD-009 | 非 OpenAI 风格 Tool 执行路径尚未获得结构化事件证据 | os-agent-integration / kylin-ai-runtime | Technical Debt | High | Open | C | D 主审；E 安全关注 | D3 阶段 | 源码 instrument 确认实际 Tool 执行路径并输出结构化事件；OS Agent 设计并验证替代 Hook 方案 | PR #19 |

## 管理规则

1. **Critical 严重程度的技术债不得带病合并。** 必须在合并前解决或降级为 High。
2. 所有 `TODO`、`FIXME`、`HACK` 注释必须引用有效的 TD 编号。
3. `代码合并` 不等于 `技术债关闭`。关闭需要对应 PR 的 Reviewer 确认验收标准达成。
4. Bug、Blocker、Risk 和技术债必须严格区分：
   - **Bug**：不符合规格的缺陷
   - **Blocker**：阻断下一个 Gate 的障碍
   - **Risk**：已知但未发生的潜在问题
   - **Technical Debt**：有意的临时实现或设计妥协
