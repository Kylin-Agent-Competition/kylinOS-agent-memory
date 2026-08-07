# Day2 麒麟 VM 运行时待执行任务清单

> **创建日期**: 2026-08-06
> **上下文**: PR #21 Review Action Items — Day2 四项遗留问题（R1~R4）代码层面已修复，所有麒麟 VM 运行时验证任务待执行
> **上游文档**: `deliverables/PR21_REVIEW_ACTION_ITEMS.md` §二、§六
> **修复 Commit**: 待提交
> **PR 链接**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/21
> **最后验证**: 2026-08-06 11:34 UTC+8 — D2-1 路线B调查报告完成, R1~R4全部通过, Gate 0 READY

---

## 修复状态总览

| 遗留编号 | 问题描述 | 代码层面 | 麒麟 VM 运行时 |
|---------|---------|:------:|:------------:|
| R1 | `kaiming_memory_client.cpp` JSON 缺 payload 闭合 `}` | ✅ 已修复 | ✅ 编译+运行通过 |
| R2 | `kaiming_memory_client.cpp` 断言 `json_has_key("status")` 假阳性 | ✅ 已修复 | ✅ 6/6 PASS (exit=0) |
| R3 | `test_systemd_lifecycle.sh` 卸载验证两个分支都执行 `ok()` | ✅ 已修复 | ✅ 18/18 PASS |
| R4 | `kysec_authorize.sh` 不支持 `--socket` 参数 | ✅ 已修复 | ✅ ACL 两面模式通过 |
| D2-1 | Kaiming → UDS Echo 真实 Hook | ✅ 路线B完成 | 🟡 BLOCKED（源码已在 openkylin 开源可获取，待 VM 内编译验证；详见 `reviewDocuments/openkylin_blocker_survey.md`） |
| D2-3 | 部署和启动可复现 | ✅ 已验证 | ✅ C++构建 + dev模式 |
| D2-4 | 统一 Socket 路径 | ✅ 已验证 | ✅ 全链路7项一致 |
| D2-6 | KYSEC 最小授权口径明确 | ✅ 已标注 | ✅ 内核接口确认不可用 |
| D2-7 | 回退对照 Day1 基线验证 | ✅ rollback执行 | ✅ 逐项对照验证 |

---

## 阶段一：代码同步与编译验证

### S1.1 上传修复后代码到麒麟 VM

| # | 任务 | 详细要求 | 产出 |
|---|------|---------|------|
| S1.1.1 | 上传 `kaiming_memory_client.cpp` | 使用 `deploy_echo.sh` 或手动 `scp` 上传修复后的文件到麒麟 VM | 文件就位确认 |
| S1.1.2 | 上传 `test_systemd_lifecycle.sh` | 上传修复后的生命周期测试脚本 | 文件就位确认 |
| S1.1.3 | 上传 `kysec_authorize.sh` | 上传新增 `--socket` 支持的授权脚本 | 文件就位确认 |

### S1.2 干净构建验证

| # | 任务 | 命令 | 预期结果 |
|---|------|------|---------|
| S1.2.1 | 干净 CMake 配置 | `cmake -S . -B build` | 无错误 |
| S1.2.2 | 编译全部 target | `cmake --build build` | `echo_client` + `kaiming_memory_client` 均编译成功 |
| S1.2.3 | 确认二进制产物 | `ls -la build/echo_client build/kaiming_memory_client` | 两个二进制均存在且可执行 |

---

## 阶段二：R1+R2 修复验证 — KAIMING-STORE

> **验证内容**: JSON 结构修复 + 断言修复后，KAIMING-STORE 测试能否正确识别 PROTOCOL_ERROR / INTERNAL_ERROR

### R1 验证：JSON 合法性

| # | 任务 | 命令/方法 | 预期结果 |
|---|------|---------|---------|
| R1.1 | 启动 Echo 服务（dev 模式） | `python3 kylin-memory-echo-server --dev` | 服务启动，socket 创建 |
| R1.2 | 发送 memory.store 请求 | `./kaiming_memory_client --method memory.store --socket /tmp/kylin-memory-echo/echo.sock` | 客户端正常连接 |
| R1.3 | 检查服务端日志 | 查看服务端 stdout/stderr | **无 `PROTOCOL_ERROR`**，JSON 成功解析 |
| R1.4 | 检查响应结构 | 查看客户端输出 | 响应包含合法 JSON，非解析错误 |

### R2 验证：断言正确性

