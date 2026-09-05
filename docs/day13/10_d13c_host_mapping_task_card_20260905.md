# C 轨原子任务卡：Host mapping 解除 — TurnExtractionAdapter + Production Resolver + Trusted Host Identity

| 字段 | 内容 |
|------|------|
| 任务编号 | C-HM（原子任务，非台账日任务；承接 D12E 合并后审计 `docs/day12/15` B-7 handoff） |
| 任务标题 | 解除 `BLOCKED_BY_HOST_MAPPING`：① 实现 C 轨 `TurnExtractionAdapter`（真实正文通道）；② 源码 instrument 关闭 TD-007/008/009；③ 配合 D 轨 trusted host identity 与 production resolver ACTIVE 化评估 |
| 责任轨道 | C（刘承恩，台账口径）；Reviewer：D 主审；安全影响 E 补审 |
| 关联阻塞 | R-ARCH-05（High / In Progress）、TD-007、TD-008、TD-009（High / Open）、D12E 审计 B-7 |
| 建议排期 | D13 剩余窗口启动，**D14-C（L3 干净 VM 发布回归）开工前完成主体**——D14-C 要求「执行 AI 助手 + MemoryClient + 主演示」真实通过，依赖本任务 |
| 分支约定 | `feat/C-host-mapping`（基于最新 main） |

---

## 一、背景（为什么有这张卡）

### 1.1 当前阻塞状态（main@896c067 实查）

```
C 轨 TurnExtractionAdapter 不存在（memory-client src/tests 零命中）
        ↓
真实正文通道（source_reference → 原文）无 production 实现
  （source_resolver.py:109 PRODUCTION_RESOLVER_STATUS = "BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED"）
        ↓
turn.finalized / event.ingest / forget.* production 默认不注册 → UNSUPPORTED_METHOD
        ↓
① D 轨 3 个写方法无法 ACTIVE（FRZ-IPC-007 路由表 CANDIDATE）
② D13C D-L2-07~10（turn.finalized 写 Chat DB、stop_reason/retry_of_turn_id 透传、
   finalization_reason 顶层）无法在麒麟 VM L2 验证
③ D14-C「AI 助手真实执行 + 主演示」验收面收窄
```

### 1.2 已有进展（R-ARCH-05 登记，不重做）

- Socket 重定向（LD_PRELOAD connect hook）VM 验证 3/3 PASS（2026-08-15）。
- Tool Result Hook 调用链审计完成：Hook 点 = `CMsgPane::onRecvTool` / `SystemChat::sendToolMessage`。
- 最小观察点 patch 已实现，头文件语法通过。
- 参考：`reviewDocuments/openkylin_blocker_survey.md`、`deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md`。

### 1.3 已知外部阻塞（预先登记，非本卡引入）

| 编号 | 阻塞 | 缓解路径 |
|------|------|----------|
| S4-BLOCK-001 | 真实 Tool 触发为 GUI-only（Wayland 无 xdotool，dbus 无消息注入） | 手动操作麒麟桌面触发；或补 X11 + xdotool 自动化 |
| S4-BLOCK-003 | VM 缺 ~40 个 -dev 包 + 无 sudo | `sudo apt-get build-dep kylin-aiassistant` 或带完整 dev 依赖的构建环境 |

---

## 二、范围

### 2.1 交付项 ①：C 轨 `TurnExtractionAdapter`（事件契约 v1 §7 五边界）

依据 `docs/day3/11_os_agent_event_contract_v1.md` L237-244 冻结的边界定义：

1. 以 C++ `event_id` 生成 Provider 候选的 `source_event_id` 关联；
2. 传递 `session_id`、`occurred_at`、`collected_at` 及真实来源类型；
3. **只通过受控 `source_reference` resolver 取得用户/助手正文**，不在 C++ 事件、普通日志或临时 JSON 复制正文（原文隔离红线）；
4. 通过 `tool_call_ids` 和受控 Tool Result resolver 组装 Provider `tool_results`，不把模型自述当真实执行结果；
5. 提供生产 resolver 与纯内存测试 resolver，**不修改 `memory-service` Provider 契约**。

实现形态（与 memory-client 现有 D5~D11 架构对齐）：

