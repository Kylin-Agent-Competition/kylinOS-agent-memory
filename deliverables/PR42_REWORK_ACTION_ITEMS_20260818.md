# PR #42 REWORK 整改任务清单（2026-08-18）

> 依据 PR #42 第二轮复审（Reviewer `lovezy0730-create`，CHANGES_REQUESTED/REWORK）。
> 本文档为工作对照清单：逐条列出「合并前必须完成事项」、修复位置、具体改法（from → to）与验证命令。
> 权威人员映射（依据 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` R-ARCH-05、`os-agent-integration/D2_C_宿主实验执行手册.md`、`scripts/d2c_evidence_collector.sh`）：
>
> - **周子腾 = D**（Reviewer 1 / IPC / SQLite / Outbox / VM 打包）
> - **谢嘉然 = E**（Reviewer 2 / 业务逻辑 / 安全 / 数据集）
>
> 整改规则：① `周子腾（E）` → `周子腾（D）`；② `E 决策` → `D 决策`（指周子腾）；③ 周子腾作为作者/决策人/冻结人时，其 Reviewer 必须是谢嘉然（E）——**作者不得自审**；④ 清理「待签署」与「已正式生效」并存的状态矛盾。

---

## 一、代码 L0 修复（Review「合并前必须完成事项 #1」）

### 1.1 deploy_hook.sh —— Shell 语法错误 ✅ 已修复
- 位置：`os-agent-integration/patches/deploy_hook.sh:126,130,131`（3 处未闭合字符串补 `"`）；`:95`（gcc 加 `-pthread`）
- 验证：`bash -n os-agent-integration/patches/deploy_hook.sh` → 已 PASS（退出码 0）

### 1.2 libconnect_hook.c —— 静态编译失败 + 线程安全 + 边界 ✅ 已修复
- 补 `#include <stddef.h>`（`offsetof`）、`#include <pthread.h>`（`pthread_once`）
- `g_initialized`/`ensure_initialized()` 改为 `pthread_once_t init_once = PTHREAD_ONCE_INIT;` + `pthread_once(&init_once, init_hook);`
- `connect()` 入口加前置边界检查：`if (addr == NULL || addrlen < offsetof(struct sockaddr_un, sun_path)) return real_connect(...);`
- 位置：`os-agent-integration/patches/libconnect_hook.c:33-34,48,72-73,106-112`

### 1.3 test_connect_hook.sh ✅ 已修复
- gcc 加 `-pthread`（`:103`）
- Test 8 重命名：`test_hook_abstract_socket` → `test_hook_non_matching_passthrough`，标题改为「Non-matching filesystem socket pass-through」（Review「安全与假实现审查 #2」）

### 1.4 CMakeLists.txt ✅ 已修复
- `find_package(Threads REQUIRED)` + `target_link_libraries(connect_hook PRIVATE dl Threads::Threads)`

### 1.5 ✅ 已修复：gcc 静态编译验证（L0 缺口已闭合）
- [x] `gcc -std=c11 -Wall -Wextra -fsyntax-only os-agent-integration/patches/libconnect_hook.c` → **PASS（退出码 0）**，麒麟 VM gcc 12.3.0（openKylin 12.3.0-1ok3k0.1）复验通过，无 warning/error；上传文件 SHA256 与本地一致（`c6031528…`）

---

## 二、Evidence 真实性修复（Review #2）

### 2.1 evidence/index.yaml —— GATE0-UT-002 状态 ✅ 已修复
- `status: HOST_VERIFIED → PARTIAL`；`runtime_result: PASS → PARTIAL`
- 保留 overall 10/12，核心 IPC 通信/恢复链路 PASS；明确 UT2-STOP / UT2-KILL9-STOP FAIL

### 2.2 evidence/index.yaml —— 剩余 2 处 reviewer（作者自审，已改）
- [x] `L513` `AGT-004-5.0.3-001`：`reviewer: "周子腾（E）"` → `reviewer: "谢嘉然（E）"`
- [x] `L621` `GATE0-UT-001`：`reviewer: "周子腾（E）"` → `reviewer: "谢嘉然（E）"`

### 2.3 UT-1/UT-2「未登记 index.yaml」过期描述（已改）
- [x] `deliverables/D4_GATE0_FORMAL_DECISION_20260817.md:40`：`⚠️ 未登记 index.yaml，见 §七` → 改为「已登记 `GATE0-UT-001`」
- [x] 同文件 `:87`：`> 注：UT-1/UT-2 结果尚未登记 index.yaml...` → 改为「已登记 `GATE0-UT-001`/`GATE0-UT-002`」
- [x] 同文件 `:209`：`UT-1/UT-2 证据未登记 index.yaml | ...审查后补登记` → 改为「✅ 已补登记 `GATE0-UT-001`（11/11）/`GATE0-UT-002`（10/12 PARTIAL）」
- [x] `deliverables/D4_BLOCKERS_SYNC_20260817.md:43`：`UT-1/UT-2 证据未登记 index.yaml | 未登记` → 改为「已登记 `GATE0-UT-001`/`GATE0-UT-002`」

---

