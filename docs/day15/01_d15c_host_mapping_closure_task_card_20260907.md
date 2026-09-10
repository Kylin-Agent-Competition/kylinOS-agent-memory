# C 轨任务卡：D15C Host Mapping 收口——Hook 证据采集、Production Identity 决策与 C→D Handoff

| 字段 | 内容 |
|------|------|
| 任务编号 | D15C（承接 C-HM 任务卡 S3~S6 剩余项；清偿 PR #151 PASS_WITH_DEBT 登记 C 轨债务） |
| 任务标题 | ① S3 Hook 观察点部署 + TD-008 Hook 点 A 确认；② S4 TD-007/009 三态 Tool 事件真实采集；③ production identity 决策输入；④ S6 C→D handoff；⑤ TD-007/008/009 与 R-ARCH-05 关闭提请 |
| 责任轨道 | C（刘承恩，台账口径）；Reviewer：D 主审；安全影响 E 补审 |
| 关联阻塞 | R-ARCH-05（High / In Progress）、TD-007、TD-008、TD-009（High / Open）、D14C Gate G4/G5（C 侧输入）、D12E 审计 B-7 |
| 建议排期 | D15（2026-09-07）单日窗口；**D14C formal L3（阶段 C/D）与 D 轨 ACTIVE 化评估依赖本卡产出**——比赛提交截止 2026-09-15，本卡是 C 轨收口关键路径 |
| 分支约定 | `feat/C-hook-evidence`（基于最新 main） |
| 编制日期 | 2026-09-06（D14 提前准备）；计划执行 2026-09-07（D15） |
| 初始状态 | `PREPARED` |
| 禁止提前表述 | `HOST_VERIFIED` / `L3 PASS` / `production ready`（正式 L3 结论归 D14C formal run） |

---

## 一、背景（为什么有这张卡）

### 1.1 C-HM 已交付与剩余债务（PR #151 PASS_WITH_DEBT 原文）

PR #151（合并提交 `8a405ae`）已交付 S1（TurnExtractionAdapter 骨架）、S2（ProductionSourceResolver）、V3-R（真实 schema 适配：RECORD + JSON blob，25 用例）、S5r2（真实 Chat DB harness 18/18 PASS）。登记在案的 C 轨剩余债务：

| 债务 / 后续项 | 状态 | 关闭条件 |
|----|------|----------|
| S3 / production identity | 未完成 | 部署 Hook 并确认其可稳定取得的行标识，再决定 production 使用 `ID`、`rowid` 或 Hook 标识；在此之前默认配置保持 fail-closed |
| TD-007 | High / Open | 源码 instrument 输出结构化 ToolExecutionEvent，覆盖成功、失败、取消三类 |
| TD-008 | High / Open | 源码 instrument / D-Bus 解码 / 真实 chatAsync 入参捕获确认 Hook 点 A 是否实现 memory_context 注入 |
| TD-009 | High / Open | 源码 instrument 确认实际 Tool 执行路径并输出结构化事件；主 Hook 不可行时验证 Route B |
| S4 GUI Tool 真实触发 | BLOCKED | 缓解 S4-BLOCK-001 后手动完成三类触发 |
| S6 C→D handoff | 未开始 | S5 完成后输出 trusted host identity 评估输入 |
| R-ARCH-05 | In Progress | S3、S4、S5/L3 证据与 handoff 均具备后申请关闭 |

### 1.2 D14C 对 C 轨的输入需求（跨卡对齐，不重做）

D14C（B 轨代执行，PR #156 任务卡）formal L3 的硬门中，两项直接依赖本卡产出：

- **G4（AI Assistant artifact 与 Host DB schema 已绑定）** ← 本卡 S3.4 identity 决策输入；
- **G5（trusted host identity 已批准）** ← 本卡 S6 handoff 备忘是 D 轨评估的必要输入。

工作项重叠对照（本卡产出直接供 D14C 消费，避免双轨重复采集）：

| D14C 工作项 | 本卡对应 | 说明 |
|----|----|----|
| D14C-07 真实 Tool 路径三态 | S4 | 同一批 GUI 采集事件，双卡引用同一证据包 |
| D14C-08 TD-008 注入点实证 | S3.3 | 同一 patch 扩展，同一结论 |
| D14C-04 真实正文 Resolver 验证 | （已完成于 S5r2，#151） | D14C 在干净 VM 复测，本卡不重做 |
| D14C-19 回退验证 | P1 回退演练 | 本卡演练一次，D14C 在 formal run 全量复核 |

### 1.3 既有资产（D4 阶段沉淀，直接复用）

