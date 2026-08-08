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
