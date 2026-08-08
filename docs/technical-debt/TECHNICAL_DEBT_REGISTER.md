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
| TD-A-005-01 | EmbeddingProvider 主动超时中断未实现（timeout_ms 无实际效果） | memory-service/providers/embedding_provider.py, cpp-bridge | Technical Debt | Medium | Open | A 轨成员 | D 主审 | 2026-08-10 | Day5 实现 Bridge 内部定时器：timeout_ms=0 语义明确；deadline 到期返回 ERR_TIMEOUT；主动中断 SDK 调用 | PR #17 |
| TD-A-005-02 | embed_batch 并行策略未定（当前顺序调用） | memory-service/providers/embedding_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-10 | Day5 确定并行策略（线程池/进程池），实测并记录延迟对比 | PR #17 |
| TD-A-005-03 | get_dimension() 首次调用用空串触发（有 IPC 副作用） | memory-service/providers/embedding_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-10 | 改用 SDK 元信息接口无副作用获取维度 | PR #17 |
| TD-A-005-04 | model_info.name 硬编码默认模型名 | memory-service/providers/embedding_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-10 | 接入 get_model_list 获取真实模型名 | PR #17 |
| TD-A-005-05 | model_info.loaded 临时语义（get_dimension 成功即代表可用） | memory-service/providers/embedding_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-10 | 精确化 loaded 状态（会话初始化 + 模型就绪） | PR #17 |
| TD-A-005-06 | EmbeddingProvider 进程级 Singleton 并发初始化缺少类级锁 | memory-service/providers/embedding_provider.py | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-10 | Memory Service 启动链路为单线程（并发入口不存在）；若后续引入并发初始化入口，需加类级锁并升级严重度 | PR #17 |
| TD-A-005-07 | Day4 Bridge/Provider 非权威文档与元数据收口（轮次标注、错误模型注释同步） | docs/day3/06_provider_contract_v1.md, docs/day4/08_bridge_provider_skeleton.md, evidence/index.yaml, cpp-bridge/src/py_module.cpp, memory-service/providers/embedding_provider.py, cpp-bridge/tests/test_bridge_failure_recovery.cpp | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-12 | 源码注释 / Day3 说明 / Day4 说明 / evidence 元数据与当前正式错误模型（ERR_FATAL_FAILURE 语义、BridgeSessionDestroyedError/BridgeFatalError）及最新 Runtime 轮次（第八轮）一致 | PR #17 |
| TD-A-005-08 | Day4 验证脚本证据文件生命周期优化（.prev 备份不自动清理） | scripts/verify_day4_vm.sh, evidence/l2-kylin-vm | Technical Debt | Low | Open | A 轨成员 | D 主审 | 2026-08-12 | 验证脚本可连续执行，无需人工删除上一次运行生成的 .prev 临时备份，同时保持 Step 1 严格工作区门禁（历史备份入 /tmp 或执行前自动清理，或建立统一 evidence archive 机制） | PR #17 |

### TD-A-005-07 / TD-A-005-08 延期说明（第四轮 Review，2026-08-08）

- **TD-A-005-07 产生原因**：Day4 多轮 REWORK 迭代中，文档/注释/元数据未随每轮同步更新，遗留描述性信息（如 Day4 文档顶部“第七轮 L2”、Day3 状态表“麒麟 VM 第七轮 L2”、EMBED-CALL-003 `date: 2026-08-07` 与第八轮运行时间 2026-08-08 不一致、py_module.cpp 注释仍写 `ERR_SESSION_* → BridgeSessionError`、embed() docstring 异常列表缺 ERR_FATAL_FAILURE、test_bridge_failure_recovery.cpp 注释把 init_session 首次失败写为 ERR_FATAL_FAILURE）。
  **当前影响**：仅影响描述性信息，不改变 Bridge 实际返回码、Provider 实际映射、生命周期控制、Runtime 执行结果、tested_commit、evidence_commit、checksum 或权威证据文件。
  **允许延期理由**：不影响运行安全、错误契约或测试可信度；待合并后统一清理，避免为纯文档改动反复触发 L2 重验。
- **TD-A-005-08 产生原因**：verify_day4_vm.sh 每次运行把上一版证据日志备份为 `day4_verify_latest.log.prev`，而 Step 1 严格工作区排除规则未覆盖 `.prev`，重复运行前可能需要人工清理。
  **当前影响**：仅影响连续运行的便利性；第八轮 L2 证据（HEAD 匹配 / status 空 / worktree clean / index clean / CTest 6/6 / pytest 52 / Smoke 11 / 生命周期 4 路径 / FAILURES=0）已生成且真实有效。
  **允许延期理由**：属测试基础设施维护，不影响已生成证据真实性。

## 管理规则

1. **Critical 严重程度的技术债不得带病合并。** 必须在合并前解决或降级为 High。
2. 所有 `TODO`、`FIXME`、`HACK` 注释必须引用有效的 TD 编号。
3. `代码合并` 不等于 `技术债关闭`。关闭需要对应 PR 的 Reviewer 确认验收标准达成。
4. Bug、Blocker、Risk 和技术债必须严格区分：
   - **Bug**：不符合规格的缺陷
   - **Blocker**：阻断下一个 Gate 的障碍
   - **Risk**：已知但未发生的潜在问题
   - **Technical Debt**：有意的临时实现或设计妥协
