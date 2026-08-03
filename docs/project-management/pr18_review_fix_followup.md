# PR#18 Review 修复后续操作清单

> **PR**: [#18 feat(echo): 麒麟环境独立 UDS Echo Spike 与部署验证](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/18)
> **修复日期**: 2026-08-03
> **本文件目的**: 记录本轮修复中因需VM环境或工作量大而延后的操作项，供后续逐一执行对照

---

## 一、P0 阻断剩余项

### P0-2：证据索引 SHA-256 填写

**现状**: `evidence/index.yaml` 中 ECHO-001 使用占位符 `a3f8c9d1...`，ECHO-004 为 `TBD`。

**执行步骤**:

1. 在麒麟 VM 上重新执行 v10 全链路测试（`v10_runtimedir_test.py`）
2. 测试通过后，计算证据文件的真实 SHA-256：
   ```bash
   # ECHO-001: v6_final_results/evidence.jsonl
   sha256sum evidence/gate0_echo/v6_final_results/evidence.jsonl

   # ECHO-004: v10_runtimedir/ 目录下的核心证据文件
   sha256sum evidence/gate0_echo/v10_runtimedir/lifecycle_chain.txt
   sha256sum evidence/gate0_echo/v10_runtimedir/journalctl.log
   ```
3. 将真实值填入 `evidence/index.yaml`：
   - ECHO-001: 替换 `checksum_sha256` 中的占位符
   - ECHO-004: 替换 `checksum_sha256: "TBD"` 为真实 SHA-256
4. 在 `evidence/index.yaml` ECHO-004 的 `limitations` 中补充：
   ```yaml
   KYSEC 状态: UNVERIFIED（仅文件权限+ACL层面，非真实KYSEC规则写入）
   ```

---

## 二、P1 重要剩余项

### P1-5：C++ 客户端协议增强 v2.0（13项全部未实现）

**影响文件**: `os-agent-integration/echo/echo_client.cpp`, `os-agent-integration/echo/kaiming_memory_client.cpp`

**建议**: 作为独立后续 PR 处理，工作量约 2-3 天。

**13项待实现清单**:

| # | 特性 | 当前状态 | 说明 |
|---|---|---|---|
| 1 | `json_escape()` | ❌ 不存在 | JSON 字符串转义（处理 `"`、`\n`、`\t` 等） |
| 2 | `send_all()` / `recv_all()` 循环 | ❌ 单次 send/recv + MSG_WAITALL | POSIX 不保证单次 send/recv 完成全部数据 |
| 3 | `SO_RCVTIMEO` / `SO_SNDTIMEO` (10s) | ❌ 无 setsockopt 调用 | 防止恶意客户端或网络故障导致永久阻塞 |
| 4 | `json_extract_str()` | ❌ 仅简单 strstr 搜索 | 完整 JSON 解析函数，提取指定字段 |
| 5 | 验证 `protocol_version` | ❌ 不验证 | 客户端应检查响应中的 protocol_version 是否兼容 |
| 6 | 验证 `request_id` / `trace_id` | ❌ 不验证 | 确保响应匹配请求 |
| 7 | 验证 `status` 字段 | ❌ 仅检查 status=="ok" | 应解析 status 并区分 ok/error 语义 |
| 8 | 验证 Echo 内容往返一致 | ❌ 不比对 | echo 方法的响应 message 应与请求完全一致 |
| 9 | 路径 `>= sizeof(sun_path)` 拒绝 | ❌ 无检查 | sun_path 通常 108 字节，超长路径应提前拒绝 |
| 10 | `#include <cerrno>` | ✅ **已修复（本轮）** | 两个客户端均已显式包含 |
| 11 | `allow_error` 参数 | ❌ 不存在 (kaiming_memory_client) | 区分预期错误（如 unknown method → error status）vs 异常（连接失败） |
| 12 | 版本号升级至 v2.0 | ❌ kaiming_memory_client 标 v1.1 | 应在完成上述增强后将版本号升级至 v2.0 |

**实现优先级建议**:
- **必须**: #2 send_all/recv_all, #3 超时, #9 路径拒绝, #10 ✅
- **重要**: #1 json_escape, #5 #6 #7 字段验证
- **建议**: #4 JSON解析, #8 echo比对, #11 allow_error

---

## 三、清理剩余项

### 清理#2：日志用户名脱敏

**现状**: 用户名 `REDACTED_VM_USER` 在如下位置仍有硬编码引用：
- `evidence/gate0_echo/v7_run_tests.py:7` — 注释中用法提示
- `evidence/gate0_echo/fix_systemd_on_vm.py:7` — 注释中用法提示
- `evidence/gate0_echo/v6_deploy_test_log.txt` — 日志文件内容

**执行**:
1. 检查并更新所有 Python 脚本注释中的用法提示为通用占位符（如 `<username>`）
2. 脱敏 `v6_deploy_test_log.txt` 中的密码痕迹（或确认日志文件为测试临时文件后删除）

### 清理#3：删除空 `server_stdout.log`

**执行**:
```bash
# 在项目根目录搜索并确认是否存在空的 server_stdout.log
find . -name "server_stdout.log" -size 0 -type f
# 如确认无用，删除
find . -name "server_stdout.log" -size 0 -type f -delete
```

### 清理#5：Shell 变量统一加引号

**影响文件** (需逐脚本检查):
- `os-agent-integration/echo/deploy_echo.sh`
- `os-agent-integration/echo/install_systemd.sh`
- `os-agent-integration/echo/test_systemd_lifecycle.sh`
- `os-agent-integration/echo/kysec_authorize.sh`
- `os-agent-integration/echo/test_kysec_full.sh`
- `os-agent-integration/echo/test_rollback.sh`

**检查要点**: 所有变量引用应使用双引号包裹（如 `"$VAR"` 而非 `$VAR`），防止空格/换行等特殊字符导致意外行为。

### 清理#10：`--output-dir` 控制证据目录

**影响文件**: 所有 `evidence/gate0_echo/` 下的证据收集脚本

**当前状态**: 各脚本硬编码输出目录（如 `v7_evidence`、`v10_runtimedir/`）

**执行**: 各脚本增加 `--output-dir` 命令行参数，允许自定义输出目录以便灵活收集证据。

---

## 四、P0-1 后续：Git 历史重写

**⚠️ 重要**: 当前代码中的明文凭据已清除，但旧 Git Commit 中仍可读取 `REDACTED_VM_PASSWORD` 密码。

**执行步骤**:
1. 确认当前分支为 `feature/kaiming-uds-echo`
2. 使用 `git filter-branch` 或 `bfg` 重写历史：
   ```bash
   # 使用 bfg（推荐，更快）
   # 1. 创建 passwords.txt 文件，内容为: REDACTED_VM_PASSWORD
   # 2. java -jar bfg.jar --replace-text passwords.txt
   # 或者使用 git filter-branch（内置）：
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch evidence/gate0_echo/v6_deploy_test_log.txt" \
     --prune-empty --tag-name-filter cat -- --all
   ```
3. Force-push 到远程：`git push --force origin feature/kaiming-uds-echo`
4. **在麒麟 VM 上修改密码**: 登录麒麟 VM 执行 `passwd` 更换当前密码

---

## 五、VM 重新验证清单

修复完成后，建议在干净麒麟 VM 快照上重新执行以下验证：

| 步骤 | 操作 | 脚本/命令 |
|---|---|---|
| 1 | 部署 Echo 服务 | `bash deploy_echo.sh <IP> <user> <port>` |
| 2 | 全链路测试 | `python3 v10_runtimedir_test.py` |
| 3 | 更新 SHA-256 | 按第一章步骤填写 `evidence/index.yaml` |
| 4 | 提交 Review 第二轮 | `git add -A && git commit && gh pr create` / 更新 PR#18 |

---

## 六、文件修改对照总览（本轮 + 待处理）

| 文件 | P0 | P1 | 清理 | 状态 |
|---|---|---|---|---|
| `v7_run_tests.py` | P0-1 | — | 清理#2 | ✅ 已完成 |
| `v8_systemd_prod_test.py` | P0-1 | — | — | ✅ 已完成 |
| `v9_full_suite_test.py` | P0-1 | — | — | ✅ 已完成 |
| `v10_runtimedir_test.py` | P0-1 | — | — | ✅ 已完成 |
| `fix_systemd_on_vm.py` | P0-1 | — | 清理#2 | ✅ 已完成 |
| `deploy_echo.sh` | — | P1-4 | 清理#5, 清理#6 | ✅ 已完成 |
| `kysec_authorize.sh` | — | P1-2, P1-3 | 清理#5 | ✅ 已完成 |
| `test_kysec_full.sh` | — | P1-2 | 清理#5 | ✅ 已完成 |
| `test_rollback.sh` | — | P1-3 | 清理#5 | ✅ 已完成 |
| `memory_echo_server.py` | — | — | 清理#7, 清理#8 | ✅ 已完成 |
| `echo_client.cpp` | — | P1-5 | 清理#4 | ✅ 部分（清理#4完成，P1-5待后续PR） |
| `kaiming_memory_client.cpp` | — | P1-5 | 清理#4 | ✅ 部分（清理#4完成，P1-5待后续PR） |
| `evidence/index.yaml` | P0-2 | — | — | 🔴 待VM重跑后补全SHA-256 |
| Shell脚本 | — | — | 清理#5 | 🟡 需逐脚本检查 |
| 证据脚本 | — | — | 清理#10 | 🟡 需增加 `--output-dir` |
| Git历史 | P0-1 | — | — | 🔴 需执行 `git filter-branch` |

---

## 七、建议补全顺序

1. **立即**: VM密码更换（麒麟VM上执行 `passwd`）
2. **本PR内（推荐）**: 清理#2/#3/#5/#10 逐项修复
3. **本PR内（必须）**: P0-2 SHA-256 补全（需VM重跑测试）
4. **本PR关闭前**: Git历史重写 + force-push
5. **下个PR**: P1-5 C++ v2.0 协议增强（13项）