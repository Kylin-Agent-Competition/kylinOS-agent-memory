# D10E 开工工作清单：精准遗忘业务与安全 Gate

## 任务信息

| 项目 | 内容 |
| --- | --- |
| 施工项 | D10 E 轨「精准遗忘与删除一致性」 |
| 本次代行 | B 轨在取得 E 轨负责人授权后，代行 E 轨限定范围 |
| 工作类型 | 新增功能：业务规则、状态机、安全测试 |
| 分支 | `feature/d10-e-forgetting-governance`（基于 `main`：`c1ee840`） |
| Draft PR 标题 | `B轨代替E轨：D10 精准遗忘业务与安全 Gate` |
| 初始进度 | 1/7（14%）：本任务卡已提交；其余实现尚未开始 |

## 目标与边界

本批次交付可测试的遗忘业务语义：受控 `ForgetPlan` 输入、精准目标范围、预览—确认—执行状态机、软/硬删除业务边界，以及误删、漏删、批量、高敏感、跨用户的安全测试。

不在本批次实现或宣称完成：D 轨 SQLite 事务、Outbox、确认令牌与审计持久化；B 轨 Vector/FTS5 物理删除、重建和残留率；C 轨 QML 预览/确认界面；真实银河麒麟宿主验证。缺少宿主证据的项目必须保持 `UNVERIFIED`。

## 工作清单

1. [x] **建立本工作清单**：确定 D10E 范围、验收、依赖、分支与 Draft PR 标题。
2. [ ] **冻结请求与 Plan 输入边界**：每种 `forget_mode` 仅接受对应 selector；`full_reset` 仅允许 `target_type=all`，默认拒绝级联。

   验证：模式正向、跨模式 selector、空白 ID/selector 的负向用例；关闭 TD-015 的实现部分。
3. [ ] **目标解析与精准范围**：以请求 `user_id` 作为强制过滤键；规则引擎生成去重且稳定排序的 `resolved_target_ids`、`affected_count` 和脱敏预览。

   验证：单条、会话、主题、时间窗、全量重置的快照；误删、漏删均为零。
4. [ ] **预览—确认—执行状态机**：仅允许 `pending → previewing → awaiting_confirmation → executing → completed/failed/rolled_back`。

   验证：逐边迁移、过期/错配确认、幂等重放、失败与回滚路径。
5. [ ] **软/硬删除业务语义**：软删除立即从标准检索与 MemoryContext 排除；硬删除后 SQLite、Vector、FTS5、日志、导出和备份中不得有可检索明文。

   验证：删除后检索排除，审计不含正文或原 selector，模式/保留字段反向测试。
6. [ ] **高敏感和跨用户防线**：高敏感对象须已鉴权用户预览后确认；身份缺失、错配或越权目标一律拒绝，审计仅保留原因码与非敏感计数。

   验证：跨用户单条、批量、全量重置均零影响；敏感内容不进入审计。
7. [ ] **安全测试矩阵与审查**：覆盖误删、漏删、批量、高敏感、跨用户、跳确认、重复提交、软删除排除、硬删除明文残留。

   验证：目标 pytest、`git diff --check`、D 轨非作者审查；麒麟宿主证据未完成时明确为 `UNVERIFIED`。

## 跨轨依赖

| 依赖 | 责任轨道 | D10E 的处理 |
| --- | --- | --- |
| 确认令牌、SQLite 事务、Outbox、最小审计持久化 | D | 仅定义接口和验收，不实现 |
| Vector/FTS5 精确删除、重建、残留率 | B | 仅消费删除结果，不改 B 轨实现 |
| 预览、确认、重试 UI | C | 仅提供 DTO/状态，不做 QML |
| `full_reset` 与级联边界 | E/D | 保守拒绝，待书面联合确认 |
| 麒麟宿主 Runtime 证据 | C/D/E | 保持 `UNVERIFIED`，不以本地测试替代 |

## Draft PR 要点

- 标题使用：`B轨代替E轨：D10 精准遗忘业务与安全 Gate`。
- 正文须说明本次由 B 轨代行 E 轨授权范围，并明确 D、B、C 的未实现依赖。
- 验证部分需分别列出本地测试、`git diff --check`、D 轨非作者审查和麒麟宿主证据状态；不得将本地结果写为宿主通过。

## 依据

- `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`：§3.7、§7.6 的精准遗忘、先预览再确认和禁止模型生成终判字段要求。
- `docs/architecture/D3_MEMORY_SECURITY_ACCEPTANCE_V1.md`：SEC-FORGET-01..05、SEC-SENS-07。
- `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`：TD-015。
