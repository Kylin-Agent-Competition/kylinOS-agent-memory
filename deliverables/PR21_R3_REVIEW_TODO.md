# PR21 第三轮 Review (#4879426406) 修复待办清单

> **Review 日期**: 2026-08-07 02:27 UTC  
> **审查结论**: `REQUEST_CHANGES — DO NOT MERGE`  
> **审查 Commit**: `c9c8143571df036ddf5a34ec64ec6f44096b3fa4`  
> **Reviewer**: lovezy0730-create  
> **梳理日期**: 2026-08-07  
> **最后更新**: 2026-08-07 13:55 UTC+8  
> **本文件**: 逐项对照 Review 意见的修复进度追踪

---

## 一、P0 阻断项（合并前必须修复）

### P0-1: 修复 `memory.store` 非法 JSON + `unknown method` 断言

✅ **已完成** — 2026-08-07

#### R1-a: JSON 多余闭合括号 ✅

**文件**: `os-agent-integration/echo/kaiming_memory_client.cpp`  
**修复**: 第155行 `"}}"` 闭合 payload+root，删除了第156行多余的 `<< "}";`

修复后拼接结果:
```
{                                             // 第145行: 开 root
  "protocol_version":"1.0",
  ...
  "payload":{                                  // 第151行: 开 payload
    "key":"...",
    "content":"...",
    "metadata":{...}                            // 第154行: metadata
  }}                                           // 第155行: 闭 payload + 闭 root ✅
```

- [x] 删除 `kaiming_memory_client.cpp:156` 多余的 `<< "}";`
- [ ] 需在麒麟 VM 上验证标准 JSON 解析器可解析 `memory.store` 请求
- [ ] 需在麒麟 VM 上验证服务端日志记录 `method=memory.store`

#### R1-b: unknown method 断言不完整 ✅

**文件**: `os-agent-integration/echo/kaiming_memory_client.cpp`  
**修复**: 第221-223行增加 `error_code=="UNSUPPORTED_METHOD"` + `json_has_key(resp, "message")` 验证

```cpp
// 第221-223行: 完整验证
bool ok = (extract_json_status(resp) == "error")
       && (extract_json_string_value(resp, "error_code") == "UNSUPPORTED_METHOD")
       && json_has_key(resp, "message");
```
- [x] `test_unknown_method()` 断言增加 `error_code=="UNSUPPORTED_METHOD"` 验证

#### R1-c: 验收标准 ⬜ 待麒麟 VM 执行

- [ ] 麒麟 VM 上执行: `kaiming_memory_client --method all`
- [ ] 输出: `Passed: 6 / Failed: 0 / Exit code: 0`
- [ ] STORE 确认: `status=error, error_code=UNSUPPORTED_METHOD`
- [ ] UNKNOWN 确认: `status=error, error_code=UNSUPPORTED_METHOD`

---

### P0-2: 消除 systemd 生命周期测试中的假 PASS

✅ **已完成** — 2026-08-07

#### R3-a: Python fallback 替代 C++ Client PASS ✅

**文件**: `os-agent-integration/echo/test_systemd_lifecycle.sh`

已拆分为三个独立结果 (第272-421行):
- [x] `SYSTEMD_SERVER_LIFECYCLE=PASS/FAIL` — 服务端启停 (第278-285行)
- [x] `CPP_CLIENT_OVER_SYSTEMD=PASS/FAIL` — C++ 客户端验证 (第333-348行，失败时 `no()` FAIL)
- [x] `PYTHON_DIAGNOSTIC_FALLBACK` — 仅诊断信息，明确标注"不计入 C++ PASS/FAIL" (第350-411行)
- [x] Python fallback 成功不修改 C++ 测试结果 (第405-406行注释)
- [x] C++ Client 失败时 `CPP_CLIENT_OVER_SYSTEMD` 记录 FAIL (第336、344行)

#### R3-b: 动态 Unit 替代仓库正式 Unit ✅

**文件**: `os-agent-integration/echo/test_systemd_lifecycle.sh`

