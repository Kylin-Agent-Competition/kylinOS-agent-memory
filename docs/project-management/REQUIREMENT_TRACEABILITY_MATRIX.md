# 赛题要求与项目交付追踪矩阵

- **版本**：v0.1
- **状态**：DRAFT
- **用途**：D1–D2 能力对照，为 D3 Gate 评审提供赛题要求 ↔ 项目交付物的双向追踪基线
- **冻结门槛**：D3 Gate 前不得视为冻结基线；须经 D/E Reviewer 审查，且与导入仓库后的赛题原文、总体架构 SOP、官方 SDK 能力边界权威基线对齐后方可冻结
- **依据来源**：
  - `README.md`（技术路线、责任轨道 A–E、项目定位与明确未完成项）
  - 各模块 `README.md`（`memory-service/`、`cpp-bridge/`、`memory-client/`、`os-agent-integration/`、`evaluation/`、`datasets/`）中的职责边界与当前状态
  - 比赛方案及项目需求基线（基线文档待人工导入，详见局限声明）
- **局限声明**：
  - 赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线文档尚未导入仓库（`docs/baseline/README.md` 均标注「待人工导入」）
  - 本稿以当前仓库已有事实为据，赛题要求文字以 `README.md` 责任轨道与项目需求基线为据，不代表官方赛题原文
  - D3 Gate 前须用导入后的权威基线文档全文复核，覆盖本稿中因依据不足可能存在的偏差

---

## 一、字段说明

| 字段 | 含义 | 取值说明 |
|------|------|----------|
| 需求编号 | 本矩阵内部统一编号 | `REQ-01` 至 `REQ-07`，与七项赛题核心要求一一对应 |
| 赛题原始要求 | 赛题文本中提出的核心要求 | 本稿以项目需求基线为据暂代赛题原文；D3 Gate 前以导入仓库的赛题原文为准 |
| 对应业务能力 | 项目为满足该要求需具备的业务能力 | 以模块职责与交互链路为单位，避免单一模块承担全部 |
| 责任轨道 | 该能力的主责与协作轨道 | 主：设计/实现主负责轨道；协：输入/评审/集成协作轨道，取值 A–E（见 `README.md` 责任轨道表） |
| 计划日期 | 预期完成 D 日窗口 | 以 D1–D15 相对日程占位；绝对日期待 `docs/project-management/README.md` 的 15 天 75 项台账导入并与 D3 对齐后落定 |
| 输入数据 | 该能力运转所需的输入 | 包括 IPC 请求、数据集、配置 Schema、上游模块输出等 |
| 交付物 | 该要求对应的预期交付物 | 可对应模块目录下的代码、数据集、评测报告、配置等 |
| 验收证据 | 该要求对应的验收证据目标 | 标注目标 Gate（Gate 0 / L0 / L1 / L2 / L3）和关键验收点；当前证据均标注「尚未产生」 |
| 当前状态 | 该要求相关的实现/验证进展 | 取值限定为 `UNTESTED`、`PENDING`、`SOURCE_VERIFIED`、`PARTIAL`、`DONE`；本 v0.1 仅使用 `PENDING` 或 `UNTESTED` |
| 风险 / 依赖 | 已知阻塞、前置条件或技术依赖 | 包括基线文档未导入、协议未定稿、ADR 未建立、SDK/Hook 待取证等 |

---

## 二、七项核心要求追踪表

