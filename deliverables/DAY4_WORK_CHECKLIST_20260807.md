# Day 4 工作清单 — 2026-08-07

- **生成时间**：2026-08-07T15:55+08:00
- **依据**：`D4_GATE0_FORMAL_DECISION_20260807.md`、`D4_IPC_PROTOCOL_FREEZE_20260807.md`、`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`、`PR21_R3_REVIEW_TODO.md`、`evidence/index.yaml`
- **当前分支**：`feature/d4-gate0-review-freeze`
- **基线 Commit**：`ceb64e6`

---

## 一、今日已完成项（签字确认）

以下工作已在今日早些时候完成，需审查人（你）做正式确认签字：

### 1.1 Gate 0 人工审查 — 已完成，待你签字
- [x] 5 项待裁决事项全部裁决完毕 → `D4_GATE0_FORMAL_DECISION_20260807.md`
- [x] 技术债登记 6 项（TD-DEPLOY-001, TD-KYSEC-001, TD-IPC-002~004, R-ARCH-05）
- [x] ADR-004 替代架构批准记录
- [x] Gate 0 总表：全部四项 PASS 或 PASS_WITH_DEBT
- [ ] **待你签字的项**：
  - [ ] 确认部署 ECHO-009 PASS_WITH_DEBT 裁决
  - [ ] 确认 KYSEC PASS_WITH_DEBT 裁决（最低可接受标准是否合理）
  - [ ] 确认原文隔离 PASS 裁决（UT-1 11/11）
  - [ ] 确认真实 Tool Result 替代架构路线批准（ADR-004）
  - [ ] 确认 UDS IPC PASS_WITH_DEBT 裁决
  - [ ] 确认 D4 BLOCKED 状态解除

### 1.2 IPC 协议冻结 — 已完成，待你签字
- [x] 长度前缀 JSON 线协议 → FRZ-IPC-001
- [x] 错误码枚举 (4项) → FRZ-IPC-002
- [x] protocol_version "1.0" → FRZ-IPC-003
- [x] deadline_ms 字段与语义 → FRZ-IPC-004
- [x] 幂等方案（设计冻结） → FRZ-IPC-005
- [x] JSON 请求/响应顶级字段 → FRZ-IPC-006
- [x] 方法路由表 (5项活跃) → FRZ-IPC-007
- [ ] **待你签字的项**：
  - [ ] 确认 7 项冻结对象的冻结范围与禁止变更条款
  - [ ] 确认 DEFERRED 项（压缩层/多路复用/心跳/连接池/流式/双向流）合理

### 1.3 数据库/部署/失败路由冻结（设计冻结层）— 已完成，待你签字
- [x] 部署路径与目录约定 → FRZ-DEP-001~004
- [x] 数据库初版 Schema (5表) → FRZ-DB-001
- [x] 失败路由策略 → FRZ-DB-002~004
- [x] 幂等写入策略 → FRZ-DB-005
- [x] 核心配置项 (8项) → FRZ-CFG-001
- [ ] **待你签字的项**：
  - [ ] 确认设计冻结层级（D4-D 实现后升级为严格冻结）
  - [ ] 确认 7 项已知缺口的技术债编号与计划

---

## 二、PR21 R3 麒麟 VM 证据链重建（今日核心推动）

依据 `PR21_R3_REVIEW_TODO.md`，代码层面修复已全部完成，剩余工作集中在麒麟 VM：

### 2.1 在麒麟 VM 上执行 pr21_r3_verify.py
- [ ] SSH 连接麒麟 VM（使用 kylin-ssh-connect skill）
- [ ] 传输最新代码（含所有 P0-1~4, P0-6 修复）
- [ ] 在最新 Head 上执行 `pr21_r3_verify.py`
- [ ] 验证 6/6 PASS（KAIMING-ECHO/HEALTH/RETRIEVE/STORE/UNKNOWN/RAPID）
- [ ] STORE 确认 `status=error, error_code=UNSUPPORTED_METHOD`
- [ ] UNKNOWN 确认 `status=error, error_code=UNSUPPORTED_METHOD`

### 2.2 P0-5：重建证据链
- [ ] 生成新的 `evidence.jsonl`（绑定最新 Head Commit SHA）
- [ ] 更新 `evidence/index.yaml` ECHO-005：
  - [ ] `tested_commit` → 新的实际 Head (40位 SHA)
  - [ ] `evidence_commit` → 与 tested_commit 一致
- [ ] 确保四处一致：原始运行日志 / evidence.jsonl / evidence/index.yaml / PR 正文
- [ ] ECHO-009 FAIL 通过重新构建+部署解决
- [ ] 更新 PR 标题和正文

