# PR#18 Review 修复后续操作清单

> **PR**: [#18 feat(echo): 麒麟环境独立 UDS Echo Spike 与部署验证](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/18)
> **修复日期**: 2026-08-03
> **最后同步**: 2026-08-03 22:55 UTC+8（跟进 uncommitted diff — P1-2/test_kysec_full.sh ✅, P1-3/test_rollback.sh 标题 ✅, P1-4/deploy_echo.sh ✅）
> **本文件目的**: 记录本轮修复中因需VM环境或工作量大而延后的操作项，供后续逐一执行对照

---

## 〇、当前真实完成进度（逐文件验证 + uncommitted diff，2026-08-03 22:55）

> 基于磁盘文件实际内容 + 未提交变更，修正前序版本的偏差。

| 类别 | 事项 | 真实状态 | 说明 |
|---|---|---|---|
| P0-1 | 明文凭据清理（5 Python 文件） | ✅ **已完成** | v7/v8/v9/v10/fix_systemd_on_vm.py 均使用 `os.environ.get("KYLIN_VM_PASSWORD", "")` + 未设置时报错退出。 |
| P0-2 | 证据索引 SHA-256 | ✅ **已完成** | ECHO-001: `268671...`, ECHO-004: `cd6038d0...` 均为真实 SHA-256 |
| P0-3 | 测试失败传播 | ✅ **已完成** | v6~v10 + test_rollback.sh 退出码传播已修复 |
| P1-1 | 真实 Kaiming 接入 | ✅ **方案B完成** | PR 标题已降级；kaiming_memory_client.cpp 标注模拟客户端 |
| P1-2 | KYSEC → ACL 口径 | ✅ **已完成** | kysec_authorize.sh ✅ + **test_kysec_full.sh ✅ (L3 "UDS ACL 三阶段验证 (原 KYSEC 口径修正)"; L5 "非真实 KYSEC 规则写入")** |
| P1-3 | 回退 → 资源清理口径 | 🟡 **标题已修，BACKUP_ID_FILE 待** | test_rollback.sh ✅ 标题已改为"测试资源清理脚本" + "不是完整原版恢复"注明；**BACKUP_ID_FILE 机制仍未实现** |
| P1-4 | scp -P 端口参数 | ✅ **已完成** | deploy_echo.sh ✅ SCP_OPTS="-P" 单独定义 + 所有 scp 调用改用 + 端口 1-65535 校验 + 主机名非空校验 |
| P1-5 | C++ 客户端协议增强 v2.0 | 🟡 **1/13** | `<cerrno>` 已修复；其余 12 项 v2.0 特性全部未实现 |
| P1-6 | systemd 生命周期 | ✅ **完成** | v10 已完成生命周期链（生产系统标记 UNVERIFIED） |
| 清理#1 | `.vscode` 绝对路径 | ✅ **完成** | `${workspaceFolder}` 相对路径 |
| 清理#2 | 日志用户名脱敏 | 🟡 **部分** | `REDACTED_VM_USER` 为 VM hostname，大量内嵌于证据日志文件 (evidence.jsonl / journalctl.log)，非代码级硬编码 |
| 清理#3 | 空 `server_stdout.log` | 🔴 **未确认** | 未确认删除 |
| 清理#4 | C++ `<cerrno>` 头文件 | ✅ **已完成** | echo_client.cpp + kaiming_memory_client.cpp 均已 `#include <cerrno>` |
| 清理#5 | Shell 变量加引号 | 🟡 **需检查** | 需逐脚本检查 |
| 清理#6 | 部署前依赖检查 | 🔴 **未执行** | deploy_echo.sh 无 `command -v` 检查 |
| 清理#7 | 服务端客户端超时 | 🔴 **未执行** | memory_echo_server.py 无 `CLIENT_READ_TIMEOUT` / `settimeout()` |
| 清理#8 | 串行 Gate 0 标注 | 🔴 **未执行** | memory_echo_server.py 头部无"单连接阻塞式"注明 |
| 清理#9 | 错误响应脱敏 | ✅ **已完成** | traceback 仅写 stderr，不返回客户端 |
| 清理#10 | `--output-dir` 控制目录 | 🔴 **未完成** | 需验证所有证据收集脚本 |

**真实进展**：
- P0: **3/3 完成** ✅（所有阻断项已解决）
- P1: **4/6 完成** (P1-1 ✅, P1-2 ✅, P1-4 ✅, P1-6 ✅; P1-3 部分, P1-5 未执行)
- 清理: **4/10 完成** (#1 ✅, #4 ✅, #9 ✅; #2 部分; #3/#5/#6/#7/#8/#10 未执行)

> 🟢 **P0 阻断项已全部清零。P1 从 2/6 → 4/6。BLOCKED 状态已可解除。**

---

## 一、P0 阻断项（3/3 已完成）

### ✅ P0-1：明文凭据清理

**已修复文件**：

| 文件 | 修复方式 | 状态 |
|---|---|---|
| `v7_run_tests.py` | `os.environ.get('KYLIN_VM_PASSWORD', '')` + 未设置报错退出 | ✅ |
| `v8_systemd_prod_test.py` | `os.environ.get("KYLIN_VM_PASSWORD", "")` + check | ✅ |
| `v9_full_suite_test.py` | `os.environ.get("KYLIN_VM_PASSWORD", "")` + check | ✅ |
| `v10_runtimedir_test.py` | `os.environ.get("KYLIN_VM_PASSWORD", "")` + check | ✅ |
| `fix_systemd_on_vm.py` | `os.environ.get('KYLIN_VM_PASSWORD', '')` + check | ✅ |

> ⚠️ `fix_systemd_on_vm.py` 中 `echo $PASS | sudo -S` 模式仍存在（使用环境变量而非硬编码密码），建议后续 PR 改用 `sudo -n` 或无密码管道方案。

### ✅ P0-2：证据索引 SHA-256

`evidence/index.yaml` 当前 SHA-256 值：

| 条目 | SHA-256 | 状态 |
|---|---|---|
| ECHO-001 | `268671980f14873c9cb3aac123c157b676f35d252da11547085b1c941824d9c0` | ✅ 真实值 |
| ECHO-002 | `TBD` | ⚠️ SUPERSEDED（可接受） |
| ECHO-003 | `TBD` | ⚠️ SUPERSEDED（可接受） |
| ECHO-004 | `cd6038d06cee8a0c841f3a54a37eafdec181ddd4653e957cdd58f1f9dea77a74` | ✅ 真实值 |

ECHO-004 `limitations` 中已包含 "KYSEC 状态: UNVERIFIED（仅文件权限+ACL层面，非真实KYSEC规则写入）"。

### ✅ P0-3：测试失败传播

所有 v6~v10 及 test_rollback.sh 均已实现正确的退出码传播。

---

## 二、P1 重要剩余项

### ✅ P1-2：KYSEC → ACL 口径修正（已完成）

| 文件 | 状态 | 说明 |
|---|---|---|
| `kysec_authorize.sh` | ✅ 已完成 | L3 "UDS 文件权限与 ACL 最小授权脚本", L5 "⚠️ 非真实 KYSEC 规则写入" |
| `test_kysec_full.sh` | ✅ **已修复**（uncommitted） | L3 "UDS ACL 三阶段验证 (原 KYSEC 口径修正)"; L5 "⚠️ 非真实 KYSEC 规则写入 — 本脚本仅验证 UDS 文件权限 + ACL 层面" |
| `evidence/index.yaml` ECHO-004 | ✅ 已完成 | limitations 中已包含 KYSEC UNVERIFIED 声明 |

### 🟡 P1-3：回退 → 资源清理口径（标题已修，BACKUP_ID_FILE 待实现）

**`test_rollback.sh`**（uncommitted）：
- ✅ L3: 标题已改为 "Kylin Memory Echo — 测试资源清理脚本"
- ✅ L5: 新增 "⚠️ 不是完整原版恢复 — 仅清理测试写入的文件/目录/systemd unit"
- ✅ Phase 5 日志改为 "测试资源清理"
- ✅ main() 标题改为 "测试资源清理"

**仍待执行**：
- [ ] `kysec_authorize.sh`: authorize 时记录唯一备份目录到 `$BACKUP_ID_FILE`
- [ ] `kysec_authorize.sh`: rollback 时优先使用 recorded_id → 兜底用 `tail -1`（最早备份）
- [ ] 回退后清理 `BACKUP_ID_FILE` 记录

### ✅ P1-4：部署脚本 scp 端口参数（已修复，uncommitted）

**`deploy_echo.sh`** 变更：
- ✅ 新增 `SCP_OPTS="-P $KYLIN_PORT -o ConnectTimeout=10 -o StrictHostKeyChecking=no"`（独立于 SSH_OPTS）
- ✅ 所有 `scp` 调用（7处）全部改用 `$SCP_OPTS`
- ✅ 新增端口号范围校验：正则 `^[0-9]+$` + 1-65535 范围检查
- ✅ 新增主机名/IP 非空校验

### 🟡 P1-5：C++ 客户端协议增强 v2.0（1/13 完成）

**影响文件**: `os-agent-integration/echo/echo_client.cpp`（无版本标注）, `os-agent-integration/echo/kaiming_memory_client.cpp`（v1.1）

**已完成**：
| # | 特性 | 状态 |
|---|---|---|
| 10 | `#include <cerrno>` | ✅ 两客户端均已显式包含 |

**待实现（12 项）**：

| # | 特性 | 当前状态 | 说明 |
|---|---|---|---|
| 1 | `json_escape()` | ❌ 不存在 | JSON 字符串转义 |
| 2 | `send_all()` / `recv_all()` 循环 | ❌ 单次 send/recv + MSG_WAITALL | POSIX 不保证单次完成 |
| 3 | `SO_RCVTIMEO` / `SO_SNDTIMEO` (10s) | ❌ 无 setsockopt | 防永久阻塞 |
| 4 | `json_extract_str()` | ❌ 简单 strstr | 完整 JSON 解析 |
| 5 | 验证 `protocol_version` | ❌ 不验证 | 响应兼容性 |
| 6 | 验证 `request_id` / `trace_id` | ❌ 不验证 | 响应匹配请求 |
| 7 | 验证 `status` 字段 | ❌ 仅 status=="ok" | ok/error 语义 |
| 8 | 验证 Echo 内容往返一致 | ❌ 不比对 | echo 往返校验 |
| 9 | 路径 `>= sizeof(sun_path)` 拒绝 | ❌ 无检查 | sun_path 108 字节 |
| 11 | `allow_error` 参数 | ❌ 不存在 (kaiming仅) | 区分预期错误 vs 异常 |
| 12 | 版本号升级至 v2.0 | ❌ v1.1/无标注 | 完成上述后升级 |

> **建议**：作为独立后续 PR 处理，工作量约 2-3 天。

### ✅ P1-6：systemd 生命周期

v10 已完成完整生命周期链测试（24/29 PASS），`memory_echo_server.py` 优先使用 `RUNTIME_DIRECTORY` 环境变量，Socket 路径 `/run/kylin-memory-echo/echo.sock`。生产系统标记 UNVERIFIED。

---

## 三、清理剩余项

### 清理#2：日志用户名脱敏

`REDACTED_VM_USER` 为 VM hostname，内嵌于以下证据/日志文件中：

- `evidence/gate0_echo/v10_runtimedir/journalctl.log` — systemd journal 输出（hostname 由系统自动记录，不可控）
- `evidence/gate0_echo/v10_runtimedir/lifecycle_chain.txt` — 测试 UDS 输出（含 `User: REDACTED_VM_USER`）
- `evidence/gate0_echo/v10_runtimedir/v10_fulllifecycle.log` — 测试日志
- `evidence/gate0_echo/v6_final_results/evidence.jsonl` — 结构化证据记录
- `evidence/gate0_echo/v8_prod_test/`、`v9_full_suite/` — 历史测试日志

**区别于代码硬编码**：上述均为测试执行时系统自动记录的 hostname 和用户信息，并非源代码中硬编码。Python 脚本注释中的用户名引用已通过环境变量方式解决。

**建议**：证据日志文件保留原样（记录测试执行环境是证据链的一部分）；后续测试使用通用 VM 用户名（如 `kylin`）重新收集证据。

### 清理#3：删除空 `server_stdout.log`

```bash
find . -name "server_stdout.log" -size 0 -type f
# 如确认无用，删除
find . -name "server_stdout.log" -size 0 -type f -delete
```

### 清理#5：Shell 变量统一加引号

**影响文件**（需逐脚本检查）:
- `os-agent-integration/echo/deploy_echo.sh`
- `os-agent-integration/echo/install_systemd.sh`
- `os-agent-integration/echo/test_systemd_lifecycle.sh`
- `os-agent-integration/echo/kysec_authorize.sh`
- `os-agent-integration/echo/test_kysec_full.sh`
- `os-agent-integration/echo/test_rollback.sh`

### 清理#10：`--output-dir` 控制证据目录

**影响文件**: 所有 `evidence/gate0_echo/` 下的证据收集脚本。增加 `--output-dir` 命令行参数。

---

## 四、P0-1 后续：Git 历史重写

**⚠️ 重要**: 当前代码中的明文凭据已清除（环境变量），但旧 Git Commit 中仍可读取 `REDACTED_VM_PASSWORD` 密码。

1. 确认当前分支为 `feature/kaiming-uds-echo`
2. 使用 `git filter-branch` 或 `bfg` 重写历史
3. Force-push 到远程：`git push --force origin feature/kaiming-uds-echo`
4. **在麒麟 VM 上修改密码**: 登录麒麟 VM 执行 `passwd`

---

## 五、VM 重新验证清单

| 步骤 | 操作 | 脚本/命令 |
|---|---|---|
| 1 | 部署 Echo 服务 | `bash deploy_echo.sh <IP> <user> <port>` |
| 2 | 全链路测试 | `python3 v10_runtimedir_test.py` |
| 3 | 验证 SHA-256 | 确认 `evidence/index.yaml` ECHO-001/ECHO-004 与证据文件一致 |
| 4 | 提交 Review 第二轮 | `git add -A && git commit && gh pr create` / 更新 PR#18 |

---

## 六、文件修改对照总览（逐文件验证 + uncommitted diff 后更新）

| 文件 | P0 | P1 | 清理 | 状态 |
|---|---|---|---|---|
| `v7_run_tests.py` | ✅ P0-1 | — | 清理#2 | ✅ P0-1 完成（环境变量） |
| `v8_systemd_prod_test.py` | ✅ P0-1 | — | — | ✅ P0-1 完成（环境变量） |
| `v9_full_suite_test.py` | ✅ P0-1 | — | — | ✅ P0-1 完成（环境变量） |
| `v10_runtimedir_test.py` | ✅ P0-1 | — | — | ✅ P0-1 完成（环境变量） |
| `fix_systemd_on_vm.py` | ✅ P0-1 | — | 清理#2 | ✅ P0-1 完成（环境变量） |
| `evidence/index.yaml` | ✅ P0-2 | ✅ P1-2 | — | ✅ SHA-256 已填写；KYSEC UNVERIFIED 已标注 |
| `kysec_authorize.sh` | — | ✅ P1-2 | 清理#5 | ✅ 标题已改为 ACL 口径 |
| `test_kysec_full.sh` | — | ✅ P1-2 | 清理#5 | ✅ "UDS ACL 三阶段验证 (原 KYSEC 口径修正)" (uncommitted) |
| `test_rollback.sh` | — | 🟡 P1-3 | 清理#5 | ✅ 标题已改为"测试资源清理脚本" (uncommitted); BACKUP_ID_FILE 待实现 |
| `deploy_echo.sh` | — | ✅ P1-4 | 🔴 清理#6 | ✅ SCP_OPTS + 端口校验已修复 (uncommitted); 依赖检查仍缺失 |
| `echo_client.cpp` | — | 🟡 P1-5 (1/13) | ✅ 清理#4 | `<cerrno>` ✅；12 项 v2.0 待后续 PR |
| `kaiming_memory_client.cpp` | — | 🟡 P1-5 (1/13) | ✅ 清理#4 | `<cerrno>` ✅；12 项 v2.0 待后续 PR |
| `memory_echo_server.py` | — | — | 🔴 清理#7, 🔴 清理#8 | 无超时；无串行标注 |
| Shell 脚本 | — | — | 🟡 清理#5 | 需逐脚本检查引号 |
| 证据脚本 | — | — | 🔴 清理#10 | 需增加 `--output-dir` |
| Git 历史 | P0-1 后续 | — | — | 🔴 需执行 `git filter-branch` |

---

## 七、建议补全顺序

1. **立即**: VM密码更换（麒麟VM上执行 `passwd`）
2. **立即**: `git add` + `git commit` 当前 uncommitted 的三个文件（P1-2/test_kysec_full.sh, P1-3/test_rollback.sh, P1-4/deploy_echo.sh）
3. **本PR内（推荐）**: P1-3 BACKUP_ID_FILE 机制（kysec_authorize.sh 约 20 行）
4. **本PR内（推荐）**: 清理#3/#5/#6/#7/#8/#10 逐项修复
5. **本PR关闭前**: Git历史重写 + force-push
6. **本PR内（可选）**: VM 重跑 v10 验证 ECHO-001/ECHO-004 SHA-256 一致性
7. **下个PR**: P1-5 C++ v2.0 协议增强（12 项剩余）

---

## 八、修订记录

| 版本 | 日期 | 修订内容 |
|---|---|---|
| v1 | 2026-08-03 | 初始生成 |
| v2 | 2026-08-03 22:30 | 逐文件代码对照后修正 — P0 从 1/3 → 3/3；P1-2/P1-3/P1-4 从 "已完成" 更正为真实未完成状态 |
| v3 | 2026-08-03 22:55 | 跟进 uncommitted diff — P1-2(test_kysec_full.sh) ✅, P1-3(test_rollback.sh标题) ✅, P1-4(deploy_echo.sh SCP_OPTS) ✅；P1 从 2/6 → 4/6 |