# D11E 开工工作清单：同一虚拟机全功能联调——业务验收与安全确认（准备阶段）

## 任务信息

- 施工项：D11 E 轨「同一虚拟机全功能联调」（台账 D11-E 行，负责人：E＝谢嘉然）。
- 授权：已取得 E 轨负责人授权，由 B 轨（高翌哲）代行 D11E 限定范围；本批＝准备阶段（工作清单与基线口径），不代行 E 轨业务实现或正式验收结论。
- 工作类型：`test`（业务验收场景、真实案例脚本与评委操作路径、UI 文案/证据/安全确认审查）。
- 工作分支：`test/D11E-vm-business-acceptance`（按提交分支要求命名：`<类型>/<用途>`，不含 `codex`）。
- 基线：`origin/main@cc4acf6`（2026-09-03 更新：初版基线 0820036，已含 D11D PR #115、C-D11 PR #116、D11B PR #111、D10D PR #120，并新增 C-D12 PR #127、D8D 持久化 PR #128、D12D PR #131、E 轨 schema-drift 修复 #137；本 PR 分支创建于 0820036，Ready/合并前以最新 main 为准）。
- 本次范围：建立 D11E 工作清单、固定验收口径与跨轨依赖/不在范围；不包含麒麟 VM 实测、业务代码修改或「主演示业务正确」的达标结论。
- 开始时间：2026-09-03（准备阶段）。最晚停止时间：进入实测/实现前须由 E 轨负责人指定并确认。
- 当前进度：阶段性证据已归档，**D11E 尚未完成**（项 1–4、6 完成；项 5 仅有可测部分、仍受 Critical 跨轨链路阻塞；A/C/D2 与硬删除无明文残留保持 `UNVERIFIED`，见 `docs/day11/26_*`；项 7 已收到 D 轨 `CHANGES_REQUESTED`，待本轮修订后复审）。

## 完成定义

对照台账 D11-E 行完成定义「主演示业务正确，真实案例具备完整输入与结果证据」：

1. 在同一麒麟 VM、同一 Commit（`main` 最新）上，偏好、知识、冲突、生命周期、遗忘五类业务按冻结契约（`docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md` §3/§5/§7、`docs/architecture/D3_MEMORY_SECURITY_ACCEPTANCE_V1.md`）在主演示链中给出可解释、可追溯的结果；
2. 真实案例脚本与评委操作路径（输入、预期输出、证据采集、判定步骤）完整，且同 Commit 同 VM 可复跑；
3. UI 文案、展示证据与安全确认（先预览再确认、确认凭据 TTL、用户隔离、敏感过滤、遗忘后排除）与成品事实一致，日志/检索/审计无正文与敏感内容泄露；
4. 业务验收报告与原始证据归档（SHA-256 登记 `evidence/index.yaml`）。

没有麒麟 VM 实测证据的结论一律标 `UNVERIFIED`；不以本地/L1 或历史 L2 证据冒充当前 Commit 的业务验收结论。

## 工作清单

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| 1 | 基线与环境盘点（准备阶段）：记录 `origin/main@cc4acf6`、D11D 统一 VM/快照与交付（PR #115：`packaging/systemd/install_kylin_memory.sh`、`kylin-memory.service`、JSON 日志/trace_id/脱敏诊断与 `evidence/l2-kylin-vm/d11d_*`）、C-D11 5 步主演示编排（PR #116）、D11B 检索联调输入（PR #111）、E 轨既有业务实现与测试（`memory-service/domain|service|security` + `tests/test_*_d4e..d10e.py`）、E 冻结契约与验收样例（`docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`、`D3_MEMORY_SECURITY_ACCEPTANCE_V1.md`、`datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json`）；确认 D11E 验收用 VM/快照与同一 Commit 口径 | `origin/main`；D11D/C-D11 合并基线 | `git status`、仓库审阅、快照/版本/哈希核对 | 待开始（基线口径已记录于本清单；VM 实测待 D11E 专用环境复核） |
| 2 | 业务验收场景方案：按冻结契约将偏好、知识、冲突、生命周期、遗忘五类业务映射到真实服务链路的验收场景与判定口径（复用/对照 D7E/D8E/D9E/D10E 的 L0/L1 用例与 G0-E-01..14、SEC-* 规则），输出验收矩阵（场景×输入×预期×证据级别×当前状态） | 工作项 1；E 冻结契约与既有测试 | 验收矩阵可核对、每条场景可映射契约条款与 SEC 规则 | 待开始 |
| 3 | 真实案例脚本与评委操作路径：整理/完善真实案例（Gate0 验收案例、D9 检索语料/Query、C-D11 5 步编排）的输入、预期输出、证据采集与评委判定步骤；同 Commit 同 VM 可复跑 | 工作项 2；C-D11 主演示路径 | 脚本/步骤复跑、输入输出与证据一致、判定可复现 | 待开始 |
| 4 | UI 文案、证据与安全确认审查：核对 QML/演示文案、提示与汇总灯初始态/终态与业务事实一致；确认先预览再确认、确认凭据 TTL 过期失败关闭、跨用户隔离、敏感过滤、遗忘后排除等安全确认真实生效（对应 SEC-CTX-01、SEC-FORGET-01..05、SEC-UI-*、SEC-SENS-* 等） | 工作项 2；C-D11 客户端 Harness 与 B/D 检索/服务证据 | 文案/状态断言、脱敏断言、真实日志核对 | 待开始 |
| 5 | 同 VM 端到端验收执行与证据归档：在统一麒麟 VM、同一 Commit 上执行五类业务验收与主演示；输出业务验收报告、原始日志/结果，SHA-256 登记 `evidence/index.yaml` | 工作项 1–4；A/B/C/D 跨轨输入就绪 | 报告与原始证据一致、可复跑命令、D 主审材料 | **阻塞**：已有 VM 的 L0/L1、部署/IPC 冒烟与偏好/软删局部证据已索引；RC-01..07 全量、`memory.retrieve` 主链、C GUI、A SDK、硬删除无明文残留尚未在同 Commit/同 VM 证实，保持 `UNVERIFIED` |
| 6 | L0/L1 回归与静态检查：运行 E 轨相关定向 pytest（preference/knowledge/conflict/lifecycle/forgetting/candidate/security）与评测契约测试；`git diff --check` | 工作项 2–4；既有 E 轨测试 | pytest 全绿、`git diff --check`、失败如实记录 | 待开始 |
| 7 | 收口与审查：整理变更、验收证据、`UNVERIFIED` 项与跨轨依赖，交由 D 轨非作者 Reviewer 审查；Review 意见回填本清单与 PR | 工作项 1–6；Review 可用性 | 审查材料完整、Review 结论回填 | 进行中：D 轨已要求修改；完成本轮两项 High 修订后申请复审。D11E 完成结论须等待项 5 解阻，不作为合并后的非阻断债务 |

