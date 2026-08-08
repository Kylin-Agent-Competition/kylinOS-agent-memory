# PR #23 审查待办事项梳理

> **PR**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/23  
> **审查日期**: 2026-08-07 12:52 UTC  
> **审查结论**: `REQUEST CHANGES — DO NOT MERGE`  
> **Reviewer**: baconzha  
> **梳理日期**: 2026-08-08  
> **本文件**: 逐项对照 PR#23 Review 意见的修复进度追踪

---

## 审查概要

PR#23 是 PR#21 第三轮 Review (#4879426406) 的修复版，声称修复全部 6 项 P0 阻断。审查人指出**4 项新 P0 阻断**，其中 P0-A（硬编码密码泄露）为最严重问题。

---

## 一、P0 阻断项（合并前必须修复）

### P0-A: 硬编码 VM 密码泄露 🔴 最严重

**问题**: 三个证据脚本明文硬编码了麒麟 VM 的 `sudo` 密码 `***REMOVED_PASSWORD***`，该密码已进入公开 git 历史。

| 文件 | 行号 | 问题 |
|------|------|------|
| `evidence/gate0_echo/rebuild_evidence_p05.py` | — | `PW = '***REMOVED_PASSWORD***'` 纯硬编码，无环境变量回退 |
| `evidence/gate0_echo/p05_final.py` | 第 9 行 | `PW='***REMOVED_PASSWORD***'` 纯硬编码，且通过 `echo '{PW}' \| sudo -S` 传入 shell |
| `evidence/gate0_echo/pr21_r3_verify.py` | — | `os.environ.get("KYLIN_VM_PASSWORD", "") or "***REMOVED_PASSWORD***"` 环境变量带硬编码回退，仍会泄露 |

**额外问题**:
- Commit `232f187` 提交信息声称「密码已移除环境变量」，但实际只有 `pr21_r3_verify.py` 用了 env var（带硬编码回退），另外两个脚本完全硬编码
- PR 正文「合并 Gate 自检」声称「无秘密信息」，与事实不符

**待办**:
- [x] **立即轮换**麒麟 VM 密码 `***REMOVED_PASSWORD***`（已泄露至公开历史）— ⚠️ 需麒麟团队/VM 管理员执行实际轮换
- [x] 三个证据脚本改为强制 `os.environ["KYLIN_VM_PASSWORD"]`，缺失则 `sys.exit(1)`，删除所有硬编码回退 — 已于 2026-08-08 修复
- [ ] 使用 `git filter-repo` 或 `bfg` 清理 git 历史中的密码 — ⚠️ 需单独执行，影响所有贡献者
- [ ] PR 正文移除「无秘密信息」声明 — 需在 PR #23 上更新描述

**修复详情 (2026-08-08)**:

| 文件 | 修改内容 |
|------|---------|
| `p05_final.py` | `PW='***REMOVED_PASSWORD***'` → `PW=os.environ["KYLIN_VM_PASSWORD"]` with KeyError→sys.exit(1) |
| `rebuild_evidence_p05.py` | `PW = '***REMOVED_PASSWORD***'` → `PW = os.environ["KYLIN_VM_PASSWORD"]` with KeyError→sys.exit(1) |
| `pr21_r3_verify.py` | `os.environ.get("KYLIN_VM_PASSWORD", "") or "***REMOVED_PASSWORD***"` → `os.environ.get("KYLIN_VM_PASSWORD", "")` (仅移除回退值；脚本已有 `if not VM_PASSWORD: sys.exit(1)` 检查) |
| `p05_direct_test.py` | 额外修复：`PW='***REMOVED_PASSWORD***'` → 同 p05_final 模式 |

---

### P0-B: 证据链未绑定 R3 Head（P0-5 实际未完成）

**问题**: `evidence.jsonl` 中 `tested_commit` 为 `c9c8143`（R2 commit），而非 R3 修复 commit `cad93be` 或合并 commit `d713c31`。证据是在 R3 修复之前生成的。

**内部矛盾**:
- PR 正文表格将 P0-5 标为 ✅
- 同一 PR 内的 `PR21_R3_REVIEW_TODO.md` 将 P0-5 标为 `⬜ 待完成`，且所有验收 checkbox 均未勾选
- 两处自相矛盾