- **Hook 点审计**：`evidence/l2-kylin-vm/d4_openkylin_remediation/tool_hook_audit.md`（2026-08-15，kylin-aiassistant @ `5a89601`）——出站 `SystemChat::sendToolMessage`（systemchat.cpp:692-755 → chatAsync）+ 回程 `CMsgPane::onRecvTool`（msgpane.cpp:1243，toolReply 信号唯一槽函数）已完整定位；
- **最小观察点 patch**：`tool_hook_patch.diff`（两文件三处插入）+ `tool_execution_observer.h`（header-only，无外部依赖，KyInfo 输出结构化 JSON）——头文件语法已通过，**尚未在真实宿主部署采集**；
- **已知宿主源码缺口**（observer 头文件注释登记）：`tool_call_id` / `source_trace_id`（toolReply 信号未携带）、`arguments`（仅出站可见）、`started_at`（需在 sendToolMessage 打点，patch 已含）、`cancelled`（宿主未显式建模）；
- **构建先例**：`tool_hook_build.log` / `build_make.log`（D4 曾在麒麟 VM 完成 patch 构建）；
- **VM 基础设施**：bacon VM（银河麒麟 V11 x86_64，Qt 5.15.19，SSH `172.19.224.1:2222`，用户 bacon）——真实 Chat DB（RECORD 表 + JSON blob）、kylin-aiassistant 运行时在位；`git archive` 离线上传路径已验证（VM 直连 GitHub 不稳定）。

---

## 二、范围

### 2.1 交付项

| # | 交付项 | 内容 | 依赖 |
|----|--------|------|------|
| S3.1 | 构建环境盘点与准备 | bacon VM 工具链核查（qmake / Qt5 dev 头 / make）、宿主源码 `5a89601` 离线上传、D4 构建命令复核 | 无（P0） |
| S3.2 | Hook patch 部署 + 冒烟 | patch + observer 编译部署（原二进制备份 + SHA-256 前后记录）、无 GUI 冒烟（日志格式行验证）、**回退演练一次** | S3.1 |
| S3.3 | TD-008 Hook 点 A 确认 | patch 扩展：`chatAsync` 入参捕获（sendMessage / sendToolMessage 两入口请求前 dump，敏感字段 redact）；普通对话真实触发一轮；结论三选一：`INJECTED` / `NOT_IMPLEMENTED_IN_HOST` / `AMBIGUOUS` | S3.2 |
| S3.4 | Production identity 决策输入 | Hook 触发时点与 RECORD 行写入时序对比（Hook 时刻只读查询 DB 的 msgIndex / rowid 分配）；产出 production sourceReference 标识建议（`rowid` vs `sessionID+msgIndex`）+ 依据数据。**只产出决策输入，默认值变更经 handoff 由 D 轨评审确认**（对齐 #151「不得以 fixture 推断 production 身份」） | S3.2 |
| S4 | TD-007/009 三态真实采集 | GUI 人工触发：成功态（图片生成/源文档正常完成）、失败态（断网/无效参数）、取消/中断态（观察宿主是否产生事件；无事件则登记宿主缺口，**禁止编造**）；每态录屏/截图 + 日志行 + SHA-256。TD-009 以同批事件作为「实际 Tool 执行路径结构化证据」（tool_call 出站 + toolReply 回程，非 OpenAI function-calling 风格） | S3.2 + 人工 GUI |
| S5r3 | 服务端全链路复测（**条件项**） | 仅当环境具备 memory-service 运行时栈：turn.finalized（test profile）→ resolver → 落库 → Chat DB 可查；否则登记 `BLOCKED_ON_SERVICE_RUNTIME`，不阻塞 S6 | 条件 |
| S6 | C→D handoff 备忘 | 汇总：TD-008 结论、identity 决策输入、三态事件样本格式、resolver 生产 config 建议、trusted host identity 评估所需全部 C 侧材料；载体 `docs/day15/02_d15c_c_to_d_handoff_memo_20260907.md` | S3.3/S3.4/S4 |
| S7 | 关闭提请 + 证据归档 | TD-007/008/009 → Resolved 提请（D 主审确认）；R-ARCH-05 收敛至「仅剩 D14C formal L3 输入」状态并视情况申请关闭；证据归档 `evidence/l2-kylin-vm/d15c_<UTC_RUN_ID>/` + `evidence/index.yaml` 登记 | S6 |

### 2.2 明确不做

- 不修改 `memory-service`（状态常量 / 注册逻辑 / Provider 契约——D 轨决定权）；
- 不重写 #151 已交付 Adapter/Resolver，不改 production 默认 config（保持 fail-closed）；
- 不代行 D 轨 trusted host identity 评估与 route ACTIVE 化（本卡只交输入）；
- 不执行 D14C formal L3、不写任何 `HOST_VERIFIED` / `L3 PASS` 结论（归 D14C formal run）；
- 不以 Mock / fixture / L0 数据推断宿主行为（所有宿主结论来自真实部署与真实触发）；
- 主演示 5 rounds（D14C-11）不在本卡——本卡证据供其消费。