## 固定验收口径

- 同一麒麟 VM、同一 Commit（`main` 最新）实测为准；无实测证据一律标 `UNVERIFIED`，不冒充既有证据。
- 主演示业务正确：偏好、知识、冲突、生命周期、遗忘在主演示链中的行为符合冻结契约（业务契约 §3/§5/§7 与安全验收 SEC-* 规则）。
- 真实案例具备完整输入与结果证据：脚本/步骤同 Commit 同 VM 可复跑，评委可据证据独立判定。
- UI 文案、证据与安全确认与成品事实一致；日志与诊断输出不得包含记忆正文、候选标识、用户标识或敏感配置；任一泄露均为 Critical。
- 正式业务验收结论只基于同 Commit 同 VM 实测；否则保持 `UNVERIFIED`。

## 跨轨依赖与不在范围

| 依赖 | 责任轨道 | D11E 处理方式 |
|---|---|---|
| Embedding/SDK 健康与降级状态 | A（D12A PR #100 已合并） | 作为验收前置状态消费，不代实现 |
| 真实检索输出、删除残留、重建一致性 | B（D11B PR #111、D10B PR #82、D12B PR #119/#121 已合并） | 以真实检索/索引输出作为业务验收输入，不代实现 |
| QML/客户端与 5 步主演示编排 | C（C-D11 PR #116 已合并） | 验收对象（文案、证据、安全确认），不代实现 |
| 统一 VM/systemd/trace/DB 与遗忘持久化 | D（D11D PR #115、D10D PR #120、D8D PR #128 已合并） | 消费统一环境与持久化结果，不代实现 |
| E 冻结契约、评测口径与既有业务测试 | E（D3/D7/D8/D9/D10 已冻结与合入） | 本批只消费与验收，不修改契约 |
| 麒麟宿主 Runtime 证据 | C/D/E | 保持 `UNVERIFIED`，不以本地测试替代 |

本批不实现或修改：memory-service 生产业务代码（domain/service/security）、C 轨 QML/客户端、A 轨 Bridge/SDK、B 轨检索/索引链路、D 轨部署/systemd/持久化；不执行麒麟 VM 实测；不产出正式业务验收达标结论。D12E 的独立安全/假实现审查不在本批范围。

## 当前状态与阻塞（准备阶段）

- D11D（PR #115）已合并并含麒麟 VM L2 证据与 `packaging/systemd` 产物；C-D11（PR #116）5 步主演示编排已合并；D11B（PR #111）、D10D（PR #120）已合并；`main` 现为 `cc4acf6`（更新后新增 C-D12 PR #127、D8D 持久化 PR #128、D12D PR #131）。E 轨 L0/L1 在 `cc4acf6` 复跑 571 passed（见 21 log；历史 b70827c 基线 535 见 05 log）。
- 已确认 D11E 端到端验收**复用 D11D 统一 VM 环境**（D11D PR #115 部署产物：`packaging/systemd/install_kylin_memory.sh`、`kylin-memory.service`、DB 迁移与 `evidence/l2-kylin-vm/d11d_*`）；D11E 专用克隆 `Kylin-V11-2603-D11E-0820036-Test` 已建并完成 VM 侧 L0/L1（535 passed，见 09/10 证据）。C 轨主演示真实运行结果与 B 轨真实检索输出需在同一 Commit 就绪后才能执行工作项 5；具体执行 VM/快照与最晚停止时间以 D 轨在 D11E 验收时指定为准。
- 本批为纯文档准备：UTF-8 无 BOM、LF 行尾、无尾随空白，`git diff --check` 通过；未改动既有生产链路、SQLite 真源、部署脚本、冻结文档或其他轨道交付物。
- 已完成 VM 侧 E 轨 L0/L1 回归（535 passed，见 09/10）；**同 VM 端到端业务验收、真实案例证据与安全确认结论保持 `UNVERIFIED`**，直到 D 轨部署产物与 A/B/C 输入就绪并在同 Commit 同 VM 复测通过。