| 需求编号 | 赛题原始要求 | 对应业务能力 | 责任轨道 | 计划日期 | 输入数据 | 交付物 | 验收证据 | 当前状态 | 风险 / 依赖 |
|----------|-------------|-------------|---------|---------|---------|--------|---------|---------|------------|
| **REQ-01** | 多源数据 | 多源（用户偏好、对话上下文、结构化知识）融合采集、归一化写入 Memory Service | 主：D、E<br>协：A、B、C | D4–D8（待台账对齐后落定） | UDS 协议 Memory/Preference/ToolResult 请求；datasets 目录下的开发集/回归集/封存集 | `memory-service/src/memory/` 多源写入链路；`memory-service/src/protocol.py` UDS 协议解析器；`datasets/` 多源样例数据集 | **目标证据**：Gate 0 ADP 协议设计通过；L1 UDS 多源写入测试通过；L2 麒麟 VM 中完整多源写入链路通过；L3 干净快照端到端验证通过<br>**当前**：尚未产生 | **PENDING** | ① 赛题原文/SOP/SDK 能力边界基线文档未导入，多源数据结构待权威基线确认<br>② UDS 协议消息格式与字段清单未定稿<br>③ 官方 AI 助手 Tool/Turn 事件结构需 Gate 0 在麒麟 VM 中取证<br>④ os-agent-integration Hook 输入格式未确认 |
| **REQ-02** | 偏好动态捕捉 | 用户偏好提取、更新、置信度推理，支持实时捕捉偏好变化 | 主：E<br>协：A、D | D5–D9（待台账对齐后落定） | Tool/Turn 上下文事件（经 os-agent-integration Hook → MemoryClient → Memory Service）；偏好标注/评测数据集 | `memory-service/src/memory/preference/` 偏好提取 Provider；`memory-service/src/memory/preference_model.py` 偏好模型与置信度推理；`evaluation/recall/` 偏好评测脚本 | **目标证据**：Gate 0 偏好模型选型 ADR 通过；L1 偏好提取单元测试全覆盖；L2 麒麟 VM 中动态偏好捕捉 Runtime 验证通过<br>**当前**：尚未产生 | **PENDING** | ① 偏好 Schema（类型、优先级、置信度、失效策略）未定义<br>② 偏好评测指标（召回率、精确率、时效性）未定<br>③ Embedding 提取 Provider 选型尚未建立 ADR<br>④ 提取频率与触发策略（随 Tool/Turn 触发 v.s. 定时批量）未定 |
| **REQ-03** | 知识整合与冲突 | 跨源知识融合、冲突检测与消解、应用层 RRF 排序 | 主：B<br>协：E、D | D6–D10（待台账对齐后落定） | 多源知识条目（SQLite 结构化记忆）；Vector 索引检索结果；FTS5 全文搜索结果 | `memory-service/src/retrieval/rrf.py` RRF 应用层排序实现；`memory-service/src/retrieval/conflict.py` 冲突检测与消解策略；`evaluation/ranking/` 排序评测 | **目标证据**：Gate 0 冲突消解策略 ADR 通过；L1 RRF 排序单元测试与 Mock 评测通过；L2 麒麟 VM 中融合检索链路通过<br>**当前**：尚未产生 | **PENDING** | ① 冲突类型分类（时间冲突/来源冲突/语义冲突）与消解优先级未定<br>② RRF 权重参数调优策略未定义<br>③ 知识融合粒度（实体级 v.s. 事实级 v.s. 段落级）待决策<br>④ 评测封存集尚未制作，排序评测指标（NDCG、MRR 等）基线未设定 |
| **REQ-04** | 端侧 Embedding 与轻量检索 | 本地 Embedding Provider 推理、Vector 索引构建与更新、FTS5 集成、混合检索 | 主：A<br>协：B | D7–D11（待台账对齐后落定） | 文本/结构化知识条目；Embedding 模型文件（不入库，运行时加载）；检索查询请求 | `memory-service/src/embedding/` Embedding Provider 抽象与本地实现；`memory-service/src/retrieval/vector_index.py` Vector 索引管理；`memory-service/src/retrieval/fts5.py` FTS5 集成；`evaluation/retrieval/` 检索评测脚本 | **目标证据**：Gate 0 Embedding 选型 ADR 通过；L1 本地 Embedding 推理与索引构建测试通过；L2 麒麟 VM 中混合检索（Vector + FTS5 + RRF）端到端通过<br>**当前**：尚未产生 | **PENDING** | ① Embedding Provider 选型 ADR 未建立（需在模型大小、推理速度、准确率间取舍）<br>② 模型文件不入库，运行时加载路径与回退策略未定义<br>③ 检索性能指标（QPS、索引构建耗时、召回率@K）未达成基线<br>④ Vector 索引与 SQLite 真源的一致性策略（增量更新/全量重建）未定 |
| **REQ-05** | 敏感过滤与精准遗忘 | 敏感词/模式过滤、按主体或范围（单条/会话/全部）精准遗忘、权限与 IPC 访问控制边界 | 主：E<br>协：D | D8–D12（待台账对齐后落定） | 用户敏感数据标注规则；遗忘请求（指定记录 ID、时间范围、会话 ID 等）；IPC 访问权限配置 | `memory-service/src/security/` 敏感过滤与遗忘模块；`memory-service/src/security/access_control.py` 权限边界实现；`docs/security/` 安全边界设计文档 | **目标证据**：Gate 0 安全与遗忘边界 ADR 通过；L2 麒麟 VM 中敏感过滤、精准遗忘、权限分离 Runtime Test 全部通过<br>**当前**：尚未产生 | **PENDING** | ① 遗忘粒度定义不完整（单条记录 / 会话级 / 用户级 / 时间窗口级）与级联效应未分析<br>② 敏感词库/模式清单未建立<br>③ IPC 权限模型（基于 UID/GID/capability 还是应用白名单）未决策<br>④ 遗忘后 Vector 索引同步删除的一致性保证策略未定 |
| **REQ-06** | 短中长期流转 | 分层记忆体系（短期/中期/长期），SQLite 为结构化记忆真源，Vector 索引可重建，Outbox 与回收策略 | 主：D<br>协：E | D9–D13（待台账对齐后落定） | 记忆条目及其时间戳/访问频率/重要性得分；分层流转策略配置 | `memory-service/src/memory/lifecycle.py` 短中长期流转策略；`memory-service/src/memory/outbox.py` Outbox 机制；`migrations/` SQLite schema 迁移脚本；`memory-service/src/memory/recycling.py` 回收与清理策略 | **目标证据**：Gate 0 SQLite Schema 与分层策略 ADR 通过；L1 流转逻辑单元测试全覆盖；L2 麒麟 VM 中短期→中期→长期流转链路通过；L3 干净快照中逻辑一致性验证通过<br>**当前**：尚未产生 | **PENDING** | ① 短期/中期/长期的分层边界（时间阈值 or 访问频率 or 混合）未定义<br>② SQLite Schema 尚未设计，迁移策略（向前兼容/数据回填）待定<br>③ Outbox 与回收机制的设计（触发时机、保留策略、恢复机制）未完成<br>④ Vector 索引从 SQLite 真源重建的正确性与性能需验证 |
| **REQ-07** | 标准化评测 | 检索与记忆质量评测体系、封存集制作与哈希锁定、评测指标定义与报告生成 | 主：B<br>协：E | D10–D14（待台账对齐后落定） | datasets/ 目录下封存集（锁定 SHA-256）；评测标注（相关性/冲突/偏好正确性）；evaluation/ 评测脚本 | `evaluation/retrieval/` 检索评测脚本与指标计算；`evaluation/recall/` 回忆/记忆准确率评测；`evaluation/ranking/` 排序质量评测；`evaluation/reports/` 评测报告模板；`datasets/` 封存集及 SHA-256 清单 | **目标证据**：Gate 0 评测指标体系与基线 ADR 通过；L1 所有评测脚本在封存集上可复现运行；L2 麒麟 VM 中对真实检索链路产出可复现评测报告<br>**当前**：尚未产生 | **PENDING** | ① 评测指标（Recall@K、MRR、NDCG、偏好准确率、遗忘验证率等）的基线阈值未定<br>② 封存集尚未制作，SHA-256 锁定流程未执行<br>③ 评测脚本框架与报告模板未建立<br>④ 评测结果的可复现性（确定性 Embedding、固定随机种子）保证策略待定 |