- `memory-client/src/adapters/turn_extraction_adapter.{h,cpp}`：从宿主麒麟 AI 助手 Chat 数据源提取 TurnFinalizedEvent 所需的 `source_reference` + 元数据（**不含正文**）；
- `memory-client/src/adapters/production_source_resolver.{h,cpp}`：受控 resolver，按 `source_reference` 从宿主 Chat DB / Hook 观察点读取正文，结果仅进入 `turn.finalized` payload 的 `original_user_text` 落库路径；
- 未命中 / 无权限 / 宿主不可读 → fail-closed（resolver 返回空，客户端按 INTERNAL_ERROR 语义走 `requestFailed`，**禁止编造正文、禁止空串替代**，对齐 ADR-010 §INSERT 语义）。

### 2.2 交付项 ②：源码 instrument 关闭 TD-007 / TD-008 / TD-009

| TD | 关闭条件（登记原文） | 对应施工 |
|----|---------------------|----------|
| TD-007 | 源码 instrument 输出结构化 ToolExecutionEvent（trace_id、tool_name、arguments、status、result、error、started_at、finished_at），覆盖成功、失败、取消三类 | 在已定位 Hook 点（`CMsgPane::onRecvTool` / `SystemChat::sendToolMessage`）部署最小观察点 patch，真实 Tool 触发（GUI 手动）下采集三类事件 |
| TD-008 | 通过源码 instrument、D-Bus 解码或真实 chatAsync 入参捕获确认 Hook 点 A 是否实现 memory_context 注入；strstr 外部观察只能得出 NOT_OBSERVED | Hook 点 A（请求前）chatAsync 入参捕获，确认注入通道存在性与字段 |
| TD-009 | 源码 instrument 确认实际 Tool 执行路径并输出结构化事件；OS Agent 设计并验证替代 Hook 方案 | 非 OpenAI 风格 Tool 路径的事件采集；若主 Hook 不可行，验证 ADR-004 已批准的 Route B 备用路径 |

产出：每项 TD 附麒麟 VM L2 证据（log + SHA-256 + index.yaml 登记），由 D 主审确认后改 Resolved。

### 2.3 交付项 ③：配合 D 轨 ACTIVE 化评估（本卡不代行）

- C 轨产出 `TurnExtractionAdapter` + production resolver 就绪证据（L2）后，向 D 轨 handoff；
- D 轨评估 `trusted host identity`（生产 resolver 注册的信任边界）+ FRZ-IPC-007 路由表 `turn.finalized` / `event.ingest` / `forget.*` 从 `CANDIDATE / BLOCKED_BY_HOST_MAPPING` 升级 `ACTIVE`；
- `source_resolver.py` 的 `PRODUCTION_RESOLVER_STATUS` 常量更新属 D 轨 PR，C 轨不改 `memory-service`。

### 2.4 范围外（本卡不做）

- 不修改 `memory-service` 任何文件（Provider 契约、resolver 常量、handler 注册均 D 轨范围）。
- 不修改已冻结契约：FRZ-IPC-001~007、ADR-010/014/019、事件契约 v1 字段。
- 不修改官方 SDK 头文件、不写 `/usr`、不覆盖官方 .so（与 D12-A 红线一致）。
- 不处理 B 轨 gateway `memory.retrieve` 检索主链接线（`docs/day13/09` 登记的 6 项 BLOCKED，独立阻塞线）。
- 不代行 D Reviewer 对 TD-013/014/015/017/016/060 的关闭确认。

---

## 三、禁止修改范围（红线）

1. **原文隔离**：正文只经受控 resolver 进入落库路径；C++ 事件、QML、日志、异常消息、临时 JSON 任何位置不得复制正文（ADR-010 契约要点、SEC-1 口径）。
2. **fail-closed**：resolver 未命中返回 None/空 → INTERNAL_ERROR（safe）；禁止编造正文、禁止以空串替代（`turns.original_user_text NOT NULL` 冻结语义）。
3. **不越权升级状态**：本卡交付前，`turn.finalized` 等方法保持 `UNSUPPORTED_METHOD`；PR/文档不得出现「真实正文通道已支持」「HOST_VERIFIED」提前表述。
4. **宿主安全**：KYSEC 最小授权、原版回退路径保留；修改版 AI 助手安装/回退证据留档。
5. **证据真实性**：L2 必须麒麟 VM 真实链路；WSL/沙箱结果不得标注 HOST_VERIFIED。

---

## 四、交付物清单