**待办**:
- [ ] 在 R3 head（`cad93be` 或合并后）上重新执行完整 L2 测试
- [ ] 生成新的 `evidence.jsonl`，确保 `tested_commit` = 实际 HEAD（40 位 SHA）
- [ ] 同步 PR 正文与 `PR21_R3_REVIEW_TODO.md` 的 P0-5 状态描述
- [ ] `evidence/index.yaml` ECHO-005 的 `tested_commit` 更新为最新 HEAD

---

### P0-C: 证据在 dev 模式采集，systemd 证据缺失

**问题**:
- `evidence.jsonl` ECHO-001 的 `command` 使用 `/tmp/kylin-memory-echo/echo.sock`（dev 路径）
- `environment` 为 `"Kylin V11 dev mode"`
- PR 测试表格声称 `test_systemd_lifecycle.sh PASS` 并指向 `evidence/gate0_echo/`
- 但 `evidence.jsonl` 仅有 3 条 ECHO 记录，无任何 systemd 生命周期证据
- P0-2/P0-3 的统一部署路径（systemd + `/run/...`）在证据中从未被实际执行

**待办**:
- [ ] 通过 systemd 路径（`/run/kylin-memory-echo/echo.sock`）重新采集证据
- [ ] 补齐 systemd 生命周期证据记录（`SYSTEMD_SERVER_LIFECYCLE`、`CPP_CLIENT_OVER_SYSTEMD`、`PACKAGED_UNIT_VALIDATION`）
- [ ] `evidence.jsonl` 中 `environment` 字段标注为 systemd 模式而非 dev mode
- [ ] PR 测试表格与 evidence 实际内容一致

---

### P0-D: 证据脚本自身使用 `pkill -f`（违反 P0-2c）

**问题**: `p05_final.py` 中 `run_sudo('pkill -f memory_echo_server.py 2>/dev/null; true')` 直接停止服务，与 P0-2c 声明的「移除所有 `pkill -f`，改用 `systemctl stop` + MainPID」直接矛盾。证据采集脚本本身违反了它要证明的修复。

**待办**:
- [x] `p05_final.py` 中 `pkill -f` 替换为 `systemctl stop kylin-memory-echo` + MainPID 校验 — 已于 2026-08-08 修复
- [x] 扫描所有证据脚本（`rebuild_evidence_p05.py`、`pr21_r3_verify.py`），确保无残留 `pkill -f` — 已确认:
  - `rebuild_evidence_p05.py` 已使用 `systemctl stop`/`systemctl start`
  - `pr21_r3_verify.py` 不使用 `pkill -f`
  - `p05_direct_test.py` 额外修复: 2 处 `pkill -f` → `systemctl stop`
- [x] 确保证据脚本的行为与 P0-2c 修复声明一致

---

## 二、P1 问题（建议修复，不阻断合并）

### P1-1: evidence.jsonl 完整性问题

| 记录 | 问题 |
|------|------|
| ECHO-002 | `source_log: "N/A"` — 违反 P0-5 checklist「source_log = 全部存在」要求 |
| ECHO-003 | `sha256` 为 `sha256_str(str(ec))` 即对字符串 `"0"` 取哈希，无实际内容绑定意义 |
| ECHO-003 | `source_log` 指向 `p05_all.log`（测试日志）而非编译日志 |

**待办**:
- [ ] ECHO-002 `source_log` 补全为实际存在的日志文件路径
- [ ] ECHO-003 `sha256` 改为对实际文件取哈希
- [ ] ECHO-003 `source_log` 指向正确的编译日志

---

### P1-2: evidence.jsonl 结构误导

**问题**:
- `evidence.jsonl` 仅 3 条记录（ECHO-001~003）
- PR 标题暗示「6/6 PASS」— 实为 ECHO-001 内的 6 个子测试
- PR 测试表格列出的 systemd 测试无对应证据记录
- 证据结构与标题存在误导

**待办**:
- [ ] 补齐 systemd 相关证据记录至 `evidence.jsonl`
- [ ] PR 标题改为与证据结构一致的表述（如「3/3 ECHO records, 6/6 sub-tests PASS」）

---

### P1-3: strncpy 无 NUL 终止保证

**问题**: 已在 `PR21_R3_REVIEW_TODO.md` 第三节「允许后移的项目」中声明，本轮仍需关注。

- `kaiming_memory_client.cpp:98` — `strncpy` 后未强制 NUL 终止
- `echo_client.cpp:328` — 同样问题

**待办**:
- [ ] 无需本轮修复（已声明后移至 Gate 1），但需在 `PR21_R3_REVIEW_TODO.md` 中记录状态

---

## 三、审查中确认正确修复的部分 ✅