- [x] 新增 `PACKAGED_UNIT_VALIDATION=PASS/FAIL` 独立判定 (第68-142行)
- [x] 优先使用仓库正式 Unit: `${DEPLOY_BASE}/share/${UNIT_FILE}` (第85-98行)
- [x] Unit 缺失 → `no "PACKAGED_UNIT_VALIDATION=FAIL"` (第99-103行)
- [x] Unit 模板占位符未替换 → FAIL (第78-81行)
- [x] `systemd-analyze verify` 已集成 (第135-142行)
- [x] 动态生成 Unit 明确标注"诊断用，不计入正式 PASS" (第105-132行)

#### R3-c: 删除 root 级 `pkill -f` ✅

**文件**: 
- `os-agent-integration/echo/test_systemd_lifecycle.sh` (第148-163行)
- `os-agent-integration/echo/install_systemd.sh` (第74-87行)

- [x] 移除所有 `pkill -f "kylin-memory-echo-server"` 
- [x] 改用 `systemctl stop` + `systemctl show -p MainPID` + PID 校验
- [x] 停止后检查 MainPID 已退出 (第152-158行)

---

### P0-3: 统一唯一部署路径并闭合干净部署流程

✅ **已完成** — 2026-08-07

#### 统一方案: Gate 0 布局

```
/home/<user>/kylin-memory-echo/
├── bin/
│   ├── kylin-memory-echo-server
│   ├── echo_client
│   └── kaiming_memory_client
├── share/
│   └── kylin-memory-echo.service   (仓库正式 Unit)
├── logs/
└── build/
```

#### 修改确认

- [x] `config/environment.example` (第24-42行): 删除 `/usr/local/bin` 路径描述，改为统一布局文档
- [x] `install_systemd.sh` (第34行): `DEPLOY_BASE="/home/$TARGET_USER/kylin-memory-echo"`
- [x] `test_systemd_lifecycle.sh` (第42行): `DEPLOY_BASE="/home/${KUSER}/kylin-memory-echo"`
- [x] `packaging/systemd/kylin-memory-echo.service` (第12行): `/home/__USERNAME__/kylin-memory-echo/bin/...`
- [x] 模式边界: dev=`/tmp/...` ; systemd=`/run/...` 已固定

#### 干净部署流程验证 ⬜ 待麒麟 VM 执行

- [ ] 传输全部源码和脚本
- [ ] `cmake configure && cmake build` 成功
- [ ] 两个客户端安装/复制到固定 `bin/`
- [ ] 三个必需产物存在且可执行
- [ ] 安装仓库正式 Unit
- [ ] `systemctl start` 成功
- [ ] C++ Client 验证通过

---

### P0-4: 移除 `evidence.record` API

✅ **已完成** — 2026-08-07

**文件**: `os-agent-integration/echo/memory_echo_server.py` (304行 → 257行)

- [x] 删除 `handle_evidence_record()` 函数
- [x] 删除 `METHOD_ROUTER` 中的 `"evidence.record": handle_evidence_record`
- [x] 文件中保留注释说明: "evidence.record API 已移除 (P0-4, PR21 R3 Review), 证据应由独立 Runner 生成"
- [x] 证据由独立 Runner (`pr21_r3_verify.py`) 在测试结束后生成

---

### P0-5: 重建绑定最新 Head 的证据链

⬜ **待完成** — 依赖 P0-1~4 代码修复全部完成后的麒麟 VM L2 运行

**当前状态**: 
- `evidence/index.yaml` ECHO-005 中 `tested_commit` 仍为 `830e694...` (旧Commit)
- `pr21_r3_verify.py` 已新增为 R3 轮次的独立证据验证脚本

**修复步骤**:
- [x] P0-1 至 P0-4 代码修复全部完成
- [ ] 在麒麟 VM 最新 Head 上重新执行完整 L2 测试 (使用 `pr21_r3_verify.py`)
- [ ] 生成新的 `evidence.jsonl`
- [ ] 确保以下四处完全一致: 原始运行日志 / evidence.jsonl / evidence/index.yaml / PR 正文
- [ ] 不得出现 `日志 FAIL + index PASS + PR 正文 0 FAIL`
- [ ] 不得手工把旧 evidence 的 `tested_commit` 替换成新 SHA
- [ ] ECHO-009 FAIL 通过重新构建+部署解决

---

