# PR #42 第三轮复审整改任务清单（2026-08-19）

> 依据 PR #42 第三轮复审（Reviewer `lovezy0730-create`，CHANGES_REQUESTED/REWORK，提交于 2026-08-19 03:08 UTC）。
> Review 链接：https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/42#pullrequestreview-4968053558
>
> 本轮结论：**REWORK**（`BLOCKER = 0`，但 `HIGH ≠ 0`）。上一轮（第二轮，见 `PR42_REWORK_ACTION_ITEMS_20260818.md`）的大部分整改已确认为 **CLOSED**，本轮新增 4 个 HIGH 合并阻断项 + 2 个 MEDIUM + 1 个 LOW。
>
> **权威人员映射（唯一依据）**：
> - **周子腾 = D**（Reviewer 1 / IPC / SQLite / Outbox / VM 打包）
> - **谢嘉然 = E**（Reviewer 2 / 业务逻辑 / 安全 / 数据集）
>
> 整改规则：① 作者不得自审；② Freeze 文档在 Reviewer E（谢嘉然）正式签署前，全仓库状态必须统一为「内容定稿 / D 决策完成 / Reviewer E 待签 / 正式生效 = NO」，不得「待签署」与「正式冻结 / 已生效」并存。

---

## 状态总览

| 分组 | 项目 | 阻断 | 状态 |
|------|------|:----:|------|
| HIGH-01 | Hook README 架构前提失真（「闭源无源码」与 openkylin 调查结论冲突） | 是 | ✅ 已修复 |
| HIGH-02 | CMake `-fvisibility=hidden` 导致 `connect` 符号无法动态导出 | 是 | ✅ 已修复 |
| HIGH-03 | `deploy_hook.sh` clean-host 部署缺 `$REMOTE_BASE/share` | 是 | ✅ 已修复 |
| HIGH-04 | Freeze/Gate「待签署」与「正式生效」状态并存 | 是 | ✅ 已修复 |
| MEDIUM-01 | `D4_BLOCKERS_SYNC` #17/#18/#19 过期 OPEN 状态 | 否 | ✅ 已处理 |
| MEDIUM-02 | Gate 规则引用未入库的 AGENTS.md 作为唯一依据 | 否 | ✅ 已处理 |
| LOW-01 | 性能表述「热路径影响可忽略」无 benchmark | 否 | ✅ 已处理（PR 描述需手动更新） |

---

## 一、HIGH 合并阻断项（必须在当前 PR 修复）

### HIGH-01：Hook README 架构前提失真 🔴

**问题**：README 仍以「闭源无源码 → 只能 LD_PRELOAD」为架构依据，但同一 PR 的 `reviewDocuments/openkylin_blocker_survey.md` 已确认 `kylin-aiassistant` 在 openkylin 完全开源、含完整 C++ 源码、可源码审计/修改/编译，且 `D2-1-KAIMING-HOOK` 已解除 BLOCKED。两套架构依据互相冲突，不能在 Gate 0 / 架构冻结 PR 中并存。

**修复位置**：

| 文件 | 行 | 当前表述 | 改法 |
|------|----|---------|------|
| `os-agent-integration/patches/README.md` | 3 | `本目录存放对上游闭源组件（libkyai-assistant.so）的运行时拦截方案` | 去掉「闭源」定性，改为「低侵入拦截 / 验证方案」 |
| 同上 | 9 | `` `libkyai-assistant.so.1.0.0` 是…**闭源分发**（无 openkylin 源码） `` | 改为「源码可在 openkylin 获取（见 `reviewDocuments/openkylin_blocker_survey.md`）」 |
| 同上 | 11 | `无法在源码层修改` | 改为「LD_PRELOAD 定位为**低侵入验证 / 备用路线**：不修改当前宿主安装包即可快速验证；正式源码 instrument / 重编译链路闭环前的备用方案」 |
| 同上 | 85 | `闭源 .so 五维信息调查` | 同步修正为「openkylin 源码可获得性调查」 |
| `os-agent-integration/patches/libconnect_hook.c` | 8 | `无需修改闭源 libkyai-assistant.so` | 删除「闭源」，改为「无需修改当前已安装的 libkyai-assistant.so」 |

