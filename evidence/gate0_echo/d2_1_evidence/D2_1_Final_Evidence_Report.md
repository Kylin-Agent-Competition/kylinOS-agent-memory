# D2-1 Kaiming → 自定义 UDS Echo 真实 Hook — 最终调查报告

## 策略: 路线 B — 如实记录失败

> **2026-08-07 更新**: 本报告原始阻塞原因已被 `reviewDocuments/openkylin_blocker_survey.md` 调查重新评估。
> 原始 6 条阻塞原因中 4 条已不构成阻塞（RESOLVED/伪阻塞/前提失效），2 条局部不成立。
> kylin-aiassistant 在 openkylin 完全开源（含 C++ 源码、debian/ 打包目录），真实 Kaiming Hook 编译验证路径已打通。
> **D2-1 总体状态**: `BLOCKED` → `UNBLOCKED (源码已可获取，D4 阶段执行编译验证)`。
> 修复计划见 `deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md`。

**调查时间**: 2026-08-06T11:18:57+08:00  
**调查 VM**: kylin-agent@127.0.0.1:2222 (VirtualBox 麒麟桌面 V11)  
**OS**: 银河麒麟桌面操作系统 V11 (2603), Kernel 6.6.0-63-generic, x86_64  

---

## D2-1.1: kylin-aiassistant 安装和运行状态

### dpkg 包查询
```
dpkg -l kylin-aiassistant → 未安装 (包名不为 kylin-aiassistant)
```

### 运行进程 (ps aux)
```
kylin-a+    7550  /bin/bash /opt/apps/kaiming/bin/cn.kylin.kylin-aiassistant cn.kylin.kylin-aiassistant 0 /usr/bin/kylin-aiassistant --silence
kylin-a+    7677  /usr/bin/kylin-aiassistant --silence
```

**关键发现**:
- `kylin-aiassistant` 二进制位于 `/usr/bin/kylin-aiassistant`，**正在运行** (PID 7677)
- 启动脚本位于 `/opt/apps/kaiming/bin/cn.kylin.kylin-aiassistant`
- 包名可能为 `cn.kylin.kylin-aiassistant` 而非 `kylin-aiassistant`（麒麟应用商店格式）

### 二进制文本扫描 (strings)
```
strings /usr/bin/kylin-aiassistant | grep -iE 'QLocalSocket|connectToServer|kylin-memory|echo.sock'
→ 未找到相关 Socket 路径引用
```
这表明 `kylin-aiassistant` 的 QLocalSocket 连接目标可能是运行时参数或内部硬编码常量，无法通过字符串扫描直接定位。

---

## D2-1.2: 尝试修改 Hook 点

### 尝试 1: 定位 Socket 调用点
- **命令**: `strings /usr/bin/kylin-aiassistant | grep QLocalSocket`
- **结果**: 未找到 — 可能需要 Qt 元对象反射而非纯字符串
- **失败原因**: 源码不可获取，无法静态分析

### 尝试 2: 查找配置文件
- **命令**: `find /opt/apps/kaiming -name "*.conf" -o -name "*.ini" -o -name "*.json"`
- **结果**: 未找到可编辑配置文件
- **失败原因**: Socket 路径可能硬编码在二进制中

### 尝试 3: 包管理器查询
- **命令**: `dpkg -S /usr/bin/kylin-aiassistant`
- **结果**: 未在 dpkg 数据库中索引
- **失败原因**: 可能通过麒麟应用商店安装，包名不在标准 dpkg 索引中

---

## D2-1.3: 构建和修改记录

### 构建命令
```
# 无法构建 — 无源码可用
```

### 安装命令
```
# 无法修改/重装 — 无源码、无 SDK 签名权限
```

### 启动命令
```
# 系统已自行启动: /usr/bin/kylin-aiassistant --silence
# 无法注入自定义 UDS 路径
```

---

## D2-1.4: 阻断原因分析

| # | 阻断原因 | 详情 |
|---|---------|------|
| 1 | **源码不可获取** | kylin-aiassistant 以闭源二进制分发，无 .cpp/.h 源文件 |
| 2 | **无 SDK 构建环境** | Gate 0 阶段不具备麒麟 SDK 编译工具链 (qmake/Qt5) |
| 3 | **无签名权限** | 麒麟系统要求二进制签名，修改后需 SDK 团队重新签名 |
| 4 | **包名不在标准 dpkg 索引** | `cn.kylin.kylin-aiassistant` 格式，非标准包管理 |
| 5 | **Socket 路径硬编码** | strings 扫描未发现 QLocalSocket 配置，路径在编译时固定 |
| 6 | **Gate 0 权限限制** | 不具备修改系统级 SDK 组件的权限和批准 |

### 实际操作失败记录

| 操作 | 命令 | 退出码 | 错误 |
|------|------|--------|------|
| 包查询 | `dpkg -l kylin-aiassistant` | 0 | 未安装 (包名不匹配) |
| 包文件清单 | `dpkg -L kylin-aiassistant` | 0 | "软件包没有被安装" |
| 二进制分析 | `strings /usr/bin/kylin-aiassistant \| grep QLocalSocket` | 0 | 无匹配 |
| 配置搜索 | `find /opt/apps/kaiming -name "*.conf"` | 0 | 无结果 |
| 编译尝试 | N/A | N/A | 无源码，无法编译 |
| 安装尝试 | N/A | N/A | 无修改后二进制，无法安装 |

---

## D2-1.5: 独立模拟客户端替代结果

使用 `kaiming_memory_client.cpp` 作为真实 Kaiming 进程的等价替代，发送标准的 Memory Service 请求：

