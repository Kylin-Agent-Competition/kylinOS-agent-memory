# C 轨 Production Integration Closure 状态（C-1）

## 目的与边界

本文建立 C 轨最终收口的第一条控制线：它消费已合入的 D15C Host Mapping
与 D14C preparation，不重做历史工程，也不把 preparation 或候选验证升级为
production / formal runtime 结论。

本批次对应 PR `feat(C): D14C production integration closure`。它是 C-1，
不是 D14C formal evidence PR，也不是 C-2 final asset lock PR。

## 阶段 ID 定义

- `D15C` = 已合入的 Host Mapping / C→D handoff（PR #167）。
- `C-1` = 当前 Production Integration Closure（PR #176）。
- `D14C Formal Evidence` = 后续正式 L3 evidence 阶段。
- `C-2` = D14C Formal Verified 后的 final asset lock。

`D15C` 只保留 Host Mapping / C→D handoff 的既有含义，不再复用于 future
final asset lock。

## 当前可核验状态

| 项目 | 状态 | 依据 |
| --- | --- | --- |
| C 轨基础工程（MemoryClient、QML、Adapter、Hook 基础） | `DELIVERED` | 已合入历史 C 轨交付 |
| D15C Host Mapping / C→D handoff | `MERGED_WITH_OPEN_FORMAL_BLOCKERS` | `docs/day15/01_d15c_host_mapping_closure_task_card_20260907.md`、`02_d15c_c_to_d_handoff_memo_20260907.md` |
| D14C preparation | `MERGED_AND_APPROVED` | PR #156 / `docs/day14/11_d14c_main_intake_audit_20260910.md` |
| D14C formal runtime | `BLOCKED / NOT_STARTED / UNVERIFIED` | G4--G7 尚未满足 |
| C-2 Final Asset Lock | `NOT_STARTED` | 需在 D14C formal verified 后开始 |

## C-1 范围

1. 消费一次真实 Host chat / Tool round-trip 的输入，收敛 TD-008、TD-009 与
   production identity 的 C 侧事实；不编造 Tool cancelled 或 Host 注入结论。
2. 准备 C→D `ProductionSourceReference` 与 trusted-host-identity 评估输入，
   状态最高为 `PROPOSED_FOR_D_APPROVAL`；C 不自行写入 `APPROVED`。
3. 在 C 侧可证明的范围内冻结 MemoryContext/client integration 输入，提交 D/E
   会签所需材料。
4. 仅在最终用户路径明确包含 Preference 或 Forget 后，处理 TD-044、TD-045、
   TD-058；在此之前不擅自改变其 release scope 或生产语义。
5. 对 TD-060 保持既有 adapter window，待 C/D 书面冻结后才决定 alias 的长期
   兼容或移除策略。

## 非本 PR 授权范围

- 不将 `memory-service` production resolver 或四条写 route 从
  `BLOCKED_BY_HOST_MAPPING` 升级为 `ACTIVE`；该激活与 trusted identity 批准由 D
  轨负责。
- 不创建 D14C formal evidence root，不声称 `HOST_VERIFIED`、`L3 PASS`、
  `D14C_COMPLETE` 或 `C_TRACK_COMPLETE`。
- 不把 validation flags、mock、fixture 或旧的 outbound-only Hook 证据当作生产闭环。

## 继续条件与顺序

```text
真实可用 Chat LLM
  -> TD-008 / TD-009 / identity 同轮采集
  -> C→D SourceReference proposal
  -> D trusted identity approval + production resolver/routes ACTIVE
  -> C/D/E MemoryContext freeze
  -> 唯一 D14C formal evidence PR
  -> C-2 final asset lock PR
```

在真实 Host 依赖可用前，C-1 只可完成不依赖该环境、且已由最终用户范围授权的
客户端修复与回归。所有阻塞保持显式记录，不能用静态或 L1 测试替代 Host evidence。

## 当前下一步

1. 提供或安装可工作的 Host Chat LLM，并记录其 package / binary identity。
2. 在同一真实回合采集 `chatAsync` 注入、Tool 回程与 Chat DB identity 时序。
3. 由 D 评审 C 侧 SourceReference / trusted identity 输入；在该批准前保持
   production resolver 与 routes fail-closed。