---

## 三、交付物总览

| 需求编号 | 预期交付物 | 所在目录 | 当前存在状态 |
|----------|-----------|---------|------------|
| REQ-01 | 多源写入链路、UDS 协议解析器、多源样例数据集 | `memory-service/src/memory/`、`memory-service/src/protocol.py`、`datasets/` | 目录已建，交付物代码/数据未编写 |
| REQ-02 | 偏好提取 Provider、偏好模型与置信度推理、偏好评测脚本 | `memory-service/src/memory/preference/`、`evaluation/recall/` | 目录未建（`memory-service/src/` 下尚无子目录），代码未编写 |
| REQ-03 | RRF 排序实现、冲突检测与消解策略、排序评测 | `memory-service/src/retrieval/`、`evaluation/ranking/` | 目录未建，代码未编写 |
| REQ-04 | Embedding Provider 抽象与本地实现、Vector 索引管理、FTS5 集成、检索评测脚本 | `memory-service/src/embedding/`、`memory-service/src/retrieval/`、`evaluation/retrieval/` | 目录未建，代码未编写 |
| REQ-05 | 敏感过滤与遗忘模块、权限边界实现、安全边界设计文档 | `memory-service/src/security/`、`docs/security/` | 目录未建（`memory-service/src/` 下尚无子目录），代码未编写 |
| REQ-06 | 短中长期流转策略、Outbox 机制、SQLite Schema 迁移、回收清理策略 | `memory-service/src/memory/`、`migrations/` | 目录已建（`migrations/` 为空），代码未编写 |
| REQ-07 | 检索评测脚本与指标、回忆准确率评测、排序评测、评测报告模板、封存集与 SHA-256 清单 | `evaluation/`、`datasets/` | 目录已建，内容均为「仅建立目录和职责边界，尚无生产实现」 |