### 2.3 P1 自检清单（在麒麟 VM 上执行）
- [ ] P1-A：全部 .sh/.py/.cpp 静态检查通过
- [ ] P1-B：干净 CMake 构建通过
- [ ] P1-C：协议验证 6/6 PASS
- [ ] P1-D：systemd 验证（PACKAGED_UNIT_VALIDATION / SYSTEMD_SERVER_LIFECYCLE / CPP_CLIENT_OVER_SYSTEMD）
- [ ] P1-E：全链路部署验证（deploy → build → bin → Unit → start → Client → stop → uninstall）
- [ ] P1-F：证据验证（tested_commit / evidence.jsonl / source_log / sha256 / index 全部一致）
- [ ] P1-G：未完成项状态声明已修正 ✅ (已完成)

---

## 三、前置依赖清理

### 3.1 权威基线资料入库与版本复核
- [ ] 确认 4 份基线文档最新版本已入库：
  - [ ] `01_sdk_capability_boundary.md` (v1.1)
  - [ ] `02_architecture_sop.md` (v1.1)
  - [ ] `03_environment_config_manual.md`
  - [ ] `04_agent_usage_guide.md`
- [ ] 版本号与 `D4_开工前置条件清单_20260806.md` 中一致

### 3.2 能力矩阵不一致修正（附录 A 3 项）
- [ ] IPC-001 (UDS 可访问性)：UNTESTED/E0 → HOST_VERIFIED/E4
- [ ] AGT-005 (Memory Context 注入)：UNTESTED/E0/E2 → PARTIAL/E4
- [ ] AGT-004 (真实 Tool Result)：PARTIAL/E2/E4 → PARTIAL/E4(模拟) + BLOCKED(真实Hook)

---

## 四、产出清单（今日完成后应具备）

| # | 产出物 | 当前状态 | 今日目标 |
|---|-------|---------|---------|
| 1 | Gate 0 正式结论（签字段） | 文档已写，待你签字 | **签字确认** |
| 2 | IPC 协议冻结声明（签字段） | 文档已写，待你签字 | **签字确认** |
| 3 | 数据库/部署/失败路由冻结声明（签字段） | 文档已写，待你签字 | **签字确认** |
| 4 | 更新后的 evidence/index.yaml | tested_commit 仍为旧 SHA | **绑定新 Head** |
| 5 | 新的 evidence.jsonl | 依赖 VM 执行 | **生成** |
| 6 | 更新后的 PR21 标题和正文 | 依赖 evidence | **更新** |
| 7 | 能力矩阵修正 | 3 项不一致 | **修正** |

---

## 五、建议执行节奏

```
┌─ 现在 (15:55) ─────────────────────────────────────────────┐
│                                                              │
│  步骤 A【15min — 你可以独立完成】                              │
│  ├── 审查并签字 Gate 0 正式结论（§一.1.1）                     │
│  ├── 审查并签字 IPC 协议冻结（§一.1.2）                        │
│  ├── 审查并签字 数据库/部署/失败路由冻结（§一.1.3）             │
│  └── 产出：签字后的 Gate 0 PASS/REWORK/BLOCKED 记录             │
│                                                              │
│  步骤 B【30min — 需麒麟 VM 接入】                              │
│  ├── 修正能力矩阵 3 项不一致（本地文件编辑）                     │
│  ├── 权威基线资料版本复核（检查 4 份文档）                       │
│  └── 产出：修正后的能力矩阵 + 基线版本记录                       │
│                                                              │
│  步骤 C【60-90min — 需麒麟 VM】                                │
│  ├── SSH 连接麒麟 VM                                          │
│  ├── 传输代码 + pr21_r3_verify.py 执行                        │
│  ├── 生成新 evidence.jsonl + 更新 index.yaml                  │
│  ├── P1 自检清单逐项执行                                       │
│  └── 产出：完整证据链（四处一致）                               │
│                                                              │
│  步骤 D【15min】                                              │
│  ├── 更新 PR21 标题/正文                                       │
│  ├── 推送分支 + 更新 PR                                       │
│  └── 产出：Gate 0 PASS 最终记录 + 共享契约基线                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 六、关键决策记录（供你参考签字）

| 决策点 | 裁决 | 风险 |
|-------|------|------|
| 部署 ECHO-009 FAIL → PASS_WITH_DEBT | 接受 PARTIAL，D4-D 修复构建顺序 | 部署流程未闭环 |
| KYSEC UNVERIFIED → PASS_WITH_DEBT | 登记技术债，最低标准 ACL+标注 | 无真实 KYSEC 规则验证 |
| 原文隔离 UNTESTED → PASS | UT-1 11/11 已验证 | 生产隔离链路待 D4+ 验证 |
| 真实 Tool Result → 替代架构批准 | 路线 B：Qt 演示壳 + 日志 Adapter（源码已在 openkylin 开源可获取，待 VM 内编译验证） | 集成风险 R-ARCH-05（降低，源码可审计） |
| UDS IPC PARTIAL → PASS_WITH_DEBT | 核心链路通过，3 项缺口登记技术债 | 权限/超时/重连待 D4 补齐 |