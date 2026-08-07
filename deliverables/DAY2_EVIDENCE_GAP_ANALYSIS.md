# Day2 麒麟 VM 运行时 — 证据提交差距分析

> **创建日期**: 2026-08-06
> **对照源**: `deliverables/DAY2_KYLIN_RUNTIME_PENDING.md`
> **证据目录**: `evidence/gate0_echo/day2_results/` + `evidence/index.yaml`
> **自动化运行日志**: `evidence/gate0_echo/day2_results/day2_runner.log`
> **审查人**: 谢嘉然

---

## 总览

| 阶段 | 编号 | 状态 | 缺陷数 |
|------|------|:----:|:------:|
| 阶段一 代码同步与编译 | S1 | ✅ PASS | 0 |
| 阶段二 KAIMING-STORE 修复验证 | R1+R2 | ⚠️ PARTIAL | 2 |
| 阶段三 Systemd 卸载假阳性 | R3 | ❌ FAIL | 3 |
| 阶段四 KYSEC/ACL 模式适配 | R4 | ⚠️ PARTIAL | 1 |
| 阶段五 D2-1 Kaiming Hook | D2-1 | ✅ BLOCKED | 0 |
| 阶段五 D2-3 部署启动 | D2-3 | ⚠️ PARTIAL | 1 |
| 阶段五 D2-4 Socket路径审计 | D2-4 | ❌ FAIL | 4 |
| 阶段五 D2-6 KYSEC授权口径 | D2-6 | ❌ FAIL | 3 |
| 阶段五 D2-7 回退对照基线 | D2-7 | ❌ FAIL | 5 |
| 阶段六 证据收集 | E1~E9 | ⚠️ PARTIAL | 3 |
| index.yaml 登记 | — | ⚠️ PARTIAL | 4 |

---

## 🔴 P0 — 阻断验收

### P0-1: R3 Systemd 生命周期测试 3/18 FAIL (exit=1)

- **任务卡要求**: 18/18 PASS, exit=0
- **实际结果**: 15/18 PASS, 3 FAIL, exit=1
- **失败项**:
  - Step 8 UDS echo 失败
  - Step 8 UDS health 失败
  - Step 11 卸载后 `systemctl status` 未匹配 "could not be found"
- **证据位置**: `day2_results/E4_systemd_lifecycle_rerun.log` L79-82; `day2_runner.log` L51
- **根因推测**: Step 8 UDS 通信阶段 echo/health socket 不可达（可能因 echo_client 未编译或路径不匹配）
- **修复方向**: 检查编译产物 `echo_client` 是否存在、socket 路径是否与 systemd RuntimeDirectory 一致

### P0-2: R2.3 全量测试 exit=1 (5/6 PASS)

- **任务卡要求**: 6/6 PASS, exit=0
- **实际结果**: 5/6 PASS, 1 FAIL (KAIMING-STORE), exit=1
- **证据位置**: `day2_results/E2_client_kaiming_store.log` L116-119; `day2_runner.log` L44
- **根因**: KAIMING-STORE 调用返回 INTERNAL_ERROR (Echo 未实现 memory.store)，客户端将其计为 FAIL → exit=1
- **修复方向**: 确认 `memory.store` 的 exit code 语义：如果是预期内的"未实现"，exit code 应为 0；或让服务端返回 UNSUPPORTED_METHOD

### P0-3: kysec_authorize.sh --socket 参数整体缺失

- **影响范围**: R4.2.4 + D2-4.5 + D2-4 一致性审计链
- **任务卡要求**: `--socket PATH` 参数支持，--help 中显示
- **实际结果**: --help 输出无 `--socket` 说明，实际脚本不支持该参数
- **证据位置**: 
  - `E5_kysec_acl_systemd.log` L266: `--socket 参数: 未说明`
  - `E9_socket_path_audit.log` L49: `--socket 参数: 未支持`
- **根因**: `kysec_authorize.sh` 代码层面未实现 `--socket` 参数解析（`parse_args()` 函数缺失）
- **修复方向**: 在 `kysec_authorize.sh` 中添加 `--socket` 参数解析和路径覆盖逻辑

---

## 🟡 P1 — 证据文件缺失

### P1-1: E3 `client_all_6x6.log` 缺失

- **要求**: 独立的全部 6 项测试重跑结果文件
- **实际**: day2_results 目录中无此文件
- **说明**: R2.3 全量测试输出已内嵌在 E2 中，但不满足任务卡对独立文件的命名要求

### P1-2: E6 `kysec_acl_dev.log` 缺失

- **要求**: 独立的 Dev 模式 ACL 授权/回退日志
- **实际**: Dev 模式 ACL 日志已合并到 E5 中
- **修复方向**: 从 E5 中拆分出 Dev 模式部分保存为独立文件

### P1-3: D2-4.6 `test_rollback.sh` 不可达

- **要求**: 检查 `test_rollback.sh` SOCKET_PATH 变量
- **实际**: `NOT_FOUND` — 文件在麒麟 VM 上不存在
- **证据位置**: `E9_socket_path_audit.log` L52-53
- **修复方向**: 确认 `packaging/deploy-package/scripts/test_rollback.sh` 是否已上传到 VM

---

## 🟡 P1 — UNVERIFIED 标注缺失

### P1-4: D2-6.1 kysec_authorize.sh 头部缺少 UNVERIFIED 标注

- **要求**: 第 5 行附近标注 `# ⚠️ 非真实 KYSEC 规则写入 — KYSEC 状态标记为 UNVERIFIED`
- **实际**: 头部无此标注
- **证据位置**: `D2_6_kysec_scope.log` L5-16: 扫描到的头部内容不含 UNVERIFIED
- **修复方向**: 在脚本头部注释块中添加 UNVERIFIED 声明