**验收**：全仓库不再出现「因闭源无源码所以必须 LD_PRELOAD」的表述；LD_PRELOAD 定位为「低侵入验证 / 备用路线」。

---

### HIGH-02：CMake `-fvisibility=hidden` 导致 `connect` 无法动态导出 🔴

**问题**：`CMakeLists.txt` 使用 `-fvisibility=hidden`，但 `connect()` 无 `__attribute__((visibility("default")))`，构建出的 `.so` 可能不导出 `connect` 动态符号，导致 LD_PRELOAD interpose 失效。手工 gcc 路径（无 `-fvisibility=hidden`）PASS 不能替代 CMake 路径验证。

**修复位置**：`os-agent-integration/patches/CMakeLists.txt:11`

二选一：
- **方案 A**：删除 `-fvisibility=hidden`
- **方案 B**：在 `libconnect_hook.c` 的 `connect()` 上显式加 `__attribute__((visibility("default")))`

**修复后必须验证**（在麒麟 VM 或 WSL 有 cmake/gcc 环境执行）：

```bash
cmake -S . -B build && cmake --build build
nm -D build/libconnect_hook.so | grep ' connect$'     # 期望: T connect
# 或
readelf -Ws build/libconnect_hook.so | grep -w connect
```

必须确认 `connect` 为可动态解析的导出符号（`T connect`），而非 LOCAL / hidden。

**验收**：`connect` 导出符号验证通过，回填真实命令与结果到 PR 描述。

---

### HIGH-03：`deploy_hook.sh` clean-host 部署缺 `$REMOTE_BASE/share` 🔴

**问题**：Step 1 只创建了 `lib` / `src/hook` / `logs/hook_tests`，但 Step 2 直接 `scp test_connect_hook.sh "$REMOTE_BASE/share/"`，未保证 `share` 存在。若此前未跑过 `deploy_echo.sh`，`share` 目录缺失导致部署失败。脚本宣称可独立部署，不应依赖隐式环境状态。

**修复位置**：`os-agent-integration/patches/deploy_hook.sh:48-53`（Step 1）

改为一次性创建自身需要的全部目录：

```bash
mkdir -p $REMOTE_BASE/bin
mkdir -p $REMOTE_BASE/lib
mkdir -p $REMOTE_BASE/share
mkdir -p $REMOTE_BASE/src/hook
mkdir -p $REMOTE_BASE/logs/hook_tests
```

**验收**：`bash -n os-agent-integration/patches/deploy_hook.sh` PASS；clean-host 下脚本自洽、不依赖 `deploy_echo.sh` 历史状态。

---

### HIGH-04：Freeze/Gate「待签署」与「正式生效」状态并存 🔴

**问题**：在 Reviewer E（谢嘉然）尚未正式签署前，仓库多处同时存在「正式冻结 / 已生效」与「Reviewer E 待签」的矛盾表述。

**修复位置与现状**：

| 文件 | 行 | 现状 | 改法 |
|------|----|------|------|
| `deliverables/D4_GATE0_FORMAL_DECISION_20260817.md` | 95 | `IPC 协议 FRZ-IPC-001~007 ｜ ☑ 正式冻结` | 改为「☑ 内容定稿，Reviewer E 待签，正式生效 = NO」 |
| 同上 | 237 | `审查主持人 ｜ 周子腾（D）｜ PASS_WITH_DEBT（已确认）` | 「已确认」与 Reviewer 待签并存 → 标注「D 决策完成，待 Reviewer E 签署」 |
| `deliverables/D4_BLOCKERS_SYNC_20260817.md` | 21 | `数据库冻结声明 v1.3 ｜ 已生效…Reviewer E 签署后转正式冻结` | 同一行「已生效」与「签署后才正式冻结」矛盾 → 改为「内容定稿 / 正式生效 = NO」 |
| 同上 | 58 | `IPC FRZ-IPC-001~007 ｜ 正式冻结` | 改为「内容定稿，Reviewer E 待签」 |
| PR 标题 / 正文 | — | 仍用「IPC 协议正式冻结 / 数据库初版设计冻结」 | 改为「内容定稿 / D 决策完成 / Reviewer E 待签 / 正式生效 = NO」口径 |