| # | 任务 | 验证点 | 预期结果 |
|---|------|--------|---------|
| R2.1 | 运行 KAIMING-STORE 单独测试 | `./kaiming_memory_client --method memory.store` | 响应 `status=="error"` **且** 包含 `error_code` **且** 包含 `error_message` → PASS |
| R2.2 | 构造非法 JSON（如有工具）发送到服务端 | 发送缺少 `}` 的错误 JSON | 响应 PROTOCOL_ERROR → `status=="error"` 但**没有**合法 error_code → FAIL |
| R2.3 | 运行全量 6/6 测试 | `./kaiming_memory_client --method all` | 6 项测试结果准确，KAIMING-STORE PASS |

---

## 阶段三：R3 修复验证 — Systemd 卸载假阳性

> **修复内容**: Step 11 卸载验证从取反逻辑改为正向逻辑
> **文件**: `test_systemd_lifecycle.sh` 第 290-295 行

| # | 任务 | 命令 | 验证点 |
|---|------|------|--------|
| R3.1 | 在干净 VM 上执行完整生命周期测试 | `sudo bash test_systemd_lifecycle.sh` | 全部步骤执行 |
| R3.2 | 检查 Step 11 — 卸载后 `systemctl status` 输出 | 查看测试日志 | `grep "could not be found"` 匹配 → `ok "systemd 已确认注销服务"` |
| R3.3 | 确认卸载失败不会误判 PASS | 手动保留 unit 文件后执行 Step 11 逻辑 | `grep "could not be found"` 不匹配 → `no "systemd 状态异常: 服务未正确注销"` |
| R3.4 | 确认总退出码 | `echo $?` | 0 = 全部 PASS, 非零 = 存在 FAIL |

---

## 阶段四：R4 修复验证 — KYSEC/ACL 模式适配

> **修复内容**: `kysec_authorize.sh` 新增 `parse_args()` + `--socket PATH` 参数
> **验证两种模式**: Systemd (`/run/...`) 和 Dev (`/tmp/...`)

### R4.1 Dev 模式（默认 /tmp）

| # | 任务 | 命令 | 预期 |
|---|------|------|------|
| R4.1.1 | 默认路径 ACL 授权 | `sudo bash kysec_authorize.sh authorize` | 操作 `/tmp/kylin-memory-echo/echo.sock` |
| R4.1.2 | 默认路径状态查看 | `sudo bash kysec_authorize.sh status` | 显示 `/tmp/...` 路径状态 |
| R4.1.3 | 默认路径回退 | `sudo bash kysec_authorize.sh rollback` | 恢复 `/tmp/...` 原权限 |

### R4.2 Systemd 模式（--socket /run/...）

| # | 任务 | 命令 | 预期 |
|---|------|------|------|
| R4.2.1 | Systemd 路径 ACL 授权 | `sudo bash kysec_authorize.sh authorize --socket /run/kylin-memory-echo/echo.sock` | 操作 `/run/kylin-memory-echo/` |
| R4.2.2 | Systemd 路径状态查看 | `sudo bash kysec_authorize.sh status --socket /run/kylin-memory-echo/echo.sock` | 显示 `/run/...` 路径状态 |
| R4.2.3 | Systemd 路径回退 | `sudo bash kysec_authorize.sh rollback --socket /run/kylin-memory-echo/echo.sock` | 恢复 `/run/...` 原权限 |
| R4.2.4 | --help 输出检查 | `bash kysec_authorize.sh --help` | 显示 `--socket PATH` 用法说明 |

---

## 阶段五：Day2 未闭合原始任务

### D2-1: Kaiming → 自定义 UDS Echo 真实 Hook ✅ (路线 B 已完成)

> **策略**: 路线 B — 如实记录失败
> **最终状态**: **BLOCKED**（源码已在 openkylin 开源可获取，待 VM 内编译验证）/ Gate 0 评估: **PARTIAL**
> **调查报告**: `evidence/gate0_echo/d2_1_evidence/D2_1_Final_Evidence_Report.md`
> **证据记录**: `evidence/gate0_echo/d2_1_evidence/D2_1_evidence_record.json`
> **evidence/index.yaml**: `D2-1-KAIMING-HOOK` (L240-259)