---

## 三、红线（违反任一即停）

1. **原文隔离**：Hook 观察日志不落正文（正文仅 sha256 + 长度）；chatAsync 入参 dump 敏感字段一律 redact；
2. **fail-closed**：observer 已知缺口字段（tool_call_id / cancelled 等）留空标注，不编造值；取消态宿主无事件则登记 `NOT_OBSERVED + 宿主缺口`，不伪造第三态；
3. **不越权**：不改 `PRODUCTION_RESOLVER_STATUS`、不改注册门禁、production identity 默认值变更走 handoff → D 轨评审；
4. **宿主安全**：部署前备份原二进制（SHA-256 记录）、可一键回退、不留永久 patch / 测试残留（对齐 D14C-19 回退边界）；
5. **证据真实性**：GUI 人工操作须录屏或截图 + 日志行 + 时间戳 + SHA-256 同链归档；RUN_ID 隔离实验轮次；
6. **只读红线**：对宿主 Chat DB 的所有诊断查询一律只读（resolve 前后 SHA-256 比对，沿用 S5r2 方法）。

---

## 四、验收矩阵

| 层级 | 内容 | 预期 |
|------|------|------|
| L0 | memory-client 全量 ctest 回归（本卡不改客户端代码，防意外回归） | 13/13 套件全绿 |
| L2-Hook 部署 | patch 编译部署成功 + 冒烟日志格式验证 + 回退演练 | 原二进制还原后 SHA-256 一致且助手可启动 |
| L2-TD007 | 成功 / 失败 ≥2 态真实结构化 ToolExecutionEvent；取消态有明确结论（采集成功或缺口登记） | 字段齐（含宿主缺口标注）+ 证据链完整 |
| L2-TD008 | chatAsync 入参捕获结论 | INJECTED / NOT_IMPLEMENTED_IN_HOST / AMBIGUOUS 三选一 + 证据 |
| L2-TD009 | 实际 Tool 执行路径结构化事件 | 三态事件齐备前 TD-009 保持 `BLOCKED`；Route B 当前未激活，继续按 ADR-004 保留为备份 |
| L2-Identity | Hook 时序与 DB 行标识对比数据 | 决策建议 + 依据，无编造 |
| 证据 | `evidence/l2-kylin-vm/d15c_<UTC_RUN_ID>/` + index.yaml 登记（path / SHA-256 / tested_commit / environment / status） | 每项字段齐全；状态限 VERIFIED / FAILED / BLOCKED / UNVERIFIED |

---

## 五、施工步骤（时间序）

### P0 环境盘点（开工首查，决策走 P1 还是缓解路径）

- bacon VM 可达性 / qmake + Qt5 dev 头 / make 工具链核查；
- 宿主源码 `5a89601` 获取（本地 git archive 离线上传，路径已验证）；
- 复核 `tool_hook_build.log` 构建命令与产物形态；
- **决策点**：构建环境可用 → P1；不可用 → 六节缓解路径，如实登记 BLOCKED 状态，不静默降级。

### P1 S3.2 patch 部署 + 冒烟 + 回退演练

上传源码 + patch + observer 三件套 → 按 D4 命令编译 → 备份原二进制（SHA-256）→ 替换部署 → 冒烟（启动助手，验证 KyInfo 输出 `tool_execution_event` JSON 结构行）→ 回退演练一次（还原 → SHA-256 比对 → 助手可启动 → 再部署）。

### P2 S3.3 TD-008 chatAsync 入参捕获

patch 扩展（两入口请求前 dump + redact）→ 重新编译部署 → 普通对话真实触发一轮 → 分析入参 JSON：是否存在 `memory_context` / `context` / `history` 类注入字段 → 三选一结论 + 证据归档。

### P3 S3.4 identity 时序对比

GUI 触发一轮对话 → 在 onRecvTool 打点时刻只读查询 Chat DB（该 session 的 msgIndex / rowid 分配与 operateTime）→ 对比 Hook 事件时序 → 产出标识建议。

### P4 S4 三态 GUI 采集（人工）

成功态 / 失败态 / 取消态逐态采集；每态：录屏或截图 + 日志行提取 + SHA-256 + 时间戳，统一 RUN_ID 归档。取消态无事件则登记缺口。

### P5 S5r3 服务端全链路（条件项）

具备 service 运行时栈则执行 turn.finalized → resolver → 落库 → Chat DB 可查全链路；否则登记 `BLOCKED_ON_SERVICE_RUNTIME`。

### P6 S6 handoff 备忘

按 2.1 S6 清单编写 `docs/day15/02_d15c_c_to_d_handoff_memo_20260907.md`。

### P7 S7 关闭提请 + PR