---

## 四、证据与 Gate 映射

| Gate | 关键证据 | 涉及需求 | 当前状态 |
|------|---------|---------|---------|
| **Gate 0** | 仓库与协作基线可验证；环境信息可在麒麟虚拟机中采集；技术方案与架构经 A–E 评审；基线文档与 ADR 就位（赛题原文/SOP/SDK 能力边界导入、Embedding 选型 ADR、安全遗忘边界 ADR、SQLite Schema ADR、评测指标体系 ADR） | REQ-01 至 REQ-07 | 仓库协作基线已建立；环境信息采集脚本已就位；基线文档均「待人工导入」；ADR 目录已建但内容为空 |
| **L0** | 静态检查、单元测试、类型检查、Mock 测试全部通过 | REQ-01 至 REQ-07 | 尚未产生（业务代码未编写） |
| **L1** | WSL 组件集成测试、UDS 协议对接、C++ Bridge 双向调用、RRF/检索评测 Mock 测试通过 | REQ-01 至 REQ-07 | 尚未产生（业务代码未编写） |
| **L2** | 麒麟 VM Runtime Test：多源写入、偏好捕捉、融合检索、敏感过滤/遗忘、短中长期流转链路的真实系统验证 | REQ-01 至 REQ-07 | 尚未产生（依赖麒麟虚拟机、业务代码完成、部署就绪后执行） |
| **L3** | 麒麟 VM 干净快照端到端验收：完整部署→初始化→服务启动→全链路测试→日志收集 | REQ-01 至 REQ-07 | 尚未产生（L2 通过后方可进入 L3） |

---

## 五、当前状态与证据等级守则

本矩阵遵循以下证据等级红线（参见 `runtime-validation.md` 与 `SECURITY.md`）：

1. **`UNTESTED` / `PENDING`**：能力尚未实现或尚未在目标层验证，不得表述为已通过。
2. **`PARTIAL`**：部分能力已实现但关键链路未验证，需附具体缺失项。
3. **`SOURCE_VERIFIED`**：上游文档或基线已确认，但代码或 Runtime 行为未验证。
4. **严禁以下表述**：
   - 「宿主已通过」「代码已完成」「Runtime 已通过」「指标已达成」「正式接口已完成」
   - 以静态检查结果替代 Runtime Test 结论
   - 以 Mock 测试替代真实 SDK/systemd/麒麟系统能力测试
   - 以代码阅读或设计评审结论替代真实系统行为验证
5. 所有 L2/L3 级证据必须在银河麒麟桌面操作系统 V11 x86_64 虚拟机中实际执行，并保留环境探针结果、命令、exit code、stdout/stderr 和系统日志。

本 v0.1 初稿中，七项核心要求的状态均为 **`PENDING`**，与 `README.md`「当前仅完成工程仓库与协作基线初始化，业务代码尚未开始」的事实一致。最终比赛交付物（第八节）与四项比赛性能指标（第九节）当前均处于 **`PENDING`** 或 **`UNVERIFIED`** 状态，尚未在目标评测环境中执行。

---

## 六、版本与冻结门槛

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|---------|------|
| v0.1 | 2026-07-30 | DRAFT 初稿，基于 README 及各模块 README 事实与任务 JSON 七项要求建立能力对照基线。赛题原文/SOP/SDK 能力边界基线文档未导入，状态均为 PENDING | E 轨道 |
| v0.1（修订） | 2026-07-30 | 审查修复：依据来源修正为比赛方案及项目需求基线；补全六类最终比赛交付物追踪、四项比赛性能指标追踪、计划窗口与 D3 Gate 约束说明；状态均保持 PENDING/UNVERIFIED，仍为 v0.1 DRAFT | E 轨道 |

