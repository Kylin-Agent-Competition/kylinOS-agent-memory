# openkylin 阻塞项修复计划

> **依据文档**: `reviewDocuments/openkylin_blocker_survey.md` (2026-08-07)
> **关联决策**: `D4_GATE0_FORMAL_DECISION_20260807.md` §1.4、§二 ADR-004
> **关联待办**: `DAY2_KYLIN_RUNTIME_PENDING.md` D2-1
> **关联任务卡**: `D1_OS_Agent_调用链与Hook_Spike_任务卡.md` §3.3 Hook C
> **关联技术债**: R-ARCH-05、TD-007
> **计划日期**: 2026-08-07
> **执行窗口**: D4 阶段
> **执行环境**: 麒麟 VM (KylinOS V11 x86_64)

---

## 〇、背景

`openkylin_blocker_survey.md` 对 D2-1 阶段标记的 6 条阻塞原因进行了逐项核查，结论如下：

| # | 原阻塞原因 | 调查结论 | 新状态 |
|---|-----------|---------|--------|
| 1 | 闭源二进制，源码不可获取 | kylin-aiassistant 在 openkylin 完全开源，含 C++ 源码、debian/ 打包目录 | **RESOLVED** |
| 2 | 无 SDK 构建环境 | README 提供 Build-Depends，kylin-ai-subsystem 提供 build-deploy.sh | **RESOLVED** |
| 3 | 无签名权限 | dpkg-buildpackage -us -uc 无需签名；qmake && make 本地编译同样无需签名 | **局部 RESOLVED**（仅生产部署需签名） |
| 4 | Socket 路径硬编码（strings 未发现） | 源码可获取后，无需再依赖黑盒扫描，可在源码层直接审计/修改 | **前提失效** |
| 5 | Gate 0 不具备修改麒麟 SDK 组件的权限 | 源码开源后，Gate 0 可在 VM 内独立 clone、修改、编译 | **伪阻塞** |
| 6 | 无 QLocalSocket 配置点 | 同 #4，源码层可审计 ChatOperator → kylin-ai-base 调用链 | **前提失效** |

**核心结论**: 6 条原始阻塞原因中 4 条已不构成阻塞（RESOLVED/伪阻塞/前提失效），2 条局部不成立。真实 Kaiming Hook 编译验证的路径已打通，可在 D4 阶段推进。

---

## 一、修复阶段总览

```
阶段 0 (即时)  →  阶段 1 (D4-W1)  →  阶段 2 (D4-W1)  →  阶段 3 (D4-W2)  →  阶段 4 (D4-W2)  →  阶段 5 (D4-W2)
文档更新           源码获取与编译       Socket 路径审计      集成测试            Tool Hook 验证      证据收集与 TD 关闭
(无需 VM)         (麒麟 VM)           (麒麟 VM + 源码分析)  (麒麟 VM)          (麒麟 VM)           (证据整理)
```

| 阶段 | 名称 | 预计耗时 | 前置依赖 | 产出 |
|------|------|---------|---------|------|
| 0 | 文档更新 | 即时 | 无 | D2-1 调查报告更新、evidence/index.yaml 更新 |
| 1 | 源码获取与编译验证 | 1-2h | 阶段 0 | kylin-aiassistant 二进制 + 编译日志 |
| 2 | Socket 路径审计与修改 | 2-4h | 阶段 1 | Socket 调用链分析报告 + 路径修改 patch |
| 3 | UDS Echo 集成测试 | 1-2h | 阶段 2 | 真实 kylin-aiassistant → Memory Service Echo 全链路证据 |
| 4 | Tool Result Hook 验证 | 2-4h | 阶段 3 | ToolExecutionEvent 捕获证据（关闭 TD-007 前置） |
| 5 | 证据收集与技术债关闭 | 1h | 阶段 3-4 | L2 证据包、R-ARCH-05 状态更新、TD-007 进展更新 |

---

## 二、阶段 0：文档更新（即时执行，无需 VM）

### 0.1 更新 D2-1 调查报告

**文件**: `evidence/gate0_echo/d2_1_evidence/D2_1_Final_Evidence_Report.md`