**需统一口径为**（Reviewer E 签署前）：

```text
内容定稿
D 决策完成
Reviewer E 待签
正式生效：NO
```

**至少检查并同步**：PR title/body、`D4_GATE0_FORMAL_DECISION_20260817.md`、`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`、`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`、`D4_BLOCKERS_SYNC_20260817.md`、ADR-005/006/007。

> 注：`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:3` 与 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:1,5` 已按「待签署生效」修正，方向正确，仅需清理其余位置（Gate 0 结论文档、Blockers Sync、PR 标题/正文）。

**验收**：全仓库不再存在「待签署」与「正式冻结 / 已生效」并存的表述。

---

## 二、MEDIUM（建议本轮一并处理，不单独阻断）

### MEDIUM-01：`D4_BLOCKERS_SYNC` #17/#18/#19 过期 OPEN 状态

**位置**：`deliverables/D4_BLOCKERS_SYNC_20260817.md:44-46`

当前仓库实际已完成（TD-DEPLOY-001 / TD-KYSEC-001 / TD-IPC-002~004 已登记、ADR-004 已建立、AGT-004 已更新为 PARTIAL），但同步表仍标「未登记 / 未写 / 未更新」。

| # | 现状 | 改法 |
|---|------|------|
| 17 | `TD-* 未入 TECHNICAL_DEBT_REGISTER.md ｜ 未登记` | 改为 `✅ CLOSED`，注明登记位置 |
| 18 | `ADR-004 无正式 ADR 文件 ｜ 未写` | 改为 `✅ CLOSED`，注明 `docs/adr/004-*` 路径 |
| 19 | `AGT-004 能力矩阵未更新 ｜ 未更新` | 改为 `✅ CLOSED`，注明已更新为 PARTIAL |

---

### MEDIUM-02：Gate 规则引用未入库的 AGENTS.md 作为唯一依据

**问题**：正式文档以「依据 AGENTS.md：D/E 为指定 Reviewer、作者不得自审」为唯一权限依据，但 `AGENTS.md` 被 `.gitignore` 忽略、不进仓库，其他成员无法仅凭仓库追溯规则。

**建议**：将这些规则引用到真正入库的项目治理文档（如 `CONTRIBUTING.md` 或 `docs/project-management/` 下的治理文档），`AGENTS.md` 仅作为本地 Agent 说明，不作正式 Gate 唯一权限依据。

**处置**：✅ 已处理 —— `CONTRIBUTING.md`「Review 规则」已补充 D/E 身份映射（D=周子腾，E=谢嘉然）与「作者不得自审」；三处正式文档引用已由「依据 AGENTS.md」改为「依据 CONTRIBUTING.md「Review 规则」」：`D4_BLOCKERS_SYNC:23`、`D4_GATE0_FORMAL_DECISION:241`、`D4_GATE0_MANUAL_REVIEW_CONCLUSION_FORM:115`。

---

## 三、LOW（不阻断）

### LOW-01：性能表述证据不足

**位置**：PR 描述

**现状**：`热路径影响可忽略` 无 benchmark 支撑。

**改法**：改为——「从静态实现看，首次调用增加 `pthread_once` 初始化，后续主要为地址类型与路径匹配判断，预计额外开销较小；当前尚未完成定量性能验证。」

**处置**：✅ 采用上述措辞；PR #42 描述需在 GitHub 手动更新为：

> 从静态实现看，首次调用增加 `pthread_once` 初始化，后续主要为地址类型与路径匹配判断，预计额外开销较小；当前尚未完成定量性能验证。

---

## 四、本轮已确认为 CLOSED 的项目（无需重复整改）

第三轮复审确认以下第二轮整改项已真实落地，视为 CLOSED：

| 项 | 状态 |
|----|------|
| `GATE0-UT-002` 整体状态改 `PARTIAL`（保留 10/12，UT2-STOP / UT2-KILL9-STOP = FAIL，核心 IPC 链路 = PASS） | ✅ CLOSED |
| `libconnect_hook.c` 补 `<stddef.h>` / `<pthread.h>`，`gcc -std=c11 -Wall -Wextra -fsyntax-only` PASS | ✅ CLOSED |
| `pthread_once` 线程安全初始化 | ✅ CLOSED |
| `addrlen` 前置边界检查（`addr == NULL || addrlen < offsetof(...)`） | ✅ CLOSED |
| `bash -n deploy_hook.sh` / `test_connect_hook.sh` PASS | ✅ CLOSED |
| Test 8 由 Abstract Socket 误标改为 non-matching filesystem socket passthrough | ✅ CLOSED |
| PR 不再宣称 `L0 N/A / 无运行时代码 / 纯文档回滚` | ✅ CLOSED |
| D/E 身份统一（周子腾 = D、谢嘉然 = E） | ✅ CLOSED |
| `PR #42 != Day4-D implementation complete` 边界明确 | ✅ CLOSED |