| # | 交付物 | 类型 |
|---|--------|------|
| 1 | `memory-client/src/adapters/turn_extraction_adapter.{h,cpp}` | 新增 |
| 2 | `memory-client/src/adapters/production_source_resolver.{h,cpp}`（含 fail-closed 语义） | 新增 |
| 3 | `memory-client/src/adapters/memory_source_resolver.h`（resolver 接口 Protocol，对齐 ADR-010 seam） | 新增 |
| 4 | `memory-client/tests/test_turn_extraction_adapter.cpp`：L0 契约测试（元数据传递、原文隔离断言、fail-closed、tool_results 组装不采信模型自述） | 新增 |
| 5 | `memory-client/tests/CMakeLists.txt`：注册新测试到 ctest | 修改 |
| 6 | Hook 观察点 patch（宿主源码 instrument，产出物走独立交付目录，不进 `/usr`） | 新增 |
| 7 | TD-007/008/009 关闭证据包：麒麟 VM L2 log + SHA-256 + `evidence/index.yaml` 条目 | 新增 |
| 8 | `docs/day13/10_d13c_host_mapping_task_card_20260905.md`：本卡 | 新增 |
| 9 | C→D handoff 备忘：ACTIVE 化评估输入清单（就绪证据 + 边界声明） | 新增 |

---

## 五、测试矩阵

| 层级 | 内容 | 预期 |
|------|------|------|
| L0 | ctest：`turn_extraction_adapter`（新）+ memory-client 全量回归（10 套件） | 全绿，含 D13C S1-S6 |
| L1 | QML Demo 不回归：VerticalLinkPage / D5~D11 Demo 套件 | 全绿 |
| L2 | ① Adapter→resolver→MockGateway 全链路（test profile）；② 麒麟 VM 真实 Chat 数据源：turn.finalized 落库含真实 `original_user_text`，Chat DB 可查；③ TD-007 三类 Tool 事件（成功/失败/取消，GUI 手动触发）；④ TD-008 Hook 点 A 注入确认；⑤ TD-009 备用路径验证 | 各项 PASS + 证据归档 |
| 回退 | 修改版 AI 助手 → 原版恢复 | 回退成功证据 |

---

## 六、技术债关联

| 条目 | 本卡动作 |
|------|----------|
| R-ARCH-05（High/In Progress） | 主体施工对象；完成后 VM 内编译 + Socket 指向 Memory Service + 完整 ToolResultEvent 链路跑通 → 关闭 |
| TD-007 / TD-008 / TD-009（High/Open） | 交付项 ② 逐项关闭（D 主审确认） |
| D12E 审计 B-7 | 本卡即其建议的「后续原子 Task」 |
| TD-016 / TD-060 | 不动（D Reviewer / D-E 协同范围） |
| 新增候选 | 若 S4-BLOCK-001/003 仍阻塞 L2 → 登记新 TD（含缓解路径与负责人），不静默降级 |

---

## 七、验收标准

1. **功能**：麒麟 VM 真实链路 `宿主 Chat 数据 → TurnExtractionAdapter → source_reference → production resolver → turn.finalized → Chat DB 落库` 端到端 PASS，`original_user_text` 为真实正文且仅经受控 resolver 通道。
2. **隔离红线**：L0/L2 均有「正文不出现在 C++ 事件 / 日志 / 异常消息」的显式断言。
3. **fail-closed**：resolver 未命中场景返回 INTERNAL_ERROR（safe），无编造/空串替代路径。
4. **TD 处置**：TD-007/008/009 附 L2 证据并经 D 主审确认关闭；R-ARCH-05 满足登记关闭条件。
5. **回归**：memory-client ctest 全绿（含新增套件）；不破坏现有 10 套件。
6. **状态口径**：C 轨交付时 `turn.finalized` 等仍为 `CANDIDATE`（ACTIVE 化由 D 轨后续 PR 执行）；本卡 PR 描述如实标注 L2 已验证面与未验证面。

---

## 八、执行顺序建议（原子拆分）

| 步 | 内容 | 依赖 |
|----|------|------|
| S1 | resolver 接口 + TurnExtractionAdapter 骨架 + L0（Mock 数据源） | 无 |
| S2 | production resolver 对接宿主 Chat DB 读取（只读、受控路径） | S1 |
| S3 | Hook 观察点 patch 部署 + TD-008 Hook 点 A 确认 | S4-BLOCK-003 缓解（dev 包） |
| S4 | TD-007 三类 Tool 事件采集（GUI 手动触发） | S3 + S4-BLOCK-001 缓解 |
| S5 | 麒麟 VM L2 全链路 + 证据归档 + TD 关闭提请 | S2 + S4 |
| S6 | C→D handoff 备忘 → D 轨 ACTIVE 化评估 | S5 |

---

## 九、执行进度与发现（滚动更新）

### 9.1 进度