TD-007/008/009 关闭提请（附证据链）→ R-ARCH-05 状态收敛申请 → 证据归档 + index.yaml 登记 → PR `feat/C-hook-evidence` → main。

---

## 六、外部依赖与缓解

| 编号 | 依赖 | 缓解路径 |
|------|------|----------|
| S4-BLOCK-001 | 真实 Tool 触发 GUI-only（Wayland 无 xdotool） | 人工操作 bacon VM 桌面，录屏佐证 |
| S4-BLOCK-003 | VM 缺 dev 包 / 无 sudo（KYSEC ostree-pkgs-guard） | P0 盘点：bacon VM 若工具链不齐 → 评估 D4 构建环境复用 / 离线 dev 包上传 / D14A 发布包构建机；均不可行则本卡 S3/S4 登记 BLOCKED + 更新 TD，不静默降级 |
| D 轨 | trusted host identity 评估（G5） | 本卡只交 handoff 输入，不等评估结果 |
| memory-service 运行时 | S5r3 条件项 | 无栈则登记 BLOCKED_ON_SERVICE_RUNTIME |

---

## 七、TD / R-ARCH-05 关闭判定（对齐登记原文）

| 项 | 关闭条件（登记原文） | 本卡口径 |
|----|---------------------|----------|
| TD-007 | 结构化 ToolExecutionEvent 覆盖成功、失败、取消三类 | 成功/失败实测；**取消态宿主未建模**：若实测无事件，按「成功/失败实测 + 取消缺口登记 + 替代判定建议」提请 D 主审裁量，不伪造第三态 |
| TD-008 | 确认 Hook 点 A 是否实现 memory_context 注入 | 三选一结论均为有效关闭输入（`NOT_IMPLEMENTED_IN_HOST` 本身即确认） |
| TD-009 | 确认实际 Tool 执行路径并输出结构化事件 | 三态证据（tool_call 出站 + toolReply 回程 + 取消态）齐备后才能关闭；当前回程 `BLOCKED`、取消 `NOT_OBSERVED`，Route B 保留为备份 |
| R-ARCH-05 | S3、S4、S5/L3 证据与 C→D handoff 均具备 | 本卡目标：收敛至「仅剩 D14C formal L3 输入」；若 S5r3/L3 未具备则保持 In Progress 并更新进展登记 |

---

## 八、PR 与证据约定

- 分支 `feat/C-hook-evidence` 基于最新 main；commit 遵循 `type(scope): description`（半角冒号）；原子提交（patch 扩展 / 证据 / handoff 备忘分提交）；
- PR 使用 `pull_request_template.md`，正文如实反映 HEAD（tested_commit / 证据清单 / 环境细节）；
- 证据：`evidence/l2-kylin-vm/d15c_<UTC_RUN_ID>/`，RUN_ID 隔离轮次；checksums.sha256 递归生成；index.yaml 登记 schema_version "1.1"，含 tested_commit 与 evidence_commit；
- 状态常量词汇表：`VERIFIED` / `FAILED` / `BLOCKED` / `UNVERIFIED` / `NOT_OBSERVED`；
- commit / push / PR / 合并均需用户明确指令。

---

## 九、执行进度登记（滚动更新）

| 步骤 | 状态 | tested_commit | 备注 |
|-------|------|---------------|------|
| P0 环境盘点 | **完成** | 5a89601 | bacon VM 可达，工具链齐备 (qmake+Qt5 dev+make)，DEVROOT 闭包构建 |
| P1 S3.2 部署+冒烟+回退演练 | **完成** | 5a89601 | 补丁二进制 SHA a712d541...，出站 tool_invocation JSON 验证；回退 SHA 86453fc6... 一致，助手可启动 |
| P2 S3.3 TD-008 | **BLOCKED** | 5a89601 | sendToolMessage payload 不含 memory_context；业务结论暂为 AMBIGUOUS；ChatSDK "model is empty" 阻塞升级 |
| P3 S3.4 identity | **BLOCKED** | 5a89601 | Hook 已证明可获得 outbound tool selector；Production Identity 为 UNRESOLVED/BLOCKED，DB 时序对比未执行 |
| P4 S4 三态采集 | **BLOCKED** | 5a89601 | 成功 VERIFIED(出站)，失败 NOT_OBSERVED（model is empty 为前置阻塞），取消 NOT_OBSERVED |
| P5 S5r3 服务端全链路 | **BLOCKED** | — | BLOCKED_ON_SERVICE_RUNTIME (条件项) |
| P6 S6 handoff 备忘 | **完成** | 5a89601 | `02_d15c_c_to_d_handoff_memo_20260907.md` 已生成 |
| P7 S7 关闭提请 + PR | 待开始 | — | 待用户指令 commit/push/PR |