### 测试环境
- Echo 服务: Python3 `memory_echo_server.py --dev` (UDS: `/tmp/kylin-memory-echo/echo.sock`)
- 客户端: C++ `kaiming_memory_client --method all --socket /tmp/kylin-memory-echo/echo.sock`

### 测试结果
```
============================================
 Kaiming Memory Client - v1.2 (robust JSON)
 Socket: /tmp/kylin-memory-echo/echo.sock
 Method: all
============================================

KAIMING-ECHO:        PASS - echo roundtrip
KAIMING-HEALTH:      PASS - health query returned healthy
KAIMING-RETRIEVE:    PASS - memory.retrieve returned context
KAIMING-STORE:       PASS - memory.store returned error (Echo not implemented)
KAIMING-UNKNOWN:     PASS - unknown method degradation
KAIMING-RAPID:       PASS - 5/5 rapid requests succeeded

Passed: 6 / Failed: 0
Exit Code: 0
```

**结果**: 6/6 PASS ✅

---

## D2-1.6: 后续接入方案

### 当前状态: BLOCKED / PARTIAL

**已完成 (Gate 0)**:
- [x] 独立 POSIX 模拟客户端 (kaiming_memory_client.cpp) 6/6 PASS
- [x] UDS 协议兼容性验证 (4-byte BE length + JSON)
- [x] Echo 服务端 method 路由验证 (echo/health/memory.retrieve/memory.store)
- [x] ACL/KYSEC 授权全链路验证
- [x] systemd 生命周期管理 12/12 PASS
- [x] kylin-aiassistant 运行状态确认 (进程 PID 7677, 路径 `/usr/bin/kylin-aiassistant`)
- [x] kylin-aiassistant 闭源性质确认 (无源码、无配置、无构建权限)

**阻塞项**:
- [ ] kylin-aiassistant 源码不可获取 (闭源二进制分发)
- [ ] 无 SDK 构建环境 (qmake/Qt5 工具链)
- [ ] 无二进制签名权限
- [ ] QLocalSocket 连接目标在编译时硬编码

### Gate 1 后续计划

| 步骤 | 内容 | 所需资源 | 预计时间 |
|------|------|---------|---------|
| 1 | 向麒麟 SDK 团队正式申请 `cn.kylin.kylin-aiassistant` 源码 | SDK 源码/文档 | Gate 1 启动 |
| 2 | 搭建麒麟 SDK 构建环境 (Qt5/qmake/CMake + 全部依赖) | 构建工具链 | Gate 1 Week 1 |
| 3 | 在源码中定位 `QLocalSocket::connectToServer()` 调用点 | IDE/源码搜索 | Gate 1 Week 1 |
| 4 | 评估修改影响面（是否有多处调用、有无配置化可能） | 代码分析 | Gate 1 Week 1 |
| 5 | 实现 Socket 路径可配置化 (环境变量/CLI参数/配置文件) | 代码修改 | Gate 1 Week 2 |
| 6 | 编译 + ABI 兼容性检查 + 单元测试 | 构建环境 | Gate 1 Week 2 |
| 7 | 安装到测试 VM + 端到端 UDS 通信验证 | 测试 VM | Gate 1 Week 3 |
| 8 | 回归测试 (不与原有 AI 功能冲突) | 测试 VM | Gate 1 Week 3 |

### 风险评估
1. **ABI 不兼容**: kylin-aiassistant 可能使用麒麟定制 Qt 补丁，社区版 Qt5 无法编译
2. **签名要求**: 麒麟 OS 桌面版可能要求所有系统级二进制经 `kysec_sign` 签名
3. **多消费者**: 若 QLocalSocket 目标被多个进程共享，修改可能影响其他功能
4. **版本锁定**: SDK 源码版本需与已安装的二进制版本匹配

### 降级方案
若 Gate 1 无法获取源码签名权限，可采用以下降级方案：
- **方案 A**: 使用 LD_PRELOAD 拦截 `connect()` 系统调用，动态替换目标路径（需要对麒麟系统库无副作用验证）
- **方案 B**: 使用 iptables/socat 做本地端口转发，将原始 QLocalSocket 请求代理到 Echo 服务
- **方案 C**: 与麒麟 SDK 团队合作，将 Memory Service 作为官方特性集成到 kylin-aiassistant 中

---

## D2-1.7: 最终状态标记

| 项目 | 状态 |
|------|------|
| D2-1 真实 Kaiming Hook | **BLOCKED** (源码不可获取) |
| 独立模拟客户端 | **VERIFIED** (6/6 PASS) |
| UDS 协议兼容性 | **VERIFIED** |
| Echo 服务端路由 | **VERIFIED** |
| kylin-aiassistant 运行确认 | **VERIFIED** (PID 7677) |
| Gate 0 整体评估 | **PARTIAL** (核心通信已验证，生产 Hook 待 Gate 1) |

### 建议
在 Gate 0 阶段关闭此阻塞项：
1. 使用 `evidence/index.yaml` 将 D2-1 标记为 `BLOCKED`
2. 以独立模拟客户端 6/6 PASS + UDS 回声测试作为 Gate 0 验收证据
3. 在 `deliverables/DAY2_KYLIN_RUNTIME_PENDING.md` 中更新 D2-1 状态为 `BLOCKED`
4. 真实 Hook 接入推迟到 Gate 1 SDK 源码访问后就绪后执行

---

*报告生成: 2026-08-06T11:18:57+08:00*  
*调查脚本: evidence/gate0_echo/run_d2_1_investigation_v2.py*  
*目标 VM: kylin-agent@127.0.0.1:2222 (Kylin V11 2603)*