**冻结条件**（满足全部方可视为冻结基线 v1.0）：

1. 赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线文档已导入仓库
2. D3 Gate 经 D/E Reviewer 审查通过
3. 矩阵中计划日期、绝对里程碑与 `docs/project-management/README.md` 中的 15 天 75 项台账对齐
4. 七项要求的赛题原始要求列已用导入后的权威原文复核修正
5. Evidence Reviewer 确认矩阵中所有状态标注与当时实际证据等级一致

在满足以上条件之前，本矩阵不视为冻结基线，不得作为最终能力判定依据。

---

## 七、人工决策待办

以下事项需团队成员在后续阶段人工完成，不纳入本 v0.1 范围：

| 编号 | 待办事项 | 优先级 | 计划窗口 |
|------|---------|--------|---------|
| HD-01 | 将赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界文档导入 `docs/baseline/`，并更新 `docs/baseline/README.md` 状态 | 高 | D3 Gate 前 |
| HD-02 | 用导入后的权威基线全文复核矩阵 REQ-01–REQ-07 的「赛题原始要求」列 | 高 | D3 Gate 前 |
| HD-03 | 与 `docs/project-management/README.md` 中的 15 天 75 项台账对齐，回填绝对计划日期 | 中 | D3 Gate 前 |
| HD-04 | 考虑是否将本矩阵链接入 `docs/project-management/README.md` 的索引（当前记为独立任务，不属于本任务范围） | 低 | 后续维护 |
| HD-05 | 建立各 REQ 的 Gate 0 ADR 清单并推动选型决策（Embedding Provider、安全遗忘边界、SQLite Schema、评测指标体系等） | 高 | D3–D5 |

---

## 八、最终比赛交付物追踪

本节聚焦比赛级最终交付物（验收提交件），与第三节需求级预期交付物（代码/数据/脚本）以节标题和作用区分。所有交付物当前状态均为 `PENDING`，业务功能尚未实现。

| 交付物名称 | 来源要求 | 主责任轨道 | 协作轨道 | 计划阶段 | 证据类型 | 当前状态 |
|-----------|---------|-----------|---------|---------|---------|---------|
| **综合测试报告** | 比赛方案及项目需求基线 | **E**（评测与报告统筹） | A、B、C、D（提供分模块测试证据） | D10–D15（待台账对齐后落定） | 评测脚本输出、评测报告（存放于 `evaluation/`）、麒麟 VM 日志（存放于 `evidence/`） | **PENDING**（业务代码未实现，评测尚未执行） |
| **效果演示** | 比赛方案及项目需求基线 | **C**（OS Agent Hook 与 QML 演示） | **E**（案例与业务验收） | D13–D15（待台账对齐后落定） | 截图、录屏、麒麟 VM 日志（存放于 `evidence/`） | **PENDING**（业务代码未实现，演示尚未执行） |
| **总体技术文档** | 比赛方案及项目需求基线 | 待项目负责人确认（拟全员供稿，指定统稿人，不得擅自指定 **A** 为唯一主责） | A、B、C、D、E | D3–D15 贯穿（待台账对齐后落定） | 技术文档（Markdown/PDF，存放于 `docs/`、`deliverables/`） | **PENDING**（文档尚未编写） |
| **用户手册** | 比赛方案及项目需求基线 | 待项目负责人确认（拟全员供稿，指定统稿人，不得擅自指定 **A** 为唯一主责） | A、B、C、D、E | D12–D15（待台账对齐后落定） | 用户手册（Markdown/PDF，存放于 `docs/`、`deliverables/`） | **PENDING**（文档尚未编写） |
| **真实场景案例** | 比赛方案及项目需求基线 | **E**（案例设计与业务验收） | **C**（OS Agent 集成验证） | D10–D15（待台账对齐后落定） | 案例文档（存放于 `datasets/`）、评测报告（存放于 `evaluation/`）、麒麟 VM 日志与截图（存放于 `evidence/`） | **PENDING**（案例尚未编写，评测尚未执行） |
| **银河麒麟适配报告** | 比赛方案及项目需求基线 | **D**（虚拟机成品化与发布） | — | D12–D15（待台账对齐后落定） | 适配报告（存放于 `deliverables/`）、麒麟 VM 日志与截图（存放于 `evidence/`） | **PENDING**（适配验证尚未执行） |

