# D15B：B 轨未结技术债审计（2026-09-09）

## 审计口径

本文件仅审计 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` 中责任人为 B 的 Open 条目。它不修改总账状态、不替 D/E 作出关闭或 release-debt acceptance；`gaoyizhe934 (B)（代 E 轨）` 的 TD-062、TD-063 不属于 B 轨本次范围，未被纳入。

截至 `a7abb1e71c03c4f1558e5c6a9eff2b9f36437993`，没有 B 轨 Open 项标记为 P0 或 High；但以下 Medium/Low 条目全部仍为 Open，不能在没有规定证据和独立审查的情况下改写为 CLOSED 或 ACCEPTED_RELEASE_DEBT。

## 逐项结果

| TD | 严重度 | 当前处置 | 关闭所需事实/责任边界 |
| --- | --- | --- | --- |
| TD-001 | Medium | 保持 Open | D1-A evidence reviewer 字段恢复，或 D 主审书面认可历史变更。B 不改写 A 轨证据字段。 |
| TD-002 | Medium | 保持 Open | 补齐 evidence schema 1.0→1.1 迁移记录、迁移验证与下游影响评估；涉及全局 evidence 治理，需 D 审查。 |
| TD-018 | Medium | 保持 Open | 生产检索接线时以 canonical filter digest 替换历史固定值，并有请求/指纹负向测试。 |
| TD-019 | Medium | 保持 Open | production Vector 查询从 SQLite truth 消费真实 version，不得写死 `v1`；需生产路径与陈旧版本回归。 |
| TD-020 | Medium | 保持 Open | B/D production deadline 链以绝对 `deadline_at` 逐层递减并有真实接口验证。 |
| TD-021 | Medium | 保持 Open | 下一次正式 evidence 重跑必须由 EIR 类 runner 写入可自描述 runtime header、命令、退出码和 checksum。当前没有 Formal L3 重跑，不能补造。 |
| TD-027 | Medium | 保持 Open | D 轨索引路由提供已验证 serving `index_generation`，B provider 对错配 fail-closed；属于 B/D 接线。 |
| TD-029 | Low | 保持 Open | 对外序列化/统一日志接线前，对 Provider 异常进行脱敏并以 URI/路径/凭据样例负向测试证明无泄露。 |
| TD-030 | Low | 保持 Open | `TruthRecord` 构造边界拒绝倒置有效期并覆盖区间边界测试。 |
| TD-032 | Medium | 保持 Open | D 侧真实 Knowledge 写入/回源生产路径构造合法 `KnowledgeIndexMetadata`；缺失时 fail-closed。 |
| TD-033 | Medium | 保持 Open | 目标麒麟 VM 的 bridge 重编译、D8-B L2 执行与 bridge SHA-256 evidence；B 不以本机替代宿主证明。 |
| TD-034 | Medium | 保持 Open | EvalConfig 通道与 algorithm-version 映射需在正式 D9 evidence 中证明与运行时一致，并由 D/E 审查。 |
| TD-035 | Medium | 保持 Open | weighted-RRF 权重校验须与运行时契约一致，并由正式输入/评测证据验证。 |
| TD-036 | Medium | 保持 Open | E 的 Gold 口径与 sealed inputs 到位后，B 对正式结果记录有效分母、剔除数和理由；候选 query 不足以关闭。 |
| TD-037 | Medium | 保持 Open | 冻结麒麟环境中的逐通道 latency 样本、P50/P95、数据/提交哈希和运行参数；历史 substitute 指标不能替代。 |
| TD-038 | Medium | 保持 Open | 正式 D9 Gold/性能 evidence 中确认严格 EvalConfig、统计方法与非法值拒绝契约。 |
| TD-054 | Low | 保持 Open | 首次跨 IPC/C/D/OS Agent/用户接口前，由 D/E 冻结公开 schema、reason-code、隐私及兼容策略；B 不自行发布候选内部字段。 |

## 与 D15B 的关系

这批 debt 的存在不会被“无 P0/High”掩盖。D15B 的最终 manifest 只能在每项取得关闭证据或其 required reviewer 的明确 `ACCEPTED_RELEASE_DEBT` 后设为 `FROZEN`。在此之前：

```text
accepted_release_debts = []
B_TRACK_COMPLETE = NO
```

当前可执行的 B 侧契约回归已在 PR #173 上通过；其结果只证明 harness、evaluator 与 D9 schema 的代码契约，不能为任何表中运行时、D/E 审查或正式环境前置项提供替代证据。
