# UNTESTED 测试项登记与进度跟踪表

- **来源文档**：`deliverables/D4_GATE0_MANUAL_REVIEW_CHECKLIST.md`
- **整理日期**：2026-08-07

---

## 汇总登记表

| 序号 | 测试项 | 当前状态 | 裁决/测试计划 | 责任人 | 完成日期 | 结果 |
|------|--------|---------|-------------|-------|---------|------|
| UT-1 | 原文隔离（独立测试） | UNTESTED | 需编写独立用例或从 R1/R2 推定 | | | |
| UT-2 | OS 重启复测（IPC） | 未覆盖 | 需安排麒麟 VM 重启验证 | | | |
| UT-3 | IPC-001 能力矩阵修正 | UNTESTED→HOST_VERIFIED | 直接引用 ECHO-003 证据修正 | | | |
| UT-4 | AGT-005 能力矩阵修正 | UNTESTED→PARTIAL | 引用 R1+R2 部分通过证据 | | | |
| S1-BLOCK-001 | peony-menu-plugin 编译失败（缺 dev包） | BLOCKED | 需 sudo install libpeony-dev + libgsettings-qt-dev；主程序编译成功，不影响阶段2-5 | 刘承恩/周子腾 | | |

---

## 详细说明

### UT-1：原文隔离（独立测试用例）

- **所属模块**：2.2 Memory Context 注入与原文隔离
- **当前状态**：UNTESTED — 无独立测试用例
- **关联待裁决项**：待裁决项 #3，是否可从 R1/R2 间接推定为 PASS_WITH_DEBT
- **参考**：`D4_GATE0_MANUAL_REVIEW_CHECKLIST.md` § 2.2

### UT-2：OS 重启复测（IPC）

- **所属模块**：2.4 Kaiming → UDS IPC
- **当前状态**：未覆盖 — 无 OS 重启复测证据
- **参考**：`D4_GATE0_MANUAL_REVIEW_CHECKLIST.md` § 2.4

### UT-3：IPC-001 (UDS 可访问性)

- **所属模块**：附录 A 能力矩阵
- **当前标记**：UNTESTED / E0
- **建议修正**：HOST_VERIFIED / E4
- **依据**：UDS Echo 全链路在麒麟 VM 通过（ECHO-003 UDS PASS）

### UT-4：AGT-005 (Memory Context 注入)

- **所属模块**：附录 A 能力矩阵
- **当前标记**：UNTESTED / E0/E2
- **建议修正**：PARTIAL / E4
- **依据**：R1 PASS + R2 6/6 模拟通过，原文隔离仍 UNTESTED
