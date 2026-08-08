# 08 轨道 A — Day4 Bridge/Provider 工程骨架

> **文档状态：作者自报（麒麟 VM 第七轮 L2 全绿 FAILURES=0，待 Reviewer 验证）** — 工程骨架 + 最小真实 SDK 调用已验证；构建/C++/导入/异常映射/失败恢复/冒烟/幂等测试全部通过麒麟 VM 实测。权威证据见 `evidence/l2-kylin-vm/day4_verify_latest.log`（EMBED-CALL-003，第七轮）；历史证据 `day4_bridge_smoke_run.log` 已标记 HISTORICAL / SUPERSEDED。

## 目标

1. 创建 cpp-bridge、pybind11 和 EmbeddingProvider 工程骨架。
2. 接入最小真实 SDK 调用。
3. 建立编译、导入和异常映射测试。

## 新增文件

| 文件 | 说明 |
|------|------|
| `cpp-bridge/include/embedding_bridge.h` | Bridge 类声明 + EmbeddingVector + SDK 符号表 |
| `cpp-bridge/src/embedding_bridge.cpp` | dlopen→dlsym→create/init→embed→destroy 最小真实调用 |
| `cpp-bridge/src/py_module.cpp` | pybind11 绑定 + 11 类 Python 异常映射（含 BridgeSessionDestroyedError / BridgeFatalError） |
| `cpp-bridge/CMakeLists.txt` | pybind11 + core static lib 构建 |
| `cpp-bridge/tests/CMakeLists.txt` | 6 个 C++ 测试注册（含 dlsym 缺失变体假 .so） |
| `cpp-bridge/tests/test_bridge_errors.cpp` | 错误码映射测试（不依赖 SDK） |
| `cpp-bridge/tests/test_bridge_so_not_found.cpp` | .so 不存在 → ERR_SO_NOT_FOUND（不依赖 SDK） |
| `cpp-bridge/tests/fake_sdk_malformed.c` | 可控假 SDK .so（P0-2 畸形结果防御测试） |
| `cpp-bridge/tests/test_bridge_malformed.cpp` | 畸形结果防御测试（null/dim0/datnull/nan/inf） |
| `memory-service/providers/embedding_provider.py` | EmbeddingProvider v1（Day3 契约接口 + Provider 错误映射） |
| `memory-service/providers/__init__.py` | providers 包 |
| `memory-service/tests/test_embedding_provider_import.py` | 导入与契约测试（pytest 风格，本地可跑） |
| `memory-service/tests/test_exception_mapping.py` | 异常映射测试（pytest 风格，需 kylin_embedding 模块） |
| `memory-service/tests/test_load_idempotent.py` | load/create_session 幂等测试（pytest 风格，需麒麟 VM） |
| `memory-service/tests/run_smoke.py` | 麒麟 VM 集成冒烟测试 |

## 依赖基线（全部来自 main 已有证据）

| 依赖 | 来源 |
|------|------|
| `cpp-bridge/embedding_abi_compat.h` | Day1（已合并 main） |
| `cpp-bridge/bridge_error_contract.h` | Day3（已合并 main） |
| 默认模型 ensemble-embd_gte-base_uint8-text | Day2 运行日志 |
| 空串/空白行为、2170 bytes 上限 | Day2 测试文档 |
| .so 路径/SHA-256/Build ID | Day1 ABI 符号日志 |

## 测试层级

| 层级 | 覆盖 | 运行环境 |
|------|------|---------|
| L0-1 | `test_bridge_errors.cpp` 错误映射 | 任意（无需 SDK） |
| L0-2 | `test_bridge_so_not_found.cpp` | 任意（无需 SDK） |
| L0-3 | `test_bridge_malformed.cpp` 畸形结果防御（P0-2） | 任意（假 .so） |
| L0-4 | `test_bridge_destroyed.cpp` destroy 终态（P0-2/P1-1） | 任意（假 .so） |
| L0-5 | `test_bridge_failure_recovery.cpp` 失败恢复策略（P1-High） | 任意（假 .so） |
| L0-6 | `test_bridge_dlsym_missing.cpp` dlsym 缺失终态（P1-High/P1-3） | 任意（符号缺失假 .so） |
| L0-7 | `test_embedding_provider_import.py` 导入/契约（pytest） | WSL/任意 |
| L0-8 | `test_provider_failure_recovery.py` Provider 失败恢复 + 错误分类（pytest，mock 假 Bridge，P1-1/P1-2/P1-3） | WSL/任意（不依赖真实 .so） |
| L1-1 | `test_exception_mapping.py` 异常映射（pytest，含 BridgeSessionDestroyedError/BridgeFatalError 断言） | 麒麟 VM（需编译模块） |
| L1-2 | `test_load_idempotent.py` 生命周期状态机（pytest） | 麒麟 VM（需真实 .so） |
| L1-3 | `test_interpreter_exit.py` 解释器退出析构（pytest） | 麒麟 VM |
| L2 | `run_smoke.py` 真实 SDK 调用 | 麒麟 VM |