> **责任说明**：主责任轨道与协作轨道依据 `README.md` 责任轨道 A–E 划分。总体技术文档与用户手册的具体主责/统稿人在现有已批准台账与责任矩阵中未明确唯一主责，已标注「待项目负责人确认」。计划阶段以 D1–D15 相对日程占位，绝对日期待 `docs/project-management/README.md` 中的 15 天 75 项台账导入并与 D3 Gate 对齐后落定。

---

## 九、比赛性能指标追踪

四项指标及目标值来自比赛方案及项目需求基线。当前仓库中权威基线文档尚未导入，目标值待 D3 Gate 前以导入后的权威基线全文复核。当前状态均为 `UNVERIFIED`，未经真实评测环境执行，不得解读为已达标。

| 指标名称 | 目标值 | 来源 | 评测责任 | 协作轨道 | 证据类型 | 当前状态 |
|---------|--------|------|---------|---------|---------|---------|
| **偏好提取准确率** | ≥85% | 比赛方案及项目需求基线（待导入复核） | **E**（记忆业务与偏好评测） | **A**（Embedding 提取质量） | 评测脚本输出（存放于 `evaluation/`）、偏好评测报告（存放于 `evidence/`） | **UNVERIFIED**（目标基线值待 D3 Gate 前以导入权威基线复核；评测尚未执行） |
| **知识检索召回率** | ≥85% | 比赛方案及项目需求基线（待导入复核） | **B**（检索评测与 RRF） | **A**（Embedding 与索引质量） | 评测脚本输出（存放于 `evaluation/`）、检索评测报告（存放于 `evidence/`） | **UNVERIFIED**（目标基线值待 D3 Gate 前以导入权威基线复核；评测尚未执行） |
| **检索响应时间** | ≤500ms | 比赛方案及项目需求基线（待导入复核） | **B**（检索评测与性能优化） | **D**（IPC 性能与 SQLite 查询优化） | 评测脚本输出（存放于 `evaluation/`）、麒麟 VM 日志（存放于 `evidence/`） | **UNVERIFIED**（目标基线值待 D3 Gate 前以导入权威基线复核；评测尚未执行） |
| **知识冲突处理正确率** | ≥88% | 比赛方案及项目需求基线（待导入复核） | **B**（冲突检测与消解策略） | **E**（知识融合业务验证） | 评测脚本输出（存放于 `evaluation/`）、冲突处理评测报告（存放于 `evidence/`） | **UNVERIFIED**（目标基线值待 D3 Gate 前以导入权威基线复核；评测尚未执行） |

> **评测责任说明**：偏好提取准确率由 **E** 主责（记忆业务与偏好评测），**A** 协作为 Embedding 提取质量提供支撑。知识检索召回率、检索响应时间、知识冲突处理正确率由 **B** 主责（检索评测与排序质量），分别由 **A**、**D**、**E** 提供对应协作支撑。所有指标的目标值待 D3 Gate 前用导入后的权威基线全文复核。

---

## 十、计划窗口与 D3 Gate 约束

1. **D1–D3 阶段**：属于 Gate 形成与冻结阶段。此阶段的文档基线建立、赛题对照、架构评审、Gate 0 证据收集均独立有效，**不依赖 D3 Gate 通过才有效**。D1–D3 产出的基线文档与矩阵为本阶段产物，D3 Gate 评审的是其完整性与一致性。

2. **D4 及以后阶段**：正式开发、联调、评测与最终交付窗口以 **D3 Gate 通过** 为前置条件。D3 Gate 未通过前，D4+ 的正式开发与联调不得全面铺开；设计决策（ADR）可在 D3 前推进，但实现须待 Gate 决定后启动。

3. **D3 Gate 延迟处理规则**：
   - 登记阻塞原因与影响范围；
   - 评估对后续计划窗口的冲击；
   - 由项目负责人与轨道负责人人工重新排期，并更新 `docs/project-management/README.md` 中的 15 天 75 项台账。
   - **禁止自动顺延天数公式，禁止以程序化规则自动改写全体计划窗口**。

4. **D4+ 交付条件**：D3 Gate 通过后，D4–D15 的每个里程碑交付物仍须通过对应的 L0/L1/L2/L3 验证 Gate，方可视为完成。