---

## 五、下一轮复审升级条件（PASS_WITH_DEBT 门槛）

作者关闭上述 4 个 HIGH 后，且确认无新增 HIGH / Evidence 回归，满足：

```text
BLOCKER = 0
HIGH = 0
L0 = PASS
Evidence = truthful
```

即可升级为 **PASS_WITH_DEBT**。

---

## 六、验证命令汇总

```bash
# HIGH-02：CMake 构建 + connect 符号导出验证（麒麟 VM / WSL）
cmake -S os-agent-integration/patches -B os-agent-integration/patches/build
cmake --build os-agent-integration/patches/build
nm -D os-agent-integration/patches/build/libconnect_hook.so | grep ' connect$'

# HIGH-03：Shell 语法回归
bash -n os-agent-integration/patches/deploy_hook.sh
bash -n os-agent-integration/patches/test_connect_hook.sh

# 全量 C 静态编译回归
gcc -std=c11 -Wall -Wextra -fsyntax-only os-agent-integration/patches/libconnect_hook.c
```

### 实际验证结果（2026-08-19，麒麟 VM gcc 12.3.0 / bash 5.2.21）

| 项 | 命令 | 结果 |
|----|------|------|
| HIGH-03 语法回归 | `bash -n deploy_hook.sh` | PASS（exit=0） |
| HIGH-03 语法回归 | `bash -n test_connect_hook.sh` | PASS（exit=0） |
| HIGH-01 C 静态编译 | `gcc -std=c11 -Wall -Wextra -fsyntax-only libconnect_hook.c` | PASS（exit=0） |
| HIGH-02 完整编译 | `gcc -shared -fPIC -O2 -pthread -ldl -Wall -Wextra -o libconnect_hook.so libconnect_hook.c` | PASS（exit=0） |
| HIGH-02 符号导出 | `nm -D libconnect_hook.so | grep -w connect` | `T connect`（默认可见性导出成功） |
| HIGH-02 CMake 构建 | `cmake -S . -B build && cmake --build build` | **PASS（exit=0）**，cmake 4.4.2（用户侧安装 tarball） |
| HIGH-02 CMake 产物导出 | `nm -D build/libconnect_hook.so | grep -w connect` | `T connect`（`GLOBAL DEFAULT` 可见性） |

> 说明：HIGH-02 采用方案 A（删除 `-fvisibility=hidden`）。CMake 构建（`cmake -S . -B build && cmake --build build`，exit=0）与手工 gcc 路径均确认 `connect` 以 `GLOBAL DEFAULT` 可见性导出为 `T connect`（`nm -D` 与 `readelf -Ws` 双重确认），LD_PRELOAD interpose 所需动态符号导出验证通过。cmake 4.4.2 位于 `/home/kylin-agent/下载/cmake-4.4.2-linux-x86_64/bin/cmake`（tarball 安装，未入 PATH）。

---

## 七、参考

- **PR #42**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/42
- **第三轮复审**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/42#pullrequestreview-4968053558
- **第二轮复审整改清单**: `deliverables/PR42_REWORK_ACTION_ITEMS_20260818.md`
- **分支**: `feature/d4-gate0-review-freeze`（HEAD: `a5293a5`）