## 构建步骤（麒麟 VM）

```bash
# 标准入口（P1-8：唯一标准复现命令，内部含构建/CTest/pytest/冒烟/生命周期）
bash scripts/verify_day4_vm.sh
```

> 说明：手动执行 pytest 时必须拆成独立进程（脚本 Step 4 的做法）：
> `test_embedding_provider_import.py` + `test_exception_mapping.py` + `test_provider_failure_recovery.py`
> 一组（a 组，failure_recovery 用 mock 假 Bridge 不依赖真实 SDK，WSL 可跑），
> `test_load_idempotent.py` 单独一组（b 组，真实 SDK），`test_interpreter_exit.py` 一组（c 组，子进程）。
> 麒麟实测 SDK 在同一进程内与异常映射测试共存会触发 Abort，且 create_session 后未 embed 直接销毁
> 也会崩溃（P0-1 已修复：destroy_session 不再 dlclose，.so 进程内只加载一次）。
> P1-2：`test_provider_failure_recovery.py` 已改为 fixture 注入假模块并恢复 sys.modules，
> 不污染其他测试文件（顺序无关，全量单进程 pytest 结果稳定）。

手动构建（可选，供调试）:
```bash
cd cpp-bridge
python -m pip install pybind11
cmake -B build -Dpybind11_DIR=$(python -m pybind11 --cmakedir)
cmake --build build
ctest --test-dir build --output-on-failure   # C++ 测试
```

## 已知限制（关联 TD）

- `timeout_ms` 当前透传保留，未实现主动超时中断 → [TD-A-005-01]
- `embed_batch` 为顺序调用，并行策略未定 → [TD-A-005-02]
- `get_dimension` 首次调用用空串触发，依赖空串返回 768 → [TD-A-005-03]
- `model_info.name` 硬编码默认模型名 → [TD-A-005-04]
- `model_info.loaded` 临时语义（get_dimension 成功即代表可用） → [TD-A-005-05]
- 异步接口未接入

## Provider 错误映射（P1-1）

Provider 层将 Bridge 异常映射为 Day3 契约的 Provider 错误码，不向 Service 层暴露 Bridge 细节：

| Bridge 异常 | Provider 错误码 |
|------------|----------------|
| BridgeSoNotFoundError / BridgeLoadError / BridgeSymbolError | ERR_SDK_NOT_LOADED |
| BridgeSessionError | ERR_SESSION_FAILED |
| BridgeSessionDestroyedError | ERR_SESSION_DESTROYED（P1-1：Bridge destroy 终态独立映射） |
| BridgeFatalError | ERR_FATAL_FAILURE（P1-1：fatal 终态后重试，需进程重启） |
| BridgeEmbedError | ERR_EMBED_FAILED |
| BridgeSdkError | ERR_SDK_ERROR |
| BridgeModelError | ERR_MODEL_INVALID（P1-3：模型错误独立映射，不归入普通 SDK 错误） |
| BridgeTimeoutError / BridgeCancelledError | ERR_TIMEOUT |
| （应用层校验） | ERR_INVALID_TEXT |

## 异常映射约定

| BridgeError | Python 异常 |
|------------|------------|
| ERR_SO_NOT_FOUND | BridgeSoNotFoundError |
| ERR_DLOPEN_FAILED | BridgeLoadError |
| ERR_DLSYM_FAILED | BridgeSymbolError |
| ERR_SESSION_CREATE / ERR_SESSION_INIT / ERR_SESSION_DESTROY | BridgeSessionError |
| ERR_SESSION_DESTROYED | BridgeSessionDestroyedError（P1-1 专用异常） |
| ERR_FATAL_FAILURE | BridgeFatalError（P1-High/P1-1 专用异常） |
| ERR_EMBED_CALL/RESULT | BridgeEmbedError |
| ERR_EMBED_ERROR | BridgeSdkError |
| ERR_TIMEOUT | BridgeTimeoutError |
| ERR_CANCELLED | BridgeCancelledError |
| ERR_MODEL_* | BridgeModelError |
| 其他 | BridgeError（基类） |
