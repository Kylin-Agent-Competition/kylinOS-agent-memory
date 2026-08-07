# PR18 Round1 Issue #18: Kaiming KillMe 进程关系信息缺失（已知技术债）

> **TD 编号**: TD-PR18-R1-18
> **创建日期**: 2026-08-06
> **来源**: PR18 Round1 审查结论
> **严重度**: 🟡 MEDIUM — 不阻塞 Gate 0 合并，但须在 Gate 1 (Day2 真实 Hook) 前完成
> **状态**: DEFERRED — 延期至 Gate 1 处理
> **责任人**: TBD (待 PR21 合并后分配)

---

## 问题描述

在 PR18 Round1 审查中，审查者记录了 Kaiming `KillMe` 进程关系中 `/proc/<pid>/xxx` 信息缺失的问题。审查结论标记为"预期弃用"，但**从未创建正式 Task 或 AdR 记录**。

### 缺失的信息

- `/proc/<pid>/cmdline` — Kaiming 宿主进程的完整命令行
- `/proc/<pid>/cwd` — Kaiming 宿主进程的当前工作目录
- `/proc/<pid>/environ` — Kaiming 宿主进程的环境变量（含 `XDG_RUNTIME_DIR`、`DBUS_SESSION_BUS_ADDRESS` 等关键变量）
- `/proc/<pid>/fd` — 已打开的文件描述符（用于验证 UDS Socket 是否已被 Kaiming 打开）
- `/proc/<pid>/maps` — 内存映射（用于验证是否正确加载 .so）

### 影响

1. **D2-1 Kaiming Hook 验证**: 缺少 `/proc/<pid>/fd` 信息导致无法通过进程级验证确认 UDS Socket 是否被 Kaiming 实际使用（当前只能通过独立 echo_client 模拟验证）
2. **环境基线完整性**: 环境基线中缺少宿主进程的完整运行时上下文，限制了问题排查能力
3. **回退验证**: 无法在回退后通过 `/proc/<pid>/maps` 验证是否完整卸载 Hook 层

---

## 延期原因

1. Kaiming 为闭源二进制，其 `KillMe` 进程管理接口的完整文档不可获取
2. D2-1 Kaiming Hook 已完成路线 B 调查报告（`evidence/gate0_echo/d2_1_evidence/`），确认宿主编译环境不可达
3. `/proc/<pid>/xxx` 信息采集需在**麒麟 VM 运行时**由人工执行，已超出当前 PR21 范围

---

## 后续计划 (Gate 1)

1. 在麒麟 VM 运行时采集完整的 `/proc/<pid>/xxx` 信息
2. 将采集结果补充到环境基线证据（`evidence/gate0_echo/final/environment.log`）
3. 创建自动化脚本 `scripts/collect_kaiming_proc_info.sh` 用于标准化采集
4. 评估是否需要实现 Kaiming Hook 真实性断言（基于 `/proc/<pid>/fd` 中是否存在 UDS Socket FD）

---

## 关联文档

- `evidence/gate0_echo/d2_1_evidence/D2_1_Final_Evidence_Report.md` — D2-1 Kaiming Hook 路线 B 调查报告
- `deliverables/PR18_ROUND2_REMEDIATION_CHECKLIST.md` — PR18 Round2 修复清单
- `deliverables/PR21_REVIEW_ACTION_ITEMS.md` — PR21 审查 Action Items（前置阻塞项 B）

---

## 变更历史

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-08-06 | 初始创建，作为 PR21 合并前提条件 | Cline (PR21 Round2 Review) |