**修改内容**:
- 在报告顶部增加 "2026-08-07 更新" 章节
- 引用 `reviewDocuments/openkylin_blocker_survey.md` 调查结论
- 将 6 条阻塞原因逐条标注新状态: RESOLVED / 局部 RESOLVED / 前提失效 / 伪阻塞
- 更新 D2-1 总体状态: `BLOCKED` → `UNBLOCKED (源码已可获取，D4 阶段执行编译验证)`

### 0.2 更新 evidence/index.yaml

**条目**: `D2-1-KAIMING-HOOK`

**修改内容**:
```yaml
D2-1-KAIMING-HOOK:
  status: UNBLOCKED  # 原 BLOCKED
  status_note: |
    2026-08-07: openkylin_blocker_survey.md 调查确认 kylin-aiassistant 完全开源。
    原始 6 条阻塞原因中 4 条已不构成阻塞。
    真实编译验证在 D4 阶段执行（见 OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md）。
  unblocked_by: reviewDocuments/openkylin_blocker_survey.md
  remediation_plan: deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md
```

### 0.3 更新技术债 R-ARCH-05 状态

**文件**: `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`

**修改内容**: R-ARCH-05 状态从"维持"更新为 "In Progress"，备注补充 survey 结论和修复计划引用。

---

## 三、阶段 1：源码获取与编译验证（麒麟 VM）

### 3.1 环境准备

```bash
# 确认麒麟 VM 网络可达 Gitee
ping -c 2 gitee.com

# 安装构建依赖（来自 kylin-aiassistant debian/control）
sudo apt-get build-dep -y kylin-aiassistant 2>/dev/null || \
  sudo apt-get install -y qt5-qmake qtbase5-dev libqt5sql5-sqlite \
    libkyai-assistant-dev libkyai-config-dev build-essential devscripts fakeroot

# 创建工作目录
mkdir -p ~/openkylin-build && cd ~/openkylin-build
```

### 3.2 克隆源码

```bash
# 克隆 kylin-aiassistant
git clone https://gitee.com/openkylin/kylin-aiassistant.git
cd kylin-aiassistant
git log --oneline -5 > ~/openkylin-build/kylin-aiassistant_commit.log

# 可选：克隆 kylin-ai-subsystem（获取统一构建脚本）
cd ~/openkylin-build
git clone https://gitee.com/openkylin/kylin-ai-subsystem.git
```

### 3.3 编译验证（方式 A：qmake 本地编译）

```bash
cd ~/openkylin-build/kylin-aiassistant
qmake kylin-aiassistant.pro 2>&1 | tee ~/openkylin-build/build_qmake.log
make -j$(nproc) 2>&1 | tee ~/openkylin-build/build_make.log

# 验证产出
ls -la kylin-aiassistant
file kylin-aiassistant
```

### 3.4 编译验证（方式 B：dpkg-buildpackage，备用）

```bash
cd ~/openkylin-build/kylin-aiassistant
dpkg-buildpackage -us -uc -b 2>&1 | tee ~/openkylin-build/build_deb.log
```

### 3.5 依赖库源码获取

```bash
cd ~/openkylin-build
for repo in kylin-ai-runtime kylin-ai-sdk kylin-ai-engine-plugins kylin-ai-model-manager; do
  git clone https://gitee.com/openkylin/${repo}.git 2>&1
done

# 记录所有仓库 commit
for d in */; do
  echo "=== $d ===" >> all_commits.log
  git -C "$d" log --oneline -3 >> all_commits.log
done
```

### 3.6 阶段 1 产出

| 文件 | 内容 |
|------|------|
| `kylin-aiassistant_commit.log` | kylin-aiassistant 源码 commit 记录 |
| `all_commits.log` | 所有克隆仓库的 commit 记录 |
| `build_qmake.log` | qmake 配置输出 |
| `build_make.log` | make 编译输出 |
| `build_deb.log` | dpkg 打包输出（如执行） |

---

## 四、阶段 2：Socket 路径审计与修改（麒麟 VM + 源码分析）

### 4.1 定位 ChatOperator 调用链