## 三、D/E 身份统一（Review #4）

### 3.1 ADR（决策人/Reviewer 身份，已改）
| 文件 | 行 | 改法 |
|------|-----|------|
| `docs/adr/005-db-error-code-envelope.md` | 3 | `已采纳（E 决策...）` → `已采纳（D 决策...）` |
| 同上 | 5 | `决策人：周子腾（E）｜Reviewer：D（待签）` → `决策人：周子腾（D）｜Reviewer：E（谢嘉然，待签）` |
| 同上 | 122 | `E 决策选方案 A` → `D 决策选方案 A` |
| `docs/adr/006-db-idempotency-primary-key.md` | 3,5,117 | 同上 |
| `docs/adr/007-db-migration-baseline-naming.md` | 3,5,107 | 同上 |

### 3.2 冻结/需求/对照文档（`周子腾（E）` → `周子腾（D）`，已改）
| 文件 | 行 |
|------|-----|
| `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md` | 4, 74 |
| `deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md` | 7, 105, 125（另 3,81-83,92-94 的 `E 决策`→`D 决策`、`Reviewer D 待签`→`Reviewer E 待签`） |
| `deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md` | 4, 5, 250, 257-259, 342 |
| `deliverables/D4_DB_SCHEMA_V53_COMPARISON_20260817.md` | 4, 98 |
| `deliverables/D4_GATE0_FORMAL_DECISION_20260817.md` | 19, 49, 237 |
| `deliverables/D4_GATE0_MANUAL_REVIEW_CONCLUSION_FORM_20260817.md` | 15, 52, 111 |
| `deliverables/D4_GATE0_REVIEW_AGENDA_TEMPLATE_20260817.md` | 93 |
| `deliverables/D4_GATE0_SUPPLEMENTARY_REVIEW_20260816.md` | 4, 149 |
| `deliverables/D4_GATE0_AGENT_MODE_MANUAL_VERIFICATION_20260816.md` | 4, 113 |
| `deliverables/D4_BLOCKERS_SYNC_20260817.md` | 18-23, 68 |
| `evidence/l2-kylin-vm/d4_agent_mode_5_0_3_20260816/v5_3_fail_no_precipitate_evidence.md` | 6, 87 |

### 3.3 签名表 Reviewer 独立（已改）
- [x] `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md` 签名表：`冻结声明人 周子腾（E）` → `周子腾（D）`；Reviewer 行补 `E（谢嘉然，待签）`
- [x] `D4_DB_INITIAL_DESIGN_FREEZE_20260817.md` 签名表：`Reviewer 1 | D（指派）` → `E（谢嘉然，待签）`
- [x] `D4_GATE0_FORMAL_DECISION_20260817.md` 签名表：`审查主持人 周子腾（E）` → `周子腾（D）`；`Reviewer 1（D）` 自审冲突 → `Reviewer 1（E 谢嘉然，待签）`

---

## 四、冻结文档「待签署 vs 正式生效」矛盾（Review #4）

- [x] `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`：标题「**正式**冻结声明」与签名区「待确认」矛盾 → 标题改为「IPC 协议冻结声明（待 D/E 签署后正式生效）」+ 声明性质标注「待签署生效」；`✅ 正式冻结` 状态列改为 `✅ 协议冻结（待 D/E 签署后正式生效）`
- [x] `D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`：顶部「本声明已满足生效条件」改为「本声明尚未正式生效，待 E（谢嘉然）签署」；`Reviewer D 签署` → `Reviewer E（谢嘉然）签署`

---

## 五、PR #42 描述更新（Review #3）

- [x] 删除「L0: N/A / 无生产代码实现 / 不引入运行时代码 / 纯文档回滚」等失实表述
- [x] 改为如实说明包含：Hook C 实现（`libconnect_hook.c`）、Shell 部署脚本（`deploy_hook.sh`）、Hook 测试脚本（`test_connect_hook.sh`）、CMake 配置
- [x] 回填真实 L0 结果：`bash -n` 两脚本 PASS、`gcc -fsyntax-only` PASS（麒麟 VM gcc 12.3.0 复验通过）
- [x] 明确 `PR #42 ≠ Day4-D 实现完成`，属于「Gate0 / IPC Freeze / DB Design Freeze / Day4-D 前置条件收口」

---

## 验证命令汇总

```bash
# L0 静态检查（脚本）
bash -n os-agent-integration/patches/deploy_hook.sh
bash -n os-agent-integration/patches/test_connect_hook.sh

# L0 静态检查（C，需 Linux gcc：麒麟 VM 或 WSL 装 gcc）
gcc -std=c11 -Wall -Wextra -fsyntax-only os-agent-integration/patches/libconnect_hook.c
```

## 状态总览

| 分组 | 状态 |
|------|------|
| 一、代码 L0 | 5/5 完成（gcc 静态编译已在麒麟 VM 复验 PASS） |
| 二、Evidence 真实性 | 3/3 完成 |
| 三、D/E 身份统一 | 13/13 文件（约 40 处）完成 |
| 四、冻结生效矛盾 | 2/2 完成 |
| 五、PR 描述 | 1/1 完成 |
