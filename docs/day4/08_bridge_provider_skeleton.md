# 08 轨道 A — Day4 Bridge/Provider 工程骨架

> **文档状态：作者自报（麒麟 VM 实测通过，待 Reviewer 验证）** — 工程骨架 + 最小真实 SDK 调用已验证；构建/C++/导入/异常映射/冒烟/幂等测试全部通过麒麟 VM 实测。证据见 `evidence/l2-kylin-vm/day4_bridge_smoke_run.log`。

## 目标

1. 创建 cpp-bridge、pybind11 和 EmbeddingProvider 工程骨架。
2. 接入最小真实 SDK 调用。
3. 建立编译、导入和异常映射测试。

## 新增文件

| 文件 | 说明 |
|------|------|
| `cpp-bridge/include/embedding_bridge.h` | Bridge 类声明 + EmbeddingVector + SDK 符号表 |
| `cpp-bridge/src/embedding_bridge.cpp` | dlopen→dlsym→create/init→embed→destroy 最小真实调用 |
| `cpp-bridge/src/py_module.cpp` | pybind11 绑定 + 9 类 Python 异常映射 |
| `cpp-bridge/CMakeLists.txt` | pybind11 + core static lib 构建 |
| `cpp-bridge/tests/CMakeLists.txt` | 3 个 C++ 测试注册 |
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
| L0-4 | `test_embedding_provider_import.py` 导入/契约（pytest） | WSL/任意 |
| L1-1 | `test_exception_mapping.py` 异常映射（pytest） | 麒麟 VM（需编译模块） |
| L1-2 | `test_load_idempotent.py` 幂等（pytest） | 麒麟 VM（需真实 .so） |
| L2 | `run_smoke.py` 真实 SDK 调用 | 麒麟 VM |

## 构建步骤（麒麟 VM）

```bash
cd cpp-bridge
python -m pip install pybind11
cmake -B build -Dpybind11_DIR=$(python -m pybind11 --cmakedir)
cmake --build build
ctest --test-dir build --output-on-failure   # C++ 测试

# 导入 + 异常映射 + 幂等测试（pytest 统一收集）
PYTHONPATH=build:../memory-service \
LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH \
python -m pytest ../memory-service/tests/test_embedding_provider_import.py \
  ../memory-service/tests/test_exception_mapping.py \
  ../memory-service/tests/test_load_idempotent.py -v

# 真实 SDK 冒烟
PYTHONPATH=build:../memory-service \
LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH \
python ../memory-service/tests/run_smoke.py
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
| BridgeEmbedError | ERR_EMBED_FAILED |
| BridgeSdkError / BridgeModelError | ERR_SDK_ERROR |
| BridgeTimeoutError / BridgeCancelledError | ERR_TIMEOUT |
| （应用层校验） | ERR_INVALID_TEXT |

## 异常映射约定

| BridgeError | Python 异常 |
|------------|------------|
| ERR_SO_NOT_FOUND | BridgeSoNotFoundError |
| ERR_DLOPEN_FAILED | BridgeLoadError |
| ERR_DLSYM_FAILED | BridgeSymbolError |
| ERR_SESSION_* | BridgeSessionError |
| ERR_EMBED_CALL/RESULT | BridgeEmbedError |
| ERR_EMBED_ERROR | BridgeSdkError |
| ERR_TIMEOUT | BridgeTimeoutError |
| ERR_CANCELLED | BridgeCancelledError |
| ERR_MODEL_* | BridgeModelError |
| 其他 | BridgeError（基类） |