## 初始 PR 正文（历史留档，非当前 PR 状态）

> 以下为开工阶段的原始正文快照。PR #132 当前为 Ready，且 D 轨已给出 `CHANGES_REQUESTED`；后续进展仅以 PR 评论、`22_*` 状态表和 `26_*` 阶段性证据归档为准，不改写原始 PR 正文。

```markdown
## test(D11E)：同一虚拟机全功能联调——业务验收与安全确认（开工工作清单 + 准备）

### 任务卡

- 台账 D11-E（E 轨＝谢嘉然；B 轨高翌哲在 E 轨授权下代行 D11E 限定范围，准备阶段）：同一虚拟机全功能联调。
- 完成定义：主演示业务正确；真实案例具备完整输入与结果证据。
- 施工任务：① 验收偏好、知识、冲突、生命周期和遗忘业务；② 完善真实案例脚本和评委操作路径；③ 审查 UI 文案、证据和安全确认。
- 基线：`origin/main@cc4acf6`（含 D11D PR #115、C-D11 PR #116、D11B PR #111、D10D PR #120 等）。
- 分支：`test/D11E-vm-business-acceptance`（不含 `codex`）。

### 提交内容

| 文件 | 变更 | 说明 |
|---|---|---|
| `docs/day11/04_d11e_business_acceptance_worklist_20260903.md` | 新增 | D11E 工作清单：任务信息、7 项工作、固定验收口径、跨轨依赖与不在范围、PR 状态 |

### 工作清单概览（7 项，全部待开始）

1. 基线与环境盘点（`origin/main@cc4acf6`、D11D 统一 VM/交付、C-D11 主演示编排、E 轨业务实现与测试、冻结契约与验收样例）。
2. 业务验收场景方案：五类业务按冻结契约映射真实服务链路，输出验收矩阵。
3. 真实案例脚本与评委操作路径：输入/预期/证据采集/判定，同 Commit 同 VM 可复跑。
4. UI 文案、证据与安全确认审查：先预览再确认、credential TTL、用户隔离、敏感过滤、遗忘后排除。
5. 同 VM 端到端验收执行与证据归档：业务验收报告 + `evidence/index.yaml` SHA-256 登记。
6. L0/L1 回归与静态检查：E 轨定向 pytest + `git diff --check`。
7. 收口与审查：交由 D 轨非作者 Reviewer 审查，Review 意见回填。

### 验证结果（本批）

- 本批为纯文档准备：UTF-8 无 BOM、LF 行尾、无尾随空白，`git diff --check` 通过。
- 未改动既有生产链路（Vector/FTS5/RRF）、SQLite 真源、QML、部署脚本、冻结文档或其他轨道交付物。

### 不在本批范围 / 未验证

- 不代行 A/B/C/D/E 轨实现或审查；不修改 memory-service 业务代码、QML/客户端、Bridge/SDK、检索/索引、部署/持久化。
- 麒麟 VM 实测、五类业务验收、真实案例证据与安全确认结论，均待 D11E 专用麒麟 VM/快照与 E 轨最晚停止时间就绪；此前一切结论保持 `UNVERIFIED`。

### Reviewer 检查重点

- 工作清单是否完整覆盖台账 D11-E 三条施工任务（业务验收；真实案例脚本与评委操作路径；UI 文案/证据/安全确认审查），且未扩大到其他轨道范围。
- 验收口径是否守住「同 Commit + 同 VM + 无实测即 `UNVERIFIED`」边界。
- 本 PR 是否未虚报任何麒麟 VM 实测、业务验收或安全确认达标结论。
```

## 依据

- `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`：§3/§5/§7（偏好、知识、冲突、生命周期、遗忘业务语义与禁止模型生成字段）。
- `docs/architecture/D3_MEMORY_SECURITY_ACCEPTANCE_V1.md`：SEC-UI-*、SEC-SENS-*、SEC-FORGET-01..05、SEC-CTX-01 等。
- `datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json`：G0-E-01..14 业务验收案例。
- `docs/day11/01_d11d_vm_integration_checklist_20260901.md` 与 `docs/project-management/PR116_body.md`：D11D 统一环境与 C-D11 5 步主演示编排基线。
- E 轨既有业务实现与测试：`memory-service/domain|service|security` 及 `memory-service/tests/test_*_d4e..d10e.py`。