### P1-5: D2-6.2 status 输出缺少 UNVERIFIED 标注

- **要求**: `status` 子命令输出包含 "UNVERIFIED"
- **实际**: 输出不含此字样
- **证据位置**: `D2_6_kysec_scope.log` L20-62

---

## 🟡 P1 — D2-7 回退对照不完整

### P1-6: D2-7.2 SHA-256 对比缺失

- **要求**: rollback 前后 SHA-256 对比
- **实际**: 仅有回退前 SHA，无回退后对比
- **证据位置**: `E8_rollback_baseline_compare.log` L46-61

### P1-7: D2-7.7 owner/group/mode 恢复检查缺失

- **要求**: `stat -c "%U:%G %a" <path>` 与基线对比
- **实际**: 完全未执行

### P1-8: D2-7.8 ACL 恢复检查缺失

- **要求**: `getfacl <path>` 与基线对比
- **实际**: 完全未执行

### P1-9: D2-7.9 包版本恢复检查缺失

- **要求**: `rpm -qa | grep kylin` 对比
- **实际**: 完全未执行

### P1-10: D2-7.5 进程清理不干净

- **要求**: `pgrep -f kylin-memory-echo-server` 无结果
- **实际**: PID 64432 仍存在
- **证据位置**: `E8_rollback_baseline_compare.log` L95-97

---

## 🟢 P2 — 文档与登记

### P2-1: evidence/index.yaml 未登记 Day2 后续条目

| 缺失 ID | 对应任务 | 状态 |
|---------|---------|:----:|
| `D2-3-DEPLOY-STARTUP` | D2-3 部署启动可复现 | 未登记 |
| `D2-4-SOCKET-AUDIT` | D2-4 统一Socket路径 | 未登记 |
| `D2-6-KYSEC-SCOPE` | D2-6 KYSEC授权口径 | 未登记 |
| `D2-7-ROLLBACK-BASELINE` | D2-7 回退对照基线 | 未登记 |

### P2-2: D2-4.1 RuntimeDirectory 配置不可确认

- **要求**: `grep RuntimeDirectory /etc/systemd/system/kylin-memory-echo.service`
- **实际**: UNIT_NOT_FOUND (审计时 unit 文件已被 uninstall 清理)
- **证据位置**: `E9_socket_path_audit.log` L5-7
- **说明**: 不是真正的缺陷，但审计链路不完整

### P2-3: D2-6.3 KYSEC 内核接口状态记录不一致

- `day2_runner.log` L119: 记录 "KYSEC 内核接口: 可用"
- `D2_6_kysec_scope.log` L66: 记录 "KYSEC_NOT_AVAILABLE"
- **修复方向**: 统一记录口径，确认 sysfs 实际状态

---

## 已完成项目确认 ✅

| 编号 | 内容 | 证据 |
|------|------|------|
| S1.1.1~1.1.3 | 3个修复文件上传，SHA256匹配 | day2_runner.log L11-16 |
| S1.2.1~1.2.3 | 干净CMake构建，两个二进制产物 | E1_build.log + D2_3_deploy_startup.log L34-36 |
| R1.1~1.3 | JSON合法性，服务端无PROTOCOL_ERROR | E2 L29 |
| R4.1.1~1.3 | Dev模式ACL authorize/status/rollback | E5 L7-65, L69-112, L114-126 |
| R4.2.1~2.3 | Systemd模式ACL authorize/status/rollback | E5 L130-190, L193-236, L238-249 |
| D2-1.1~1.8 | Kaiming Hook调查（全部8项） | d2_1_evidence/ + index.yaml L240-259 |
| D2-3.2~3.4 | CMake构建 + dev模式 + 非dev拒绝回退 | D2_3_deploy_startup.log |
| D2-4.4 | kaiming_memory_client --socket支持 | E9 L24-27 |
| D2-4.7 | 交叉验证 dev服务+systemd路径 → 预期失败 | E9 L56-75 |
| D2-6.4~6.5 | KYSEC无法验证原因 + Gate1计划 | D2_6_kysec_scope.log L70-85 |
| E1 | build.log | ✅ |
| E2 | client_kaiming_store.log | ✅ |
| E4 | systemd_lifecycle_rerun.log | ✅ |
| E5 | kysec_acl_systemd.log | ✅ |
| E7 | kaiming_hook_attempt.log | ✅ |
| E8 | rollback_baseline_compare.log | ✅ |
| E9 | socket_path_audit.log | ✅ |

---

## 修复优先级汇总

```
P0 (阻塞Gate):
  1. R3 生命周期 3/18 FAIL → 修复echo_client编译或socket路径
  2. R2.3 exit=1 → 修复KAIMING-STORE的exit code语义
  3. kysec_authorize.sh --socket 参数 → 代码实现

P1 (证据不完整):
  4. E3/E6 缺失 → 补充独立文件
  5. D2-6.1/D2-6.2 UNVERIFIED标注 → 修改脚本头部和status输出
  6. D2-7.2/7.7/7.8/7.9 回退对比缺失 → 补充逐项对比

P2 (文档完善):
  7. index.yaml 登记4条 → 补充登记
  8. D2-4.1/D2-6.3 记录一致性 → 修正
```

---

> **关联文档**: `deliverables/DAY2_KYLIN_RUNTIME_PENDING.md`, `deliverables/PR21_REVIEW_ACTION_ITEMS.md`, `evidence/gate0_echo/day2_results/DAY2_SUMMARY.md`