| # | 任务 | 状态 | 产出 |
|---|------|:----:|------|
| D2-1.1 | 定位 kylin-aiassistant 源码中的 Socket 调用点 | ✅ | `strings /usr/bin/kylin-aiassistant` 扫描: QLocalSocket/connectToServer/echo.sock 均未发现 — 路径可能在编译时硬编码 |
| D2-1.2 | 记录尝试修改内容 | ✅ | 三次尝试记录: (1) 二进制 strings 扫描 (2) 配置文件搜索 (3) dpkg 包管理器查询 — 全部失败，详细记录见最终报告 §D2-1.2 |
| D2-1.3 | 提交构建命令和构建日志 | ✅ | N/A — D2-1 阶段误判为闭源二进制，无法构建。`reviewDocuments/openkylin_blocker_survey.md` 调查发现 kylin-aiassistant 已在 openkylin 完全开源（含完整 C++ 源码、`debian/` 打包目录），`qmake && make` 可本地编译验证 |
| D2-1.4 | 记录实际失败命令和错误日志 | ✅ | 6 项操作完整记录 (dpkg/strings/find)，含退出码和错误信息，见最终报告 §D2-1.4 实际操作失败记录表 |
| D2-1.5 | 说明阻断原因 | ✅ | D2-1 阶段列出 6 条阻断原因，`reviewDocuments/openkylin_blocker_survey.md` 调查后发现：源码已开源(1不成立)、构建环境 README 已提供(2不成立)、`dpkg-buildpackage -us -uc` 无需签名(3局部不成立)、Socket 路径源码层可审计(4前提失效)、Gate 0 可在 VM 内编译修改(5伪阻塞)、`kylin-ai-base` 接口待查(6前提失效)。详见 survey 表 |
| D2-1.6 | 提交独立模拟客户端替代结果 | ✅ | `kaiming_memory_client --method all` → **6/6 PASS** (exit=0). 详见最终报告 §D2-1.5 |
| D2-1.7 | 提交后续接入方案 | ✅ | D4 阶段在 VM 内 `git clone kylin-aiassistant` → `qmake && make` 编译 → 源码审计 Socket 路径 → 修改指向 Memory Service，见最终报告 §D2-1.6 |
| D2-1.8 | 状态标记 | ✅ | `evidence/index.yaml` 已更新: `D2-1-KAIMING-HOOK` → **BLOCKED**; Gate 0 整体 → **PARTIAL** |

> **⚠️ 已知不一致 (已修复)**: 原始自动化调查脚本输出 `D2_1_Kaiming_Hook_Investigation_Report.md` 记录独立客户端为 0/12 FAIL，原因是调查时 Echo 服务未启动导致 connect() 全部失败。该文件已标注 DEPRECATED，最终结论以 `D2_1_Final_Evidence_Report.md` 为准。

> **最新进展 (2026-08-07)**: `reviewDocuments/openkylin_blocker_survey.md` 调查发现 kylin-aiassistant 已在 openkylin 完全开源，D2-1 阶段的"闭源二进制"假设不成立。D4 阶段可在 VM 内直接 clone 源码编译验证，无需等待 SDK 团队授权。

### D2-3: 部署和启动可复现 🔴

| # | 任务 | 命令 | 预期 |
|---|------|------|------|
| D2-3.1 | 干净目录部署 | `bash deploy_echo.sh` | 全部文件上传成功 |
| D2-3.2 | 干净 CMake 构建 | `cmake -S . -B build && cmake --build build` | 两个客户端均编译成功 |
| D2-3.3 | 手动 dev 模式启动 | `python3 kylin-memory-echo-server --dev` | socket 在 `/tmp/...` 创建 |
| D2-3.4 | 验证 --dev 参数使能 | 不带 `--dev` 启动并检查 socket 路径 | 确认 systemd 模式不会静默回退 `/tmp` |

### D2-4: 统一 Socket 路径 🔴

> **完整路径对照验证**

| # | 组件 | 预期路径 | 验证命令 | 产出 |
|---|------|---------|---------|------|
| D2-4.1 | systemd unit | `/run/kylin-memory-echo/echo.sock` | `grep RuntimeDirectory /etc/systemd/system/kylin-memory-echo.service` | RuntimeDirectory 配置确认 |
| D2-4.2 | 服务端 systemd 模式 | `/run/kylin-memory-echo/echo.sock` | 启动后 `ls -la /run/kylin-memory-echo/` | socket 在 /run 下 |
| D2-4.3 | 服务端 dev 模式 | `/tmp/kylin-memory-echo/echo.sock` | `python3 kylin-memory-echo-server --dev` 后检查 | socket 在 /tmp 下 |
| D2-4.4 | C++ 客户端 | 支持 `--socket` 覆盖 | `./kaiming_memory_client --help` | --socket 参数说明正确 |
| D2-4.5 | ACL 脚本 | 支持 `--socket` 覆盖 | `bash kysec_authorize.sh --help` | --socket 参数说明正确 |
| D2-4.6 | rollback 测试 | `/tmp/...` (CI/开发) | 检查 `test_rollback.sh` SOCKET_PATH 变量 | 路径合理 |
| D2-4.7 | 交叉验证 | dev 模式服务 + systemd 路径客户端 → 预期失败 | `--socket /run/...` 连 dev 服务 | 明确报错，不静默 |

