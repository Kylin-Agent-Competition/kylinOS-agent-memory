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
| `cpp-bridge/tests/CMakeLists.txt` | 2 个 C++ 测试注册 |
| `cpp-bridge/tests/test_bridge_errors.cpp` | 错误码映射测试（不依赖 SDK） |
| `cpp-bridge/tests/test_bridge_so_not_found.cpp` | .so 不存在 → ERR_SO_NOT_FOUND（不依赖 SDK） |
| `memory-service/providers/embedding_provider.py` | EmbeddingProvider v1（Day3 契约接口） |
| `memory-service/providers/__init__.py` | providers 包 |
| `memory-service/tests/test_embedding_provider_import.py` | 导入与契约测试（本地可跑） |
| `memory-service/tests/test_exception_mapping.py` | 异常映射测试（需 kylin_embedding 模块） |
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
| L0-3 | `test_embedding_provider_import.py` 导入/契约 | WSL/任意 |
| L1-1 | `test_exception_mapping.py` 异常映射 | 麒麟 VM（需编译模块） |
| L2 | `run_smoke.py` 真实 SDK 调用 | 麒麟 VM |

## 构建步骤（麒麟 VM）

```bash
cd cpp-bridge
python -m pip install pybind11
cmake -B build -Dpybind11_DIR=$(python -m pybind11 --cmakedir)
cmake --build build
ctest --test-dir build --output-on-failure   # C++ 测试

# 导入 + 异常映射测试
PYTHONPATH=build:../memory-service python ../memory-service/tests/test_exception_mapping.py

# 真实 SDK 冒烟
PYTHONPATH=build:../memory-service \
LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH \
python ../memory-service/tests/run_smoke.py
```

## 已知限制

- `timeout_ms` 当前透传保留，未实现主动超时中断（Day5）
- `embed_batch` 为顺序调用，并行策略未定（Day5）
- `get_dimension` 首次调用用空串触发，依赖空串返回 768（Day2 已实测）
- `model_info.name` 硬编码默认模型名（精确 get_model_list 未实现）
- 异步接口未接入

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
