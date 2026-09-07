# D12-A Bridge 假实现/吞异常检查清单

> 对照：台账 D12-A 任务 ②「逐一核对 cpp-bridge 无假实现、无吞异常（对照 D11 期间 Bridge 安全审计口径）」。
> 基线：main @ d4f564c（D11A 已合并）。检查方式：源码逐行核对 + 既有测试覆盖核对。
> 结论：**✅ 无假实现、无吞异常**。两处"看似固定值"的实现均为**已登记 Wontfix 的 SDK 能力边界**（见 §4），非假实现。

## 1. 检查范围

| 文件 | 角色 |
|------|------|
| `cpp-bridge/src/embedding_bridge.cpp` | Bridge 核心实现（dlopen/dlsym/会话/embed） |
| `cpp-bridge/src/py_module.cpp` | pybind11 绑定 + BridgeError→Python 异常映射 |
| `cpp-bridge/include/embedding_bridge.h` | 接口声明 + 生命周期/终态注释 |
| `cpp-bridge/bridge_error_contract.h` | 错误码契约 + BridgeResult |
| `cpp-bridge/embedding_abi_compat.h` | ABI 状态标注 |
| `cpp-bridge/tests/*.cpp` | 测试覆盖核对（so_not_found / malformed / failure_recovery / destroyed / dlsym_missing / errors） |

## 2. 吞异常检查（逐 catch 核对）

| 位置 | catch 类型 | 行为 | 判定 |
|------|-----------|------|------|
| `load()` / `create_session()` / `destroy_session()` / `embed()` 外层 | `bad_alloc` | 返回 `BridgeStatus/BridgeResult::fail(UNKNOWN, "...bad_alloc")` | ✅ 非吞：转为错误码 |
| 同上 | `std::exception` | 返回 `fail(UNKNOWN, e.what())` | ✅ 非吞：异常原文进错误消息 |
| 同上 | `...` | 返回 `fail(UNKNOWN, "unknown exception")` | ✅ 非吞：捕获并显式失败 |
| `destroy_unlocked()`（析构） | noexcept | 符号缺失时 `fprintf(stderr, "session leaked")` 记录并接受泄漏 | ✅ 记录诊断，非静默 |
| `py_module.cpp raise_for_error` | switch 全覆盖 | 每个 BridgeError 枚举 → 对应 Python 异常；SUCCESS/NOT_IMPLEMENTED/UNKNOWN/default 全部显式抛出 | ✅ 无遗漏、无吞 |

**结论**：所有 catch 均将异常映射为结构化错误码返回，无空 catch、无 `catch(...){}` 静默吞掉、无"捕获后假装成功"路径。

## 3. 假实现检查（逐函数核对）

| 函数 | 实现性质 | 判定 |
|------|---------|------|
| `load()` | 真实 access/dlopen/dlsym + 符号存在性检查，必需符号缺失 → ERR_DLSYM_FAILED + fatal | ✅ 真实 |
| `create_session()` | 真实 `text_embedding_create_session` + `init_session`，NULL/非零 → 明确错误 | ✅ 真实 |
| `embed()` | 真实 `text_embedding` 调用 + 结果读取 + NaN/Inf/维度/NULL 畸形防御 | ✅ 真实 |
| `get_default_model_name()` | 返回 create_session 时缓存的模型名（SDK 日志确认值） | ✅ 见 §4-① |
| `refresh_model_name_cache_locked()` | 直接赋值固定模型名字符串 | ✅ 见 §4-① |
| `bridge_error_contract.h TimeoutConfig` | 定义了 embed_ms/batch_ms/init_ms 但 Bridge 层不主动中断 | ✅ 见 §4-② |
| `embed_impl()` 的 `timeout_ms` 参数 | 签名存在但未使用（`/*timeout_ms*/`） | ✅ 见 §4-② |
| `get_model_list` 相关符号 | dlsym 仅存在性检查，禁止外部调用（UAF 风险） | ✅ 见 §4-③ |