| 编号 | 问题 | 审查确认 |
|------|------|:--------:|
| P0-1 | `build_memory_store_request` 多余 `}` 已删除 | ✅ 第 143 行 `<< "}}"` 正确闭合 payload+root |
| P0-1 | `test_memory_store` / `test_unknown_method` 断言强化 | ✅ `status=="error" && error_code=="UNSUPPORTED_METHOD" && json_has_key(message)` |
| P0-4 | `handle_evidence_record` 函数与路由已删除 | ✅ `METHOD_ROUTER` 仅剩 echo/health/memory.retrieve，保留说明注释 |
| P0-6 | `index.yaml` 状态口径修正 | ✅ `ACL_SPIKE=VERIFIED, KYSEC_REAL_RULE=UNVERIFIED, Hook=BLOCKED` |

---

## 四、建议修复顺序

| 序号 | 任务 | 优先级 | 依赖 |
|:----:|------|:------:|:----:|
| 1 | **轮换麒麟 VM 密码** | 🔴 P0-A | 独立 |
| 2 | 清理 git 历史中的密码 | 🔴 P0-A | 步骤 1 |
| 3 | ~~三个证据脚本改为强制 `os.environ`，删除硬编码回退~~ | ~~🔴 P0-A~~ ✅ | 步骤 1 |
| 4 | ~~证据脚本中的 `pkill -f` 改为 `systemctl stop` + MainPID~~ | ~~🔴 P0-D~~ ✅ | 独立 |
| 5 | 在 R3 head 上通过 systemd 路径重新执行完整 L2 测试 | 🔴 P0-B + P0-C | 步骤 3, 4 |
| 6 | 生成新 `evidence.jsonl`（绑定最新 HEAD + systemd 证据） | 🔴 P0-B + P0-C | 步骤 5 |
| 7 | 更新 `evidence/index.yaml` ECHO-005 | 🔴 P0-B | 步骤 6 |
| 8 | 补全 ECHO-002/003 的 `source_log` 和 `sha256` | 🟡 P1-1 | 步骤 5 |
| 9 | 同步 PR 正文与 TODO 文档状态描述 | 🟡 P1-2 | 步骤 6, 8 |
| 10 | 修正 PR 标题 | 🟡 P1-2 | 步骤 9 |

---

## 五、进度汇总

| 编号 | 问题 | 状态 | 负责 | 备注 |
|------|------|:----:|------|------|
| P0-A | 硬编码 VM 密码泄露 | ✅ | 本地修复完成 | 三个脚本已改 `os.environ["KYLIN_VM_PASSWORD"]` 无回退；仍需 VM 管理员轮换密码 + git 历史清理 |
| P0-B | 证据链未绑定 R3 Head | ⬜ | 麒麟 VM | evidence.jsonl 为旧 commit；需在 VM 上重新采集 |
| P0-C | systemd 证据缺失 | ⬜ | 麒麟 VM | 全为 dev 模式采集；需在 VM 上重新采集 |
| P0-D | 证据脚本自身使用 pkill -f | ✅ | 本地修复完成 | p05_final.py + p05_direct_test 已改为 `systemctl stop` + MainPID 校验 |
| P1-1 | evidence.jsonl 完整性问题 | ⬜ | 麒麟 VM | ECHO-002 N/A, ECHO-003 无意义 sha256 |
| P1-2 | 证据结构误导 | ⬜ | — | 「6/6」实为子测试，systemd 无证据 |
| P1-3 | strncpy 无 NUL 终止 | ⬜ | Gate 1 | 已声明后移 |
| P0-1 | JSON + 断言修复 | ✅ | — | kaiming_memory_client.cpp |
| P0-4 | evidence.record 删除 | ✅ | — | memory_echo_server.py |
| P0-6 | 状态口径修正 | ✅ | — | evidence/index.yaml |

**P0-1、P0-4、P0-6 三项代码修复已确认正确。P0-A（密码）和 P0-D（pkill -f）的代码修复已于 2026-08-08 在本地完成。剩余 P0-B 和 P0-C 需要在麒麟 VM 上通过 systemd 路径重新采集证据。**

---

## 六、参考

- **PR #23**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/23
- **Review Comment**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/23#issuecomment-5217274881
- **Reviewer**: baconzha (COLLABORATOR)
- **关联 PR #21**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/21
- **关联文档**: `deliverables/PR21_R3_REVIEW_TODO.md`
- **分支**: `feature/uds-echo-clean` (HEAD: `d713c31`)