```bash
cd ~/openkylin-build/kylin-aiassistant

# 搜索 QLocalSocket 相关引用
grep -rn "QLocalSocket\|connectToServer\|localSocket\|local_socket" --include="*.cpp" --include="*.h" .

# 搜索 kylin-ai-base 相关引用
grep -rn "kylin-ai-base\|kyai-base\|kyai_base\|chatAsync\|assistant\.sock" --include="*.cpp" --include="*.h" .

# 搜索 ChatOperator 类定义
grep -rn "ChatOperator\|chatOperator\|chat_operator" --include="*.cpp" --include="*.h" .

# 搜索 Socket 路径定义（可能在 .conf / .json / .ini 中）
grep -rn "assistant\.sock\|kylin-ai-runtime\|/tmp/\.kylin" . --include="*.cpp" --include="*.h" --include="*.conf" --include="*.json" --include="*.ini"
```

### 4.2 审计 Socket 建立过程

**需要回答的关键问题**:

| # | 问题 | 调查方法 |
|---|------|---------|
| Q1 | QLocalSocket 在哪个类/文件中初始化？ | 源码搜索 QLocalSocket 构造函数调用 |
| Q2 | connectToServer 的目标路径是如何确定的？ | 追踪路径变量的赋值来源 |
| Q3 | Socket 路径是否可通过环境变量注入？ | 搜索 getenv / qEnvironmentVariable 调用 |
| Q4 | Socket 路径是否可通过配置文件注入？ | 搜索 QSettings / config 文件读取 |
| Q5 | kylin-ai-base 库提供什么接口？ | 如未找到独立仓库，搜索 kylin-ai-sdk / kylin-ai-runtime 中相关头文件 |

### 4.3 制定 Socket 路径修改方案

根据审计结果，按优先级选择方案：

| 优先级 | 方案 | 条件 | 修改范围 |
|--------|------|------|---------|
| **P0** | 环境变量注入 | 源码已支持 `KMA_SOCKET_PATH` 或类似环境变量读取 | 零代码修改，仅需启动脚本 |
| **P1** | 配置文件注入 | 源码读取配置文件中的 socket 路径 | 修改配置文件 |
| **P2** | 编译期宏定义 | 路径在 .pro 文件或头文件中以宏定义 | 修改 .pro 文件添加 `DEFINES += KMA_SOCKET_PATH=...` |
| **P3** | 源码硬编码修改 | 路径直接写死在源码中 | 修改源码中的路径字符串，指向 `/tmp/kylin-memory-echo/echo.sock` |

### 4.4 执行路径修改并重新编译

```bash
cd ~/openkylin-build/kylin-aiassistant

# 根据 4.3 选择的方案执行修改
# 例 (P3): 修改源码中 assistant.sock 为 echo.sock
# sed -i 's|/tmp/.kylin-ai-runtime-unix/.*/assistant\.sock|/tmp/kylin-memory-echo/echo.sock|g' src/chatoperator.cpp

# 重新编译
make -j$(nproc) 2>&1 | tee ~/openkylin-build/build_make_patched.log

# 验证 patch
strings kylin-aiassistant | grep -E "echo\.sock|memory-echo|kylin-memory"
```

### 4.5 kylin-ai-base 接口确认

```bash
# 在 kylin-ai-sdk 或 kylin-ai-runtime 中搜索
cd ~/openkylin-build
grep -rn "kylin-ai-base\|kyai.base\|libkyai-base" --include="*.h" --include="*.cpp" --include="*.pro" .

# 查看 ChatOperator 对 kylin-ai-base 的实际调用
cd ~/openkylin-build/kylin-aiassistant
grep -B5 -A10 "ChatOperator\|chatAsync\|OsAssistant" src/*.cpp src/*.h 2>/dev/null | head -100
```

### 4.6 阶段 2 产出

| 文件 | 内容 |
|------|------|
| `socket_audit_report.md` | Socket 调用链完整分析，含调用点、路径来源、可修改性评估 |
| `socket_path_patch.diff` | 路径修改 patch（如有代码改动） |
| `kylin_ai_base_interface.md` | kylin-ai-base 接口分析（位置、调用方式、可替换性） |
| `build_make_patched.log` | patch 后编译日志 |

---