**结论**：生产路径全部真实调用 SDK；无固定返回向量、无 stub、无"返回成功但不做事"的实现。

## 4. 两处"看似固定值"的逐项判定（非假实现）

### ① 模型名 `ensemble-embd_gte-base_uint8-text`（TD-A-005-04 Wontfix）

- **现象**：`refresh_model_name_cache_locked()` 直接赋值固定模型名，不动态查询。
- **原因**：SDK `text_embedding_get_model_list` 在 `init_session` 内部使用后释放内部缓冲区，外部调用触发 use-after-free 段错误（TD-A-D9-SDK-MODEL-LIST-UAF，麒麟实测 10/10 段错误）。**无安全动态查询 API 可用**。
- **证据**：麒麟 VM 日志确认默认模型（`Get default model success, model: ensemble-embd_gte-base_uint8-text`），dim=768 实测，`evidence/l2-kylin-vm/td_a_005_04_model_name.log`。
- **判定**：✅ 有据可依的缓存值，非假实现。

### ② `timeout_ms` 无实际效果（TD-A-005-01 Wontfix）

- **现象**：Bridge `embed()` 的 `timeout_ms` 参数未使用；`TimeoutConfig` 定义了但 Bridge 不主动中断。
- **原因**：SDK 无 `text_embedding_cancel/abort/interrupt` API（麒麟实测，证据 `evidence/l2-kylin-vm/td_a_005_01_no_cancel_api.log`）。**Bridge 内部无 API 可调**。
- **现有缓解**：EmbeddingService 层 `fut.result(timeout)` 提供调用方超时保护（ERR_TIMEOUT 结构化返回不阻塞聊天线程）；**本 PR 新增第二层保障**——线程池挂死恢复（超时后无法中断的 worker 通过 hang 检测 + executor 重建释放，防永久占满）。
- **判定**：✅ 已登记 Wontfix + 本 PR 补强，非吞异常、非假实现。

### ③ `get_model_list` 符号仅作 dlsym 存在性检查（TD-A-D9-SDK-MODEL-LIST-UAF）

- **现象**：符号解析后保留，禁止外部调用。
- **原因**：UAF 段错误风险（同①）。
- **判定**：✅ 主动规避危险 API，非假实现。

## 5. 测试覆盖核对（对应检查项）

| 测试 | 覆盖 |
|------|------|
| `test_bridge_errors.cpp` | 未加载/未建会话错误码、错误码枚举无重叠、load 失败重试 |
| `test_bridge_malformed.cpp` | NULL/维度0/data NULL/NaN/Inf/embed false 畸形结果防御（7 项） |
| `test_bridge_failure_recovery.cpp` | .so 不存在可重试 / init_session 失败 fatal / create NULL / destroy 终态 |
| `test_bridge_destroyed.cpp` | destroy 终态稳定错误（create/embed 均 ERR_SESSION_DESTROYED） |
| `test_bridge_dlsym_missing.cpp` | dlsym 缺失 fatal 终态 + 稳定重试错误 |
| `test_bridge_so_not_found.cpp` | .so 不存在路径 |
| Python `test_exception_mapping.py` | pybind 异常类型存在 + 继承 BridgeError + 映射（WSL skip/L2 强制） |
| Python `test_provider_failure_recovery.py` | Provider 层错误码端到端映射（fatal/destroyed/dlsym/initfail） |

## 6. 检查结论

| 检查项 | 结论 |
|--------|------|
| 吞异常（空 catch / 静默成功） | ✅ 无。所有 catch 显式转错误码 |
| 假实现（固定返回 / stub / 空实现） | ✅ 无。生产路径真实调用 SDK |
| 危险 API 规避（get_model_list UAF） | ✅ 已规避并有据可依 |
| timeout 语义 | ✅ TD-A-005-01 Wontfix + 本 PR 挂死恢复补强 |
| 测试覆盖 | ✅ C++ 6 套 + Python 映射/恢复测试 |

---
*检查人：A 轨（opencode，2026-09-01）｜依据：源码核对 + evidence/l2-kylin-vm/ 历史证据*
