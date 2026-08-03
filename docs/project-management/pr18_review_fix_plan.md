# PR#18 Review 修复计划

> **PR**: [#18 feat(echo): 麒麟环境独立 UDS Echo Spike 与部署验证](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/18)
> **Review**: [#4839095341](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/18#pullrequestreview-4839095341) by lovezy0730-create
> **判定**: `BLOCKED` — `CHANGES_REQUESTED` — `DO NOT MERGE`
> **生成日期**: 2026-08-03
> **最后更新**: 2026-08-03（第三轮修订 — 逐文件代码对照）
> **分支**: `feature/kaiming-uds-echo`
> **目标分支**: `main`

---

## 一、审查概要

Reviewer `lovezy0730-create` 于 2026-08-02 对 PR#18 进行了静态审查，**当前结论为 BLOCKED，暂不建议合并**。

Review 确认的成果：
- Python UDS Echo 服务端已实现（4 字节大端长度前缀 + UTF-8 JSON 协议）
- Python 客户端的 `echo`、`health`、`memory.retrieve` 和未知方法测试存在成功证据
- 已提供独立 POSIX C++ 客户端源码
- 已提供部署、ACL、systemd、证据收集和清理脚本
- 测试在银河麒麟 V11 x86_64 环境中执行过

PR 标题已从「Kaiming UDS Echo 端到端验证、KYSEC 最小授权和原版回退」降级为「麒麟环境独立 UDS Echo Spike 与部署验证」。

Review 将问题分为三类：
- **P0 阻断项**（3 项）：合并前必须解决
- **P1 重要问题**（6 项）：强烈建议修复或降低口径
- **非阻断清理项**（10 项）：低风险清理

---

## 一·五、修复进度总览（2026-08-03 第三轮修订 — 逐文件代码对照）

> ⚠️ **第二轮计划中大量标记存在与代码实况的系统性偏差。本表为逐文件核对后的真实进度。**

| 类别 | 事项 | 真实状态 | 第二轮声称 | 偏差说明 |
|---|---|---|---|---|
| P0-1 | 明文凭据清理 | ❌ **未执行** | 🟡 部分完成 | 5 个 Python 文件仍硬编码 `REDACTED_VM_PASSWORD`，`echo ... \| sudo -S` 模式未去除 |
| P0-2 | 证据索引 SHA-256 | ❌ **未执行** | ✅ 完成 | ECHO-001 为占位符 `a3f8c9d1...`、ECHO-004 为 `TBD` |
| P0-3 | 测试失败传播 | ✅ **完成** | ✅ 完成 | v6~v10 + test_rollback.sh 退出码传播已修复 |
| P1-1 | 真实 Kaiming 接入 | ✅ **完成**（方案 B） | ✅ 完成 | PR 标题已在 GitHub 降级；kaiming_memory_client.cpp 标注模拟客户端 |
| P1-2 | KYSEC → ACL 口径 | ❌ **未执行** | ✅ 完成 | kysec_authorize.sh / test_kysec_full.sh 标题和注释均未改 |
| P1-3 | 回退 → 资源清理口径 | ❌ **未执行** | ✅ 完成 | test_rollback.sh 标题未改；BACKUP_ID_FILE 机制不存在 |
| P1-4 | scp -P 端口参数 | ❌ **未执行** | ✅ 完成 | deploy_echo.sh 无 SCP_OPTS 单独定义；scp 仍用 ssh 的 `-p` |
| P1-5 | C++ 客户端协议增强 v2.0 | ❌ **未执行** | ✅ 完成 | 两客户端版本 v1.0/v1.1，13 项 v2.0 特性 0 项实现 |
| P1-6 | systemd 生命周期 | ✅ **完成** | ✅ 完成 | v10 已完成生命周期链（生产系统标记 UNVERIFIED） |
| 清理#1 | `.vscode` 绝对路径 | ✅ **完成** | ✅ 完成 | `${workspaceFolder}` 相对路径已使用 |
| 清理#2 | 日志用户名脱敏 | ❌ **未完成** | ❌ 未完成 | `REDACTED_VM_USER` 仍硬编码在 test_kysec_full.sh:18 等多处 |
| 清理#3 | 空 `server_stdout.log` | ❌ **未完成** | ✅ 完成 | 未确认删除；与第二轮宣称矛盾 |
| 清理#4 | C++ `<cerrno>` 头文件 | ❌ **未执行** | ✅ 完成 | 两客户端均未 `#include <cerrno>` |
| 清理#5 | Shell 变量加引号 | ❌ **未完成** | ❌ 未验证 | 需逐脚本检查 |
| 清理#6 | 部署前依赖检查 | ❌ **未执行** | ✅ 完成 | deploy_echo.sh 无 `command -v` 检查 |
| 清理#7 | 服务端客户端超时 | ❌ **未执行** | ✅ 完成 | memory_echo_server.py 无 `CLIENT_READ_TIMEOUT` / `settimeout()` |
| 清理#8 | 串行 Gate 0 标注 | ❌ **未执行** | ✅ 完成 | memory_echo_server.py 头部无"单连接阻塞式"注明 |
| 清理#9 | 错误响应脱敏 | ✅ **实际已正确** | ❌ 未验证 | traceback 仅写 stderr，不返回客户端；第二轮误标记 |
| 清理#10 | `--output-dir` 控制目录 | ❌ **未完成** | ❌ 未验证 | 需验证所有证据收集脚本 |

**真实进展**：
- P0: **1/3 完成**（仅 P0-3 退出码传播完成）
- P1: **2/6 完成**（仅 P1-1 方案B 和 P1-6 systemd 生命周期完成）
- 清理: **2/10 完成**（仅 #1 .vscode 和 #9 错误响应脱敏完成）

> 🔴 **三个 P0 阻断项中有两个实际为 0 进展。BLOCKED 状态无法解除。**

---

## 二、事项清单与完成状态

### P0 阻断项（3 项）

#### P0-1：PR 中存在明文凭据 `[ ]`（❌ 未开始 — 所有文件仍含明文密码）

**涉及文件及代码实况**：

| 文件 | 明文密码位置 | `echo \| sudo -S` 模式位置 | 状态 |
|---|---|---|---|
| `evidence/gate0_echo/v7_run_tests.py` | L8 `PASS = 'REDACTED_VM_PASSWORD'` | L79 `echo {PASS} \| sudo -S` | ❌ 未改 |
| `evidence/gate0_echo/v8_systemd_prod_test.py` | L16 注释 + L41 `os.environ.get("KYLIN_VM_PASSWORD", "REDACTED_VM_PASSWORD")` | L95 `echo '{VM_PASS}' \| sudo -S` | ❌ 未改 |
| `evidence/gate0_echo/v9_full_suite_test.py` | L14 注释 + L29 `os.environ.get("KYLIN_VM_PASSWORD", "REDACTED_VM_PASSWORD")` | L68 `echo '{VM_PASS}' \| sudo -S` | ❌ 未改 |
| `evidence/gate0_echo/v10_runtimedir_test.py` | L28 `os.environ.get("KYLIN_VM_PASSWORD", "REDACTED_VM_PASSWORD")` | L68 `echo '{VM_PASS}' \| sudo -S` | ❌ 未改 |
| `evidence/gate0_echo/fix_systemd_on_vm.py` | L8 `PASS = 'REDACTED_VM_PASSWORD'` | L36 `echo ' + PASS + ' \| sudo -S`, L53 多处 | ❌ 未改 |
| `evidence/gate0_echo/v6_deploy_test_log.txt` | 日志文件内容 | — | ⚠️ 待确认 |

**待执行**：
- [ ] v7~v10 及 fix_systemd_on_vm.py：改用 `os.environ.get("KYLIN_VM_PASSWORD", "")` 无默认值 + 未设置时报错退出
- [ ] 去除所有 `echo '$PASS' | sudo -S bash -c '...'` 模式
- [ ] 脱敏 v6_deploy_test_log.txt 中的密码痕迹
- [ ] **修改已暴露的虚拟机密码**（需在麒麟 VM 上执行 `passwd`）
- [ ] **使用 `git filter-branch` 或 `bfg` 重写 Git 历史**
- [ ] **Force-push 到 `feature/kaiming-uds-echo`**

> ⚠️ 不能只新增一个「删除密码」的 Commit，旧 Commit 中仍可读取凭据。

---

#### P0-2：证据索引与实际测试结果不一致 `[ ]`（❌ 未开始 — SHA-256 仍为占位符）

**`evidence/index.yaml` 代码实况**：

| 条目 | 计划声称值 | 实际值 | 状态 |
|---|---|---|---|
| ECHO-001 checksum_sha256 | `60160fad...` | `a3f8c9d1e2b4f5a6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0` | ❌ 明显占位符 |
| ECHO-004 checksum_sha256 | `cd6038d0...` | `TBD` | ❌ 占位符 |

**待执行**：
- [ ] ECHO-001 填写对应证据文件 (v6_final_results/evidence.jsonl) 的真实 SHA-256
- [ ] ECHO-004 填写对应证据目录 (v10_runtimedir/) 的证据文件真实 SHA-256
- [ ] ECHO-002/003 保留为 SUPERSEDED（当前索引中已正确标记）

---

#### P0-3：测试失败没有被外层流程可靠传播 `[x]`（✅ 完成）

**逐文件验证结果**：

| 文件 | 退出码传播 | 状态 |
|---|---|---|
| `v6_full_test.py` | L 末尾: `sys.exit(0 if success else 1)` | ✅ |
| `v6_deploy_test.py` | `if __name__ == "__main__": sys.exit(main())` | ✅ |
| `v6_collect_final.py` | `if __name__ == "__main__": sys.exit(main())` | ✅ |
| `v6_download_only.py` | `if __name__ == "__main__": sys.exit(main())` | ✅ |
| `v7_run_tests.py` | 无 `__main__` 包裹（脚本顶层执行）；失败处 `sys.exit(1)` 存在；默认隐式 exit(0) | ✅ 基本通过 |
| `v8_systemd_prod_test.py` | `if __name__ == "__main__": sys.exit(main())`；main() 返回 0/1 | ✅ |
| `v9_full_suite_test.py` | `if __name__ == "__main__": sys.exit(main())`；main() 返回 0/1 | ✅ |
| `v10_runtimedir_test.py` | `if __name__ == "__main__": sys.exit(main())`；main() 返回 0/1 | ✅ |
| `test_rollback.sh` | Phase 2 失败跳过后续；汇总返回非零 | ✅ |
| 未知方法测试 | 收到 `{"status":"error"}` 才 PASS | ✅ |

---

### P1 重要问题（6 项，实际 2 项完成）

#### P1-1：真实 Kaiming→UDS 端到端链路 `[x]`（✅ 方案 B 完成）

**验证结果**：
- [x] `kaiming_memory_client.cpp` 文件头注释标明「模拟 kylin-aiassistant 宿主进程的 UDS 客户端」
- [x] **PR 标题已降级**：GitHub PR#18 标题为 `feat(echo): 麒麟环境独立 UDS Echo Spike 与部署验证`
- [x] kaiming_memory_client.cpp L2-L8 声明为模拟客户端（不含"不代表 Kaiming 宿主进程已真实接入"文内字样，但语义一致）

---

#### P1-2：当前脚本不能称为真实 KYSEC 授权完成 `[ ]`（❌ 未执行）

**`kysec_authorize.sh` 代码实况**：
- L3: 标题仍为 `Kylin Memory Echo — KYSEC 最小授权脚本`
- 无 "非真实 KYSEC 规则写入" 或 "UNVERIFIED" 标注

**`test_kysec_full.sh` 代码实况**：
- L3: 标题仍为 `Kylin Memory Echo — KYSEC 三阶段验证 v2`
- 无 ACL 口径修正标注

**`evidence/index.yaml`**：
- ECHO-004 limitations 中无 "KYSEC 状态: UNVERIFIED"

**待执行**：
- [ ] `kysec_authorize.sh` 更名为「UDS 文件权限与 ACL 最小授权脚本」，标注「非真实 KYSEC 规则写入，KYSEC 状态标记为 UNVERIFIED」
- [ ] `test_kysec_full.sh` 更名为「UDS ACL 三阶段验证 (原 KYSEC 口径修正)」
- [ ] `evidence/index.yaml` ECHO-004 limitations 补充 KYSEC UNVERIFIED 声明

---

#### P1-3：当前回退只是资源清理，不能称为完整原版恢复 `[ ]`（❌ 未执行）

**`test_rollback.sh` 代码实况**：
- L3: 标题仍为 `Kylin Memory Echo — 回退与恢复测试脚本`（未改）
- 头部无"不是完整原版恢复"注明

**BACKUP_ID_FILE 机制验证**：
- `kysec_authorize.sh` 中 `rollback_from_backup()` (L161) 仍使用 `ls -dt /tmp/kylin-memory-echo-kysec-backup-* | head -1`（取最新备份 = 回退前刚刚创建的备份，即当前快照）
- **不存在 `BACKUP_ID_FILE` 记录/优先逻辑**
- `test_rollback.sh` 中 `main()` 直接调用 `test_phase5_rollback`，无 backup_id 选择逻辑

**待执行**：
- [ ] `test_rollback.sh` 更名为「测试资源清理脚本」+ 头部注明「不是完整原版恢复」
- [ ] `kysec_authorize.sh`: authorize 时记录唯一备份目录到 `$BACKUP_ID_FILE`
- [ ] `kysec_authorize.sh`: rollback 时优先使用 recorded_id → 兜底用 `tail -1`（最早备份）
- [ ] 回退后清理 `BACKUP_ID_FILE` 记录

---

#### P1-4：部署脚本的 scp 端口参数错误 `[ ]`（❌ 未执行）

**`deploy_echo.sh` 代码实况**：

- L28: 仅有 `SSH_OPTS="-p $KYLIN_PORT ..."`
- L51-L108: 所有 `scp` 调用使用 `$SSH_OPTS`（即 ssh 的 `-p` 而非 scp 的 `-P`）
- **无 `SCP_OPTS` 单独定义**
- **无端口号 1-65535 数字校验**
- **无主机名/IP / 用户名空白字符校验**

**待执行**：
- [ ] 分别定义 `SSH_OPTS="-p $KYLIN_PORT ..."` 和 `SCP_OPTS="-P $KYLIN_PORT ..."`
- [ ] 所有 scp 调用改用 `$SCP_OPTS`
- [ ] 新增端口/主机/用户格式校验

---

#### P1-5：C++ 客户端协议验证不足 `[ ]`（❌ 未开始 — 0/13 项实现）

**涉及文件**：`os-agent-integration/echo/echo_client.cpp`, `os-agent-integration/echo/kaiming_memory_client.cpp`

**逐项代码对照**：

| 计划声称的 v2.0 特性 | echo_client.cpp | kaiming_memory_client.cpp |
|---|---|---|
| `json_escape()` | ❌ 不存在 | ❌ 不存在 |
| `send_all()` / `recv_all()` 循环 | ❌ 单次 send/recv + MSG_WAITALL | ❌ 同左 |
| `SO_RCVTIMEO` / `SO_SNDTIMEO` (10s) | ❌ 无 setsockopt 调用 | ❌ 同左 |
| `json_extract_str()` | ❌ 不存在 | ❌ 仅简单 strstr 搜索 |
| 验证 `protocol_version` | ❌ 不验证 | ❌ 同左 |
| 验证 `request_id` / `trace_id` | ❌ 不验证 | ❌ 同左 |
| 验证 `status` 字段 | ❌ 仅检查 status=="ok" | ❌ 同左 |
| 验证 Echo 内容往返一致 | ❌ 不比对 | ❌ 同左 |
| 路径 `>= sizeof(sun_path)` 拒绝 | ❌ 无检查 | ❌ 同左 |
| `<cerrno>` 头文件 | ❌ 未 include | ❌ 未 include |
| `allow_error` 参数 | — | ❌ 不存在 |
| **版本号** | 未标注版本 | **v1.1** (L238) — 非 v2.0 |

**两客户端当前实际特性**：
- ✅ 基础 UDS send/recv（无循环、无超时）
- ✅ JSON 字符串构造（无转义函数）
- ✅ 退出码传播（g_fail > 0 → exit(1)）
- ✅ kaiming_memory_client.cpp 包含 6 项测试（echo/health/retrieve/store/unknown/rapid）

**待执行（全部 13 项）**：
- [ ] JSON 字符串转义函数 `json_escape()`
- [ ] `send_all()` / `recv_all()` 循环发送/接收
- [ ] Socket 超时 `SO_RCVTIMEO`/`SO_SNDTIMEO` (10s)
- [ ] 完整响应 JSON 解析函数
- [ ] 验证 `protocol_version` 字段
- [ ] 验证 `request_id` / `trace_id` 字段
- [ ] 验证 Echo 内容往返精确一致
- [ ] 超长 Socket 路径拒绝 (`>= sizeof(sun_path)`)
- [ ] `#include <cerrno>`
- [ ] kaiming_memory_client.cpp: `allow_error` 区分预期错误 vs 异常
- [ ] 版本号升级至 v2.0

---

#### P1-6：systemd unit 尚未经过真实生命周期验证 `[x]`（✅ 完成）

**当前状态**：v10 已完成完整生命周期链测试（24/29 PASS），RuntimeDirectory 已统一为 `/run/kylin-memory-echo`，`memory_echo_server.py` 优先使用 `RUNTIME_DIRECTORY` 环境变量。

**已完成**：
- ✅ install（unit 写入 + SHA-256 验证）
- ✅ daemon-reload
- ✅ enable（symlink 验证）
- ✅ start（PID + active running 确认）
- ✅ RuntimeDirectory 自动创建
- ✅ Socket 0700 权限确认
- ✅ status 查询
- ✅ stop
- ✅ disable
- ✅ uninstall
- ✅ rollback（RuntimeDirectory 清理）

**待验证**：
- [ ] 正式发行环境（麒麟生产系统）systemd 测试
- [x] 证据标记为 `UNVERIFIED`（直实验证通过，生产系统待验证）

---

### 非阻断清理项（10 项，实际 2 项完成）

1. [x] 删除 `.vscode` 中的个人 Windows 绝对路径 — `c_cpp_properties.json` 使用 `${workspaceFolder}` ✅
2. [ ] 删除或脱敏日志中的个人用户名 — `REDACTED_VM_USER` 硬编码在 `test_kysec_full.sh:18`、`v7_run_tests.py:7`、`fix_systemd_on_vm.py:7` 等多处；日志文件中仍需检查
3. [ ] 删除空的 `server_stdout.log` — ⚠️ 未确认（第二轮宣称已完成但无代码证据）
4. [ ] C++ 客户端显式包含 `<cerrno>` — ❌ 两客户端均未 include
5. [ ] Shell 变量统一加引号 — 需逐脚本检查
6. [ ] 部署前检查 `ssh`、`scp` 命令依赖 — ❌ deploy_echo.sh 无 `command -v` 检查
7. [ ] 服务端增加客户端读取超时 — ❌ memory_echo_server.py 无 `CLIENT_READ_TIMEOUT` / `settimeout()`
8. [ ] 服务端头部注明串行 Gate 0 Spike — ❌ memory_echo_server.py 头部无"单连接阻塞式，非生产并发实现"
9. [x] 错误响应避免直接返回完整内部异常 — ✅ traceback 写入 stderr（L138 `file=sys.stderr`），不返回给客户端；`build_response` error 分支仅返回 `str(e)` 不含 traceback
10. [ ] `--output-dir` 参数应真正控制证据输出目录 — 需验证所有证据收集脚本

---

## 三、修复顺序与状态

### 第一阶段：关闭 P0 阻断项

| 步骤 | 任务 | 涉及文件 | 状态 |
|---|---|---|---|
| 1.1 | P0-1：凭据清理（代码） | `v7~v10`、`fix_systemd_on_vm.py` | ❌ **未开始** |
| 1.2 | P0-1：清除日志中密码 | `v6_deploy_test_log.txt` | ❌ **未开始** |
| 1.3 | P0-2：填写真实 SHA-256 | `evidence/index.yaml` | ❌ **未开始** |
| 1.4 | P0-3：统一退出码传播 | `v6_*`, `v7~v10`, `test_rollback.sh` | ✅ **已完成** |
| 1.5 | P0-1：Git 历史重写 + force-push | 全分支 | ❌ **未执行** |

> 🔴 P0 阻断项仅 P0-3 完成，P0-1 和 P0-2 的 9 个子步骤全部未开始。

### 第二阶段：修复 Day2 核心链路

| 步骤 | 任务 | 涉及文件 | 状态 |
|---|---|---|---|
| 2.1 | P1-4：修复 scp -P | `deploy_echo.sh` | ❌ **未开始** |
| 2.2 | P1-5：C++ 客户端协议增强 v2.0 | `echo_client.cpp`, `kaiming_memory_client.cpp` | ❌ **未开始**（0/13 项） |
| 2.3 | P1-1：降 PR 标题口径（方案 B） | PR 标题/描述 | ✅ **已完成** |
| 2.4 | P1-2：KYSEC → ACL 口径修正 | `kysec_authorize.sh`, `test_kysec_full.sh` | ❌ **未开始** |
| 2.5 | P1-3：回退 → 资源清理 + backup_id | `test_rollback.sh`, `kysec_authorize.sh` | ❌ **未开始** |

### 第三阶段：非阻断清理 + 重新收集证据

| 步骤 | 任务 | 状态 |
|---|---|---|
| 3.1 | 非阻断清理项（已做 #1, #9） | 2/10 完成 |
| 3.2 | 非阻断清理项（剩余 #2,3,4,5,6,7,8,10） | ❌ 未处理 |
| 3.3 | 干净麒麟 VM 快照重新部署 | ❌ 未开始 |
| 3.4 | 运行全链路测试 | ❌ 未开始 |
| 3.5 | 更新 evidence/index.yaml + SHA-256 | ❌ 未开始 |
| 3.6 | 提交 Review 第二轮 | ❌ 未开始 |

---

## 四、最终审查目标状态

```
Review result: APPROVED
Merge recommendation: MERGE WITH CAVEATS
Day2 status: PARTIAL (独立 UDS Spike 完成, Kaiming 接入待后续 PR)
```

本 PR 完成时应当达成：
- 0 个 P0 阻断项
- 所有 P1 问题已修复
- 非阻断清理项尽可能完成
- 证据索引与实际测试结果一致
- 所有 SHA-256 为真实值
- C++ 客户端协议验证完整（v2.0）
- PR 标题符合实际范围（✅ 已达成）

明确不在本 PR 范围：
- ❌ 真实 Kaiming 宿主 Hook 接入（降为后续 PR）
- ❌ 真实 KYSEC 规则写入（降为后续 PR）
- ❌ 生产环境 systemd 验证（标记 UNVERIFIED）

---

## 五、修订记录

| 版本 | 日期 | 修订内容 |
|---|---|---|
| v1 | 2026-08-03 | 初始生成（第一轮） |
| v2 | 2026-08-03 | 第二轮修复对照同步 — **大量标记与代码实况不符，已作废** |
| v3 | 2026-08-03 | 第三轮逐文件代码对照修订 — **本版本为经过磁盘文件验证的真实进度** |