### P0-6: 修正完成状态口径

✅ **已完成** — 2026-08-07

- [x] `evidence/index.yaml` ECHO-005 (第223-240行):
  - `ACL_SPIKE=VERIFIED` ✅
  - `KYSEC_REAL_RULE=UNVERIFIED` (Gate 0 不具备 KYSEC 管理员 token 和内核模块加载权限) ✅
- [x] `D2-1-KAIMING-HOOK` 状态: `BLOCKED` (第245行) ✅
  - limitations 明确: 闭源二进制 + 无SDK构建环境 + 无签名权限 + Socket路径硬编码
- [x] 不再出现"模拟客户端=真实Kaiming Hook"或"ACL=真实KYSEC"等等价混淆
- [ ] PR 标题和正文需在 P0-5 完成后同步更新

---

## 二、P1 自检清单（下一轮提交前逐项确认）

### A. 代码静态检查

- [ ] `bash -n os-agent-integration/echo/deploy_echo.sh` → exit 0
- [ ] `bash -n os-agent-integration/echo/install_systemd.sh` → exit 0
- [ ] `bash -n os-agent-integration/echo/test_systemd_lifecycle.sh` → exit 0
- [ ] `bash -n os-agent-integration/echo/test_rollback.sh` → exit 0
- [ ] `bash -n os-agent-integration/echo/kysec_authorize.sh` → exit 0
- [ ] `python3 -m py_compile os-agent-integration/echo/memory_echo_server.py` → exit 0
- [ ] `g++ -std=c++17 -Wall -Wextra -fsyntax-only os-agent-integration/echo/echo_client.cpp` → exit 0
- [ ] `g++ -std=c++17 -Wall -Wextra -fsyntax-only os-agent-integration/echo/kaiming_memory_client.cpp` → exit 0

### B. 干净构建

- [ ] `cmake -S os-agent-integration/echo -B /tmp/pr21-clean-build` → exit 0
- [ ] `cmake --build /tmp/pr21-clean-build` → 生成 `echo_client` + `kaiming_memory_client`
- [ ] 产物按统一布局进入固定 `bin/`

### C. 协议验证 ⬜ 待麒麟 VM

- [ ] `kaiming_memory_client --method all` 输出:
  ```text
  KAIMING-ECHO       PASS
  KAIMING-HEALTH     PASS
  KAIMING-RETRIEVE   PASS
  KAIMING-STORE      PASS
  KAIMING-UNKNOWN    PASS
  KAIMING-RAPID      PASS
  Passed: 6 / Failed: 0 / Exit code: 0
  ```
- [ ] STORE 确认: `status=error, error_code=UNSUPPORTED_METHOD`
- [ ] UNKNOWN 确认: `status=error, error_code=UNSUPPORTED_METHOD`

### D. systemd 验证 ⬜ 待麒麟 VM

- [ ] 使用仓库正式 Unit: `packaging/systemd/kylin-memory-echo.service`
- [ ] 独立输出: `PACKAGED_UNIT_VALIDATION` / `SYSTEMD_SERVER_LIFECYCLE` / `CPP_CLIENT_OVER_SYSTEMD` / `PYTHON_DIAGNOSTIC_FALLBACK`
- [ ] Python fallback 不计入 C++ PASS

### E. 部署验证 ⬜ 待麒麟 VM

- [ ] 从干净 VM 快照开始全链路: deploy → build → 固定bin产物 → 正式Unit install → start → C++ Client → stop → uninstall → 测试资源清理

### F. 证据验证 ⬜ 待麒麟 VM

- [ ] `tested_commit` = 新的实际 Head (40位SHA)
- [ ] `evidence.jsonl` = 新运行生成
- [ ] `source_log` = 全部存在
- [ ] `sha256` = 与 `source_log` 实际一致
- [ ] `index` = 与 `evidence.jsonl` 一致

### G. 未完成项目状态 ✅ 代码层面已修正

- [x] `REAL_KAIMING_HOOK=BLOCKED/UNVERIFIED` (index.yaml D2-1-KAIMING-HOOK 状态已为 BLOCKED)
- [x] `KYSEC_REAL_RULE=UNVERIFIED` (index.yaml ECHO-005 limitations 中已声明)
- [x] `ORIGINAL_RESTORE=UNVERIFIED` (test_rollback.sh 中已诚实声明 TEST RESOURCE CLEANUP ONLY)

