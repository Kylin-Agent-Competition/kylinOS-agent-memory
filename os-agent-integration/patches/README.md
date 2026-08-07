# Patches / LD_PRELOAD Hooks

本目录存放对上游闭源组件（libkyai-assistant.so）的运行时拦截方案。

---

## 背景

`libkyai-assistant.so.1.0.0` 是麒麟 AI 助手的核心运行时库，**闭源分发**（无 openkylin 源码）。
该库硬编码了 Socket 路径 `/tmp/.kylin-ai-runtime-unix/<PID>/assistant.sock`，
无法在源码层修改。详见 `reviewDocuments/openkylin_blocker_survey.md` 和
`deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md` 第 8 章。

## P0 方案：LD_PRELOAD connect() 劫持

**原理**: 拦截 libc `connect()` 系统调用，检测目标路径是否包含 `kylin-ai-runtime-unix`，
若匹配则透明替换为 `/tmp/kylin-memory-echo/echo.sock`。

**优势**: 无需修改闭源 .so 或重签名，纯运行时方案。

### 文件清单

| 文件 | 用途 |
|------|------|
| `libconnect_hook.c` | LD_PRELOAD 共享库源码，拦截 `connect()` |
| `CMakeLists.txt` | CMake 构建配置（可选，gcc 单行编译亦可） |
| `test_connect_hook.sh` | 8 项集成测试（麒麟 VM 执行） |
| `deploy_hook.sh` | SSH 一键部署到麒麟 VM |

### 快速开始

```bash
# 在 Windows 开发机上:
bash deploy_hook.sh <麒麟VM_IP>

# 在麒麟 VM 上运行测试:
ssh kylin@<麒麟VM_IP>
bash ~/kylin-memory-echo/share/test_connect_hook.sh
```

### 手动编译

```bash
# 麒麟 VM 上:
gcc -shared -fPIC -O2 -ldl -o libconnect_hook.so libconnect_hook.c
```

### 使用方式

```bash
# 针对真实 kylin-aiassistant:
CONNECT_HOOK_DEBUG=1 \
LD_PRELOAD=/path/to/libconnect_hook.so \
  /opt/kaiming/layers/stable/.../files/bin/kylin-aiassistant

# 环境变量:
#   CONNECT_HOOK_MATCH     - 路径匹配子串 (默认: kylin-ai-runtime-unix)
#   CONNECT_HOOK_REDIRECT  - 重定向目标   (默认: /tmp/kylin-memory-echo/echo.sock)
#   CONNECT_HOOK_DEBUG     - 调试日志     (1 或 true)
```

### 测试场景矩阵

| # | 场景 | 预期 | 状态 |
|---|------|------|------|
| 1 | 直接连接 echo.sock（无 hook） | PASS | 待麒麟 VM 验证 |
| 2 | connect() 到 kylin-ai-runtime-unix 路径，hook 加载 | 重定向到 echo.sock，health check PASS | 待麒麟 VM 验证 |
| 3 | connect() 到非匹配路径，hook 加载 | 直通（pass-through），不影响 | 待麒麟 VM 验证 |
| 4 | 自定义 CONNECT_HOOK_MATCH 环境变量 | 按自定义子串匹配 | 待麒麟 VM 验证 |
| 5 | 自定义 CONNECT_HOOK_REDIRECT，无服务端 | connect() 失败（预期） | 待麒麟 VM 验证 |
| 6 | 连续 5 次重定向 | 全部成功，无句柄泄露 | 待麒麟 VM 验证 |
| 7 | 无 LD_PRELOAD，连接 mock 路径 | 连接失败（路径不存在） | 待麒麟 VM 验证 |
| 8 | 非匹配路径直通 | pass-through，不触发 MATCH | 待麒麟 VM 验证 |

### 架构约束

- **仅拦截 `connect()`**，不拦截 `socket()`/`bind()`/`socketpair()`
- **QLocalSocket 兼容**: Qt5 的 QLocalSocket 在 Linux 上底层使用 `socket() + connect()`，hook 对其透明
- **Abstract socket 安全**: `sun_path[0] == '\0'` 的 Linux abstract socket 不会被拦截
- **线程安全**: 只读全局变量 + `dlsym` 一次性初始化（`_dl_init` 阶段完成实际初始化）
- **调试**: `CONNECT_HOOK_DEBUG=1` 输出到 stderr，不污染 stdout

### 关联文档

- `reviewDocuments/openkylin_blocker_survey.md` — 闭源 .so 五维信息调查
- `deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md` — 修复计划（第 8 章：风险与回退）
- `os-agent-integration/D1_OS_Agent_调用链与Hook_Spike_任务卡.md` — Hook 点定义
- `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` — R-ARCH-05 真实 Kaiming Hook 未验证

---

## 使用规范

- 每个补丁对应一个上游组件和一个明确修改目的。
- 补丁命名：`<component>-<brief-description>.patch`
- 补丁应在源码中注明修改原因，并关联 ADR。
- 禁止存放完整的上游源码。
- LD_PRELOAD hook 源码同样适用上述规范，存放在本目录。