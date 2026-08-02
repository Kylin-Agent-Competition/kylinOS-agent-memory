# Tests

自动化测试根目录。

## 当前状态

已建立目录和职责边界，并包含 D1/D2 Vector Engine 探针与安全回归。
`tests/vector-engine/run_d2_vector_smoke_safety_test.sh` 覆盖数据库路径、
Collection 命名、Manifest 身份、直接绕过 cleanup、重复 cleanup 和 stale
Manifest 等门禁；同时覆盖 C++ 对真实二进制、InvocationID、engine DB 与
Socket 所有者的校验，以及双进程并发 cleanup 只有一个进程可进入探针。
真实数据面仍只在麒麟 VM 中执行。

## 测试层级说明

| 层级 | 说明 | 环境 |
|------|------|------|
| L0 | 单元测试、静态检查 | WSL2 / CI |
| L1 | 组件集成测试 | WSL2 |
| L2 | Runtime Test | 麒麟 VM |
| L3 | 全链路验收 | 麒麟 VM 干净快照 |

## 未来主要目录

```
tests/
├── memory-service/
├── cpp-bridge/
├── memory-client/
├── integration/
├── vector-engine/
└── conftest.py
```