| 步 | 状态 | 提交 | 说明 |
|----|------|------|------|
| S1 | 完成 | `f0778e1` | TurnExtractionAdapter 骨架 + L0（13 用例，纯内存 resolver） |
| S2 | 完成 | `a8b78df` | ProductionSourceResolver（fixture SQLite L0，16 用例）；发现并规避 Qt 5.15 `QSQLITE_OPEN_READONLY=TRUE` 带值形式回退读写模式的缺陷 |
| S3/S5 首轮 VM 回归 | 部分 | `6581d2f` | 见 `evidence/l2-kylin-vm/pr151_vm_test_report_20260905.md`；ctest 12/12、Hook 集成 20 PASS、QML 构建 OK；S3 patch 部署/TD-008 确认/S5 全链路未完成，发现 4 项（见 9.2） |
| V1/V2 修复 | 完成 | `0764118` | QML Qt 5.12 兼容修复 + `qml_pages_load` 全量加载 L0 回归（见 9.2） |
| S4 | 未开始 | — | 依赖 S4-BLOCK-001 缓解 |
| S6 | 未开始 | — | 依赖 S5 完成 |

### 9.2 首轮 VM 回归发现与处置

VM 环境：银河麒麟 V11 x86_64（Qt 5.12）；报告：`evidence/l2-kylin-vm/pr151_vm_test_report_20260905.md`。

| # | 发现 | 处置 |
|---|------|------|
| V1 | `VerticalLinkPage.qml:96` ColumnLayout `bottomPadding`：QtQuick.Layouts 的 padding 属性自 Qt 5.15 起才有，VM（Qt 5.12）加载即退出 255；CI（Qt 5.15.3）全绿——`d11c_qml_load` 仅覆盖 D11 页面，其余 QML 文件无任何加载覆盖 | **已修复（`0764118`）**：BehaviorObserve / ManualConfig / ToolAdapter / VerticalLink 四页面 padding 改 `x/y/width` + 末尾 spacer；新增 `test_qml_pages_load`（qrc 内全部 14 个 QML 文件逐个 `QQmlComponent` 编译加载断言 `status==Ready`），堵住「CI 绿但低版本 Qt 加载失败」盲区。已知局限：Qt 版本特性差异仍以 VM L2 为准 |
| V2 | `ManualConfigPage.qml:118` SpinBox `suffix`：QtQuick.Controls 2（Qt 5.x）无该属性（Controls 1 / Qt 6 才有），编译即 Error；`main.qml` 因引用该页类型连带失败——**该页面此前在任何环境（含 CI）都未成功加载过**，由新测试首次暴露 | **已修复（`0764118`）**：移除 `suffix`，单位改独立 `Label` |
| V3 | 真实宿主 Chat DB 与 S2 假设 schema 不匹配：实际 `RECORD(ID, sessionID, msgIndex, message, operateTime)`，**无 role / turn_id 列**；且当前 0 条 RECORD、0 session | **登记待办（不盲改）**：表名 / ID 列 / 正文列可经 `ProductionSourceResolverConfig` 覆盖；但 ① 无 role 列无法区分用户消息与 assistant 终稿、② sessionID 为会话级而非 turn 级——查询模型扩展须以真实数据确认 msgIndex 角色编码与 turn 划分规则为前提。fail-closed 原则下无真实数据不推断，S5 复测前置 = VM 产生真实对话数据，或从 kylin-aiassistant 源码确认 RECORD 写入逻辑 |
| V4 | `memory-service` 的 `PRODUCTION_RESOLVER_STATUS` 保持 `BLOCKED_BY_HOST_MAPPING` | **符合预期**（红线 §三.3，非缺陷）：C 轨不改 memory-service |

### 9.3 S5 复测前置条件（汇总）

1. V3 schema 确认（真实数据样本或源码级 RECORD 写入逻辑）；
2. S4-BLOCK-003 缓解：VM dev 包与构建环境（S3 patch 编译部署前置）；
3. S4-BLOCK-001 缓解：GUI 手动 Tool 触发方案（TD-007 三类事件采集前置）；
4. 本轮 QML 修复在 VM 复跑 QML smoke 实测确认（修复依据 Qt 5.12 兼容性分析，以 VM 实测为准，不提前标注 HOST_VERIFIED）。

---
*任务卡编制：2026-09-05｜依据：D12E 合并后审计 `docs/day12/15` §B-7、事件契约 v1 §7、ADR-010、TD Register R-ARCH-05/TD-007~009、台账 D14-C 依赖分析*