## 五、阶段 3：UDS Echo 集成测试（麒麟 VM）

### 5.1 测试环境准备

```bash
# 确保 Memory Echo Service 可用
ls -la /tmp/kylin-memory-echo/echo.sock

# 如未运行，启动 Echo 服务
python3 /path/to/kylin-memory-echo-server --dev &

# 确认 Socket 存在且有读写权限
ls -la /tmp/kylin-memory-echo/echo.sock
```

### 5.2 真实 kylin-aiassistant → Memory Service UDS Echo 测试

**目标**: 验证修改后的 kylin-aiassistant 能否成功建立 UDS 连接到 Memory Echo Service。

```bash
cd ~/openkylin-build/kylin-aiassistant

# 启动修改后的 kylin-aiassistant（dev 模式，不依赖完整 AI Runtime）
# 具体启动命令取决于 kylin-aiassistant 的入口和参数
./kylin-aiassistant --help 2>&1 | head -20

# 方式 A：前台运行，观察 Socket 连接日志
# 方式 B：strace 追踪 connect() 系统调用
strace -f -e trace=connect,sendto,recvfrom -o ~/strace_kylin_ai.log \
  ./kylin-aiassistant [启动参数] &

# 检查是否成功连接到 echo.sock
sleep 3
ss -x | grep echo.sock
```

### 5.3 Echo 回显验证

**验证步骤**:

| # | 操作 | 预期结果 |
|---|------|---------|
| 1 | 启动 Echo Service (dev 模式) | Socket 在 `/tmp/kylin-memory-echo/echo.sock` 创建 |
| 2 | 启动修改后的 kylin-aiassistant | 进程启动，连接到 echo.sock |
| 3 | 发送简单文本消息 | Echo Service 收到 JSON 请求并返回合法 JSON 响应 |
| 4 | 检查 Echo Service 日志 | 有 `ECHO-003` 相关连接和请求日志 |
| 5 | 发送 `memory.retrieve` 格式请求 | 返回 `status=="ok"` 的 Echo 响应 |
| 6 | 发送 `memory.store` 格式请求 | 返回 `status=="ok"` 的 Echo 响应 |

### 5.4 异常路径验证

| # | 场景 | 操作 | 预期结果 |
|---|------|------|---------|
| E1 | Echo Service 未启动 | 先启动 kylin-aiassistant | 连接失败，kylin-aiassistant 不应崩溃，有明确错误日志 |
| E2 | Echo Service 中途重启 | 启动 → kill Echo → 重启 Echo | 客户端正确重连或超时降级 |
| E3 | 超大消息 | 发送 10KB+ 消息 | 协议正常分帧/截断，不崩溃 |

### 5.5 阶段 3 产出

| 文件 | 内容 |
|------|------|
| `strace_kylin_ai.log` | strace 系统调用追踪日志（connect/sendto/recvfrom） |
| `echo_integration_test.log` | 6 步 Echo 回显验证结果 |
| `echo_error_path_test.log` | 3 种异常路径测试结果 |

---

## 六、阶段 4：Tool Result Hook 验证（麒麟 VM）

> **关联**: D1 任务卡 §3.3 Hook C、TD-007
> **前置条件**: 阶段 3 通过（Echo 全链路通）

### 6.1 定位 sendToolMessage 调用路径

```bash
cd ~/openkylin-build/kylin-aiassistant

# 搜索 Tool 相关调用
grep -rn "sendToolMessage\|toolMessage\|ToolResult\|tool_result\|toolCall\|tool_call" \
  --include="*.cpp" --include="*.h" .

# 搜索 Tool 结果回调
grep -rn "onToolResult\|toolResult\|toolFinished\|toolFailed" \
  --include="*.cpp" --include="*.h" .
```

### 6.2 实现 ToolExecutionEvent 捕获（最小修改）

参考 D1 任务卡 §3.3 的 ToolExecutionEvent Schema（02 表31），在 `sendToolMessage` 路径加入观察点：