### D2-6: KYSEC 授权口径明确 🔴

| # | 任务 | 产出 |
|---|------|------|
| D2-6.1 | 确认 `kysec_authorize.sh` 头部标注 | 检查第 5 行 `# ⚠️ 非真实 KYSEC 规则写入 — KYSEC 状态标记为 UNVERIFIED` |
| D2-6.2 | 确认 `show_status()` 输出标注 | 运行 `status` 子命令，检查输出包含 "UNVERIFIED" |
| D2-6.3 | 检查 KYSEC 内核接口状态 | `ls /sys/kernel/security/kylin/ 2>/dev/null && echo "KYSEC available" || echo "KYSEC NOT available"` |
| D2-6.4 | 记录无法验证真实 KYSEC 的原因 | (1) Gate 0 阶段不具备生产 KYSEC 规则写入权限 (2) 需要 KYSEC 管理员 token |
| D2-6.5 | 提交 Gate 1 后续计划 | 获取 KYSEC 开发者文档 → 申请测试环境授权 → 最小规则集验证 |
| D2-6.6 | 状态文件更新 | 在 evidence 中标注: `ACL Spike: VERIFIED` / `KYSEC real rule: UNVERIFIED` |

### D2-7: 回退对照 Day1 基线验证 🔴

> **对照流程**: `Day1 基线` → `安装/授权/测试` → `rollback` → `逐项对比`

| # | 对比项 | 验证方法 | 预期结果 |
|---|--------|---------|---------|
| D2-7.1 | 文件是否恢复 | 对比 rollback 前后 `find /home/<user>/kylin-memory-echo -type f` | 与基线一致 |
| D2-7.2 | SHA-256 是否一致 | `sha256sum <file>` 对比脚本/配置 | 与基线一致 |
| D2-7.3 | unit 是否恢复 | `systemctl cat kylin-memory-echo` 或 `ls /etc/systemd/system/kylin-memory-echo.service` | 不存在 |
| D2-7.4 | service 是否恢复 | `systemctl status kylin-memory-echo` | "could not be found" |
| D2-7.5 | 进程是否清理 | `pgrep -f kylin-memory-echo-server` | 无结果 |
| D2-7.6 | Socket 是否清理 | `ls /run/kylin-memory-echo/echo.sock /tmp/kylin-memory-echo/echo.sock 2>&1` | 均不存在 |
| D2-7.7 | owner/group/mode 是否恢复 | `stat -c "%U:%G %a" <path>` | 与基线一致 |
| D2-7.8 | ACL 是否恢复 | `getfacl <path>` | 与基线一致 |
| D2-7.9 | 包版本是否恢复 | `rpm -qa \| grep kylin` 对比 | 与基线一致 |

> 若无法原版恢复：声明 `TEST RESOURCE CLEANUP ONLY / ORIGINAL RESTORE UNVERIFIED`

---

## 阶段六：证据收集与提交

| # | 产出文件 | 内容 | 来源阶段 |
|---|---------|------|---------|
| E1 | `build.log` | 干净 CMake 构建日志 | S1.2 |
| E2 | `client_kaiming_store.log` | KAIMING-STORE 修复后测试输出 | R1, R2 |
| E3 | `client_all_6x6.log` | 全部 6 项测试重跑结果 | R2.3 |
| E4 | `systemd_lifecycle_rerun.log` | 修复后完整生命周期重跑 | R3 |
| E5 | `kysec_acl_systemd.log` | Systemd 模式 ACL 授权/回退 | R4.2 |
| E6 | `kysec_acl_dev.log` | Dev 模式 ACL 授权/回退 | R4.1 |
| E7 | `kaiming_hook_attempt.log` | 真实 Hook 尝试过程 | D2-1 |
| E8 | `rollback_baseline_compare.log` | 回退对照基线逐项对比 | D2-7 |
| E9 | `socket_path_audit.log` | 全链路 Socket 路径一致性审计 | D2-4 |

---

## 执行顺序建议

```
阶段一 (S1) → 阶段二 (R1+R2) → 阶段三 (R3) → 阶段四 (R4)
                                              ↓
                              阶段五 (D2-1 → D2-3 → D2-4 → D2-6 → D2-7)
                                              ↓
                                         阶段六 (证据整理)
```

> **最小编译验证（快速反馈）**: S1.2 → R2.3 → R3.1 三项通过即可确认代码修复有效，其余可分批执行。