---

## 三、允许后移的项目（不阻断合并）

### P1: 相关模块开始前关闭

- [ ] 任意用户文本的 JSON 转义
- [ ] partial send/recv
- [ ] Socket 连接和读写超时
- [ ] request_id/trace_id 唯一化
- [ ] response request_id 关联校验
- [ ] `strncpy` 路径长度和 NUL 终止
- [ ] 旧 Unit 备份及安装失败恢复
- [ ] ACL 路径白名单和 owner 安全校验
- [ ] owner/group/mode/ACL 的精确回退比较

### 技术债 / Gate 1

- [ ] 真实 Kaiming Hook
- [ ] Kaiming `/proc/<pid>/...` 完整采集
- [ ] 真实 KYSEC 规则写入
- [ ] Qt5 QLocalSocket 后端
- [ ] Server 并发处理
- [ ] 生产级 systemd 沙箱
- [ ] 日志轮转
- [ ] 多用户隔离
- [ ] 性能和并发压测
- [ ] 正式软件包级升级与回退
- [ ] `StrictHostKeyChecking=no` 的生产化修复

---

## 四、进度汇总

| 编号 | 问题 | 状态 | 负责 | 备注 |
|------|------|:----:|------|------|
| P0-1-a | JSON 多余闭合括号 | ✅ | — | kaiming_memory_client.cpp:156 已删除 |
| P0-1-b | unknown 断言 | ✅ | — | kaiming_memory_client.cpp:221-223 已修复 |
| P0-1-c | 协议验收 (6/6 VM) | ⬜ | 麒麟 VM | 需 `pr21_r3_verify.py` 执行 |
| P0-2-a | Python fallback 假阳性 | ✅ | — | test_systemd_lifecycle.sh:272-421 已拆分 |
| P0-2-b | 动态 Unit 假阳性 | ✅ | — | test_systemd_lifecycle.sh:68-142 PACKAGED_UNIT_VALIDATION |
| P0-2-c | pkill -f 移除 | ✅ | — | test_systemd_lifecycle.sh + install_systemd.sh 已改用 systemctl stop+MainPID |
| P0-3 | 部署路径统一 | ✅ | — | 7 文件全部使用 /home/<user>/kylin-memory-echo/ |
| P0-4 | evidence.record 删除 | ✅ | — | memory_echo_server.py 304→257行，已移除 |
| P0-5 | 证据链重建 | ⬜ | 麒麟 VM | pr21_r3_verify.py 已就绪，待执行 |
| P0-6 | 状态口径修正 | ✅ | — | index.yaml KYSEC_REAL_RULE=UNVERIFIED + Hook=BLOCKED |
| P1-A | 静态检查 | ⬜ | 本地/麒麟 VM | 全部 .sh/.py/.cpp |
| P1-B | 干净构建 | ⬜ | 麒麟 VM | CMake |
| P1-C | 协议验证 6/6 | ⬜ | 麒麟 VM | kaiming_memory_client |
| P1-D | systemd 验证 | ⬜ | 麒麟 VM | test_systemd_lifecycle.sh |
| P1-E | 部署验证 | ⬜ | 麒麟 VM | 全链路 |
| P1-F | 证据验证 | ⬜ | 麒麟 VM | evidence/* |
| P1-G | 未完成项状态 | ✅ | — | 各文件状态声明已修正 |

---

## 五、下一轮提交前关键行动项

1. **在麒麟 VM 上执行 `pr21_r3_verify.py`** — 完成 P0-1-c / P0-5 / P1-A~F
2. **生成新 evidence.jsonl** — tested_commit 绑定最新 Head
3. **更新 evidence/index.yaml** — ECHO-005 tested_commit 和 evidence_commit 改为最新 SHA
4. **更新 PR 标题** — 移除 `P0全清 | 0 FAIL`，改为与真实证据一致的表述

**代码层面修复 (P0-1~4, P0-6) 全部完成。剩余工作集中在麒麟 VM 上的一次完整 L2 执行和证据生成。**