```cpp
// 最小修改语义 (伪代码，具体位置待源码审计确认)
void onToolResult(const ToolResult& result) {
    ToolExecutionEvent event{
        .tool_call_id = result.callId,
        .tool_name = result.toolName,
        .arguments = result.arguments,
        .started_at = result.startedAt,
        .finished_at = result.finishedAt,
        .status = result.success ? "success" : "failure",
        .result = result.success ? result.data : "",
        .error = result.success ? "" : result.errorMessage,
        .side_effect = result.sideEffect,
        .user_confirmed = result.userConfirmed,
        .rollback_status = "none",
        .source_trace_id = currentTraceId
    };
    memoryClient.observeToolEventAsync(event);
}
```

### 6.3 Tool Result 场景测试矩阵

| 场景 | Tool 类型 | 触发方式 | 预期 ToolExecutionEvent | 通过标准 |
|------|----------|---------|------------------------|---------|
| T1 | 成功 Tool | 触发一次成功的工具调用（如天气查询、计算器） | status=success, result 非空 | 结构化事件正确生成 |
| T2 | 失败 Tool | 触发一次会失败的工具调用 | status=failure, error 非空 | error 字段完整 |
| T3 | 取消 Tool | 用户中断进行中的 Tool | status=cancelled | cancelled 状态正确 |
| T4 | Prompt Skill 不误判 | 触发翻译/润色/总结 | 不生成 ToolExecutionEvent | 不产生误报 |
| T5 | 失败 Tool 不形成成功知识 | 检查知识候选列表 | 不包含成功记忆 | FailureMemory 仅记录失败 |

### 6.4 阶段 4 产出

| 文件 | 内容 |
|------|------|
| `tool_hook_audit.md` | sendToolMessage 调用链分析 |
| `tool_hook_patch.diff` | ToolExecutionEvent 捕获代码 patch |
| `tool_result_test_matrix.log` | 5 种场景测试结果 |

---

## 七、阶段 5：证据收集与技术债关闭

### 7.1 证据收集

```bash
# 在麒麟 VM 中执行
mkdir -p ~/evidence/d4_openkylin_remediation

# 复制所有产出到证据目录
cp ~/openkylin-build/*.log ~/evidence/d4_openkylin_remediation/
cp ~/openkylin-build/*.diff ~/evidence/d4_openkylin_remediation/
cp ~/openkylin-build/*.md ~/evidence/d4_openkylin_remediation/

# 生成 SHA-256 校验
cd ~/evidence/d4_openkylin_remediation
sha256sum * > MANIFEST.sha256
```

### 7.2 上传到项目仓库

```bash
# 从宿主机执行
scp -P $KYLIN_VM_PORT $KYLIN_VM_USER@$KYLIN_VM_HOST:~/evidence/d4_openkylin_remediation/* \
  evidence/l2-kylin-vm/d4_openkylin_remediation/
```

### 7.3 技术债状态更新

**R-ARCH-05**（真实 Kaiming Hook 未验证）:

| 当前 | 阶段 3 后 | 阶段 4 后 | 最终 |
|------|----------|----------|------|
| 维持 | Echo 全链路验证通过 → In Progress | Tool 事件捕获通过 → Resolved | 需 D 主审确认关闭 |

**TD-007**（真实 Tool Result Hook 宿主验证）:

| 当前 | 阶段 4 后 |
|------|----------|
| Open / PLANNED | Tool Result 5 场景全通过 → Resolved |

### 7.4 Gate 0 第 3 项重新评估

| 子项 | 当前状态 | 修复后状态 |
|------|---------|-----------|
| 模拟客户端 | PASS | PASS (不变) |
| 真实 Hook | BLOCKED（源码已开源，待编译验证） | **PASS**（D4 VM 编译 + Echo + Tool 全部通过后） |

### 7.5 阶段 5 产出

| 文件 | 内容 |
|------|------|
| `MANIFEST.sha256` | 所有证据文件 SHA-256 校验 |
| `REMEDIATION_COMPLETION_REPORT.md` | 修复完成报告，包含所有阶段结果汇总、Gate 0 重新评估、TD 更新建议 |
| `evidence/index.yaml` diff | 新增条目 `D4-OPENKYLIN-HOOK` |

---

