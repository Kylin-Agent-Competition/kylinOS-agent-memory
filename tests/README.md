# Tests

自动化测试根目录。

## 当前状态

**仅建立目录和职责边界，尚无测试代码。**

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
└── conftest.py
```