## 八、风险与回退

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| kylin-aiassistant 编译依赖缺失 | 中 | 阶段 1 阻塞 | 使用 kylin-ai-subsystem/build-deploy.sh 自动解析依赖；手动安装缺失包 |
| Socket 路径完全硬编码且无法通过 patch 修改 | 低 | 阶段 2 阻塞 | 使用 LD_PRELOAD 拦截 connect()；或使用 socat 做 UDS 转发 |
| kylin-ai-base 是闭源 .so | 低 | 阶段 2 部分阻塞 | 在 kylin-ai-sdk 源码层分析接口；如闭源则只能依赖 LD_PRELOAD |
| 修改后的 kylin-aiassistant 需要完整 AI Runtime 才能启动 | 中 | 阶段 3 阻塞 | 检查是否有 --headless / --no-runtime 参数；使用 mock runtime socket |
| Tool 路径在 UI 层触发，无法仅靠源码修改自动化测试 | 中 | 阶段 4 阻塞 | 手动操作麒麟桌面 AI 助手触发 Tool；或用 dbus/命令行注入模拟 |

**回退方案**: 所有修改在独立分支（`feat/d4-openkylin-hook`）进行，不影响替代架构路线（路线 B：独立 Qt 演示壳 + 执行日志 Adapter）。若阶段 1-4 任何一步失败超过 4 小时，回退到 ADR-004 替代架构，真实 Hook 标记为 BLOCKED 并延迟到 Gate 1。

---

## 九、时间估算

| 阶段 | 预计耗时 | 累计 |
|------|---------|------|
| 阶段 0（文档更新） | 30 min | 30 min |
| 阶段 1（源码获取与编译） | 1-2h | 2-2.5h |
| 阶段 2（Socket 审计与修改） | 2-4h | 4-6.5h |
| 阶段 3（UDS Echo 集成测试） | 1-2h | 5-8.5h |
| 阶段 4（Tool Hook 验证） | 2-4h | 7-12.5h |
| 阶段 5（证据收集与 TD 关闭） | 1h | 8-13.5h |

**总计**: 1-2 个工作日（含编译等待、调试和异常处理余量）。

---

## 十、检查清单

- [ ] **阶段 0**: D2-1 调查报告已更新 RESOLVED 状态
- [ ] **阶段 0**: evidence/index.yaml D2-1-KAIMING-HOOK 状态更新
- [ ] **阶段 0**: R-ARCH-05 技术债状态更新为 In Progress
- [ ] **阶段 1**: kylin-aiassistant 源码 clone 成功并记录 commit
- [ ] **阶段 1**: qmake && make 编译通过
- [ ] **阶段 1**: 依赖库（kylin-ai-runtime/sdk/engine-plugins/model-manager）clone 成功
- [ ] **阶段 2**: ChatOperator → QLocalSocket 调用链完整分析完成
- [ ] **阶段 2**: Socket 路径可修改性评估完成（环境变量/配置文件/宏/硬编码）
- [ ] **阶段 2**: 路径修改 patch 已应用并重新编译通过
- [ ] **阶段 2**: kylin-ai-base 接口位置和调用方式已确认
- [ ] **阶段 3**: 修改后的 kylin-aiassistant 成功连接到 Echo Service
- [ ] **阶段 3**: 6 步 Echo 回显验证全部通过
- [ ] **阶段 3**: 3 种异常路径测试全部通过
- [ ] **阶段 4**: sendToolMessage 调用路径已定位
- [ ] **阶段 4**: ToolExecutionEvent 捕获代码已加入并编译通过
- [ ] **阶段 4**: 5 种 Tool Result 场景测试全部通过
- [ ] **阶段 5**: 所有证据文件 SHA-256 校验并上传
- [ ] **阶段 5**: R-ARCH-05 更新为 Resolved（或标注未通过项）
- [ ] **阶段 5**: TD-007 更新为 Resolved（或标注未通过项）
- [ ] **阶段 5**: 修复完成报告已提交

---

> **下一步**: 阶段 0 可立即执行（纯文档更新，无需 VM）。阶段 1-5 在 D4 阶段按顺序执行，建议由轨道 C 开发者（刘承恩）与轨道 D 主审（周子腾）协作推进，阶段 3-4 的集成测试结果由 E（谢嘉然）做安全补审。